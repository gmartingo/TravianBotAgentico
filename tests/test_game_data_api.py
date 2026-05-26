"""
Tests de API para los endpoints de datos de juego.

GET /catalog/troops/{tribe}/stats  — stats numéricos de tropas
GET /catalog/icons                 — metadatos de iconos

Los tests usan TestClient con lifespan para disparar startup (GameDataSQLiteAdapter
se inicializa con BD en memoria via override del estado de la app).

Convención de Accept-Language:
  - /catalog/troops/{tribe}/stats → OPCIONAL:
      sin cabecera → 200 con language multi-idioma.
      idioma soportado → 200 con language de una clave.
      idioma no soportado → 400.
  - /catalog/icons → OBLIGATORIA (el campo language no existe en iconos,
      pero la cabecera se mantiene obligatoria para coherencia futura).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from adapters.api.main import app
from adapters.db.game_data_sqlite_adapter import GameDataSQLiteAdapter
from core.entities.tribe import Tribe


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    """
    Cliente de test con lifespan activado.
    El lifespan de main.py inicializa game_data_port con BD real (travian_bot.db).
    Para tests que necesiten datos, se inyecta el mock directamente en app.state.
    """
    with TestClient(app) as c:
        yield c


def _make_mock_game_data_port(troop_rows=None, icon_rows=None):
    """
    Crea un mock de GameDataPort para inyectar en app.state.
    troop_rows: lista de dicts para get_all_troop_stats
    icon_rows: lista de dicts para list_icons
    """
    mock = MagicMock()
    mock.get_all_troop_stats = AsyncMock(return_value=troop_rows or [])
    mock.list_icons = AsyncMock(return_value=icon_rows or [])
    return mock


def _troop_row_with_icon(ordinal: int = 1) -> dict:
    return {
        "server_version": "1.45",
        "tribe": "romans",
        "ordinal": ordinal,
        "is_playable": True,
        "attack": 40,
        "def_infantry": 35,
        "def_cavalry": 50,
        "speed": 6,
        "carry": 50,
        "cost_wood": 120,
        "cost_clay": 100,
        "cost_iron": 150,
        "cost_crop": 30,
        "cost_sum": 400,
        "upkeep": 1,
        "train_time_s": 1600,
        "icon_id": f"romans_{ordinal}",
    }


def _troop_row_with_null_attack(ordinal: int = 1) -> dict:
    row = _troop_row_with_icon(ordinal)
    row["attack"] = None
    row["icon_id"] = None
    return row


def _icon_row(icon_id: str = "romans_1", icon_type: str = "troop") -> dict:
    return {
        "icon_id": icon_id,
        "icon_type": icon_type,
        "tribe": "romans" if icon_type == "troop" else None,
        "ordinal": 1 if icon_type == "troop" else None,
        "stat_name": None if icon_type == "troop" else "attack",
        "file_path": f"assets/icons/{icon_id}.png",
        "file_size_bytes": 1024,
        "width_px": 24,
        "height_px": 24,
        "scraped_at": "2026-05-24T00:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# Tests — GET /catalog/troops/{tribe}/stats — Accept-Language
# ---------------------------------------------------------------------------


def test_stats_valid_lang(client):
    """200 con Accept-Language válido y datos en BD (mock)."""
    mock_port = _make_mock_game_data_port(troop_rows=[_troop_row_with_icon(1)])
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/troops/romans/stats",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["tribe"] == "romans"
        assert body["server_version"] == "1.45"
        assert len(body["troops"]) == 1
    finally:
        app.state.game_data_port = original


def test_stats_missing_lang_devuelve_200_todos_idiomas(client):
    """Sin Accept-Language → 200; language de cada tropa tiene múltiples idiomas."""
    mock_port = _make_mock_game_data_port(troop_rows=[_troop_row_with_icon(1)])
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get("/catalog/troops/romans/stats")
        assert response.status_code == 200
        troops = response.json()["troops"]
        assert len(troops) == 1
        language = troops[0]["language"]
        # El catálogo real tiene 25 idiomas; al menos es y en deben aparecer
        assert len(language) > 1, (
            f"Se esperaban múltiples idiomas pero language tiene solo: {language}"
        )
        assert "es" in language
        assert "en" in language
    finally:
        app.state.game_data_port = original


def test_stats_unsupported_lang(client):
    """400 si el idioma no está soportado (zh no está en los 25)."""
    response = client.get(
        "/catalog/troops/romans/stats",
        headers={"Accept-Language": "zh"},
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Tests nuevos — 25 idiomas + ?lang= + precedencia + Vary (stats)
# ---------------------------------------------------------------------------


def test_stats_it_ahora_valido(client):
    """'it' ahora es uno de los 25 soportados → 200 (antes 400 con SUPPORTED=5)."""
    mock_port = _make_mock_game_data_port(troop_rows=[_troop_row_with_icon(1)])
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/troops/romans/stats",
            headers={"Accept-Language": "it"},
        )
        assert response.status_code == 200
    finally:
        app.state.game_data_port = original


def test_stats_lang_query_valido_devuelve_un_idioma(client):
    """?lang=en → 200 con language de una sola clave."""
    mock_port = _make_mock_game_data_port(troop_rows=[_troop_row_with_icon(1)])
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get("/catalog/troops/romans/stats?lang=en")
        assert response.status_code == 200
        troops = response.json()["troops"]
        assert len(troops) == 1
        assert len(troops[0]["language"]) == 1
    finally:
        app.state.game_data_port = original


def test_stats_lang_query_it_valido(client):
    """?lang=it → 200 (it es uno de los 25)."""
    mock_port = _make_mock_game_data_port(troop_rows=[_troop_row_with_icon(1)])
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get("/catalog/troops/romans/stats?lang=it")
        assert response.status_code == 200
    finally:
        app.state.game_data_port = original


def test_stats_lang_query_xx_invalido_devuelve_400(client):
    """?lang=xx (no existe en los 25) → 400."""
    response = client.get("/catalog/troops/romans/stats?lang=xx")
    assert response.status_code == 400


def test_stats_lang_query_zz_invalido_devuelve_400(client):
    """?lang=zz (no existe en los 25) → 400."""
    response = client.get("/catalog/troops/romans/stats?lang=zz")
    assert response.status_code == 400


def test_stats_precedencia_lang_query_sobre_header(client):
    """?lang=en + Accept-Language: es → gana ?lang= → devuelve un solo idioma."""
    mock_port = _make_mock_game_data_port(troop_rows=[_troop_row_with_icon(1)])
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/troops/romans/stats?lang=en",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        troops = response.json()["troops"]
        assert len(troops[0]["language"]) == 1
    finally:
        app.state.game_data_port = original


def test_stats_sin_lang_query_ni_header_devuelve_todos(client):
    """Sin ?lang= ni Accept-Language → language con múltiples idiomas."""
    mock_port = _make_mock_game_data_port(troop_rows=[_troop_row_with_icon(1)])
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get("/catalog/troops/romans/stats")
        assert response.status_code == 200
        troops = response.json()["troops"]
        assert len(troops[0]["language"]) > 1
    finally:
        app.state.game_data_port = original


def test_stats_vary_header_presente(client):
    """La respuesta de stats incluye Vary: Accept-Language."""
    mock_port = _make_mock_game_data_port(troop_rows=[_troop_row_with_icon(1)])
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/troops/romans/stats",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        vary = response.headers.get("vary", "")
        assert "Accept-Language" in vary, f"Vary esperado, obtenido: '{vary}'"
    finally:
        app.state.game_data_port = original


def test_stats_vary_header_sin_accept_language(client):
    """La respuesta incluye Vary: Accept-Language incluso sin cabecera."""
    mock_port = _make_mock_game_data_port(troop_rows=[_troop_row_with_icon(1)])
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get("/catalog/troops/romans/stats")
        assert response.status_code == 200
        vary = response.headers.get("vary", "")
        assert "Accept-Language" in vary
    finally:
        app.state.game_data_port = original


# ---------------------------------------------------------------------------
# Tests — GET /catalog/troops/{tribe}/stats — funcionales
# ---------------------------------------------------------------------------


def test_stats_invalid_tribe(client):
    """422 si tribe no es un valor válido del enum Tribe."""
    response = client.get(
        "/catalog/troops/unknown/stats",
        headers={"Accept-Language": "es"},
    )
    assert response.status_code == 422


def test_stats_tribe_no_data(client):
    """404 si la tribu no tiene stats en la BD (mock devuelve lista vacía)."""
    mock_port = _make_mock_game_data_port(troop_rows=[])
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/troops/romans/stats",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 404
        detail = response.json()["detail"]
        # El detail incluye la tribe y el server_version para facilitar debug
        assert "romans" in detail
        assert "1.45" in detail
    finally:
        app.state.game_data_port = original


def test_stats_null_attack(client):
    """Tropa con attack=NULL en BD → 'attack': null en JSON (EC-01 / RN-07)."""
    mock_port = _make_mock_game_data_port(troop_rows=[_troop_row_with_null_attack(1)])
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/troops/romans/stats",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        troop = response.json()["troops"][0]
        assert troop["attack"] is None
    finally:
        app.state.game_data_port = original


def test_stats_icon_url_present(client):
    """Tropa con icon_id en BD → icon_url con ruta correcta."""
    mock_port = _make_mock_game_data_port(troop_rows=[_troop_row_with_icon(1)])
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/troops/romans/stats",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        troop = response.json()["troops"][0]
        assert troop["icon_url"] == "/static/icons/romans_1.png"
    finally:
        app.state.game_data_port = original


def test_stats_icon_url_null(client):
    """Tropa sin icon_id en BD → icon_url = null."""
    mock_port = _make_mock_game_data_port(troop_rows=[_troop_row_with_null_attack(1)])
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/troops/romans/stats",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        troop = response.json()["troops"][0]
        assert troop["icon_url"] is None
    finally:
        app.state.game_data_port = original


def test_stats_response_structure(client):
    """Verifica la estructura completa del response (campos requeridos)."""
    mock_port = _make_mock_game_data_port(troop_rows=[_troop_row_with_icon(1)])
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/troops/romans/stats",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        body = response.json()
        # Campos del wrapper
        assert "tribe" in body
        assert "server_version" in body
        assert "troops" in body
        # Campos de cada tropa
        troop = body["troops"][0]
        required_fields = [
            "ordinal", "key", "is_playable", "language",
            "attack", "def_infantry", "def_cavalry", "speed", "carry",
            "cost_wood", "cost_clay", "cost_iron", "cost_crop", "cost_sum",
            "upkeep", "train_time_s", "icon_url",
        ]
        for field in required_fields:
            assert field in troop, f"Campo '{field}' falta en la respuesta de tropa"
    finally:
        app.state.game_data_port = original


def test_stats_cache_control_header(client):
    """El middleware añade Cache-Control: public, max-age=3600 para rutas /catalog/."""
    mock_port = _make_mock_game_data_port(troop_rows=[_troop_row_with_icon(1)])
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/troops/romans/stats",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        assert response.headers.get("cache-control") == "public, max-age=3600"
    finally:
        app.state.game_data_port = original


def test_stats_security_headers(client):
    """Las cabeceras mínimas de seguridad están presentes."""
    mock_port = _make_mock_game_data_port(troop_rows=[_troop_row_with_icon(1)])
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/troops/romans/stats",
            headers={"Accept-Language": "es"},
        )
        assert response.headers.get("x-request-id")
        assert response.headers.get("x-api-version")
        assert response.headers.get("x-content-type-options") == "nosniff"
        assert response.headers.get("x-frame-options") == "DENY"
    finally:
        app.state.game_data_port = original


def test_stats_tribe_no_data_includes_server_version(client):
    """El 404 de tribu sin datos incluye server_version en el detail."""
    mock_port = _make_mock_game_data_port(troop_rows=[])
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/troops/nature/stats?server_version=2.45",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 404
        assert "2.45" in response.json()["detail"]
    finally:
        app.state.game_data_port = original


# ---------------------------------------------------------------------------
# Tests — GET /catalog/icons — Accept-Language
# ---------------------------------------------------------------------------


def test_icons_missing_lang(client):
    """400 si Accept-Language está ausente."""
    response = client.get("/catalog/icons")
    assert response.status_code == 400


def test_icons_unsupported_lang(client):
    """400 si el idioma no está soportado."""
    response = client.get(
        "/catalog/icons",
        headers={"Accept-Language": "zh"},
    )
    assert response.status_code == 400


def test_icons_invalid_type(client):
    """422 si icon_type es un valor fuera del Literal permitido."""
    response = client.get(
        "/catalog/icons?icon_type=invalid_type",
        headers={"Accept-Language": "es"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Tests — GET /catalog/icons — funcionales
# ---------------------------------------------------------------------------


def test_icons_no_filter(client):
    """200 con lista de iconos sin filtro."""
    mock_port = _make_mock_game_data_port(icon_rows=[
        _icon_row("romans_1", "troop"),
        _icon_row("stat_attack", "stat"),
    ])
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/icons",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        body = response.json()
        assert "icons" in body
        assert len(body["icons"]) == 2
    finally:
        app.state.game_data_port = original


def test_icons_filter_type_troop(client):
    """Solo iconos de tipo 'troop' cuando se filtra por icon_type=troop."""
    mock_port = _make_mock_game_data_port(icon_rows=[_icon_row("romans_1", "troop")])
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/icons?icon_type=troop",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        icons = response.json()["icons"]
        assert len(icons) == 1
        assert icons[0]["icon_type"] == "troop"
    finally:
        app.state.game_data_port = original


def test_icons_filter_tribe(client):
    """Filtra por tribu correctamente."""
    mock_port = _make_mock_game_data_port(icon_rows=[_icon_row("romans_1", "troop")])
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/icons?tribe=romans",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        icons = response.json()["icons"]
        assert all(i["tribe"] == "romans" for i in icons)
    finally:
        app.state.game_data_port = original


def test_icons_empty_result_is_200_not_404(client):
    """Lista vacía devuelve 200, no 404 (semántica REST para colecciones)."""
    mock_port = _make_mock_game_data_port(icon_rows=[])
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/icons?icon_type=upgrade",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        assert response.json()["icons"] == []
    finally:
        app.state.game_data_port = original


def test_icons_url_field_correct(client):
    """El campo url de cada icono tiene la ruta /static/icons/{icon_id}.png."""
    mock_port = _make_mock_game_data_port(icon_rows=[_icon_row("stat_attack", "stat")])
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/icons",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        icon = response.json()["icons"][0]
        assert icon["url"] == "/static/icons/stat_attack.png"
    finally:
        app.state.game_data_port = original


def test_icons_response_structure(client):
    """Verifica la estructura del response de iconos."""
    mock_port = _make_mock_game_data_port(icon_rows=[_icon_row("romans_1", "troop")])
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/icons",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        icon = response.json()["icons"][0]
        required_fields = ["icon_id", "icon_type", "tribe", "ordinal", "stat_name", "url", "width_px", "height_px"]
        for field in required_fields:
            assert field in icon, f"Campo '{field}' falta en el response de icono"
    finally:
        app.state.game_data_port = original


def test_icons_stat_has_null_tribe_ordinal(client):
    """Iconos de stat tienen tribe=null y ordinal=null."""
    mock_port = _make_mock_game_data_port(icon_rows=[_icon_row("stat_attack", "stat")])
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/icons",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        icon = response.json()["icons"][0]
        assert icon["tribe"] is None
        assert icon["ordinal"] is None
        assert icon["stat_name"] == "attack"
    finally:
        app.state.game_data_port = original


def test_icons_cache_control_header(client):
    """Cache-Control: public, max-age=3600 en respuesta de /catalog/icons."""
    mock_port = _make_mock_game_data_port(icon_rows=[])
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/icons",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        assert response.headers.get("cache-control") == "public, max-age=3600"
    finally:
        app.state.game_data_port = original


# ---------------------------------------------------------------------------
# Helpers — datos de mejora
# ---------------------------------------------------------------------------


def _upgrade_rows_legionario() -> list[dict]:
    """
    Filas de mejora simuladas para un Legionario romano (ordinal=1).
    Solo attack y def_cavalry (las columnas que aplican).
    Niveles 1 y 2.
    """
    base = {
        "server_version": "1.45",
        "tribe": "romans",
        "ordinal": 1,
        "cost_wood": 940,
        "cost_clay": 800,
        "cost_iron": 1250,
        "cost_crop": 370,
        "cost_sum": 3360,
        "upgrade_time_s": 6846,   # 1:54:06
    }
    return [
        {**base, "level": 1, "stat_name": "attack",      "stat_value": 40.58},
        {**base, "level": 1, "stat_name": "def_cavalry",  "stat_value": 50.65},
        {**base, "level": 2, "stat_name": "attack",      "stat_value": 42.1,
         "cost_wood": 1100, "cost_clay": 950, "cost_iron": 1450, "cost_crop": 430,
         "cost_sum": 3930, "upgrade_time_s": 7200},
        {**base, "level": 2, "stat_name": "def_cavalry",  "stat_value": 52.3,
         "cost_wood": 1100, "cost_clay": 950, "cost_iron": 1450, "cost_crop": 430,
         "cost_sum": 3930, "upgrade_time_s": 7200},
    ]


# ---------------------------------------------------------------------------
# Tests — GET /catalog/troops/{tribe}/{ordinal}/upgrades
# ---------------------------------------------------------------------------


def test_upgrades_200_estructura_agrupada(client):
    """
    200 con datos: los niveles se agrupan correctamente.
    Nivel 1 tiene stats {attack, def_cavalry}.
    Nivel 2 tiene stats {attack, def_cavalry}.
    """
    mock_port = _make_mock_game_data_port()
    mock_port.get_troop_upgrades = AsyncMock(return_value=_upgrade_rows_legionario())
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/troops/romans/1/upgrades",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        body = response.json()

        assert body["tribe"] == "romans"
        assert body["ordinal"] == 1
        assert body["server_version"] == "1.45"
        assert "levels" in body

        levels = body["levels"]
        assert len(levels) == 2  # niveles 1 y 2

        # Nivel 1
        lvl1 = next(lv for lv in levels if lv["level"] == 1)
        assert lvl1["cost_wood"] == 940
        assert lvl1["cost_clay"] == 800
        assert lvl1["cost_iron"] == 1250
        assert lvl1["cost_crop"] == 370
        assert lvl1["cost_sum"] == 3360
        assert lvl1["upgrade_time_s"] == 6846
        assert lvl1["stats"]["attack"] == pytest.approx(40.58)
        assert lvl1["stats"]["def_cavalry"] == pytest.approx(50.65)
        assert "def_infantry" not in lvl1["stats"]  # no aplica a esta unidad

        # Nivel 2
        lvl2 = next(lv for lv in levels if lv["level"] == 2)
        assert lvl2["stats"]["attack"] == pytest.approx(42.1)
    finally:
        app.state.game_data_port = original


def test_upgrades_404_sin_datos(client):
    """404 si no hay datos de mejora para esa tropa (mock devuelve lista vacía)."""
    mock_port = _make_mock_game_data_port()
    mock_port.get_troop_upgrades = AsyncMock(return_value=[])
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/troops/romans/1/upgrades",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 404
        detail = response.json()["detail"]
        assert "romans" in detail
        assert "1" in detail  # ordinal
        assert "1.45" in detail  # server_version
    finally:
        app.state.game_data_port = original


def test_upgrades_tribu_invalida_422(client):
    """422 si tribe no es un valor válido del enum Tribe."""
    response = client.get(
        "/catalog/troops/unknown/1/upgrades",
        headers={"Accept-Language": "es"},
    )
    assert response.status_code == 422


def test_upgrades_sin_accept_language_200(client):
    """
    Sin Accept-Language → 200 (a diferencia de /catalog/icons, este endpoint
    no tiene texto localizado: Accept-Language es OPCIONAL aquí).
    """
    mock_port = _make_mock_game_data_port()
    mock_port.get_troop_upgrades = AsyncMock(return_value=_upgrade_rows_legionario())
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get("/catalog/troops/romans/1/upgrades")
        assert response.status_code == 200
    finally:
        app.state.game_data_port = original


def test_upgrades_idioma_invalido_400(client):
    """
    Accept-Language con idioma no soportado → 400 (mismo comportamiento
    que en /stats: si viene idioma, debe ser válido).
    """
    response = client.get(
        "/catalog/troops/romans/1/upgrades",
        headers={"Accept-Language": "zh"},
    )
    assert response.status_code == 400


def test_upgrades_server_version_query(client):
    """?server_version= se puede enviar y se propaga al get_troop_upgrades."""
    mock_port = _make_mock_game_data_port()
    mock_port.get_troop_upgrades = AsyncMock(return_value=_upgrade_rows_legionario())
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/troops/romans/1/upgrades?server_version=1.45",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        assert response.json()["server_version"] == "1.45"
        # Verificar que get_troop_upgrades fue llamado con los parámetros correctos
        mock_port.get_troop_upgrades.assert_called_once()
    finally:
        app.state.game_data_port = original


def test_upgrades_levels_ordenados(client):
    """Los niveles en la respuesta están ordenados ascendentemente por level."""
    mock_port = _make_mock_game_data_port()
    # Devolver filas en orden inverso para verificar que el endpoint las ordena
    rows = _upgrade_rows_legionario()
    rows_reversed = rows[::-1]
    mock_port.get_troop_upgrades = AsyncMock(return_value=rows_reversed)
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/troops/romans/1/upgrades",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        levels = response.json()["levels"]
        level_nums = [lv["level"] for lv in levels]
        assert level_nums == sorted(level_nums)
    finally:
        app.state.game_data_port = original


def test_upgrades_cache_control_header(client):
    """Cache-Control: public, max-age=3600 (ruta bajo /catalog/)."""
    mock_port = _make_mock_game_data_port()
    mock_port.get_troop_upgrades = AsyncMock(return_value=_upgrade_rows_legionario())
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/troops/romans/1/upgrades",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        assert response.headers.get("cache-control") == "public, max-age=3600"
    finally:
        app.state.game_data_port = original
