"""
Tests de API de sesión (TestClient, sin Chrome real) — sección 12.2 del spec
login-sesion-api.

Estrategia:
  - TestClient con lifespan activado (scope="module") — igual que test_building_stats_api.py.
  - En cada test se sobrescriben app.state.db_port y app.state.world_runtime_port
    con mocks, restaurando el original en el bloque finally.
  - MockRegistry simula WorldRuntimePort sin abrir ningún browser.
  - MockDb simula DbPort: get_account devuelve una cuenta con mundos configurables.
  - Ningún test abre Chrome real.

11 tests cubriendo los casos de sección 12.2 + 3 del helper _verify_world_belongs_to_account.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from adapters.api.main import app
from core.crypto import encrypt_password
from core.entities.account import Account
from core.entities.tribe import Tribe
from core.entities.world import World

# Fernet de test para los casos del Amendment A1
_TEST_FERNET = Fernet(Fernet.generate_key())
_OTHER_FERNET = Fernet(Fernet.generate_key())  # clave diferente para simular InvalidToken


# ---------------------------------------------------------------------------
# Mock de WorldRuntimePort (no SessionRegistry real — sin Chrome)
# ---------------------------------------------------------------------------

class MockRegistry:
    """Mock mínimo de WorldRuntimePort para los tests de API."""

    def __init__(self, login_result: bool = True, active_result: bool = False):
        self._login_result = login_result
        self._active = active_result

    async def login(self, account, world) -> bool:
        return self._login_result

    async def logout(self, world_id: int) -> None:
        pass  # no-op

    def is_active(self, world_id: int) -> bool:
        return self._active


# ---------------------------------------------------------------------------
# Helpers para construir mocks de DbPort
# ---------------------------------------------------------------------------

def _make_world(world_id: int = 1) -> World:
    return World(
        id=world_id,
        server="https://ts20.x2.america.travian.com/",
        tribe=Tribe.ROMANS,
    )


def _make_account(world_ids: list[int] | None = None) -> Account:
    worlds = [_make_world(wid) for wid in (world_ids or [1])]
    return Account(
        id=1,
        email="testtravian13@gmail.com",
        username="testtravian13@gmail.com",
        password="secret",
        worlds=worlds,
    )


def _make_db(account: Account | None = None, cipher: bytes | None = None) -> MagicMock:
    """
    Mock de DbPort: get_account devuelve account (o None si no se especifica).
    get_account_password_cipher devuelve cipher (o un token válido por defecto si la cuenta existe).
    """
    db = MagicMock()
    db.get_account = AsyncMock(return_value=account)
    # Si no se especifica cipher pero hay cuenta, generar uno válido con _TEST_FERNET
    if cipher is None and account is not None:
        cipher = encrypt_password(_TEST_FERNET, "test_password")
    db.get_account_password_cipher = AsyncMock(return_value=cipher)
    return db


# ---------------------------------------------------------------------------
# Fixture de TestClient con lifespan activado
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    """Cliente de test con lifespan activado (igual que test_building_stats_api.py)."""
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Helper para sustituir temporalmente db_port y world_runtime_port en app.state
# ---------------------------------------------------------------------------

class _StateOverride:
    """Context manager que sobreescribe app.state attrs y los restaura al salir."""

    def __init__(self, **overrides):
        self._overrides = overrides
        self._originals = {}

    def __enter__(self):
        for key, value in self._overrides.items():
            self._originals[key] = getattr(app.state, key, None)
            setattr(app.state, key, value)
        return self

    def __exit__(self, *_):
        for key, original in self._originals.items():
            setattr(app.state, key, original)


# ---------------------------------------------------------------------------
# Tests — POST /accounts/{account_id}/worlds/{world_id}/session
# ---------------------------------------------------------------------------

def test_post_session_success(client):
    """POST con account+world válidos y registry.login → True: 200 + active=true."""
    account = _make_account(world_ids=[1])
    # cipher generado con _TEST_FERNET; fernet inyectado también es _TEST_FERNET → descifrado OK
    db = _make_db(account=account)
    registry = MockRegistry(login_result=True)

    with _StateOverride(db_port=db, world_runtime_port=registry, fernet=_TEST_FERNET):
        r = client.post("/accounts/1/worlds/1/session")

    assert r.status_code == 200
    body = r.json()
    assert body["active"] is True
    assert body["world_id"] == 1
    assert body["account_id"] == 1


def test_post_session_login_failed(client):
    """POST con registry.login → False: 401 con detail que contiene el username."""
    account = _make_account(world_ids=[1])
    db = _make_db(account=account)
    registry = MockRegistry(login_result=False)

    with _StateOverride(db_port=db, world_runtime_port=registry, fernet=_TEST_FERNET):
        r = client.post("/accounts/1/worlds/1/session")

    assert r.status_code == 401
    assert "testtravian13@gmail.com" in r.json()["detail"]


def test_post_session_account_not_found(client):
    """POST con account_id inexistente: 404 con detail que contiene '99'."""
    db = _make_db(account=None)  # cuenta no existe; cipher tampoco necesario
    registry = MockRegistry()

    with _StateOverride(db_port=db, world_runtime_port=registry, fernet=_TEST_FERNET):
        r = client.post("/accounts/99/worlds/1/session")

    assert r.status_code == 404
    assert "99" in r.json()["detail"]


def test_post_session_world_not_in_account(client):
    """POST con world_id que no pertenece a la cuenta: 404 con detail que contiene '99'."""
    account = _make_account(world_ids=[1])  # solo world_id=1, no 99
    db = _make_db(account=account)
    registry = MockRegistry()

    with _StateOverride(db_port=db, world_runtime_port=registry, fernet=_TEST_FERNET):
        r = client.post("/accounts/1/worlds/99/session")

    assert r.status_code == 404
    assert "99" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Tests — DELETE /accounts/{account_id}/worlds/{world_id}/session
# ---------------------------------------------------------------------------

def test_delete_session_success(client):
    """DELETE con account+world válidos: 204 sin body."""
    account = _make_account(world_ids=[1])
    db = _make_db(account=account)
    registry = MockRegistry()

    with _StateOverride(db_port=db, world_runtime_port=registry):
        r = client.delete("/accounts/1/worlds/1/session")

    assert r.status_code == 204


def test_delete_session_no_active_session(client):
    """DELETE sin sesión activa: 204 igualmente (idempotente, RN-08)."""
    account = _make_account(world_ids=[1])
    db = _make_db(account=account)
    registry = MockRegistry(active_result=False)

    with _StateOverride(db_port=db, world_runtime_port=registry):
        r = client.delete("/accounts/1/worlds/1/session")

    assert r.status_code == 204


def test_delete_session_account_not_found(client):
    """DELETE con account_id inexistente: 404."""
    db = _make_db(account=None)
    registry = MockRegistry()

    with _StateOverride(db_port=db, world_runtime_port=registry):
        r = client.delete("/accounts/99/worlds/1/session")

    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Tests — GET /accounts/{account_id}/worlds/{world_id}/session
# ---------------------------------------------------------------------------

def test_get_session_active(client):
    """GET con sesión activa: 200 + active=true."""
    account = _make_account(world_ids=[1])
    db = _make_db(account=account)
    registry = MockRegistry(active_result=True)

    with _StateOverride(db_port=db, world_runtime_port=registry):
        r = client.get("/accounts/1/worlds/1/session")

    assert r.status_code == 200
    body = r.json()
    assert body["active"] is True
    assert body["world_id"] == 1
    assert body["account_id"] == 1


def test_get_session_inactive(client):
    """GET sin sesión activa: 200 + active=false."""
    account = _make_account(world_ids=[1])
    db = _make_db(account=account)
    registry = MockRegistry(active_result=False)

    with _StateOverride(db_port=db, world_runtime_port=registry):
        r = client.get("/accounts/1/worlds/1/session")

    assert r.status_code == 200
    body = r.json()
    assert body["active"] is False
    assert body["world_id"] == 1
    assert body["account_id"] == 1


def test_get_session_account_not_found(client):
    """GET con account_id inexistente: 404."""
    db = _make_db(account=None)
    registry = MockRegistry()

    with _StateOverride(db_port=db, world_runtime_port=registry):
        r = client.get("/accounts/99/worlds/1/session")

    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Tests — EC-11: registry no disponible (503)
# ---------------------------------------------------------------------------

def test_registry_unavailable(client):
    """POST con world_runtime_port=None en app.state: 503 con detail que menciona SessionRegistry."""
    account = _make_account(world_ids=[1])
    db = _make_db(account=account)

    with _StateOverride(db_port=db, world_runtime_port=None):
        r = client.post("/accounts/1/worlds/1/session")

    assert r.status_code == 503
    assert "SessionRegistry" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Tests — helper _verify_world_belongs_to_account (sección 12.3)
# ---------------------------------------------------------------------------

def test_verify_account_not_found():
    """Cuenta no encontrada → AccountNotFoundError."""
    from adapters.api.routes.accounts import _verify_world_belongs_to_account
    from core.exceptions import AccountNotFoundError

    db = _make_db(account=None)

    with pytest.raises(AccountNotFoundError):
        asyncio.run(_verify_world_belongs_to_account(99, 1, db))


def test_verify_world_not_in_account():
    """Cuenta existe pero world_id no pertenece a ella → WorldNotFoundError."""
    from adapters.api.routes.accounts import _verify_world_belongs_to_account
    from core.exceptions import WorldNotFoundError

    account = _make_account(world_ids=[1])
    db = _make_db(account=account)

    with pytest.raises(WorldNotFoundError):
        asyncio.run(_verify_world_belongs_to_account(1, 99, db))


def test_verify_ok():
    """Cuenta existe y world_id pertenece a ella → no lanza excepción."""
    from adapters.api.routes.accounts import _verify_world_belongs_to_account

    account = _make_account(world_ids=[1])
    db = _make_db(account=account)

    # No debe lanzar ninguna excepción
    asyncio.run(_verify_world_belongs_to_account(1, 1, db))


# ---------------------------------------------------------------------------
# Tests del Amendment A1.9.3 — casos nuevos del endpoint POST
# ---------------------------------------------------------------------------

def test_post_session_invalid_token(client):
    """
    A1 EC-A2: token cifrado con clave distinta → InvalidToken dentro de LoginUseCase
    → handler recibe LoginFailedError → 401.
    Confirma que InvalidToken no se propaga como 500.
    """
    account = _make_account(world_ids=[1])
    # Cifrar con _OTHER_FERNET; el use case usará _TEST_FERNET → InvalidToken
    wrong_cipher = encrypt_password(_OTHER_FERNET, "otra_password")
    db = _make_db(account=account, cipher=wrong_cipher)
    registry = MockRegistry(login_result=True)

    with _StateOverride(db_port=db, world_runtime_port=registry, fernet=_TEST_FERNET):
        r = client.post("/accounts/1/worlds/1/session")

    assert r.status_code == 401
    # El detail debe mencionar el login fallido (no un traceback ni 500)
    assert "detail" in r.json()


def test_post_session_cipher_none(client):
    """
    A1 EC-A1: get_account_password_cipher devuelve None (BD corrupta)
    → LoginUseCase lanza LoginFailedError → 401.
    """
    account = _make_account(world_ids=[1])
    db = _make_db(account=account, cipher=None)
    # Forzar cipher=None explícitamente (sobrescribe el default del helper)
    db.get_account_password_cipher = AsyncMock(return_value=None)
    registry = MockRegistry(login_result=True)

    with _StateOverride(db_port=db, world_runtime_port=registry, fernet=_TEST_FERNET):
        r = client.post("/accounts/1/worlds/1/session")

    assert r.status_code == 401
    assert "detail" in r.json()
