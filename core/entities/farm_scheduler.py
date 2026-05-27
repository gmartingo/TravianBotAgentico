"""
Entidad FarmScheduler — scheduler de envío periódico de farm lists.

Un scheduler agrupa una o varias farm lists de un mismo mundo y las envía
de forma recurrente con un intervalo aleatorio en [interval_min_ms, interval_max_ms]
para evitar patrones de tiempo detectables (anti-detección, RN-02).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FarmScheduler:
    """
    Scheduler de farm lists.

    `last_run` / `next_run` / `execution_count` reflejan el estado
    persistido en BD. La cola de tareas en sí vive solo en memoria.
    `farm_list_ids` es la lista de IDs de farm lists asignadas al scheduler.
    """
    id: int | None
    world_id: int
    name: str
    interval_min_ms: int
    interval_max_ms: int
    is_enabled: bool = True
    last_run: datetime | None = None
    next_run: datetime | None = None
    execution_count: int = 0
    farm_list_ids: list[int] = field(default_factory=list)
