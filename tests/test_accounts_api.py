"""
Tests de API (TestClient) para el router de cuentas y mundos.

Cubren el plan de pruebas AT-01..AT-24 del spec docs/specs/registro-cuentas-mundos.md
más el test de paridad PlayableTribe ↔ PLAYABLE_TRIBES (gap F-1 detectado por palantir).

Estrategia: app REAL (con sus middlewares y handler global de errores) contra una BD
SQLite en archivo TEMPORAL, aislada por test (monkeypatch de DB_PATH antes del lifespan).
Esto ejercita el cableado completo: router → use case → AccountSQLiteAdapter → SQLite real.

La clave Fernet la fija tests/conftest.py para toda la sesión.
"""
import pytest
from fastapi.testclient import TestClient

from adapters.api.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class _FakeRuntimePort:
    """Doble de WorldRuntimePort: is_active() es síncrono (igual que el puerto real)."""

    def __init__(self, active: bool) -> None:
        self._active = active

    def is_active(self, world_id: int) -> bool:
        return self._active


@pytest.fixture
def client(monkeypatch, tmp_path):
    """Cliente con la app real apuntando a una BD temporal por test."""
    db_file = tmp_path / "test_accounts.db"
    # get_connection() lee adapters.db.database.DB_PATH en tiempo de llamada (en el lifespan).
    monkeypatch.setattr("adapters.db.database.DB_PATH", str(db_file))

    # Estado limpio: app es singleton de módulo, evitar fugas de world_runtime_port entre tests.
    if hasattr(app.state, "world_runtime_port"):
        delattr(app.state, "world_runtime_port")

    with TestClient(app) as c:
        yield c

    if hasattr(app.state, "world_runtime_port"):
        delattr(app.state, "world_runtime_port")


def _create_account(client, email="player@example.com", username="Player", password="secret123"):
    return client.post(
        "/accounts",
        json={"email": email, "username": username, "password": password},
    )


def _add_world(client, account_id, server="https://ts1.x1.international.travian.com/", tribe="romans"):
    return client.post(
        f"/accounts/{account_id}/worlds",
        json={"server": server, "tribe": tribe},
    )


# ---------------------------------------------------------------------------
# Paridad PlayableTribe ↔ PLAYABLE_TRIBES (gap F-1)
# ---------------------------------------------------------------------------

def test_playable_tribe_paridad_con_core():
    """El enum de la API y el frozenset del core deben listar exactamente las mismas tribus.

    Evita la desincronización que palantir señaló (RT-06): si se añade una tribu
    jugable a PLAYABLE_TRIBES y no a PlayableTribe, la API la rechazaría con 422.
    """
    from adapters.api.routes.accounts import PlayableTribe
    from core.entities.tribe import PLAYABLE_TRIBES

    assert {t.value for t in PlayableTribe} == {t.value for t in PLAYABLE_TRIBES}


# ---------------------------------------------------------------------------
# Cuentas
# ---------------------------------------------------------------------------

def test_at01_post_account_valido(client):
    r = _create_account(client)
    assert r.status_code == 201
    body = r.json()
    assert isinstance(body["id"], int) and body["id"] > 0
    assert body["email"] == "player@example.com"
    assert r.headers["Location"] == f"/accounts/{body['id']}"


def test_at02_post_account_email_duplicado(client):
    _create_account(client)
    r = _create_account(client)  # mismo email
    assert r.status_code == 409
    assert "player@example.com" in r.json()["detail"]


def test_at02b_email_duplicado_case_insensitive(client):
    _create_account(client, email="player@example.com")
    r = _create_account(client, email="PLAYER@Example.COM")
    assert r.status_code == 409


def test_at03_post_account_email_invalido(client):
    r = _create_account(client, email="no-es-un-email")
    assert r.status_code == 422


def test_at04_post_account_password_ausente(client):
    r = client.post("/accounts", json={"email": "a@b.com", "username": "X"})
    assert r.status_code == 422


def test_at05_get_accounts_vacio(client):
    r = client.get("/accounts")
    assert r.status_code == 200
    assert r.json() == {"accounts": []}


def test_at06_get_account_por_id(client):
    account_id = _create_account(client).json()["id"]
    r = client.get(f"/accounts/{account_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == account_id
    assert body["email"] == "player@example.com"


def test_at07_get_account_inexistente(client):
    r = client.get("/accounts/9999")
    assert r.status_code == 404


def test_at08_get_account_id_no_entero(client):
    r = client.get("/accounts/abc")
    assert r.status_code == 422


def test_at09_put_account_cambia_username(client):
    account_id = _create_account(client).json()["id"]
    r = client.put(
        f"/accounts/{account_id}",
        json={"email": "player@example.com", "username": "NuevoNombre"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == "NuevoNombre"
    assert "worlds" in body  # PUT devuelve AccountResponse con worlds (corrección desarrollador-apis)


def test_at10_put_account_email_a_uno_duplicado(client):
    id1 = _create_account(client, email="uno@example.com").json()["id"]
    _create_account(client, email="dos@example.com")
    r = client.put(
        f"/accounts/{id1}",
        json={"email": "dos@example.com", "username": "X"},
    )
    assert r.status_code == 409


def test_at11_put_account_sin_password_ok(client):
    account_id = _create_account(client).json()["id"]
    # Sin campo password → no cambia la contraseña; debe responder 200.
    r = client.put(
        f"/accounts/{account_id}",
        json={"email": "player@example.com", "username": "Player"},
    )
    assert r.status_code == 200


def test_at12_delete_account_ok(client):
    account_id = _create_account(client).json()["id"]
    r = client.delete(f"/accounts/{account_id}")
    assert r.status_code == 204
    assert client.get(f"/accounts/{account_id}").status_code == 404


def test_at13_delete_account_con_sesion_activa(client):
    account_id = _create_account(client).json()["id"]
    _add_world(client, account_id)
    app.state.world_runtime_port = _FakeRuntimePort(active=True)
    r = client.delete(f"/accounts/{account_id}")
    assert r.status_code == 409


def test_at14_delete_account_inexistente(client):
    r = client.delete("/accounts/9999")
    assert r.status_code == 404


def test_at24_password_nunca_en_respuesta(client):
    account_id = _create_account(client).json()["id"]
    assert "password" not in client.post(
        "/accounts", json={"email": "x@y.com", "username": "U", "password": "p"}
    ).json()
    assert "password" not in client.get(f"/accounts/{account_id}").json()
    assert "password" not in client.get("/accounts").json()["accounts"][0]


# ---------------------------------------------------------------------------
# Mundos
# ---------------------------------------------------------------------------

def test_at15_post_world_tribu_jugable(client):
    account_id = _create_account(client).json()["id"]
    r = _add_world(client, account_id, tribe="romans")
    assert r.status_code == 201
    body = r.json()
    assert body["tribe"] == "romans"
    assert r.headers["Location"] == f"/accounts/{account_id}/worlds/{body['id']}"


def test_at16_post_world_tribu_npc_nature(client):
    account_id = _create_account(client).json()["id"]
    r = _add_world(client, account_id, tribe="nature")
    assert r.status_code == 422


def test_at16b_post_world_tribu_npc_natars(client):
    account_id = _create_account(client).json()["id"]
    r = _add_world(client, account_id, tribe="natars")
    assert r.status_code == 422


def test_at17_post_world_url_sin_protocolo(client):
    account_id = _create_account(client).json()["id"]
    r = _add_world(client, account_id, server="ts1.travian.com")
    assert r.status_code == 422


def test_at18_post_world_duplicado_misma_cuenta(client):
    account_id = _create_account(client).json()["id"]
    _add_world(client, account_id)
    r = _add_world(client, account_id)  # mismo server
    assert r.status_code == 409


def test_at18b_mismo_server_en_cuentas_distintas_permitido(client):
    id1 = _create_account(client, email="uno@example.com").json()["id"]
    id2 = _create_account(client, email="dos@example.com").json()["id"]
    assert _add_world(client, id1).status_code == 201
    assert _add_world(client, id2).status_code == 201  # mismo server, otra cuenta → permitido


def test_at19_post_world_cuenta_inexistente(client):
    r = _add_world(client, 9999)
    assert r.status_code == 404


def test_at20_get_worlds_vacio(client):
    account_id = _create_account(client).json()["id"]
    r = client.get(f"/accounts/{account_id}/worlds")
    assert r.status_code == 200
    assert r.json() == {"worlds": []}


def test_at21_delete_world_ok(client):
    account_id = _create_account(client).json()["id"]
    world_id = _add_world(client, account_id).json()["id"]
    r = client.delete(f"/accounts/{account_id}/worlds/{world_id}")
    assert r.status_code == 204
    assert client.get(f"/accounts/{account_id}/worlds").json() == {"worlds": []}


def test_at22_delete_world_con_sesion_activa(client):
    account_id = _create_account(client).json()["id"]
    world_id = _add_world(client, account_id).json()["id"]
    app.state.world_runtime_port = _FakeRuntimePort(active=True)
    r = client.delete(f"/accounts/{account_id}/worlds/{world_id}")
    assert r.status_code == 409


def test_at23_delete_world_no_pertenece_a_la_cuenta(client):
    id1 = _create_account(client, email="uno@example.com").json()["id"]
    id2 = _create_account(client, email="dos@example.com").json()["id"]
    world_id = _add_world(client, id1).json()["id"]
    r = client.delete(f"/accounts/{id2}/worlds/{world_id}")  # world de id1, cuenta id2
    assert r.status_code == 404
