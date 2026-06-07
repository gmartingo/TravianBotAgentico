"""
Parser del rally point de Travian para el Componente C del radar de ataques entrantes.

Parsea `table.troop_details.inAttack` del HTML del rally point:
  - Atacante y aldea origen (troopHeadline a[href*='karte.php?d='])
  - Tropas entrantes (tbody.units img.unit.uNN + cantidades tbody.units.last td.unit)
  - Hora de impacto (tbody.infos span.timer[value] / data-value)
  - Tribu derivada estructuralmente de la primera tropa con count>0 (RN-26)
  - operation_type inferida de las tropas (RN-28)

Selectores verificados contra fixture:
  tests/fixtures/incoming_attacks/troop_details_in_attack.html
GAP-02 cerrado (v4, 2026-06-07).

Constante TRIBE_BY_VILLAGE_CLASS exportada para reutilización en VillageProfileParser
(fallback tribu desde village-N — RN-27).

ADVERTENCIA: el mapeo TRIBE_BY_VILLAGE_CLASS está confirmado parcialmente —
solo village-6=gauls tiene evidencia de fixture. El resto es inferido del orden
kirilloid. Ver RN-27 y RT-12.

Ver spec docs/specs/radar-ataques-entrantes.md §9.7, §4 RN-25..28.
"""
from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup, Tag

from adapters.browser.parsers._common import extract_unit_class, parse_coord
from core.dtos.incoming_attack_dto import RallyPointAttackDTO
from core.utils.units import unit_class_to_tribe_ordinal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constante de mapeo tribu por clase village-N (RN-27)
# ADVERTENCIA: confirmado solo village-6=gauls en fixture real; el resto es
# inferido del orden de kirilloid. Si observas discrepancias, reportar para
# actualizar. Usar este mapeo SOLO como fallback cuando las tropas del
# rally point no permiten inferir la tribu.
# ---------------------------------------------------------------------------
TRIBE_BY_VILLAGE_CLASS: dict[int, str] = {
    1: "romans",
    2: "teutons",
    3: "gauls",
    4: "nature",
    5: "natars",
    6: "egyptians",
    7: "huns",
    8: "spartans",
    9: "vikings",
}

# Regex para extraer el nombre del atacante del texto del troopHeadline.
# Fixture: "GonnaDie attacks 05" → attacker_name="GonnaDie"
# Estrategia: coger el primer token hasta el primer espacio.
# El nombre del jugador en Travian siempre precede al verbo (localizado) y al
# nombre de la aldea. Si el nombre contiene espacios (infrecuente), se pierde
# la parte posterior — fallback: guardar el texto completo (EC-18).
# Ver RT-11.
_ATTACKER_NAME_RE = re.compile(r"^(\S+)")

# Ordinales de explorador por tribu (RN-28: spy si SOLO hay exploradores)
# ordinal 1-based dentro de la tribu:
#   Romans u3 → ordinal 3  (Equites Legati)
#   Teutons u13 → ordinal 3 (Scout)
#   Gauls u23 → ordinal 3  (Pathfinder)
_SPY_ORDINAL = 3


class RallyPointParser:
    """
    Parser estático del rally point de Travian (Componente C).

    Parsea el HTML completo de la página build.php?gid=16&tt=1 buscando
    todas las tablas table.troop_details.inAttack.
    """

    @staticmethod
    def parse(html: str) -> list[RallyPointAttackDTO]:
        """
        Parsea el HTML del rally point y devuelve los ataques entrantes encontrados.

        Si no hay table.troop_details.inAttack → retorna lista vacía (EC-11).
        Si una tabla no tiene troopHeadline identificable → se omite.

        Nunca propaga excepciones; las tablas con errores individuales se omiten
        con log WARNING.
        """
        soup = BeautifulSoup(html, "html.parser")
        results: list[RallyPointAttackDTO] = []

        for table in soup.select("table.troop_details.inAttack"):
            try:
                dto = RallyPointParser._parse_table(table)
                if dto is not None:
                    results.append(dto)
            except Exception as exc:
                logger.warning(
                    "RallyPointParser: error parsando tabla inAttack: %s", exc
                )

        return results

    @staticmethod
    def _parse_table(table: Tag) -> RallyPointAttackDTO | None:
        """Parsea una sola tabla table.troop_details.inAttack."""

        # --- Atacante + href de la aldea atacante ---
        headline_a = table.select_one(
            "thead td.troopHeadline a[href*='karte.php?d=']"
        )
        if not headline_a:
            return None  # tabla sin identificador de atacante → ignorar

        origin_village_href: str | None = headline_a.get("href") or None
        headline_text = headline_a.get_text(strip=True)
        m = _ATTACKER_NAME_RE.match(headline_text)
        attacker_name: str | None = m.group(1) if m else (headline_text or None)
        # EC-18: si el texto está vacío o el regex no da nada, usamos el texto completo
        if not attacker_name:
            attacker_name = headline_text or None

        # --- Coordenadas de la aldea atacante (origen del ataque) ---
        coords_th = table.select_one("tbody.units th.coords")
        if coords_th:
            x_el = coords_th.select_one("span.coordinateX")
            y_el = coords_th.select_one("span.coordinateY")
            coord_x: int | None = parse_coord(x_el) if x_el else None
            coord_y: int | None = parse_coord(y_el) if y_el else None
        else:
            coord_x, coord_y = None, None

        # --- Tropas: iconos + cantidades ---
        # El primer tbody.units (sin .last) contiene los iconos (td.uniticon > img.unit)
        # El tbody.units.last contiene las cantidades (td.unit, incluye td.unit.none)
        # Hacemos zip por posición para mantener correspondencia icono↔cantidad.
        icon_tbody = table.select_one("tbody.units:not(.last)")
        count_tbody = table.select_one("tbody.units.last")

        troops: dict[str, int] = {}

        if icon_tbody and count_tbody:
            icon_tds = icon_tbody.select("td.uniticon")
            count_tds = count_tbody.select("td.unit")  # incluye td.unit.none

            for icon_td, count_td in zip(icon_tds, count_tds):
                img = icon_td.select_one("img.unit")
                if not img:
                    continue
                unit_cls = extract_unit_class(img)
                if not unit_cls:
                    continue
                count_text = count_td.get_text(strip=True)
                try:
                    count = int(count_text)
                except ValueError:
                    count = 0
                troops[unit_cls] = count

        # --- Tribu: primera unidad con cantidad > 0 (RN-26) ---
        tribe: str | None = None
        for unit_cls, count in troops.items():
            if count > 0:
                result = unit_class_to_tribe_ordinal(unit_cls)
                if result:
                    tribe = result[0].value  # Tribe enum → str
                    break

        # --- Timer (segundos al impacto) ---
        timer_el = table.select_one("tbody.infos span.timer")
        seconds_to_impact: int | None = None
        if timer_el:
            val = timer_el.get("value") or timer_el.get("data-value")
            if val:
                try:
                    seconds_to_impact = int(val)
                except ValueError:
                    logger.warning(
                        "RallyPointParser: span.timer value no numérico: %r", val
                    )

        # --- Hora display (verbatim) ---
        at_span = table.select_one("tbody.infos div.at span")
        impact_at_display: str | None = (
            at_span.get_text(strip=True) if at_span else None
        )

        # --- operation_type (RN-28) ---
        # Default 'attack' para cualquier tropa de img.att1.
        # 'spy' si TODAS las unidades con count>0 tienen ordinal == _SPY_ORDINAL.
        # Ordinal 3 corresponde al explorador en Romans, Teutons, Gauls, etc.
        operation_type = "attack"
        positive_ordinals: list[int] = []
        for unit_cls, count in troops.items():
            if count > 0:
                r = unit_class_to_tribe_ordinal(unit_cls)
                if r:
                    positive_ordinals.append(r[1])  # ordinal 1-based dentro de tribu

        if positive_ordinals and all(o == _SPY_ORDINAL for o in positive_ordinals):
            operation_type = "spy"

        return RallyPointAttackDTO(
            attacker_name=attacker_name,
            origin_village_name=None,    # no disponible en Comp. C (RT-13): viene de Comp. D
            origin_village_coord_x=coord_x,
            origin_village_coord_y=coord_y,
            origin_village_href=origin_village_href,
            operation_type=operation_type,
            impact_at_display=impact_at_display,
            seconds_to_impact=seconds_to_impact,
            tribe=tribe,
            troops=troops,
        )
