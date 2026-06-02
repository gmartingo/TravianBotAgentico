"""
Tests de integración de EP-SPAWN — GET /attack-reports/stats/oasis/spawn-composition

Cubre los escenarios del spec docs/specs/oasis-spawn-mechanics-stats.md §12:
  T-COMP-* — composición típica por oasis
  T-TYP-*  — inferencia de tipo y confianza
  T-WORST-* — peor combinación a batir
  T-CD-*    — cooldown/respawn
  T-MIG-01  — avg_regen_per_hour NO aparece en EP-SPAWN

También verifica criterios de aceptación de §15 relativos al backend.

Usa TestClient con lifespan activado (BD real en fichero temporal, aislada por test).
Mismo patrón de fixture que test_oasis_comparison_api.py.

IMPORTANTE: el parser de Travian usa tabulaciones para separar múltiples animales
en la misma línea (formato "Rat\tSpider\tBat"). Siempre usar _make_report() que
construye el formato correcto.

Añadido en la feature oasis-spawn-mechanics-stats (2026-06-02).
"""
from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient

from adapters.api.main import app

# ---------------------------------------------------------------------------
# Constantes de defensa de animales — extraídas de seeds/game_data/troop_stats.json
# ---------------------------------------------------------------------------
# Rat (ord 1):       def_infantry=25,  def_cavalry=20
# Spider (ord 2):    def_infantry=35,  def_cavalry=40
# Serpent (ord 3):   def_infantry=40,  def_cavalry=60
# Bat (ord 4):       def_infantry=66,  def_cavalry=50
# Wild boar (ord 5): def_infantry=70,  def_cavalry=33
# Wolf (ord 6):      def_infantry=80,  def_cavalry=70
# Bear (ord 7):      def_infantry=140, def_cavalry=200
# Crocodile (ord 8): def_infantry=380, def_cavalry=240
# Tiger (ord 9):     def_infantry=170, def_cavalry=250
# Elephant (ord 10): def_infantry=440, def_cavalry=520
_DEF_INFANTRY = {1: 25, 2: 35, 3: 40, 4: 66, 5: 70, 6: 80, 7: 140, 8: 380, 9: 170, 10: 440}
_DEF_CAVALRY  = {1: 20, 2: 40, 3: 60, 4: 50, 5: 33, 6: 70, 7: 200, 8: 240, 9: 250, 10: 520}

# SPAWN_TIMER_S por ordinal (servidor x1)
_SPAWN_TIMER_S = {1: 300, 2: 360, 3: 420, 4: 480, 5: 540, 6: 600, 7: 660, 8: 720, 9: 780, 10: 840}

_EP = "/attack-reports/stats/oasis/spawn-composition"


# ---------------------------------------------------------------------------
# Fixture — cliente con BD temporal aislada por test
# ---------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch, tmp_path):
    """
    Cliente con la app real apuntando a una BD temporal por test.

    Monkeypatcha DB_PATH antes del lifespan para garantizar BD limpia.
    Limpia app.state residual entre tests para evitar interferencias.
    """
    db_file = tmp_path / "test_spawn_composition.db"
    monkeypatch.setattr("adapters.db.database.DB_PATH", str(db_file))

    for attr in ("attack_report_port", "world_runtime_port"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)

    with TestClient(app) as c:
        yield c

    for attr in ("attack_report_port", "world_runtime_port"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)


# ---------------------------------------------------------------------------
# Helpers para construir y guardar reportes
# ---------------------------------------------------------------------------

def _make_report(
    x: int,
    y: int,
    date_str: str,
    animals: list[tuple[str, int, int]],
    village: str = "TestVillage",
    utc_offset: str = "+01:00",
    bounty: str = "100  100  100  100",
) -> str:
    """
    Construye el texto crudo de un reporte de victoria de oasis con MÚLTIPLES animales.

    date_str: formato "DD.MM.YY, HH:MM:SS"
    animals: lista de (nombre_en_inglés, present, killed).
             El formato Travian usa tabulaciones: "Rat\tSpider\tBat" en la misma línea.
    """
    server_hour = date_str.split(", ")[1]
    names_row   = "\t".join(a[0] for a in animals)
    present_row = "\t".join(str(a[1]) for a in animals)
    killed_row  = "\t".join(str(a[2]) for a in animals)

    return (
        f"Attack report on Oasis ({x}|{y})\n\n"
        f"{date_str}\n"
        f"Server time: {server_hour} (UTC {utc_offset})\n\n"
        f"Attacker\n{village} (1|2)\nLegionnaire\n100\n0\n\n"
        f"Defender\n{names_row}\n{present_row}\n{killed_row}\n\n"
        f"Bounty\n{bounty}\n50/100\n"
    )


def _save(client: TestClient, raw_text: str) -> int:
    """Guarda un reporte y devuelve su id."""
    resp = client.post("/attack-reports", json={"raw_text": raw_text})
    assert resp.status_code == 201, f"save failed ({resp.status_code}): {resp.text}"
    return resp.json()["id"]


def _get_spawn(client: TestClient, timer_min: int) -> dict:
    """Llama a EP-SPAWN y devuelve el JSON de la respuesta 200."""
    resp = client.get(_EP, params={"timer_min": timer_min})
    assert resp.status_code == 200, f"EP-SPAWN failed ({resp.status_code}): {resp.text}"
    return resp.json()


def _find_oasis(data: dict, x: int, y: int) -> dict | None:
    """Busca un oasis por coordenadas en la respuesta de EP-SPAWN."""
    for o in data["oasis"]:
        if o["coord_x_dest"] == x and o["coord_y_dest"] == y:
            return o
    return None


def _find_species(oasis: dict, ordinal: int) -> dict | None:
    """Busca una especie por ordinal en el array species[] del oasis."""
    for s in oasis["species"]:
        if s["animal_ordinal"] == ordinal:
            return s
    return None


# ---------------------------------------------------------------------------
# T-COMP — Composición típica (Pieza 2)
# ---------------------------------------------------------------------------

def test_COMP_01_two_oasis_isolated(client):
    """T-COMP-01: 2 oasis con animales distintos no se contaminan entre sí."""
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 5, 5)]))
    _save(client, _make_report(12, -45, "01.06.26, 11:00:00", [("Spider", 3, 3)]))

    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    ob = _find_oasis(data, 12, -45)

    assert oa is not None
    assert ob is not None
    assert [s["animal_ordinal"] for s in oa["species"]] == [1]
    assert [s["animal_ordinal"] for s in ob["species"]] == [2]


def test_COMP_02_animal_present_zero_excluded(client):
    """T-COMP-02: animal con present=0 implícito (no mencionado) no aparece en species[]."""
    # Solo mencionamos Rat (ord 1). Serpent (ord 3) tiene present=0 implícito → excluido.
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 5, 5)]))
    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    assert oa is not None
    ordinals = [s["animal_ordinal"] for s in oa["species"]]
    assert 3 not in ordinals  # serpiente no aparece
    assert 1 in ordinals       # rata sí aparece


def test_COMP_03_single_report_avg_equals_max(client):
    """T-COMP-03: un solo reporte con present>0 → avg_present == max_present."""
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 7, 7)]))
    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    sp = _find_species(oa, 1)
    assert sp is not None
    assert sp["avg_present_per_burst"] == sp["max_present_per_burst"]
    assert sp["max_present_per_burst"] == 7


def test_COMP_04_empty_db(client):
    """T-COMP-04: BD vacía → 200 con oasis: []."""
    data = _get_spawn(client, 6)
    assert data["oasis"] == []
    assert data["timer_min"] == 6
    assert "computed_at" in data


def test_COMP_05_defeat_report_does_not_crash(client):
    """T-COMP-05: reporte de derrota (survived=0, present='?') → no provoca error 500."""
    defeat = (
        "Attack report on Oasis (-10|20)\n\n"
        "01.06.26, 10:00:00\n"
        "Server time: 10:00:00 (UTC +00:00)\n\n"
        "Attacker\nDefeatVillage (5|5)\nLegionnaire\n100\n100\n\n"
        "Defender\nTiger\n?\n?\n\n"
        "Bounty\n0  0  0  0\n0/100\n"
    )
    _save(client, defeat)
    data = _get_spawn(client, 6)
    assert isinstance(data["oasis"], list)


# ---------------------------------------------------------------------------
# T-TYP — Inferencia de tipo de oasis
# ---------------------------------------------------------------------------

def test_TYP_01_hierro_detection(client):
    """T-TYP-01: rata+araña+murciélago → inferred_type='hierro', score 3/3."""
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00",
                               [("Rat", 3, 3), ("Spider", 2, 2), ("Bat", 1, 1)]))
    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    assert oa is not None
    assert oa["inferred_type"] == "hierro"


def test_TYP_02_arcilla_detection(client):
    """T-TYP-02: rata+araña+jabalí → inferred_type='arcilla'."""
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00",
                               [("Rat", 3, 3), ("Spider", 2, 2), ("Wild boar", 1, 1)]))
    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    assert oa is not None
    assert oa["inferred_type"] == "arcilla"


def test_TYP_03_cereal_detection(client):
    """T-TYP-03: tigre+elefante+oso → inferred_type='cereal' (score 3 vs madera score 1)."""
    # Tiger(9)+Elephant(10)+Bear(7): todos en cereal (score=3); madera solo tiene Bear (score=1)
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00",
                               [("Tiger", 2, 2), ("Elephant", 1, 1), ("Bear", 1, 1)]))
    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    assert oa is not None
    assert oa["inferred_type"] == "cereal"


def test_TYP_04_madera_detection_by_cardinal_tiebreak(client):
    """T-TYP-04: Wild boar+Wolf+Bear → tipo='madera'.

    Con Jaccard (RN-TYP-02 v2): {5,6,7} da score 1.0 con madera y 0.3 con cereal
    ({1..10}) → gana madera. Todos del set → ninguna anomalía.
    """
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00",
                               [("Wild boar", 4, 4), ("Wolf", 3, 3), ("Bear", 2, 2)]))
    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    assert oa is not None
    assert oa["inferred_type"] == "madera"
    # Todos son del set de madera → ninguna anomalía
    for sp in oa["species"]:
        assert sp["is_anomaly"] is False


def test_TYP_04b_anomaly_croc_in_arcilla_integration(client):
    """T-TYP-04b (integración, RN-TYP-02 v2 / RN-TYP-03): un cocodrilo (ordinal 8)
    en un oasis de arcilla se clasifica como 'arcilla' con el cocodrilo marcado
    is_anomaly=True end-to-end.

    Observados {1,2,5,8}: con Jaccard arcilla={1,2,5}→3/4=0.75, cereal={1..10}→4/10=0.40
    → gana arcilla. El cocodrilo (8) ∉ arcilla → anomalía. Con el solapamiento bruto
    anterior, este caso clasificaba erróneamente como cereal sin anomalías.
    """
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00",
                               [("Rat", 8, 8), ("Spider", 5, 5),
                                ("Wild boar", 4, 4), ("Crocodile", 1, 1)]))
    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    assert oa is not None
    assert oa["inferred_type"] == "arcilla"

    # El cocodrilo (ordinal 8) es anomalía; rata/araña/jabalí no.
    sp_croc = _find_species(oa, 8)
    assert sp_croc is not None
    assert sp_croc["is_anomaly"] is True
    # Anomalía excluida del peor caso (RN-WORST-05)
    assert sp_croc["worst_case_count"] is None
    assert sp_croc["def_infantry_contribution"] is None
    for ordinal in (1, 2, 5):
        sp = _find_species(oa, ordinal)
        assert sp is not None and sp["is_anomaly"] is False
        assert sp["worst_case_count"] is not None
    # worst_case_summary suma solo los del set base (sin el cocodrilo)
    assert oa["worst_case_summary"] is not None


def test_TYP_05_single_report_low_confidence(client):
    """T-TYP-05: un solo reporte → confidence='low'."""
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 5, 5)]))
    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    assert oa is not None
    assert oa["confidence"] == "low"


def test_TYP_06_three_reports_medium_confidence(client):
    """T-TYP-06: 3 reportes con present>0 → confidence='medium'."""
    for i in range(3):
        _save(client, _make_report(-70, 73, f"0{i+1}.06.26, 10:00:00", [("Rat", 5, 5)]))
    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    assert oa is not None
    assert oa["confidence"] == "medium"


def test_TYP_07_no_present_ever(client):
    """T-TYP-07: BD vacía o solo derrotas sin present>0 → sin oasis con species."""
    # BD vacía → oasis vacío (ya cubierto en T-COMP-04, verificamos aquí también)
    data = _get_spawn(client, 6)
    assert data["oasis"] == []
    # Con derrota: si el parser guarda present=None/0 para animales '?',
    # el oasis puede aparecer sin species → inferred_type=null, spawn_status='unknown'.
    defeat = (
        "Attack report on Oasis (-10|20)\n\n"
        "01.06.26, 10:00:00\n"
        "Server time: 10:00:00 (UTC +00:00)\n\n"
        "Attacker\nDefeatVillage (5|5)\nLegionnaire\n100\n100\n\n"
        "Defender\nTiger\n?\n?\n\n"
        "Bounty\n0  0  0  0\n0/100\n"
    )
    _save(client, defeat)
    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -10, 20)
    if oa is not None and oa["species"] == []:
        assert oa["inferred_type"] is None
        assert oa["confidence"] is None
        assert oa["spawn_status"] == "unknown"


def test_TYP_08_tie_resolution_alphabetical(client):
    """T-TYP-08: empate de score+cardinal → tipo alfabéticamente primero (EC-07)."""
    # Rat(1)+Spider(2): hierro={1,2,4} score=2, arcilla={1,2,5} score=2.
    # Ambos cardinal=3, igual → desempate alfabético: 'arcilla' < 'hierro'.
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00",
                               [("Rat", 3, 3), ("Spider", 2, 2)]))
    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    assert oa is not None
    assert oa["inferred_type"] == "arcilla"


# ---------------------------------------------------------------------------
# T-WORST — Peor combinación (Pieza 3)
# ---------------------------------------------------------------------------

def test_WORST_01_rata_timer6(client):
    """T-WORST-01: timer=6min, Rat (timer 5min): floor(360/300)=1; max=3 → worst=4."""
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00",
                               [("Rat", 3, 3), ("Spider", 2, 2), ("Bat", 1, 1)]))
    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    sp_rat = _find_species(oa, 1)
    assert sp_rat is not None
    expected_wc = 3 + math.floor(360 / _SPAWN_TIMER_S[1])  # 3+1=4
    assert sp_rat["worst_case_count"] == expected_wc


def test_WORST_02_elefante_timer6(client):
    """T-WORST-02: timer=6min, Elephant (timer 14min): floor(360/840)=0; max=2 → worst=2."""
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00",
                               [("Tiger", 4, 4), ("Elephant", 2, 2)]))
    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    sp_elefante = _find_species(oa, 10)
    assert sp_elefante is not None
    expected_wc = 2 + math.floor(360 / _SPAWN_TIMER_S[10])  # 2+0=2
    assert sp_elefante["worst_case_count"] == expected_wc


def test_WORST_03_anomaly_has_null_worst_unit():
    """T-WORST-03 (unitario): animal marcado como anomalía → worst_case_count=null.

    La función _worst_case_count devuelve None si is_anomaly=True (RN-WORST-05).
    En integración con OASIS_TYPE_SETS actuales (cereal={1..10}), la anomalía
    prácticamente no ocurre porque cereal siempre supera en score; se testea
    aquí unitariamente para garantizar que la lógica del spec es correcta.
    """
    from adapters.db.attack_report_sqlite_adapter import _worst_case_count
    from core.game_data.oasis_spawn_catalog import SPAWN_TIMER_S

    # Animal marcado como anomalía → None
    wc = _worst_case_count(
        animal_ordinal=2,  # Spider
        max_present=3,
        tipo="madera",    # madera no incluye Spider → is_anomaly=True
        is_anomaly=True,
        timer_s=360,
        spawn_timer_s=SPAWN_TIMER_S,
    )
    assert wc is None

    # Animal del set base → valor calculado
    wc2 = _worst_case_count(
        animal_ordinal=5,  # Wild boar (en madera)
        max_present=4,
        tipo="madera",
        is_anomaly=False,
        timer_s=360,
        spawn_timer_s=SPAWN_TIMER_S,
    )
    assert wc2 is not None
    assert wc2 == 4 + (360 // SPAWN_TIMER_S[5])  # 4 + floor(360/540) = 4+0 = 4

    # Tipo=None → None
    wc3 = _worst_case_count(
        animal_ordinal=1,
        max_present=5,
        tipo=None,
        is_anomaly=False,
        timer_s=360,
        spawn_timer_s=SPAWN_TIMER_S,
    )
    assert wc3 is None


def test_WORST_04_null_type_no_worst_summary(client):
    """T-WORST-04: inferred_type=null → worst_case_summary=null."""
    # BD vacía: sin oasis → verificación implícita (oasis:[])
    data = _get_spawn(client, 6)
    assert data["oasis"] == []
    # Verifica también con un oasis que aparezca con inferred_type=null
    defeat = (
        "Attack report on Oasis (-10|20)\n\n"
        "01.06.26, 10:00:00\n"
        "Server time: 10:00:00 (UTC +00:00)\n\n"
        "Attacker\nDefeatVillage (5|5)\nLegionnaire\n100\n100\n\n"
        "Defender\nTiger\n?\n?\n\n"
        "Bounty\n0  0  0  0\n0/100\n"
    )
    _save(client, defeat)
    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -10, 20)
    if oa is not None and oa["inferred_type"] is None:
        assert oa["worst_case_summary"] is None


def test_WORST_05_def_infantry_hierro_timer6(client):
    """T-WORST-05: def_infantry_total correcto para oasis hierro con timer=6."""
    # hierro: Rat(1) max=3, Spider(2) max=2, Bat(4) max=1
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00",
                               [("Rat", 3, 3), ("Spider", 2, 2), ("Bat", 1, 1)]))
    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    assert oa is not None
    assert oa["inferred_type"] == "hierro"

    timer_s = 6 * 60  # 360s
    wc_rat    = 3 + math.floor(timer_s / _SPAWN_TIMER_S[1])   # 3+1=4
    wc_spider = 2 + math.floor(timer_s / _SPAWN_TIMER_S[2])   # 2+1=3
    wc_bat    = 1 + math.floor(timer_s / _SPAWN_TIMER_S[4])   # 1+0=1

    expected_inf = (wc_rat    * _DEF_INFANTRY[1] +
                    wc_spider * _DEF_INFANTRY[2] +
                    wc_bat    * _DEF_INFANTRY[4])
    expected_cav = (wc_rat    * _DEF_CAVALRY[1] +
                    wc_spider * _DEF_CAVALRY[2] +
                    wc_bat    * _DEF_CAVALRY[4])

    ws = oa["worst_case_summary"]
    assert ws is not None
    assert ws["def_infantry_total"] == expected_inf
    assert ws["def_cavalry_total"] == expected_cav


def test_WORST_06_invalid_timer_min(client):
    """T-WORST-06: timer_min=8 (inválido) → 400 con detail legible."""
    resp = client.get(_EP, params={"timer_min": 8})
    assert resp.status_code == 400
    body = resp.json()
    assert "detail" in body
    assert "8" in body["detail"]


def test_WORST_07_missing_timer_min(client):
    """T-WORST-07: timer_min ausente → 422 (FastAPI validation)."""
    resp = client.get(_EP)
    assert resp.status_code == 422


def test_WORST_all_timer_values_accepted(client):
    """Todos los valores válidos de timer_min (6,7,10,15) devuelven 200."""
    for t in (6, 7, 10, 15):
        resp = client.get(_EP, params={"timer_min": t})
        assert resp.status_code == 200, f"timer_min={t} falló con {resp.status_code}"


# ---------------------------------------------------------------------------
# T-CD — Cooldown / respawn (Pieza 4)
# ---------------------------------------------------------------------------

def test_CD_01_respawning_status(client):
    """T-CD-01: elapsed_s <= max(timers del set) → spawn_status='respawning'."""
    # Oasis de tipo madera: Wild boar(5)+Wolf(6)+Bear(7) → umbral_respawning=660s
    # Guardamos con fecha "ahora" para que elapsed~0 → respawning.
    now_utc = datetime.now(timezone.utc)
    local_str = now_utc.strftime("%d.%m.%y, %H:%M:%S")
    _save(client, _make_report(-70, 73, local_str, utc_offset="+00:00",
                               animals=[("Wild boar", 4, 4), ("Wolf", 3, 3), ("Bear", 2, 2)]))
    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    assert oa is not None
    assert oa["elapsed_seconds"] >= 0.0
    assert oa["spawn_status"] == "respawning"


def test_CD_02_cooldown_status(client):
    """T-CD-02: elapsed_s > 4h (14400s) → spawn_status='cooldown'."""
    # Fecha antigua → elapsed enorme
    _save(client, _make_report(-70, 73, "01.01.25, 10:00:00", utc_offset="+00:00",
                               animals=[("Rat", 3, 3), ("Spider", 2, 2), ("Bat", 1, 1)]))
    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    assert oa is not None
    assert oa["elapsed_seconds"] > 14400
    assert oa["spawn_status"] == "cooldown"


def test_CD_03_unknown_intermediate_zone(client):
    """T-CD-03: elapsed entre max_timer y 4h → spawn_status='unknown'."""
    # Madera: umbral_respawning=660s. Usamos 30 minutos atrás (1800s).
    thirty_min_ago = datetime.now(timezone.utc) - timedelta(minutes=30)
    local_str = thirty_min_ago.strftime("%d.%m.%y, %H:%M:%S")
    _save(client, _make_report(-70, 73, local_str, utc_offset="+00:00",
                               animals=[("Wild boar", 4, 4), ("Wolf", 3, 3), ("Bear", 2, 2)]))
    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    assert oa is not None
    assert 660 < oa["elapsed_seconds"] < 14400
    assert oa["spawn_status"] == "unknown"


def test_CD_04_null_type_unknown_status(client):
    """T-CD-04: inferred_type=null → spawn_status='unknown'."""
    defeat = (
        "Attack report on Oasis (-10|20)\n\n"
        "01.06.26, 10:00:00\n"
        "Server time: 10:00:00 (UTC +00:00)\n\n"
        "Attacker\nDefeatVillage (5|5)\nLegionnaire\n100\n100\n\n"
        "Defender\nTiger\n?\n?\n\n"
        "Bounty\n0  0  0  0\n0/100\n"
    )
    _save(client, defeat)
    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -10, 20)
    if oa is not None and oa["inferred_type"] is None:
        assert oa["spawn_status"] == "unknown"


def test_CD_05_elapsed_never_negative(client):
    """T-CD-05: elapsed_seconds siempre >= 0 (EC-09)."""
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 5, 5)]))
    data = _get_spawn(client, 6)
    for oasis in data["oasis"]:
        assert oasis["elapsed_seconds"] >= 0.0


# ---------------------------------------------------------------------------
# T-MIG — Migración avg_regen_per_hour (Pieza 5)
# ---------------------------------------------------------------------------

def test_MIG_01_no_avg_regen_per_hour_in_ep_spawn(client):
    """T-MIG-01: EP-SPAWN no devuelve avg_regen_per_hour en ningún nivel."""
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 5, 5)]))
    data = _get_spawn(client, 6)
    assert "avg_regen_per_hour" not in data
    for oasis in data["oasis"]:
        assert "avg_regen_per_hour" not in oasis
        for sp in oasis["species"]:
            assert "avg_regen_per_hour" not in sp


# ---------------------------------------------------------------------------
# Criterios de aceptación de §15 (backend)
# ---------------------------------------------------------------------------

def test_CA_spawn_catalog_exists():
    """CA: core/game_data/oasis_spawn_catalog.py tiene SPAWN_TIMER_S (10) y OASIS_TYPE_SETS (4)."""
    from core.game_data.oasis_spawn_catalog import SPAWN_TIMER_S, OASIS_TYPE_SETS
    assert len(SPAWN_TIMER_S) == 10
    assert set(SPAWN_TIMER_S.keys()) == set(range(1, 11))
    assert len(OASIS_TYPE_SETS) == 4
    assert set(OASIS_TYPE_SETS.keys()) == {"hierro", "arcilla", "madera", "cereal"}


def test_CA_port_has_get_all_oasis_regen_comparison():
    """CA: get_all_oasis_regen_comparison() está declarado como abstracto en el port (gap TR-06)."""
    from core.ports.attack_report_port import AttackReportPort
    assert hasattr(AttackReportPort, "get_all_oasis_regen_comparison")
    method = getattr(AttackReportPort, "get_all_oasis_regen_comparison")
    assert getattr(method, "__isabstractmethod__", False)


def test_CA_port_has_get_oasis_spawn_composition():
    """CA: get_oasis_spawn_composition() está declarado como abstracto en el port."""
    from core.ports.attack_report_port import AttackReportPort
    assert hasattr(AttackReportPort, "get_oasis_spawn_composition")
    method = getattr(AttackReportPort, "get_oasis_spawn_composition")
    assert getattr(method, "__isabstractmethod__", False)


def test_CA_200_with_timer_6(client):
    """CA: GET /attack-reports/stats/oasis/spawn-composition?timer_min=6 → 200."""
    resp = client.get(_EP, params={"timer_min": 6})
    assert resp.status_code == 200
    body = resp.json()
    assert "oasis" in body
    assert body["timer_min"] == 6
    assert "computed_at" in body


def test_CA_400_invalid_timer(client):
    """CA: timer_min fuera de {6,7,10,15} → 400 con detail legible."""
    resp = client.get(_EP, params={"timer_min": 5})
    assert resp.status_code == 400
    assert "detail" in resp.json()


def test_CA_422_missing_timer(client):
    """CA: timer_min ausente → 422."""
    resp = client.get(_EP)
    assert resp.status_code == 422


def test_CA_empty_db_returns_200_with_empty_oasis(client):
    """CA: BD vacía → 200 con oasis:[]."""
    data = _get_spawn(client, 6)
    assert data["oasis"] == []


def test_CA_anomaly_worst_null_unit():
    """CA (unitario): is_anomaly=True → worst_case_count=null (lógica de _worst_case_count).

    La integración de is_anomaly en la práctica depende de que el tipo ganador excluya
    el animal; con OASIS_TYPE_SETS["cereal"]={1..10}, cereal siempre abarca todos los
    animales → is_anomaly nunca ocurre en producción a menos que el tipo ganador sea
    hierro/arcilla/madera (solo cuando cereal empata y pierde por cardinal).
    El comportamiento correcto se verifica unitariamente.
    """
    from adapters.db.attack_report_sqlite_adapter import _worst_case_count
    from core.game_data.oasis_spawn_catalog import SPAWN_TIMER_S

    wc = _worst_case_count(
        animal_ordinal=2, max_present=3, tipo="madera",
        is_anomaly=True, timer_s=360, spawn_timer_s=SPAWN_TIMER_S,
    )
    assert wc is None


def test_CA_ep_spawn_before_ep04_routing(client):
    """CA: EP-SPAWN declarado ANTES de EP-04 — FastAPI resuelve la ruta como literal."""
    # Sin timer_min → 422 de FastAPI (campo requerido), NO 422/404 de /{id}
    resp = client.get("/attack-reports/stats/oasis/spawn-composition")
    assert resp.status_code == 422
    body = resp.json()
    detail_str = str(body.get("detail", ""))
    # El error menciona timer_min (campo requerido), no confunde el path con /{id}
    assert "timer_min" in detail_str or "query" in detail_str.lower()


def test_CA_worst_summary_null_when_no_type(client):
    """CA: worst_case_summary=null cuando inferred_type=null."""
    defeat = (
        "Attack report on Oasis (-10|20)\n\n"
        "01.06.26, 10:00:00\n"
        "Server time: 10:00:00 (UTC +00:00)\n\n"
        "Attacker\nDefeatVillage (5|5)\nLegionnaire\n100\n100\n\n"
        "Defender\nTiger\n?\n?\n\n"
        "Bounty\n0  0  0  0\n0/100\n"
    )
    _save(client, defeat)
    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -10, 20)
    if oa is not None and oa["inferred_type"] is None:
        assert oa["worst_case_summary"] is None


def test_CA_spawn_timer_in_species(client):
    """CA: species[].spawn_timer_s coincide con SPAWN_TIMER_S del catálogo."""
    from core.game_data.oasis_spawn_catalog import SPAWN_TIMER_S
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00",
                               [("Rat", 5, 5), ("Spider", 3, 3)]))
    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    for sp in oa["species"]:
        ordinal = sp["animal_ordinal"]
        assert sp["spawn_timer_s"] == SPAWN_TIMER_S[ordinal]


def test_CA_icon_url_format(client):
    """CA: icon_url sigue el patrón /static/icons/nature_{ordinal}.png."""
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Tiger", 2, 2)]))
    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    for sp in oa["species"]:
        assert sp["icon_url"] == f"/static/icons/nature_{sp['animal_ordinal']}.png"


# ---------------------------------------------------------------------------
# T-ACCT — Jugador/aldea atacante inferida (v2.6, §4.7, RN-ACCT-01..07)
# ---------------------------------------------------------------------------
# v2.6 (2026-06-02): origin_villages: string[] SUSTITUIDO por
# attackers: [{player, village}]. Extrae el par (player, village) del blob
# quitando el tag de alianza, buscando el marcador "from village", y
# canonizando el nombre de aldea contra villages.name.
#
# Los tests verifican `oasis[].attackers: [{player, village}]`.
# Usan _make_report_blob() (attacker_line sin coords) para reproducir los
# blobs `[Tag] Player from village X` tal como los guarda el parser.
#
# La tabla farm_slots NO interviene en la atribución (JOIN eliminado en v2.5).
# ---------------------------------------------------------------------------

import asyncio as _asyncio


def _get_conn(client: TestClient):
    """Devuelve la conexión aiosqlite del adaptador activo (vía app.state)."""
    return client.app.state.attack_report_port._conn


def _seed_account(conn) -> int:
    """Inserta una cuenta de prueba y devuelve su id (sincronamente via asyncio.run)."""
    async def _do():
        async with conn.execute(
            "INSERT INTO accounts (email, username, password, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("test@test.com", "tester", b"x", "2026-01-01", "2026-01-01"),
        ) as cur:
            return cur.lastrowid
    return _asyncio.run(_do())


def _seed_world(conn, account_id: int) -> int:
    """Inserta un mundo de prueba y devuelve su id."""
    async def _do():
        async with conn.execute(
            "INSERT INTO worlds (account_id, server, tribe, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (account_id, "https://t1.test.com", "romans", "2026-01-01", "2026-01-01"),
        ) as cur:
            return cur.lastrowid
    return _asyncio.run(_do())


def _seed_village(conn, world_id: int, name: str, x: int, y: int, data_id: int = 1) -> int:
    """Inserta una aldea y devuelve su id."""
    async def _do():
        async with conn.execute(
            "INSERT INTO villages (world_id, data_id, name, x, y) VALUES (?, ?, ?, ?, ?)",
            (world_id, data_id, name, x, y),
        ) as cur:
            return cur.lastrowid
    return _asyncio.run(_do())


def _seed_farm_list(conn, name: str, owner_village_id: int) -> int:
    """Inserta una farm_list y devuelve su id.

    Se conserva para compatibilidad con tests de farm (T-ACCT-12).
    """
    async def _do():
        async with conn.execute(
            "INSERT INTO farm_lists (name, owner_village_id) VALUES (?, ?)",
            (name, owner_village_id),
        ) as cur:
            return cur.lastrowid
    return _asyncio.run(_do())


_seed_slot_counter = 0  # contador global para IDs únicos de farm_slots


def _seed_farm_slot(conn, farm_list_id: int, x: int, y: int, target_name: str = "Oasis") -> int:
    """Inserta un farm_slot. Usado en T-ACCT-12 para verificar que se ignora."""
    global _seed_slot_counter
    _seed_slot_counter += 1
    slot_id = _seed_slot_counter

    async def _do():
        async with conn.execute(
            "INSERT INTO farm_slots "
            "(id, farm_list_id, target_name, x, y, population, troops, is_active, "
            "disabled_by_bot, last_raid_state, last_raid_time, last_raid_report_id, "
            "last_raid_bounty, average_raid_bounty, distance, "
            "cooldown_seconds, report_id_at_disable) "
            "VALUES (?, ?, ?, ?, ?, 0, '{}', 1, 0, '', '', '', 0, 0, 0.0, 3600, '')",
            (slot_id, farm_list_id, target_name, x, y),
        ) as cur:
            return cur.lastrowid
    return _asyncio.run(_do())


def _commit(conn) -> None:
    """Hace commit de todas las inserciones pendientes."""
    _asyncio.run(conn.commit())


def _make_report_blob(
    x: int,
    y: int,
    date_str: str,
    animals: list[tuple[str, int, int]],
    attacker_line: str,
    utc_offset: str = "+01:00",
    bounty: str = "100  100  100  100",
) -> str:
    """
    Construye un reporte cuya línea de atacante es exactamente `attacker_line`
    SIN coordenadas "(X|Y)" al final, para que el parser guarde el texto completo
    de esa línea como origin_village_name.

    Usado en los tests T-ACCT para blobs `[Tag] Player from village X` que deben
    ser procesados por el algoritmo de extracción v2.6.
    """
    server_hour = date_str.split(", ")[1]
    names_row   = "\t".join(a[0] for a in animals)
    present_row = "\t".join(str(a[1]) for a in animals)
    killed_row  = "\t".join(str(a[2]) for a in animals)

    return (
        f"Attack report on Oasis ({x}|{y})\n\n"
        f"{date_str}\n"
        f"Server time: {server_hour} (UTC {utc_offset})\n\n"
        f"Attacker\n{attacker_line}\nLegionnaire\n100\n0\n\n"
        f"Defender\n{names_row}\n{present_row}\n{killed_row}\n\n"
        f"Bounty\n{bounty}\n50/100\n"
    )


def _get_attackers(oa: dict) -> list[dict]:
    """Devuelve el campo attackers del oasis, ya validado como lista."""
    assert "attackers" in oa, "Falta campo 'attackers' en el oasis"
    assert isinstance(oa["attackers"], list)
    assert len(oa["attackers"]) >= 1, "attackers no puede estar vacío (RN-ACCT-05)"
    return oa["attackers"]


def test_ACCT_01_basic_player_village_no_canonization(client):
    """T-ACCT-01: blob '[Storm] GonnaDie from village 05' con villages={00,01,02,03}.
    Ningún vname es substring de '05' → B extrae player='GonnaDie', village_raw='05';
    C-a sin match → village='05'.
    Resultado: [{"player":"GonnaDie","village":"05"}].
    """
    conn = _get_conn(client)
    acc_id = _seed_account(conn)
    wld_id = _seed_world(conn, acc_id)
    for i, (name, did) in enumerate([("00", 1), ("01", 2), ("02", 3), ("03", 4)]):
        _seed_village(conn, wld_id, name, i, 0, data_id=did)
    _commit(conn)

    _save(client, _make_report_blob(
        -70, 73, "01.06.26, 10:00:00", [("Rat", 5, 5)],
        attacker_line="[Storm] GonnaDie from village 05",
    ))

    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    assert oa is not None
    attackers = _get_attackers(oa)
    assert attackers == [{"player": "GonnaDie", "village": "05"}], (
        f"T-ACCT-01: esperado [{{GonnaDie,05}}], obtenido {attackers}"
    )


def test_ACCT_02_canonization_of_village_raw(client):
    """T-ACCT-02: blob '[Storm] GonnaDie from village 02' con villages={00,01,02,03}.
    B extrae village_raw='02'; C-a: '02' es substring → canónico '02'.
    Resultado: [{"player":"GonnaDie","village":"02"}].
    """
    conn = _get_conn(client)
    acc_id = _seed_account(conn)
    wld_id = _seed_world(conn, acc_id)
    for i, (name, did) in enumerate([("00", 1), ("01", 2), ("02", 3), ("03", 4)]):
        _seed_village(conn, wld_id, name, i, 0, data_id=did)
    _commit(conn)

    _save(client, _make_report_blob(
        -70, 73, "01.06.26, 10:00:00", [("Rat", 5, 5)],
        attacker_line="[Storm] GonnaDie from village 02",
    ))

    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    assert oa is not None
    attackers = _get_attackers(oa)
    assert attackers == [{"player": "GonnaDie", "village": "02"}], (
        f"T-ACCT-02: esperado [{{GonnaDie,02}}], obtenido {attackers}"
    )


def test_ACCT_03_canonization_multiword_village_raw(client):
    """T-ACCT-03: blob '[Storm] CrazyMouse from village 01 Rome But Broke'
    con villages={00,01,02,03}. C-a: '01' es substring de '01 Rome But Broke' → canónico '01'.
    Resultado: [{"player":"CrazyMouse","village":"01"}].
    """
    conn = _get_conn(client)
    acc_id = _seed_account(conn)
    wld_id = _seed_world(conn, acc_id)
    for i, (name, did) in enumerate([("00", 1), ("01", 2), ("02", 3), ("03", 4)]):
        _seed_village(conn, wld_id, name, i, 0, data_id=did)
    _commit(conn)

    _save(client, _make_report_blob(
        -70, 73, "01.06.26, 10:00:00", [("Rat", 5, 5)],
        attacker_line="[Storm] CrazyMouse from village 01 Rome But Broke",
    ))

    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    assert oa is not None
    attackers = _get_attackers(oa)
    assert attackers == [{"player": "CrazyMouse", "village": "01"}], (
        f"T-ACCT-03: esperado [{{CrazyMouse,01}}], obtenido {attackers}"
    )


def test_ACCT_04_multiword_village_no_canonization(client):
    """T-ACCT-04: blob '[Storm] CrazyMouse from village 05 Caesar On Leave'
    con villages={00,01,02,03}. Ningún vname es substring de '05 Caesar On Leave'
    → village=village_raw='05 Caesar On Leave'.
    Resultado: [{"player":"CrazyMouse","village":"05 Caesar On Leave"}].
    """
    conn = _get_conn(client)
    acc_id = _seed_account(conn)
    wld_id = _seed_world(conn, acc_id)
    for i, (name, did) in enumerate([("00", 1), ("01", 2), ("02", 3), ("03", 4)]):
        _seed_village(conn, wld_id, name, i, 0, data_id=did)
    _commit(conn)

    _save(client, _make_report_blob(
        -70, 73, "01.06.26, 10:00:00", [("Rat", 5, 5)],
        attacker_line="[Storm] CrazyMouse from village 05 Caesar On Leave",
    ))

    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    assert oa is not None
    attackers = _get_attackers(oa)
    assert attackers == [{"player": "CrazyMouse", "village": "05 Caesar On Leave"}], (
        f"T-ACCT-04: esperado [{{CrazyMouse,'05 Caesar On Leave'}}], obtenido {attackers}"
    )


def test_ACCT_05_no_marker_player_desconocido(client):
    """T-ACCT-05: blob sin marcador reconocible y sin villages en BD.
    B: sin marcador → player='Desconocido', village_raw=None.
    C: sin villages, sin match → village='Desconocido'.
    Resultado: [{"player":"Desconocido","village":"Desconocido"}]. (RN-ACCT-07)
    """
    _save(client, _make_report_blob(
        -70, 73, "01.06.26, 10:00:00", [("Rat", 5, 5)],
        attacker_line="texto_sin_marcador_irreconocible",
    ))

    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    assert oa is not None
    attackers = _get_attackers(oa)
    assert attackers == [{"player": "Desconocido", "village": "Desconocido"}], (
        f"T-ACCT-05: esperado [{{Desconocido,Desconocido}}], obtenido {attackers}"
    )


def test_ACCT_06_same_oasis_two_players(client):
    """T-ACCT-06: oasis con dos blobs de players distintos.
    blob1: GonnaDie/'05'; blob2: CrazyMouse/'05 Caesar On Leave'.
    Ambos pares DISTINCT, ordenados player A-Z (CrazyMouse < GonnaDie).
    (EC-ACCT-01, RN-ACCT-06)
    """
    conn = _get_conn(client)
    acc_id = _seed_account(conn)
    wld_id = _seed_world(conn, acc_id)
    for i, (name, did) in enumerate([("00", 1), ("01", 2), ("02", 3), ("03", 4)]):
        _seed_village(conn, wld_id, name, i, 0, data_id=did)
    _commit(conn)

    _save(client, _make_report_blob(
        -70, 73, "01.06.26, 10:00:00", [("Rat", 5, 5)],
        attacker_line="[Storm] GonnaDie from village 05",
    ))
    _save(client, _make_report_blob(
        -70, 73, "02.06.26, 10:00:00", [("Rat", 3, 3)],
        attacker_line="[Storm] CrazyMouse from village 05 Caesar On Leave",
    ))

    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    assert oa is not None
    attackers = _get_attackers(oa)
    assert attackers == [
        {"player": "CrazyMouse", "village": "05 Caesar On Leave"},
        {"player": "GonnaDie",   "village": "05"},
    ], f"T-ACCT-06: pares distintos y ordenados A-Z, obtenido {attackers}"


def test_ACCT_07_two_players_same_village_name(client):
    """T-ACCT-07: dos players, ambos con village '00' (mismo nombre canónico).
    blob1: GonnaDie from village 00; blob2: SharpHorseman from village SharpHorseman [00].
    Son pares distintos: (GonnaDie,'00') y (SharpHorseman,'00'). No se mezclan.
    (EC-ACCT-02, RN-ACCT-02)
    """
    conn = _get_conn(client)
    acc_id = _seed_account(conn)
    wld_id = _seed_world(conn, acc_id)
    _seed_village(conn, wld_id, "00", 0, 0, data_id=1)
    _commit(conn)

    _save(client, _make_report_blob(
        -70, 73, "01.06.26, 10:00:00", [("Rat", 5, 5)],
        attacker_line="[Storm] GonnaDie from village 00",
    ))
    _save(client, _make_report_blob(
        -70, 73, "02.06.26, 10:00:00", [("Rat", 3, 3)],
        attacker_line="[Storm] SharpHorseman from village SharpHorseman [00]",
    ))

    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    assert oa is not None
    attackers = _get_attackers(oa)
    assert attackers == [
        {"player": "GonnaDie",      "village": "00"},
        {"player": "SharpHorseman", "village": "00"},
    ], f"T-ACCT-07: dos pares distintos por player, obtenido {attackers}"


def test_ACCT_08_ordering_player_az_then_village_az(client):
    """T-ACCT-08: orden correcto: player A-Z, luego village A-Z dentro del mismo player.
    blob1: Zorro/Beta; blob2: Apple/Gamma; blob3: Apple/Alpha.
    Resultado: Apple/Alpha, Apple/Gamma, Zorro/Beta.
    """
    _save(client, _make_report_blob(
        -70, 73, "01.06.26, 10:00:00", [("Rat", 5, 5)],
        attacker_line="[X] Zorro from village Beta",
    ))
    _save(client, _make_report_blob(
        -70, 73, "02.06.26, 10:00:00", [("Rat", 3, 3)],
        attacker_line="[X] Apple from village Gamma",
    ))
    _save(client, _make_report_blob(
        -70, 73, "03.06.26, 10:00:00", [("Rat", 2, 2)],
        attacker_line="[X] Apple from village Alpha",
    ))

    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    assert oa is not None
    attackers = _get_attackers(oa)
    assert attackers == [
        {"player": "Apple", "village": "Alpha"},
        {"player": "Apple", "village": "Gamma"},
        {"player": "Zorro", "village": "Beta"},
    ], f"T-ACCT-08: orden player A-Z luego village A-Z, obtenido {attackers}"


def test_ACCT_09_blob_desconocido_parser_fallback(client):
    """T-ACCT-09: blob literal 'Desconocido' (fallback del parser original).
    A: sin tag → resto='Desconocido'.
    B: sin marcador → player='Desconocido', village_raw=None.
    C: 'Aldea X' no es substring de 'Desconocido' → village='Desconocido'.
    (RN-ACCT-07, EC-CITY-10)
    """
    conn = _get_conn(client)
    acc_id = _seed_account(conn)
    wld_id = _seed_world(conn, acc_id)
    _seed_village(conn, wld_id, "Aldea X", 0, 0, data_id=1)
    _commit(conn)

    # _make_report con village="Desconocido" → parser extrae "Desconocido" (sin coords)
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 5, 5)],
                               village="Desconocido"))

    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    assert oa is not None
    attackers = _get_attackers(oa)
    assert attackers == [{"player": "Desconocido", "village": "Desconocido"}], (
        f"T-ACCT-09: esperado [{{Desconocido,Desconocido}}], obtenido {attackers}"
    )


def test_ACCT_10_attackers_never_empty_no_blobs(client):
    """T-ACCT-10: attackers nunca vacío aunque blobs_by_oasis esté vacío para la key.
    _infer_attackers devuelve [{"player":"Desconocido","village":"Desconocido"}] (RN-ACCT-05).

    Se consigue con un blob sin marcador y sin villages en BD (sin hits en ningún paso).
    """
    _save(client, _make_report_blob(
        -70, 73, "01.06.26, 10:00:00", [("Rat", 5, 5)],
        attacker_line="NADA",
    ))

    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    assert oa is not None
    attackers = _get_attackers(oa)
    # Nunca vacío: mínimo Desconocido/Desconocido
    assert len(attackers) >= 1
    assert all("player" in a and "village" in a for a in attackers)


def test_ACCT_11_false_positive_canonization_sharpHorseman(client):
    """T-ACCT-11: canonización produce falso positivo aceptable.
    blob='[Storm] SharpHorseman from village SharpHorseman [00]'; villages={00,01,02,03}.
    village_raw='SharpHorseman [00]'; C-a: '00' es substring → canónico '00'.
    Par queda bajo SharpHorseman/'00' — aceptado (EC-ACCT-04, RN-ACCT-04).
    """
    conn = _get_conn(client)
    acc_id = _seed_account(conn)
    wld_id = _seed_world(conn, acc_id)
    for i, (name, did) in enumerate([("00", 1), ("01", 2), ("02", 3), ("03", 4)]):
        _seed_village(conn, wld_id, name, i, 0, data_id=did)
    _commit(conn)

    _save(client, _make_report_blob(
        -70, 73, "01.06.26, 10:00:00", [("Rat", 5, 5)],
        attacker_line="[Storm] SharpHorseman from village SharpHorseman [00]",
    ))

    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    assert oa is not None
    attackers = _get_attackers(oa)
    assert attackers == [{"player": "SharpHorseman", "village": "00"}], (
        f"T-ACCT-11: esperado [{{SharpHorseman,00}}], obtenido {attackers}"
    )


def test_ACCT_12_farm_slots_completely_ignored(client):
    """T-ACCT-12: farm_slots presentes pero completamente ignorados.
    Setup: villages={'02'}, farm_slot de 'Aldea X' apuntando al oasis,
    blob '[Storm] GonnaDie from village 02'.
    El campo attackers extrae el par del blob, NO de farm_slots (RN-CITY-01 v2.6).
    """
    conn = _get_conn(client)
    acc_id = _seed_account(conn)
    wld_id = _seed_world(conn, acc_id)
    _seed_village(conn, wld_id, "02", 0, 0, data_id=1)
    vil_x = _seed_village(conn, wld_id, "Aldea X", 0, 0, data_id=2)
    fl_x = _seed_farm_list(conn, "Lista X", vil_x)
    _seed_farm_slot(conn, fl_x, -70, 73)  # debe ser completamente ignorado
    _commit(conn)

    _save(client, _make_report_blob(
        -70, 73, "01.06.26, 10:00:00", [("Rat", 5, 5)],
        attacker_line="[Storm] GonnaDie from village 02",
    ))

    data = _get_spawn(client, 6)
    oa = _find_oasis(data, -70, 73)
    assert oa is not None
    attackers = _get_attackers(oa)
    assert attackers == [{"player": "GonnaDie", "village": "02"}], (
        f"T-ACCT-12: farm_slots ignorados; esperado [{{GonnaDie,02}}], obtenido {attackers}"
    )
