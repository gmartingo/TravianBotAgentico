"""
Tests del exception handler global (sección 12.5 del spec i18n-backend).

Prueba:
- Traducción de errores al idioma del cliente.
- Default a 'es' cuando falta Accept-Language.
- Cabeceras mínimas en respuestas de error.
- Modo verbose (X-Verbose: true) con traza enmascarada.
- Enmascarado de datos sensibles: passwords/tokens Y rutas de perfil Chrome y URLs de Travian.
"""
import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from adapters.api.main import app
from core.exceptions import AccountNotFoundError, LoginError


# ---------------------------------------------------------------------------
# Ruta de prueba que lanza excepciones del dominio
# ---------------------------------------------------------------------------
# Añadimos un router temporal al app para poder lanzar excepciones controladas.
# Se registra antes de crear los clients para que FastAPI lo incluya.

_test_router = APIRouter(prefix="/test-errors", tags=["test-only"])


@_test_router.get("/account-not-found/{account_id}")
def raise_account_not_found(account_id: int):
    raise AccountNotFoundError(account_id)


@_test_router.get("/login-error")
def raise_login_error():
    password = "s3cr3t_p4ssw0rd"  # noqa: F841 — variable local sensible para test de enmascarado
    api_key = "SUPER_SECRET_KEY"   # noqa: F841 — campo sensible
    user_data_dir = "/Users/bot/profiles/account1"  # noqa: F841 — ruta de perfil Chrome
    world_server = "https://ts20.travian.com"        # noqa: F841 — URL de Travian
    raise LoginError("Error de login para test")


app.include_router(_test_router)


@pytest.fixture(scope="module")
def client():
    """Cliente de test con lifespan activado."""
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# 12.5 — Traducción al idioma del cliente
# ---------------------------------------------------------------------------

def test_account_not_found_en_devuelve_404_en_ingles(client):
    response = client.get(
        "/test-errors/account-not-found/42",
        headers={"Accept-Language": "en"},
    )
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "42" in detail
    assert "not found" in detail.lower() or "found" in detail.lower()


def test_account_not_found_es_devuelve_404_en_espanol(client):
    response = client.get(
        "/test-errors/account-not-found/42",
        headers={"Accept-Language": "es"},
    )
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "42" in detail
    # Debe contener texto en español
    assert "cuenta" in detail.lower() or "encontrada" in detail.lower()


def test_error_sin_header_usa_default_es(client):
    """Sin Accept-Language → detail en español (default 'es')."""
    response = client.get("/test-errors/account-not-found/7")
    assert response.status_code == 404
    detail = response.json()["detail"]
    # Debe ser en español (default)
    assert "cuenta" in detail.lower() or "encontrada" in detail.lower()


# ---------------------------------------------------------------------------
# 12.5 — Cabeceras mínimas en respuestas de error
# ---------------------------------------------------------------------------

def test_error_handler_cabeceras_minimas(client):
    """Las respuestas de error incluyen las cabeceras mínimas."""
    response = client.get(
        "/test-errors/account-not-found/1",
        headers={"Accept-Language": "es"},
    )
    assert response.status_code == 404
    headers = response.headers
    assert headers.get("x-request-id")
    assert headers.get("x-api-version") == "0.1.0"
    assert "application/json" in headers.get("content-type", "")
    assert "utf-8" in headers.get("content-type", "").lower()
    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("x-frame-options") == "DENY"


def test_error_handler_x_request_id_eco(client):
    """X-Request-ID enviado en la request de error vuelve idéntico en la respuesta."""
    known_id = "error-handler-test-id-001"
    response = client.get(
        "/test-errors/account-not-found/1",
        headers={"Accept-Language": "es", "X-Request-ID": known_id},
    )
    assert response.status_code == 404
    assert response.headers.get("x-request-id") == known_id


# ---------------------------------------------------------------------------
# 12.5 — Cache-Control NO se hereda en respuestas de error
# ---------------------------------------------------------------------------

def test_error_handler_no_tiene_cache_control(client):
    """Las respuestas de error NO deben tener Cache-Control: public."""
    response = client.get(
        "/test-errors/account-not-found/1",
        headers={"Accept-Language": "es"},
    )
    assert response.status_code == 404
    cc = response.headers.get("cache-control", "")
    assert "public" not in cc


# ---------------------------------------------------------------------------
# 12.5 — Modo verbose (X-Verbose: true)
# ---------------------------------------------------------------------------

def test_error_handler_verbose_true_popula_error_details(client):
    """
    Con X-Verbose: true, la respuesta incluye `error_details` con:
    exception, http_code, timestamp, trace.
    """
    response = client.get(
        "/test-errors/login-error",
        headers={"Accept-Language": "es", "X-Verbose": "true"},
    )
    assert response.status_code == 500
    body = response.json()
    assert "error_details" in body
    ed = body["error_details"]
    assert "exception" in ed
    assert "http_code" in ed
    assert ed["http_code"] == 500
    assert "timestamp" in ed
    assert "trace" in ed
    assert isinstance(ed["trace"], list)


def test_error_handler_verbose_false_error_details_null(client):
    """Sin X-Verbose, error_details no aparece en el body."""
    response = client.get(
        "/test-errors/login-error",
        headers={"Accept-Language": "es"},
    )
    assert response.status_code == 500
    body = response.json()
    assert "error_details" not in body or body.get("error_details") is None
    assert "detail" in body


# ---------------------------------------------------------------------------
# 12.5 — Enmascarado de datos sensibles en verbose
# Condición obligatoria del guardian-antideteccion (sección 11 del spec):
# - password, token, api_key, authorization
# - user_data_dir, profile_dir (rutas de perfil Chrome)
# - URLs/hostnames de Travian (world.server, travian.com, etc.)
# ---------------------------------------------------------------------------

def test_error_handler_verbose_enmascara_secretos(client):
    """
    Forzar error con datos sensibles en vars del frame → verificar que:
    1. password/token/api_key/authorization salen como "***REDACTED***"
    2. user_data_dir/profile_dir salen como "***REDACTED***"
    3. URLs de Travian salen como "***REDACTED***"
    """
    response = client.get(
        "/test-errors/login-error",
        headers={"Accept-Language": "es", "X-Verbose": "true"},
    )
    assert response.status_code == 500
    body = response.json()
    assert "error_details" in body

    trace = body["error_details"]["trace"]
    # Recorrer todos los frames buscando los locals que debería haber enmascarado
    all_locals: dict = {}
    for frame in trace:
        all_locals.update(frame.get("locals", {}))

    # Verificar que ningún valor sensible aparece sin enmascarar
    # Campos sensibles estándar
    for field in ["password", "api_key"]:
        if field in all_locals:
            assert all_locals[field] == "***REDACTED***", (
                f"Campo '{field}' no fue enmascarado: {all_locals[field]}"
            )

    # Rutas de perfil Chrome
    for field in ["user_data_dir"]:
        if field in all_locals:
            assert all_locals[field] == "***REDACTED***", (
                f"Ruta de perfil Chrome '{field}' no fue enmascarada: {all_locals[field]}"
            )

    # URLs de Travian — variable world_server cuyo valor contiene "travian.com"
    for field in ["world_server"]:
        if field in all_locals:
            assert all_locals[field] == "***REDACTED***", (
                f"URL de Travian '{field}' no fue enmascarada: {all_locals[field]}"
            )

    # Verificar que el valor real nunca aparece en ninguna parte del body serializado
    body_str = str(body)
    assert "s3cr3t_p4ssw0rd" not in body_str, "Password real apareció en la respuesta verbose"
    assert "SUPER_SECRET_KEY" not in body_str, "API key real apareció en la respuesta verbose"
    assert "/Users/bot/profiles/account1" not in body_str, "Ruta de perfil apareció en respuesta verbose"
    assert "ts20.travian.com" not in body_str, "URL de Travian apareció en respuesta verbose"
