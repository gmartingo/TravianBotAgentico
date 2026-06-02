"""
Tests de contrato para EP-N11, EP-N12 y EP-N13 — Noise Path Wizard.

Estrategia:
  - TestClient con BD temporal (monkeypatch de DB_PATH).
  - Lifespan real (con TestClient en modo context manager).
  - Las dependencias de dominio aún no implementadas (get_villages_for_world,
    agent.refresh_villages) se mockean/stubbean para que los tests de contrato
    sean independientes de la lógica de negocio.

Spec noise-path-wizard.md §8.1 (EP-N11), §8.2 (EP-N12), §8.3 (EP-N13).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from adapters.api.main import app


# ---------------------------------------------------------------------------
# Helper: assert cabeceras mínimas del proyecto
# ---------------------------------------------------------------------------

def assert_cabeceras_basicas(response) -> None:
    """Verifica que content-type sea JSON en respuestas con cuerpo."""
    assert "application/json" in response.headers.get("content-type", ""), (
        f"Content-Type debe ser application/json, got: {response.headers.get('content-type')}"
    )


# ---------------------------------------------------------------------------
# Fixture de cliente HTTP con BD temporal
# ---------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch, tmp_path):
    """TestClient con BD en archivo temporal y lifespan real."""
    db_file = tmp_path / "test_noise_wizard_api.db"
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


def _setup_world(c: TestClient, server: str = "https://ts1.travian.es/") -> tuple[int, int]:
    """Crea account + world vía HTTP. Devuelve (account_id, world_id)."""
    r = c.post(
        "/accounts",
        json={
            "email": "wizard_test@example.com",
            "username": "wizardbot",
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


# ---------------------------------------------------------------------------
# EP-N11 — POST /worlds/{id}/noise/derive-selector
# ---------------------------------------------------------------------------

def test_EP_N11_derive_selector_id_valido_devuelve_200(client):
    """Happy path: outerHTML con id no auto-generado → selector=#id, method=id, is_unique=True."""
    _, world_id = _setup_world(client)

    r = client.post(
        f"/worlds/{world_id}/noise/derive-selector",
        json={"outer_html": '<a id="statistics" href="/statistics">Estadísticas</a>'},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["selector"] == "#statistics"
    assert data["method"] == "id"
    assert data["is_unique"] is True
    assert data["priority_level"] == 1
    assert data["warning"] is None


def test_EP_N11_derive_selector_href_exacto_devuelve_200(client):
    """outerHTML con href exacto → selector=a[href='...'], method=href_exact."""
    _, world_id = _setup_world(client)

    r = client.post(
        f"/worlds/{world_id}/noise/derive-selector",
        json={"outer_html": '<a href="/statistics" class="nav-link">Estadísticas</a>'},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["selector"] == "a[href='/statistics']"
    assert data["method"] == "href_exact"
    assert data["is_unique"] is True
    assert data["priority_level"] == 4


def test_EP_N11_derive_selector_gid_devuelve_200(client):
    """outerHTML con href que contiene gid=N → selector=a[href*='gid=2'], method=gid."""
    _, world_id = _setup_world(client)

    r = client.post(
        f"/worlds/{world_id}/noise/derive-selector",
        json={"outer_html": '<a href="/build.php?gid=2&id=0">Edificio</a>'},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["selector"] == "a[href*='gid=2']"
    assert data["method"] == "gid"
    assert data["is_unique"] is True
    assert data["priority_level"] == 3


def test_EP_N11_derive_selector_name_attribute_devuelve_200(client):
    """outerHTML con atributo name → selector=input[name='...'], method=name."""
    _, world_id = _setup_world(client)

    r = client.post(
        f"/worlds/{world_id}/noise/derive-selector",
        json={"outer_html": '<input name="username" type="text">'},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["selector"] == "input[name='username']"
    assert data["method"] == "name"
    assert data["is_unique"] is True
    assert data["priority_level"] == 2


def test_EP_N11_derive_selector_data_attr_devuelve_200(client):
    """outerHTML con data-* estable → selector=li[data-gid='2'], method=data_attr."""
    _, world_id = _setup_world(client)

    r = client.post(
        f"/worlds/{world_id}/noise/derive-selector",
        json={"outer_html": '<li data-gid="2" class="building">Carpintería</li>'},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["selector"] == "li[data-gid='2']"
    assert data["method"] == "data_attr"
    assert data["is_unique"] is True
    assert data["priority_level"] == 6


def test_EP_N11_derive_selector_clases_semanticas_is_unique_false(client):
    """outerHTML con solo clases CSS → is_unique=False y warning presente."""
    _, world_id = _setup_world(client)

    r = client.post(
        f"/worlds/{world_id}/noise/derive-selector",
        json={"outer_html": '<a class="nav-link statistics">Estadísticas</a>'},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["is_unique"] is False
    assert data["method"] == "class_combo"
    assert data["warning"] is not None
    assert data["priority_level"] == 7


def test_EP_N11_derive_selector_fallback_is_unique_false(client):
    """outerHTML con solo clases Tailwind utilitarias → fallback, priority_level=9."""
    _, world_id = _setup_world(client)

    r = client.post(
        f"/worlds/{world_id}/noise/derive-selector",
        json={"outer_html": '<a class="flex items-center text-sm">Link</a>'},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["is_unique"] is False
    assert data["priority_level"] == 9
    assert data["warning"] is not None


def test_EP_N11_derive_selector_outer_html_vacio_devuelve_422(client):
    """outer_html vacío → 422."""
    _, world_id = _setup_world(client)

    # Pydantic valida min_length=1 antes de llegar al handler
    r = client.post(
        f"/worlds/{world_id}/noise/derive-selector",
        json={"outer_html": ""},
    )
    assert r.status_code == 422, r.text


def test_EP_N11_derive_selector_html_malformado_devuelve_422(client):
    """HTML que no parsea → 422 con detail descriptivo."""
    _, world_id = _setup_world(client)

    r = client.post(
        f"/worlds/{world_id}/noise/derive-selector",
        json={"outer_html": "texto plano sin etiquetas HTML"},
    )
    assert r.status_code == 422, r.text
    assert "parsear" in r.json()["detail"].lower() or "html" in r.json()["detail"].lower()


def test_EP_N11_derive_selector_mundo_inexistente_devuelve_404(client):
    """Mundo que no existe → 404."""
    r = client.post(
        "/worlds/99999/noise/derive-selector",
        json={"outer_html": '<a href="/stats">Stats</a>'},
    )
    assert r.status_code == 404, r.text
    assert "mundo" in r.json()["detail"].lower()


def test_EP_N11_derive_selector_id_autogenerado_avanza_siguiente_nivel(client):
    """id auto-generado (ember123) → se descarta, avanza al siguiente nivel."""
    _, world_id = _setup_world(client)

    r = client.post(
        f"/worlds/{world_id}/noise/derive-selector",
        json={"outer_html": '<div id="ember123" class="menu-item">Item</div>'},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # El id se descarta — no debe devolver #ember123
    assert data["selector"] != "#ember123"
    assert data["priority_level"] > 1


def test_EP_N11_derive_selector_response_tiene_todos_los_campos(client):
    """La response incluye todos los campos del contrato."""
    _, world_id = _setup_world(client)

    r = client.post(
        f"/worlds/{world_id}/noise/derive-selector",
        json={"outer_html": '<a href="/statistics">Stats</a>'},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    for campo in ("selector", "is_unique", "priority_level", "method", "warning", "alternatives"):
        assert campo in data, f"Campo '{campo}' ausente en la response"
    assert_cabeceras_basicas(r)


def test_EP_N11_derive_selector_campo_requerido_ausente_devuelve_422(client):
    """body sin outer_html → 422 por validación Pydantic."""
    _, world_id = _setup_world(client)

    r = client.post(
        f"/worlds/{world_id}/noise/derive-selector",
        json={},
    )
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# EP-N12 — GET /worlds/{id}/noise/origins
# ---------------------------------------------------------------------------

def test_EP_N12_origins_sin_aldeas_devuelve_9_genericos(client):
    """
    Sin aldeas en BD → generic_origins tiene exactamente 9 elementos,
    village_origins vacío, villages_loaded=False.
    """
    _, world_id = _setup_world(client)

    # Mockear get_villages_for_world para devolver lista vacía
    # (el método aún no está implementado en el adaptador real)
    with patch.object(
        app.state.__class__,
        "__getattr__",
        side_effect=lambda self, name: None,
    ):
        pass  # no necesario si el método ya existe o se mockea más abajo

    # get_villages_for_world es un método del noise_db_port
    # En tests usamos el adaptador real con BD vacía (villages no existe aún)
    # Dado que get_villages_for_world no está implementado aún en el adaptador,
    # necesitamos mockearlo en la instancia del adaptador
    noise_db = app.state.noise_db_port
    noise_db.get_villages_for_world = AsyncMock(return_value=[])

    r = client.get(f"/worlds/{world_id}/noise/origins")
    assert r.status_code == 200, r.text
    data = r.json()

    assert len(data["generic_origins"]) == 9
    assert data["village_origins"] == []
    assert data["villages_loaded"] is False


def test_EP_N12_origins_con_aldeas_devuelve_village_origins(client):
    """Con aldeas en BD → village_origins populados y villages_loaded=True."""
    _, world_id = _setup_world(client)

    # Simular aldeas retornadas por el adaptador
    from unittest.mock import MagicMock
    village1 = MagicMock()
    village1.data_id = 12345
    village1.name = "Merlinia"
    village1.x = 42
    village1.y = -17

    village2 = MagicMock()
    village2.data_id = 12346
    village2.name = "Forticia"
    village2.x = 43
    village2.y = -17

    noise_db = app.state.noise_db_port
    noise_db.get_villages_for_world = AsyncMock(return_value=[village1, village2])

    r = client.get(f"/worlds/{world_id}/noise/origins")
    assert r.status_code == 200, r.text
    data = r.json()

    assert len(data["generic_origins"]) == 9
    assert len(data["village_origins"]) == 2
    assert data["villages_loaded"] is True

    # Verificar estructura de una entrada de aldea
    v = data["village_origins"][0]
    assert v["value"] == "VILLAGE_12345"
    assert v["label"] == "Merlinia"
    assert v["data_id"] == 12345
    assert v["x"] == 42
    assert v["y"] == -17
    assert v["path"] == "/dorf1.php?newdid=12345"


def test_EP_N12_origins_generic_origins_tiene_valores_correctos(client):
    """Los 9 genéricos tienen los valores del enum y etiquetas correctas."""
    _, world_id = _setup_world(client)

    noise_db = app.state.noise_db_port
    noise_db.get_villages_for_world = AsyncMock(return_value=[])

    r = client.get(f"/worlds/{world_id}/noise/origins")
    assert r.status_code == 200, r.text
    data = r.json()

    generic_values = {o["value"] for o in data["generic_origins"]}
    expected_values = {
        "DORF1", "DORF2", "MAP", "STATISTICS", "REPORTS",
        "MESSAGES", "VILLAGE_STATISTICS", "OASIS_VIEW", "ANY",
    }
    assert generic_values == expected_values


def test_EP_N12_origins_any_tiene_path_null(client):
    """El origen ANY debe tener path=null."""
    _, world_id = _setup_world(client)

    noise_db = app.state.noise_db_port
    noise_db.get_villages_for_world = AsyncMock(return_value=[])

    r = client.get(f"/worlds/{world_id}/noise/origins")
    assert r.status_code == 200, r.text
    data = r.json()

    any_origin = next(o for o in data["generic_origins"] if o["value"] == "ANY")
    assert any_origin["path"] is None


def test_EP_N12_origins_mundo_inexistente_devuelve_404(client):
    """Mundo que no existe → 404."""
    r = client.get("/worlds/99999/noise/origins")
    assert r.status_code == 404, r.text
    assert "mundo" in r.json()["detail"].lower()


def test_EP_N12_origins_cache_control_no_store(client):
    """Response incluye Cache-Control: no-store."""
    _, world_id = _setup_world(client)

    noise_db = app.state.noise_db_port
    noise_db.get_villages_for_world = AsyncMock(return_value=[])

    r = client.get(f"/worlds/{world_id}/noise/origins")
    assert r.status_code == 200, r.text
    assert "no-store" in r.headers.get("cache-control", "").lower()


def test_EP_N12_origins_response_tiene_todos_los_campos(client):
    """La response incluye todos los campos del contrato."""
    _, world_id = _setup_world(client)

    noise_db = app.state.noise_db_port
    noise_db.get_villages_for_world = AsyncMock(return_value=[])

    r = client.get(f"/worlds/{world_id}/noise/origins")
    assert r.status_code == 200, r.text
    data = r.json()

    assert "generic_origins" in data
    assert "village_origins" in data
    assert "villages_loaded" in data
    assert_cabeceras_basicas(r)


# ---------------------------------------------------------------------------
# EP-N13 — POST /worlds/{id}/noise/refresh-villages
# ---------------------------------------------------------------------------

def test_EP_N13_refresh_villages_sin_agente_devuelve_409(client):
    """Sin WorldAgent iniciado para el mundo → 409."""
    _, world_id = _setup_world(client)

    # world_agents existe pero no tiene el world_id (o el agente no está RUNNING)
    # Por defecto world_agents = {} en el lifespan, así que el agente no existe → 409
    r = client.post(f"/worlds/{world_id}/noise/refresh-villages")
    assert r.status_code == 409, r.text
    assert "desconectado" in r.json()["detail"].lower() or "sesión" in r.json()["detail"].lower()


def test_EP_N13_refresh_villages_agente_stopped_devuelve_409(client):
    """WorldAgent en estado STOPPED → 409."""
    _, world_id = _setup_world(client)

    from core.scheduling.world_agent import AgentState

    agent_mock = MagicMock()
    agent_mock.state = AgentState.STOPPED

    app.state.world_agents[world_id] = agent_mock

    r = client.post(f"/worlds/{world_id}/noise/refresh-villages")
    assert r.status_code == 409, r.text


def test_EP_N13_refresh_villages_agente_activo_devuelve_200(client):
    """WorldAgent RUNNING → delega al agente y devuelve villages_found y villages_data."""
    _, world_id = _setup_world(client)

    from core.scheduling.world_agent import AgentState

    village1 = MagicMock()
    village1.data_id = 12345
    village1.name = "Merlinia"
    village1.x = 42
    village1.y = -17

    village2 = MagicMock()
    village2.data_id = 12346
    village2.name = "Forticia"
    village2.x = 43
    village2.y = -17

    agent_mock = MagicMock()
    agent_mock.state = AgentState.RUNNING
    agent_mock.refresh_villages = AsyncMock(return_value=[village1, village2])

    app.state.world_agents[world_id] = agent_mock

    r = client.post(f"/worlds/{world_id}/noise/refresh-villages")
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["villages_found"] == 2
    assert len(data["villages_data"]) == 2
    assert data["villages_data"][0]["data_id"] == 12345
    assert data["villages_data"][0]["name"] == "Merlinia"
    assert data["villages_data"][0]["x"] == 42
    assert data["villages_data"][0]["y"] == -17


def test_EP_N13_refresh_villages_agente_activo_sin_aldeas_devuelve_0(client):
    """WorldAgent RUNNING pero sin aldeas → villages_found=0, villages_data=[]."""
    _, world_id = _setup_world(client)

    from core.scheduling.world_agent import AgentState

    agent_mock = MagicMock()
    agent_mock.state = AgentState.RUNNING
    agent_mock.refresh_villages = AsyncMock(return_value=[])

    app.state.world_agents[world_id] = agent_mock

    r = client.post(f"/worlds/{world_id}/noise/refresh-villages")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["villages_found"] == 0
    assert data["villages_data"] == []


def test_EP_N13_refresh_villages_mundo_inexistente_devuelve_404(client):
    """Mundo que no existe → 404 antes de verificar el agente."""
    r = client.post("/worlds/99999/noise/refresh-villages")
    assert r.status_code == 404, r.text
    assert "mundo" in r.json()["detail"].lower()


def test_EP_N13_refresh_villages_response_tiene_todos_los_campos(client):
    """La response incluye todos los campos del contrato."""
    _, world_id = _setup_world(client)

    from core.scheduling.world_agent import AgentState

    agent_mock = MagicMock()
    agent_mock.state = AgentState.RUNNING
    agent_mock.refresh_villages = AsyncMock(return_value=[])

    app.state.world_agents[world_id] = agent_mock

    r = client.post(f"/worlds/{world_id}/noise/refresh-villages")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "villages_found" in data
    assert "villages_data" in data
    assert_cabeceras_basicas(r)


# ---------------------------------------------------------------------------
# Tests de impacto en EP-N07/N08/N09 — campos nuevos en responses existentes
# ---------------------------------------------------------------------------

def _create_dest_and_path(c: TestClient, world_id: int, origin: str = "ANY") -> tuple[int, int]:
    """Crea un destino y una ruta básica. Devuelve (dest_id, path_id)."""
    r = c.post(
        f"/worlds/{world_id}/noise/destinations",
        json={"url_pattern": "/karte.php", "label": "Mapa", "category": "MAP"},
    )
    assert r.status_code == 201, r.text
    dest_id = r.json()["id"]

    r = c.post(
        f"/worlds/{world_id}/noise/destinations/{dest_id}/paths",
        json={
            "origin": origin,
            "label": "Ruta de prueba",
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


def test_EP_N07_list_paths_incluye_consecutive_failures_count(client):
    """EP-N07: la response de cada ruta incluye consecutive_failures_count."""
    _, world_id = _setup_world(client)
    dest_id, _ = _create_dest_and_path(client, world_id)

    r = client.get(f"/worlds/{world_id}/noise/destinations/{dest_id}/paths")
    assert r.status_code == 200, r.text
    paths = r.json()
    assert len(paths) == 1
    assert "consecutive_failures_count" in paths[0]
    assert paths[0]["consecutive_failures_count"] == 0


def test_EP_N07_list_paths_incluye_expected_url_after_click_en_steps(client):
    """EP-N07: cada paso en la response incluye expected_url_after_click."""
    _, world_id = _setup_world(client)
    dest_id, _ = _create_dest_and_path(client, world_id)

    r = client.get(f"/worlds/{world_id}/noise/destinations/{dest_id}/paths")
    assert r.status_code == 200, r.text
    paths = r.json()
    step = paths[0]["steps"][0]
    assert "expected_url_after_click" in step
    assert step["expected_url_after_click"] is None  # no se pasó, default None


def test_EP_N08_create_path_acepta_expected_url_after_click_en_steps(client):
    """EP-N08: crear ruta con expected_url_after_click en un paso → 201 y round-trip."""
    _, world_id = _setup_world(client)

    r = client.post(
        f"/worlds/{world_id}/noise/destinations",
        json={"url_pattern": "/statistics", "label": "Stats", "category": "OTHER"},
    )
    dest_id = r.json()["id"]

    r = client.post(
        f"/worlds/{world_id}/noise/destinations/{dest_id}/paths",
        json={
            "origin": "STATISTICS",
            "label": "Ir a stats",
            "steps": [
                {
                    "step_order": 0,
                    "action": "CLICK",
                    "selector": "a[href='/statistics']",
                    "expected_url_after_click": "/statistics",
                },
            ],
        },
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["consecutive_failures_count"] == 0
    assert data["steps"][0]["expected_url_after_click"] == "/statistics"


def test_EP_N08_create_path_acepta_nuevos_origins_del_enum(client):
    """EP-N08: origin 'STATISTICS' (nuevo valor del enum) se acepta correctamente."""
    _, world_id = _setup_world(client)

    r = client.post(
        f"/worlds/{world_id}/noise/destinations",
        json={"url_pattern": "/statistics", "label": "Stats", "category": "OTHER"},
    )
    dest_id = r.json()["id"]

    for origin in ("STATISTICS", "REPORTS", "MESSAGES", "VILLAGE_STATISTICS", "OASIS_VIEW"):
        r = client.post(
            f"/worlds/{world_id}/noise/destinations/{dest_id}/paths",
            json={
                "origin": origin,
                "label": f"Ruta desde {origin}",
                "steps": [{"step_order": 0, "action": "CLICK", "selector": "a.nav"}],
            },
        )
        assert r.status_code == 201, f"Falló para origin={origin}: {r.text}"
        assert r.json()["origin"] == origin


def test_EP_N08_create_path_selector_texto_visible_devuelve_422(client):
    """EC-NP14: selector con :contains() → 422."""
    _, world_id = _setup_world(client)

    r = client.post(
        f"/worlds/{world_id}/noise/destinations",
        json={"url_pattern": "/karte.php", "label": "Mapa", "category": "MAP"},
    )
    dest_id = r.json()["id"]

    r = client.post(
        f"/worlds/{world_id}/noise/destinations/{dest_id}/paths",
        json={
            "origin": "ANY",
            "label": "Test texto",
            "steps": [
                {
                    "step_order": 0,
                    "action": "CLICK",
                    "selector": 'a:contains("Estadísticas")',
                },
            ],
        },
    )
    assert r.status_code == 422, r.text


def test_EP_N09_update_path_acepta_expected_url_after_click_en_steps(client):
    """EP-N09: actualizar ruta con expected_url_after_click en steps → round-trip."""
    _, world_id = _setup_world(client)
    dest_id, path_id = _create_dest_and_path(client, world_id)

    r = client.put(
        f"/worlds/{world_id}/noise/paths/{path_id}",
        json={
            "steps": [
                {
                    "step_order": 0,
                    "action": "CLICK",
                    "selector": "a[href*='karte']",
                    "expected_url_after_click": "/karte.php",
                },
            ],
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["steps"][0]["expected_url_after_click"] == "/karte.php"
