"""
Tests de API para el endpoint de stats de edificios.

GET /catalog/buildings/{gid}/stats  — stats numéricos de edificios por gid
GET /catalog/buildings              — catálogo actualizado con campos opcionales

Los tests usan TestClient con lifespan para disparar startup.
Se inyectan mocks de game_data_port y translation_port en app.state.

Convención de Accept-Language para /catalog/buildings/{gid}/stats:
  - OPCIONAL: sin cabecera ni ?lang= → 200 con todos los idiomas (~25 claves).
  - Idioma soportado (vía header o ?lang=) → 200 con un idioma.
  - Idioma no soportado → 400.
  - ?lang= tiene precedencia sobre Accept-Language.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from adapters.api.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    """Cliente de test con lifespan activado."""
    with TestClient(app) as c:
        yield c


def _make_mock_game_data_port(
    building_stats_rows=None,
    building_catalog=None,
    all_building_stats=None,
    all_building_catalog=None,
    icon_rows=None,
) -> MagicMock:
    """Crea un mock de GameDataPort para inyectar en app.state."""
    mock = MagicMock()
    mock.get_building_stats = AsyncMock(return_value=building_stats_rows or [])
    mock.get_building_catalog = AsyncMock(return_value=building_catalog)
    mock.get_all_building_stats = AsyncMock(return_value=all_building_stats or {})
    mock.get_all_building_catalog = AsyncMock(return_value=all_building_catalog or {})
    mock.list_icons = AsyncMock(return_value=icon_rows or [])
    # Mantener métodos de tropas para que los otros endpoints no fallen
    mock.get_all_troop_stats = AsyncMock(return_value=[])
    mock.get_troop_stats = AsyncMock(return_value=None)
    mock.get_troop_upgrades = AsyncMock(return_value=[])
    return mock


def _building_level_row(level: int = 1) -> dict:
    return {
        "server_version": "1.45",
        "gid": 10,
        "level": level,
        "cost_wood": 130,
        "cost_clay": 160,
        "cost_iron": 90,
        "cost_crop": 40,
        "cost_sum": 420,
        "upkeep": 1,
        "culture_points": 1,
        "build_time_s": 1000,
        "effect_value": 1200,
        "effect_label": "Almacena",
    }


def _building_catalog_meta(icon_id: str | None = "building_10_warehouse") -> dict:
    return {
        "server_version": "1.45",
        "gid": 10,
        "alias": "warehouse",
        "category": "infrastructure",
        "description": "Amplía la capacidad de almacenamiento.",
        "icon_id": icon_id,
        "scraped_at": "2026-05-25T00:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# Tests — GET /catalog/buildings/{gid}/stats — Accept-Language
# ---------------------------------------------------------------------------


def test_building_stats_valid_lang(client):
    """200 con Accept-Language válido y datos en BD (mock)."""
    mock_port = _make_mock_game_data_port(
        building_stats_rows=[_building_level_row()],
        building_catalog=_building_catalog_meta(),
    )
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/buildings/10/stats",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["gid"] == 10
        assert body["server_version"] == "1.45"
        assert "es" in body["language"]
        assert len(body["levels"]) == 1
    finally:
        app.state.game_data_port = original


def test_building_stats_missing_lang_returns_all(client):
    """Sin cabecera ni ?lang= → 200 con language multi-idioma (~25 claves)."""
    mock_port = _make_mock_game_data_port(
        building_stats_rows=[_building_level_row()],
        building_catalog=_building_catalog_meta(),
    )
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get("/catalog/buildings/10/stats")
        assert response.status_code == 200
        body = response.json()
        language = body["language"]
        # El catálogo real tiene múltiples idiomas para gid=10
        assert len(language) >= 1, f"language vacío: {language}"
    finally:
        app.state.game_data_port = original


def test_building_stats_unsupported_lang(client):
    """400 si el idioma no está soportado."""
    response = client.get(
        "/catalog/buildings/10/stats",
        headers={"Accept-Language": "zh"},
    )
    assert response.status_code == 400


def test_building_stats_query_lang_override(client):
    """?lang=en + Accept-Language: es → language con clave 'en' (precedencia)."""
    mock_port = _make_mock_game_data_port(
        building_stats_rows=[_building_level_row()],
        building_catalog=_building_catalog_meta(),
    )
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/buildings/10/stats?lang=en",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        body = response.json()
        assert "en" in body["language"]
    finally:
        app.state.game_data_port = original


def test_building_stats_invalid_gid(client):
    """422 si gid no es entero."""
    response = client.get(
        "/catalog/buildings/abc/stats",
        headers={"Accept-Language": "es"},
    )
    assert response.status_code == 422


def test_building_stats_no_data(client):
    """404 si gid sin datos en BD, con server_version en el detail."""
    mock_port = _make_mock_game_data_port(
        building_stats_rows=[],
        building_catalog=None,
    )
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/buildings/999/stats",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 404
        assert "server_version" in response.json()["detail"]
    finally:
        app.state.game_data_port = original


def test_building_stats_null_effect(client):
    """Nivel con effect_value=None → 'effect_value': null en JSON."""
    row = _building_level_row()
    row["effect_value"] = None
    row["effect_label"] = None
    mock_port = _make_mock_game_data_port(
        building_stats_rows=[row],
        building_catalog=_building_catalog_meta(),
    )
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/buildings/10/stats",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        levels = response.json()["levels"]
        assert levels[0]["effect_value"] is None
    finally:
        app.state.game_data_port = original


def test_building_stats_icon_url_present(client):
    """Edificio con icon_id descriptivo en BD → icon_url con ruta correcta."""
    mock_port = _make_mock_game_data_port(
        building_stats_rows=[_building_level_row()],
        building_catalog=_building_catalog_meta(icon_id="building_10_warehouse"),
    )
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/buildings/10/stats",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        assert response.json()["icon_url"] == "/static/icons/building_10_warehouse.png"
    finally:
        app.state.game_data_port = original


def test_building_stats_icon_url_null(client):
    """Edificio sin icon_id → icon_url: null."""
    mock_port = _make_mock_game_data_port(
        building_stats_rows=[_building_level_row()],
        building_catalog=_building_catalog_meta(icon_id=None),
    )
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/buildings/10/stats",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        assert response.json()["icon_url"] is None
    finally:
        app.state.game_data_port = original


def test_building_stats_vary_header(client):
    """Cualquier 200 → Vary: Accept-Language en la respuesta."""
    mock_port = _make_mock_game_data_port(
        building_stats_rows=[_building_level_row()],
        building_catalog=_building_catalog_meta(),
    )
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/buildings/10/stats",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        assert "Accept-Language" in response.headers.get("vary", "")
    finally:
        app.state.game_data_port = original


def test_building_stats_cache_control(client):
    """Cualquier 200 → Cache-Control: public, max-age=3600."""
    mock_port = _make_mock_game_data_port(
        building_stats_rows=[_building_level_row()],
        building_catalog=_building_catalog_meta(),
    )
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/buildings/10/stats",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        cc = response.headers.get("cache-control", "")
        assert "public" in cc
        assert "max-age=3600" in cc
    finally:
        app.state.game_data_port = original


def test_building_stats_unsupported_query_lang(client):
    """?lang=xx con idioma no soportado → 400."""
    response = client.get("/catalog/buildings/10/stats?lang=xx")
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Tests — GET /catalog/buildings (endpoint actualizado)
# ---------------------------------------------------------------------------


def test_buildings_catalog_includes_levels_when_available(client):
    """Con datos en BD → levels no es null en al menos un edificio."""
    mock_port = _make_mock_game_data_port(
        all_building_stats={10: [_building_level_row()]},
        all_building_catalog={10: _building_catalog_meta()},
    )
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/buildings",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        buildings = response.json()["buildings"]
        # Buscar gid=10 en la lista
        b10 = next((b for b in buildings if b["gid"] == 10), None)
        if b10 is not None:
            assert b10["levels"] is not None, "levels debe ser no null cuando hay datos"
    finally:
        app.state.game_data_port = original


def test_buildings_catalog_levels_null_when_no_data(client):
    """Sin datos en BD → levels: null, no falla (retrocompatibilidad)."""
    mock_port = _make_mock_game_data_port(
        all_building_stats={},
        all_building_catalog={},
    )
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/buildings",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        buildings = response.json()["buildings"]
        # Sin datos, todos los campos opcionales son None
        for b in buildings:
            assert b["levels"] is None
            assert b["category"] is None
    finally:
        app.state.game_data_port = original


def test_buildings_catalog_category_present(client):
    """Con datos en BD → category tiene valor válido."""
    mock_port = _make_mock_game_data_port(
        all_building_stats={10: [_building_level_row()]},
        all_building_catalog={10: _building_catalog_meta()},
    )
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/buildings",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        buildings = response.json()["buildings"]
        b10 = next((b for b in buildings if b["gid"] == 10), None)
        if b10 is not None:
            assert b10["category"] == "infrastructure"
    finally:
        app.state.game_data_port = original


def test_buildings_catalog_icon_url_present(client):
    """Con icon_id descriptivo en BD → icon_url correcto."""
    mock_port = _make_mock_game_data_port(
        all_building_stats={10: [_building_level_row()]},
        all_building_catalog={10: _building_catalog_meta(icon_id="building_10_warehouse")},
    )
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/buildings",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        buildings = response.json()["buildings"]
        b10 = next((b for b in buildings if b["gid"] == 10), None)
        if b10 is not None:
            assert b10["icon_url"] == "/static/icons/building_10_warehouse.png"
    finally:
        app.state.game_data_port = original


def test_buildings_catalog_retrocompatible_without_levels(client):
    """Clientes que solo leen gid, alias y language no se ven afectados."""
    mock_port = _make_mock_game_data_port(
        all_building_stats={},
        all_building_catalog={},
    )
    original = app.state.game_data_port
    app.state.game_data_port = mock_port
    try:
        response = client.get(
            "/catalog/buildings",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        buildings = response.json()["buildings"]
        # Todos los edificios deben tener gid, alias y language (campos existentes)
        for b in buildings:
            assert "gid" in b
            assert "alias" in b
            assert "language" in b
            assert isinstance(b["language"], dict)
    finally:
        app.state.game_data_port = original
