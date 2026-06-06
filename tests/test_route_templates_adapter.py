"""
Tests de integración para RouteTemplateSQLiteAdapter y las extensiones de
NoiseSQLiteAdapter relacionadas con el catálogo de plantillas.

Cubre:
  - CRUD de plantillas (TI-RT01..TI-RT10).
  - Migración M-RT01 idempotente (template_id en noise_destinations).
  - Migraciones M-RT02 (origin_template_id) y M-RT03 (DROP navigation_weight).
  - ON DELETE SET NULL para origin_template_id (CA-V2-05).
  - Métodos de lookup: find_destination_by_url, find_destination_by_template.
  - Retrocompatibilidad de create_destination con y sin template_id.
  - Seed idempotente por slug con 2 pasadas (TI-RT22..TI-RT23).
  - get_templates_by_origin (v2).

Spec route-templates-developer-portal.md §12, §v2.12.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
import pytest

from adapters.db.noise_sqlite_adapter import (
    NoiseSQLiteAdapter,
    _migrate_noise_destinations_free_category,
)
from adapters.db.route_template_sqlite_adapter import (
    RouteTemplateSQLiteAdapter,
    _migrate_m_rt04,
    seed_route_templates,
)
from core.entities.noise import (
    NavigationStep,
    NoiseAction,
    NoiseCategory,
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


async def _insert_world(conn: aiosqlite.Connection, server: str = "https://ts1.travian.es/", email: str = "test@example.com") -> int:
    """Inserta una cuenta y un mundo de prueba. Devuelve world_id."""
    now = datetime.now(timezone.utc).isoformat()
    cursor = await conn.execute(
        "INSERT INTO accounts (email, username, password, created_at) VALUES (?,?,?,?)",
        (email, "testbot", "hashed", now),
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
    category: "NoiseCategory | str" = NoiseCategory.MAP,
    url_pattern: str = "/karte.php",
    with_path: bool = False,
    origin_template_id: int | None = None,
) -> RouteTemplate:
    """
    Construye una RouteTemplate válida (v2: sin navigation_weight).
    El campo navigation_weight fue eliminado en v2 rev.2.
    """
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
        category=category,
        url_pattern=url_pattern,
        origin_template_id=origin_template_id,
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
            assert tpl.origin_template_id is None  # v2
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
            await rt.create_template(_make_template(slug="t2", category=NoiseCategory.BUILDING_VIEW, url_pattern="/build.php?gid=13"))
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
            await rt.create_template(_make_template(slug="map1", category=NoiseCategory.MAP))
            await rt.create_template(_make_template(slug="map2", category=NoiseCategory.MAP, url_pattern="/karte2.php"))
            await rt.create_template(_make_template(slug="bv1", category=NoiseCategory.BUILDING_VIEW, url_pattern="/build.php?gid=13"))
            result = await rt.list_templates(category=NoiseCategory.MAP)
            assert len(result) == 2
            # category ahora es str ("MAP"), no el enum NoiseCategory.MAP
            assert all(t.category == "MAP" for t in result)
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
# TI-RT06 — get_template con ID inexistente → None
# ---------------------------------------------------------------------------

def test_TI_RT06_get_template_not_found(tmp_path):
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
    """update_template actualiza el label."""
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
# TI-RT08 — update_template: slug no tiene parámetro (inmutable)
# ---------------------------------------------------------------------------

def test_TI_RT08_slug_immutable_via_update(tmp_path):
    """update_template no tiene parámetro slug — es inmutable a nivel de adaptador."""
    import inspect
    sig = inspect.signature(RouteTemplateSQLiteAdapter.update_template)
    assert "slug" not in sig.parameters


# ---------------------------------------------------------------------------
# TI-RT09 — delete_template sin instancias
# ---------------------------------------------------------------------------

def test_TI_RT09_delete_template(tmp_path):
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
# TI-RT10 — delete_template con instancias clonadas → template_id=NULL (CA-RT08)
# ---------------------------------------------------------------------------

def test_TI_RT10_delete_template_orphans_clones(tmp_path):
    """Borrar plantilla pone template_id=NULL en los noise_destinations clonados (RN-RT06)."""
    async def run():
        conn, noise, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            world_id = await _insert_world(conn)
            tpl = await rt.create_template(_make_template())

            dest = await noise.create_destination(
                world_id=world_id,
                url_pattern="/karte.php",
                label="Mapa",
                category=NoiseCategory.MAP,
                frequency_weight=1.0,
                is_safe=True,
                template_id=tpl.id,
            )
            assert dest.template_id == tpl.id

            await rt.delete_template(tpl.id)

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
    """ensure_tables() es idempotente: llamarlo dos veces no falla."""
    async def run():
        conn, noise, _ = await _setup_db(str(tmp_path / "test.db"))
        try:
            await noise.ensure_tables()
            cursor = await conn.execute("PRAGMA table_info(noise_destinations)")
            cols = {row[1] for row in await cursor.fetchall()}
            assert "template_id" in cols
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# Migración M-RT02 — origin_template_id añadida a route_templates
# ---------------------------------------------------------------------------

def test_migration_M_RT02_origin_column(tmp_path):
    """M-RT02: columna origin_template_id existe en route_templates tras ensure_tables."""
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            cursor = await conn.execute("PRAGMA table_info(route_templates)")
            cols = {row[1] for row in await cursor.fetchall()}
            assert "origin_template_id" in cols, (
                "M-RT02 no añadió origin_template_id a route_templates"
            )
        finally:
            await conn.close()
    asyncio.run(run())


def test_migration_M_RT02_idempotent(tmp_path):
    """M-RT02 es idempotente: ensure_tables() dos veces no falla."""
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            await rt.ensure_tables()  # segunda llamada
            cursor = await conn.execute("PRAGMA table_info(route_templates)")
            cols = {row[1] for row in await cursor.fetchall()}
            assert "origin_template_id" in cols
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# Migración M-RT03 — navigation_weight eliminada de route_templates
# ---------------------------------------------------------------------------

def test_migration_M_RT03_no_navigation_weight(tmp_path):
    """M-RT03: navigation_weight NO existe en route_templates tras ensure_tables."""
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            cursor = await conn.execute("PRAGMA table_info(route_templates)")
            cols = {row[1] for row in await cursor.fetchall()}
            assert "navigation_weight" not in cols, (
                "M-RT03 debería haber eliminado navigation_weight de route_templates"
            )
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# origin_template_id — persiste y se lee correctamente
# ---------------------------------------------------------------------------

def test_origin_template_id_persists(tmp_path):
    """
    origin_template_id se persiste en BD y se devuelve al leer la plantilla.
    Spec §v2.2.3.
    """
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            # Crear plantilla raíz
            root = await rt.create_template(_make_template(slug="statistics", url_pattern="/statistics"))
            assert root.origin_template_id is None

            # Crear plantilla hija
            child = await rt.create_template(_make_template(
                slug="top10-alianzas",
                url_pattern="/statistics/alliances",
                origin_template_id=root.id,
            ))
            assert child.origin_template_id == root.id

            # Leer de BD y verificar persistencia
            fetched = await rt.get_template(child.id)
            assert fetched is not None
            assert fetched.origin_template_id == root.id
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# ON DELETE SET NULL en origin_template_id (CA-V2-05, EC-V2-03)
# ---------------------------------------------------------------------------

def test_delete_origin_sets_null_in_children(tmp_path):
    """
    CA-V2-05: Borrar plantilla origen pone origin_template_id=NULL en las hijas.
    EC-V2-03: Las hijas pasan a ser raíces libres (no se destruyen).
    Spec §v2.2.1, §EC-V2-03.
    """
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            root = await rt.create_template(_make_template(slug="statistics", url_pattern="/statistics"))
            child = await rt.create_template(_make_template(
                slug="top10-alianzas",
                url_pattern="/statistics/alliances",
                origin_template_id=root.id,
            ))
            assert child.origin_template_id == root.id

            # Borrar la raíz
            await rt.delete_template(root.id)

            # La hija sigue existiendo pero con origin_template_id=NULL
            fetched_child = await rt.get_template(child.id)
            assert fetched_child is not None, "La plantilla hija debe seguir existiendo"
            assert fetched_child.origin_template_id is None, (
                "ON DELETE SET NULL debe poner origin_template_id=NULL en las hijas"
            )
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# get_templates_by_origin (v2)
# ---------------------------------------------------------------------------

def test_get_templates_by_origin(tmp_path):
    """get_templates_by_origin devuelve las plantillas hijas del origen dado."""
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            root = await rt.create_template(_make_template(slug="statistics", url_pattern="/statistics"))
            child1 = await rt.create_template(_make_template(
                slug="top10-alianzas",
                url_pattern="/statistics/alliances",
                origin_template_id=root.id,
            ))
            child2 = await rt.create_template(_make_template(
                slug="top10-jugadores",
                url_pattern="/statistics/players",
                origin_template_id=root.id,
            ))

            hijas = await rt.get_templates_by_origin(root.id)
            assert len(hijas) == 2
            ids = {t.id for t in hijas}
            assert child1.id in ids
            assert child2.id in ids
        finally:
            await conn.close()
    asyncio.run(run())


def test_get_templates_by_origin_none(tmp_path):
    """get_templates_by_origin devuelve [] si no hay hijas."""
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            root = await rt.create_template(_make_template(slug="statistics", url_pattern="/statistics"))
            result = await rt.get_templates_by_origin(root.id)
            assert result == []
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# update_template con origin_template_id editable (v2)
# ---------------------------------------------------------------------------

def test_update_template_origin_template_id(tmp_path):
    """update_template puede reasignar origin_template_id (v2: campo mutable)."""
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            root = await rt.create_template(_make_template(slug="root-a", url_pattern="/root"))
            child = await rt.create_template(_make_template(
                slug="child-a",
                url_pattern="/child",
                origin_template_id=root.id,
            ))
            assert child.origin_template_id == root.id

            # Quitar origen (pasa a raíz libre)
            updated = await rt.update_template(child.id, origin_template_id=None)
            assert updated.origin_template_id is None
        finally:
            await conn.close()
    asyncio.run(run())


def test_update_template_origin_ellipsis_no_change(tmp_path):
    """update_template con origin_template_id=Ellipsis (default) no cambia el valor."""
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            root = await rt.create_template(_make_template(slug="root-b", url_pattern="/root2"))
            child = await rt.create_template(_make_template(
                slug="child-b",
                url_pattern="/child2",
                origin_template_id=root.id,
            ))
            # update_template sin pasar origin_template_id → no debe cambiar
            updated = await rt.update_template(child.id, label="Nuevo label")
            assert updated.label == "Nuevo label"
            assert updated.origin_template_id == root.id  # sin cambiar
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# Seed con BD vacía: funciona con seed vacío []
# ---------------------------------------------------------------------------

def test_seed_empty_json_ok(tmp_path, monkeypatch):
    """
    seed_route_templates con seeds/route_templates.json vacío ([]) devuelve 0
    y no lanza excepción.
    """
    async def run():
        import json
        from pathlib import Path

        # Crear un seed vacío temporal
        seed_path = tmp_path / "route_templates.json"
        seed_path.write_text("[]", encoding="utf-8")

        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            # Monkeypatching: seed_route_templates usa la ruta relativa al fichero.
            # Usamos el método seed_templates del adaptador con lista vacía.
            inserted = await rt.seed_templates([])
            assert inserted == 0
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# TI-RT22 — Seed en BD vacía (CA-RT19)
# ---------------------------------------------------------------------------

def test_TI_RT22_seed_loads_templates(tmp_path):
    """
    seed_route_templates carga las plantillas del seed (CA-RT19).
    Si el seed está vacío ([]) devuelve 0 sin error.
    """
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            inserted = await seed_route_templates(rt)
            # El seed actual es [] — debe devolver 0 sin error
            assert inserted >= 0
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# TI-RT23 — Seed idempotente (CA-RT20)
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
# find_destination_by_url
# ---------------------------------------------------------------------------

def test_find_destination_by_url_found(tmp_path):
    async def run():
        conn, noise, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            world_id = await _insert_world(conn)
            await noise.create_destination(
                world_id=world_id,
                url_pattern="/karte.php",
                label="Mapa",
                category=NoiseCategory.MAP,
                frequency_weight=1.0,
            )
            result = await noise.find_destination_by_url(world_id, "/karte.php")
            assert result is not None
            assert result.url_pattern == "/karte.php"
        finally:
            await conn.close()
    asyncio.run(run())


def test_find_destination_by_url_not_found(tmp_path):
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
                category=NoiseCategory.MAP,
                frequency_weight=1.0,
            )
            result = await noise.find_destination_by_url(world_id_2, "/karte.php")
            assert result is None
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# find_destination_by_template
# ---------------------------------------------------------------------------

def test_find_destination_by_template_found(tmp_path):
    async def run():
        conn, noise, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            world_id = await _insert_world(conn)
            tpl = await rt.create_template(_make_template())
            await noise.create_destination(
                world_id=world_id,
                url_pattern="/karte.php",
                label="Mapa clonado",
                category=NoiseCategory.MAP,
                frequency_weight=1.0,
                template_id=tpl.id,
            )
            result = await noise.find_destination_by_template(world_id, tpl.id)
            assert result is not None
            assert result.template_id == tpl.id
        finally:
            await conn.close()
    asyncio.run(run())


def test_find_destination_by_template_not_found(tmp_path):
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
# Retrocompatibilidad create_destination
# ---------------------------------------------------------------------------

def test_create_destination_without_template_id(tmp_path):
    async def run():
        conn, noise, _ = await _setup_db(str(tmp_path / "test.db"))
        try:
            world_id = await _insert_world(conn)
            dest = await noise.create_destination(
                world_id=world_id,
                url_pattern="/karte.php",
                label="Mapa",
                category=NoiseCategory.MAP,
                frequency_weight=1.0,
            )
            assert dest.template_id is None
        finally:
            await conn.close()
    asyncio.run(run())


def test_create_destination_with_template_id(tmp_path):
    async def run():
        conn, noise, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            world_id = await _insert_world(conn)
            tpl = await rt.create_template(_make_template())
            dest = await noise.create_destination(
                world_id=world_id,
                url_pattern="/karte.php",
                label="Mapa clonado",
                category=NoiseCategory.MAP,
                frequency_weight=1.0,
                template_id=tpl.id,
            )
            assert dest.template_id == tpl.id
            fetched = await noise.get_destination(dest.id)
            assert fetched.template_id == tpl.id
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# count_paths_for_template
# ---------------------------------------------------------------------------

def test_count_paths_for_template(tmp_path):
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            tpl = await rt.create_template(_make_template(with_path=True))
            count = await rt.count_paths_for_template(tpl.id)
            assert count == 1
            tpl2 = await rt.create_template(_make_template(slug="no-paths"))
            assert await rt.count_paths_for_template(tpl2.id) == 0
            assert await rt.count_paths_for_template(9999) == 0
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# get_template_by_slug
# ---------------------------------------------------------------------------

def test_get_template_by_slug(tmp_path):
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
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            tpl = await rt.create_template(_make_template(with_path=True))
            assert len(tpl.paths) == 1

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

            second = await rt.seed_templates([tpl1, tpl2])
            assert second == 0

            tpl3 = _make_template(slug="s3", url_pattern="/dorf2.php")
            mixed = await rt.seed_templates([tpl1, tpl3])
            assert mixed == 1
        finally:
            await conn.close()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# v2-cat-libre — Tests de categoría libre en adaptador
# ---------------------------------------------------------------------------

def test_CAT_AD01_crear_template_con_categoria_libre(tmp_path):
    """create_template con category="Estadísticas" (str libre) → guardado y leído correctamente."""
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            tpl = _make_template(slug="cat-libre", category="Estadísticas")
            created = await rt.create_template(tpl)
            assert created.category == "Estadísticas"

            read = await rt.get_template(created.id)
            assert read is not None
            assert read.category == "Estadísticas"
        finally:
            await conn.close()
    asyncio.run(run())


def test_CAT_AD02_update_template_cambia_categoria(tmp_path):
    """update_template con category nueva → persiste la categoría actualizada."""
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            created = await rt.create_template(_make_template(slug="upd-cat"))
            assert str(created.category) == "MAP"

            updated = await rt.update_template(created.id, category="Top 10")
            assert updated.category == "Top 10"

            read = await rt.get_template(created.id)
            assert read is not None
            assert read.category == "Top 10"
        finally:
            await conn.close()
    asyncio.run(run())


def test_CAT_AD03_update_template_sin_category_no_cambia(tmp_path):
    """update_template sin pasar category → categoría original se mantiene."""
    async def run():
        conn, _, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            created = await rt.create_template(_make_template(slug="cat-keep", category="REPORTS"))
            updated = await rt.update_template(created.id, label="Nuevo label")
            assert updated.category == "REPORTS"
        finally:
            await conn.close()
    asyncio.run(run())


def test_CAT_AD04_migracion_m_rt04_idempotente(tmp_path):
    """
    M-RT04 aplicada dos veces → no falla y los datos (id=3,4,5) se preservan.
    Simula el caso de la BD del worktree con rutas existentes.
    """
    async def run():
        conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = OFF")

        # Crear la tabla route_templates CON el CHECK (estado pre-M-RT04)
        await conn.execute("""
            CREATE TABLE route_templates (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                slug             TEXT    NOT NULL UNIQUE,
                label            TEXT    NOT NULL,
                category         TEXT    NOT NULL
                                         CHECK (category IN (
                                             'MAP','OASIS_INFO','PLAYER_PROFILE',
                                             'MESSAGES','REPORTS','BUILDING_VIEW','OTHER'
                                         )),
                url_pattern      TEXT    NOT NULL,
                is_safe          INTEGER NOT NULL DEFAULT 1,
                origin_template_id INTEGER DEFAULT NULL
                                         REFERENCES route_templates(id) ON DELETE SET NULL,
                created_at       TEXT    NOT NULL,
                updated_at       TEXT    NOT NULL
            )
        """)
        # Insertar datos que simulan los id=3,4,5 del worktree
        now = "2026-06-05T00:00:00"
        await conn.execute("""
            INSERT INTO route_templates (id, slug, label, category, url_pattern, is_safe, created_at, updated_at)
            VALUES (3, 'centro-aldea', 'Centro de la aldea', 'OTHER', '/dorf2.php', 1, ?, ?)
        """, (now, now))
        await conn.execute("""
            INSERT INTO route_templates (id, slug, label, category, url_pattern, is_safe, created_at, updated_at)
            VALUES (4, 'estadisticas-aldeas', 'Estadisticas aldea', 'OTHER', '/village/statistics', 1, ?, ?)
        """, (now, now))
        await conn.execute("""
            INSERT INTO route_templates (id, slug, label, category, url_pattern, is_safe, created_at, updated_at)
            VALUES (5, 'estadisticas-tropas', 'Estadisticas tropas', 'MAP', '/village/statistics/troops', 1, ?, ?)
        """, (now, now))
        await conn.commit()

        # Aplicar M-RT04 por primera vez
        await _migrate_m_rt04(conn)

        # Verificar que los datos se preservaron
        rows = await conn.execute_fetchall(
            "SELECT id, slug, category FROM route_templates ORDER BY id"
        )
        assert len(rows) == 3
        assert rows[0]["id"] == 3
        assert rows[1]["slug"] == "estadisticas-aldeas"
        assert rows[2]["category"] == "MAP"

        # Verificar que el CHECK ya no existe (podemos insertar categoría libre)
        await conn.execute("""
            INSERT INTO route_templates (slug, label, category, url_pattern, is_safe, created_at, updated_at)
            VALUES ('nueva-libre', 'Nueva', 'Estadísticas', '/stats', 1, ?, ?)
        """, (now, now))
        await conn.commit()

        # Aplicar M-RT04 por segunda vez → no-op (idempotente)
        await _migrate_m_rt04(conn)

        rows2 = await conn.execute_fetchall(
            "SELECT id FROM route_templates ORDER BY id"
        )
        assert len(rows2) == 4  # 3 originales + 1 nueva

        await conn.close()
    asyncio.run(run())


def test_CAT_AD05_migracion_m_nd02_idempotente(tmp_path):
    """
    M-ND02 aplicada dos veces → no falla y los datos de noise_destinations se preservan.
    """
    async def run():
        conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = OFF")

        # Crear tablas mínimas
        now = "2026-06-05T00:00:00"
        await conn.execute("""
            CREATE TABLE accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        await conn.execute("""
            CREATE TABLE worlds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                server TEXT NOT NULL,
                tribe TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        await conn.execute(
            "INSERT INTO accounts (email, username, password, created_at) VALUES (?,?,?,?)",
            ("u@t.es", "bot", "hash", now)
        )
        await conn.execute(
            "INSERT INTO worlds (account_id, server, tribe, created_at) VALUES (?,?,?,?)",
            (1, "https://ts1.travian.es/", "romans", now)
        )

        # Crear noise_destinations CON el CHECK de category
        await conn.execute("""
            CREATE TABLE noise_destinations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                world_id INTEGER NOT NULL,
                url_pattern TEXT NOT NULL,
                label TEXT NOT NULL,
                category TEXT NOT NULL
                           CHECK (category IN ('MAP','OASIS_INFO','PLAYER_PROFILE',
                                               'MESSAGES','REPORTS','BUILDING_VIEW','OTHER')),
                frequency_weight REAL NOT NULL DEFAULT 1.0
                           CHECK (frequency_weight >= 0.1 AND frequency_weight <= 5.0),
                is_safe INTEGER NOT NULL DEFAULT 1,
                is_dead INTEGER NOT NULL DEFAULT 0,
                consecutive_failures_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                last_used_at TEXT,
                UNIQUE (world_id, url_pattern)
            )
        """)
        await conn.execute("""
            INSERT INTO noise_destinations
              (world_id, url_pattern, label, category, frequency_weight, is_safe, created_at)
            VALUES (1, '/karte.php', 'Mapa', 'MAP', 1.0, 1, ?)
        """, (now,))
        await conn.commit()

        # Aplicar M-ND02 primera vez
        await _migrate_noise_destinations_free_category(conn)

        # El dato original debe preservarse
        rows = await conn.execute_fetchall("SELECT label, category FROM noise_destinations")
        assert len(rows) == 1
        assert rows[0]["category"] == "MAP"

        # Ahora podemos insertar categoría libre
        await conn.execute("""
            INSERT INTO noise_destinations
              (world_id, url_pattern, label, category, frequency_weight, is_safe, created_at)
            VALUES (1, '/statistics', 'Stats', 'Estadísticas', 1.0, 1, ?)
        """, (now,))
        await conn.commit()

        # Aplicar M-ND02 segunda vez → no-op
        await _migrate_noise_destinations_free_category(conn)

        rows2 = await conn.execute_fetchall("SELECT category FROM noise_destinations ORDER BY id")
        assert len(rows2) == 2
        assert rows2[0]["category"] == "MAP"
        assert rows2[1]["category"] == "Estadísticas"

        await conn.close()
    asyncio.run(run())


def test_CAT_AD06_clonar_con_categoria_libre_a_mundo(tmp_path):
    """
    Clonar una plantilla con category="Estadísticas" a un mundo → noise_destination
    creado con category="Estadísticas" (sin IntegrityError del CHECK).
    """
    async def run():
        conn, noise, rt = await _setup_db(str(tmp_path / "test.db"))
        try:
            world_id = await _insert_world(conn)
            # Crear plantilla con categoría libre
            tpl = _make_template(slug="tpl-libre", category="Estadísticas", url_pattern="/statistics")
            created = await rt.create_template(tpl)

            # Clonar (create_destination con category str libre)
            dest = await noise.create_destination(
                world_id=world_id,
                url_pattern="/statistics",
                label=created.label,
                category=created.category,   # "Estadísticas"
                frequency_weight=1.0,
                is_safe=True,
                template_id=created.id,
            )
            assert dest.category == "Estadísticas"
            assert dest.template_id == created.id
        finally:
            await conn.close()
    asyncio.run(run())
