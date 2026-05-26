"""
Tests unitarios del TroopsParser contra los 5 fixtures reales de troops.

Cubre las secciones 12.1–12.5 del spec lectura-troops.

Convención del proyecto: los tests de endpoint (TestClient) van con
@pytest.mark.skip porque la app no arranca en tests por el WIP de accounts
(requiere email-validator + TRAVIAN_BOT_SECRET_KEY). Los tests de parser y
use case son completamente independientes de la app y no llevan skip.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from adapters.browser.parsers.troops_parser import TroopsParser

# ---------------------------------------------------------------------------
# Fixtures de ficheros HTML
# ---------------------------------------------------------------------------

_FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent / "fixtures" / "overview"
)


def _html(filename: str) -> str:
    return (_FIXTURES_DIR / filename).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 12.1  parse_own — troops_own.html
# ---------------------------------------------------------------------------

class TestParseOwn:

    def test_troop_types(self):
        """El thead expone u21-u30 + uhero en ese orden."""
        raw = TroopsParser.parse_own(_html("troops_own.html"))
        assert raw.troop_types == [
            "u21", "u22", "u23", "u24", "u25", "u26", "u27", "u28", "u29", "u30", "uhero"
        ]

    def test_village_count(self):
        """6 aldeas (00–05); tr.empty y tr.sum no cuentan como aldeas."""
        raw = TroopsParser.parse_own(_html("troops_own.html"))
        assert len(raw.villages) == 6

    def test_village_00_counts(self):
        """Aldea game_id=19040: valores exactos del fixture."""
        raw = TroopsParser.parse_own(_html("troops_own.html"))
        v = next(v for v in raw.villages if v.game_id == 19040)
        assert v.counts == {
            "u21": 227, "u22": 3136, "u23": 125, "u24": 1885,
            "u25": 0, "u26": 420, "u27": 30, "u28": 60,
            "u29": 0, "u30": 0, "uhero": 0,
        }

    def test_village_04_all_zero(self):
        """Aldea game_id=26421: todos los counts son 0 (EC-01)."""
        raw = TroopsParser.parse_own(_html("troops_own.html"))
        v = next(v for v in raw.villages if v.game_id == 26421)
        assert all(count == 0 for count in v.counts.values())

    def test_village_02_hero_present(self):
        """Aldea game_id=25306: uhero=1."""
        raw = TroopsParser.parse_own(_html("troops_own.html"))
        v = next(v for v in raw.villages if v.game_id == 25306)
        assert v.counts["uhero"] == 1

    def test_totals(self):
        """tr.sum se parsea correctamente como totales globales."""
        raw = TroopsParser.parse_own(_html("troops_own.html"))
        assert raw.totals == {
            "u21": 327, "u22": 4883, "u23": 278, "u24": 3357,
            "u25": 17, "u26": 480, "u27": 54, "u28": 78,
            "u29": 0, "u30": 0, "uhero": 1,
        }

    def test_ignores_sum_row_as_village(self):
        """tr.sum NO aparece en la lista de aldeas."""
        raw = TroopsParser.parse_own(_html("troops_own.html"))
        assert len(raw.villages) == 6  # misma aserción que test_village_count

    def test_ignores_empty_row(self):
        """tr.empty (colspan) NO aparece en la lista de aldeas."""
        raw = TroopsParser.parse_own(_html("troops_own.html"))
        assert len(raw.villages) == 6

    def test_troop_types_are_strings(self):
        """troop_types del parser devuelve list[str], no list[TroopTypeInfo]."""
        raw = TroopsParser.parse_own(_html("troops_own.html"))
        assert all(isinstance(t, str) for t in raw.troop_types)


# ---------------------------------------------------------------------------
# 12.2  parse_support — troops_support.html
# ---------------------------------------------------------------------------

class TestParseSupport:

    def test_village_count(self):
        """6 wrappers → 6 aldeas."""
        raw = TroopsParser.parse_support(_html("troops_support.html"))
        assert len(raw.villages) == 6

    def test_village_00_nature_u40(self):
        """Aldea 19040: u40=5 en nature (EC-09 — naturaleza presente)."""
        raw = TroopsParser.parse_support(_html("troops_support.html"))
        v = next(v for v in raw.villages if v.game_id == 19040)
        assert v.nature.get("u40") == 5

    def test_village_00_own(self):
        """Aldea 19040: propias correctas."""
        raw = TroopsParser.parse_support(_html("troops_support.html"))
        v = next(v for v in raw.villages if v.game_id == 19040)
        assert v.own["u21"] == 227
        assert v.own["u22"] == 1199
        assert v.own["u23"] == 125
        assert v.own["u24"] == 848
        assert v.own["u26"] == 228
        assert v.own["u25"] == 0

    def test_village_00_upkeep(self):
        """Aldea 19040: cereal/hora = 9093."""
        raw = TroopsParser.parse_support(_html("troops_support.html"))
        v = next(v for v in raw.villages if v.game_id == 19040)
        assert v.upkeep_per_hour == 9093

    def test_village_00_offence(self):
        """Aldea 19040: offence = 201060 (con bidi EC-18)."""
        raw = TroopsParser.parse_support(_html("troops_support.html"))
        v = next(v for v in raw.villages if v.game_id == 19040)
        assert v.offence == 201060

    def test_village_00_def_infantry(self):
        """Aldea 19040: def_infantry = 90625."""
        raw = TroopsParser.parse_support(_html("troops_support.html"))
        v = next(v for v in raw.villages if v.game_id == 19040)
        assert v.def_infantry == 90625

    def test_village_00_def_cavalry(self):
        """Aldea 19040: def_cavalry = 110720."""
        raw = TroopsParser.parse_support(_html("troops_support.html"))
        v = next(v for v in raw.villages if v.game_id == 19040)
        assert v.def_cavalry == 110720

    def test_village_02_no_nature(self):
        """Aldea 25306 (aldea 02): sin fila de naturaleza → nature vacío o sin entradas (EC-17)."""
        raw = TroopsParser.parse_support(_html("troops_support.html"))
        v = next(v for v in raw.villages if v.game_id == 25306)
        # No debe haber u31-u40 en nature
        nature_with_troops = {k: qty for k, qty in v.nature.items() if qty > 0}
        assert nature_with_troops == {}

    def test_village_04_all_zero_strength(self):
        """Aldea 26421 (sin tropas): offence/def_infantry/def_cavalry = None (EC-10/EC-11)."""
        raw = TroopsParser.parse_support(_html("troops_support.html"))
        v = next(v for v in raw.villages if v.game_id == 26421)
        assert v.offence is None
        assert v.def_infantry is None
        assert v.def_cavalry is None

    def test_village_04_upkeep_zero(self):
        """Aldea 26421 (sin tropas): upkeep_per_hour = 0."""
        raw = TroopsParser.parse_support(_html("troops_support.html"))
        v = next(v for v in raw.villages if v.game_id == 26421)
        assert v.upkeep_per_hour == 0

    def test_hero_alias_consistency(self):
        """hero == own.get('uhero', 0) para todas las aldeas (TR-06)."""
        raw = TroopsParser.parse_support(_html("troops_support.html"))
        for v in raw.villages:
            assert v.hero == v.own.get("uhero", 0)

    def test_troop_names_empty_from_parser(self):
        """El parser devuelve troop_names vacío — el use case lo construye."""
        raw = TroopsParser.parse_support(_html("troops_support.html"))
        assert raw.troop_names == {}


# ---------------------------------------------------------------------------
# 12.3  parse_smithy — troops_smithy.html
# ---------------------------------------------------------------------------

class TestParseSmithry:

    def test_troop_types(self):
        """El thead de smithy expone u21-u28 (8 tropas de combate galos, RN-06)."""
        raw = TroopsParser.parse_smithy(_html("troops_smithy.html"))
        assert raw.troop_types == ["u21", "u22", "u23", "u24", "u25", "u26", "u27", "u28"]

    def test_village_count(self):
        """6 aldeas en smithy."""
        raw = TroopsParser.parse_smithy(_html("troops_smithy.html"))
        assert len(raw.villages) == 6

    def test_village_00_in_progress(self):
        """Aldea 19040: u22 y u24 en investigación activa (EC-04)."""
        raw = TroopsParser.parse_smithy(_html("troops_smithy.html"))
        v = next(v for v in raw.villages if v.game_id == 19040)
        assert v.in_progress == ["u22", "u24"]

    def test_village_01_no_progress(self):
        """Aldea 24341: span.dot → in_progress=[] (EC-05)."""
        raw = TroopsParser.parse_smithy(_html("troops_smithy.html"))
        v = next(v for v in raw.villages if v.game_id == 24341)
        assert v.in_progress == []

    def test_village_00_levels(self):
        """Aldea 19040: niveles exactos del fixture."""
        raw = TroopsParser.parse_smithy(_html("troops_smithy.html"))
        v = next(v for v in raw.villages if v.game_id == 19040)
        assert v.levels == {
            "u21": 0, "u22": 9, "u23": 0, "u24": 9,
            "u25": 0, "u26": 3, "u27": 0, "u28": 0,
        }

    def test_dash_is_none(self):
        """Aldea 25306: u26="-" → None (EC-02: no investigable)."""
        raw = TroopsParser.parse_smithy(_html("troops_smithy.html"))
        v = next(v for v in raw.villages if v.game_id == 25306)
        assert v.levels["u26"] is None
        assert v.levels["u27"] is None
        assert v.levels["u28"] is None

    def test_zero_is_int(self):
        """Aldea 25306: u21="0" → 0 (int, no None) (EC-03)."""
        raw = TroopsParser.parse_smithy(_html("troops_smithy.html"))
        v = next(v for v in raw.villages if v.game_id == 25306)
        assert v.levels["u21"] == 0
        assert isinstance(v.levels["u21"], int)

    def test_village_04_mostly_dash(self):
        """Aldea 26421: solo u21=0 entero, resto None."""
        raw = TroopsParser.parse_smithy(_html("troops_smithy.html"))
        v = next(v for v in raw.villages if v.game_id == 26421)
        assert v.levels["u21"] == 0
        assert v.levels["u22"] is None
        assert v.levels["u23"] is None

    def test_troop_types_are_strings(self):
        """troop_types del parser devuelve list[str]."""
        raw = TroopsParser.parse_smithy(_html("troops_smithy.html"))
        assert all(isinstance(t, str) for t in raw.troop_types)


# ---------------------------------------------------------------------------
# 12.4  parse_hospital — troops_hospital.html
# ---------------------------------------------------------------------------

class TestParseHospital:

    def test_player_tribe(self):
        """Tribu del jugador = 3 (Galos), extraído de i.tribe3_medium (RN-05)."""
        raw = TroopsParser.parse_hospital(_html("troops_hospital.html"))
        assert raw.player_tribe == 3

    def test_troop_types(self):
        """El thead de hospital expone u21-u26 (RN-07)."""
        raw = TroopsParser.parse_hospital(_html("troops_hospital.html"))
        assert raw.troop_types == ["u21", "u22", "u23", "u24", "u25", "u26"]

    def test_village_count(self):
        """6 aldeas en hospital."""
        raw = TroopsParser.parse_hospital(_html("troops_hospital.html"))
        assert len(raw.villages) == 6

    def test_village_00_has_hospital_no_healing(self):
        """Aldea 19040: span.dot → has_hospital=True, healing=False (EC-06)."""
        raw = TroopsParser.parse_hospital(_html("troops_hospital.html"))
        v = next(v for v in raw.villages if v.game_id == 19040)
        assert v.has_hospital is True
        assert v.healing is False

    def test_village_00_wounded_all_zero(self):
        """Aldea 19040: hospital existe, sin heridos (EC-08)."""
        raw = TroopsParser.parse_hospital(_html("troops_hospital.html"))
        v = next(v for v in raw.villages if v.game_id == 19040)
        assert all(count == 0 for count in v.wounded.values())
        assert len(v.wounded) == 6  # u21-u26

    def test_village_02_no_hospital(self):
        """Aldea 25306: span.none → has_hospital=False, healing=False, wounded={} (EC-07)."""
        raw = TroopsParser.parse_hospital(_html("troops_hospital.html"))
        v = next(v for v in raw.villages if v.game_id == 25306)
        assert v.has_hospital is False
        assert v.healing is False
        assert v.wounded == {}

    def test_village_01_has_hospital(self):
        """Aldea 24341: span.dot → has_hospital=True."""
        raw = TroopsParser.parse_hospital(_html("troops_hospital.html"))
        v = next(v for v in raw.villages if v.game_id == 24341)
        assert v.has_hospital is True

    def test_village_01_wounded_u22(self):
        """Aldea 24341: u22=2 heridos."""
        raw = TroopsParser.parse_hospital(_html("troops_hospital.html"))
        v = next(v for v in raw.villages if v.game_id == 24341)
        assert v.wounded["u22"] == 2

    def test_troop_types_are_strings(self):
        """troop_types del parser devuelve list[str]."""
        raw = TroopsParser.parse_hospital(_html("troops_hospital.html"))
        assert all(isinstance(t, str) for t in raw.troop_types)


# ---------------------------------------------------------------------------
# 12.5  parse_training — troops_training.html
# ---------------------------------------------------------------------------

class TestParseTraining:

    def test_building_gids(self):
        """Columnas del thead: [19, 20, 21, 46] (RN-08)."""
        raw = TroopsParser.parse_training(_html("troops_training.html"))
        assert raw.building_gids == [19, 20, 21, 46]

    def test_village_count(self):
        """6 aldeas en training."""
        raw = TroopsParser.parse_training(_html("troops_training.html"))
        assert len(raw.villages) == 6

    def test_village_00_cuartel(self):
        """Aldea 19040, gid=19: 1:56:06 = 6966 segundos."""
        raw = TroopsParser.parse_training(_html("troops_training.html"))
        v = next(v for v in raw.villages if v.game_id == 19040)
        q = next(q for q in v.queues if q.gid == 19)
        assert q.building_exists is True
        assert q.queue_seconds == 6966

    def test_village_00_establo(self):
        """Aldea 19040, gid=20: 2:36:45 = 9405 segundos."""
        raw = TroopsParser.parse_training(_html("troops_training.html"))
        v = next(v for v in raw.villages if v.game_id == 19040)
        q = next(q for q in v.queues if q.gid == 20)
        assert q.building_exists is True
        assert q.queue_seconds == 9405

    def test_village_00_taller_dot(self):
        """Aldea 19040, gid=21: span.dot → building_exists=True, queue_seconds=0 (EC-12)."""
        raw = TroopsParser.parse_training(_html("troops_training.html"))
        v = next(v for v in raw.villages if v.game_id == 19040)
        q = next(q for q in v.queues if q.gid == 21)
        assert q.building_exists is True
        assert q.queue_seconds == 0

    def test_village_00_hospital_dot(self):
        """Aldea 19040, gid=46: span.dot → building_exists=True, queue_seconds=0."""
        raw = TroopsParser.parse_training(_html("troops_training.html"))
        v = next(v for v in raw.villages if v.game_id == 19040)
        q = next(q for q in v.queues if q.gid == 46)
        assert q.building_exists is True
        assert q.queue_seconds == 0

    def test_village_02_taller_none(self):
        """Aldea 25306, gid=21: span.none → building_exists=False, queue_seconds=None (EC-13)."""
        raw = TroopsParser.parse_training(_html("troops_training.html"))
        v = next(v for v in raw.villages if v.game_id == 25306)
        q = next(q for q in v.queues if q.gid == 21)
        assert q.building_exists is False
        assert q.queue_seconds is None

    def test_village_02_hospital_none(self):
        """Aldea 25306, gid=46: span.none → building_exists=False, queue_seconds=None."""
        raw = TroopsParser.parse_training(_html("troops_training.html"))
        v = next(v for v in raw.villages if v.game_id == 25306)
        q = next(q for q in v.queues if q.gid == 46)
        assert q.building_exists is False
        assert q.queue_seconds is None

    def test_village_04_cuartel_dot(self):
        """Aldea 26421, gid=19: span.dot → building_exists=True, queue_seconds=0."""
        raw = TroopsParser.parse_training(_html("troops_training.html"))
        v = next(v for v in raw.villages if v.game_id == 26421)
        q = next(q for q in v.queues if q.gid == 19)
        assert q.building_exists is True
        assert q.queue_seconds == 0

    def test_village_05_cuartel(self):
        """Aldea 24498, gid=19: 0:55:25 = 3325 segundos."""
        raw = TroopsParser.parse_training(_html("troops_training.html"))
        v = next(v for v in raw.villages if v.game_id == 24498)
        q = next(q for q in v.queues if q.gid == 19)
        assert q.building_exists is True
        assert q.queue_seconds == 3325

    def test_whitespace_in_duration(self):
        """EC-14: parse_time maneja whitespace; el fixture 19040/cuartel tiene '    1:56:06    '."""
        raw = TroopsParser.parse_training(_html("troops_training.html"))
        v = next(v for v in raw.villages if v.game_id == 19040)
        q = next(q for q in v.queues if q.gid == 19)
        # Si el whitespace hubiera roto el parser, queue_seconds sería incorrecto o habría excepción
        assert q.queue_seconds == 6966

    def test_buildings_empty_from_parser(self):
        """El parser devuelve buildings=[] — el use case lo enriquece con BuildingInfo."""
        raw = TroopsParser.parse_training(_html("troops_training.html"))
        assert raw.buildings == []

    def test_village_02_cuartel_duration(self):
        """Aldea 25306, gid=19: 23:49:50 = 85790 segundos."""
        raw = TroopsParser.parse_training(_html("troops_training.html"))
        v = next(v for v in raw.villages if v.game_id == 25306)
        q = next(q for q in v.queues if q.gid == 19)
        assert q.building_exists is True
        assert q.queue_seconds == 85790

    def test_village_02_establo_duration(self):
        """Aldea 25306, gid=20: 12:58:21 = 46701 segundos."""
        raw = TroopsParser.parse_training(_html("troops_training.html"))
        v = next(v for v in raw.villages if v.game_id == 25306)
        q = next(q for q in v.queues if q.gid == 20)
        assert q.building_exists is True
        assert q.queue_seconds == 46701
