"""
Tests de contrato para EP-N14 — POST /worlds/{id}/noise/paths/{path_id}/test.

Spec: noise-path-wizard.md §16.8

Estrategia:
  - TestClient con BD temporal (monkeypatch de DB_PATH).
  - Lifespan real (TestClient en modo context manager).
  - agent.execute_path_test se mockea con AsyncMock para aislar el dominio.
  - BrowserBusyError se importa de core.exceptions.
  - PathTestReport se construye como SimpleNamespace para evitar importar el
    dataclass que implementará desarrollador-funcionalidades.

Cobertura:
  1. 200 ruta OK (overall="ok", todos los pasos ok)
  2. 200 ruta con fallo (overall="error") — HTTP 200 aunque la ruta falle
  3. 404 mundo inexistente
  4. 404 path inexistente
  5. 409 agente no activo (no existe en world_agents)
  6. 409 agente STOPPED (estado != RUNNING)
  7. 409 browser ocupado (BrowserBusyError desde execute_path_test)
  8. 200 ruta sin pasos (steps=[])
  9. 200 origin=ANY → anchor_navigated_to=null
 10. Cabeceras mínimas: Content-Type JSON
 11. 500 RuntimeError inesperado en execute_path_test
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from adapters.api.main import app
from core.exceptions import BrowserBusyError


# ---------------------------------------------------------------------------
# Helper cabeceras mínimas
# ---------------------------------------------------------------------------

def assert_cabeceras_minimas(response) -> None:
    """Verifica que Content-Type sea application/json en respuestas con cuerpo."""
    assert "application/json" in response.headers.get("content-type", ""), (
        f"Content-Type debe ser application/json, got: {response.headers.get('content-type')}"
    )


# ---------------------------------------------------------------------------
# Fixture de cliente HTTP con BD temporal
# ---------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch, tmp_path):
    """TestClient con BD en archivo temporal y lifespan real."""
    db_file = tmp_path / "test_ep_n14.db"
    monkeypatch.setattr("adapters.db.database.DB_PATH", str(db_file))
    for attr in ("world_runtime_port", "farm_db_port", "world_agents",
                 "session_db_port", "db_port", "noise_db_port"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)
    with TestClient(app) as c:
        yield c
    for attr in ("world_runtime_port", "farm_db_port", "world_agents",
                 "session_db_port", "db_port", "noise_db_port"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)


# ---------------------------------------------------------------------------
# Helpers de setup
# ---------------------------------------------------------------------------

def _setup_world(c: TestClient, server: str = "https://ts1.travian.es/") -> tuple[int, int]:
    """Crea account + world vía HTTP. Devuelve (account_id, world_id)."""
    r = c.post(
        "/accounts",
        json={
            "email": "n14_test@example.com",
            "username": "n14bot",
            "password": "pass123",
        },
    )
    assert r.status_code == 201, r.text
    account_id = r.json()["id"]

    r = c.post(
        f"/accounts/{account_id}/worlds",
        json={"server": server, "tribe": "romans"},
    )
    assert r.status_code == 201, r.text
    world_id = r.json()["id"]
    return account_id, world_id


def _create_destination_and_path(
    c: TestClient, world_id: int, origin: str = "MAP"
) -> tuple[int, int]:
    """Crea un destino y una ruta básica con un paso. Devuelve (dest_id, path_id)."""
    r = c.post(
        f"/worlds/{world_id}/noise/destinations",
        json={"url_pattern": "/karte.php", "label": "Mapa", "category_slug": "uncategorized"},
    )
    assert r.status_code == 201, r.text
    dest_id = r.json()["id"]

    r = c.post(
        f"/worlds/{world_id}/noise/destinations/{dest_id}/paths",
        json={
            "origin": origin,
            "label": "Ruta de prueba EP-N14",
            "steps": [
                {
                    "step_order": 0,
                    "action": "CLICK",
                    "selector": "a[href*='karte']",
                },
            ],
        },
    )
    assert r.status_code == 201, r.text
    path_id = r.json()["id"]
    return dest_id, path_id


def _make_step_result(
    step_order: int,
    action: str = "CLICK",
    selector: str = "a[href='/statistics']",
    status: str = "ok",
    reason: str | None = None,
    current_url: str | None = "https://ts1.travian.es/statistics",
) -> SimpleNamespace:
    """Construye un PathTestStepResult simulado."""
    return SimpleNamespace(
        step_order=step_order,
        action=action,
        selector=selector,
        status=status,
        reason=reason,
        current_url=current_url,
    )


def _make_report(
    overall: str = "ok",
    steps: list | None = None,
    aborted_at_step: int | None = None,
    anchor_navigated_to: str | None = "https://ts1.travian.es/statistics",
) -> SimpleNamespace:
    """Construye un PathTestReport simulado."""
    return SimpleNamespace(
        overall=overall,
        steps=steps if steps is not None else [],
        aborted_at_step=aborted_at_step,
        anchor_navigated_to=anchor_navigated_to,
    )


def _mock_running_agent(world_id: int, execute_path_test_return) -> MagicMock:
    """Devuelve un MagicMock de WorldAgent con estado RUNNING y execute_path_test mockeado."""
    from core.scheduling.world_agent import AgentState
    agent_mock = MagicMock()
    agent_mock.state = AgentState.RUNNING
    agent_mock.execute_path_test = AsyncMock(return_value=execute_path_test_return)
    return agent_mock


# ---------------------------------------------------------------------------
# Test 1 — 200 ruta OK (overall="ok")
# ---------------------------------------------------------------------------

def test_EP_N14_ruta_ok_devuelve_200_con_overall_ok(client):
    """Happy path: ruta se ejecuta con éxito → 200, overall='ok', steps con datos."""
    _, world_id = _setup_world(client)
    _, path_id = _create_destination_and_path(client, world_id)

    step0 = _make_step_result(
        step_order=0,
        action="CLICK",
        selector="a[href='/statistics']",
        status="ok",
        reason=None,
        current_url="https://ts1.travian.es/statistics",
    )
    report = _make_report(
        overall="ok",
        steps=[step0],
        aborted_at_step=None,
        anchor_navigated_to="https://ts1.travian.es/statistics",
    )

    agent_mock = _mock_running_agent(world_id, report)
    app.state.world_agents[world_id] = agent_mock

    r = client.post(f"/worlds/{world_id}/noise/paths/{path_id}/test")
    assert r.status_code == 200, r.text

    data = r.json()
    assert data["overall"] == "ok"
    assert data["aborted_at_step"] is None
    assert data["anchor_navigated_to"] == "https://ts1.travian.es/statistics"
    assert len(data["steps"]) == 1
    assert data["steps"][0]["step_order"] == 0
    assert data["steps"][0]["action"] == "CLICK"
    assert data["steps"][0]["selector"] == "a[href='/statistics']"
    assert data["steps"][0]["status"] == "ok"
    assert data["steps"][0]["reason"] is None
    assert data["steps"][0]["current_url"] == "https://ts1.travian.es/statistics"
    assert "browser_note" in data


# ---------------------------------------------------------------------------
# Test 2 — 200 ruta con fallo (overall="error")
# ---------------------------------------------------------------------------

def test_EP_N14_ruta_con_fallo_devuelve_200_con_overall_error(client):
    """Ruta con un paso fallido → HTTP 200 (endpoint ejecutó correctamente), overall='error'."""
    _, world_id = _setup_world(client)
    _, path_id = _create_destination_and_path(client, world_id)

    step0 = _make_step_result(
        step_order=0,
        action="CLICK",
        selector="a[href='/bad-path']",
        status="error",
        reason="elemento no encontrado en el DOM",
        current_url="https://ts1.travian.es/statistics",
    )
    report = _make_report(
        overall="error",
        steps=[step0],
        aborted_at_step=0,
        anchor_navigated_to="https://ts1.travian.es/statistics",
    )

    agent_mock = _mock_running_agent(world_id, report)
    app.state.world_agents[world_id] = agent_mock

    r = client.post(f"/worlds/{world_id}/noise/paths/{path_id}/test")
    assert r.status_code == 200, r.text

    data = r.json()
    assert data["overall"] == "error"
    assert data["aborted_at_step"] == 0
    assert len(data["steps"]) == 1
    assert data["steps"][0]["status"] == "error"
    assert data["steps"][0]["reason"] == "elemento no encontrado en el DOM"


# ---------------------------------------------------------------------------
# Test 3 — 404 mundo inexistente
# ---------------------------------------------------------------------------

def test_EP_N14_mundo_inexistente_devuelve_404(client):
    """Mundo que no existe → 404 antes de verificar el agente."""
    r = client.post("/worlds/99999/noise/paths/1/test")
    assert r.status_code == 404, r.text
    assert "mundo" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 4 — 404 path inexistente
# ---------------------------------------------------------------------------

def test_EP_N14_path_inexistente_devuelve_404(client):
    """Mundo existe pero path no → 404."""
    _, world_id = _setup_world(client)

    from core.scheduling.world_agent import AgentState
    agent_mock = MagicMock()
    agent_mock.state = AgentState.RUNNING
    app.state.world_agents[world_id] = agent_mock

    r = client.post(f"/worlds/{world_id}/noise/paths/99999/test")
    assert r.status_code == 404, r.text
    assert "ruta" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 5 — 409 agente no activo (no existe en world_agents)
# ---------------------------------------------------------------------------

def test_EP_N14_sin_agente_devuelve_409(client):
    """Sin WorldAgent iniciado para el mundo → 409."""
    _, world_id = _setup_world(client)
    _, path_id = _create_destination_and_path(client, world_id)

    # world_agents existe pero no tiene este world_id → agent es None → 409
    r = client.post(f"/worlds/{world_id}/noise/paths/{path_id}/test")
    assert r.status_code == 409, r.text
    detail = r.json()["detail"].lower()
    assert "desconectado" in detail or "sesión" in detail or "inicia" in detail


# ---------------------------------------------------------------------------
# Test 6 — 409 agente STOPPED (estado != RUNNING)
# ---------------------------------------------------------------------------

def test_EP_N14_agente_stopped_devuelve_409(client):
    """WorldAgent en estado STOPPED → 409."""
    _, world_id = _setup_world(client)
    _, path_id = _create_destination_and_path(client, world_id)

    from core.scheduling.world_agent import AgentState
    agent_mock = MagicMock()
    agent_mock.state = AgentState.STOPPED
    app.state.world_agents[world_id] = agent_mock

    r = client.post(f"/worlds/{world_id}/noise/paths/{path_id}/test")
    assert r.status_code == 409, r.text


# ---------------------------------------------------------------------------
# Test 6b — 409 agente RUNNING pero sin sesión de browser (DISCONNECTED)
# ---------------------------------------------------------------------------

def test_EP_N14_running_sin_sesion_devuelve_409(client):
    """
    Regresión: el agente está RUNNING (loop vivo) pero el bloque horario es
    DISCONNECTED → no hay Chrome abierto (_session_active() == False).

    Antes esto pasaba la precondición (que solo miraba state==RUNNING) y
    execute_path_test lanzaba RuntimeError('no hay browser activo') → 500.
    Ahora debe devolver un 409 claro ('inicia sesión primero'), no un 500.
    """
    _, world_id = _setup_world(client)
    _, path_id = _create_destination_and_path(client, world_id)

    from core.scheduling.world_agent import AgentState
    agent_mock = MagicMock()
    agent_mock.state = AgentState.RUNNING
    agent_mock._session_active.return_value = False  # sesión DISCONNECTED
    # execute_path_test NO debe ni llegar a llamarse
    agent_mock.execute_path_test = AsyncMock(
        side_effect=AssertionError("no debe ejecutarse sin sesión activa")
    )
    app.state.world_agents[world_id] = agent_mock

    r = client.post(f"/worlds/{world_id}/noise/paths/{path_id}/test")
    assert r.status_code == 409, r.text
    assert "sesión" in r.json()["detail"].lower() or "sesion" in r.json()["detail"].lower() \
        or "desconectado" in r.json()["detail"].lower()
    agent_mock.execute_path_test.assert_not_called()


# ---------------------------------------------------------------------------
# Test 7 — 409 browser ocupado (BrowserBusyError)
# ---------------------------------------------------------------------------

def test_EP_N14_browser_ocupado_devuelve_409(client):
    """execute_path_test lanza BrowserBusyError → 409 con detail 'browser ocupado'."""
    _, world_id = _setup_world(client)
    _, path_id = _create_destination_and_path(client, world_id)

    from core.scheduling.world_agent import AgentState
    agent_mock = MagicMock()
    agent_mock.state = AgentState.RUNNING
    agent_mock.execute_path_test = AsyncMock(
        side_effect=BrowserBusyError(world_id=world_id, timeout_s=60)
    )
    app.state.world_agents[world_id] = agent_mock

    r = client.post(f"/worlds/{world_id}/noise/paths/{path_id}/test")
    assert r.status_code == 409, r.text
    detail = r.json()["detail"].lower()
    assert "browser" in detail and "ocupado" in detail


# ---------------------------------------------------------------------------
# Test 8 — 200 ruta sin pasos (steps=[])
# ---------------------------------------------------------------------------

def test_EP_N14_ruta_sin_pasos_devuelve_200_ok(client):
    """Ruta sin pasos → overall='ok', steps=[], el endpoint se ejecutó correctamente."""
    _, world_id = _setup_world(client)
    _, path_id = _create_destination_and_path(client, world_id)

    report = _make_report(
        overall="ok",
        steps=[],
        aborted_at_step=None,
        anchor_navigated_to="https://ts1.travian.es/statistics",
    )
    agent_mock = _mock_running_agent(world_id, report)
    app.state.world_agents[world_id] = agent_mock

    r = client.post(f"/worlds/{world_id}/noise/paths/{path_id}/test")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["overall"] == "ok"
    assert data["steps"] == []
    assert data["aborted_at_step"] is None
    assert data["anchor_navigated_to"] == "https://ts1.travian.es/statistics"


# ---------------------------------------------------------------------------
# Test 9 — 200 origin=ANY → anchor_navigated_to=null
# ---------------------------------------------------------------------------

def test_EP_N14_origin_any_anchor_es_null(client):
    """origin=ANY → execute_path_test no navega al ancla → anchor_navigated_to=null."""
    _, world_id = _setup_world(client)
    _, path_id = _create_destination_and_path(client, world_id, origin="ANY")  # ANY es siempre válido

    step0 = _make_step_result(
        step_order=0, status="ok", current_url="https://ts1.travian.es/dorf1.php"
    )
    report = _make_report(
        overall="ok",
        steps=[step0],
        aborted_at_step=None,
        anchor_navigated_to=None,  # origin=ANY
    )
    agent_mock = _mock_running_agent(world_id, report)
    app.state.world_agents[world_id] = agent_mock

    r = client.post(f"/worlds/{world_id}/noise/paths/{path_id}/test")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["anchor_navigated_to"] is None


# ---------------------------------------------------------------------------
# Test 10 — Cabeceras mínimas: Content-Type JSON
# ---------------------------------------------------------------------------

def test_EP_N14_respuesta_200_tiene_content_type_json(client):
    """La respuesta 200 incluye Content-Type: application/json."""
    _, world_id = _setup_world(client)
    _, path_id = _create_destination_and_path(client, world_id)

    report = _make_report(overall="ok", steps=[])
    agent_mock = _mock_running_agent(world_id, report)
    app.state.world_agents[world_id] = agent_mock

    r = client.post(f"/worlds/{world_id}/noise/paths/{path_id}/test")
    assert r.status_code == 200, r.text
    assert_cabeceras_minimas(r)


# ---------------------------------------------------------------------------
# Test 11 — 500 RuntimeError inesperado
# ---------------------------------------------------------------------------

def test_EP_N14_runtime_error_en_execute_path_test_devuelve_500(client):
    """execute_path_test lanza RuntimeError → 500 con detail 'error interno'."""
    _, world_id = _setup_world(client)
    _, path_id = _create_destination_and_path(client, world_id)

    from core.scheduling.world_agent import AgentState
    agent_mock = MagicMock()
    agent_mock.state = AgentState.RUNNING
    agent_mock.execute_path_test = AsyncMock(
        side_effect=RuntimeError("servidor del mundo no disponible")
    )
    app.state.world_agents[world_id] = agent_mock

    r = client.post(f"/worlds/{world_id}/noise/paths/{path_id}/test")
    assert r.status_code == 500, r.text
    assert "error interno" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 12 — body de respuesta 200 contiene todos los campos del contrato
# ---------------------------------------------------------------------------

def test_EP_N14_response_200_contiene_todos_los_campos_del_contrato(client):
    """La respuesta 200 incluye todos los campos definidos en §16.8."""
    _, world_id = _setup_world(client)
    _, path_id = _create_destination_and_path(client, world_id)

    step0 = _make_step_result(
        step_order=0,
        action="CLICK",
        selector="a[href='/statistics']",
        status="ok",
        reason=None,
        current_url="https://ts1.travian.es/statistics",
    )
    report = _make_report(
        overall="ok",
        steps=[step0],
        aborted_at_step=None,
        anchor_navigated_to="https://ts1.travian.es/statistics",
    )
    agent_mock = _mock_running_agent(world_id, report)
    app.state.world_agents[world_id] = agent_mock

    r = client.post(f"/worlds/{world_id}/noise/paths/{path_id}/test")
    assert r.status_code == 200, r.text
    data = r.json()

    # Campos raíz del PathTestResponse
    assert "overall" in data
    assert "aborted_at_step" in data
    assert "anchor_navigated_to" in data
    assert "steps" in data
    assert "browser_note" in data

    # Campos del PathTestStepResultResponse
    step = data["steps"][0]
    assert "step_order" in step
    assert "action" in step
    assert "selector" in step
    assert "status" in step
    assert "reason" in step
    assert "current_url" in step


# ---------------------------------------------------------------------------
# Test 13 — browser_note siempre presente y con el valor fijo del spec
# ---------------------------------------------------------------------------

def test_EP_N14_browser_note_siempre_presente_con_valor_fijo(client):
    """browser_note tiene el texto exacto definido en §16.8 (CA-PT16)."""
    _, world_id = _setup_world(client)
    _, path_id = _create_destination_and_path(client, world_id)

    report = _make_report(overall="ok", steps=[])
    agent_mock = _mock_running_agent(world_id, report)
    app.state.world_agents[world_id] = agent_mock

    r = client.post(f"/worlds/{world_id}/noise/paths/{path_id}/test")
    assert r.status_code == 200, r.text
    assert r.json()["browser_note"] == (
        "El browser queda en la última página visitada durante el test."
    )


# ---------------------------------------------------------------------------
# Test 14 — execute_path_test recibe el path correcto
# ---------------------------------------------------------------------------

def test_EP_N14_handler_pasa_path_correcto_al_agente(client):
    """El handler invoca execute_path_test con el NavigationPath correcto (por path_id)."""
    _, world_id = _setup_world(client)
    _, path_id = _create_destination_and_path(client, world_id)

    report = _make_report(overall="ok", steps=[])
    agent_mock = _mock_running_agent(world_id, report)
    app.state.world_agents[world_id] = agent_mock

    r = client.post(f"/worlds/{world_id}/noise/paths/{path_id}/test")
    assert r.status_code == 200, r.text

    agent_mock.execute_path_test.assert_called_once()
    # El primer argumento posicional es el NavigationPath
    call_args = agent_mock.execute_path_test.call_args
    path_arg = call_args[0][0]  # primer positional
    assert path_arg.id == path_id
