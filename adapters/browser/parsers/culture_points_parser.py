"""
Parser estático para la tabla #culture_points de /village/statistics/culturepoints.

Extrae por aldea:
  - game_id y nombre desde td.vil.fc > a[href*='newdid=']
  - CP/día desde td.cps
  - Segundos de fiesta activa desde td.cel > a > span.timer[data-value], o None
  - Slots de fundación usados/totales desde td.slo (con limpieza de bidi anidado)

La fila tr.sum contiene los totales globales: se extrae por separado y NO genera
una VillageCulturePoints.

La fila separadora <td colspan="5" class="empty"> se ignora naturalmente (no tiene
td.vil.fc con newdid=).

Selectores verificados contra tests/fixtures/overview/culturepoints.html
(T4.x, Galos, ts20.x2.america.travian.com).

Sin IO. Sin dependencias de sesión ni Chrome. Testable con fixture en disco.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from core.dtos.culture_points_dto import CulturePointsSummary, VillageCulturePoints
from core.utils.parsing import parse_int

# Patrón para extraer newdid= del href de una aldea.
_NEWDID_RE = re.compile(r"newdid=(\d+)")

# Caracteres de control bidi que Travian inyecta en los slots (U+202D y U+202C).
# parse_int los elimina para un solo número; aquí limpiamos la cadena compuesta
# "N/M" completa antes de splitear.
_BIDI_CHARS = "‭‬"


class CulturePointsParser:
    """
    Parser puro: dado el HTML de /village/statistics/culturepoints,
    extrae la lista de VillageCulturePoints y el resumen de totales.

    Selectores verificados con tests/fixtures/overview/culturepoints.html.
    Sin IO. Sin dependencias de sesión ni Chrome.
    """

    @staticmethod
    def parse(html: str) -> CulturePointsSummary:
        """
        Parsea el HTML de la página de culture points.

        Retorna CulturePointsSummary con:
          - villages: lista de VillageCulturePoints (una por aldea, sin tr.sum)
          - cp_total_per_day: total de CP/día de la fila tr.sum
          - slots_used_total: slots usados totales de la fila tr.sum
          - slots_total: slots totales de la fila tr.sum

        Si no existe table#culture_points en el HTML → CulturePointsSummary vacío (EC-11).
        """
        soup = BeautifulSoup(html, "html.parser")

        table = soup.select_one("table#culture_points")
        if table is None:
            # EC-11: HTML sin tabla → resumen vacío con totales a 0/None
            return CulturePointsSummary(
                villages=[],
                cp_total_per_day=0,
                slots_used_total=None,
                slots_total=None,
            )

        villages: list[VillageCulturePoints] = []
        cp_total_per_day: int = 0
        slots_used_total: int | None = None
        slots_total_sum: int | None = None

        for row in table.select("tbody > tr"):

            # ---------------------------------------------------------------
            # Fila de totales (tr.sum) — extraer totales y continuar
            # ---------------------------------------------------------------
            if "sum" in row.get("class", []):
                cps_cell = row.select_one("td.cps")
                slo_cell = row.select_one("td.slo")
                if cps_cell:
                    try:
                        cp_total_per_day = parse_int(cps_cell.get_text(strip=True))
                    except (ValueError, TypeError):
                        cp_total_per_day = 0
                if slo_cell:
                    slots_used_total, slots_total_sum = _parse_slots(
                        slo_cell.get_text(strip=True)
                    )
                continue

            # ---------------------------------------------------------------
            # Filas de aldea — requieren td.vil.fc con a[href*='newdid=']
            # ---------------------------------------------------------------
            vil_cell = row.select_one("td.vil.fc")
            if vil_cell is None:
                # Fila separadora (td.empty) u otra sin aldea — ignorar (RN-08, EC-06)
                continue

            link = vil_cell.select_one("a[href*='newdid=']")
            if link is None:
                continue
            m = _NEWDID_RE.search(link.get("href", ""))
            if m is None:
                continue
            game_id = int(m.group(1))
            name = link.get_text(strip=True)
            if not name:
                continue

            # CP/día (RN-03)
            cps_cell = row.select_one("td.cps")
            try:
                cp_per_day = parse_int(cps_cell.get_text(strip=True)) if cps_cell else 0
            except (ValueError, TypeError):
                cp_per_day = 0

            # Fiesta activa via data-value (RN-01) o span.none (RN-02)
            cel_cell = row.select_one("td.cel")
            celebration_seconds_remaining = _parse_celebration(cel_cell)

            # Slots (RN-04)
            slo_cell = row.select_one("td.slo")
            slots_used, slots_total = _parse_slots(
                slo_cell.get_text(strip=True) if slo_cell else ""
            )

            villages.append(
                VillageCulturePoints(
                    game_id=game_id,
                    name=name,
                    cp_per_day=cp_per_day,
                    celebration_seconds_remaining=celebration_seconds_remaining,
                    slots_used=slots_used,
                    slots_total=slots_total,
                )
            )

        return CulturePointsSummary(
            villages=villages,
            cp_total_per_day=cp_total_per_day,
            slots_used_total=slots_used_total,
            slots_total=slots_total_sum,
        )


def _parse_celebration(cel_cell: Tag | None) -> int | None:
    """
    Extrae los segundos restantes de fiesta de td.cel.

    Prioridad:
      1. span.timer[data-value]  → int(data-value)  (fiesta activa, RN-01)
         Ejemplo fixture: <span class="timer" data-value="138145">38:22:25</span>
      2. Cualquier otro caso     → None              (sin fiesta o formato inesperado)
         Cubre: span.none (RN-02) y EC-09 (td.cel malformado).

    Nunca lanza excepción ante contenido inesperado (EC-09).
    EC-02: data-value="0" devuelve 0, no None.
    """
    if cel_cell is None:
        return None
    timer = cel_cell.select_one("span.timer[data-value]")
    if timer is not None:
        try:
            return int(timer["data-value"])
        except (KeyError, ValueError, TypeError):
            return None
    # span.none o cualquier otro estado → sin fiesta
    return None


def _parse_slots(text: str) -> tuple[int | None, int | None]:
    """
    Parsea "usados/total" de td.slo (con posibles bidi anidados, RN-04).

    El texto en el fixture real viene con bidi anidado rodeando cada número
    y la cadena completa, por ejemplo: "‭‭1‬/‭1‬‬"
    Estrategia: limpiar todos los caracteres bidi, luego splitear por '/'.

    Retorna (slots_used, slots_total) como ints, o (None, None) si el formato
    no es parseable (EC-10). Nunca lanza excepción.

    Casos válidos del fixture:
      "‭‭1‬/‭1‬‬"  →  (1, 1)
      "‭‭2‬/‭2‬‬"  →  (2, 2)
      "‭‭0‬/‭1‬‬"  →  (0, 1)
      "‭‭1‬/‭0‬‬"  →  (1, 0)   — EC-04: estado válido, sin error
      "‭‭6‬/‭6‬‬"  →  (6, 6)
    """
    cleaned = text.strip().translate(str.maketrans("", "", _BIDI_CHARS))
    parts = cleaned.split("/")
    if len(parts) != 2:
        return None, None
    try:
        used = int(parts[0].strip())
        total = int(parts[1].strip())
        return used, total
    except ValueError:
        return None, None
