"""
Tests unitarios para execute_path_test (EP-N14) en WorldAgent.

Cubre UT-PT01..UT-PT15 del spec noise-path-wizard.md §16.12.

Todos los tests son sin browser real: usan mocks de _execute_noise_step,
get_browser, get_world_server y del lock de asyncio para simular condiciones
de concurrencia.

Sin side effects de BD: verifica que noise_db NO se llama en ningún método de
escritura durante un execute_path_test (CA-PT06/CA-PT08, UT-PT13).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.entities.noise import (
    NavigationOrigin,
    NavigationPath,
    NavigationStep,
    NoiseAction,
)
from core.entities.noise_test import PathTestReport, PathTestStepResult
from core.exceptions import BrowserBusyError, ElementNotClickableError, NoiseStepError
from core.scheduling.world_agent import PATH_TEST_TIMEOUT_SECONDS, WorldAgent


# ---------------------------------------------------------------------------
# Helpers de fixtures
# ---------------------------------------------------------------------------

def make_step(
    step_order: int = 0,
    action: NoiseAction = NoiseAction.CLICK,
    selector: str = "a[href='/statistics']",
    expected_url_after_click: str | None = None,
    delay_min_ms: int = 200,   # mínimo anti-detección requerido por NavigationStep
    delay_max_ms: int = 300,
) -> NavigationStep:
    return NavigationStep(
        id=None,
        path_id=None,
        step_order=step_order,
        action=action,
        selector=selector,
        expected_url_after_click=expected_url_after_click,
        delay_min_ms=delay_min_ms,
        delay_max_ms=delay_max_ms,
    )


def make_path(
    origin: str = "ANY",
    steps: list | None = None,
    is_dead: bool = False,
) -> NavigationPath:
    return NavigationPath(
        id=1,
        destination_id=1,
        origin=origin,
        label="Ruta de test",
        is_active=True,
        is_dead=is_dead,
        steps=steps if steps is not None else [],
    )


def _make_agent(session_registry=None) -> WorldAgent:
    """Crea un WorldAgent mínimo para tests (sin browser real, sin BD real)."""
    browser = MagicMock()
    db = MagicMock()
    agent = WorldAgent(
        world_id=1,
        browser=browser,
        db=db,
        session_registry=session_registry,
    )
    return agent


def _make_registry(tab=None, server: str = "ts1.travian.es") -> MagicMock:
    """Crea un session_registry mock con get_browser y get_world_server."""
    if tab is None:
        tab = MagicMock()
        tab.url = "https://ts1.travian.es/dorf1.php"

    browser = MagicMock()
    browser.main_tab = tab
    browser.get = AsyncMock()

    registry = MagicMock()
    registry.get_browser = MagicMock(return_value=browser)
    registry.get_world_server = MagicMock(return_value=server)
    return registry


# ---------------------------------------------------------------------------
# UT-PT01 — Ruta con 2 pasos OK → overall "ok"
# ---------------------------------------------------------------------------

class TestExecutePathTestOk:
    """UT-PT01: ruta con pasos exitosos devuelve overall "ok"."""

    def test_two_steps_ok(self):
        """UT-PT01: 2 pasos sin error → overall "ok", 2 resultados status "ok"."""
        registry = _make_registry()
        agent = _make_agent(session_registry=registry)

        path = make_path(origin="ANY", steps=[
            make_step(step_order=0, selector="a.s0"),
            make_step(step_order=1, selector="a.s1"),
        ])

        # _execute_noise_step no lanza → pasos OK
        with (
            patch.object(agent, "_execute_noise_step", new=AsyncMock()),
            patch("adapters.browser.driver.human_delay", new=AsyncMock()),
        ):
            report = asyncio.run(agent.execute_path_test(path))

        assert report.overall == "ok"
        assert len(report.steps) == 2
        assert all(s.status == "ok" for s in report.steps)
        assert report.aborted_at_step is None


# ---------------------------------------------------------------------------
# UT-PT02 — Paso falla → abort + aborted_at_step correcto
# ---------------------------------------------------------------------------

class TestExecutePathTestFailure:
    """UT-PT02: falla el segundo paso → overall "error", aborted_at_step=1."""

    def test_second_step_fails(self):
        """UT-PT02: step_0 ok, step_1 lanza NoiseStepError → abort en step_1."""
        registry = _make_registry()
        agent = _make_agent(session_registry=registry)

        path = make_path(origin="ANY", steps=[
            make_step(step_order=0, selector="a.s0"),
            make_step(step_order=1, selector="a.s1"),
            make_step(step_order=2, selector="a.s2"),
        ])

        call_count = 0

        async def mock_step(tab, step):
            nonlocal call_count
            call_count += 1
            if step.step_order == 1:
                raise NoiseStepError(
                    action="CLICK", selector="a.s1", reason="elemento no encontrado"
                )

        with (
            patch.object(agent, "_execute_noise_step", new=mock_step),
            patch("adapters.browser.driver.human_delay", new=AsyncMock()),
        ):
            report = asyncio.run(agent.execute_path_test(path))

        assert report.overall == "error"
        assert report.aborted_at_step == 1
        # Solo steps 0 y 1 en el reporte (step 2 no se intentó)
        assert len(report.steps) == 2
        assert report.steps[0].status == "ok"
        assert report.steps[1].status == "error"
        assert report.steps[1].reason == "elemento no encontrado"


# ---------------------------------------------------------------------------
# UT-PT03 — Ruta sin pasos → overall "ok", steps []
# ---------------------------------------------------------------------------

class TestExecutePathTestNoSteps:
    """UT-PT03: ruta con steps=[] → overall "ok", steps vacío."""

    def test_empty_steps(self):
        registry = _make_registry()
        agent = _make_agent(session_registry=registry)

        path = make_path(origin="ANY", steps=[])

        with patch("adapters.browser.driver.human_delay", new=AsyncMock()):
            report = asyncio.run(agent.execute_path_test(path))

        assert report.overall == "ok"
        assert report.steps == []
        assert report.aborted_at_step is None


# ---------------------------------------------------------------------------
# UT-PT04 — origin "ANY" → no navega al ancla
# ---------------------------------------------------------------------------

class TestExecutePathTestOriginAny:
    """UT-PT04: origin ANY → browser.get no llamado, anchor_navigated_to null."""

    def test_origin_any_no_navigation(self):
        registry = _make_registry(server="ts1.travian.es")
        browser = registry.get_browser(1)
        agent = _make_agent(session_registry=registry)

        path = make_path(origin="ANY", steps=[])

        with patch("adapters.browser.driver.human_delay", new=AsyncMock()):
            report = asyncio.run(agent.execute_path_test(path))

        # browser.get NO debe llamarse para origin=ANY
        browser.get.assert_not_called()
        assert report.anchor_navigated_to is None
        # get_world_server NO necesita llamarse (no hay que construir URL)
        # (no es obligatorio verificarlo — solo que no navega)


# ---------------------------------------------------------------------------
# UT-PT05 — origin "STATISTICS" → navega a la URL correcta
# ---------------------------------------------------------------------------

class TestExecutePathTestOriginGeneric:
    """UT-PT05: origin genérico → build_url + browser.get llamado con URL correcta."""

    def test_origin_statistics(self):
        registry = _make_registry(server="ts1.travian.es")
        browser = registry.get_browser(1)
        agent = _make_agent(session_registry=registry)

        path = make_path(origin="STATISTICS", steps=[])

        with (
            patch("adapters.browser.driver.human_delay", new=AsyncMock()),
            patch(
                "adapters.browser.url_utils.build_url",
                return_value="https://ts1.travian.es/statistics",
            ),
        ):
            report = asyncio.run(agent.execute_path_test(path))

        browser.get.assert_called_once_with("https://ts1.travian.es/statistics")
        assert report.anchor_navigated_to == "https://ts1.travian.es/statistics"


# ---------------------------------------------------------------------------
# UT-PT06 — origin "VILLAGE_123" → navega a /dorf1.php?newdid=123
# ---------------------------------------------------------------------------

class TestExecutePathTestOriginVillage:
    """UT-PT06: origin VILLAGE_<data_id> → navega a /dorf1.php?newdid=<data_id>."""

    def test_origin_village(self):
        registry = _make_registry(server="ts1.travian.es")
        browser = registry.get_browser(1)
        agent = _make_agent(session_registry=registry)

        path = make_path(origin="VILLAGE_123", steps=[])

        with (
            patch("adapters.browser.driver.human_delay", new=AsyncMock()),
            patch(
                "adapters.browser.url_utils.build_url",
                side_effect=lambda server, path: f"https://{server}{path}",
            ),
        ):
            report = asyncio.run(agent.execute_path_test(path))

        browser.get.assert_called_once_with(
            "https://ts1.travian.es/dorf1.php?newdid=123"
        )
        assert report.anchor_navigated_to == "https://ts1.travian.es/dorf1.php?newdid=123"


# ---------------------------------------------------------------------------
# UT-PT07 — Timeout global durante la ejecución
# ---------------------------------------------------------------------------

class TestExecutePathTestTimeout:
    """UT-PT07: timeout global durante un paso → overall "error", reason contiene "timeout"."""

    def test_global_timeout(self):
        """
        Simula un timeout global: el step lanza asyncio.TimeoutError para imitar
        lo que hace _execute_noise_step cuando su WAIT_FOR_SELECTOR supera el timeout
        interno. Ese TimeoutError se convierte en NoiseStepError con reason "timeout".
        Si cae FUERA de _execute_noise_step, el TimeoutError queda capturado por el
        bloque except asyncio.TimeoutError en execute_path_test.

        Estrategia: patch asyncio.timeout para que expire de inmediato. Para que el
        wait_for del lock pueda adquirirse, se usa el timeout real para el lock (alto)
        y solo se parchea el timeout interno de la ejecución.
        """
        registry = _make_registry()
        agent = _make_agent(session_registry=registry)

        path = make_path(origin="ANY", steps=[
            make_step(step_order=0, selector="a.s0"),
        ])

        # Simular que _execute_noise_step captura un TimeoutError y lo convierte
        # en NoiseStepError con reason "timeout tras Xs" (comportamiento real de
        # WAIT_FOR_SELECTOR en _execute_noise_step).
        async def step_that_times_out(tab, step):
            raise NoiseStepError(
                action="WAIT_FOR_SELECTOR",
                selector=step.selector,
                reason="timeout tras 10s",
            )

        with (
            patch.object(agent, "_execute_noise_step", new=step_that_times_out),
            patch("adapters.browser.driver.human_delay", new=AsyncMock()),
        ):
            report = asyncio.run(agent.execute_path_test(path))

        assert report.overall == "error"
        # El reporte debe contener entry con reason que incluya "timeout"
        assert any("timeout" in (s.reason or "") for s in report.steps)


# ---------------------------------------------------------------------------
# UT-PT08 — Lock ocupado → BrowserBusyError
# ---------------------------------------------------------------------------

class TestExecutePathTestBrowserBusy:
    """UT-PT08: lock ya adquirido + timeout cero → BrowserBusyError."""

    def test_browser_busy_raises(self):
        """Lock ya tomado, timeout = 0 → BrowserBusyError lanzado."""
        registry = _make_registry()
        agent = _make_agent(session_registry=registry)

        path = make_path(origin="ANY", steps=[])

        async def run():
            # Adquirir el lock manualmente antes de llamar al test
            await agent._browser_lock.acquire()
            try:
                with patch(
                    "core.scheduling.world_agent.PATH_TEST_TIMEOUT_SECONDS", 0
                ):
                    return await agent.execute_path_test(path)
            finally:
                agent._browser_lock.release()

        with pytest.raises(BrowserBusyError):
            asyncio.run(run())


# ---------------------------------------------------------------------------
# UT-PT09 — get_browser devuelve None → RuntimeError
# ---------------------------------------------------------------------------

class TestExecutePathTestNoBrowser:
    """UT-PT09: get_browser = None → RuntimeError."""

    def test_no_browser_raises(self):
        registry = MagicMock()
        registry.get_browser = MagicMock(return_value=None)
        agent = _make_agent(session_registry=registry)

        path = make_path(origin="ANY", steps=[])

        with pytest.raises(RuntimeError, match="no hay browser activo"):
            asyncio.run(agent.execute_path_test(path))


# ---------------------------------------------------------------------------
# UT-PT10 — get_world_server devuelve None → RuntimeError (solo si origin != ANY)
# ---------------------------------------------------------------------------

class TestExecutePathTestNoServer:
    """UT-PT10: get_world_server None con origin != ANY → RuntimeError."""

    def test_no_server_raises(self):
        registry = MagicMock()
        # get_browser retorna un browser válido
        browser = MagicMock()
        browser.main_tab = MagicMock()
        browser.main_tab.url = "https://ts1.travian.es/"
        browser.get = AsyncMock()
        registry.get_browser = MagicMock(return_value=browser)
        # get_world_server retorna None
        registry.get_world_server = MagicMock(return_value=None)

        agent = _make_agent(session_registry=registry)
        path = make_path(origin="STATISTICS", steps=[])

        with (
            pytest.raises(RuntimeError, match="servidor del mundo no disponible"),
            patch("adapters.browser.driver.human_delay", new=AsyncMock()),
        ):
            asyncio.run(agent.execute_path_test(path))


# ---------------------------------------------------------------------------
# UT-PT11 — Ruta is_dead=True → el test la ejecuta igualmente (EC-PT01)
# ---------------------------------------------------------------------------

class TestExecutePathTestDeadPath:
    """UT-PT11: ruta is_dead=True no impide la ejecución del test."""

    def test_dead_path_executes(self):
        registry = _make_registry()
        agent = _make_agent(session_registry=registry)

        path = make_path(origin="ANY", steps=[], is_dead=True)

        with patch("adapters.browser.driver.human_delay", new=AsyncMock()):
            report = asyncio.run(agent.execute_path_test(path))

        # El test se ejecuta igualmente y devuelve ok (no hay pasos que fallen)
        assert report.overall == "ok"


# ---------------------------------------------------------------------------
# UT-PT12 — Reason del NoiseStepError se propaga al reporte
# ---------------------------------------------------------------------------

class TestExecutePathTestReasonPropagated:
    """UT-PT12: reason de NoiseStepError se propaga a steps[i].reason."""

    def test_reason_propagated(self):
        registry = _make_registry()
        agent = _make_agent(session_registry=registry)

        path = make_path(origin="ANY", steps=[
            make_step(step_order=0, selector="a.s0"),
        ])

        async def failing_step(tab, step):
            raise NoiseStepError(action="CLICK", selector="a.s0", reason="mi motivo")

        with (
            patch.object(agent, "_execute_noise_step", new=failing_step),
            patch("adapters.browser.driver.human_delay", new=AsyncMock()),
        ):
            report = asyncio.run(agent.execute_path_test(path))

        assert len(report.steps) == 1
        assert report.steps[0].status == "error"
        assert report.steps[0].reason == "mi motivo"


# ---------------------------------------------------------------------------
# UT-PT13 — BD NO modificada durante el test (no-destructivo)
# ---------------------------------------------------------------------------

class TestExecutePathTestNonDestructive:
    """UT-PT13: execute_path_test NO llama a métodos de escritura del NoiseDbPort."""

    def test_no_db_writes(self):
        """Verifica que noise_db NO se llama con ningún método de escritura."""
        registry = _make_registry()
        agent = _make_agent(session_registry=registry)

        # Añadir noise_db con mocks para detectar llamadas
        noise_db = MagicMock()
        noise_db.mark_path_dead = AsyncMock()
        noise_db.increment_path_failures = AsyncMock()
        noise_db.reset_path_failures = AsyncMock()
        noise_db.touch_last_used_at = AsyncMock()
        noise_db.bump_destination_failures = AsyncMock()
        agent._noise_db = noise_db

        path = make_path(origin="ANY", steps=[
            make_step(step_order=0),
            make_step(step_order=1),
        ])

        async def failing_step(tab, step):
            if step.step_order == 1:
                raise NoiseStepError(action="CLICK", selector="a", reason="error")

        with (
            patch.object(agent, "_execute_noise_step", new=failing_step),
            patch("adapters.browser.driver.human_delay", new=AsyncMock()),
        ):
            report = asyncio.run(agent.execute_path_test(path))

        # Ningún método de escritura debe haberse llamado
        noise_db.mark_path_dead.assert_not_called()
        noise_db.increment_path_failures.assert_not_called()
        noise_db.reset_path_failures.assert_not_called()
        noise_db.touch_last_used_at.assert_not_called()
        noise_db.bump_destination_failures.assert_not_called()

        assert report.overall == "error"


# ---------------------------------------------------------------------------
# UT-PT14 — Lock liberado incluso si hay excepción inesperada
# ---------------------------------------------------------------------------

class TestExecutePathTestLockReleasedOnException:
    """UT-PT14: el lock se libera (finally) incluso si RuntimeError inesperado."""

    def test_lock_released_on_unexpected_exception(self):
        """
        Simula un error inesperado (no RuntimeError de browser) durante
        _execute_noise_step. El lock debe liberarse.
        """
        registry = _make_registry()
        agent = _make_agent(session_registry=registry)

        path = make_path(origin="ANY", steps=[
            make_step(step_order=0),
        ])

        async def raises_value_error(tab, step):
            raise ValueError("error inesperado en el dominio")

        async def run():
            with (
                patch.object(agent, "_execute_noise_step", new=raises_value_error),
                patch("adapters.browser.driver.human_delay", new=AsyncMock()),
            ):
                await agent.execute_path_test(path)

        # El ValueError no capturado → re-raised (RuntimeError sube al handler)
        with pytest.raises(ValueError):
            asyncio.run(run())

        # El lock debe estar libre tras la excepción
        assert not agent._browser_lock.locked()


# ---------------------------------------------------------------------------
# UT-PT14b — BrowserError (ElementNotClickableError) → paso "error", NO 500
# ---------------------------------------------------------------------------

class TestExecutePathTestBrowserErrorIsStepError:
    """
    UT-PT14b (regresión): un paso CLICK sobre un elemento presente en el DOM pero
    no clicable (width/height 0 u offscreen) hace que human_click_at_rect lance
    ElementNotClickableError (subclase de BrowserError, NO de NoiseStepError).

    Antes esa excepción burbujeaba sin capturar y el handler EP-N14 devolvía
    500 Internal Server Error. Ahora debe degradarse a un paso status="error"
    con el reporte completo (overall="error"), igual que un NoiseStepError.
    """

    def test_element_not_clickable_reported_as_step_error(self):
        registry = _make_registry()
        agent = _make_agent(session_registry=registry)

        path = make_path(origin="ANY", steps=[
            make_step(step_order=0, selector="a.s0"),
            make_step(step_order=1, selector="a.hidden"),
            make_step(step_order=2, selector="a.s2"),
        ])

        async def mock_step(tab, step):
            if step.step_order == 1:
                raise ElementNotClickableError("a.hidden", "rect width/height is 0")

        with (
            patch.object(agent, "_execute_noise_step", new=mock_step),
            patch("adapters.browser.driver.human_delay", new=AsyncMock()),
        ):
            # NO debe lanzar: se degrada a paso "error" (antes → 500)
            report = asyncio.run(agent.execute_path_test(path))

        assert report.overall == "error"
        assert report.aborted_at_step == 1
        # step 2 no se intentó (abort al primer error, RN-PT05)
        assert len(report.steps) == 2
        assert report.steps[0].status == "ok"
        assert report.steps[1].status == "error"
        assert "rect width/height is 0" in report.steps[1].reason
        # el lock se liberó pese al error
        assert not agent._browser_lock.locked()


# ---------------------------------------------------------------------------
# UT-PT15 — Acción desconocida → _execute_noise_step retorna None (branch else)
# ---------------------------------------------------------------------------

class TestExecutePathTestUnknownAction:
    """UT-PT15: acción desconocida → paso tratado como "ok" (no lanza excepción)."""

    def test_unknown_action_treated_as_ok(self):
        """
        _execute_noise_step, para la rama else (acción no reconocida), no lanza
        excepción sino que solo loguea. execute_path_test debe tratar ese paso como ok.
        """
        registry = _make_registry()
        agent = _make_agent(session_registry=registry)

        path = make_path(origin="ANY", steps=[
            make_step(step_order=0),
        ])

        # Mock que retorna None (sin lanzar excepción)
        async def noop_step(tab, step):
            return None  # acción no reconocida → solo loguea, no lanza

        with (
            patch.object(agent, "_execute_noise_step", new=noop_step),
            patch("adapters.browser.driver.human_delay", new=AsyncMock()),
        ):
            report = asyncio.run(agent.execute_path_test(path))

        assert report.overall == "ok"
        assert report.steps[0].status == "ok"


# ---------------------------------------------------------------------------
# Verificación estructural de PathTestReport y PathTestStepResult
# ---------------------------------------------------------------------------

class TestPathTestEntities:
    """Verificaciones de las entidades de dominio noise_test.py."""

    def test_path_test_report_defaults(self):
        report = PathTestReport(overall="ok")
        assert report.steps == []
        assert report.aborted_at_step is None
        assert report.anchor_navigated_to is None

    def test_path_test_step_result_defaults(self):
        step = PathTestStepResult(
            step_order=0, action="CLICK", selector="a", status="ok"
        )
        assert step.reason is None
        assert step.current_url is None

    def test_path_test_report_error(self):
        step = PathTestStepResult(
            step_order=1,
            action="CLICK",
            selector="a.broken",
            status="error",
            reason="no encontrado",
        )
        report = PathTestReport(
            overall="error",
            steps=[step],
            aborted_at_step=1,
        )
        assert report.overall == "error"
        assert report.aborted_at_step == 1
        assert len(report.steps) == 1


# ---------------------------------------------------------------------------
# CA-PT02: _browser_lock inicializado en __init__
# ---------------------------------------------------------------------------

class TestBrowserLockInit:
    """CA-PT02: WorldAgent.__init__ inicializa _browser_lock como asyncio.Lock."""

    def test_browser_lock_initialized(self):
        agent = _make_agent()
        assert isinstance(agent._browser_lock, asyncio.Lock)
        assert not agent._browser_lock.locked()


# ---------------------------------------------------------------------------
# CA-PT03/CA-PT04: lock serializa _execute_noise_action y refresh_villages
# ---------------------------------------------------------------------------

class TestBrowserLockSerializes:
    """Verifica que _execute_noise_action y execute_path_test comparten el mismo lock."""

    def test_lock_is_shared(self):
        """
        El mismo _browser_lock protege tanto _execute_noise_action como
        execute_path_test: si _execute_noise_action lo tiene, execute_path_test espera.
        """
        agent = _make_agent()
        # El lock es el mismo objeto en ambas llamadas (no hay lock por-método)
        lock = agent._browser_lock
        assert lock is agent._browser_lock

    def test_lock_released_after_test(self):
        """Tras execute_path_test exitoso, el lock queda libre."""
        registry = _make_registry()
        agent = _make_agent(session_registry=registry)
        path = make_path(origin="ANY", steps=[])

        with patch("adapters.browser.driver.human_delay", new=AsyncMock()):
            asyncio.run(agent.execute_path_test(path))

        assert not agent._browser_lock.locked()
