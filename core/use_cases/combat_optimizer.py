"""
Optimizador de ataque a oasis — frente de Pareto multi-objetivo.

Estrategia principal: NSGA-II via pymoo.
Fallback (si pymoo no disponible o N <= 5): búsqueda por muestreo con comparación de dominancia.

Ver spec §RN-09, §RN-10 y §9 (Algoritmo optimizador).
Añadido en la feature simulador-combate (2026-05-29).
"""
from __future__ import annotations

import asyncio
import itertools
import logging
from typing import Any

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
from core.use_cases.combat_engine import simulate_combat

logger = logging.getLogger(__name__)

# Intentar importar pymoo; si falla, usar fallback por muestreo
try:
    import numpy as np
    from pymoo.algorithms.moo.nsga2 import NSGA2
    from pymoo.core.problem import ElementwiseProblem
    from pymoo.optimize import minimize
    from pymoo.termination import get_termination

    _PYMOO_AVAILABLE = True
except ImportError:
    _PYMOO_AVAILABLE = False
    logger.info(
        "pymoo no disponible — el optimizador usará fallback por muestreo (N<=5 tipos de tropas)."
    )

# Número máximo de tipos de tropas para el fallback por muestreo
_FALLBACK_MAX_N = 5


# ---------------------------------------------------------------------------
# Helpers de dominancia de Pareto
# ---------------------------------------------------------------------------

def _dominates(a: dict, b: dict) -> bool:
    """
    True si la solución 'a' domina a 'b' en el espacio de objetivos.

    a domina b si:
      - es mejor o igual en TODOS los objetivos
      - es estrictamente mejor en AL MENOS uno

    Objetivos (todos a minimizar):
      - neg_resources_gained (negativo de recursos ganados → minimizar)
      - total_resource_losses (minimizar)
      - troops_sent_count    (minimizar)
      - travel_time_h        (minimizar, 0 si sin distancia)
    """
    keys = ["neg_resources", "total_resource_losses", "troops_sent_count", "travel_time_h"]
    better_in_all = all(a.get(k, 0) <= b.get(k, 0) for k in keys)
    strictly_better = any(a.get(k, 0) < b.get(k, 0) for k in keys)
    return better_in_all and strictly_better


def _compute_pareto_front(candidates: list[dict]) -> list[dict]:
    """
    Devuelve el subconjunto de candidatos que forman el frente de Pareto.
    Una solución está en el frente si ninguna otra la domina.
    """
    pareto: list[dict] = []
    for candidate in candidates:
        dominated = False
        for other in candidates:
            if other is candidate:
                continue
            if _dominates(other, candidate):
                dominated = True
                break
        if not dominated:
            pareto.append(candidate)
    return pareto


# ---------------------------------------------------------------------------
# Balance score (Modo B/C — inventario)
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


def _balance_score(ev: dict, available_map: dict) -> float:
    """
    Mide el desequilibrio relativo del uso del inventario.
    Retorna stdev(sent_i / available_i) para los tipos con sent > 0 y available > 0.
    Un score bajo = uso más equilibrado entre tipos de tropa.

    available_map: {(tribe, ordinal): quantity_available}
    ev["troops_sent"]: lista de TroopResult con quantity_initial = enviadas.

    Retorna 0.0 si hay 0 o 1 tipo activo (sin stdev definido), o si available_map vacío.
    """
    import statistics
    ratios: list[float] = []
    for t in ev.get("troop_entries", []):
        key = (t.tribe, t.ordinal)
        avail = available_map.get(key, 0)
        sent = t.quantity
        if sent > 0 and avail > 0:
            ratios.append(sent / avail)
    if len(ratios) <= 1:
        return 0.0
    return statistics.stdev(ratios)


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
        # Objetivos para dominancia (todos a minimizar)
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
    weights: dict,
    server_version: str = "1.45",
    # RN-05: cuando se reciben, el muestreo añade una fase dirigida a producir
    # oleadas con N ∈ [n_min, n_max] (la fase fina por sí sola no alcanza el
    # tramo grande de Espadas+TT necesario para esos N).
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

    # ── Fase 3 — dirigida por rango N (RN-05) ────────────────────────────────
    # Solo activa si el usuario pidió un rango y hay inventario real (Modo C).
    # Genera oleadas tales que floor(min_i avail_i / sent_i) ∈ [n_min, n_max].
    # Esencial porque las fases gruesa+fina nunca evalúan combos donde un tipo
    # vaya a ~13 unidades y otro a ~90 a la vez (la fina tope ~21).
    if (n_min is not None or n_max is not None) and all(m > 0 for m in max_quantities):
        # Rango por tipo: sent_i debe estar en [ceil(avail/n_max), floor(avail/n_min)]
        # para que N quede en [n_min, n_max]. Si solo se da uno de los dos, el otro
        # extremo queda abierto.
        range_lo_hi: list[tuple[int, int]] = []
        for i, avail in enumerate(max_quantities):
            if avail <= 0:
                range_lo_hi.append((0, 0))
                continue
            lo = (avail + n_max - 1) // n_max if n_max else 1
            hi = avail // n_min if n_min else avail
            lo = max(0, min(avail, lo))
            hi = max(lo, min(avail, hi))
            range_lo_hi.append((lo, hi))

        # Cada tipo se muestrea con paso 1 si el rango es pequeño; si es grande,
        # se reparte uniformemente con un máximo de ~8 puntos por tipo para
        # mantener el producto cartesiano dentro del presupuesto.
        range_samples: list[list[int]] = []
        for lo, hi in range_lo_hi:
            if hi <= lo:
                range_samples.append([lo])
                continue
            span = hi - lo + 1
            if span <= 8:
                pts = list(range(lo, hi + 1))
            else:
                step = max(1, span // 8)
                pts = list(range(lo, hi + 1, step))
                if hi not in pts:
                    pts.append(hi)
            range_samples.append(pts)

        for combo in itertools.product(*range_samples):
            if all(q == 0 for q in combo):
                continue
            if combo in seen:
                continue
            seen.add(combo)
            combos_to_eval.append(list(combo))

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
# Optimizador con pymoo NSGA-II
# ---------------------------------------------------------------------------

async def _optimize_with_nsga2(
    troop_specs: list[dict],
    max_quantities: list[int],
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
    weights: dict,
    server_version: str = "1.45",
) -> list[dict]:
    """
    Optimización con NSGA-II de pymoo.

    Ejecuta la búsqueda en el executor de asyncio para no bloquear el event loop.
    """
    import numpy as np
    from pymoo.algorithms.moo.nsga2 import NSGA2
    from pymoo.core.problem import ElementwiseProblem
    from pymoo.optimize import minimize
    from pymoo.termination import get_termination

    n = len(troop_specs)
    upper_bounds = [
        (max_q if max_q > 0 else 1000)
        for max_q in max_quantities
    ]

    # Cache de evaluaciones para evitar re-simular combinaciones idénticas
    _cache: dict[tuple, dict | None] = {}

    # Lista para acumular resultados evaluados desde el callback
    evaluated_results: list[dict] = []

    # Referencia al event loop para llamar await dentro del executor
    loop = asyncio.get_event_loop()

    class CombatProblem(ElementwiseProblem):
        def __init__(self):
            xl = np.zeros(n)
            xu = np.array(upper_bounds, dtype=float)
            super().__init__(n_var=n, n_obj=4, n_ieq_constr=1, xl=xl, xu=xu)

        def _evaluate(self, x, out, *args, **kwargs):
            quantities = [max(0, int(round(v))) for v in x]
            key = tuple(quantities)

            if key in _cache:
                ev = _cache[key]
            else:
                # Llamar evaluate en el event loop
                future = asyncio.run_coroutine_threadsafe(
                    _evaluate_combination(
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
                    ),
                    loop,
                )
                ev = future.result(timeout=30)
                _cache[key] = ev

            if ev is None:
                out["F"] = [1e9, 1e9, 1e9, 1e9]
                out["G"] = [1.0]  # infeasible: restricción no cumplida
                return

            evaluated_results.append(ev)

            f1 = float(ev["neg_resources"])
            f2 = float(ev["total_resource_losses"])
            f3 = float(ev["troops_sent_count"])
            f4 = float(ev["travel_time_h"])

            out["F"] = [f1, f2, f3, f4]
            # Restricción: al menos 1 tropa enviada (G <= 0 para ser feasible)
            out["G"] = [-1.0]  # siempre feasible si llegamos aquí

    def _run_nsga2():
        problem = CombatProblem()
        algorithm = NSGA2(pop_size=50)
        termination = get_termination("n_gen", 30)
        result = minimize(problem, algorithm, termination, seed=42, verbose=False)
        return result

    # Ejecutar en thread pool para no bloquear el event loop
    result = await asyncio.get_event_loop().run_in_executor(None, _run_nsga2)

    return evaluated_results


# ---------------------------------------------------------------------------
# Función principal: find_optimal_attack
# ---------------------------------------------------------------------------

async def find_optimal_attack(
    attacker_tribe: Tribe,
    troop_types: list[TroopTypeSpec] | None,      # Modo A
    village_troops: list[TroopAvailability] | None,  # Modo B
    hero_attack_points: float,
    hero_attack_bonus_percent: float,
    alliance_bonus: float,
    artifacts: AttackerArtifacts,
    oasis_defenders: list[TroopEntry],
    opt_config: OptimizationConfig,
    lang: str,
    game_data_port: GameDataPort,
    translation_port: TranslationPort,
    server_version: str = "1.45",
) -> OptimizationResult:
    """
    Encuentra la combinación óptima de tropas para atacar un oasis.

    Modo A (troop_types): tipos de tropas sin cantidad máxima.
    Modo B (village_troops): tropas disponibles con cantidad máxima.

    Ver spec §RN-10 y §9 (Algoritmo optimizador).
    """
    warnings: list[str] = []

    # -----------------------------------------------------------------------
    # Construir troop_specs con speeds (para cálculo de travel_time_h)
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
            troop_specs.append({
                "tribe": attacker_tribe,
                "ordinal": ts.ordinal,
                "smithy_level": ts.smithy_level,
                "speed": stats.get("speed") or 1,
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
            troop_specs.append({
                "tribe": attacker_tribe,
                "ordinal": tv.ordinal,
                "smithy_level": tv.smithy_level,
                "speed": stats.get("speed") or 1,
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

    # Construir defender_troops de referencia (para el response)
    # Inicialmente con todos los animales vivos (se actualizará en cada alternativa)
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
            quantity_survived=entry.quantity,  # valor provisional
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
            "No hay datos de drops de animales de naturaleza. "
            "El objetivo 'recursos ganados' se ignoró en la optimización."
        )

    # -----------------------------------------------------------------------
    # Elegir estrategia de optimización
    # -----------------------------------------------------------------------
    n = len(troop_specs)
    use_sampling = (not _PYMOO_AVAILABLE) or (n <= _FALLBACK_MAX_N)

    if use_sampling:
        # RN-05: pasamos n_min/n_max al muestreo SOLO si Modo C agregado
        # (en single los campos se ignoran de extremo a extremo).
        _sampling_n_min = opt_config.n_min if opt_config.scoring_mode == "aggregate" else None
        _sampling_n_max = opt_config.n_max if opt_config.scoring_mode == "aggregate" else None
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
            weights={
                "resources_gained": opt_config.optimization_weights.resources_gained,
                "total_losses": opt_config.optimization_weights.total_losses,
                "troops_sent": opt_config.optimization_weights.troops_sent,
                "travel_time": opt_config.optimization_weights.travel_time,
            },
            server_version=server_version,
            n_min=_sampling_n_min,
            n_max=_sampling_n_max,
        )
    else:
        warnings.append(
            f"N={n} tipos de tropas → usando NSGA-II (pymoo). "
            f"El cálculo puede tardar varios segundos."
        )
        evaluated = await _optimize_with_nsga2(
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
            weights={
                "resources_gained": opt_config.optimization_weights.resources_gained,
                "total_losses": opt_config.optimization_weights.total_losses,
                "troops_sent": opt_config.optimization_weights.troops_sent,
                "travel_time": opt_config.optimization_weights.travel_time,
            },
            server_version=server_version,
        )

    if not evaluated:
        raise ValueError("No se pudo evaluar ninguna combinación de tropas.")

    # -----------------------------------------------------------------------
    # Separar ganadoras de no-ganadoras
    # -----------------------------------------------------------------------
    winning = [e for e in evaluated if e["is_winning"]]
    losing = [e for e in evaluated if not e["is_winning"]]

    has_winning = len(winning) > 0
    pool = winning if has_winning else losing

    # -----------------------------------------------------------------------
    # Calcular frente de Pareto del pool (con pesos para ordenar)
    # -----------------------------------------------------------------------
    pareto = _compute_pareto_front(pool)
    if not pareto:
        pareto = pool  # fallback: si todos se dominan entre sí, tomar todos

    # -----------------------------------------------------------------------
    # Construir available_map para balance_score (solo en Modo B/C)
    # -----------------------------------------------------------------------
    available_map: dict = {}
    if village_troops:
        for tv in village_troops:
            available_map[(tv.tribe, tv.ordinal)] = tv.quantity_available

    # -----------------------------------------------------------------------
    # Ordenar por score ponderado
    # -----------------------------------------------------------------------
    w = opt_config.optimization_weights
    all_w = w.resources_gained + w.total_losses + w.troops_sent + w.travel_time + w.balance
    if all_w == 0:
        # Todos los pesos en 0: usar pesos iguales con warning
        warnings.append(
            "Todos los pesos de optimización son 0 — aplicando pesos iguales."
        )
        w_res, w_loss, w_troops, w_time, w_balance = 1.0, 1.0, 1.0, 0.0, 0.0
    else:
        w_res = w.resources_gained
        w_loss = w.total_losses
        w_troops = w.troops_sent
        w_time = w.travel_time
        w_balance = w.balance

    # RN-04 / RN-05: scoring agregado opcional + acotación de N por rango usuario.
    scoring_mode = opt_config.scoring_mode
    n_min_cfg = opt_config.n_min
    n_max_cfg = opt_config.n_max

    # Constante de penalización para infactibles (RN-05). Suficientemente
    # grande para empujar TODA infactible por debajo de cualquier factible
    # razonable, pero finita para que el ranking entre infactibles dependa de
    # la distancia a n_min (lo más cerca, mejor).
    _INFEASIBLE_BASE = 1e15

    def _score(e: dict) -> float:
        # Menor es mejor para todos (recursos se invierten con neg_resources)
        bs = _balance_score(e, available_map) if available_map else 0.0
        # n_factor multiplica los términos por-raid cuando el usuario optimiza
        # por agregado de N raids (Modo C). En "single" siempre es 1.
        n_factor = 1
        infeasibility = 0.0
        if scoring_mode == "aggregate" and available_map:
            n_nat = _compute_n_natural(e, available_map)
            if n_nat is not None and n_nat > 0:
                if n_min_cfg is not None and n_nat < n_min_cfg:
                    # Infactible. Devolvemos puntuación base alta + distancia
                    # ponderada para que entre infactibles gane el que MÁS se
                    # acerca a n_min (RN-05 refinado tras prueba de usuario).
                    n_factor = n_nat
                    infeasibility = _INFEASIBLE_BASE + (n_min_cfg - n_nat) * 1e9
                else:
                    n_factor = n_nat if n_max_cfg is None else min(n_nat, n_max_cfg)
        return (
            infeasibility
            + w_res * n_factor * e.get("neg_resources", 0)
            + w_loss * n_factor * e.get("total_resource_losses", 0)
            + w_troops * n_factor * e.get("troops_sent_count", 0)
            + w_time * n_factor * e.get("travel_time_h", 0)
            + w_balance * bs
        )

    pareto.sort(key=_score)
    top = pareto[: opt_config.top_n]

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
            # Calcular raids_possible = min_i floor(available_i / sent_i)
            # para todos los tipos con sent_i > 0
            sent_entries = [t for t in result.attacker_troops if t.quantity_initial > 0]
            if sent_entries:
                n_raids_natural = min(
                    available_map.get((t.tribe, t.ordinal), 0) // t.quantity_initial
                    for t in sent_entries
                    if t.quantity_initial > 0
                )
                n_raids = max(0, n_raids_natural)
                # RN-05: n_max cappea el N visible al usuario solo en modo aggregate.
                # En "single" se mantiene el N natural.
                if scoring_mode == "aggregate" and n_max_cfg is not None:
                    n_raids = min(n_raids, n_max_cfg)
                # RN-05: si el N natural no alcanza el mínimo pedido, dejamos el N visible
                # como el natural (el dato real) y emitimos el warning global más abajo.
                raids_possible = n_raids

                # remaining_troops: available_i - n_raids × sent_i (clamp 0)
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

                # aggregate: N × métricas de esta oleada
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
                # Sin tropas enviadas en el resultado: valores vacíos
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

        # Desglose por recurso de las bajas (POR-RAID), reusa AnimalResourceDrop.
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
            loot=None,  # loot es null en el optimizador (sin village_resources)
            travel_time_h=travel_time_h,
            raids_possible=raids_possible,
            remaining_troops=remaining_troops_list,
            aggregate=aggregate,
            resource_losses_breakdown=rlb,
            attacker_infantry_power=result.attacker_infantry_power,
            attacker_cavalry_power=result.attacker_cavalry_power,
            defender_infantry_power=result.defender_infantry_power,
            defender_cavalry_power=result.defender_cavalry_power,
        ))

    # -----------------------------------------------------------------------
    # Actualizar defender_troops según el resultado
    # -----------------------------------------------------------------------
    if has_winning and alternatives and top:
        # Ganadoras: mostrar estado real de los defensores tras el combate ganador
        best_result = top[0]["result"]
        defender_result_list = best_result.defender_troops
    else:
        # Sin ganadoras: el oasis NO fue destruido.
        # Todos los animales "sobreviven" con quantity_survived = quantity_initial.
        # Ver spec §8 nota crítica: "la defensa del oasis no fue atacada con éxito".
        for dt in defender_result_list:
            # Forzar estado intacto (quantity_survived ya fue inicializado como quantity_initial)
            pass  # defender_result_list ya tiene quantity_survived = quantity_initial

    # RN-05: si el usuario pidió n_min y ninguna alternativa del top lo alcanza,
    # avisar para que la UI lo refleje (las alternativas infactibles ya quedaron
    # al fondo del ranking por el +inf en _score).
    if scoring_mode == "aggregate" and n_min_cfg is not None and alternatives:
        best_n = alternatives[0].raids_possible or 0
        if best_n < n_min_cfg:
            warnings.append(
                f"Ninguna combinación alcanza el mínimo de {n_min_cfg} raids con el "
                f"inventario disponible (mejor: {best_n})."
            )

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
