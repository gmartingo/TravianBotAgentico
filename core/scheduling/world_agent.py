"""
WorldAgent — agente ejecutor de un mundo (solo bloque de farm lists).

Mantiene un bucle asyncio que:
  1. Saca de la TaskQueue la tarea más próxima con execute_at <= now.
  2. La ejecuta (handler SEND_FARM_LIST_GROUP).
  3. Si es recurrente, la reencola con intervalo aleatorio (anti-detección).

Un solo agente por mundo = nunca dos acciones de browser al mismo tiempo en
ese mundo, sin necesidad de locks. Distintos mundos corren en asyncio.Task
separados (browsers diferentes → concurrencia permitida).

La parada es limpia: _stop_event despierta el bucle desde _sleep_until_next
para que no haya que esperar hasta la próxima tarea.
"""
from __future__ import annotations

import asyncio
import logging
import random
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from core.entities.farm_scheduler import FarmScheduler
from core.entities.task import Task, TaskType
from core.exceptions import SchedulerNotFoundError
from core.ports.farm_list_browser_port import FarmListBrowserPort
from core.ports.farm_list_db_port import FarmListDbPort
from core.scheduling.task_queue import TaskQueue
from core.use_cases.farm_lists import SendSchedulerGroupUseCase

logger = logging.getLogger(__name__)


class AgentState(str, Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR   = "error"
    PAUSED  = "paused"


@dataclass
class AgentStatus:
    world_id: int
    state: AgentState
    queued_tasks: int
    next_task_at: datetime | None
    last_error: str | None


class WorldAgent:
    """
    Agente de scheduling para farm lists de un mundo.

    Parámetros:
      world_id — ID del mundo que gestiona este agente.
      browser  — FarmListBrowserPort: acceso al browser de ese mundo.
      db       — FarmListDbPort: acceso a la BD de ese mundo.
      queue    — TaskQueue inyectado (facilita tests sin depender del constructor).
    """

    # Segundos de espera cuando la cola está vacía antes de volver a mirar.
    DEFAULT_IDLE_SECONDS = 60.0

    def __init__(
        self,
        world_id: int,
        browser: FarmListBrowserPort,
        db: FarmListDbPort,
        queue: TaskQueue | None = None,
    ) -> None:
        self.world_id = world_id
        self._browser = browser
        self._db = db
        self._queue: TaskQueue = queue or TaskQueue()
        self._stop_event = asyncio.Event()
        self._notify_event = asyncio.Event()
        self._send_group = SendSchedulerGroupUseCase(browser=browser, db=db)
        self.state: AgentState = AgentState.STOPPED
        self.last_error: str | None = None
        self._activity: deque[dict] = deque(maxlen=50)

    # ------------------------------------------------------------------
    # Arranque
    # ------------------------------------------------------------------

    async def seed_from_schedulers(self) -> int:
        """
        Reconstruye la cola en memoria a partir de los schedulers persistidos.
        Solo encola los schedulers habilitados. Devuelve cuántos se encolaron.
        """
        now = datetime.now()
        schedulers = await self._db.get_schedulers_by_world(self.world_id)
        seeded = 0
        for scheduler in schedulers:
            if not scheduler.is_enabled:
                continue
            execute_at = self._initial_execute_at(scheduler, now)
            self._queue.add(self._build_task(scheduler, execute_at))
            await self._db.update_scheduler_run_state(
                scheduler_id=scheduler.id,
                last_run=scheduler.last_run,
                next_run=execute_at,
                execution_count=scheduler.execution_count,
            )
            seeded += 1
        logger.info(
            "Mundo %d: %d farm schedulers encolados en arranque", self.world_id, seeded
        )
        return seeded

    def _initial_execute_at(self, scheduler: FarmScheduler, now: datetime) -> datetime:
        """
        Si el scheduler tiene un next_run en el futuro, lo respeta
        (rearranque tras reinicio). En caso contrario calcula un próximo disparo
        aleatorio para no arrancar todos los schedulers al mismo instante.
        """
        if scheduler.next_run is not None and scheduler.next_run > now:
            return scheduler.next_run
        return now + timedelta(milliseconds=self._random_interval_ms(scheduler))

    # ------------------------------------------------------------------
    # Bucle principal
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """
        Bucle principal del agente. Ejecuta tareas a medida que vencen.
        Se detiene cuando se llama a request_stop().
        """
        self.state = AgentState.RUNNING
        logger.info(
            "Agente del mundo %d arrancado (%d tareas en cola)",
            self.world_id, len(self._queue),
        )
        try:
            while not self._stop_event.is_set():
                now = datetime.now()
                task = self._queue.pop_ready(now)
                if task is None:
                    if await self._sleep_until_next(now):
                        break  # se pidió Stop mientras esperaba
                    continue

                await self._execute(task)
                if task.recurring:
                    await self._reschedule_farm(task)
        except asyncio.CancelledError:
            logger.info("Agente del mundo %d cancelado", self.world_id)
            raise
        finally:
            self.state = AgentState.STOPPED
            logger.info("Agente del mundo %d detenido", self.world_id)

    async def _sleep_until_next(self, now: datetime) -> bool:
        """
        Espera hasta la próxima tarea, un notify (run_now) o Stop.
        Devuelve True si se pidió Stop durante la espera.
        """
        delay = self._queue.seconds_until_next(now)
        if delay is None:
            delay = self.DEFAULT_IDLE_SECONDS

        sleep_task = asyncio.create_task(asyncio.sleep(delay))
        stop_task = asyncio.create_task(self._stop_event.wait())
        notify_task = asyncio.create_task(self._notify_event.wait())
        try:
            await asyncio.wait(
                {sleep_task, stop_task, notify_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            for t in (sleep_task, stop_task, notify_task):
                t.cancel()
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass
        self._notify_event.clear()
        return self._stop_event.is_set()

    async def _execute(self, task: Task) -> None:
        """
        Ejecuta una tarea. Un fallo no mata el agente: se loguea y se sigue
        (spec sección 11 — errores y recuperación).
        """
        try:
            if task.task_type == TaskType.SEND_FARM_LIST_GROUP:
                scheduler_id = task.payload["scheduler_id"]
                self._log_act("info", f"Farm list scheduler={scheduler_id} enviando…")
                await self._send_group.execute(scheduler_id)
                self._log_act("ok", f"Farm list scheduler={scheduler_id} enviada")
                self.state = AgentState.RUNNING
                self.last_error = None
            else:
                logger.warning(
                    "Tipo de tarea desconocido en mundo %d: %s",
                    self.world_id, task.task_type,
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.state = AgentState.ERROR
            self.last_error = str(exc)
            self._log_act("error", f"Error en {task.task_type}: {exc}")
            logger.exception(
                "Fallo ejecutando %s en mundo %d", task.task_type, self.world_id
            )

    async def _reschedule_farm(self, task: Task) -> None:
        """
        Reencola el scheduler con un intervalo aleatorio (anti-detección).
        EC-07: si is_enabled=False, no reencola.
        EC-08: si el scheduler fue borrado (SchedulerNotFoundError), no reencola.
        """
        try:
            scheduler = await self._db.get_scheduler(task.source_scheduler_id)
        except SchedulerNotFoundError:
            logger.info(
                "Scheduler %d ya no existe — no se reencola", task.source_scheduler_id
            )
            return
        if not scheduler.is_enabled:
            logger.info(
                "Scheduler %d deshabilitado — no se reencola", scheduler.id
            )
            return

        now = datetime.now()
        next_at = now + timedelta(milliseconds=self._random_interval_ms(scheduler))
        await self._db.update_scheduler_run_state(
            scheduler_id=scheduler.id,
            last_run=now,
            next_run=next_at,
            execution_count=scheduler.execution_count + 1,
        )
        self._queue.add(self._build_task(scheduler, next_at))
        logger.info(
            "Scheduler %d reencolado para %s",
            scheduler.id, next_at.isoformat(timespec="seconds"),
        )

    # ------------------------------------------------------------------
    # Control y estado
    # ------------------------------------------------------------------

    def request_stop(self) -> None:
        """Solicita parada limpia del agente. La tarea en curso termina antes de parar."""
        self._stop_event.set()

    def run_now(self, scheduler_id: int) -> None:
        """
        Adelanta el próximo disparo del scheduler a ahora mismo.
        Síncrono (no async): modifica la cola y notifica el bucle.
        EC-13: silencioso si el scheduler no estaba en cola.
        """
        self._queue.remove_by_scheduler(scheduler_id)
        self._queue.add(self._build_task_at(scheduler_id, datetime.now()))
        self._notify_event.set()
        self._log_act("info", f"Scheduler={scheduler_id} adelantado a ahora (run-now)")

    def status(self) -> AgentStatus:
        """Devuelve el estado actual del agente."""
        nxt = self._queue.peek_next()
        return AgentStatus(
            world_id=self.world_id,
            state=self.state,
            queued_tasks=len(self._queue),
            next_task_at=nxt.execute_at if nxt is not None else None,
            last_error=self.last_error,
        )

    def get_activity(self) -> list[dict]:
        """Devuelve el log de actividad reciente (últimas 50 entradas)."""
        return list(self._activity)

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    def _build_task(self, scheduler: FarmScheduler, execute_at: datetime) -> Task:
        return self._build_task_at(scheduler.id, execute_at)

    def _build_task_at(self, scheduler_id: int, execute_at: datetime) -> Task:
        return Task(
            task_type=TaskType.SEND_FARM_LIST_GROUP,
            world_id=self.world_id,
            execute_at=execute_at,
            priority=1,
            payload={"scheduler_id": scheduler_id, "scheduler_type": "farm"},
            recurring=True,
            source_scheduler_id=scheduler_id,
        )

    @staticmethod
    def _random_interval_ms(scheduler: FarmScheduler) -> float:
        return random.uniform(scheduler.interval_min_ms, scheduler.interval_max_ms)

    def _log_act(self, level: str, msg: str) -> None:
        self._activity.append({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "level": level,
            "msg": msg,
        })
        logger.debug("[activity] %s", msg)
