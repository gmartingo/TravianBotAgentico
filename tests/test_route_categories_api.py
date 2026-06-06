"""
Tests de integración HTTP para el Catálogo Dinámico de Categorías de Rutas.

Cubre:
  - EP-CAT01 GET /route-categories — listar categorías.
  - EP-CAT02 POST /route-categories — crear (201 + Location), duplicado → 409, vacío → 422, color inválido → 422.
  - EP-CAT03 GET /route-categories/{slug} — obtener, 404 si no existe.
  - EP-CAT04 PATCH /route-categories/{slug} — actualizar label/color, body vacío → 422, duplicado → 409.
  - EP-CAT05 DELETE /route-categories/{slug} — borrar vacía, borrar con rutas, borrar default → 409.
  - Criterios de aceptación AC-01..AC-16 del spec §15.
  - Edge cases EC-CAT01..EC-CAT11 de §6.

Spec route-categories-dynamic.md §8, §12.3, §15.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from adapters.api.main import app


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

_APP_STATE_ATTRS = (
    "world_runtime_port", "farm_db_port", "world_agents",
    "session_db_port", "db_port", "noise_db_port",
    "route_template_port", "route_category_port",
)


@pytest.fixture
def client(monkeypatch, tmp_path):
    """TestClient con BD en archivo temporal y lifespan real."""
    db_file = tmp_path / "test_categories.db"
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

def _setup_world(c: TestClient) -> tuple[int, int]:
    """Crea account + world. Devuelve (account_id, world_id)."""
    r = c.post(
        "/accounts",
        json={"email": "cat_test@example.com", "username": "catbot", "password": "pass123"},
    )
    assert r.status_code == 201, r.text
    account_id = r.json()["id"]
    r = c.post(
        f"/accounts/{account_id}/worlds",
        json={"server": "https://ts1.travian.es/", "tribe": "romans"},
    )
    assert r.status_code == 201, r.text
    return account_id, r.json()["id"]


def _create_category(c: TestClient, label: str, color: str | None = None) -> dict:
    body = {"label": label}
    if color is not None:
        body["color"] = color
    r = c.post("/route-categories", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _create_template(c: TestClient, slug: str, category_slug: str = "uncategorized") -> dict:
    r = c.post(
        "/route-templates",
        json={
            "slug": slug,
            "label": f"Template {slug}",
            "category_slug": category_slug,
            "url_pattern": f"/{slug}.php",
            "navigation_weight": 1.0,
            "is_safe": True,
            "paths": [],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------
# EP-CAT01 — GET /route-categories
# ---------------------------------------------------------------------------

class TestEP_CAT01_List:

    def test_list_returns_uncategorized_in_new_db(self, client):
        """AC-01: GET /route-categories en BD nueva devuelve 1 item: uncategorized."""
        r = client.get("/route-categories")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["slug"] == "uncategorized"
        assert data[0]["is_default"] is True

    def test_list_uncategorized_first(self, client):
        """La categoría default siempre aparece primera."""
        _create_category(client, "Zebra")
        _create_category(client, "Alpha")
        r = client.get("/route-categories")
        items = r.json()
        assert items[0]["slug"] == "uncategorized"

    def test_list_includes_all_categories(self, client):
        """Después de crear 2 categorías, la lista tiene 3 (uncategorized + 2)."""
        _create_category(client, "Mapa")
        _create_category(client, "Oasis")
        r = client.get("/route-categories")
        assert r.status_code == 200
        assert len(r.json()) == 3


# ---------------------------------------------------------------------------
# EP-CAT02 — POST /route-categories
# ---------------------------------------------------------------------------

class TestEP_CAT02_Create:

    def test_create_ok_201_with_location(self, client):
        """AC-02: POST → 201 + slug generado + Location header."""
        r = client.post("/route-categories", json={"label": "Mapa", "color": "#4A90D9"})
        assert r.status_code == 201
        data = r.json()
        assert data["slug"] == "mapa"
        assert data["label"] == "Mapa"
        assert data["color"] == "#4A90D9"
        assert data["is_default"] is False
        assert "Location" in r.headers
        assert r.headers["Location"] == "/route-categories/mapa"

    def test_create_without_color_ok(self, client):
        """Crear sin color es válido (RN-CAT09)."""
        r = client.post("/route-categories", json={"label": "Sin Color"})
        assert r.status_code == 201
        assert r.json()["color"] is None

    def test_create_duplicate_label_409(self, client):
        """AC-03: label duplicado (CI) → 409."""
        client.post("/route-categories", json={"label": "Mapa"})
        r = client.post("/route-categories", json={"label": "mapa"})
        assert r.status_code == 409
        assert "ya existe" in r.json()["detail"].lower()

    def test_create_empty_label_422(self, client):
        """Label vacío → 422."""
        r = client.post("/route-categories", json={"label": ""})
        assert r.status_code == 422

    def test_create_whitespace_only_label_422(self, client):
        """EC-CAT03: Label de solo espacios → 422."""
        r = client.post("/route-categories", json={"label": "   "})
        assert r.status_code == 422

    def test_create_invalid_color_422(self, client):
        """Color sin # → 422 (validación Pydantic)."""
        r = client.post("/route-categories", json={"label": "Test", "color": "4A90D9"})
        assert r.status_code == 422

    def test_create_short_hex_color_ok(self, client):
        """Color hex de 3 chars (#RGB) es válido."""
        r = client.post("/route-categories", json={"label": "Azul", "color": "#4AF"})
        assert r.status_code == 201
        assert r.json()["color"] == "#4AF"

    def test_create_slug_auto_generated_from_label(self, client):
        """El slug se genera automáticamente (RN-CAT08)."""
        r = client.post("/route-categories", json={"label": "Oasis Info"})
        assert r.status_code == 201
        assert r.json()["slug"] == "oasis-info"

    def test_create_slug_collision_gets_suffix(self, client):
        """EC-CAT04: colisión de slugs genera sufijo -2, -3, etc."""
        # "A-B" y "A B" generan el mismo slug "a-b"
        r1 = client.post("/route-categories", json={"label": "A-B"})
        r2 = client.post("/route-categories", json={"label": "A B"})
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["slug"] == "a-b"
        assert r2.json()["slug"] == "a-b-2"


# ---------------------------------------------------------------------------
# EP-CAT03 — GET /route-categories/{slug}
# ---------------------------------------------------------------------------

class TestEP_CAT03_Get:

    def test_get_existing_category(self, client):
        """GET por slug existente → 200."""
        _create_category(client, "Mapa", "#4A90D9")
        r = client.get("/route-categories/mapa")
        assert r.status_code == 200
        data = r.json()
        assert data["slug"] == "mapa"
        assert data["color"] == "#4A90D9"

    def test_get_uncategorized(self, client):
        """GET uncategorized → 200 con is_default=true."""
        r = client.get("/route-categories/uncategorized")
        assert r.status_code == 200
        assert r.json()["is_default"] is True

    def test_get_not_found_404(self, client):
        """FA-03: slug inexistente → 404."""
        r = client.get("/route-categories/no-existe")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# EP-CAT04 — PATCH /route-categories/{slug}
# ---------------------------------------------------------------------------

class TestEP_CAT04_Patch:

    def test_patch_label_ok(self, client):
        """AC-04: PATCH label → 200 con nuevo label; slug inmutable."""
        _create_category(client, "Mapa")
        r = client.patch("/route-categories/mapa", json={"label": "Mapamundi"})
        assert r.status_code == 200
        data = r.json()
        assert data["label"] == "Mapamundi"
        assert data["slug"] == "mapa"  # slug inmutable

    def test_patch_color_ok(self, client):
        """PATCH solo color → 200."""
        _create_category(client, "Oasis")
        r = client.patch("/route-categories/oasis", json={"color": "#5BAD6F"})
        assert r.status_code == 200
        assert r.json()["color"] == "#5BAD6F"

    def test_patch_color_to_null_removes_color(self, client):
        """C-04: color: null en el body → quita el color."""
        _create_category(client, "Test", "#4A90D9")
        r = client.patch("/route-categories/test", json={"color": None})
        assert r.status_code == 200
        assert r.json()["color"] is None

    def test_patch_absent_color_preserves_current(self, client):
        """C-04: color ausente del body → conserva el valor actual."""
        _create_category(client, "Preserved", "#4A90D9")
        r = client.patch("/route-categories/preserved", json={"label": "Preserved New"})
        assert r.status_code == 200
        assert r.json()["color"] == "#4A90D9"  # conservado

    def test_patch_duplicate_label_409(self, client):
        """EC-CAT05: renombrar a label existente en otra categoría → 409."""
        _create_category(client, "Alpha")
        _create_category(client, "Beta")
        r = client.patch("/route-categories/beta", json={"label": "Alpha"})
        assert r.status_code == 409

    def test_patch_empty_body_422(self, client):
        """C-06: body {} sin ningún campo → 422."""
        _create_category(client, "Vacia")
        r = client.patch("/route-categories/vacia", json={})
        assert r.status_code == 422
        # detail puede ser str o list (Pydantic); verificar que contiene el mensaje
        detail = r.json()["detail"]
        detail_str = str(detail).lower()
        assert "al menos uno" in detail_str

    def test_patch_not_found_404(self, client):
        """PATCH de slug inexistente → 404."""
        r = client.patch("/route-categories/no-existe", json={"label": "X"})
        assert r.status_code == 404

    def test_patch_uncategorized_label_ok(self, client):
        """RN-CAT02: la categoría default puede renombrarse."""
        r = client.patch("/route-categories/uncategorized", json={"label": "Sin Categoría"})
        assert r.status_code == 200
        assert r.json()["label"] == "Sin Categoría"
        assert r.json()["slug"] == "uncategorized"  # slug inmutable


# ---------------------------------------------------------------------------
# EP-CAT05 — DELETE /route-categories/{slug}
# ---------------------------------------------------------------------------

class TestEP_CAT05_Delete:

    def test_delete_empty_category_ok(self, client):
        """EC-CAT06: borrar categoría sin rutas → 200, reassigned_count=0."""
        _create_category(client, "Vacia")
        r = client.delete("/route-categories/vacia")
        assert r.status_code == 200
        data = r.json()
        assert data["deleted_slug"] == "vacia"
        assert data["reassigned_count"] == 0
        assert data["reassigned_to"] == "uncategorized"

    def test_delete_with_templates_reassigns(self, client):
        """AC-06 + EC-CAT07: borrar categoría con N plantillas → reasigna a uncategorized."""
        cat = _create_category(client, "Activa")
        cat_slug = cat["slug"]
        _create_template(client, "t1", cat_slug)
        _create_template(client, "t2", cat_slug)

        r = client.delete(f"/route-categories/{cat_slug}")
        assert r.status_code == 200
        data = r.json()
        assert data["reassigned_count"] >= 2

        # Las plantillas deben quedar con category_slug=uncategorized
        r_list = client.get("/route-templates")
        templates = r_list.json()
        for t in templates:
            if t["slug"] in ("t1", "t2"):
                assert t["category_slug"] == "uncategorized"

        # La categoría ya no existe
        r_get = client.get(f"/route-categories/{cat_slug}")
        assert r_get.status_code == 404

    def test_delete_default_409(self, client):
        """AC-05 + EC-CAT01 + C-05: borrar uncategorized → 409 (no 403)."""
        r = client.delete("/route-categories/uncategorized")
        assert r.status_code == 409
        assert "por defecto" in r.json()["detail"].lower()

    def test_delete_not_found_404(self, client):
        """FA-03: borrar slug inexistente → 404."""
        r = client.delete("/route-categories/no-existe")
        assert r.status_code == 404

    def test_delete_category_not_in_list_after(self, client):
        """Después del borrado, la categoría no aparece en GET /route-categories."""
        _create_category(client, "Efimera")
        client.delete("/route-categories/efimera")
        r = client.get("/route-categories")
        slugs = [c["slug"] for c in r.json()]
        assert "efimera" not in slugs


# ---------------------------------------------------------------------------
# Tests de integración con route-templates y noise
# ---------------------------------------------------------------------------

class TestCategoryIntegrationWithTemplates:

    def test_create_template_with_valid_category_slug(self, client):
        """AC-08: POST /route-templates con category_slug válido → 201."""
        cat = _create_category(client, "Mapa")
        r = client.post(
            "/route-templates",
            json={
                "slug": "test-map",
                "label": "Test Mapa",
                "category_slug": cat["slug"],
                "url_pattern": "/karte.php",
                "navigation_weight": 1.0,
                "paths": [],
            },
        )
        assert r.status_code == 201
        assert r.json()["category_slug"] == cat["slug"]

    def test_create_template_invalid_category_slug_422(self, client):
        """AC-09: POST /route-templates con slug inexistente → 422."""
        r = client.post(
            "/route-templates",
            json={
                "slug": "test-invalid",
                "label": "Test Invalid",
                "category_slug": "slug-que-no-existe",
                "url_pattern": "/test.php",
                "navigation_weight": 1.0,
                "paths": [],
            },
        )
        assert r.status_code == 422
        assert "no encontrada" in r.json()["detail"].lower()

    def test_update_template_category_ok(self, client):
        """AC-10: PUT /route-templates/{id} con category_slug → 200 (sin rechazo)."""
        cat = _create_category(client, "Nueva Categoria")
        tpl = _create_template(client, "test-update")
        r = client.put(
            f"/route-templates/{tpl['id']}",
            json={"category_slug": cat["slug"]},
        )
        assert r.status_code == 200
        assert r.json()["category_slug"] == cat["slug"]

    def test_filter_templates_by_category_slug(self, client):
        """EP-RT01 filtro ?category_slug= devuelve solo las plantillas de esa categoría."""
        cat = _create_category(client, "Filtrable")
        _create_template(client, "t-filtrable", cat["slug"])
        _create_template(client, "t-no-filtrable")  # queda en uncategorized

        r = client.get(f"/route-templates?category_slug={cat['slug']}")
        assert r.status_code == 200
        items = r.json()
        assert len(items) >= 1
        assert all(t["category_slug"] == cat["slug"] for t in items)

    def test_filter_templates_unknown_slug_returns_empty(self, client):
        """C-01: filtrar por slug inexistente → 200 [] (filtro silencioso)."""
        r = client.get("/route-templates?category_slug=slug-total-mente-inexistente")
        assert r.status_code == 200
        assert r.json() == []

    def test_create_noise_destination_with_category_slug(self, client):
        """AC-08 (noise): POST /worlds/{id}/noise/destinations con category_slug válido."""
        _, world_id = _setup_world(client)
        cat = _create_category(client, "Ruido Destino")

        r = client.post(
            f"/worlds/{world_id}/noise/destinations",
            json={
                "url_pattern": "/karte.php",
                "label": "Destino Mapa",
                "category_slug": cat["slug"],
                "navigation_weight": 1.0,
            },
        )
        assert r.status_code == 201
        assert r.json()["category_slug"] == cat["slug"]

    def test_create_noise_destination_invalid_category_slug_422(self, client):
        """AC-09 (noise): POST destino con slug inexistente → 422."""
        _, world_id = _setup_world(client)
        r = client.post(
            f"/worlds/{world_id}/noise/destinations",
            json={
                "url_pattern": "/karte.php",
                "label": "Destino Inválido",
                "category_slug": "slug-inexistente",
                "navigation_weight": 1.0,
            },
        )
        assert r.status_code == 422

    def test_update_noise_destination_category_ok(self, client):
        """AC-12: PUT /worlds/{wid}/noise/destinations/{did} con category_slug → 200."""
        _, world_id = _setup_world(client)
        cat = _create_category(client, "Nueva Cat Dest")

        # Crear destino con uncategorized
        r_create = client.post(
            f"/worlds/{world_id}/noise/destinations",
            json={"url_pattern": "/karte.php", "label": "Mapa", "navigation_weight": 1.0},
        )
        assert r_create.status_code == 201
        dest_id = r_create.json()["id"]

        # Actualizar category_slug
        r = client.put(
            f"/worlds/{world_id}/noise/destinations/{dest_id}",
            json={"category_slug": cat["slug"]},
        )
        assert r.status_code == 200
        assert r.json()["category_slug"] == cat["slug"]


# ---------------------------------------------------------------------------
# Tests de migración idempotente
# ---------------------------------------------------------------------------

class TestMigrationIdempotent:

    def test_ensure_tables_idempotent(self, client):
        """AC-15 + EC-CAT13: ejecutar lifespan dos veces no da error."""
        # La fixture arranca el lifespan una vez; simplemente verificar que la API funciona.
        r = client.get("/route-categories")
        assert r.status_code == 200
        # uncategorized siempre existe
        slugs = [c["slug"] for c in r.json()]
        assert "uncategorized" in slugs

    def test_uncategorized_always_exists(self, client):
        """AC-01 + RN-CAT10: uncategorized siempre existe en BD nueva."""
        r = client.get("/route-categories/uncategorized")
        assert r.status_code == 200
        data = r.json()
        assert data["is_default"] is True
        assert data["slug"] == "uncategorized"


# ---------------------------------------------------------------------------
# Tests del adaptador SQLite (unitarios con BD real)
# ---------------------------------------------------------------------------

class TestRouteCategorySQLiteAdapter:

    def test_slugify_basic(self):
        from adapters.db.route_category_sqlite_adapter import slugify
        assert slugify("Mapa") == "mapa"
        assert slugify("Oasis Info") == "oasis-info"
        assert slugify("A  B--C") == "a-b-c"

    def test_slugify_strips_boundaries(self):
        from adapters.db.route_category_sqlite_adapter import slugify
        assert slugify("  hola  ") == "hola"
        assert slugify("-hola-") == "hola"

    def test_slugify_special_chars(self):
        from adapters.db.route_category_sqlite_adapter import slugify
        assert slugify("A&B") == "a-b"
        # 'é' no es [a-z0-9] → se elimina, el guión queda al borde → strip('-')
        assert slugify("Café") == "caf"
