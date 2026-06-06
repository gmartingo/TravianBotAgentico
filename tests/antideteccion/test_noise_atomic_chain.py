"""
Tests anti-detección y de motor del flujo de rutas atómicas componibles (v2).

Cubre los criterios de aceptación del spec:
  CA-V2-09  — Motor ejecuta cadena con human_click + delays humanizados; CERO browser.get
  CA-V2-11  — Modo test recorre cadena con human_click (no browser.get)
  CA-V2-12  — url_pattern / expected_url_after_click solo VERIFICAN, nunca navegan
  CA-V2-16  — (GAP-1) INVARIANTE-NAV-01: grep del bloque v2 en world_agent.py → cero browser.get
  CA-V2-17  — (GAP-2) ColdStartAbortError cuando el browser no está en Travian
  CA-V2-18  — (GAP-3) Delay inter-step nunca < 200 ms aunque dato sea 50 ms

Y los tests del spec §v2.12:
  TI-V2-14  — Motor aplica max(200, step.delay_min_ms) con delay_min_ms=50
  TI-V2-15  — Motor llama a _execute_noise_action con tab en about:blank → ColdStartAbortError

Tests ESTÁTICOS (grep/AST sobre el código fuente) + DINÁMICOS con mocks.
NINGUNO abre Chrome real ni hace red.

Spec: route-templates-developer-portal.md §v2.6, §v2-REGLA-NAV, §v2-ARRANQUE-FRIO.
"""
from __future__ import annotations

import ast
import asyncio
import pathlib
import re
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import dataclasses

from core.entities.noise import (
    NavigationOrigin,
    NavigationPath,
    NavigationStep,
    NoiseAction,
    NoiseCategory,
    NoiseConfig,
    NoiseDestination,
)
from core.exceptions import (
    BrowserBusyError,
    ColdStartAbortError,
    NoiseStepError,
)
from core.scheduling.world_agent import (
    WorldAgent,
    _check_cold_start,
    execute_path_test_standalone,
)
from core.use_cases.route_template_service import ResolvedStep


def _make_nav_step_corrupted(delay_min_ms: int = 50, delay_max_ms: int = 300) -> NavigationStep:
    """
    Construye un NavigationStep con delay_min_ms < 200, simulando un dato
    corrupto en BD (escrito antes de que existiera la validación de escritura).
    Bypasea __post_init__ usando object.__setattr__ para simular datos corruptos.
    """
    # Primero creamos un step válido y luego forzamos el campo corrupto.
    step = NavigationStep(
        id=None,
        path_id=None,
        step_order=0,
        action=NoiseAction.CLICK,
        selector="a[href*='statistics']",
        value="",
        delay_min_ms=200,  # valor válido inicialmente
        delay_max_ms=delay_max_ms,
        expected_url_after_click=None,
    )
    # Bypass de __post_init__ para simular dato corrupto en BD.
    object.__setattr__(step, "delay_min_ms", delay_min_ms)
    return step

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
WORLD_AGENT_SRC = REPO_ROOT / "core" / "scheduling" / "world_agent.py"


# ---------------------------------------------------------------------------
# Helpers de construcción de fixtures (sin browser real)
# ---------------------------------------------------------------------------

def _make_nav_step(
    step_order: int = 0,
    delay_min_ms: int = 500,
    delay_max_ms: int = 900,
    expected_url: str | None = None,
    selector: str = "a[href*='statistics']",
) -> NavigationStep:
    return NavigationStep(
        id=None,
        path_id=None,
        step_order=step_order,
        action=NoiseAction.CLICK,
        selector=selector,
        value="",
        delay_min_ms=delay_min_ms,
        delay_max_ms=delay_max_ms,
        expected_url_after_click=expected_url,
    )


def _make_atomic_path(
    origin: str = "ROUTE_TEMPLATE:1",
    step_order: int = 0,
    delay_min_ms: int = 500,
    delay_max_ms: int = 900,
    expected_url: str | None = None,
) -> NavigationPath:
    """NavigationPath con origin atómico para tests."""
    return NavigationPath(
        id=1,
        destination_id=1,
        origin=origin,
        label="Test atómico",
        is_active=True,
        is_dead=False,
        consecutive_failures_count=0,
        steps=[_make_nav_step(
            step_order=step_order,
            delay_min_ms=delay_min_ms,
            delay_max_ms=delay_max_ms,
            expected_url=expected_url,
        )],
    )


def _make_v1_path(origin: str = "ANY") -> NavigationPath:
    """NavigationPath con origin v1 clásico (NavigationOrigin)."""
    return NavigationPath(
        id=2,
        destination_id=2,
        origin=origin,
        label="Test v1",
        is_active=True,
        is_dead=False,
        consecutive_failures_count=0,
        steps=[_make_nav_step()],
    )


def _make_resolved_step(
    template_id: int = 1,
    slug: str = "statistics",
    selector: str = "a[href*='/statistics']",
    expected_url: str | None = "/statistics",
    delay_min_ms: int = 500,
    delay_max_ms: int = 900,
) -> ResolvedStep:
    step = _make_nav_step(
        selector=selector,
        delay_min_ms=delay_min_ms,
        delay_max_ms=delay_max_ms,
        expected_url=expected_url,
    )
    return ResolvedStep(
        template_id=template_id,
        template_slug=slug,
        label=slug,
        path_id=template_id,
        step=step,
        expected_url=expected_url,
    )


def _make_tab_mock(url: str = "https://ts1.travian.es/dorf1.php") -> MagicMock:
    """Mock de tab zendriver con url sincrónico y evaluate async."""
    tab = MagicMock()
    type(tab).url = property(lambda self: url)
    tab.evaluate = AsyncMock(return_value={"x": 100, "y": 200, "width": 50, "height": 20})
    return tab


def _make_browser_mock(tab_url: str = "https://ts1.travian.es/dorf1.php") -> MagicMock:
    browser = MagicMock()
    browser.main_tab = _make_tab_mock(tab_url)
    return browser


# ---------------------------------------------------------------------------
# CA-V2-16 / INVARIANTE-NAV-01 — Test ESTÁTICO
# Ninguna rama alcanzable desde el bloque "ROUTE_TEMPLATE:" contiene browser.get
# ---------------------------------------------------------------------------

class TestInvarianteNav01:
    """
    CA-V2-16: grep del bloque v2 en world_agent.py → CERO browser.get/tab.get.

    El test lee el código fuente de world_agent.py y verifica que dentro
    del bloque condicional que maneja 'ROUTE_TEMPLATE:' no hay llamadas a
    browser.get ni tab.get.

    Estrategia: se extrae el bloque que sigue al guard
    `if path.origin.startswith("ROUTE_TEMPLATE:")` hasta el `else:` (o hasta
    el comentario de FIN DEL FLUJO v2), y se verifica que no contiene
    `browser.get` ni `tab.get`.
    """

    # Número de bloques v2 que deben existir en world_agent.py:
    #   execute_path_test_standalone + _execute_noise_action + execute_path_test.
    EXPECTED_V2_BLOCKS = 3

    def _extract_atomic_block(self, source: str) -> str:
        """
        Extrae el contenido COMPLETO de cada bloque v2 buscando el guard de
        ROUTE_TEMPLATE y terminando SIEMPRE en el marcador 'FIN DEL FLUJO v2'.

        IMPORTANTE (guardian): el terminador es EXCLUSIVAMENTE
        '# FIN DEL FLUJO v2'. NO se usa 'else:' como terminador alternativo
        porque el primer 'else:' que aparece dentro del bloque atómico
        (p.ej. el `else` de `if not chain:` en _execute_noise_action, o el
        `else` del ancla v1 en el standalone) truncaría la captura ANTES del
        bucle real de ejecución de la cadena, dejando código sin auditar y
        produciendo un falso verde si alguien introdujera un browser.get en
        el bucle. El marcador de FIN delimita el bloque entero.

        Devuelve el texto concatenado de los N bloques. Cada bloque va
        delimitado por la línea-comentario de FIN, garantizando que el bucle
        de clics de la cadena queda DENTRO de lo auditado.
        """
        blocks = []
        pattern = re.compile(
            r'if path\.origin\.startswith\("ROUTE_TEMPLATE:"\):(.*?)'
            r'#\s*FIN DEL FLUJO v2',
            re.DOTALL,
        )
        for m in pattern.finditer(source):
            blocks.append(m.group(1))
        # Anti-falso-verde: si no se encontraron los N bloques esperados,
        # significa que un marcador de FIN se ha movido/borrado y la captura
        # ya no cubre el bucle de la cadena → el test DEBE fallar, no pasar
        # auditando un bloque parcial.
        assert len(blocks) == self.EXPECTED_V2_BLOCKS, (
            f"Se esperaban {self.EXPECTED_V2_BLOCKS} bloques v2 delimitados por "
            f"'# FIN DEL FLUJO v2', se encontraron {len(blocks)}. "
            "INVARIANTE-NAV-01 no auditable: revisa que cada guard "
            "'ROUTE_TEMPLATE:' termine con el marcador de FIN, o el bucle de "
            "ejecución de la cadena podría quedar sin auditar (falso verde)."
        )
        return "\n".join(blocks)

    def test_ca_v2_16_no_browser_get_en_bloque_atomico(self):
        """
        CA-V2-16: CERO browser.get / tab.get en el bloque v2 de world_agent.py.
        """
        source = WORLD_AGENT_SRC.read_text(encoding="utf-8")
        atomic_block = self._extract_atomic_block(source)
        assert atomic_block, (
            "No se encontró el bloque v2 (guard 'ROUTE_TEMPLATE:') en world_agent.py. "
            "Verifica que el guard está implementado."
        )
        # Verificar ausencia de browser.get y tab.get en el bloque atómico.
        assert "browser.get(" not in atomic_block, (
            "CA-V2-16 FALLIDO: se encontró 'browser.get(' en el bloque v2 de world_agent.py. "
            "INVARIANTE-NAV-01 violado — el bloque atómico NO puede contener browser.get."
        )
        assert "tab.get(" not in atomic_block, (
            "CA-V2-16 FALLIDO: se encontró 'tab.get(' en el bloque v2 de world_agent.py. "
            "INVARIANTE-NAV-01 violado — el bloque atómico NO puede contener tab.get."
        )

    def test_ca_v2_16_ast_ninguna_navegacion_en_cuerpo_del_guard(self):
        """
        CA-V2-16 (refuerzo AST, anti-falso-verde): recorre el AST de
        world_agent.py, localiza CADA `if path.origin.startswith("ROUTE_TEMPLATE:")`
        y verifica que en TODO el cuerpo del guard (incluido el bucle de
        ejecución de la cadena, anidamientos profundos y el dwell) no existe
        ninguna llamada de navegación: `browser.get(...)`, `tab.get(...)` ni
        `<algo>.main_tab.get(...)`.

        A diferencia del test por regex (que delimita por comentario), este test
        no depende de marcadores textuales: opera sobre la estructura real del
        código, por lo que un browser.get introducido en cualquier punto del
        bucle de la cadena lo hace fallar de inmediato.
        """
        source = WORLD_AGENT_SRC.read_text(encoding="utf-8")
        tree = ast.parse(source)

        def _is_route_template_guard(node: ast.If) -> bool:
            test = node.test
            # Forma: path.origin.startswith("ROUTE_TEMPLATE:")
            return (
                isinstance(test, ast.Call)
                and isinstance(test.func, ast.Attribute)
                and test.func.attr == "startswith"
                and len(test.args) == 1
                and isinstance(test.args[0], ast.Constant)
                and test.args[0].value == "ROUTE_TEMPLATE:"
            )

        def _navigation_calls_in(node: ast.AST) -> list[str]:
            """Devuelve descripciones de toda llamada .get( que parezca navegación."""
            hits: list[str] = []
            for sub in ast.walk(node):
                if not isinstance(sub, ast.Call):
                    continue
                func = sub.func
                if not isinstance(func, ast.Attribute) or func.attr != "get":
                    continue
                # Resolver el objeto receptor del .get(...)
                recv = func.value
                # browser.get(...) / tab.get(...) / browser.main_tab.get(...)
                recv_name = None
                if isinstance(recv, ast.Name):
                    recv_name = recv.id
                elif isinstance(recv, ast.Attribute):
                    recv_name = recv.attr  # p.ej. main_tab
                if recv_name in {"browser", "tab", "main_tab", "_browser"}:
                    hits.append(f"línea {sub.lineno}: {recv_name}.get(...)")
            return hits

        guards = [n for n in ast.walk(tree) if isinstance(n, ast.If) and _is_route_template_guard(n)]
        assert len(guards) >= 3, (
            f"Se esperaban >=3 guards 'ROUTE_TEMPLATE:' en el AST, hay {len(guards)}. "
            "El motor atómico debe bifurcar en standalone + _execute_noise_action + "
            "execute_path_test."
        )

        for guard in guards:
            # Auditar SOLO el cuerpo del guard (rama if), NO el else (flujo v1).
            offending: list[str] = []
            for stmt in guard.body:
                offending.extend(_navigation_calls_in(stmt))
            assert not offending, (
                "INVARIANTE-NAV-01 VIOLADO (AST): el cuerpo de un guard "
                f"'ROUTE_TEMPLATE:' (línea {guard.lineno}) contiene navegación: "
                f"{offending}. Las rutas atómicas NO pueden navegar con .get(); "
                "cada movimiento debe hacerse con human_click_at_rect."
            )

    def test_ca_v2_12_expected_url_no_se_pasa_a_browser_get(self):
        """
        CA-V2-12: expected_url_after_click y url_pattern solo aparecen en
        contextos de verificación (comparación), nunca como argumento de browser.get/tab.get.
        """
        source = WORLD_AGENT_SRC.read_text(encoding="utf-8")
        # Buscar patrones del tipo: browser.get(... expected_url ...) o
        # tab.get(... url_pattern ...)
        # Una búsqueda exacta es difícil; usamos el bloque atómico ya extraído.
        atomic_block = self._extract_atomic_block(source)
        # Asegurarse de que las únicas apariciones de expected_url en el bloque
        # son en comparaciones (in / not in), no en browser.get().
        # Buscamos el patrón: `browser.get(` seguido de algo que contenga "expected_url"
        bad_pattern = re.compile(r'browser\.get\([^)]*expected_url[^)]*\)')
        assert not bad_pattern.search(atomic_block), (
            "CA-V2-12 FALLIDO: expected_url se está usando como argumento de browser.get "
            "en el bloque v2."
        )

    def test_guard_tipo_existe_en_execute_noise_action(self):
        """
        El guard 'ROUTE_TEMPLATE:' existe en _execute_noise_action.
        """
        source = WORLD_AGENT_SRC.read_text(encoding="utf-8")
        assert 'path.origin.startswith("ROUTE_TEMPLATE:")' in source, (
            "El guard INVARIANTE-NAV-01 no está presente en world_agent.py. "
            "Debe existir el check 'if path.origin.startswith(\"ROUTE_TEMPLATE:\")'"
        )

    def test_guard_tipo_existe_en_execute_path_test(self):
        """
        El guard también existe en execute_path_test (o en execute_path_test_standalone).
        Verificar que hay al menos 2 ocurrencias del guard.
        """
        source = WORLD_AGENT_SRC.read_text(encoding="utf-8")
        count = source.count('path.origin.startswith("ROUTE_TEMPLATE:")')
        assert count >= 2, (
            f"Solo {count} ocurrencia(s) del guard ROUTE_TEMPLATE en world_agent.py. "
            "Se esperan al menos 2 (execute_path_test_standalone + execute_path_test o "
            "_execute_noise_action)."
        )


# ---------------------------------------------------------------------------
# CA-V2-17 / GAP-2 — ColdStartAbortError (tests dinámicos)
# ---------------------------------------------------------------------------

class TestColdStartAbort:
    """
    CA-V2-17: el motor aborta con ColdStartAbortError cuando el browser
    no está en una página válida de Travian.
    El motor NO llama a browser.get ni tab.get para recuperar la sesión.
    La noise_destination NO se marca is_dead por este fallo.
    """

    def test_check_cold_start_about_blank(self):
        """TI-V2-15 (parcial): about:blank → ColdStartAbortError."""
        tab = _make_tab_mock("about:blank")
        with pytest.raises(ColdStartAbortError) as exc_info:
            _check_cold_start(tab, "ts1.travian.es", world_id=1)
        assert exc_info.value.current_url == "about:blank"
        assert exc_info.value.world_id == 1

    def test_check_cold_start_empty_url(self):
        """URL vacía → ColdStartAbortError."""
        tab = _make_tab_mock("")
        with pytest.raises(ColdStartAbortError):
            _check_cold_start(tab, "ts1.travian.es", world_id=1)

    def test_check_cold_start_wrong_domain(self):
        """URL de dominio distinto al world_server → ColdStartAbortError."""
        tab = _make_tab_mock("https://google.com/")
        with pytest.raises(ColdStartAbortError) as exc_info:
            _check_cold_start(tab, "ts1.travian.es", world_id=2)
        assert "google.com" in exc_info.value.current_url

    def test_check_cold_start_login_page(self):
        """URL con patrón de login → ColdStartAbortError."""
        tab = _make_tab_mock("https://ts1.travian.es/login?next=/dorf1.php")
        with pytest.raises(ColdStartAbortError):
            _check_cold_start(tab, "ts1.travian.es", world_id=1)

    def test_check_cold_start_logout_page(self):
        """URL con /logout → ColdStartAbortError."""
        tab = _make_tab_mock("https://ts1.travian.es/logout")
        with pytest.raises(ColdStartAbortError):
            _check_cold_start(tab, "ts1.travian.es", world_id=1)

    def test_check_cold_start_valid_page_passes(self):
        """URL de página de juego válida → no lanza excepción."""
        tab = _make_tab_mock("https://ts1.travian.es/dorf1.php")
        # No debe lanzar
        _check_cold_start(tab, "ts1.travian.es", world_id=1)

    def test_check_cold_start_statistics_page_passes(self):
        """URL de estadísticas de Travian → no lanza excepción."""
        tab = _make_tab_mock("https://ts1.travian.es/statistics")
        _check_cold_start(tab, "ts1.travian.es", world_id=1)

    def test_check_cold_start_no_world_server_passes(self):
        """Sin world_server (string vacío) → no verifica dominio → no lanza."""
        tab = _make_tab_mock("https://ts1.travian.es/dorf1.php")
        _check_cold_start(tab, "", world_id=1)

    @pytest.mark.asyncio
    async def test_ti_v2_15_execute_noise_action_about_blank(self):
        """
        TI-V2-15: _execute_noise_action con tab en about:blank → no marca is_dead.

        El WorldAgent captura ColdStartAbortError y devuelve "error" sin tocar
        los contadores de is_dead (el fallo es de contexto, no de la ruta).
        """
        noise_db = MagicMock()
        noise_db.bump_destination_failures = AsyncMock(return_value=0)
        noise_db.mark_destination_dead = AsyncMock()
        noise_db.increment_path_failures = AsyncMock(return_value=0)
        noise_db.mark_path_dead = AsyncMock()

        browser_mock = _make_browser_mock("about:blank")
        registry = MagicMock()
        registry.get_browser = MagicMock(return_value=browser_mock)
        registry.get_world_server = MagicMock(return_value="ts1.travian.es")

        agent = WorldAgent(
            world_id=1,
            browser=MagicMock(),
            db=MagicMock(),
            noise_db=noise_db,
            session_registry=registry,
        )

        dest = NoiseDestination(
            id=1, world_id=1, label="Test", url_pattern="/statistics",
            category=NoiseCategory.OTHER,
            is_safe=True, is_dead=False, frequency_weight=1.0,
        )
        path = _make_atomic_path(origin="ROUTE_TEMPLATE:1")
        config = NoiseConfig(world_id=1)

        result = await agent._execute_noise_action(dest, path, config)

        assert result == "error", "Debe devolver 'error' en arranque en frío"
        # CRÍTICO: NO debe marcar el destino como dead (CA-V2-17)
        noise_db.mark_destination_dead.assert_not_called()
        # NO debe llamar a browser.get (verificado indirectamente: si llamara,
        # el mock lanzaría y se propagaría al caller)
        assert not browser_mock.get.called if hasattr(browser_mock, 'get') else True

    @pytest.mark.asyncio
    async def test_execute_path_test_standalone_cold_start_raises(self):
        """
        execute_path_test_standalone con browser en about:blank → ColdStartAbortError.
        Sin llamadas a browser.get.
        """
        browser = _make_browser_mock("about:blank")
        lock = asyncio.Lock()
        path = _make_atomic_path(origin="ROUTE_TEMPLATE:1")

        route_db = MagicMock()
        route_db.get_template = AsyncMock()

        with pytest.raises(ColdStartAbortError):
            await execute_path_test_standalone(
                browser=browser,
                path=path,
                lock=lock,
                world_id=1,
                world_server="ts1.travian.es",
                route_template_db=route_db,
            )

        # El lock debe haberse liberado (sino el siguiente test colgaría)
        assert not lock.locked(), "El lock debe liberarse aunque haya excepción"

    @pytest.mark.asyncio
    async def test_execute_path_test_standalone_cold_start_no_browser_get(self):
        """
        CA-V2-17: ninguna llamada a browser.get cuando el browser está en about:blank.
        """
        browser = _make_browser_mock("about:blank")
        browser.get = AsyncMock()  # trackeamos llamadas
        lock = asyncio.Lock()
        path = _make_atomic_path(origin="ROUTE_TEMPLATE:1")

        with pytest.raises(ColdStartAbortError):
            await execute_path_test_standalone(
                browser=browser,
                path=path,
                lock=lock,
                world_id=1,
                world_server="ts1.travian.es",
                route_template_db=MagicMock(),
            )

        browser.get.assert_not_called()


# ---------------------------------------------------------------------------
# CA-V2-18 / GAP-3 — Piso defensivo de delay en runtime
# ---------------------------------------------------------------------------

class TestDelayPisoDefensivo:
    """
    CA-V2-18 / TI-V2-14: el delay entre steps de la cadena nunca baja de
    200 ms en runtime, aunque step.delay_min_ms sea 50 (dato corrupto).

    Verificamos que execute_path_test_standalone llama a human_delay con
    max(200, step.delay_min_ms) como primer argumento.
    """

    @pytest.mark.asyncio
    async def test_ti_v2_14_piso_200ms_delay_min_corrupto(self):
        """
        TI-V2-14: step.delay_min_ms=50 (dato corrupto en BD) → human_delay
        llamado con mínimo 200 ms (piso GAP-3).
        El step se construye con bypass de __post_init__ para simular dato pre-validación.
        """
        step_with_low_delay = _make_nav_step_corrupted(delay_min_ms=50, delay_max_ms=300)
        resolved = ResolvedStep(
            template_id=1,
            template_slug="statistics",
            label="Estadísticas",
            path_id=1,
            step=step_with_low_delay,
            expected_url=None,
        )

        browser = _make_browser_mock("https://ts1.travian.es/dorf1.php")
        lock = asyncio.Lock()
        # El path en sí puede tener delay_min_ms válido (el step es el corrupto)
        path = _make_atomic_path(origin="ROUTE_TEMPLATE:1")

        route_db = MagicMock()
        route_db.get_template = AsyncMock()

        human_delay_calls = []

        async def mock_human_delay(min_ms: int, max_ms: int) -> None:
            human_delay_calls.append((min_ms, max_ms))

        async def mock_human_click_at_rect(rect, tab):
            pass

        with (
            patch(
                "core.scheduling.world_agent.resolve_origin_chain",
                new=AsyncMock(return_value=[resolved]),
            ),
            patch(
                "adapters.browser.driver.human_click_at_rect",
                new=mock_human_click_at_rect,
            ),
            patch(
                "adapters.browser.driver.human_delay",
                new=mock_human_delay,
            ),
        ):
            report = await execute_path_test_standalone(
                browser=browser,
                path=path,
                lock=lock,
                world_id=1,
                world_server="ts1.travian.es",
                route_template_db=route_db,
            )

        # Verificar que human_delay se llamó con mínimo 200 ms (piso GAP-3)
        assert human_delay_calls, "human_delay debe haberse llamado al menos una vez"
        for min_ms, max_ms in human_delay_calls:
            assert min_ms >= 200, (
                f"CA-V2-18 / GAP-3 FALLIDO: human_delay llamado con min_ms={min_ms} < 200. "
                "El piso defensivo de 200 ms debe aplicarse SIEMPRE."
            )

    @pytest.mark.asyncio
    async def test_delay_min_500_no_reducido(self):
        """
        Si delay_min_ms=500 (válido), se usa directamente sin alterar.
        """
        step = _make_nav_step(delay_min_ms=500, delay_max_ms=900)
        resolved = ResolvedStep(
            template_id=1, template_slug="stats", label="Stats",
            path_id=1, step=step, expected_url=None,
        )

        browser = _make_browser_mock("https://ts1.travian.es/dorf1.php")
        lock = asyncio.Lock()
        path = _make_atomic_path(origin="ROUTE_TEMPLATE:1")

        human_delay_calls = []

        async def mock_human_delay(min_ms, max_ms):
            human_delay_calls.append((min_ms, max_ms))

        async def mock_human_click_at_rect(rect, tab):
            pass

        with (
            patch("core.scheduling.world_agent.resolve_origin_chain",
                  new=AsyncMock(return_value=[resolved])),
            patch("adapters.browser.driver.human_click_at_rect",
                  new=mock_human_click_at_rect),
            patch("adapters.browser.driver.human_delay", new=mock_human_delay),
        ):
            await execute_path_test_standalone(
                browser=browser, path=path, lock=lock,
                world_id=1, world_server="ts1.travian.es",
                route_template_db=MagicMock(),
            )

        assert any(min_ms == 500 for min_ms, _ in human_delay_calls), (
            "delay_min_ms=500 debe usarse tal cual (sin reducción)"
        )


# ---------------------------------------------------------------------------
# CA-V2-09 / CA-V2-11 — Motor ejecuta cadena con human_click (tests dinámicos)
# ---------------------------------------------------------------------------

class TestCadenaHumanClick:
    """
    CA-V2-09: Motor ejecuta la cadena completa con human_click para cada step.
    CA-V2-11: Modo test recorre la cadena con human_click (no browser.get).
    """

    @pytest.mark.asyncio
    async def test_cadena_3_pasos_usa_human_click_at_rect(self):
        """
        Una cadena de 3 ResolvedStep → human_click_at_rect llamado 3 veces.
        """
        chain = [
            _make_resolved_step(1, "statistics", "a[href*='/statistics']", "/statistics"),
            _make_resolved_step(2, "top10-alianzas", "a[href*='/alliances']", "/statistics/alliances"),
            _make_resolved_step(3, "rival-alliances", "a.alliance-name", "/statistics/alliances/2"),
        ]

        browser = _make_browser_mock("https://ts1.travian.es/dorf1.php")
        lock = asyncio.Lock()
        path = _make_atomic_path(origin="ROUTE_TEMPLATE:3")

        click_calls = []

        async def mock_click(rect, tab):
            click_calls.append(rect)

        async def mock_delay(min_ms, max_ms):
            pass

        # Simular que tab.url cambia progresivamente para que las verificaciones pasen
        urls = [
            "https://ts1.travian.es/statistics",
            "https://ts1.travian.es/statistics/alliances",
            "https://ts1.travian.es/statistics/alliances/2",
        ]
        call_count = [0]

        original_tab = browser.main_tab
        original_eval = original_tab.evaluate

        async def mock_evaluate(js):
            return {"x": 100, "y": 200, "width": 50, "height": 20}

        original_tab.evaluate = mock_evaluate

        # Parchear tab.url para que devuelva progresivamente
        url_iter = iter(urls)
        def get_url():
            try:
                return next(url_iter)
            except StopIteration:
                return urls[-1]
        type(original_tab).url = property(lambda self: get_url())

        with (
            patch("core.scheduling.world_agent.resolve_origin_chain",
                  new=AsyncMock(return_value=chain)),
            patch("adapters.browser.driver.human_click_at_rect", new=mock_click),
            patch("adapters.browser.driver.human_delay", new=mock_delay),
        ):
            report = await execute_path_test_standalone(
                browser=browser, path=path, lock=lock,
                world_id=1, world_server="ts1.travian.es",
                route_template_db=MagicMock(),
            )

        assert len(click_calls) == 3, (
            f"CA-V2-09: se esperaban 3 clicks, se hicieron {len(click_calls)}"
        )
        assert report.overall == "ok", f"El test debería completarse ok: {report}"

    @pytest.mark.asyncio
    async def test_motor_produccion_cadena_usa_human_click_sin_browser_get(self):
        """
        CA-V2-09 (motor de PRODUCCIÓN): _execute_noise_action ejecuta la cadena
        atómica con human_click_at_rect por CADA eslabón y SIN browser.get.

        A diferencia de los demás tests de esta clase (que prueban el helper
        standalone), este ejercita el camino real que corre el scheduler:
        WorldAgent._execute_noise_action con path.origin='ROUTE_TEMPLATE:'.
        """
        chain = [
            _make_resolved_step(1, "statistics", "a[href*='/statistics']", None),
            _make_resolved_step(2, "top10", "a[href*='/alliances']", None),
            _make_resolved_step(3, "rival", "a.alliance-name", None),
        ]

        browser = _make_browser_mock("https://ts1.travian.es/dorf1.php")
        browser.get = AsyncMock()  # trackear cualquier intento de navegación

        registry = MagicMock()
        registry.get_browser = MagicMock(return_value=browser)
        registry.get_world_server = MagicMock(return_value="ts1.travian.es")

        route_db = MagicMock()
        noise_db = MagicMock()
        noise_db.get_route_template_db = MagicMock(return_value=route_db)
        noise_db.reset_destination_failures = AsyncMock()
        noise_db.touch_last_used_at = AsyncMock()
        noise_db.reset_path_failures = AsyncMock()
        noise_db.bump_destination_failures = AsyncMock(return_value=0)
        noise_db.mark_destination_dead = AsyncMock()
        noise_db.increment_path_failures = AsyncMock(return_value=0)
        noise_db.mark_path_dead = AsyncMock()

        agent = WorldAgent(
            world_id=1, browser=MagicMock(), db=MagicMock(),
            noise_db=noise_db, session_registry=registry,
        )

        dest = NoiseDestination(
            id=1, world_id=1, label="Test", url_pattern="/statistics",
            category=NoiseCategory.OTHER,
            is_safe=True, is_dead=False, frequency_weight=1.0,
        )
        path = _make_atomic_path(origin="ROUTE_TEMPLATE:1")
        config = NoiseConfig(world_id=1, dwell_min_seconds=0.0, dwell_max_seconds=0.0)

        click_calls = []

        async def mock_click(rect, tab):
            click_calls.append(rect)

        async def mock_delay(min_ms, max_ms):
            pass

        with (
            patch("core.scheduling.world_agent.resolve_origin_chain",
                  new=AsyncMock(return_value=chain)),
            patch("adapters.browser.driver.human_click_at_rect", new=mock_click),
            patch("adapters.browser.driver.human_delay", new=mock_delay),
        ):
            result = await agent._execute_noise_action(dest, path, config)

        assert result == "ok", f"La cadena debía completarse ok, fue '{result}'"
        assert len(click_calls) == 3, (
            f"CA-V2-09: se esperaban 3 human_click_at_rect en el motor de "
            f"producción, hubo {len(click_calls)}"
        )
        browser.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_motor_produccion_piso_200ms_dato_corrupto(self):
        """
        CA-V2-18 (motor de PRODUCCIÓN): aunque el step llegue con delay_min_ms=50
        (dato corrupto en BD), _execute_noise_action llama a human_delay con
        mínimo 200 ms. El piso defensivo se aplica en el camino real, no solo
        en el helper standalone.
        """
        corrupted = _make_nav_step_corrupted(delay_min_ms=50, delay_max_ms=300)
        resolved = ResolvedStep(
            template_id=1, template_slug="stats", label="Stats",
            path_id=1, step=corrupted, expected_url=None,
        )

        browser = _make_browser_mock("https://ts1.travian.es/dorf1.php")
        browser.get = AsyncMock()
        registry = MagicMock()
        registry.get_browser = MagicMock(return_value=browser)
        registry.get_world_server = MagicMock(return_value="ts1.travian.es")

        route_db = MagicMock()
        noise_db = MagicMock()
        noise_db.get_route_template_db = MagicMock(return_value=route_db)
        noise_db.reset_destination_failures = AsyncMock()
        noise_db.touch_last_used_at = AsyncMock()
        noise_db.reset_path_failures = AsyncMock()

        agent = WorldAgent(
            world_id=1, browser=MagicMock(), db=MagicMock(),
            noise_db=noise_db, session_registry=registry,
        )

        dest = NoiseDestination(
            id=1, world_id=1, label="Test", url_pattern="/statistics",
            category=NoiseCategory.OTHER,
            is_safe=True, is_dead=False, frequency_weight=1.0,
        )
        path = _make_atomic_path(origin="ROUTE_TEMPLATE:1")
        config = NoiseConfig(world_id=1, dwell_min_seconds=0.0, dwell_max_seconds=0.0)

        delay_calls = []

        async def mock_click(rect, tab):
            pass

        async def mock_delay(min_ms, max_ms):
            delay_calls.append((min_ms, max_ms))

        with (
            patch("core.scheduling.world_agent.resolve_origin_chain",
                  new=AsyncMock(return_value=[resolved])),
            patch("adapters.browser.driver.human_click_at_rect", new=mock_click),
            patch("adapters.browser.driver.human_delay", new=mock_delay),
        ):
            result = await agent._execute_noise_action(dest, path, config)

        assert result == "ok"
        assert delay_calls, "human_delay debe llamarse al menos una vez"
        for min_ms, _max_ms in delay_calls:
            assert min_ms >= 200, (
                f"CA-V2-18 (producción) FALLIDO: human_delay con min_ms={min_ms} < 200. "
                "El piso de 200 ms debe aplicarse en el motor real."
            )
        browser.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_cadena_vacia_no_falla(self):
        """
        EC-V2-07: plantilla sin steps → cadena vacía → reporte ok sin clicks.
        """
        browser = _make_browser_mock("https://ts1.travian.es/dorf1.php")
        lock = asyncio.Lock()
        path = _make_atomic_path(origin="ROUTE_TEMPLATE:1")

        with patch("core.scheduling.world_agent.resolve_origin_chain",
                   new=AsyncMock(return_value=[])):
            report = await execute_path_test_standalone(
                browser=browser, path=path, lock=lock,
                world_id=1, world_server="ts1.travian.es",
                route_template_db=MagicMock(),
            )

        assert report.overall == "ok"
        assert report.steps == []

    @pytest.mark.asyncio
    async def test_fallo_verificacion_url_aborta_cadena(self):
        """
        Si expected_url no coincide con la URL actual tras el click,
        la cadena se aborta en ese eslabón. Los steps posteriores NO se ejecutan.

        CA-V2-10 (parcial): abortar cadena al primer fallo de URL.
        """
        chain = [
            _make_resolved_step(1, "statistics", "a[href*='/statistics']",
                                expected_url="/statistics"),
            _make_resolved_step(2, "top10", "a[href*='/alliances']",
                                expected_url="/statistics/alliances"),
        ]

        # Tab siempre en dorf1 → la URL nunca coincide con expected_url
        browser = _make_browser_mock("https://ts1.travian.es/dorf1.php")
        lock = asyncio.Lock()
        path = _make_atomic_path(origin="ROUTE_TEMPLATE:2")

        click_calls = []

        async def mock_click(rect, tab):
            click_calls.append(1)

        async def mock_delay(min_ms, max_ms):
            pass

        with (
            patch("core.scheduling.world_agent.resolve_origin_chain",
                  new=AsyncMock(return_value=chain)),
            patch("adapters.browser.driver.human_click_at_rect", new=mock_click),
            patch("adapters.browser.driver.human_delay", new=mock_delay),
        ):
            report = await execute_path_test_standalone(
                browser=browser, path=path, lock=lock,
                world_id=1, world_server="ts1.travian.es",
                route_template_db=MagicMock(),
            )

        assert report.overall == "error", "Fallo de URL debe producir overall=error"
        assert len(click_calls) == 1, (
            f"Solo debe ejecutarse el primer click antes de abortar (se hicieron {len(click_calls)})"
        )
        assert report.aborted_at_step == 0, f"Debe abortar en el step 0, no en {report.aborted_at_step}"

    @pytest.mark.asyncio
    async def test_selector_no_encontrado_aborta_cadena(self):
        """
        Si el selector del primer eslabón no existe en el DOM,
        la cadena se aborta sin ejecutar los siguientes.
        """
        chain = [
            _make_resolved_step(1, "statistics", "a[href*='/statistics']", None),
            _make_resolved_step(2, "top10", "a[href*='/alliances']", None),
        ]

        browser = _make_browser_mock("https://ts1.travian.es/dorf1.php")
        # tab.evaluate devuelve None → elemento no encontrado
        browser.main_tab.evaluate = AsyncMock(return_value=None)
        lock = asyncio.Lock()
        path = _make_atomic_path(origin="ROUTE_TEMPLATE:2")

        click_calls = []

        async def mock_click(rect, tab):
            click_calls.append(1)

        async def mock_delay(min_ms, max_ms):
            pass

        with (
            patch("core.scheduling.world_agent.resolve_origin_chain",
                  new=AsyncMock(return_value=chain)),
            patch("adapters.browser.driver.human_click_at_rect", new=mock_click),
            patch("adapters.browser.driver.human_delay", new=mock_delay),
        ):
            report = await execute_path_test_standalone(
                browser=browser, path=path, lock=lock,
                world_id=1, world_server="ts1.travian.es",
                route_template_db=MagicMock(),
            )

        assert report.overall == "error"
        # Ningún click debe haberse ejecutado si el elemento no se encontró
        assert len(click_calls) == 0, "No debe clicar si el elemento no existe en el DOM"


# ---------------------------------------------------------------------------
# Verificar que execute_path_test del WorldAgent (wrapper) sigue el guard
# ---------------------------------------------------------------------------

class TestExecutePathTestWrapper:
    """
    execute_path_test (método de WorldAgent) aplica el guard ROUTE_TEMPLATE:
    y delega en execute_path_test_standalone para rutas atómicas.
    Para rutas v1, mantiene el comportamiento original.
    """

    @pytest.mark.asyncio
    async def test_execute_path_test_atomico_delega_en_standalone(self):
        """
        CA-V2-11: execute_path_test con origin ROUTE_TEMPLATE: delega en standalone.
        No llama a browser.get.
        """
        browser = _make_browser_mock("https://ts1.travian.es/dorf1.php")
        registry = MagicMock()
        registry.get_browser = MagicMock(return_value=browser)
        registry.get_world_server = MagicMock(return_value="ts1.travian.es")

        noise_db = MagicMock()
        noise_db._route_template_db = MagicMock()

        agent = WorldAgent(
            world_id=1,
            browser=MagicMock(),
            db=MagicMock(),
            noise_db=noise_db,
            session_registry=registry,
        )

        path = _make_atomic_path(origin="ROUTE_TEMPLATE:1")

        standalone_called = []

        async def mock_standalone(browser, path, lock, world_id, world_server, route_template_db):
            standalone_called.append(True)
            from core.entities.noise_test import PathTestReport
            return PathTestReport(overall="ok")

        with patch("core.scheduling.world_agent.execute_path_test_standalone",
                   new=mock_standalone):
            report = await agent.execute_path_test(path)

        assert standalone_called, (
            "CA-V2-11: execute_path_test debe delegar en execute_path_test_standalone "
            "para rutas atómicas."
        )
        assert report.overall == "ok"

    @pytest.mark.asyncio
    async def test_execute_path_test_v1_usa_browser_get(self):
        """
        Rutas v1 clásicas (NavigationOrigin.ANY) mantienen el comportamiento original.
        """
        browser = _make_browser_mock("https://ts1.travian.es/dorf1.php")
        browser.get = AsyncMock()
        registry = MagicMock()
        registry.get_browser = MagicMock(return_value=browser)
        registry.get_world_server = MagicMock(return_value="ts1.travian.es")

        agent = WorldAgent(
            world_id=1, browser=MagicMock(), db=MagicMock(),
            session_registry=registry,
        )

        path = _make_v1_path(origin="ANY")  # NavigationOrigin.ANY

        async def mock_execute_step(tab, step):
            pass

        async def mock_delay(min_ms, max_ms):
            pass

        with (
            patch.object(agent, "_execute_noise_step", new=mock_execute_step),
            patch("adapters.browser.driver.human_delay", new=mock_delay),
        ):
            report = await agent.execute_path_test(path)

        # Con origin=ANY, NO navega al ancla (no hay browser.get esperado por eso)
        # pero el flujo v1 sí se ejecutó (no el v2)
        assert report is not None


# ---------------------------------------------------------------------------
# Lock liberado siempre — incluso con excepción
# ---------------------------------------------------------------------------

class TestLockSiempreLiberado:
    """
    El lock de browser debe liberarse siempre, incluso si hay excepción.
    Esto incluye ColdStartAbortError.
    """

    @pytest.mark.asyncio
    async def test_lock_liberado_tras_cold_start_abort(self):
        """Lock liberado tras ColdStartAbortError."""
        browser = _make_browser_mock("about:blank")
        lock = asyncio.Lock()
        path = _make_atomic_path(origin="ROUTE_TEMPLATE:1")

        with pytest.raises(ColdStartAbortError):
            await execute_path_test_standalone(
                browser=browser, path=path, lock=lock,
                world_id=1, world_server="ts1.travian.es",
                route_template_db=MagicMock(),
            )

        assert not lock.locked(), "El lock debe estar liberado tras ColdStartAbortError"

    @pytest.mark.asyncio
    async def test_lock_liberado_tras_exito(self):
        """Lock liberado tras ejecución exitosa."""
        browser = _make_browser_mock("https://ts1.travian.es/dorf1.php")
        lock = asyncio.Lock()
        path = _make_atomic_path(origin="ROUTE_TEMPLATE:1")

        with (
            patch("core.scheduling.world_agent.resolve_origin_chain",
                  new=AsyncMock(return_value=[])),
        ):
            await execute_path_test_standalone(
                browser=browser, path=path, lock=lock,
                world_id=1, world_server="ts1.travian.es",
                route_template_db=MagicMock(),
            )

        assert not lock.locked(), "El lock debe estar liberado tras ejecución exitosa"

    @pytest.mark.asyncio
    async def test_browser_busy_si_lock_tomado(self):
        """Si el lock ya está tomado, execute_path_test_standalone lanza BrowserBusyError."""
        browser = _make_browser_mock("https://ts1.travian.es/dorf1.php")
        lock = asyncio.Lock()
        await lock.acquire()  # Lock ya tomado

        path = _make_atomic_path(origin="ROUTE_TEMPLATE:1")

        # PATH_TEST_TIMEOUT_SECONDS es 60 — para el test usamos un timeout pequeño
        import core.scheduling.world_agent as wa_module
        original = wa_module.PATH_TEST_TIMEOUT_SECONDS
        wa_module.PATH_TEST_TIMEOUT_SECONDS = 0.01  # 10 ms para acelerar el test

        try:
            with pytest.raises(BrowserBusyError):
                await execute_path_test_standalone(
                    browser=browser, path=path, lock=lock,
                    world_id=1, world_server="ts1.travian.es",
                    route_template_db=MagicMock(),
                )
        finally:
            wa_module.PATH_TEST_TIMEOUT_SECONDS = original
            lock.release()
