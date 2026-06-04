"""
Cola de tareas del WorldAgent (TaskQueue).

Implementación con lista ordenada por (priority, execute_at). Con decenas de
schedulers el sort() es irrelevante. Si creciera mucho, sustituir por heapq
sin cambiar la interfaz pública (spec sección 11).

La cola vive en memoria. asyncio es single-threaded por evento, así que no
necesita locks (un solo WorldAgent por mundo → no hay concurrencia en la cola).
"""
from __future__ import annotations

from datetime import datetime

from core.entities.task import Task, TaskType


class TaskQueue:
    """
    Cola de tareas ordenada por (priority, execute_at).

    Menor priority = mayor urgencia. Dentro del mismo priority, la tarea
    más próxima en el tiempo tiene prioridad.
    """

    def __init__(self) -> None:
        self._tasks: list[Task] = []

    def add(self, task: Task) -> None:
        """Añade una tarea y re-ordena la cola."""
        self._tasks.append(task)
        self._tasks.sort()

    def pop_ready(self, now: datetime) -> Task | None:
        """
        Extrae y devuelve la primera tarea cuyo execute_at <= now.
        Devuelve None si no hay ninguna lista para ejecutar.
        La cola está ordenada, así que basta comprobar el primer elemento.
        """
        if self._tasks and self._tasks[0].execute_at <= now:
            return self._tasks.pop(0)
        return None

    def pop_farm_ready(self, now: datetime) -> Task | None:
        """
        Extrae y devuelve la primera tarea SEND_FARM_LIST_GROUP cuyo execute_at <= now.
        Devuelve None si no hay ninguna lista para ejecutar de ese tipo.
        Usado en modo PASIVO: solo procesa farm lists, ignora el resto.
        """
        for i, task in enumerate(self._tasks):
            if task.execute_at > now:
                break
            if task.task_type == TaskType.SEND_FARM_LIST_GROUP:
                return self._tasks.pop(i)
        return None

    def peek_next(self) -> Task | None:
        """Devuelve la próxima tarea sin extraerla (o None si la cola está vacía)."""
        return self._tasks[0] if self._tasks else None

    def seconds_until_next(self, now: datetime) -> float | None:
        """
        Segundos hasta que la próxima tarea sea ejecutable.
        Devuelve None si la cola está vacía.
        Devuelve 0.0 si la próxima tarea ya estaba lista.
        """
        nxt = self.peek_next()
        if nxt is None:
            return None
        return max(0.0, (nxt.execute_at - now).total_seconds())

    def remove_by_scheduler(self, scheduler_id: int) -> int:
        """
        Elimina todas las tareas del scheduler indicado.
        Silencioso si no hay ninguna (EC-13).
        Devuelve cuántas se eliminaron.
        """
        before = len(self._tasks)
        self._tasks = [t for t in self._tasks if t.source_scheduler_id != scheduler_id]
        return before - len(self._tasks)

    def has_scheduler(self, scheduler_id: int) -> bool:
        """True si hay al menos una tarea del scheduler en cola."""
        return any(t.source_scheduler_id == scheduler_id for t in self._tasks)

    def has_task_type(self, task_type: TaskType) -> bool:
        """True si hay al menos una tarea del tipo indicado en cola."""
        return any(t.task_type == task_type for t in self._tasks)

    def snapshot(self) -> list[Task]:
        """Copia de la cola actual (para inspección, no para modificar)."""
        return list(self._tasks)

    def clear(self) -> None:
        """Vacía la cola."""
        self._tasks.clear()

    def get_tasks_by_priority(self, max_priority: int) -> list[Task]:
        """
        Devuelve las tareas con priority <= max_priority, ordenadas.
        Útil para calcular huecos entre farm lists antes de entrenar.
        """
        return [t for t in self._tasks if t.priority <= max_priority]

    def __len__(self) -> int:
        return len(self._tasks)
