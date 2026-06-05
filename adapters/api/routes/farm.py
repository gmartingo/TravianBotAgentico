"""
Router FastAPI para farm lists.

Endpoints (prefijo /farm — spec sección 8):

  8.1 Schedulers
    GET  /farm/worlds/{world_id}/schedulers                             → 200 [FarmScheduler]
    POST /farm/worlds/{world_id}/schedulers                             → 201 FarmScheduler
    PUT  /farm/worlds/{world_id}/schedulers/{scheduler_id}              → 200 FarmScheduler
    DELETE /farm/worlds/{world_id}/schedulers/{scheduler_id}            → 204
    PUT  /farm/worlds/{world_id}/schedulers/{scheduler_id}/farm-lists   → 200 FarmScheduler

  8.2 Farm Lists
    GET  /farm/worlds/{world_id}/farm-lists                             → 200 [FarmList]
    POST /farm/worlds/{world_id}/farm-lists/read                        → 200 [FarmList]

  8.3 Slots
    POST /farm/slots/{slot_id}/activate                                 → 200 FarmSlot
    POST /farm/slots/{slot_id}/deactivate                               → 200 FarmSlot
    POST /farm/slots/{slot_id}/bot-disable                              → 200 FarmSlot
    POST /farm/slots/{slot_id}/bot-enable                               → 200 FarmSlot
    POST /farm/slots/{slot_id}/cancel-probe                             → 200 FarmSlot

  8.4 Envío manual
    POST /farm/farm-lists/{farm_list_id}/send                           → 200 FarmListSendEvent

  8.5 Historial
    GET  /farm/worlds/{world_id}/history                                → 200 paginado
    GET  /farm/worlds/{world_id}/slot-events                            → 200 paginado

  8.6 Control del agente
    POST /farm/worlds/{world_id}/agent/start                            → 200
    POST /farm/worlds/{world_id}/agent/stop                             → 200
    GET  /farm/worlds/{world_id}/agent/status                           → 200
    POST /farm/worlds/{world_id}/schedulers/{scheduler_id}/run-now      → 200

Convenciones:
  - Sin prefijo /api (el proxy de Vite lo retira).
  - Sin Accept-Language: datos de juego, no catálogo i18n (spec sección 3).
  - world_id siempre en la ruta.
  - Errores con {"detail": "<mensaje legible>"}.
  - Paginación: page/page_size (max 100) + envelope {items, page, page_size, total}.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from core.entities.farm_list import BotSlotStatus, FarmList, FarmSlot, SlotEvent
from core.entities.farm_list_send_event import FarmListSendEvent
from core.entities.farm_scheduler import FarmScheduler
from core.exceptions import (
    FarmListNotFoundError,
    FarmListPageError,
    FarmListSendError,
    FarmSlotNotFoundError,
    SchedulerNotFoundError,
    SessionNotActiveError,
)
from core.entities.farm_scheduler import SchedulerStats
from core.use_cases.farm_lists import (
    ActivateSlotInTravianUseCase,
    CancelProbeUseCase,
    DeactivateSlotInTravianUseCase,
    DisableSlotByBotUseCase,
    EnableSlotByBotUseCase,
    GetFarmListsUseCase,
    GetSchedulerStatsUseCase,
    ReadFarmListsUseCase,
    SendFarmListUseCase,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/farm", tags=["farm"])


# ---------------------------------------------------------------------------
# Helpers de acceso a app.state
# ---------------------------------------------------------------------------


def _get_farm_db(request: Request):
    """FarmListDbPort singleton (FarmListSQLiteAdapter)."""
    port = getattr(request.app.state, "farm_db_port", None)
    if port is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="farm_db_port no disponible — el servidor puede estar iniciándose.",
        )
    return port


def _get_farm_browser(request: Request, world_id: int):
    """
    LiveFarmListAdapter para el mundo indicado.
    Crea el adaptador on-demand si la sesión está activa (no requiere /agent/start previo).
    """
    get_or_create = getattr(request.app.state, "get_or_create_farm_browser", None)
    if get_or_create is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="farm_browser_adapters no disponible — el servidor puede estar iniciándose.",
        )
    return get_or_create(world_id)


def _get_world_agent(request: Request, world_id: int):
    """
    WorldAgent para el mundo indicado (puede ser None si no ha arrancado).
    app.state.world_agents es un dict[int, WorldAgent].
    """
    agents: dict = getattr(request.app.state, "world_agents", {})
    return agents.get(world_id)


# ---------------------------------------------------------------------------
# Helpers de serialización
# ---------------------------------------------------------------------------


def _serialize_scheduler(s: FarmScheduler) -> dict:
    return {
        "id": s.id,
        "world_id": s.world_id,
        "name": s.name,
        "interval_min_ms": s.interval_min_ms,
        "interval_max_ms": s.interval_max_ms,
        "is_enabled": s.is_enabled,
        "last_run": s.last_run.isoformat() if s.last_run else None,
        "next_run": s.next_run.isoformat() if s.next_run else None,
        "execution_count": s.execution_count,
        "farm_list_ids": s.farm_list_ids,
    }


def _serialize_slot(slot: FarmSlot) -> dict:
    return {
        "id": slot.id,
        "farm_list_id": slot.farm_list_id,
        "target_name": slot.target_name,
        "x": slot.x,
        "y": slot.y,
        "population": slot.population,
        "troops": slot.troops,
        "is_active": slot.is_active,
        "disabled_by_bot": slot.disabled_by_bot,
        "last_raid_state": slot.last_raid_state,
        "last_raid_time": slot.last_raid_time,
        "last_raid_report_id": slot.last_raid_report_id,
        "last_raid_bounty": slot.last_raid_bounty,
        "average_raid_bounty": slot.average_raid_bounty,
        "total_bounty": slot.total_bounty,
        "distance": slot.distance,
        "disabled_at": slot.disabled_at.isoformat() if slot.disabled_at else None,
        "cooldown_seconds": slot.cooldown_seconds,
        "report_id_at_disable": slot.report_id_at_disable,
    }


def _serialize_farm_list(
    fl: FarmList,
    last_send_time: datetime | None = None,
) -> dict:
    """
    Serializa una FarmList. last_send_time se pasa desde fuera (Gap A):
    es el MAX(timestamp) del historial de envíos, calculado por get_last_send_times_by_world.
    """
    active_slots = [s for s in fl.slots if s.is_active]
    total_bounty = sum(s.total_bounty for s in fl.slots)
    avg_bounty_per_send = (
        round(sum(s.average_raid_bounty for s in active_slots) / len(active_slots))
        if active_slots else 0
    )
    return {
        "id": fl.id,
        "name": fl.name,
        "owner_village_id": fl.owner_village_id,
        "village_name": fl.village_name,
        "village_x": fl.village_x,
        "village_y": fl.village_y,
        "scheduler_id": fl.scheduler_id,
        "slots": [_serialize_slot(s) for s in fl.slots],
        "total_bounty": total_bounty,
        "avg_bounty_per_send": avg_bounty_per_send,
        # Gap A: poblado desde el historial de envíos (RN-A01, RN-A02)
        "last_send_time": last_send_time.isoformat() if last_send_time else None,
    }


def _serialize_send_event(ev: FarmListSendEvent) -> dict:
    return {
        "id": ev.id,
        "farm_list_id": ev.farm_list_id,
        "farm_list_name": ev.farm_list_name,
        "world_id": ev.world_id,
        "sent_at": ev.timestamp.isoformat() if ev.timestamp else None,
        "status": ev.status,
        "slots_sent": ev.being_raided_current,
        "being_raided_total": ev.being_raided_total,
        "triggered_by": ev.triggered_by,
        "scheduler_id": ev.scheduler_id,
        # Gap B: metadata del scheduler en el momento del envío (RN-B01)
        "scheduler_name": ev.scheduler_name,
        "scheduler_interval_min_ms": ev.scheduler_interval_min_ms,
        "scheduler_interval_max_ms": ev.scheduler_interval_max_ms,
        "scheduler_execution_count": ev.scheduler_execution_count,
        "deactivated_slots": ev.bot_disabled_slots,
        "loot_wood": ev.loot_wood,
        "loot_clay": ev.loot_clay,
        "loot_iron": ev.loot_iron,
        "loot_crop": ev.loot_crop,
    }


def _serialize_scheduler_stats(stats: SchedulerStats) -> dict:
    """Serializa un SchedulerStats a dict (Gap D, sección 8.3)."""
    return {
        "scheduler_id": stats.scheduler_id,
        "scheduler_name": stats.scheduler_name,
        "world_id": stats.world_id,
        "execution_count": stats.execution_count,
        "last_send_time": stats.last_send_time.isoformat() if stats.last_send_time else None,
        "success_rate": stats.success_rate,
        "active_slots_avg": stats.active_slots_avg,
        "total_bounty": stats.total_bounty,
        "bounty_per_hour": stats.bounty_per_hour,
        "per_list": [
            {
                "farm_list_id": ls.farm_list_id,
                "farm_list_name": ls.farm_list_name,
                "last_send_time": ls.last_send_time.isoformat() if ls.last_send_time else None,
                "success_rate": ls.success_rate,
                "active_slots_avg": ls.active_slots_avg,
                "total_bounty": ls.total_bounty,
                "bounty_per_hour": ls.bounty_per_hour,
            }
            for ls in stats.per_list
        ],
    }


def _serialize_slot_event(ev: SlotEvent) -> dict:
    return {
        "id": ev.id,
        "timestamp": ev.timestamp.isoformat() if ev.timestamp else None,
        "slot_id": ev.slot_id,
        "slot_name": ev.slot_name,
        "farm_list_id": ev.farm_list_id,
        "farm_list_name": ev.farm_list_name,
        "world_id": ev.world_id,
        "event_type": ev.event_type,
        "last_raid_state": ev.last_raid_state,
        "cooldown_seconds": ev.cooldown_seconds,
        "last_raid_report_id": ev.last_raid_report_id,
    }


# ---------------------------------------------------------------------------
# Schemas de request (Pydantic)
# ---------------------------------------------------------------------------


class SchedulerCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    interval_min_ms: int = Field(..., ge=60_000, description="Mínimo 60000 ms (1 minuto)")
    interval_max_ms: int = Field(..., ge=60_000)
    is_enabled: bool = True

    def validate_intervals(self) -> None:
        if self.interval_min_ms > self.interval_max_ms:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="interval_min_ms no puede ser mayor que interval_max_ms",
            )


class AssignFarmListsRequest(BaseModel):
    farm_list_ids: list[int]


class SlotActionRequest(BaseModel):
    farm_list_id: int
    world_id: int


class CancelProbeRequest(BaseModel):
    farm_list_id: int
    world_id: int
    mode: str = Field(default="deactivate", pattern="^(deactivate|send_now)$")


class SendFarmListRequest(BaseModel):
    world_id: int


# ---------------------------------------------------------------------------
# 8.1 Schedulers
# ---------------------------------------------------------------------------


@router.get("/worlds/{world_id}/schedulers", summary="Lista schedulers de un mundo")
async def list_schedulers(world_id: int, request: Request) -> list[dict]:
    """Devuelve todos los schedulers de un mundo."""
    db = _get_farm_db(request)
    schedulers = await db.get_schedulers_by_world(world_id)
    return [_serialize_scheduler(s) for s in schedulers]


@router.post(
    "/worlds/{world_id}/schedulers",
    status_code=status.HTTP_201_CREATED,
    summary="Crea un scheduler",
)
async def create_scheduler(
    world_id: int, body: SchedulerCreateRequest, request: Request
) -> dict:
    """Crea un scheduler para el mundo indicado."""
    body.validate_intervals()
    db = _get_farm_db(request)
    scheduler = FarmScheduler(
        id=0,
        world_id=world_id,
        name=body.name,
        interval_min_ms=body.interval_min_ms,
        interval_max_ms=body.interval_max_ms,
        is_enabled=body.is_enabled,
    )
    created = await db.create_scheduler(scheduler)
    return _serialize_scheduler(created)


@router.put(
    "/worlds/{world_id}/schedulers/{scheduler_id}",
    summary="Actualiza un scheduler",
)
async def update_scheduler(
    world_id: int, scheduler_id: int, body: SchedulerCreateRequest, request: Request
) -> dict:
    """Actualiza nombre, intervalos e is_enabled de un scheduler."""
    body.validate_intervals()
    db = _get_farm_db(request)
    try:
        existing = await db.get_scheduler(scheduler_id)
    except SchedulerNotFoundError:
        raise HTTPException(status_code=404, detail=f"Scheduler {scheduler_id} no encontrado")

    existing.name = body.name
    existing.interval_min_ms = body.interval_min_ms
    existing.interval_max_ms = body.interval_max_ms
    existing.is_enabled = body.is_enabled
    updated = await db.update_scheduler(existing)
    return _serialize_scheduler(updated)


@router.delete(
    "/worlds/{world_id}/schedulers/{scheduler_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Borra un scheduler",
)
async def delete_scheduler(
    world_id: int, scheduler_id: int, request: Request
) -> None:
    """Borra el scheduler. Las farm lists asignadas quedan con scheduler_id=NULL (RN-14)."""
    db = _get_farm_db(request)
    try:
        await db.delete_scheduler(scheduler_id)
    except SchedulerNotFoundError:
        raise HTTPException(status_code=404, detail=f"Scheduler {scheduler_id} no encontrado")


@router.put(
    "/worlds/{world_id}/schedulers/{scheduler_id}/farm-lists",
    summary="Asigna farm lists a un scheduler",
)
async def assign_farm_lists(
    world_id: int,
    scheduler_id: int,
    body: AssignFarmListsRequest,
    request: Request,
) -> dict:
    """Asigna exactamente las farm lists indicadas al scheduler."""
    db = _get_farm_db(request)
    try:
        updated = await db.assign_farm_lists_to_scheduler(scheduler_id, body.farm_list_ids)
    except SchedulerNotFoundError:
        raise HTTPException(status_code=404, detail=f"Scheduler {scheduler_id} no encontrado")
    except FarmListNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _serialize_scheduler(updated)


@router.post(
    "/worlds/{world_id}/schedulers/{scheduler_id}/toggle",
    summary="Alterna is_enabled de un scheduler",
)
async def toggle_scheduler(
    world_id: int, scheduler_id: int, request: Request
) -> dict:
    """
    Alterna is_enabled del scheduler (True→False, False→True).
    No toca el WorldAgent — el agente usa is_enabled en el próximo ciclo.
    404 si el scheduler no existe.
    """
    db = _get_farm_db(request)
    try:
        scheduler = await db.get_scheduler(scheduler_id)
    except SchedulerNotFoundError:
        raise HTTPException(status_code=404, detail=f"Scheduler {scheduler_id} no encontrado")
    scheduler.is_enabled = not scheduler.is_enabled
    updated = await db.update_scheduler(scheduler)
    return _serialize_scheduler(updated)


@router.get(
    "/worlds/{world_id}/schedulers/{scheduler_id}/stats",
    summary="Estadísticas de un scheduler",
)
async def get_scheduler_stats(
    world_id: int, scheduler_id: int, request: Request
) -> dict:
    """
    Métricas agregadas del scheduler y por cada farm list asignada (Gap D, sección 8.3).
    No requiere sesión activa del browser (solo consulta BD, RN-D07).
    404 si el scheduler no existe o su world_id no coincide con el de la ruta (EC-D03).
    """
    db = _get_farm_db(request)
    try:
        stats = await GetSchedulerStatsUseCase(db=db).execute(scheduler_id, world_id)
    except SchedulerNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Scheduler {scheduler_id} no encontrado en el mundo {world_id}",
        )
    return _serialize_scheduler_stats(stats)


# ---------------------------------------------------------------------------
# 8.2 Farm Lists
# ---------------------------------------------------------------------------


@router.get(
    "/worlds/{world_id}/farm-lists",
    summary="Lista farm lists de un mundo",
)
async def list_farm_lists(world_id: int, request: Request) -> list[dict]:
    """Devuelve todas las farm lists del mundo con sus slots y last_send_time (Gap A)."""
    db = _get_farm_db(request)
    uc = GetFarmListsUseCase(db=db)
    farm_lists = await uc.execute(world_id)

    # Gap A: poblar last_send_time consultando el historial de envíos (RN-A01, RN-A02)
    farm_list_ids = [fl.id for fl in farm_lists]
    last_send_times = await db.get_last_send_times_by_world(world_id, farm_list_ids)

    return [
        _serialize_farm_list(fl, last_send_time=last_send_times.get(fl.id))
        for fl in farm_lists
    ]


@router.post(
    "/worlds/{world_id}/farm-lists/read",
    summary="Sincroniza farm lists desde el DOM de Travian",
)
async def read_farm_lists(world_id: int, request: Request) -> list[dict]:
    """
    Navega a la plaza de reuniones, lee las farm lists del DOM y sincroniza en BD.
    Operación lenta — implica navegación del browser.

    503 si no hay sesión activa; 502 si FarmListPageError.
    """
    db = _get_farm_db(request)
    browser = _get_farm_browser(request, world_id)
    uc = ReadFarmListsUseCase(browser=browser, db=db)
    try:
        farm_lists = await uc.execute(world_id)
    except SessionNotActiveError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No hay sesión activa para este mundo. Inicia sesión primero.",
        )
    except FarmListPageError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error al leer farm lists del DOM: {e}",
        )

    # Gap A: poblar last_send_time también en la respuesta del POST /read
    farm_list_ids = [fl.id for fl in farm_lists]
    last_send_times = await db.get_last_send_times_by_world(world_id, farm_list_ids)
    return [
        _serialize_farm_list(fl, last_send_time=last_send_times.get(fl.id))
        for fl in farm_lists
    ]


# ---------------------------------------------------------------------------
# 8.3 Gestión de slots
# ---------------------------------------------------------------------------


@router.post(
    "/slots/{slot_id}/activate",
    summary="Activa un slot en Travian",
)
async def activate_slot(
    slot_id: int, body: SlotActionRequest, request: Request
) -> dict:
    """
    Activa el slot en Travian y limpia disabled_by_bot.
    Si estaba disabled_by_bot, registra evento REACTIVATED.
    """
    db = _get_farm_db(request)
    browser = _get_farm_browser(request, body.world_id)
    uc = ActivateSlotInTravianUseCase(browser=browser, db=db)
    try:
        slot = await uc.execute(slot_id, body.farm_list_id, body.world_id)
    except FarmSlotNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Slot {slot_id} / farm_list_id {body.farm_list_id} no encontrado",
        )
    except SessionNotActiveError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No hay sesión activa para este mundo.",
        )
    except FarmListSendError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error al activar slot en Travian: {e}",
        )
    return _serialize_slot(slot)


@router.post(
    "/slots/{slot_id}/deactivate",
    summary="Desactiva un slot en Travian",
)
async def deactivate_slot(
    slot_id: int, body: SlotActionRequest, request: Request
) -> dict:
    """Desactiva el slot en Travian. No toca disabled_by_bot."""
    db = _get_farm_db(request)
    browser = _get_farm_browser(request, body.world_id)
    uc = DeactivateSlotInTravianUseCase(browser=browser, db=db)
    try:
        slot = await uc.execute(slot_id, body.farm_list_id)
    except FarmSlotNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Slot {slot_id} / farm_list_id {body.farm_list_id} no encontrado",
        )
    except SessionNotActiveError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No hay sesión activa para este mundo.",
        )
    except FarmListSendError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error al desactivar slot en Travian: {e}",
        )
    return _serialize_slot(slot)


@router.post(
    "/slots/{slot_id}/bot-disable",
    summary="El bot desactiva un slot",
)
async def bot_disable_slot(
    slot_id: int, body: SlotActionRequest, request: Request
) -> dict:
    """Desactiva el slot en Travian y pone disabled_by_bot=True."""
    db = _get_farm_db(request)
    browser = _get_farm_browser(request, body.world_id)
    uc = DisableSlotByBotUseCase(browser=browser, db=db)
    try:
        slot = await uc.execute(slot_id, body.farm_list_id)
    except FarmSlotNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Slot {slot_id} / farm_list_id {body.farm_list_id} no encontrado",
        )
    except SessionNotActiveError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No hay sesión activa para este mundo.",
        )
    except FarmListSendError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error al bot-disable slot en Travian: {e}",
        )
    return _serialize_slot(slot)


@router.post(
    "/slots/{slot_id}/bot-enable",
    summary="El bot reactiva un slot",
)
async def bot_enable_slot(
    slot_id: int, body: SlotActionRequest, request: Request
) -> dict:
    """Activa el slot en Travian y limpia disabled_by_bot."""
    db = _get_farm_db(request)
    browser = _get_farm_browser(request, body.world_id)
    uc = EnableSlotByBotUseCase(browser=browser, db=db)
    try:
        slot = await uc.execute(slot_id, body.farm_list_id)
    except FarmSlotNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Slot {slot_id} / farm_list_id {body.farm_list_id} no encontrado",
        )
    except SessionNotActiveError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No hay sesión activa para este mundo.",
        )
    except FarmListSendError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error al bot-enable slot en Travian: {e}",
        )
    return _serialize_slot(slot)


@router.post(
    "/slots/{slot_id}/cancel-probe",
    summary="Cancela la sonda pendiente de un slot",
)
async def cancel_probe(
    slot_id: int, body: CancelProbeRequest, request: Request
) -> dict:
    """
    Cancela la sonda de un slot.

    mode='deactivate': desactiva indefinidamente (disabled_by_bot=False, is_active=False).
    mode='send_now': expira el cooldown para que el próximo ciclo envíe la sonda.
    400 si el slot no tiene disabled_by_bot=True.
    """
    db = _get_farm_db(request)
    try:
        slot = await db.get_slot_by_id(slot_id, body.farm_list_id)
    except FarmSlotNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Slot {slot_id} / farm_list_id {body.farm_list_id} no encontrado",
        )

    if not slot.disabled_by_bot:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"El slot {slot_id} no tiene disabled_by_bot=True — no hay sonda activa. "
                "solo se puede cancelar una sonda en slots desactivados por el bot."
            ),
        )

    # CancelProbeUseCase no usa browser (no navega Travian) — solo BD
    uc = CancelProbeUseCase(db=db)
    try:
        updated_slot = await uc.execute(slot_id, body.farm_list_id, body.world_id, body.mode)
    except FarmSlotNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Slot {slot_id} / farm_list_id {body.farm_list_id} no encontrado",
        )
    return _serialize_slot(updated_slot)


# ---------------------------------------------------------------------------
# 8.4 Envío manual
# ---------------------------------------------------------------------------


@router.post(
    "/farm-lists/{farm_list_id}/send",
    summary="Envía manualmente una farm list",
)
async def send_farm_list(
    farm_list_id: int, body: SendFarmListRequest, request: Request
) -> dict:
    """
    Envía manualmente una farm list. Devuelve el FarmListSendEvent resultante.

    503 si no hay sesión activa; 502 si FarmListSendError o FarmListPageError.
    """
    db = _get_farm_db(request)
    browser = _get_farm_browser(request, body.world_id)
    uc = SendFarmListUseCase(browser=browser, db=db, world_id=body.world_id)
    try:
        event = await uc.execute(farm_list_id)
    except FarmListNotFoundError:
        raise HTTPException(status_code=404, detail=f"Farm list {farm_list_id} no encontrada")
    except SessionNotActiveError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No hay sesión activa para este mundo.",
        )
    except (FarmListSendError, FarmListPageError) as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error al enviar farm list: {e}",
        )
    return _serialize_send_event(event)


# ---------------------------------------------------------------------------
# 8.5 Historial
# ---------------------------------------------------------------------------


def _validate_pagination(page: int, page_size: int) -> None:
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="page debe ser >= 1",
        )
    if not (1 <= page_size <= 100):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="page_size debe estar entre 1 y 100",
        )


@router.get(
    "/worlds/{world_id}/history",
    summary="Historial de envíos de farm lists",
)
async def get_history(
    world_id: int,
    request: Request,
    scheduler_id: Optional[int] = Query(default=None),
    from_dt: Optional[datetime] = Query(default=None),
    to_dt: Optional[datetime] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=100),
) -> dict:
    """Historial paginado de envíos de farm lists."""
    _validate_pagination(page, page_size)
    db = _get_farm_db(request)
    items, total = await db.get_farm_list_send_history(
        world_id,
        scheduler_id=scheduler_id,
        from_dt=from_dt,
        to_dt=to_dt,
        page=page,
        page_size=page_size,
    )
    return {
        "items": [_serialize_send_event(ev) for ev in items],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.get(
    "/worlds/{world_id}/slot-events",
    summary="Historial de eventos de slots",
)
async def get_slot_events(
    world_id: int,
    request: Request,
    scheduler_id: Optional[int] = Query(default=None),
    from_dt: Optional[datetime] = Query(default=None),
    to_dt: Optional[datetime] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=100),
) -> dict:
    """Historial paginado de eventos de slots (pérdidas, sondas, reactivaciones)."""
    _validate_pagination(page, page_size)
    db = _get_farm_db(request)

    items, total = await db.get_slot_events(
        world_id,
        scheduler_id=scheduler_id,
        from_dt=from_dt,
        to_dt=to_dt,
        page=page,
        page_size=page_size,
    )
    return {
        "items": [_serialize_slot_event(ev) for ev in items],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


# ---------------------------------------------------------------------------
# 8.6 Control del agente
# ---------------------------------------------------------------------------


@router.post(
    "/worlds/{world_id}/agent/start",
    summary="Arranca el WorldAgent para el mundo",
)
async def start_agent(world_id: int, request: Request) -> dict:
    """
    Arranca el WorldAgent. Carga schedulers de BD y construye la cola.
    409 si ya está corriendo; 503 si no hay sesión activa.
    """
    from core.scheduling.world_agent import AgentState, WorldAgent

    agents: dict = getattr(request.app.state, "world_agents", None)
    if agents is None:
        request.app.state.world_agents = {}
        agents = request.app.state.world_agents

    existing = agents.get(world_id)
    if existing is not None and existing.state == AgentState.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El WorldAgent del mundo {world_id} ya está corriendo.",
        )

    db = _get_farm_db(request)

    # Crear o recuperar el LiveFarmListAdapter para el mundo.
    # El helper está en app.state para evitar importar LiveFarmListAdapter aquí.
    get_or_create = getattr(request.app.state, "get_or_create_farm_browser", None)
    if get_or_create is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="farm_browser_adapters no disponible — el servidor puede estar iniciándose.",
        )
    browser = get_or_create(world_id)

    # Cablear el WorldAgent con sus dependencias de sesión y ruido.
    # Sin esto el agente queda "ciego": no ve la sesión de Chrome abierta (que vive
    # en el SessionRegistry singleton), no sigue el timeline de modos y no puede
    # ejecutar ruido ni probar rutas (get_browser → None → 500/409 espurio).
    #   - session_registry: para que el agente vea/use el browser real del mundo.
    #   - session_db:       timeline horario (HARDCORE/PASIVO/DISCONNECTED) + override.
    #   - noise_db:         destinos y rutas de ruido de navegación.
    #   - login_use_case + account_id: relogin automático al salir de DISCONNECTED.
    session_registry = getattr(request.app.state, "world_runtime_port", None)
    session_db = getattr(request.app.state, "session_db_port", None)
    noise_db = getattr(request.app.state, "noise_db_port", None)
    accounts_db = getattr(request.app.state, "db_port", None)
    fernet = getattr(request.app.state, "fernet", None)

    login_use_case = None
    account_id = None
    if accounts_db is not None and fernet is not None and session_registry is not None:
        from core.use_cases.login_use_case import LoginUseCase  # noqa: PLC0415

        account_id = await accounts_db.get_account_id_for_world(world_id)
        login_use_case = LoginUseCase(registry=session_registry, db=accounts_db, fernet=fernet)

    # Callables del radar de ataques entrantes — se construyen aquí (composition root,
    # capa de adapters) para que WorldAgent (core) no importe adapters.browser directamente.
    # Patrón: inyección de funciones en lugar de clases concretas (frontera hexagonal).
    incoming_db = getattr(request.app.state, "incoming_attack_db_port", None)
    sidebar_attack_hook = None
    dorf1_attack_reader = None
    if incoming_db is not None:
        from adapters.browser.incoming_attack_hook import check_sidebar_attacks  # noqa: PLC0415
        from adapters.browser.incoming_attack_browser_adapter import IncomingAttackBrowserAdapter  # noqa: PLC0415
        from adapters.browser.parsers.dorf1_incoming_parser import Dorf1IncomingParser  # noqa: PLC0415

        sidebar_attack_hook = check_sidebar_attacks

        if session_registry is not None:
            _browser_adapter = IncomingAttackBrowserAdapter(
                get_browser=session_registry.get_browser,
                get_world_server=session_registry.get_world_server,
            )

            async def _dorf1_reader(wid: int, _adapter=_browser_adapter) -> list:
                html = await _adapter.get_dorf1_html(wid)
                return Dorf1IncomingParser.parse(html)

            dorf1_attack_reader = _dorf1_reader

    agent = WorldAgent(
        world_id=world_id,
        browser=browser,
        db=db,
        session_db=session_db,
        session_registry=session_registry,
        login_use_case=login_use_case,
        account_id=account_id,
        noise_db=noise_db,
        incoming_db=incoming_db,
        sidebar_attack_hook=sidebar_attack_hook,
        dorf1_attack_reader=dorf1_attack_reader,
    )
    seeded = await agent.seed_from_schedulers()
    agents[world_id] = agent

    # Lanzar el bucle del agente como asyncio.Task (no bloqueante)
    asyncio.create_task(agent.run(), name=f"world-agent-{world_id}")

    return {
        "status": "started",
        "world_id": world_id,
        "queued_tasks": seeded,
    }


@router.post(
    "/worlds/{world_id}/agent/stop",
    summary="Solicita parada limpia del WorldAgent",
)
async def stop_agent(world_id: int, request: Request) -> dict:
    """
    Solicita parada limpia del agente (la tarea en curso termina antes).
    404 si el agente no existe para ese mundo.
    """
    agent = _get_world_agent(request, world_id)
    if agent is None:
        raise HTTPException(
            status_code=404,
            detail=f"No existe WorldAgent para el mundo {world_id}.",
        )
    agent.request_stop()
    return {"status": "stop_requested", "world_id": world_id}


@router.get(
    "/worlds/{world_id}/agent/status",
    summary="Estado actual del WorldAgent",
)
async def agent_status(world_id: int, request: Request) -> dict:
    """Estado actual del agente (state, queued_tasks, next_task_at, last_error).
    Devuelve state='stopped' si el agente no ha sido arrancado aún (nunca 404).
    """
    agent = _get_world_agent(request, world_id)
    if agent is None:
        return {
            "world_id": world_id,
            "state": "stopped",
            "queued_tasks": 0,
            "next_task_at": None,
            "last_error": None,
        }
    s = agent.status()
    return {
        "world_id": s.world_id,
        "state": s.state,
        "queued_tasks": s.queued_tasks,
        "next_task_at": s.next_task_at.isoformat() if s.next_task_at else None,
        "last_error": s.last_error,
    }


@router.post(
    "/worlds/{world_id}/schedulers/{scheduler_id}/run-now",
    summary="Adelanta el próximo disparo del scheduler a ahora mismo",
)
async def run_now(world_id: int, scheduler_id: int, request: Request) -> dict:
    """
    Adelanta el próximo disparo del scheduler a now.
    404 si el scheduler no existe en BD.
    409 si el WorldAgent no está corriendo (no tiene sentido adelantar si está parado).
    """
    from core.scheduling.world_agent import AgentState

    db = _get_farm_db(request)
    # Verificar que el scheduler existe en BD
    try:
        await db.get_scheduler(scheduler_id)
    except SchedulerNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Scheduler {scheduler_id} no encontrado.",
        )

    agent = _get_world_agent(request, world_id)
    if agent is None or agent.state != AgentState.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"El WorldAgent del mundo {world_id} no está corriendo. "
                "Arranca el agente primero."
            ),
        )

    agent.run_now(scheduler_id)
    return {"status": "scheduled_now", "scheduler_id": scheduler_id}
