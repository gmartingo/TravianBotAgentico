"""
Motor de combate — fórmula Travian T4.5 completa.

Implementa simulate_combat() y sus helpers auxiliares.
Toda la lógica es pura (sin I/O) salvo las llamadas a ports (async).

Ver spec §RN-01..RN-13 y §9 (flujo lógico paso a paso).
Añadido en la feature simulador-combate (2026-05-29).
"""
from __future__ import annotations

import asyncio
from math import floor


# ---------------------------------------------------------------------------
# Factor K — "involved factor" de Travian T4.5 (fuente: kirilloid)
# ---------------------------------------------------------------------------

def compute_k(total_units: int) -> float:
    """
    Calcula el exponente K de la fórmula de bajas según el total de tropas.

    Travian T4.5 (verificado contra kirilloid):
      - N <= 1000:  K = 1.5
      - N >  1000:  K = 2 * (1.8592 - N^0.015)   (rango 1.2578 .. 1.5)

    `total_units` es la suma de TODAS las tropas (atacante + defensor) en el campo.
    """
    if total_units <= 1000:
        return 1.5
    return 2.0 * (1.8592 - total_units ** 0.015)

from core.entities.combat import (
    AnimalResourceDrop,
    AttackerFormation,
    CatapultResult,
    CombatConfig,
    CombatResult,
    DefenderFormation,
    Loot,
    ResourceLosses,
    ResourceLossesBand,
    StructuralDamage,
    TroopResourceLoss,
    TroopResult,
    WallConfig,
)
from core.entities.tribe import Tribe
from core.ports.game_data_port import GameDataPort
from core.ports.translation_port import TranslationPort
from core.use_cases.nature_animal_drops import NATURE_DROPS, get_nature_drop

# ---------------------------------------------------------------------------
# Tablas estáticas de clasificación de tropas por tribu
# ---------------------------------------------------------------------------

# Tropas de infantería por tribu (ordenadas por ordinal).
# Las de caballería son las que NO están aquí y no son arietes/catapultas/héroes/etc.
# Criterio: infantería = todo lo que no es caballería en la tribu jugable estándar de Travian.
#
# Travian T4.5 — verificado contra kirilloid:
#   Romans:    1=Legionario, 2=Pretoriano, 3=Impedido, 4=Equites Legati(cav), 5=Equites Imperatoris(cav),
#              6=Equites Caesaris(cav), 7=Carnero(ariet), 8=Catapulta, 9=Senador, 10=Asentista
#   Teutons:   1=Espadachín, 2=Lancero, 3=Exploradora(cav inf debatible→cav), 4=Paladin(cav), 5=Caballero Teutón(cav),
#              6=Ariete, 7=Ariete de madera, 8=Catapulta, 9=Cabecilla, 10=Asentista
#   Gauls:     1=Falanx, 2=Guerrero de la espada, 3=Jinete galo(cav), 4=Lanzacabezas(cav), 5=Druida(cav),
#              6=Haeduan(cav), 7=Ariete de madera, 8=Cat. de guerra, 9=Cacique, 10=Asentista
#
# Simplificación práctica: clasificación por ordinal (Travian T4.5 es estático).
# La clasificación afecta al cálculo de proporción cav para la defensa mixta (RN-05).

# Ordinales de caballería para cada tribu jugable
_CAVALRY_ORDINALS: dict[Tribe, frozenset[int]] = {
    Tribe.ROMANS:    frozenset({4, 5, 6}),    # Equites Legati, Imperatoris, Caesaris
    Tribe.TEUTONS:   frozenset({4, 5}),       # Paladin, Caballero Teutón
    Tribe.GAULS:     frozenset({3, 4, 5, 6}), # Jinete, Lanzacabezas, Druida, Haeduan
    Tribe.EGYPTIANS: frozenset({4, 5, 6}),    # Khopesh, Sopdu, Resheph (caballería similar)
    Tribe.HUNS:      frozenset({1, 2, 3, 4, 5}),  # Huns son mayoritariamente caballería
    Tribe.SPARTANS:  frozenset({4, 5, 6}),
    Tribe.VIKINGS:   frozenset({4, 5, 6}),
    Tribe.NATURE:    frozenset(),              # NPC: todos infantería
    Tribe.NATARS:    frozenset(),              # NPC: todos infantería
}

# Ordinal del ariet por tribu (siempre ordinal 7 en T4.5 — verificado)
_RAM_ORDINALS: dict[Tribe, int] = {
    Tribe.ROMANS:    7,
    Tribe.TEUTONS:   7,
    Tribe.GAULS:     7,
    Tribe.EGYPTIANS: 7,
    Tribe.HUNS:      7,
    Tribe.SPARTANS:  7,
    Tribe.VIKINGS:   7,
}

# Ordinal de la catapulta por tribu (siempre ordinal 8 en T4.5 — verificado)
_CATAPULT_ORDINALS: dict[Tribe, int] = {
    Tribe.ROMANS:    8,
    Tribe.TEUTONS:   8,
    Tribe.GAULS:     8,
    Tribe.EGYPTIANS: 8,
    Tribe.HUNS:      8,
    Tribe.SPARTANS:  8,
    Tribe.VIKINGS:   8,
}

# gid del edificio de muro por tribu (Travian T4.5 — spec §RN-03)
WALL_GID_BY_TRIBE: dict[Tribe, int] = {
    Tribe.ROMANS:    40,  # City Wall
    Tribe.TEUTONS:   41,  # Earth Wall
    Tribe.GAULS:     42,  # Palisade
    Tribe.EGYPTIANS: 43,  # Stone Wall
    # Huns, Spartans, Vikings: pendiente verificación de gid en BD tras scraping
}


# ---------------------------------------------------------------------------
# Helpers de clasificación (puras, sin I/O)
# ---------------------------------------------------------------------------

def is_cavalry(tribe: Tribe, ordinal: int) -> bool:
    """True si la tropa es caballería para la tribu dada."""
    return ordinal in _CAVALRY_ORDINALS.get(tribe, frozenset())


def is_infantry(tribe: Tribe, ordinal: int) -> bool:
    """True si la tropa es infantería (todo lo que no es caballería)."""
    return not is_cavalry(tribe, ordinal)


def is_ram(tribe: Tribe, ordinal: int) -> bool:
    """True si la tropa es un ariet para la tribu dada."""
    return _RAM_ORDINALS.get(tribe) == ordinal


def is_catapult(tribe: Tribe, ordinal: int) -> bool:
    """True si la tropa es una catapulta para la tribu dada."""
    return _CATAPULT_ORDINALS.get(tribe) == ordinal


# ---------------------------------------------------------------------------
# Helper: aplicar modificador de smithy (RN-02)
# ---------------------------------------------------------------------------

async def apply_smithy(
    base_stat: int | None,
    tribe: Tribe,
    ordinal: int,
    smithy_level: int,
    game_data_port: GameDataPort,
    warnings: list[str],
    stat: str,
    server_version: str = "1.45",
) -> float:
    """
    Aplica el modificador de smithy sobre un stat base.

    Retorna base_stat × (1 + mejora_porcentual / 100) para el nivel de smithy dado.
    Si no hay upgrades en BD, devuelve el stat base con warning.
    Si smithy_level > max disponible, clampea al máximo con warning.
    """
    if base_stat is None:
        return 0.0
    if smithy_level == 0:
        return float(base_stat)

    upgrades = await game_data_port.get_troop_upgrades(tribe, ordinal, server_version)
    # Filtrar upgrades para el stat pedido
    stat_upgrades = [u for u in upgrades if u["stat_name"] == stat]

    if not stat_upgrades:
        warnings.append(
            f"Sin datos de upgrade para {tribe.value}/{ordinal} stat={stat} "
            f"— usando stat base sin modificador de smithy."
        )
        return float(base_stat)

    max_level = max(u["level"] for u in stat_upgrades)
    effective_level = smithy_level
    if smithy_level > max_level:
        warnings.append(
            f"Nivel smithy {smithy_level} > máximo disponible ({max_level}) "
            f"para {tribe.value}/{ordinal} stat={stat} — clampeado a {max_level}."
        )
        effective_level = max_level

    # Buscar el stat_value para el nivel efectivo
    row = next(
        (u for u in stat_upgrades if u["level"] == effective_level),
        None
    )
    if row is None:
        # Nivel no encontrado (huecos en la tabla): usar el máximo disponible
        row = max(stat_upgrades, key=lambda u: u["level"])
        warnings.append(
            f"Nivel {effective_level} no encontrado en upgrades de {tribe.value}/{ordinal} "
            f"stat={stat} — usando nivel {row['level']}."
        )

    # stat_value es el valor absoluto mejorado (no el delta)
    return float(row["stat_value"])


# ---------------------------------------------------------------------------
# Helper: resolver multiplicador de muro (RN-03)
# ---------------------------------------------------------------------------

async def resolve_wall_multiplier(
    wall: WallConfig,
    game_data_port: GameDataPort,
    warnings: list[str],
) -> float:
    """
    Calcula el multiplicador de muro (1 + bonus) × stonemason_mult.

    Obtiene el bonus desde GameDataPort si wall_tribe está especificado;
    usa la aproximación 0.03×nivel si no hay datos o no se especificó tribu.
    """
    stonemason_mult = 1.0 + 0.05 * wall.stonemason_level

    if wall.wall_level == 0:
        return stonemason_mult  # sin muro; stonemason aún aplica

    if wall.wall_tribe is None:
        warnings.append(
            "wall_tribe no especificado — usando aproximación 3% por nivel de muro."
        )
        return (1.0 + wall.wall_level * 0.03) * stonemason_mult

    wall_gid = WALL_GID_BY_TRIBE.get(wall.wall_tribe)
    if wall_gid is None:
        warnings.append(
            f"No se conoce el gid del muro para la tribu {wall.wall_tribe.value} "
            f"— usando aproximación 3% por nivel."
        )
        return (1.0 + wall.wall_level * 0.03) * stonemason_mult

    bonus = await game_data_port.get_building_defense_bonus(wall_gid, wall.wall_level)
    if bonus is None:
        warnings.append(
            f"Sin datos de edificio gid={wall_gid} nivel={wall.wall_level} en BD "
            f"— usando aproximación 3% por nivel."
        )
        return (1.0 + wall.wall_level * 0.03) * stonemason_mult

    return (1.0 + bonus) * stonemason_mult


# ---------------------------------------------------------------------------
# Helper: nombre e icono de tropa
# ---------------------------------------------------------------------------

async def _resolve_troop_display(
    tribe: Tribe,
    ordinal: int,
    lang: str,
    translation_port: TranslationPort,
    game_data_port: GameDataPort,
) -> tuple[str, str | None]:
    """
    Devuelve (nombre_localizado, icon_url) para una tropa.

    icon_url es None si no hay icon_id en BD (EC-15).
    """
    name = translation_port.get_troop_name(tribe, ordinal, lang)

    # Obtener icon_id desde los stats de la tropa
    stats = await game_data_port.get_troop_stats(tribe, ordinal)
    icon_id = stats["icon_id"] if stats else None
    icon_url = f"/static/icons/{icon_id}.png" if icon_id else None

    return name, icon_url


# ---------------------------------------------------------------------------
# Helper: construir TroopResult list
# ---------------------------------------------------------------------------

async def build_troop_results(
    enriched: list[dict],
    survived: list[int],
    lang: str,
    translation_port: TranslationPort,
    game_data_port: GameDataPort,
) -> list[TroopResult]:
    """Construye la lista de TroopResult con nombres, iconos y supervivientes."""
    results = []
    for i, e in enumerate(enriched):
        tribe = e["tribe"] if isinstance(e["tribe"], Tribe) else Tribe(e["tribe"])
        ordinal = e["ordinal"]
        qty_initial = e["quantity"]
        qty_survived = survived[i]
        qty_lost = qty_initial - qty_survived

        name, icon_url = await _resolve_troop_display(
            tribe, ordinal, lang, translation_port, game_data_port
        )

        results.append(TroopResult(
            tribe=tribe,
            ordinal=ordinal,
            name=name,
            icon_url=icon_url,
            quantity_initial=qty_initial,
            quantity_survived=qty_survived,
            quantity_lost=qty_lost,
        ))
    return results


# ---------------------------------------------------------------------------
# Helper: coste en recursos de bajas (RN-09)
# ---------------------------------------------------------------------------

def _compute_resource_losses(
    enriched: list[dict],
    lost_quantities: list[int],
    lang: str,
    translation_port: TranslationPort,
) -> ResourceLossesBand:
    """
    Calcula el coste en recursos de las bajas de un bando.

    Para tropas NATURE el cost_sum = 0, por lo que total_resources = 0.
    El breakdown se incluye igualmente para consistencia.
    """
    total_resources = 0
    breakdown: list[TroopResourceLoss] = []

    for i, e in enumerate(enriched):
        qty_lost = lost_quantities[i]
        if qty_lost == 0:
            continue

        stats = e["stats"]
        tribe = e["tribe"] if isinstance(e["tribe"], Tribe) else Tribe(e["tribe"])
        ordinal = e["ordinal"]
        cost_per_unit = {
            "wood":  stats.get("cost_wood", 0) or 0,
            "clay":  stats.get("cost_clay", 0) or 0,
            "iron":  stats.get("cost_iron", 0) or 0,
            "crop":  stats.get("cost_crop", 0) or 0,
        }
        total_cost = {k: qty_lost * v for k, v in cost_per_unit.items()}
        cost_sum = stats.get("cost_sum", 0) or 0
        total_resources += qty_lost * cost_sum

        name = translation_port.get_troop_name(tribe, ordinal, lang)

        breakdown.append(TroopResourceLoss(
            tribe=tribe,
            ordinal=ordinal,
            name=name,
            quantity_lost=qty_lost,
            cost_per_unit=cost_per_unit,
            total_cost=total_cost,
        ))

    return ResourceLossesBand(
        total_resources=total_resources,
        breakdown=breakdown,
    )


# ---------------------------------------------------------------------------
# Helper: calcular loot (RN-07 + RN-08)
# ---------------------------------------------------------------------------

def _compute_loot(
    atk_enriched: list[dict],
    atk_survived: list[int],
    all_def_enriched: list[dict],
    def_survived: list[int],
    defenders: list[DefenderFormation],
    attacker_wins: bool,
) -> Loot:
    """Calcula el botín del ataque."""
    # Capacidad de carga de supervivientes atacantes
    loot_capacity = sum(
        (e["stats"].get("carry", 0) or 0) * atk_survived[i]
        for i, e in enumerate(atk_enriched)
    )

    # Loot potential: solo si el atacante gana y hay village_resources en el primer defensor
    loot_potential: int | None = None
    if attacker_wins and defenders:
        vr = defenders[0].village_resources
        if vr is not None:
            loot_potential = min(vr, loot_capacity)

    # Recursos de animales muertos (RN-08)
    nature_killed: list[tuple[int, int]] = []
    for i, e in enumerate(all_def_enriched):
        tribe = e["tribe"] if isinstance(e["tribe"], Tribe) else Tribe(e["tribe"])
        if tribe == Tribe.NATURE:
            killed = e["quantity"] - def_survived[i]
            if killed > 0:
                nature_killed.append((killed, e["ordinal"]))

    if nature_killed:
        drop_wood = sum(k * get_nature_drop(o, "wood") for k, o in nature_killed)
        drop_clay = sum(k * get_nature_drop(o, "clay") for k, o in nature_killed)
        drop_iron = sum(k * get_nature_drop(o, "iron") for k, o in nature_killed)
        drop_crop = sum(k * get_nature_drop(o, "crop") for k, o in nature_killed)
        resources_from_animals: AnimalResourceDrop | None = AnimalResourceDrop(
            wood=drop_wood,
            clay=drop_clay,
            iron=drop_iron,
            crop=drop_crop,
            total=drop_wood + drop_clay + drop_iron + drop_crop,
        )
    else:
        resources_from_animals = None

    return Loot(
        capacity=loot_capacity,
        potential=loot_potential,
        resources_gained_from_animals=resources_from_animals,
    )


# ---------------------------------------------------------------------------
# Helper: daño estructural (RN-13)
# ---------------------------------------------------------------------------

async def _compute_structural_damage(
    attacker: AttackerFormation,
    atk_enriched: list[dict],
    atk_survived: list[int],
    wall: WallConfig,
    defenders: list[DefenderFormation],
    game_data_port: GameDataPort,
    warnings: list[str],
    attacker_wins: bool,
) -> StructuralDamage:
    """
    Calcula el daño estructural (catapultas + arietes).
    Solo se llama cuando attack_type='attack'.
    """
    catapult_results: list[CatapultResult] = []
    wall_before = wall.wall_level
    wall_after = wall_before

    if not attacker_wins:
        # Las catapultas y arietes no disparan si el atacante pierde
        return StructuralDamage(
            catapult_results=[],
            wall_before=wall_before,
            wall_after=wall_after,
        )

    # Catapultas supervivientes
    catapults_survived = sum(
        atk_survived[i]
        for i, e in enumerate(atk_enriched)
        if is_catapult(attacker.tribe, e["ordinal"])
    )

    # Daño de catapultas a edificios objetivo
    if attacker.catapult_targets and catapults_survived > 0:
        for target in attacker.catapult_targets:
            hits = floor(catapults_survived * 0.8)
            levels_destroyed = floor(hits / (target.current_level + 1))
            new_level = max(0, target.current_level - levels_destroyed)
            catapult_results.append(CatapultResult(
                building_gid=target.building_gid,
                level_before=target.current_level,
                level_after=new_level,
                hits=hits,
            ))

    # Arietes sobre el muro
    if attacker.rams and attacker.rams.quantity > 0 and wall.wall_level > 0:
        rams_survived = sum(
            atk_survived[i]
            for i, e in enumerate(atk_enriched)
            if is_ram(attacker.tribe, e["ordinal"])
        )

        if rams_survived > 0:
            # Stat de ataque del ariet
            ram_stats = await game_data_port.get_troop_stats(
                attacker.tribe, _RAM_ORDINALS.get(attacker.tribe, 7)
            )
            ram_attack = (ram_stats["attack"] or 0) if ram_stats else 0

            # strong_buildings del primer defensor (default 1.0)
            strong_buildings = (
                defenders[0].artifacts.strong_buildings if defenders else 1.0
            )

            # Bonus de muro para calcular resistencia
            wall_gid = WALL_GID_BY_TRIBE.get(wall.wall_tribe) if wall.wall_tribe else None
            if wall_gid:
                wall_bonus = await game_data_port.get_building_defense_bonus(
                    wall_gid, wall.wall_level
                )
            else:
                wall_bonus = None

            if wall_bonus is None:
                wall_bonus = wall.wall_level * 0.03

            if wall_bonus > 0:
                wall_damage = floor(
                    rams_survived * ram_attack / (wall_bonus * strong_buildings)
                )
            else:
                wall_damage = 0

            wall_after = max(0, wall_before - wall_damage)

    return StructuralDamage(
        catapult_results=catapult_results,
        wall_before=wall_before,
        wall_after=wall_after,
    )


# ---------------------------------------------------------------------------
# Función principal: simulate_combat
# ---------------------------------------------------------------------------

async def simulate_combat(
    attacker: AttackerFormation,
    defenders: list[DefenderFormation],
    wall: WallConfig,
    config: CombatConfig,
    lang: str,
    game_data_port: GameDataPort,
    translation_port: TranslationPort,
    server_version: str = "1.45",
) -> CombatResult:
    """
    Simula un combate completo según la fórmula Travian T4.5.

    Ver spec §RN-01..RN-13 y §9 para la lógica completa.
    """
    warnings: list[str] = []

    # -----------------------------------------------------------------------
    # 1. Cargar y enriquecer tropas atacantes
    # -----------------------------------------------------------------------
    atk_enriched: list[dict] = []
    for entry in attacker.troops:
        stats = await game_data_port.get_troop_stats(
            attacker.tribe, entry.ordinal, server_version
        )
        if stats is None:
            raise ValueError(
                f"Sin stats en BD para tropa {attacker.tribe.value} ordinal={entry.ordinal}. "
                f"Ejecuta el scraper de kirilloid para poblar la tabla troop_stats."
            )
        attack_eff = await apply_smithy(
            stats["attack"], attacker.tribe, entry.ordinal,
            entry.smithy_level, game_data_port, warnings, stat="attack",
            server_version=server_version,
        )
        atk_enriched.append({
            "tribe": attacker.tribe,
            "ordinal": entry.ordinal,
            "quantity": entry.quantity,
            "smithy_level": entry.smithy_level,
            "attack_eff": attack_eff,
            "stats": stats,
        })

    # -----------------------------------------------------------------------
    # 2. Calcular A efectivo
    # -----------------------------------------------------------------------
    A_base = sum(e["attack_eff"] * e["quantity"] for e in atk_enriched)
    if A_base == 0 and attacker.hero_attack_points == 0:
        raise ValueError("El ejército atacante no tiene tropas activas (ataque total = 0).")

    A_con_heroe = (A_base + attacker.hero_attack_points) * (
        1.0 + attacker.hero_attack_bonus_percent / 100.0
    )
    A_total = A_con_heroe * (1.0 + attacker.alliance_bonus / 100.0)

    # Clampear moral (RN-04)
    moral = attacker.morale
    if moral < 30:
        warnings.append(f"Moral {moral} < 30 (mínimo Travian) — ajustada a 30.")
        moral = 30.0
    elif moral > 100:
        warnings.append(f"Moral {moral} > 100 — ajustada a 100.")
        moral = 100.0

    A_efectivo = A_total * (moral / 100.0)

    # -----------------------------------------------------------------------
    # 3. Proporción caballería del atacante (RN-05)
    # -----------------------------------------------------------------------
    A_inf = sum(
        e["attack_eff"] * e["quantity"]
        for e in atk_enriched
        if is_infantry(attacker.tribe, e["ordinal"])
    )
    A_cav = sum(
        e["attack_eff"] * e["quantity"]
        for e in atk_enriched
        if is_cavalry(attacker.tribe, e["ordinal"])
    )
    prop_cav = A_cav / (A_inf + A_cav) if (A_inf + A_cav) > 0 else 0.0

    # -----------------------------------------------------------------------
    # 4. Cargar y enriquecer tropas defensoras
    # -----------------------------------------------------------------------
    all_def_enriched: list[dict] = []
    total_hero_def_points = 0.0

    for formation in defenders:
        for entry in formation.troops:
            stats = await game_data_port.get_troop_stats(
                entry.tribe, entry.ordinal, server_version
            )
            if stats is None:
                raise ValueError(
                    f"Sin stats en BD para tropa {entry.tribe.value} ordinal={entry.ordinal}. "
                    f"Ejecuta el scraper de kirilloid."
                )
            def_inf_eff = await apply_smithy(
                stats["def_infantry"], entry.tribe, entry.ordinal,
                entry.smithy_level, game_data_port, warnings, stat="def_infantry",
                server_version=server_version,
            )
            def_cav_eff = await apply_smithy(
                stats["def_cavalry"], entry.tribe, entry.ordinal,
                entry.smithy_level, game_data_port, warnings, stat="def_cavalry",
                server_version=server_version,
            )
            all_def_enriched.append({
                "tribe": entry.tribe,
                "ordinal": entry.ordinal,
                "quantity": entry.quantity,
                "smithy_level": entry.smithy_level,
                "def_inf": def_inf_eff,
                "def_cav": def_cav_eff,
                "hero_bonus_percent": formation.hero_defense_bonus_percent,
                "stats": stats,
            })
        total_hero_def_points += formation.hero_defense_points

    # -----------------------------------------------------------------------
    # 5. Calcular D_base (suma de todos los defensores)
    # -----------------------------------------------------------------------
    D_base = sum(
        e["quantity"] * (
            e["def_inf"] * (1.0 - prop_cav) + e["def_cav"] * prop_cav
        )
        for e in all_def_enriched
    )

    # -----------------------------------------------------------------------
    # 6. Bonus de héroe defensor — promedio simple de bonus porcentuales (RN-01)
    # -----------------------------------------------------------------------
    hero_def_bonus_pct = 0.0
    if defenders:
        hero_def_bonus_pct = (
            sum(f.hero_defense_bonus_percent for f in defenders) / len(defenders)
        )

    D_con_heroe = (D_base + total_hero_def_points) * (
        1.0 + hero_def_bonus_pct / 100.0
    )

    # -----------------------------------------------------------------------
    # 7. Multiplicador de muro (RN-03)
    # -----------------------------------------------------------------------
    wall_multiplier = await resolve_wall_multiplier(wall, game_data_port, warnings)
    D_efectiva = D_con_heroe * wall_multiplier

    # -----------------------------------------------------------------------
    # 8. Ratio, factor K y supervivientes (fórmula Travian T4.5)
    # -----------------------------------------------------------------------
    # K se calcula con el TOTAL de tropas en el campo (atacante + defensor).
    # Fuente: kirilloid — K = 1.5 si N<=1000, K = 2*(1.8592 - N^0.015) en caso contrario.
    total_units = sum(e["quantity"] for e in atk_enriched) + sum(
        e["quantity"] for e in all_def_enriched
    )
    K = compute_k(total_units)

    if D_efectiva == 0:
        # EC-01: defensa vacía → victoria inmediata, todos sobreviven
        attacker_wins = True
        ratio: float | None = None
        atk_survived = [e["quantity"] for e in atk_enriched]
        def_survived = [0] * len(all_def_enriched)
    else:
        ratio_raw = A_efectivo / D_efectiva
        attacker_wins = ratio_raw >= 1.0  # EC-03: ratio exactamente 1 → atacante gana

        # Fuerzas absolutas para la fórmula de bajas
        if attacker_wins:
            winner_power, loser_power = A_efectivo, D_efectiva
        else:
            winner_power, loser_power = D_efectiva, A_efectivo

        # x = (loser / winner) ^ K  — base de las dos variantes (attack y raid)
        x = (loser_power / winner_power) ** K

        if attacker.attack_type == "attack":
            # Attack normal (kirilloid):
            #   winner_losses% = x        (capado a 1 por seguridad numérica)
            #   loser_losses%  = 1        (perdedor aniquilado)
            winner_loss_pct = min(x, 1.0)
            loser_loss_pct = 1.0
        else:
            # Raid (kirilloid):
            #   winner_losses% = x / (1+x)
            #   loser_losses%  = 1 / (1+x)
            # Total combinado = 100% repartido proporcionalmente.
            winner_loss_pct = x / (1.0 + x)
            loser_loss_pct = 1.0 / (1.0 + x)

        if attacker_wins:
            atk_loss_pct, def_loss_pct = winner_loss_pct, loser_loss_pct
        else:
            atk_loss_pct, def_loss_pct = loser_loss_pct, winner_loss_pct

        # round() sobre supervivientes (Travian redondea al sup más cercano)
        atk_survived = [
            round(e["quantity"] * (1.0 - atk_loss_pct))
            for e in atk_enriched
        ]
        def_survived = [
            round(e["quantity"] * (1.0 - def_loss_pct))
            for e in all_def_enriched
        ]
        ratio = round(ratio_raw, 4)

        # -----------------------------------------------------------------------
        # Regla mínimo 1 superviviente para el GANADOR (Travian garantiza que
        # el ganador nunca queda con 0 tropas si tenía al menos 1 al inicio).
        # El perdedor NO tiene esta garantía:
        #   - en attack normal el perdedor es siempre aniquilado por fórmula;
        #   - en raid el perdedor mantiene sus supervivientes proporcionales
        #     según x/(1+x), incluyendo el caso 0 cuando la diferencia es brutal.
        # -----------------------------------------------------------------------
        if attacker_wins and sum(atk_survived) == 0:
            best = max(range(len(atk_enriched)), key=lambda i: atk_enriched[i]["quantity"])
            atk_survived[best] = 1
        if (not attacker_wins) and sum(def_survived) == 0:
            best = max(range(len(all_def_enriched)), key=lambda i: all_def_enriched[i]["quantity"])
            def_survived[best] = 1

    # -----------------------------------------------------------------------
    # 9a. Botín (RN-07 + RN-08)
    # -----------------------------------------------------------------------
    loot = _compute_loot(
        atk_enriched, atk_survived, all_def_enriched, def_survived,
        defenders, attacker_wins,
    )

    # -----------------------------------------------------------------------
    # 9b. Coste en recursos de bajas (RN-09)
    # -----------------------------------------------------------------------
    atk_lost_qty = [e["quantity"] - atk_survived[i] for i, e in enumerate(atk_enriched)]
    def_lost_qty = [e["quantity"] - def_survived[i] for i, e in enumerate(all_def_enriched)]

    resource_losses = ResourceLosses(
        attacker=_compute_resource_losses(
            atk_enriched, atk_lost_qty, lang, translation_port
        ),
        defender=_compute_resource_losses(
            all_def_enriched, def_lost_qty, lang, translation_port
        ),
    )

    # -----------------------------------------------------------------------
    # 9c. Daño estructural (RN-13)
    # -----------------------------------------------------------------------
    structural_damage: StructuralDamage | None = None
    if attacker.attack_type == "attack":
        structural_damage = await _compute_structural_damage(
            attacker, atk_enriched, atk_survived, wall, defenders,
            game_data_port, warnings, attacker_wins,
        )
    elif attacker.attack_type == "raid" and attacker.catapult_targets:
        warnings.append(
            "catapult_targets ignorado en modo saqueo (attack_type='raid')."
        )

    # -----------------------------------------------------------------------
    # 10. Crop consumption (RN-06)
    # -----------------------------------------------------------------------
    crop_consumption: int | None = None
    if config.distance_fields is not None:
        min_speed = min(
            (e["stats"].get("speed") or 1) for e in atk_enriched
        )
        speed_eff = (
            (min_speed / config.server_speed) * attacker.artifacts.fast_troops
        )
        travel_h = (config.distance_fields / speed_eff) if speed_eff > 0 else 0.0
        crop_ph = sum(
            (e["stats"].get("upkeep") or 0) * e["quantity"]
            for e in atk_enriched
        )
        crop_consumption = round(
            crop_ph * travel_h * 2.0 * attacker.artifacts.diet
        )

    # -----------------------------------------------------------------------
    # 11. Resolver nombres e iconos
    # -----------------------------------------------------------------------
    atk_results = await build_troop_results(
        atk_enriched, atk_survived, lang, translation_port, game_data_port
    )
    def_results = await build_troop_results(
        all_def_enriched, def_survived, lang, translation_port, game_data_port
    )

    return CombatResult(
        attacker_wins=attacker_wins,
        attacker_troops=atk_results,
        defender_troops=def_results,
        attacker_power=round(A_efectivo, 2),
        defender_power=round(D_efectiva, 2),
        ratio=ratio,
        loot=loot,
        resource_losses=resource_losses,
        structural_damage=structural_damage,
        crop_consumption=crop_consumption,
        warnings=warnings,
    )
