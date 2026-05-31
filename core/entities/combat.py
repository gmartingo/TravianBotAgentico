"""
Entidades del dominio de combate — Simulador y Optimizador de Travian.

Todas son dataclasses inmutables (no persistidas en BD).
Se crean durante el cálculo y se serializa el resultado al router.

Ver spec §7 para la definición completa de cada entidad.
Añadidas en la feature simulador-combate (2026-05-29).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.entities.tribe import Tribe


# ---------------------------------------------------------------------------
# Entidades de INPUT
# ---------------------------------------------------------------------------


@dataclass
class TroopEntry:
    """Tropa atacante o defensora con cantidad conocida."""
    tribe: Tribe
    ordinal: int        # ordinal 1-based dentro de la tribu
    quantity: int       # 1..1_000_000
    smithy_level: int = 0  # 0..20


@dataclass
class TroopTypeSpec:
    """Tipo de tropa sin cantidad — Modo A del optimizador."""
    tribe: Tribe
    ordinal: int
    smithy_level: int = 0  # 0..20


@dataclass
class TroopAvailability:
    """Tipo de tropa con cantidad máxima — Modo B del optimizador."""
    tribe: Tribe
    ordinal: int
    quantity_available: int  # cantidad máxima que puede enviar
    smithy_level: int = 0    # 0..20


@dataclass
class AttackerArtifacts:
    """Artefactos del atacante (multiplicadores declarativos, sin validación de negocio)."""
    fast_troops: float = 1.0  # multiplicador de velocidad de marcha
    diet: float = 1.0         # multiplicador de consumo de crop


@dataclass
class DefenderArtifacts:
    """Artefactos del defensor (presentes para compatibilidad de contrato v2)."""
    strong_buildings: float = 1.0  # multiplicador durabilidad vs catapultas (futuro)
    great_cranny: float = 1.0      # multiplicador cranny (futuro)


@dataclass
class CatapultTarget:
    """Edificio objetivo de catapultas en modo attack."""
    building_gid: int   # gid del edificio objetivo
    current_level: int  # nivel actual del edificio (0..20)


@dataclass
class RamSpec:
    """Arietes con nivel de herrería."""
    quantity: int       # número de arietes (0..1_000_000; 0 = sin arietes)
    smithy_level: int = 0  # nivel de smithy del ariet (0..20)


@dataclass
class AttackerFormation:
    """Ejército atacante completo con todos sus modificadores."""
    tribe: Tribe
    troops: list[TroopEntry]
    attack_type: str = "raid"              # "attack" | "raid"
    hero_attack_points: float = 0.0        # puntos propios del héroe (0..20000)
    hero_attack_bonus_percent: float = 0.0 # bonus % sobre el ejército (0..100)
    alliance_bonus: float = 0.0            # 0..5 (%)
    morale: float = 100.0                  # 30..100 (clampea con warning)
    artifacts: AttackerArtifacts = field(default_factory=AttackerArtifacts)
    catapult_targets: list[CatapultTarget] = field(default_factory=list)
    rams: RamSpec | None = None


@dataclass
class DefenderFormation:
    """Un ejército defensor dentro de la lista de formaciones defensoras."""
    tribe: Tribe | None
    troops: list[TroopEntry]
    hero_defense_points: float = 0.0        # puntos propios del héroe defensor
    hero_defense_bonus_percent: float = 0.0 # bonus % sobre la defensa
    artifacts: DefenderArtifacts = field(default_factory=DefenderArtifacts)
    village_resources: int | None = None    # recursos del objetivo (para loot.potential)


@dataclass
class WallConfig:
    """Configuración del muro defensor."""
    wall_level: int = 0         # 0..20
    stonemason_level: int = 0   # 0..5
    wall_tribe: Tribe | None = None  # None → fallback 0.03×nivel


@dataclass
class CombatConfig:
    """Parámetros de configuración del cálculo de combate.

    El exponente K (1.5..1.2578) NO es input: se calcula en runtime desde el
    total de tropas en el campo (ver combat_engine.compute_k).
    """
    server_speed: float = 1.0          # 1..10 (divisor de velocidad)
    distance_fields: float | None = None  # distancia en campos; None → sin crop


# ---------------------------------------------------------------------------
# Entidades de OUTPUT
# ---------------------------------------------------------------------------


@dataclass
class TroopResult:
    """Tropa con resultado del combate (supervivientes, bajas, nombre e icono)."""
    tribe: Tribe
    ordinal: int
    name: str               # nombre localizado
    icon_url: str | None    # /static/icons/{icon_id}.png o None
    quantity_initial: int
    quantity_survived: int
    quantity_lost: int


@dataclass
class TroopResourceLoss:
    """Desglose de coste en recursos para un tipo de tropa perdida."""
    tribe: Tribe
    ordinal: int
    name: str
    quantity_lost: int
    cost_per_unit: dict     # {"wood": int, "clay": int, "iron": int, "crop": int}
    total_cost: dict        # {"wood": int, "clay": int, "iron": int, "crop": int}


@dataclass
class ResourceLossesBand:
    """Coste total en recursos de bajas para un bando (atacante o defensor)."""
    total_resources: int              # Σ(quantity_lost_i × cost_sum_i)
    breakdown: list[TroopResourceLoss]


@dataclass
class ResourceLosses:
    """Coste en recursos de bajas, desglosado por bando."""
    attacker: ResourceLossesBand
    defender: ResourceLossesBand


@dataclass
class AnimalResourceDrop:
    """Recursos obtenidos de animales de naturaleza muertos, desglosados por tipo."""
    wood: int
    clay: int
    iron: int
    crop: int
    total: int  # = wood + clay + iron + crop


@dataclass
class Loot:
    """Botín del ataque — capacidad de carga y recursos obtenidos."""
    capacity: int                                    # cap total de supervivientes atacantes
    potential: int | None                            # min(village_resources, capacity)
    resources_gained_from_animals: AnimalResourceDrop | None
    # None cuando no hay tropas NATURE entre los defensores muertos


@dataclass
class CatapultResult:
    """Resultado de daño de catapultas en un edificio objetivo."""
    building_gid: int
    level_before: int
    level_after: int
    hits: int


@dataclass
class StructuralDamage:
    """Daño estructural total del ataque (solo cuando attack_type='attack')."""
    catapult_results: list[CatapultResult]  # vacío si no hay catapultas o targets
    wall_before: int
    wall_after: int


@dataclass
class CombatResult:
    """Resultado completo de una simulación de combate."""
    attacker_wins: bool
    attacker_troops: list[TroopResult]
    defender_troops: list[TroopResult]   # aplanado: todas las formaciones juntas
    attacker_power: float                # A efectivo (total)
    defender_power: float                # D efectivo (total)
    ratio: float | None                  # A/D — None cuando defender_power == 0
    loot: Loot
    resource_losses: ResourceLosses
    structural_damage: StructuralDamage | None  # None si attack_type='raid'
    crop_consumption: int | None               # None si distance_fields no proporcionado
    warnings: list[str]
    # Desglose de potencia infantería vs caballería (raw, antes de moral/muro).
    # Permite a la UI separar la fila "Fuerza de combate" en dos líneas con
    # iconos del juego (stat_attack / stat_def_infantry / stat_def_cavalry).
    attacker_infantry_power: float = 0.0     # A_inf — ataque hecho por infantería atacante
    attacker_cavalry_power: float = 0.0      # A_cav — ataque hecho por caballería atacante
    defender_infantry_power: float = 0.0     # Σ(qty × def_inf) — defensa total contra infantería
    defender_cavalry_power: float = 0.0      # Σ(qty × def_cav) — defensa total contra caballería


# ---------------------------------------------------------------------------
# Entidades del OPTIMIZADOR
# ---------------------------------------------------------------------------


@dataclass
class OptimizationWeights:
    """Pesos de los objetivos del optimizador multi-objetivo."""
    resources_gained: float = 1.0  # maximizar recursos de animales
    total_losses: float = 1.0      # minimizar coste en recursos de bajas
    troops_sent: float = 0.5       # minimizar tropas enviadas
    travel_time: float = 0.0       # minimizar tiempo de marcha
    balance: float = 0.0           # minimizar desequilibrio de uso del inventario (0.0 = sin efecto)


@dataclass
class OptimizationConfig:
    """Configuración del optimizador. K se calcula dinámicamente, igual que en CombatConfig."""
    server_speed: float = 1.0
    distance_fields: float | None = None
    top_n: int = 3                   # 1..10
    optimization_weights: OptimizationWeights = field(
        default_factory=OptimizationWeights
    )
    # scoring_mode (RN-04): "single" puntúa cada alternativa por-raid (compatible);
    # "aggregate" multiplica los términos de loot/pérdidas/tropas/tiempo por N efectivo.
    # Solo Modo C lo activa.
    scoring_mode: str = "single"     # "single" | "aggregate"
    # n_min/n_max (RN-05): acotan N efectivo en modo aggregate. None = sin límite.
    n_min: int | None = None
    n_max: int | None = None


@dataclass
class MultiRaidAggregate:
    """Totales acumulados de N raids idénticas."""
    n_raids: int
    total_resources_gained: AnimalResourceDrop   # N × resources_gained de la oleada
    total_resource_losses: int                   # N × total_resource_losses del atacante
    total_troops_sent: int                       # N × troops_sent_count
    total_travel_time_h: float | None            # N × travel_time_h; None si sin distancia


@dataclass
class OptimizationAlternative:
    """Una alternativa del frente de Pareto devuelta por el optimizador."""
    rank: int                         # 1 = mejor según criterio
    is_winning: bool
    troops_sent: list[TroopResult]
    total_losses: int                 # Σ(quantity_lost) — conteo de unidades
    total_resource_losses: int        # coste en recursos de bajas del atacante
    troops_sent_count: int            # Σ(quantity_sent)
    attacker_power: float
    defender_power: float
    ratio: float
    resources_gained: AnimalResourceDrop | None  # null si sin tropas NATURE
    loot: Loot | None                # null en optimizador (sin village_resources)
    travel_time_h: float | None      # null si no se proporcionó distance_fields
    raids_possible: int | None = None              # None si sin inventario (Modo A)
    remaining_troops: list[TroopResult] | None = None  # None si sin inventario
    aggregate: MultiRaidAggregate | None = None    # None si sin inventario
    # Desglose por recurso del coste de tropas perdidas del atacante (POR-RAID).
    # Permite a la UI calcular el neto madera/barro/hierro/cereal contra el botín
    # de animales. La suma .total == total_resource_losses por construcción.
    resource_losses_breakdown: AnimalResourceDrop | None = None
    # Desglose de potencia infantería vs caballería para la fila "Fuerza de
    # combate" partida en 2 en la UI (mismo origen que SimulateResult).
    attacker_infantry_power: float = 0.0
    attacker_cavalry_power: float = 0.0
    defender_infantry_power: float = 0.0
    defender_cavalry_power: float = 0.0


@dataclass
class OptimizationResult:
    """Resultado del optimizador — frente de Pareto de combinaciones de tropas."""
    alternatives: list[OptimizationAlternative]  # nunca vacío
    has_winning_combination: bool
    defender_troops: list[TroopResult]           # defensa del oasis (referencia)
    warnings: list[str]
    message: str | None  # mensaje cuando has_winning_combination=False
