"""
DTOs de respuesta para el endpoint GET /game/culture-points/{world_id}.

Todos los dataclasses son frozen=True: inmutables una vez construidos,
igual que los DTOs del bloque overview.

Semántica de None/0:
  - celebration_seconds_remaining=None  significa sin fiesta activa (td.cel > span.none).
  - celebration_seconds_remaining=0     significa fiesta activa con timer a 0 (EC-02).
  - slots_used/slots_total=None         significa formato de td.slo no parseable (EC-10).
  - slots_used=1, slots_total=0         es un estado válido del juego (EC-04, aldea "05").
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VillageCulturePoints:
    """
    Datos de culture points de una aldea individual.

    Campos:
      game_id                       — ID de aldea en Travian (parámetro newdid=N del href)
      name                          — Nombre de la aldea (texto del <a> en td.vil.fc)
      cp_per_day                    — CP que produce la aldea por día (td.cps)
      celebration_seconds_remaining — Segundos restantes de fiesta activa, o None si
                                      no hay fiesta (td.cel > a > span.timer[data-value])
      slots_used                    — Slots de fundación usados (parte izquierda de td.slo),
                                      o None si el formato no es parseable.
      slots_total                   — Slots de fundación totales (parte derecha de td.slo),
                                      o None si el formato no es parseable.
                                      Puede ser 0 con slots_used > 0 (EC-04, estado válido).
    """
    game_id:                       int
    name:                          str
    cp_per_day:                    int
    celebration_seconds_remaining: int | None
    slots_used:                    int | None
    slots_total:                   int | None


@dataclass(frozen=True)
class CulturePointsSummary:
    """
    Resumen de culture points de todas las aldeas del jugador.

    Campos:
      villages         — Lista de VillageCulturePoints (una por aldea; tr.sum NO incluida)
      cp_total_per_day — CP/día total de la fila tr.sum (td.cps de tr.sum)
      slots_used_total — Slots usados totales de la fila tr.sum (parte izquierda de td.slo)
      slots_total      — Slots totales de la fila tr.sum (parte derecha de td.slo);
                         None si el formato de td.slo en tr.sum no es parseable.
    """
    villages:         list[VillageCulturePoints]
    cp_total_per_day: int
    slots_used_total: int | None
    slots_total:      int | None
