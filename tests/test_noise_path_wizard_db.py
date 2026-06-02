"""
Tests de integración de BD para Noise Path Wizard.

Cubre IT-NP01..IT-NP12 del spec noise-path-wizard.md §12:
  - Crear ruta con origin genérico y leer de vuelta (IT-NP01).
  - Crear ruta con origin VILLAGE_123 con aldea existente (IT-NP02).
  - Crear ruta con origin VILLAGE_999 sin aldea → ValueError (IT-NP03).
  - Pasos pre-migración tienen expected_url_after_click=NULL (IT-NP04).
  - Crear paso con expected_url_after_click y leer de vuelta (IT-NP05).
  - mark_path_dead, increment_path_failures, reset_path_failures (IT-NP11).

IT-NP13..IT-NP15 — Regresión M-NP01/M-NP03 (bug FK rota):
  - IT-NP13: BD con esquema pre-M-NP01 (FK correcta) → ensure_tables migra sin romper FK.
  - IT-NP14: BD con FK ya rota (noise_navigation_paths_old) → ensure_tables auto-repara.
  - IT-NP15: idempotencia de auto-reparación (ensure_tables dos veces sobre BD sana).
  - update_path con is_active=True resetea consecutive_failures_count (IT-NP12).
  - get_villages_for_world y upsert_village (IT-NP02, IT-NP07, IT-NP08).

Estrategia: aiosqlite temporal (asyncio.run directo), patrón del proyecto.
Spec noise-path-wizard.md §12 (Plan de pruebas — integración).
"""
from __future__ import annotations

import asyncio
import os
import tempfile

import aiosqlite
import pytest

from adapters.db.account_sqlite_adapter import AccountSQLiteAdapter
from adapters.db.noise_sqlite_adapter import NoiseSQLiteAdapter
from core.entities.noise import (
    NavigationOrigin,
    NavigationStep,
    NoiseAction,
    NoiseCategory,
)
from core.entities.village import Village


# ---------------------------------------------------------------------------
# Helpers de setup
# ---------------------------------------------------------------------------

async def _create_adapters(db_path: str):
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    account_adapter = AccountSQLiteAdapter(conn)
    noise_adapter   = NoiseSQLiteAdapter(conn)
    await account_adapter.ensure_tables()
    await noise_adapter.ensure_tables()
    return conn, account_adapter, noise_adapter


async def _setup_world(account_adapter: AccountSQLiteAdapter) -> tuple[int, int]:
    """Crea cuenta + mundo de prueba. Devuelve (account_id, world_id)."""
    from core.entities.account import Account
    from core.entities.tribe import Tribe
    from core.entities.world import World

    account = await account_adapter.save_account(
        Account(id=None, email="test@example.com", username="testbot", password=""),
        password_cifrada=b"dummy",
    )
    world = await account_adapter.save_world(
        account_id=account.id,
        world=World(id=0, server="https://ts1.travian.es/", tribe=Tribe.ROMANS),
    )
    return account.id, world.id


async def _create_destination(noise_adapter: NoiseSQLiteAdapter, world_id: int):
    return await noise_adapter.create_destination(
        world_id=world_id,
        url_pattern="/karte.php",
        label="Mapa",
        category=NoiseCategory.MAP,
        frequency_weight=1.0,
    )


def _make_step(expected_url: str | None = None) -> NavigationStep:
    return NavigationStep(
        id=None, path_id=None, step_order=0,
        action=NoiseAction.CLICK, selector="a[href='/statistics']",
        expected_url_after_click=expected_url,
    )


# ---------------------------------------------------------------------------
# IT-NP01 — Crear ruta con origin genérico y leer de vuelta
# ---------------------------------------------------------------------------

def test_IT_NP01_crear_ruta_origin_generico_round_trip(tmp_path):
    """Crear ruta STATISTICS + GET paths → origin='STATISTICS' y consecutive_failures=0."""

    async def _run():
        conn, account_adapter, noise_adapter = await _create_adapters(
            str(tmp_path / "test.db")
        )
        _, world_id = await _setup_world(account_adapter)
        dest = await _create_destination(noise_adapter, world_id)

        path = await noise_adapter.create_path(
            dest_id=dest.id,
            origin="STATISTICS",
            label="Ruta a estadísticas",
            steps=[_make_step()],
        )

        paths = await noise_adapter.list_paths(dest.id)
        assert len(paths) == 1
        assert paths[0].origin == "STATISTICS"
        assert paths[0].consecutive_failures_count == 0
        assert paths[0].is_dead is False
        await conn.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# IT-NP02 — Crear ruta con origin VILLAGE_123 con aldea existente
# ---------------------------------------------------------------------------

def test_IT_NP02_crear_ruta_village_origin_existente(tmp_path):
    """VILLAGE_123 con aldea existente → ruta creada correctamente."""

    async def _run():
        conn, account_adapter, noise_adapter = await _create_adapters(
            str(tmp_path / "test.db")
        )
        _, world_id = await _setup_world(account_adapter)
        dest = await _create_destination(noise_adapter, world_id)

        # Insertar aldea en villages
        v = Village(id=0, world_id=world_id, data_id=123, name="Merlinia", x=42, y=-17)
        await noise_adapter.upsert_village(v)

        path = await noise_adapter.create_path(
            dest_id=dest.id,
            origin="VILLAGE_123",
            label="Desde Merlinia",
            steps=[_make_step()],
        )

        assert path.origin == "VILLAGE_123"
        paths = await noise_adapter.list_paths(dest.id)
        assert paths[0].origin == "VILLAGE_123"
        await conn.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# IT-NP03 — Crear ruta con origin VILLAGE_999 sin aldea → ValueError
# ---------------------------------------------------------------------------

def test_IT_NP03_crear_ruta_village_origin_inexistente_lanza_error(tmp_path):
    """VILLAGE_999 sin aldea en villages → ValueError (CA-NP24)."""

    async def _run():
        conn, account_adapter, noise_adapter = await _create_adapters(
            str(tmp_path / "test.db")
        )
        _, world_id = await _setup_world(account_adapter)
        dest = await _create_destination(noise_adapter, world_id)

        with pytest.raises(ValueError, match="999"):
            await noise_adapter.create_path(
                dest_id=dest.id,
                origin="VILLAGE_999",
                label="Ruta inválida",
                steps=[_make_step()],
            )
        await conn.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# IT-NP05 — Crear paso con expected_url_after_click y leer de vuelta
# ---------------------------------------------------------------------------

def test_IT_NP05_expected_url_round_trip(tmp_path):
    """Crear paso con expected_url_after_click → leer de vuelta conserva el valor (CA-NP22)."""

    async def _run():
        conn, account_adapter, noise_adapter = await _create_adapters(
            str(tmp_path / "test.db")
        )
        _, world_id = await _setup_world(account_adapter)
        dest = await _create_destination(noise_adapter, world_id)

        path = await noise_adapter.create_path(
            dest_id=dest.id,
            origin="STATISTICS",
            label="Ruta con URL verificada",
            steps=[_make_step(expected_url="/statistics")],
        )

        paths = await noise_adapter.list_paths(dest.id)
        assert len(paths[0].steps) == 1
        assert paths[0].steps[0].expected_url_after_click == "/statistics"
        await conn.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# IT-NP10 — consecutive_failures_count inicial es 0
# ---------------------------------------------------------------------------

def test_IT_NP10_consecutive_failures_count_inicial_cero(tmp_path):
    """Path recién creado tiene consecutive_failures_count=0 (CA-NP21)."""

    async def _run():
        conn, account_adapter, noise_adapter = await _create_adapters(
            str(tmp_path / "test.db")
        )
        _, world_id = await _setup_world(account_adapter)
        dest = await _create_destination(noise_adapter, world_id)

        path = await noise_adapter.create_path(
            dest_id=dest.id,
            origin="ANY",
            label="Ruta nueva",
            steps=[_make_step()],
        )

        assert path.consecutive_failures_count == 0
        paths = await noise_adapter.list_paths(dest.id)
        assert paths[0].consecutive_failures_count == 0
        await conn.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# IT-NP11 — mark_path_dead, increment_path_failures, reset_path_failures
# ---------------------------------------------------------------------------

def test_IT_NP11_mark_path_dead(tmp_path):
    """mark_path_dead(path_id) → is_dead=True en BD."""

    async def _run():
        conn, account_adapter, noise_adapter = await _create_adapters(
            str(tmp_path / "test.db")
        )
        _, world_id = await _setup_world(account_adapter)
        dest = await _create_destination(noise_adapter, world_id)

        path = await noise_adapter.create_path(
            dest_id=dest.id,
            origin="ANY",
            label="Ruta a matar",
            steps=[_make_step()],
        )

        await noise_adapter.mark_path_dead(path.id)

        updated = await noise_adapter.get_path(path.id)
        assert updated.is_dead is True
        await conn.close()

    asyncio.run(_run())


def test_IT_NP11_increment_path_failures(tmp_path):
    """increment_path_failures → consecutive_failures_count aumenta."""

    async def _run():
        conn, account_adapter, noise_adapter = await _create_adapters(
            str(tmp_path / "test.db")
        )
        _, world_id = await _setup_world(account_adapter)
        dest = await _create_destination(noise_adapter, world_id)

        path = await noise_adapter.create_path(
            dest_id=dest.id,
            origin="ANY",
            label="Ruta con fallos",
            steps=[_make_step()],
        )

        count1 = await noise_adapter.increment_path_failures(path.id)
        assert count1 == 1
        count2 = await noise_adapter.increment_path_failures(path.id)
        assert count2 == 2

        updated = await noise_adapter.get_path(path.id)
        assert updated.consecutive_failures_count == 2
        await conn.close()

    asyncio.run(_run())


def test_IT_NP11_reset_path_failures(tmp_path):
    """reset_path_failures → consecutive_failures_count=0."""

    async def _run():
        conn, account_adapter, noise_adapter = await _create_adapters(
            str(tmp_path / "test.db")
        )
        _, world_id = await _setup_world(account_adapter)
        dest = await _create_destination(noise_adapter, world_id)

        path = await noise_adapter.create_path(
            dest_id=dest.id,
            origin="ANY",
            label="Ruta a resetear",
            steps=[_make_step()],
        )

        await noise_adapter.increment_path_failures(path.id)
        await noise_adapter.increment_path_failures(path.id)
        await noise_adapter.reset_path_failures(path.id)

        updated = await noise_adapter.get_path(path.id)
        assert updated.consecutive_failures_count == 0
        await conn.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# IT-NP12 — update_path con is_active=True resetea consecutive_failures_count
# ---------------------------------------------------------------------------

def test_IT_NP12_update_path_reactivar_resetea_contador(tmp_path):
    """CA-NP25: PUT con is_active=True resetea consecutive_failures_count a 0."""

    async def _run():
        conn, account_adapter, noise_adapter = await _create_adapters(
            str(tmp_path / "test.db")
        )
        _, world_id = await _setup_world(account_adapter)
        dest = await _create_destination(noise_adapter, world_id)

        path = await noise_adapter.create_path(
            dest_id=dest.id,
            origin="ANY",
            label="Ruta a reactivar",
            steps=[_make_step()],
        )

        # Simular 2 fallos y marcar dead
        await noise_adapter.increment_path_failures(path.id)
        await noise_adapter.increment_path_failures(path.id)
        await noise_adapter.mark_path_dead(path.id)

        # Verificar estado antes
        before = await noise_adapter.get_path(path.id)
        assert before.consecutive_failures_count == 2
        assert before.is_dead is True

        # Reactivar
        await noise_adapter.update_path(path_id=path.id, is_active=True)

        after = await noise_adapter.get_path(path.id)
        assert after.consecutive_failures_count == 0
        assert after.is_dead is False
        assert after.is_active is True
        await conn.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# IT — get_villages_for_world + upsert_village
# ---------------------------------------------------------------------------

def test_IT_villages_upsert_y_get(tmp_path):
    """upsert_village + get_villages_for_world → round-trip correcto."""

    async def _run():
        conn, account_adapter, noise_adapter = await _create_adapters(
            str(tmp_path / "test.db")
        )
        _, world_id = await _setup_world(account_adapter)

        v1 = Village(id=0, world_id=world_id, data_id=123, name="Merlinia", x=42, y=-17)
        v2 = Village(id=0, world_id=world_id, data_id=456, name="Forticia", x=43, y=-17)
        await noise_adapter.upsert_village(v1)
        await noise_adapter.upsert_village(v2)

        villages = await noise_adapter.get_villages_for_world(world_id)
        assert len(villages) == 2
        data_ids = {v.data_id for v in villages}
        assert 123 in data_ids
        assert 456 in data_ids
        await conn.close()

    asyncio.run(_run())


def test_IT_villages_upsert_idempotente(tmp_path):
    """Upsert de aldea ya existente actualiza name, x, y sin duplicar."""

    async def _run():
        conn, account_adapter, noise_adapter = await _create_adapters(
            str(tmp_path / "test.db")
        )
        _, world_id = await _setup_world(account_adapter)

        v = Village(id=0, world_id=world_id, data_id=123, name="Merlinia", x=42, y=-17)
        await noise_adapter.upsert_village(v)

        v_updated = Village(id=0, world_id=world_id, data_id=123, name="Merlinia II", x=99, y=88)
        await noise_adapter.upsert_village(v_updated)

        villages = await noise_adapter.get_villages_for_world(world_id)
        assert len(villages) == 1  # sin duplicado
        assert villages[0].name == "Merlinia II"
        assert villages[0].x == 99
        await conn.close()

    asyncio.run(_run())


def test_IT_villages_vacias_para_mundo_nuevo(tmp_path):
    """get_villages_for_world en mundo sin aldeas → lista vacía (EC-NP06)."""

    async def _run():
        conn, account_adapter, noise_adapter = await _create_adapters(
            str(tmp_path / "test.db")
        )
        _, world_id = await _setup_world(account_adapter)

        villages = await noise_adapter.get_villages_for_world(world_id)
        assert villages == []
        await conn.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# IT — Migración: ensure_tables idempotente con tablas ya existentes
# ---------------------------------------------------------------------------

def test_IT_ensure_tables_idempotente(tmp_path):
    """Llamar ensure_tables dos veces no rompe nada (migraciones idempotentes)."""

    async def _run():
        conn, account_adapter, noise_adapter = await _create_adapters(
            str(tmp_path / "test.db")
        )
        # Segunda llamada: debe ser idempotente
        await noise_adapter.ensure_tables()
        _, world_id = await _setup_world(account_adapter)
        dest = await _create_destination(noise_adapter, world_id)
        path = await noise_adapter.create_path(
            dest_id=dest.id,
            origin="ANY",
            label="Idempotency test",
            steps=[_make_step()],
        )
        assert path.id is not None
        await conn.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Helpers internos para los tests de regresión M-NP01/M-NP03
# ---------------------------------------------------------------------------

async def _create_conn(db_path: str) -> aiosqlite.Connection:
    """Abre conexión con row_factory y WAL, sin ejecutar ensure_tables."""
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    return conn


async def _bootstrap_schema_pre_m_np01(conn: aiosqlite.Connection) -> tuple[int, int]:
    """
    Crea el esquema completo en estado PRE-M-NP01:
      - Todas las tablas de AccountSQLiteAdapter (accounts, worlds, villages).
      - noise_destinations, world_noise_config.
      - noise_navigation_paths con CHECK de origin (esquema original) y SIN
        columnas is_dead / consecutive_failures_count.
      - noise_navigation_steps con FK correcta a noise_navigation_paths(id)
        y SIN columna expected_url_after_click.
    Devuelve (world_id, dest_id) para poder crear rutas de prueba.
    """
    from adapters.db.account_sqlite_adapter import AccountSQLiteAdapter
    from core.entities.account import Account
    from core.entities.tribe import Tribe
    from core.entities.world import World

    account_adapter = AccountSQLiteAdapter(conn)
    await account_adapter.ensure_tables()

    # noise_destinations
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS noise_destinations (
            id                        INTEGER PRIMARY KEY AUTOINCREMENT,
            world_id                  INTEGER NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
            url_pattern               TEXT    NOT NULL,
            label                     TEXT    NOT NULL,
            category                  TEXT    NOT NULL
                                              CHECK (category IN (
                                                  'MAP','OASIS_INFO','PLAYER_PROFILE',
                                                  'MESSAGES','REPORTS','BUILDING_VIEW','OTHER'
                                              )),
            frequency_weight          REAL    NOT NULL DEFAULT 1.0 CHECK (frequency_weight > 0),
            is_safe                   INTEGER NOT NULL DEFAULT 1,
            is_dead                   INTEGER NOT NULL DEFAULT 0,
            consecutive_failures_count INTEGER NOT NULL DEFAULT 0,
            created_at                TEXT    NOT NULL,
            last_used_at              TEXT,
            UNIQUE (world_id, url_pattern)
        )
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_noise_destinations_world
            ON noise_destinations(world_id, is_dead, is_safe)
    """)

    # noise_navigation_paths — esquema VIEJO (con CHECK, sin is_dead ni failures)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS noise_navigation_paths (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            destination_id INTEGER NOT NULL
                                   REFERENCES noise_destinations(id) ON DELETE CASCADE,
            origin         TEXT    NOT NULL
                                   CHECK (origin IN ('DORF1','DORF2','MAP','STATISTICS','ANY',
                                                     'MESSAGES','REPORTS','HERO','AUCTIONS')),
            label          TEXT    NOT NULL,
            is_active      INTEGER NOT NULL DEFAULT 1
        )
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_noise_paths_destination
            ON noise_navigation_paths(destination_id)
    """)

    # noise_navigation_steps — esquema VIEJO (sin expected_url_after_click)
    # FK apunta correctamente a noise_navigation_paths
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS noise_navigation_steps (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            path_id      INTEGER NOT NULL
                                 REFERENCES noise_navigation_paths(id) ON DELETE CASCADE,
            step_order   INTEGER NOT NULL,
            action       TEXT    NOT NULL
                                 CHECK (action IN ('CLICK','WAIT_FOR_SELECTOR','SCROLL_TO','HOVER')),
            selector     TEXT    NOT NULL,
            value        TEXT    NOT NULL DEFAULT '',
            delay_min_ms INTEGER NOT NULL DEFAULT 500,
            delay_max_ms INTEGER NOT NULL DEFAULT 900,
            UNIQUE (path_id, step_order)
        )
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_noise_steps_path
            ON noise_navigation_steps(path_id, step_order)
    """)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS world_noise_config (
            world_id                         INTEGER PRIMARY KEY
                                                     REFERENCES worlds(id) ON DELETE CASCADE,
            noise_enabled                    INTEGER NOT NULL DEFAULT 1,
            hardcore_total_req_per_hour_min  INTEGER NOT NULL DEFAULT 80,
            hardcore_total_req_per_hour_max  INTEGER NOT NULL DEFAULT 150,
            passive_total_req_per_hour_min   INTEGER NOT NULL DEFAULT 15,
            passive_total_req_per_hour_max   INTEGER NOT NULL DEFAULT 40,
            dwell_min_seconds                REAL    NOT NULL DEFAULT 2.0,
            dwell_max_seconds                REAL    NOT NULL DEFAULT 30.0
        )
    """)
    await conn.commit()

    # Insertar cuenta + mundo + destino
    account = await account_adapter.save_account(
        Account(id=None, email="reg@example.com", username="regbot", password=""),
        password_cifrada=b"dummy",
    )
    world = await account_adapter.save_world(
        account_id=account.id,
        world=World(id=0, server="https://ts1.travian.es/", tribe=Tribe.ROMANS),
    )
    from datetime import datetime, timezone
    await conn.execute("""
        INSERT INTO noise_destinations
          (world_id, url_pattern, label, category, frequency_weight,
           is_safe, is_dead, consecutive_failures_count, created_at)
        VALUES (?, '/karte.php', 'Mapa', 'MAP', 1.0, 1, 0, 0, ?)
    """, (world.id, datetime.now(timezone.utc).isoformat()))
    await conn.commit()
    cursor = await conn.execute(
        "SELECT id FROM noise_destinations WHERE world_id=? AND url_pattern='/karte.php'",
        (world.id,),
    )
    row = await cursor.fetchone()
    return world.id, row["id"]


async def _bootstrap_schema_broken_fk(conn: aiosqlite.Connection) -> tuple[int, int]:
    """
    Crea una BD ya CORRUPTA, reproduciendo exactamente el daño que causó la
    versión pre-fix de M-NP01:
      - noise_navigation_paths ya tiene is_dead y consecutive_failures_count
        (migración M-NP01 ya corrió).
      - noise_navigation_steps.path_id apunta a noise_navigation_paths_old(id)
        (la versión pre-fix reescribió la FK antes de borrar _old).
      - noise_navigation_paths_old NO existe (ya fue eliminada).
    Devuelve (world_id, dest_id).
    """
    from adapters.db.account_sqlite_adapter import AccountSQLiteAdapter
    from core.entities.account import Account
    from core.entities.tribe import Tribe
    from core.entities.world import World

    account_adapter = AccountSQLiteAdapter(conn)
    await account_adapter.ensure_tables()

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS noise_destinations (
            id                        INTEGER PRIMARY KEY AUTOINCREMENT,
            world_id                  INTEGER NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
            url_pattern               TEXT    NOT NULL,
            label                     TEXT    NOT NULL,
            category                  TEXT    NOT NULL
                                              CHECK (category IN (
                                                  'MAP','OASIS_INFO','PLAYER_PROFILE',
                                                  'MESSAGES','REPORTS','BUILDING_VIEW','OTHER'
                                              )),
            frequency_weight          REAL    NOT NULL DEFAULT 1.0 CHECK (frequency_weight > 0),
            is_safe                   INTEGER NOT NULL DEFAULT 1,
            is_dead                   INTEGER NOT NULL DEFAULT 0,
            consecutive_failures_count INTEGER NOT NULL DEFAULT 0,
            created_at                TEXT    NOT NULL,
            last_used_at              TEXT,
            UNIQUE (world_id, url_pattern)
        )
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_noise_destinations_world
            ON noise_destinations(world_id, is_dead, is_safe)
    """)

    # noise_navigation_paths ya migrada (tiene is_dead + failures)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS noise_navigation_paths (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            destination_id              INTEGER NOT NULL
                                                REFERENCES noise_destinations(id) ON DELETE CASCADE,
            origin                      TEXT    NOT NULL,
            label                       TEXT    NOT NULL,
            is_active                   INTEGER NOT NULL DEFAULT 1,
            is_dead                     INTEGER NOT NULL DEFAULT 0,
            consecutive_failures_count  INTEGER NOT NULL DEFAULT 0
        )
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_noise_paths_destination
            ON noise_navigation_paths(destination_id)
    """)

    # FK ROTA: apunta a noise_navigation_paths_old (que no existe)
    # Esto reproduce exactamente lo que hace SQLite >= 3.25 cuando renombras
    # la tabla padre con legacy_alter_table=OFF.
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS noise_navigation_steps (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            path_id                     INTEGER NOT NULL
                                                REFERENCES "noise_navigation_paths_old"(id) ON DELETE CASCADE,
            step_order                  INTEGER NOT NULL,
            action                      TEXT    NOT NULL
                                                CHECK (action IN (
                                                    'CLICK','WAIT_FOR_SELECTOR','SCROLL_TO','HOVER'
                                                )),
            selector                    TEXT    NOT NULL,
            value                       TEXT    NOT NULL DEFAULT '',
            delay_min_ms                INTEGER NOT NULL DEFAULT 500,
            delay_max_ms                INTEGER NOT NULL DEFAULT 900,
            expected_url_after_click    TEXT    DEFAULT NULL,
            UNIQUE (path_id, step_order)
        )
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_noise_steps_path
            ON noise_navigation_steps(path_id, step_order)
    """)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS world_noise_config (
            world_id                         INTEGER PRIMARY KEY
                                                     REFERENCES worlds(id) ON DELETE CASCADE,
            noise_enabled                    INTEGER NOT NULL DEFAULT 1,
            hardcore_total_req_per_hour_min  INTEGER NOT NULL DEFAULT 80,
            hardcore_total_req_per_hour_max  INTEGER NOT NULL DEFAULT 150,
            passive_total_req_per_hour_min   INTEGER NOT NULL DEFAULT 15,
            passive_total_req_per_hour_max   INTEGER NOT NULL DEFAULT 40,
            dwell_min_seconds                REAL    NOT NULL DEFAULT 2.0,
            dwell_max_seconds                REAL    NOT NULL DEFAULT 30.0
        )
    """)
    await conn.commit()

    account = await account_adapter.save_account(
        Account(id=None, email="broken@example.com", username="brokenbot", password=""),
        password_cifrada=b"dummy",
    )
    world = await account_adapter.save_world(
        account_id=account.id,
        world=World(id=0, server="https://ts1.travian.es/", tribe=Tribe.ROMANS),
    )
    from datetime import datetime, timezone
    await conn.execute("""
        INSERT INTO noise_destinations
          (world_id, url_pattern, label, category, frequency_weight,
           is_safe, is_dead, consecutive_failures_count, created_at)
        VALUES (?, '/karte.php', 'Mapa', 'MAP', 1.0, 1, 0, 0, ?)
    """, (world.id, datetime.now(timezone.utc).isoformat()))
    await conn.commit()
    cursor = await conn.execute(
        "SELECT id FROM noise_destinations WHERE world_id=? AND url_pattern='/karte.php'",
        (world.id,),
    )
    row = await cursor.fetchone()
    return world.id, row["id"]


async def _get_steps_table_sql(conn: aiosqlite.Connection) -> str:
    """Lee el SQL de CREATE TABLE de noise_navigation_steps desde sqlite_master."""
    rows = await conn.execute_fetchall(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='noise_navigation_steps'"
    )
    return rows[0]["sql"] if rows else ""


async def _fk_check_passes(conn: aiosqlite.Connection) -> bool:
    """Ejecuta PRAGMA foreign_key_check y devuelve True si no hay violaciones."""
    rows = await conn.execute_fetchall("PRAGMA foreign_key_check")
    return len(rows) == 0


# ---------------------------------------------------------------------------
# IT-NP13 — BD pre-M-NP01 → ensure_tables migra sin romper FK
# ---------------------------------------------------------------------------

def test_IT_NP13_esquema_pre_m_np01_ensure_tables_no_rompe_fk(tmp_path):
    """
    BD con esquema pre-M-NP01 (FK correcta, sin is_dead/failures):
    ensure_tables debe ejecutar M-NP01 y dejar la FK apuntando a
    noise_navigation_paths (no a _old). PRAGMA foreign_key_check limpio.
    """

    async def _run():
        db_path = str(tmp_path / "pre_m_np01.db")
        conn = await _create_conn(db_path)

        # Construir esquema viejo (pre-M-NP01)
        world_id, dest_id = await _bootstrap_schema_pre_m_np01(conn)

        # Ejecutar ensure_tables (debe correr M-NP01, M-NP02 y M-NP03)
        noise_adapter = NoiseSQLiteAdapter(conn)
        await noise_adapter.ensure_tables()

        # Verificar que la FK en noise_navigation_steps apunta a noise_navigation_paths
        steps_sql = await _get_steps_table_sql(conn)
        assert "noise_navigation_paths_old" not in steps_sql, (
            f"FK rota detectada en noise_navigation_steps tras ensure_tables: {steps_sql!r}"
        )
        assert "noise_navigation_paths" in steps_sql, (
            f"FK a noise_navigation_paths no encontrada: {steps_sql!r}"
        )

        # PRAGMA foreign_key_check limpio
        assert await _fk_check_passes(conn), "PRAGMA foreign_key_check reportó violaciones FK"

        # Además: noise_navigation_paths debe tener las columnas nuevas
        cursor = await conn.execute("PRAGMA table_info(noise_navigation_paths)")
        cols = {row["name"] for row in await cursor.fetchall()}
        assert "is_dead" in cols
        assert "consecutive_failures_count" in cols

        await conn.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# IT-NP14 — BD con FK ya rota → ensure_tables auto-repara y create_path funciona
# ---------------------------------------------------------------------------

def test_IT_NP14_fk_rota_ensure_tables_auto_repara(tmp_path):
    """
    BD con noise_navigation_steps.path_id apuntando a noise_navigation_paths_old
    (tabla inexistente): ensure_tables debe detectarlo, reparar la FK y permitir
    que create_path funcione sin error con foreign_keys=ON.
    """

    async def _run():
        db_path = str(tmp_path / "broken_fk.db")
        conn = await _create_conn(db_path)

        # Construir BD corrupta (FK rota)
        world_id, dest_id = await _bootstrap_schema_broken_fk(conn)

        # Verificar que la FK está efectivamente rota antes de la reparación
        steps_sql_before = await _get_steps_table_sql(conn)
        assert "noise_navigation_paths_old" in steps_sql_before, (
            "El helper de setup no creó la FK rota correctamente"
        )

        # Ejecutar ensure_tables (debe detectar y reparar vía M-NP03)
        noise_adapter = NoiseSQLiteAdapter(conn)
        await noise_adapter.ensure_tables()

        # Verificar que la FK ya no apunta a _old
        steps_sql_after = await _get_steps_table_sql(conn)
        assert "noise_navigation_paths_old" not in steps_sql_after, (
            f"FK sigue rota tras ensure_tables: {steps_sql_after!r}"
        )
        assert "noise_navigation_paths" in steps_sql_after, (
            f"FK a noise_navigation_paths no encontrada: {steps_sql_after!r}"
        )

        # PRAGMA foreign_key_check limpio
        assert await _fk_check_passes(conn), "PRAGMA foreign_key_check reportó violaciones FK"

        # Lo más importante: create_path con >= 1 step debe funcionar sin error
        # (con foreign_keys=ON, que es el modo de la app en producción)
        path = await noise_adapter.create_path(
            dest_id=dest_id,
            origin="ANY",
            label="Ruta post-reparación",
            steps=[_make_step()],
        )
        assert path.id is not None
        assert len(path.steps) == 1

        # Y debe poder leerse de vuelta
        paths = await noise_adapter.list_paths(dest_id)
        assert len(paths) == 1
        assert paths[0].id == path.id

        await conn.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# IT-NP15 — Idempotencia de ensure_tables sobre BD ya sana (M-NP03 no actúa)
# ---------------------------------------------------------------------------

def test_IT_NP15_ensure_tables_idempotente_fk_sana(tmp_path):
    """
    ensure_tables llamado dos veces sobre una BD con FK correcta no rompe nada.
    M-NP03 debe detectar que no hay daño y omitir la reparación.
    """

    async def _run():
        db_path = str(tmp_path / "idempotent.db")
        conn, account_adapter, noise_adapter = await _create_adapters(db_path)
        _, world_id = await _setup_world(account_adapter)
        dest = await _create_destination(noise_adapter, world_id)

        # Crear una ruta con un step antes de la segunda llamada
        path = await noise_adapter.create_path(
            dest_id=dest.id,
            origin="ANY",
            label="Ruta idempotencia",
            steps=[_make_step()],
        )

        # Segunda llamada a ensure_tables (debe ser completamente inocua)
        await noise_adapter.ensure_tables()

        # FK sigue correcta
        steps_sql = await _get_steps_table_sql(conn)
        assert "noise_navigation_paths_old" not in steps_sql
        assert "noise_navigation_paths" in steps_sql

        # PRAGMA foreign_key_check limpio
        assert await _fk_check_passes(conn)

        # Los datos siguen intactos
        paths = await noise_adapter.list_paths(dest.id)
        assert len(paths) == 1
        assert paths[0].id == path.id
        assert len(paths[0].steps) == 1

        await conn.close()

    asyncio.run(_run())
