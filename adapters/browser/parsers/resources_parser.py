"""
Parser HTML para el bloque de lectura de recursos de Travian.

Parsea las tres pestañas de /village/statistics/resources:
  - parse_stored:     table#ressources     → almacenado por aldea + totales
  - parse_production: table#production     → producción bruta por hora + totales
  - parse_capacity:   table#capacity       → capacidad almacén/granero + totales

Todos los métodos son estáticos: sin estado, sin IO, sin dependencias externas.
Verificados contra los fixtures reales de ts20.x2.america.travian.com (T4.x).

Nota de nomenclatura CSS vs DTOs:
  - CSS de Travian usa 'lum' para madera y 'tra' para mercaderes.
  - Los DTOs usan 'wood' (semántico en inglés) y 'merchants'.
  - El mapping se documenta en cada método.

Trampa del selector de tabla:
  - La tabla de almacenado tiene id='ressources' (con doble 's') en el HTML real.
  - Los DTOs y el endpoint usan 'resources' (en inglés correcto).
  - El selector DEBE usar 'table#ressources' — no 'table#resources'.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from adapters.browser.parsers._common import (
    extract_game_id_from_vil_cell,
    parse_merchants_text,
)
from core.dtos.resources_dto import (
    CapacityTotals,
    ProductionTotals,
    StoredTotals,
    VillageCapacity,
    VillageMerchants,
    VillageProductionResources,
    VillageStoredResources,
)
from core.utils.parsing import parse_int, parse_int_or_none


class ResourcesParser:
    """
    Parsers HTML para el bloque resources. Todos los métodos son estáticos.

    Selectores verificados contra fixtures reales (T4.x, ts20.x2.america.travian.com).
    Ningún selector depende de texto visible — todos son selectores estructurales.
    """

    # ---------------------------------------------------------------------------
    # Helpers privados
    # ---------------------------------------------------------------------------

    @staticmethod
    def _extract_name_from_vil_cell(vil_cell: Tag) -> str:
        """
        Extrae el nombre de la aldea desde un td.vil.fc.

        El nombre es el texto del primer <a> que contiene newdid= en su href.
        En los fixtures de test, los nombres son '00', '01', etc.
        """
        link = vil_cell.select_one("a[href*='newdid=']")
        if link is None:
            return ""
        return link.get_text(strip=True)

    @staticmethod
    def _parse_merchants(td_tra: Tag) -> VillageMerchants:
        """
        Extrae los mercaderes libres y totales de un td.tra.

        Maneja dos casos:
          - Fila de aldea: td.tra contiene un <a> con el texto 'libres/totales'
          - Fila tr.sum:   td.tra contiene el texto directamente (sin <a>)

        El texto siempre tiene formato 'N/M' con posibles caracteres bidi U+202D/U+202C.
        Se reutiliza parse_merchants_text de _common.py que ya maneja la limpieza bidi.
        """
        raw = td_tra.get_text(strip=True)
        free, total = parse_merchants_text(raw, context=f"td.tra '{raw}'")
        return VillageMerchants(free=free, total=total)

    # ---------------------------------------------------------------------------
    # Parsers de las tres tablas
    # ---------------------------------------------------------------------------

    @staticmethod
    def parse_stored(html: str) -> tuple[list[VillageStoredResources], StoredTotals]:
        """
        Parsea la tabla de recursos almacenados.

        TRAMPA: el id de la tabla en el HTML real es 'ressources' (doble 's'),
        NO 'resources'. El selector DEBE ser 'table#ressources'.

        Selectores:
          - Tabla:          soup.select_one("table#ressources")
          - Filas de aldea: tbody > tr que tienen td.vil.fc (filtra separadores y sum)
          - game_id:        extract_game_id_from_vil_cell(td.vil.fc)
          - name:           texto del <a> en td.vil.fc
          - wood:           td.lum   → parse_int  (lum = madera en CSS de Travian)
          - clay:           td.clay  → parse_int
          - iron:           td.iron  → parse_int
          - crop:           td.crop  → parse_int
          - merchants:      td.tra   → _parse_merchants (con <a> en filas de aldea)
          - Fila sum:       tr.sum   → mismos selectores; td.tra sin <a> (texto directo)

        Devuelve: (lista_aldeas, totales)
        """
        soup = BeautifulSoup(html, "html.parser")

        # TRAMPA: doble 's' en 'ressources'
        table = soup.select_one("table#ressources")
        if table is None:
            raise ValueError(
                "No se encontró table#ressources en el HTML. "
                "Verificar que el HTML es de la pestaña /village/statistics/resources. "
                "OJO: el id en el HTML de Travian usa 'ressources' con doble 's'."
            )

        villages: list[VillageStoredResources] = []

        for row in table.select("tbody > tr"):
            vil_cell = row.select_one("td.vil.fc")
            if vil_cell is None:
                # Fila separadora (tr.empty) o fila sum — se ignoran en esta iteración
                continue

            game_id = extract_game_id_from_vil_cell(vil_cell)
            if game_id is None:
                continue

            name = ResourcesParser._extract_name_from_vil_cell(vil_cell)

            wood = parse_int(row.select_one("td.lum").get_text(strip=True))
            clay = parse_int(row.select_one("td.clay").get_text(strip=True))
            iron = parse_int(row.select_one("td.iron").get_text(strip=True))
            crop = parse_int(row.select_one("td.crop").get_text(strip=True))
            merchants = ResourcesParser._parse_merchants(row.select_one("td.tra"))

            villages.append(VillageStoredResources(
                game_id=game_id,
                name=name,
                wood=wood,
                clay=clay,
                iron=iron,
                crop=crop,
                merchants=merchants,
            ))

        # Fila de totales — identificada por clase CSS 'sum', no por posición
        tr_sum = table.select_one("tr.sum")
        if tr_sum is None:
            raise ValueError("No se encontró tr.sum en table#ressources.")

        totals = StoredTotals(
            wood=parse_int(tr_sum.select_one("td.lum").get_text(strip=True)),
            clay=parse_int(tr_sum.select_one("td.clay").get_text(strip=True)),
            iron=parse_int(tr_sum.select_one("td.iron").get_text(strip=True)),
            crop=parse_int(tr_sum.select_one("td.crop").get_text(strip=True)),
            merchants=ResourcesParser._parse_merchants(tr_sum.select_one("td.tra")),
        )

        return villages, totals

    @staticmethod
    def parse_production(html: str) -> tuple[list[VillageProductionResources], ProductionTotals]:
        """
        Parsea la tabla de producción bruta por hora.

        NOTA IMPORTANTE: Los valores de crop son BRUTOS — no restan el consumo del
        ejército. Un valor crop que parezca bajo respecto a las tropas es correcto.

        Selectores:
          - Tabla:          soup.select_one("table#production")
          - Filas de aldea: tbody > tr que tienen td.vil.fc
          - wood/clay/iron/crop: td.lum / td.clay / td.iron / td.crop → parse_int
          - Fila sum — total_all_resources:
              tr_sum.select_one("td.vil span.total") → parse_int si existe, None si no (EC-07)

        Devuelve: (lista_aldeas, totales)
        """
        soup = BeautifulSoup(html, "html.parser")

        table = soup.select_one("table#production")
        if table is None:
            raise ValueError(
                "No se encontró table#production en el HTML. "
                "Verificar que el HTML es de la pestaña /village/statistics/resources/production."
            )

        villages: list[VillageProductionResources] = []

        for row in table.select("tbody > tr"):
            vil_cell = row.select_one("td.vil.fc")
            if vil_cell is None:
                continue

            game_id = extract_game_id_from_vil_cell(vil_cell)
            if game_id is None:
                continue

            name = ResourcesParser._extract_name_from_vil_cell(vil_cell)

            # Valores de producción BRUTA (lum=madera, clay=arcilla, iron=hierro, crop=cereal)
            wood = parse_int(row.select_one("td.lum").get_text(strip=True))
            clay = parse_int(row.select_one("td.clay").get_text(strip=True))
            iron = parse_int(row.select_one("td.iron").get_text(strip=True))
            crop = parse_int(row.select_one("td.crop").get_text(strip=True))

            villages.append(VillageProductionResources(
                game_id=game_id,
                name=name,
                wood=wood,
                clay=clay,
                iron=iron,
                crop=crop,
            ))

        tr_sum = table.select_one("tr.sum")
        if tr_sum is None:
            raise ValueError("No se encontró tr.sum en table#production.")

        # total_all_resources viene de span.total dentro de td.vil en la fila sum
        # Si no existe (EC-07), se devuelve None sin fallar el parseo completo
        span_total = tr_sum.select_one("td.vil span.total")
        total_all_resources: int | None = None
        if span_total is not None:
            total_all_resources = parse_int_or_none(span_total.get_text(strip=True))

        totals = ProductionTotals(
            wood=parse_int(tr_sum.select_one("td.lum").get_text(strip=True)),
            clay=parse_int(tr_sum.select_one("td.clay").get_text(strip=True)),
            iron=parse_int(tr_sum.select_one("td.iron").get_text(strip=True)),
            crop=parse_int(tr_sum.select_one("td.crop").get_text(strip=True)),
            total_all_resources=total_all_resources,
        )

        return villages, totals

    @staticmethod
    def parse_capacity(html: str) -> tuple[list[VillageCapacity], CapacityTotals]:
        """
        Parsea la tabla de capacidades de almacén y granero.

        Selectores:
          - Tabla:          soup.select_one("table#capacity")
          - Filas de aldea: tbody > tr que tienen td.vil.fc
          - warehouse:      td.max123 → parse_int (almacén: madera, arcilla, hierro)
          - granary:        td.max4   → parse_int (granero: cereal)
          - Fila sum:       tr.sum → mismos selectores

        Devuelve: (lista_aldeas, totales)
        """
        soup = BeautifulSoup(html, "html.parser")

        table = soup.select_one("table#capacity")
        if table is None:
            raise ValueError(
                "No se encontró table#capacity en el HTML. "
                "Verificar que el HTML es de la pestaña /village/statistics/resources/capacity."
            )

        villages: list[VillageCapacity] = []

        for row in table.select("tbody > tr"):
            vil_cell = row.select_one("td.vil.fc")
            if vil_cell is None:
                continue

            game_id = extract_game_id_from_vil_cell(vil_cell)
            if game_id is None:
                continue

            name = ResourcesParser._extract_name_from_vil_cell(vil_cell)

            warehouse = parse_int(row.select_one("td.max123").get_text(strip=True))
            granary = parse_int(row.select_one("td.max4").get_text(strip=True))

            villages.append(VillageCapacity(
                game_id=game_id,
                name=name,
                warehouse=warehouse,
                granary=granary,
            ))

        tr_sum = table.select_one("tr.sum")
        if tr_sum is None:
            raise ValueError("No se encontró tr.sum en table#capacity.")

        totals = CapacityTotals(
            warehouse=parse_int(tr_sum.select_one("td.max123").get_text(strip=True)),
            granary=parse_int(tr_sum.select_one("td.max4").get_text(strip=True)),
        )

        return villages, totals
