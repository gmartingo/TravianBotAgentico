"""
Puerto de BD para farm lists (FarmListDbPort).

Contrato abstracto para todas las operaciones de persistencia de farm lists,
schedulers, historial de envíos y eventos de slots.

La implementación concreta es FarmListSQLiteAdapter
(adapters/db/farm_list_sqlite_adapter.py).

NO extiende DbPort: convención explícita del proyecto (ver CLAUDE.md y spec
farm-lists sección 13).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from core.entities.farm_list import BotSlotStatus, FarmList, FarmSlot, SlotBountyRecord, SlotEvent
from core.entities.farm_list_send_event import FarmListSendEvent
from core.entities.farm_scheduler import FarmScheduler, SchedulerStats
from core.entities.village import Village


class FarmListDbPort(ABC):

    # --- Farm lists ---

    @abstractmethod
    async def sync_farm_lists(
        self, village_id: int, farm_lists: list[FarmList], world_id: int
    ) -> list[FarmList]:
        """
        Sincroniza la lista completa de farm lists de una aldea.
        - Inserta listas nuevas.
        - Actualiza las existentes.
        - Borra listas que ya no aparecen en el DOM.
        Devuelve la lista sincronizada (con estado bot preservado en los slots).
        world_id es necesario para delegar a sync_farm_list (Gap C).
        """

    @abstractmethod
    async def sync_farm_list(self, farm_list: FarmList, world_id: int) -> FarmList:
        """
        Sincroniza una sola farm list. Matching de slots por coordenadas (x, y)
        para preservar el estado bot aunque Travian reasigne IDs (RN-15, EC-05).
        world_id es necesario para insertar en slot_bounty_history y para la purga TTL.

        EC-06: si el DOM devuelve is_active=True para un slot que tenía
        disabled_by_bot=True, resetea disabled_by_bot=False, disabled_at=None,
        cooldown_seconds=3600.

        Gap C: inserta en slot_bounty_history cuando last_raid_report_id cambia
        y last_raid_bounty > 0 (RN-C01). Reasigna IDs de slot en slot_bounty_history
        antes de borrar el slot viejo (EC-C03, RN-C06).
        """

    @abstractmethod
    async def get_farm_lists_by_village(self, village_id: int) -> list[FarmList]:
        """Devuelve todas las farm lists de una aldea con sus slots."""

    @abstractmethod
    async def get_farm_lists_by_world(self, world_id: int) -> list[FarmList]:
        """Devuelve todas las farm lists de un mundo con sus slots."""

    @abstractmethod
    async def get_farm_list_by_id(self, farm_list_id: int) -> FarmList:
        """
        Devuelve la farm list con sus slots.
        Lanza FarmListNotFoundError si no existe.
        """

    @abstractmethod
    async def get_villages_by_world(self, world_id: int) -> list[Village]:
        """Devuelve todas las aldeas de un mundo."""

    @abstractmethod
    async def upsert_village(self, world_id: int, data_id: int, name: str) -> Village:
        """
        Inserta la aldea si no existe (por world_id + data_id); actualiza el nombre si cambió.
        Devuelve la Village con su id de BD.
        """

    # --- Slots ---

    @abstractmethod
    async def get_slot_by_id(self, slot_id: int, farm_list_id: int) -> FarmSlot:
        """
        Devuelve el slot por clave compuesta (slot_id, farm_list_id).
        Lanza FarmSlotNotFoundError si no existe.
        """

    @abstractmethod
    async def update_slot_flags(
        self,
        slot_id: int,
        farm_list_id: int,
        *,
        is_active: bool | None = None,
        disabled_by_bot: bool | None = None,
    ) -> FarmSlot:
        """
        Actualiza uno o ambos flags del slot (is_active, disabled_by_bot).
        Los parámetros con valor None no se tocan.
        Devuelve el slot actualizado.
        """

    @abstractmethod
    async def update_slot_cooldown_state(
        self,
        slot_id: int,
        farm_list_id: int,
        *,
        disabled_at: datetime | None,
        cooldown_seconds: int,
        report_id_at_disable: str,
        disabled_by_bot: bool,
        is_active: bool,
    ) -> FarmSlot:
        """
        Actualiza el estado de cooldown completo del slot.
        Usado por ProcessFarmListUseCase al detectar pérdidas, reactivar
        o gestionar sondas.
        """

    @abstractmethod
    async def get_bot_status_slots(self, world_id: int) -> list[BotSlotStatus]:
        """
        Devuelve resumen del estado bot de todos los slots del mundo.
        Usado para construir vistas de monitoreo del dashboard.
        """

    # --- Eventos de slot ---

    @abstractmethod
    async def add_slot_event(self, event: SlotEvent) -> None:
        """Persiste un nuevo evento de slot."""

    @abstractmethod
    async def get_slot_events(
        self,
        world_id: int,
        *,
        scheduler_id: int | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[list[SlotEvent], int]:
        """
        Devuelve (items, total) — historial de eventos de slots paginado.
        Filtra por scheduler_id (vía farm_list_id IN scheduler.farm_list_ids)
        y/o rango de fechas si se especifica.
        """

    # --- Schedulers ---

    @abstractmethod
    async def create_scheduler(self, scheduler: FarmScheduler) -> FarmScheduler:
        """Crea un nuevo scheduler y devuelve el objeto con id asignado."""

    @abstractmethod
    async def get_scheduler(self, scheduler_id: int) -> FarmScheduler:
        """
        Devuelve el scheduler por id.
        Lanza SchedulerNotFoundError si no existe.
        """

    @abstractmethod
    async def get_schedulers_by_world(self, world_id: int) -> list[FarmScheduler]:
        """Devuelve todos los schedulers de un mundo."""

    @abstractmethod
    async def update_scheduler(self, scheduler: FarmScheduler) -> FarmScheduler:
        """
        Actualiza nombre, intervalos e is_enabled de un scheduler.
        Lanza SchedulerNotFoundError si no existe.
        """

    @abstractmethod
    async def delete_scheduler(self, scheduler_id: int) -> None:
        """
        Borra un scheduler. Las farm lists asignadas quedan con scheduler_id=NULL
        (RN-14). Lanza SchedulerNotFoundError si no existe.
        """

    @abstractmethod
    async def assign_farm_lists_to_scheduler(
        self, scheduler_id: int, farm_list_ids: list[int]
    ) -> FarmScheduler:
        """
        Asigna exactamente las farm lists indicadas al scheduler, desvinculando
        las que ya no estén en la lista. Devuelve el scheduler actualizado.
        Lanza SchedulerNotFoundError si el scheduler no existe.
        Lanza FarmListNotFoundError si alguna farm list no existe.
        """

    @abstractmethod
    async def update_scheduler_run_state(
        self,
        scheduler_id: int,
        last_run: datetime | None,
        next_run: datetime | None,
        execution_count: int,
    ) -> None:
        """Actualiza last_run, next_run y execution_count del scheduler."""

    # --- Historial de envíos ---

    @abstractmethod
    async def add_farm_list_send_event(self, event: FarmListSendEvent) -> None:
        """
        Persiste un evento de envío de farm list y purga automáticamente
        los registros con más de 7 días (RN-13, EC-15).
        """

    @abstractmethod
    async def get_farm_list_send_history(
        self,
        world_id: int,
        *,
        scheduler_id: int | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[list[FarmListSendEvent], int]:
        """
        Devuelve (items, total) — historial de envíos paginado.
        Filtra por scheduler_id y/o rango de fechas si se especifica.
        """

    # --- Gap C: historial de bounty por slot ---

    @abstractmethod
    async def add_slot_bounty_record(self, record: SlotBountyRecord) -> None:
        """
        Inserta un registro de bounty en slot_bounty_history y purga los registros
        con más de 7 días para el mismo world_id (RN-C01, RN-C02).
        No llamar directamente si bounty == 0 o raid_report_id == ''.
        """

    # --- Gap A: last_send_time por farm list ---

    @abstractmethod
    async def get_last_send_times_by_world(
        self, world_id: int, farm_list_ids: list[int]
    ) -> dict[int, datetime | None]:
        """
        Devuelve MAX(timestamp) de farm_list_send_history GROUP BY farm_list_id,
        filtrado a los farm_list_ids indicados (RN-A01, RN-A02).
        Clave: farm_list_id. Valor: datetime o None si no hay historial.
        """

    # --- Gap D: estadísticas del scheduler ---

    @abstractmethod
    async def get_scheduler_stats(
        self, scheduler_id: int, world_id: int
    ) -> SchedulerStats:
        """
        Devuelve métricas agregadas del scheduler (RN-D01..D07).
        Lanza SchedulerNotFoundError si no existe o world_id no coincide (EC-D03).
        """
