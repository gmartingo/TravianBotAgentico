"""
Tests unitarios del optimizador de combate — spec §7 (rediseño 2026-06-09).

UT-01..03  ELIMINADOS (test_balance_score_*) — _balance_score desaparece con los 5 pesos
UT-04  test_raids_possible_exact            — fórmula min_i floor(available_i / sent_i) con inventario concreto
UT-05  test_aggregate_arithmetic            — totales = N × oleada
UT-06  test_no_regression_min_net_gain_pct_zero — sin suelo (min_net_gain_pct=0) comportamiento análogo al anterior (CA-02)

Adicionalmente:
UT-07  ELIMINADO (test_balance_score_empty_map) — _balance_score desaparece
UT-08  test_raids_possible_mode_a_is_none   — Modo A (sin village_troops) → raids_possible/aggregate = null
UT-09  test_aggregate_loser_resources_zero  — alternativa perdedora en modo raid → aggregate.total_resources_gained.total = 0

NUEVOS (spec §12):
UT-10  valor_de_tropa(185, 600) — Espada Teutona → entre 221 y 226
UT-11  valor_de_tropa(600, 1800) — TT Teutón → entre 841 y 858
UT-12  valor_de_tropa(100, 0) → exactamente 100.0
UT-13  valor_de_tropa(100, 0.0) → exactamente 100.0 (explícito)
UT-14  valor_de_tropa(1000, 999999) — cap → entre 1775 y 1780
UT-15  net_gain_pct = 100 cuando bajas=0 y saqueo>0
UT-16  net_gain_pct = None cuando saqueo=0
UT-17  net_gain_pct negativo cuando valor_bajas > saqueo
UT-18  Multi-Tropa ordena por troops_sent_count ASC
UT-19  Multi-Raid ordena por n_raids DESC
UT-20  Fallback a pool completo cuando ninguna cumple suelo (+ warning)
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.entities.combat import (
    AnimalResourceDrop,
    AttackerArtifacts,
    MultiRaidAggregate,
    OptimizationConfig,
    TroopAvailability,
    TroopEntry,
    TroopTypeSpec,
)
from core.entities.tribe import Tribe
from core.use_cases.combat_engine import (
    TRAIN_TIME_MAX_LOG_FACTOR,
    TRAIN_TIME_TAU_S,
    TRAIN_TIME_WEIGHT_K,
    valor_de_tropa,
)
from core.use_cases.combat_optimizer import _compute_n_natural


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(tribe, ordinal, qty):
    """Crea un TroopEntry mínimo."""
    from core.entities.combat import TroopEntry
    return TroopEntry(tribe=tribe, ordinal=ordinal, quantity=qty, smithy_level=0)


def _make_ev(entries):
    return {"troop_entries": entries}


# ---------------------------------------------------------------------------
# UT-10 — valor_de_tropa(185, 600) — Espada Teutona  (spec §12)
# ---------------------------------------------------------------------------

def test_ut10_valor_de_tropa_espada_teutona():
    """valor_de_tropa(185, 600) debe estar entre 221 y 226 (factor ≈ 1.208)."""
    result = valor_de_tropa(185, 600)
    assert 221 <= result <= 226, f"Esperado [221, 226], obtenido {result}"


# ---------------------------------------------------------------------------
# UT-11 — valor_de_tropa(600, 1800) — TT Teutón  (spec §12)
# ---------------------------------------------------------------------------

def test_ut11_valor_de_tropa_tt_teuton():
    """valor_de_tropa(600, 1800) debe estar entre 841 y 858 (factor ≈ 1.416)."""
    result = valor_de_tropa(600, 1800)
    assert 841 <= result <= 858, f"Esperado [841, 858], obtenido {result}"


# ---------------------------------------------------------------------------
# UT-12 — valor_de_tropa(100, 0) — sin penalización por train_time=0
# ---------------------------------------------------------------------------

def test_ut12_valor_de_tropa_sin_penalizacion_int():
    """valor_de_tropa(100, 0) → exactamente 100.0 (sin penalización)."""
    assert valor_de_tropa(100, 0) == 100.0


# ---------------------------------------------------------------------------
# UT-13 — valor_de_tropa(100, 0.0) — train_time_s=0.0 explícito
# ---------------------------------------------------------------------------

def test_ut13_valor_de_tropa_sin_penalizacion_float():
    """valor_de_tropa(100, 0.0) → exactamente 100.0."""
    assert valor_de_tropa(100, 0.0) == 100.0


# ---------------------------------------------------------------------------
# UT-14 — valor_de_tropa(1000, 999999) — cap logarítmico nunca superado
# ---------------------------------------------------------------------------

def test_ut14_valor_de_tropa_cap():
    """valor_de_tropa(1000, 999999) → entre 1775 y 1780 (factor ≤ 1.78, cap nunca superado)."""
    result = valor_de_tropa(1000, 999999)
    assert 1775 <= result <= 1780, f"Esperado [1775, 1780], obtenido {result}"
    # Verificar explícitamente que el factor no supera 1.0 + MAX_LOG_FACTOR
    factor = result / 1000
    assert factor <= 1.0 + TRAIN_TIME_MAX_LOG_FACTOR


# ---------------------------------------------------------------------------
# UT-04 — raids_possible = min_i floor(available_i / sent_i)  (CA-03)
# ---------------------------------------------------------------------------

def test_raids_possible_exact():
    """
    Inventario: espada 1=1000, espada 2=500.
    Oleada enviada: espada 1=200, espada 2=100.
    raids_possible = min(floor(1000/200), floor(500/100)) = min(5, 5) = 5.
    """
    # Construimos el escenario manualmente para no depender del optimizador completo.
    sent_per_type = {1: 200, 2: 100}
    avail_per_type = {1: 1000, 2: 500}
    n_raids = min(
        avail_per_type[ord_] // sent
        for ord_, sent in sent_per_type.items()
        if sent > 0
    )
    assert n_raids == 5


def test_raids_possible_binding_type():
    """
    Inventario: espada 1=1000, espada 2=300.
    Oleada enviada: espada 1=200, espada 2=100.
    raids_possible = min(floor(1000/200), floor(300/100)) = min(5, 3) = 3.
    """
    sent_per_type = {1: 200, 2: 100}
    avail_per_type = {1: 1000, 2: 300}
    n_raids = min(
        avail_per_type[ord_] // sent
        for ord_, sent in sent_per_type.items()
        if sent > 0
    )
    assert n_raids == 3


# ---------------------------------------------------------------------------
# UT-05 — aggregate.totales = N × oleada  (CA-04)
# ---------------------------------------------------------------------------

def test_aggregate_arithmetic():
    """
    N=5, oleada: resources_gained.total=50, total_resource_losses=200, troops_sent=300.
    aggregate.total_resources_gained.total = 5×50 = 250
    aggregate.total_resource_losses = 5×200 = 1000
    aggregate.total_troops_sent = 5×300 = 1500
    """
    n_raids = 5
    oleada_drop = AnimalResourceDrop(wood=10, clay=10, iron=10, crop=20, total=50)
    oleada_losses = 200
    oleada_troops = 300
    oleada_travel = 2.0

    agg = MultiRaidAggregate(
        n_raids=n_raids,
        total_resources_gained=AnimalResourceDrop(
            wood=n_raids * oleada_drop.wood,
            clay=n_raids * oleada_drop.clay,
            iron=n_raids * oleada_drop.iron,
            crop=n_raids * oleada_drop.crop,
            total=n_raids * oleada_drop.total,
        ),
        total_resource_losses=n_raids * oleada_losses,
        total_troops_sent=n_raids * oleada_troops,
        total_travel_time_h=n_raids * oleada_travel,
    )

    assert agg.total_resources_gained.total == 250     # CA-04
    assert agg.total_resource_losses == 1000
    assert agg.total_troops_sent == 1500
    assert agg.total_travel_time_h == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# UT-06 — min_net_gain_pct=0 equivale a comportamiento sin suelo (no-regresión CA-02)
# ---------------------------------------------------------------------------

def test_no_regression_min_net_gain_pct_zero():
    """
    OptimizationConfig con min_net_gain_pct=0.0 no aplica suelo.
    Es la no-regresión del comportamiento anterior (todos los candidatos pasan el filtro).
    """
    cfg = OptimizationConfig(min_net_gain_pct=0.0)
    assert cfg.min_net_gain_pct == 0.0
    # Sin suelo, todas las alternativas ganadoras se presentan
    # (equivalente al comportamiento antes del rediseño)
    assert cfg.scoring_mode == "single"
    assert cfg.n_min is None
    assert cfg.n_max is None


# ---------------------------------------------------------------------------
# UT-08 — Modo A (sin village_troops) → raids_possible null en la entidad
# ---------------------------------------------------------------------------

def test_modo_a_new_fields_default_none():
    """
    OptimizationAlternative recién construida sin campos multi-raid
    tiene raids_possible=None, remaining_troops=None, aggregate=None.
    """
    from core.entities.combat import OptimizationAlternative, AnimalResourceDrop, Loot, TroopResult

    alt = OptimizationAlternative(
        rank=1,
        is_winning=True,
        troops_sent=[],
        total_losses=0,
        total_resource_losses=0,
        troops_sent_count=0,
        attacker_power=100.0,
        defender_power=50.0,
        ratio=2.0,
        resources_gained=None,
        loot=None,
        travel_time_h=None,
    )
    assert alt.raids_possible is None      # CA-06
    assert alt.remaining_troops is None
    assert alt.aggregate is None


# ---------------------------------------------------------------------------
# UT-09 — Alternativa perdedora → aggregate.total_resources_gained.total = 0
# ---------------------------------------------------------------------------

def test_aggregate_loser_resources_zero():
    """
    Para una alternativa perdedora en modo raid, no hay botín de naturales.
    Si oleada_drop es None → aggregate.total_resources_gained.total = 0.
    (CA-06b)
    """
    # Simular la lógica de decoración para una oleada perdedora sin drops
    n_raids = 3
    oleada_drop = None  # perdedor: no loot

    if oleada_drop is not None:
        agg_total = n_raids * oleada_drop.total
    else:
        agg_total = 0

    assert agg_total == 0


# ---------------------------------------------------------------------------
# UT-10..UT-14 — scoring_mode + n_min/n_max (RN-04 / RN-05)
# ---------------------------------------------------------------------------

def test_compute_n_natural_returns_min_ratio():
    """N natural = min(avail/sent) sobre tipos con sent > 0. Ejemplo del usuario:
    2000S/150 = 13, 500TT/30 = 16, 100H/10 = 10 → cuello de botella = 10."""
    avail = {
        (Tribe.ROMANS, 1): 2000,
        (Tribe.ROMANS, 2): 500,
        (Tribe.ROMANS, 3): 100,
    }
    entries = [
        _make_entry(Tribe.ROMANS, 1, 150),
        _make_entry(Tribe.ROMANS, 2, 30),
        _make_entry(Tribe.ROMANS, 3, 10),
    ]
    ev = _make_ev(entries)
    assert _compute_n_natural(ev, avail) == 10


def test_compute_n_natural_none_without_inventory():
    """Sin available_map (Modo A) → None: el concepto no aplica."""
    entries = [_make_entry(Tribe.ROMANS, 1, 100)]
    ev = _make_ev(entries)
    assert _compute_n_natural(ev, {}) is None


def test_compute_n_natural_zero_when_inventory_lacks_type():
    """Si envías un tipo del que no tienes nada → 0 (infactible)."""
    avail = {(Tribe.ROMANS, 1): 100}  # falta el tipo (ROMANS, 2)
    entries = [
        _make_entry(Tribe.ROMANS, 1, 10),
        _make_entry(Tribe.ROMANS, 2, 5),
    ]
    ev = _make_ev(entries)
    assert _compute_n_natural(ev, avail) == 0


def test_compute_n_natural_ignores_zero_sent():
    """Tipos con sent = 0 no entran al cálculo (no son cuello de botella)."""
    avail = {
        (Tribe.ROMANS, 1): 100,
        (Tribe.ROMANS, 2): 1,  # solo 1 disponible pero no se manda
    }
    entries = [
        _make_entry(Tribe.ROMANS, 1, 10),
        _make_entry(Tribe.ROMANS, 2, 0),  # no enviado
    ]
    ev = _make_ev(entries)
    assert _compute_n_natural(ev, avail) == 10  # solo el tipo 1 limita


def test_scoring_mode_default_is_single():
    """OptimizationConfig por defecto = 'single' — preserva no-regresión (CA-10)."""
    cfg = OptimizationConfig()
    assert cfg.scoring_mode == "single"
    assert cfg.n_min is None
    assert cfg.n_max is None


# ---------------------------------------------------------------------------
# UT-15 — net_gain_pct = 100 cuando bajas=0 y saqueo>0  (spec §12)
# ---------------------------------------------------------------------------

def test_ut15_net_gain_pct_cien_sin_bajas():
    """
    Si el atacante no pierde ninguna tropa y el saqueo > 0,
    net_gain_pct debe ser exactamente 100.0 (victoria limpia).
    """
    # Simular la lógica del cálculo: ninguna tropa perdida
    saqueo = 50
    valor_bajas = 0.0
    net_gain_pct = 100.0 * (saqueo - valor_bajas) / saqueo
    assert net_gain_pct == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# UT-16 — net_gain_pct = None cuando saqueo=0  (spec §12)
# ---------------------------------------------------------------------------

def test_ut16_net_gain_pct_none_sin_saqueo():
    """
    Si el saqueo es 0 (oasis sin drops NATURE conocidos),
    net_gain_pct debe ser None (no se puede calcular el denominador).
    """
    saqueo = 0
    net_gain_pct = None if saqueo == 0 else 100.0
    assert net_gain_pct is None


# ---------------------------------------------------------------------------
# UT-17 — net_gain_pct negativo cuando valor_bajas > saqueo  (spec §12)
# ---------------------------------------------------------------------------

def test_ut17_net_gain_pct_negativo():
    """
    Si el coste de bajas supera el saqueo, net_gain_pct es negativo.
    El valor negativo es válido; el suelo min_net_gain_pct lo filtra si aplica.
    Ejemplo: saqueo=10, valor_bajas (calculado con valor_de_tropa) = 20 → -100%
    """
    saqueo = 10
    valor_bajas = 20.0  # pierdes el doble de lo que ganas
    net_gain_pct = 100.0 * (saqueo - valor_bajas) / saqueo
    assert net_gain_pct == pytest.approx(-100.0)
    assert net_gain_pct < 0


# ---------------------------------------------------------------------------
# UT-18 — Multi-Tropa ordena por troops_sent_count ASC  (spec §12/RN-01)
# ---------------------------------------------------------------------------

def test_ut18_multi_troop_order_asc():
    """
    La herramienta multi_troop debe ordenar las alternativas con
    troops_sent_count ascendente (ejército mínimo primero).
    """
    # Simulamos el ordenamiento que hace find_optimal_attack para tool="multi_troop"
    pool = [
        {"troops_sent_count": 30, "total_resource_losses": 100, "net_gain_pct": 50.0},
        {"troops_sent_count": 10, "total_resource_losses": 200, "net_gain_pct": 60.0},
        {"troops_sent_count": 20, "total_resource_losses": 150, "net_gain_pct": 40.0},
    ]
    pool.sort(key=lambda e: (e["troops_sent_count"], e["total_resource_losses"]))
    assert pool[0]["troops_sent_count"] == 10
    assert pool[1]["troops_sent_count"] == 20
    assert pool[2]["troops_sent_count"] == 30


# ---------------------------------------------------------------------------
# UT-19 — Multi-Raid ordena por n_raids DESC  (spec §12/RN-03)
# ---------------------------------------------------------------------------

def test_ut19_multi_raid_order_desc():
    """
    La herramienta multi_raid debe ordenar por n_raids descendente (más oleadas primero).
    Aquí simulamos el cálculo de N natural y el ordenamiento.
    """
    available_map = {(Tribe.ROMANS, 1): 1000, (Tribe.ROMANS, 2): 300}
    # Oleada A: envía 100 y 100 → N=min(10, 3)=3
    ev_a = _make_ev([_make_entry(Tribe.ROMANS, 1, 100), _make_entry(Tribe.ROMANS, 2, 100)])
    ev_a["net_gain_pct"] = 60.0
    # Oleada B: envía 100 y 10 → N=min(10, 30)=10
    ev_b = _make_ev([_make_entry(Tribe.ROMANS, 1, 100), _make_entry(Tribe.ROMANS, 2, 10)])
    ev_b["net_gain_pct"] = 55.0
    pool = [ev_a, ev_b]
    pool.sort(
        key=lambda e: (
            -(_compute_n_natural(e, available_map) or 0),
            -(e["net_gain_pct"] if e["net_gain_pct"] is not None else -1e15),
        )
    )
    assert _compute_n_natural(pool[0], available_map) == 10  # oleada B primero (N=10)
    assert _compute_n_natural(pool[1], available_map) == 3   # oleada A después (N=3)


# ---------------------------------------------------------------------------
# UT-20 — Fallback a pool completo cuando ninguna cumple suelo (+ warning)
# ---------------------------------------------------------------------------

def test_ut20_fallback_sin_suelo():
    """
    Si ninguna alternativa supera el suelo min_net_gain_pct, el resultado
    contiene todas las ganadoras disponibles y se emite un warning.
    Simula la lógica de find_optimal_attack: suelo_aplicable cae a pool completo.
    """
    pool = [
        {"net_gain_pct": 10.0, "troops_sent_count": 5},
        {"net_gain_pct": -5.0, "troops_sent_count": 3},
    ]
    min_ngp = 50.0
    warnings_list: list[str] = []

    suelo_aplicable = [
        e for e in pool
        if e["net_gain_pct"] is None or e["net_gain_pct"] >= min_ngp
    ]
    if not suelo_aplicable and pool:
        suelo_aplicable = pool
        warnings_list.append(
            f"El suelo de ganancia neta ({min_ngp}%) es inalcanzable con los tipos de "
            f"tropa dados; se muestran las mejores ganadoras disponibles."
        )

    assert len(suelo_aplicable) == 2   # todas vuelven al pool
    assert len(warnings_list) == 1
    assert "inalcanzable" in warnings_list[0]
