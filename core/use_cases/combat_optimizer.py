"""
Optimizador de ataque a oasis — herramientas especializadas con ganancia neta %.

Rediseñado en 2026-06-09: se eliminan NSGA-II (pymoo), frente de Pareto y los 5 pesos.
Se introduce net_gain_pct como fitness escalar y tres herramientas (multi_troop,
army_sim, multi_raid) con ordenamiento explícito.
Ver spec optimizadores-oasis-rediseno §4, §9, §14.
"""
from __future__ import annotations

import asyncio
import itertools
import logging
from typing import Literal

from core.entities.combat import (
    AnimalResourceDrop,
    AttackerArtifacts,
    AttackerFormation,
    CombatConfig,
    DefenderArtifacts,
    DefenderFormation,
    Loot,
    MultiRaidAggregate,
    OptimizationAlternative,
    OptimizationConfig,
    OptimizationResult,
    TroopAvailability,
    TroopEntry,
    TroopResult,
    TroopTypeSpec,
    WallConfig,
)
from core.entities.tribe import Tribe
from core.ports.game_data_port import GameDataPort
from core.ports.translation_port import TranslationPort
from core.use_cases.combat_engine import simulate_combat, valor_de_tropa

logger = logging.getLogger(__name__)

# Cap máximo de N para el barrido automático en Multi-Raid sin n_max explícito.
# Evita que un inventario enorme (ej. 50 000 tropas) genere un producto cartesiano
# inmanejable en la Fase 3. 200 oleadas cubre cualquier caso real de juego.
_MULTI_RAID_N_CAP: int = 200


# ---------------------------------------------------------------------------
# Helper: N natural para Multi-Raid
# ---------------------------------------------------------------------------

def _compute_n_natural(ev: dict, available_map: dict) -> int | None:
    """N "natural" = floor(min_i(available_i / sent_i)) sobre tipos con sent_i > 0.

    Retorna None si no aplica (sin inventario o sin tropas enviadas).
    Retorna 0 si algún tipo enviado no está disponible en absoluto.
    """
    if not available_map:
        return None
    ratios: list[int] = []
    for t in ev.get("troop_entries", []):
        sent = t.quantity
        if sent <= 0:
            continue
        avail = available_map.get((t.tribe, t.ordinal), 0)
        if avail <= 0:
            return 0
        ratios.append(avail // sent)
    if not ratios:
        return None
    return min(ratios)


# ---------------------------------------------------------------------------
# Evaluación de una combinación de tropas
# ---------------------------------------------------------------------------

async def _evaluate_combination(
    quantities: list[int],
    troop_specs: list[dict],        # [{tribe, ordinal, smithy_level}]
    attacker_tribe: Tribe,
    hero_attack_points: float,
    hero_attack_bonus_percent: float,
    alliance_bonus: float,
    artifacts: AttackerArtifacts,
    oasis_defenders: list[TroopEntry],
    server_speed: float,
    distance_fields: float | None,
    lang: str,
    game_data_port: GameDataPort,
    translation_port: TranslationPort,
    server_version: str = "1.45",
) -> dict | None:
    """
    Evalúa una combinación de cantidades de tropas simulando el combate.
    Devuelve un dict con métricas o None si no hay tropas enviadas.
    """
    # Construir tropas del atacante
    troop_entries = [
        TroopEntry(
            tribe=attacker_tribe,
            ordinal=spec["ordinal"],
            quantity=q,
            smithy_level=spec["smithy_level"],
        )
        for spec, q in zip(troop_specs, quantities)
        if q > 0
    ]
    if not troop_entries:
        return None

    attacker = AttackerFormation(
        tribe=attacker_tribe,
        troops=troop_entries,
        attack_type="raid",  # optimizador siempre evalúa como saqueo
        hero_attack_points=hero_attack_points,
        hero_attack_bonus_percent=hero_attack_bonus_percent,
        alliance_bonus=alliance_bonus,
        morale=100.0,
        artifacts=artifacts,
    )

    # Defensores: oasis NATURE sin smithy
    nature_troops = [
        TroopEntry(
            tribe=Tribe.NATURE,
            ordinal=t.ordinal,
            quantity=t.quantity,
            smithy_level=0,
        )
        for t in oasis_defenders
    ]
    defenders = [
        DefenderFormation(
            tribe=Tribe.NATURE,
            troops=nature_troops,
            hero_defense_points=0.0,
            hero_defense_bonus_percent=0.0,
            artifacts=DefenderArtifacts(),
        )
    ]

    combat_config = CombatConfig(
        server_speed=server_speed,
        distance_fields=distance_fields,
    )

    try:
        result = await simulate_combat(
            attacker=attacker,
            defenders=defenders,
            wall=WallConfig(),  # oasis sin muro
            config=combat_config,
            lang=lang,
            game_data_port=game_data_port,
            translation_port=translation_port,
            server_version=server_version,
        )
    except ValueError:
        return None  # combinación inválida (sin ataque real)

    # Calcular tiempo de marcha
    travel_time_h = 0.0
    if distance_fields is not None and result.crop_consumption is not None:
        # Re-derivar travel_time_h a partir de los stats
        if troop_entries:
            # La velocidad mínima del ejército ya se calculó en simulate_combat
            # Lo recalculamos aquí de forma consistente
            min_speed = min(
                (spec.get("speed") or 1) for spec in [
                    {"speed": None}  # placeholder — lo buscamos abajo
                ]
            )
            # Buscar speed mínimo entre los troop_specs enviados
            speeds = []
            for ts in troop_specs:
                if ts["ordinal"] in [te.ordinal for te in troop_entries]:
                    s = ts.get("speed")
                    if s:
                        speeds.append(s)
            if speeds:
                min_speed = min(speeds)
                speed_eff = (min_speed / server_speed) * artifacts.fast_troops
                if speed_eff > 0 and distance_fields is not None:
                    travel_time_h = distance_fields / speed_eff

    total_resource_losses = result.resource_losses.attacker.total_resources
    troops_sent_count = sum(te.quantity for te in troop_entries)
    total_losses = sum(tr.quantity_lost for tr in result.attacker_troops)

    # Desglose por recurso del coste de las bajas del atacante. Sumamos los
    # total_cost de cada tropa perdida (cada uno ya viene con wood/clay/iron/crop).
    # Si una breakdown no tiene total_cost, contribuye 0. .total ≡ total_resources.
    breakdown_w = breakdown_c = breakdown_i = breakdown_cr = 0
    for entry in result.resource_losses.attacker.breakdown:
        tc = entry.total_cost or {}
        breakdown_w  += int(tc.get("wood",  0) or 0)
        breakdown_c  += int(tc.get("clay",  0) or 0)
        breakdown_i  += int(tc.get("iron",  0) or 0)
        breakdown_cr += int(tc.get("crop",  0) or 0)
    resource_losses_breakdown = {
        "wood":  breakdown_w,
        "clay":  breakdown_c,
        "iron":  breakdown_i,
        "crop":  breakdown_cr,
        "total": breakdown_w + breakdown_c + breakdown_i + breakdown_cr,
    }

    # Recursos de animales (puede ser None si no hay NATURE en defensa)
    resources_gained_total = 0
    if result.loot.resources_gained_from_animals:
        resources_gained_total = result.loot.resources_gained_from_animals.total

    # NUEVO §9.2/§9.3: calcular net_gain_pct para el atacante.
    # IMPORTANTE: se usa EXCLUSIVAMENTE con bajas del ejército ATACANTE.
    # Los animales defensores (NATURE) NUNCA se pasan a valor_de_tropa;
    # solo contribuyen al saqueo (resources_gained_total).
    net_gain_pct: float | None = None
    if resources_gained_total > 0:
        # Construir mapa (tribe, ordinal) → spec para buscar cost_sum y train_time_s
        spec_map = {(s["tribe"], s["ordinal"]): s for s in troop_specs}
        valor_bajas = 0.0
        for tr in result.attacker_troops:
            if tr.quantity_lost <= 0:
                continue
            key = (tr.tribe, tr.ordinal)
            spec = spec_map.get(key, {})
            cost_s = spec.get("cost_sum") or 0
            tt_s = spec.get("train_time_s") or 0.0
            valor_bajas += tr.quantity_lost * valor_de_tropa(cost_s, tt_s)
        net_gain_pct = 100.0 * (resources_gained_total - valor_bajas) / resources_gained_total

    return {
        "quantities": quantities,
        "troop_entries": troop_entries,
        "result": result,
        "is_winning": result.attacker_wins,
        "total_resource_losses": total_resource_losses,
        "resource_losses_breakdown": resource_losses_breakdown,
        "troops_sent_count": troops_sent_count,
        "total_losses": total_losses,
        "resources_gained_total": resources_gained_total,
        "travel_time_h": travel_time_h,
        # net_gain_pct (spec §4/§7): None si saqueo=0
        "net_gain_pct": net_gain_pct,
        # Objetivos auxiliares para ordenamiento
        "neg_resources": -resources_gained_total,
        "travel_time_h_obj": travel_time_h,
    }


# ---------------------------------------------------------------------------
# Fallback: búsqueda por muestreo
# ---------------------------------------------------------------------------

async def _optimize_by_sampling(
    troop_specs: list[dict],
    max_quantities: list[int],      # para cada tipo; 0 = libre (Modo A)
    attacker_tribe: Tribe,
    hero_attack_points: float,
    hero_attack_bonus_percent: float,
    alliance_bonus: float,
    artifacts: AttackerArtifacts,
    oasis_defenders: list[TroopEntry],
    server_speed: float,
    distance_fields: float | None,
    lang: str,
    game_data_port: GameDataPort,
    translation_port: TranslationPort,
    top_n: int,
    server_version: str = "1.45",
    # Fase 3 dirigida por rango N (Multi-Raid): solo activa en Modo C agregado
    n_min: int | None = None,
    n_max: int | None = None,
) -> list[dict]:
    """
    Busca combinaciones de tropas por muestreo en DOS fases:

    Fase 1 — gruesa (paso ~10% de la escala): cubre ejércitos grandes y descubre
             la región general donde la victoria es trivial (p.ej. enviar 1k
             espadachines no requiere optimización fina).
    Fase 2 — fina (paso 1): explora cantidades pequeñas (0..fine_max por tipo)
             para descubrir el "ejército mínimo ganador" que es lo verdaderamente
             interesante contra oasis típicos (10 ratas, 5 lobos, etc.).

    El máximo por tipo en la fase fina es adaptativo según N para evitar
    explosión combinatoria (presupuesto ≈ 10 000 combos en la fase fina).

    Modo A (max=0): escala 100; fase fina hasta fine_max.
    Modo B (max>0): escala = cantidad disponible; fase fina capada por scale[i].
    """
    n = len(troop_specs)
    if n == 0:
        return []

    scale = [max_q if max_q > 0 else 100 for max_q in max_quantities]

    # ── Fase 1 — gruesa (paso ~10%) ──────────────────────────────────────────
    coarse_steps = 10
    coarse_ranges = [
        list(range(0, scale[i] + 1, max(1, scale[i] // coarse_steps)))
        for i in range(n)
    ]
    for i in range(n):
        if scale[i] not in coarse_ranges[i]:
            coarse_ranges[i].append(scale[i])

    # ── Fase 2 — fina (paso 1) ───────────────────────────────────────────────
    # fine_max adaptativo: presupuesto ≈ 10 000 combos en esta fase.
    #   N=1 → 30        (capado por techo absoluto)
    #   N=2 → 30        (capado)
    #   N=3 → 21
    #   N=4 → 10
    #   N=5 → 6
    fine_max_per_type = max(5, min(30, int(10_000 ** (1.0 / n))))
    fine_ranges = [
        list(range(0, min(fine_max_per_type, scale[i]) + 1, 1))
        for i in range(n)
    ]

    # ── Combinar y deduplicar (la fase fina solapa con la gruesa en 0) ──────
    seen: set[tuple[int, ...]] = set()
    combos_to_eval: list[list[int]] = []

    for combo in itertools.product(*coarse_ranges):
        if all(q == 0 for q in combo):
            continue
        if combo in seen:
            continue
        seen.add(combo)
        combos_to_eval.append(list(combo))

    for combo in itertools.product(*fine_ranges):
        if all(q == 0 for q in combo):
            continue
        if combo in seen:
            continue
        seen.add(combo)
        combos_to_eval.append(list(combo))

    # ── Fase 3 — dirigida por N (Multi-Raid) ─────────────────────────────────
    # Activa en modo aggregate (Multi-Raid) cuando hay inventario real.
    # Con campo "mínimo de oasis" vacío usa n_min=1, n_max=_MULTI_RAID_N_CAP.
    # Estrategia: muestrear N directamente (barrido denso en N) y derivar
    # sent_i = max(1, round(avail_i / N)) para cada N candidato.
    # Esto garantiza cobertura uniforme del espacio N, incluyendo N altos donde
    # sent_i < paso_grueso (hueco que Fases 1+2 no cubren). Esencial para que
    # subir min_net_gain_pct reduzca N (oleadas mayores, más limpias) y bajarlo
    # lo aumente. Ver spec RN-03 y §9.
    if (n_min is not None or n_max is not None) and all(m > 0 for m in max_quantities):
        _n_lo = max(1, n_min if n_min is not None else 1)
        _n_hi = max(_n_lo, n_max if n_max is not None else min(max_quantities))

        # Muestrear N con hasta _N3_BUDGET valores; N=1..pequeño siempre incluido.
        _N3_BUDGET = 200
        n_span = _n_hi - _n_lo + 1
        if n_span <= _N3_BUDGET:
            n_candidates = list(range(_n_lo, _n_hi + 1))
        else:
            step = max(1, n_span // _N3_BUDGET)
            n_candidates = list(range(_n_lo, _n_hi + 1, step))
            if _n_hi not in n_candidates:
                n_candidates.append(_n_hi)

        for n_target in n_candidates:
            # Oleada "natural" para este N: cada tipo envía round(avail/N)
            combo = tuple(max(1, round(avail / n_target)) for avail in max_quantities)
            if all(q == 0 for q in combo):
                continue
            if combo in seen:
                continue
            seen.add(combo)
            combos_to_eval.append(list(combo))

            # Variaciones: desplazar sent de cada tipo ±1 para capturar
            # combinaciones mixtas que maximicen N (inf baja, cav alta).
            for delta in (-1, 1):
                for i in range(n):
                    varied = list(combo)
                    varied[i] = max(1, combo[i] + delta)
                    t = tuple(varied)
                    if t in seen:
                        continue
                    seen.add(t)
                    combos_to_eval.append(varied)

    # Salvaguarda dura por si la combinación de fases dispara el total
    HARD_CAP = 30_000
    if len(combos_to_eval) > HARD_CAP:
        logger.warning(
            "Optimizer sampling: %d combos exceeds budget; truncating to %d.",
            len(combos_to_eval), HARD_CAP,
        )
        combos_to_eval = combos_to_eval[:HARD_CAP]

    # ── Evaluar ──────────────────────────────────────────────────────────────
    evaluated: list[dict] = []
    for quantities in combos_to_eval:
        ev = await _evaluate_combination(
            quantities=quantities,
            troop_specs=troop_specs,
            attacker_tribe=attacker_tribe,
            hero_attack_points=hero_attack_points,
            hero_attack_bonus_percent=hero_attack_bonus_percent,
            alliance_bonus=alliance_bonus,
            artifacts=artifacts,
            oasis_defenders=oasis_defenders,
            server_speed=server_speed,
            distance_fields=distance_fields,
            lang=lang,
            game_data_port=game_data_port,
            translation_port=translation_port,
            server_version=server_version,
        )
        if ev is not None:
            evaluated.append(ev)

    return evaluated


# ---------------------------------------------------------------------------
# Función principal: find_optimal_attack
# ---------------------------------------------------------------------------

async def find_optimal_attack(
    attacker_tribe: Tribe,
    troop_types: list[TroopTypeSpec] | None,         # Modo A (sin inventario)
    village_troops: list[TroopAvailability] | None,  # Modo B (con inventario)
    hero_attack_points: float,
    hero_attack_bonus_percent: float,
    alliance_bonus: float,
    artifacts: AttackerArtifacts,
    oasis_defenders: list[TroopEntry],
    opt_config: OptimizationConfig,
    lang: str,
    game_data_port: GameDataPort,
    translation_port: TranslationPort,
    tool: str = "multi_troop",    # "multi_troop" | "army_sim" | "multi_raid"
    server_version: str = "1.45",
) -> OptimizationResult:
    """
    Encuentra la combinación óptima de tropas para atacar un oasis.

    Herramientas:
      multi_troop — Modo A: minimiza tropas enviadas, suelo min_net_gain_pct.
      army_sim    — Modo B: maximiza net_gain_pct.
      multi_raid  — Modo B agregado: maximiza N raids, suelo min_net_gain_pct.

    Ver spec optimizadores-oasis-rediseno §9 y §14.
    """
    warnings: list[str] = []

    # -----------------------------------------------------------------------
    # Construir troop_specs con speed, cost_sum y train_time_s
    # -----------------------------------------------------------------------
    troop_specs: list[dict] = []
    max_quantities: list[int] = []

    if troop_types is not None:
        for ts in troop_types:
            stats = await game_data_port.get_troop_stats(
                attacker_tribe, ts.ordinal, server_version
            )
            if stats is None:
                raise ValueError(
                    f"Sin stats en BD para {attacker_tribe.value} ordinal={ts.ordinal}."
                )
            cost_s = stats.get("cost_sum") or 0
            if cost_s == 0:
                warnings.append(
                    f"cost_sum=0 para {attacker_tribe.value} ordinal={ts.ordinal} "
                    f"— dato posiblemente corrupto en BD."
                )
            troop_specs.append({
                "tribe": attacker_tribe,
                "ordinal": ts.ordinal,
                "smithy_level": ts.smithy_level,
                "speed": stats.get("speed") or 1,
                "cost_sum": cost_s,
                "train_time_s": stats.get("train_time_s") or 0.0,
            })
            max_quantities.append(0)  # Modo A: libre
    else:
        for tv in (village_troops or []):
            stats = await game_data_port.get_troop_stats(
                attacker_tribe, tv.ordinal, server_version
            )
            if stats is None:
                raise ValueError(
                    f"Sin stats en BD para {attacker_tribe.value} ordinal={tv.ordinal}."
                )
            cost_s = stats.get("cost_sum") or 0
            if cost_s == 0:
                warnings.append(
                    f"cost_sum=0 para {attacker_tribe.value} ordinal={tv.ordinal} "
                    f"— dato posiblemente corrupto en BD."
                )
            troop_specs.append({
                "tribe": attacker_tribe,
                "ordinal": tv.ordinal,
                "smithy_level": tv.smithy_level,
                "speed": stats.get("speed") or 1,
                "cost_sum": cost_s,
                "train_time_s": stats.get("train_time_s") or 0.0,
            })
            max_quantities.append(tv.quantity_available)

    # -----------------------------------------------------------------------
    # Preparar defensa del oasis (referencia para el resultado)
    # -----------------------------------------------------------------------
    nature_troop_entries = [
        TroopEntry(
            tribe=Tribe.NATURE,
            ordinal=t.ordinal,
            quantity=t.quantity,
            smithy_level=0,
        )
        for t in oasis_defenders
    ]

    # Construir defender_troops de referencia (inicialmente animales intactos)
    defender_result_list: list[TroopResult] = []
    for entry in nature_troop_entries:
        name = translation_port.get_troop_name(Tribe.NATURE, entry.ordinal, lang)
        stats = await game_data_port.get_troop_stats(Tribe.NATURE, entry.ordinal)
        icon_id = stats["icon_id"] if stats else None
        icon_url = f"/static/icons/{icon_id}.png" if icon_id else None
        defender_result_list.append(TroopResult(
            tribe=Tribe.NATURE,
            ordinal=entry.ordinal,
            name=name,
            icon_url=icon_url,
            quantity_initial=entry.quantity,
            quantity_survived=entry.quantity,  # provisional
            quantity_lost=0,
        ))

    # -----------------------------------------------------------------------
    # Verificar si hay datos de drops de naturales
    # -----------------------------------------------------------------------
    from core.use_cases.nature_animal_drops import NATURE_DROPS
    oasis_ordinales = {t.ordinal for t in oasis_defenders}
    has_nature_drops = any(o in NATURE_DROPS for o in oasis_ordinales)
    if oasis_defenders and not has_nature_drops:
        warnings.append(
            "Sin datos de drops de animales de naturaleza; ganancia neta no disponible."
        )

    # -----------------------------------------------------------------------
    # Muestreo (único camino — NSGA-II y Pareto eliminados en rediseño 2026-06-09)
    # -----------------------------------------------------------------------
    # En modo aggregate (Multi-Raid), la Fase 3 SIEMPRE se activa para barrer N.
    # El campo "mínimo de oasis" (n_min) solo ACOTA, no HABILITA, el barrido.
    # Ver spec §9 RN-03/RN-05: "en aggregate el muestreo barre N siempre".
    _sampling_n_min: int | None = None
    _sampling_n_max: int | None = None
    if opt_config.scoring_mode == "aggregate" and all(m > 0 for m in max_quantities):
        # n_min: usa el valor del usuario si está presente; sino 1 (barrer desde 1 oleada)
        _sampling_n_min = opt_config.n_min if opt_config.n_min is not None else 1
        # n_max: usa el valor del usuario si está presente; sino el N máximo natural
        # capado a _MULTI_RAID_N_CAP para no explotar el presupuesto de combos.
        if opt_config.n_max is not None:
            _sampling_n_max = opt_config.n_max
        else:
            _natural_n_max = min(max_quantities)  # máximo N posible con 1 tropa/oleada
            _sampling_n_max = min(_natural_n_max, _MULTI_RAID_N_CAP)

    evaluated = await _optimize_by_sampling(
        troop_specs=troop_specs,
        max_quantities=max_quantities,
        attacker_tribe=attacker_tribe,
        hero_attack_points=hero_attack_points,
        hero_attack_bonus_percent=hero_attack_bonus_percent,
        alliance_bonus=alliance_bonus,
        artifacts=artifacts,
        oasis_defenders=oasis_defenders,
        server_speed=opt_config.server_speed,
        distance_fields=opt_config.distance_fields,
        lang=lang,
        game_data_port=game_data_port,
        translation_port=translation_port,
        top_n=opt_config.top_n,
        server_version=server_version,
        n_min=_sampling_n_min,
        n_max=_sampling_n_max,
    )

    if not evaluated:
        raise ValueError("No se pudo evaluar ninguna combinación de tropas.")

    # -----------------------------------------------------------------------
    # Separar ganadoras de no-ganadoras
    # -----------------------------------------------------------------------
    winning = [e for e in evaluated if e["is_winning"]]
    has_winning = len(winning) > 0
    pool = winning if has_winning else evaluated

    # -----------------------------------------------------------------------
    # Construir available_map (solo en Modo B/C — con inventario)
    # -----------------------------------------------------------------------
    available_map: dict = {}
    if village_troops:
        for tv in village_troops:
            available_map[(tv.tribe, tv.ordinal)] = tv.quantity_available

    # -----------------------------------------------------------------------
    # Filtrar por suelo min_net_gain_pct (spec §9.2)
    # -----------------------------------------------------------------------
    min_ngp = opt_config.min_net_gain_pct
    suelo_aplicable = [
        e for e in pool
        if e["net_gain_pct"] is None or e["net_gain_pct"] >= min_ngp
    ]
    suelo_inalcanzable = False
    if not suelo_aplicable and pool:
        # El suelo no se puede cumplir con NINGUNA combinación. El usuario puso un
        # suelo alto porque quiere LIMPIEZA; si es inalcanzable le mostramos lo MÁS
        # LIMPIO posible (mayor net_gain_pct), nunca la opción de más oasis (que es
        # justo la que más sangra). Ver spec §5 flujo D / RN-01/02/03.
        suelo_inalcanzable = True
        suelo_aplicable = pool

    # -----------------------------------------------------------------------
    # Ordenar según la herramienta (spec §9.2)
    # -----------------------------------------------------------------------
    scoring_mode = opt_config.scoring_mode
    n_min_cfg = opt_config.n_min
    n_max_cfg = opt_config.n_max

    def _ngp_desc(e: dict) -> float:
        # Clave para ordenar por ganancia neta DESCENDENTE (None al fondo).
        return -(e["net_gain_pct"] if e["net_gain_pct"] is not None else -1e15)

    if suelo_inalcanzable:
        # Suelo inalcanzable → lo MÁS LIMPIO primero, para CUALQUIER herramienta.
        suelo_aplicable.sort(key=_ngp_desc)
    elif tool == "multi_troop":
        # Minimizar ejército; desempate por recurso de bajas
        suelo_aplicable.sort(
            key=lambda e: (e["troops_sent_count"], e["total_resource_losses"])
        )
    elif tool == "army_sim":
        # Maximizar net_gain_pct; fallback a resources_gained_total si None
        suelo_aplicable.sort(
            key=lambda e: (_ngp_desc(e), -e.get("resources_gained_total", 0))
        )
    elif tool == "multi_raid":
        # Maximizar N; desempate por net_gain_pct
        suelo_aplicable.sort(
            key=lambda e: (-(_compute_n_natural(e, available_map) or 0), _ngp_desc(e))
        )
    else:
        # Desconocido: comportamiento seguro, igual que multi_troop
        suelo_aplicable.sort(
            key=lambda e: (e["troops_sent_count"], e["total_resource_losses"])
        )

    # Aviso de suelo inalcanzable, enriquecido con el máximo REAL alcanzable
    # (la lista ya está ordenada de más limpio a menos).
    if suelo_inalcanzable and suelo_aplicable:
        best = suelo_aplicable[0]
        best_ngp = best["net_gain_pct"]
        best_n = _compute_n_natural(best, available_map)
        if best_ngp is not None:
            detalle = f"lo más limpio posible es {best_ngp:.0f}% de ganancia neta"
            if best_n:
                detalle += f" atacando {best_n} oasis"
        else:
            detalle = "no hay datos de ganancia neta para estas combinaciones"
        warnings.append(
            f"El suelo de ganancia neta ({min_ngp:.0f}%) es inalcanzable con tu "
            f"ejército contra este oasis; {detalle}. Se muestra de más limpio a menos."
        )

    # Advertencia por n_min cuando el mejor N no alcanza el mínimo pedido
    if scoring_mode == "aggregate" and n_min_cfg is not None and suelo_aplicable:
        best_n = _compute_n_natural(suelo_aplicable[0], available_map) or 0
        if best_n < n_min_cfg:
            warnings.append(
                f"Ninguna combinación alcanza el mínimo de {n_min_cfg} raids con el "
                f"inventario disponible (mejor: {best_n})."
            )

    top = suelo_aplicable[: opt_config.top_n]

    # -----------------------------------------------------------------------
    # Construir OptimizationAlternative para cada resultado del top
    # -----------------------------------------------------------------------
    alternatives: list[OptimizationAlternative] = []
    for rank, ev in enumerate(top, start=1):
        result = ev["result"]

        # travel_time_h recalculado de forma limpia
        travel_time_h: float | None = None
        if opt_config.distance_fields is not None:
            speeds = [spec["speed"] for spec in troop_specs]
            if speeds:
                min_speed = min(speeds)
                speed_eff = (min_speed / opt_config.server_speed) * artifacts.fast_troops
                if speed_eff > 0:
                    travel_time_h = opt_config.distance_fields / speed_eff

        # ── Decoración multi-raid (solo en Modo B/C — cuando hay inventario) ──
        raids_possible: int | None = None
        remaining_troops_list: list[TroopResult] | None = None
        aggregate: MultiRaidAggregate | None = None

        if village_troops is not None:
            sent_entries = [t for t in result.attacker_troops if t.quantity_initial > 0]
            if sent_entries:
                n_raids_natural = min(
                    available_map.get((t.tribe, t.ordinal), 0) // t.quantity_initial
                    for t in sent_entries
                    if t.quantity_initial > 0
                )
                n_raids = max(0, n_raids_natural)
                if scoring_mode == "aggregate" and n_max_cfg is not None:
                    n_raids = min(n_raids, n_max_cfg)
                raids_possible = n_raids

                remaining_troops_list = []
                for t in result.attacker_troops:
                    avail = available_map.get((t.tribe, t.ordinal), 0)
                    sent = t.quantity_initial
                    remaining = max(0, avail - raids_possible * sent)
                    remaining_troops_list.append(TroopResult(
                        tribe=t.tribe,
                        ordinal=t.ordinal,
                        name=t.name,
                        icon_url=t.icon_url,
                        quantity_initial=avail,
                        quantity_survived=remaining,
                        quantity_lost=avail - remaining,
                    ))

                oleada_drop = result.loot.resources_gained_from_animals
                if oleada_drop is not None:
                    agg_wood  = raids_possible * oleada_drop.wood
                    agg_clay  = raids_possible * oleada_drop.clay
                    agg_iron  = raids_possible * oleada_drop.iron
                    agg_crop  = raids_possible * oleada_drop.crop
                    agg_total = raids_possible * oleada_drop.total
                else:
                    agg_wood = agg_clay = agg_iron = agg_crop = agg_total = 0

                aggregate = MultiRaidAggregate(
                    n_raids=raids_possible,
                    total_resources_gained=AnimalResourceDrop(
                        wood=agg_wood,
                        clay=agg_clay,
                        iron=agg_iron,
                        crop=agg_crop,
                        total=agg_total,
                    ),
                    total_resource_losses=raids_possible * ev["total_resource_losses"],
                    total_troops_sent=raids_possible * ev["troops_sent_count"],
                    total_travel_time_h=(
                        raids_possible * travel_time_h
                        if travel_time_h is not None
                        else None
                    ),
                )
            else:
                raids_possible = 0
                remaining_troops_list = []
                aggregate = MultiRaidAggregate(
                    n_raids=0,
                    total_resources_gained=AnimalResourceDrop(
                        wood=0, clay=0, iron=0, crop=0, total=0
                    ),
                    total_resource_losses=0,
                    total_troops_sent=0,
                    total_travel_time_h=None,
                )

        # Desglose por recurso de las bajas (POR-RAID)
        bd = ev.get("resource_losses_breakdown") or {}
        rlb = AnimalResourceDrop(
            wood=int(bd.get("wood", 0)),
            clay=int(bd.get("clay", 0)),
            iron=int(bd.get("iron", 0)),
            crop=int(bd.get("crop", 0)),
            total=int(bd.get("total", 0)),
        )

        alternatives.append(OptimizationAlternative(
            rank=rank,
            is_winning=ev["is_winning"],
            troops_sent=result.attacker_troops,
            total_losses=ev["total_losses"],
            total_resource_losses=ev["total_resource_losses"],
            troops_sent_count=ev["troops_sent_count"],
            attacker_power=result.attacker_power,
            defender_power=result.defender_power,
            ratio=result.ratio if result.ratio is not None else 0.0,
            resources_gained=result.loot.resources_gained_from_animals,
            loot=None,
            travel_time_h=travel_time_h,
            raids_possible=raids_possible,
            remaining_troops=remaining_troops_list,
            aggregate=aggregate,
            resource_losses_breakdown=rlb,
            net_gain_pct=ev.get("net_gain_pct"),
            attacker_infantry_power=result.attacker_infantry_power,
            attacker_cavalry_power=result.attacker_cavalry_power,
            defender_infantry_power=result.defender_infantry_power,
            defender_cavalry_power=result.defender_cavalry_power,
        ))

    # -----------------------------------------------------------------------
    # Actualizar defender_troops según el resultado
    # -----------------------------------------------------------------------
    if has_winning and alternatives and top:
        best_result = top[0]["result"]
        defender_result_list = best_result.defender_troops
    # else: defender_result_list ya tiene todos los animales intactos (quantity_survived=qty_initial)

    message: str | None = None
    if not has_winning:
        message = (
            "No se encontró ninguna combinación ganadora con los tipos de tropa "
            "disponibles. Se muestran las mejores alternativas disponibles."
        )

    return OptimizationResult(
        alternatives=alternatives,
        has_winning_combination=has_winning,
        defender_troops=defender_result_list,
        warnings=warnings,
        message=message,
    )
