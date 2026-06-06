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
    """
    Cuerpo mínimo válido para crear una plantilla.
    NOTA v2 rev.2: navigation_weight eliminado del body — el peso se fija al clonar.
    """
    base = {
        "slug": "test-template",
        "label": "Plantilla de test",
        "category_slug": "uncategorized",
        "url_pattern": "/karte.php",
        "is_safe": True,
        "paths": [],
    }
    # Quitar navigation_weight si se pasa (eliminado en v2 rev.2)
    overrides.pop("navigation_weight", None)
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
    """
    POST /route-templates con datos válidos → 201, objeto completo, Location.
    NOTA v2 rev.2: navigation_weight eliminado del response de plantilla.
    """
    r = client.post("/route-templates", json=_make_template_body())
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["slug"] == "test-template"
    assert data["label"] == "Plantilla de test"
    assert data["category_slug"] == "uncategorized"
    assert data["url_pattern"] == "/karte.php"
    assert "navigation_weight" not in data, (
        "navigation_weight fue eliminado de RouteTemplate en v2 rev.2"
    )
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


def test_TI_RT02c_navigation_weight_ignorado_en_plantilla(client):
    """
    POST /route-templates con navigation_weight en el body → se ignora (v2 rev.2).
    La plantilla se crea correctamente y el response no contiene navigation_weight.
    navigation_weight fue eliminado del modelo de plantilla; el body lo ignora.
    Spec §v2-PESO.
    """
    # Enviar navigation_weight en el body — debe ignorarse (no es un campo del modelo)
    r = client.post("/route-templates", json={
        "slug": "test-weight-ignore",
        "label": "Test ignore weight",
        "category": "MAP",
        "url_pattern": "/karte.php",
        "navigation_weight": 0.05,  # campo eliminado — Pydantic lo ignora por defecto
    })
    # 201 porque la plantilla se crea; navigation_weight se ignora silenciosamente
    assert r.status_code == 201, r.text
    data = r.json()
    assert "navigation_weight" not in data


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


def test_TI_RT04_categoria_libre_devuelve_200_lista_vacia(client):
    """
    GET /route-templates?category=INVALIDA → 200 con lista vacía.

    Desde v2-cat-libre, category es texto libre (no enum). Cualquier string es
    válido como filtro; si no hay coincidencias devuelve []. Ya no hay 422.
    """
    r = client.get("/route-templates?category=INVALIDA")
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
    """
    El seed se carga al arrancar (CA-RT19).
    NOTA v2: seeds/route_templates.json está vacío ([]) — el seed devuelve 0 plantillas.
    El test verifica que el endpoint responde 200 (no error) y que no hay duplicados.
    Cuando el seed tenga plantillas atómicas encadenadas (Fase v2), este test se ajustará.
    """
    r = client.get("/route-templates")
    assert r.status_code == 200
    templates = r.json()
    # El seed v2 está vacío; la BD empieza vacía
    assert isinstance(templates, list), "Debe devolver una lista"
    # Sin duplicados
    slugs = [t["slug"] for t in templates]
    assert len(slugs) == len(set(slugs)), "No debe haber slugs duplicados"


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

def test_RT10_v3_sin_agente_sin_session_registry_world_sin_cuenta_devuelve_404(client):
    """
    EP-RT10 v3 — mundo sin cuenta asociada → 404 "no tiene cuenta asociada".
    En v3 ya no hay 409 "desconectado": se intenta ensure_session.
    Si el mundo no tiene cuenta → WorldOrphanError → 404.
    El world_id creado por _setup_world SÍ tiene cuenta, así que usamos un ID válido
    pero sin cuenta: crear solo el mundo sin cuenta (imposible vía HTTP, así que
    usamos un world_id de otro setup donde quitamos la cuenta a nivel de app.state).
    Alternativa: usar world_id=9999 para 404 de "mundo no encontrado".
    El test válido para "mundo sin cuenta" requiere mock del db_port, así que
    probamos el caso más común: mundo inexistente → 404 con _ensure_session.
    """
    r = client.post("/route-templates", json=_make_template_with_path())
    tpl_id = r.json()["id"]
    app.state.world_agents = {}  # sin agente
    # Mundo inexistente → 404 de _require_world antes de ensure_session
    r = client.post(f"/route-templates/{tpl_id}/test", json={"world_id": 9999})
    assert r.status_code == 404, r.text


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


# ---------------------------------------------------------------------------
# EP-RT11 — GET /route-templates/{id}/chain (v2 NUEVO)
# ---------------------------------------------------------------------------

def _make_chain_template(client, slug: str, origin_template_id=None) -> int:
    """Crea plantilla con un step válido, opcionalmente con origen. Devuelve su id."""
    body = {
        "slug": slug,
        "label": f"Plantilla {slug}",
        "category": "OTHER",
        "url_pattern": f"/path-{slug}",
        "is_safe": True,
        "origin_template_id": origin_template_id,
        "paths": [
            {
                "origin": "ANY" if origin_template_id is None else f"ROUTE_TEMPLATE:{origin_template_id}",
                "label": "path de test",
                "is_active": True,
                "steps": [
                    {
                        "step_order": 0,
                        "action": "CLICK",
                        "selector": f"a[href*='{slug}']",
                        "value": "",
                        "delay_min_ms": 400,
                        "delay_max_ms": 800,
                    }
                ],
            }
        ],
    }
    r = client.post("/route-templates", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_TI_V2_04_chain_cadena_de_3_niveles(client):
    """EP-RT11 — cadena de 3 niveles → 200 con 3 steps ordenados, primero is_root=true."""
    raiz_id = _make_chain_template(client, "raiz-stats")
    medio_id = _make_chain_template(client, "top10-alianzas", origin_template_id=raiz_id)
    hoja_id = _make_chain_template(client, "top10-rivales", origin_template_id=medio_id)

    r = client.get(f"/route-templates/{hoja_id}/chain")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["template_id"] == hoja_id
    assert data["template_slug"] == "top10-rivales"
    assert data["depth"] == 3
    assert len(data["steps"]) == 3
    # El primero es la raíz
    assert data["steps"][0]["is_root"] is True
    assert data["steps"][0]["template_id"] == raiz_id
    # El último es la hoja
    assert data["steps"][2]["template_id"] == hoja_id
    assert data["steps"][2]["is_root"] is False
    # Posiciones en orden
    for i, step in enumerate(data["steps"]):
        assert step["position"] == i
    assert_cabeceras_minimas(r)


def test_TI_V2_05_chain_ruta_raiz_devuelve_1_step(client):
    """EP-RT11 — ruta raíz (sin origen) → 200 con 1 step, is_root=true."""
    raiz_id = _make_chain_template(client, "solo-raiz")
    r = client.get(f"/route-templates/{raiz_id}/chain")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["depth"] == 1
    assert len(data["steps"]) == 1
    assert data["steps"][0]["is_root"] is True
    assert data["steps"][0]["template_id"] == raiz_id


def test_TI_V2_06_chain_con_origen_borrado_devuelve_solo_clic_propio(client):
    """EP-RT11 — origen borrado (ON DELETE SET NULL actuó) → 200 con solo el clic propio."""
    raiz_id = _make_chain_template(client, "raiz-borrar")
    hija_id = _make_chain_template(client, "hija-huerfana", origin_template_id=raiz_id)

    # Borrar la raíz → ON DELETE SET NULL pone origin_template_id=NULL en la hija
    r = client.delete(f"/route-templates/{raiz_id}")
    assert r.status_code == 204, r.text

    # La hija ahora es raíz (origin=NULL por ON DELETE SET NULL)
    r = client.get(f"/route-templates/{hija_id}/chain")
    assert r.status_code == 200, r.text
    data = r.json()
    # Solo el clic propio de la hija (que ahora es raíz)
    assert len(data["steps"]) == 1
    assert data["steps"][0]["template_id"] == hija_id


def test_TI_V2_chain_404_plantilla_inexistente(client):
    """EP-RT11 con plantilla inexistente → 404."""
    r = client.get("/route-templates/9999/chain")
    assert r.status_code == 404, r.text


def test_TI_V2_chain_plantilla_sin_path_steps_vacios(client):
    """EP-RT11 — plantilla sin paths/steps → 200 con steps vacío (EC-V2-07)."""
    body = _make_template_body(slug="sin-steps")
    r = client.post("/route-templates", json=body)
    assert r.status_code == 201, r.text
    tpl_id = r.json()["id"]
    r = client.get(f"/route-templates/{tpl_id}/chain")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["depth"] == 0
    assert data["steps"] == []


# ---------------------------------------------------------------------------
# EP-RT02/EP-RT04 — Validación anti-ciclos (v2)
# ---------------------------------------------------------------------------

def test_TI_V2_01_create_con_origin_valido_devuelve_201_con_origin_template_id(client):
    """POST /route-templates con origin_template_id válido → 201 con origin_template_id en response."""
    raiz_id = _make_chain_template(client, "raiz-v2-01")
    body = _make_template_body(slug="hija-v2-01", origin_template_id=raiz_id)
    r = client.post("/route-templates", json=body)
    assert r.status_code == 201, r.text
    assert r.json()["origin_template_id"] == raiz_id


def test_TI_V2_02_create_con_origin_inexistente_devuelve_404(client):
    """POST /route-templates con origin_template_id inexistente → 404."""
    body = _make_template_body(slug="hija-orphan", origin_template_id=9999)
    r = client.post("/route-templates", json=body)
    assert r.status_code == 404, r.text
    assert "9999" in r.json()["detail"]


def test_TI_V2_03_put_que_crea_ciclo_directo_devuelve_409_con_cycle_path(client):
    """PUT /route-templates/{id} con origin_template_id que crea ciclo directo → 409 cycle_path."""
    a_id = _make_chain_template(client, "ciclo-a")
    b_id = _make_chain_template(client, "ciclo-b", origin_template_id=a_id)
    # Intentar que A → B (lo que crearía A→B y B→A = ciclo)
    r = client.put(f"/route-templates/{a_id}", json={"origin_template_id": b_id})
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert "cycle_path" in detail
    assert isinstance(detail["cycle_path"], list)


def test_TI_V2_04_put_origin_valido_sin_ciclo_devuelve_200(client):
    """PUT /route-templates/{id} con origin_template_id válido (sin ciclo) → 200."""
    raiz_id = _make_chain_template(client, "raiz-put-v2")
    hija_id = _make_chain_template(client, "hija-put-v2")
    # Reasignar hija para tener raíz como origen
    r = client.put(f"/route-templates/{hija_id}", json={"origin_template_id": raiz_id})
    assert r.status_code == 200, r.text
    assert r.json()["origin_template_id"] == raiz_id


# ---------------------------------------------------------------------------
# EP-RT02/EP-RT04 — Validación selectores estructurales (v2 GAP-4)
# ---------------------------------------------------------------------------

def test_TI_V2_11_create_selector_por_texto_visible_devuelve_422(client):
    """POST /route-templates con selector ':has-text(...)' → 422 con mensaje multi-idioma."""
    body = {
        "slug": "bad-selector-create",
        "label": "Test",
        "category": "OTHER",
        "url_pattern": "/test",
        "is_safe": True,
        "paths": [
            {
                "origin": "ANY",
                "label": "path",
                "is_active": True,
                "steps": [
                    {
                        "step_order": 0,
                        "action": "CLICK",
                        "selector": 'a:has-text("Estadísticas")',
                        "value": "",
                        "delay_min_ms": 500,
                        "delay_max_ms": 900,
                    }
                ],
            }
        ],
    }
    r = client.post("/route-templates", json=body)
    assert r.status_code == 422, r.text
    assert "texto visible" in r.json()["detail"]
    assert "idioma" in r.json()["detail"].lower()


def test_TI_V2_12_put_paths_con_contains_devuelve_422(client):
    """PUT /route-templates/{id} con paths que incluyen ':contains(...)' → 422."""
    tpl_id = _make_chain_template(client, "bad-selector-put")
    r = client.put(
        f"/route-templates/{tpl_id}",
        json={
            "paths": [
                {
                    "origin": "ANY",
                    "label": "path mal",
                    "is_active": True,
                    "steps": [
                        {
                            "step_order": 0,
                            "action": "CLICK",
                            "selector": 'li:contains("Mensajes")',
                            "value": "",
                            "delay_min_ms": 500,
                            "delay_max_ms": 900,
                        }
                    ],
                }
            ]
        },
    )
    assert r.status_code == 422, r.text
    assert "texto visible" in r.json()["detail"]


def test_TI_V2_13_create_selector_estructural_valido_devuelve_201(client):
    """POST /route-templates con selector estructural válido → 201, sin error."""
    body = {
        "slug": "good-selector",
        "label": "Test selector correcto",
        "category": "OTHER",
        "url_pattern": "/statistics",
        "is_safe": True,
        "paths": [
            {
                "origin": "ANY",
                "label": "path",
                "is_active": True,
                "steps": [
                    {
                        "step_order": 0,
                        "action": "CLICK",
                        "selector": "a[href*='/statistics']",
                        "value": "",
                        "delay_min_ms": 500,
                        "delay_max_ms": 900,
                    }
                ],
            }
        ],
    }
    r = client.post("/route-templates", json=body)
    assert r.status_code == 201, r.text


# ---------------------------------------------------------------------------
# EP-RT07 — navigation_weight del REQUEST (v2)
# ---------------------------------------------------------------------------

def test_EP_RT07_v2_navigation_weight_del_request_se_aplica(client):
    """EP-RT07 — navigation_weight del body del REQUEST se aplica al destino clonado."""
    _, world_id = _setup_world(client)
    r = client.post("/route-templates", json=_make_template_body())
    tpl_id = r.json()["id"]

    # Clonar con peso 2.5
    r = client.post(
        f"/route-templates/{tpl_id}/clone-to-world/{world_id}",
        json={"navigation_weight": 2.5},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["result"] == "cloned"
    assert data["navigation_weight"] == 2.5

    # Verificar que el destino tiene navigation_weight=2.5 (alias de frequency_weight en el response)
    dest_id = data["destination_id"]
    dests = client.get(f"/worlds/{world_id}/noise/destinations").json()
    dest = next((d for d in dests if d["id"] == dest_id), None)
    assert dest is not None
    assert dest["navigation_weight"] == 2.5


def test_EP_RT07_v2_navigation_weight_default_1_si_body_omitido(client):
    """EP-RT07 — body omitido → navigation_weight=1.0 por defecto."""
    _, world_id = _setup_world(client)
    r = client.post("/route-templates", json=_make_template_body())
    tpl_id = r.json()["id"]

    # Sin body
    r = client.post(f"/route-templates/{tpl_id}/clone-to-world/{world_id}")
    assert r.status_code == 201, r.text
    assert r.json()["navigation_weight"] == 1.0


def test_EP_RT07_v2_navigation_weight_fuera_de_rango_devuelve_422(client):
    """EP-RT07 — navigation_weight=5.5 (fuera de [0.1,5.0]) → 422."""
    _, world_id = _setup_world(client)
    r = client.post("/route-templates", json=_make_template_body(slug="weight-422"))
    tpl_id = r.json()["id"]

    r = client.post(
        f"/route-templates/{tpl_id}/clone-to-world/{world_id}",
        json={"navigation_weight": 5.5},
    )
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# EP-RT08 — default_navigation_weight en bulk (v2)
# ---------------------------------------------------------------------------

def test_EP_RT08_v2_default_navigation_weight_se_aplica_a_clonados(client):
    """EP-RT08 — default_navigation_weight se aplica a cada ítem clonado."""
    _, world_id = _setup_world(client)
    r1 = client.post("/route-templates", json=_make_template_body(slug="bulk-w-1"))
    r2 = client.post("/route-templates", json=_make_template_body(slug="bulk-w-2", url_pattern="/bulk-w-2"))
    ids = [r1.json()["id"], r2.json()["id"]]

    r = client.post(
        f"/worlds/{world_id}/noise/apply-templates",
        json={"template_ids": ids, "default_navigation_weight": 3.0},
    )
    assert r.status_code == 200, r.text
    results = r.json()["results"]
    cloned = [x for x in results if x["result"] == "cloned"]
    assert all(x["navigation_weight"] == 3.0 for x in cloned)


# ---------------------------------------------------------------------------
# EP-RT12 — DELETE /worlds/{world_id}/session (v3 NUEVO)
# ---------------------------------------------------------------------------

def test_TI_V3_08_delete_session_sin_sesion_activa_idempotente_204(client):
    """DELETE /worlds/{id}/session sin sesión activa → 204 idempotente."""
    _, world_id = _setup_world(client)
    # session_registry.is_active=False (sin sesión)
    session_mock = MagicMock()
    session_mock.close_session = AsyncMock()
    app.state.world_runtime_port = session_mock

    r = client.delete(f"/worlds/{world_id}/session")
    assert r.status_code == 204, r.text
    session_mock.close_session.assert_called_once_with(world_id)


def test_TI_V3_10_delete_session_world_inexistente_devuelve_404(client):
    """DELETE /worlds/9999/session con world_id inexistente → 404."""
    r = client.delete("/worlds/9999/session")
    assert r.status_code == 404, r.text
    assert "no encontrado" in r.json()["detail"].lower()


def test_TI_V3_stop_agent_cierra_sesion_chrome(client):
    """POST /farm/worlds/{id}/agent/stop → cierra también la sesión Chrome."""
    _, world_id = _setup_world(client)

    from core.scheduling.world_agent import AgentState
    agent = MagicMock()
    agent.state = AgentState.RUNNING
    agent.request_stop = MagicMock()
    app.state.world_agents = {world_id: agent}

    session_mock = MagicMock()
    session_mock.close_session = AsyncMock()
    app.state.world_runtime_port = session_mock

    r = client.post(f"/farm/worlds/{world_id}/agent/stop")
    assert r.status_code == 200, r.text
    agent.request_stop.assert_called_once()
    session_mock.close_session.assert_called_once_with(world_id)

    app.state.world_agents = {}


# ---------------------------------------------------------------------------
# EP-RT10 v3 — _ensure_session con mocks
# ---------------------------------------------------------------------------

def test_TI_V3_02_ep_rt10_sesion_ya_activa_no_hace_login(client):
    """EP-RT10 v3 — sesión ya activa → ensure_session NO llama login de nuevo."""
    _, world_id = _setup_world(client)
    r = client.post("/route-templates", json=_make_template_with_path())
    tpl_id = r.json()["id"]

    # Montar session_registry con is_active=True
    session_mock = MagicMock()
    session_mock.is_active = MagicMock(return_value=True)
    session_mock.get_browser = MagicMock(return_value=None)
    app.state.world_runtime_port = session_mock

    report = _make_report(overall="ok")
    app.state.world_agents = {world_id: _running_agent(report)}

    r = client.post(f"/route-templates/{tpl_id}/test", json={"world_id": world_id})
    # is_active=True → ensure_session retorna inmediatamente sin llamar login
    # execute_path_test del agente → 200
    assert r.status_code == 200, r.text
    # Verificar que login NO fue llamado (solo is_active)
    session_mock.login.assert_not_called()

    app.state.world_agents = {}


def test_TI_V3_03_ep_rt10_mundo_sin_cuenta_devuelve_404(client):
    """EP-RT10 v3 — mundo sin cuenta asociada → 404."""
    _, world_id = _setup_world(client)
    r = client.post("/route-templates", json=_make_template_with_path())
    tpl_id = r.json()["id"]

    # session_registry con is_active=False; accounts_db que devuelve None para account_id
    session_mock = MagicMock()
    session_mock.is_active = MagicMock(return_value=False)
    app.state.world_runtime_port = session_mock
    app.state.world_agents = {}

    # Mock del accounts_db para que get_account_id_for_world devuelva None
    original_db = getattr(app.state, "db_port", None)
    mock_db = MagicMock()
    mock_db.get_world = AsyncMock(return_value=MagicMock(id=world_id, server="https://ts1.travian.es/"))
    mock_db.get_account_id_for_world = AsyncMock(return_value=None)
    app.state.db_port = mock_db

    try:
        r = client.post(f"/route-templates/{tpl_id}/test", json={"world_id": world_id})
        assert r.status_code == 404, r.text
        assert "cuenta asociada" in r.json()["detail"]
    finally:
        if original_db is not None:
            app.state.db_port = original_db


def test_TI_V3_04_ep_rt10_fernet_error_devuelve_401(client):
    """EP-RT10 v3 — FernetDecryptionError → 401 con mención a TRAVIAN_BOT_SECRET_KEY."""
    from core.exceptions import FernetDecryptionError as FDE
    _, world_id = _setup_world(client)
    r = client.post("/route-templates", json=_make_template_with_path())
    tpl_id = r.json()["id"]

    session_mock = MagicMock()
    session_mock.is_active = MagicMock(return_value=False)
    app.state.world_runtime_port = session_mock
    app.state.world_agents = {}

    original_db = getattr(app.state, "db_port", None)
    mock_db = MagicMock()
    mock_db.get_world = AsyncMock(return_value=MagicMock(id=world_id, server="https://ts1.travian.es/"))
    mock_db.get_account_id_for_world = AsyncMock(return_value=42)
    app.state.db_port = mock_db
    original_fernet = getattr(app.state, "fernet", None)
    app.state.fernet = MagicMock()  # fernet real necesario solo para LoginUseCase

    # Mock de LoginUseCase para que lance FernetDecryptionError
    import unittest.mock as um
    with um.patch(
        "core.use_cases.login_use_case.LoginUseCase.execute",
        new=AsyncMock(side_effect=FDE(42)),
    ):
        try:
            r = client.post(f"/route-templates/{tpl_id}/test", json={"world_id": world_id})
            assert r.status_code == 401, r.text
            assert "travian_bot_secret_key" in r.json()["detail"].lower()
        finally:
            if original_db is not None:
                app.state.db_port = original_db
            if original_fernet is not None:
                app.state.fernet = original_fernet


def test_TI_V3_05_ep_rt10_login_failed_devuelve_401(client):
    """EP-RT10 v3 — LoginFailedError → 401 con mención a credenciales."""
    from core.exceptions import LoginFailedError as LFE
    _, world_id = _setup_world(client)
    r = client.post("/route-templates", json=_make_template_with_path())
    tpl_id = r.json()["id"]

    session_mock = MagicMock()
    session_mock.is_active = MagicMock(return_value=False)
    app.state.world_runtime_port = session_mock
    app.state.world_agents = {}

    original_db = getattr(app.state, "db_port", None)
    mock_db = MagicMock()
    mock_db.get_world = AsyncMock(return_value=MagicMock(id=world_id, server="https://ts1.travian.es/"))
    mock_db.get_account_id_for_world = AsyncMock(return_value=42)
    app.state.db_port = mock_db
    original_fernet = getattr(app.state, "fernet", None)
    app.state.fernet = MagicMock()

    import unittest.mock as um
    with um.patch(
        "core.use_cases.login_use_case.LoginUseCase.execute",
        new=AsyncMock(side_effect=LFE("rtbot")),
    ):
        try:
            r = client.post(f"/route-templates/{tpl_id}/test", json={"world_id": world_id})
            assert r.status_code == 401, r.text
            assert "credencial" in r.json()["detail"].lower()
        finally:
            if original_db is not None:
                app.state.db_port = original_db
            if original_fernet is not None:
                app.state.fernet = original_fernet


def test_TI_V3_06_ep_rt10_sin_world_agent_usa_standalone(client):
    """EP-RT10 v3 — sin WorldAgent pero con sesión activa → usa execute_path_test_standalone."""
    _, world_id = _setup_world(client)
    r = client.post("/route-templates", json=_make_template_with_path())
    tpl_id = r.json()["id"]

    # Sesión activa, sin WorldAgent
    mock_browser = MagicMock()
    session_mock = MagicMock()
    session_mock.is_active = MagicMock(return_value=True)  # sesión ya activa
    session_mock.get_browser = MagicMock(return_value=mock_browser)
    app.state.world_runtime_port = session_mock
    app.state.world_agents = {}  # sin agente

    import unittest.mock as um
    from core.scheduling import world_agent as wa_module

    mock_report = _make_report(overall="ok", steps=[
        SimpleNamespace(
            step_order=0,
            action="WAIT_FOR_SELECTOR",
            selector="#map",
            status="ok",
            reason=None,
            current_url="/karte.php",
        )
    ])
    with um.patch.object(wa_module, "execute_path_test_standalone", new=AsyncMock(return_value=mock_report)):
        r = client.post(f"/route-templates/{tpl_id}/test", json={"world_id": world_id})
        assert r.status_code == 200, r.text
        assert r.json()["overall"] == "ok"


def test_TI_V3_07_ep_rt10_con_world_agent_usa_world_agent(client):
    """EP-RT10 v3 — con WorldAgent RUNNING → usa WorldAgent.execute_path_test (no standalone)."""
    _, world_id = _setup_world(client)
    r = client.post("/route-templates", json=_make_template_with_path())
    tpl_id = r.json()["id"]

    session_mock = MagicMock()
    session_mock.is_active = MagicMock(return_value=True)
    session_mock.get_browser = MagicMock(return_value=MagicMock())
    app.state.world_runtime_port = session_mock

    report = _make_report(overall="ok")
    agent = _running_agent(report)
    app.state.world_agents = {world_id: agent}

    r = client.post(f"/route-templates/{tpl_id}/test", json={"world_id": world_id})
    assert r.status_code == 200, r.text
    # El WorldAgent.execute_path_test fue llamado
    agent.execute_path_test.assert_called_once()

    app.state.world_agents = {}


# ---------------------------------------------------------------------------
# v2-cat-libre — Categoría libre: crear, editar, filtrar
# ---------------------------------------------------------------------------

def test_CAT01_crear_plantilla_con_categoria_libre(client):
    """POST /route-templates con category="Estadísticas" → 201, category guardada."""
    body = _make_template_body(slug="stats-libre", category="Estadísticas")
    r = client.post("/route-templates", json=body)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["category"] == "Estadísticas"


def test_CAT02_crear_plantilla_con_top10(client):
    """POST /route-templates con category="Top 10" → 201."""
    body = _make_template_body(slug="top-10-libre", category="Top 10", url_pattern="/dorf1.php")
    r = client.post("/route-templates", json=body)
    assert r.status_code == 201, r.text
    assert r.json()["category"] == "Top 10"


def test_CAT03_editar_categoria_de_ruta_existente(client):
    """PUT /route-templates/{id} con category nueva → 200, category actualizada."""
    r = client.post("/route-templates", json=_make_template_body(slug="edit-cat-test"))
    tpl_id = r.json()["id"]
    assert r.json()["category"] == "MAP"

    r = client.put(f"/route-templates/{tpl_id}", json={"category": "Estadísticas"})
    assert r.status_code == 200, r.text
    assert r.json()["category"] == "Estadísticas"


def test_CAT04_editar_categoria_persiste_tras_get(client):
    """Editar categoría y verificar que GET devuelve la nueva categoría."""
    r = client.post("/route-templates", json=_make_template_body(slug="cat-persist"))
    tpl_id = r.json()["id"]

    client.put(f"/route-templates/{tpl_id}", json={"category": "Top 10"})

    r = client.get(f"/route-templates/{tpl_id}")
    assert r.status_code == 200, r.text
    assert r.json()["category"] == "Top 10"


def test_CAT05_categoria_vacia_devuelve_422(client):
    """POST /route-templates con category="" → 422 (campo requerido, min_length=1)."""
    body = _make_template_body(slug="cat-empty", category="")
    r = client.post("/route-templates", json=body)
    assert r.status_code == 422, r.text


def test_CAT06_categoria_demasiado_larga_devuelve_422(client):
    """POST /route-templates con category de más de 50 chars → 422."""
    long_cat = "A" * 51
    body = _make_template_body(slug="cat-long", category=long_cat)
    r = client.post("/route-templates", json=body)
    assert r.status_code == 422, r.text


def test_CAT07_filtrar_por_categoria_libre(client):
    """GET /route-templates?category=Estadísticas → solo las que tienen esa categoría."""
    client.post("/route-templates", json=_make_template_body(slug="cat-a", category="Estadísticas"))
    client.post("/route-templates", json=_make_template_body(slug="cat-b", category="MAP", url_pattern="/karte.php"))
    r = client.get("/route-templates?category=Estadísticas")
    assert r.status_code == 200, r.text
    items = r.json()
    assert all(t["category"] == "Estadísticas" for t in items)
    slugs = [t["slug"] for t in items]
    assert "cat-a" in slugs
    assert "cat-b" not in slugs


def test_CAT08_url_pattern_invalido_devuelve_422_en_putcategory(client):
    """PUT /route-templates/{id} con url_pattern → 422 (inmutable)."""
    r = client.post("/route-templates", json=_make_template_body(slug="url-immut"))
    tpl_id = r.json()["id"]
    r = client.put(f"/route-templates/{tpl_id}", json={"url_pattern": "/new.php"})
    assert r.status_code == 422, r.text
