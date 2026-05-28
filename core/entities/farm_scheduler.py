"""
Entidad FarmScheduler — scheduler de envío periódico de farm lists.

Un scheduler agrupa una o varias farm lists de un mismo mundo y las envía
de forma recurrente con un intervalo aleatorio en [interval_min_ms, interval_max_ms]
para evitar patrones de tiempo detectables (anti-detección, RN-02).

Entidades de stats (Gap D):
  SchedulerListStats — métricas de una farm list individual dentro de un scheduler.
  SchedulerStats     — métricas agregadas de un scheduler completo.
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


@dataclass
class SchedulerListStats:
    """Métricas de una farm list individual dentro de un scheduler (Gap D, RN-D06)."""
    farm_list_id: int
    farm_list_name: str
    last_send_time: datetime | None
    success_rate: float
    active_slots_avg: float
    total_bounty: int
    bounty_per_hour: float


@dataclass
class SchedulerStats:
    """Métricas agregadas de un scheduler (Gap D, RN-D01..D07)."""
    scheduler_id: int
    scheduler_name: str
    world_id: int
    execution_count: int
    last_send_time: datetime | None
    success_rate: float
    active_slots_avg: float
    total_bounty: int
    bounty_per_hour: float
    per_list: list[SchedulerListStats] = field(default_factory=list)
