"""
WorldAgent — agente ejecutor de un mundo con soporte de Human Sessions.

Mantiene un bucle asyncio que:
  1. Comprueba la transición de modo de sesión (_check_mode_transition).
  2. Según el modo activo (HARDCORE / PASIVO / DISCONNECTED), ejecuta o suspende tareas.
  3. Si la tarea es SEND_FARM_LIST_GROUP y el modo es PASIVO, aplica el dado de
     probabilidad y el multiplicador de intervalo (RN-HS12).

Un solo agente por mundo = nunca dos acciones de browser al mismo tiempo en
ese mundo, sin necesidad de locks. Distintos mundos corren en asyncio.Task
separados (browsers diferentes → concurrencia permitida).

La parada es limpia: _stop_event despierta el bucle desde _sleep_until_next
para que no haya que esperar hasta la próxima tarea.

Spec §9.3 (_check_mode_transition), §9.4 (PASIVO farm lists), §9.5 (bucle principal).
"""
from __future__ import annotations

import asyncio
import logging
import random
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING

from core.entities.farm_scheduler import FarmScheduler
from core.entities.session import (
    SessionMode,
    SessionTimeline,
    current_mode as compute_current_mode,
    get_default_timeline,
)
from core.entities.task import Task, TaskType
from core.exceptions import FernetDecryptionError, SchedulerNotFoundError
from core.ports.farm_list_browser_port import FarmListBrowserPort
from core.ports.farm_list_db_port import FarmListDbPort
from core.ports.session_timeline_db_port import SessionTimelineDbPort
from core.scheduling.task_queue import TaskQueue
from core.use_cases.farm_lists import SendSchedulerGroupUseCase

if TYPE_CHECKING:
    from core.entities.session import SessionConfig, SessionOverride
    from core.ports.world_runtime_port import WorldRuntimePort
    from core.use_cases.login_use_case import LoginUseCase

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
    active_mode: str | None = None


class WorldAgent:
    """
    Agente de scheduling para farm lists de un mundo, con soporte de
    Human Sessions (timeline horario de actividad con tres modos).

    Parámetros:
      world_id     — ID del mundo que gestiona este agente.
      browser      — FarmListBrowserPort: acceso al browser de ese mundo.
      db           — FarmListDbPort: acceso a la BD de ese mundo.
      session_db   — SessionTimelineDbPort: acceso al timeline de sesión.
      session_registry — WorldRuntimePort con close_session / has_active_session.
      login_use_case   — LoginUseCase para relogin automático al salir de DISCONNECTED.
      account_id   — ID de la cuenta propietaria del mundo (necesario para relogin).
      queue        — TaskQueue inyectado (facilita tests sin depender del constructor).
    """

    # Segundos de espera en DISCONNECTED antes de volver a comprobar transición.
    DEFAULT_IDLE_SECONDS = 60.0

    def __init__(
        self,
        world_id: int,
        browser: FarmListBrowserPort,
        db: FarmListDbPort,
        session_db: SessionTimelineDbPort | None = None,
        session_registry=None,          # WorldRuntimePort con close/has_active
        login_use_case=None,            # LoginUseCase
        account_id: int | None = None,  # para pasar a LoginUseCase.execute()
        queue: TaskQueue | None = None,
    ) -> None:
        self.world_id    = world_id
        self._browser    = browser
        self._db         = db
        self._session_db = session_db
        self._session_registry = session_registry
        self._login_use_case   = login_use_case
        self._account_id = account_id

        self._queue: TaskQueue = queue or TaskQueue()
        self._stop_event   = asyncio.Event()
        self._notify_event = asyncio.Event()
        self._send_group   = SendSchedulerGroupUseCase(browser=browser, db=db)

        self.state: AgentState = AgentState.STOPPED
        self.last_error: str | None = None
        self._activity: deque[dict] = deque(maxlen=50)

        # Estado de sesión (runtime, nunca persistido — RN-HS02)
        self._active_mode: SessionMode = SessionMode.HARDCORE  # default provisional
        self._jitter_fin: datetime = datetime.now()            # se recalcula en run()

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
    # Bucle principal (con soporte de modos de sesión)
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """
        Bucle principal del agente. Ejecuta tareas a medida que vencen.
        Se detiene cuando se llama a request_stop().

        Arranque:
          1. Calcular modo activo con _current_mode(now) (§9.5, §RN-HS09).
          2. Si modo != DISCONNECTED y no hay sesión activa → relogin (§RN-HS13).
          3. Si modo == HARDCORE → seed_oasis_groups_from_db (§RN-HS08).
          4. Entrar en el bucle principal.
        """
        self.state = AgentState.RUNNING

        # Calcular modo inicial (§9.5, §RN-HS09: arrancar en el modo del calendario)
        now = datetime.now()
        timeline = await self._load_timeline(now)
        override = await self._get_override_safe()
        self._active_mode, self._jitter_fin = compute_current_mode(now, timeline, override)

        logger.info(
            "Agente del mundo %d arrancado: modo=%s, jitter_fin=%s",
            self.world_id, self._active_mode.value,
            self._jitter_fin.isoformat(timespec="seconds"),
        )

        # Si arranca en modo activo y no hay sesión → relogin (§9.5)
        if self._active_mode != SessionMode.DISCONNECTED:
            if not self._session_active():
                await self._relogin_with_backoff()

        # Si arranca en HARDCORE → seed oasis (§RN-HS08)
        if self._active_mode == SessionMode.HARDCORE:
            await self._safe_seed_oasis()

        try:
            while not self._stop_event.is_set():
                now = datetime.now()
                await self._check_mode_transition(now)

                if self._active_mode == SessionMode.DISCONNECTED:
                    # Esperar hasta el próximo borde de bloque (o stop)
                    wait_secs = max(1.0, (self._jitter_fin - now).total_seconds())
                    wait_secs = min(wait_secs, self.DEFAULT_IDLE_SECONDS)
                    if await self._sleep(wait_secs):
                        break
                    continue

                if self._active_mode == SessionMode.PASIVO:
                    # Solo farm lists VILLAGE con lógica PASIVO (RN-HS12)
                    task = self._queue.pop_farm_ready(now)
                    if task is None:
                        if await self._sleep_until_next(now):
                            break
                        continue
                    await self._handle_send_farm_list_group_pasivo(task)
                    continue

                # HARDCORE: lógica completa existente
                task = self._queue.pop_ready(now)
                if task is None:
                    if await self._sleep_until_next(now):
                        break
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

    # ------------------------------------------------------------------
    # Gestión de modos de sesión (§9.3)
    # ------------------------------------------------------------------

    async def _check_mode_transition(self, now: datetime) -> None:
        """
        Llamar al inicio de cada iteración del bucle principal.
        Si ha llegado el momento de cambiar de modo, aplica la transición
        con sus efectos secundarios (cierre/relogin/seed-oasis).
        """
        # 1. Leer override (limpia automáticamente si está expirado)
        override = await self._get_override_safe()

        # 2. Calcular el modo que debería estar activo ahora
        timeline = await self._load_timeline(now)
        target_mode, new_jitter_fin = compute_current_mode(now, timeline, override)

        # 3. ¿Ha cambiado algo?
        if target_mode == self._active_mode and now < self._jitter_fin:
            return  # Sin transición: nada que hacer

        old_mode = self._active_mode
        self._active_mode = target_mode
        self._jitter_fin  = new_jitter_fin

        logger.info(
            "Mundo %d: modo %s → %s (jitter_fin=%s)",
            self.world_id, old_mode.value, target_mode.value,
            self._jitter_fin.isoformat(timespec="seconds"),
        )

        # 4. Efectos secundarios de la transición
        if target_mode == SessionMode.DISCONNECTED:
            # Cerrar Chrome de este mundo (RN-HS13)
            await self._close_chrome_safe()

        if old_mode == SessionMode.DISCONNECTED and target_mode != SessionMode.DISCONNECTED:
            # Salir de DISCONNECTED → relogin automático (RN-HS13)
            await self._relogin_with_backoff()

        if target_mode == SessionMode.HARDCORE and old_mode != SessionMode.HARDCORE:
            # Entrar en HARDCORE: reactivar oasis (RN-HS08)
            await self._safe_seed_oasis()

        # Al salir de HARDCORE → PASIVO o DISCONNECTED:
        # No cancelar tareas en vuelo. Las tareas OASIS en cola se consumen sin reencolar
        # (comprobado en el handler de SEND_OASIS_RAID si lo hay).

    async def _load_timeline(self, now: datetime) -> SessionTimeline:
        """
        Carga el timeline del día de la semana de 'now' desde BD.
        Si no existe configuración → devuelve el default hardcodeado (RN-HS11).
        """
        weekday = now.weekday()  # 0=lunes … 6=domingo
        if self._session_db is not None:
            timeline = await self._session_db.get_timeline(self.world_id, weekday)
            if timeline is not None:
                return timeline
        return get_default_timeline(self.world_id, weekday)

    async def _get_override_safe(self):
        """Lee el override de BD. Devuelve None si session_db no está inyectado."""
        if self._session_db is None:
            return None
        try:
            return await self._session_db.get_override(self.world_id)
        except Exception as exc:
            logger.warning("Mundo %d: error leyendo override: %s", self.world_id, exc)
            return None

    async def _close_chrome_safe(self) -> None:
        """Cierra Chrome del mundo. Captura excepciones para no abortar la transición."""
        if self._session_registry is None:
            return
        try:
            await self._session_registry.close_session(self.world_id)
            logger.info("Mundo %d: Chrome cerrado (DISCONNECTED)", self.world_id)
        except Exception as exc:
            logger.error("Mundo %d: error al cerrar Chrome: %s", self.world_id, exc)

    def _session_active(self) -> bool:
        """Devuelve True si hay sesión activa en el SessionRegistry."""
        if self._session_registry is None:
            return False
        return self._session_registry.has_active_session(self.world_id)

    async def _relogin_with_backoff(self) -> None:
        """
        Relogin automático con backoff exponencial: 10 → 20 → 40 → 60 min.

        FernetDecryptionError → estado DISCONNECTED-error sin backoff (EC-HS15).
        Error transitorio → reintento hasta éxito o hasta que el calendario
        cambie a DISCONNECTED (en cuyo caso el WorldAgent aborta el relogin —
        EC-HS16).

        Spec §9.3, RN-HS13.
        """
        if self._login_use_case is None or self._account_id is None:
            logger.warning(
                "Mundo %d: relogin requerido pero login_use_case/account_id no inyectados",
                self.world_id,
            )
            return

        delay_minutes = 10
        while True:
            # Comprobar si el calendario cambió a DISCONNECTED mientras esperábamos
            now = datetime.now()
            timeline = await self._load_timeline(now)
            override = await self._get_override_safe()
            calendar_mode, _ = compute_current_mode(now, timeline, override)
            if calendar_mode == SessionMode.DISCONNECTED:
                logger.info(
                    "Mundo %d: calendario vuelve a DISCONNECTED — abortando relogin",
                    self.world_id,
                )
                self._active_mode = SessionMode.DISCONNECTED
                await self._close_chrome_safe()
                return

            try:
                success = await self._login_use_case.execute(self._account_id, self.world_id)
                if success:
                    logger.info("Mundo %d: relogin completado", self.world_id)
                    return
                # Login devolvió False (sin excepción) — tratar como error transitorio
                raise RuntimeError("Login devolvió False")

            except FernetDecryptionError as exc:
                # Error de configuración — sin backoff (EC-HS15)
                logger.critical(
                    "Mundo %d: credencial no descifrable — DISCONNECTED-error: %s",
                    self.world_id, exc,
                )
                self._active_mode = SessionMode.DISCONNECTED
                self._log_act("error", "Credencial no disponible. Corregir y reiniciar.")
                return

            except asyncio.CancelledError:
                raise

            except Exception as exc:
                logger.error(
                    "Mundo %d: relogin fallido: %s. Reintento en %d min",
                    self.world_id, exc, delay_minutes,
                )
                if await self._sleep(delay_minutes * 60):
                    return  # stop_event disparado durante la espera
                delay_minutes = min(delay_minutes * 2, 60)

    async def _safe_seed_oasis(self) -> None:
        """
        Llama a seed_oasis_groups_from_db() capturando excepciones (EC-HS07).
        Si seed falla, el WorldAgent entra en HARDCORE igualmente sin oasis.
        """
        try:
            n = await self.seed_oasis_groups_from_db()
            logger.info("Mundo %d: %d grupos de oasis reencolados", self.world_id, n)
        except Exception as exc:
            logger.error(
                "Mundo %d: error en seed_oasis_groups_from_db: %s — HARDCORE sin oasis",
                self.world_id, exc,
            )

    async def seed_oasis_groups_from_db(self) -> int:
        """
        Stub de siembra de grupos de oasis.
        Implementación real cuando el spec de oasis-farming esté integrado.
        Devuelve 0 mientras no haya grupos que encolar.
        """
        return 0

    # ------------------------------------------------------------------
    # PASIVO — farm lists con probabilidad y multiplicador (§9.4 / RN-HS12)
    # ------------------------------------------------------------------

    async def _handle_send_farm_list_group_pasivo(self, task: Task) -> None:
        """
        Handler de SEND_FARM_LIST_GROUP en modo PASIVO.

        1. Dado de probabilidad: si roll >= passive_send_probability → SALTA.
        2. Multiplicador de intervalo: al reencolar, multiplica min/max por
           passive_interval_factor.
        """
        config = await self._get_session_config()

        roll = random.random()  # [0, 1)
        if roll >= config.passive_send_probability:
            logger.debug(
                "Mundo %d: SEND_FARM_LIST_GROUP skipped (PASIVO, roll=%.3f >= %.2f)",
                self.world_id, roll, config.passive_send_probability,
            )
            # Tarea consumida sin ejecutar → reencolar con intervalo multiplicado
            await self._reschedule_farm_pasivo(task, config)
            return

        # Ejecutar normalmente
        await self._execute(task)
        # Reencolar con intervalo multiplicado
        await self._reschedule_farm_pasivo(task, config)

    async def _reschedule_farm_pasivo(self, task: Task, config) -> None:
        """Reencola la tarea SEND_FARM_LIST_GROUP con el multiplicador PASIVO."""
        try:
            scheduler = await self._db.get_scheduler(task.source_scheduler_id)
        except SchedulerNotFoundError:
            logger.info(
                "Scheduler %d ya no existe — no se reencola (PASIVO)", task.source_scheduler_id
            )
            return
        if not scheduler.is_enabled:
            logger.info(
                "Scheduler %d deshabilitado — no se reencola (PASIVO)", scheduler.id
            )
            return

        factor = config.passive_interval_factor
        interval_min_ms = int(scheduler.interval_min_ms * factor)
        interval_max_ms = int(scheduler.interval_max_ms * factor)
        now = datetime.now()
        next_at = now + timedelta(milliseconds=random.randint(interval_min_ms, interval_max_ms))
        await self._db.update_scheduler_run_state(
            scheduler_id=scheduler.id,
            last_run=now,
            next_run=next_at,
            execution_count=scheduler.execution_count + 1,
        )
        self._queue.add(self._build_task(scheduler, next_at))
        logger.info(
            "Scheduler %d reencolado (PASIVO ×%.1f) para %s",
            scheduler.id, factor, next_at.isoformat(timespec="seconds"),
        )

    async def _get_session_config(self):
        """Devuelve la SessionConfig del mundo (o defaults si session_db no está inyectado)."""
        from core.entities.session import SessionConfig
        if self._session_db is not None:
            try:
                return await self._session_db.get_session_config(self.world_id)
            except Exception as exc:
                logger.warning("Mundo %d: error leyendo session config: %s", self.world_id, exc)
        return SessionConfig(world_id=self.world_id)  # defaults

    # ------------------------------------------------------------------
    # Sleep con soporte de stop y notify
    # ------------------------------------------------------------------

    async def _sleep(self, seconds: float) -> bool:
        """
        Espera 'seconds' segundos o hasta que se dispare _stop_event.
        Devuelve True si se pidió Stop durante la espera.
        """
        sleep_task  = asyncio.create_task(asyncio.sleep(seconds))
        stop_task   = asyncio.create_task(self._stop_event.wait())
        try:
            await asyncio.wait(
                {sleep_task, stop_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            for t in (sleep_task, stop_task):
                t.cancel()
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass
        return self._stop_event.is_set()

    async def _sleep_until_next(self, now: datetime) -> bool:
        """
        Espera hasta la próxima tarea, un notify (run_now) o Stop.
        Devuelve True si se pidió Stop durante la espera.
        """
        delay = self._queue.seconds_until_next(now)
        if delay is None:
            delay = self.DEFAULT_IDLE_SECONDS

        sleep_task  = asyncio.create_task(asyncio.sleep(delay))
        stop_task   = asyncio.create_task(self._stop_event.wait())
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

    # ------------------------------------------------------------------
    # Ejecución y reencole
    # ------------------------------------------------------------------

    async def _execute(self, task: Task) -> None:
        """
        Ejecuta una tarea. Un fallo no mata el agente: se loguea y se sigue.
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
            active_mode=self._active_mode.value if self._active_mode else None,
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
