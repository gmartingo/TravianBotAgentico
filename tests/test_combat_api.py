"""
Tests de integración de los endpoints de combate (IT-01 a IT-24).

POST /combat/simulate  — Simulador de combate.
POST /combat/optimize  — Optimizador de ataque a oasis.

Los tests usan TestClient con lifespan activado. La BD de juego real (con seed)
es la fuente de datos; se usa Tribe.ROMANS y Tribe.NATURE que deben estar en BD.

Estrategia:
  - IT-01..IT-11, IT-18..IT-24: simulate — usan la BD real con tropas romanas
    y tropas NATURE (cargadas por el seed en el lifespan).
  - IT-12..IT-17: optimize — usan Modo A/B con tropas romanas vs oasis NATURE.
  - Tests que necesitan tropas no disponibles en BD usan un mock de game_data_port.

Ver spec §12 para la correspondencia IT-XX.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from adapters.api.main import app
from core.entities.tribe import Tribe


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gdp_mock(
    stats_callable=None,
    upgrades=None,
    wall_bonus=None,
):
    """Crea un mock completo de GameDataPort."""
    mock = MagicMock()

    if stats_callable is not None:
        async def _get_stats(tribe, ordinal, sv="1.45"):
            return stats_callable(tribe, ordinal)
        mock.get_troop_stats = _get_stats
    else:
        async def _default_stats(tribe, ordinal, sv="1.45"):
            return {
                "attack": 60,
                "def_infantry": 40,
                "def_cavalry": 20,
                "speed": 6,
                "carry": 50,
                "upkeep": 1,
                "cost_wood": 120,
                "cost_clay": 100,
                "cost_iron": 150,
                "cost_crop": 30,
                "cost_sum": 400,
                "icon_id": f"troop_{tribe.value}_{ordinal}",
            }
        mock.get_troop_stats = _default_stats

    async def _get_upgrades(tribe, ordinal, sv="1.45"):
        return upgrades or []
    mock.get_troop_upgrades = _get_upgrades

    async def _get_defense_bonus(gid, level, sv="1.45"):
        return wall_bonus
    mock.get_building_defense_bonus = _get_defense_bonus

    return mock


# ---------------------------------------------------------------------------
# Fixture — cliente con lifespan (BD real con seed)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    """Cliente con lifespan activado. La BD se inicializa con el seed en el startup."""
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Payloads básicos reutilizables
# ---------------------------------------------------------------------------

_BASIC_SIMULATE_BODY = {
    "attacker": {
        "tribe": "romans",
        "attack_type": "raid",
        "troops": [{"ordinal": 1, "quantity": 500, "smithy_level": 0}],
    },
    "defenders": [
        {
            "tribe": "nature",
            "troops": [
                {"tribe": "nature", "ordinal": 1, "quantity": 10, "smithy_level": 0}
            ],
        }
    ],
    "wall": {"wall_level": 0},
    "config": {},
}

_BASIC_OPTIMIZE_BODY_MODE_A = {
    "attacker": {
        "tribe": "romans",
        "troop_types": [
            {"ordinal": 1, "smithy_level": 0},
        ],
    },
    "oasis_defense": {
        "troops": [
            {"ordinal": 1, "quantity": 5},
        ]
    },
    "config": {"top_n": 3},
}


# ---------------------------------------------------------------------------
# IT-01 — simulate válido con romanos vs NATURE → 200
# ---------------------------------------------------------------------------

def test_it01_simulate_basic_roman_vs_nature(client):
    """Request válido con romanos vs ratas NATURE → 200 con resultado correcto."""
    resp = client.post(
        "/combat/simulate",
        json=_BASIC_SIMULATE_BODY,
        headers={"Accept-Language": "es"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "attacker_wins" in data
    assert "ratio" in data
    assert "loot" in data
    assert "resource_losses" in data
    assert "attacker_troops" in data
    assert "defender_troops" in data


# ---------------------------------------------------------------------------
# IT-02 — sin Accept-Language → 400
# ---------------------------------------------------------------------------

def test_it02_simulate_no_language_400(client):
    """Sin Accept-Language y sin ?lang=, el endpoint devuelve 400."""
    resp = client.post("/combat/simulate", json=_BASIC_SIMULATE_BODY)
    assert resp.status_code == 400
    assert "Accept-Language" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# IT-03 — troops vacío → 422
# ---------------------------------------------------------------------------

def test_it03_simulate_empty_troops_422(client):
    """Lista de tropas del atacante vacía → 422."""
    body = dict(_BASIC_SIMULATE_BODY)
    body["attacker"] = dict(body["attacker"])
    body["attacker"]["troops"] = []
    resp = client.post(
        "/combat/simulate",
        json=body,
        headers={"Accept-Language": "es"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# IT-05 — ?lang=xx inválido → 400
# ---------------------------------------------------------------------------

def test_it05_simulate_invalid_lang_400(client):
    """Idioma no soportado en ?lang= → 400."""
    resp = client.post(
        "/combat/simulate?lang=xx",
        json=_BASIC_SIMULATE_BODY,
    )
    assert resp.status_code == 400
    assert "xx" in resp.json()["detail"].lower() or "soportado" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# IT-06 — dos defensores → defender_troops aplanado
# ---------------------------------------------------------------------------

def test_it06_simulate_two_defenders_flattened(client):
    """Dos defensores distintos → defender_troops aplanado con tropas de ambos."""
    body = dict(_BASIC_SIMULATE_BODY)
    body["defenders"] = [
        {
            "tribe": "nature",
            "troops": [{"tribe": "nature", "ordinal": 1, "quantity": 5}],
        },
        {
            "tribe": "nature",
            "troops": [{"tribe": "nature", "ordinal": 2, "quantity": 5}],
        },
    ]
    resp = client.post(
        "/combat/simulate",
        json=body,
        headers={"Accept-Language": "es"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # defender_troops debe tener entradas de ambas formaciones
    assert len(data["defender_troops"]) == 2
    ordinales = {t["ordinal"] for t in data["defender_troops"]}
    assert 1 in ordinales and 2 in ordinales


# ---------------------------------------------------------------------------
# IT-07 — defensa vacía (EC-01) → attacker_wins: true, ratio: null
# ---------------------------------------------------------------------------

def test_it07_simulate_empty_defense_ec01(client):
    """Defensa vacía → 200, attacker_wins: true, ratio: null, bajas = 0."""
    body = dict(_BASIC_SIMULATE_BODY)
    body["defenders"] = [{"tribe": "nature", "troops": []}]
    resp = client.post(
        "/combat/simulate",
        json=body,
        headers={"Accept-Language": "es"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["attacker_wins"] is True
    assert data["ratio"] is None
    for t in data["attacker_troops"]:
        assert t["quantity_lost"] == 0


# ---------------------------------------------------------------------------
# IT-09 — Moral 20 → 200 con warning (moral clampeada a 30)
# ---------------------------------------------------------------------------

def test_it09_simulate_moral_below_min_clamped(client):
    """moral=20 → Pydantic lo rechaza (ge=30) → 422 (validación Pydantic)."""
    body = dict(_BASIC_SIMULATE_BODY)
    body["attacker"] = dict(body["attacker"])
    body["attacker"]["morale"] = 20  # bajo el mínimo de 30
    resp = client.post(
        "/combat/simulate",
        json=body,
        headers={"Accept-Language": "es"},
    )
    # Pydantic valida ge=30, así que debe ser 422
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# IT-10 — attack_type="raid" → structural_damage: null
# ---------------------------------------------------------------------------

def test_it10_simulate_raid_no_structural_damage(client):
    """attack_type='raid' → structural_damage: null en el response."""
    body = dict(_BASIC_SIMULATE_BODY)
    body["attacker"] = dict(body["attacker"])
    body["attacker"]["attack_type"] = "raid"
    resp = client.post(
        "/combat/simulate",
        json=body,
        headers={"Accept-Language": "es"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["structural_damage"] is None


# ---------------------------------------------------------------------------
# IT-11 — hero_attack_points=500 → attacker_power mayor
# ---------------------------------------------------------------------------

def test_it11_hero_attack_points_increases_power(client):
    """hero_attack_points=500 hace que attacker_power sea mayor que sin héroe."""
    body_sin = dict(_BASIC_SIMULATE_BODY)
    body_con = dict(_BASIC_SIMULATE_BODY)
    body_con["attacker"] = dict(body_con["attacker"])
    body_con["attacker"]["hero_attack_points"] = 500.0

    resp_sin = client.post("/combat/simulate", json=body_sin, headers={"Accept-Language": "es"})
    resp_con = client.post("/combat/simulate", json=body_con, headers={"Accept-Language": "es"})

    assert resp_sin.status_code == 200
    assert resp_con.status_code == 200
    assert resp_con.json()["attacker_power"] > resp_sin.json()["attacker_power"]


# ---------------------------------------------------------------------------
# IT-18 — attack_type="attack" + catapultas → catapult_results poblado
# ---------------------------------------------------------------------------

def test_it18_attack_mode_catapult_results(client):
    """attack_type='attack' + catapultas + target → structural_damage.catapult_results."""
    body = {
        "attacker": {
            "tribe": "romans",
            "attack_type": "attack",
            # Muchas catapultas (ordinal 8) para ganar con seguridad
            "troops": [{"ordinal": 8, "quantity": 1000, "smithy_level": 0}],
            "catapult_targets": [{"building_gid": 15, "current_level": 10}],
        },
        "defenders": [{"tribe": "nature", "troops": []}],  # sin defensa
        "wall": {"wall_level": 0},
        "config": {},
    }
    resp = client.post(
        "/combat/simulate",
        json=body,
        headers={"Accept-Language": "es"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["structural_damage"] is not None
    assert len(data["structural_damage"]["catapult_results"]) == 1
    cr = data["structural_damage"]["catapult_results"][0]
    assert cr["level_after"] < cr["level_before"]
    assert cr["level_after"] >= 0


# ---------------------------------------------------------------------------
# IT-19 — Arietes + muro nivel 10 → wall_after < 10
# ---------------------------------------------------------------------------

def test_it19_rams_reduce_wall(client):
    """Arietes con muro nivel 10 → wall_after < 10."""
    body = {
        "attacker": {
            "tribe": "romans",
            "attack_type": "attack",
            "troops": [{"ordinal": 7, "quantity": 500, "smithy_level": 0}],
            "rams": {"quantity": 500, "smithy_level": 0},
        },
        "defenders": [{"tribe": "romans", "troops": []}],
        "wall": {"wall_level": 10, "stonemason_level": 0, "wall_tribe": "romans"},
        "config": {},
    }
    resp = client.post(
        "/combat/simulate",
        json=body,
        headers={"Accept-Language": "es"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["structural_damage"] is not None
    assert data["structural_damage"]["wall_after"] < 10


# ---------------------------------------------------------------------------
# IT-20 — village_resources=50000 → loot.potential <= 50000
# ---------------------------------------------------------------------------

def test_it20_village_resources_caps_loot(client):
    """loot.potential = min(village_resources, loot.capacity)."""
    body = dict(_BASIC_SIMULATE_BODY)
    body["defenders"] = [{
        "tribe": "nature",
        "troops": [],
        "village_resources": 50_000,
    }]
    resp = client.post(
        "/combat/simulate",
        json=body,
        headers={"Accept-Language": "es"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["loot"]["potential"] is not None
    assert data["loot"]["potential"] <= 50_000


# ---------------------------------------------------------------------------
# IT-21 — sin village_resources → loot.potential = null
# ---------------------------------------------------------------------------

def test_it21_no_village_resources_potential_null(client):
    """Sin village_resources, loot.potential es null y loot.capacity está presente."""
    resp = client.post(
        "/combat/simulate",
        json=_BASIC_SIMULATE_BODY,
        headers={"Accept-Language": "es"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["loot"]["potential"] is None
    assert data["loot"]["capacity"] is not None
    assert isinstance(data["loot"]["capacity"], int)


# ---------------------------------------------------------------------------
# IT-22 — NATURE ordinal 2 muertos → resources_gained_from_animals objeto
# ---------------------------------------------------------------------------

def test_it22_nature_spiders_killed_animal_drop(client):
    """Arañas NATURE muertas → resources_gained_from_animals es un objeto con total > 0."""
    body = {
        "attacker": {
            "tribe": "romans",
            "troops": [{"ordinal": 1, "quantity": 10_000, "smithy_level": 0}],
        },
        "defenders": [
            {
                "tribe": "nature",
                "troops": [{"tribe": "nature", "ordinal": 2, "quantity": 30}],
            }
        ],
        "wall": {"wall_level": 0},
        "config": {},
    }
    resp = client.post(
        "/combat/simulate",
        json=body,
        headers={"Accept-Language": "es"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    drop = data["loot"]["resources_gained_from_animals"]
    assert drop is not None
    assert drop["total"] > 0
    assert drop["wood"] > 0
    assert drop["clay"] > 0
    assert drop["iron"] > 0
    assert drop["crop"] > 0


# ---------------------------------------------------------------------------
# IT-23 — resource_losses.attacker.total_resources > 0 cuando hay bajas
# ---------------------------------------------------------------------------

def test_it23_attacker_resource_losses_when_losses(client):
    """resource_losses.attacker.total_resources > 0 cuando hay bajas."""
    body = {
        "attacker": {
            "tribe": "romans",
            "troops": [{"ordinal": 1, "quantity": 50, "smithy_level": 0}],
        },
        "defenders": [
            {
                "tribe": "nature",
                "troops": [{"tribe": "nature", "ordinal": 10, "quantity": 500}],
            }
        ],
        "wall": {"wall_level": 0},
        "config": {},
    }
    resp = client.post(
        "/combat/simulate",
        json=body,
        headers={"Accept-Language": "es"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Si el atacante pierde al menos algunas tropas, resource_losses > 0
    # (puede que gane o pierda dependiendo de los datos de BD reales)
    rl = data["resource_losses"]["attacker"]["total_resources"]
    atk_lost = sum(t["quantity_lost"] for t in data["attacker_troops"])
    if atk_lost > 0:
        assert rl > 0


# ---------------------------------------------------------------------------
# IT-24 — attack_type inválido → 422
# ---------------------------------------------------------------------------

def test_it24_invalid_attack_type_422(client):
    """attack_type con valor inválido → 422."""
    body = dict(_BASIC_SIMULATE_BODY)
    body["attacker"] = dict(body["attacker"])
    body["attacker"]["attack_type"] = "siege"  # valor no reconocido
    resp = client.post(
        "/combat/simulate",
        json=body,
        headers={"Accept-Language": "es"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# IT-12 — optimize Modo A → 200 con alternatives
# ---------------------------------------------------------------------------

def test_it12_optimize_mode_a_returns_alternatives(client):
    """Modo A (troop_types) → 200 con lista de alternativas."""
    resp = client.post(
        "/combat/optimize",
        json=_BASIC_OPTIMIZE_BODY_MODE_A,
        headers={"Accept-Language": "es"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "alternatives" in data
    assert len(data["alternatives"]) > 0
    assert "has_winning_combination" in data
    assert "defender_troops" in data


# ---------------------------------------------------------------------------
# IT-13 — optimize Modo B → alternatives sin superar quantity_available
# ---------------------------------------------------------------------------

def test_it13_optimize_mode_b_respects_max_quantity(client):
    """Modo B (village_troops) → alternatives no superan quantity_available."""
    body = {
        "attacker": {
            "tribe": "romans",
            "village_troops": [
                {"ordinal": 1, "quantity_available": 100, "smithy_level": 0},
            ],
        },
        "oasis_defense": {
            "troops": [{"ordinal": 1, "quantity": 5}]
        },
        "config": {"top_n": 3},
    }
    resp = client.post(
        "/combat/optimize",
        json=body,
        headers={"Accept-Language": "es"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    for alt in data["alternatives"]:
        for ts in alt["troops_sent"]:
            assert ts["quantity_initial"] <= 100


# ---------------------------------------------------------------------------
# IT-14 — troop_types Y village_troops juntos → 422
# ---------------------------------------------------------------------------

def test_it14_both_modes_422(client):
    """Ambos modos simultáneamente → 422."""
    body = {
        "attacker": {
            "tribe": "romans",
            "troop_types": [{"ordinal": 1, "smithy_level": 0}],
            "village_troops": [{"ordinal": 1, "quantity_available": 100}],
        },
        "oasis_defense": {"troops": [{"ordinal": 1, "quantity": 5}]},
        "config": {"top_n": 3},
    }
    resp = client.post(
        "/combat/optimize",
        json=body,
        headers={"Accept-Language": "es"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# IT-15 — Optimizador sin ganadoras → 200 con has_winning_combination=false
# ---------------------------------------------------------------------------

def test_it15_optimize_no_winners_returns_non_winners(client):
    """Sin combinación ganadora → 200, has_winning_combination: false, alternatives no vacío."""
    # Oasis con muchos elefantes (ordinal 10) contra pocas tropas romanas disponibles
    body = {
        "attacker": {
            "tribe": "romans",
            "village_troops": [
                {"ordinal": 1, "quantity_available": 1, "smithy_level": 0},
            ],
        },
        "oasis_defense": {
            "troops": [{"ordinal": 10, "quantity": 10_000}]  # 10k elefantes → inganable con 1 tropa
        },
        "config": {"top_n": 3},
    }
    resp = client.post(
        "/combat/optimize",
        json=body,
        headers={"Accept-Language": "es"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["has_winning_combination"] is False
    assert len(data["alternatives"]) > 0
    assert data["message"] is not None


# ---------------------------------------------------------------------------
# IT-16 — optimize sin Accept-Language → 400
# ---------------------------------------------------------------------------

def test_it16_optimize_no_language_400(client):
    """Optimize sin Accept-Language ni ?lang= → 400."""
    resp = client.post("/combat/optimize", json=_BASIC_OPTIMIZE_BODY_MODE_A)
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# IT-17 — defender_troops cuando sin ganadoras → quantity_survived = quantity_initial
# ---------------------------------------------------------------------------

def test_it17_no_winners_defender_troops_intact(client):
    """Sin ganadoras, los defender_troops muestran quantity_survived = quantity_initial."""
    body = {
        "attacker": {
            "tribe": "romans",
            "village_troops": [
                {"ordinal": 1, "quantity_available": 1, "smithy_level": 0},
            ],
        },
        "oasis_defense": {
            "troops": [{"ordinal": 10, "quantity": 10_000}]
        },
        "config": {"top_n": 3},
    }
    resp = client.post(
        "/combat/optimize",
        json=body,
        headers={"Accept-Language": "es"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    if not data["has_winning_combination"]:
        for dt in data["defender_troops"]:
            assert dt["quantity_survived"] == dt["quantity_initial"]
            assert dt["quantity_lost"] == 0


# ---------------------------------------------------------------------------
# IT-08 — simulate con icon_id nulo en BD
# ---------------------------------------------------------------------------

def test_it08_simulate_null_icon_id(client):
    """Si icon_id es null en BD, icon_url en el response es null."""
    # Inyectar un mock que devuelve icon_id=None
    original_port = app.state.game_data_port

    class _NullIconPort:
        async def get_troop_stats(self, tribe, ordinal, sv="1.45"):
            return {
                "attack": 100,
                "def_infantry": 50,
                "def_cavalry": 30,
                "speed": 6,
                "carry": 50,
                "upkeep": 1,
                "cost_wood": 120,
                "cost_clay": 100,
                "cost_iron": 150,
                "cost_crop": 30,
                "cost_sum": 400,
                "icon_id": None,  # sin icon
            }

        async def get_troop_upgrades(self, *a, **kw):
            return []

        async def get_building_defense_bonus(self, *a, **kw):
            return None

    app.state.game_data_port = _NullIconPort()
    try:
        resp = client.post(
            "/combat/simulate",
            json=_BASIC_SIMULATE_BODY,
            headers={"Accept-Language": "es"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        for t in data["attacker_troops"]:
            assert t["icon_url"] is None
    finally:
        app.state.game_data_port = original_port


# ---------------------------------------------------------------------------
# IT-04 — simulate con tropa sin stats en BD → 422
# ---------------------------------------------------------------------------

def test_it04_simulate_missing_stats_422(client):
    """Tropa sin stats en BD → 422 con mensaje descriptivo."""
    original_port = app.state.game_data_port

    class _NoDataPort:
        async def get_troop_stats(self, tribe, ordinal, sv="1.45"):
            return None  # sin datos

        async def get_troop_upgrades(self, *a, **kw):
            return []

        async def get_building_defense_bonus(self, *a, **kw):
            return None

    app.state.game_data_port = _NoDataPort()
    try:
        resp = client.post(
            "/combat/simulate",
            json=_BASIC_SIMULATE_BODY,
            headers={"Accept-Language": "es"},
        )
        assert resp.status_code == 422
        assert "stats" in resp.json()["detail"].lower() or "BD" in resp.json()["detail"]
    finally:
        app.state.game_data_port = original_port


# ---------------------------------------------------------------------------
# IT-30 — scoring_mode + n_min/n_max: contrato y validación
# ---------------------------------------------------------------------------

def test_it30_scoring_mode_default_single(client):
    """Sin scoring_mode en el request → default 'single' (no-regresión, CA-10)."""
    body = {
        "attacker": {
            "tribe": "romans",
            "village_troops": [
                {"ordinal": 1, "quantity_available": 100, "smithy_level": 0},
            ],
        },
        "oasis_defense": {"troops": [{"ordinal": 1, "quantity": 5}]},
        "config": {"top_n": 3},
    }
    resp = client.post("/combat/optimize", json=body, headers={"Accept-Language": "es"})
    assert resp.status_code == 200, resp.text


def test_it31_scoring_mode_aggregate_accepted(client):
    """scoring_mode='aggregate' + n_min/n_max válidos → 200."""
    body = {
        "attacker": {
            "tribe": "romans",
            "village_troops": [
                {"ordinal": 1, "quantity_available": 500, "smithy_level": 0},
            ],
        },
        "oasis_defense": {"troops": [{"ordinal": 1, "quantity": 5}]},
        "config": {
            "top_n": 3,
            "scoring_mode": "aggregate",
            "n_min": 2,
            "n_max": 50,
        },
    }
    resp = client.post("/combat/optimize", json=body, headers={"Accept-Language": "es"})
    assert resp.status_code == 200, resp.text


def test_it32_scoring_mode_invalid_value_422(client):
    """scoring_mode con valor fuera del enum → 422."""
    body = {
        "attacker": {
            "tribe": "romans",
            "village_troops": [
                {"ordinal": 1, "quantity_available": 100, "smithy_level": 0},
            ],
        },
        "oasis_defense": {"troops": [{"ordinal": 1, "quantity": 5}]},
        "config": {"scoring_mode": "wrong"},
    }
    resp = client.post("/combat/optimize", json=body, headers={"Accept-Language": "es"})
    assert resp.status_code == 422


def test_it33_n_min_greater_than_n_max_422(client):
    """n_min > n_max → 422 (CA-13)."""
    body = {
        "attacker": {
            "tribe": "romans",
            "village_troops": [
                {"ordinal": 1, "quantity_available": 100, "smithy_level": 0},
            ],
        },
        "oasis_defense": {"troops": [{"ordinal": 1, "quantity": 5}]},
        "config": {"n_min": 20, "n_max": 5},
    }
    resp = client.post("/combat/optimize", json=body, headers={"Accept-Language": "es"})
    assert resp.status_code == 422


def test_it34_n_min_zero_rejected_422(client):
    """n_min < 1 → 422 (campo con ge=1)."""
    body = {
        "attacker": {
            "tribe": "romans",
            "village_troops": [
                {"ordinal": 1, "quantity_available": 100, "smithy_level": 0},
            ],
        },
        "oasis_defense": {"troops": [{"ordinal": 1, "quantity": 5}]},
        "config": {"n_min": 0},
    }
    resp = client.post("/combat/optimize", json=body, headers={"Accept-Language": "es"})
    assert resp.status_code == 422


def test_it37_simulate_includes_infantry_cavalry_power_split(client):
    """Simulate devuelve attacker/defender_infantry_power y _cavalry_power
    desglosados — la UI los usa para partir la fila "Fuerza de combate" en 2."""
    body = {
        "attacker": {
            "tribe": "romans",
            "troops": [
                # ordinal 1 (Legionnaire) = infantería
                # ordinal 5 (Equites Imperatoris) = caballería con ataque > 0
                # (ordinal 4 es scout y tiene ataque 0, no sirve aquí)
                {"ordinal": 1, "quantity": 100, "smithy_level": 0},
                {"ordinal": 5, "quantity": 50, "smithy_level": 0},
            ],
            "attack_type": "raid",
            "alliance_bonus": 0.0,
        },
        "defenders": [{
            "tribe": "nature",
            "troops": [{"ordinal": 1, "quantity": 5, "smithy_level": 0}],
            "hero_defense_points": 0,
            "hero_defense_bonus_percent": 0,
            "artifacts": {"strong_buildings": 1.0, "great_cranny": 1.0},
        }],
        "wall": {"wall_level": 0, "stonemason_level": 0},
        "config": {"server_speed": 1.0},
    }
    resp = client.post("/combat/simulate", json=body, headers={"Accept-Language": "es"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    for key in (
        "attacker_infantry_power", "attacker_cavalry_power",
        "defender_infantry_power", "defender_cavalry_power",
    ):
        assert key in data, f"Falta {key} en SimulateResponse"
    # Con infantería + caballería ambas deben ser > 0
    assert data["attacker_infantry_power"] > 0
    assert data["attacker_cavalry_power"] > 0


def test_it36_optimize_alternative_includes_resource_losses_breakdown(client):
    """Cada alternativa del optimizador trae el desglose por recurso de las
    bajas del atacante (w/c/i/c + total). Permite a la UI computar el neto.

    Escenario calibrado para forzar bajas reales en el atacante: envío
    pequeño vs un oasis con defensores duros (elefantes). Garantiza que el
    desglose por recurso no es null ni todo ceros.
    """
    body = {
        "attacker": {
            "tribe": "romans",
            "village_troops": [
                {"ordinal": 1, "quantity_available": 200, "smithy_level": 0},
            ],
        },
        # ordinal 10 = elefante (defensor potente) → fuerza bajas atacantes
        "oasis_defense": {"troops": [{"ordinal": 10, "quantity": 10}]},
        "config": {"top_n": 3},
    }
    resp = client.post("/combat/optimize", json=body, headers={"Accept-Language": "es"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Para AL MENOS UNA alternativa con bajas, el desglose tiene que estar
    # poblado y la suma debe coincidir con total_resource_losses.
    found_breakdown = False
    for alt in data["alternatives"]:
        assert "resource_losses_breakdown" in alt
        bd = alt["resource_losses_breakdown"]
        if alt["total_resource_losses"] > 0:
            assert bd is not None, (
                f"Alt con total_resource_losses={alt['total_resource_losses']} "
                f"trae resource_losses_breakdown=null — la UI no podrá pintar el coste."
            )
            for k in ("wood", "clay", "iron", "crop", "total"):
                assert k in bd
            assert bd["total"] == bd["wood"] + bd["clay"] + bd["iron"] + bd["crop"]
            assert bd["total"] == alt["total_resource_losses"], (
                f"Desglose incoherente: bd.total={bd['total']} vs "
                f"total_resource_losses={alt['total_resource_losses']}"
            )
            assert bd["total"] > 0
            found_breakdown = True
    assert found_breakdown, "Ninguna alternativa expuso resource_losses_breakdown poblado"


def test_it35_aggregate_range_targeted_sampling(client):
    """Escenario del usuario: con inventario donde el cuello de botella obliga
    a oleadas pequeñas (pero los otros tipos son grandes), el muestreo dirigido
    por rango DEBE encontrar combinaciones factibles con N ∈ [n_min, n_max].

    Reproduce el caso real: 6000 ordinal=1 + 3000 ordinal=2 + 100 ordinal=3,
    n_min=65, n_max=70. Sin la fase de rango, la fase fina (tope 21 por tipo)
    nunca evaluaría una oleada del tipo 90/45/13 — el cuello es ordinal=3.
    """
    body = {
        "attacker": {
            "tribe": "gauls",
            "village_troops": [
                {"ordinal": 1, "quantity_available": 6000, "smithy_level": 0},
                {"ordinal": 2, "quantity_available": 3000, "smithy_level": 0},
                {"ordinal": 3, "quantity_available": 100, "smithy_level": 0},
            ],
        },
        "oasis_defense": {"troops": [{"ordinal": 1, "quantity": 3}]},
        "config": {
            "scoring_mode": "aggregate",
            "n_min": 65,
            "n_max": 70,
            "top_n": 3,
        },
    }
    resp = client.post("/combat/optimize", json=body, headers={"Accept-Language": "es"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # La primera alternativa debe tener N ≥ n_min (no quedar bloqueada en
    # el caso pre-fix donde el muestreo no exploraba el rango y todas las
    # candidatas eran infactibles).
    top = data["alternatives"][0]
    assert top["raids_possible"] is not None
    assert top["raids_possible"] >= 65, (
        f"Alternativa #1 con raids_possible={top['raids_possible']} no cumple n_min=65; "
        f"el muestreo dirigido por rango no se está aplicando."
    )
    assert top["raids_possible"] <= 70, (
        f"Alternativa #1 con raids_possible={top['raids_possible']} excede n_max=70."
    )
