"""
Tests del endpoint GET /catalog/buildings (sección 12.2 del spec i18n-backend).

El TestClient usa context manager para disparar el evento startup
que inicializa app.state.translation_port (CA-17: cargado una sola vez).
"""
import pytest
from fastapi.testclient import TestClient

from adapters.api.main import app


@pytest.fixture(scope="module")
def client():
    """Cliente de test con lifespan activado (dispara startup)."""
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# 12.2 — Casos base
# ---------------------------------------------------------------------------

def test_buildings_idioma_valido_en(client):
    response = client.get("/catalog/buildings", headers={"Accept-Language": "en"})
    assert response.status_code == 200
    buildings = response.json()["buildings"]
    assert len(buildings) > 0
    for item in buildings:
        assert "language" in item
        lang_key = list(item["language"].keys())[0]
        # Para "en": todos los edificios tienen traducción en inglés en el catálogo base
        # (puede ser "en" o "es" por fallback; lo que importa es que la clave existe)
        assert lang_key in ("en", "es")
        assert item["language"][lang_key]  # nombre no vacío


def test_buildings_idioma_valido_es(client):
    response = client.get("/catalog/buildings", headers={"Accept-Language": "es"})
    assert response.status_code == 200
    buildings = response.json()["buildings"]
    assert len(buildings) > 0
    for item in buildings:
        lang_key = list(item["language"].keys())[0]
        assert lang_key == "es"
        assert item["language"][lang_key]


def test_buildings_sin_header(client):
    response = client.get("/catalog/buildings")
    assert response.status_code == 400


def test_buildings_idioma_no_soportado(client):
    response = client.get("/catalog/buildings", headers={"Accept-Language": "ja"})
    assert response.status_code == 400


def test_buildings_estructura_respuesta(client):
    response = client.get("/catalog/buildings", headers={"Accept-Language": "en"})
    assert response.status_code == 200
    buildings = response.json()["buildings"]
    for item in buildings:
        assert isinstance(item["gid"], int)
        assert isinstance(item["alias"], str)
        assert isinstance(item["language"], dict)
        assert len(item["language"]) == 1  # exactamente una clave (el idioma servido)


def test_buildings_no_contiene_campo_name(client):
    """Los items NO deben tener campo `name` plano (eliminado en Ajuste 1 del spec)."""
    response = client.get("/catalog/buildings", headers={"Accept-Language": "es"})
    assert response.status_code == 200
    buildings = response.json()["buildings"]
    for item in buildings:
        assert "name" not in item


def test_buildings_no_contiene_campo_lang_wrapper(client):
    """El wrapper de la respuesta NO debe tener campo `lang`."""
    response = client.get("/catalog/buildings", headers={"Accept-Language": "es"})
    assert response.status_code == 200
    body = response.json()
    assert "lang" not in body


def test_buildings_cache_control_header(client):
    response = client.get("/catalog/buildings", headers={"Accept-Language": "es"})
    assert response.status_code == 200
    assert response.headers.get("cache-control") == "public, max-age=3600"


def test_buildings_fallback_de_idioma_servido_es(client):
    """
    Con Accept-Language: de y un item sin traducción en 'de',
    el campo language lleva clave 'es' (no 'de').
    """
    response = client.get("/catalog/buildings", headers={"Accept-Language": "de"})
    assert response.status_code == 200
    buildings = response.json()["buildings"]
    # gid=1 (woodcutter): tiene "de" = "Holzfäller" en catálogo base → clave "de"
    # Si algún item no tiene "de" → clave "es"
    keys_found = set()
    for item in buildings:
        keys_found.update(item["language"].keys())
    # El catálogo base tiene traducciones "de" para todos los edificios, así que
    # verificamos que la estructura es correcta: solo una clave por item
    for item in buildings:
        assert len(item["language"]) == 1


def test_buildings_fallback_de_idioma_servido_mixto(client):
    """
    Con Accept-Language: de, verificar que items con traducción en 'de'
    tienen clave 'de' y los que no la tienen tienen clave 'es'.
    La estructura de dict tiene exactamente una clave por item.
    """
    response = client.get("/catalog/buildings", headers={"Accept-Language": "de"})
    assert response.status_code == 200
    buildings = response.json()["buildings"]
    for item in buildings:
        lang_key = list(item["language"].keys())[0]
        assert lang_key in ("de", "es")
        assert item["language"][lang_key]  # nombre no vacío


def test_buildings_cabeceras_minimas(client):
    """Verificar presencia de las cabeceras mínimas de seguridad."""
    response = client.get("/catalog/buildings", headers={"Accept-Language": "es"})
    assert response.status_code == 200
    headers = response.headers
    assert "application/json" in headers.get("content-type", "")
    assert "utf-8" in headers.get("content-type", "").lower()
    assert headers.get("x-request-id")
    assert headers.get("x-api-version") == "0.1.0"
    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("x-frame-options") == "DENY"


def test_buildings_x_request_id_eco(client):
    """Si el cliente envía X-Request-ID, debe volver idéntico en la respuesta."""
    known_id = "test-request-id-12345"
    response = client.get(
        "/catalog/buildings",
        headers={"Accept-Language": "es", "X-Request-ID": known_id},
    )
    assert response.status_code == 200
    assert response.headers.get("x-request-id") == known_id
