"""
Parser del diálogo de ficha de aldea en karte.php para el Componente D del radar.

Parsea `div#tileDetails` del HTML de la página de mapa de Travian:
  - Nombre de aldea y coordenadas (h1.titleInHeader)
  - Propietario (#village_info td.player a[href*='/profile/'])
  - Alianza (#village_info td.alliance a[href*='/alliance/'])
  - Población (primer td con valor numérico en #village_info — posición fija)
  - Tribu fallback (clase village-N del div#tileDetails → TRIBE_BY_VILLAGE_CLASS, RN-27)

Selectores verificados contra fixture:
  tests/fixtures/incoming_attacks/karte_tile_attacker_dialog.html
GAP-03 cerrado (v4, 2026-06-07).

ADVERTENCIA sobre tribu: la clase village-N es el fallback cuando las tropas
del rally point (Comp. C) no permitieron inferir la tribu. El mapeo
TRIBE_BY_VILLAGE_CLASS importado de rally_point_parser está solo parcialmente
confirmado (village-6=gauls es el único valor con evidencia de fixture).

Ver spec docs/specs/radar-ataques-entrantes.md §9.8, §4 RN-29.
"""
from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup, Tag

from adapters.browser.parsers._common import parse_coord
from adapters.browser.parsers.rally_point_parser import TRIBE_BY_VILLAGE_CLASS
from core.dtos.incoming_attack_dto import VillageProfileDTO

logger = logging.getLogger(__name__)

# Regex para extraer el número N de la clase CSS "village-N"
_VILLAGE_N_RE = re.compile(r"^village-(\d+)$")

# Regex para detectar un valor numérico limpio en una celda de población
_NUMERIC_RE = re.compile(r"^\d+$")


class VillageProfileParser:
    """
    Parser estático de la ficha de aldea en karte.php (Componente D).

    Parsea el div#tileDetails del HTML completo de la página del mapa.
    """

    @staticmethod
    def parse(html: str) -> VillageProfileDTO | None:
        """
        Parsea el HTML y devuelve un VillageProfileDTO, o None si no hay #tileDetails.

        Si div#tileDetails no existe → retorna None (EC-12).
        Si #village_info está vacío → extrae solo nombre y coords del h1 (EC-22).
        Si village-N no está mapeado en TRIBE_BY_VILLAGE_CLASS → tribe=None + WARNING (EC-20).

        Nunca propaga excepciones.
        """
        soup = BeautifulSoup(html, "html.parser")
        tile: Tag | None = soup.select_one("div#tileDetails")
        if not tile:
            return None  # diálogo no encontrado (EC-12)

        # --- Nombre de aldea + coordenadas desde h1.titleInHeader ---
        h1 = tile.select_one("h1.titleInHeader")
        village_name: str | None = None
        coord_x: int = 0
        coord_y: int = 0

        if h1:
            x_el = h1.select_one("span.coordinateX")
            y_el = h1.select_one("span.coordinateY")
            coord_x = parse_coord(x_el) if x_el else 0
            coord_y = parse_coord(y_el) if y_el else 0
            # Nombre: texto del h1 antes del primer '(' de las coordenadas.
            # get_text(separator=" ") une todo el texto con espacios;
            # re.split en '(' o '（' (paréntesis Unicode) y coge la parte izquierda.
            h1_text = h1.get_text(separator=" ", strip=True)
            name_part = re.split(r"[\(（]", h1_text)[0].strip()
            village_name = name_part if name_part else None

        # --- Propietario ---
        player_a = tile.select_one("#village_info td.player a[href*='/profile/']")
        player_name: str | None = player_a.get_text(strip=True) if player_a else None
        player_href: str | None = player_a.get("href") if player_a else None

        # --- Alianza ---
        alliance_a = tile.select_one("#village_info td.alliance a[href*='/alliance/']")
        alliance_name: str | None = (
            alliance_a.get_text(strip=True) if alliance_a else None
        )
        alliance_href: str | None = alliance_a.get("href") if alliance_a else None

        # --- Población: primer td con valor numérico en las filas de #village_info ---
        # La posición es fija (cuarta fila en el fixture), pero para máxima robustez
        # iteramos buscando el primer td cuyo texto sea un entero puro.
        # No depende del texto del th (localizado). (§9.8, RN-29)
        population: int | None = None
        for row in tile.select("#village_info tbody tr"):
            tds = row.find_all("td", recursive=False)
            if not tds:
                continue
            text = tds[0].get_text(strip=True).replace(" ", "").replace(" ", "")
            if _NUMERIC_RE.match(text):
                try:
                    population = int(text)
                except ValueError:
                    pass
                break

        # --- Tribu desde clase village-N (fallback RN-27) ---
        tribe: str | None = None
        for cls in (tile.get("class") or []):
            vm = _VILLAGE_N_RE.match(cls)
            if vm:
                n = int(vm.group(1))
                tribe = TRIBE_BY_VILLAGE_CLASS.get(n)
                if tribe is None:
                    logger.warning(
                        "VillageProfileParser: village-%d no está en TRIBE_BY_VILLAGE_CLASS"
                        " — tribe=None (EC-20, RN-27). Reportar para validar el mapeo.",
                        n,
                    )
                break

        return VillageProfileDTO(
            village_name=village_name,
            coord_x=coord_x,
            coord_y=coord_y,
            player_name=player_name,
            player_href=player_href,
            alliance_name=alliance_name,
            alliance_href=alliance_href,
            tribe=tribe,
            population=population,
        )
