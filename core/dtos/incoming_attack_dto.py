"""
DTOs del radar de ataques entrantes.

Componente A (VillageUnderAttackDTO): resultado del parser de sidebar.
Componente B (Dorf1AttackDTO): resultado del parser de dorf1.
Componente C (RallyPointAttackDTO): resultado de RallyPointParser — GAP-02 cerrado (v4).
Componente D (VillageProfileDTO): resultado de VillageProfileParser — GAP-03 cerrado (v4).

Ver spec docs/specs/radar-ataques-entrantes.md §7.
Añadido en la feature radar-ataques-entrantes (2026-06-05).
Actualizado v4 (2026-06-07): RallyPointAttackDTO y VillageProfileDTO con campos reales
del fixture (GAP-02 y GAP-03 cerrados).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VillageUnderAttackDTO:
    """
    Resultado del Componente A (sidebar).
    Identifica una aldea propia con ataque entrante.
    Discriminador: clase CSS 'attack' en div.listEntry.village (GAP-01 cerrado).
    """
    village_game_id: int        # data-did del div.listEntry.village.attack
    village_name:    str        # texto de span.name
    coord_x:         int        # valor de span.coordinateX (sin paréntesis)
    coord_y:         int        # valor de span.coordinateY (sin paréntesis)


@dataclass(frozen=True)
class Dorf1AttackDTO:
    """
    Resultado del Componente B (dorf1).
    Un bloque de ataque entrante con timer.
    Solo ataques entrantes (img.att1); los salientes (img.att2) se ignoran.
    """
    attack_count:       int         # número extraído de span.a1 con regex \d+
    seconds_to_impact:  int         # value de span.timer (o data-value como fallback)
    rally_point_href:   str         # href del <a> que envuelve img.att1


@dataclass(frozen=True)
class RallyPointAttackDTO:
    """
    Resultado del Componente C (rally point).
    Verificado contra fixture troop_details_in_attack.html — GAP-02 cerrado (v4).

    Campos:
      attacker_name         — primer token del texto de troopHeadline <a> (RT-11).
      origin_village_name   — siempre None en Comp. C; se rellena en Comp. D (RT-13).
      origin_village_coord_x/y — coords del tbody.units th.coords (puede ser None).
      origin_village_href   — href del <a> de troopHeadline (karte.php?d=NNN).
      operation_type        — 'attack' por defecto; 'spy' si solo hay exploradores (RN-28).
      impact_at_display     — texto verbatim de div.at span ("at 09:31:38").
      seconds_to_impact     — value de tbody.infos span.timer.
      tribe                 — Tribe.value desde unit_class_to_tribe_ordinal(uNN) (RN-26).
      troops                — {unit_class: count} p.ej. {"u22": 2, "u21": 0, ...}.
    """
    attacker_name:          str | None
    origin_village_name:    str | None   # None en Comp. C — viene de Comp. D (RT-13)
    origin_village_coord_x: int | None
    origin_village_coord_y: int | None
    origin_village_href:    str | None
    operation_type:         str          # 'attack' | 'spy' (default 'attack' — RN-28)
    impact_at_display:      str | None   # texto verbatim "at 09:31:38"
    seconds_to_impact:      int | None
    tribe:                  str | None   # Tribe.value (p.ej. 'gauls') o None
    troops:                 dict = field(default_factory=dict)  # {unit_class: count}


@dataclass(frozen=True)
class VillageProfileDTO:
    """
    Resultado del Componente D (ficha del atacante en karte.php).
    Verificado contra fixture karte_tile_attacker_dialog.html — GAP-03 cerrado (v4).

    Campos:
      village_name   — texto del h1.titleInHeader antes del primer '('.
      coord_x/y      — de .coordinateX/.coordinateY dentro del h1.
      player_name    — texto de #village_info td.player a.
      player_href    — href completo de td.player a (contiene /profile/NNN).
      alliance_name  — texto de td.alliance a.
      alliance_href  — href de td.alliance a (contiene /alliance/N).
      tribe          — fallback desde village-N → TRIBE_BY_VILLAGE_CLASS (RN-27).
      population     — primer valor numérico en filas de #village_info.
    """
    village_name:   str | None
    coord_x:        int
    coord_y:        int
    player_name:    str | None
    player_href:    str | None
    alliance_name:  str | None
    alliance_href:  str | None
    tribe:          str | None      # código de tribu ('romans', 'gauls', etc.) o None
    population:     int | None
