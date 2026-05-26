# Cubre Capa 2 — Selectores | Capa 3 — Timing humano | Capa 4 — Comportamiento DOM (anti-rafaga)
"""
Tests anti-deteccion del LiveOverviewAdapter (adapters/browser/live_overview_adapter.py).

El LiveOverviewAdapter navega Travian (/village/statistics/<tab>) con el Chrome
autenticado. Es codigo que toca la interaccion con la web de Travian, por lo que
debe respetar las capas de anti-deteccion. Estos tests fijan esas garantias para
que un cambio futuro no las elimine en silencio.

Ninguno abre Chrome real: son estaticos (ast/regex sobre el fuente) o usan mocks
asincronos del browser. El adaptador recibe el browser por callables inyectados,
asi que mockearlo es trivial.

Cobertura:
  - Capa 2: el adaptador no usa selectores por texto; el selector de carga es
    estructural (#content).
  - Capa 3: la ruta de navegacion llama a human_delay() (timing humano) y NO usa
    sleeps con valor constante.
  - Capa 4 (anti-rafaga): la cache TTL evita golpear Travian en cada peticion;
    dos peticiones simultaneas en cache miss producen UNA sola navegacion; y
    cada navegacion lleva su propio human_delay (no se encadenan get() sin pausa).
"""
import ast
import asyncio
import pathlib
import re
import unittest.mock as mock

import pytest

# tests/antideteccion/<este>.py -> parents[2] = raiz del repo (portable).
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
ADAPTER_PATH = REPO_ROOT / "adapters" / "browser" / "live_overview_adapter.py"
PARSER_PATH = REPO_ROOT / "core" / "use_cases" / "village_map.py"


# ---------------------------------------------------------------------------
# Helpers de mock del browser zendriver (sin Chrome real)
# ---------------------------------------------------------------------------

class _FakeTab:
    """Tab falso: wait_for no falla y get_content devuelve HTML no vacio."""

    def __init__(self, html: str = "<html><body>#content ok</body></html>"):
        self._html = html
        self.waited_selectors: list[str] = []

    async def wait_for(self, selector, timeout=None):
        self.waited_selectors.append(selector)
        return None

    async def get_content(self):
        return self._html


class _FakeBrowser:
    """Browser falso que cuenta cuantas veces se navega (browser.get)."""

    def __init__(self, tab: _FakeTab):
        self._tab = tab
        self.get_calls: list[str] = []

    async def get(self, url):
        self.get_calls.append(url)
        return self._tab


def _make_adapter(browser):
    """Construye un LiveOverviewAdapter cableado a un browser mock."""
    from adapters.browser.live_overview_adapter import LiveOverviewAdapter

    return LiveOverviewAdapter(
        get_browser=lambda wid: browser,
        get_world_server=lambda wid: "https://ts20.x2.america.travian.com/",
    )


# ---------------------------------------------------------------------------
# Capa 3 — Timing humano: la ruta de navegacion DEBE llamar a human_delay
# ---------------------------------------------------------------------------

def test_navegacion_llama_human_delay_con_rango_humano():
    """
    Cubre Capa 3 — Timing humano.
    _navigate_and_get debe llamar a human_delay() tras navegar, con el rango
    humano (500, 900) ms. Si alguien borra esa llamada, el bot navegaria sin
    pausa de percepcion humana -> detectable.
    """
    from adapters.browser import live_overview_adapter as mod
    from core.ports.overview_html_source_port import OverviewPage

    tab = _FakeTab()
    browser = _FakeBrowser(tab)
    adapter = _make_adapter(browser)

    llamadas_delay = []

    async def fake_human_delay(min_ms=500, max_ms=900):
        llamadas_delay.append((min_ms, max_ms))
        # no dormimos de verdad — el rango ya esta validado en test_config_zendriver

    with mock.patch.object(mod, "human_delay", side_effect=fake_human_delay):
        asyncio.run(adapter.get_page_html(world_id=1, page=OverviewPage.OVERVIEW))

    assert llamadas_delay, (
        "BLOQUEANTE Capa 3: la navegacion no llamo a human_delay(). "
        "Toda navegacion a Travian debe llevar una pausa humana tras browser.get()."
    )
    assert (500, 900) in llamadas_delay, (
        f"BLOQUEANTE Capa 3: human_delay() se llamo con un rango distinto al "
        f"humano (500, 900) ms. Llamadas: {llamadas_delay}"
    )


def test_no_hay_sleep_con_valor_constante_en_el_adaptador():
    """
    Cubre Capa 3 — Timing humano.
    El adaptador no debe contener time.sleep(<fijo>) ni asyncio.sleep(<fijo>):
    el timing debe delegarse al helper human_delay (aleatorio).
    Excepcion: lineas con comentario '# anti-deteccion-ok: <razon>'.
    """
    lines = ADAPTER_PATH.read_text(encoding="utf-8").splitlines()
    patron_sleep_fijo = re.compile(r'(time|asyncio)\.sleep\s*\(\s*\d+\.?\d*\s*\)')

    violaciones = []
    for lineno, line in enumerate(lines, start=1):
        if patron_sleep_fijo.search(line):
            prev = lines[lineno - 2] if lineno >= 2 else ""
            if "# anti-deteccion-ok:" not in prev:
                violaciones.append(f"{ADAPTER_PATH.name}:{lineno} — {line.strip()}")

    assert not violaciones, (
        "BLOQUEANTE Capa 3: sleep con valor constante en live_overview_adapter.py. "
        "Usar human_delay(). Violaciones:\n" + "\n".join(violaciones)
    )


# ---------------------------------------------------------------------------
# Capa 2 — Selectores: el selector de carga es estructural, no por texto
# ---------------------------------------------------------------------------

def test_selector_de_carga_es_estructural():
    """
    Cubre Capa 2 — Selectores.
    El selector que indica 'pagina cargada' debe ser estructural (id/clase/
    atributo), nunca por texto visible. El spec fija '#content' (id), presente
    en todas las pestañas de /village/statistics e independiente del idioma.
    """
    from adapters.browser import live_overview_adapter as mod

    selector = mod.OVERVIEW_LOADED_SELECTOR
    assert selector.startswith(("#", ".", "[")) or selector.isidentifier(), (
        f"BLOQUEANTE Capa 2: OVERVIEW_LOADED_SELECTOR='{selector}' no parece "
        "estructural. Debe ser id (#...), clase (....) o atributo ([...])."
    )
    # No debe contener pseudo-selectores por texto.
    for prohibido in (":has-text(", ":contains(", "text()"):
        assert prohibido not in selector, (
            f"BLOQUEANTE Capa 2: el selector de carga usa '{prohibido}' (por texto)."
        )


def test_urls_de_paginas_son_estructurales_no_localizadas():
    """
    Cubre Capa 2 — Selectores / navegacion idioma-independiente.
    Las rutas de cada OverviewPage deben ser paths estables de Travian
    (/village/statistics/...), nunca texto de pestaña traducible.
    """
    from adapters.browser import live_overview_adapter as mod
    from core.ports.overview_html_source_port import OverviewPage

    # Todas las paginas del enum deben tener ruta declarada.
    for page in OverviewPage:
        assert page in mod._PAGE_PATHS, (
            f"BLOQUEANTE: OverviewPage.{page.name} no tiene ruta en _PAGE_PATHS. "
            "Una pagina sin ruta forzaria a improvisar la navegacion."
        )
        ruta = mod._PAGE_PATHS[page]
        assert ruta.startswith("village/statistics/"), (
            f"BLOQUEANTE Capa 2: la ruta de {page.name} ('{ruta}') no es un path "
            "estructural de /village/statistics. No usar texto de pestaña."
        )


# ---------------------------------------------------------------------------
# Capa 2 — Selectores: el parser de aldeas (RN-05) usa solo selectores
# estructurales, nunca texto visible. Vive en core/, fuera del barrido de
# adapters/browser/, por eso se cubre aqui explicitamente.
# ---------------------------------------------------------------------------

def test_parser_aldeas_sin_selectores_por_texto():
    """
    Cubre Capa 2 — Selectores (RN-05).
    VillageOverviewParser (core/use_cases/village_map.py) parsea el HTML de
    Travian, que es multilenguaje. Ningun selector puede depender de texto
    visible: ni pseudo-selectores CSS, ni filtrado por .text en Python.
    """
    lines = PARSER_PATH.read_text(encoding="utf-8").splitlines()
    patrones_prohibidos = [
        ":has-text(",
        ":contains(",
        "contains(text()",
        "text()=",
        "find_element_by_link_text",
        "By.LINK_TEXT",
        "By.PARTIAL_LINK_TEXT",
        # filtrado por texto visible en Python (string=, text=) propio de bs4
        "string=",
        ", text=",
    ]
    # Comparaciones por texto visible: .text == "..." / get_text() == "..."
    patron_text_compare = re.compile(r'(\.text|get_text\([^)]*\))\s*(==|!=|\.startswith|\.endswith|\bin\b)')

    violaciones = []
    for lineno, line in enumerate(lines, start=1):
        for patron in patrones_prohibidos:
            if patron in line:
                violaciones.append(f"{PARSER_PATH.name}:{lineno} — '{patron}' — {line.strip()}")
        if patron_text_compare.search(line):
            violaciones.append(
                f"{PARSER_PATH.name}:{lineno} — comparacion por texto visible — {line.strip()}"
            )

    assert not violaciones, (
        "BLOQUEANTE Capa 2 (RN-05): el parser de aldeas usa seleccion/filtrado "
        "por texto visible. Travian es multilenguaje; usar solo atributos, clases, "
        "ids o el parametro newdid del href.\n" + "\n".join(violaciones)
    )


# ---------------------------------------------------------------------------
# Capa 4 — Anti-rafaga: la cache evita golpear Travian repetidamente
# ---------------------------------------------------------------------------

def test_cache_hit_no_navega_segunda_vez():
    """
    Cubre Capa 4 — Comportamiento DOM (anti-rafaga).
    Dos peticiones identicas dentro del TTL deben producir UNA sola navegacion.
    Sin cache, un consumidor que refresca el estado golpearia Travian en cada
    request -> patron robotico.
    """
    from adapters.browser import live_overview_adapter as mod
    from core.ports.overview_html_source_port import OverviewPage

    tab = _FakeTab()
    browser = _FakeBrowser(tab)
    adapter = _make_adapter(browser)

    async def fake_human_delay(min_ms=500, max_ms=900):
        return None

    async def run():
        await adapter.get_page_html(world_id=1, page=OverviewPage.OVERVIEW)
        await adapter.get_page_html(world_id=1, page=OverviewPage.OVERVIEW)

    with mock.patch.object(mod, "human_delay", side_effect=fake_human_delay):
        asyncio.run(run())

    assert len(browser.get_calls) == 1, (
        f"BLOQUEANTE Capa 4: la cache no evito la segunda navegacion. "
        f"browser.get() se llamo {len(browser.get_calls)} veces (esperado 1)."
    )


def test_concurrencia_cache_miss_navega_una_sola_vez():
    """
    Cubre Capa 4 — Comportamiento DOM (anti-rafaga) / EC-05.
    Dos coroutines piden la misma pagina simultaneamente con cache vacia.
    El lock por clave debe garantizar UNA sola navegacion (la segunda espera y
    reutiliza el HTML). Sin esto, una concurrencia disparararia dos cargas
    identicas casi simultaneas -> patron anomalo (rafaga).
    """
    from adapters.browser import live_overview_adapter as mod
    from core.ports.overview_html_source_port import OverviewPage

    tab = _FakeTab()
    browser = _FakeBrowser(tab)
    adapter = _make_adapter(browser)

    async def fake_human_delay(min_ms=500, max_ms=900):
        # cede el control para forzar el solapamiento de las dos coroutines
        await asyncio.sleep(0)

    async def run():
        await asyncio.gather(
            adapter.get_page_html(world_id=1, page=OverviewPage.OVERVIEW),
            adapter.get_page_html(world_id=1, page=OverviewPage.OVERVIEW),
        )

    with mock.patch.object(mod, "human_delay", side_effect=fake_human_delay):
        asyncio.run(run())

    assert len(browser.get_calls) == 1, (
        f"BLOQUEANTE Capa 4: cache miss concurrente produjo "
        f"{len(browser.get_calls)} navegaciones (esperado 1). "
        "El lock por clave no esta protegiendo contra navegaciones duplicadas."
    )


def test_cada_navegacion_lleva_su_propia_pausa_humana():
    """
    Cubre Capa 3 + Capa 4 — encadenar varias paginas sin pausa es detectable.
    Navegar las 3 pestañas distintas (cache miss en cada una) debe producir
    una llamada a human_delay POR navegacion: nunca 'get -> get -> get' seguidos.
    """
    from adapters.browser import live_overview_adapter as mod
    from core.ports.overview_html_source_port import OverviewPage

    tab = _FakeTab()
    browser = _FakeBrowser(tab)
    adapter = _make_adapter(browser)

    delays = []

    async def fake_human_delay(min_ms=500, max_ms=900):
        delays.append(1)

    paginas = [
        OverviewPage.OVERVIEW,
        OverviewPage.RESOURCES,
        OverviewPage.CULTURE_POINTS,
    ]

    async def run():
        for p in paginas:
            await adapter.get_page_html(world_id=1, page=p)

    with mock.patch.object(mod, "human_delay", side_effect=fake_human_delay):
        asyncio.run(run())

    assert len(browser.get_calls) == len(paginas), (
        f"Se esperaban {len(paginas)} navegaciones, hubo {len(browser.get_calls)}."
    )
    assert len(delays) == len(browser.get_calls), (
        f"BLOQUEANTE Capa 3/4: hubo {len(browser.get_calls)} navegaciones pero "
        f"solo {len(delays)} pausas humanas. Cada browser.get() debe ir seguido "
        "de un human_delay() — no encadenar navegaciones sin pausa."
    )


# ---------------------------------------------------------------------------
# Capa 1/4 — el adaptador NO reinventa la capa de browser ni abre Chrome propio
# ---------------------------------------------------------------------------

def test_adaptador_no_crea_su_propio_browser_ni_config():
    """
    Cubre Capa 1 — Configuracion de Chrome.
    El LiveOverviewAdapter debe REUSAR el browser inyectado, nunca construir su
    propio zd.Config / zd.start (eso duplicaria flags y podria divergir de las
    capas anti-deteccion centralizadas en driver.create_browser).
    """
    source = ADAPTER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    llamadas_prohibidas = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # zd.start(...) / zendriver.start(...) / zd.Config(...)
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in ("start", "Config"):
                val = func.value
                if isinstance(val, ast.Name) and val.id in ("zd", "zendriver"):
                    llamadas_prohibidas.append(f"{val.id}.{func.attr}(...)")

    assert not llamadas_prohibidas, (
        "BLOQUEANTE Capa 1: el LiveOverviewAdapter construye su propio browser "
        f"({llamadas_prohibidas}). Debe reusar el browser inyectado por callable, "
        "no crear uno con flags propios."
    )


def test_adaptador_no_importa_zendriver():
    """
    Cubre Capa 1 / arquitectura — el adaptador trabaja con el browser inyectado
    como objeto opaco; no necesita importar zendriver. Importarlo seria sintoma
    de que esta a punto de configurar Chrome por su cuenta.
    """
    source = ADAPTER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("zendriver"), (
                    "BLOQUEANTE Capa 1: live_overview_adapter.py importa zendriver. "
                    "El adaptador debe usar el browser inyectado, no tocar zendriver."
                )
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("zendriver"):
            pytest.fail(
                "BLOQUEANTE Capa 1: live_overview_adapter.py importa de zendriver. "
                "El adaptador debe usar el browser inyectado, no tocar zendriver."
            )
