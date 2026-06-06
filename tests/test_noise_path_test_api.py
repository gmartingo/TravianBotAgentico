"""
Tests de integración HTTP para EP-N14 — POST /worlds/{id}/noise/paths/{path_id}/test.

Complementa tests/test_ep_n14_test_path_api.py (14 tests de contrato de desarrollador-apis)
con los casos del spec §16.12 IT-PT01..IT-PT08 que prueban la integración entre
el handler HTTP, el WorldAgent y la BD.

Spec: noise-path-wizard.md §16.12
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from adapters.api.main import app
from core.exceptions import BrowserBusyError


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch, tmp_path):
    """TestClient con BD en archivo temporal y lifespan real."""
    db_file = tmp_path / "test_noise_path_test.db"
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
# Helpers
# ---------------------------------------------------------------------------

def _setup_world(c: TestClient) -> tuple[int, int]:
    r = c.post(
        "/accounts",
        json={"email": "itpt@example.com", "username": "itptbot", "password": "pass"},
    )
    assert r.status_code == 201, r.text
    account_id = r.json()["id"]
    r = c.post(
        f"/accounts/{account_id}/worlds",
        json={"server": "https://ts1.travian.es/", "tribe": "romans"},
    )
    assert r.status_code == 201, r.text
    return account_id, r.json()["id"]


def _create_path(c: TestClient, world_id: int, origin: str = "MAP") -> tuple[int, int]:
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
            "label": "Ruta IT",
            "steps": [{"step_order": 0, "action": "CLICK", "selector": "a.nav"}],
        },
    )
    assert r.status_code == 201, r.text
    return dest_id, r.json()["id"]


def _make_report(overall="ok", steps=None, aborted_at_step=None, anchor=None):
    return SimpleNamespace(
        overall=overall,
        steps=steps or [],
        aborted_at_step=aborted_at_step,
        anchor_navigated_to=anchor,
    )


def _running_agent(report):
    from core.scheduling.world_agent import AgentState
    agent = MagicMock()
    agent.state = AgentState.RUNNING
    agent.execute_path_test = AsyncMock(return_value=report)
    return agent


# ---------------------------------------------------------------------------
# IT-PT01 — 404 mundo inexistente
# ---------------------------------------------------------------------------

def test_IT_PT01_mundo_inexistente_404(client):
    """IT-PT01: mundo 99 no en BD → 404."""
    r = client.post("/worlds/99/noise/paths/1/test")
    assert r.status_code == 404
    assert "mundo" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# IT-PT02 — 404 path inexistente
# ---------------------------------------------------------------------------

def test_IT_PT02_path_inexistente_404(client):
    """IT-PT02: path 99 no existe en BD → 404."""
    _, world_id = _setup_world(client)
    r = client.post(f"/worlds/{world_id}/noise/paths/99/test")
    assert r.status_code == 404
    assert "ruta" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# IT-PT03 — 409 agente no existe en world_agents
# ---------------------------------------------------------------------------

def test_IT_PT03_agente_no_existe_409(client):
    """IT-PT03: world_agents no contiene el world_id → 409."""
    _, world_id = _setup_world(client)
    _, path_id = _create_path(client, world_id)

    # Asegurar que no hay agente registrado
    app.state.world_agents.pop(world_id, None)

    r = client.post(f"/worlds/{world_id}/noise/paths/{path_id}/test")
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# IT-PT04 — 409 agente en estado STOPPED
# ---------------------------------------------------------------------------

def test_IT_PT04_agente_stopped_409(client):
    """IT-PT04: agent.state = AgentState.STOPPED → 409."""
    _, world_id = _setup_world(client)
    _, path_id = _create_path(client, world_id)

    from core.scheduling.world_agent import AgentState
    agent = MagicMock()
    agent.state = AgentState.STOPPED
    app.state.world_agents[world_id] = agent

    r = client.post(f"/worlds/{world_id}/noise/paths/{path_id}/test")
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# IT-PT05 — 200 con overall "ok" (happy path)
# ---------------------------------------------------------------------------

def test_IT_PT05_agente_running_ruta_ok_200(client):
    """IT-PT05: agente RUNNING + execute_path_test retorna PathTestReport OK → 200 overall ok."""
    _, world_id = _setup_world(client)
    _, path_id = _create_path(client, world_id)

    step = SimpleNamespace(
        step_order=0, action="CLICK", selector="a.nav",
        status="ok", reason=None, current_url="https://ts1.travian.es/karte.php",
    )
    report = _make_report(overall="ok", steps=[step], anchor="https://ts1.travian.es/karte.php")
    agent = _running_agent(report)
    app.state.world_agents[world_id] = agent

    r = client.post(f"/worlds/{world_id}/noise/paths/{path_id}/test")
    assert r.status_code == 200
    data = r.json()
    assert data["overall"] == "ok"
    assert len(data["steps"]) == 1
    assert data["steps"][0]["status"] == "ok"


# ---------------------------------------------------------------------------
# IT-PT06 — 200 con overall "error" (ruta falla, HTTP sigue siendo 200)
# ---------------------------------------------------------------------------

def test_IT_PT06_ruta_falla_devuelve_200_con_overall_error(client):
    """IT-PT06: execute_path_test retorna PathTestReport con overall "error" → HTTP 200."""
    _, world_id = _setup_world(client)
    _, path_id = _create_path(client, world_id)

    step = SimpleNamespace(
        step_order=0, action="CLICK", selector="a.roto",
        status="error", reason="elemento no encontrado en el DOM",
        current_url="https://ts1.travian.es/karte.php",
    )
    report = _make_report(overall="error", steps=[step], aborted_at_step=0, anchor=None)
    agent = _running_agent(report)
    app.state.world_agents[world_id] = agent

    r = client.post(f"/worlds/{world_id}/noise/paths/{path_id}/test")
    assert r.status_code == 200
    data = r.json()
    assert data["overall"] == "error"
    assert data["aborted_at_step"] == 0
    assert data["steps"][0]["status"] == "error"
    assert "no encontrado" in data["steps"][0]["reason"]


# ---------------------------------------------------------------------------
# IT-PT07 — 409 BrowserBusyError
# ---------------------------------------------------------------------------

def test_IT_PT07_browser_busy_409(client):
    """IT-PT07: execute_path_test lanza BrowserBusyError → 409."""
    _, world_id = _setup_world(client)
    _, path_id = _create_path(client, world_id)

    from core.scheduling.world_agent import AgentState
    agent = MagicMock()
    agent.state = AgentState.RUNNING
    agent.execute_path_test = AsyncMock(
        side_effect=BrowserBusyError(world_id=world_id, timeout_s=60)
    )
    app.state.world_agents[world_id] = agent

    r = client.post(f"/worlds/{world_id}/noise/paths/{path_id}/test")
    assert r.status_code == 409
    # El 409 de browser ocupado tiene un detail distinto al de agente desconectado
    detail = r.json()["detail"].lower()
    assert "browser" in detail


# ---------------------------------------------------------------------------
# IT-PT08 — 500 RuntimeError en execute_path_test
# ---------------------------------------------------------------------------

def test_IT_PT08_runtime_error_500(client):
    """IT-PT08: execute_path_test lanza RuntimeError → 500."""
    _, world_id = _setup_world(client)
    _, path_id = _create_path(client, world_id)

    from core.scheduling.world_agent import AgentState
    agent = MagicMock()
    agent.state = AgentState.RUNNING
    agent.execute_path_test = AsyncMock(
        side_effect=RuntimeError("no hay browser activo")
    )
    app.state.world_agents[world_id] = agent

    r = client.post(f"/worlds/{world_id}/noise/paths/{path_id}/test")
    assert r.status_code == 500
    assert "error interno" in r.json()["detail"].lower()
