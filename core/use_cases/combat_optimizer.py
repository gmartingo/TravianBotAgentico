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
    exponent: float,
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
        exponent=exponent,
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
    exponent: float,
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
    Busca combinaciones de tropas por muestreo en pasos del 10%.

    Para Modo A (max=0): estima la cantidad mínima ganadora y muestrea en torno a ella.
    Para Modo B (max>0): muestrea {0%, 10%, ..., 100%} de la cantidad disponible.
    """
    n = len(troop_specs)
    candidates: list[dict] = []

    # Para Modo A, necesitamos una escala de referencia.
    # Empezamos con una cantidad razonable para estimar (p.ej. 100 por tipo).
    scale = [
        max_q if max_q > 0 else 100
        for max_q in max_quantities
    ]
    steps = 10  # pasos del 10%

    # Generar combinaciones por proporciones discretas
    ranges = [list(range(0, scale[i] + 1, max(1, scale[i] // steps))) for i in range(n)]
    # Asegurar que el máximo está incluido
    for i in range(n):
        if scale[i] not in ranges[i]:
            ranges[i].append(scale[i])

    total_combos = 1
    for r in ranges:
        total_combos *= len(r)

    if total_combos > 200_000:
        # Reducir resolución si hay demasiadas combinaciones
        steps = 5
        ranges = [list(range(0, scale[i] + 1, max(1, scale[i] // steps))) for i in range(n)]
        for i in range(n):
            if scale[i] not in ranges[i]:
                ranges[i].append(scale[i])

    # Evaluar todas las combinaciones
    tasks = []
    combo_list = list(itertools.product(*ranges))

    # Evaluar en batch asíncrono (secuencialmente para no saturar la BD)
    for combo in combo_list:
        quantities = list(combo)
        if all(q == 0 for q in quantities):
            continue
        tasks.append(quantities)

    evaluated: list[dict] = []
    for quantities in tasks:
        ev = await _evaluate_combination(
            quantities=quantities,
            troop_specs=troop_specs,
            attacker_tribe=attacker_tribe,
            hero_attack_points=hero_attack_points,
            hero_attack_bonus_percent=hero_attack_bonus_percent,
            alliance_bonus=alliance_bonus,
            artifacts=artifacts,
            oasis_defenders=oasis_defenders,
            exponent=exponent,
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
    exponent: float,
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
                        exponent=exponent,
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
        evaluated = await _optimize_by_sampling(
            troop_specs=troop_specs,
            max_quantities=max_quantities,
            attacker_tribe=attacker_tribe,
            hero_attack_points=hero_attack_points,
            hero_attack_bonus_percent=hero_attack_bonus_percent,
            alliance_bonus=alliance_bonus,
            artifacts=artifacts,
            oasis_defenders=oasis_defenders,
            exponent=opt_config.exponent,
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
            exponent=opt_config.exponent,
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
    # Ordenar por score ponderado
    # -----------------------------------------------------------------------
    w = opt_config.optimization_weights
    all_w = w.resources_gained + w.total_losses + w.troops_sent + w.travel_time
    if all_w == 0:
        # Todos los pesos en 0: usar pesos iguales con warning
        warnings.append(
            "Todos los pesos de optimización son 0 — aplicando pesos iguales."
        )
        w_res, w_loss, w_troops, w_time = 1.0, 1.0, 1.0, 0.0
    else:
        w_res = w.resources_gained
        w_loss = w.total_losses
        w_troops = w.troops_sent
        w_time = w.travel_time

    def _score(e: dict) -> float:
        # Menor es mejor para todos (recursos se invierten con neg_resources)
        return (
            w_res * e.get("neg_resources", 0)
            + w_loss * e.get("total_resource_losses", 0)
            + w_troops * e.get("troops_sent_count", 0)
            + w_time * e.get("travel_time_h", 0)
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
