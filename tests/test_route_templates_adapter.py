"""
Tests de integración para RouteTemplateSQLiteAdapter y las extensiones de
NoiseSQLiteAdapter relacionadas con el catálogo de plantillas.

Cubre:
  - CRUD de plantillas (TI-RT01..TI-RT10).
  - Migración M-RT01 idempotente (template_id en noise_destinations).
  - Métodos de lookup nuevos: find_destination_by_url, find_destination_by_template.
  - Retrocompatibilidad de create_destination con y sin template_id.
  - Seed idempotente por slug (TI-RT22..TI-RT23).

Spec route-templates-developer-portal.md §12.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import pytest

import aiosqlite

from adapters.db.noise_sqlite_adapter import NoiseSQLiteAdapter
from adapters.db.route_template_sqlite_adapter import (
    RouteTemplateSQLiteAdapter,
    seed_route_templates,
)
from core.entities.noise import (
    NavigationStep,
    NoiseAction,
    RouteTemplate,
    RouteTemplatePath,
)


# ---------------------------------------------------------------------------
# Helpers de fixtures
# ---------------------------------------------------------------------------

async def _setup_db(db_path: str):
    """Crea conexión, asegura tablas base (accounts+worlds) y tablas de noise+plantillas."""
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")

    # Tablas mínimas que noise_destinations necesita por FK
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            username TEXT NOT NULL,
            password TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS worlds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            server TEXT NOT NULL,
            tribe TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS villages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            world_id INTEGER NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
            data_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            x INTEGER NOT NULL DEFAULT 0,
            y INTEGER NOT NULL DEFAULT 0,
            UNIQUE(world_id, data_id)
        )
    """)
    await conn.commit()

    noise_adapter = NoiseSQLiteAdapter(conn)
    await noise_adapter.ensure_tables()

    rt_adapter = RouteTemplateSQLiteAdapter(conn)
    await rt_adapter.ensure_tables()

    return conn, noise_adapter, rt_adapter


async def _insert_world(conn: aiosqlite.Connection, server: str = "https://ts1.travian.es/") -> int:
    """Inserta una cuenta y un mundo de prueba. Devuelve world_id."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    cursor = await conn.execute(
        "INSERT INTO accounts (email, username, password, created_at) VALUES (?,?,?,?)",
        ("test@example.com", "testbot", "hashed", now),
    )
    account_id = cursor.lastrowid
    cursor = await conn.execute(
        "INSERT INTO worlds (account_id, server, tribe, created_at) VALUES (?,?,?,?)",
        (account_id, server, "romans", now),
    )
    await conn.commit()
    return cursor.lastrowid


def _make_template(
    slug: str = "test-template",
    label: str = "Test Template",
    category_slug: str = "uncategorized",
    url_pattern: str = "/karte.php",
    navigation_weight: float = 1.0,
    with_path: bool = False,
) -> RouteTemplate:
    paths = []
    if with_path:
        step = NavigationStep(
            id=None,
            path_id=None,
            step_order=0,
            action=NoiseAction.WAIT_FOR_SELECTOR,
            selector="#map",
            delay_min_ms=500,
            delay_max_ms=900,
        )
        path = RouteTemplatePath(
            id=None,
            template_id=None,
            origin="ANY",
            label="Desde cualquier aldea",
            steps=[step],
        )
        paths = [path]
    return RouteTemplate(
        id=None,
        slug=slug,
        label=label,
        category_slug=category_slug,
        url_pattern=url_pattern,
        navigation_weight=navigation_weight,
        paths=paths,
    )


# ---------------------------------------------------------------------------
# TI-RT01 — create_template con datos válidos
# ---------------------------------------------------------------------------

def test_TI_RT01_create_template(tmp_path):
    """create_template devuelve plantilla con id asignado."""
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            tpl = await rt.create_template(_make_template())
            assert tpl.id is not None
            assert tpl.slug == "test-template"
            assert tpl.created_at is not None
            assert tpl.updated_at is not None
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# TI-RT02 — slug duplicado → ValueError
# ---------------------------------------------------------------------------

def test_TI_RT02_duplicate_slug_raises(tmp_path):
    """create_template con slug duplicado lanza ValueError (CA-RT04)."""
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            await rt.create_template(_make_template(slug="dup-slug"))
            with pytest.raises(ValueError, match="slug"):
                await rt.create_template(_make_template(slug="dup-slug"))
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# TI-RT03 — list_templates devuelve todas las plantillas
# ---------------------------------------------------------------------------

def test_TI_RT03_list_templates(tmp_path):
    """list_templates devuelve todas las plantillas insertadas (CA-RT05)."""
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            await rt.create_template(_make_template(slug="t1"))
            await rt.create_template(_make_template(slug="t2", category_slug="building-view", url_pattern="/build.php?gid=13"))
            templates = await rt.list_templates()
            assert len(templates) == 2
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# TI-RT04 — list_templates con filtro por category
# ---------------------------------------------------------------------------

def test_TI_RT04_list_templates_by_category(tmp_path):
    """list_templates con filtro category=MAP devuelve solo las de MAP (CA-RT06)."""
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            await rt.create_template(_make_template(slug="map1", category_slug="map"))
            await rt.create_template(_make_template(slug="map2", category_slug="map", url_pattern="/karte2.php"))
            await rt.create_template(_make_template(slug="bv1", category_slug="building-view", url_pattern="/build.php?gid=13"))
            result = await rt.list_templates(category_slug="map")
            assert len(result) == 2
            assert all(t.category_slug == "map" for t in result)
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# TI-RT05 — get_template existente con paths y steps
# ---------------------------------------------------------------------------

def test_TI_RT05_get_template_with_paths(tmp_path):
    """get_template devuelve la plantilla con paths y steps anidados."""
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            created = await rt.create_template(_make_template(with_path=True))
            fetched = await rt.get_template(created.id)
            assert fetched is not None
            assert fetched.slug == "test-template"
            assert len(fetched.paths) == 1
            assert len(fetched.paths[0].steps) == 1
            assert fetched.paths[0].steps[0].selector == "#map"
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# TI-RT06 — get_template con ID inexistente → None (404)
# ---------------------------------------------------------------------------

def test_TI_RT06_get_template_not_found(tmp_path):
    """get_template con ID inexistente devuelve None."""
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            result = await rt.get_template(9999)
            assert result is None
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# TI-RT07 — update_template con label nuevo
# ---------------------------------------------------------------------------

def test_TI_RT07_update_template_label(tmp_path):
    """update_template actualiza el label (CA-RT07 parcial)."""
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            created = await rt.create_template(_make_template())
            updated = await rt.update_template(created.id, label="Nuevo label")
            assert updated.label == "Nuevo label"
            assert updated.slug == "test-template"  # slug no cambia
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# TI-RT08 — update_template con slug → el spec dice 422; aquí el adaptador
# no valida eso (lo hace el handler). Verificamos que slug es inmutable:
# no existe un método para cambiarlo.
# ---------------------------------------------------------------------------

def test_TI_RT08_slug_immutable_via_update(tmp_path):
    """update_template no tiene parámetro slug — es inmutable a nivel de adaptador."""
    import inspect
    sig = inspect.signature(RouteTemplateSQLiteAdapter.update_template)
    assert "slug" not in sig.parameters


# ---------------------------------------------------------------------------
# TI-RT09 — delete_template sin instancias → idempotente
# ---------------------------------------------------------------------------

def test_TI_RT09_delete_template(tmp_path):
    """delete_template borra la plantilla; get_template posterior devuelve None."""
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            created = await rt.create_template(_make_template())
            await rt.delete_template(created.id)
            result = await rt.get_template(created.id)
            assert result is None
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# TI-RT10 — delete_template con instancias clonadas → template_id=NULL
# ---------------------------------------------------------------------------

def test_TI_RT10_delete_template_orphans_clones(tmp_path):
    """Borrar plantilla pone template_id=NULL en los noise_destinations clonados (RN-RT06, CA-RT08)."""
    async def run():
        conn, noise, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            world_id = await _insert_world(conn)
            tpl = await rt.create_template(_make_template())

            # Crear destino en el mundo con template_id = tpl.id
            dest = await noise.create_destination(
                world_id=world_id,
                url_pattern="/karte.php",
                label="Mapa",
                category_slug="uncategorized",
                frequency_weight=1.0,
                is_safe=True,
                template_id=tpl.id,
            )
            assert dest.template_id == tpl.id

            # Borrar la plantilla
            await rt.delete_template(tpl.id)

            # El destino sigue vivo pero con template_id=NULL
            fetched = await noise.get_destination(dest.id)
            assert fetched is not None
            assert fetched.template_id is None
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# Migración M-RT01 — idempotente
# ---------------------------------------------------------------------------

def test_migration_M_RT01_idempotent(tmp_path):
    """ensure_tables() en NoiseSQLiteAdapter es idempotente: llamarlo dos veces no falla."""
    async def run():
        conn, noise, _ = await _setup_db(str(tmp_path / "test.db"))
        try:
            # Segunda llamada debe ser idempotente
            await noise.ensure_tables()
            # Verificar que la columna template_id existe
            cursor = await conn.execute("PRAGMA table_info(noise_destinations)")
            cols = {row[1] for row in await cursor.fetchall()}
            assert "template_id" in cols
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# find_destination_by_url — lookup por url_pattern
# ---------------------------------------------------------------------------

def test_find_destination_by_url_found(tmp_path):
    """find_destination_by_url devuelve el destino si existe."""
    async def run():
        conn, noise, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            world_id = await _insert_world(conn)
            await noise.create_destination(
                world_id=world_id,
                url_pattern="/karte.php",
                label="Mapa",
                category_slug="uncategorized",
                frequency_weight=1.0,
            )
            result = await noise.find_destination_by_url(world_id, "/karte.php")
            assert result is not None
            assert result.url_pattern == "/karte.php"
        finally:
            await conn.close()
    asyncio.run(run())


def test_find_destination_by_url_not_found(tmp_path):
    """find_destination_by_url devuelve None si no existe."""
    async def run():
        conn, noise, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            world_id = await _insert_world(conn)
            result = await noise.find_destination_by_url(world_id, "/karte.php")
            assert result is None
        finally:
            await conn.close()
    asyncio.run(run())


def test_find_destination_by_url_cross_world(tmp_path):
    """find_destination_by_url no devuelve resultados de otro mundo."""
    async def run():
        conn, noise, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            world_id_1 = await _insert_world(conn, server="https://ts1.travian.es/")
            # Insertar otro mundo
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()
            cursor = await conn.execute(
                "INSERT INTO accounts (email, username, password, created_at) VALUES (?,?,?,?)",
                ("other@example.com", "other", "hashed", now),
            )
            account_id2 = cursor.lastrowid
            cursor = await conn.execute(
                "INSERT INTO worlds (account_id, server, tribe, created_at) VALUES (?,?,?,?)",
                (account_id2, "https://ts2.travian.es/", "romans", now),
            )
            await conn.commit()
            world_id_2 = cursor.lastrowid

            await noise.create_destination(
                world_id=world_id_1,
                url_pattern="/karte.php",
                label="Mapa",
                category_slug="uncategorized",
                frequency_weight=1.0,
            )
            # Buscar en el segundo mundo — no debe encontrar nada
            result = await noise.find_destination_by_url(world_id_2, "/karte.php")
            assert result is None
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# find_destination_by_template — lookup por template_id
# ---------------------------------------------------------------------------

def test_find_destination_by_template_found(tmp_path):
    """find_destination_by_template devuelve el destino clonado si existe."""
    async def run():
        conn, noise, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            world_id = await _insert_world(conn)
            tpl = await rt.create_template(_make_template())
            await noise.create_destination(
                world_id=world_id,
                url_pattern="/karte.php",
                label="Mapa clonado",
                category_slug="uncategorized",
                frequency_weight=1.0,
                template_id=tpl.id,
            )
            result = await noise.find_destination_by_template(world_id, tpl.id)
            assert result is not None
            assert result.template_id == tpl.id
            assert result.url_pattern == "/karte.php"
        finally:
            await conn.close()
    asyncio.run(run())


def test_find_destination_by_template_not_found(tmp_path):
    """find_destination_by_template devuelve None si no hay instancia."""
    async def run():
        conn, noise, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            world_id = await _insert_world(conn)
            result = await noise.find_destination_by_template(world_id, 9999)
            assert result is None
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# Retrocompatibilidad de create_destination sin template_id
# ---------------------------------------------------------------------------

def test_create_destination_without_template_id(tmp_path):
    """create_destination sin template_id (call-site existente) produce template_id=None."""
    async def run():
        conn, noise, _ = await _setup_db(str(tmp_path / "test.db"))
        try:
            world_id = await _insert_world(conn)
            dest = await noise.create_destination(
                world_id=world_id,
                url_pattern="/karte.php",
                label="Mapa",
                category_slug="uncategorized",
                frequency_weight=1.0,
            )
            assert dest.template_id is None
        finally:
            await conn.close()
    asyncio.run(run())


def test_create_destination_with_template_id(tmp_path):
    """create_destination con template_id propaga el valor correctamente (M-RT01)."""
    async def run():
        conn, noise, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            world_id = await _insert_world(conn)
            tpl = await rt.create_template(_make_template())
            dest = await noise.create_destination(
                world_id=world_id,
                url_pattern="/karte.php",
                label="Mapa clonado",
                category_slug="uncategorized",
                frequency_weight=1.0,
                template_id=tpl.id,
            )
            assert dest.template_id == tpl.id
            # Verificar en BD directamente
            fetched = await noise.get_destination(dest.id)
            assert fetched.template_id == tpl.id
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# TI-RT22 — Seed en BD vacía
# ---------------------------------------------------------------------------

def test_TI_RT22_seed_loads_templates(tmp_path):
    """seed_route_templates carga al menos 18 plantillas en una BD vacía (CA-RT19)."""
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            inserted = await seed_route_templates(rt)
            assert inserted >= 18, f"Solo se insertaron {inserted} plantillas"
            all_templates = await rt.list_templates()
            assert len(all_templates) >= 18
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# TI-RT23 — Seed idempotente (re-ejecutado no duplica)
# ---------------------------------------------------------------------------

def test_TI_RT23_seed_idempotent(tmp_path):
    """seed_route_templates re-ejecutado no duplica plantillas (EC-RT10, CA-RT20)."""
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            first_run = await seed_route_templates(rt)
            second_run = await seed_route_templates(rt)
            assert second_run == 0, "El segundo seed no debe insertar nada"
            all_templates = await rt.list_templates()
            assert len(all_templates) == first_run
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# count_paths_for_template
# ---------------------------------------------------------------------------

def test_count_paths_for_template(tmp_path):
    """count_paths_for_template devuelve el número correcto de paths."""
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            tpl = await rt.create_template(_make_template(with_path=True))
            count = await rt.count_paths_for_template(tpl.id)
            assert count == 1
            # Plantilla sin paths
            tpl2 = await rt.create_template(_make_template(slug="no-paths"))
            assert await rt.count_paths_for_template(tpl2.id) == 0
            # ID inexistente
            assert await rt.count_paths_for_template(9999) == 0
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# get_template_by_slug
# ---------------------------------------------------------------------------

def test_get_template_by_slug(tmp_path):
    """get_template_by_slug devuelve la plantilla correcta o None."""
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            await rt.create_template(_make_template(slug="my-slug"))
            found = await rt.get_template_by_slug("my-slug")
            assert found is not None
            assert found.slug == "my-slug"
            not_found = await rt.get_template_by_slug("nonexistent")
            assert not_found is None
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# update_template — reemplazo atómico de paths
# ---------------------------------------------------------------------------

def test_update_template_replace_paths(tmp_path):
    """update_template con paths=[...] reemplaza atómicamente los paths existentes."""
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            tpl = await rt.create_template(_make_template(with_path=True))
            assert len(tpl.paths) == 1

            # Crear nuevos paths para reemplazar
            new_step = NavigationStep(
                id=None, path_id=None, step_order=0,
                action=NoiseAction.HOVER, selector=".new-selector",
                delay_min_ms=500, delay_max_ms=900,
            )
            new_path = RouteTemplatePath(
                id=None, template_id=None,
                origin="DORF1", label="Nuevo path",
                steps=[new_step],
            )
            updated = await rt.update_template(tpl.id, paths=[new_path])
            assert len(updated.paths) == 1
            assert updated.paths[0].origin == "DORF1"
            assert updated.paths[0].steps[0].selector == ".new-selector"
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# list_paths_for_template
# ---------------------------------------------------------------------------

def test_list_paths_for_template(tmp_path):
    """list_paths_for_template devuelve los paths con steps de la plantilla."""
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            tpl = await rt.create_template(_make_template(with_path=True))
            paths = await rt.list_paths_for_template(tpl.id)
            assert len(paths) == 1
            assert paths[0].template_id == tpl.id
            assert len(paths[0].steps) == 1
        finally:
            await conn.close()
    asyncio.run(run())


def test_list_paths_for_nonexistent_template(tmp_path):
    """list_paths_for_template devuelve [] para template_id inexistente."""
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            paths = await rt.list_paths_for_template(9999)
            assert paths == []
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# seed_templates (método del puerto)
# ---------------------------------------------------------------------------

def test_seed_templates_method(tmp_path):
    """seed_templates inserta solo las plantillas que no existen (idempotente)."""
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            tpl1 = _make_template(slug="s1")
            tpl2 = _make_template(slug="s2", url_pattern="/dorf1.php")

            first = await rt.seed_templates([tpl1, tpl2])
            assert first == 2

            # Segunda llamada con los mismos slugs → 0 insertados
            second = await rt.seed_templates([tpl1, tpl2])
            assert second == 0

            # Mezcla de existente y nuevo
            tpl3 = _make_template(slug="s3", url_pattern="/dorf2.php")
            mixed = await rt.seed_templates([tpl1, tpl3])
            assert mixed == 1
        finally:
            await conn.close()
    asyncio.run(run())
