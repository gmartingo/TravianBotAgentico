"""
Entidades del dominio de ataques a oasis — BD de reportes de ataque.

Todas son dataclasses. AttackReportPreview es el resultado in-memory del parser
(nunca persistida directamente). Las demás son DTOs para serialización.

Ver spec docs/specs/bd-ataques-oasis.md §7 y §14 para la definición completa.
Añadidas en la feature bd-ataques-oasis (2026-05-30).

Corrección C2 del spec: hero_inventory es campo RAÍZ de AttackReportPreview,
NO va dentro de BountyData. BountyData solo contiene recursos de drop + capacidad.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Entidades de filas hijas
# ---------------------------------------------------------------------------


@dataclass
class AnimalEntry:
    """Un tipo de animal en la sección de defensor (Nature).

    §17.5 (delta reporte perdido): present/killed/survived son int | None.
      - None  → desconocido: el atacante perdió y Travian ocultó las cantidades.
      - 0     → oasis vacío de ese tipo de animal (semánticamente distinto de None).

    Precedente: AttackerTroopEntry.troop_ordinal: int | None (mismo fichero).
    """
    animal_ordinal: int          # 1=Rata … 10=Elefante
    animal_name: str             # nombre localizado tal como aparece en el reporte
    present: int | None          # presentes al inicio del combate; None si reporte perdido
    killed: int | None           # muertos en el combate; None si reporte perdido
    survived: int | None         # = present - killed (calculado al parsear); None si reporte perdido


@dataclass
class AttackerTroopEntry:
    """Un tipo de tropa en la sección de atacante."""
    troop_name: str              # nombre tal como aparece en el reporte
    troop_ordinal: int | None    # None si el nombre es ambiguo entre tribus (RN-03)
    sent: int                    # tropas enviadas
    lost: int                    # tropas perdidas
    survived: int                # = sent - lost (calculado al parsear)


@dataclass
class BountyData:
    """
    Recursos del drop de animales + capacidad de carga.

    IMPORTANTE (C2): hero_inventory NO va aquí. Es campo raíz de AttackReportPreview.
    Solo contiene los 6 campos de recursos del botín y la capacidad.
    """
    wood: int
    clay: int
    iron: int
    crop: int
    capacity_used: int
    capacity_total: int


# ---------------------------------------------------------------------------
# Preview — resultado del parser (in-memory, no persistida)
# ---------------------------------------------------------------------------


@dataclass
class AttackReportPreview:
    """
    Resultado del parser: todos los datos del reporte parseados y normalizados.

    Se usa como DTO de respuesta del endpoint POST /attack-reports/parse (EP-01)
    y como entrada de save_report() en el puerto de persistencia.

    El campo hero_inventory (C2) está en primer nivel, separado de bounty.
    Al serializar el response JSON, debe quedar:
      { ..., "bounty": { wood, clay, iron, crop, capacity_used, capacity_total },
             "hero_inventory": null | { wood, clay, iron, crop }, ... }
    """
    attacked_at: str                    # ISO 8601 UTC (o server-local si sin offset)
    utc_offset: str | None              # "+01:00" o None si no disponible
    coord_x_dest: int
    coord_y_dest: int
    origin_village_name: str
    attacker_troops: list[AttackerTroopEntry]
    animals: list[AnimalEntry]
    bounty: BountyData
    hero_inventory: dict | None         # CAMPO RAÍZ (C2): {wood, clay, iron, crop} o None
    already_exists: bool = False
    existing_id: int | None = None
    attacker_tribe: str | None = None   # tribu deducida del roster (gauls, romans…) para iconos
