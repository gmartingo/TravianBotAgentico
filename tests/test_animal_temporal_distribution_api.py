"""
Tests de integración de EP-TD — GET /attack-reports/stats/oasis/temporal-distribution

Cubre los casos T-TD01..T-TD35 del spec
docs/specs/bd-ataques-oasis-temporal-distribution.md §12 (v3).

Spec v3: respuesta agrupada en 5 secciones fijas por tipo de oasis inferido
(hierro, arcilla, madera, cereal, sin_clasificar). El campo animals[] de la
raíz de v2 desaparece — ahora vive dentro de cada sección de types[].

Usa TestClient con lifespan activado (BD real en fichero temporal, aislada por test).
Mismo patrón de fixture que test_oasis_spawn_composition_api.py.

Actualizado en la feature bd-ataques-oasis-temporal-distribution v3 (2026-06-02).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from adapters.api.main import app

_EP = "/attack-reports/stats/oasis/temporal-distribution"
_LANG_ES = "es"
_LANG_EN = "en"
_LANG_IT = "it"

# Coordenadas de oasis por tipo (para fixtures v3)
# Hierro: {1,2,4} — Rata, Araña, Murciélago
_OX_HIERRO, _OY_HIERRO = -70, 73
# Madera: {5,6,7} — Jabalí, Lobo, Oso
_OX_MADERA, _OY_MADERA = 10, 20
# Arcilla: {1,2,5} — Rata, Araña, Jabalí
_OX_ARCILLA, _OY_ARCILLA = 30, 40
# Sin_clasificar (solo derrotas)
_OX_DEFEAT, _OY_DEFEAT = 50, 60


# ---------------------------------------------------------------------------
# Fixture — cliente con BD temporal aislada por test
# ---------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch, tmp_path):
    """
    Cliente con la app real apuntando a una BD temporal por test.
    Monkeypatcha DB_PATH antes del lifespan para garantizar BD limpia.
    """
    db_file = tmp_path / "test_temporal_dist_v3.db"
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


def _find_section(data: dict, oasis_type: str) -> dict | None:
    """Busca una sección por oasis_type en types[]."""
    for sec in data["types"]:
        if sec["oasis_type"] == oasis_type:
            return sec
    return None


def _find_animal_in_section(section: dict, ordinal: int) -> dict | None:
    """Busca un animal por ordinal dentro de una sección."""
    for a in section["animals"]:
        if a["animal_ordinal"] == ordinal:
            return a
    return None


# Compatibilidad: helper global que busca en TODAS las secciones
def _find_animal(data: dict, ordinal: int) -> dict | None:
    """Busca un animal por ordinal en cualquiera de las secciones de types[]."""
    for sec in data.get("types", []):
        for a in sec["animals"]:
            if a["animal_ordinal"] == ordinal:
                return a
    return None


# ---------------------------------------------------------------------------
# Fixture de reportes hierro (Rata ord=1, Araña ord=2, Murciélago ord=4)
# Gap de 4h (14400s) — bin 240 [14400, 18000)
# ---------------------------------------------------------------------------

def _insert_hierro_reports_4h(client, n_pairs=3):
    """
    Inserta n_pairs pares de reportes para el oasis hierro con gap de 4h.
    n_pairs=3 → 3 gaps → confidence='medium' (>=3 bursts present>0).
    """
    # Primer reporte (sin gap)
    _save(client, _make_report(
        _OX_HIERRO, _OY_HIERRO, "01.06.26, 06:00:00",
        [("Rat", 2, 2), ("Spider", 1, 1), ("Bat", 3, 3)],
    ))
    for i in range(n_pairs):
        h = 10 + i * 4
        _save(client, _make_report(
            _OX_HIERRO, _OY_HIERRO, f"01.06.26, {h:02d}:00:00",
            [("Rat", 3, 3), ("Spider", 2, 2), ("Bat", 4, 4)],
        ))


def _insert_madera_reports_4h(client, n_pairs=3):
    """
    Inserta n_pairs pares de reportes para el oasis madera con gap de 4h.
    """
    _save(client, _make_report(
        _OX_MADERA, _OY_MADERA, "01.06.26, 06:00:00",
        [("Wild boar", 2, 2), ("Wolf", 3, 3), ("Bear", 1, 1)],
    ))
    for i in range(n_pairs):
        h = 10 + i * 4
        _save(client, _make_report(
            _OX_MADERA, _OY_MADERA, f"01.06.26, {h:02d}:00:00",
            [("Wild boar", 3, 3), ("Wolf", 5, 5), ("Bear", 2, 2)],
        ))


# ---------------------------------------------------------------------------
# T-TD01 — Camino feliz: interval_minutes=240, lang=es, oasis hierro
# ---------------------------------------------------------------------------

def test_TD01_happy_path_240_es(client):
    """T-TD01: interval_minutes=240, lang=es, BD con oasis hierro y gaps en [14400, 18000).
    200, interval_minutes=240, interval_label='4h', window correcta,
    n_reports_in_window>0, types tiene 5 elementos, sección hierro con datos.
    """
    _insert_hierro_reports_4h(client)

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)

    assert data["interval_minutes"] == 240
    assert data["interval_label"] == "4h"
    assert data["window"]["lower_min"] == 240
    assert data["window"]["upper_min"] == 300
    assert data["window"]["is_open"] is False
    assert data["n_reports_in_window"] >= 1

    # v3: field types en lugar de animals en raíz
    assert "types" in data
    assert "animals" not in data  # campo raíz de v2 eliminado en v3
    assert len(data["types"]) == 5

    # Sección hierro debe tener datos
    sec = _find_section(data, "hierro")
    assert sec is not None
    assert sec["n_reports_in_section"] >= 1
    assert len(sec["animals"]) >= 1

    # Animales ordenados por ordinal ASC dentro de la sección
    ordinals = [a["animal_ordinal"] for a in sec["animals"]]
    assert ordinals == sorted(ordinals)

    # Rata (ord 1) en sección hierro con icon_url correcto
    rat = _find_animal_in_section(sec, 1)
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
    El oasis solo con derrotas → sin_clasificar (tipo=None).
    """
    # Primer ataque con present>0 para que el oasis tenga tipo
    _save(client, _make_report(_OX_MADERA, _OY_MADERA, "01.06.26, 10:00:00",
                                [("Wolf", 3, 3), ("Wild boar", 2, 2), ("Bear", 1, 1)]))
    # Segundo ataque: derrota → present=NULL — gap=4h → bin 240
    _save(client, _make_report(_OX_MADERA, _OY_MADERA, "01.06.26, 14:00:00",
                                [("Wolf", None, None)], defeat=True))

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)

    # Wolf está en sección madera
    sec_madera = _find_section(data, "madera")
    assert sec_madera is not None
    wolf = _find_animal_in_section(sec_madera, 6)
    assert wolf is not None
    assert wolf["n_total"] == 1      # el reporte ocurrió
    assert wolf["n_valid"] == 0      # present=NULL → excluido
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
# T-TD07 — BD vacía: 200 con 5 secciones vacías
# ---------------------------------------------------------------------------

def test_TD07_empty_db(client):
    """T-TD07: BD vacía → 200 con n_reports_in_window=0, types con 5 secciones vacías."""
    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    assert data["interval_minutes"] == 240
    assert data["n_reports_in_window"] == 0
    assert "types" in data
    assert len(data["types"]) == 5
    for sec in data["types"]:
        assert sec["n_oasis"] == 0
        assert sec["n_oasis_low_confidence"] == 0
        assert sec["n_reports_in_section"] == 0
        assert sec["animals"] == []


# ---------------------------------------------------------------------------
# T-TD08 — Un solo reporte por oasis (no puede generar gap)
# ---------------------------------------------------------------------------

def test_TD08_single_report_per_oasis_no_gaps(client):
    """T-TD08: BD con exactamente 1 reporte por oasis → 200, n_reports_in_window=0,
    5 secciones vacías."""
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 3, 3)]))
    _save(client, _make_report(12, -45, "01.06.26, 10:00:00", [("Wolf", 5, 5)]))

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    assert data["n_reports_in_window"] == 0
    assert len(data["types"]) == 5
    for sec in data["types"]:
        assert sec["n_reports_in_section"] == 0


# ---------------------------------------------------------------------------
# T-TD09 — Localización italiana
# ---------------------------------------------------------------------------

def test_TD09_lang_it(client):
    """T-TD09: lang=it → nombres de animales en italiano dentro de types[].animals."""
    _save(client, _make_report(_OX_MADERA, _OY_MADERA, "01.06.26, 10:00:00",
                                [("Wolf", 3, 3), ("Wild boar", 2, 2), ("Bear", 1, 1)]))
    _save(client, _make_report(_OX_MADERA, _OY_MADERA, "01.06.26, 14:00:00",
                                [("Wolf", 5, 5), ("Wild boar", 3, 3), ("Bear", 2, 2)]))

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
    """T-TD10: animal_name nunca está vacío (sea localizado o fallback de BD)."""
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 3, 3)]))
    _save(client, _make_report(-70, 73, "01.06.26, 14:00:00", [("Rat", 5, 5)]))

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
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 3, 3)]))
    _save(client, _make_report(-70, 73, "01.06.26, 10:07:00", [("Rat", 5, 5)]))

    # Con interval_minutes=7 → ventana [420s, 600s): el gap exacto de 420s debe contar
    data = _get_td(client, interval_minutes=7, lang=_LANG_ES)
    assert data["n_reports_in_window"] >= 1

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
    Frontera superior exclusiva.
    """
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 3, 3)]))
    _save(client, _make_report(-70, 73, "01.06.26, 10:10:00", [("Rat", 5, 5)]))
    # gap = 10*60 = 600s

    # Bin 7 [420, 600): 600 NO pertenece (frontera exclusiva)
    data_7 = _get_td(client, interval_minutes=7, lang=_LANG_ES)
    assert data_7["n_reports_in_window"] == 0

    # Bin 10 [600, 900): 600 sí pertenece
    data_10 = _get_td(client, interval_minutes=10, lang=_LANG_ES)
    assert data_10["n_reports_in_window"] >= 1


# ---------------------------------------------------------------------------
# T-TD15 — Gap < 6 min descartado
# ---------------------------------------------------------------------------

def test_TD15_gap_less_than_6min_discarded(client):
    """T-TD15: gap de 5*60=300s (< 6 min) → descartado. n_reports_in_window=0."""
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 3, 3)]))
    _save(client, _make_report(-70, 73, "01.06.26, 10:05:00", [("Rat", 5, 5)]))
    # gap = 300s < 360s → descartado

    data = _get_td(client, interval_minutes=6, lang=_LANG_ES)
    assert data["n_reports_in_window"] == 0


# ---------------------------------------------------------------------------
# T-TD16 — Gap de 86400s (24h) con interval_minutes=240 no cuenta
# ---------------------------------------------------------------------------

def test_TD16_gap_24h_not_in_240_bin(client):
    """T-TD16: gap de 86400s (24h) con interval_minutes=240 → NO cuenta.
    Con interval_minutes=300 → sí cuenta (ventana abierta [18000, ∞)).
    """
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 3, 3)]))
    _save(client, _make_report(-70, 73, "02.06.26, 10:00:00", [("Rat", 5, 5)]))
    # gap = 86400s

    # Bin 240 [14400, 18000): 86400 >= 18000 → no cae aquí
    data_240 = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    assert data_240["n_reports_in_window"] == 0

    # Bin 300 [18000, ∞): 86400 >= 18000 → sí cuenta
    data_300 = _get_td(client, interval_minutes=300, lang=_LANG_ES)
    assert data_300["n_reports_in_window"] >= 1


# ---------------------------------------------------------------------------
# T-TD17 — Gap de 86400s con interval_minutes=300 cuenta (bin abierto)
# ---------------------------------------------------------------------------

def test_TD17_gap_24h_in_300_bin(client):
    """T-TD17: gap de 86400s (24h) con interval_minutes=300 → cuenta (bin abierto)."""
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 3, 3)]))
    _save(client, _make_report(-70, 73, "02.06.26, 10:00:00", [("Rat", 5, 5)]))

    data = _get_td(client, interval_minutes=300, lang=_LANG_ES)
    assert data["n_reports_in_window"] >= 1


# ---------------------------------------------------------------------------
# T-TD18 — Gap en límite superior exacto no pertenece al bin
# ---------------------------------------------------------------------------

def test_TD18_gap_at_exact_upper_limit_belongs_to_next_bin(client):
    """T-TD18: gap exactamente en upper_min * 60 → no pertenece al bin.
    Pertenece al bin siguiente.
    """
    # gap = 10 * 60 = 600s = upper_sec de bin 7 → pertenece a bin 10
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 3, 3)]))
    _save(client, _make_report(-70, 73, "01.06.26, 10:10:00", [("Rat", 5, 5)]))

    # Bin 7 no lo recibe
    data_7 = _get_td(client, interval_minutes=7, lang=_LANG_ES)
    assert data_7["n_reports_in_window"] == 0

    # Bin 10 lo recibe
    data_10 = _get_td(client, interval_minutes=10, lang=_LANG_ES)
    assert data_10["n_reports_in_window"] >= 1


# ---------------------------------------------------------------------------
# T-TD19 — Gap de 0s (relojes iguales) descartado
# ---------------------------------------------------------------------------

def test_TD19_zero_gap_discarded(client):
    """T-TD19: gap de 0s (mismo attacked_at) → descartado."""
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 3, 3)]))
    # Con la constraint UNIQUE (coord, attacked_at, origin), dos reportes iguales fallan.
    # Simulamos con dos orígenes distintos pero a la misma hora (gap entre orígenes = 0s)
    # En realidad el gap LAG es PARTITION BY coords, así que el segundo insert con igual
    # attacked_at da gap=0 → descartado.
    # Verificamos con un segundo oasis (coords distintas) para evitar UNIQUE violation:
    _save(client, _make_report(-70, 74, "01.06.26, 10:00:00", [("Rat", 3, 3)]))
    _save(client, _make_report(-70, 74, "01.06.26, 10:00:00", [("Rat", 5, 5)], village="OtherVillage"))
    # El gap = 0 → descartado

    data = _get_td(client, interval_minutes=6, lang=_LANG_ES)
    # El gap 0 no debe contribuir a ningún bin
    assert data["n_reports_in_window"] == 0


# ---------------------------------------------------------------------------
# T-TD20 — interval_minutes=45 (entero pero fuera del set) → 400
# ---------------------------------------------------------------------------

def test_TD20_interval_minutes_out_of_set(client):
    """T-TD20: interval_minutes=45 → 400 con detail que lista los 10 valores válidos."""
    resp = client.get(
        _EP,
        params={"interval_minutes": 45},
        headers={"Accept-Language": _LANG_ES},
    )
    assert resp.status_code == 400
    body = resp.json()
    detail = body["detail"]
    # Detail debe mencionar los 10 valores válidos
    for v in ["6", "7", "10", "15", "30", "60", "120", "180", "240", "300"]:
        assert v in detail, f"valor {v} no mencionado en el detail: {detail}"
    assert "45" in detail  # el valor recibido también debe aparecer


# ---------------------------------------------------------------------------
# T-TD21 — interval_minutes=0 → 400
# ---------------------------------------------------------------------------

def test_TD21_interval_minutes_zero(client):
    """T-TD21: interval_minutes=0 → 400."""
    resp = client.get(
        _EP,
        params={"interval_minutes": 0},
        headers={"Accept-Language": _LANG_ES},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# T-TD22 — interval_minutes=301 → 400
# ---------------------------------------------------------------------------

def test_TD22_interval_minutes_301(client):
    """T-TD22: interval_minutes=301 → 400."""
    resp = client.get(
        _EP,
        params={"interval_minutes": 301},
        headers={"Accept-Language": _LANG_ES},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# T-TD23 — interval_minutes no entero → 422
# ---------------------------------------------------------------------------

def test_TD23_interval_minutes_not_int(client):
    """T-TD23: interval_minutes='cuatro' → 422 (FastAPI validation automática)."""
    resp = client.get(
        _EP,
        params={"interval_minutes": "cuatro"},
        headers={"Accept-Language": _LANG_ES},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# T-TD24 — Accept-Language ausente → 400
# ---------------------------------------------------------------------------

def test_TD24_accept_language_missing(client):
    """T-TD24: Accept-Language ausente → 400."""
    resp = client.get(_EP, params={"interval_minutes": 240})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# T-TD25 — Accept-Language no soportado → 400
# ---------------------------------------------------------------------------

def test_TD25_accept_language_unsupported(client):
    """T-TD25: Accept-Language: zh (no soportado) → 400."""
    resp = client.get(
        _EP,
        params={"interval_minutes": 240},
        headers={"Accept-Language": "zh"},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# T-TD26 — LAG no cruza oasis distintos
# ---------------------------------------------------------------------------

def test_TD26_lag_does_not_cross_oasis(client):
    """T-TD26: dos oasis con el mismo animal; gaps de oasis A no cruzan a oasis B.
    Verificar que el particionado por coords es correcto.
    """
    # Oasis A: dos reportes con gap de 4h
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 3, 3)]))
    _save(client, _make_report(-70, 73, "01.06.26, 14:00:00", [("Rat", 5, 5)]))

    # Oasis B: UN solo reporte (no puede generar gap)
    _save(client, _make_report(12, -45, "01.06.26, 12:00:00", [("Rat", 2, 2)]))

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    # Solo 1 gap (del oasis A)
    assert data["n_reports_in_window"] == 1


# ---------------------------------------------------------------------------
# T-TD27 — Ventana solicitada sin datos → 200 con n_reports_in_window=0
# ---------------------------------------------------------------------------

def test_TD27_empty_window(client):
    """T-TD27: ventana solicitada sin datos → 200 con n_reports_in_window=0."""
    # Inserta reportes con gap de 4h (bin 240) pero pide bin 6
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 3, 3)]))
    _save(client, _make_report(-70, 73, "01.06.26, 14:00:00", [("Rat", 5, 5)]))

    data = _get_td(client, interval_minutes=6, lang=_LANG_ES)
    assert data["n_reports_in_window"] == 0
    assert len(data["types"]) == 5
    for sec in data["types"]:
        assert sec["n_reports_in_section"] == 0


# ===========================================================================
# T-TD28..T-TD35 — Tests específicos v3
# ===========================================================================

# ---------------------------------------------------------------------------
# T-TD28 — Oasis hierro {1,2,4} y madera {5,6,7}: secciones arcilla/cereal/sin_clasificar vacías
# ---------------------------------------------------------------------------

def test_TD28_hierro_and_madera_sections(client):
    """T-TD28: BD con oasis hierro {1,2,4} y madera {5,6,7}; gaps de ambos en ventana.
    types tiene 5 elementos; secciones hierro y madera con datos;
    secciones arcilla, cereal, sin_clasificar vacías.
    """
    _insert_hierro_reports_4h(client)
    _insert_madera_reports_4h(client)

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)

    assert len(data["types"]) == 5

    sec_hierro = _find_section(data, "hierro")
    sec_madera = _find_section(data, "madera")
    sec_arcilla = _find_section(data, "arcilla")
    sec_cereal = _find_section(data, "cereal")
    sec_sc = _find_section(data, "sin_clasificar")

    assert sec_hierro["n_reports_in_section"] > 0, "hierro debe tener datos"
    assert sec_madera["n_reports_in_section"] > 0, "madera debe tener datos"
    assert sec_arcilla["n_reports_in_section"] == 0, "arcilla debe estar vacía"
    assert sec_cereal["n_reports_in_section"] == 0, "cereal debe estar vacía"
    assert sec_sc["n_reports_in_section"] == 0, "sin_clasificar debe estar vacía"

    # Oasis con animales {1,2,4} → hierro (Jaccard=1.0)
    # Rata (ord 1), Araña (ord 2), Murciélago (ord 4) deben estar en hierro
    assert _find_animal_in_section(sec_hierro, 1) is not None, "Rata en hierro"
    assert _find_animal_in_section(sec_hierro, 2) is not None, "Araña en hierro"
    assert _find_animal_in_section(sec_hierro, 4) is not None, "Murciélago en hierro"

    # Oasis con animales {5,6,7} → madera (Jaccard=1.0)
    # Jabalí (ord 5), Lobo (ord 6), Oso (ord 7) deben estar en madera
    assert _find_animal_in_section(sec_madera, 5) is not None, "Jabalí en madera"
    assert _find_animal_in_section(sec_madera, 6) is not None, "Lobo en madera"
    assert _find_animal_in_section(sec_madera, 7) is not None, "Oso en madera"


# ---------------------------------------------------------------------------
# T-TD29 — Oasis con solo reportes de derrota → sin_clasificar
# ---------------------------------------------------------------------------

def test_TD29_defeat_only_oasis_goes_to_sin_clasificar(client):
    """T-TD29: oasis con solo reportes de derrota (present=NULL en todos) →
    tipo=None → gap va a sección sin_clasificar.
    """
    # Primer ataque del oasis (no genera gap, solo establece línea temporal)
    _save(client, _make_report(_OX_DEFEAT, _OY_DEFEAT, "01.06.26, 10:00:00",
                                [("Wolf", None, None)], defeat=True))
    # Segundo ataque: derrota también → present=NULL; gap=4h → bin 240
    _save(client, _make_report(_OX_DEFEAT, _OY_DEFEAT, "01.06.26, 14:00:00",
                                [("Wolf", None, None)], defeat=True))

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)

    sec_sc = _find_section(data, "sin_clasificar")
    assert sec_sc is not None
    # El gap debe estar en sin_clasificar (tipo=None porque no hay present>0)
    assert sec_sc["n_reports_in_section"] >= 1


# ---------------------------------------------------------------------------
# T-TD30 — Oasis con 1 burst observable → low confidence, se queda en su sección de tipo
# ---------------------------------------------------------------------------

def test_TD30_low_confidence_stays_in_type_section(client):
    """T-TD30: oasis con burst_count_total < 3 (confidence='low') y gap en ventana →
    incluido en su sección de tipo. n_oasis_low_confidence=1.
    Usa Murciélago (ordinal=4) como único animal: Jaccard(hierro={1,2,4},{4})=1/3 > resto.
    Hierro es el único tipo con Jaccard>0 para {4} (arcilla/madera tienen 0) → clasifica único.
    2 reportes → burst_count=2 < 3 → confidence='low'.
    """
    # Oasis con SOLO Murciélago (ordinal 4):
    #   Jaccard(hierro={1,2,4}, obs={4}) = 1/3 ≈ 0.33
    #   Jaccard(arcilla={1,2,5}, obs={4}) = 0     ← arcilla NO tiene el 4
    #   Jaccard(madera={5,6,7}, obs={4}) = 0
    #   Jaccard(cereal={1..10}, obs={4}) = 1/10 = 0.10
    # → hierro gana con max score 1/3. burst_count_total = 2 (1 Bat en cada reporte) < 3 → low.
    _save(client, _make_report(-99, -99, "01.06.26, 10:00:00", [("Bat", 3, 3)]))
    _save(client, _make_report(-99, -99, "01.06.26, 14:00:00", [("Bat", 4, 4)]))
    # burst_count = 2 para Bat (ord=4) → total_bursts=2 < 3 → confidence='low'

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)

    # El oasis (-99,-99) va a sección hierro con confidence=low
    sec_hierro = _find_section(data, "hierro")
    assert sec_hierro is not None
    assert sec_hierro["n_reports_in_section"] >= 1, "Hierro debe tener el gap del oasis Bat"
    assert sec_hierro["n_oasis_low_confidence"] >= 1, (
        f"Esperaba n_oasis_low_confidence>=1 en hierro (oasis con Bat, 2 bursts<3), "
        f"got {sec_hierro['n_oasis_low_confidence']}"
    )
    # El oasis sí tiene present>0 → NO va a sin_clasificar
    sec_sc = _find_section(data, "sin_clasificar")
    assert sec_sc is not None
    # Bat en hierro, no en sin_clasificar
    bat_in_sc = _find_animal_in_section(sec_sc, 4)
    assert bat_in_sc is None, "Bat no debe estar en sin_clasificar (tiene tipo hierro)"


# ---------------------------------------------------------------------------
# T-TD31 — Oasis con >=3 bursts (confidence=medium) → n_oasis_low_confidence no incrementa
# ---------------------------------------------------------------------------

def test_TD31_medium_confidence_no_increment(client):
    """T-TD31: oasis con 3 o más bursts (confidence='medium') →
    n_oasis_low_confidence=0 para ese oasis en su sección.
    """
    # 4 reportes del oasis hierro: burst_count >=3 por tipo de animal → medium
    _save(client, _make_report(_OX_HIERRO, _OY_HIERRO, "01.06.26, 06:00:00",
                                [("Rat", 3, 3), ("Spider", 1, 1), ("Bat", 2, 2)]))
    _save(client, _make_report(_OX_HIERRO, _OY_HIERRO, "01.06.26, 10:00:00",
                                [("Rat", 4, 4), ("Spider", 2, 2), ("Bat", 3, 3)]))
    _save(client, _make_report(_OX_HIERRO, _OY_HIERRO, "01.06.26, 14:00:00",
                                [("Rat", 5, 5), ("Spider", 3, 3), ("Bat", 4, 4)]))
    _save(client, _make_report(_OX_HIERRO, _OY_HIERRO, "01.06.26, 18:00:00",
                                [("Rat", 3, 3), ("Spider", 2, 2), ("Bat", 2, 2)]))
    # burst_count total: Rata=3 + Araña=3 + Murciélago=3 = 9 ≥ 3 → medium

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)

    sec_hierro = _find_section(data, "hierro")
    assert sec_hierro is not None
    assert sec_hierro["n_reports_in_section"] >= 1
    # Solo este oasis → n_oasis_low_confidence debe ser 0
    assert sec_hierro["n_oasis_low_confidence"] == 0, (
        f"Esperaba n_oasis_low_confidence=0 (medium confidence), "
        f"got {sec_hierro['n_oasis_low_confidence']}"
    )


# ---------------------------------------------------------------------------
# T-TD32 — Dos oasis del mismo tipo: n_oasis=2, animals agrega los gaps de ambos
# ---------------------------------------------------------------------------

def test_TD32_two_oasis_same_type_aggregated(client):
    """T-TD32: dos oasis del tipo 'hierro' con gaps en la ventana →
    n_oasis=2 en la sección hierro; animals agrega los gaps de ambos.
    """
    # Oasis 1 hierro
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00",
                                [("Rat", 3, 3), ("Spider", 1, 1), ("Bat", 2, 2)]))
    _save(client, _make_report(-70, 73, "01.06.26, 14:00:00",
                                [("Rat", 5, 5), ("Spider", 2, 2), ("Bat", 3, 3)]))

    # Oasis 2 hierro (coords distintas)
    _save(client, _make_report(-71, 74, "01.06.26, 10:00:00",
                                [("Rat", 2, 2), ("Spider", 1, 1), ("Bat", 1, 1)]))
    _save(client, _make_report(-71, 74, "01.06.26, 14:00:00",
                                [("Rat", 4, 4), ("Spider", 3, 3), ("Bat", 2, 2)]))

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)

    sec_hierro = _find_section(data, "hierro")
    assert sec_hierro is not None
    assert sec_hierro["n_oasis"] == 2, (
        f"Esperaba n_oasis=2 en hierro, got {sec_hierro['n_oasis']}"
    )
    assert sec_hierro["n_reports_in_section"] == 2, (
        f"Esperaba n_reports_in_section=2, got {sec_hierro['n_reports_in_section']}"
    )

    # Los animals agregan de ambos oasis
    rat = _find_animal_in_section(sec_hierro, 1)
    assert rat is not None
    assert rat["n_total"] == 2  # 1 gap de cada oasis


# ---------------------------------------------------------------------------
# T-TD33 — n_reports_in_window == suma de n_reports_in_section (invariante)
# ---------------------------------------------------------------------------

def test_TD33_n_reports_invariant(client):
    """T-TD33: n_reports_in_window == suma de n_reports_in_section de las 5 secciones."""
    _insert_hierro_reports_4h(client)
    _insert_madera_reports_4h(client)

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)

    suma = sum(sec["n_reports_in_section"] for sec in data["types"])
    assert data["n_reports_in_window"] == suma, (
        f"Invariante violada: n_reports_in_window={data['n_reports_in_window']} "
        f"!= suma secciones={suma}"
    )


# ---------------------------------------------------------------------------
# T-TD34 — Secciones en orden fijo (hierro[0], arcilla[1], madera[2], cereal[3], sin_clasificar[4])
# ---------------------------------------------------------------------------

def test_TD34_sections_fixed_order(client):
    """T-TD34: types[0].oasis_type='hierro', types[1]='arcilla', ..., types[4]='sin_clasificar'."""
    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)

    tipos = [sec["oasis_type"] for sec in data["types"]]
    assert tipos == ["hierro", "arcilla", "madera", "cereal", "sin_clasificar"], (
        f"Orden de secciones incorrecto: {tipos}"
    )


# ---------------------------------------------------------------------------
# T-TD35 — oasis_type_label de arcilla es "Barro"
# ---------------------------------------------------------------------------

def test_TD35_arcilla_label_is_barro(client):
    """T-TD35: types[1].oasis_type_label == 'Barro' (no 'Arcilla'). RN-TD18."""
    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)

    sec_arcilla = _find_section(data, "arcilla")
    assert sec_arcilla is not None
    assert sec_arcilla["oasis_type_label"] == "Barro", (
        f"Esperaba 'Barro', got '{sec_arcilla['oasis_type_label']}'"
    )
    # Verificar todas las etiquetas fijas
    labels = {sec["oasis_type"]: sec["oasis_type_label"] for sec in data["types"]}
    assert labels["hierro"] == "Hierro"
    assert labels["arcilla"] == "Barro"
    assert labels["madera"] == "Madera"
    assert labels["cereal"] == "Cereal"
    assert labels["sin_clasificar"] == "Sin clasificar"


# ===========================================================================
# Tests adicionales de criterios de aceptación (v2 que siguen válidos en v3)
# ===========================================================================

def test_CA_all_5_sections_always_present_even_empty(client):
    """CA: las 5 secciones se devuelven siempre aunque estén vacías (BD vacía)."""
    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    assert len(data["types"]) == 5
    tipos = [sec["oasis_type"] for sec in data["types"]]
    assert "hierro" in tipos
    assert "arcilla" in tipos
    assert "madera" in tipos
    assert "cereal" in tipos
    assert "sin_clasificar" in tipos


def test_CA_no_animals_at_root_level(client):
    """CA: el campo 'animals' NO existe en el nivel raíz de la respuesta (v3)."""
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00", [("Rat", 3, 3)]))
    _save(client, _make_report(-70, 73, "01.06.26, 14:00:00", [("Rat", 5, 5)]))

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    assert "animals" not in data, (
        "v3: 'animals' no debe existir en el nivel raíz; ahora vive dentro de cada sección de types[]"
    )


def test_CA_window_metadata_correct_for_all_bins(client):
    """CA: metadatos de ventana correctos para todos los bins."""
    expected = [
        (6,   {"lower_min": 6,   "upper_min": 7,   "is_open": False, "label": "6 min"}),
        (7,   {"lower_min": 7,   "upper_min": 10,  "is_open": False, "label": "7 min"}),
        (10,  {"lower_min": 10,  "upper_min": 15,  "is_open": False, "label": "10 min"}),
        (15,  {"lower_min": 15,  "upper_min": 30,  "is_open": False, "label": "15 min"}),
        (30,  {"lower_min": 30,  "upper_min": 60,  "is_open": False, "label": "30 min"}),
        (60,  {"lower_min": 60,  "upper_min": 120, "is_open": False, "label": "1h"}),
        (120, {"lower_min": 120, "upper_min": 180, "is_open": False, "label": "2h"}),
        (180, {"lower_min": 180, "upper_min": 240, "is_open": False, "label": "3h"}),
        (240, {"lower_min": 240, "upper_min": 300, "is_open": False, "label": "4h"}),
        (300, {"lower_min": 300, "upper_min": None,"is_open": True,  "label": "5h+"}),
    ]
    for interval, exp in expected:
        resp = client.get(
            _EP,
            params={"interval_minutes": interval},
            headers={"Accept-Language": _LANG_ES},
        )
        assert resp.status_code == 200, f"bin={interval}"
        body = resp.json()
        assert body["interval_minutes"] == interval, f"bin={interval}"
        assert body["interval_label"] == exp["label"], f"bin={interval}"
        assert body["window"]["lower_min"] == exp["lower_min"], f"bin={interval}"
        assert body["window"]["upper_min"] == exp["upper_min"], f"bin={interval}"
        assert body["window"]["is_open"] == exp["is_open"], f"bin={interval}"


def test_CA_n_reports_in_window_zero_all_sections_empty(client):
    """CA: cuando n_reports_in_window=0, todas las secciones tienen n_reports_in_section=0."""
    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    assert data["n_reports_in_window"] == 0
    for sec in data["types"]:
        assert sec["n_reports_in_section"] == 0
        assert sec["animals"] == []


def test_CA_consistency_with_EP_SPAWN_same_oasis_type(client):
    """CA: consistencia entre EP-TD y EP-SPAWN — el mismo oasis debe
    inferir el mismo tipo en ambos endpoints.
    """
    # Oasis hierro con suficientes reportes para medium confidence
    _insert_hierro_reports_4h(client)

    # Pedir EP-TD
    data_td = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    sec_hierro = _find_section(data_td, "hierro")
    assert sec_hierro is not None
    assert sec_hierro["n_reports_in_section"] > 0, "EP-TD debe tener datos en hierro"

    # Pedir EP-SPAWN para el mismo oasis
    resp_spawn = client.get(
        "/attack-reports/stats/oasis/spawn-composition",
        params={"timer_min": 15},
        headers={"Accept-Language": _LANG_ES},
    )
    assert resp_spawn.status_code == 200
    spawn_data = resp_spawn.json()

    # Encontrar el oasis en EP-SPAWN
    oasis_spawn = None
    for o in spawn_data["oasis"]:
        if o["coord_x_dest"] == _OX_HIERRO and o["coord_y_dest"] == _OY_HIERRO:
            oasis_spawn = o
            break

    if oasis_spawn is not None:
        # Ambos endpoints deben inferir "hierro" para el mismo oasis
        assert oasis_spawn["inferred_type"] == "hierro", (
            f"EP-SPAWN infirió '{oasis_spawn['inferred_type']}', EP-TD lo puso en 'hierro'. "
            "Inconsistencia en la lógica Jaccard."
        )


def test_CA_oasis_with_gaps_outside_window_not_counted(client):
    """CA (EC-TD26): oasis con tipo inferido pero sin gaps en la ventana solicitada
    no incrementa n_oasis ni n_reports_in_section.
    """
    # Oasis hierro con gap de 4h (bin 240) — insertamos solo 2 reportes
    _save(client, _make_report(_OX_HIERRO, _OY_HIERRO, "01.06.26, 10:00:00",
                                [("Rat", 3, 3), ("Spider", 1, 1), ("Bat", 2, 2)]))
    _save(client, _make_report(_OX_HIERRO, _OY_HIERRO, "01.06.26, 14:00:00",
                                [("Rat", 5, 5), ("Spider", 2, 2), ("Bat", 3, 3)]))
    # gap = 4h = 14400s → bin 240 [14400, 18000)

    # Pedimos bin 6 (ventana [360, 420)) — el gap de 14400s no cae aquí
    data = _get_td(client, interval_minutes=6, lang=_LANG_ES)

    sec_hierro = _find_section(data, "hierro")
    assert sec_hierro is not None
    # Aunque el oasis tiene tipo hierro, sus gaps no caen en la ventana 6
    assert sec_hierro["n_oasis"] == 0
    assert sec_hierro["n_reports_in_section"] == 0


# ===========================================================================
# T-TD36..T-TD48 — Tests específicos v4
# ===========================================================================

# ---------------------------------------------------------------------------
# T-TD36 — max_present con n_valid>0: igual al máximo de present observados
# ---------------------------------------------------------------------------

def test_TD36_max_present_with_valid_values(client):
    """T-TD36: max_present = max(present) cuando n_valid>0 (RN-TD20).
    Dos reportes con Rata (present=2, present=5) → max_present=5.
    """
    # Primer reporte del oasis (sin gap)
    _save(client, _make_report(_OX_HIERRO, _OY_HIERRO, "01.06.26, 10:00:00",
                                [("Rat", 2, 2), ("Spider", 1, 1), ("Bat", 1, 1)]))
    # Segundo reporte: gap de 4h → bin 240
    _save(client, _make_report(_OX_HIERRO, _OY_HIERRO, "01.06.26, 14:00:00",
                                [("Rat", 5, 5), ("Spider", 3, 3), ("Bat", 2, 2)]))

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    sec = _find_section(data, "hierro")
    assert sec is not None

    rat = _find_animal_in_section(sec, 1)  # Rata ordinal 1
    assert rat is not None
    # n_valid=1 (un gap con present=5)
    assert rat["max_present"] == 5, f"Esperaba max_present=5, got {rat['max_present']}"


# ---------------------------------------------------------------------------
# T-TD37 — max_present todos derrota: null
# ---------------------------------------------------------------------------

def test_TD37_max_present_all_defeat_is_null(client):
    """T-TD37: todos los reportes son derrota (present=NULL) → max_present=null (EC-TD28)."""
    # Oasis madera: primer reporte con present>0 para que tenga tipo (necesario para clasificar)
    _save(client, _make_report(_OX_MADERA, _OY_MADERA, "01.06.26, 10:00:00",
                                [("Wolf", 3, 3), ("Wild boar", 2, 2), ("Bear", 1, 1)]))
    # Segundo reporte: derrota → present=NULL en todos → gap 4h → bin 240
    _save(client, _make_report(_OX_MADERA, _OY_MADERA, "01.06.26, 14:00:00",
                                [("Wolf", None, None), ("Wild boar", None, None), ("Bear", None, None)],
                                defeat=True))

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    sec = _find_section(data, "madera")
    assert sec is not None

    # El único gap en la ventana es una derrota → n_valid=0 → max_present=null
    wolf = _find_animal_in_section(sec, 6)  # Lobo ordinal 6
    if wolf is not None:
        assert wolf["max_present"] is None, (
            f"Esperaba max_present=null (derrota), got {wolf['max_present']}"
        )
        assert wolf["n_valid"] == 0


# ---------------------------------------------------------------------------
# T-TD38 — max_present excluye NULL (present=[3, null, 5] → max=5)
# ---------------------------------------------------------------------------

def test_TD38_max_present_excludes_null(client):
    """T-TD38: present=[3, null, 5] → max_present=5 (el NULL se excluye, RN-TD20).
    3 reportes del oasis: 2 victorias + 1 derrota intermedia.
    """
    # Primer reporte (sin gap)
    _save(client, _make_report(_OX_HIERRO, _OY_HIERRO, "01.06.26, 06:00:00",
                                [("Rat", 3, 3), ("Spider", 1, 1), ("Bat", 1, 1)]))
    # Segundo reporte: derrota → present=NULL; gap = 4h → bin 240
    _save(client, _make_report(_OX_HIERRO, _OY_HIERRO, "01.06.26, 10:00:00",
                                [("Rat", None, None), ("Spider", None, None), ("Bat", None, None)],
                                defeat=True))
    # Tercer reporte: victoria con present=5; gap = 4h → bin 240
    _save(client, _make_report(_OX_HIERRO, _OY_HIERRO, "01.06.26, 14:00:00",
                                [("Rat", 5, 5), ("Spider", 2, 2), ("Bat", 3, 3)]))

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    sec = _find_section(data, "hierro")
    assert sec is not None

    rat = _find_animal_in_section(sec, 1)
    assert rat is not None
    # n_total=2 (2 gaps: derrota + victoria), n_valid=1 (solo la victoria present=5)
    # max_present = max([5]) = 5 (el NULL y el present=3 del reporte anterior no están
    # en este gap — el gap del tercer reporte tiene present=5)
    assert rat["max_present"] == 5, (
        f"Esperaba max_present=5 (NULL excluido), got {rat['max_present']}"
    )
    assert rat["n_valid"] >= 1


# ---------------------------------------------------------------------------
# T-TD39 — avg_bounty: denominador incluye derrotas con bounty=0
# ---------------------------------------------------------------------------

def test_TD39_avg_bounty_includes_defeats(client):
    """T-TD39: 2 victorias con iron=300 + 1 derrota con iron=0 → avg_bounty.iron=200.
    Denominador = 3 (n_reports_in_section incluye derrota). RN-TD22.
    """
    # Oasis hierro — primer reporte (sin gap, solo inicializa la línea temporal)
    _save(client, _make_report(_OX_HIERRO, _OY_HIERRO, "01.06.26, 06:00:00",
                                [("Rat", 2, 2), ("Spider", 1, 1), ("Bat", 1, 1)],
                                bounty="0  0  300  0"))
    # Segundo reporte: victoria con iron=300; gap=4h → bin 240
    _save(client, _make_report(_OX_HIERRO, _OY_HIERRO, "01.06.26, 10:00:00",
                                [("Rat", 3, 3), ("Spider", 2, 2), ("Bat", 2, 2)],
                                bounty="0  0  300  0"))
    # Tercer reporte: victoria con iron=300; gap=4h → bin 240
    _save(client, _make_report(_OX_HIERRO, _OY_HIERRO, "01.06.26, 14:00:00",
                                [("Rat", 4, 4), ("Spider", 2, 2), ("Bat", 3, 3)],
                                bounty="0  0  300  0"))
    # Cuarto reporte: derrota con bounty=0; gap=4h → bin 240
    _save(client, _make_report(_OX_HIERRO, _OY_HIERRO, "01.06.26, 18:00:00",
                                [("Rat", None, None), ("Spider", None, None), ("Bat", None, None)],
                                defeat=True))

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    sec = _find_section(data, "hierro")
    assert sec is not None
    assert sec["n_reports_in_section"] == 3, (
        f"Esperaba 3 gaps en hierro (2 victorias + 1 derrota), got {sec['n_reports_in_section']}"
    )
    avg_b = sec["avg_bounty"]
    # 2 victorias iron=300 + 1 derrota iron=0 → sum=600, n=3 → avg=200
    assert avg_b["iron"] == 200, f"Esperaba avg_bounty.iron=200, got {avg_b['iron']}"


# ---------------------------------------------------------------------------
# T-TD40 — avg_bounty.total != suma de medias individuales (por redondeo)
# ---------------------------------------------------------------------------

def test_TD40_avg_bounty_total_is_not_sum_of_averages(client):
    """T-TD40: avg_bounty.total se calcula sobre la suma por reporte (RN-TD23),
    no como suma de los 4 campos individuales (puede diferir en ±1 por redondeo).
    3 reportes: (1,1,1,1), (2,2,2,2), (1,1,2,2).
      Medias individuales: wood=round(4/3)=1, clay=round(4/3)=1, iron=round(5/3)=2, crop=round(5/3)=2
      Suma de medias = 6.
      Totales por reporte: (4,8,6) → media = round(18/3) = 6.
      En este caso coinciden, pero el campo total se calcula correctamente por la ruta
      directa (suma de totales por reporte / n), no sumando los campos individuales.
    """
    # Primer reporte — sin gap
    _save(client, _make_report(_OX_HIERRO, _OY_HIERRO, "01.06.26, 06:00:00",
                                [("Rat", 2, 2), ("Spider", 1, 1), ("Bat", 1, 1)],
                                bounty="1  1  1  1"))
    # Segundo reporte — gap 4h → bin 240, bounty (2,2,2,2)
    _save(client, _make_report(_OX_HIERRO, _OY_HIERRO, "01.06.26, 10:00:00",
                                [("Rat", 3, 3), ("Spider", 2, 2), ("Bat", 2, 2)],
                                bounty="2  2  2  2"))
    # Tercer reporte — gap 4h → bin 240, bounty (1,1,2,2)
    _save(client, _make_report(_OX_HIERRO, _OY_HIERRO, "01.06.26, 14:00:00",
                                [("Rat", 4, 4), ("Spider", 2, 2), ("Bat", 3, 3)],
                                bounty="1  1  2  2"))
    # Cuarto reporte — gap 4h → bin 240, bounty (2,2,2,2)
    _save(client, _make_report(_OX_HIERRO, _OY_HIERRO, "01.06.26, 18:00:00",
                                [("Rat", 3, 3), ("Spider", 1, 1), ("Bat", 2, 2)],
                                bounty="2  2  2  2"))

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    sec = _find_section(data, "hierro")
    assert sec is not None

    avg_b = sec["avg_bounty"]
    # Verificar que avg_bounty.total es el resultado correcto:
    # total_per_report = [w+c+i+cr por reporte en la ventana] → media
    # Los 3 gaps caen en bin 240: rep2=(2,2,2,2)→total=8, rep3=(1,1,2,2)→total=6, rep4=(2,2,2,2)→total=8
    # avg_total = round((8+6+8)/3) = round(22/3) = round(7.33) = 7
    assert avg_b["total"] == 7, (
        f"Esperaba avg_bounty.total=7 (media de totales por reporte), got {avg_b['total']}"
    )


# ---------------------------------------------------------------------------
# T-TD41 — avg_bounty en sección vacía: todos a 0 (no null)
# ---------------------------------------------------------------------------

def test_TD41_avg_bounty_empty_section_is_zero(client):
    """T-TD41: sección vacía → avg_bounty todos a 0 (EC-TD33). No null."""
    # BD vacía → todas las secciones vacías
    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    for sec in data["types"]:
        ab = sec["avg_bounty"]
        assert ab["wood"] == 0
        assert ab["clay"] == 0
        assert ab["iron"] == 0
        assert ab["crop"] == 0
        assert ab["total"] == 0
        # No null
        assert ab["wood"] is not None
        assert ab["total"] is not None


# ---------------------------------------------------------------------------
# T-TD42 — avg_bounty no multiplicado por número de animales del JOIN
# ---------------------------------------------------------------------------

def test_TD42_avg_bounty_not_multiplied_by_animals(client):
    """T-TD42: 1 reporte con 3 animales e iron=500 → avg_bounty.iron=500 (no 1500).
    CRÍTICO: el botín NO debe acumularse N veces por el JOIN con attack_report_animals
    (RN-TD25). Solo UNA vez por report_id distinto.
    """
    # Primer reporte del oasis (sin gap)
    _save(client, _make_report(_OX_HIERRO, _OY_HIERRO, "01.06.26, 10:00:00",
                                [("Rat", 2, 2), ("Spider", 1, 1), ("Bat", 1, 1)],
                                bounty="0  0  500  0"))
    # Segundo reporte: 3 animales, iron=500; gap=4h → bin 240
    _save(client, _make_report(_OX_HIERRO, _OY_HIERRO, "01.06.26, 14:00:00",
                                [("Rat", 4, 4), ("Spider", 2, 2), ("Bat", 3, 3)],
                                bounty="0  0  500  0"))

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    sec = _find_section(data, "hierro")
    assert sec is not None
    assert sec["n_reports_in_section"] == 1, "Solo 1 gap en bin 240"

    avg_b = sec["avg_bounty"]
    # 1 reporte en la sección con iron=500 → avg_bounty.iron = round(500/1) = 500
    # (no 1500 como sería si se multiplicara por los 3 animales del JOIN)
    assert avg_b["iron"] == 500, (
        f"CRÍTICO: avg_bounty.iron={avg_b['iron']} en lugar de 500. "
        "Posible doble conteo del botín por el JOIN con attack_report_animals."
    )


# ---------------------------------------------------------------------------
# T-TD43 — total_animals: regla TODO-O-NADA
# ---------------------------------------------------------------------------

def test_TD43_total_animals_any_null_excludes_report(client):
    """T-TD43: reporte con un animal present=NULL se excluye de n_valid de total_animals
    pero cuenta en n_total (regla TODO-O-NADA, RN-TD21 / EC-TD29).
    """
    # Primer reporte del oasis (sin gap)
    _save(client, _make_report(_OX_HIERRO, _OY_HIERRO, "01.06.26, 06:00:00",
                                [("Rat", 2, 2), ("Spider", 1, 1), ("Bat", 1, 1)]))
    # Segundo reporte: DERROTA (todos present=NULL); gap=4h → bin 240
    _save(client, _make_report(_OX_HIERRO, _OY_HIERRO, "01.06.26, 10:00:00",
                                [("Rat", None, None), ("Spider", None, None), ("Bat", None, None)],
                                defeat=True))
    # Tercer reporte: victoria (todos present no nulos); gap=4h → bin 240
    _save(client, _make_report(_OX_HIERRO, _OY_HIERRO, "01.06.26, 14:00:00",
                                [("Rat", 3, 3), ("Spider", 2, 2), ("Bat", 2, 2)]))

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    sec = _find_section(data, "hierro")
    assert sec is not None

    ta = sec["total_animals"]
    # n_total = 2 (2 gaps en la ventana: derrota + victoria)
    # n_valid = 1 (solo la victoria: Rata=3, Araña=2, Murciélago=2 → total=7)
    assert ta["n_total"] == 2, f"Esperaba n_total=2, got {ta['n_total']}"
    assert ta["n_valid"] == 1, f"Esperaba n_valid=1, got {ta['n_valid']}"
    # avg = 7.0 (un solo reporte válido con total=7)
    assert ta["avg"] == 7.0, f"Esperaba avg=7.0, got {ta['avg']}"
    assert ta["max"] == 7, f"Esperaba max=7, got {ta['max']}"
    assert ta["mode"] == [7], f"Esperaba mode=[7], got {ta['mode']}"


# ---------------------------------------------------------------------------
# T-TD44 — total_animals: todos derrota → avg null, mode [], max null
# ---------------------------------------------------------------------------

def test_TD44_total_animals_all_defeats(client):
    """T-TD44: todos los reportes de la sección son derrota → total_animals con
    n_valid=0, avg=null, mode=[], max=null (EC-TD28).
    """
    # Oasis madera: primer reporte con present>0 para establecer tipo
    _save(client, _make_report(_OX_MADERA, _OY_MADERA, "01.06.26, 10:00:00",
                                [("Wolf", 3, 3), ("Wild boar", 2, 2), ("Bear", 1, 1)]))
    # Segundo reporte: derrota → gap 4h → bin 240
    _save(client, _make_report(_OX_MADERA, _OY_MADERA, "01.06.26, 14:00:00",
                                [("Wolf", None, None), ("Wild boar", None, None), ("Bear", None, None)],
                                defeat=True))

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    sec = _find_section(data, "madera")
    assert sec is not None
    assert sec["n_reports_in_section"] == 1

    ta = sec["total_animals"]
    assert ta["n_total"] == 1
    assert ta["n_valid"] == 0
    assert ta["avg"] is None
    assert ta["mode"] == []
    assert ta["max"] is None


# ---------------------------------------------------------------------------
# T-TD45 — total_animals: n_total == n_reports_in_section (invariante)
# ---------------------------------------------------------------------------

def test_TD45_total_animals_n_total_equals_n_reports(client):
    """T-TD45: total_animals.n_total siempre igual a n_reports_in_section (invariante)."""
    _insert_hierro_reports_4h(client)   # 3 gaps en bin 240

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    sec = _find_section(data, "hierro")
    assert sec is not None

    assert sec["total_animals"]["n_total"] == sec["n_reports_in_section"], (
        f"Invariante: total_animals.n_total={sec['total_animals']['n_total']} "
        f"!= n_reports_in_section={sec['n_reports_in_section']}"
    )


# ---------------------------------------------------------------------------
# T-TD46 — oasis_coords: ordenadas (y ASC, x ASC) y deduplicadas
# ---------------------------------------------------------------------------

def test_TD46_oasis_coords_ordered_and_deduplicated(client):
    """T-TD46: dos oasis hierro con coords distintas → oasis_coords contiene ambos
    ordenados (y ASC, x ASC) y sin duplicados (EC-TD35, RN-TD24).
    """
    # Oasis 1 hierro: (-70, 73)
    _save(client, _make_report(-70, 73, "01.06.26, 10:00:00",
                                [("Rat", 3, 3), ("Spider", 1, 1), ("Bat", 2, 2)]))
    _save(client, _make_report(-70, 73, "01.06.26, 14:00:00",
                                [("Rat", 5, 5), ("Spider", 2, 2), ("Bat", 3, 3)]))

    # Oasis 2 hierro: (-71, 72) — y más pequeño, debe aparecer primero
    _save(client, _make_report(-71, 72, "01.06.26, 10:00:00",
                                [("Rat", 2, 2), ("Spider", 1, 1), ("Bat", 1, 1)]))
    _save(client, _make_report(-71, 72, "01.06.26, 14:00:00",
                                [("Rat", 4, 4), ("Spider", 3, 3), ("Bat", 2, 2)]))

    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)
    sec = _find_section(data, "hierro")
    assert sec is not None

    coords = sec["oasis_coords"]
    # Exactamente 2 coordenadas, sin duplicados
    assert len(coords) == 2, f"Esperaba 2 oasis_coords, got {len(coords)}: {coords}"

    # Ordenados (y ASC, x ASC): (-71,72) < (-70,73) por y
    assert coords[0] == {"x": -71, "y": 72}, (
        f"Primer coord debería ser (-71,72), got {coords[0]}"
    )
    assert coords[1] == {"x": -70, "y": 73}, (
        f"Segundo coord debería ser (-70,73), got {coords[1]}"
    )

    # Verificar que son enteros, no strings
    assert isinstance(coords[0]["x"], int)
    assert isinstance(coords[0]["y"], int)


# ---------------------------------------------------------------------------
# T-TD47 — campos v4 presentes en secciones vacías
# ---------------------------------------------------------------------------

def test_TD47_v4_fields_present_in_empty_sections(client):
    """T-TD47: las secciones vacías (n_reports_in_section=0) contienen los campos v4
    con sus valores de 'vacío' correctos (EC-TD33):
      oasis_coords=[], avg_bounty todos a 0, total_animals con avg/max=null/n_valid=0/n_total=0.
    """
    # BD vacía: todas las secciones vacías
    data = _get_td(client, interval_minutes=240, lang=_LANG_ES)

    for sec in data["types"]:
        assert sec["n_reports_in_section"] == 0, f"BD vacía: sección {sec['oasis_type']} no vacía"

        # oasis_coords: []
        assert "oasis_coords" in sec, f"Falta oasis_coords en sección {sec['oasis_type']}"
        assert sec["oasis_coords"] == [], (
            f"oasis_coords debe ser [] en sección vacía {sec['oasis_type']}, got {sec['oasis_coords']}"
        )

        # avg_bounty: todos a 0
        assert "avg_bounty" in sec, f"Falta avg_bounty en sección {sec['oasis_type']}"
        ab = sec["avg_bounty"]
        for field in ("wood", "clay", "iron", "crop", "total"):
            assert ab[field] == 0, (
                f"avg_bounty.{field} debe ser 0 en sección vacía {sec['oasis_type']}, got {ab[field]}"
            )

        # total_animals: avg=null, mode=[], max=null, n_valid=0, n_total=0
        assert "total_animals" in sec, f"Falta total_animals en sección {sec['oasis_type']}"
        ta = sec["total_animals"]
        assert ta["avg"] is None, f"total_animals.avg debe ser null en sección vacía"
        assert ta["mode"] == [], f"total_animals.mode debe ser [] en sección vacía"
        assert ta["max"] is None, f"total_animals.max debe ser null en sección vacía"
        assert ta["n_valid"] == 0
        assert ta["n_total"] == 0


# ---------------------------------------------------------------------------
# T-TD48 — oasis_coords vacío en sección sin gaps en la ventana
# ---------------------------------------------------------------------------

def test_TD48_oasis_coords_empty_when_no_gaps_in_window(client):
    """T-TD48: oasis con tipo hierro pero sin gaps en el bin solicitado →
    oasis_coords=[] en esa sección (EC-TD26 + EC-TD33).
    """
    # Oasis hierro con gap de 4h (bin 240), pero pediremos bin 6
    _save(client, _make_report(_OX_HIERRO, _OY_HIERRO, "01.06.26, 10:00:00",
                                [("Rat", 3, 3), ("Spider", 1, 1), ("Bat", 2, 2)]))
    _save(client, _make_report(_OX_HIERRO, _OY_HIERRO, "01.06.26, 14:00:00",
                                [("Rat", 5, 5), ("Spider", 2, 2), ("Bat", 3, 3)]))

    # Pedimos bin 6 → gap de 14400s no cae en [360,420)
    data = _get_td(client, interval_minutes=6, lang=_LANG_ES)
    sec = _find_section(data, "hierro")
    assert sec is not None
    assert sec["n_reports_in_section"] == 0
    assert sec["oasis_coords"] == [], (
        f"oasis_coords debe ser [] si el oasis no tiene gaps en la ventana, "
        f"got {sec['oasis_coords']}"
    )
    assert sec["animals"] == []
