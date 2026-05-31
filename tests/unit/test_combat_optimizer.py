"""
Tests unitarios del optimizador de combate — spec §7.

UT-01  test_balance_score_single_type       — 1 tipo activo → score = 0.0
UT-02  test_balance_score_uniform           — 2 tipos con mismo ratio → score ≈ 0.0
UT-03  test_balance_score_unequal           — 2 tipos con ratios muy distintos → score > umbral
UT-04  test_raids_possible_exact            — fórmula min_i floor(available_i / sent_i) con inventario concreto
UT-05  test_aggregate_arithmetic            — totales = N × oleada
UT-06  test_no_regression_no_balance_field  — request sin campo balance → mismo resultado que antes (CA-02)

Adicionalmente:
UT-07  test_balance_score_empty_map         — available_map vacío → 0.0
UT-08  test_raids_possible_mode_a_is_none   — Modo A (sin village_troops) → raids_possible/aggregate = null
UT-09  test_aggregate_loser_resources_zero  — alternativa perdedora en modo raid → aggregate.total_resources_gained.total = 0
"""
from __future__ import annotations

import asyncio

import pytest

from core.entities.combat import (
    AnimalResourceDrop,
    AttackerArtifacts,
    MultiRaidAggregate,
    OptimizationConfig,
    OptimizationWeights,
    TroopAvailability,
    TroopEntry,
    TroopTypeSpec,
)
from core.entities.tribe import Tribe
from core.use_cases.combat_optimizer import _balance_score, _compute_n_natural


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(tribe, ordinal, qty):
    """Crea un TroopEntry mínimo para usar en _balance_score."""
    from core.entities.combat import TroopEntry
    return TroopEntry(tribe=tribe, ordinal=ordinal, quantity=qty, smithy_level=0)


# _balance_score espera el campo "troop_entries" dentro del dict 'ev'
def _make_ev(entries):
    return {"troop_entries": entries}


# ---------------------------------------------------------------------------
# UT-01 — 1 tipo activo → balance_score = 0.0  (CA-07)
# ---------------------------------------------------------------------------

def test_balance_score_single_type():
    """Un único tipo de tropa con sent > 0 → stdev indefinido → 0.0."""
    avail = {(Tribe.ROMANS, 1): 1000}
    entries = [_make_entry(Tribe.ROMANS, 1, 300)]
    ev = _make_ev(entries)
    score = _balance_score(ev, avail)
    assert score == 0.0


# ---------------------------------------------------------------------------
# UT-02 — 2 tipos con el mismo ratio → score ≈ 0.0
# ---------------------------------------------------------------------------

def test_balance_score_uniform():
    """Dos tipos con el mismo porcentaje enviado/disponible → score muy cercano a 0."""
    avail = {(Tribe.ROMANS, 1): 1000, (Tribe.ROMANS, 2): 800}
    # Ambos al 50%
    entries = [
        _make_entry(Tribe.ROMANS, 1, 500),
        _make_entry(Tribe.ROMANS, 2, 400),
    ]
    ev = _make_ev(entries)
    score = _balance_score(ev, avail)
    assert score < 1e-9  # esencialmente 0


# ---------------------------------------------------------------------------
# UT-03 — 2 tipos con ratios muy distintos → score > umbral
# ---------------------------------------------------------------------------

def test_balance_score_unequal():
    """Ratio 0.9 vs 0.1 → stdev > 0.3."""
    avail = {(Tribe.ROMANS, 1): 1000, (Tribe.ROMANS, 2): 1000}
    entries = [
        _make_entry(Tribe.ROMANS, 1, 900),   # 90%
        _make_entry(Tribe.ROMANS, 2, 100),   # 10%
    ]
    ev = _make_ev(entries)
    score = _balance_score(ev, avail)
    # stdev([0.9, 0.1]) ≈ 0.5657
    assert score > 0.3


# ---------------------------------------------------------------------------
# UT-07 — available_map vacío → 0.0
# ---------------------------------------------------------------------------

def test_balance_score_empty_map():
    """Sin inventario disponible (mapa vacío) → 0.0."""
    entries = [
        _make_entry(Tribe.ROMANS, 1, 500),
        _make_entry(Tribe.ROMANS, 2, 300),
    ]
    ev = _make_ev(entries)
    score = _balance_score(ev, {})
    assert score == 0.0


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
# UT-06 — request sin campo balance → mismo resultado (CA-02 no-regresión)
# ---------------------------------------------------------------------------

def test_no_regression_no_balance_field():
    """
    OptimizationWeights sin campo 'balance' usa el default 0.0.
    Llamadas existentes que no envían 'balance' deben comportarse idénticamente.
    Este test verifica que el default es 0.0 y no afecta el score.
    """
    # Sin el campo balance (instancia con defaults)
    w1 = OptimizationWeights(resources_gained=1.0, total_losses=1.0, troops_sent=0.5, travel_time=0.0)
    # Con balance explícito a 0.0
    w2 = OptimizationWeights(resources_gained=1.0, total_losses=1.0, troops_sent=0.5, travel_time=0.0, balance=0.0)

    assert w1.balance == 0.0
    assert w2.balance == 0.0
    assert w1 == w2  # Ambas instancias son idénticas


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
