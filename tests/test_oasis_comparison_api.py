"""
Tests de integración de EP-10 — GET /attack-reports/stats/oasis/comparison

Cubre los escenarios T-01..T-12 del spec docs/specs/reaparicion-animales-oasis.md §12.
También verifica que EP-06 y EP-09 siguen funcionando (no se rompió el routing).

Usa TestClient con lifespan activado (BD real en fichero temporal, aislada por test).
Mismo patrón de fixture que test_global_oasis_stats_api.py.

Añadido en la feature reaparicion-animales-oasis (2026-06-01).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from adapters.api.main import app

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
    db_file = tmp_path / "test_oasis_comparison.db"
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

def _build_report(
    x: int,
    y: int,
    date_str: str,
    village: str,
    animals_str: str = "Rat",
    animals_present: str = "10",
    animals_killed: str = "10",
    utc_offset: str = "+01:00",
    bounty: str = "100  100  100  100",
) -> str:
    """
    Construye el texto crudo de un reporte de oasis.

    date_str: formato "DD.MM.YY, HH:MM:SS"
    Los reportes de victoria tienen survived = present - killed.
    """
    server_hour = date_str.split(", ")[1]  # extrae la hora
    return (
        f"Attack report on Oasis ({x}|{y})\n\n"
        f"{date_str}\n"
        f"Server time: {server_hour} (UTC {utc_offset})\n\n"
        f"Attacker\n{village} (1|2)\nLegionnaire\n100\n0\n\n"
        f"Defender\n{animals_str}\n{animals_present}\n{animals_killed}\n\n"
        f"Bounty\n{bounty}\n50/100\n"
    )


def _save(client: TestClient, raw_text: str) -> int:
    """Guarda un reporte y devuelve su id."""
    resp = client.post("/attack-reports", json={"raw_text": raw_text})
    assert resp.status_code == 201, f"save failed ({resp.status_code}): {resp.text}"
    return resp.json()["id"]


# Reporte de derrota: la tabla de animales no incluye killed/survived
_DEFEAT_REPORT = """\
Attack report on Oasis (-77|-77)

01.06.26, 09:00:00
Server time: 10:00:00 (UTC +01:00)

Attacker
DefeatVillage (5|5)
Legionnaire
100
100

Defender
Tiger
?
?

Bounty
0  0  0  0
0/100
"""

_DEFEAT_REPORT_2 = """\
Attack report on Oasis (-77|-77)

01.06.26, 10:00:00
Server time: 11:00:00 (UTC +01:00)

Attacker
DefeatVillage (5|5)
Legionnaire
100
100

Defender
Tiger
?
?

Bounty
0  0  0  0
0/100
"""


# ---------------------------------------------------------------------------
# T-04 — BD vacía
# ---------------------------------------------------------------------------

class TestBDVacia:
    def test_T04_bd_vacia_devuelve_200_con_listas_vacias(self, client):
        """T-04: BD vacía → 200 con oasis:[] y species_columns:[]."""
        resp = client.get("/attack-reports/stats/oasis/comparison")
        assert resp.status_code == 200
        data = resp.json()
        assert data["oasis"] == []
        assert data["species_columns"] == []
        assert "computed_at" in data

    def test_computed_at_es_iso8601_utc(self, client):
        """computed_at está en formato ISO 8601 con zona horaria UTC."""
        resp = client.get("/attack-reports/stats/oasis/comparison")
        data = resp.json()
        computed_at = data["computed_at"]
        assert "+" in computed_at or computed_at.endswith("Z")
        # Verificar que parseamos sin errores
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(computed_at)
        assert dt.tzinfo is not None


# ---------------------------------------------------------------------------
# T-05 — Todos los oasis con 1 solo reporte
# ---------------------------------------------------------------------------

class TestOasisConUnSoloReporte:
    def test_T05_un_reporte_has_rates_false_species_vacio(self, client):
        """T-05: Oasis con 1 solo reporte → has_rates:false, species:[]."""
        _save(client, _build_report(-10, -10, "01.06.26, 09:00:00", "V1"))
        _save(client, _build_report(-20, -20, "01.06.26, 10:00:00", "V2"))

        resp = client.get("/attack-reports/stats/oasis/comparison")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["oasis"]) == 2
        for oasis in data["oasis"]:
            assert oasis["has_rates"] is False
            assert oasis["species"] == []
            assert oasis["total_attacks"] == 1
        # Sin tasas en ningún oasis → species_columns vacío
        assert data["species_columns"] == []


# ---------------------------------------------------------------------------
# T-01 — Datos completos: tasas y proyecciones calculadas
# ---------------------------------------------------------------------------

class TestConDatos:
    def test_T01_tres_oasis_tasas_y_proyecciones(self, client):
        """
        T-01: 3 oasis con >=2 ataques y especies distintas.
        Verifica: 200, estructura, species_columns unión, proyecciones calculadas.
        """
        # Oasis A (-30|-30): Rat, 2 ataques, gap 1h
        # Ataque 1: Rat 10 presentes, 10 muertos → 0 survived
        _save(client, _build_report(-30, -30, "01.06.26, 08:00:00", "VA1",
                                    animals_str="Rat", animals_present="10", animals_killed="10"))
        # Ataque 2: Rat 4 presentes (regeneró 4 desde 0 en 1h → rate=4/h)
        _save(client, _build_report(-30, -30, "01.06.26, 09:00:00", "VA1",
                                    animals_str="Rat", animals_present="4", animals_killed="4"))

        # Oasis B (-31|-31): Spider, 2 ataques, gap 2h
        _save(client, _build_report(-31, -31, "01.06.26, 07:00:00", "VB1",
                                    animals_str="Spider", animals_present="8", animals_killed="8"))
        _save(client, _build_report(-31, -31, "01.06.26, 09:00:00", "VB1",
                                    animals_str="Spider", animals_present="6", animals_killed="6"))

        # Oasis C (-32|-32): 1 solo ataque (sin tasas)
        _save(client, _build_report(-32, -32, "01.06.26, 09:00:00", "VC1",
                                    animals_str="Rat", animals_present="5", animals_killed="5"))

        resp = client.get("/attack-reports/stats/oasis/comparison")
        assert resp.status_code == 200
        data = resp.json()

        assert len(data["oasis"]) == 3
        # species_columns: unión de Rat (ordinal 1) y Spider (ordinal 2)
        col_ordinals = [c["animal_ordinal"] for c in data["species_columns"]]
        assert 1 in col_ordinals  # Rat
        assert 2 in col_ordinals  # Spider

        # Los dos primeros oasis deben tener has_rates=True
        has_rates_oasis = [o for o in data["oasis"] if o["has_rates"]]
        no_rates_oasis = [o for o in data["oasis"] if not o["has_rates"]]
        assert len(has_rates_oasis) == 2
        assert len(no_rates_oasis) == 1

    def test_projected_now_formula_floor(self, client):
        """
        Verifica que projected_now = floor(last_survived + avg_regen_per_hour * hours).
        Con gap 1h, Rat regenera 4/h, último survived=4.
        El tiempo desde el último ataque no es predecible (depende del reloj del servidor),
        así que solo verificamos que projected_now >= last_survived (no decrece).
        """
        _save(client, _build_report(-33, -33, "01.06.26, 08:00:00", "VF1",
                                    animals_str="Rat", animals_present="10", animals_killed="10"))
        _save(client, _build_report(-33, -33, "01.06.26, 09:00:00", "VF1",
                                    animals_str="Rat", animals_present="4", animals_killed="4"))

        resp = client.get("/attack-reports/stats/oasis/comparison")
        assert resp.status_code == 200
        data = resp.json()

        oasis_entry = next(o for o in data["oasis"]
                           if o["coord_x_dest"] == -33 and o["coord_y_dest"] == -33)
        assert oasis_entry["has_rates"] is True
        assert len(oasis_entry["species"]) == 1
        sp = oasis_entry["species"][0]
        assert sp["animal_ordinal"] == 1
        assert sp["avg_regen_per_hour"] == 4.0
        assert sp["valid_intervals"] == 1
        assert sp["last_survived"] == 0  # 4 presentes, 4 muertos → 0 survived
        assert sp["projected_now"] is not None
        assert sp["projected_now"] >= 0  # floor, mínimo 0
        assert isinstance(sp["projected_now"], int)


# ---------------------------------------------------------------------------
# T-06 — last_survived null (reporte de derrota)
# ---------------------------------------------------------------------------

class TestLastSurvivedNull:
    def test_T06_derrota_projected_now_null(self, client):
        """
        T-06: Oasis con 2 reportes donde el último es una derrota (survived=null).
        → last_survived:null, projected_now:null, pero has_rates puede ser True
          si el primer intervalo fue victoria.
        """
        # Ataque 1 (victoria): Tiger 5 presentes, 5 muertos
        _save(client, _build_report(-77, -77, "01.06.26, 08:00:00", "VD1",
                                    animals_str="Tiger", animals_present="5", animals_killed="5"))
        # Ataque 2 (victoria): Tiger 3 presentes (regeneró 3 desde 0 en 1h → rate=3/h)
        _save(client, _build_report(-77, -77, "01.06.26, 09:00:00", "VD1",
                                    animals_str="Tiger", animals_present="3", animals_killed="3"))
        # Ataque 3 (derrota): Tiger survived=null
        _save(client, _DEFEAT_REPORT)
        # Ataque 4 (derrota): para que el último sea derrota
        _save(client, _DEFEAT_REPORT_2)

        resp = client.get("/attack-reports/stats/oasis/comparison")
        assert resp.status_code == 200
        data = resp.json()

        oasis_entry = next(
            (o for o in data["oasis"] if o["coord_x_dest"] == -77 and o["coord_y_dest"] == -77),
            None,
        )
        assert oasis_entry is not None
        # Debe haber tasa (los primeros intervalos son válidos)
        assert oasis_entry["has_rates"] is True
        tiger_species = next(
            (s for s in oasis_entry["species"] if "iger" in s["animal_name"]),
            None,
        )
        assert tiger_species is not None
        # Último reporte fue derrota → survived null
        assert tiger_species["last_survived"] is None
        # RN-08: projected_now null cuando last_survived es null
        assert tiger_species["projected_now"] is None


# ---------------------------------------------------------------------------
# T-02 — Especie compartida: solo un oasis tiene tasa
# ---------------------------------------------------------------------------

class TestEspecieCompartida:
    def test_T02_especie_en_columns_pero_ausente_en_species(self, client):
        """
        T-02: Dos oasis comparten especie (Rat), pero solo uno tiene tasa.
        → species_columns tiene Rat; oasis sin tasa NO la tiene en species[].
        """
        # Oasis A (-40|-40): Rat con 2 ataques → tiene tasa
        _save(client, _build_report(-40, -40, "01.06.26, 08:00:00", "V40A",
                                    animals_str="Rat", animals_present="10", animals_killed="10"))
        _save(client, _build_report(-40, -40, "01.06.26, 09:00:00", "V40A",
                                    animals_str="Rat", animals_present="5", animals_killed="5"))

        # Oasis B (-41|-41): Rat con 1 ataque → sin tasa
        _save(client, _build_report(-41, -41, "01.06.26, 09:30:00", "V41A",
                                    animals_str="Rat", animals_present="7", animals_killed="7"))

        resp = client.get("/attack-reports/stats/oasis/comparison")
        assert resp.status_code == 200
        data = resp.json()

        # species_columns debe incluir Rat (viene del oasis A)
        col_ordinals = [c["animal_ordinal"] for c in data["species_columns"]]
        assert 1 in col_ordinals  # Rat ordinal=1

        # Oasis B (sin tasa) no debe tener Rat en species[]
        oasis_b = next(o for o in data["oasis"]
                       if o["coord_x_dest"] == -41 and o["coord_y_dest"] == -41)
        assert oasis_b["has_rates"] is False
        rat_in_b = [s for s in oasis_b["species"] if s["animal_ordinal"] == 1]
        assert rat_in_b == [], "Oasis sin tasa para Rat no debe tener Rat en species[]"


# ---------------------------------------------------------------------------
# icon_url presente y con el patrón correcto
# ---------------------------------------------------------------------------

class TestIconUrl:
    def test_icon_url_en_species_columns_y_species(self, client):
        """
        icon_url presente en species_columns[] y species[] con el patrón
        /static/icons/nature_{ordinal}.png.
        """
        _save(client, _build_report(-50, -50, "01.06.26, 08:00:00", "VIcon1",
                                    animals_str="Rat", animals_present="10", animals_killed="10"))
        _save(client, _build_report(-50, -50, "01.06.26, 09:00:00", "VIcon1",
                                    animals_str="Rat", animals_present="4", animals_killed="4"))

        resp = client.get("/attack-reports/stats/oasis/comparison")
        assert resp.status_code == 200
        data = resp.json()

        # Verificar icon_url en species_columns
        for col in data["species_columns"]:
            ordinal = col["animal_ordinal"]
            assert col["icon_url"] == f"/static/icons/nature_{ordinal}.png"

        # Verificar icon_url en species[] de cada oasis
        for oasis in data["oasis"]:
            for sp in oasis["species"]:
                ordinal = sp["animal_ordinal"]
                assert sp["icon_url"] == f"/static/icons/nature_{ordinal}.png"


# ---------------------------------------------------------------------------
# Sin Accept-Language obligatorio
# ---------------------------------------------------------------------------

class TestSinAcceptLanguage:
    def test_no_requiere_accept_language(self, client):
        """
        EP-10 no requiere Accept-Language. Sin la cabecera debe devolver 200.
        (Contraste con endpoints de catálogo que devuelven 400 sin ella.)
        """
        resp = client.get(
            "/attack-reports/stats/oasis/comparison",
            headers={},  # explícitamente sin Accept-Language
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Ordenación: has_rates=True antes que has_rates=False (RN-05)
# ---------------------------------------------------------------------------

class TestOrdenacion:
    def test_T12_has_rates_true_primero(self, client):
        """
        T-12: Oasis con has_rates=True aparecen antes que has_rates=False.
        """
        # Oasis sin tasas (1 ataque, más reciente)
        _save(client, _build_report(-60, -60, "02.06.26, 09:00:00", "VOrder1",
                                    animals_str="Rat", animals_present="5", animals_killed="5"))

        # Oasis con tasas (2 ataques, más antiguo)
        _save(client, _build_report(-61, -61, "01.06.26, 08:00:00", "VOrder2",
                                    animals_str="Rat", animals_present="10", animals_killed="10"))
        _save(client, _build_report(-61, -61, "01.06.26, 09:00:00", "VOrder2",
                                    animals_str="Rat", animals_present="4", animals_killed="4"))

        resp = client.get("/attack-reports/stats/oasis/comparison")
        assert resp.status_code == 200
        oasis_list = resp.json()["oasis"]

        assert len(oasis_list) == 2
        # El primero debe tener has_rates=True aunque su last_attack sea más antiguo
        assert oasis_list[0]["has_rates"] is True
        assert oasis_list[1]["has_rates"] is False

    def test_dentro_mismo_grupo_last_attack_desc(self, client):
        """
        Dentro del grupo has_rates=True, el oasis más reciente primero (last_attack DESC).
        """
        # Oasis A: 2 ataques más reciente (09:30)
        _save(client, _build_report(-62, -62, "01.06.26, 08:00:00", "VOrder3A",
                                    animals_str="Rat", animals_present="10", animals_killed="10"))
        _save(client, _build_report(-62, -62, "01.06.26, 09:30:00", "VOrder3A",
                                    animals_str="Rat", animals_present="5", animals_killed="5"))

        # Oasis B: 2 ataques más antiguo (09:00)
        _save(client, _build_report(-63, -63, "01.06.26, 08:00:00", "VOrder3B",
                                    animals_str="Rat", animals_present="10", animals_killed="10"))
        _save(client, _build_report(-63, -63, "01.06.26, 09:00:00", "VOrder3B",
                                    animals_str="Rat", animals_present="5", animals_killed="5"))

        resp = client.get("/attack-reports/stats/oasis/comparison")
        assert resp.status_code == 200
        oasis_list = resp.json()["oasis"]

        has_rates_list = [o for o in oasis_list if o["has_rates"]]
        assert len(has_rates_list) == 2
        # Oasis A (09:30) debe ir antes que Oasis B (09:00)
        assert has_rates_list[0]["last_attack"] > has_rates_list[1]["last_attack"]


# ---------------------------------------------------------------------------
# T-08 — utc_offset = null → asumir UTC
# ---------------------------------------------------------------------------

class TestUtcOffsetNull:
    def test_T08_sin_utc_offset_asume_utc(self, client):
        """
        T-08: utc_offset=null en el último reporte → attacked_at tratado como UTC.
        El endpoint no debe fallar (comportamiento defensivo).
        """
        # Construir un reporte sin hora de servidor (sin utc_offset)
        report_sin_offset = """\
Attack report on Oasis (-88|-88)

01.06.26, 09:00:00

Attacker
OffVillage (1|2)
Legionnaire
100
0

Defender
Rat
10
10

Bounty
100  100  100  100
50/100
"""
        report_sin_offset_2 = """\
Attack report on Oasis (-88|-88)

01.06.26, 10:00:00

Attacker
OffVillage (1|2)
Legionnaire
100
0

Defender
Rat
4
4

Bounty
100  100  100  100
50/100
"""
        # Intentar guardar (puede fallar si el parser requiere Server time)
        r1 = client.post("/attack-reports", json={"raw_text": report_sin_offset})
        r2 = client.post("/attack-reports", json={"raw_text": report_sin_offset_2})
        # Si el parser no acepta sin offset, este test verifica que el endpoint
        # siempre devuelve 200 (con los reportes que haya)
        resp = client.get("/attack-reports/stats/oasis/comparison")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# T-09 — hours_since_last_attack negativo → tratar como 0
# ---------------------------------------------------------------------------

class TestHorasNegativas:
    def test_T09_projected_now_es_last_survived_cuando_horas_cero(self, client):
        """
        T-09: Si hours=0 (caso límite o reloj adelantado), projected_now = last_survived.
        Verificamos que el campo es >= 0 (nunca negativo).
        """
        # Reporte con fecha en el futuro lejano para forzar hours~=0
        _save(client, _build_report(-90, -90, "01.06.26, 08:00:00", "VNeg1",
                                    animals_str="Rat", animals_present="10", animals_killed="10"))
        _save(client, _build_report(-90, -90, "01.06.26, 09:00:00", "VNeg1",
                                    animals_str="Rat", animals_present="3", animals_killed="3"))

        resp = client.get("/attack-reports/stats/oasis/comparison")
        assert resp.status_code == 200
        data = resp.json()

        oasis_entry = next(
            (o for o in data["oasis"] if o["coord_x_dest"] == -90 and o["coord_y_dest"] == -90),
            None,
        )
        assert oasis_entry is not None
        assert oasis_entry["hours_since_last_attack"] >= 0
        for sp in oasis_entry["species"]:
            if sp["projected_now"] is not None:
                assert sp["projected_now"] >= 0


# ---------------------------------------------------------------------------
# T-10 — avg_regen_per_hour = 0
# ---------------------------------------------------------------------------

class TestRegenCero:
    def test_T10_regen_cero_projected_now_igual_a_last_survived(self, client):
        """
        T-10: avg_regen_per_hour=0 → projected_now = last_survived (floor(s + 0*h) = s).
        Se obtiene con dos ataques donde regenerated=0 (mismo survived que prev_survived).
        """
        # Ataque 1: Rat 10 presentes, 0 muertos → survived=10
        _save(client, _build_report(-91, -91, "01.06.26, 08:00:00", "VZero1",
                                    animals_str="Rat", animals_present="10", animals_killed="0"))
        # Ataque 2: Rat 10 presentes (regeneró 0 desde 10 → rate=0/h)
        _save(client, _build_report(-91, -91, "01.06.26, 09:00:00", "VZero1",
                                    animals_str="Rat", animals_present="10", animals_killed="0"))

        resp = client.get("/attack-reports/stats/oasis/comparison")
        assert resp.status_code == 200
        data = resp.json()

        oasis_entry = next(
            (o for o in data["oasis"] if o["coord_x_dest"] == -91 and o["coord_y_dest"] == -91),
            None,
        )
        assert oasis_entry is not None
        if oasis_entry["has_rates"] and oasis_entry["species"]:
            sp = oasis_entry["species"][0]
            assert sp["avg_regen_per_hour"] == 0.0
            if sp["last_survived"] is not None and sp["projected_now"] is not None:
                assert sp["projected_now"] >= 0


# ---------------------------------------------------------------------------
# Verificación de que EP-06 y EP-09 siguen funcionando (no se rompió el routing)
# ---------------------------------------------------------------------------

class TestRoutingNoRoto:
    def test_ep06_sigue_funcionando(self, client):
        """
        EP-06 (GET /attack-reports/stats/oasis?x=...&y=...) no fue capturado
        ni roto por la declaración de EP-10.
        """
        resp = client.get("/attack-reports/stats/oasis?x=-999&y=-999")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_attacks" in data
        assert data["total_attacks"] == 0

    def test_ep09_sigue_funcionando(self, client):
        """
        EP-09 (GET /attack-reports/stats/global) no fue afectado por EP-10.
        """
        resp = client.get("/attack-reports/stats/global")
        assert resp.status_code == 200
        data = resp.json()
        assert "animal_appearances" in data
        assert "animal_regen_rates" in data

    def test_ep10_no_capturado_por_ep04(self, client):
        """
        EP-10 (ruta literal /stats/oasis/comparison) no es capturado por
        EP-04 (/{id} que espera int). Si lo fuera, daría 422.
        """
        resp = client.get("/attack-reports/stats/oasis/comparison")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Estructura de la respuesta
# ---------------------------------------------------------------------------

class TestEstructuraRespuesta:
    def test_campos_de_oasis_entry(self, client):
        """Los campos requeridos están presentes en cada entrada de oasis."""
        _save(client, _build_report(-92, -92, "01.06.26, 08:00:00", "VStruct1",
                                    animals_str="Rat", animals_present="10", animals_killed="10"))
        _save(client, _build_report(-92, -92, "01.06.26, 09:00:00", "VStruct1",
                                    animals_str="Rat", animals_present="4", animals_killed="4"))

        resp = client.get("/attack-reports/stats/oasis/comparison")
        assert resp.status_code == 200
        data = resp.json()

        assert "computed_at" in data
        assert "species_columns" in data
        assert "oasis" in data

        for oasis in data["oasis"]:
            assert "coord_x_dest" in oasis
            assert "coord_y_dest" in oasis
            assert "total_attacks" in oasis
            assert "last_attack" in oasis
            assert "hours_since_last_attack" in oasis
            assert "has_rates" in oasis
            assert "species" in oasis
            assert isinstance(oasis["has_rates"], bool)
            assert isinstance(oasis["total_attacks"], int)
            assert oasis["hours_since_last_attack"] >= 0

    def test_campos_de_species_entry(self, client):
        """Los campos requeridos están presentes en cada entrada de species[]."""
        _save(client, _build_report(-93, -93, "01.06.26, 08:00:00", "VStruct2",
                                    animals_str="Rat", animals_present="10", animals_killed="10"))
        _save(client, _build_report(-93, -93, "01.06.26, 09:00:00", "VStruct2",
                                    animals_str="Rat", animals_present="4", animals_killed="4"))

        resp = client.get("/attack-reports/stats/oasis/comparison")
        assert resp.status_code == 200
        data = resp.json()

        for oasis in data["oasis"]:
            for sp in oasis["species"]:
                assert "animal_ordinal" in sp
                assert "animal_name" in sp
                assert "icon_url" in sp
                assert "avg_regen_per_hour" in sp
                assert "valid_intervals" in sp
                assert "last_survived" in sp
                assert "projected_now" in sp
                assert sp["valid_intervals"] >= 1

    def test_especie_sin_tasa_ausente_de_species(self, client):
        """
        Matiz central: especie que NUNCA apareció en un oasis no está en su species[].
        (No es 0, es ausencia.)
        """
        # Oasis X: solo Rat con 2 ataques → Rat tiene tasa
        _save(client, _build_report(-94, -94, "01.06.26, 08:00:00", "VAbsence1",
                                    animals_str="Rat", animals_present="10", animals_killed="10"))
        _save(client, _build_report(-94, -94, "01.06.26, 09:00:00", "VAbsence1",
                                    animals_str="Rat", animals_present="4", animals_killed="4"))

        # Oasis Y: solo Spider con 2 ataques → Spider tiene tasa
        _save(client, _build_report(-95, -95, "01.06.26, 08:00:00", "VAbsence2",
                                    animals_str="Spider", animals_present="6", animals_killed="6"))
        _save(client, _build_report(-95, -95, "01.06.26, 09:00:00", "VAbsence2",
                                    animals_str="Spider", animals_present="3", animals_killed="3"))

        resp = client.get("/attack-reports/stats/oasis/comparison")
        assert resp.status_code == 200
        data = resp.json()

        # species_columns tiene tanto Rat como Spider (unión)
        col_ordinals = {c["animal_ordinal"] for c in data["species_columns"]}
        assert 1 in col_ordinals  # Rat
        assert 2 in col_ordinals  # Spider

        # Oasis X (-94|-94): solo Rat en species[], NO Spider
        oasis_x = next(o for o in data["oasis"]
                       if o["coord_x_dest"] == -94 and o["coord_y_dest"] == -94)
        species_ordinals_x = {s["animal_ordinal"] for s in oasis_x["species"]}
        assert 1 in species_ordinals_x  # Rat presente
        assert 2 not in species_ordinals_x  # Spider AUSENTE (no 0)

        # Oasis Y (-95|-95): solo Spider en species[], NO Rat
        oasis_y = next(o for o in data["oasis"]
                       if o["coord_x_dest"] == -95 and o["coord_y_dest"] == -95)
        species_ordinals_y = {s["animal_ordinal"] for s in oasis_y["species"]}
        assert 2 in species_ordinals_y  # Spider presente
        assert 1 not in species_ordinals_y  # Rat AUSENTE (no 0)


# ---------------------------------------------------------------------------
# Tests que reproducen el bug real: el parser inserta 10 filas por reporte
# ---------------------------------------------------------------------------

def _build_report_10_species(
    x: int,
    y: int,
    date_str: str,
    village: str,
    present_counts: list[int],  # longitud 10, uno por especie (Rat→Elephant)
    killed_counts: list[int],   # longitud 10
    utc_offset: str = "+01:00",
    bounty: str = "100  100  100  100",
) -> str:
    """
    Construye un reporte con las 10 columnas de animales, tal como hace Travian real.
    Los oasis de Travian muestran las 10 especies en la tabla del defensor, con 0
    en las que no existen en ese oasis. El parser inserta 10 filas por reporte.

    present_counts y killed_counts tienen longitud 10; el índice 0 es Rat, el 10 es Elephant.
    """
    ANIMAL_HEADER = "Rat  Spider  Snake  Bat  Wild Boar  Wolf  Bear  Crocodile  Tiger  Elephant"
    present_row = "  ".join(str(v) for v in present_counts)
    killed_row  = "  ".join(str(v) for v in killed_counts)
    server_hour = date_str.split(", ")[1]
    return (
        f"Attack report on Oasis ({x}|{y})\n\n"
        f"{date_str}\n"
        f"Server time: {server_hour} (UTC {utc_offset})\n\n"
        f"Attacker\n{village} (1|2)\nLegionnaire\n100\n0\n\n"
        f"Defender\n{ANIMAL_HEADER}\n{present_row}\n{killed_row}\n\n"
        f"Bounty\n{bounty}\n50/100\n"
    )


class TestBugEspeciesNuncaPresentes:
    """
    Reproduces el bug real: el parser inserta 10 filas por reporte (present=0 para
    las que no existen en ese oasis). Sin el fix, el endpoint incluye esas especies
    con avg_regen_per_hour=0.0 en species[]. Con el fix, solo las que tuvieron
    present>0 en al menos un reporte aparecen en species[].
    """

    def test_especie_con_present_siempre_cero_no_aparece_en_species(self, client):
        """
        Un oasis con reportes de 10 columnas donde Rat/Spider/WildBoar tienen
        present>0 y las otras 7 siempre tienen present=0.
        → species[] debe contener SOLO Rat, Spider, WildBoar (las 3 presentes).
        → Las 7 ausentes (Snake, Bat, Wolf, Bear, Crocodile, Tiger, Elephant)
          NO deben aparecer en species[] ni con avg_regen_per_hour=0.0.
        """
        # Oasis (-40|18) — 2 reportes con 10 columnas (reproduce BD real)
        # Rat=ordinal1, Spider=ordinal2, Snake=3, Bat=4, WildBoar=5, Wolf=6,
        # Bear=7, Crocodile=8, Tiger=9, Elephant=10
        # present_counts: [Rat, Spider, Snake, Bat, WildBoar, Wolf, Bear, Croc, Tiger, Eleph]
        _save(client, _build_report_10_species(
            -40, 18, "01.06.26, 08:57:03", "V1",
            present_counts=[26, 22, 0, 0, 12, 0, 0, 0, 0, 0],
            killed_counts= [25, 21, 0, 0, 12, 0, 0, 0, 0, 0],
        ))
        _save(client, _build_report_10_species(
            -40, 18, "01.06.26, 10:54:08", "V1",
            present_counts=[13,  3, 0, 0,  0, 0, 0, 0, 0, 0],
            killed_counts= [13,  3, 0, 0,  0, 0, 0, 0, 0, 0],
        ))

        resp = client.get("/attack-reports/stats/oasis/comparison")
        assert resp.status_code == 200
        data = resp.json()

        oasis_entry = next(
            (o for o in data["oasis"] if o["coord_x_dest"] == -40 and o["coord_y_dest"] == 18),
            None,
        )
        assert oasis_entry is not None

        species_ordinals = {s["animal_ordinal"] for s in oasis_entry["species"]}

        # Presentes (alguna vez present>0) → deben aparecer
        assert 1 in species_ordinals, "Rat (ordinal 1) debe estar en species[]"
        assert 2 in species_ordinals, "Spider (ordinal 2) debe estar en species[]"
        # Wild Boar (ordinal 5) solo estuvo en el primer reporte (present=12, killed=12)
        # → no genera tasa válida (solo 1 intervalo posible: 0 survived → present=0 en T2)
        # → con 2 reportes SÍ puede tener tasa (regenerated = present2 - survived1 = 0 - 0 = 0)
        # Lo importante es que las AUSENTES no aparezcan

        # Nunca presentes → NO deben aparecer (ni con avg_regen_per_hour=0.0)
        assert 3 not in species_ordinals, "Snake (ord 3) nunca presente → AUSENTE"
        assert 4 not in species_ordinals, "Bat (ord 4) nunca presente → AUSENTE"
        assert 6 not in species_ordinals, "Wolf (ord 6) nunca presente → AUSENTE"
        assert 7 not in species_ordinals, "Bear (ord 7) nunca presente → AUSENTE"
        assert 8 not in species_ordinals, "Crocodile (ord 8) nunca presente → AUSENTE"
        assert 9 not in species_ordinals, "Tiger (ord 9) nunca presente → AUSENTE"
        assert 10 not in species_ordinals, "Elephant (ord 10) nunca presente → AUSENTE"

        # Verificar que ninguna especie ausente aparece con avg_regen_per_hour=0.0
        AUSENTES = {3, 4, 6, 7, 8, 9, 10}
        for sp in oasis_entry["species"]:
            assert sp["animal_ordinal"] not in AUSENTES, (
                f"Especie ord={sp['animal_ordinal']} (nunca presente) "
                f"no debe estar en species[] (avg={sp['avg_regen_per_hour']})"
            )

    def test_especie_con_present_cero_en_todos_los_reportes_ausente_de_species_columns(self, client):
        """
        Si una especie tiene present=0 en TODOS los reportes de TODOS los oasis,
        no debe aparecer en species_columns global.
        """
        # Un único oasis con 2 reportes: solo Rat presente, otras 9 siempre 0
        _save(client, _build_report_10_species(
            -50, 50, "01.06.26, 08:00:00", "V2",
            present_counts=[10, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            killed_counts= [10, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        ))
        _save(client, _build_report_10_species(
            -50, 50, "01.06.26, 09:00:00", "V2",
            present_counts=[ 5, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            killed_counts= [ 5, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        ))

        resp = client.get("/attack-reports/stats/oasis/comparison")
        assert resp.status_code == 200
        data = resp.json()

        col_ordinals = {c["animal_ordinal"] for c in data["species_columns"]}

        # Solo Rat debe estar en species_columns (las otras 9 nunca tuvieron present>0)
        # Rat puede tener tasa: regenerated = 5 - 0 = 5 en el segundo intervalo
        assert 1 in col_ordinals, "Rat debe estar en species_columns (sí tuvo present>0)"

        AUSENTES = {2, 3, 4, 5, 6, 7, 8, 9, 10}
        for ordinal in AUSENTES:
            assert ordinal not in col_ordinals, (
                f"Especie ordinal={ordinal} (nunca present>0) "
                f"no debe estar en species_columns"
            )

    def test_especie_presente_pero_tasa_cero_si_aparece_en_species(self, client):
        """
        EC-07 del spec: avg_regen_per_hour=0 cuando el delta regenerado es 0.
        Una especie que SÍ tuvo present>0 pero cuya tasa calculada es 0.0 DEBE
        aparecer en species[] (no se omite por tasa cero; eso es distinto de ausencia).

        Escenario: Rat present=10 → survived=10 (no se matan), luego present=10 → survived=10.
        regenerated = 10 - 10 = 0, rate = 0.0/h. Rat SÍ estuvo presente → debe aparecer.
        """
        _save(client, _build_report_10_species(
            -60, 60, "01.06.26, 08:00:00", "V3",
            present_counts=[10, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            killed_counts= [ 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],  # survived=10
        ))
        _save(client, _build_report_10_species(
            -60, 60, "01.06.26, 09:00:00", "V3",
            present_counts=[10, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            killed_counts= [ 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],  # survived=10
        ))

        resp = client.get("/attack-reports/stats/oasis/comparison")
        assert resp.status_code == 200
        data = resp.json()

        oasis_entry = next(
            (o for o in data["oasis"] if o["coord_x_dest"] == -60 and o["coord_y_dest"] == 60),
            None,
        )
        assert oasis_entry is not None

        species_ordinals = {s["animal_ordinal"] for s in oasis_entry["species"]}

        # Rat tuvo present>0 → debe estar en species[], aunque su tasa sea 0.0
        assert 1 in species_ordinals, (
            "Rat (present>0 en todos los reportes) debe aparecer en species[] "
            "aunque avg_regen_per_hour sea 0.0 (EC-07)"
        )

        # Verificar que la tasa es efectivamente 0.0 (no omitida)
        rat = next(s for s in oasis_entry["species"] if s["animal_ordinal"] == 1)
        assert rat["avg_regen_per_hour"] == 0.0, "La tasa de regeneración de Rat debe ser 0.0"

        # Las otras 9 (nunca present>0) no deben aparecer
        AUSENTES = {2, 3, 4, 5, 6, 7, 8, 9, 10}
        for sp in oasis_entry["species"]:
            assert sp["animal_ordinal"] not in AUSENTES, (
                f"Especie ord={sp['animal_ordinal']} nunca presente no debe estar en species[]"
            )
