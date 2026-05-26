"""
Helpers de parseo compartidos entre los parsers de las páginas de estadísticas de Travian.

Todos los helpers son funciones puras que operan sobre Tags de BeautifulSoup.
No tienen efectos secundarios ni dependencias de IO.

Funciones exportadas:
  - extract_game_id_from_vil_cell(vil_cell)           — td.vil.fc → game_id
  - extract_game_id_from_village_name_cell(name_cell) — td.villageName → game_id
  - parse_merchants_text(raw, context)                — 'libres/totales' con bidi → (free, total)
  - extract_unit_class(img_tag)                       — primer 'uNN'/'uhero' de clases de img
"""
from __future__ import annotations

import logging
import re

from bs4 import Tag

from core.utils.parsing import parse_int

logger = logging.getLogger(__name__)

# Patrón para el newdid= en los hrefs de aldea.
_NEWDID_RE = re.compile(r"newdid=(\d+)")

# Patrón para clases de unidad Travian: uNN (numérico) o uhero.
_UNIT_CLASS_RE = re.compile(r"^(u\d+|uhero)$")


def extract_game_id_from_vil_cell(vil_cell: Tag) -> int | None:
    """
    Extrae el game_id desde una celda td.vil.fc de la tabla #overview o #ressources.

    Busca el primer enlace con newdid= en el href y devuelve su valor como int.
    Devuelve None si la celda no contiene enlace o el param newdid no está presente.

    Selector de referencia: td.vil.fc > a[href*='newdid='] → int(newdid)
    Verificado contra overview.html y resources.html.
    """
    link = vil_cell.select_one("a[href*='newdid=']")
    if link is None:
        return None
    m = _NEWDID_RE.search(link.get("href", ""))
    if m is None:
        return None
    return int(m.group(1))


def extract_game_id_from_village_name_cell(name_cell: Tag) -> int | None:
    """
    Extrae el game_id desde una celda td.villageName de las tablas de tropas.

    Busca el primer enlace con newdid= en el href y devuelve su valor como int.
    Devuelve None si la celda no contiene enlace o el param newdid no está presente.

    Selector de referencia: td.villageName > a[href*='newdid='] → int(newdid)
    Verificado contra troops_own.html (build.php?newdid=N&id=39#td).
    """
    link = name_cell.select_one("a[href*='newdid=']")
    if link is None:
        return None
    m = _NEWDID_RE.search(link.get("href", ""))
    if m is None:
        return None
    return int(m.group(1))


def parse_merchants_text(raw: str, context: str = "") -> tuple[int, int]:
    """
    Parsea el texto de mercaderes 'libres/totales' limpiando caracteres bidi U+202D/U+202C.

    El texto en Travian viene en formato '‭‭14‬/‭14‬‬' (con caracteres de control bidi).
    parse_int de core/utils/parsing.py los elimina antes de convertir.

    Formato esperado: 'libres/totales'  → (free, total)
    Caso especial (EC-15): más de un '/' → usar tokens[0] y tokens[-1]; loggear warning.
    Caso especial (EC-08): sin '/' o no numérico → (0, 0); loggear warning.

    Args:
        raw:     Texto crudo del nodo de texto (a o span) de td.tra.
        context: Identificador para el warning (p.ej. 'game_id=19040').

    Returns:
        Tupla (merchants_free, merchants_total). Nunca lanza.
    """
    tokens = raw.split("/")
    if len(tokens) < 2:
        logger.warning(
            "_common: formato mercaderes inesperado [%s]: %r", context, raw
        )
        return 0, 0
    if len(tokens) > 2:
        logger.warning(
            "_common: más de un '/' en mercaderes [%s]: %r", context, raw
        )
    try:
        free = parse_int(tokens[0].strip())
        total = parse_int(tokens[-1].strip())
        return free, total
    except ValueError:
        logger.warning(
            "_common: no se pudo parsear mercaderes [%s]: %r", context, raw
        )
        return 0, 0


def extract_unit_class(img_tag: Tag) -> str | None:
    """
    Extrae la primera clase de unidad Travian (uNN o uhero) de las clases de un <img>.

    Las imágenes de unidades tienen clases como ['unit', 'u22'] o ['uhero'].
    Esta función devuelve el primer token que coincide con el patrón uNN o uhero.
    Devuelve None si ninguna clase del img es una clase de unidad reconocida.

    Verificado contra overview.html: img.unit.u22 → 'u22'.
    """
    classes = img_tag.get("class", [])
    for cls in classes:
        if _UNIT_CLASS_RE.match(cls):
            return cls
    return None
