"""
Integración end-to-end de execute_path_test (EP-N14) conduciendo el CÓDIGO REAL
del browser — NO se mockea _execute_noise_step ni human_click_at_rect.

Reproduce la forma EXACTA de la ruta 2 que falla en producción del usuario:
    origin = "STATISTICS"  (navega al ancla /statistics)
    paso 0 = CLICK sobre "a[href='/statistics/player/overview']"

Se usa un FakeTab/FakeBrowser que:
  - responde a tab.evaluate(...) con window.innerWidth/Height y el rect del
    elemento (getBoundingClientRect) como lo haría Chrome,
  - stubea tab.send(...) (los eventos CDP de ratón) como no-op,
  - registra browser.get(url) para verificar la navegación al ancla.

Así pasa por _execute_noise_step REAL → human_click_at_rect REAL → bezier +
mouse dispatch REAL (con send stubeado). Si algo de esa cadena lanzara una
excepción no controlada (el bug del 500), el test la captaría.

NINGÚN test abre Chrome real ni hace red.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from core.entities.noise import (
    NavigationOrigin,
    NavigationPath,
    NavigationStep,
    NoiseAction,
)
from core.scheduling.world_agent import WorldAgent

SERVER = "ts1.travian.es"
ANCHOR_URL = "https://ts1.travian.es/statistics"  # build_url(SERVER, "/statistics") tras prefijar esquema


# ---------------------------------------------------------------------------
# Fake browser/tab que imita lo justo de zendriver para el camino real
# ---------------------------------------------------------------------------

class FakeTab:
    def __init__(self, rect: dict | None):
        # rect que devolverá el JS de getBoundingClientRect; None = elemento no encontrado
        self._rect = rect
        self.url = f"https://{SERVER}/dorf1.php"
        self.sent: list = []  # eventos CDP de ratón

    async def evaluate(self, js: str):
        if "innerWidth" in js:
            return 1280
        if "innerHeight" in js:
            return 800
        # JS de CLICK/HOVER: querySelector + getBoundingClientRect → rect o null
        if "getBoundingClientRect" in js:
            return self._rect
        # JS de SCROLL_TO: querySelector + scrollIntoView → bool
        if "scrollIntoView" in js:
            return self._rect is not None
        return None

    async def send(self, *args, **kwargs):
        # Eventos CDP de ratón (mouse move/down/up). No-op pero registrado.
        self.sent.append((args, kwargs))
        return None


class FakeBrowser:
    def __init__(self, tab: FakeTab):
        self.main_tab = tab
        self.gets: list[str] = []

    async def get(self, url: str):
        self.gets.append(url)
        # Simular que la navegación cambia la URL del tab.
        self.main_tab.url = url
        return None


def _make_registry(browser: FakeBrowser):
    registry = MagicMock()
    registry.get_browser = MagicMock(return_value=browser)
    registry.get_world_server = MagicMock(return_value=SERVER)
    registry.has_active_session = MagicMock(return_value=True)
    return registry


def _make_agent(browser: FakeBrowser) -> WorldAgent:
    return WorldAgent(
        world_id=2,
        browser=MagicMock(),
        db=MagicMock(),
        session_registry=_make_registry(browser),
        noise_db=MagicMock(),
    )


def _make_path_statistics() -> NavigationPath:
    """Forma exacta de la ruta 2 del usuario."""
    step = NavigationStep(
        id=1,
        path_id=2,
        step_order=0,
        action=NoiseAction.CLICK,
        selector="a[href='/statistics/player/overview']",
        value="",
        delay_min_ms=500,
        delay_max_ms=900,
        expected_url_after_click=None,
    )
    return NavigationPath(
        id=2,
        destination_id=3,
        origin="STATISTICS",
        label="Ranking habitantes desde estadisticas",
        is_active=True,
        is_dead=False,
        steps=[step],
    )


# ---------------------------------------------------------------------------
# Caso feliz: rect válido → click real → overall "ok", sin 500
# ---------------------------------------------------------------------------

def test_ruta2_statistics_click_ok_extremo_a_extremo():
    """
    La ruta 2 con un elemento clicable normal debe completarse con overall="ok",
    navegando primero al ancla /statistics y luego haciendo el click real
    (human_click_at_rect) sobre el enlace. Esto es lo que el usuario debería
    obtener al pulsar 'Probar ruta' con la sesión conectada.
    """
    tab = FakeTab(rect={"x": 100.0, "y": 200.0, "width": 120.0, "height": 30.0})
    browser = FakeBrowser(tab)
    agent = _make_agent(browser)

    report = asyncio.run(agent.execute_path_test(_make_path_statistics()))

    assert report.overall == "ok", report
    # Navegó al ancla de STATISTICS
    assert report.anchor_navigated_to is not None
    assert report.anchor_navigated_to.endswith("/statistics")
    assert browser.gets and browser.gets[0].endswith("/statistics")
    # El paso de click se reportó ok
    assert len(report.steps) == 1
    assert report.steps[0].status == "ok"
    assert report.steps[0].action == "CLICK"
    # human_click_at_rect REAL emitió eventos CDP de ratón (move/down/up)
    assert len(tab.sent) >= 3, "no se dispararon eventos CDP de ratón (click no real)"
    # El lock quedó libre
    assert not agent._browser_lock.locked()


# ---------------------------------------------------------------------------
# Elemento no encontrado: querySelector → null → paso "error", NO 500
# ---------------------------------------------------------------------------

def test_ruta2_elemento_no_encontrado_es_paso_error_no_500():
    """
    Si el selector no existe en el DOM (rect = null), _execute_noise_step lanza
    NoiseStepError 'elemento no encontrado' → se reporta como paso error con
    overall='error'. NUNCA debe propagar excepción (que sería un 500).
    """
    tab = FakeTab(rect=None)  # querySelector devuelve null
    browser = FakeBrowser(tab)
    agent = _make_agent(browser)

    report = asyncio.run(agent.execute_path_test(_make_path_statistics()))

    assert report.overall == "error"
    assert report.aborted_at_step == 0
    assert len(report.steps) == 1
    assert report.steps[0].status == "error"
    assert "no encontrado" in report.steps[0].reason.lower()
    assert not agent._browser_lock.locked()


# ---------------------------------------------------------------------------
# Elemento presente pero no clicable (rect 0×0) → ElementNotClickableError
# capturada como paso "error", NO 500  (el bug original)
# ---------------------------------------------------------------------------

def test_ruta2_elemento_no_clicable_rect_cero_es_paso_error_no_500():
    """
    Regresión del 500 original: el elemento existe pero tiene width/height 0
    (p.ej. display:none). human_click_at_rect REAL lanza ElementNotClickableError
    (subclase de BrowserError, NO NoiseStepError). Antes burbujeaba → 500.
    Ahora debe degradarse a paso 'error' con overall='error'.
    """
    tab = FakeTab(rect={"x": 100.0, "y": 200.0, "width": 0.0, "height": 0.0})
    browser = FakeBrowser(tab)
    agent = _make_agent(browser)

    report = asyncio.run(agent.execute_path_test(_make_path_statistics()))

    assert report.overall == "error"
    assert report.aborted_at_step == 0
    assert len(report.steps) == 1
    assert report.steps[0].status == "error"
    assert report.steps[0].reason  # algún motivo legible
    assert not agent._browser_lock.locked()
