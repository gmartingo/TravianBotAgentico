"""
Use cases de farm lists.

Implementa toda la lógica de negocio descrita en el spec (secciones 4, 5, 9):
  - ReadFarmListsUseCase       — navega + lee DOM + sincroniza en BD.
  - GetFarmListsUseCase        — consulta BD por mundo.
  - ProcessFarmListUseCase     — ciclo inteligente de envío con cooldown y backoff.
  - SendSchedulerGroupUseCase  — procesa todas las listas de un scheduler.
  - SendFarmListUseCase        — envío manual de una lista.
  - ActivateSlotInTravianUseCase — activa slot + registra REACTIVATED si procede.
  - DeactivateSlotInTravianUseCase — desactiva slot (sin tocar disabled_by_bot).
  - DisableSlotByBotUseCase    — toggle Bot→excluir.
  - EnableSlotByBotUseCase     — toggle Bot→incluir.
  - CancelProbeUseCase         — cancela sonda pendiente (mode: deactivate|send_now).

Las constantes de negocio se definen aquí (no en la capa de API ni en la BD).
"""
from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from core.entities.farm_list import FarmList, FarmSlot, SlotEvent
from core.entities.farm_list_send_event import FarmListSendEvent
from core.entities.village import Village
from core.ports.farm_list_browser_port import FarmListBrowserPort
from core.ports.farm_list_db_port import FarmListDbPort

logger = logging.getLogger(__name__)

# Pausa variable entre el envío de farm lists del mismo grupo (anti-detección, RN-03).
_GROUP_GAP_MIN_SECONDS = 2.0
_GROUP_GAP_MAX_SECONDS = 5.0

# Cooldown base al detectar pérdidas (RN-05).
_BASE_COOLDOWN_SECONDS = 3600       # 1 hora
# Cooldown máximo de sonda (EC-09).
_MAX_COOLDOWN_SECONDS  = 86_400     # 24 horas


# ---------------------------------------------------------------------------
# Helpers de evaluación de estado de slot
# ---------------------------------------------------------------------------

def _won_without_losses(last_raid_state: str) -> bool:
    """True si el último raid se ganó sin pérdidas de tropas."""
    return "withoutLosses" in last_raid_state


def _had_losses(last_raid_state: str) -> bool:
    """True si el último raid tuvo pérdidas (victoria con pérdidas o derrota)."""
    return "withLosses" in last_raid_state or "lost" in last_raid_state


def _has_new_raid(slot: FarmSlot) -> bool:
    """True si llegó un raid nuevo después de que el bot desactivara el slot."""
    return bool(
        slot.report_id_at_disable
        and slot.last_raid_report_id
        and slot.last_raid_report_id != slot.report_id_at_disable
    )


def _cooldown_expired(slot: FarmSlot) -> bool:
    """True si el timer de cooldown ha expirado. False si disabled_at es None."""
    if slot.disabled_at is None:
        return False
    elapsed = (datetime.utcnow() - slot.disabled_at).total_seconds()
    return elapsed >= slot.cooldown_seconds


def _make_slot_event(
    event_type: str,
    slot: FarmSlot,
    farm_list: FarmList,
    world_id: int,
    now: datetime,
    cooldown_seconds: int,
) -> SlotEvent:
    return SlotEvent(
        id=0,
        timestamp=now,
        slot_id=slot.id,
        slot_name=slot.target_name,
        farm_list_id=farm_list.id,
        farm_list_name=farm_list.name,
        world_id=world_id,
        event_type=event_type,
        last_raid_state=slot.last_raid_state,
        cooldown_seconds=cooldown_seconds,
        last_raid_report_id=slot.last_raid_report_id,
    )


# ---------------------------------------------------------------------------
# Use cases
# ---------------------------------------------------------------------------

@dataclass
class ReadFarmListsUseCase:
    """
    Navega a la plaza de reuniones, lee todas las listas de vacas del DOM
    (agrupadas por aldea), las empareja con las aldeas de la BD por nombre
    y sincroniza cada grupo.

    EC-01: si una aldea del DOM no está en BD, loguea warning y omite.
    """
    browser: FarmListBrowserPort
    db: FarmListDbPort

    async def execute(self, world_id: int) -> list[FarmList]:
        villages = await self.db.get_villages_by_world(world_id)
        village_by_name: dict[str, Village] = {v.name: v for v in villages}
        village_by_id: dict[int, Village] = {v.id: v for v in villages}

        raw_lists = await self.browser.read_farm_lists()

        lists_by_village: dict[int, list[FarmList]] = {}
        for fl in raw_lists:
            village = village_by_name.get(fl.village_name)
            if village is None:
                if fl.village_data_id > 0:
                    village = await self.db.upsert_village(
                        world_id, fl.village_data_id, fl.village_name
                    )
                    village_by_name[village.name] = village
                    village_by_id[village.id] = village
                    logger.info(
                        "Aldea '%s' (data_id=%d) creada en BD automáticamente",
                        fl.village_name, fl.village_data_id,
                    )
                else:
                    logger.warning(
                        "Lista '%s' (id=%d): aldea '%s' sin data_id en el DOM — se omite",
                        fl.name, fl.id, fl.village_name,
                    )
                    continue
            fl.owner_village_id = village.id
            lists_by_village.setdefault(village.id, []).append(fl)

        result: list[FarmList] = []
        for village_id, fls in lists_by_village.items():
            synced = await self.db.sync_farm_lists(village_id, fls)
            village = village_by_id[village_id]
            for fl in synced:
                fl.village_name = village.name
                fl.village_x = village.x
                fl.village_y = village.y
            result.extend(synced)

        return result


@dataclass
class GetFarmListsUseCase:
    """Devuelve todas las farm lists de un mundo con sus slots."""
    db: FarmListDbPort

    async def execute(self, world_id: int) -> list[FarmList]:
        villages = await self.db.get_villages_by_world(world_id)
        village_by_id = {v.id: v for v in villages}
        farm_lists = await self.db.get_farm_lists_by_world(world_id)
        for fl in farm_lists:
            village = village_by_id.get(fl.owner_village_id)
            if village:
                fl.village_name = village.name
                fl.village_x = village.x
                fl.village_y = village.y
        return farm_lists


@dataclass
class ProcessFarmListUseCase:
    """
    Ciclo de envío inteligente de UNA farm list con cooldown y backoff exponencial.

    1. Lee la lista actual de Travian y sincroniza en BD.
    2. Para cada slot evalúa:
       - Desactivado manualmente → no toca (RN-04).
       - Pérdidas en slot activo (no procesadas todavía) → desactivar, iniciar timer BASE (RN-05).
       - Desactivado por bot + raid nuevo limpio → reactivar (RN-06).
       - Desactivado por bot + raid nuevo con pérdidas → actualizar report_id (RN-07).
       - Desactivado por bot + cooldown expirado + sin raid nuevo → sonda (RN-08).
    3. Envía la lista (las sondas salen incluidas).
    4. Desactiva sondas y duplica cooldown (RN-08, EC-09).
    """
    browser: FarmListBrowserPort
    db: FarmListDbPort

    async def execute(self, farm_list_id: int, world_id: int) -> None:
        now = datetime.utcnow()
        fresh  = await self.browser.read_farm_list(farm_list_id)
        synced = await self.db.sync_farm_list(fresh)

        probe_slot_ids: list[int] = []
        bot_disabled_slot_names: list[str] = []

        for slot in synced.slots:
            # RN-04: slot desactivado manualmente → el bot no lo toca.
            if not slot.is_active and not slot.disabled_by_bot:
                continue

            # RN-09: guard de losses_already_seen.
            losses_already_seen = bool(
                slot.report_id_at_disable
                and slot.last_raid_report_id == slot.report_id_at_disable
            )

            if _had_losses(slot.last_raid_state) and not slot.disabled_by_bot and not losses_already_seen:
                # CASO 1: slot activo con pérdidas → desactivar (RN-05).
                logger.info(
                    "Vaca %d ('%s'): pérdidas → desactivando, cooldown %ds",
                    slot.id, slot.target_name, _BASE_COOLDOWN_SECONDS,
                )
                bot_disabled_slot_names.append(slot.target_name)
                await self.browser.deactivate_slot_in_travian(slot.id, farm_list_id)
                await self.db.update_slot_cooldown_state(
                    slot.id, farm_list_id,
                    disabled_at=now,
                    cooldown_seconds=_BASE_COOLDOWN_SECONDS,
                    report_id_at_disable=slot.last_raid_report_id,
                    disabled_by_bot=True,
                    is_active=False,
                )
                await self.db.add_slot_event(
                    _make_slot_event("LOSSES_DETECTED", slot, synced, world_id, now, _BASE_COOLDOWN_SECONDS)
                )

            elif slot.disabled_by_bot:
                # CASO 2: desactivado por bot.
                new_raid = _has_new_raid(slot)

                if new_raid and _won_without_losses(slot.last_raid_state):
                    # Sub-caso 2a: informe nuevo limpio → reactivar (RN-06).
                    logger.info(
                        "Vaca %d ('%s'): raid limpio tras desactivación → reactivando",
                        slot.id, slot.target_name,
                    )
                    await self.browser.activate_slot_in_travian(slot.id, farm_list_id)
                    await self.db.update_slot_cooldown_state(
                        slot.id, farm_list_id,
                        disabled_at=None,
                        cooldown_seconds=_BASE_COOLDOWN_SECONDS,
                        report_id_at_disable="",
                        disabled_by_bot=False,
                        is_active=True,
                    )
                    await self.db.add_slot_event(
                        _make_slot_event("REACTIVATED", slot, synced, world_id, now, _BASE_COOLDOWN_SECONDS)
                    )

                elif new_raid and _had_losses(slot.last_raid_state):
                    # Sub-caso 2b: sonda o raid in-flight con pérdidas → actualizar report_id (RN-07).
                    logger.info(
                        "Vaca %d ('%s'): nuevo raid con pérdidas — actualizando report_id",
                        slot.id, slot.target_name,
                    )
                    await self.db.update_slot_cooldown_state(
                        slot.id, farm_list_id,
                        disabled_at=slot.disabled_at,
                        cooldown_seconds=slot.cooldown_seconds,
                        report_id_at_disable=slot.last_raid_report_id,
                        disabled_by_bot=True,
                        is_active=False,
                    )

                elif not new_raid and _cooldown_expired(slot):
                    # Sub-caso 2c: cooldown expirado sin informe nuevo → sonda (RN-08).
                    logger.info(
                        "Vaca %d ('%s'): cooldown expirado → enviando sonda",
                        slot.id, slot.target_name,
                    )
                    await self.browser.activate_slot_in_travian(slot.id, farm_list_id)
                    probe_slot_ids.append(slot.id)
                # else: cooldown aún activo y sin informe nuevo → no hacer nada.

        # Enviar la lista (las sondas salen incluidas) y registrar en historial.
        send_result = await self.browser.send_farm_list(farm_list_id)
        await self.db.add_farm_list_send_event(FarmListSendEvent(
            farm_list_id=farm_list_id,
            farm_list_name=synced.name,
            world_id=world_id,
            timestamp=now,
            status=send_result.status,
            being_raided_current=send_result.being_raided_current,
            being_raided_total=send_result.being_raided_total,
            triggered_by="scheduler",
            scheduler_id=synced.scheduler_id,
            bot_disabled_slots=bot_disabled_slot_names,
        ))
        logger.info(
            "Farm list %d ('%s'): estado=%s raideando=%d/%d",
            farm_list_id, synced.name,
            send_result.status,
            send_result.being_raided_current,
            send_result.being_raided_total,
        )

        # Desactivar sondas inmediatamente tras el send y duplicar cooldown (RN-08).
        for slot_id in probe_slot_ids:
            slot = next(s for s in synced.slots if s.id == slot_id)
            new_cooldown = min(slot.cooldown_seconds * 2, _MAX_COOLDOWN_SECONDS)
            await self.browser.deactivate_slot_in_travian(slot_id, farm_list_id)
            await self.db.update_slot_cooldown_state(
                slot_id, farm_list_id,
                disabled_at=now,
                cooldown_seconds=new_cooldown,
                report_id_at_disable=slot.last_raid_report_id,
                disabled_by_bot=True,
                is_active=False,
            )
            await self.db.add_slot_event(
                _make_slot_event("PROBE_SENT", slot, synced, world_id, now, new_cooldown)
            )
            logger.info("Vaca %d: sonda enviada, cooldown siguiente=%ds", slot_id, new_cooldown)

        logger.info("Farm list %d procesada y enviada", farm_list_id)


@dataclass
class SendSchedulerGroupUseCase:
    """
    Procesa todas las farm lists de un scheduler con el ciclo inteligente
    (ProcessFarmListUseCase), con una pausa variable entre listas (anti-detección).

    EC-03: si el scheduler no tiene farm lists asignadas, devuelve 0 sin hacer nada.
    El fallo de una lista individual no detiene las demás (spec sección 11).
    """
    browser: FarmListBrowserPort
    db: FarmListDbPort

    async def execute(self, scheduler_id: int) -> int:
        scheduler = await self.db.get_scheduler(scheduler_id)
        farm_list_ids = scheduler.farm_list_ids
        if not farm_list_ids:
            logger.info(
                "Scheduler %d no tiene farm lists asignadas — nada que enviar", scheduler_id
            )
            return 0

        processor = ProcessFarmListUseCase(browser=self.browser, db=self.db)
        processed = 0
        for i, farm_list_id in enumerate(farm_list_ids):
            try:
                await processor.execute(farm_list_id, world_id=scheduler.world_id)
                processed += 1
            except Exception:
                logger.exception(
                    "Fallo procesando la farm list %d del scheduler %d",
                    farm_list_id, scheduler_id,
                )
            # Pausa entre listas (anti-detección, RN-03) — salvo la última.
            if i < len(farm_list_ids) - 1:
                await asyncio.sleep(
                    random.uniform(_GROUP_GAP_MIN_SECONDS, _GROUP_GAP_MAX_SECONDS)
                )

        logger.info(
            "Scheduler %d: %d/%d farm lists procesadas",
            scheduler_id, processed, len(farm_list_ids),
        )
        return processed


@dataclass
class SendFarmListUseCase:
    """
    Envío manual de una farm list. No ejecuta el ciclo de pérdidas/sondas —
    solo pulsa Start y registra el evento con triggered_by="manual".
    """
    browser: FarmListBrowserPort
    db: FarmListDbPort
    world_id: int

    async def execute(self, farm_list_id: int) -> FarmListSendEvent:
        farm_list = await self.db.get_farm_list_by_id(farm_list_id)
        result = await self.browser.send_farm_list(farm_list_id)
        now = datetime.utcnow()
        event = FarmListSendEvent(
            farm_list_id=farm_list_id,
            farm_list_name=farm_list.name,
            world_id=self.world_id,
            timestamp=now,
            status=result.status,
            being_raided_current=result.being_raided_current,
            being_raided_total=result.being_raided_total,
            triggered_by="manual",
        )
        await self.db.add_farm_list_send_event(event)
        return event


@dataclass
class ActivateSlotInTravianUseCase:
    """
    Toggle Travian→on: activa la vaca en Travian y limpia disabled_by_bot.
    Registra REACTIVATED si el slot estaba desactivado por el bot (RN-10).
    """
    browser: FarmListBrowserPort
    db: FarmListDbPort

    async def execute(self, slot_id: int, farm_list_id: int, world_id: int) -> FarmSlot:
        slot = await self.db.get_slot_by_id(slot_id, farm_list_id)
        was_disabled_by_bot = slot.disabled_by_bot
        await self.browser.activate_slot_in_travian(slot_id, farm_list_id)
        updated = await self.db.update_slot_flags(
            slot_id, farm_list_id, is_active=True, disabled_by_bot=False
        )
        if was_disabled_by_bot:
            farm_list = await self.db.get_farm_list_by_id(farm_list_id)
            await self.db.add_slot_event(
                _make_slot_event(
                    "REACTIVATED", slot, farm_list, world_id,
                    datetime.utcnow(), _BASE_COOLDOWN_SECONDS,
                )
            )
        return updated


@dataclass
class DeactivateSlotInTravianUseCase:
    """Toggle Travian→off: desactiva la vaca en Travian. No toca disabled_by_bot."""
    browser: FarmListBrowserPort
    db: FarmListDbPort

    async def execute(self, slot_id: int, farm_list_id: int) -> FarmSlot:
        await self.browser.deactivate_slot_in_travian(slot_id, farm_list_id)
        return await self.db.update_slot_flags(slot_id, farm_list_id, is_active=False)


@dataclass
class DisableSlotByBotUseCase:
    """Toggle Bot→excluir: desactiva la vaca en Travian y marca disabled_by_bot=True."""
    browser: FarmListBrowserPort
    db: FarmListDbPort

    async def execute(self, slot_id: int, farm_list_id: int) -> FarmSlot:
        await self.browser.deactivate_slot_in_travian(slot_id, farm_list_id)
        return await self.db.update_slot_flags(
            slot_id, farm_list_id, is_active=False, disabled_by_bot=True
        )


@dataclass
class EnableSlotByBotUseCase:
    """Toggle Bot→incluir: activa la vaca en Travian y limpia disabled_by_bot."""
    browser: FarmListBrowserPort
    db: FarmListDbPort

    async def execute(self, slot_id: int, farm_list_id: int) -> FarmSlot:
        await self.browser.activate_slot_in_travian(slot_id, farm_list_id)
        return await self.db.update_slot_flags(
            slot_id, farm_list_id, is_active=True, disabled_by_bot=False
        )


@dataclass
class CancelProbeUseCase:
    """
    Cancela la sonda pendiente de un slot. Dos modos (RN-16):
    - 'deactivate' (default): para el countdown indefinidamente; la vaca queda
      desactivada como si el usuario la hubiera apagado (disabled_by_bot=False →
      el bot no la gestiona). Registra PROBE_CANCELLED.
    - 'send_now': expira el cooldown para que el próximo ciclo del bot envíe la sonda.
      No registra evento (el timer está expirado pero la sonda no se ha enviado aún).

    EC-16: si el slot no tiene disabled_by_bot=True, el use case lo ejecuta igualmente
    pero no registra PROBE_CANCELLED (no hay sonda activa que cancelar). La validación
    400 se hace en el endpoint.
    """
    db: FarmListDbPort

    async def execute(
        self,
        slot_id: int,
        farm_list_id: int,
        world_id: int,
        mode: str = "deactivate",
    ) -> FarmSlot:
        slot = await self.db.get_slot_by_id(slot_id, farm_list_id)
        farm_list = await self.db.get_farm_list_by_id(slot.farm_list_id)
        now = datetime.utcnow()

        if mode == "send_now":
            # Expirar el cooldown para que el próximo ciclo del bot envíe la sonda.
            updated = await self.db.update_slot_cooldown_state(
                slot_id, farm_list_id,
                disabled_at=now - timedelta(seconds=slot.cooldown_seconds + 1),
                cooldown_seconds=slot.cooldown_seconds,
                report_id_at_disable=slot.report_id_at_disable,
                disabled_by_bot=True,
                is_active=False,
            )
        else:
            # mode == "deactivate": la vaca queda apagada como si el usuario la
            # hubiera apagado manualmente (disabled_by_bot=False → bot no la gestiona).
            updated = await self.db.update_slot_cooldown_state(
                slot_id, farm_list_id,
                disabled_at=None,
                cooldown_seconds=_BASE_COOLDOWN_SECONDS,
                report_id_at_disable=slot.last_raid_report_id,
                disabled_by_bot=False,
                is_active=False,
            )
            if slot.disabled_by_bot:
                await self.db.add_slot_event(
                    _make_slot_event("PROBE_CANCELLED", slot, farm_list, world_id, now, 0)
                )
        return updated
