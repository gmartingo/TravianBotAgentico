# Cubre Capa 2 — Selectores, Capa 3 — Timing humano, Capa 4 — Comportamiento DOM
"""
Tests de anti-deteccion del Noise Path Wizard (spec noise-path-wizard.md).

Auditoria del guardian sobre las piezas que tocan el DOM / la interaccion con
Travian:
  - adapters/browser/village_switcher.py  (lectura del village-switcher)
  - core/scheduling/world_agent.py         (_execute_noise_step / _execute_noise_action)
  - core/use_cases/derive_selector.py      (derivacion de selectores)
  - core/entities/noise.py                 (invariante de timing del step)

Todos los tests son estaticos (AST / lectura de fichero) o con entidades puras.
NINGUNO abre Chrome real ni hace red.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
VILLAGE_SWITCHER = REPO_ROOT / "adapters" / "browser" / "village_switcher.py"
WORLD_AGENT = REPO_ROOT / "core" / "scheduling" / "world_agent.py"
DERIVE_SELECTOR = REPO_ROOT / "core" / "use_cases" / "derive_selector.py"

# Tokens prohibidos de seleccion por texto visible (Capa 2 — multi-idioma).
SELECTORES_POR_TEXTO_PROHIBIDOS = (
    "By.LINK_TEXT",
    "By.PARTIAL_LINK_TEXT",
    "link_text=",
    "partial_link_text=",
    ":has-text(",
    ":contains(",
    "contains(text(",
    "text()=",
)


# ---------------------------------------------------------------------------
# Capa 2 — Selectores estructurales en village_switcher
# ---------------------------------------------------------------------------

def test_village_switcher_no_usa_selectores_por_texto():
    """
    Cubre Capa 2 — village_switcher.py no debe seleccionar por texto visible.
    Travian es multi-idioma: el texto cambia, los selectores estructurales no.
    """
    src = VILLAGE_SWITCHER.read_text(encoding="utf-8")
    for token in SELECTORES_POR_TEXTO_PROHIBIDOS:
        assert token not in src, (
            f"village_switcher.py contiene un selector por texto prohibido: {token!r}"
        )


def test_village_switcher_usa_selector_estructural_data_did():
    """
    Cubre Capa 2 — el parser debe usar el selector estructural verificado
    span.name[data-did] (mismo que farm_lists.py:146), no texto visible.
    """
    src = VILLAGE_SWITCHER.read_text(encoding="utf-8")
    assert "span.name[data-did]" in src, (
        "village_switcher.py debe usar el selector estructural 'span.name[data-did]', "
        "el mismo ya verificado en farm_lists.py"
    )


def test_village_switcher_selector_consistente_con_farm_lists():
    """
    Cubre Capa 2 — el selector del village-switcher debe coincidir EXACTAMENTE
    con el ya verificado en farm_lists.py, evitando dos fuentes de verdad.
    """
    farm_lists = (REPO_ROOT / "adapters" / "browser" / "farm_lists.py").read_text(
        encoding="utf-8"
    )
    vs = VILLAGE_SWITCHER.read_text(encoding="utf-8")
    assert "span.name[data-did]" in farm_lists, (
        "farm_lists.py ya no usa span.name[data-did]: revisar la referencia del guardian"
    )
    assert "span.name[data-did]" in vs


# ---------------------------------------------------------------------------
# Capa 4 — Comportamiento DOM: lectura pura, sin efectos observables
# ---------------------------------------------------------------------------

def test_village_switcher_es_solo_lectura_sin_click_ni_navegacion():
    """
    Cubre Capa 4 — el parser solo lee el DOM (tab.evaluate). No debe contener
    clicks, navegacion (page.get / tab.get) ni scroll: el listado ya esta en la
    pagina, no debe generar peticiones extra a Travian.
    """
    src = VILLAGE_SWITCHER.read_text(encoding="utf-8")
    prohibidos = (".click(", "human_click", "page.get(", "tab.get(",
                  "scrollIntoView", "scrollTo(", "scroll(")
    for token in prohibidos:
        assert token not in src, (
            f"village_switcher.py debe ser solo-lectura; encontrado {token!r}"
        )


def test_village_switcher_js_no_modifica_fingerprint():
    """
    Cubre Capa 4 — el JS inyectado no debe tocar navigator / window.chrome /
    localStorage (patrones automatizables / modificacion de fingerprint).
    """
    src = VILLAGE_SWITCHER.read_text(encoding="utf-8")
    prohibidos = ("navigator.", "window.chrome", "localStorage", "sessionStorage")
    for token in prohibidos:
        assert token not in src, (
            f"village_switcher.py inyecta JS que toca {token!r} (fingerprint)"
        )


# ---------------------------------------------------------------------------
# Capa 4 + human-click — clicks de ruido NUNCA con element.click() / .click() JS
# ---------------------------------------------------------------------------

def _click_strings_en_archivo(path: pathlib.Path) -> list[str]:
    """Devuelve literales de string que contienen '.click()' (sospechosos de
    click sintetico JS), excluyendo human_click* que es el helper legitimo."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    encontrados: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if ".click()" in node.value:
                encontrados.append(node.value)
    return encontrados


def test_world_agent_noise_no_usa_click_sintetico_js():
    """
    Cubre human-click — los pasos de ruido no deben hacer '.click()' inyectado
    en JS (firma trivial). Los clicks van por human_click_at_rect (CDP real).
    """
    encontrados = _click_strings_en_archivo(WORLD_AGENT)
    assert not encontrados, (
        "world_agent.py contiene strings JS con '.click()': "
        f"{encontrados}. Usar human_click_at_rect en su lugar."
    )


def test_world_agent_noise_usa_human_click_at_rect():
    """
    Cubre human-click — la accion CLICK del ruido debe ejecutarse con
    human_click_at_rect (Bezier + gaussiana + mousedown/up separados).
    """
    src = WORLD_AGENT.read_text(encoding="utf-8")
    assert "human_click_at_rect(" in src, (
        "_execute_noise_step debe usar human_click_at_rect para los CLICK de ruido"
    )


def test_world_agent_noise_hover_usa_human_drift():
    """
    Cubre human-click — el HOVER del ruido debe usar human_drift_toward,
    no un mouse-move instantaneo.
    """
    src = WORLD_AGENT.read_text(encoding="utf-8")
    assert "human_drift_toward(" in src


# ---------------------------------------------------------------------------
# Capa 4 — verificacion de URL tras CLICK con espera de carga humanizada
# ---------------------------------------------------------------------------

def test_verificacion_url_tras_click_espera_carga_humana():
    """
    Cubre Capa 4 — tras un CLICK con expected_url_after_click, NO se debe leer
    tab.url en el mismo instante: debe haber una espera de carga humanizada
    (human_delay) antes de la lectura, o se producen falsos negativos que
    marcan rutas como muertas y el timing es robotico.

    Verificacion AST: en el cuerpo del bloque que comprueba
    step.expected_url_after_click debe aparecer una llamada a human_delay
    ANTES del acceso a tab.url.
    """
    tree = ast.parse(WORLD_AGENT.read_text(encoding="utf-8"))

    # Localizar el 'if step.expected_url_after_click:'
    objetivo = None
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = node.test
            if (
                isinstance(test, ast.Attribute)
                and test.attr == "expected_url_after_click"
            ):
                objetivo = node
                break

    assert objetivo is not None, (
        "No se encontro el bloque 'if step.expected_url_after_click:' en world_agent.py"
    )

    # Recorrer el cuerpo: human_delay debe aparecer antes que el acceso a .url
    src_bloque = ast.dump(objetivo)
    assert "human_delay" in src_bloque, (
        "BLOQUEANTE: la verificacion de URL tras CLICK no espera carga humana "
        "(falta human_delay antes de leer tab.url)"
    )

    # Confirmar orden: indice de aparicion de 'human_delay' < indice de '.url'
    # sobre el codigo fuente del bloque concreto.
    inicio = objetivo.body[0].lineno
    fin = objetivo.body[-1].end_lineno
    lineas = WORLD_AGENT.read_text(encoding="utf-8").splitlines()[inicio - 1:fin]
    bloque = "\n".join(lineas)
    idx_delay = bloque.find("human_delay")
    idx_url = bloque.find(".url")
    assert idx_delay != -1 and idx_url != -1
    assert idx_delay < idx_url, (
        "BLOQUEANTE: human_delay debe llamarse ANTES de leer tab.url tras el click"
    )


# ---------------------------------------------------------------------------
# Capa 3 — Timing humano: invariante del NavigationStep
# ---------------------------------------------------------------------------

def _make_step(delay_min, delay_max):
    from core.entities.noise import NavigationStep, NoiseAction
    return NavigationStep(
        id=None, path_id=None, step_order=0,
        action=NoiseAction.CLICK, selector="a[href*='karte']",
        delay_min_ms=delay_min, delay_max_ms=delay_max,
    )


def test_noise_step_rechaza_delay_instantaneo():
    """
    Cubre Capa 3 — un step con delay 0 (encadenamiento instantaneo de
    interacciones sobre Travian) debe ser rechazado por la entidad.
    """
    with pytest.raises(ValueError, match="anti-detección|>="):
        _make_step(0, 0)


def test_noise_step_rechaza_delay_por_debajo_del_piso():
    """Cubre Capa 3 — delay por debajo del umbral de reaccion humana se rechaza."""
    from core.entities.noise import NavigationStep
    floor = NavigationStep.NOISE_STEP_DELAY_FLOOR_MS
    with pytest.raises(ValueError):
        _make_step(floor - 1, floor + 100)


def test_noise_step_rechaza_delay_excesivo():
    """Cubre Capa 3 — delay por encima del techo ('lento por miedo') se rechaza."""
    from core.entities.noise import NavigationStep
    ceiling = NavigationStep.NOISE_STEP_DELAY_CEILING_MS
    with pytest.raises(ValueError):
        _make_step(500, ceiling + 1)


def test_noise_step_acepta_defaults_humanos():
    """Cubre Capa 3 — los defaults 500-900 ms (rango humano) son validos."""
    step = _make_step(500, 900)
    assert step.delay_min_ms == 500
    assert step.delay_max_ms == 900


def test_noise_step_delay_es_rango_no_constante_en_runtime():
    """
    Cubre Capa 3 — el runtime usa human_delay(min, max), que muestrea
    random.uniform: el delay NO es constante mientras min != max.
    Verificacion estatica de que el step se ejecuta via human_delay(step...).
    """
    src = WORLD_AGENT.read_text(encoding="utf-8")
    assert "human_delay(step.delay_min_ms, step.delay_max_ms)" in src, (
        "El delay entre pasos de ruido debe ejecutarse via human_delay(min,max), "
        "no con un sleep fijo"
    )


def test_noise_dwell_es_aleatorio():
    """Cubre Capa 3 — el dwell final tras el destino usa random.uniform, no fijo."""
    src = WORLD_AGENT.read_text(encoding="utf-8")
    assert "random.uniform(config.dwell_min_seconds, config.dwell_max_seconds)" in src


# ---------------------------------------------------------------------------
# Capa 2 — derive_selector nunca produce selectores por texto
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "outer_html",
    [
        '<a href="/karte.php">Mapa</a>',
        '<a href="/dorf2.php?gid=2">Construir</a>',
        '<span class="villageName">Aldea 1</span>',
        '<button class="textButtonV1 green build">Construir edificio</button>',
        '<div data-list="42">Lista de granjas</div>',
        '<input name="name" value="usuario">',
    ],
)
def test_derive_selector_no_genera_selector_por_texto(outer_html):
    """
    Cubre Capa 2 — el derivador de selectores SOLO produce selectores
    estructurales; nunca debe emitir :contains, text(), has-text, etc.,
    aunque el elemento tenga texto visible.
    """
    from core.use_cases.derive_selector import derive_selector

    result = derive_selector(outer_html)
    todos = [result.selector, *result.alternatives]
    for sel in todos:
        for token in SELECTORES_POR_TEXTO_PROHIBIDOS:
            assert token not in sel, (
                f"derive_selector produjo un selector por texto: {sel!r} (token {token!r})"
            )
        # Tampoco debe filtrar por el contenido textual del elemento
        assert "Construir" not in sel
        assert "Mapa" not in sel
        assert "Aldea" not in sel
