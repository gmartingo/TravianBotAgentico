"""
Tests de integración de EP-TD — GET /attack-reports/stats/oasis/temporal-distribution

Cubre los casos T-TD01..T-TD27 del spec
docs/specs/bd-ataques-oasis-temporal-distribution.md §12 (v2).

Spec v2: interval_minutes sustituye a bucket_hours. Binning por umbral inferior
(Opción B). Respuesta de UNA sola frecuencia (no matriz).

Usa TestClient con lifespan activado (BD real en fichero temporal, aislada por test).
Mismo patrón de fixture que test_oasis_spawn_composition_api.py.

Actualizado en la feature bd-ataques-oasis-temporal-distribution v2 (2026-06-02).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from adapters.api.main import app

_EP = "/attack-reports/stats/oasis/temporal-distribution"
_LANG_ES = "es"
_LANG_EN = "en"
_LANG_IT = "it"


# ---------------------------------------------------------------------------
# Fixture — cliente con BD temporal aislada por test
# ---------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch, tmp_path):
    """
    Cliente con la app real apuntando a una BD temporal por test.
    Monkeypatcha DB_PATH antes del lifespan para garantizar BD limpia.
    """
    db_file = tmp_path / "test_temporal_dist_v2.db"
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
    animals: list[tuple[str, int | None, int | None]],
    village: str = "TestVillage",
    utc_offset: str = "+01:00",
    bounty: str = "100  100  100  100",
    defeat: bool = False,
) -> str:
    """
    Construye el texto crudo de un reporte de oasis.

    date_str: formato "DD.MM.YY, HH:MM:SS"
    animals: lista de (nombre_en_inglés, present, killed).
             defeat=True → usa "?" en lugar de valores numéricos.
    """
    server_hour = date_str.split(", ")[1]
    if defeat:
        names_row   = "\t".join(a[0] for a in animals)
        present_row = "\t".join("?" for _ in animals)
        killed_row  = "\t".join("?" for _ in animals)
        return (
            f"Attack report on Oasis ({x}|{y})\n\n"
            f"{date_str}\n"
            f"Server time: {server_hour} (UTC {utc_offset})\n\n"
            f"Attacker\n{village} (1|2)\nLegionnaire\n100\n100\n\n"
            f"Defender\n{names_row}\n{present_row}\n{killed_row}\n\n"
            f"Bounty\n0  0  0  0\n0/100\n"
        )
    else:
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


def _get_td(
    client: TestClient,
    interval_minutes: int = 240,
    lang: str = _LANG_ES,
) -> dict:
    """Llama a EP-TD y devuelve el JSON de la respuesta 200."""
    resp = client.get(
        _EP,
        params={"interval_minutes": interval_minutes},
        headers={"Accept-Language": lang},
    )
    assert resp.status_code == 200, f"EP-TD failed ({resp.status_code}): {resp.text}"
    return resp.json()


def _find_animal(data: dict, ordinal: int) -> dict | None:
    """Busca un animal por ordinal en animals[]."""
    for a in data["animals"]:
        if a["animal_ordinal"] == ordinal:
            return a
    return None


# ---------------------------------------------------------------------------
# T-TD01 — Camino feliz: interval_minutes=240, lang=es
# ---------------------------------------------------------------------------

def test_TD01_happy_path_240_es(client):
    """T-TD01: interval_minutes=240, lang=es, BD con gaps en [14400, 18000).
    200, interval_minutes=240, interval_label='4h', window correcta,
    n_reports_in_window>0, animales ordenados por animal_ordinal ASC.
    """
    # Dos reportes al mismo oasis con gap de 4h (14400s) — cae en [14400, 18000)
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 3, 3)]))
    _save(client, _make_report(-70, 73, "01.06.26, 14:00:00", [("Rat", 5, 5)]))

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)

    assert data["interval_minutes"] == 240
    assert data["interval_label"] == "4h"
    assert data["window"]["lower_min"] == 240
    assert data["window"]["upper_min"] == 300
    assert data["window"]["is_open"] is False
    assert data["n_reports_in_window"] >= 1
    assert isinstance(data["animals"], list)
    assert len(data["animals"]) >= 1

    # Animales ordenados por ordinal ASC
    ordinals = [a["animal_ordinal"] for a in data["animals"]]
    assert ordinals == sorted(ordinals)

    # Rat (ord 1) debe aparecer con icon_url correcto
    rat = _find_animal(data, 1)
    assert rat is not None
    assert rat["icon_url"] == "/static/icons/nature_1.png"


# ---------------------------------------------------------------------------
# T-TD02 — interval_minutes=60, lang=en
# ---------------------------------------------------------------------------

def test_TD02_60_en(client):
    """T-TD02: interval_minutes=60, lang=en. 200, interval_label='1h', window={60,120}."""
    # Gap de 1.5h (5400s) — cae en [3600, 7200) = bin 60
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 3, 3)]))
    _save(client, _make_report(-70, 73, "01.06.26, 11:30:00", [("Rat", 2, 2)]))

    data = _get_td(client, interval_minutes=60, lang=_LANG_EN)

    assert data["interval_minutes"] == 60
    assert data["interval_label"] == "1h"
    assert data["window"]["lower_min"] == 60
    assert data["window"]["upper_min"] == 120
    assert data["window"]["is_open"] is False
    assert data["n_reports_in_window"] >= 1


# ---------------------------------------------------------------------------
# T-TD03 — interval_minutes=300, bin abierto
# ---------------------------------------------------------------------------

def test_TD03_300_open_bin(client):
    """T-TD03: interval_minutes=300 → interval_label='5h+', window.is_open=true,
    window.upper_min=null."""
    # Gap de 6h (21600s) — cae en [18000, ∞) = bin 300
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 3, 3)]))
    _save(client, _make_report(-70, 73, "01.06.26, 16:00:00", [("Rat", 5, 5)]))

    data = _get_td(client, interval_minutes=300, lang=_LANG_ES)

    assert data["interval_minutes"] == 300
    assert data["interval_label"] == "5h+"
    assert data["window"]["lower_min"] == 300
    assert data["window"]["upper_min"] is None
    assert data["window"]["is_open"] is True
    assert data["n_reports_in_window"] >= 1


# ---------------------------------------------------------------------------
# T-TD04 — Derrotas: n_total > n_valid, avg_present=null si todos son derrota
# ---------------------------------------------------------------------------

def test_TD04_defeat_n_total_gt_n_valid(client):
    """T-TD04: reporte de derrota (present=null) en la ventana.
    n_total > n_valid. Si todos son derrota: avg_present=null, mode_present=[].
    """
    # Primer ataque (gap NULL — descartado)
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Wolf", 3, 3)]))
    # Segundo ataque: derrota → Wolf.present = NULL
    # Gap = 4h (14400s) → bin 240 [14400, 18000)
    defeat_text = (
        "Attack report on Oasis (-70|73)\n\n"
        "01.06.26, 14:00:00\n"
        "Server time: 14:00:00 (UTC +01:00)\n\n"
        "Attacker\nTestVillage (1|2)\nLegionnaire\n100\n100\n\n"
        "Defender\nWolf\n?\n?\n\n"
        "Bounty\n0  0  0  0\n0/100\n"
    )
    _save(client, defeat_text)

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)

    wolf = _find_animal(data, 6)
    assert wolf is not None
    assert wolf["n_total"] == 1    # el reporte ocurrió
    assert wolf["n_valid"] == 0    # present=NULL → excluido
    assert wolf["avg_present"] is None
    assert wolf["mode_present"] == []


# ---------------------------------------------------------------------------
# T-TD05 — Empate en moda: mode_present=[2,3]
# ---------------------------------------------------------------------------

def test_TD05_mode_tie(client):
    """T-TD05: empate en moda (present=[2,2,3,3]) → mode_present=[2,3] ordenado ASC."""
    # 5 reportes: el primero genera gap NULL; los 4 siguientes con gaps de ~4h
    dates = [
        "01.06.26, 10:00:00",   # gap NULL (primer ataque)
        "01.06.26, 14:00:00",   # gap 4h → bin 240
        "01.06.26, 18:00:00",   # gap 4h → bin 240
        "01.06.26, 22:00:00",   # gap 4h → bin 240
        "02.06.26, 02:00:00",   # gap 4h → bin 240
    ]
    presents = [5, 2, 3, 2, 3]
    for d, p in zip(dates, presents):
        _save(client, _make_report(-70, 73, d, [("Rat", p, p)]))

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    rat = _find_animal(data, 1)
    assert rat is not None
    # present=[2,3,2,3] → Counter({2:2, 3:2}) → mode=[2,3] ordenado ASC
    assert rat["mode_present"] == [2, 3]


# ---------------------------------------------------------------------------
# T-TD06 — Moda con valor único
# ---------------------------------------------------------------------------

def test_TD06_mode_single_value(client):
    """T-TD06: animal con un único valor de present → mode_present=[valor]."""
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 5, 5)]))
    _save(client, _make_report(-70, 73, "01.06.26, 14:00:00", [("Rat", 5, 5)]))
    _save(client, _make_report(-70, 73, "01.06.26, 18:00:00", [("Rat", 5, 5)]))

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    rat = _find_animal(data, 1)
    assert rat is not None
    assert rat["mode_present"] == [5]
    assert rat["avg_present"] == 5.0


# ---------------------------------------------------------------------------
# T-TD07 — BD vacía
# ---------------------------------------------------------------------------

def test_TD07_empty_db(client):
    """T-TD07: BD vacía → 200 con n_reports_in_window=0, animals: []."""
    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    assert data["interval_minutes"] == 240
    assert data["n_reports_in_window"] == 0
    assert data["animals"] == []


# ---------------------------------------------------------------------------
# T-TD08 — Un solo reporte por oasis (no puede generar gap)
# ---------------------------------------------------------------------------

def test_TD08_single_report_per_oasis_no_gaps(client):
    """T-TD08: BD con exactamente 1 reporte por oasis → 200, n_reports_in_window=0, animals:[]."""
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 3, 3)]))
    _save(client, _make_report(12, -45, "01.06.26, 10:00:00", [("Wolf", 5, 5)]))

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    assert data["n_reports_in_window"] == 0
    assert data["animals"] == []


# ---------------------------------------------------------------------------
# T-TD09 — Localización italiana
# ---------------------------------------------------------------------------

def test_TD09_lang_it(client):
    """T-TD09: lang=it → nombres de animales en italiano."""
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Wolf", 3, 3)]))
    _save(client, _make_report(-70, 73, "01.06.26, 14:00:00", [("Wolf", 5, 5)]))

    data_it = _get_td(client, interval_minutes=240, lang=_LANG_IT)
    data_es = _get_td(client, interval_minutes=240, lang=_LANG_ES)

    wolf_it = _find_animal(data_it, 6)
    wolf_es = _find_animal(data_es, 6)
    assert wolf_it is not None
    assert wolf_es is not None
    # Ambos deben tener nombres (localizados)
    assert isinstance(wolf_it["animal_name"], str) and len(wolf_it["animal_name"]) > 0
    assert isinstance(wolf_es["animal_name"], str) and len(wolf_es["animal_name"]) > 0
    # Los nombres deben ser distintos entre it y es
    assert wolf_it["animal_name"] != wolf_es["animal_name"]


# ---------------------------------------------------------------------------
# T-TD10 — Ordinal sin nombre en catálogo → fallback al nombre de BD
# ---------------------------------------------------------------------------

def test_TD10_fallback_to_db_name(client):
    """T-TD10: ordinal sin nombre en catálogo para el idioma → fallback a animal_name de BD."""
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 3, 3)]))
    _save(client, _make_report(-70, 73, "01.06.26, 14:00:00", [("Rat", 5, 5)]))

    # El catálogo tiene los 10 animales en los 25 idiomas soportados.
    # Verificamos que animal_name nunca está vacío (sea localizado o fallback de BD).
    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    rat = _find_animal(data, 1)
    assert rat is not None
    assert isinstance(rat["animal_name"], str)
    assert len(rat["animal_name"]) > 0


# ---------------------------------------------------------------------------
# T-TD11 — interval_minutes ausente → 200 con default 240
# ---------------------------------------------------------------------------

def test_TD11_default_interval_minutes(client):
    """T-TD11: interval_minutes ausente → 200 con interval_minutes=240 (default)."""
    resp = client.get(_EP, headers={"Accept-Language": _LANG_ES})
    assert resp.status_code == 200
    body = resp.json()
    assert body["interval_minutes"] == 240
    assert body["interval_label"] == "4h"


# ---------------------------------------------------------------------------
# T-TD12 — Frontera inclusiva inferior: gap=420s con interval_minutes=7
# ---------------------------------------------------------------------------

def test_TD12_boundary_inclusive_lower(client):
    """T-TD12: gap exactamente 7*60=420s con interval_minutes=7 → cuenta en bin 7 [420,600).
    Frontera inclusiva inferior.
    """
    # Dos reportes al mismo oasis con gap exactamente 420s
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 3, 3)]))
    _save(client, _make_report(-70, 73, "01.06.26, 10:07:00", [("Rat", 5, 5)]))

    # Con interval_minutes=7 → ventana [420s, 600s): el gap exacto de 420s debe contar
    data = _get_td(client, interval_minutes=7, lang=_LANG_ES)
    assert data["n_reports_in_window"] >= 1
    rat = _find_animal(data, 1)
    assert rat is not None
    assert rat["n_total"] >= 1

    # Con interval_minutes=6 → ventana [360s, 420s): 420s es exclusivo → NO debe contar
    data_6 = _get_td(client, interval_minutes=6, lang=_LANG_ES)
    assert data_6["n_reports_in_window"] == 0


# ---------------------------------------------------------------------------
# T-TD13 — Gap de 540s con interval_minutes=7: ruido dentro del bin, no salta al 10
# ---------------------------------------------------------------------------

def test_TD13_noise_stays_in_bin_7(client):
    """T-TD13: gap de 9*60=540s con interval_minutes=7 cae en [420,600) → cuenta en bin 7.
    No salta al bin 10. Robustez de Opción B.
    """
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 3, 3)]))
    _save(client, _make_report(-70, 73, "01.06.26, 10:09:00", [("Rat", 5, 5)]))
    # gap = 9*60 = 540s → bin 7 [420, 600)

    data_7 = _get_td(client, interval_minutes=7, lang=_LANG_ES)
    assert data_7["n_reports_in_window"] >= 1

    # No debe estar en bin 10 [600, 900)
    data_10 = _get_td(client, interval_minutes=10, lang=_LANG_ES)
    assert data_10["n_reports_in_window"] == 0


# ---------------------------------------------------------------------------
# T-TD14 — Frontera exclusiva superior: gap=600s con interval_minutes=7 cae en bin 10
# ---------------------------------------------------------------------------

def test_TD14_boundary_exclusive_upper(client):
    """T-TD14: gap de 10*60=600s con interval_minutes=7 → NO en bin 7, sí en bin 10.
    Frontera superior exclusiva: 600 >= upper_sec de bin 7 (600).
    """
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 3, 3)]))
    _save(client, _make_report(-70, 73, "01.06.26, 10:10:00", [("Rat", 5, 5)]))
    # gap = 10*60 = 600s

    # Bin 7 [420, 600): 600 NO pertenece (frontera exclusiva)
    data_7 = _get_td(client, interval_minutes=7, lang=_LANG_ES)
    assert data_7["n_reports_in_window"] == 0

    # Bin 10 [600, 900): 600 pertenece (frontera inclusiva inferior)
    data_10 = _get_td(client, interval_minutes=10, lang=_LANG_ES)
    assert data_10["n_reports_in_window"] >= 1


# ---------------------------------------------------------------------------
# T-TD15 — Gap de 300s (< 6 min) descartado
# ---------------------------------------------------------------------------

def test_TD15_gap_less_than_6min_discarded(client):
    """T-TD15: gap de 5*60=300s (< 6 min = < 360s) → descartado. Con interval_minutes=6
    (ventana [360, 420)) → n_reports_in_window=0.
    """
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 3, 3)]))
    _save(client, _make_report(-70, 73, "01.06.26, 10:05:00", [("Rat", 5, 5)]))
    # gap = 5*60 = 300s < 360s → descartado

    data = _get_td(client, interval_minutes=6, lang=_LANG_ES)
    assert data["n_reports_in_window"] == 0
    assert data["animals"] == []


# ---------------------------------------------------------------------------
# T-TD16 — Gap de 86400s (24h): no en bin 240, sí en bin 300
# ---------------------------------------------------------------------------

def test_TD16_gap_86400s_not_in_240_but_in_300(client):
    """T-TD16: gap de 86400s (24h). Ventana 240 = [14400,18000): 86400>=18000 → no cuenta.
    Ventana 300 = [18000,∞): 86400>=18000 → cuenta.
    """
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 3, 3)]))
    # Exactamente 24h después
    _save(client, _make_report(-70, 73, "02.06.26, 10:00:00", [("Rat", 5, 5)]))
    # gap = 86400s

    # Bin 240 [14400, 18000): 86400 >= 18000 → NO pertenece
    data_240 = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    assert data_240["n_reports_in_window"] == 0

    # Bin 300 [18000, ∞): 86400 >= 18000 → pertenece
    data_300 = _get_td(client, interval_minutes=300, lang=_LANG_ES)
    assert data_300["n_reports_in_window"] >= 1


# ---------------------------------------------------------------------------
# T-TD17 — Gap de 86400s con interval_minutes=300: cuenta en bin abierto
# ---------------------------------------------------------------------------

def test_TD17_gap_86400s_in_300_open_bin(client):
    """T-TD17: gap de 86400s (24h) con interval_minutes=300 → pertenece al bin abierto."""
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 3, 3)]))
    _save(client, _make_report(-70, 73, "02.06.26, 10:00:00", [("Rat", 5, 5)]))

    data = _get_td(client, interval_minutes=300, lang=_LANG_ES)
    assert data["window"]["is_open"] is True
    assert data["window"]["upper_min"] is None
    assert data["n_reports_in_window"] >= 1
    rat = _find_animal(data, 1)
    assert rat is not None


# ---------------------------------------------------------------------------
# T-TD18 — Gap exactamente en límite superior del bin: no pertenece
# ---------------------------------------------------------------------------

def test_TD18_boundary_upper_exclusive_exact(client):
    """T-TD18: gap exactamente upper_min*60 del bin → no pertenece a ese bin,
    pertenece al siguiente. Ejemplo: gap=600s (upper de bin 7) → no en 7, sí en 10.
    """
    # gap = 600s = 10*60 = lower de bin 10 (ya cubierto en T-TD14, aquí verificamos explícitamente
    # que upper_min*60 del bin 7 NO pertenece a ese bin)
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 3, 3)]))
    _save(client, _make_report(-70, 73, "01.06.26, 10:10:00", [("Rat", 5, 5)]))
    # gap = 600s = 10 min → upper_sec de bin 7 es 600s → no pertenece a bin 7

    data_7 = _get_td(client, interval_minutes=7, lang=_LANG_ES)
    assert data_7["n_reports_in_window"] == 0

    data_10 = _get_td(client, interval_minutes=10, lang=_LANG_ES)
    assert data_10["n_reports_in_window"] >= 1


# ---------------------------------------------------------------------------
# T-TD19 — Gap de 0s: descartado
# ---------------------------------------------------------------------------

def test_TD19_gap_zero_discarded(client):
    """T-TD19: gap de 0s (misma hora) → descartado. No aparece en ninguna ventana."""
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 3, 3)],
                               village="Village_A"))
    # Segundo reporte: misma hora, otra aldea → gap=0
    resp = client.post("/attack-reports", json={
        "raw_text": _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 5, 5)],
                                 village="Village_B"),
    })
    # Puede ser 201 (aldeas distintas) o 409; en cualquier caso gap=0 → descartado

    # Con 2 reportes al mismo segundo, el gap es 0 y se descarta
    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    assert data["n_reports_in_window"] == 0


# ---------------------------------------------------------------------------
# T-TD20 — interval_minutes=45 (fuera del set) → 400
# ---------------------------------------------------------------------------

def test_TD20_invalid_interval_minutes_45(client):
    """T-TD20: interval_minutes=45 (entero pero fuera del set) → 400, detail con 10 valores."""
    resp = client.get(
        _EP, params={"interval_minutes": 45}, headers={"Accept-Language": _LANG_ES}
    )
    assert resp.status_code == 400
    body = resp.json()
    assert "detail" in body
    detail = body["detail"]
    # El detail debe mencionar los 10 valores válidos
    for v in ("6", "7", "10", "15", "30", "60", "120", "180", "240", "300"):
        assert v in detail, f"Valor {v} no aparece en detail: {detail}"


# ---------------------------------------------------------------------------
# T-TD21 — interval_minutes=0 → 400
# ---------------------------------------------------------------------------

def test_TD21_invalid_interval_minutes_0(client):
    """T-TD21: interval_minutes=0 → 400."""
    resp = client.get(
        _EP, params={"interval_minutes": 0}, headers={"Accept-Language": _LANG_ES}
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# T-TD22 — interval_minutes=301 → 400
# ---------------------------------------------------------------------------

def test_TD22_invalid_interval_minutes_301(client):
    """T-TD22: interval_minutes=301 → 400."""
    resp = client.get(
        _EP, params={"interval_minutes": 301}, headers={"Accept-Language": _LANG_ES}
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# T-TD23 — interval_minutes no entero → 422
# ---------------------------------------------------------------------------

def test_TD23_non_integer_422(client):
    """T-TD23: interval_minutes='cuatro' (no entero) → 422 (FastAPI validation)."""
    resp = client.get(
        _EP, params={"interval_minutes": "cuatro"},
        headers={"Accept-Language": _LANG_ES},
    )
    assert resp.status_code == 422


def test_TD23b_float_422(client):
    """T-TD23b: interval_minutes=2.5 (flotante) → 422 (FastAPI validation)."""
    resp = client.get(
        _EP, params={"interval_minutes": "2.5"},
        headers={"Accept-Language": _LANG_ES},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# T-TD24 — Accept-Language ausente → 400
# ---------------------------------------------------------------------------

def test_TD24_missing_accept_language(client):
    """T-TD24: Accept-Language ausente → 400."""
    resp = client.get(_EP, params={"interval_minutes": 240})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# T-TD25 — Accept-Language: zh (no soportado) → 400
# ---------------------------------------------------------------------------

def test_TD25_unsupported_language_zh(client):
    """T-TD25: Accept-Language: zh (no soportado) → 400.
    zh no está en los 25 idiomas soportados.
    """
    resp = client.get(
        _EP, params={"interval_minutes": 240},
        headers={"Accept-Language": "zh"},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# T-TD26 — Particionado por coords: gaps de oasis A no cruzan a oasis B
# ---------------------------------------------------------------------------

def test_TD26_partition_by_coords_no_cross(client):
    """T-TD26: dos oasis con el mismo animal; gaps de oasis A no cruzan a oasis B.
    Verificar que el LAG usa PARTITION BY coord_x_dest, coord_y_dest correctamente.

    Diseño:
      Oasis A (-70, 73): gap=420s → bin 7 [420, 600)
      Oasis B (12, -45): gap=14400s → bin 240 [14400, 18000)
    """
    # Oasis A: gap exacto 420s (7 min)
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 3, 3)]))
    _save(client, _make_report(-70, 73, "01.06.26, 10:07:00", [("Rat", 5, 5)]))

    # Oasis B: gap exacto 14400s (240 min = 4h)
    _save(client, _make_report(12, -45, "01.06.26, 10:00:00", [("Rat", 2, 2)]))
    _save(client, _make_report(12, -45, "01.06.26, 14:00:00", [("Rat", 4, 4)]))

    # Con interval_minutes=7: solo debería contar el gap del oasis A
    data_7 = _get_td(client, interval_minutes=7, lang=_LANG_ES)
    assert data_7["n_reports_in_window"] == 1, (
        f"Solo 1 gap en bin 7 (del oasis A), pero n_reports_in_window={data_7['n_reports_in_window']}"
    )

    # Con interval_minutes=240: solo debería contar el gap del oasis B
    data_240 = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    assert data_240["n_reports_in_window"] == 1, (
        f"Solo 1 gap en bin 240 (del oasis B), pero n_reports_in_window={data_240['n_reports_in_window']}"
    )


# ---------------------------------------------------------------------------
# T-TD27 — Ventana sin datos (frecuencia inusual)
# ---------------------------------------------------------------------------

def test_TD27_window_with_no_data(client):
    """T-TD27: ventana solicitada sin datos → 200, n_reports_in_window=0, animals:[]."""
    # Guardamos reportes con gap de 4h (bin 240) pero pedimos bin 6 (muy pequeño)
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 3, 3)]))
    _save(client, _make_report(-70, 73, "01.06.26, 14:00:00", [("Rat", 5, 5)]))

    data = _get_td(client, interval_minutes=6, lang=_LANG_ES)
    assert data["n_reports_in_window"] == 0
    assert data["animals"] == []
    # Pero la respuesta debe tener los metadatos de la ventana correctos
    assert data["interval_minutes"] == 6
    assert data["interval_label"] == "6 min"
    assert data["window"]["lower_min"] == 6
    assert data["window"]["upper_min"] == 7
    assert data["window"]["is_open"] is False


# ---------------------------------------------------------------------------
# Criterios de aceptación adicionales (§15)
# ---------------------------------------------------------------------------

def test_CA_port_has_abstract_method_v2():
    """CA: get_animal_temporal_distribution() con firma v2 en el port."""
    from core.ports.attack_report_port import AttackReportPort
    import inspect
    assert hasattr(AttackReportPort, "get_animal_temporal_distribution")
    method = getattr(AttackReportPort, "get_animal_temporal_distribution")
    assert getattr(method, "__isabstractmethod__", False)
    sig = inspect.signature(method)
    assert "interval_minutes" in sig.parameters
    assert "bucket_hours" not in sig.parameters


def test_CA_ep_td_before_ep06_routing(client):
    """CA: EP-TD declarado ANTES de EP-06 — FastAPI resuelve la ruta como literal."""
    resp = client.get("/attack-reports/stats/oasis/temporal-distribution")
    # Sin Accept-Language → 400 de get_language, no 422/404 de /{id}
    assert resp.status_code == 400
    body = resp.json()
    assert "detail" in body


def test_CA_all_valid_interval_minutes_accepted(client):
    """CA: todos los valores válidos de interval_minutes devuelven 200."""
    for im in (6, 7, 10, 15, 30, 60, 120, 180, 240, 300):
        resp = client.get(
            _EP, params={"interval_minutes": im},
            headers={"Accept-Language": _LANG_ES},
        )
        assert resp.status_code == 200, f"interval_minutes={im} falló con {resp.status_code}"
        body = resp.json()
        assert body["interval_minutes"] == im


def test_CA_headers_content_type_present(client):
    """CA: cabecera Content-Type application/json presente en 200."""
    resp = client.get(
        _EP, params={"interval_minutes": 240},
        headers={"Accept-Language": _LANG_ES},
    )
    assert resp.status_code == 200
    ct = resp.headers.get("content-type", "")
    assert "application/json" in ct


def test_CA_interval_labels_correct(client):
    """CA: interval_label correcto para cada interval_minutes."""
    expected = {
        6: "6 min", 7: "7 min", 10: "10 min", 15: "15 min", 30: "30 min",
        60: "1h", 120: "2h", 180: "3h", 240: "4h", 300: "5h+",
    }
    for im, label in expected.items():
        resp = client.get(
            _EP, params={"interval_minutes": im},
            headers={"Accept-Language": _LANG_ES},
        )
        body = resp.json()
        assert body["interval_label"] == label, (
            f"interval_minutes={im}: esperado '{label}', obtenido '{body['interval_label']}'"
        )


def test_CA_window_metadata_correct(client):
    """CA: window.lower_min, upper_min e is_open correctos para todos los valores."""
    expected = {
        6:   (6,   7,   False),
        7:   (7,   10,  False),
        10:  (10,  15,  False),
        15:  (15,  30,  False),
        30:  (30,  60,  False),
        60:  (60,  120, False),
        120: (120, 180, False),
        180: (180, 240, False),
        240: (240, 300, False),
        300: (300, None, True),
    }
    for im, (lower, upper, is_open) in expected.items():
        resp = client.get(
            _EP, params={"interval_minutes": im},
            headers={"Accept-Language": _LANG_ES},
        )
        w = resp.json()["window"]
        assert w["lower_min"] == lower, f"im={im}: lower_min incorrecto"
        assert w["upper_min"] == upper, f"im={im}: upper_min incorrecto"
        assert w["is_open"] == is_open, f"im={im}: is_open incorrecto"


def test_CA_n_valid_le_n_total(client):
    """CA: n_valid <= n_total en todos los animales."""
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 5, 5)]))
    _save(client, _make_report(-70, 73, "01.06.26, 14:00:00", [("Rat", 3, 3)]))

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    for animal in data["animals"]:
        assert animal["n_valid"] <= animal["n_total"], (
            f"animal_ordinal={animal['animal_ordinal']}: n_valid={animal['n_valid']} > n_total={animal['n_total']}"
        )


def test_CA_avg_present_rounded_2_decimals(client):
    """CA: avg_present redondeado a 2 decimales."""
    # present=[1,1,2] → avg=4/3≈1.33 (2 decimales)
    dates = ["01.06.26, 10:00:00", "01.06.26, 14:00:00", "01.06.26, 18:00:00", "01.06.26, 22:00:00"]
    presents = [10, 1, 1, 2]
    for d, p in zip(dates, presents):
        _save(client, _make_report(-70, 73, d, [("Rat", p, p)]))

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    for animal in data["animals"]:
        if animal["avg_present"] is not None:
            s = str(animal["avg_present"])
            if "." in s:
                decimals = len(s.split(".")[1])
                assert decimals <= 2, f"avg_present={animal['avg_present']} tiene >2 decimales"


def test_CA_mode_present_sorted_asc(client):
    """CA: mode_present siempre ordenado ASC."""
    dates = ["01.06.26, 10:00:00", "01.06.26, 14:00:00", "01.06.26, 18:00:00",
             "01.06.26, 22:00:00", "02.06.26, 02:00:00"]
    presents = [10, 3, 2, 3, 2]
    for d, p in zip(dates, presents):
        _save(client, _make_report(-70, 73, d, [("Rat", p, p)]))

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    for animal in data["animals"]:
        mp = animal["mode_present"]
        assert mp == sorted(mp), f"mode_present no está ordenado ASC: {mp}"


def test_CA_200_empty_not_404(client):
    """CA: BD vacía → 200 con n_reports_in_window:0, animals:[], nunca 404."""
    resp = client.get(
        _EP, params={"interval_minutes": 240},
        headers={"Accept-Language": _LANG_ES},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["n_reports_in_window"] == 0
    assert body["animals"] == []


def test_CA_animals_sorted_asc(client):
    """CA: animals[] ordenados por animal_ordinal ASC."""
    # Rat (ord 1) + Wolf (ord 6) con gaps en bin 240
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 3, 3), ("Wolf", 2, 2)]))
    _save(client, _make_report(-70, 73, "01.06.26, 14:00:00", [("Rat", 5, 5), ("Wolf", 3, 3)]))

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    ordinals = [a["animal_ordinal"] for a in data["animals"]]
    assert ordinals == sorted(ordinals)
