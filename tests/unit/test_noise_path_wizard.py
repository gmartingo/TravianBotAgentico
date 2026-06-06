"""
Tests de dominio para Noise Path Wizard.

Cubre:
  - derive_selector (UT-NP01..UT-NP11): algoritmo de derivación de selectores.
  - _validate_origin (UT-NP12..UT-NP16): validación de origin en rutas.
  - NavigationStep / NavigationPath constructores (UT-NP17, UT-NP18).
  - _extract_url_path (UT-NP19, UT-NP20): helper de extracción de path.
  - Lógica is_dead en WorldAgent (UT-NP21, UT-NP22, UT-NP23): fallos de ruta.

Spec noise-path-wizard.md §12 (Plan de pruebas).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adapters.db.noise_sqlite_adapter import _validate_origin
from core.entities.noise import (
    NavigationOrigin,
    NavigationPath,
    NavigationStep,
    NoiseAction,
    NoiseConfig,
    NoiseDestination,
)
from core.entities.session import SessionMode
from core.scheduling.world_agent import (
    NOISE_PATH_DEAD_THRESHOLD,
    WorldAgent,
    _extract_url_path,
)
from core.use_cases.derive_selector import derive_selector


# ===========================================================================
# Helpers
# ===========================================================================

def make_destination(
    id: int = 1,
    world_id: int = 1,
    url_pattern: str = "/karte.php",
    label: str = "Mapa",
    category_slug: str = "uncategorized",
) -> NoiseDestination:
    return NoiseDestination(
        id=id, world_id=world_id, url_pattern=url_pattern,
        label=label, category_slug=category_slug, frequency_weight=1.0,
    )


def make_step(
    action: NoiseAction = NoiseAction.CLICK,
    selector: str = "a[href*='/statistics']",
    expected_url: str | None = None,
) -> NavigationStep:
    return NavigationStep(
        id=None, path_id=None, step_order=0,
        action=action, selector=selector,
        expected_url_after_click=expected_url,
    )


def make_path(
    id: int = 1,
    steps: list | None = None,
    consecutive_failures_count: int = 0,
) -> NavigationPath:
    return NavigationPath(
        id=id,
        destination_id=1,
        origin=NavigationOrigin.ANY.value,
        label="Ruta de test",
        is_active=True,
        consecutive_failures_count=consecutive_failures_count,
        steps=steps or [make_step()],
    )


def _make_noise_db_mock(bump_path_return: int = 1, bump_dest_return: int = 1) -> MagicMock:
    db = MagicMock()
    db.reset_destination_failures = AsyncMock()
    db.bump_destination_failures   = AsyncMock(return_value=bump_dest_return)
    db.mark_destination_dead       = AsyncMock()
    db.touch_last_used_at          = AsyncMock()
    db.increment_path_failures     = AsyncMock(return_value=bump_path_return)
    db.reset_path_failures         = AsyncMock()
    db.mark_path_dead              = AsyncMock()
    return db


def _make_agent(noise_db=None, session_registry=None) -> WorldAgent:
    browser = MagicMock()
    db      = MagicMock()
    return WorldAgent(
        world_id=1, browser=browser, db=db,
        noise_db=noise_db, session_registry=session_registry,
    )


def _make_registry_with_browser(tab=None) -> MagicMock:
    if tab is None:
        tab = MagicMock()
    browser = MagicMock()
    browser.main_tab = tab
    registry = MagicMock()
    registry.get_browser = MagicMock(return_value=browser)
    return registry


def _make_mock_tab(url: str = "https://ts1.travian.es/dorf1.php") -> MagicMock:
    tab = MagicMock()
    tab.evaluate = AsyncMock()
    tab.wait_for = AsyncMock()
    tab.url = url  # propiedad sincrónica en zendriver
    return tab


# ===========================================================================
# UT-NP01..UT-NP11 — derive_selector
# ===========================================================================

class TestDeriveSelector:

    def test_UT_NP01_id_valido(self):
        """UT-NP01: id válido → selector='#statistics', method='id', is_unique=True."""
        result = derive_selector('<a id="statistics" href="/stats">Estadísticas</a>')
        assert result.selector == "#statistics"
        assert result.method == "id"
        assert result.is_unique is True

    def test_UT_NP02_id_autogenerado_ember_descartado(self):
        """UT-NP02: id auto-generado (ember) → se descarta; avanza al siguiente nivel."""
        result = derive_selector('<div id="ember123" class="menu-item"></div>')
        # El id ember123 se descarta; sin name, href, data-* → clases o fallback
        assert result.method != "id"

    def test_UT_NP03_name_attribute(self):
        """UT-NP03: atributo name → selector='input[name='username']', method='name'."""
        result = derive_selector('<input name="username" type="text">')
        assert result.selector == "input[name='username']"
        assert result.method == "name"
        assert result.is_unique is True

    def test_UT_NP04_gid_en_href(self):
        """UT-NP04: gid=N en href → selector='a[href*='gid=2']', method='gid'."""
        result = derive_selector('<a href="/build.php?gid=2">Almacén</a>')
        assert result.selector == "a[href*='gid=2']"
        assert result.method == "gid"
        assert result.is_unique is True

    def test_UT_NP05_href_exacto(self):
        """UT-NP05: href exacto (sin query/hash, empieza por /) → method='href_exact'."""
        result = derive_selector('<a href="/statistics">Estadísticas</a>')
        assert result.selector == "a[href='/statistics']"
        assert result.method == "href_exact"
        assert result.is_unique is True

    def test_UT_NP06_href_parcial(self):
        """UT-NP06: href con query string → method='href_partial', is_unique heurístico."""
        result = derive_selector('<a href="/village/statistics?did=123">Stats aldea</a>')
        assert result.selector == "a[href*='/village/statistics']"
        assert result.method == "href_partial"
        # is_unique puede ser True (heurístico) o False, ambos son válidos
        assert result.priority_level == 5

    def test_UT_NP07_data_attr_estable(self):
        """UT-NP07: data-* con valor estable → method='data_attr'."""
        result = derive_selector('<li data-gid="2">Granero</li>')
        assert result.selector == "li[data-gid='2']"
        assert result.method == "data_attr"
        assert result.is_unique is True

    def test_UT_NP08_data_attr_inestable_descartado(self):
        """UT-NP08: data-* con timestamp → se descarta; avanza."""
        # 1717326000 tiene 10 dígitos → UNSTABLE_DATA_PATTERN lo descarta
        result = derive_selector('<div data-ts="1717326000" class="item">X</div>')
        assert result.method != "data_attr"

    def test_UT_NP09_clases_css_semanticas(self):
        """UT-NP09: clases CSS semánticas → method='class_combo', is_unique=False."""
        result = derive_selector('<a class="nav-link statistics">Estadísticas</a>')
        assert result.method == "class_combo"
        assert result.is_unique is False
        assert "nav-link" in result.selector or "statistics" in result.selector

    def test_UT_NP10_solo_clases_utilitarias_tailwind(self):
        """UT-NP10: solo clases utilitarias Tailwind → fallback, priority_level=9."""
        result = derive_selector('<a class="w-4 h-4 flex">X</a>')
        assert result.priority_level == 9
        assert result.method == "fallback"

    def test_UT_NP11_html_malformado_lanza_valueerror(self):
        """UT-NP11: HTML malformado → ValueError."""
        with pytest.raises(ValueError, match="outerHTML no pudo parsearse"):
            derive_selector("<not html")

    def test_outer_html_vacio_lanza_valueerror(self):
        """outer_html vacío → ValueError."""
        with pytest.raises(ValueError, match="vacío"):
            derive_selector("")

    def test_outer_html_solo_whitespace_lanza_valueerror(self):
        """outer_html con solo espacios → ValueError."""
        with pytest.raises(ValueError, match="vacío"):
            derive_selector("   ")


# ===========================================================================
# UT-NP12..UT-NP16 — _validate_origin
# ===========================================================================

class TestValidateOrigin:

    def test_UT_NP12_valor_enum_valido(self):
        """UT-NP12: valor del enum válido → sin excepción."""
        _validate_origin("STATISTICS", village_data_ids=[])
        _validate_origin("DORF1", village_data_ids=[])
        _validate_origin("ANY", village_data_ids=[])

    def test_UT_NP13_village_data_id_existente(self):
        """UT-NP13: VILLAGE_123 con data_id=123 en villages → sin excepción."""
        _validate_origin("VILLAGE_123", village_data_ids=[123, 456])

    def test_UT_NP14_village_data_id_inexistente(self):
        """UT-NP14: VILLAGE_999 con data_id=999 no en villages → ValueError."""
        with pytest.raises(ValueError, match="999"):
            _validate_origin("VILLAGE_999", village_data_ids=[123])

    def test_UT_NP15_valor_invalido(self):
        """UT-NP15: valor inválido → ValueError."""
        with pytest.raises(ValueError):
            _validate_origin("UNKNOWN", village_data_ids=[])

    def test_UT_NP16_village_data_id_no_numerico(self):
        """UT-NP16: VILLAGE_abc → ValueError (sufijo no numérico)."""
        with pytest.raises(ValueError):
            _validate_origin("VILLAGE_abc", village_data_ids=[])


# ===========================================================================
# UT-NP17, UT-NP18 — NavigationStep y NavigationPath
# ===========================================================================

class TestNavigationEntities:

    def test_UT_NP17_expected_url_none_valido(self):
        """UT-NP17: NavigationStep con expected_url_after_click=None → sin error."""
        step = NavigationStep(
            id=None, path_id=None, step_order=0,
            action=NoiseAction.CLICK, selector="a[href='/statistics']",
            expected_url_after_click=None,
        )
        assert step.expected_url_after_click is None

    def test_UT_NP18_consecutive_failures_default_cero(self):
        """UT-NP18: NavigationPath sin consecutive_failures_count → default=0."""
        path = NavigationPath(
            id=None, destination_id=1,
            origin="ANY", label="Test path",
        )
        assert path.consecutive_failures_count == 0

    def test_navegation_path_is_dead_default_false(self):
        """NavigationPath.is_dead = False por defecto."""
        path = NavigationPath(id=None, destination_id=1, origin="ANY", label="x")
        assert path.is_dead is False

    def test_navegation_origin_tiene_9_valores(self):
        """CA-NP01: NavigationOrigin tiene exactamente 9 valores."""
        expected = {
            "DORF1", "DORF2", "MAP", "STATISTICS", "REPORTS",
            "MESSAGES", "VILLAGE_STATISTICS", "OASIS_VIEW", "ANY"
        }
        actual = {o.value for o in NavigationOrigin}
        assert actual == expected


# ===========================================================================
# UT-NP19, UT-NP20 — _extract_url_path
# ===========================================================================

class TestExtractUrlPath:

    def test_UT_NP19_url_absoluta(self):
        """UT-NP19: URL absoluta → extrae solo el path."""
        assert _extract_url_path("https://ts1.travian.es/statistics") == "/statistics"

    def test_UT_NP20_ruta_relativa(self):
        """UT-NP20: ruta relativa → devuelve tal cual."""
        assert _extract_url_path("/statistics") == "/statistics"

    def test_url_absoluta_con_query(self):
        """URL absoluta con query string → incluye el path+query."""
        result = _extract_url_path("https://ts1.travian.es/statistics?x=1")
        assert "/statistics" in result

    def test_url_relativa_con_query(self):
        """URL relativa con query → devuelve tal cual."""
        assert _extract_url_path("/statistics?session=abc") == "/statistics?session=abc"


# ===========================================================================
# UT-NP21, UT-NP22, UT-NP23 — lógica is_dead de rutas en WorldAgent
# ===========================================================================

class TestWorldAgentPathFailures:

    def test_UT_NP21_fallo_paso_incrementa_contador(self):
        """UT-NP21: fallo en paso → incrementa consecutive_failures_count, ruta no muerta."""
        noise_db = _make_noise_db_mock(bump_path_return=1, bump_dest_return=1)

        tab = _make_mock_tab()
        tab.evaluate = AsyncMock(return_value=None)  # → NoiseStepError

        registry = _make_registry_with_browser(tab=tab)
        agent = _make_agent(noise_db=noise_db, session_registry=registry)

        dest   = make_destination()
        path   = make_path(id=42)
        config = NoiseConfig(world_id=1)

        with patch("adapters.browser.driver.human_click_at_rect", new=AsyncMock()), \
             patch("adapters.browser.driver.human_delay", new=AsyncMock()):
            result = asyncio.run(agent._execute_noise_action(dest, path, config))

        assert result == "error"
        noise_db.increment_path_failures.assert_called_once_with(42)
        noise_db.mark_path_dead.assert_not_called()

    def test_UT_NP22_tres_fallos_consecutivos_marca_dead(self):
        """UT-NP22: 3 fallos consecutivos → mark_path_dead llamado."""
        noise_db = _make_noise_db_mock(
            bump_path_return=NOISE_PATH_DEAD_THRESHOLD,
            bump_dest_return=NOISE_PATH_DEAD_THRESHOLD,
        )

        tab = _make_mock_tab()
        tab.evaluate = AsyncMock(return_value=None)

        registry = _make_registry_with_browser(tab=tab)
        agent = _make_agent(noise_db=noise_db, session_registry=registry)

        dest   = make_destination()
        path   = make_path(id=42)
        config = NoiseConfig(world_id=1)

        with patch("adapters.browser.driver.human_click_at_rect", new=AsyncMock()), \
             patch("adapters.browser.driver.human_delay", new=AsyncMock()):
            asyncio.run(agent._execute_noise_action(dest, path, config))

        noise_db.mark_path_dead.assert_called_once_with(42)

    def test_UT_NP23_exito_resetea_contador(self):
        """UT-NP23: paso CLICK exitoso → reset_path_failures llamado."""
        noise_db = _make_noise_db_mock(bump_path_return=0, bump_dest_return=0)

        tab = _make_mock_tab()
        # Simular que evaluate devuelve un rect válido (CLICK exitoso)
        tab.evaluate = AsyncMock(return_value={"x": 10, "y": 20, "width": 100, "height": 30})

        registry = _make_registry_with_browser(tab=tab)
        agent = _make_agent(noise_db=noise_db, session_registry=registry)

        dest   = make_destination()
        path   = make_path(id=42, consecutive_failures_count=2)
        config = NoiseConfig(world_id=1, dwell_min_seconds=0.001, dwell_max_seconds=0.002)

        with patch("adapters.browser.driver.human_click_at_rect", new=AsyncMock()), \
             patch("adapters.browser.driver.human_delay", new=AsyncMock()):
            result = asyncio.run(agent._execute_noise_action(dest, path, config))

        assert result == "ok"
        noise_db.reset_path_failures.assert_called_once_with(42)

    def test_select_noise_action_excluye_rutas_is_dead(self):
        """CA-NP33: _select_noise_action no devuelve rutas con is_dead=True."""
        dead_path = NavigationPath(
            id=1, destination_id=1,
            origin=NavigationOrigin.ANY.value,
            label="Ruta muerta", is_active=True, is_dead=True,
        )
        dest = make_destination()

        noise_db = MagicMock()
        noise_db.pick_random_safe_destination = AsyncMock(return_value=dest)
        noise_db.list_paths = AsyncMock(return_value=[dead_path])

        agent = _make_agent(noise_db=noise_db)

        result = asyncio.run(agent._select_noise_action())
        # No hay paths compatibles (todos dead) → None tras 3 intentos
        assert result is None

    def test_select_noise_action_incluye_rutas_activas_no_dead(self):
        """_select_noise_action selecciona rutas activas no muertas."""
        active_path = NavigationPath(
            id=1, destination_id=1,
            origin=NavigationOrigin.ANY.value,
            label="Ruta activa", is_active=True, is_dead=False,
        )
        dest = make_destination()

        noise_db = MagicMock()
        noise_db.pick_random_safe_destination = AsyncMock(return_value=dest)
        noise_db.list_paths = AsyncMock(return_value=[active_path])

        agent = _make_agent(noise_db=noise_db)

        result = asyncio.run(agent._select_noise_action())
        assert result is not None
        _, path = result
        assert path.id == 1

    def test_url_verificacion_falla_genera_noise_step_error(self):
        """expected_url_after_click no coincide → NoiseStepError en _execute_noise_step."""
        noise_db = _make_noise_db_mock(bump_path_return=1, bump_dest_return=1)

        tab = _make_mock_tab(url="https://ts1.travian.es/dorf1.php")
        # evaluate devuelve rect válido para que el click proceda
        tab.evaluate = AsyncMock(return_value={"x": 10, "y": 20, "width": 100, "height": 30})

        registry = _make_registry_with_browser(tab=tab)
        agent = _make_agent(noise_db=noise_db, session_registry=registry)

        dest   = make_destination()
        step   = make_step(
            action=NoiseAction.CLICK,
            selector="a[href='/statistics']",
            expected_url="/statistics",  # La URL actual es /dorf1.php → no coincide
        )
        path   = make_path(steps=[step])
        config = NoiseConfig(world_id=1)

        with patch("adapters.browser.driver.human_click_at_rect", new=AsyncMock()), \
             patch("adapters.browser.driver.human_delay", new=AsyncMock()):
            result = asyncio.run(agent._execute_noise_action(dest, path, config))

        assert result == "error"
        noise_db.increment_path_failures.assert_called_once()

    def test_url_verificacion_exitosa_no_genera_error(self):
        """expected_url_after_click coincide → paso exitoso, no se incrementa contador."""
        noise_db = _make_noise_db_mock(bump_path_return=0, bump_dest_return=0)

        tab = _make_mock_tab(url="https://ts1.travian.es/statistics")
        tab.evaluate = AsyncMock(return_value={"x": 10, "y": 20, "width": 100, "height": 30})

        registry = _make_registry_with_browser(tab=tab)
        agent = _make_agent(noise_db=noise_db, session_registry=registry)

        dest   = make_destination()
        step   = make_step(
            action=NoiseAction.CLICK,
            selector="a[href='/statistics']",
            expected_url="/statistics",  # coincide con la URL actual
        )
        path   = make_path(steps=[step])
        config = NoiseConfig(world_id=1, dwell_min_seconds=0.001, dwell_max_seconds=0.002)

        with patch("adapters.browser.driver.human_click_at_rect", new=AsyncMock()), \
             patch("adapters.browser.driver.human_delay", new=AsyncMock()):
            result = asyncio.run(agent._execute_noise_action(dest, path, config))

        assert result == "ok"
        noise_db.increment_path_failures.assert_not_called()
        noise_db.reset_path_failures.assert_called_once()

    def test_noise_path_dead_threshold_es_3(self):
        """CA: NOISE_PATH_DEAD_THRESHOLD = 3 (constante del spec RN-NP07)."""
        assert NOISE_PATH_DEAD_THRESHOLD == 3
