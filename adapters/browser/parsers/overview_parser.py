"""
Parser estático para la tabla #overview de /village/statistics/overview.

Extrae los datos de todas las aldeas de las cuatro columnas de resumen:
  - td.att — movimientos de tropas activos
  - td.bui — edificios en construcción
  - td.tro — tropas presentes
  - td.tra — mercaderes libres/totales

Todos los métodos son estáticos: reciben html: str y devuelven datos Python puros.
Selectores SIEMPRE estructurales — nunca por texto visible (idioma-independientes).
El tipo de tropa se extrae por la clase uNN del img, nunca por el alt.

Helpers importados de _common.py para evitar duplicación:
  - extract_game_id_from_vil_cell  — game_id desde td.vil.fc
  - extract_unit_class             — primera clase uNN de un img
  - parse_merchants_text           — parseo "libres/totales" con limpieza bidi
"""
from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from adapters.browser.parsers._common import (
    extract_game_id_from_vil_cell,
    extract_unit_class,
    parse_merchants_text,
)

logger = logging.getLogger(__name__)


class OverviewParser:
    """
    Parser estático para la tabla #overview de /village/statistics/overview.

    Todos los métodos reciben html: str y devuelven datos Python puros.
    Selectores estructurales — nunca por texto visible.
    """

    @staticmethod
    def extract_overview_data(html: str) -> list[dict]:
        """
        Extrae los datos de todas las aldeas de la tabla #overview.

        Devuelve lista de dicts con claves:
          game_id:                      int   — extraído del href newdid=N de td.vil.fc
          movements:                    list[dict] — [{movement_type: str, quantity: int}]
          buildings_under_construction: list[dict] — [{building_name: str}]
          troops_present:               list[dict] — [{unit_class: str, quantity: int}]
          merchants_free:               int
          merchants_total:              int

        Reglas de parseo:
          - RN-03: captura genéricamente TODOS los img dentro de td.att (no filtra por clase).
          - RN-04: span.none en cualquier columna → lista vacía.
          - RN-06: tipo de tropa SIEMPRE por clase uNN del img, nunca por alt.
          - RN-07: mercaderes parseados con parse_merchants_text (limpieza bidi incluida).
          - RN-09: tabla #overview no tiene tr.sum; solo filas con td.vil.fc.
          - EC-06: alt con "0x …" incluye el movimiento con quantity=0.
          - EC-07: alt sin prefijo numérico → tropa omitida + warning.
          - EC-08: td.tra sin nodo de texto → (0, 0) + warning (vía parse_merchants_text).
        """
        soup = BeautifulSoup(html, "html.parser")
        result = []

        for row in soup.select("table#overview > tbody > tr"):
            # Extraer game_id de td.vil.fc (helper compartido de _common.py)
            vil_cell = row.select_one("td.vil.fc")
            if vil_cell is None:
                continue  # tr sin aldea (no hay tr.sum en overview — RN-09)
            game_id = extract_game_id_from_vil_cell(vil_cell)
            if game_id is None:
                continue

            # ── td.att — movimientos ──────────────────────────────────────────────
            movements = []
            att_cell = row.select_one("td.att")
            if att_cell and not att_cell.select_one("span.none"):
                for img in att_cell.find_all("img"):
                    classes = img.get("class", [])
                    # El tipo es cualquier clase que no sea "img" (genérico — RN-03)
                    movement_type = next(
                        (c for c in classes if c != "img"), None
                    )
                    if movement_type is None:
                        continue
                    alt = img.get("alt", "")
                    qty = _parse_quantity_from_alt(alt)
                    if qty is not None:
                        movements.append({
                            "movement_type": movement_type,
                            "quantity": qty,
                        })
                    # EC-06: qty=0 también se incluye (Travian puede emitirlo)

            # ── td.bui — edificios en construcción ────────────────────────────────
            buildings = []
            bui_cell = row.select_one("td.bui")
            if bui_cell and not bui_cell.select_one("span.none"):
                for img in bui_cell.select("img.bau"):
                    building_name = img.get("alt", "")
                    buildings.append({"building_name": building_name})

            # ── td.tro — tropas presentes ─────────────────────────────────────────
            troops = []
            tro_cell = row.select_one("td.tro")
            if tro_cell and not tro_cell.select_one("span.none"):
                for img in tro_cell.select("img.unit"):
                    # Tipo SIEMPRE por clase uNN, nunca por alt — RN-06
                    unit_class = extract_unit_class(img)
                    if unit_class is None:
                        continue
                    alt = img.get("alt", "")
                    qty = _parse_quantity_from_alt(alt)
                    if qty is None:
                        # EC-07: alt sin prefijo numérico → omitir + warning
                        logger.warning(
                            "overview: no se pudo parsear cantidad de tropa en aldea "
                            "%s, alt=%r", game_id, alt
                        )
                        continue
                    troops.append({"unit_class": unit_class, "quantity": qty})

            # ── td.tra — mercaderes libres/totales ────────────────────────────────
            merchants_free = 0
            merchants_total = 0
            tra_cell = row.select_one("td.tra")
            if tra_cell:
                # Puede ser <a> (aldea con mercado) o <span> (aldea sin mercado — EC-04)
                # EC-08: si ni <a> ni <span> → parse_merchants_text manejará el vacío
                text_node = tra_cell.select_one("a") or tra_cell.select_one("span")
                if text_node:
                    raw = text_node.get_text(strip=True)
                    merchants_free, merchants_total = parse_merchants_text(
                        raw, context=f"game_id={game_id}"
                    )
                else:
                    logger.warning(
                        "overview: td.tra sin <a> ni <span> en aldea %s — "
                        "merchants_free=0, merchants_total=0", game_id
                    )

            result.append({
                "game_id":                      game_id,
                "movements":                    movements,
                "buildings_under_construction": buildings,
                "troops_present":               troops,
                "merchants_free":               merchants_free,
                "merchants_total":              merchants_total,
            })

        return result


def _parse_quantity_from_alt(alt: str) -> int | None:
    """
    Extrae el número del prefijo "Nx ..." del atributo alt.

    Ej: "618x Arriving reinforcing troops" → 618
    Ej: "71x Swordsman" → 71
    Ej: "0x Something" → 0  (EC-06: incluir movimientos con cantidad 0)

    Devuelve None si no hay prefijo numérico reconocible (EC-07).
    El prefijo debe tener la forma exacta "<dígitos>x<espacio>" al inicio.
    """
    m = re.match(r"^(\d+)x\s", alt)
    if m:
        return int(m.group(1))
    return None
