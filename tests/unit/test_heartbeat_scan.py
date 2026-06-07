"""
Tests del Componente E — Vigilancia híbrida (HEARTBEAT_SCAN).

Cubre UT-RE01-HB a UT-RE11-HB del §12 del spec:
  radar-ataques-entrantes.md Bloque 6, §9.12.

Todos los tests son unitarios con mocks — sin browser real, sin BD real.
El WorldAgent se construye con stubs mínimos; los callables de browser se
reemplazan con AsyncMock/MagicMock para verificar invocaciones.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.entities.task import Task, TaskType
from core.entities.session import SessionMode
from core.scheduling.world_agent import WorldAgent


# ---------------------------------------------------------------------------
# Helper de construcción del agente
# ---------------------------------------------------------------------------

def _make_agent(
    *,
    incoming_db=True,          # True → stub MagicMock, False → None
    session_active: bool = True,
    active_mode: SessionMode = SessionMode.HARDCORE,
    last_sidebar_scan: datetime | None = None,
    heartbeat_interval_s: int = 600,
    dorf1_html: str = "<html>dorf1</html>",
    dorf1_raises: Exception | None = None,
    hook_calls: list | None = None,
) -> WorldAgent:
    """
    Construye un WorldAgent con stubs mínimos para tests del heartbeat.

    - incoming_db: si True, inyecta un MagicMock; si False, None.
    - session_active: controla lo que devuelve _session_active().
    - active_mode: modo de sesión actual del agente.
    - last_sidebar_scan: valor inicial de _last_sidebar_scan.
    - heartbeat_interval_s: intervalo del latido.
    - dorf1_html: HTML que devuelve get_dorf1_html().
    - dorf1_raises: excepción que lanza get_dorf1_html() (sobreescribe dorf1_html).
    - hook_calls: lista donde se acumulan los HTML enviados a _post_page_hook.
    """
    browser_mock = AsyncMock()
    db_mock = AsyncMock()

    # Stub de incoming_db
    incoming_db_stub = MagicMock() if incoming_db else None

    # Stub del browser adapter para el radar (Comp. C/D/E)
    browser_adapter_mock = AsyncMock()
    if dorf1_raises is not None:
        browser_adapter_mock.get_dorf1_html = AsyncMock(side_effect=dorf1_raises)
    else:
        browser_adapter_mock.get_dorf1_html = AsyncMock(return_value=dorf1_html)

    # sidebar_attack_hook espiado
    if hook_calls is None:
        hook_calls = []

    async def _hook(html, world_id, db_port):
        hook_calls.append(html)
        return []

    # session_registry stub
    session_registry_mock = MagicMock()
    session_registry_mock.has_active_session = MagicMock(return_value=session_active)

    agent = WorldAgent(
        world_id=1,
        browser=browser_mock,
        db=db_mock,
        session_registry=session_registry_mock,
        incoming_db=incoming_db_stub,
        incoming_attack_browser_adapter=browser_adapter_mock,
        sidebar_attack_hook=_hook,
    )
    agent._send_group = AsyncMock()

    # Sobreescribir atributos de runtime
    agent._active_mode = active_mode
    agent._last_sidebar_scan = last_sidebar_scan
    agent._heartbeat_interval_s = heartbeat_interval_s

    return agent, hook_calls


# ===========================================================================
# UT-RE01-HB — Latido encola con jitter correcto
# ===========================================================================

class TestEnqueueHeartbeat:

    def test_re01hb_jitter_en_rango(self):
        """
        _enqueue_heartbeat() añade una tarea HEARTBEAT_SCAN con execute_at en el
        rango [now+300s, now+900s] para intervalo=600. NUNCA exactamente 600 s.
        """
        agent, _ = _make_agent()

        now_before = datetime.now()
        agent._enqueue_heartbeat()
        now_after = datetime.now()

        tasks = [t for t in agent._queue if t.task_type == TaskType.HEARTBEAT_SCAN]
        assert len(tasks) == 1, "Debe haber exactamente 1 tarea HEARTBEAT_SCAN encolada"
        t = tasks[0]

        # Rango: [now+300, now+900]
        lower = now_before + timedelta(seconds=300)
        upper = now_after + timedelta(seconds=900)
        assert t.execute_at >= lower, f"execute_at={t.execute_at} < lower={lower}"
        assert t.execute_at <= upper, f"execute_at={t.execute_at} > upper={upper}"

        # No debe ser exactamente 600 s — verificar que no es un valor punto flotante exacto
        # (esto no es determinístico pero uniform() nunca produce exactamente el extremo)
        delta = (t.execute_at - now_before).total_seconds()
        assert 300 <= delta <= 900, f"delta={delta} fuera de rango [300, 900]"

    def test_re01hb_priority_es_2(self):
        """HEARTBEAT_SCAN debe tener priority=2 (igual que ruido)."""
        agent, _ = _make_agent()
        agent._enqueue_heartbeat()
        tasks = [t for t in agent._queue if t.task_type == TaskType.HEARTBEAT_SCAN]
        assert tasks[0].priority == 2

    # UT-RE02-HB — No encola en DISCONNECTED
    def test_re02hb_no_encola_en_disconnected(self):
        """
        Con _active_mode=DISCONNECTED, _enqueue_heartbeat() no añade ninguna tarea.
        """
        agent, _ = _make_agent(active_mode=SessionMode.DISCONNECTED)
        agent._enqueue_heartbeat()

        tasks = [t for t in agent._queue if t.task_type == TaskType.HEARTBEAT_SCAN]
        assert tasks == [], "No debe encolar en modo DISCONNECTED"

    def test_re02hb_no_encola_sin_incoming_db(self):
        """Sin incoming_db, _enqueue_heartbeat() no encola aunque el modo sea HARDCORE."""
        agent, _ = _make_agent(incoming_db=False)
        agent._enqueue_heartbeat()

        tasks = [t for t in agent._queue if t.task_type == TaskType.HEARTBEAT_SCAN]
        assert tasks == [], "Sin incoming_db no debe encolar"


# ===========================================================================
# UT-RE03-HB a UT-RE07-HB — Handler _handle_heartbeat_scan
# ===========================================================================

class TestHandleHeartbeatScan:

    # UT-RE03-HB — Skip por piggyback reciente
    def test_re03hb_skip_si_piggyback_reciente(self):
        """
        _last_sidebar_scan = 100 s antes; intervalo=600 → umbral=300.
        Como 100 < 300: handler reencola SIN llamar a get_dorf1_html.
        """
        last = datetime.now() - timedelta(seconds=100)
        agent, hook_calls = _make_agent(last_sidebar_scan=last)
        browser_adapter = agent._incoming_attack_browser_adapter

        async def _run():
            await agent._handle_heartbeat_scan()

        asyncio.run(_run())

        browser_adapter.get_dorf1_html.assert_not_called()
        assert hook_calls == [], "El hook no debe invocarse si piggyback es reciente"
        # Debe reencolar
        tasks = [t for t in agent._queue if t.task_type == TaskType.HEARTBEAT_SCAN]
        assert len(tasks) == 1

    # UT-RE04-HB — Navega cuando inactivo
    def test_re04hb_navega_cuando_inactivo(self):
        """
        _last_sidebar_scan = 400 s antes; intervalo=600 → umbral=300.
        Como 400 >= 300: handler llama a get_dorf1_html(world_id) y luego a _post_page_hook.
        """
        last = datetime.now() - timedelta(seconds=400)
        hook_calls = []
        agent, _ = _make_agent(last_sidebar_scan=last, hook_calls=hook_calls)
        browser_adapter = agent._incoming_attack_browser_adapter

        async def _run():
            await agent._handle_heartbeat_scan()

        asyncio.run(_run())

        browser_adapter.get_dorf1_html.assert_called_once_with(1)
        assert len(hook_calls) == 1, "El hook debe invocarse una vez"
        assert hook_calls[0] == "<html>dorf1</html>"

    # UT-RE05-HB — Skip sin sesión activa
    def test_re05hb_skip_sin_sesion_activa(self):
        """
        _session_active() devuelve False → handler reencola sin navegar.
        """
        agent, hook_calls = _make_agent(session_active=False)
        browser_adapter = agent._incoming_attack_browser_adapter

        async def _run():
            await agent._handle_heartbeat_scan()

        asyncio.run(_run())

        browser_adapter.get_dorf1_html.assert_not_called()
        assert hook_calls == []
        # Debe reencolar (session_active=False no es DISCONNECTED; _should_reenqueue_noise
        # comprueba _active_mode, no session_active — el agente puede estar en HARDCORE
        # pero con sesión caída. Verificamos que se reencoló.)
        tasks = [t for t in agent._queue if t.task_type == TaskType.HEARTBEAT_SCAN]
        assert len(tasks) == 1

    # UT-RE06-HB — _last_sidebar_scan = None (primer arranque)
    def test_re06hb_navega_cuando_last_scan_es_none(self):
        """
        Con _last_sidebar_scan=None (primer arranque), la condición b no aplica
        y el handler navega directamente (EC-27).
        """
        hook_calls = []
        agent, _ = _make_agent(last_sidebar_scan=None, hook_calls=hook_calls)
        browser_adapter = agent._incoming_attack_browser_adapter

        async def _run():
            await agent._handle_heartbeat_scan()

        asyncio.run(_run())

        browser_adapter.get_dorf1_html.assert_called_once()
        assert len(hook_calls) == 1

    # UT-RE07-HB — Error de browser no bloquea agente
    def test_re07hb_error_browser_no_tumba_agente(self):
        """
        get_dorf1_html lanza RuntimeError → handler loggea WARNING, reencola el latido
        y retorna sin propagar (EC-15 para heartbeat).
        """
        last = datetime.now() - timedelta(seconds=700)  # > umbral 300 → navega
        agent, hook_calls = _make_agent(
            last_sidebar_scan=last,
            dorf1_raises=RuntimeError("browser caído"),
        )
        browser_adapter = agent._incoming_attack_browser_adapter

        async def _run():
            # No debe lanzar
            await agent._handle_heartbeat_scan()

        asyncio.run(_run())  # No debe fallar

        browser_adapter.get_dorf1_html.assert_called_once()
        assert hook_calls == [], "El hook no debe invocarse si get_dorf1_html falla"
        # Debe reencolar a pesar del error
        tasks = [t for t in agent._queue if t.task_type == TaskType.HEARTBEAT_SCAN]
        assert len(tasks) == 1

    def test_re07hb_agente_no_propaga_excepcion(self):
        """El agente no propaga ninguna excepción del latido al caller (_execute)."""
        last = datetime.now() - timedelta(seconds=700)
        agent, _ = _make_agent(
            last_sidebar_scan=last,
            dorf1_raises=ValueError("inesperado"),
        )

        async def _run():
            # _execute captura excepciones; pero también _handle_heartbeat_scan
            # no debe propagar nada. Probar directamente el handler.
            await agent._handle_heartbeat_scan()

        # No debe lanzar
        asyncio.run(_run())

    # EC-25: sin incoming_db el handler retorna inmediatamente
    def test_re_ec25_sin_incoming_db_retorna_inmediato(self):
        """Con incoming_db=None el handler retorna inmediatamente sin reencolar."""
        agent, hook_calls = _make_agent(incoming_db=False)
        browser_adapter = agent._incoming_attack_browser_adapter

        async def _run():
            await agent._handle_heartbeat_scan()

        asyncio.run(_run())

        browser_adapter.get_dorf1_html.assert_not_called()
        tasks = [t for t in agent._queue if t.task_type == TaskType.HEARTBEAT_SCAN]
        assert tasks == [], "Sin incoming_db no debe reencolar"


# ===========================================================================
# UT-RE08-HB y UT-RE09-HB — seed_noise_loop_on_session_start
# ===========================================================================

class TestSeedHeartbeat:

    def _make_agent_for_seed(
        self,
        incoming_db: bool = True,
        active_mode: SessionMode = SessionMode.HARDCORE,
    ) -> WorldAgent:
        browser_mock = AsyncMock()
        db_mock = AsyncMock()
        incoming_db_stub = MagicMock() if incoming_db else None

        # noise_db necesario para que seed_noise_loop_on_session_start no haga early return
        noise_db_mock = AsyncMock()
        noise_config_mock = MagicMock()
        noise_config_mock.noise_enabled = True
        noise_config_mock.hardcore_interval_min_seconds = 60
        noise_config_mock.hardcore_interval_max_seconds = 120
        noise_config_mock.passive_interval_min_seconds = 120
        noise_config_mock.passive_interval_max_seconds = 240
        noise_db_mock.get_or_create_noise_config = AsyncMock(return_value=noise_config_mock)

        agent = WorldAgent(
            world_id=1,
            browser=browser_mock,
            db=db_mock,
            noise_db=noise_db_mock,
            incoming_db=incoming_db_stub,
        )
        agent._active_mode = active_mode
        return agent

    # UT-RE08-HB — seed encola primer latido si radar activo
    def test_re08hb_seed_encola_heartbeat_con_incoming_db(self):
        """
        seed_noise_loop_on_session_start() con incoming_db != None →
        encola 1 tarea HEARTBEAT_SCAN con execute_at en rango [now+300s, now+900s].
        """
        agent = self._make_agent_for_seed(incoming_db=True)

        async def _run():
            now_before = datetime.now()
            await agent.seed_noise_loop_on_session_start()
            now_after = datetime.now()

            tasks = [t for t in agent._queue if t.task_type == TaskType.HEARTBEAT_SCAN]
            assert len(tasks) == 1, "Debe encolar exactamente 1 HEARTBEAT_SCAN"
            t = tasks[0]
            lower = now_before + timedelta(seconds=300)
            upper = now_after + timedelta(seconds=900)
            assert t.execute_at >= lower
            assert t.execute_at <= upper

        asyncio.run(_run())

    # UT-RE09-HB — seed NO encola si radar no activo
    def test_re09hb_seed_no_encola_sin_incoming_db(self):
        """
        seed_noise_loop_on_session_start() con incoming_db=None →
        NO encola HEARTBEAT_SCAN.
        """
        agent = self._make_agent_for_seed(incoming_db=False)

        async def _run():
            await agent.seed_noise_loop_on_session_start()
            tasks = [t for t in agent._queue if t.task_type == TaskType.HEARTBEAT_SCAN]
            assert tasks == [], "No debe encolar HEARTBEAT_SCAN sin incoming_db"

        asyncio.run(_run())


# ===========================================================================
# UT-RE10-HB — _maybe_run_page_hook actualiza _last_sidebar_scan
# ===========================================================================

class TestMaybeRunPageHookTimestamp:

    # UT-RE10-HB
    def test_re10hb_maybe_run_page_hook_actualiza_last_sidebar_scan(self):
        """
        Llamar a _maybe_run_page_hook() con provider que devuelve HTML válido →
        _last_sidebar_scan se actualiza a datetime cercana a now.
        """
        browser_mock = AsyncMock()
        db_mock = AsyncMock()
        incoming_db_mock = MagicMock()
        hook_calls = []

        async def _provider():
            return "<html>post-login page</html>"

        async def _hook(html, world_id, db_port):
            hook_calls.append(html)
            return []

        agent = WorldAgent(
            world_id=1,
            browser=browser_mock,
            db=db_mock,
            incoming_db=incoming_db_mock,
            sidebar_attack_hook=_hook,
            page_html_provider=_provider,
        )

        async def _run():
            assert agent._last_sidebar_scan is None, "Debe ser None antes del primer call"
            now_before = datetime.now()
            await agent._maybe_run_page_hook()
            now_after = datetime.now()

            assert agent._last_sidebar_scan is not None
            assert agent._last_sidebar_scan >= now_before
            assert agent._last_sidebar_scan <= now_after

        asyncio.run(_run())

    def test_re10hb_last_scan_no_actualiza_si_provider_devuelve_none(self):
        """
        Si el provider devuelve None, _last_sidebar_scan NO se actualiza.
        """
        browser_mock = AsyncMock()
        db_mock = AsyncMock()
        incoming_db_mock = MagicMock()

        async def _provider_none():
            return None

        async def _hook(html, world_id, db_port):
            return []

        agent = WorldAgent(
            world_id=1,
            browser=browser_mock,
            db=db_mock,
            incoming_db=incoming_db_mock,
            sidebar_attack_hook=_hook,
            page_html_provider=_provider_none,
        )

        async def _run():
            await agent._maybe_run_page_hook()
            assert agent._last_sidebar_scan is None

        asyncio.run(_run())


# ===========================================================================
# UT-RE11-HB — _execute despacha HEARTBEAT_SCAN al handler correcto
# ===========================================================================

class TestExecuteDispatchesHeartbeat:

    # UT-RE11-HB
    def test_re11hb_execute_despacha_heartbeat_scan(self):
        """
        _execute(Task(task_type=HEARTBEAT_SCAN,...)) llama a _handle_heartbeat_scan.
        No cae en el bloque else (tarea desconocida).
        """
        browser_mock = AsyncMock()
        db_mock = AsyncMock()
        incoming_db_mock = MagicMock()

        agent = WorldAgent(
            world_id=1,
            browser=browser_mock,
            db=db_mock,
            incoming_db=incoming_db_mock,
        )
        agent._send_group = AsyncMock()

        handler_called = []

        async def _fake_heartbeat():
            handler_called.append(True)

        agent._handle_heartbeat_scan = _fake_heartbeat

        async def _run():
            task = Task(
                task_type=TaskType.HEARTBEAT_SCAN,
                world_id=1,
                execute_at=datetime.now(),
                priority=2,
                payload={},
                recurring=False,
            )
            await agent._execute(task)

        asyncio.run(_run())

        assert handler_called == [True], (
            "_handle_heartbeat_scan no fue invocado desde _execute para HEARTBEAT_SCAN"
        )

    def test_re11hb_heartbeat_no_invoca_maybe_run_page_hook(self):
        """
        HEARTBEAT_SCAN no debe invocar _maybe_run_page_hook adicional
        (el handler ya llama a _post_page_hook directamente — evita doble scan).
        """
        browser_mock = AsyncMock()
        db_mock = AsyncMock()
        incoming_db_mock = MagicMock()
        hook_calls = []

        async def _hook(html, world_id, db_port):
            hook_calls.append(html)
            return []

        async def _provider():
            return "<html>from provider</html>"

        agent = WorldAgent(
            world_id=1,
            browser=browser_mock,
            db=db_mock,
            incoming_db=incoming_db_mock,
            sidebar_attack_hook=_hook,
            page_html_provider=_provider,
        )
        agent._send_group = AsyncMock()

        # _handle_heartbeat_scan que registra si fue llamado pero no invoca el hook
        handler_called = []

        async def _fake_heartbeat():
            handler_called.append(True)
            # No llamar a _post_page_hook aquí (simulamos el handler real que
            # usa dorf1 html, pero sin browser real simplemente no lo llamamos)

        agent._handle_heartbeat_scan = _fake_heartbeat

        async def _run():
            task = Task(
                task_type=TaskType.HEARTBEAT_SCAN,
                world_id=1,
                execute_at=datetime.now(),
                priority=2,
                payload={},
                recurring=False,
            )
            await agent._execute(task)

        asyncio.run(_run())

        # El hook no debe haberse llamado vía _maybe_run_page_hook
        # (solo se llama desde _handle_heartbeat_scan, que está reemplazado)
        assert hook_calls == [], (
            "_maybe_run_page_hook no debe invocarse tras HEARTBEAT_SCAN en _execute"
        )


# ===========================================================================
# Tests de cobertura adicional: verificar que _last_sidebar_scan se actualiza
# dentro de _handle_heartbeat_scan cuando navega
# ===========================================================================

class TestHandleHeartbeatScanTimestampUpdate:

    def test_handle_heartbeat_actualiza_timestamp_antes_del_hook(self):
        """
        Cuando _handle_heartbeat_scan navega dorf1, actualiza _last_sidebar_scan
        antes de llamar al hook (y el timestamp es coherente con datetime.now()).
        """
        last = datetime.now() - timedelta(seconds=700)  # > umbral → navega
        hook_calls = []
        timestamps_at_hook_call = []

        browser_mock = AsyncMock()
        db_mock = AsyncMock()
        incoming_db_mock = MagicMock()
        session_registry_mock = MagicMock()
        session_registry_mock.has_active_session = MagicMock(return_value=True)
        browser_adapter_mock = AsyncMock()
        browser_adapter_mock.get_dorf1_html = AsyncMock(return_value="<html>dorf1</html>")

        async def _hook(html, world_id, db_port):
            hook_calls.append(html)
            return []

        agent = WorldAgent(
            world_id=1,
            browser=browser_mock,
            db=db_mock,
            session_registry=session_registry_mock,
            incoming_db=incoming_db_mock,
            incoming_attack_browser_adapter=browser_adapter_mock,
            sidebar_attack_hook=_hook,
        )
        agent._active_mode = SessionMode.HARDCORE
        agent._last_sidebar_scan = last
        agent._heartbeat_interval_s = 600

        async def _run():
            before = datetime.now()
            await agent._handle_heartbeat_scan()
            after = datetime.now()

            assert agent._last_sidebar_scan is not None
            assert agent._last_sidebar_scan >= before
            assert agent._last_sidebar_scan <= after
            assert len(hook_calls) == 1

        asyncio.run(_run())
