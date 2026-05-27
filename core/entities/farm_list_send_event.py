"""
Entidad FarmListSendEvent — registro de un envío de farm list.

Campos denormalizados (farm_list_name, world_id) para que el historial sea
legible aunque se borre la lista original (RN-13, EC-15).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FarmListSendEvent:
    """
    Registro histórico de un envío de farm list.

    `status`: success | partial | error | unknown
    `triggered_by`: scheduler | manual
    `bot_disabled_slots`: nombres de vacas desactivadas en este ciclo (denormalizado).
    """
    farm_list_id: int
    farm_list_name: str
    world_id: int
    timestamp: datetime
    status: str
    being_raided_current: int = 0
    being_raided_total: int = 0
    triggered_by: str = "scheduler"   # scheduler | manual
    scheduler_id: int | None = None
    bot_disabled_slots: list[str] = field(default_factory=list)
    id: int = 0   # asignado por BD al persistir
    loot_wood: int = 0    # reservado Agente ROI
    loot_clay: int = 0    # reservado Agente ROI
    loot_iron: int = 0    # reservado Agente ROI
    loot_crop: int = 0    # reservado Agente ROI
