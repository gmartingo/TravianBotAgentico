"""
Tests unitarios del motor de combate (T-01 a T-33).

No abren BD ni browser. Usan mocks de GameDataPort y TranslationPort
para controlar los stats de tropas de forma determinista.

Ver spec §12 (Plan de pruebas) para la correspondencia T-XX.
"""
from __future__ import annotations

import asyncio
from math import floor
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.entities.combat import (
    AttackerArtifacts,
    AttackerFormation,
    CatapultTarget,
    CombatConfig,
    DefenderArtifacts,
    DefenderFormation,
    RamSpec,
    TroopEntry,
    WallConfig,
)
from core.entities.tribe import Tribe
from core.use_cases.combat_engine import (
    WALL_GID_BY_TRIBE,
    apply_smithy,
    simulate_combat,
)
from core.use_cases.nature_animal_drops import NATURE_DROPS, get_nature_drop


# ---------------------------------------------------------------------------
# Fixtures de mocks
# ---------------------------------------------------------------------------

def _make_stats(
    attack: int = 60,
    def_inf: int = 40,
    def_cav: int = 20,
    speed: int = 6,
    carry: int = 50,
    upkeep: int = 1,
    cost_wood: int = 120,
    cost_clay: int = 100,
    cost_iron: int = 150,
    cost_crop: int = 30,
    cost_sum: int = 400,
    icon_id: str | None = "troop_romans_1",
) -> dict:
    return {
        "attack": attack,
        "def_infantry": def_inf,
        "def_cavalry": def_cav,
        "speed": speed,
        "carry": carry,
        "upkeep": upkeep,
        "cost_wood": cost_wood,
        "cost_clay": cost_clay,
        "cost_iron": cost_iron,
        "cost_crop": cost_crop,
        "cost_sum": cost_sum,
        "icon_id": icon_id,
    }


def _make_nature_stats(ordinal: int) -> dict:
    """Stats mínimos de un animal de naturaleza (sin coste, sin carry)."""
    base_def = ordinal * 10
    return {
        "attack": 0,
        "def_infantry": base_def,
        "def_cavalry": base_def,
        "speed": 3,
        "carry": 0,
        "upkeep": 0,
        "cost_wood": 0,
        "cost_clay": 0,
        "cost_iron": 0,
        "cost_crop": 0,
        "cost_sum": 0,
        "icon_id": f"troop_nature_{ordinal}",
    }


def _make_game_data_port(
    troop_stats: dict | None = None,
    upgrades: list | None = None,
    wall_bonus: float | None = None,
) -> MagicMock:
    """
    Crea un mock de GameDataPort.

    troop_stats: dict o callable (tribe, ordinal) → dict.
    upgrades: lista de dicts de upgrades (por defecto vacía).
    wall_bonus: float devuelto por get_building_defense_bonus (por defecto None).
    """
    port = MagicMock()
    _stats = troop_stats or _make_stats()

    if callable(troop_stats):
        async def _get_stats(tribe, ordinal, sv="1.45"):
            return troop_stats(tribe, ordinal)
        port.get_troop_stats = _get_stats
    else:
        async def _get_stats(tribe, ordinal, sv="1.45"):
            return _stats
        port.get_troop_stats = _get_stats

    _upgrades = upgrades if upgrades is not None else []

    async def _get_upgrades(tribe, ordinal, sv="1.45"):
        return _upgrades
    port.get_troop_upgrades = _get_upgrades

    async def _get_defense_bonus(gid, level, sv="1.45"):
        return wall_bonus
    port.get_building_defense_bonus = _get_defense_bonus

    return port


def _make_translation_port(name: str = "Tropa") -> MagicMock:
    port = MagicMock()
    port.get_troop_name = MagicMock(return_value=name)
    return port


def _run(coro):
    """Ejecuta una coroutine en el event loop de forma síncrona."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Helpers para construir ejércitos simples
# ---------------------------------------------------------------------------

def _make_attacker(
    troops=None,
    attack_type="raid",
    hero_attack_points=0.0,
    hero_attack_bonus_percent=0.0,
    alliance_bonus=0.0,
    morale=100.0,
    artifacts=None,
    catapult_targets=None,
    rams=None,
) -> AttackerFormation:
    return AttackerFormation(
        tribe=Tribe.ROMANS,
        troops=troops or [TroopEntry(Tribe.ROMANS, 1, 100, 0)],
        attack_type=attack_type,
        hero_attack_points=hero_attack_points,
        hero_attack_bonus_percent=hero_attack_bonus_percent,
        alliance_bonus=alliance_bonus,
        morale=morale,
        artifacts=artifacts or AttackerArtifacts(),
        catapult_targets=catapult_targets or [],
        rams=rams,
    )


def _make_defender(
    troops=None,
    tribe=Tribe.GAULS,
    hero_defense_points=0.0,
    hero_defense_bonus_percent=0.0,
    village_resources=None,
) -> DefenderFormation:
    return DefenderFormation(
        tribe=tribe,
        troops=troops or [TroopEntry(tribe, 1, 100, 0)],
        hero_defense_points=hero_defense_points,
        hero_defense_bonus_percent=hero_defense_bonus_percent,
        artifacts=DefenderArtifacts(),
        village_resources=village_resources,
    )


def _make_config(
    exponent=0.5,
    server_speed=1.0,
    distance_fields=None,
) -> CombatConfig:
    return CombatConfig(
        exponent=exponent,
        server_speed=server_speed,
        distance_fields=distance_fields,
    )


# ---------------------------------------------------------------------------
# T-01 — ratio >= 1 → atacante gana; supervivientes correctos
# ---------------------------------------------------------------------------

def test_t01_attacker_wins_when_ratio_gte_1():
    """Atacante con stats superiores debe ganar y quedar con supervivientes."""
    # Atacante: 1000 unidades con ataque 100
    # Defensor: 100 unidades con defensa 10/10
    def _stats(tribe, ordinal):
        if tribe == Tribe.ROMANS:
            return _make_stats(attack=100, def_inf=10, def_cav=10, speed=6, carry=50,
                               cost_sum=400)
        return _make_stats(attack=10, def_inf=10, def_cav=10, cost_sum=100)

    port = _make_game_data_port(troop_stats=_stats)
    tr = _make_translation_port()

    # attack_type="attack" explícito: en raid el defensor puede sobrevivir con mínimo 1
    attacker = _make_attacker(troops=[TroopEntry(Tribe.ROMANS, 1, 1000, 0)], attack_type="attack")
    defenders = [_make_defender(troops=[TroopEntry(Tribe.GAULS, 1, 100, 0)])]

    result = _run(simulate_combat(attacker, defenders, WallConfig(), _make_config(), "es", port, tr))

    assert result.attacker_wins is True
    total_survived = sum(t.quantity_survived for t in result.attacker_troops)
    assert total_survived > 0
    assert all(t.quantity_survived == 0 for t in result.defender_troops)


# ---------------------------------------------------------------------------
# T-02 — ratio < 1 → defensor gana; supervivientes correctos
# ---------------------------------------------------------------------------

def test_t02_defender_wins_when_ratio_lt_1():
    """Defensor con stats superiores debe ganar."""
    def _stats(tribe, ordinal):
        if tribe == Tribe.ROMANS:
            return _make_stats(attack=10, def_inf=100, def_cav=100, cost_sum=400)
        return _make_stats(attack=10, def_inf=100, def_cav=100, cost_sum=200)

    port = _make_game_data_port(troop_stats=_stats)
    tr = _make_translation_port()

    # attack_type="attack": en raid el atacante perdedor escapa con mínimo 1
    attacker = _make_attacker(troops=[TroopEntry(Tribe.ROMANS, 1, 100, 0)], attack_type="attack")
    defenders = [_make_defender(troops=[TroopEntry(Tribe.GAULS, 1, 1000, 0)])]

    result = _run(simulate_combat(attacker, defenders, WallConfig(), _make_config(), "es", port, tr))

    assert result.attacker_wins is False
    assert all(t.quantity_survived == 0 for t in result.attacker_troops)
    total_def_survived = sum(t.quantity_survived for t in result.defender_troops)
    assert total_def_survived > 0


# ---------------------------------------------------------------------------
# T-03 — D_efectiva = 0 → victoria inmediata, ratio=None (EC-01)
# ---------------------------------------------------------------------------

def test_t03_empty_defense_victory_ratio_none():
    """Defensa vacía → victoria inmediata, ratio=None, 0 bajas en el atacante."""
    port = _make_game_data_port()
    tr = _make_translation_port()

    attacker = _make_attacker(troops=[TroopEntry(Tribe.ROMANS, 1, 500, 0)])
    defenders = [DefenderFormation(tribe=Tribe.GAULS, troops=[], artifacts=DefenderArtifacts())]

    result = _run(simulate_combat(attacker, defenders, WallConfig(), _make_config(), "es", port, tr))

    assert result.attacker_wins is True
    assert result.ratio is None
    assert all(t.quantity_survived == t.quantity_initial for t in result.attacker_troops)


# ---------------------------------------------------------------------------
# T-04 — Moral = 50 → A_efectivo reducido a la mitad
# ---------------------------------------------------------------------------

def test_t04_morale_50_halves_attacker_power():
    """Con morale=50, el attacker_power debe ser la mitad del caso morale=100."""
    port = _make_game_data_port()
    tr = _make_translation_port()

    attacker_100 = _make_attacker(troops=[TroopEntry(Tribe.ROMANS, 1, 100, 0)], morale=100.0)
    attacker_50 = _make_attacker(troops=[TroopEntry(Tribe.ROMANS, 1, 100, 0)], morale=50.0)
    defenders = [_make_defender()]

    res_100 = _run(simulate_combat(attacker_100, defenders, WallConfig(), _make_config(), "es", port, tr))
    res_50 = _run(simulate_combat(attacker_50, defenders, WallConfig(), _make_config(), "es", port, tr))

    assert abs(res_50.attacker_power - res_100.attacker_power / 2) < 1.0


# ---------------------------------------------------------------------------
# T-05 — Smithy level 10 aplica multiplicador correcto
# ---------------------------------------------------------------------------

def test_t05_smithy_level_10_increases_attack():
    """Con smithy_level=10 y upgrade disponible, el attacker_power debe ser mayor."""
    # Simular que el upgrade al nivel 10 sube el ataque de 60 a 90
    _upgrades = [{"level": 10, "stat_name": "attack", "stat_value": 90.0}]

    port_0 = _make_game_data_port(upgrades=[])
    port_10 = _make_game_data_port(upgrades=_upgrades)
    tr = _make_translation_port()

    attacker_0 = _make_attacker(troops=[TroopEntry(Tribe.ROMANS, 1, 100, 0)])
    attacker_10 = _make_attacker(troops=[TroopEntry(Tribe.ROMANS, 1, 100, 10)])
    defenders = [DefenderFormation(tribe=Tribe.GAULS, troops=[], artifacts=DefenderArtifacts())]

    res_0 = _run(simulate_combat(attacker_0, defenders, WallConfig(), _make_config(), "es", port_0, tr))
    res_10 = _run(simulate_combat(attacker_10, defenders, WallConfig(), _make_config(), "es", port_10, tr))

    assert res_10.attacker_power > res_0.attacker_power


# ---------------------------------------------------------------------------
# T-06 — Smithy level 25 (imposible) → clamped a 20 con warning (EC-06)
# ---------------------------------------------------------------------------

def test_t06_smithy_level_clamped_with_warning():
    """Smithy level mayor al máximo disponible debe clampearse con warning."""
    _upgrades = [{"level": 20, "stat_name": "attack", "stat_value": 100.0}]
    port = _make_game_data_port(upgrades=_upgrades)
    tr = _make_translation_port()

    warnings: list[str] = []
    result_val = _run(apply_smithy(60, Tribe.ROMANS, 1, 25, port, warnings, stat="attack"))

    assert any("25" in w or "clampeado" in w.lower() for w in warnings)
    assert result_val == 100.0  # usa el nivel 20


# ---------------------------------------------------------------------------
# T-07 — Smithy sin upgrades en BD → base stat + warning (EC-06)
# ---------------------------------------------------------------------------

def test_t07_smithy_no_upgrades_uses_base():
    """Sin upgrades en BD, apply_smithy devuelve el stat base con warning."""
    port = _make_game_data_port(upgrades=[])
    warnings: list[str] = []

    result_val = _run(apply_smithy(60, Tribe.ROMANS, 1, 10, port, warnings, stat="attack"))

    assert result_val == 60.0
    assert len(warnings) > 0


# ---------------------------------------------------------------------------
# T-08 — Ejército mixto inf/cav → prop_cav ponderada (RN-05)
# ---------------------------------------------------------------------------

def test_t08_mixed_army_cav_ratio_affects_defense():
    """Con ejército mixto, la proporción caballería afecta a la defensa activada."""
    # Defensor con def_inf=100, def_cav=0 → con cav_ratio=0: D alta; con cav_ratio=1: D=0
    def _stats(tribe, ordinal):
        if tribe == Tribe.ROMANS:
            return _make_stats(attack=50, def_inf=50, def_cav=50, cost_sum=400)
        return _make_stats(attack=0, def_inf=100, def_cav=0, cost_sum=0)

    port = _make_game_data_port(troop_stats=_stats)
    tr = _make_translation_port()

    # Solo infantería (ordinals 1-3 son inf en romans)
    attacker_inf = _make_attacker(troops=[TroopEntry(Tribe.ROMANS, 1, 500, 0)])
    # Caballería (ordinal 4 = Equites Legati)
    attacker_cav = _make_attacker(troops=[TroopEntry(Tribe.ROMANS, 4, 500, 0)])
    defenders = [_make_defender(troops=[TroopEntry(Tribe.GAULS, 1, 100, 0)])]

    res_inf = _run(simulate_combat(attacker_inf, defenders, WallConfig(), _make_config(), "es", port, tr))
    res_cav = _run(simulate_combat(attacker_cav, defenders, WallConfig(), _make_config(), "es", port, tr))

    # Con infantería: D_base = 100*100 = 10000 (máximo)
    # Con caballería: D_base = 100*0 = 0 (mínimo)
    # El poder defensor debería ser mayor vs infantería
    assert res_inf.defender_power >= res_cav.defender_power


# ---------------------------------------------------------------------------
# T-09 — Wall level 10 + stonemason 2 → D bonus correcto desde GameDataPort
# ---------------------------------------------------------------------------

def test_t09_wall_bonus_from_game_data_port():
    """wall_multiplier usa get_building_defense_bonus cuando hay datos en BD."""
    # Simular wall_bonus = 0.30 (30% de bonus)
    port = _make_game_data_port(wall_bonus=0.30)
    tr = _make_translation_port()

    attacker = _make_attacker()
    defenders = [_make_defender()]
    wall = WallConfig(wall_level=10, stonemason_level=2, wall_tribe=Tribe.ROMANS)

    result = _run(simulate_combat(attacker, defenders, wall, _make_config(), "es", port, tr))

    # stonemason_mult = 1 + 0.05*2 = 1.10
    # wall_mult = (1 + 0.30) * 1.10 = 1.43
    # D_efectiva debe ser mayor que sin muro
    result_no_wall = _run(simulate_combat(attacker, defenders, WallConfig(), _make_config(), "es", port, tr))
    assert result.defender_power > result_no_wall.defender_power


# ---------------------------------------------------------------------------
# T-10 — Wall sin datos en GameDataPort → fallback 0.03×10 + warning
# ---------------------------------------------------------------------------

def test_t10_wall_fallback_when_no_bd_data():
    """Sin datos de edificio en BD, usa fallback 0.03×nivel y añade warning."""
    port = _make_game_data_port(wall_bonus=None)
    tr = _make_translation_port()

    attacker = _make_attacker()
    defenders = [_make_defender()]
    wall = WallConfig(wall_level=10, stonemason_level=0, wall_tribe=Tribe.ROMANS)

    result = _run(simulate_combat(attacker, defenders, wall, _make_config(), "es", port, tr))

    assert any("aproximación" in w or "fallback" in w.lower() or "BD" in w
               for w in result.warnings)
    # wall_mult = (1 + 0.03*10) * 1.0 = 1.30
    result_no_wall = _run(simulate_combat(attacker, defenders, WallConfig(), _make_config(), "es", port, tr))
    assert result.defender_power > result_no_wall.defender_power


# ---------------------------------------------------------------------------
# T-11 — crop_consumption con distance_fields=10, server_speed=3, artifact_diet=0.5
# ---------------------------------------------------------------------------

def test_t11_crop_consumption_calculated_correctly():
    """crop_consumption = round(crop_ph × travel_h × 2 × diet)."""
    port = _make_game_data_port()  # upkeep=1, speed=6
    tr = _make_translation_port()

    # 100 tropas con upkeep=1 → crop_ph = 100
    # speed=6, server_speed=3 → velocidad_efectiva = 6/3 = 2 campos/h
    # artifact_fast=1.0 → travel_h = 10/2 = 5h
    # diet=0.5 → crop = round(100 × 5 × 2 × 0.5) = 500
    attacker = _make_attacker(
        troops=[TroopEntry(Tribe.ROMANS, 1, 100, 0)],
        artifacts=AttackerArtifacts(fast_troops=1.0, diet=0.5),
    )
    defenders = [DefenderFormation(tribe=Tribe.GAULS, troops=[], artifacts=DefenderArtifacts())]
    config = _make_config(server_speed=3.0, distance_fields=10.0)

    result = _run(simulate_combat(attacker, defenders, WallConfig(), config, "es", port, tr))

    assert result.crop_consumption == 500


# ---------------------------------------------------------------------------
# T-12 — distance_fields=None → crop_consumption=None
# ---------------------------------------------------------------------------

def test_t12_no_distance_fields_no_crop():
    """Sin distance_fields, crop_consumption es None."""
    port = _make_game_data_port()
    tr = _make_translation_port()

    result = _run(simulate_combat(
        _make_attacker(), [_make_defender()],
        WallConfig(), _make_config(distance_fields=None), "es", port, tr
    ))

    assert result.crop_consumption is None


# ---------------------------------------------------------------------------
# T-13 — Atacante con ataque=0 → A_total=0 → 422 (EC-04 → ValueError)
# ---------------------------------------------------------------------------

def test_t13_zero_attack_raises_value_error():
    """Ejército con ataque total=0 (solo exploradores) lanza ValueError."""
    port = _make_game_data_port(troop_stats=_make_stats(attack=0))
    tr = _make_translation_port()

    attacker = _make_attacker(troops=[TroopEntry(Tribe.ROMANS, 4, 100, 0)])
    defenders = [_make_defender()]

    with pytest.raises(ValueError, match="ejército atacante"):
        _run(simulate_combat(attacker, defenders, WallConfig(), _make_config(), "es", port, tr))


# ---------------------------------------------------------------------------
# T-14 — ratio exactamente = 1 → atacante gana (EC-03)
# ---------------------------------------------------------------------------

def test_t14_ratio_exactly_1_attacker_wins():
    """Cuando A == D, el atacante gana (ratio >= 1)."""
    # Configurar exactamente A = D
    # 100 tropas × ataque 50 = A=5000; 100 tropas × def 50 = D=5000
    def _stats(tribe, ordinal):
        return _make_stats(attack=50, def_inf=50, def_cav=50, cost_sum=400)

    port = _make_game_data_port(troop_stats=_stats)
    tr = _make_translation_port()

    attacker = _make_attacker(troops=[TroopEntry(Tribe.ROMANS, 1, 100, 0)])
    # Solo infantería para que prop_cav = 0 → D = D_inf
    defenders = [_make_defender(
        troops=[TroopEntry(Tribe.GAULS, 1, 100, 0)],
        tribe=Tribe.GAULS,
    )]

    result = _run(simulate_combat(attacker, defenders, WallConfig(), _make_config(), "es", port, tr))

    assert result.attacker_wins is True


# ---------------------------------------------------------------------------
# T-15 — hero_attack_points=500 → se suma a A_base antes del bonus porcentual
# ---------------------------------------------------------------------------

def test_t15_hero_attack_points_added_to_a_base():
    """hero_attack_points se suma antes del bonus porcentual → A mayor."""
    port = _make_game_data_port()
    tr = _make_translation_port()

    attacker_sin_heroe = _make_attacker(hero_attack_points=0.0)
    attacker_con_heroe = _make_attacker(hero_attack_points=500.0)
    defenders = [DefenderFormation(tribe=Tribe.GAULS, troops=[], artifacts=DefenderArtifacts())]

    res_sin = _run(simulate_combat(attacker_sin_heroe, defenders, WallConfig(), _make_config(), "es", port, tr))
    res_con = _run(simulate_combat(attacker_con_heroe, defenders, WallConfig(), _make_config(), "es", port, tr))

    assert res_con.attacker_power > res_sin.attacker_power


# ---------------------------------------------------------------------------
# T-16 — Dos defensores con héroe → hero_defense_points se suman
# ---------------------------------------------------------------------------

def test_t16_two_defenders_hero_points_sum():
    """Con dos defensores, sus hero_defense_points se acumulan."""
    port = _make_game_data_port()
    tr = _make_translation_port()

    attacker = _make_attacker()

    # Un defensor sin héroe
    defenders_sin = [_make_defender(hero_defense_points=0.0)]
    # Dos defensores, cada uno con 500 puntos de héroe
    defenders_con = [
        _make_defender(hero_defense_points=500.0),
        _make_defender(hero_defense_points=500.0),
    ]

    res_sin = _run(simulate_combat(attacker, defenders_sin, WallConfig(), _make_config(), "es", port, tr))
    res_con = _run(simulate_combat(attacker, defenders_con, WallConfig(), _make_config(), "es", port, tr))

    assert res_con.defender_power > res_sin.defender_power


# ---------------------------------------------------------------------------
# T-17 — artifact_fast_troops=2.0 → travel_time_h se divide a la mitad
# ---------------------------------------------------------------------------

def test_t17_artifact_fast_troops_halves_travel_time():
    """artifact_fast_troops=2.0 debe reducir el crop a la mitad."""
    port = _make_game_data_port()  # speed=6, upkeep=1
    tr = _make_translation_port()

    defenders = [DefenderFormation(tribe=Tribe.GAULS, troops=[], artifacts=DefenderArtifacts())]
    config = _make_config(distance_fields=10.0)

    attacker_normal = _make_attacker(
        troops=[TroopEntry(Tribe.ROMANS, 1, 100, 0)],
        artifacts=AttackerArtifacts(fast_troops=1.0, diet=1.0),
    )
    attacker_fast = _make_attacker(
        troops=[TroopEntry(Tribe.ROMANS, 1, 100, 0)],
        artifacts=AttackerArtifacts(fast_troops=2.0, diet=1.0),
    )

    res_normal = _run(simulate_combat(attacker_normal, defenders, WallConfig(), config, "es", port, tr))
    res_fast = _run(simulate_combat(attacker_fast, defenders, WallConfig(), config, "es", port, tr))

    # crop con fast=2: travel_h = 10/(6*2) = 0.833h vs 10/6 = 1.667h
    # crop_fast = round(100 × 0.833 × 2) = 167; crop_normal = round(100 × 1.667 × 2) = 333
    assert res_fast.crop_consumption < res_normal.crop_consumption
    assert abs(res_fast.crop_consumption - res_normal.crop_consumption / 2) < 5  # tolerancia


# ---------------------------------------------------------------------------
# T-21 — attack_type="raid" → structural_damage=None; catapult_targets ignorados
# ---------------------------------------------------------------------------

def test_t21_raid_mode_no_structural_damage():
    """En modo raid, structural_damage=None aunque se proporcionen catapult_targets."""
    port = _make_game_data_port()
    tr = _make_translation_port()

    attacker = _make_attacker(
        attack_type="raid",
        catapult_targets=[CatapultTarget(building_gid=15, current_level=10)],
    )
    defenders = [DefenderFormation(tribe=Tribe.GAULS, troops=[], artifacts=DefenderArtifacts())]

    result = _run(simulate_combat(attacker, defenders, WallConfig(), _make_config(), "es", port, tr))

    assert result.structural_damage is None
    assert any("ignorado" in w.lower() or "raid" in w.lower() for w in result.warnings)


# ---------------------------------------------------------------------------
# T-22 — attack_type="attack" + catapultas → nivel_after < nivel_before
# ---------------------------------------------------------------------------

def test_t22_attack_mode_catapults_reduce_building_level():
    """En modo attack con catapultas, el nivel del edificio baja."""
    def _stats(tribe, ordinal):
        if ordinal == 8 and tribe == Tribe.ROMANS:
            # Catapulta romana (ordinal 8)
            return _make_stats(attack=50, def_inf=0, def_cav=0, cost_sum=5000)
        return _make_stats(attack=60, def_inf=40, def_cav=20, cost_sum=400)

    port = _make_game_data_port(troop_stats=_stats)
    tr = _make_translation_port()

    # 200 catapultas ganadoras vs defensa vacía → todas sobreviven
    attacker = _make_attacker(
        troops=[TroopEntry(Tribe.ROMANS, 8, 200, 0)],
        attack_type="attack",
        catapult_targets=[CatapultTarget(building_gid=15, current_level=10)],
    )
    defenders = [DefenderFormation(tribe=Tribe.GAULS, troops=[], artifacts=DefenderArtifacts())]

    result = _run(simulate_combat(attacker, defenders, WallConfig(), _make_config(), "es", port, tr))

    assert result.structural_damage is not None
    assert len(result.structural_damage.catapult_results) == 1
    cr = result.structural_damage.catapult_results[0]
    assert cr.level_after < cr.level_before
    assert cr.level_after >= 0


# ---------------------------------------------------------------------------
# T-23 — attack_type="attack" + arietes → wall_after < wall_before
# ---------------------------------------------------------------------------

def test_t23_attack_mode_rams_reduce_wall():
    """En modo attack con arietes, el nivel del muro baja."""
    def _stats(tribe, ordinal):
        if ordinal == 7 and tribe == Tribe.ROMANS:
            # Ariete romano (ordinal 7)
            return _make_stats(attack=65, def_inf=30, def_cav=80, cost_sum=3000)
        return _make_stats(attack=60, def_inf=40, def_cav=20, cost_sum=400)

    # wall_bonus = 0.20 (20%)
    port = _make_game_data_port(troop_stats=_stats, wall_bonus=0.20)
    tr = _make_translation_port()

    # 300 arietes vs defensa vacía → todos sobreviven
    attacker = _make_attacker(
        troops=[TroopEntry(Tribe.ROMANS, 7, 300, 0)],
        attack_type="attack",
        rams=RamSpec(quantity=300, smithy_level=0),
    )
    defenders = [DefenderFormation(tribe=Tribe.ROMANS, troops=[], artifacts=DefenderArtifacts())]
    wall = WallConfig(wall_level=10, stonemason_level=0, wall_tribe=Tribe.ROMANS)

    result = _run(simulate_combat(attacker, defenders, wall, _make_config(), "es", port, tr))

    assert result.structural_damage is not None
    assert result.structural_damage.wall_after < result.structural_damage.wall_before


# ---------------------------------------------------------------------------
# T-24 — wall_level=0 + arietes → wall_after = 0 (no negativo) (EC-29)
# ---------------------------------------------------------------------------

def test_t24_wall_at_zero_after_rams():
    """Arietes con muro en nivel 0 → wall_after = 0 (nunca negativo)."""
    def _stats(tribe, ordinal):
        if ordinal == 7:
            return _make_stats(attack=65, cost_sum=3000)
        return _make_stats(attack=60, cost_sum=400)

    port = _make_game_data_port(troop_stats=_stats, wall_bonus=0.0)
    tr = _make_translation_port()

    attacker = _make_attacker(
        troops=[TroopEntry(Tribe.ROMANS, 7, 500, 0)],
        attack_type="attack",
        rams=RamSpec(quantity=500, smithy_level=0),
    )
    defenders = [DefenderFormation(tribe=Tribe.GAULS, troops=[], artifacts=DefenderArtifacts())]
    wall = WallConfig(wall_level=0, stonemason_level=0, wall_tribe=Tribe.ROMANS)

    result = _run(simulate_combat(attacker, defenders, wall, _make_config(), "es", port, tr))

    assert result.structural_damage is not None
    assert result.structural_damage.wall_after == 0
    assert result.structural_damage.wall_before == 0


# ---------------------------------------------------------------------------
# T-25 — loot.capacity = Σ(survived × carry)
# ---------------------------------------------------------------------------

def test_t25_loot_capacity_correct():
    """loot.capacity = suma de supervivientes × carry."""
    # 500 unidades con carry=50 vs defensa vacía → todos sobreviven → capacity=25000
    port = _make_game_data_port(_make_stats(attack=60, carry=50))
    tr = _make_translation_port()

    attacker = _make_attacker(troops=[TroopEntry(Tribe.ROMANS, 1, 500, 0)])
    defenders = [DefenderFormation(tribe=Tribe.GAULS, troops=[], artifacts=DefenderArtifacts())]

    result = _run(simulate_combat(attacker, defenders, WallConfig(), _make_config(), "es", port, tr))

    assert result.loot.capacity == 500 * 50


# ---------------------------------------------------------------------------
# T-26 — village_resources → loot.potential = min(village_resources, capacity)
# ---------------------------------------------------------------------------

def test_t26_loot_potential_capped_by_village_resources():
    """loot.potential = min(village_resources, capacity)."""
    port = _make_game_data_port(_make_stats(attack=60, carry=50))
    tr = _make_translation_port()

    attacker = _make_attacker(troops=[TroopEntry(Tribe.ROMANS, 1, 500, 0)])
    defenders = [DefenderFormation(
        tribe=Tribe.GAULS,
        troops=[],
        artifacts=DefenderArtifacts(),
        village_resources=10_000,
    )]

    result = _run(simulate_combat(attacker, defenders, WallConfig(), _make_config(), "es", port, tr))

    # capacity = 500 × 50 = 25000 > 10000 → potential = 10000
    assert result.loot.potential == 10_000


# ---------------------------------------------------------------------------
# T-27 — sin village_resources → loot.potential = None
# ---------------------------------------------------------------------------

def test_t27_no_village_resources_potential_is_none():
    """Sin village_resources, loot.potential es None."""
    port = _make_game_data_port()
    tr = _make_translation_port()

    attacker = _make_attacker(troops=[TroopEntry(Tribe.ROMANS, 1, 500, 0)])
    defenders = [DefenderFormation(
        tribe=Tribe.GAULS, troops=[], artifacts=DefenderArtifacts(), village_resources=None
    )]

    result = _run(simulate_combat(attacker, defenders, WallConfig(), _make_config(), "es", port, tr))

    assert result.loot.potential is None
    assert result.loot.capacity > 0


# ---------------------------------------------------------------------------
# T-28 — Ratas × 50 muertas → resources_gained_from_animals correcto
# ---------------------------------------------------------------------------

def test_t28_nature_rats_drop_resources():
    """50 ratas (ordinal 1) muertas → 50 × 40 de cada recurso = {wood:2000,...,total:8000}."""
    def _stats(tribe, ordinal):
        if tribe == Tribe.NATURE:
            return _make_nature_stats(ordinal)
        return _make_stats(attack=1000, cost_sum=400)  # atacante aplastante

    port = _make_game_data_port(troop_stats=_stats)
    tr = _make_translation_port()

    attacker = _make_attacker(troops=[TroopEntry(Tribe.ROMANS, 1, 10_000, 0)])
    defenders = [DefenderFormation(
        tribe=Tribe.NATURE,
        troops=[TroopEntry(Tribe.NATURE, 1, 50, 0)],  # 50 Ratas
        artifacts=DefenderArtifacts(),
    )]

    result = _run(simulate_combat(attacker, defenders, WallConfig(), _make_config(), "es", port, tr))

    assert result.attacker_wins is True
    drop = result.loot.resources_gained_from_animals
    assert drop is not None
    assert drop.wood == 50 * 40
    assert drop.clay == 50 * 40
    assert drop.iron == 50 * 40
    assert drop.crop == 50 * 40
    assert drop.total == 50 * 40 * 4


# ---------------------------------------------------------------------------
# T-29 — Sin tropas NATURE → resources_gained_from_animals = None
# ---------------------------------------------------------------------------

def test_t29_no_nature_troops_no_animal_drop():
    """Sin tropas NATURE en la defensa, resources_gained_from_animals es None."""
    port = _make_game_data_port()
    tr = _make_translation_port()

    attacker = _make_attacker(troops=[TroopEntry(Tribe.ROMANS, 1, 100, 0)])
    defenders = [_make_defender()]  # GAULS, no NATURE

    result = _run(simulate_combat(attacker, defenders, WallConfig(), _make_config(), "es", port, tr))

    assert result.loot.resources_gained_from_animals is None


# ---------------------------------------------------------------------------
# T-30 — resource_losses.attacker.total_resources correcto
# ---------------------------------------------------------------------------

def test_t30_attacker_resource_losses_correct():
    """resource_losses.attacker.total_resources = Σ(lost × cost_sum)."""
    def _stats(tribe, ordinal):
        if tribe == Tribe.ROMANS:
            return _make_stats(attack=10, def_inf=100, def_cav=100, cost_sum=400)
        return _make_stats(attack=100, def_inf=100, def_cav=100, cost_sum=100)

    port = _make_game_data_port(troop_stats=_stats)
    tr = _make_translation_port()

    # attack_type="attack": en raid el atacante perdedor escapa con 1 tropa, cambiando el total
    attacker = _make_attacker(troops=[TroopEntry(Tribe.ROMANS, 1, 100, 0)], attack_type="attack")
    defenders = [_make_defender(troops=[TroopEntry(Tribe.GAULS, 1, 1000, 0)])]

    result = _run(simulate_combat(attacker, defenders, WallConfig(), _make_config(), "es", port, tr))

    assert result.attacker_wins is False
    # Todos los atacantes murieron
    assert result.resource_losses.attacker.total_resources == 100 * 400


# ---------------------------------------------------------------------------
# T-31 — resource_losses.defender = 0 para tropas NATURE (cost_sum=0)
# ---------------------------------------------------------------------------

def test_t31_nature_resource_losses_zero():
    """Las tropas NATURE tienen cost_sum=0, por lo que su resource_loss es 0."""
    def _stats(tribe, ordinal):
        if tribe == Tribe.NATURE:
            return _make_nature_stats(ordinal)
        return _make_stats(attack=1000, cost_sum=400)

    port = _make_game_data_port(troop_stats=_stats)
    tr = _make_translation_port()

    attacker = _make_attacker(troops=[TroopEntry(Tribe.ROMANS, 1, 10_000, 0)])
    defenders = [DefenderFormation(
        tribe=Tribe.NATURE,
        troops=[TroopEntry(Tribe.NATURE, 1, 100, 0)],
        artifacts=DefenderArtifacts(),
    )]

    result = _run(simulate_combat(attacker, defenders, WallConfig(), _make_config(), "es", port, tr))

    assert result.resource_losses.defender.total_resources == 0


# ---------------------------------------------------------------------------
# T-33 — rams.quantity=0 → wall_after = wall_before (EC-29)
# ---------------------------------------------------------------------------

def test_t33_rams_quantity_0_no_wall_damage():
    """Con rams.quantity=0, el muro no sufre daño."""
    port = _make_game_data_port(wall_bonus=0.30)
    tr = _make_translation_port()

    attacker = _make_attacker(
        attack_type="attack",
        rams=RamSpec(quantity=0, smithy_level=0),
    )
    defenders = [DefenderFormation(tribe=Tribe.ROMANS, troops=[], artifacts=DefenderArtifacts())]
    wall = WallConfig(wall_level=10, stonemason_level=0, wall_tribe=Tribe.ROMANS)

    result = _run(simulate_combat(attacker, defenders, wall, _make_config(), "es", port, tr))

    assert result.structural_damage is not None
    assert result.structural_damage.wall_after == result.structural_damage.wall_before


# ---------------------------------------------------------------------------
# Tests de drops de naturaleza (módulo nature_animal_drops)
# ---------------------------------------------------------------------------

def test_nature_drops_rata_confirmed():
    """La Rata (ordinal 1) da exactamente 40 de cada recurso."""
    assert get_nature_drop(1, "wood") == 40
    assert get_nature_drop(1, "clay") == 40
    assert get_nature_drop(1, "iron") == 40
    assert get_nature_drop(1, "crop") == 40


def test_nature_drops_unknown_ordinal_returns_zero():
    """Un ordinal desconocido devuelve 0."""
    assert get_nature_drop(99, "wood") == 0


def test_nature_drops_unknown_resource_returns_zero():
    """Un recurso desconocido devuelve 0."""
    assert get_nature_drop(1, "gold") == 0


def test_nature_drops_all_10_animals_present():
    """Los 10 animales están en la tabla."""
    assert len(NATURE_DROPS) == 10
    for ordinal in range(1, 11):
        assert ordinal in NATURE_DROPS


def test_wall_gid_by_tribe_has_main_tribes():
    """WALL_GID_BY_TRIBE contiene al menos las 4 tribus principales."""
    assert Tribe.ROMANS in WALL_GID_BY_TRIBE
    assert Tribe.TEUTONS in WALL_GID_BY_TRIBE
    assert Tribe.GAULS in WALL_GID_BY_TRIBE
    assert Tribe.EGYPTIANS in WALL_GID_BY_TRIBE
