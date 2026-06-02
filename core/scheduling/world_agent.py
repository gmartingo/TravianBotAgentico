"""
WorldAgent — agente ejecutor de un mundo con soporte de Human Sessions.

Mantiene un bucle asyncio que:
  1. Comprueba la transición de modo de sesión (_check_mode_transition).
  2. Según el modo activo (HARDCORE / PASIVO / DISCONNECTED), ejecuta o suspende tareas.
  3. Si la tarea es SEND_FARM_LIST_GROUP y el modo es PASIVO, aplica el dado de
     probabilidad y el multiplicador de intervalo (RN-HS12).
  4. Si la tarea es NOISE_NAVIGATION, ejecuta la navegación de ruido anti-detección
     (Human Sessions v2.2 — §9.7-9.10).

Un solo agente por mundo = nunca dos acciones de browser al mismo tiempo en
ese mundo, sin necesidad de locks. Distintos mundos corren en asyncio.Task
separados (browsers diferentes → concurrencia permitida).

La parada es limpia: _stop_event despierta el bucle desde _sleep_until_next
para que no haya que esperar hasta la próxima tarea.

Spec §9.3 (_check_mode_transition), §9.4 (PASIVO farm lists), §9.5 (bucle principal),
§9.7-9.10 (Ruido Humano de Navegación).
"""
from __future__ import annotations

import asyncio
import logging
import math
import random
from collections import deque
from dataclasses import dataclass, field as dc_field
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING

from core.entities.farm_scheduler import FarmScheduler
from core.entities.noise import (
    NavigationOrigin,
    NavigationPath,
    NavigationStep,
    NoiseAction,
    NoiseCategory,
    NoiseConfig,
    NoiseDestination,
    ORIGIN_PATHS,
)
from core.entities.session import (
    SessionMode,
    SessionTimeline,
    current_mode as compute_current_mode,
    get_default_timeline,
)
from core.entities.task import Task, TaskType
from core.exceptions import (
    BrowserBusyError,
    BrowserError,
    FernetDecryptionError,
    NoiseStepError,
    SchedulerNotFoundError,
)
from core.ports.farm_list_browser_port import FarmListBrowserPort
from core.ports.farm_list_db_port import FarmListDbPort
from core.ports.noise_db_port import NoiseDbPort
from core.ports.session_timeline_db_port import SessionTimelineDbPort
from core.scheduling.task_queue import TaskQueue
from core.use_cases.farm_lists import SendSchedulerGroupUseCase

if TYPE_CHECKING:
    import zendriver as zd

    from core.entities.session import SessionConfig, SessionOverride
    from core.ports.world_runtime_port import WorldRuntimePort
    from core.use_cases.login_use_case import LoginUseCase

logger = logging.getLogger(__name__)

# Número de fallos consecutivos de expected_url_after_click que marcan una ruta
# como is_dead=True. Spec noise-path-wizard.md RN-NP07.
NOISE_PATH_DEAD_THRESHOLD: int = 3

# Timeout en segundos para execute_path_test: tanto para adquirir el lock de browser
# como para el timeout global de la ejecución del test. Spec §16.4 (RN-PT04), §16.9.
PATH_TEST_TIMEOUT_SECONDS: int = 60


def _extract_url_path(url: str) -> str:
    """
    Extrae la parte del path de una URL para comparación tolerante.

    Si la URL es absoluta (contiene://), devuelve solo el path+query.
    Si ya es relativa, la devuelve tal cual.
    El dominio se ignora para tolerar diferencias entre entornos (EC-NP08).

    Spec noise-path-wizard.md §9.4, EC-NP08.

    Ejemplos:
        "https://ts1.travian.es/statistics" → "/statistics"
        "/statistics" → "/statistics"
        "/statistics?session=123" → "/statistics?session=123"
    """
    from urllib.parse import urlparse  # stdlib
    parsed = urlparse(url)
    # Si tiene netloc, es absoluta; devolver path (con query si la tiene)
    if parsed.netloc:
        result = parsed.path
        if parsed.query:
            result += "?" + parsed.query
        return result or url
    # Relativa: devolver tal cual
    return url


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
        noise_db: NoiseDbPort | None = None,  # puerto de ruido de navegación (v2.2)
    ) -> None:
        self.world_id    = world_id
        self._browser    = browser
        self._db         = db
        self._session_db = session_db
        self._session_registry = session_registry
        self._login_use_case   = login_use_case
        self._account_id = account_id
        self._noise_db   = noise_db

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

        # Estado de ruido — máquina de estados burst/silence (RN-HS24bis)
        self._noise_in_burst: bool = False
        self._noise_burst_remaining: int = 0  # clicks restantes en el burst actual
        self._noise_recent_count: int = 0     # navegaciones en las últimas 30 min
        self._noise_window_start: datetime = datetime.now()

        # Contador de tráfico productivo (SEND_FARM_LIST_GROUP) en ventana de 30 min.
        # Se usa para descontarlo del target de req/h al calcular el gap del ruido,
        # garantizando que el tráfico total observable (productivo+ruido) ≤ ceiling.
        self._productive_recent_count: int = 0
        self._productive_window_start: datetime = datetime.now()

        # Lock de browser: serializa _execute_noise_action, execute_path_test y
        # refresh_villages para evitar interleaving de comandos CDP en el mismo tab.
        # Spec noise-path-wizard.md §16.9, §16.11, R-PT02.
        self._browser_lock: asyncio.Lock = asyncio.Lock()

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

        # Si arranca en modo activo → inicializar bucle de ruido (RN-HS24, Opción B)
        if self._active_mode in (SessionMode.HARDCORE, SessionMode.PASIVO):
            await self._safe_seed_noise_loop()

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
            # Inicializar bucle de ruido si no hay NOISE_NAVIGATION ya encoladas (RN-HS24)
            if not self._queue.has_task_type(TaskType.NOISE_NAVIGATION):
                await self._safe_seed_noise_loop()

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
                    # RN-HS24quater: warmup post-relogin — encolar 1-3 NOISE antes de
                    # reanudar tareas productivas
                    warmup_n = random.randint(1, 3)
                    await self._enqueue_noise_warmup(warmup_n)
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

    async def _safe_seed_noise_loop(self) -> None:
        """
        Llama a seed_noise_loop_on_session_start() capturando excepciones.
        Si falla, el bucle de ruido no arranca pero el agente continúa.
        """
        try:
            await self.seed_noise_loop_on_session_start()
        except Exception as exc:
            logger.error(
                "Mundo %d: error al inicializar bucle de ruido: %s — ruido deshabilitado",
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
                # Contabilizar para que el ruido descuente este tráfico productivo
                # al calcular el siguiente gap (guardian amber #1).
                self._productive_recent_count += 1

            elif task.task_type == TaskType.NOISE_NAVIGATION:
                await self._handle_noise_navigation()

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

    # ------------------------------------------------------------------
    # Ruido Humano de Navegación — §9.7-9.10 (Human Sessions v2.2)
    # ------------------------------------------------------------------

    async def _get_noise_config(self) -> NoiseConfig:
        """Devuelve la configuración de ruido (o defaults si noise_db no está inyectado)."""
        if self._noise_db is not None:
            try:
                return await self._noise_db.get_or_create_noise_config(self.world_id)
            except Exception as exc:
                logger.warning(
                    "Mundo %d: error leyendo noise config: %s — usando defaults",
                    self.world_id, exc,
                )
        return NoiseConfig(world_id=self.world_id)

    def _calculate_next_noise_gap(
        self,
        mode: SessionMode,
        config: NoiseConfig,
        recent_productive_traffic: int = 0,
    ) -> float:
        """
        Calcula el gap en segundos hasta la siguiente NOISE_NAVIGATION.

        Distribución bursty (RN-HS24bis): máquina de estados burst/silence.
          - Burst:   gap = uniform(0.5, 4.0) s.
          - Silence: gap = expovariate(1 / (base_gap × 3.5)), cap [20, 600] s.
          - base_gap = 3600 / uniform(target_min, target_max), descontando tráfico productivo.

        Returns:
            Segundos hasta la próxima navegación de ruido (float >= 0.5).
        """
        if mode == SessionMode.HARDCORE:
            target_min = max(1, config.hardcore_total_req_per_hour_min - recent_productive_traffic)
            target_max = max(1, config.hardcore_total_req_per_hour_max - recent_productive_traffic)
        else:  # PASIVO
            target_min = max(1, config.passive_total_req_per_hour_min - recent_productive_traffic)
            target_max = max(1, config.passive_total_req_per_hour_max - recent_productive_traffic)

        rate = random.uniform(target_min, target_max)
        base_gap = 3600.0 / max(rate, 1.0)  # segundos por navegación en promedio

        if self._noise_in_burst:
            gap = random.uniform(0.5, 4.0)
            self._noise_burst_remaining -= 1
            if self._noise_burst_remaining <= 0:
                self._noise_in_burst = False
                logger.debug("Mundo %d: ruido — fin de burst, pasando a silence", self.world_id)
        else:
            # Silence: exponencial con media = base_gap × 3.5, cap [20, 600]
            mean = base_gap * 3.5
            raw = random.expovariate(1.0 / mean)
            gap = max(20.0, min(600.0, raw))

            # Decidir si el próximo ciclo entra en burst (~40%) o sigue en silence (~60%)
            if random.random() < 0.40:
                self._noise_in_burst = True
                self._noise_burst_remaining = random.randint(3, 12)
                logger.debug(
                    "Mundo %d: ruido — próximo ciclo será burst (%d clicks)",
                    self.world_id, self._noise_burst_remaining,
                )

        return gap

    async def _select_noise_action(
        self,
    ) -> tuple[NoiseDestination, NavigationPath] | None:
        """
        Selecciona aleatoriamente un destino y una ruta compatible con el estado
        actual del browser (origin). Reintenta hasta 3 veces si no hay paths compatibles.

        Devuelve None si el catálogo está vacío o no hay combinación válida.
        """
        if self._noise_db is None:
            return None

        # Obtener URL actual del browser para mapear origin
        current_origin = await self._get_current_origin()

        for attempt in range(3):
            dest = await self._noise_db.pick_random_safe_destination(self.world_id)
            if dest is None:
                logger.info(
                    "Mundo %d: catálogo de ruido vacío — sin destinos disponibles",
                    self.world_id,
                )
                return None

            paths = await self._noise_db.list_paths(dest.id)
            # Filtrar paths activos, no muertos y compatibles con el origin actual.
            # CA-NP33: rutas con is_dead=True se excluyen del pool (spec RN-NP07 + EC-NP09).
            compatible = [
                p for p in paths
                if p.is_active and not p.is_dead and (
                    p.origin == NavigationOrigin.ANY
                    or p.origin == NavigationOrigin.ANY.value
                    or p.origin == current_origin
                    or p.origin == current_origin.value
                )
            ]

            if compatible:
                path = random.choice(compatible)
                return dest, path

            logger.debug(
                "Mundo %d: destino %d sin paths compatibles con origin=%s (intento %d/3)",
                self.world_id, dest.id, current_origin.value, attempt + 1,
            )

        logger.info(
            "Mundo %d: no se encontró ningún path compatible tras 3 intentos",
            self.world_id,
        )
        return None

    async def _get_current_origin(self) -> NavigationOrigin:
        """
        Intenta leer la URL actual del browser para determinar el origin.
        Si no hay browser o falla, devuelve ANY.
        """
        # El browser (FarmListBrowserPort) no expone URL directamente en la interfaz
        # abstracta. Intentamos obtenerla via duck typing si el adaptador lo soporta.
        try:
            if hasattr(self._browser, "get_current_url"):
                url = await self._browser.get_current_url(self.world_id)
                url_lower = url.lower()
                if "dorf1" in url_lower or "dorfplatz" in url_lower:
                    return NavigationOrigin.DORF1
                if "dorf2" in url_lower or "gebaeude" in url_lower:
                    return NavigationOrigin.DORF2
                if "karte" in url_lower or "map" in url_lower:
                    return NavigationOrigin.MAP
        except Exception:
            pass
        return NavigationOrigin.ANY

    async def _execute_noise_step(self, tab: "zd.Tab", step: NavigationStep) -> None:
        """
        Ejecuta un único paso de la ruta de ruido en el tab activo.

        Lanza NoiseStepError si el paso no puede completarse.

        Acciones soportadas:
          CLICK             — scrollIntoView + getBoundingClientRect + human_click_at_rect.
          WAIT_FOR_SELECTOR — tab.wait_for(selector, timeout=int(value or 10)).
          SCROLL_TO         — scrollIntoView via JS, sin click.
          HOVER             — scrollIntoView + getBoundingClientRect + human_drift_toward.
        """
        # Import diferido para no crear dependencia circular en el módulo de core.
        # driver.py vive en adapters/, pero world_agent.py es core/.
        # Este import se resuelve en tiempo de ejecución, nunca en tiempo de carga.
        from adapters.browser.driver import (  # noqa: PLC0415
            human_click_at_rect,
            human_delay,
            human_drift_toward,
        )

        action = step.action
        selector = step.selector

        if action == NoiseAction.CLICK:
            rect = await tab.evaluate(
                f"""
                (() => {{
                    const el = document.querySelector({selector!r});
                    if (!el) return null;
                    el.scrollIntoView({{block: 'center', inline: 'nearest', behavior: 'instant'}});
                    const r = el.getBoundingClientRect();
                    return {{x: r.left, y: r.top, width: r.width, height: r.height}};
                }})()
                """
            )
            if not rect:
                raise NoiseStepError(
                    action=action.value, selector=selector,
                    reason="elemento no encontrado en el DOM",
                )
            await human_click_at_rect(rect, tab)

            # NUEVO (noise-path-wizard.md §9.4, RN-NP06):
            # Verificar la URL esperada tras el click si está configurada.
            # Se comprueba por containment para tolerar query strings adicionales.
            if step.expected_url_after_click:
                # ANTI-DETECCION: tras un click que navega, un humano NO comprueba
                # el resultado en el mismo instante; espera a que la página cargue.
                # Además, leer tab.url antes de que la navegación termine produciría
                # falsos negativos que dispararían increment_path_failures /
                # mark_path_dead erróneamente. Esperamos un tramo humanizado
                # (carga real de Travian) antes de leer la URL. El delay del step
                # del caller ocurre DESPUES de retornar de aquí, no antes, por lo
                # que esta espera es la única previa a la lectura de URL.
                await human_delay(900, 1600)
                # tab.url es propiedad sincrónica en zendriver (verificado en login.py:59)
                current_url: str = tab.url
                expected_path = _extract_url_path(step.expected_url_after_click)
                if expected_path not in current_url:
                    raise NoiseStepError(
                        action=action.value, selector=selector,
                        reason=(
                            f"URL esperada '{step.expected_url_after_click}' "
                            f"no encontrada en '{current_url}'"
                        ),
                    )

        elif action == NoiseAction.WAIT_FOR_SELECTOR:
            timeout_seconds = int(step.value) if step.value else 10
            try:
                await tab.wait_for(selector, timeout=timeout_seconds)
            except asyncio.TimeoutError as exc:
                raise NoiseStepError(
                    action=action.value, selector=selector,
                    reason=f"timeout tras {timeout_seconds}s",
                ) from exc
            except Exception as exc:
                raise NoiseStepError(
                    action=action.value, selector=selector,
                    reason=str(exc),
                ) from exc

        elif action == NoiseAction.SCROLL_TO:
            found = await tab.evaluate(
                f"""
                (() => {{
                    const el = document.querySelector({selector!r});
                    if (!el) return false;
                    el.scrollIntoView({{block: 'center', behavior: 'instant'}});
                    return true;
                }})()
                """
            )
            if not found:
                raise NoiseStepError(
                    action=action.value, selector=selector,
                    reason="elemento no encontrado en el DOM",
                )

        elif action == NoiseAction.HOVER:
            rect = await tab.evaluate(
                f"""
                (() => {{
                    const el = document.querySelector({selector!r});
                    if (!el) return null;
                    el.scrollIntoView({{block: 'center', inline: 'nearest', behavior: 'instant'}});
                    const r = el.getBoundingClientRect();
                    return {{x: r.left, y: r.top, width: r.width, height: r.height}};
                }})()
                """
            )
            if not rect:
                raise NoiseStepError(
                    action=action.value, selector=selector,
                    reason="elemento no encontrado en el DOM",
                )
            duration_ms = random.uniform(400, 900)
            await human_drift_toward(rect, tab, duration_ms=duration_ms, end_distance_px=0)

        else:
            logger.warning(
                "Mundo %d: acción de ruido desconocida '%s' — paso omitido",
                self.world_id, action,
            )

    async def _execute_noise_action(
        self,
        dest: NoiseDestination,
        path: NavigationPath,
        config: NoiseConfig,
    ) -> str:
        """
        Ejecuta los pasos de la ruta de ruido en orden usando el browser activo.

        Para cada step: _execute_noise_step + human_delay(step.delay_min_ms, step.delay_max_ms).
        Tras completar todos los pasos: dwell aleatorio [dwell_min, dwell_max] segundos.
        En caso de error: bump_destination_failures; si >= 3 → mark_destination_dead.

        Si no hay browser activo (mundo en DISCONNECTED o sesión caída) → "error"
        sin marcar el destino como fallido (no es su culpa).

        Returns:
            "ok"    — todos los pasos completados.
            "error" — algún paso falló o no hay browser.
        """
        from adapters.browser.driver import human_delay  # noqa: PLC0415

        if self._noise_db is None:
            return "error"

        # Obtener el browser activo via session_registry (duck typing — el registry
        # concreto expone get_browser aunque WorldRuntimePort no lo declare).
        browser = None
        if self._session_registry is not None and hasattr(self._session_registry, "get_browser"):
            browser = self._session_registry.get_browser(self.world_id)

        if browser is None:
            logger.warning(
                "Mundo %d: sin browser activo, ruido descartado (no es fallo del destino)",
                self.world_id,
            )
            return "error"

        # Adquirir el lock de browser antes de acceder al tab.
        # Serializa _execute_noise_action, execute_path_test y refresh_villages para
        # evitar interleaving de comandos CDP en el mismo tab.
        # Spec noise-path-wizard.md §16.11, §16.14 Paso 2, R-PT02.
        async with self._browser_lock:
            tab = browser.main_tab

            logger.info(
                "Mundo %d: NOISE_NAVIGATION → destino '%s' vía path '%s' (%d pasos)",
                self.world_id, dest.label, path.label, len(path.steps),
            )
            self._log_act(
                "info",
                f"Ruido: navegando a '{dest.label}' ({len(path.steps)} pasos)",
            )

            try:
                for step in path.steps:
                    await self._execute_noise_step(tab, step)
                    await human_delay(step.delay_min_ms, step.delay_max_ms)

                # Dwell final tras llegar al destino (RN-NP09 — ya existente)
                dwell_s = random.uniform(config.dwell_min_seconds, config.dwell_max_seconds)
                await asyncio.sleep(dwell_s)

            except asyncio.CancelledError:
                raise
            except (NoiseStepError, asyncio.TimeoutError) as exc:
                logger.warning(
                    "Mundo %d: ruido falló en step (%s / ruta '%s'): %s",
                    self.world_id, dest.label, path.label, exc,
                )
                # Fallos a nivel de DESTINO (ya existentes)
                new_dest_count = await self._noise_db.bump_destination_failures(dest.id)
                if new_dest_count >= 3:
                    await self._noise_db.mark_destination_dead(dest.id)
                    self._log_act("warn", f"Ruido: destino '{dest.label}' marcado dead tras 3 fallos")
                    logger.warning(
                        "Mundo %d: destino '%s' marcado como muerto (%d fallos consecutivos)",
                        self.world_id, dest.label, new_dest_count,
                    )
                # NUEVO: fallos a nivel de RUTA (spec noise-path-wizard.md §9.4, RN-NP07, CA-NP30/31)
                if path.id is not None:
                    new_path_count = await self._noise_db.increment_path_failures(path.id)
                    if new_path_count >= NOISE_PATH_DEAD_THRESHOLD:
                        await self._noise_db.mark_path_dead(path.id)
                        self._log_act(
                            "warn",
                            f"Ruido: ruta '{path.label}' marcada dead tras {new_path_count} fallos",
                        )
                        logger.warning(
                            "Mundo %d: ruta '%s' marcada como muerta (%d fallos consecutivos de URL)",
                            self.world_id, path.label, new_path_count,
                        )
                return "error"
            except Exception as exc:
                logger.error(
                    "Mundo %d: error inesperado ejecutando noise action en '%s' / ruta '%s': %s",
                    self.world_id, dest.label, path.label, exc,
                )
                new_dest_count = await self._noise_db.bump_destination_failures(dest.id)
                if new_dest_count >= 3:
                    await self._noise_db.mark_destination_dead(dest.id)
                    self._log_act("warn", f"Ruido: destino '{dest.label}' marcado dead tras 3 fallos")
                if path.id is not None:
                    new_path_count = await self._noise_db.increment_path_failures(path.id)
                    if new_path_count >= NOISE_PATH_DEAD_THRESHOLD:
                        await self._noise_db.mark_path_dead(path.id)
                        logger.warning(
                            "Mundo %d: ruta '%s' marcada como muerta (%d fallos consecutivos de URL)",
                            self.world_id, path.label, new_path_count,
                        )
                return "error"

        # Éxito completo: actualizar contadores y last_used_at.
        # Estas operaciones son de BD (no de browser) y ocurren fuera del lock.
        # spec noise-path-wizard.md §9.4, CA-NP32.
        await self._noise_db.reset_destination_failures(dest.id)
        await self._noise_db.touch_last_used_at(dest.id, datetime.now())
        if path.id is not None:
            await self._noise_db.reset_path_failures(path.id)
        self._log_act("ok", f"Ruido: '{dest.label}' completado")

        # Actualizar contador de tráfico de ruido para _is_noise_below_min_threshold
        self._noise_recent_count += 1

        return "ok"

    def _is_noise_below_min_threshold(self, config: NoiseConfig) -> bool:
        """
        RN-HS24ter: devuelve True si el ratio efectivo de ruido cae <40% del target mínimo
        durante la ventana de los últimos 30 min.
        """
        now = datetime.now()
        window_seconds = (now - self._noise_window_start).total_seconds()

        # Resetear ventana cada 30 minutos
        if window_seconds >= 1800:
            self._noise_recent_count = 0
            self._noise_window_start = now
            return False

        if window_seconds < 60:
            # Ventana demasiado pequeña para calcular ratio significativo
            return False

        # Extrapolamos la tasa actual a 30 min
        target_min = (
            config.hardcore_total_req_per_hour_min
            if self._active_mode == SessionMode.HARDCORE
            else config.passive_total_req_per_hour_min
        )
        # target en 30 min = target_per_hour / 2
        target_in_30min = target_min / 2.0
        # efectivo en la ventana actual, extrapolado a 30 min
        effective = self._noise_recent_count * (1800.0 / window_seconds)

        return effective < (target_in_30min * 0.40)

    def _should_reenqueue_noise(self) -> bool:
        """Reenqueue NOISE_NAVIGATION si estamos en HARDCORE o PASIVO (no DISCONNECTED)."""
        return self._active_mode in (SessionMode.HARDCORE, SessionMode.PASIVO)

    def _get_productive_recent_rate(self) -> int:
        """
        Extrapola el contador de tráfico productivo en la ventana actual a req/h.
        Resetea la ventana cada 30 min para evitar acumulación indefinida.
        Devuelve 0 si la ventana es < 60 s (muestra insuficiente).

        Guardian amber #1: descontar tráfico productivo del target de ruido
        para no superar el ceiling configurado.
        """
        now = datetime.now()
        window_seconds = (now - self._productive_window_start).total_seconds()
        if window_seconds >= 1800:
            self._productive_recent_count = 0
            self._productive_window_start = now
            return 0
        if window_seconds < 60:
            return 0
        # Extrapolar a 1 hora
        return int(self._productive_recent_count * (3600.0 / window_seconds))

    def _enqueue_noise(self, execute_at: datetime, priority: int = 2) -> None:
        """Encola una tarea NOISE_NAVIGATION con la prioridad indicada."""
        task = Task(
            task_type=TaskType.NOISE_NAVIGATION,
            world_id=self.world_id,
            execute_at=execute_at,
            priority=priority,
            payload={},
            recurring=False,  # se reencola manualmente tras cada ejecución
            source_scheduler_id=None,
        )
        self._queue.add(task)
        logger.debug(
            "Mundo %d: NOISE_NAVIGATION encolada para %s (priority=%d)",
            self.world_id, execute_at.isoformat(timespec="seconds"), priority,
        )

    async def seed_noise_loop_on_session_start(self) -> None:
        """
        Encola la primera NOISE_NAVIGATION al arrancar en HARDCORE o PASIVO.
        El gap inicial se calcula con _calculate_next_noise_gap.
        """
        if self._active_mode not in (SessionMode.HARDCORE, SessionMode.PASIVO):
            return
        if self._noise_db is None:
            return

        config = await self._get_noise_config()
        if not config.noise_enabled:
            return

        gap = self._calculate_next_noise_gap(
            self._active_mode,
            config,
            recent_productive_traffic=self._get_productive_recent_rate(),
        )
        execute_at = datetime.now() + timedelta(seconds=gap)
        self._enqueue_noise(execute_at)
        logger.info(
            "Mundo %d: ruido inicializado — primera NOISE_NAVIGATION en %.0f s",
            self.world_id, gap,
        )

    async def _handle_noise_navigation(self) -> None:
        """
        Handler de TaskType.NOISE_NAVIGATION.

        - No ejecuta en DISCONNECTED o si noise_enabled=False.
        - Selecciona destino + path compatibles.
        - Ejecuta la navegación de ruido.
        - Reencola si debe.
        - RN-HS24ter: si ratio bajo, usa priority=1.
        """
        if self._active_mode not in (SessionMode.HARDCORE, SessionMode.PASIVO):
            logger.debug(
                "Mundo %d: NOISE_NAVIGATION ignorada (modo=%s)",
                self.world_id, self._active_mode.value,
            )
            return

        if self._noise_db is None:
            return

        config = await self._get_noise_config()
        if not config.noise_enabled:
            logger.debug("Mundo %d: ruido deshabilitado (noise_enabled=False)", self.world_id)
            return

        selected = await self._select_noise_action()
        if selected is None:
            logger.info(
                "Mundo %d: catálogo de ruido vacío o sin paths válidos — omitiendo",
                self.world_id,
            )
        else:
            dest, path = selected
            await self._execute_noise_action(dest, path, config)

        if self._should_reenqueue_noise():
            priority = 1 if self._is_noise_below_min_threshold(config) else 2
            gap = self._calculate_next_noise_gap(
                self._active_mode,
                config,
                recent_productive_traffic=self._get_productive_recent_rate(),
            )
            execute_at = datetime.now() + timedelta(seconds=gap)
            self._enqueue_noise(execute_at, priority=priority)

    async def _enqueue_noise_warmup(self, n: int = 2) -> None:
        """
        RN-HS24quater: warmup post-relogin.
        Encola n tareas NOISE_NAVIGATION (preferiblemente MESSAGES/REPORTS)
        con separación de 1.5-4.5 segundos entre ellas, ANTES de cualquier
        tarea productiva. Se encolan todas antes de que el bucle principal
        arranque tareas productivas, con priority=1 para ejecutarse primero.
        """
        if self._noise_db is None:
            return

        config = await self._get_noise_config()
        if not config.noise_enabled:
            return

        # Prefetch destinos de MESSAGES o REPORTS para warmup más creíble
        warmup_count = max(1, min(n, 3))
        now = datetime.now()
        delay = 0.0

        for i in range(warmup_count):
            # Espaciado humano entre warmup tasks
            delay += random.uniform(1.5, 4.5)
            execute_at = now + timedelta(seconds=delay)
            # priority=0 (máxima): warmup DEBE ganar a cualquier farm task que
            # estuviera lista en el momento del relogin. Si fuera priority=1
            # (igual que farm), una farm task con execute_at < now ganaría
            # y la primera acción observable tras el relogin sería un raid,
            # defeating the purpose del warmup. Guardian amber #2.
            self._enqueue_noise(execute_at, priority=0)

        logger.info(
            "Mundo %d: warmup post-relogin — %d NOISE_NAVIGATION encoladas "
            "(priority=0, ganan siempre a productivas)",
            self.world_id, warmup_count,
        )

    # ------------------------------------------------------------------
    # refresh_villages (spec noise-path-wizard.md §9, RN-NP03, EP-N13)
    # ------------------------------------------------------------------

    async def refresh_villages(self) -> list:
        """
        Ejecuta el parser del village-switcher y persiste las aldeas encontradas.

        Devuelve la lista de Village upserteadas (puede ser vacía si el
        selector no encontró elementos en el DOM).

        Lanza RuntimeError si no hay browser activo (sesión cerrada/no iniciada).
        El endpoint EP-N13 ya garantiza que el agente está en estado RUNNING
        antes de llamar este método.

        Spec noise-path-wizard.md §9, RN-NP03, CA-NP20.
        """
        # Import diferido para no crear dependencia circular
        from adapters.browser.village_switcher import parse_village_switcher  # noqa: PLC0415

        # Obtener browser activo vía session_registry
        browser = None
        if self._session_registry is not None and hasattr(self._session_registry, "get_browser"):
            browser = self._session_registry.get_browser(self.world_id)

        if browser is None:
            raise RuntimeError(
                f"Mundo {self.world_id}: no hay browser activo para ejecutar "
                "el parser del village-switcher."
            )

        # Adquirir el lock de browser antes de acceder al tab.
        # parse_village_switcher usa tab.evaluate() — serializar con _execute_noise_action
        # y execute_path_test para evitar interleaving de CDP. Spec §16.11, §16.14 Paso 2.
        async with self._browser_lock:
            tab = browser.main_tab

            # Parsear el village-switcher (solo lectura del DOM)
            villages = await parse_village_switcher(tab, self.world_id)

        if self._noise_db is None:
            logger.warning(
                "Mundo %d: noise_db no disponible — aldeas parseadas pero no persistidas",
                self.world_id,
            )
            return villages

        # UPSERT de cada aldea en la tabla villages
        upserted = []
        for village in villages:
            try:
                saved = await self._noise_db.upsert_village(village)
                upserted.append(saved)
            except Exception as exc:
                logger.warning(
                    "Mundo %d: error upserteando aldea data_id=%d ('%s'): %s",
                    self.world_id, village.data_id, village.name, exc,
                )

        logger.info(
            "Mundo %d: refresh_villages — %d/%d aldeas persistidas en BD",
            self.world_id, len(upserted), len(villages),
        )
        return upserted

    # ------------------------------------------------------------------
    # EP-N14 — Test en vivo de ruta de navegación (no-destructivo)
    # ------------------------------------------------------------------

    async def execute_path_test(self, path: NavigationPath) -> "PathTestReport":
        """
        Ejecuta la ruta en vivo en el browser real y devuelve un reporte paso a paso.

        NO modifica BD, NO incrementa contadores de fallos, NO ejecuta dwell final.
        Es puramente informativo (diagnóstico). Spec §16.

        ANTI-DETECCIÓN: usa los mismos human_click/_execute_noise_step que producción.
        GATE GUARDIAN: esta función toca el browser real de Travian — revisar antes del commit.

        Returns: PathTestReport con el resultado de cada paso.
        Raises:
            BrowserBusyError — si no consigue el _browser_lock en PATH_TEST_TIMEOUT_SECONDS.
            RuntimeError — si no hay browser activo o servidor no disponible.
        """
        from adapters.browser.driver import human_delay      # noqa: PLC0415
        from adapters.browser.url_utils import build_url     # noqa: PLC0415
        from core.entities.noise_test import PathTestReport, PathTestStepResult  # noqa: PLC0415

        # Obtener browser activo
        browser = None
        if self._session_registry is not None and hasattr(self._session_registry, "get_browser"):
            browser = self._session_registry.get_browser(self.world_id)
        if browser is None:
            raise RuntimeError(
                f"Mundo {self.world_id}: no hay browser activo para execute_path_test."
            )

        tab = browser.main_tab

        # Intentar adquirir el lock de browser con timeout.
        # Si el lock está tomado por _execute_noise_action o refresh_villages, esperamos.
        # Si supera PATH_TEST_TIMEOUT_SECONDS → BrowserBusyError → handler HTTP → 409.
        try:
            await asyncio.wait_for(
                self._browser_lock.acquire(),
                timeout=PATH_TEST_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            raise BrowserBusyError(
                world_id=self.world_id,
                timeout_s=PATH_TEST_TIMEOUT_SECONDS,
            )

        report = PathTestReport(overall="ok")

        try:
            # Envolver toda la ejecución en un timeout global (RN-PT04)
            async with asyncio.timeout(PATH_TEST_TIMEOUT_SECONDS):

                # 1. Navegar al ancla de origen (salvo ANY) — RN-PT03
                anchor_url: str | None = None
                if path.origin != NavigationOrigin.ANY.value:
                    server = None
                    if (self._session_registry is not None
                            and hasattr(self._session_registry, "get_world_server")):
                        server = self._session_registry.get_world_server(self.world_id)
                    # get_world_server devuelve "" (no None) si no hay sesión activa:
                    # `not server` cubre ambos casos (None en tests, "" en el adapter real).
                    if not server:
                        raise RuntimeError(
                            f"Mundo {self.world_id}: servidor del mundo no disponible "
                            "para construir la URL del ancla."
                        )

                    if path.origin.startswith("VILLAGE_"):
                        # "VILLAGE_12345" → "/dorf1.php?newdid=12345"
                        data_id = path.origin[8:]
                        relative = f"/dorf1.php?newdid={data_id}"
                    else:
                        # Valor del enum genérico
                        try:
                            origin_enum = NavigationOrigin(path.origin)
                            relative = ORIGIN_PATHS.get(origin_enum, "")
                        except ValueError:
                            relative = ""  # origen desconocido — ejecutar desde donde esté

                    if relative:
                        anchor_url = build_url(server, relative)
                        # La navegación al ancla es una interacción con el browser que
                        # puede fallar (URL inalcanzable, error CDP/zendriver, ...). Igual
                        # que un paso, NO debe convertirse en un 500: se reporta como un
                        # paso sintético "error" y se aborta con gracia (RN-PT05).
                        # Cancelación/timeout se propagan al except externo (RN-PT04).
                        try:
                            await browser.get(anchor_url)
                            await human_delay(500, 900)
                            report.anchor_navigated_to = anchor_url
                        except asyncio.CancelledError:
                            raise
                        except asyncio.TimeoutError:
                            raise
                        except Exception as exc:
                            reason = getattr(exc, "reason", None) or str(exc) or exc.__class__.__name__
                            report.steps.append(PathTestStepResult(
                                step_order=-1,
                                action="GOTO_ANCHOR",
                                selector=anchor_url,
                                status="error",
                                reason=f"no se pudo navegar al ancla: {reason}",
                                current_url=None,
                            ))
                            report.overall = "error"
                            report.aborted_at_step = -1
                            return report

                # 2. Ejecutar pasos en orden (RN-PT05: abortar al primer error)
                steps_sorted = sorted(path.steps, key=lambda s: s.step_order)

                for step in steps_sorted:
                    current_url: str | None = None
                    try:
                        # URL antes del paso (propiedad sincrónica en zendriver)
                        current_url = tab.url
                        await self._execute_noise_step(tab, step)
                        # URL tras el paso
                        current_url = tab.url
                        step_result = PathTestStepResult(
                            step_order=step.step_order,
                            action=step.action.value,
                            selector=step.selector,
                            status="ok",
                            reason=None,
                            current_url=current_url,
                        )
                        report.steps.append(step_result)
                        # Delay humano entre pasos (igual que en _execute_noise_action)
                        await human_delay(step.delay_min_ms, step.delay_max_ms)

                    except (NoiseStepError, BrowserError) as exc:
                        # Fallo a nivel de PASO: se reporta como status="error" y aborta
                        # con gracia (RN-PT05), sin convertirse en un 500.
                        # - NoiseStepError: el paso falló (selector no encontrado, URL
                        #   esperada no alcanzada, timeout de WAIT_FOR_SELECTOR, ...).
                        # - BrowserError (incluye ElementNotClickableError): el elemento
                        #   existe en el DOM pero no es clicable (width/height 0, offscreen).
                        #   Antes burbujeaba sin capturar y el handler devolvía 500.
                        # Los errores realmente inesperados (bugs) NO se capturan aquí:
                        # suben al except externo y acaban en 500 (contrato EP-N14, UT-PT14).
                        reason = getattr(exc, "reason", None) or str(exc) or exc.__class__.__name__
                        step_result = PathTestStepResult(
                            step_order=step.step_order,
                            action=step.action.value,
                            selector=step.selector,
                            status="error",
                            reason=reason,
                            current_url=current_url,
                        )
                        report.steps.append(step_result)
                        report.overall = "error"
                        report.aborted_at_step = step.step_order
                        break  # abortar al primer error (RN-PT05)

        except asyncio.TimeoutError:
            # Timeout global (RN-PT04): el timeout ocurrió fuera de un paso medido
            # (p.ej. en human_delay, en la navegación al ancla, o entre pasos).
            # NoiseStepError captura los timeouts de WAIT_FOR_SELECTOR internamente,
            # así que si llegamos aquí el overall no debería ser "error" aún.
            if report.overall != "error":
                last_step_order = (
                    report.steps[-1].step_order if report.steps else -1
                )
                report.steps.append(PathTestStepResult(
                    step_order=last_step_order + 1,
                    action="TIMEOUT",
                    selector="(timeout global)",
                    status="error",
                    reason=f"timeout global del test ({PATH_TEST_TIMEOUT_SECONDS}s)",
                    current_url=None,
                ))
                report.overall = "error"
                report.aborted_at_step = last_step_order + 1

        except Exception:
            # Error inesperado — re-raise para que el handler devuelva 500.
            # El finally liberará el lock siempre.
            raise

        finally:
            # Siempre liberar el lock, incluso si hubo excepción (CA-PT18)
            self._browser_lock.release()

        logger.info(
            "Mundo %d: execute_path_test → overall='%s', pasos=%d, aborted_at=%s",
            self.world_id, report.overall, len(report.steps), report.aborted_at_step,
        )
        return report
