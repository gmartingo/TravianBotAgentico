"""
Tests del endpoint GET /catalog/troops/{tribe} (sección 12.3 del spec i18n-backend).
"""
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from adapters.api.main import app
from core.entities.tribe import Tribe
from core.exceptions import TroopNotFoundError


@pytest.fixture(scope="module")
def client():
    """Cliente de test con lifespan activado (dispara startup)."""
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# 12.3 — Casos base
# ---------------------------------------------------------------------------

def test_troops_tribu_valida_idioma_valido(client):
    response = client.get(
        "/catalog/troops/romans",
        headers={"Accept-Language": "es"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["tribe"] == "romans"
    troops = body["troops"]
    assert len(troops) == 10  # romanos tienen 10 tropas en el catálogo base
    for item in troops:
        lang_key = list(item["language"].keys())[0]
        assert lang_key == "es"
        assert item["language"][lang_key]


def test_troops_estructura_respuesta(client):
    response = client.get(
        "/catalog/troops/gauls",
        headers={"Accept-Language": "es"},
    )
    assert response.status_code == 200
    troops = response.json()["troops"]
    for item in troops:
        assert isinstance(item["ordinal"], int)
        assert isinstance(item["key"], str)
        assert isinstance(item["language"], dict)
        assert len(item["language"]) == 1


def test_troops_no_contiene_campo_name(client):
    """Los items NO deben tener campo `name` plano."""
    response = client.get(
        "/catalog/troops/romans",
        headers={"Accept-Language": "es"},
    )
    assert response.status_code == 200
    troops = response.json()["troops"]
    for item in troops:
        assert "name" not in item


def test_troops_no_contiene_campo_lang_wrapper(client):
    """El wrapper de la respuesta NO debe tener campo `lang`."""
    response = client.get(
        "/catalog/troops/romans",
        headers={"Accept-Language": "es"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "lang" not in body


def test_troops_sin_header(client):
    response = client.get("/catalog/troops/romans")
    assert response.status_code == 400


def test_troops_idioma_no_soportado(client):
    response = client.get(
        "/catalog/troops/romans",
        headers={"Accept-Language": "zh"},
    )
    assert response.status_code == 400


def test_troops_tribu_invalida(client):
    """Tribu no válida en el enum → FastAPI devuelve 422 automáticamente."""
    response = client.get(
        "/catalog/troops/persians",
        headers={"Accept-Language": "es"},
    )
    assert response.status_code == 422


def test_troops_cache_control_header(client):
    response = client.get(
        "/catalog/troops/romans",
        headers={"Accept-Language": "es"},
    )
    assert response.status_code == 200
    assert response.headers.get("cache-control") == "public, max-age=3600"


def test_troops_todas_las_tribus(client):
    """Verificar que las 5 tribus devuelven 200."""
    for tribe in ["romans", "teutons", "gauls", "egyptians", "huns"]:
        response = client.get(
            f"/catalog/troops/{tribe}",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200, f"Tribu {tribe} falló con {response.status_code}"
        assert response.json()["tribe"] == tribe


def test_troops_fallback_de_idioma_servido_es(client):
    """
    Con Accept-Language: de y tropas sin traducción en 'de',
    el campo language lleva clave 'es' (no 'de').
    """
    response = client.get(
        "/catalog/troops/romans",
        headers={"Accept-Language": "de"},
    )
    assert response.status_code == 200
    troops = response.json()["troops"]
    for item in troops:
        lang_key = list(item["language"].keys())[0]
        # Romanos no tienen "de" en el catálogo base → todos deben ser "es"
        assert lang_key == "es"
        assert item["language"][lang_key]


def test_troops_fallback_de_idioma_servido_mixto(client):
    """
    Con Accept-Language: de, items con trad. de tienen clave 'de',
    los que no la tienen tienen clave 'es'. Exactamente una clave por item.
    """
    response = client.get(
        "/catalog/troops/romans",
        headers={"Accept-Language": "de"},
    )
    assert response.status_code == 200
    troops = response.json()["troops"]
    for item in troops:
        lang_key = list(item["language"].keys())[0]
        assert lang_key in ("de", "es")
        assert len(item["language"]) == 1


def test_troops_tribu_valida_sin_tropas_devuelve_404(client):
    """
    Tribu válida en enum pero sin entradas en catálogo → 404.
    Mockea el adaptador para lanzar TroopNotFoundError.
    """
    from unittest.mock import patch

    # Monkey-patching del app.state.translation_port para esta prueba
    mock_port = MagicMock()
    mock_port.get_troop_names_by_tribe.side_effect = TroopNotFoundError(
        tribe=Tribe.ROMANS, ordinal=None
    )

    original_port = app.state.translation_port
    app.state.translation_port = mock_port
    try:
        response = client.get(
            "/catalog/troops/romans",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 404
        assert "romans" in response.json()["detail"].lower()
    finally:
        app.state.translation_port = original_port


def test_troops_cabeceras_minimas(client):
    """Verificar presencia de las cabeceras mínimas de seguridad."""
    response = client.get(
        "/catalog/troops/romans",
        headers={"Accept-Language": "es"},
    )
    assert response.status_code == 200
    headers = response.headers
    assert "application/json" in headers.get("content-type", "")
    assert "utf-8" in headers.get("content-type", "").lower()
    assert headers.get("x-request-id")
    assert headers.get("x-api-version") == "0.1.0"
    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("x-frame-options") == "DENY"


def test_troops_x_request_id_eco(client):
    """Si el cliente envía X-Request-ID, debe volver idéntico en la respuesta."""
    known_id = "troop-test-request-id-99"
    response = client.get(
        "/catalog/troops/romans",
        headers={"Accept-Language": "es", "X-Request-ID": known_id},
    )
    assert response.status_code == 200
    assert response.headers.get("x-request-id") == known_id
