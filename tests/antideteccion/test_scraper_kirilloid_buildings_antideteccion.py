# Cubre Capa 1, Capa 2 y Capa 5 — auditoría anti-detección del scraper de edificios kirilloid
"""
Tests estáticos anti-detección del scraper de edificios de kirilloid.ru.

Análogo a test_scraper_kirilloid_antideteccion.py para el scraper de tropas.
Verifica que kirilloid_buildings_scraper.py y load_kirilloid_buildings.py respetan
las mismas capas de anti-detección que el scraper de tropas.

QUÉ APLICA Y QUÉ NO (idéntico al scraper de tropas — ver test_scraper_kirilloid_antideteccion.py):

  SÍ APLICAN:
    - Capa 1: no recrear zd.Config, no reintroducir flags peligrosos.
    - Capa 2: selectores estructurales (clase/atributo/id), nunca por texto visible.
    - Capa 5: perfil SEPARADO garantizado, jamás el perfil de una cuenta jugadora.
    - driver.py debe permanecer intacto.

  NO APLICA:
    - Capa 3 (timing humano): kirilloid no es Travian, no tiene anti-bot.
      Los delays funcionales (asyncio.sleep <= 1 s) están permitidos.
"""
import ast
import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

SCRAPER_FILE = REPO_ROOT / "adapters" / "scraper" / "kirilloid_buildings_scraper.py"
LOAD_SCRIPT = REPO_ROOT / "scripts" / "load_kirilloid_buildings.py"
UTILS_FILE = REPO_ROOT / "adapters" / "scraper" / "utils.py"


def _buildings_scraper_files() -> list[pathlib.Path]:
    """Ficheros del scraper de edificios + script CLI + utils."""
    files = []
    for f in [SCRAPER_FILE, LOAD_SCRIPT, UTILS_FILE]:
        if f.exists():
            files.append(f)
    return files


# ---------------------------------------------------------------------------
# Test 1: Selectores prohibidos por texto visible (Capa 2)
# ---------------------------------------------------------------------------


def test_no_existen_selectores_por_texto_en_buildings_scraper():
    """
    Cubre Capa 2 — Selectores prohibidos en el scraper de edificios.

    kirilloid es multilenguaje (~25 idiomas). Los selectores deben ser
    estructurales (clase/atributo/id), nunca por texto visible.
    """
    files = _buildings_scraper_files()
    assert files, "No se encontraron ficheros del scraper de edificios."

    patrones_prohibidos = [
        "By.LINK_TEXT",
        "By.PARTIAL_LINK_TEXT",
        "link_text=",
        "partial_link_text=",
        ":has-text(",
        ":contains(",
        "contains(text()",
        'text()="',
        "text()='",
        ".getText(",
        "xpath",
    ]

    violaciones = []
    for py_file in files:
        source = py_file.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(source.splitlines(), start=1):
            for patron in patrones_prohibidos:
                if patron in line:
                    violaciones.append(
                        f"{py_file.name}:{lineno} — patron '{patron}' — {line.strip()}"
                    )

    assert not violaciones, (
        "BLOQUEANTE Capa 2: selectores por texto visible en scraper de edificios:\n"
        + "\n".join(violaciones)
    )


# ---------------------------------------------------------------------------
# Test 2: No hay comparaciones de .text para DECIDIR selección (Capa 2)
# ---------------------------------------------------------------------------


def _es_acceso_text(node: ast.AST) -> bool:
    """True si el nodo es `x.text` o `x.text()` (lectura de texto del DOM)."""
    if isinstance(node, ast.Attribute) and node.attr == "text":
        return True
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "text"
    ):
        return True
    # `(await x.text()).strip()` → Call(.strip) sobre Await(Call(.text))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        inner = node.func.value
        if isinstance(inner, ast.Await):
            inner = inner.value
        if (
            isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Attribute)
            and inner.func.attr == "text"
        ):
            return True
    return False


def test_no_se_decide_seleccion_por_texto_visible_en_buildings_scraper():
    """
    Cubre Capa 2 — Refuerzo: ninguna decisión de selección depende de .text
    comparado contra un literal de string que no sea un marcador de dato vacío.
    """
    marcadores_dato_vacio = {"—", "", "-"}
    violaciones = []

    for py_file in _buildings_scraper_files():
        source = py_file.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(py_file))

        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            partes = [node.left, *node.comparators]
            usa_text = any(_es_acceso_text(p) for p in partes)
            if not usa_text:
                continue
            literales = [
                p.value for p in partes
                if isinstance(p, ast.Constant) and isinstance(p.value, str)
            ]
            sospechosos = [s for s in literales if s not in marcadores_dato_vacio]
            if sospechosos:
                violaciones.append(
                    f"{py_file.name}:{node.lineno} — comparación de .text contra "
                    f"texto visible {sospechosos}"
                )

    assert not violaciones, (
        "BLOQUEANTE Capa 2: se decide selección por texto visible "
        "(rompería en otro idioma de kirilloid):\n" + "\n".join(violaciones)
    )


# ---------------------------------------------------------------------------
# Test 3: El script CLI usa el perfil separado (Capa 5)
# ---------------------------------------------------------------------------


def test_buildings_script_usa_perfil_separado_nunca_perfil_de_cuenta():
    """
    Cubre Capa 5 — Aislamiento de perfil.

    El scraper de edificios NUNCA debe usar el perfil de Chrome de una cuenta
    jugadora de Travian. Verifica que la llamada a create_browser() en el
    script CLI recibe el perfil separado 'profiles/scraper_kirilloid'.
    """
    assert LOAD_SCRIPT.exists(), "scripts/load_kirilloid_buildings.py no existe."

    source = LOAD_SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(LOAD_SCRIPT))

    llamadas_create_browser = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "create_browser"
    ]

    assert llamadas_create_browser, (
        "No se encontró ninguna llamada a create_browser() en el script CLI. "
        "Revisar que el scraper arranca el browser vía el driver compartido."
    )

    for call in llamadas_create_browser:
        assert call.args, (
            f"create_browser() en línea {call.lineno} sin argumento de perfil."
        )
        arg = call.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            perfil = arg.value
        else:
            pytest.fail(
                f"BLOQUEANTE Capa 5: create_browser() en línea {call.lineno} "
                f"recibe un perfil no literal — no se puede garantizar "
                f"estáticamente que sea el perfil separado del scraper."
            )

        assert "scraper_kirilloid" in perfil, (
            f"BLOQUEANTE Capa 5: create_browser() usa el perfil '{perfil}', "
            f"que no es el perfil separado del scraper (profiles/scraper_kirilloid)."
        )
        assert "account" not in perfil.lower(), (
            f"BLOQUEANTE Capa 5: create_browser() usa un perfil que parece de "
            f"una cuenta jugadora: '{perfil}'."
        )


# ---------------------------------------------------------------------------
# Test 4: El scraper NO reintroduce flags peligrosos ni parchea el driver (Capa 1)
# ---------------------------------------------------------------------------


def test_buildings_scraper_no_debilita_el_driver_compartido():
    """
    Cubre Capa 1 — El scraper reutiliza el driver compartido (create_browser),
    nunca recrea zd.Config con flags propios ni reintroduce headless.
    """
    patrones_prohibidos = [
        "headless=True",
        "--headless",
        "--headless=new",
        "--enable-automation",
        "zd.Config",
        "zendriver.Config",
        "navigator.webdriver",
        "window.chrome",
    ]

    violaciones = []
    for py_file in _buildings_scraper_files():
        source = py_file.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(source.splitlines(), start=1):
            for patron in patrones_prohibidos:
                if patron in line:
                    violaciones.append(
                        f"{py_file.name}:{lineno} — patron '{patron}' — {line.strip()}"
                    )

    assert not violaciones, (
        "BLOQUEANTE Capa 1: el scraper de edificios reintroduce flags peligrosos "
        "o recrea la config del browser:\n" + "\n".join(violaciones)
    )


# ---------------------------------------------------------------------------
# Test 5: El scraper de edificios está EXENTO del pacing humano (NO Capa 3)
# ---------------------------------------------------------------------------


def test_buildings_scraper_exento_de_pacing_humano():
    """
    EXENCIÓN DELIBERADA de Capa 3 (timing humano) para el scraper de edificios.

    - NO debe usar human_delay (kirilloid no es Travian).
    - asyncio.sleep FIJO <= 1 s está permitido (espera funcional del SPA / cortesía).
    """
    assert LOAD_SCRIPT.exists(), "scripts/load_kirilloid_buildings.py no existe."
    source = LOAD_SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(LOAD_SCRIPT))

    # 1) No debe usar human_delay
    llamadas_human_delay = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "human_delay"
    ]
    assert not llamadas_human_delay, (
        f"El scraper de edificios NO debe usar human_delay(). "
        f"Encontradas {len(llamadas_human_delay)} llamadas."
    )

    # 2) asyncio.sleep FIJO <= 1 s
    patron_sleep_fijo = re.compile(r'asyncio\.sleep\s*\(\s*(\d+\.?\d*)\s*\)')
    for i, line in enumerate(source.splitlines(), start=1):
        m = patron_sleep_fijo.search(line)
        if m:
            valor_s = float(m.group(1))
            assert valor_s <= 1.0, (
                f"línea {i}: asyncio.sleep({valor_s}) excede 1 s. "
                "Un sleep fijo en el scraper de kirilloid solo debe cubrir el "
                "re-render del SPA o la cortesía entre gids."
            )


# ---------------------------------------------------------------------------
# Test 6: driver.py permanece intacto (Capa 1 — verificación de no modificación)
# ---------------------------------------------------------------------------


def test_driver_py_no_modificado_por_scraper_de_edificios():
    """
    Cubre Capa 1 — driver.py no debe ser tocado por los ficheros del scraper.

    Verifica que kirilloid_buildings_scraper.py y load_kirilloid_buildings.py
    NO importan de driver.py directamente (solo el script CLI puede importar
    create_browser, que es la interfaz pública aprobada).
    """
    scraper_file = SCRAPER_FILE
    assert scraper_file.exists(), "kirilloid_buildings_scraper.py no existe."

    source = scraper_file.read_text(encoding="utf-8")
    # El módulo del scraper NO debe importar directamente de adapters.browser.driver
    # (lo hace solo el script CLI, que sí está autorizado a usar create_browser)
    assert "from adapters.browser.driver" not in source, (
        "BLOQUEANTE Capa 1: kirilloid_buildings_scraper.py importa directamente de "
        "adapters.browser.driver. El scraper no debe manipular el driver; "
        "create_browser() solo se usa en el script CLI."
    )
    assert "import adapters.browser.driver" not in source, (
        "BLOQUEANTE Capa 1: kirilloid_buildings_scraper.py importa el módulo driver."
    )
