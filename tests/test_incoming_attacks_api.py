"""
Tests de integración para el radar de ataques entrantes.

EP-RA01: GET /game/incoming-attacks/{world_id}
EP-RA02: POST /game/incoming-attacks/{world_id}/check

Cobertura:
  - Camino feliz: 200 con wrapper correcto, cabeceras mínimas presentes.
  - seconds_remaining null cuando impact_at es None.
  - seconds_remaining calculado cuando impact_at es futuro.
  - include_past filtra ataques pasados correctamente.
  - village_game_id filtra por aldea.
  - Paginación: limit/offset.
  - 404 cuando el mundo no existe (EP-RA01 y EP-RA02).
  - 422 cuando los query params son inválidos.
  - 503 cuando no hay sesión activa (EP-RA02).
  - Cabeceras mínimas: Content-Type, X-Request-ID, X-API-Version.
  - Eco de X-Request-ID.

Estrategia:
  - TestClient con BD temporal (monkeypatch de DB_PATH).
  - Lifespan real para inicializar todos los puertos.
  - Inserta ataques directamente en BD para aislar de la capa browser.
  - EP-RA02 usa un mock del browser adapter para simular la sesión.

Añadido en la feature radar-ataques-entrantes (2026-06-05).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from adapters.api.main import app


# ---------------------------------------------------------------------------
# Fixture de cliente con BD temporal
# ---------------------------------------------------------------------------

# Atributos de app.state que deben limpiarse entre tests para evitar estado residual
_STATE_ATTRS = (
    "world_runtime_port",
    "farm_db_port",
    "world_agents",
    "session_db_port",
    "db_port",
    "incoming_attack_port",
    "noise_db_port",
)


@pytest.fixture
def client(monkeypatch, tmp_path):
    """TestClient con BD en archivo temporal y lifespan real."""
    db_file = tmp_path / "test_incoming_attacks.db"
    monkeypatch.setattr("adapters.db.database.DB_PATH", str(db_file))
    # Limpiar state residual de tests anteriores
    for attr in _STATE_ATTRS:
        if hasattr(app.state, attr):
            delattr(app.state, attr)
    with TestClient(app) as c:
        yield c
    for attr in _STATE_ATTRS:
        if hasattr(app.state, attr):
            delattr(app.state, attr)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert_cabeceras_minimas(response) -> None:
    """Verifica que las cabeceras mínimas obligatorias están presentes."""
    ct = response.headers.get("content-type", "")
    assert "application/json" in ct, f"Content-Type incorrecto: {ct}"
    assert "charset=utf-8" in ct, f"charset ausente en Content-Type: {ct}"
    assert "x-request-id" in response.headers, "X-Request-ID ausente"
    assert "x-api-version" in response.headers, "X-API-Version ausente"


def _setup_world(c: TestClient) -> tuple[int, int]:
    """Crea account + world vía HTTP. Devuelve (account_id, world_id)."""
    r = c.post(
        "/accounts",
        json={
            "email": "radar_test@example.com",
            "username": "radarbot",
            "password": "pass123",
        },
    )
    assert r.status_code == 201, r.text
    account_id = r.json()["id"]

    r = c.post(
        f"/accounts/{account_id}/worlds",
        json={"server": "https://ts1.travian.com/", "tribe": "romans"},
    )
    assert r.status_code == 201, r.text
    world_id = r.json()["id"]
    return account_id, world_id


def _insert_attack(c: TestClient, world_id: int, **overrides) -> None:
    """
    Inserta un ataque en la BD directamente usando el adaptador del app.state.
    Permite pasar overrides para personalizar el registro.
    """
    from core.ports.incoming_attack_db_port import IncomingAttackRecord

    now_iso = datetime.now(timezone.utc).isoformat()
    record = IncomingAttackRecord(
        world_id=world_id,
        village_game_id=overrides.get("village_game_id", 11111),
        village_name=overrides.get("village_name", "Aldea Test"),
        village_coord_x=overrides.get("village_coord_x", 10),
        village_coord_y=overrides.get("village_coord_y", -20),
        attack_count=overrides.get("attack_count", 1),
        impact_at=overrides.get("impact_at", None),  # None por defecto = sin timer
        rally_point_href=overrides.get("rally_point_href", "/build.php?gid=16&id=1"),
        attacker_name=overrides.get("attacker_name", None),
        origin_village_name=overrides.get("origin_village_name", None),
        origin_village_coord_x=overrides.get("origin_village_coord_x", None),
        origin_village_coord_y=overrides.get("origin_village_coord_y", None),
        operation_type=overrides.get("operation_type", None),
        attacker_snapshot_json=overrides.get("attacker_snapshot_json", None),
        source=overrides.get("source", "dorf1"),
        detected_at=overrides.get("detected_at", now_iso),
        updated_at=overrides.get("updated_at", now_iso),
    )
    port = app.state.incoming_attack_port
    # asyncio.run() crea un nuevo event loop temporal — necesario en Python 3.14
    # donde get_event_loop() ya no crea uno implícitamente en el hilo principal.
    asyncio.run(port.upsert_attack(record))


# ---------------------------------------------------------------------------
# EP-RA01 — Camino feliz: 200, wrapper correcto, cabeceras mínimas
# ---------------------------------------------------------------------------

def test_ep_ra01_lista_vacia_devuelve_200_wrapper_correcto(client):
    """EP-RA01: mundo sin ataques → 200 con items=[], total=0, limit, offset."""
    c = client
    _, world_id = _setup_world(c)

    r = c.get(f"/game/incoming-attacks/{world_id}")

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["limit"] == 50
    assert data["offset"] == 0
    _assert_cabeceras_minimas(r)


def test_ep_ra01_con_ataque_sin_timer_devuelve_seconds_remaining_null(client):
    """EP-RA01: ataque con impact_at=None → seconds_remaining es null en la respuesta."""
    c = client
    _, world_id = _setup_world(c)
    _insert_attack(c, world_id, impact_at=None)

    r = c.get(f"/game/incoming-attacks/{world_id}")

    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["seconds_remaining"] is None
    assert items[0]["impact_at"] is None


def test_ep_ra01_con_ataque_con_timer_futuro_devuelve_seconds_remaining_positivo(client):
    """EP-RA01: ataque con impact_at futuro → seconds_remaining > 0."""
    c = client
    _, world_id = _setup_world(c)
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    _insert_attack(c, world_id, impact_at=future)

    r = c.get(f"/game/incoming-attacks/{world_id}")

    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1
    sr = items[0]["seconds_remaining"]
    assert sr is not None
    assert sr > 0
    assert sr <= 3600


def test_ep_ra01_ataque_pasado_no_aparece_por_defecto(client):
    """EP-RA01: ataque con impact_at pasado → no aparece sin include_past=true."""
    c = client
    _, world_id = _setup_world(c)
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    _insert_attack(c, world_id, impact_at=past)

    r = c.get(f"/game/incoming-attacks/{world_id}")

    assert r.status_code == 200, r.text
    assert r.json()["total"] == 0
    assert r.json()["items"] == []


def test_ep_ra01_include_past_true_incluye_ataques_pasados(client):
    """EP-RA01: include_past=true → incluye ataques con impact_at ya pasado."""
    c = client
    _, world_id = _setup_world(c)
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    _insert_attack(c, world_id, impact_at=past)

    r = c.get(f"/game/incoming-attacks/{world_id}?include_past=true")

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1


def test_ep_ra01_filtro_village_game_id(client):
    """EP-RA01: village_game_id filtra por aldea correctamente."""
    c = client
    _, world_id = _setup_world(c)
    _insert_attack(c, world_id, village_game_id=11111)
    _insert_attack(c, world_id, village_game_id=22222)

    r = c.get(f"/game/incoming-attacks/{world_id}?include_past=true&village_game_id=11111")

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["village_game_id"] == 11111


def test_ep_ra01_paginacion_limit_offset(client):
    """EP-RA01: limit y offset paginan correctamente."""
    c = client
    _, world_id = _setup_world(c)
    # Insertar 3 ataques pasados (para tenerlos todos) con village_game_id distintos
    for vid in [11111, 22222, 33333]:
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        _insert_attack(c, world_id, village_game_id=vid, impact_at=past)

    r_all = c.get(f"/game/incoming-attacks/{world_id}?include_past=true&limit=100")
    assert r_all.json()["total"] == 3

    r_p1 = c.get(f"/game/incoming-attacks/{world_id}?include_past=true&limit=2&offset=0")
    r_p2 = c.get(f"/game/incoming-attacks/{world_id}?include_past=true&limit=2&offset=2")

    assert len(r_p1.json()["items"]) == 2
    assert len(r_p2.json()["items"]) == 1
    assert r_p1.json()["limit"] == 2
    assert r_p1.json()["offset"] == 0
    assert r_p2.json()["offset"] == 2


def test_ep_ra01_campos_del_item_presentes(client):
    """EP-RA01: cada item del wrapper tiene todos los campos del contrato."""
    c = client
    _, world_id = _setup_world(c)
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    _insert_attack(
        c,
        world_id,
        village_game_id=55555,
        village_name="Aldea Alfa",
        village_coord_x=100,
        village_coord_y=-50,
        attack_count=3,
        impact_at=future,
        rally_point_href="/build.php?gid=16&id=7",
        source="dorf1",
    )

    r = c.get(f"/game/incoming-attacks/{world_id}")
    assert r.status_code == 200, r.text
    item = r.json()["items"][0]

    campos_esperados = [
        "id", "village_game_id", "village_name",
        "village_coord_x", "village_coord_y",
        "attack_count", "impact_at", "seconds_remaining",
        "rally_point_href", "attacker_name", "origin_village_name",
        "origin_village_coord_x", "origin_village_coord_y",
        "operation_type", "attacker_snapshot", "source", "detected_at",
    ]
    for campo in campos_esperados:
        assert campo in item, f"Campo '{campo}' ausente en el item"


def test_ep_ra01_wrapper_no_incluye_world_id_en_raiz(client):
    """EP-RA01: el wrapper raíz NO tiene campo world_id (solo items/total/limit/offset)."""
    c = client
    _, world_id = _setup_world(c)

    r = c.get(f"/game/incoming-attacks/{world_id}")
    assert r.status_code == 200
    data = r.json()
    assert "world_id" not in data
    assert set(data.keys()) == {"items", "total", "limit", "offset"}


# ---------------------------------------------------------------------------
# EP-RA01 — Errores
# ---------------------------------------------------------------------------

def test_ep_ra01_mundo_no_existe_devuelve_404(client):
    """EP-RA01: world_id que no existe → 404."""
    c = client
    r = c.get("/game/incoming-attacks/99999")
    assert r.status_code == 404, r.text
    _assert_cabeceras_minimas(r)


def test_ep_ra01_limit_cero_devuelve_422(client):
    """EP-RA01: limit=0 viola ge=1 → 422."""
    c = client
    _, world_id = _setup_world(c)
    r = c.get(f"/game/incoming-attacks/{world_id}?limit=0")
    assert r.status_code == 422, r.text


def test_ep_ra01_limit_mayor_100_devuelve_422(client):
    """EP-RA01: limit=101 viola le=100 → 422."""
    c = client
    _, world_id = _setup_world(c)
    r = c.get(f"/game/incoming-attacks/{world_id}?limit=101")
    assert r.status_code == 422, r.text


def test_ep_ra01_offset_negativo_devuelve_422(client):
    """EP-RA01: offset=-1 viola ge=0 → 422."""
    c = client
    _, world_id = _setup_world(c)
    r = c.get(f"/game/incoming-attacks/{world_id}?offset=-1")
    assert r.status_code == 422, r.text


def test_ep_ra01_village_game_id_cero_devuelve_422(client):
    """EP-RA01: village_game_id=0 viola ge=1 → 422."""
    c = client
    _, world_id = _setup_world(c)
    r = c.get(f"/game/incoming-attacks/{world_id}?village_game_id=0")
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# EP-RA01 — Cabeceras
# ---------------------------------------------------------------------------

def test_ep_ra01_cabeceras_minimas_presentes(client):
    """EP-RA01: respuesta 200 tiene Content-Type, X-Request-ID, X-API-Version."""
    c = client
    _, world_id = _setup_world(c)
    r = c.get(f"/game/incoming-attacks/{world_id}")
    assert r.status_code == 200
    _assert_cabeceras_minimas(r)


def test_ep_ra01_eco_x_request_id(client):
    """EP-RA01: X-Request-ID enviado en la request vuelve idéntico en la respuesta."""
    c = client
    _, world_id = _setup_world(c)
    custom_id = "test-radar-12345"
    r = c.get(f"/game/incoming-attacks/{world_id}", headers={"X-Request-ID": custom_id})
    assert r.status_code == 200
    assert r.headers.get("x-request-id") == custom_id


# ---------------------------------------------------------------------------
# Helpers para EP-RA02 — mock de WorldAgent
# ---------------------------------------------------------------------------

def _make_fake_agent(state_value, check_result: int = 0):
    """
    Crea un fake WorldAgent con .state y .check_incoming_sidebar().

    state_value: AgentState enum (RUNNING / STOPPED).
    check_result: int devuelto por check_incoming_sidebar (nº de ataques).
    """
    fake = MagicMock()
    fake.state = state_value
    fake.check_incoming_sidebar = AsyncMock(return_value=check_result)
    return fake


# ---------------------------------------------------------------------------
# EP-RA02 — UT-B06..B09 + cabeceras + eco (spec radar-check-boton-sidebar §12)
# ---------------------------------------------------------------------------

# UT-B06 — WorldAgent no existe → 409
def test_ep_ra02_ut_b06_agente_no_existe_devuelve_409(client):
    """UT-B06: world_agents vacío (sin WorldAgent) → 409 con detail 'no está activo'."""
    from core.scheduling.world_agent import AgentState  # noqa: F401 — solo para que la clase se importe

    c = client
    _, world_id = _setup_world(c)
    app.state.world_agents = {}

    r = c.post(f"/game/incoming-attacks/{world_id}/check")

    assert r.status_code == 409, r.text
    assert "no está activo" in r.json()["detail"]
    _assert_cabeceras_minimas(r)


# UT-B07 — WorldAgent en estado STOPPED → 409
def test_ep_ra02_ut_b07_agente_stopped_devuelve_409(client):
    """UT-B07: WorldAgent con state=STOPPED → 409."""
    from core.scheduling.world_agent import AgentState

    c = client
    _, world_id = _setup_world(c)
    app.state.world_agents = {world_id: _make_fake_agent(AgentState.STOPPED)}

    r = c.post(f"/game/incoming-attacks/{world_id}/check")

    assert r.status_code == 409, r.text
    _assert_cabeceras_minimas(r)


# UT-B08 — WorldAgent RUNNING, sidebar sin ataques → 200 con attacks_detected=0
def test_ep_ra02_ut_b08_agente_running_sin_ataques_devuelve_200(client):
    """UT-B08: WorldAgent RUNNING, check_incoming_sidebar → 0 → 200 attacks_detected=0."""
    from core.scheduling.world_agent import AgentState

    c = client
    _, world_id = _setup_world(c)
    app.state.world_agents = {world_id: _make_fake_agent(AgentState.RUNNING, check_result=0)}

    r = c.post(f"/game/incoming-attacks/{world_id}/check")

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["attacks_detected"] == 0
    assert data["message"] == "Check completado"
    assert data["world_id"] == world_id
    _assert_cabeceras_minimas(r)


# UT-B09 — WorldAgent RUNNING, sidebar con 1 ataque → 200 con attacks_detected=1
def test_ep_ra02_ut_b09_agente_running_con_ataque_devuelve_200(client):
    """UT-B09: WorldAgent RUNNING, check_incoming_sidebar → 1 → 200 attacks_detected=1."""
    from core.scheduling.world_agent import AgentState

    c = client
    _, world_id = _setup_world(c)
    app.state.world_agents = {world_id: _make_fake_agent(AgentState.RUNNING, check_result=1)}

    r = c.post(f"/game/incoming-attacks/{world_id}/check")

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["attacks_detected"] == 1
    assert data["world_id"] == world_id
    _assert_cabeceras_minimas(r)


# 404 — mundo no existe (comportamiento existente, no cambia)
def test_ep_ra02_mundo_no_existe_devuelve_404(client):
    """EP-RA02: world_id inexistente → 404."""
    c = client
    r = c.post("/game/incoming-attacks/99999/check")
    assert r.status_code == 404, r.text
    _assert_cabeceras_minimas(r)


# Cabeceras mínimas — 200 con agente RUNNING
def test_ep_ra02_check_cabeceras_minimas(client):
    """EP-RA02: respuesta 200 tiene Content-Type, X-Request-ID, X-API-Version."""
    from core.scheduling.world_agent import AgentState

    c = client
    _, world_id = _setup_world(c)
    app.state.world_agents = {world_id: _make_fake_agent(AgentState.RUNNING, check_result=0)}

    r = c.post(f"/game/incoming-attacks/{world_id}/check")

    assert r.status_code == 200
    _assert_cabeceras_minimas(r)


# Eco de X-Request-ID — 200 con agente RUNNING
def test_ep_ra02_eco_x_request_id(client):
    """EP-RA02: X-Request-ID enviado en la request vuelve idéntico en la respuesta."""
    from core.scheduling.world_agent import AgentState

    c = client
    _, world_id = _setup_world(c)
    app.state.world_agents = {world_id: _make_fake_agent(AgentState.RUNNING, check_result=0)}

    custom_id = "radar-check-9999"
    r = c.post(
        f"/game/incoming-attacks/{world_id}/check",
        headers={"X-Request-ID": custom_id},
    )
    assert r.headers.get("x-request-id") == custom_id


# world_agents no existe en app.state (EC-B01) → 409 (getattr devuelve {} → agente None)
def test_ep_ra02_world_agents_ausente_devuelve_409(client):
    """EP-RA02: EC-B01 — world_agents no existe en app.state → 409."""
    c = client
    _, world_id = _setup_world(c)
    if hasattr(app.state, "world_agents"):
        delattr(app.state, "world_agents")

    r = c.post(f"/game/incoming-attacks/{world_id}/check")

    assert r.status_code == 409, r.text


# ---------------------------------------------------------------------------
# EP-RA01 — seconds_remaining: casos límite
# ---------------------------------------------------------------------------

def test_ep_ra01_seconds_remaining_no_negativo_para_impacto_ya_pasado(client):
    """
    EP-RA01: impact_at ya pasado pero impact_at IS NOT NULL → seconds_remaining=0
    (max(0, ...) garantizado por el use case).
    Solo aplica cuando include_past=true, porque por defecto los pasados se ocultan.
    """
    c = client
    _, world_id = _setup_world(c)
    past = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    _insert_attack(c, world_id, impact_at=past)

    r = c.get(f"/game/incoming-attacks/{world_id}?include_past=true")

    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    # El use case garantiza max(0, ...) → nunca negativo
    assert items[0]["seconds_remaining"] == 0


# ---------------------------------------------------------------------------
# EP-RA03 — GET /game/incoming-attacks/summary
# ---------------------------------------------------------------------------

def test_ep_ra03_sin_mundos_devuelve_lista_vacia(client):
    """EP-RA03: sin mundos en BD → 200 con lista vacía []."""
    c = client
    r = c.get("/game/incoming-attacks/summary")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data == []


def test_ep_ra03_un_mundo_sin_ataques_devuelve_pending_cero(client):
    """EP-RA03: un mundo sin ataques → [{world_id, pending_attacks: 0}]."""
    c = client
    _, world_id = _setup_world(c)

    r = c.get("/game/incoming-attacks/summary")

    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 1
    entry = data[0]
    assert entry["world_id"] == world_id
    assert entry["pending_attacks"] == 0


def test_ep_ra03_cuenta_ataques_pendientes_correctamente(client):
    """EP-RA03: con ataques pendientes → pending_attacks con recuento correcto."""
    c = client
    _, world_id = _setup_world(c)
    # Ataque pendiente con timer futuro
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    _insert_attack(c, world_id, village_game_id=11111, impact_at=future)
    # Ataque pendiente sin timer (sidebar)
    _insert_attack(c, world_id, village_game_id=22222, impact_at=None)

    r = c.get("/game/incoming-attacks/summary")

    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data) == 1
    entry = data[0]
    assert entry["world_id"] == world_id
    assert entry["pending_attacks"] == 2


def test_ep_ra03_no_cuenta_ataques_pasados(client):
    """EP-RA03: ataques con impact_at en el pasado no se cuentan en pending_attacks."""
    c = client
    _, world_id = _setup_world(c)
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    _insert_attack(c, world_id, village_game_id=99999, impact_at=past)

    r = c.get("/game/incoming-attacks/summary")

    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data) == 1
    assert data[0]["pending_attacks"] == 0


def test_ep_ra03_incluye_todos_los_mundos_aunque_tengan_cero_ataques(client):
    """EP-RA03: todos los mundos aparecen en la respuesta, incluso los de 0 ataques."""
    c = client
    # Crear dos mundos
    r = c.post(
        "/accounts",
        json={
            "email": "summary_multi@example.com",
            "username": "multiworld",
            "password": "pass123",
        },
    )
    assert r.status_code == 201
    account_id = r.json()["id"]

    r1 = c.post(
        f"/accounts/{account_id}/worlds",
        json={"server": "https://ts1.travian.com/", "tribe": "romans"},
    )
    r2 = c.post(
        f"/accounts/{account_id}/worlds",
        json={"server": "https://ts2.travian.com/", "tribe": "gauls"},
    )
    world_id_1 = r1.json()["id"]
    world_id_2 = r2.json()["id"]

    # Solo el mundo 1 tiene ataques
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    _insert_attack(c, world_id_1, village_game_id=11111, impact_at=future)

    r = c.get("/game/incoming-attacks/summary")

    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data) == 2

    world_ids_en_respuesta = {entry["world_id"] for entry in data}
    assert world_id_1 in world_ids_en_respuesta
    assert world_id_2 in world_ids_en_respuesta

    by_world = {entry["world_id"]: entry["pending_attacks"] for entry in data}
    assert by_world[world_id_1] == 1
    assert by_world[world_id_2] == 0


def test_ep_ra03_shape_correcto_de_cada_item(client):
    """EP-RA03: cada item tiene exactamente los campos world_id y pending_attacks."""
    c = client
    _, world_id = _setup_world(c)

    r = c.get("/game/incoming-attacks/summary")

    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data) == 1
    entry = data[0]
    assert set(entry.keys()) == {"world_id", "pending_attacks"}
    assert isinstance(entry["world_id"], int)
    assert isinstance(entry["pending_attacks"], int)


def test_ep_ra03_cabeceras_minimas(client):
    """EP-RA03: respuesta 200 tiene Content-Type, X-Request-ID, X-API-Version."""
    c = client
    r = c.get("/game/incoming-attacks/summary")
    assert r.status_code == 200
    _assert_cabeceras_minimas(r)


def test_ep_ra03_eco_x_request_id(client):
    """EP-RA03: X-Request-ID enviado en la request vuelve idéntico en la respuesta."""
    c = client
    custom_id = "summary-badge-test-001"
    r = c.get("/game/incoming-attacks/summary", headers={"X-Request-ID": custom_id})
    assert r.status_code == 200
    assert r.headers.get("x-request-id") == custom_id


def test_ep_ra03_sin_accept_language_no_falla(client):
    """EP-RA03: sin Accept-Language → 200 sin problema (endpoint no localizado)."""
    c = client
    _, world_id = _setup_world(c)
    # No enviar Accept-Language explícitamente
    r = c.get("/game/incoming-attacks/summary")
    assert r.status_code == 200, r.text


def test_ep_ra03_no_confunde_summary_con_world_id_int(client):
    """
    EP-RA03: GET /game/incoming-attacks/summary no devuelve 422 (FastAPI no intenta
    parsear 'summary' como int de world_id). Verifica el orden de declaración de rutas.
    """
    c = client
    r = c.get("/game/incoming-attacks/summary")
    # Si la ruta está mal ordenada, FastAPI intentaría parsear 'summary' como int → 422.
    # El resultado correcto es 200 (o como mínimo NOT 422).
    assert r.status_code != 422, (
        "FastAPI intentó parsear 'summary' como int — revisar el orden de declaración de rutas."
    )
