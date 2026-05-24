# Cubre Capa 2 — Selectores (CA-20 del spec i18n-backend)
"""
Test estático de anti-detección — CA-20.

Garantiza que la capa de traducción (i18n) NUNCA actúa como puente hacia el
adaptador de navegador. Si un nombre traducido del catálogo (p. ej. "Woodcutter",
"Leñador", "Legionnaire", "Legionario") apareciera dentro de adapters/browser/,
significaría que algún selector se construye a partir de texto visible — lo que
rompe la regla de selectores estructurales (Travian es multilenguaje) y vuelve al
bot detectable y frágil entre idiomas.

Reglas verificadas:
1. Ningún nombre traducido ni alias del catálogo aparece como palabra en
   adapters/browser/**/*.py.
2. adapters/browser/ no importa ni referencia i18n / translation / catalog.

Los tests son 100% estáticos: leen ficheros, no abren Chrome ni la API.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# Raíz del proyecto: tests/antideteccion/<este_fichero> → subir dos niveles.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CATALOG_DIR = _PROJECT_ROOT / "core" / "i18n" / "catalog"
_BROWSER_DIR = _PROJECT_ROOT / "adapters" / "browser"


def _recolectar_nombres_catalogo() -> set[str]:
    """
    Extrae todos los strings traducibles (alias + nombres por idioma) de los
    catálogos JSON. Excluye plantillas de mensaje (contienen '{') porque no son
    nombres de dominio plausibles como selector y contienen placeholders.
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
                    if v and "{" not in v:
                        nombres.add(v)
    return nombres


def _ficheros_browser() -> list[Path]:
    return sorted(_BROWSER_DIR.rglob("*.py"))


# Términos del idioma común que colisionan con vocabulario de configuración del
# navegador y NO son uso del nombre como selector. Ejemplo real: "stable" en la
# ruta del binario de Chrome '/usr/bin/google-chrome-stable' (canal de release de
# Chrome), no el edificio Establo del catálogo. Se ignoran SOLO cuando la línea
# que los contiene es claramente configuración de Chrome (ruta del ejecutable),
# nunca cuando aparecen junto a un selector.
_LINEA_ES_RUTA_CHROME = re.compile(r"chrome", re.IGNORECASE)


def test_ningun_nombre_de_catalogo_aparece_en_adapters_browser():
    """
    CA-20: ningún nombre traducido del catálogo puede aparecer como palabra
    completa dentro del código del adaptador de navegador.

    Se usa coincidencia por límite de palabra (\\b) e ignorando mayúsculas para
    evitar falsos positivos por substring (p. ej. 'stable' dentro de la ruta
    'google-chrome-stable', o 'Ram' dentro de 'Program Files'), pero detectando
    cualquier uso real del nombre de un edificio o tropa como texto.
    """
    nombres = _recolectar_nombres_catalogo()
    assert nombres, "El catálogo está vacío o no se pudo leer — revisar core/i18n/catalog"

    ficheros = _ficheros_browser()
    assert ficheros, "No se encontró ningún .py en adapters/browser/"

    # Escanear línea a línea, descartando las líneas que son rutas del binario de
    # Chrome (CHROME_PATHS). Esas líneas contienen el canal 'stable' del ejecutable
    # de Chrome, que colisiona con el alias del edificio Establo pero NO es un uso
    # del nombre como selector. Cualquier otra línea sí se evalúa íntegra.
    lineas_por_fichero: dict[Path, list[str]] = {}
    for f in ficheros:
        lineas_por_fichero[f] = [
            ln for ln in f.read_text(encoding="utf-8").splitlines()
            if not _LINEA_ES_RUTA_CHROME.search(ln)
        ]

    hallazgos: list[str] = []
    for nombre in nombres:
        # Coincidencia por límite de palabra (\b) e ignorando mayúsculas: cuenta el
        # uso del término exacto, no substrings (p. ej. 'Ram' en 'Program Files').
        patron = re.compile(r"\b" + re.escape(nombre) + r"\b", re.IGNORECASE)
        for fichero, lineas in lineas_por_fichero.items():
            for n_linea, linea in enumerate(lineas, start=1):
                if patron.search(linea):
                    rel = fichero.relative_to(_PROJECT_ROOT)
                    hallazgos.append(
                        f"{rel}: nombre de catálogo {nombre!r} usado en el browser "
                        f"→ {linea.strip()!r}"
                    )

    assert not hallazgos, (
        "CA-20 VIOLADO — la capa i18n actúa como puente hacia el browser. "
        "Los selectores deben ser estructurales (gid, name, clase CSS), nunca texto "
        "traducido:\n" + "\n".join(hallazgos)
    )


def test_adapters_browser_no_importa_ni_referencia_i18n():
    """
    CA-20 (segunda barrera): adapters/browser/ no debe importar ni mencionar la
    capa de traducción. Aunque hoy no haya colisión de nombres, un import sería
    el primer paso hacia construir selectores desde el catálogo.
    """
    prohibidos = ("i18n", "translation_port", "JsonTranslationAdapter", "catalog")
    hallazgos: list[str] = []
    for fichero in _ficheros_browser():
        codigo = fichero.read_text(encoding="utf-8")
        for token in prohibidos:
            if token.lower() in codigo.lower():
                rel = fichero.relative_to(_PROJECT_ROOT)
                hallazgos.append(f"{rel}: referencia prohibida a {token!r}")

    assert not hallazgos, (
        "CA-20 VIOLADO — adapters/browser/ referencia la capa i18n/catálogo:\n"
        + "\n".join(hallazgos)
    )
