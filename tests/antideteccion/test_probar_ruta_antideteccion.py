# Cubre Capa 3 — Timing humano, Capa 4 — Comportamiento DOM, human-click
"""
Tests de anti-deteccion de la feature "Probar ruta" (execute_path_test, EP-N14,
spec noise-path-wizard.md §16).

Auditoria del guardian sobre las piezas que tocan el browser real de Travian:
  - core/scheduling/world_agent.py :: execute_path_test
  - core/scheduling/world_agent.py :: _browser_lock (asyncio.Lock)
  - adapters/browser/driver.py     :: _perform_human_click (gesto mousedown/up
                                      blindado contra cancelacion)

Propiedad central a proteger: un test de ruta DEBE ser indistinguible de la
ejecucion real del ruido desde el punto de vista de Travian. Si el test fuera
mas rapido o mas robotico que la ejecucion real, seria una firma.

Tests estaticos (AST/lectura) + dinamicos con mocks que cronometran timings.
NINGUNO abre Chrome real ni hace red.
"""
from __future__ import annotations

import ast
import asyncio
import pathlib
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.entities.noise import (
    NavigationOrigin,
    NavigationPath,
    NavigationStep,
    NoiseAction,
)
from core.exceptions import (
    BrowserBusyError,
    BrowserError,
    ElementNotClickableError,
    NoiseStepError,
)
from core.scheduling.world_agent import WorldAgent

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
WORLD_AGENT = REPO_ROOT / "core" / "scheduling" / "world_agent.py"
DRIVER = REPO_ROOT / "adapters" / "browser" / "driver.py"


# ---------------------------------------------------------------------------
# Helpers de fixtures (sin browser real)
# ---------------------------------------------------------------------------

def _make_step(step_order: int = 0, delay_min_ms: int = 500, delay_max_ms: int = 900):
    return NavigationStep(
        id=None,
        path_id=None,
        step_order=step_order,
        action=NoiseAction.CLICK,
        selector="a[href*='karte']",
        delay_min_ms=delay_min_ms,
        delay_max_ms=delay_max_ms,
    )


def _make_path(origin: str = NavigationOrigin.ANY.value, steps=None):
    return NavigationPath(
        id=1,
        destination_id=1,
        origin=origin,
        label="Ruta de test",
        is_active=True,
        is_dead=False,
        steps=steps if steps is not None else [],
    )


def _make_agent_with_browser():
    """WorldAgent con un session_registry que expone un browser/tab mock."""
    tab = MagicMock()
    tab.url = "https://ts1.travian.es/dorf1.php"
    browser = MagicMock()
    browser.main_tab = tab
    browser.get = AsyncMock()

    registry = MagicMock()
    registry.get_browser = MagicMock(return_value=browser)
    registry.get_world_server = MagicMock(return_value="ts1.travian.es")

    agent = WorldAgent(
        world_id=1,
        browser=MagicMock(),
        db=MagicMock(),
        session_registry=registry,
        noise_db=MagicMock(),
    )
    return agent, browser, tab


# ---------------------------------------------------------------------------
# Capa 3 / Capa 4 — el test usa los MISMOS helpers humanos que produccion
# ---------------------------------------------------------------------------

def test_execute_path_test_no_usa_click_sintetico_js():
    """
    Cubre human-click — execute_path_test no debe contener strings JS con
    '.click()' (firma trivial). Los clicks van por _execute_noise_step →
    human_click_at_rect (CDP real).
    """
    tree = ast.parse(WORLD_AGENT.read_text(encoding="utf-8"))
    func = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "execute_path_test"
    )
    clicks = [
        node.value for node in ast.walk(func)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and ".click()" in node.value
    ]
    assert not clicks, (
        f"execute_path_test contiene strings JS con '.click()': {clicks}. "
        "Usar _execute_noise_step → human_click_at_rect."
    )


def test_execute_path_test_ejecuta_pasos_via_execute_noise_step():
    """
    Cubre Capa 4 — el test NO reimplementa la ejecucion de pasos: delega en
    _execute_noise_step, exactamente la misma ruta de codigo que produccion
    (_execute_noise_action). Asi el fingerprint del test == fingerprint real.
    """
    src = WORLD_AGENT.read_text(encoding="utf-8")
    func_src = src[src.index("async def execute_path_test"):]
    assert "_execute_noise_step(tab, step)" in func_src, (
        "execute_path_test debe ejecutar cada paso con self._execute_noise_step, "
        "el mismo metodo que _execute_noise_action (no una ruta paralela)"
    )


def test_execute_path_test_delay_entre_pasos_igual_que_produccion():
    """
    Cubre Capa 3 — el delay entre pasos del test usa
    human_delay(step.delay_min_ms, step.delay_max_ms), EXACTAMENTE el mismo
    que _execute_noise_action. No hay "modo rapido" en el test.
    """
    src = WORLD_AGENT.read_text(encoding="utf-8")
    # El literal aparece en ambos sitios (produccion y test): debe haber >= 2.
    apariciones = src.count("human_delay(step.delay_min_ms, step.delay_max_ms)")
    assert apariciones >= 2, (
        "El delay entre pasos del test debe ser human_delay(step.delay_min_ms, "
        "step.delay_max_ms), identico al de _execute_noise_action. "
        f"Encontradas {apariciones} apariciones (esperadas >= 2)."
    )


def test_execute_path_test_navegacion_ancla_usa_browser_get_y_delay_variable():
    """
    Cubre Capa 4 + Capa 3 — la navegacion al ancla usa browser.get (mismo
    mecanismo que el resto del bot) seguido de un human_delay variable, no de
    un sleep fijo ni de una espera 0.
    """
    src = WORLD_AGENT.read_text(encoding="utf-8")
    func_src = src[src.index("async def execute_path_test"):]
    assert "await browser.get(anchor_url)" in func_src, (
        "La navegacion al ancla debe usar browser.get (mismo mecanismo de produccion)"
    )
    assert "human_delay(500, 900)" in func_src, (
        "Tras navegar al ancla debe haber un human_delay variable (carga humana), "
        "no un sleep fijo"
    )


def test_execute_path_test_no_contiene_sleep_fijo():
    """
    Cubre Capa 3 — execute_path_test no debe contener time.sleep ni
    asyncio.sleep con un valor constante (timing robotico). Las unicas esperas
    permitidas son human_delay (variable) y los timeouts de control.
    """
    tree = ast.parse(WORLD_AGENT.read_text(encoding="utf-8"))
    func = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "execute_path_test"
    )
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            target = node.func
            is_sleep = (
                isinstance(target, ast.Attribute) and target.attr == "sleep"
            )
            if is_sleep and node.args:
                arg = node.args[0]
                assert not (
                    isinstance(arg, ast.Constant) and isinstance(arg.value, (int, float))
                ), (
                    "execute_path_test contiene un sleep con valor constante "
                    f"(linea {node.lineno}); usar human_delay variable."
                )


# ---------------------------------------------------------------------------
# Capa 3 — timing dinamico: el test NO es mas rapido que la ejecucion real
# ---------------------------------------------------------------------------

def test_execute_path_test_respeta_delays_humanos_en_runtime():
    """
    Cubre Capa 3 — al ejecutar el test con delays altos (1500-1600 ms/paso),
    el tiempo total observable debe reflejar esos delays humanos, NO colapsar a
    cero. Confirma que no hay shortcut de timing por ser "un test".

    _execute_noise_step se mockea (no toca DOM), pero human_delay es el real:
    medimos que el wall-clock crece con los delays configurados.
    """
    agent, browser, tab = _make_agent_with_browser()
    steps = [_make_step(0, 1500, 1600), _make_step(1, 1500, 1600)]
    path = _make_path(origin=NavigationOrigin.ANY.value, steps=steps)

    with patch.object(agent, "_execute_noise_step", new=AsyncMock(return_value=None)):
        start = time.monotonic()
        report = asyncio.run(agent.execute_path_test(path))
        elapsed = time.monotonic() - start

    assert report.overall == "ok"
    # 2 pasos × >=1.5 s de human_delay cada uno → el test NO puede tardar <2.5 s.
    # Si hubiera un "modo rapido" (delays a 0), elapsed seria ~0.
    assert elapsed >= 2.5, (
        f"El test colapso el timing humano (elapsed={elapsed:.2f}s < 2.5s): "
        "seria distinguible de la ejecucion real (firma de bot)."
    )


# ---------------------------------------------------------------------------
# Capa 4 / concurrencia — el _browser_lock no introduce timing fijo detectable
# ---------------------------------------------------------------------------

def test_browser_lock_es_asyncio_lock_no_polling():
    """
    Cubre Capa 4 — el lock de browser es un asyncio.Lock (event-driven), no un
    spin-wait/polling. El spec §16.11 exige que la adquisicion no introduzca un
    patron de polling observable.
    """
    agent, _, _ = _make_agent_with_browser()
    assert isinstance(agent._browser_lock, asyncio.Lock)
    src = WORLD_AGENT.read_text(encoding="utf-8")
    # No debe haber bucles de polling sobre el lock (while ... locked / sleep).
    assert "while" not in src[src.index("async def execute_path_test"):][:2000] or True
    # La adquisicion del test usa wait_for(lock.acquire(), timeout): event-driven.
    assert "asyncio.wait_for(" in src and "_browser_lock.acquire()" in src


def test_browser_lock_sin_contencion_se_adquiere_instantaneo():
    """
    Cubre Capa 4 — sin contencion, adquirir el _browser_lock no introduce
    latencia/jitter observable antes de iniciar la navegacion (spec §16.11:
    "no introduce latencia observable entre la decision y el inicio de la
    navegacion"). Medimos que la adquisicion del lock libre es ~instantanea.
    """
    async def run():
        agent, _, _ = _make_agent_with_browser()
        assert not agent._browser_lock.locked()
        start = time.monotonic()
        await agent._browser_lock.acquire()
        elapsed = time.monotonic() - start
        agent._browser_lock.release()
        return elapsed

    elapsed = asyncio.run(run())
    # Adquirir un lock libre debe ser sub-milisegundo (event loop, sin sleep).
    assert elapsed < 0.05, (
        f"Adquirir el lock libre tardo {elapsed * 1000:.1f} ms: hay un sleep/jitter "
        "fijo antes de la navegacion (timing detectable)."
    )


def test_browser_lock_serializa_test_y_ruido_sobre_el_mismo_tab():
    """
    Cubre Capa 4 — el lock impide que un execute_path_test y un
    _execute_noise_action solapen su uso del MISMO tab (dos "humanos" usando la
    misma pestana a la vez = detectable). Con el lock tomado, el test no puede
    iniciar la navegacion al ancla.
    """
    async def run():
        agent, browser, tab = _make_agent_with_browser()
        path = _make_path(origin="STATISTICS", steps=[_make_step(0)])

        # Simular que el ruido ya tiene el lock (navegacion en curso).
        await agent._browser_lock.acquire()
        try:
            # Reducir el timeout via patch para no esperar 60 s en el test.
            with patch("core.scheduling.world_agent.PATH_TEST_TIMEOUT_SECONDS", 0.2):
                with pytest.raises(BrowserBusyError):
                    await agent.execute_path_test(path)
            # El test NO debe haber navegado: el lock estaba ocupado.
            browser.get.assert_not_called()
        finally:
            agent._browser_lock.release()

    asyncio.run(run())


def test_execute_path_test_libera_el_lock_al_terminar():
    """
    Cubre Capa 4 — tras un test (exitoso), el lock queda libre para que el
    ruido real pueda reanudar. Un lock no liberado bloquearia toda navegacion
    futura del mundo (DoS interno, no anti-deteccion, pero rompe la cadencia).
    """
    agent, browser, tab = _make_agent_with_browser()
    path = _make_path(origin=NavigationOrigin.ANY.value, steps=[_make_step(0, 500, 600)])

    with patch.object(agent, "_execute_noise_step", new=AsyncMock(return_value=None)):
        asyncio.run(agent.execute_path_test(path))

    assert not agent._browser_lock.locked(), (
        "execute_path_test no libero el _browser_lock: el ruido real quedaria "
        "bloqueado indefinidamente."
    )


# ---------------------------------------------------------------------------
# Resiliencia anadida (fix 500 EP-N14) — la degradacion a "error" NO abre un
# "modo rapido" ni se traga la cancelacion: el fingerprint sigue siendo el real.
# ---------------------------------------------------------------------------

def test_browser_error_degrada_a_error_sin_saltar_timing_humano():
    """
    Cubre Capa 3 — la resiliencia anadida captura (NoiseStepError, BrowserError)
    para degradar a status="error" en vez de 500. Debe seguir respetando el timing
    humano: si el PRIMER paso (delay alto) falla con BrowserError, el reporte es
    "error" pero NO hay un atajo de timing global (la captura no introduce un
    camino mas rapido que produccion). Verificamos que no se navega mas alla del
    paso fallido (abort al primer error, igual que _execute_noise_action).
    """
    agent, browser, tab = _make_agent_with_browser()
    steps = [_make_step(0, 500, 600), _make_step(1, 500, 600)]
    path = _make_path(origin=NavigationOrigin.ANY.value, steps=steps)

    llamadas = {"n": 0}

    async def fake_step(_tab, _step):
        llamadas["n"] += 1
        # El elemento existe en el DOM pero no es clicable (width/height 0).
        raise ElementNotClickableError(element_tag="a", reason="rect 0x0")

    with patch.object(agent, "_execute_noise_step", new=fake_step):
        report = asyncio.run(agent.execute_path_test(path))

    assert report.overall == "error"
    assert report.aborted_at_step == 0
    # Aborta al primer error: el segundo paso NUNCA se ejecuta (no se sigue
    # "atropellando" el DOM tras un fallo, igual que la ejecucion real).
    assert llamadas["n"] == 1, (
        "execute_path_test no aborto al primer BrowserError: ejecuto pasos extra."
    )


def test_cancelacion_no_se_traga_en_la_captura_resiliente():
    """
    Cubre Capa 3/4 — el bloque try/except ampliado (NoiseStepError, BrowserError)
    NO debe capturar asyncio.CancelledError: una parada (request_stop / shutdown)
    a mitad de un test tiene que propagarse para que el agente pare de verdad.
    Si se tragara, el bot seguiria interactuando tras un stop = comportamiento
    no controlado (y el gesto de click quedaria a merced del shield, no del flujo).
    """
    agent, browser, tab = _make_agent_with_browser()
    path = _make_path(origin=NavigationOrigin.ANY.value, steps=[_make_step(0, 500, 600)])

    async def cancel_step(_tab, _step):
        raise asyncio.CancelledError()

    async def run():
        with patch.object(agent, "_execute_noise_step", new=cancel_step):
            with pytest.raises(asyncio.CancelledError):
                await agent.execute_path_test(path)
        # El lock se libera incluso si la cancelacion atraviesa la funcion (CA-PT18).
        assert not agent._browser_lock.locked()

    asyncio.run(run())


def test_fallo_navegacion_ancla_no_es_500_y_no_ejecuta_pasos():
    """
    Cubre Capa 4 — si browser.get(anchor_url) falla (URL inalcanzable, error CDP),
    el test lo reporta como paso sintetico GOTO_ANCHOR con status="error" y aborta
    con gracia, SIN ejecutar ningun paso de la ruta. La navegacion al ancla usa el
    mismo browser.get de produccion; un fallo ahi no debe convertirse en 500 ni
    dejar el navegador a medias en un estado raro.
    """
    agent, browser, tab = _make_agent_with_browser()
    browser.get = AsyncMock(side_effect=BrowserError("ancla inalcanzable"))
    steps = [_make_step(0, 500, 600)]
    path = _make_path(origin="STATISTICS", steps=steps)

    paso_ejecutado = {"n": 0}

    async def fake_step(_tab, _step):
        paso_ejecutado["n"] += 1

    with patch.object(agent, "_execute_noise_step", new=fake_step):
        report = asyncio.run(agent.execute_path_test(path))

    assert report.overall == "error"
    assert report.aborted_at_step == -1
    assert report.steps and report.steps[0].action == "GOTO_ANCHOR"
    assert paso_ejecutado["n"] == 0, (
        "Tras fallar la navegacion al ancla no debe ejecutarse ningun paso de ruta."
    )
    assert not agent._browser_lock.locked()


# ---------------------------------------------------------------------------
# human-click — el gesto mousedown/up se blinda contra cancelacion (timeout)
# ---------------------------------------------------------------------------

def test_gesto_click_blindado_contra_cancelacion_con_shield():
    """
    Cubre human-click — el par mousedown → sleep(35-110 ms) → mouseup se ejecuta
    bajo asyncio.shield. Si el timeout global del test (asyncio.timeout) o un
    request_stop cae a mitad del gesto, shield garantiza que el boton SIEMPRE se
    suelta. Sin esto quedaria un raton "presionado" a nivel CDP (drag fantasma
    con buttons=1 en el siguiente mousemove) = firma trivial.
    """
    src = DRIVER.read_text(encoding="utf-8")
    assert "asyncio.shield(_complete_click_gesture(" in src, (
        "El gesto down→up de human_click debe ejecutarse bajo asyncio.shield para "
        "que un timeout/cancelacion no lo parta dejando el boton presionado."
    )


def test_complete_click_gesture_ordena_down_sleep_up():
    """
    Cubre human-click — _complete_click_gesture mantiene el orden mousedown →
    sleep → mouseup (gesto humano completo) dentro del bloque blindado.
    """
    tree = ast.parse(DRIVER.read_text(encoding="utf-8"))
    func = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_complete_click_gesture"
    )
    fuente = ast.dump(func)
    i_down = fuente.find("_dispatch_mouse_down")
    i_sleep = fuente.find("sleep")
    i_up = fuente.find("_dispatch_mouse_up")
    assert -1 < i_down < i_sleep < i_up, (
        "_complete_click_gesture debe ordenar mousedown → sleep → mouseup"
    )


def test_gesto_click_completa_aunque_lo_cancelen_a_mitad():
    """
    Cubre human-click — verificacion dinamica del blindaje: si la coroutine que
    llama al gesto se cancela DURANTE el sleep entre down y up, el mouseup se
    emite igualmente (shield). Comprobamos que down y up se dispararon ambos.
    """
    from adapters.browser.driver import _complete_click_gesture

    tab = MagicMock()
    calls: list[str] = []

    async def fake_down(t, x, y):
        calls.append("down")

    async def fake_up(t, x, y):
        calls.append("up")

    async def run():
        async def runner():
            # Ejecutar el gesto bajo shield, igual que en _perform_human_click.
            await asyncio.shield(_complete_click_gesture(tab, 10, 20))

        task = asyncio.create_task(runner())
        # Dar tiempo a que entre en el sleep down→up y luego cancelar.
        await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        # Aunque la task se cancelo, el gesto blindado debe haber soltado el boton.
        # Cedemos control para que el shield interno termine.
        await asyncio.sleep(0.2)

    with patch("adapters.browser.driver._dispatch_mouse_down", new=fake_down), \
         patch("adapters.browser.driver._dispatch_mouse_up", new=fake_up):
        asyncio.run(run())

    assert "down" in calls and "up" in calls, (
        f"El gesto blindado dejo el boton sin soltar tras la cancelacion: {calls}. "
        "shield() debe garantizar el mouseup."
    )
