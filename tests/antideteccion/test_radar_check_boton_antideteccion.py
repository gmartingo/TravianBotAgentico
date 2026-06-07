# Cubre Capa 4 — Comportamiento DOM, Capa 2 — Selectores, Capa 3 — Timing
"""
Tests de anti-deteccion del boton "Forzar deteccion (debug)" del radar de
ataques entrantes (spec docs/specs/radar-check-boton-sidebar.md §11/§15).

Propiedad central a proteger: el flujo del boton es un cambio anti-deteccion
POSITIVO — solo LEE el DOM ya cargado (tab.get_content via CDP) bajo el
_browser_lock, y NUNCA navega por URL ni simula clicks. El handler antiguo
construia un adapter ad-hoc y hacia browser.get(dorf1.php) sin lock; eso se
ELIMINO. Estos tests blindan que no vuelva a entrar navegacion en este camino.

Cadena del flujo:
  handler check_incoming_attacks (adapters/api/routes/incoming_attacks.py)
    -> WorldAgent.check_incoming_sidebar (core/scheduling/world_agent.py)
      -> _page_html_provider()  [solo tab.get_content(), composition root farm.py]
      -> check_sidebar_attacks (adapters/browser/incoming_attack_hook.py)
        -> IncomingAttackSidebarParser.parse  [BeautifulSoup puro]

Tests estaticos (AST/lectura) + dinamicos con mocks. NINGUNO abre Chrome ni red.
"""
from __future__ import annotations

import asyncio
import pathlib
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.scheduling.world_agent import WorldAgent

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
HANDLER = REPO_ROOT / "adapters" / "api" / "routes" / "incoming_attacks.py"
HOOK = REPO_ROOT / "adapters" / "browser" / "incoming_attack_hook.py"
SIDEBAR_PARSER = (
    REPO_ROOT / "adapters" / "browser" / "parsers" / "incoming_attack_sidebar_parser.py"
)
PROVIDER_ROOT = REPO_ROOT / "adapters" / "api" / "routes" / "farm.py"


def _code_lines(path: pathlib.Path) -> list[str]:
    """Lineas del fichero ignorando comentarios (#...) y docstrings simples.

    Devuelve las lineas de codigo "vivo" para grep estatico: descarta lineas
    que empiezan por # y el contenido entre comillas triples, para no marcar
    falsos positivos cuando la palabra aparece en documentacion.
    """
    raw = path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    in_doc = False
    doc_delim = ""
    for line in raw:
        stripped = line.strip()
        if in_doc:
            if doc_delim in line:
                in_doc = False
            continue
        # docstring de una sola linea o apertura de bloque
        for delim in ('"""', "'''"):
            if stripped.startswith(delim):
                rest = stripped[len(delim):]
                if delim not in rest:  # no cierra en la misma linea
                    in_doc = True
                    doc_delim = delim
                stripped = ""  # descartar la linea de apertura
                break
        if not stripped or stripped.startswith("#"):
            continue
        # quitar comentario inline
        code = line.split("#", 1)[0]
        out.append(code)
    return out


# ── Capa 4 — Sin navegacion nueva en el handler del boton ─────────────────────

def test_handler_check_no_navega_ni_construye_adapter_dorf1():
    """El handler reescrito NO debe contener navegacion ni el adapter ad-hoc.

    Prohibido en codigo vivo (no en comentarios/docstrings):
      browser.get(  /  .get_dorf1  /  Dorf1IncomingParser  /
      IncomingAttackBrowserAdapter  /  evaluate(  /  .click(
    """
    lines = _code_lines(HANDLER)
    prohibidos = [
        "browser.get(",
        ".get_dorf1",
        "Dorf1IncomingParser",
        "IncomingAttackBrowserAdapter",
        ".evaluate(",
        ".click(",
        ".get(dorf1",
    ]
    hits = [
        (n, t)
        for n, line in enumerate(lines, 1)
        for t in prohibidos
        if t in line
    ]
    assert hits == [], f"Navegacion/click prohibido reintroducido en el handler: {hits}"


def test_hook_sidebar_no_hace_peticiones_http():
    """check_sidebar_attacks es parseo puro: sin browser.get/tab.get/evaluate/requests."""
    lines = _code_lines(HOOK)
    prohibidos = ["browser.get", "tab.get", ".evaluate(", "import requests", "httpx", "aiohttp", "urllib"]
    hits = [(n, t) for n, line in enumerate(lines, 1) for t in prohibidos if t in line]
    assert hits == [], f"El hook del sidebar introdujo I/O de red prohibido: {hits}"


# ── Capa 2 — Selectores estructurales, nunca por texto visible ────────────────

def test_parser_sidebar_usa_selectores_estructurales_no_texto():
    """El parser del sidebar no debe filtrar por texto visible (multi-idioma)."""
    lines = _code_lines(SIDEBAR_PARSER)
    prohibidos = [
        ":has-text(",
        ":contains(",
        "contains(text()",
        "text()=",
        "By.LINK_TEXT",
        "By.PARTIAL_LINK_TEXT",
        "link_text=",
    ]
    hits = [(n, t) for n, line in enumerate(lines, 1) for t in prohibidos if t in line]
    assert hits == [], f"Selector por texto en el parser del sidebar: {hits}"
    # El discriminador estructural confirmado debe seguir presente.
    blob = SIDEBAR_PARSER.read_text(encoding="utf-8")
    assert "div.listEntry.village.attack" in blob


# ── Capa 4 — check_incoming_sidebar: solo lee, no navega, bajo lock ───────────

def test_check_incoming_sidebar_solo_lee_dom_nunca_navega():
    """El metodo del boton solo invoca el provider de lectura; nunca navega.

    Mockea browser/db; verifica que:
      - El provider de HTML (lectura DOM) se invoca exactamente 1 vez.
      - El metodo retiene _browser_lock mientras lo invoca (serializa con el
        radar autonomo y execute_path_test).
      - NUNCA se invoca browser.get / tab.get(url) sobre el browser real.
    """
    async def _run():
        browser = MagicMock()
        # Cualquier intento de navegar con el browser real debe explotar el test.
        browser.get = AsyncMock(side_effect=AssertionError("browser.get() PROHIBIDO en el flujo del boton"))
        main_tab = MagicMock()
        main_tab.get = AsyncMock(side_effect=AssertionError("tab.get(url) PROHIBIDO en el flujo del boton"))
        main_tab.get_content = AsyncMock(return_value="<html><div id='sidebarBoxVillageList'></div></html>")
        browser.main_tab = main_tab

        # Provider de lectura: replica el composition root (solo get_content).
        provider_calls = {"n": 0, "lock_held": None}

        agent = WorldAgent(
            world_id=1,
            browser=browser,
            db=AsyncMock(),
            incoming_db=MagicMock(),
            sidebar_attack_hook=AsyncMock(return_value=[object(), object()]),  # 2 ataques
        )

        async def _provider():
            provider_calls["n"] += 1
            # El lock DEBE estar retenido cuando se lee el DOM (RN-B03).
            provider_calls["lock_held"] = agent._browser_lock.locked()
            return await agent._browser.main_tab.get_content()

        agent._page_html_provider = _provider

        result = await agent.check_incoming_sidebar()

        assert result == 2
        assert provider_calls["n"] == 1, "el provider de lectura debe llamarse exactamente 1 vez"
        assert provider_calls["lock_held"] is True, "la lectura del DOM debe ocurrir bajo _browser_lock"
        browser.get.assert_not_called()
        main_tab.get.assert_not_called()
        # get_content (lectura CDP pura) SI debe haberse usado.
        main_tab.get_content.assert_awaited_once()

    asyncio.run(_run())


def test_provider_del_composition_root_solo_usa_get_content():
    """El _page_html_provider del composition root (farm.py) solo lee el DOM.

    Estatico: dentro del cuerpo de la funcion interna _page_html_provider no
    debe aparecer .get( de navegacion; solo get_content() y get_browser().
    """
    blob = PROVIDER_ROOT.read_text(encoding="utf-8")
    assert "async def _page_html_provider(" in blob, "no se encontro el provider en farm.py"
    # Aislar el cuerpo del provider (hasta la asignacion page_html_provider = _page_html_provider).
    start = blob.index("async def _page_html_provider(")
    end = blob.index("page_html_provider = _page_html_provider", start)
    body = blob[start:end]
    assert "tab.get_content()" in body, "el provider debe leer con tab.get_content()"
    # Ninguna navegacion por URL dentro del provider.
    for prohibido in ("tab.get(", "browser.get(", ".evaluate("):
        assert prohibido not in body, f"navegacion/click prohibido en el provider: {prohibido}"
