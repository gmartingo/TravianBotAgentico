"""
Entidades de scheduling: Task y TaskType.

Task     — unidad de trabajo que el WorldAgent saca de la TaskQueue y ejecuta.
TaskType — tipos de tarea conocidos por el agente.

El agente ejecuta las tareas ordenadas por (priority, execute_at).
Prioridades (menor número = mayor prioridad):
  1 — SEND_FARM_LIST_GROUP (farm lists, prioridad máxima de esta feature)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class TaskType(str, Enum):
    SEND_FARM_LIST_GROUP = "SEND_FARM_LIST_GROUP"
    # Navegación de ruido anti-detección (Human Sessions v2.2)
    NOISE_NAVIGATION = "NOISE_NAVIGATION"
    # Radar de ataques entrantes — lectura de dorf1 con timer (Componente B)
    # Encolado desde WorldAgent._post_page_hook con retraso variable 3-15 s (RN-22).
    # Ver spec docs/specs/radar-ataques-entrantes.md §9.5.
    CHECK_INCOMING_ATTACK_DETAIL = "CHECK_INCOMING_ATTACK_DETAIL"


@dataclass
class Task:
    """
    Unidad de trabajo en la cola del WorldAgent.

    Campos:
      task_type           — tipo de tarea (TaskType).
      world_id            — mundo al que pertenece la tarea.
      execute_at          — momento en que la tarea puede ejecutarse.
      priority            — orden relativo (menor = antes); usada como criterio de ordenación junto a execute_at.
      payload             — datos específicos del tipo de tarea (ej. scheduler_id).
      recurring           — True si la tarea se reencola tras ejecutarse.
      source_scheduler_id — ID del scheduler que originó la tarea (para reencolar).
      defer_count         — cuántas veces fue aplazada la tarea (anti-bounce).
    """
    task_type: TaskType
    world_id: int
    execute_at: datetime
    priority: int = 1
    payload: dict = field(default_factory=dict)
    recurring: bool = True
    source_scheduler_id: int | None = None
    defer_count: int = 0

    def __lt__(self, other: "Task") -> bool:
        """Orden para heapq / sorted: (priority, execute_at)."""
        return (self.priority, self.execute_at) < (other.priority, other.execute_at)
