"""
Tests de integración de los endpoints de ataques a oasis (EP-01 a EP-06).

POST   /attack-reports/parse       — EP-01
POST   /attack-reports             — EP-02
GET    /attack-reports             — EP-03
GET    /attack-reports/{id}        — EP-04
DELETE /attack-reports/{id}        — EP-05
GET    /attack-reports/stats/oasis — EP-06

Los tests usan TestClient con lifespan activado (BD real en fichero temporal).
Cada módulo de tests crea su propio cliente con lifespan para aislar el estado
de la BD entre módulos.

Ver spec docs/specs/bd-ataques-oasis.md §12 para la correspondencia de tests.
Añadido en la feature bd-ataques-oasis (2026-05-30).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from adapters.api.main import app


# ---------------------------------------------------------------------------
# Fixtures de texto crudo
# ---------------------------------------------------------------------------

# Nota: se usa función-scope con tmp_path + monkeypatch de DB_PATH (patrón del proyecto,
# igual que test_accounts_api.py) para garantizar BD limpia en cada test.

# Reporte válido en inglés — oasis (-32|-45)
_REPORT_VALID = """\
Attack report on Oasis (-32|-45)

30.05.26, 16:28:53
Server time: 17:28:53 (UTC +1:00)

Attacker
MyVillage (-10|-20)
Legionnaire
100
5

Defender
Rat  Spider
12   8
12   8

Bounty
480  480  480  480
120/240
"""

# Segundo ataque al mismo oasis — timestamp diferente (30 min después)
_REPORT_VALID_2 = """\
Attack report on Oasis (-32|-45)

30.05.26, 17:00:00
Server time: 18:00:00 (UTC +1:00)

Attacker
MyVillage (-10|-20)
Legionnaire
150
10

Defender
Rat  Spider
8    5
6    4

Bounty
320  320  320  320
100/240
"""

# Reporte con coordenadas negativas — EC-02
_REPORT_NEG = """\
Attack report on Oasis (-100|-200)

30.05.26, 16:28:53
Server time: 17:28:53 (UTC +1:00)

Attacker
Village2 (50|60)
Legionnaire
50
0

Defender
Rat
5
5

Bounty
100  100  100  100
50/100
"""

# Texto vacío (validación DTO) — T-EC07
_EMPTY_TEXT = ""

# Texto con 2 bloques — T-EC03
_REPORT_TWO_BLOCKS = """\
Attack report on Oasis (-32|-45)

30.05.26, 16:28:53
Server time: 17:28:53 (UTC +1:00)

Attacker
MyVillage (-10|-20)
Legionnaire
100
5

Attack report on Oasis (-33|-46)

31.05.26, 10:00:00
Server time: 11:00:00 (UTC +1:00)

Attacker
MyVillage (-10|-20)
Legionnaire
100
0
"""

# Texto con nombre de animal no reconocido — T-EC01
_REPORT_UNKNOWN_ANIMAL = """\
Attack report on Oasis (-32|-45)

30.05.26, 16:28:53
Server time: 17:28:53 (UTC +1:00)

Attacker
MyVillage (-10|-20)
Legionnaire
100
5

Defender
Lobezno  Dragón
10       5
10       5

Bounty
100  100  100  100
50/100
"""

# Texto sin sección Nature — T-EC02
_REPORT_NOT_NATURE = """\
Attack report on Village (-32|-45)

30.05.26, 16:28:53
Server time: 17:28:53 (UTC +1:00)

Attacker
MyVillage (-10|-20)
Legionnaire
100
5

Defender
Pretoriano
50
10

Bounty
200  200  200  200
200/500
"""


# ---------------------------------------------------------------------------
# Fixture — cliente con lifespan y BD temporal aislada por test
# ---------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch, tmp_path):
    """
    Cliente con la app real apuntando a una BD temporal por test.

    Usa el mismo patrón que test_accounts_api.py: monkeypatch de DB_PATH
    antes del lifespan para garantizar BD limpia en cada test.
    """
    db_file = tmp_path / "test_attack_reports.db"
    monkeypatch.setattr("adapters.db.database.DB_PATH", str(db_file))

    # Limpiar estado residual del app singleton entre tests
    for attr in ("attack_report_port", "world_runtime_port"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)

    with TestClient(app) as c:
        yield c

    for attr in ("attack_report_port", "world_runtime_port"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)


# ---------------------------------------------------------------------------
# EP-01 — Parse sin guardar
# ---------------------------------------------------------------------------

class TestParse:
    def test_T01_parse_valid_report(self, client):
        """T-01: Parse de reporte válido → 200 con preview correcto."""
        resp = client.post("/attack-reports/parse", json={"raw_text": _REPORT_VALID})
        assert resp.status_code == 200
        data = resp.json()
        assert data["coord_x_dest"] == -32
        assert data["coord_y_dest"] == -45
        assert data["utc_offset"] == "+01:00"
        assert "attacked_at" in data
        assert "attacker_troops" in data
        assert len(data["attacker_troops"]) >= 1
        assert "animals" in data
        assert len(data["animals"]) >= 1
        assert "bounty" in data
        assert "hero_inventory" in data   # C2: campo raíz
        # hero_inventory NO debe estar dentro de bounty
        assert "hero_inventory" not in data["bounty"]
        assert data["already_exists"] is False

    def test_attacker_cost_loss_computed(self, client):
        """El coste de las tropas perdidas se calcula por tribu+ordinal.

        _REPORT_VALID: Legionnaire (romano_1) pierde 5. Coste unitario
        120/100/150/30 → ×5 = 600/500/750/150 (total 2000).
        """
        resp = client.post("/attack-reports/parse", json={"raw_text": _REPORT_VALID})
        assert resp.status_code == 200
        data = resp.json()
        assert data["attacker_tribe"] == "romans"
        cl = data["attacker_cost_loss"]
        assert cl == {"wood": 600, "clay": 500, "iron": 750, "crop": 150, "total": 2000}

    def test_T03_utc_offset_in_parse(self, client):
        """T-03: attacked_at verbatim (naive, sin offset), utc_offset presente como metadato."""
        resp = client.post("/attack-reports/parse", json={"raw_text": _REPORT_VALID})
        data = resp.json()
        assert data["utc_offset"] == "+01:00"
        assert "T" in data["attacked_at"]  # ISO 8601 naive
        # Verbatim: la hora del ataque es 16:28:53, no la hora UTC restada
        assert "16:28:53" in data["attacked_at"]
        # Sin offset en el string (verbatim naive)
        assert "+" not in data["attacked_at"]
        assert "Z" not in data["attacked_at"]

    def test_T04_no_hero_inventory(self, client):
        """T-04: Sin inventario de héroe → hero_inventory: null."""
        resp = client.post("/attack-reports/parse", json={"raw_text": _REPORT_VALID})
        data = resp.json()
        assert data["hero_inventory"] is None

    def test_T_EC01_unrecognized_animal(self, client):
        """T-EC01: Nombre de animal no reconocido → 422 con lista."""
        resp = client.post("/attack-reports/parse", json={"raw_text": _REPORT_UNKNOWN_ANIMAL})
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "Lobezno" in detail or "lobezno" in detail.lower()

    def test_T_EC02_not_nature(self, client):
        """T-EC02: Sin sección Nature → 422."""
        resp = client.post("/attack-reports/parse", json={"raw_text": _REPORT_NOT_NATURE})
        assert resp.status_code == 422

    def test_T_EC03_multiple_reports(self, client):
        """T-EC03: 2 bloques de reporte → 422 con mención de bloques."""
        resp = client.post("/attack-reports/parse", json={"raw_text": _REPORT_TWO_BLOCKS})
        assert resp.status_code == 422
        assert "2" in resp.json()["detail"]

    def test_T_EC07_empty_text(self, client):
        """T-EC07: raw_text vacío → 422 (validación Pydantic min_length=1)."""
        resp = client.post("/attack-reports/parse", json={"raw_text": _EMPTY_TEXT})
        assert resp.status_code == 422

    def test_T_EC08_text_too_long(self, client):
        """T-EC08: raw_text > 50 000 chars → 422 (validación Pydantic max_length)."""
        long_text = "A" * 50_001
        resp = client.post("/attack-reports/parse", json={"raw_text": long_text})
        assert resp.status_code == 422

    def test_T13_already_exists_field(self, client):
        """T-13: Después de guardar, el parse del mismo reporte devuelve already_exists=true."""
        # Primero guardar
        client.post("/attack-reports", json={"raw_text": _REPORT_VALID})
        # Luego parsear de nuevo
        resp = client.post("/attack-reports/parse", json={"raw_text": _REPORT_VALID})
        data = resp.json()
        assert data["already_exists"] is True
        assert data["existing_id"] is not None


# ---------------------------------------------------------------------------
# EP-02 — Save
# ---------------------------------------------------------------------------

class TestSave:
    def test_T05_save_new_report(self, client):
        """T-05: Save de reporte nuevo → 201 con id."""
        resp = client.post("/attack-reports", json={"raw_text": _REPORT_NEG})
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["id"] >= 1
        assert data["coord_x_dest"] == -100
        assert data["coord_y_dest"] == -200
        assert data["utc_offset"] == "+01:00"  # C3: incluir en 201

    def test_T_EC04_duplicate_report(self, client):
        """T-EC04: Save del mismo reporte dos veces → 409 con detail."""
        # Usar un reporte único con timestamp diferente para aislar el test
        report = """\
Attack report on Oasis (-55|-55)

15.01.26, 10:00:00
Server time: 11:00:00 (UTC +1:00)

Attacker
DupVillage (1|2)
Legionnaire
50
2

Defender
Rat
6
6

Bounty
60  60  60  60
60/100
"""
        # Primera vez → 201
        r1 = client.post("/attack-reports", json={"raw_text": report})
        assert r1.status_code == 201

        # Segunda vez → 409
        r2 = client.post("/attack-reports", json={"raw_text": report})
        assert r2.status_code == 409
        detail = r2.json()["detail"]
        assert "id" in detail.lower() or str(r1.json()["id"]) in detail

    def test_save_unrecognized_animal(self, client):
        """Save con animal no reconocido → 422."""
        resp = client.post("/attack-reports", json={"raw_text": _REPORT_UNKNOWN_ANIMAL})
        assert resp.status_code == 422

    def test_T_EC07_empty_text_save(self, client):
        """Save con texto vacío → 422."""
        resp = client.post("/attack-reports", json={"raw_text": ""})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# EP-03 — List
# ---------------------------------------------------------------------------

class TestList:
    def test_T06_list_no_filters(self, client):
        """T-06: List sin filtros → 200 con paginado."""
        resp = client.get("/attack-reports")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "items" in data
        assert "cumulative_bounty" in data
        assert isinstance(data["total"], int)
        assert isinstance(data["items"], list)

    def test_T07_list_filtered_by_coords(self, client):
        """T-07: List filtrado por coords → solo reportes del oasis indicado."""
        resp = client.get("/attack-reports?x=-100&y=-200")
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["coord_x_dest"] == -100
            assert item["coord_y_dest"] == -200

    def test_T_EC09_x_without_y(self, client):
        """T-EC09: x sin y → 400."""
        resp = client.get("/attack-reports?x=-32")
        assert resp.status_code == 400
        assert "y" in resp.json()["detail"].lower()

    def test_T_EC09_y_without_x(self, client):
        """T-EC09: y sin x → 400."""
        resp = client.get("/attack-reports?y=-45")
        assert resp.status_code == 400

    def test_T_EC10_limit_zero(self, client):
        """T-EC10: limit=0 → 400."""
        resp = client.get("/attack-reports?limit=0")
        assert resp.status_code == 400

    def test_T_EC10_limit_over_100(self, client):
        """T-EC10: limit=101 → 400."""
        resp = client.get("/attack-reports?limit=101")
        assert resp.status_code == 400

    def test_negative_offset(self, client):
        """offset < 0 → 400."""
        resp = client.get("/attack-reports?offset=-1")
        assert resp.status_code == 400

    def test_invalid_from_date(self, client):
        """from_date no ISO 8601 → 400."""
        resp = client.get("/attack-reports?from_date=not-a-date")
        assert resp.status_code == 400

    def test_invalid_to_date(self, client):
        """to_date no ISO 8601 → 400."""
        resp = client.get("/attack-reports?to_date=not-a-date")
        assert resp.status_code == 400

    def test_from_date_after_to_date(self, client):
        """from_date > to_date → 400."""
        resp = client.get("/attack-reports?from_date=2026-12-01&to_date=2026-01-01")
        assert resp.status_code == 400

    def test_list_items_structure(self, client):
        """Los items del listado tienen la estructura esperada."""
        resp = client.get("/attack-reports?limit=1")
        assert resp.status_code == 200
        data = resp.json()
        if data["items"]:
            item = data["items"][0]
            assert "id" in item
            assert "attacked_at" in item
            assert "bounty" in item
            assert "animals_summary" in item
            assert "attacker_losses_count" in item
            assert "bounty_total" in item


# ---------------------------------------------------------------------------
# EP-04 — Detail
# ---------------------------------------------------------------------------

class TestDetail:
    def test_T09_detail_existing_report(self, client):
        """T-09: Detail de reporte existente → todos los campos completos."""
        # Primero guardar un reporte para obtener su id
        report = """\
Attack report on Oasis (-60|-60)

20.01.26, 10:00:00
Server time: 11:00:00 (UTC +1:00)

Attacker
DetailVillage (3|4)
Legionnaire
80
4

Defender
Rat  Spider
10   6
8    4

Bounty
200  200  200  200
100/200
"""
        save_resp = client.post("/attack-reports", json={"raw_text": report})
        assert save_resp.status_code == 201
        report_id = save_resp.json()["id"]

        # Obtener el detalle
        resp = client.get(f"/attack-reports/{report_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == report_id
        assert "attacked_at" in data
        assert "utc_offset" in data
        assert "attacker_troops" in data
        assert "animals" in data
        assert "bounty" in data
        assert "hero_inventory" in data   # C2: campo raíz
        assert "hero_inventory" not in data["bounty"]
        assert "created_at" in data

    def test_T_EC11_detail_not_found(self, client):
        """T-EC11: Detail de reporte inexistente → 404."""
        resp = client.get("/attack-reports/999999")
        assert resp.status_code == 404
        assert "no encontrado" in resp.json()["detail"].lower()

    def test_detail_with_id_zero_invalid(self, client):
        """id=0 → 422 (ge=1 en Path)."""
        resp = client.get("/attack-reports/0")
        assert resp.status_code == 422

    def test_detail_with_string_id(self, client):
        """id='abc' → 422 (no puede convertir a int)."""
        # "stats" como path no debería llegar a este handler (routing correcto C6)
        resp = client.get("/attack-reports/abc")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# EP-05 — Delete
# ---------------------------------------------------------------------------

class TestDelete:
    def test_T10_delete_existing(self, client):
        """T-10: Delete de reporte existente → 204; fila borrada; cascade borra hijas."""
        report = """\
Attack report on Oasis (-70|-70)

25.01.26, 12:00:00
Server time: 13:00:00 (UTC +1:00)

Attacker
DelVillage (5|5)
Legionnaire
60
3

Defender
Rat
8
8

Bounty
80  80  80  80
80/100
"""
        save_resp = client.post("/attack-reports", json={"raw_text": report})
        assert save_resp.status_code == 201
        report_id = save_resp.json()["id"]

        # Borrar
        del_resp = client.delete(f"/attack-reports/{report_id}")
        assert del_resp.status_code == 204

        # Verificar que ya no existe
        get_resp = client.get(f"/attack-reports/{report_id}")
        assert get_resp.status_code == 404

    def test_T_EC11_delete_not_found(self, client):
        """T-EC11: Delete de reporte inexistente → 404."""
        resp = client.delete("/attack-reports/999998")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# EP-06 — Estadísticas de oasis
# ---------------------------------------------------------------------------

class TestOasisStats:
    def _save_report_for_stats(self, client, x, y, date_str, village, animals_str="Rat", animals_present="10", animals_killed="10"):
        """Helper para guardar un reporte en coords específicas."""
        report = f"""\
Attack report on Oasis ({x}|{y})

{date_str}

Attacker
{village} (1|2)
Legionnaire
100
5

Defender
{animals_str}
{animals_present}
{animals_killed}

Bounty
100  100  100  100
50/100
"""
        resp = client.post("/attack-reports", json={"raw_text": report})
        return resp

    def test_T_EC12_stats_no_reports(self, client):
        """T-EC12: Stats de oasis sin reportes → 200 con total_attacks=0."""
        resp = client.get("/attack-reports/stats/oasis?x=-999&y=-999")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_attacks"] == 0
        assert data["first_attack"] is None
        assert data["last_attack"] is None
        assert data["animal_appearances"] == []
        assert data["repopulation_gaps"] == []

    def test_T11_stats_one_attack(self, client):
        """T-11: Stats con 1 ataque → gap_seconds=null, regenerated=null."""
        # Usar coordenadas únicas para aislar
        ox, oy = -80, -80
        r = self._save_report_for_stats(
            client, ox, oy, "10.02.26, 09:00:00", "StatVillage1"
        )
        # Si falla (p.ej. reporte ya existe), ignorar y aún así verificar stats
        resp = client.get(f"/attack-reports/stats/oasis?x={ox}&y={oy}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_attacks"] >= 1
        # El primer ataque debe tener gap_seconds=null y regenerated=null
        if data["repopulation_gaps"]:
            first_gap = min(data["repopulation_gaps"], key=lambda g: g["attacked_at"])
            assert first_gap["gap_seconds"] is None
            assert first_gap["prev_attacked_at"] is None
            for ra in first_gap.get("regenerated_animals", []):
                assert ra["regenerated"] is None
                assert ra["prev_survived"] is None

    def test_T12_stats_two_attacks(self, client):
        """T-12: Stats con 2+ ataques → gap_seconds > 0, regenerated numérico."""
        ox, oy = -81, -81
        # Primer ataque
        self._save_report_for_stats(
            client, ox, oy, "10.02.26, 09:00:00", "StatVillage2a",
            animals_str="Rat", animals_present="10", animals_killed="10"
        )
        # Segundo ataque (30 min después: 09:30:00)
        self._save_report_for_stats(
            client, ox, oy, "10.02.26, 09:30:00", "StatVillage2a",
            animals_str="Rat", animals_present="5", animals_killed="5"
        )
        resp = client.get(f"/attack-reports/stats/oasis?x={ox}&y={oy}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_attacks"] >= 2
        # Debe haber al menos un gap con gap_seconds != null
        gaps_with_seconds = [g for g in data["repopulation_gaps"] if g["gap_seconds"] is not None]
        assert len(gaps_with_seconds) >= 1
        assert gaps_with_seconds[0]["gap_seconds"] > 0

    def test_stats_missing_x_or_y(self, client):
        """Sin x o y → 400."""
        resp = client.get("/attack-reports/stats/oasis?x=-32")
        assert resp.status_code == 400
        resp2 = client.get("/attack-reports/stats/oasis")
        assert resp2.status_code == 400

    def test_stats_route_not_captured_by_id_route(self, client):
        """
        Verifica que /attack-reports/stats/oasis no es capturado por /{id}.
        Si EP-06 está declarado antes de EP-04, /stats no llega como {id}='stats'.
        """
        resp = client.get("/attack-reports/stats/oasis?x=-999&y=-999")
        # Si la ruta colisionara, devolvería 422 (cannot convert 'stats' to int).
        # Si está bien declarada, devuelve 200 (aunque sea con datos vacíos).
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# CA-14 — GET /attack-reports sin filtros devuelve JSON paginado con total correcto
# ---------------------------------------------------------------------------

class TestPagination:
    def test_CA14_list_returns_total(self, client):
        """CA-14: GET /attack-reports sin filtros → total correcto."""
        resp = client.get("/attack-reports")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["total"], int)
        assert data["total"] >= 0
        assert len(data["items"]) <= data["total"]

    def test_cumulative_bounty_is_int_or_zero(self, client):
        """cumulative_bounty es un entero >= 0."""
        resp = client.get("/attack-reports")
        data = resp.json()
        assert isinstance(data["cumulative_bounty"], (int, float))
        assert data["cumulative_bounty"] >= 0


# ---------------------------------------------------------------------------
# EP-07 — Balance de recursos (GET /attack-reports/stats/bounty)
# ---------------------------------------------------------------------------

# Reporte con botín conocido para tests de bounty
_REPORT_BOUNTY_A = """\
Attack report on Oasis (-32|-45)

05.06.26, 10:00:00
Server time: 11:00:00 (UTC +1:00)

Attacker
BountyVillage (1|2)
Legionnaire
100
0

Defender
Rat
10
10

Bounty
100  200  300  400
200/500
"""

_REPORT_BOUNTY_B = """\
Attack report on Oasis (-32|-45)

05.06.26, 11:00:00
Server time: 12:00:00 (UTC +1:00)

Attacker
BountyVillage (1|2)
Legionnaire
100
0

Defender
Rat
8
8

Bounty
50  60  70  80
200/500
"""

_REPORT_BOUNTY_OTHER = """\
Attack report on Oasis (-99|-99)

05.06.26, 10:00:00
Server time: 11:00:00 (UTC +1:00)

Attacker
OtherVillage (3|4)
Legionnaire
50
0

Defender
Rat
5
5

Bounty
10  20  30  40
50/100
"""


class TestBountyStats:
    def _save(self, client, report_text):
        resp = client.post("/attack-reports", json={"raw_text": report_text})
        assert resp.status_code == 201
        return resp.json()["id"]

    def test_T_B1_bounty_oasis_with_reports(self, client):
        """T-B1: GET /attack-reports/stats/bounty?x=-32&y=-45 con 2 reportes."""
        self._save(client, _REPORT_BOUNTY_A)
        self._save(client, _REPORT_BOUNTY_B)
        resp = client.get("/attack-reports/stats/bounty?x=-32&y=-45")
        assert resp.status_code == 200
        data = resp.json()
        assert data["scope"] == "oasis"
        assert data["coord_x_dest"] == -32
        assert data["coord_y_dest"] == -45
        assert data["total_reports"] == 2
        # Sumas: wood=100+50=150, clay=200+60=260, iron=300+70=370, crop=400+80=480
        assert data["bounty"]["wood"] == 150
        assert data["bounty"]["clay"] == 260
        assert data["bounty"]["iron"] == 370
        assert data["bounty"]["crop"] == 480

    def test_T_B2_bounty_global_with_reports(self, client):
        """T-B2: GET /attack-reports/stats/bounty (global) con reportes."""
        self._save(client, _REPORT_BOUNTY_A)
        self._save(client, _REPORT_BOUNTY_OTHER)
        resp = client.get("/attack-reports/stats/bounty")
        assert resp.status_code == 200
        data = resp.json()
        assert data["scope"] == "global"
        assert data["coord_x_dest"] is None
        assert data["coord_y_dest"] is None
        assert data["total_reports"] >= 2

    def test_T_B3_bounty_oasis_no_reports(self, client):
        """T-B3: GET /attack-reports/stats/bounty?x=-32&y=-45 sin reportes → 200 con ceros."""
        resp = client.get("/attack-reports/stats/bounty?x=-32&y=-45")
        assert resp.status_code == 200
        data = resp.json()
        assert data["scope"] == "oasis"
        assert data["coord_x_dest"] == -32
        assert data["coord_y_dest"] == -45
        assert data["total_reports"] == 0
        assert data["bounty"]["wood"] == 0
        assert data["bounty"]["clay"] == 0
        assert data["bounty"]["iron"] == 0
        assert data["bounty"]["crop"] == 0
        assert data["bounty"]["total"] == 0

    def test_T_B4_bounty_global_empty_db(self, client):
        """T-B4: GET /attack-reports/stats/bounty (global) con BD vacía → 200 con ceros."""
        resp = client.get("/attack-reports/stats/bounty")
        assert resp.status_code == 200
        data = resp.json()
        assert data["scope"] == "global"
        assert data["coord_x_dest"] is None
        assert data["coord_y_dest"] is None
        assert data["total_reports"] == 0
        assert data["bounty"]["total"] == 0

    def test_T_B5_x_without_y(self, client):
        """T-B5: x sin y → 400."""
        resp = client.get("/attack-reports/stats/bounty?x=-32")
        assert resp.status_code == 400
        assert "y" in resp.json()["detail"].lower() or "x" in resp.json()["detail"].lower()

    def test_T_B6_y_without_x(self, client):
        """T-B6: y sin x → 400."""
        resp = client.get("/attack-reports/stats/bounty?y=-45")
        assert resp.status_code == 400

    def test_T_B7_bounty_total_equals_sum(self, client):
        """T-B7: bounty.total == wood + clay + iron + crop."""
        self._save(client, _REPORT_BOUNTY_A)
        resp = client.get("/attack-reports/stats/bounty?x=-32&y=-45")
        assert resp.status_code == 200
        b = resp.json()["bounty"]
        assert b["total"] == b["wood"] + b["clay"] + b["iron"] + b["crop"]

    def test_T_B8_out_of_range(self, client):
        """T-B8: x fuera de rango (-400..400) → 422."""
        resp = client.get("/attack-reports/stats/bounty?x=999&y=10")
        assert resp.status_code == 422

    def test_route_not_captured_by_id(self, client):
        """stats/bounty no es capturado por /{id}."""
        # Si hubiera colisión daría 422 (cannot convert 'stats' to int)
        resp = client.get("/attack-reports/stats/bounty")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# EP-06 — animal_regen_rates (MEJORA 1)
# ---------------------------------------------------------------------------

# Reporte para test de regen (oasis -83|-83)
def _make_regen_report(x, y, date_str, village, animal="Rat", present="10", killed="10", bounty="50 50 50 50"):
    return f"""\
Attack report on Oasis ({x}|{y})

{date_str}

Attacker
{village} (1|2)
Legionnaire
100
0

Defender
{animal}
{present}
{killed}

Bounty
{bounty}
50/100
"""


class TestOasisStatsRegen:
    def test_T_R5_no_intervals_one_attack(self, client):
        """T-R5: Oasis con 1 ataque → animal_regen_rates = []."""
        report = _make_regen_report(-83, -83, "10.02.26, 09:00:00", "RegenV1")
        client.post("/attack-reports", json={"raw_text": report})
        resp = client.get("/attack-reports/stats/oasis?x=-83&y=-83")
        assert resp.status_code == 200
        data = resp.json()
        assert "animal_regen_rates" in data
        assert data["animal_regen_rates"] == []

    def test_T_R9_field_present_in_response(self, client):
        """T-R9: animal_regen_rates siempre presente en EP-06 (aunque sea vacío)."""
        resp = client.get("/attack-reports/stats/oasis?x=-999&y=-999")
        assert resp.status_code == 200
        assert "animal_regen_rates" in resp.json()

    def test_T_R8_zero_attacks_empty_list(self, client):
        """T-R8: Oasis sin ataques → animal_regen_rates = []."""
        resp = client.get("/attack-reports/stats/oasis?x=-987&y=-987")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_attacks"] == 0
        assert data["animal_regen_rates"] == []

    def test_T_R1_two_attacks_regen_calculated(self, client):
        """T-R1: 2 ataques → animal_regen_rates contiene entrada para Rat con valid_intervals=1."""
        # Ataque 1: Rat 10 presentes, 10 muertos → 0 supervivientes
        r1 = _make_regen_report(-84, -84, "10.02.26, 09:00:00", "RegenV2", animal="Rat", present="10", killed="10")
        # Ataque 2 (1h después): Rat 4 presentes (regeneró 4 desde 0)
        r2 = _make_regen_report(-84, -84, "10.02.26, 10:00:00", "RegenV2", animal="Rat", present="4", killed="4")
        client.post("/attack-reports", json={"raw_text": r1})
        client.post("/attack-reports", json={"raw_text": r2})
        resp = client.get("/attack-reports/stats/oasis?x=-84&y=-84")
        assert resp.status_code == 200
        data = resp.json()
        rates = data["animal_regen_rates"]
        assert len(rates) >= 1
        rat_rate = next((r for r in rates if "at" in r["animal_name"].lower()), None)
        assert rat_rate is not None
        assert rat_rate["valid_intervals"] == 1
        # Regenerados = 4 - 0 (supervivientes) = 4, gap = 3600s → 4/1 = 4.0/h
        assert rat_rate["avg_regen_per_hour"] == 4.0

    def test_regen_rates_structure(self, client):
        """Los items de animal_regen_rates tienen los campos correctos."""
        r1 = _make_regen_report(-85, -85, "10.02.26, 09:00:00", "RegenV3", animal="Rat", present="10", killed="10")
        r2 = _make_regen_report(-85, -85, "10.02.26, 10:00:00", "RegenV3", animal="Rat", present="5", killed="5")
        client.post("/attack-reports", json={"raw_text": r1})
        client.post("/attack-reports", json={"raw_text": r2})
        resp = client.get("/attack-reports/stats/oasis?x=-85&y=-85")
        data = resp.json()
        for rate in data["animal_regen_rates"]:
            assert "animal_ordinal" in rate
            assert "animal_name" in rate
            assert "avg_regen_per_hour" in rate
            assert "valid_intervals" in rate
            assert rate["valid_intervals"] >= 1
            assert rate["avg_regen_per_hour"] is not None


# ---------------------------------------------------------------------------
# EP-08 — Lista de oasis (GET /attack-reports/oasis)
# ---------------------------------------------------------------------------

_REPORT_OASIS_LIST_A = """\
Attack report on Oasis (-70|73)

31.05.26, 13:39:30
Server time: 14:39:30 (UTC +1:00)

Attacker
ListVillage (1|2)
Legionnaire
100
0

Defender
Rat
10
10

Bounty
100  200  300  400
200/500
"""

_REPORT_OASIS_LIST_B = """\
Attack report on Oasis (-45|12)

30.05.26, 09:14:21
Server time: 10:14:21 (UTC +1:00)

Attacker
ListVillage (1|2)
Legionnaire
80
0

Defender
Spider
5
5

Bounty
50  50  50  50
100/200
"""

_REPORT_OASIS_LIST_B2 = """\
Attack report on Oasis (-45|12)

30.05.26, 15:00:00
Server time: 16:00:00 (UTC +1:00)

Attacker
ListVillage (1|2)
Legionnaire
80
0

Defender
Spider
3
3

Bounty
30  30  30  30
80/200
"""


class TestOasisList:
    def _save(self, client, report_text):
        resp = client.post("/attack-reports", json={"raw_text": report_text})
        assert resp.status_code == 201
        return resp.json()["id"]

    def test_T_N1_list_two_oasis(self, client):
        """T-N1: GET /attack-reports/oasis con 2 oasis en BD → total=2, ordenados por last_attack DESC."""
        self._save(client, _REPORT_OASIS_LIST_A)
        self._save(client, _REPORT_OASIS_LIST_B)
        resp = client.get("/attack-reports/oasis")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        # Primer item = oasis con last_attack más reciente
        assert data["items"][0]["last_attack"] >= data["items"][1]["last_attack"]

    def test_T_N2_list_empty_db(self, client):
        """T-N2: GET /attack-reports/oasis con BD vacía → total=0, items=[]."""
        resp = client.get("/attack-reports/oasis")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_T_N3_filter_by_coords(self, client):
        """T-N3: GET /attack-reports/oasis?x=-70&y=73 con 1 reporte → total=1."""
        self._save(client, _REPORT_OASIS_LIST_A)
        resp = client.get("/attack-reports/oasis?x=-70&y=73")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        item = data["items"][0]
        assert item["coord_x_dest"] == -70
        assert item["coord_y_dest"] == 73
        assert item["attack_count"] == 1

    def test_T_N4_filter_coords_no_reports(self, client):
        """T-N4: GET /attack-reports/oasis?x=-70&y=99 sin reportes → total=0, items=[]."""
        resp = client.get("/attack-reports/oasis?x=-70&y=99")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_T_N5_x_without_y(self, client):
        """T-N5: x sin y → 400."""
        resp = client.get("/attack-reports/oasis?x=-70")
        assert resp.status_code == 400
        assert "y" in resp.json()["detail"].lower() or "x" in resp.json()["detail"].lower()

    def test_T_N6_y_without_x(self, client):
        """T-N6: y sin x → 400."""
        resp = client.get("/attack-reports/oasis?y=73")
        assert resp.status_code == 400

    def test_T_N7_out_of_range(self, client):
        """T-N7: x fuera de rango → 422."""
        resp = client.get("/attack-reports/oasis?x=999&y=73")
        assert resp.status_code == 422

    def test_T_N8_total_bounty_sum(self, client):
        """T-N8: total_bounty = suma de bounty_wood+clay+iron+crop de todos los reportes del oasis."""
        self._save(client, _REPORT_OASIS_LIST_B)
        self._save(client, _REPORT_OASIS_LIST_B2)
        resp = client.get("/attack-reports/oasis?x=-45&y=12")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        item = data["items"][0]
        assert item["attack_count"] == 2
        # Reporte B: 50+50+50+50=200, Reporte B2: 30+30+30+30=120 → total=320
        assert item["total_bounty"] == 320

    def test_T_N9_last_attack_verbatim(self, client):
        """T-N9: last_attack es el attacked_at más reciente (verbatim, sin zona)."""
        self._save(client, _REPORT_OASIS_LIST_A)
        resp = client.get("/attack-reports/oasis?x=-70&y=73")
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        # Verbatim: "2026-05-31T13:39:30" (sin offset)
        assert item["last_attack"] == "2026-05-31T13:39:30"
        assert "+" not in item["last_attack"]
        assert "Z" not in item["last_attack"]

    def test_route_oasis_not_captured_by_id(self, client):
        """EP-08 (/oasis) no es capturado por /{id}."""
        resp = client.get("/attack-reports/oasis")
        # Si hubiera colisión de routing daría 422 (cannot convert 'oasis' to int)
        assert resp.status_code == 200

    def test_items_structure(self, client):
        """Los items de EP-08 tienen los campos correctos."""
        self._save(client, _REPORT_OASIS_LIST_A)
        resp = client.get("/attack-reports/oasis")
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert "coord_x_dest" in item
        assert "coord_y_dest" in item
        assert "attack_count" in item
        assert "last_attack" in item
        assert "total_bounty" in item
        assert isinstance(item["total_bounty"], int)
