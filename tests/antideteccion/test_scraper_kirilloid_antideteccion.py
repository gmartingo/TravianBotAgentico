# Cubre Capa 1, Capa 2 y Capa 5 — auditoria anti-deteccion del scraper de kirilloid
"""
Tests estaticos anti-deteccion del scraper de travian.kirilloid.ru.

No abren Chrome real. Verifican que el codigo nuevo de la feature kirilloid
(adapters/scraper/ y scripts/load_kirilloid.py) respeta las capas de
anti-deteccion que SI le aplican, igual que ya se exige a adapters/browser/.

Por que existe este fichero:
  El test estatico de selectores en test_config_zendriver.py solo recorre
  adapters/browser/. La feature kirilloid introdujo adapters/scraper/ y
  scripts/, que tambien interactuan con el browser compartido y deben
  cumplir las mismas reglas. El riesgo de deteccion por Travian es INDIRECTO
  (contaminacion del perfil del bot o debilitamiento del driver compartido),
  pero el guardian no negocia en lo que SI aplica.

QUE APLICA Y QUE NO al scraper de kirilloid:
  kirilloid.ru es un sitio de TERCEROS, NO es Travian y NO tiene anti-bot.
  El bot ataca a Travian con un perfil de Chrome SEPARADO
  (profiles/scraper_kirilloid). Por tanto:

  SI APLICAN (no negociables, este fichero los exige):
    - Capa 1: no recrear zd.Config, no reintroducir flags peligrosos, no
      headless, no parchear el fingerprint del driver compartido.
    - Capa 2: selectores estructurales (clase/atributo/id), nunca por texto
      visible — kirilloid es multilenguaje (~25 idiomas).
    - Capa 5: perfil SEPARADO garantizado, jamas el perfil de una cuenta
      jugadora.
    - driver.py debe permanecer intacto.

  NO APLICA (exencion deliberada, decision de producto del usuario):
    - Capa 3 (timing humano / pacing con human_delay): el timing humano
      existe para enganar el anti-bot de TRAVIAN. kirilloid no tiene anti-bot,
      asi que simular humano aqui solo ralentiza sin aportar indetectabilidad.
      El scraper de kirilloid PUEDE y DEBE usar un sleep fijo corto para
      esperar el re-render del SPA tras cambiar de idioma (espera funcional,
      no humana). El requisito de human_delay/jitter sigue vigente para los
      adapters TRAVIAN-facing (adapters/browser/ y el resto del bot), donde
      se audita en test_config_zendriver.py.
"""
import ast
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# Ficheros/directorios de la feature kirilloid que tocan el browser compartido.
SCRAPER_DIR = REPO_ROOT / "adapters" / "scraper"
LOAD_SCRIPT = REPO_ROOT / "scripts" / "load_kirilloid.py"


def _scraper_py_files() -> list[pathlib.Path]:
    """Todos los .py del scraper + el script CLI."""
    files = list(SCRAPER_DIR.rglob("*.py")) if SCRAPER_DIR.exists() else []
    if LOAD_SCRIPT.exists():
        files.append(LOAD_SCRIPT)
    return files


# ---------------------------------------------------------------------------
# Test 1: Selectores prohibidos por texto visible (Capa 2)
# ---------------------------------------------------------------------------

def test_no_existen_selectores_por_texto_en_scraper():
    """
    Cubre Capa 2 — Selectores prohibidos.

    kirilloid es multilenguaje (~25 idiomas). Buscar elementos por texto
    visible romperia al cambiar de idioma y es un patron tipico de bot.
    Todos los selectores del scraper deben ser estructurales
    (clase/atributo/id).

    Nota: `(await td.text()).strip()` esta PERMITIDO — es LECTURA del valor
    de una celda ya localizada por selector estructural, no SELECCION por
    texto. Solo se prohiben los patrones que localizan/filtran por texto.
    """
    py_files = _scraper_py_files()
    assert py_files, (
        "No se encontraron archivos .py del scraper. "
        "Verificar adapters/scraper/ y scripts/load_kirilloid.py."
    )

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
    for py_file in py_files:
        source = py_file.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(source.splitlines(), start=1):
            for patron in patrones_prohibidos:
                if patron in line:
                    violaciones.append(
                        f"{py_file.name}:{lineno} — patron '{patron}' — {line.strip()}"
                    )

    assert not violaciones, (
        "BLOQUEANTE Capa 2: selectores por texto visible en el scraper:\n"
        + "\n".join(violaciones)
    )


# ---------------------------------------------------------------------------
# Test 2: No hay comparaciones de .text() para DECIDIR seleccion (Capa 2)
# ---------------------------------------------------------------------------

def test_no_se_decide_seleccion_por_texto_visible_en_scraper():
    """
    Cubre Capa 2 — Refuerzo: ninguna decision de seleccion de elemento
    depende de comparar texto visible (`.text == "Construir"`, etc.).

    Parsea el AST y busca comparaciones donde uno de los lados sea una
    llamada `.text(...)` o atributo `.text` comparado contra un literal
    de string que NO sea un marcador neutro de dato vacio ('—', '', '-').
    Esos marcadores son tratamiento de dato (RN-07), no seleccion por idioma.
    """
    marcadores_dato_vacio = {"—", "", "-"}
    violaciones = []

    for py_file in _scraper_py_files():
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
            # Permitido: comparar text contra marcadores de dato vacio.
            sospechosos = [s for s in literales if s not in marcadores_dato_vacio]
            if sospechosos:
                violaciones.append(
                    f"{py_file.name}:{node.lineno} — comparacion de .text contra "
                    f"texto visible {sospechosos}"
                )

    assert not violaciones, (
        "BLOQUEANTE Capa 2: se decide seleccion/filtrado por texto visible "
        "(romperia en otro idioma de kirilloid):\n" + "\n".join(violaciones)
    )


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
    # caso `(await x.text()).strip()` -> Call(.strip) sobre Await(Call(.text))
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


# ---------------------------------------------------------------------------
# Test 3: El scraper usa SIEMPRE el perfil separado (Capa 5)
# ---------------------------------------------------------------------------

def test_scraper_usa_perfil_separado_nunca_perfil_de_cuenta():
    """
    Cubre Capa 5 — Aislamiento de perfil.

    El scraper de un sitio de TERCEROS (kirilloid) NUNCA debe usar el perfil
    de Chrome de una cuenta jugadora de Travian. Si kirilloid detectase el
    acceso, no debe poder correlacionarlo con la sesion del bot.

    Verifica que toda llamada a create_browser(...) en el script CLI recibe
    como argumento la constante/literal del perfil separado
    'profiles/scraper_kirilloid', y nunca un perfil que contenga 'account'.
    """
    assert LOAD_SCRIPT.exists(), "scripts/load_kirilloid.py no existe."

    source = LOAD_SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(LOAD_SCRIPT))

    llamadas_create_browser = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "create_browser"
    ]

    assert llamadas_create_browser, (
        "No se encontro ninguna llamada a create_browser() en el script CLI. "
        "Revisar que el scraper arranca el browser via el driver compartido."
    )

    for call in llamadas_create_browser:
        assert call.args, (
            f"create_browser() en linea {call.lineno} sin argumento de perfil."
        )
        arg = call.args[0]
        # El argumento debe ser un literal con el perfil del scraper.
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            perfil = arg.value
        else:
            pytest.fail(
                f"BLOQUEANTE Capa 5: create_browser() en linea {call.lineno} "
                f"recibe un perfil no literal — no se puede garantizar "
                f"estaticamente que sea el perfil separado del scraper."
            )

        assert "scraper_kirilloid" in perfil, (
            f"BLOQUEANTE Capa 5: create_browser() usa el perfil '{perfil}', "
            f"que no es el perfil separado del scraper (profiles/scraper_kirilloid)."
        )
        assert "account" not in perfil.lower(), (
            f"BLOQUEANTE Capa 5: create_browser() usa un perfil que parece de "
            f"una cuenta jugadora: '{perfil}'. El scraper jamas debe contaminar "
            f"el perfil de una cuenta de Travian."
        )


# ---------------------------------------------------------------------------
# Test 4: El scraper NO reintroduce flags peligrosos ni parchea el driver (Capa 1)
# ---------------------------------------------------------------------------

def test_scraper_no_debilita_el_driver_compartido():
    """
    Cubre Capa 1 — Configuracion de Chrome.

    El scraper debe REUTILIZAR el driver compartido (create_browser), nunca
    recrear zd.Config con flags propios ni reactivar webdriver/headless ni
    tocar el fingerprint. Verifica que no aparecen patrones peligrosos en
    el codigo del scraper.
    """
    patrones_prohibidos = [
        "headless=True",
        "--headless",
        "--headless=new",
        "--enable-automation",
        "zd.Config",          # el scraper no debe construir su propia config
        "zendriver.Config",
        "navigator.webdriver",
        "window.chrome",
    ]

    violaciones = []
    for py_file in _scraper_py_files():
        source = py_file.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(source.splitlines(), start=1):
            for patron in patrones_prohibidos:
                if patron in line:
                    violaciones.append(
                        f"{py_file.name}:{lineno} — patron '{patron}' — {line.strip()}"
                    )

    assert not violaciones, (
        "BLOQUEANTE Capa 1: el scraper reintroduce flags peligrosos o recrea "
        "la config del browser en vez de reutilizar el driver compartido:\n"
        + "\n".join(violaciones)
    )


# ---------------------------------------------------------------------------
# Test 5: El scraper de kirilloid esta EXENTO del pacing humano (NO Capa 3)
# ---------------------------------------------------------------------------

def test_scraper_kirilloid_exento_de_pacing_humano():
    """
    EXENCION DELIBERADA de Capa 3 (timing humano) para el scraper de kirilloid.

    POR QUE la exencion:
      El timing humano (human_delay con jitter 500-900 ms) existe para enganar
      el anti-bot de TRAVIAN. kirilloid.ru es un sitio de TERCEROS sin anti-bot
      y el bot lo visita con un perfil de Chrome SEPARADO
      (profiles/scraper_kirilloid), aislado del perfil de juego. Simular humano
      aqui no aporta NINGUNA indetectabilidad ante Travian: solo ralentiza un
      scraping de ~9 tribus x ~25 idiomas. Decision de producto del usuario:
      este scraper NO simula humano.

    Por tanto este test verifica lo CONTRARIO al requisito Travian-facing:
      - El scraper NO debe usar human_delay (ese helper es para Travian; aqui
        seria pacing humano injustificado y mas lento).
      - Un asyncio.sleep FIJO y corto SI esta permitido (espera funcional del
        re-render del SPA tras cambiar idioma), pero acotado a un rango sano
        (<= 1000 ms) para que nadie reintroduzca un "delay de cortesia" largo
        disfrazado de espera de render.

    El requisito de human_delay/jitter sigue vigente y se audita para los
    adapters TRAVIAN-facing en tests/antideteccion/test_config_zendriver.py
    (Test 4: time.sleep sin constante en adapters/browser y core; Test 5:
    distribucion estadistica de human_delay).
    """
    import re

    assert LOAD_SCRIPT.exists(), "scripts/load_kirilloid.py no existe."
    source = LOAD_SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(LOAD_SCRIPT))

    # 1) El scraper de kirilloid NO debe usar human_delay (pacing Travian-facing).
    llamadas_human_delay = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "human_delay"
    ]
    assert not llamadas_human_delay, (
        "El scraper de kirilloid NO debe usar human_delay(): kirilloid es un "
        "sitio de terceros sin anti-bot, el pacing humano solo ralentiza sin "
        "aportar indetectabilidad ante Travian. Usar un sleep fijo corto para "
        f"el re-render. Encontradas {len(llamadas_human_delay)} llamadas."
    )

    # 2) Los asyncio.sleep FIJOS estan permitidos aqui, pero acotados (<= 1 s)
    #    para que nadie reintroduzca un delay largo disfrazado de espera de render.
    patron_sleep_fijo = re.compile(r'asyncio\.sleep\s*\(\s*(\d+\.?\d*)\s*\)')
    for i, line in enumerate(source.splitlines(), start=1):
        m = patron_sleep_fijo.search(line)
        if m:
            valor_s = float(m.group(1))
            assert valor_s <= 1.0, (
                f"linea {i}: asyncio.sleep({valor_s}) excede 1 s. Un sleep fijo "
                "en el scraper de kirilloid solo debe cubrir el re-render del "
                "SPA; un valor largo seria un 'delay de cortesia' encubierto que "
                "el usuario decidio eliminar por velocidad."
            )
