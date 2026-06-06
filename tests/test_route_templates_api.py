"""
Tests de integración HTTP para el Portal de Desarrollador de Rutas (EP-RT01..RT10).

Cubre:
  - CRUD de plantillas (EP-RT01..EP-RT06): status codes, Location, shapes de response.
  - Clonado (EP-RT07): 201 nuevo, 200 idempotente, 409 colisión con conflicting_destination_id,
    force=true sobreescribe.
  - Bulk clone (EP-RT08): resultado por ítem, 422 template_ids vacío.
  - Re-sync (EP-RT09): 200 synced, 201 created (sin instancia previa), preserva nav_weight.
  - Test en vivo (EP-RT10): mock de WorldAgent.execute_path_test, 409 browser busy,
    422 path_index fuera de rango.
  - Retrocompatibilidad EP-N03/EP-N04: template_id presente en response y en request.
  - Cabeceras mínimas: X-Request-ID, X-API-Version, Content-Type en todas las respuestas.

Spec route-templates-developer-portal.md §8, §12.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from adapters.api.main import app
from core.exceptions import BrowserBusyError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_APP_STATE_ATTRS = (
    "world_runtime_port", "farm_db_port", "world_agents",
    "session_db_port", "db_port", "noise_db_port", "route_template_port",
)


@pytest.fixture
def client(monkeypatch, tmp_path):
    """TestClient con BD en archivo temporal y lifespan real."""
    db_file = tmp_path / "test_rt_api.db"
    monkeypatch.setattr("adapters.db.database.DB_PATH", str(db_file))
    for attr in _APP_STATE_ATTRS:
        if hasattr(app.state, attr):
            delattr(app.state, attr)
    with TestClient(app) as c:
        yield c
    for attr in _APP_STATE_ATTRS:
        if hasattr(app.state, attr):
            delattr(app.state, attr)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_world(c: TestClient, server: str = "https://ts1.travian.es/") -> tuple[int, int]:
    """Crea account + world vía HTTP. Devuelve (account_id, world_id)."""
    r = c.post(
        "/accounts",
        json={"email": "rt_test@example.com", "username": "rtbot", "password": "pass123"},
    )
    assert r.status_code == 201, r.text
    account_id = r.json()["id"]
    r = c.post(
        f"/accounts/{account_id}/worlds",
        json={"server": server, "tribe": "romans"},
    )
    assert r.status_code == 201, r.text
    return account_id, r.json()["id"]


def _make_template_body(**overrides) -> dict:
    """Cuerpo mínimo válido para crear una plantilla."""
    base = {
        "slug": "test-template",
        "label": "Plantilla de test",
        "category_slug": "uncategorized",
        "url_pattern": "/karte.php",
        "navigation_weight": 1.0,
        "is_safe": True,
        "paths": [],
    }
    # Compatibilidad: si se pasa 'category' (viejo), mapearlo a 'category_slug'
    if "category" in overrides:
        overrides.setdefault("category_slug", "uncategorized")
        del overrides["category"]
    base.update(overrides)
    return base


def _make_template_with_path(**overrides) -> dict:
    """Plantilla con un path y un step válido."""
    body = _make_template_body(**overrides)
    body["paths"] = [
        {
            "origin": "ANY",
            "label": "Desde cualquier página",
            "is_active": True,
            "steps": [
                {
                    "step_order": 0,
                    "action": "WAIT_FOR_SELECTOR",
                    "selector": "#map",
                    "value": "",
                    "delay_min_ms": 500,
                    "delay_max_ms": 900,
                }
            ],
        }
    ]
    return body


def assert_cabeceras_minimas(response) -> None:
    """Verifica las cabeceras mínimas en cualquier respuesta."""
    assert "x-request-id" in response.headers, "Falta X-Request-ID"
    assert "x-api-version" in response.headers, "Falta X-API-Version"
    ct = response.headers.get("content-type", "")
    assert "application/json" in ct, f"Content-Type no es JSON: {ct}"


def _make_report(overall="ok", steps=None, aborted_at_step=None, anchor=None):
    return SimpleNamespace(
        overall=overall,
        steps=steps or [],
        aborted_at_step=aborted_at_step,
        anchor_navigated_to=anchor,
    )


def _running_agent(report=None):
    from core.scheduling.world_agent import AgentState
    agent = MagicMock()
    agent.state = AgentState.RUNNING
    agent._session_active = MagicMock(return_value=True)
    if report is not None:
        agent.execute_path_test = AsyncMock(return_value=report)
    return agent


# ---------------------------------------------------------------------------
# TI-RT01 — POST /route-templates: camino feliz
# ---------------------------------------------------------------------------

def test_TI_RT01_crear_plantilla_devuelve_201_y_cabeceras_minimas(client):
    """POST /route-templates con datos válidos → 201, objeto completo, Location."""
    r = client.post("/route-templates", json=_make_template_body())
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["slug"] == "test-template"
    assert data["label"] == "Plantilla de test"
    assert data["category_slug"] == "uncategorized"
    assert data["url_pattern"] == "/karte.php"
    assert data["navigation_weight"] == 1.0
    assert data["is_safe"] is True
    assert "id" in data
    assert "paths" in data
    assert "Location" in r.headers
    assert r.headers["Location"] == f"/route-templates/{data['id']}"
    assert_cabeceras_minimas(r)


def test_TI_RT01_crear_plantilla_con_paths_y_steps(client):
    """POST /route-templates con paths+steps → 201, paths incluidos en response."""
    r = client.post("/route-templates", json=_make_template_with_path())
    assert r.status_code == 201, r.text
    data = r.json()
    assert len(data["paths"]) == 1
    assert len(data["paths"][0]["steps"]) == 1
    assert data["paths"][0]["steps"][0]["selector"] == "#map"


# ---------------------------------------------------------------------------
# TI-RT02 — POST /route-templates: slug duplicado → 409
# ---------------------------------------------------------------------------

def test_TI_RT02_crear_plantilla_slug_duplicado_devuelve_409(client):
    """POST /route-templates con slug ya existente → 409 Conflict."""
    client.post("/route-templates", json=_make_template_body())
    r = client.post("/route-templates", json=_make_template_body())
    assert r.status_code == 409, r.text
    assert "slug" in r.json()["detail"].lower() or "plantilla" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# TI-RT02b — POST /route-templates: slug inválido → 422
# ---------------------------------------------------------------------------

def test_TI_RT02b_crear_plantilla_slug_invalido_devuelve_422(client):
    """POST /route-templates con slug no kebab-case → 422."""
    r = client.post("/route-templates", json=_make_template_body(slug="Invalid Slug!"))
    assert r.status_code == 422, r.text


def test_TI_RT02c_crear_plantilla_navigation_weight_invalido_devuelve_422(client):
    """POST /route-templates con navigation_weight fuera de rango → 422."""
    r = client.post("/route-templates", json=_make_template_body(navigation_weight=0.05))
    assert r.status_code == 422, r.text


def test_TI_RT02d_crear_plantilla_step_delay_bajo_devuelve_422(client):
    """POST /route-templates con step delay_min_ms < 200 → 422 (anti-detección)."""
    body = _make_template_with_path()
    body["paths"][0]["steps"][0]["delay_min_ms"] = 50
    r = client.post("/route-templates", json=body)
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# TI-RT03 — GET /route-templates: listar plantillas
# ---------------------------------------------------------------------------

def test_TI_RT03_listar_plantillas_devuelve_200(client):
    """GET /route-templates → 200, lista (puede incluir las del seed)."""
    r = client.get("/route-templates")
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)
    assert_cabeceras_minimas(r)


def test_TI_RT03_listar_plantillas_con_include_paths(client):
    """GET /route-templates?include_paths=true → paths incluidos en cada item."""
    client.post("/route-templates", json=_make_template_with_path())
    r = client.get("/route-templates?include_paths=true")
    assert r.status_code == 200, r.text
    items = r.json()
    # Buscar la plantilla recién creada
    created = next((t for t in items if t["slug"] == "test-template"), None)
    assert created is not None
    assert created["paths"] is not None
    assert len(created["paths"]) == 1


# ---------------------------------------------------------------------------
# TI-RT04 — GET /route-templates?category=MAP
# ---------------------------------------------------------------------------

def test_TI_RT04_listar_por_categoria(client):
    """GET /route-templates?category_slug=<slug> → solo plantillas de esa categoría."""
    # Crear una categoría real
    r_cat = client.post("/route-categories", json={"label": "Mapas"})
    assert r_cat.status_code == 201
    cat_slug = r_cat.json()["slug"]

    client.post("/route-templates", json=_make_template_body(slug="map-1", category_slug=cat_slug))
    client.post(
        "/route-templates",
        json=_make_template_body(slug="reports-1", url_pattern="/report"),  # queda en uncategorized
    )
    r = client.get(f"/route-templates?category_slug={cat_slug}")
    assert r.status_code == 200, r.text
    items = r.json()
    assert all(t["category_slug"] == cat_slug for t in items)
    slugs = [t["slug"] for t in items]
    assert "map-1" in slugs
    assert "reports-1" not in slugs


def test_TI_RT04_categoria_invalida_devuelve_empty(client):
    """GET /route-templates?category_slug=<slug-inexistente> → 200 [] (filtro silencioso, C-01)."""
    r = client.get("/route-templates?category_slug=slug-inexistente")
    assert r.status_code == 200, r.text
    assert r.json() == []


# ---------------------------------------------------------------------------
# TI-RT05 — GET /route-templates/{id}: obtener plantilla existente
# ---------------------------------------------------------------------------

def test_TI_RT05_obtener_plantilla_existente_devuelve_200(client):
    """GET /route-templates/{id} existente → 200, con paths y steps."""
    r = client.post("/route-templates", json=_make_template_with_path())
    tpl_id = r.json()["id"]
    r = client.get(f"/route-templates/{tpl_id}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["id"] == tpl_id
    assert len(data["paths"]) == 1
    assert_cabeceras_minimas(r)


# ---------------------------------------------------------------------------
# TI-RT06 — GET /route-templates/9999: plantilla inexistente → 404
# ---------------------------------------------------------------------------

def test_TI_RT06_obtener_plantilla_inexistente_devuelve_404(client):
    """GET /route-templates/9999 → 404."""
    r = client.get("/route-templates/9999")
    assert r.status_code == 404, r.text
    assert r.json()["detail"] == "Plantilla no encontrada."


# ---------------------------------------------------------------------------
# TI-RT07 — PUT /route-templates/{id}: actualizar plantilla
# ---------------------------------------------------------------------------

def test_TI_RT07_actualizar_plantilla_label_devuelve_200(client):
    """PUT /route-templates/{id} con label nuevo → 200, campo actualizado."""
    r = client.post("/route-templates", json=_make_template_body())
    tpl_id = r.json()["id"]
    r = client.put(f"/route-templates/{tpl_id}", json={"label": "Nuevo label"})
    assert r.status_code == 200, r.text
    assert r.json()["label"] == "Nuevo label"
    assert_cabeceras_minimas(r)


def test_TI_RT07_actualizar_slug_devuelve_422(client):
    """PUT /route-templates/{id} con slug → 422 (inmutable)."""
    r = client.post("/route-templates", json=_make_template_body())
    tpl_id = r.json()["id"]
    r = client.put(f"/route-templates/{tpl_id}", json={"slug": "nuevo-slug"})
    assert r.status_code == 422, r.text


def test_TI_RT07_body_vacio_devuelve_422(client):
    """PUT /route-templates/{id} con body sin campos mutables → 422."""
    r = client.post("/route-templates", json=_make_template_body())
    tpl_id = r.json()["id"]
    # Body sin campos mutables conocidos (slug solo sería 422 por inmutable,
    # pero {} no tiene ningún campo → at_least_one_mutable_field)
    r = client.put(f"/route-templates/{tpl_id}", json={})
    assert r.status_code == 422, r.text


def test_TI_RT07_actualizar_plantilla_inexistente_devuelve_404(client):
    """PUT /route-templates/9999 → 404."""
    r = client.put("/route-templates/9999", json={"label": "X"})
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# TI-RT08 — PUT con paths: reemplazo atómico
# ---------------------------------------------------------------------------

def test_TI_RT08_actualizar_paths_reemplazo_atomico(client):
    """PUT /route-templates/{id} con paths → reemplazo atómico, paths actualizados."""
    r = client.post("/route-templates", json=_make_template_with_path())
    tpl_id = r.json()["id"]
    nuevos_paths = [
        {
            "origin": "DORF2",
            "label": "Desde dorf2",
            "is_active": True,
            "steps": [
                {"step_order": 0, "action": "CLICK", "selector": "a.nav-item", "delay_min_ms": 500, "delay_max_ms": 900}
            ],
        }
    ]
    r = client.put(f"/route-templates/{tpl_id}", json={"paths": nuevos_paths})
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["paths"]) == 1
    assert data["paths"][0]["origin"] == "DORF2"


# ---------------------------------------------------------------------------
# TI-RT09 — DELETE /route-templates/{id}
# ---------------------------------------------------------------------------

def test_TI_RT09_borrar_plantilla_sin_instancias_devuelve_204(client):
    """DELETE /route-templates/{id} sin instancias clonadas → 204."""
    r = client.post("/route-templates", json=_make_template_body())
    tpl_id = r.json()["id"]
    r = client.delete(f"/route-templates/{tpl_id}")
    assert r.status_code == 204, r.text


def test_TI_RT09_borrar_plantilla_inexistente_devuelve_404(client):
    """DELETE /route-templates/9999 → 404."""
    r = client.delete("/route-templates/9999")
    assert r.status_code == 404, r.text


def test_TI_RT10_borrar_plantilla_con_instancias_deja_template_id_null(client):
    """DELETE con instancias clonadas → 204, instancias quedan con template_id=null (CA-RT08)."""
    _, world_id = _setup_world(client)
    r = client.post("/route-templates", json=_make_template_body())
    tpl_id = r.json()["id"]
    # Clonar al mundo
    r = client.post(f"/route-templates/{tpl_id}/clone-to-world/{world_id}")
    assert r.status_code == 201, r.text
    dest_id = r.json()["destination_id"]
    # Borrar la plantilla
    r = client.delete(f"/route-templates/{tpl_id}")
    assert r.status_code == 204, r.text
    # La instancia debe seguir viva con template_id=null
    r = client.get(f"/worlds/{world_id}/noise/destinations")
    assert r.status_code == 200, r.text
    dests = r.json()
    matching = [d for d in dests if d["id"] == dest_id]
    assert len(matching) == 1
    assert matching[0]["template_id"] is None


# ---------------------------------------------------------------------------
# TI-RT06b — GET /route-templates/{id}/paths
# ---------------------------------------------------------------------------

def test_TI_RT06b_listar_paths_plantilla_existente(client):
    """GET /route-templates/{id}/paths → 200, lista de paths."""
    r = client.post("/route-templates", json=_make_template_with_path())
    tpl_id = r.json()["id"]
    r = client.get(f"/route-templates/{tpl_id}/paths")
    assert r.status_code == 200, r.text
    paths = r.json()
    assert len(paths) == 1
    assert paths[0]["origin"] == "ANY"
    assert_cabeceras_minimas(r)


def test_TI_RT06b_listar_paths_plantilla_inexistente_devuelve_404(client):
    """GET /route-templates/9999/paths → 404."""
    r = client.get("/route-templates/9999/paths")
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# TI-RT11 — Clone sin conflicto → 201
# ---------------------------------------------------------------------------

def test_TI_RT11_clonar_sin_conflicto_devuelve_201(client):
    """Clone plantilla a mundo sin conflicto → 201, result=cloned, Location, template_id."""
    _, world_id = _setup_world(client)
    r = client.post("/route-templates", json=_make_template_body())
    tpl_id = r.json()["id"]
    r = client.post(f"/route-templates/{tpl_id}/clone-to-world/{world_id}")
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["result"] == "cloned"
    assert data["world_id"] == world_id
    assert data["template_id"] == tpl_id
    assert "destination_id" in data
    assert "Location" in r.headers
    assert_cabeceras_minimas(r)


def test_TI_RT11_clonar_copia_paths_al_mundo(client):
    """Clone copia paths+steps de la plantilla al mundo (CA-RT13)."""
    _, world_id = _setup_world(client)
    r = client.post("/route-templates", json=_make_template_with_path())
    tpl_id = r.json()["id"]
    r = client.post(f"/route-templates/{tpl_id}/clone-to-world/{world_id}")
    dest_id = r.json()["destination_id"]
    # Verificar paths copiados
    r = client.get(f"/worlds/{world_id}/noise/destinations/{dest_id}/paths")
    assert r.status_code == 200, r.text
    paths = r.json()
    assert len(paths) == 1
    assert len(paths[0]["steps"]) == 1


# ---------------------------------------------------------------------------
# TI-RT12 — Clone idempotente → 200
# ---------------------------------------------------------------------------

def test_TI_RT12_clonar_idempotente_devuelve_200(client):
    """Clone misma plantilla al mismo mundo segunda vez → 200 result=already_exists (CA-RT10)."""
    _, world_id = _setup_world(client)
    r = client.post("/route-templates", json=_make_template_body())
    tpl_id = r.json()["id"]
    client.post(f"/route-templates/{tpl_id}/clone-to-world/{world_id}")
    r = client.post(f"/route-templates/{tpl_id}/clone-to-world/{world_id}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["result"] == "already_exists"
    assert_cabeceras_minimas(r)


# ---------------------------------------------------------------------------
# TI-RT13 — Clone con colisión → 409 con conflicting_destination_id en detail
# ---------------------------------------------------------------------------

def test_TI_RT13_clonar_con_colision_devuelve_409(client):
    """Clone con URL ocupada por otro destino → 409 con conflicting_destination_id (CA-RT11)."""
    _, world_id = _setup_world(client)
    # Crear destino con la misma URL
    r = client.post(
        f"/worlds/{world_id}/noise/destinations",
        json={"url_pattern": "/karte.php", "label": "Mapa manual", "category_slug": "uncategorized"},
    )
    assert r.status_code == 201, r.text
    conflicting_id = r.json()["id"]

    r = client.post("/route-templates", json=_make_template_body())
    tpl_id = r.json()["id"]
    r = client.post(f"/route-templates/{tpl_id}/clone-to-world/{world_id}")
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert isinstance(detail, dict), f"detail debe ser dict, got: {detail!r}"
    assert "conflicting_destination_id" in detail
    assert detail["conflicting_destination_id"] == conflicting_id


# ---------------------------------------------------------------------------
# TI-RT14 — Clone con force=true sobre conflicto → 201
# ---------------------------------------------------------------------------

def test_TI_RT14_clonar_con_force_sobre_conflicto_devuelve_201(client):
    """Clone con force=true sobre destino conflictivo → 201, destino antiguo borrado (CA-RT12)."""
    _, world_id = _setup_world(client)
    # Crear destino conflictivo
    r = client.post(
        f"/worlds/{world_id}/noise/destinations",
        json={"url_pattern": "/karte.php", "label": "Mapa manual", "category_slug": "uncategorized"},
    )
    conflicting_id = r.json()["id"]

    r = client.post("/route-templates", json=_make_template_body())
    tpl_id = r.json()["id"]
    r = client.post(f"/route-templates/{tpl_id}/clone-to-world/{world_id}?force=true")
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["result"] == "cloned"
    # El destino conflictivo ya no existe
    r2 = client.get(f"/worlds/{world_id}/noise/destinations")
    ids = [d["id"] for d in r2.json()]
    assert conflicting_id not in ids


# ---------------------------------------------------------------------------
# TI-RT11b — Clone: 404 plantilla inexistente / 404 mundo inexistente
# ---------------------------------------------------------------------------

def test_TI_RT11b_clonar_plantilla_inexistente_devuelve_404(client):
    _, world_id = _setup_world(client)
    r = client.post(f"/route-templates/9999/clone-to-world/{world_id}")
    assert r.status_code == 404, r.text


def test_TI_RT11c_clonar_mundo_inexistente_devuelve_404(client):
    r = client.post("/route-templates", json=_make_template_body())
    tpl_id = r.json()["id"]
    r = client.post(f"/route-templates/{tpl_id}/clone-to-world/9999")
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# TI-RT15 — Destino clonado tiene template_id correcto
# ---------------------------------------------------------------------------

def test_TI_RT15_destino_clonado_tiene_template_id(client):
    """El destino creado por clone tiene template_id con el id de la plantilla (CA-RT09)."""
    _, world_id = _setup_world(client)
    r = client.post("/route-templates", json=_make_template_body())
    tpl_id = r.json()["id"]
    r = client.post(f"/route-templates/{tpl_id}/clone-to-world/{world_id}")
    dest_id = r.json()["destination_id"]
    # Verificar template_id en EP-N03 (CA-RT21)
    r = client.get(f"/worlds/{world_id}/noise/destinations")
    dests = r.json()
    d = next(d for d in dests if d["id"] == dest_id)
    assert d["template_id"] == tpl_id


# ---------------------------------------------------------------------------
# TI-RT20 — Bulk clone (EP-RT08): 3 plantillas, una con conflicto
# ---------------------------------------------------------------------------

def test_TI_RT20_bulk_clone_mixto(client):
    """Bulk clone con cloned/already_exists/conflict en resultado por ítem (CA-RT17)."""
    _, world_id = _setup_world(client)

    # Plantilla 1: sin conflicto
    r = client.post("/route-templates", json=_make_template_body(slug="tpl-1", url_pattern="/karte.php"))
    tpl1_id = r.json()["id"]

    # Plantilla 2: URL diferente (sin conflicto en primer clone, ya_existe en bulk)
    r = client.post(
        "/route-templates",
        json=_make_template_body(slug="tpl-2", url_pattern="/report"),
    )
    tpl2_id = r.json()["id"]

    # Plantilla 3: URL ocupada por destino sin template_id
    r = client.post(
        f"/worlds/{world_id}/noise/destinations",
        json={"url_pattern": "/messages", "label": "Mensajes manual", "category_slug": "uncategorized"},
    )
    conflicting_id = r.json()["id"]
    r = client.post(
        "/route-templates",
        json=_make_template_body(slug="tpl-3", url_pattern="/messages"),
    )
    tpl3_id = r.json()["id"]

    # Clonar tpl1 primero para que aparezca como already_exists en el bulk
    client.post(f"/route-templates/{tpl1_id}/clone-to-world/{world_id}")

    r = client.post(
        f"/worlds/{world_id}/noise/apply-templates",
        json={"template_ids": [tpl1_id, tpl2_id, tpl3_id], "force": False},
    )
    assert r.status_code == 200, r.text
    results = {item["template_id"]: item for item in r.json()["results"]}
    assert results[tpl1_id]["result"] == "already_exists"
    assert results[tpl2_id]["result"] == "cloned"
    assert results[tpl3_id]["result"] == "conflict"
    assert results[tpl3_id]["conflicting_destination_id"] == conflicting_id
    assert_cabeceras_minimas(r)


def test_TI_RT21_bulk_clone_template_ids_vacio_devuelve_422(client):
    """EP-RT08 con template_ids=[] → 422 (CA-RT18)."""
    _, world_id = _setup_world(client)
    r = client.post(
        f"/worlds/{world_id}/noise/apply-templates",
        json={"template_ids": []},
    )
    assert r.status_code == 422, r.text


def test_TI_RT21b_bulk_clone_mundo_inexistente_devuelve_404(client):
    """EP-RT08 con mundo que no existe → 404."""
    r = client.post(
        "/worlds/9999/noise/apply-templates",
        json={"template_ids": [1]},
    )
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# TI-RT16 — Re-sync (EP-RT09): instancia existe → 200 synced
# ---------------------------------------------------------------------------

def test_TI_RT16_sync_instancia_existente_devuelve_200_synced(client):
    """Sync a mundo con instancia existente → 200 result=synced, paths_replaced."""
    _, world_id = _setup_world(client)
    r = client.post("/route-templates", json=_make_template_with_path())
    tpl_id = r.json()["id"]
    client.post(f"/route-templates/{tpl_id}/clone-to-world/{world_id}")
    # Modificar la plantilla para que tenga 2 paths
    nuevos_paths = [
        {
            "origin": "ANY",
            "label": "Path A",
            "steps": [{"step_order": 0, "action": "CLICK", "selector": "#a", "delay_min_ms": 500, "delay_max_ms": 900}],
        },
        {
            "origin": "DORF2",
            "label": "Path B",
            "steps": [{"step_order": 0, "action": "CLICK", "selector": "#b", "delay_min_ms": 500, "delay_max_ms": 900}],
        },
    ]
    client.put(f"/route-templates/{tpl_id}", json={"paths": nuevos_paths})
    r = client.post(f"/route-templates/{tpl_id}/sync-to-world/{world_id}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["result"] == "synced"
    assert data["paths_replaced"] == 2
    assert_cabeceras_minimas(r)


# ---------------------------------------------------------------------------
# TI-RT17 — Re-sync: sin instancia → 201 created
# ---------------------------------------------------------------------------

def test_TI_RT17_sync_sin_instancia_devuelve_201_created(client):
    """Sync a mundo SIN instancia → comportamiento de clone → 201 result=created (CA-RT16)."""
    _, world_id = _setup_world(client)
    r = client.post("/route-templates", json=_make_template_body())
    tpl_id = r.json()["id"]
    r = client.post(f"/route-templates/{tpl_id}/sync-to-world/{world_id}")
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["result"] == "created"
    assert "destination_id" in data
    assert "Location" in r.headers
    assert_cabeceras_minimas(r)


# ---------------------------------------------------------------------------
# TI-RT18 — Re-sync NO modifica navigation_weight de la instancia
# ---------------------------------------------------------------------------

def test_TI_RT18_sync_no_modifica_navigation_weight(client):
    """Sync NO sobreescribe navigation_weight del destino del usuario (CA-RT15)."""
    _, world_id = _setup_world(client)
    r = client.post("/route-templates", json=_make_template_with_path(navigation_weight=1.0))
    tpl_id = r.json()["id"]
    # Clonar
    r_clone = client.post(f"/route-templates/{tpl_id}/clone-to-world/{world_id}")
    dest_id = r_clone.json()["destination_id"]
    # Usuario cambia navigation_weight
    client.put(
        f"/worlds/{world_id}/noise/destinations/{dest_id}",
        json={"navigation_weight": 3.5},
    )
    # Sync
    client.post(f"/route-templates/{tpl_id}/sync-to-world/{world_id}")
    # El navigation_weight del destino debe seguir siendo 3.5
    dests = client.get(f"/worlds/{world_id}/noise/destinations").json()
    d = next(d for d in dests if d["id"] == dest_id)
    assert d["navigation_weight"] == 3.5


# ---------------------------------------------------------------------------
# TI-RT19 — Re-sync reemplaza paths/steps (CA-RT14)
# ---------------------------------------------------------------------------

def test_TI_RT19_sync_reemplaza_paths(client):
    """Sync sustituye paths/steps de la instancia por los de la plantilla actualizada."""
    _, world_id = _setup_world(client)
    r = client.post("/route-templates", json=_make_template_with_path())
    tpl_id = r.json()["id"]
    client.post(f"/route-templates/{tpl_id}/clone-to-world/{world_id}")
    # Actualizar plantilla con selector distinto
    nuevos_paths = [
        {
            "origin": "ANY",
            "label": "Path actualizado",
            "steps": [{"step_order": 0, "action": "CLICK", "selector": "#nuevo-selector", "delay_min_ms": 500, "delay_max_ms": 900}],
        }
    ]
    client.put(f"/route-templates/{tpl_id}", json={"paths": nuevos_paths})
    client.post(f"/route-templates/{tpl_id}/sync-to-world/{world_id}")
    # Verificar que los paths del destino se actualizaron
    dests = client.get(f"/worlds/{world_id}/noise/destinations").json()
    dest_id = next(d["id"] for d in dests if d["template_id"] == tpl_id)
    paths = client.get(f"/worlds/{world_id}/noise/destinations/{dest_id}/paths").json()
    assert len(paths) == 1
    assert paths[0]["steps"][0]["selector"] == "#nuevo-selector"


# ---------------------------------------------------------------------------
# TI-RT22/23 — Seed idempotente
# ---------------------------------------------------------------------------

def test_TI_RT22_seed_cargado_en_bd_vacia(client):
    """El seed carga plantillas al arrancar (CA-RT19). Al menos 1 plantilla."""
    r = client.get("/route-templates")
    assert r.status_code == 200
    templates = r.json()
    assert len(templates) >= 1, "El seed debe cargar al menos 1 plantilla"


def test_TI_RT23_seed_idempotente(client, monkeypatch, tmp_path):
    """
    Simular que el servidor arranca dos veces → no duplicados (CA-RT20).
    Verificamos indirectamente: el slug 'map-explore' del seed no se duplica.
    """
    r = client.get("/route-templates")
    templates = r.json()
    slugs = [t["slug"] for t in templates]
    # No debe haber slugs duplicados
    assert len(slugs) == len(set(slugs)), "Hay slugs duplicados en el catálogo"


# ---------------------------------------------------------------------------
# EP-N03/EP-N04 — Retrocompatibilidad con template_id
# ---------------------------------------------------------------------------

def test_EP_N03_response_incluye_template_id_null(client):
    """GET /worlds/{id}/noise/destinations → template_id=null en destinos creados a mano (CA-RT21)."""
    _, world_id = _setup_world(client)
    client.post(
        f"/worlds/{world_id}/noise/destinations",
        json={"url_pattern": "/karte.php", "label": "Mapa", "category_slug": "uncategorized"},
    )
    r = client.get(f"/worlds/{world_id}/noise/destinations")
    assert r.status_code == 200, r.text
    dests = r.json()
    assert len(dests) >= 1
    for d in dests:
        assert "template_id" in d, "template_id debe estar en el response de EP-N03"


def test_EP_N04_acepta_template_id_opcional_sin_romper(client):
    """POST /worlds/{id}/noise/destinations sin template_id → 201 (retrocompatible)."""
    _, world_id = _setup_world(client)
    r = client.post(
        f"/worlds/{world_id}/noise/destinations",
        json={"url_pattern": "/karte.php", "label": "Mapa", "category_slug": "uncategorized"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["template_id"] is None


# ---------------------------------------------------------------------------
# EP-RT10 — Test en vivo (mock de WorldAgent)
# ---------------------------------------------------------------------------

def test_RT10_test_plantilla_sin_sesion_activa_devuelve_409(client):
    """EP-RT10 sin WorldAgent activo → 409 desconectado."""
    _, world_id = _setup_world(client)
    r = client.post("/route-templates", json=_make_template_with_path())
    tpl_id = r.json()["id"]
    app.state.world_agents = {}  # sin agente
    r = client.post(f"/route-templates/{tpl_id}/test", json={"world_id": world_id})
    assert r.status_code == 409, r.text
    assert "desconectado" in r.json()["detail"].lower()


def test_RT10_test_plantilla_con_agente_activo_devuelve_200(client):
    """EP-RT10 con WorldAgent activo → 200, PathTestResponse shape correcto."""
    _, world_id = _setup_world(client)
    r = client.post("/route-templates", json=_make_template_with_path())
    tpl_id = r.json()["id"]

    report = _make_report(
        overall="ok",
        steps=[
            SimpleNamespace(
                step_order=0,
                action="WAIT_FOR_SELECTOR",
                selector="#map",
                status="ok",
                reason=None,
                current_url="/karte.php",
            )
        ],
    )
    app.state.world_agents = {world_id: _running_agent(report)}

    r = client.post(f"/route-templates/{tpl_id}/test", json={"world_id": world_id})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["overall"] == "ok"
    assert len(data["steps"]) == 1
    assert_cabeceras_minimas(r)

    # Limpiar
    app.state.world_agents = {}


def test_RT10_test_plantilla_path_index_fuera_de_rango_devuelve_422(client):
    """EP-RT10 con path_index fuera de rango → 422."""
    _, world_id = _setup_world(client)
    # Plantilla sin paths
    r = client.post("/route-templates", json=_make_template_body())
    tpl_id = r.json()["id"]

    report = _make_report()
    app.state.world_agents = {world_id: _running_agent(report)}

    r = client.post(f"/route-templates/{tpl_id}/test", json={"world_id": world_id, "path_index": 5})
    assert r.status_code == 422, r.text
    assert "path_index" in r.json()["detail"]

    app.state.world_agents = {}


def test_RT10_test_plantilla_browser_busy_devuelve_409(client):
    """EP-RT10 con BrowserBusyError → 409 browser ocupado."""
    _, world_id = _setup_world(client)
    r = client.post("/route-templates", json=_make_template_with_path())
    tpl_id = r.json()["id"]

    agent = _running_agent()
    agent.execute_path_test = AsyncMock(side_effect=BrowserBusyError())
    app.state.world_agents = {world_id: agent}

    r = client.post(f"/route-templates/{tpl_id}/test", json={"world_id": world_id})
    assert r.status_code == 409, r.text
    assert "ocupado" in r.json()["detail"].lower()

    app.state.world_agents = {}


def test_RT10_test_plantilla_404_plantilla_inexistente(client):
    """EP-RT10 con plantilla inexistente → 404."""
    r = client.post(f"/route-templates/9999/test", json={"world_id": 1})
    assert r.status_code == 404, r.text


def test_RT10_test_plantilla_404_mundo_inexistente(client):
    """EP-RT10 con mundo inexistente → 404."""
    r = client.post("/route-templates", json=_make_template_with_path())
    tpl_id = r.json()["id"]
    r = client.post(f"/route-templates/{tpl_id}/test", json={"world_id": 9999})
    assert r.status_code == 404, r.text


def test_RT10_test_plantilla_borra_instancia_temporal(client):
    """EP-RT10 crea clon temporal y lo borra tras el test."""
    _, world_id = _setup_world(client)
    r = client.post("/route-templates", json=_make_template_with_path())
    tpl_id = r.json()["id"]

    report = _make_report()
    app.state.world_agents = {world_id: _running_agent(report)}

    r = client.post(f"/route-templates/{tpl_id}/test", json={"world_id": world_id})
    assert r.status_code == 200, r.text

    # El clon temporal debe haberse borrado
    dests = client.get(f"/worlds/{world_id}/noise/destinations").json()
    assert all(d["label"] != "[TEST TEMPORAL]" for d in dests), (
        "El clon temporal [TEST TEMPORAL] no fue eliminado"
    )

    app.state.world_agents = {}


def test_RT10_test_plantilla_sin_clonar_usa_temporal_y_no_persiste(client):
    """EP-RT10 con plantilla NO clonada: crea temporal, ejecuta, borra. No queda nada."""
    _, world_id = _setup_world(client)
    r = client.post("/route-templates", json=_make_template_with_path())
    tpl_id = r.json()["id"]

    report = _make_report(overall="error")
    app.state.world_agents = {world_id: _running_agent(report)}

    # No hay instancia clonada → debe crear temporal
    r = client.post(f"/route-templates/{tpl_id}/test", json={"world_id": world_id})
    assert r.status_code == 200, r.text
    assert r.json()["overall"] == "error"

    # No debe quedar ninguna instancia en el mundo
    dests = client.get(f"/worlds/{world_id}/noise/destinations").json()
    assert all(d["template_id"] != tpl_id for d in dests), (
        "La instancia temporal no fue eliminada"
    )

    app.state.world_agents = {}


# ---------------------------------------------------------------------------
# Cabeceras mínimas — test específico
# ---------------------------------------------------------------------------

def test_cabeceras_minimas_en_get_templates(client):
    """Verificación explícita de cabeceras mínimas en GET /route-templates."""
    r = client.get("/route-templates")
    assert r.status_code == 200
    assert "x-request-id" in r.headers
    assert "x-api-version" in r.headers
    assert "application/json" in r.headers.get("content-type", "")
    assert "x-content-type-options" in r.headers
    assert "x-frame-options" in r.headers


def test_eco_x_request_id(client):
    """Enviar X-Request-ID en la request → vuelve idéntico en la response."""
    custom_id = "mi-request-id-12345"
    r = client.get("/route-templates", headers={"X-Request-ID": custom_id})
    assert r.headers.get("x-request-id") == custom_id
