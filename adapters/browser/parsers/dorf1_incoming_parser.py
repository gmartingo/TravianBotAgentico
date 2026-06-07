"""
Parser de dorf1.php para detectar ataques entrantes con timer.

Componente B del radar de ataques entrantes.

Función pura: recibe HTML como string, devuelve lista de Dorf1AttackDTO.
SIN navegación adicional — parsea el HTML ya cargado.

Discrimina ataques entrantes (img.att1) de salientes (img.att2).
SOLO persiste los entrantes (img.att1) — RN-05.

Timer: lee span.timer[value]; si no hay value, usa data-value como fallback — RN-06.
Cantidad: regex \\d+ sobre span.a1; fallback=1 si no hay match — RN-07 / EC-14.
Rally point href: <a> padre de img.att1 — RN-08.

Ver spec docs/specs/radar-ataques-entrantes.md §4 RN-05/RN-06/RN-07, §9.4.
Añadido en la feature radar-ataques-entrantes (2026-06-05).
"""
from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from core.dtos.incoming_attack_dto import Dorf1AttackDTO

logger = logging.getLogger(__name__)


class Dorf1IncomingParser:
    """
    Parser estático del HTML de dorf1.php.

    Extrae ataques entrantes del bloque troopMovements.
    Solo lee img.att1 (entrantes); img.att2 (salientes) se ignoran — RN-05.
    """

    @staticmethod
    def parse(html: str) -> list[Dorf1AttackDTO]:
        """
        Parsea el HTML de dorf1.php y devuelve los ataques entrantes.

        Si no hay bloque troopMovements → retorna lista vacía (EC-05).
        Si span.timer no tiene value ni data-value → loggea WARNING + skip (EC-04).
        Si span.a1 no tiene texto numérico → attack_count=1 como fallback (EC-14).

        Devuelve lista vacía ante ausencia de ataques entrantes.
        """
        soup = BeautifulSoup(html, "html.parser")
        results: list[Dorf1AttackDTO] = []

        # Seleccionar solo img.att1 (entrantes); img.att2 (salientes) son ignorados (RN-05)
        for img in soup.select("img.att1"):
            # El <a> padre contiene el href al rally point (RN-08)
            link = img.find_parent("a")
            if not link:
                logger.warning("img.att1 sin <a> padre — ignorando bloque")
                continue
            href = link.get("href", "")

            # La fila hermana siguiente contiene el timer y la cantidad
            row = img.find_parent("tr")
            if not row:
                logger.warning("img.att1 sin <tr> padre — ignorando bloque")
                continue

            next_row = row.find_next_sibling("tr")
            if not next_row:
                logger.warning("No hay <tr> hermana tras img.att1 — ignorando bloque")
                continue

            # Timer — RN-06: leer value, fallback a data-value
            timer_el = next_row.select_one("span.timer")
            if not timer_el:
                logger.warning("Bloque att1 sin span.timer en la fila siguiente — ignorando")
                continue

            value_str = timer_el.get("value") or timer_el.get("data-value")
            if value_str is None:
                logger.warning(
                    "span.timer sin atributo 'value' ni 'data-value' — ignorando bloque (EC-04)"
                )
                continue

            try:
                seconds = int(value_str)
            except ValueError:
                logger.warning(
                    "span.timer value no numérico: %r — ignorando bloque", value_str
                )
                continue

            # Cantidad — RN-07: regex \d+ sobre span.a1; fallback=1 (EC-14)
            count = 1
            count_el = next_row.select_one("span.a1")
            if count_el:
                m = re.search(r"\d+", count_el.get_text())
                if m:
                    count = int(m.group())

            results.append(Dorf1AttackDTO(
                attack_count=count,
                seconds_to_impact=seconds,
                rally_point_href=href,
            ))

        return results
