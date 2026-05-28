"""
Entidades de dominio para farm lists (listas de vacas).

FarmSlot        — una vaca (aldea objetivo) dentro de una lista.
FarmList        — lista de vacas con sus slots.
BotSlotStatus   — resumen del estado bot de un slot (para queries de monitoreo).
SlotEvent       — evento de cambio de estado de un slot (pérdidas, sonda, reactivación).
SlotBountyRecord — registro histórico de botín por slot (acumulación TTL 7 días).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FarmSlot:
    """Representa un objetivo (vaca) dentro de una farm list."""
    id: int
    farm_list_id: int
    target_name: str
    x: int
    y: int
    population: int = 0
    troops: dict = field(default_factory=dict)  # {"t1": 2, "t4": 1}
    is_active: bool = True
    disabled_by_bot: bool = False
    last_raid_state: str = ""
    last_raid_time: str = ""
    last_raid_report_id: str = ""
    last_raid_bounty: int = 0
    average_raid_bounty: int = 0
    total_bounty: int = 0
    distance: float = 0.0
    disabled_at: datetime | None = None
    cooldown_seconds: int = 3600
    report_id_at_disable: str = ""


@dataclass
class FarmList:
    """
    Lista de vacas. Agrupa FarmSlots de la misma aldea propietaria.
    `village_name` solo está presente en memoria (no persiste en BD);
    se usa para matching durante la sincronización.
    """
    id: int
    name: str
    owner_village_id: int
    slots: list[FarmSlot] = field(default_factory=list)
    scheduler_id: int | None = None
    village_name: str = ""       # transitorio: nombre de la aldea propietaria
    village_data_id: int = 0     # transitorio: data_id (data-did) de la aldea propietaria
    village_x: int = 0           # transitorio: coordenada x de la aldea propietaria
    village_y: int = 0           # transitorio: coordenada y de la aldea propietaria


@dataclass
class BotSlotStatus:
    """
    Resumen del estado bot de un slot para monitoreo.
    Usado por GetBotStatusSlotsUseCase para construir vistas de dashboard.
    """
    slot_id: int
    farm_list_id: int
    target_name: str
    disabled_by_bot: bool
    disabled_at: datetime | None
    cooldown_seconds: int
    last_raid_state: str
    last_raid_report_id: str
    report_id_at_disable: str


@dataclass
class SlotEvent:
    """
    Evento de cambio de estado de un slot.
    Campos denormalizados (target_name, farm_list_name) para que los registros
    históricos sean legibles aunque se borre la entidad original.
    """
    id: int
    timestamp: datetime
    slot_id: int
    slot_name: str
    farm_list_id: int
    farm_list_name: str
    world_id: int
    event_type: str   # LOSSES_DETECTED | PROBE_SENT | REACTIVATED | PROBE_CANCELLED
    last_raid_state: str = ""
    cooldown_seconds: int = 3600
    last_raid_report_id: str = ""


@dataclass
class SlotBountyRecord:
    """
    Registro histórico de botín por slot (acumulación para total_bounty).

    Se inserta en slot_bounty_history cuando last_raid_report_id cambia
    y last_raid_bounty > 0 (RN-C01). TTL de 7 días (RN-C02).
    No tiene FK a farm_slots: los registros sobreviven al borrado del slot origen.
    """
    slot_id: int
    farm_list_id: int
    world_id: int
    timestamp: datetime
    bounty: int
    raid_report_id: str = ""
    id: int = 0   # asignado por BD al persistir
