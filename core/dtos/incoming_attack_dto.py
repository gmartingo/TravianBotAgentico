"""
DTOs del radar de ataques entrantes.

Componente A (VillageUnderAttackDTO): resultado del parser de sidebar.
Componente B (Dorf1AttackDTO): resultado del parser de dorf1.
Componentes C y D (RallyPointAttackDTO, VillageProfileDTO): contratos de diseño,
parsers BLOQUEADOS hasta recibir fixtures GAP-02 / GAP-03.

Ver spec docs/specs/radar-ataques-entrantes.md §7.
Añadido en la feature radar-ataques-entrantes (2026-06-05).
"""
from __future__ import annotations

from dataclasses import dataclass


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
    Resultado del Componente C (rally point) — CONTRATO DESEADO.
    Parser BLOQUEADO hasta recibir fixture GAP-02.
    """
    attacker_name:       str        # nombre del jugador atacante
    origin_village_name: str        # nombre de la aldea de origen
    origin_village_href: str        # href de la ficha de la aldea atacante (para Comp.D)
    operation_type:      str        # 'attack' | 'raid' | 'spy' | 'reinforce'
    impact_at_display:   str        # hora de impacto tal como aparece en la tabla


@dataclass(frozen=True)
class VillageProfileDTO:
    """
    Resultado del Componente D (ficha del atacante) — CONTRATO DESEADO.
    Parser BLOQUEADO hasta recibir fixture GAP-03.
    """
    village_name:   str
    coord_x:        int
    coord_y:        int
    player_name:    str | None
    tribe:          str | None      # código de tribu ('romans', 'teutons', etc.)
    population:     int | None
