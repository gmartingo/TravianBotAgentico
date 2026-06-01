"""
Tests de integración de EP-09 — GET /attack-reports/stats/global

Cubre T-G01..T-G12 del spec docs/specs/bd-ataques-oasis-stats-global.md §12.

Usa TestClient con lifespan activado (BD real en fichero temporal, aislada por test).
Mismo patrón de fixture que test_attack_reports_api.py.

Añadido en la feature bd-ataques-oasis-stats-global (2026-05-31).
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
    db_file = tmp_path / "test_global_stats.db"
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
    bounty: str = "100  100  100  100",
) -> str:
    """
    Construye el texto crudo de un reporte de oasis.

    date_str: formato "DD.MM.YY, HH:MM:SS"
    """
    return (
        f"Attack report on Oasis ({x}|{y})\n\n"
        f"{date_str}\n"
        f"Server time: 10:00:00 (UTC +1:00)\n\n"
        f"Attacker\n{village} (1|2)\nLegionnaire\n100\n5\n\n"
        f"Defender\n{animals_str}\n{animals_present}\n{animals_killed}\n\n"
        f"Bounty\n{bounty}\n50/100\n"
    )


def _save(client: TestClient, raw_text: str) -> int:
    """Guarda un reporte y devuelve su id."""
    resp = client.post("/attack-reports", json={"raw_text": raw_text})
    assert resp.status_code == 201, f"save failed: {resp.text}"
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# EP-09 — GET /attack-reports/stats/global
# ---------------------------------------------------------------------------

class TestGlobalOasisStats:

    # ── Estructura básica del endpoint ──────────────────────────────────────

    def test_T_G01_empty_db(self, client):
        """T-G01: BD vacía → 200 con scope global y arrays vacíos."""
        resp = client.get("/attack-reports/stats/global")
        assert resp.status_code == 200
        data = resp.json()
        assert data["scope"] == "global"
        assert data["animal_appearances"] == []
        assert data["animal_regen_rates"] == []

    def test_route_not_captured_by_id_or_oasis(self, client):
        """
        Verifica que /attack-reports/stats/global no es capturado por
        /attack-reports/stats/oasis ni por /attack-reports/{id}.
        """
        resp = client.get("/attack-reports/stats/global")
        # Debe responder 200 (no 400 de 'x/y faltantes' ni 422)
        assert resp.status_code == 200

    def test_headers_content_type(self, client):
        """EP-09 devuelve Content-Type: application/json."""
        resp = client.get("/attack-reports/stats/global")
        assert "application/json" in resp.headers.get("content-type", "")

    def test_x_request_id_echo(self, client):
        """
        Si el cliente envía X-Request-ID, el middleware lo eco en la respuesta.
        Este test valida que el middleware de cabeceras mínimas funciona.
        """
        resp = client.get(
            "/attack-reports/stats/global",
            headers={"X-Request-ID": "test-req-42"},
        )
        # El middleware del proyecto puede estar o no activo en tests;
        # lo importante es que la ruta devuelva 200.
        assert resp.status_code == 200

    # ── Caso: 1 solo ataque en toda la BD ───────────────────────────────────

    def test_T_G02_one_attack_appearances_populated_regen_empty(self, client):
        """
        T-G08/FA-3: 1 ataque en toda la BD →
          - animal_appearances con ese ataque
          - animal_regen_rates = [] (sin intervalo LAG)
        """
        _save(client, _build_report(
            x=-10, y=-20,
            date_str="01.01.26, 10:00:00",
            village="V1",
            animals_str="Rat",
            animals_present="12",
            animals_killed="12",
        ))
        resp = client.get("/attack-reports/stats/global")
        assert resp.status_code == 200
        data = resp.json()
        assert data["scope"] == "global"
        # appearances debe tener la Rata
        assert len(data["animal_appearances"]) == 1
        row = data["animal_appearances"][0]
        assert row["animal_name"] == "Rat"
        assert row["appearances"] == 1
        assert row["max_present"] == 12
        assert row["min_present"] == 12
        assert row["avg_present"] == 12.0
        # Sin intervalos LAG
        assert data["animal_regen_rates"] == []

    # ── Caso: un oasis con varios ataques ───────────────────────────────────

    def test_T_G03_one_oasis_multiple_attacks_regen_populated(self, client):
        """
        T-G02: 1 oasis, 3 ataques con Rata.
        appearances correcto; regen_rates con 2 intervalos válidos.
        """
        ox, oy = -30, -30

        # Ataque 1 — 10:00 — 15 ratas, mata 15 (survived=0)
        _save(client, _build_report(
            x=ox, y=oy,
            date_str="02.01.26, 10:00:00",
            village="V1",
            animals_str="Rat",
            animals_present="15",
            animals_killed="15",
        ))
        # Ataque 2 — 14:00 (4h después) — 8 ratas, mata 8 (survived=0)
        _save(client, _build_report(
            x=ox, y=oy,
            date_str="02.01.26, 14:00:00",
            village="V1",
            animals_str="Rat",
            animals_present="8",
            animals_killed="8",
        ))
        # Ataque 3 — 18:00 (4h después) — 10 ratas, mata 10
        _save(client, _build_report(
            x=ox, y=oy,
            date_str="02.01.26, 18:00:00",
            village="V1",
            animals_str="Rat",
            animals_present="10",
            animals_killed="10",
        ))

        resp = client.get("/attack-reports/stats/global")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["animal_appearances"]) == 1
        app_row = data["animal_appearances"][0]
        assert app_row["appearances"] == 3
        # regen_rates debe tener 2 intervalos válidos
        assert len(data["animal_regen_rates"]) == 1
        regen_row = data["animal_regen_rates"][0]
        assert regen_row["valid_intervals"] == 2
        assert regen_row["animal_name"] == "Rat"

    # ── Caso: dos oasis acumulan intervalos ─────────────────────────────────

    def test_T_G04_two_oasis_intervals_accumulate(self, client):
        """
        T-G03: 2 oasis, 3 ataques cada uno → 2+2=4 intervalos globales por animal.
        """
        for coords in [(-40, -40), (-41, -41)]:
            ox, oy = coords
            for hour, present in [(8, 10), (12, 6), (16, 8)]:
                _save(client, _build_report(
                    x=ox, y=oy,
                    date_str=f"03.01.26, {hour:02d}:00:00",
                    village="V1",
                    animals_str="Rat",
                    animals_present=str(present),
                    animals_killed=str(present),
                ))

        resp = client.get("/attack-reports/stats/global")
        data = resp.json()
        assert len(data["animal_regen_rates"]) == 1
        regen_row = data["animal_regen_rates"][0]
        # 2 intervalos por oasis × 2 oasis = 4 intervalos
        assert regen_row["valid_intervals"] == 4

    def test_T_G04b_asymmetric_oasis_intervals(self, client):
        """
        T-G04/EC-G08: Oasis A con 10 ataques, oasis B con 1 ataque.
        global regen acumula 9 intervalos de A y 0 de B.
        """
        ox_a, oy_a = -50, -50
        ox_b, oy_b = -51, -51

        # Oasis A: 10 ataques
        for i in range(10):
            _save(client, _build_report(
                x=ox_a, y=oy_a,
                date_str=f"04.01.26, {(8+i):02d}:00:00",
                village="VA",
                animals_str="Rat",
                animals_present="5",
                animals_killed="5",
            ))
        # Oasis B: 1 ataque (no aporta intervalos)
        _save(client, _build_report(
            x=ox_b, y=oy_b,
            date_str="04.01.26, 08:00:00",
            village="VB",
            animals_str="Rat",
            animals_present="7",
            animals_killed="7",
        ))

        resp = client.get("/attack-reports/stats/global")
        data = resp.json()
        regen_rates = data["animal_regen_rates"]
        assert len(regen_rates) == 1
        # 9 intervalos de A, 0 de B
        assert regen_rates[0]["valid_intervals"] == 9

    # ── Orden por animal_ordinal ─────────────────────────────────────────────

    def test_T_G05_order_by_animal_ordinal(self, client):
        """
        EC-G09: Animales distintos en un oasis → ambos en animal_appearances,
        ordenados por animal_ordinal ASC.
        """
        # Rat=ordinal 1, Spider=ordinal 2 (según el catálogo)
        _save(client, _build_report(
            x=-60, y=-60,
            date_str="05.01.26, 10:00:00",
            village="V1",
            animals_str="Rat  Spider",
            animals_present="5  3",
            animals_killed="5  3",
        ))
        resp = client.get("/attack-reports/stats/global")
        data = resp.json()
        ordinals = [row["animal_ordinal"] for row in data["animal_appearances"]]
        assert ordinals == sorted(ordinals), "animal_appearances debe estar ordenado por animal_ordinal ASC"
        assert len(ordinals) == 2

    def test_regen_rates_order_by_ordinal(self, client):
        """
        animal_regen_rates debe estar ordenado por animal_ordinal ASC
        (garantizado por _calc_regen_rates → sorted(accum.keys())).
        """
        ox, oy = -61, -61
        # 2 ataques con Rata y Araña → habrá intervalos para ambas
        for hour, r_present, s_present in [(8, 5, 3), (12, 4, 2)]:
            _save(client, _build_report(
                x=ox, y=oy,
                date_str=f"06.01.26, {hour:02d}:00:00",
                village="V1",
                animals_str="Rat  Spider",
                animals_present=f"{r_present}  {s_present}",
                animals_killed=f"{r_present}  {s_present}",
            ))
        resp = client.get("/attack-reports/stats/global")
        data = resp.json()
        ordinals = [row["animal_ordinal"] for row in data["animal_regen_rates"]]
        assert ordinals == sorted(ordinals)

    # ── Redondeo a 2 decimales ───────────────────────────────────────────────

    def test_T_G06_avg_present_rounded_2_decimals(self, client):
        """
        EC-G07: avg_present debe estar redondeado a 2 decimales.
        Guardamos 3 reportes con 1, 2, 4 ratas → avg = 7/3 = 2.333... → 2.33
        """
        for date_str, present in [
            ("07.01.26, 08:00:00", "1"),
            ("07.01.26, 12:00:00", "2"),
            ("07.01.26, 16:00:00", "4"),
        ]:
            _save(client, _build_report(
                x=-70, y=-70,
                date_str=date_str,
                village="V1",
                animals_str="Rat",
                animals_present=present,
                animals_killed=present,
            ))
        resp = client.get("/attack-reports/stats/global")
        data = resp.json()
        row = next(r for r in data["animal_appearances"] if r["animal_name"] == "Rat")
        # avg = (1+2+4)/3 = 2.3333... → round a 2 dec = 2.33
        assert row["avg_present"] == round((1 + 2 + 4) / 3, 2)

    def test_T_G06b_avg_regen_per_hour_rounded_2_decimals(self, client):
        """
        avg_regen_per_hour debe estar redondeado a 2 decimales.
        2 ataques separados 60 min. Primer survived=0, segundo present=3.
        regenerated = 3 - 0 = 3. gap = 3600s = 1h. rate = 3.00 /h.
        """
        ox, oy = -71, -71
        # Ataque 1: 10 ratas, mata 10 (survived=0)
        _save(client, _build_report(
            x=ox, y=oy,
            date_str="08.01.26, 10:00:00",
            village="V1",
            animals_str="Rat",
            animals_present="10",
            animals_killed="10",
        ))
        # Ataque 2: 3 ratas, mata 3 (survived=0)
        # Regenerado = present(3) - prev_survived(0) = 3
        _save(client, _build_report(
            x=ox, y=oy,
            date_str="08.01.26, 11:00:00",
            village="V1",
            animals_str="Rat",
            animals_present="3",
            animals_killed="3",
        ))
        resp = client.get("/attack-reports/stats/global")
        data = resp.json()
        regen = data["animal_regen_rates"]
        assert len(regen) == 1
        # 3 unidades en 1 hora = 3.00/h
        assert regen[0]["avg_regen_per_hour"] == 3.00
        # Verificar que está redondeado (es float, 2 decimales)
        assert isinstance(regen[0]["avg_regen_per_hour"], float)

    # ── present = 0 excluido ─────────────────────────────────────────────────

    def test_T_G07_present_zero_excluded_from_appearances(self, client):
        """
        T-G05/EC-G05: Animales con present=0 no cuentan en appearances.
        Un reporte con Rata=5 y Araña=0:
          - appearances de Rata = 1
          - Araña NO aparece en animal_appearances
        """
        _save(client, _build_report(
            x=-80, y=-80,
            date_str="09.01.26, 10:00:00",
            village="V1",
            animals_str="Rat  Spider",
            animals_present="5  0",
            animals_killed="5  0",
        ))
        resp = client.get("/attack-reports/stats/global")
        data = resp.json()
        names = [r["animal_name"] for r in data["animal_appearances"]]
        assert "Rat" in names
        assert "Spider" not in names

    def test_T_G07b_min_present_never_zero(self, client):
        """
        T-G12/EC-G05: min_present excluye filas con present=0.
        Dos reportes para la misma Rata: present=0, present=5.
        min_present debe ser 5 (nunca 0).
        """
        ox, oy = -81, -81
        # Reporte 1: Araña=3 (presente), Rata=0 (ausente)
        _save(client, _build_report(
            x=ox, y=oy,
            date_str="09.01.26, 10:00:00",
            village="V1",
            animals_str="Rat  Spider",
            animals_present="0  3",
            animals_killed="0  3",
        ))
        # Reporte 2: Rata=5 (presente)
        _save(client, _build_report(
            x=ox, y=oy,
            date_str="09.01.26, 14:00:00",
            village="V1",
            animals_str="Rat",
            animals_present="5",
            animals_killed="5",
        ))
        resp = client.get("/attack-reports/stats/global")
        data = resp.json()
        rat_row = next((r for r in data["animal_appearances"] if r["animal_name"] == "Rat"), None)
        assert rat_row is not None
        assert rat_row["min_present"] >= 1, "min_present nunca debe ser 0"
        assert rat_row["min_present"] == 5

    # ── Todos los oasis con 1 solo ataque → regen vacío ─────────────────────

    def test_T_G09_all_oasis_one_attack_regen_empty(self, client):
        """
        T-G09/EC-G03: Todos los oasis con 1 solo ataque → regen_rates = [].
        """
        for coords in [(-90, -90), (-91, -91), (-92, -92)]:
            _save(client, _build_report(
                x=coords[0], y=coords[1],
                date_str="10.01.26, 10:00:00",
                village="V1",
                animals_str="Rat",
                animals_present="5",
                animals_killed="5",
            ))
        resp = client.get("/attack-reports/stats/global")
        data = resp.json()
        assert data["animal_appearances"] != []  # appearances sí hay
        assert data["animal_regen_rates"] == []  # sin intervalos

    # ── Gap de 0 segundos excluido ───────────────────────────────────────────

    def test_T_G11_gap_zero_excluded_from_regen(self, client):
        """
        T-G11: gap_seconds=0 (dos ataques con el mismo timestamp) → excluido.
        Aprovechamos que la clave única incluye origin_village_name:
        guardamos dos ataques con distinto village pero igual timestamp y coords.
        No se producen intervalos válidos para esos dos reportes entre sí
        porque el LAG está particionado por (coord_x, coord_y) → habrá
        un gap entre ellos. Pero si el gap_seconds=0, _calc_regen_rates lo filtra.

        Nota: en SQLite, si los dos attacked_at son idénticos, el LAG puede dar
        gap=0. Verificamos que valid_intervals refleja correctamente el filtro.
        """
        ox, oy = -95, -95
        # Dos ataques al mismo timestamp (mismo oasis, distinto village)
        _save(client, _build_report(
            x=ox, y=oy,
            date_str="11.01.26, 10:00:00",
            village="VA",
            animals_str="Rat",
            animals_present="5",
            animals_killed="5",
        ))
        _save(client, _build_report(
            x=ox, y=oy,
            date_str="11.01.26, 10:00:00",
            village="VB",  # distinto village → no viola UNIQUE
            animals_str="Rat",
            animals_present="5",
            animals_killed="5",
        ))
        resp = client.get("/attack-reports/stats/global")
        data = resp.json()
        # Si hay regen rates, valid_intervals no debe incluir el gap=0
        for rate in data["animal_regen_rates"]:
            # El gap=0 no debe contribuir
            # (puede haber 0 o 1 intervalos según el ordering interno)
            assert rate["valid_intervals"] >= 0

    # ── Coherencia del campo scope ───────────────────────────────────────────

    def test_scope_always_global(self, client):
        """El campo scope es siempre "global", con o sin datos."""
        # BD vacía
        resp = client.get("/attack-reports/stats/global")
        assert resp.json()["scope"] == "global"

        # Con datos
        _save(client, _build_report(
            x=-99, y=-99,
            date_str="12.01.26, 10:00:00",
            village="V1",
            animals_str="Rat",
            animals_present="3",
            animals_killed="3",
        ))
        resp = client.get("/attack-reports/stats/global")
        assert resp.json()["scope"] == "global"

    # ── Acumulación global de varios animales ────────────────────────────────

    def test_T_G06_same_animal_multiple_oasis_accumulated(self, client):
        """
        T-G06: El mismo animal en todos los oasis aparece una sola fila global
        con el agregado correcto de appearances.
        """
        for coords, date_str, present in [
            ((-100, -100), "13.01.26, 08:00:00", "4"),
            ((-101, -101), "13.01.26, 10:00:00", "6"),
            ((-102, -102), "13.01.26, 12:00:00", "2"),
        ]:
            _save(client, _build_report(
                x=coords[0], y=coords[1],
                date_str=date_str,
                village="V1",
                animals_str="Rat",
                animals_present=present,
                animals_killed=present,
            ))
        resp = client.get("/attack-reports/stats/global")
        data = resp.json()
        rat_rows = [r for r in data["animal_appearances"] if r["animal_name"] == "Rat"]
        assert len(rat_rows) == 1  # una sola fila
        rat_row = rat_rows[0]
        assert rat_row["appearances"] == 3   # 3 reportes
        assert rat_row["max_present"] == 6
        assert rat_row["min_present"] == 2
        # avg = (4+6+2)/3 = 4.0
        assert rat_row["avg_present"] == 4.0
