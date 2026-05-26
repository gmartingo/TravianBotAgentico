# Cubre Capa 2 — Selectores (CA-20 del spec i18n-backend)
"""
Test estático de anti-detección — CA-20.

Garantiza que la capa de traducción (i18n) NUNCA actúa como puente hacia el
adaptador de navegador. Si un nombre traducido del catálogo (p. ej. "Woodcutter",
"Leñador", "Legionnaire", "Legionario") se usara para construir un selector a
partir de texto visible, el bot sería detectable y frágil entre idiomas (Travian
es multilenguaje). Los selectores deben ser SIEMPRE estructurales: clase CSS
(uNN, td.max123), id (#troops), gid/newdid, no texto.

Reglas verificadas:
1. Ningún nombre traducido del catálogo aparece dentro de un LITERAL DE CADENA del
   código de adapters/browser/ (lo que delataría un selector construido por texto,
   p. ej. find(text="Almacén"), string="Warehouse").
2. adapters/browser/ no IMPORTA ni referencia en código la capa i18n/translation/
   catalog.

Precisión (por qué este test no usa grep bruto):
- Solo mira código real. Comentarios y docstrings se excluyen vía AST, porque una
  explicación en prosa ("el parser no llama a translation_port", "todas las
  pestañas") NO es una violación — y el español "las" o el nombre de variable
  inglés `warehouse` colisionan con nombres del catálogo sin ser selectores.
- Solo cuentan los LITERALES DE CADENA (un selector por texto siempre es una
  string), nunca los identificadores (la variable `warehouse` es un campo, no un
  selector).
- Se descartan nombres de catálogo de < 4 caracteres (artículos/abreviaturas como
  "Las", "as", "de") que generan colisiones con vocabulario común. Límite conocido
  y aceptado (trade-off señal/ruido): esto también deja fuera algunos nombres
  cortos REALES de tropas/edificios (p. ej. "Ram", o nombres CJK de 2-3 caracteres);
  su nombre canónico inglés sí es largo y sí se detecta.
- Se descartan literales de configuración del navegador (rutas de Chrome,
  user-agent) que contienen tokens como "stable" del canal de release.

Los tests son 100% estáticos: leen y parsean ficheros, no abren Chrome ni la API.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

# Raíz del proyecto: tests/antideteccion/<este_fichero> → subir dos niveles.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CATALOG_DIR = _PROJECT_ROOT / "core" / "i18n" / "catalog"
_BROWSER_DIR = _PROJECT_ROOT / "adapters" / "browser"

# Longitud mínima de un nombre de catálogo para considerarlo. Por debajo de esto
# (artículos, abreviaturas como "Las") la colisión con vocabulario común es ruido.
_LONGITUD_MINIMA_NOMBRE = 4

# Un literal de cadena que sea claramente configuración del navegador (ruta del
# binario de Chrome, user-agent) NO es un selector de dominio aunque contenga un
# token que coincida con un alias del catálogo (p. ej. 'stable' del canal de
# release de Chrome colisiona con el alias del edificio Establo).
_LITERAL_ES_INFRA_BROWSER = re.compile(
    r"chrome|mozilla|applewebkit|webkit|safari|gecko|://|/usr/|/opt/|\.app|user-agent",
    re.IGNORECASE,
)


# Marcadores inequívocos de un selector XPath POR TEXTO. Un XPath contiene '/'
# (ejes/pasos), así que sin esta excepción la heurística de ruta lo dejaría pasar
# (//span[text()="Almacén"], .//a[contains(text(),"Granary")]). Ninguna ruta/URL
# legítima de Travian ('village/statistics/troops/hospital') contiene 'text()' ni
# 'contains(', de modo que esta lista no reintroduce falsos positivos.
_XPATH_POR_TEXTO = ("text()", "contains(")


def _literal_es_ruta(literal: str) -> bool:
    """
    True si el literal es una RUTA/URL de Travian (contiene '/'), no un selector por
    texto. Las rutas de Travian son slugs estructurales en inglés, independientes del
    idioma de la UI (p. ej. 'village/statistics/troops/hospital'): que 'hospital' o
    'smithy' coincidan con un nombre del catálogo es colisión, no un selector por
    texto. Un selector por texto en BeautifulSoup (find(text="Hospital"),
    string="Almacén") es el nombre suelto, SIN '/', así que se sigue detectando.

    EXCEPCIÓN: un XPath por texto también contiene '/', pero SÍ es un selector
    prohibido. Si el literal incluye un marcador de XPath-por-texto, NO se trata como
    ruta y se sigue escaneando.
    """
    if any(marcador in literal for marcador in _XPATH_POR_TEXTO):
        return False
    return "/" in literal

# Fragmentos de módulo/símbolo de la capa de traducción cuyo IMPORT o USO en
# adapters/browser/ está prohibido (esta sí es la defensa dura: un import sería el
# primer paso hacia construir selectores desde el catálogo).
_MODULOS_I18N_PROHIBIDOS = ("i18n", "translation", "catalog")
_SIMBOLOS_I18N_PROHIBIDOS = (
    "translationport",
    "jsontranslationadapter",
    "translation_port",
)


def _recolectar_nombres_catalogo() -> set[str]:
    """
    Extrae todos los strings traducibles (alias + nombres por idioma) de los
    catálogos JSON. Excluye plantillas de mensaje (contienen '{') y nombres de
    menos de _LONGITUD_MINIMA_NOMBRE caracteres (colisionan con vocabulario común).
    """
    nombres: set[str] = set()
    for jf in _CATALOG_DIR.rglob("*.json"):
        data = json.loads(jf.read_text(encoding="utf-8"))
        for entry in data.values():
            if not isinstance(entry, dict):
                continue
            for valor in entry.values():
                if isinstance(valor, str):
                    v = valor.strip()
                    if v and "{" not in v and len(v) >= _LONGITUD_MINIMA_NOMBRE:
                        nombres.add(v)
    return nombres


def _ficheros_browser() -> list[Path]:
    return sorted(_BROWSER_DIR.rglob("*.py"))


def _ids_de_docstrings(tree: ast.Module) -> set[int]:
    """
    Devuelve los id() de los nodos Constant que son docstrings (de módulo, clase o
    función). Sirve para excluirlos del escaneo: una docstring es documentación, no
    un selector.
    """
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            cuerpo = getattr(node, "body", [])
            if cuerpo and isinstance(cuerpo[0], ast.Expr):
                valor = cuerpo[0].value
                if isinstance(valor, ast.Constant) and isinstance(valor.value, str):
                    ids.add(id(valor))
    return ids


def _literales_de_cadena_del_codigo(tree: ast.Module) -> list[str]:
    """
    Devuelve todos los literales str del código EXCEPTO docstrings. Los comentarios
    no existen en el AST, así que quedan excluidos automáticamente.
    """
    doc_ids = _ids_de_docstrings(tree)
    out: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in doc_ids
        ):
            out.append(node.value)
    return out


def test_ningun_nombre_de_catalogo_se_usa_como_selector_de_texto():
    """
    CA-20: ningún nombre traducido del catálogo puede aparecer en un literal de
    cadena del código del adaptador de navegador.

    Un selector construido por texto visible (find(text="Almacén"),
    string="Warehouse", comparación con get_text()) es siempre un literal str que
    contiene el nombre. Los identificadores (la variable `warehouse`), los
    comentarios y las docstrings NO son violaciones y se excluyen.
    """
    nombres = _recolectar_nombres_catalogo()
    assert nombres, "El catálogo está vacío o no se pudo leer — revisar core/i18n/catalog"

    ficheros = _ficheros_browser()
    assert ficheros, "No se encontró ningún .py en adapters/browser/"

    # Una sola regex con todos los nombres (alternación), por límite de palabra e
    # ignorando mayúsculas. Más largos primero para que la alternación prefiera el
    # nombre completo.
    alternancia = "|".join(
        re.escape(n) for n in sorted(nombres, key=len, reverse=True)
    )
    patron = re.compile(r"\b(" + alternancia + r")\b", re.IGNORECASE)

    hallazgos: list[str] = []
    for fichero in ficheros:
        tree = ast.parse(fichero.read_text(encoding="utf-8"))
        for literal in _literales_de_cadena_del_codigo(tree):
            if _LITERAL_ES_INFRA_BROWSER.search(literal) or _literal_es_ruta(literal):
                continue  # config de Chrome / user-agent / ruta-URL: no es selector por texto
            m = patron.search(literal)
            if m:
                rel = fichero.relative_to(_PROJECT_ROOT)
                hallazgos.append(
                    f"{rel}: nombre de catálogo {m.group(0)!r} en un literal de "
                    f"cadena → {literal.strip()!r}"
                )

    assert not hallazgos, (
        "CA-20 VIOLADO — un nombre traducido del catálogo aparece en un literal de "
        "cadena del browser. Los selectores deben ser estructurales (gid, name, "
        "clase CSS), nunca texto traducido:\n" + "\n".join(hallazgos)
    )


def test_adapters_browser_no_importa_ni_usa_i18n():
    """
    CA-20 (segunda barrera, defensa dura): adapters/browser/ no debe IMPORTAR ni
    referenciar en código la capa i18n/translation/catalog. Un import sería el
    primer paso hacia construir selectores desde el catálogo.

    Se analiza el AST: imports reales (import / from ... import) y usos de símbolos
    (Name/Attribute). Las menciones en comentarios o docstrings (p. ej. "el use
    case lo construye con translation_port") NO cuentan: son documentación, no
    dependencia.
    """
    hallazgos: list[str] = []
    for fichero in _ficheros_browser():
        tree = ast.parse(fichero.read_text(encoding="utf-8"))
        rel = fichero.relative_to(_PROJECT_ROOT)

        for node in ast.walk(tree):
            # import xxx  /  import a.b.i18n
            if isinstance(node, ast.Import):
                for alias in node.names:
                    bajo = alias.name.lower()
                    if any(frag in bajo for frag in _MODULOS_I18N_PROHIBIDOS):
                        hallazgos.append(f"{rel}: import prohibido {alias.name!r}")
            # from a.b.translation_port import X
            elif isinstance(node, ast.ImportFrom):
                modulo = (node.module or "").lower()
                if any(frag in modulo for frag in _MODULOS_I18N_PROHIBIDOS):
                    hallazgos.append(
                        f"{rel}: import-from prohibido {node.module!r}"
                    )
            # uso de un símbolo de traducción: translation_port.x / TranslationPort
            elif isinstance(node, ast.Name):
                if node.id.lower() in _SIMBOLOS_I18N_PROHIBIDOS:
                    hallazgos.append(f"{rel}: uso de símbolo i18n {node.id!r}")
            elif isinstance(node, ast.Attribute):
                if node.attr.lower() in _SIMBOLOS_I18N_PROHIBIDOS:
                    hallazgos.append(f"{rel}: uso de atributo i18n {node.attr!r}")

    assert not hallazgos, (
        "CA-20 VIOLADO — adapters/browser/ importa o usa la capa i18n/catálogo:\n"
        + "\n".join(hallazgos)
    )
