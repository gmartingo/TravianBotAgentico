"""
Tests unitarios de GameDataSQLiteAdapter — métodos de edificios.

Usa BD en memoria (":memory:") — sin ficheros en disco, sin Chrome.
Verifica UPSERT idempotente, getters y manejo de NULL.

Convención del proyecto: tests síncronos que llaman a asyncio.run() directamente.
"""
import asyncio

import aiosqlite
import pytest

from adapters.db.game_data_sqlite_adapter import GameDataSQLiteAdapter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_adapter():
    """Crea un adaptador con BD en memoria. Devuelve (adapter, conn)."""
    async def _create():
        conn = await aiosqlite.connect(":memory:")
        conn.row_factory = aiosqlite.Row
        adapter = GameDataSQLiteAdapter(conn)
        await adapter.ensure_tables()
        return adapter, conn

    return asyncio.run(_create())


def _stats_warehouse_lvl1() -> dict:
    return {
        "server_version": "1.45",
        "gid": 10,
        "level": 1,
        "cost_wood": 130,
        "cost_clay": 160,
        "cost_iron": 90,
        "cost_crop": 40,
        "cost_sum": 420,
        "upkeep": 1,
        "culture_points": 1,
        "build_time_s": 1000,
        "effect_value": 1200,
        "effect_label": "Almacena",
    }


def _stats_warehouse_lvl2() -> dict:
    d = _stats_warehouse_lvl1()
    d["level"] = 2
    d["cost_sum"] = 800
    d["effect_value"] = 2400
    return d


def _catalog_warehouse() -> dict:
    return {
        "server_version": "1.45",
        "gid": 10,
        "alias": "warehouse",
        "category": "infrastructure",
        "description": "Amplía la capacidad de almacenamiento.",
        "icon_id": "building_10_warehouse",
    }


# ---------------------------------------------------------------------------
# Tests de building_stats
# ---------------------------------------------------------------------------


def test_upsert_building_stats_creates():
    """UPSERT crea la fila correctamente."""
    adapter, conn = _make_adapter()
    try:
        asyncio.run(adapter.upsert_building_stats(_stats_warehouse_lvl1()))
        rows = asyncio.run(adapter.get_building_stats(10, "1.45"))
        assert len(rows) == 1
        assert rows[0]["level"] == 1
        assert rows[0]["cost_wood"] == 130
        assert rows[0]["effect_value"] == 1200
        assert rows[0]["effect_label"] == "Almacena"
    finally:
        asyncio.run(conn.close())


def test_upsert_building_stats_updates():
    """Segundo UPSERT actualiza sin duplicar."""
    adapter, conn = _make_adapter()
    try:
        asyncio.run(adapter.upsert_building_stats(_stats_warehouse_lvl1()))
        updated = _stats_warehouse_lvl1()
        updated["cost_wood"] = 999
        asyncio.run(adapter.upsert_building_stats(updated))
        rows = asyncio.run(adapter.get_building_stats(10, "1.45"))
        assert len(rows) == 1  # sin duplicado
        assert rows[0]["cost_wood"] == 999
    finally:
        asyncio.run(conn.close())


def test_get_building_stats_empty():
    """Sin datos → lista vacía (no excepción)."""
    adapter, conn = _make_adapter()
    try:
        rows = asyncio.run(adapter.get_building_stats(999, "1.45"))
        assert rows == []
    finally:
        asyncio.run(conn.close())


def test_get_building_stats_returns_levels_ordered():
    """Los niveles se devuelven ordenados por level asc."""
    adapter, conn = _make_adapter()
    try:
        asyncio.run(adapter.upsert_building_stats(_stats_warehouse_lvl2()))
        asyncio.run(adapter.upsert_building_stats(_stats_warehouse_lvl1()))
        rows = asyncio.run(adapter.get_building_stats(10, "1.45"))
        assert rows[0]["level"] == 1
        assert rows[1]["level"] == 2
    finally:
        asyncio.run(conn.close())


def test_get_all_building_stats_indexed_by_gid():
    """get_all_building_stats devuelve dict {gid: [rows]}."""
    adapter, conn = _make_adapter()
    try:
        asyncio.run(adapter.upsert_building_stats(_stats_warehouse_lvl1()))
        granary_lvl1 = {**_stats_warehouse_lvl1(), "gid": 11, "alias": "granary"}
        asyncio.run(adapter.upsert_building_stats(granary_lvl1))
        all_stats = asyncio.run(adapter.get_all_building_stats("1.45"))
        assert 10 in all_stats
        assert 11 in all_stats
        assert all_stats[10][0]["gid"] == 10
        assert all_stats[11][0]["gid"] == 11
    finally:
        asyncio.run(conn.close())


def test_null_values_round_trip():
    """NULL en BD → None en dict devuelto."""
    adapter, conn = _make_adapter()
    try:
        stats = {
            "server_version": "1.45",
            "gid": 5,
            "level": 1,
            "cost_wood": None,
            "cost_clay": None,
            "cost_iron": None,
            "cost_crop": None,
            "cost_sum": None,
            "upkeep": None,
            "culture_points": None,
            "build_time_s": None,
            "effect_value": None,
            "effect_label": "",
        }
        asyncio.run(adapter.upsert_building_stats(stats))
        rows = asyncio.run(adapter.get_building_stats(5, "1.45"))
        assert len(rows) == 1
        assert rows[0]["cost_wood"] is None
        assert rows[0]["effect_value"] is None
    finally:
        asyncio.run(conn.close())


# ---------------------------------------------------------------------------
# Tests de building_catalog
# ---------------------------------------------------------------------------


def test_upsert_building_catalog_creates():
    """UPSERT crea la fila de building_catalog."""
    adapter, conn = _make_adapter()
    try:
        asyncio.run(adapter.upsert_building_catalog(_catalog_warehouse()))
        meta = asyncio.run(adapter.get_building_catalog(10, "1.45"))
        assert meta is not None
        assert meta["alias"] == "warehouse"
        assert meta["category"] == "infrastructure"
        assert meta["description"] == "Amplía la capacidad de almacenamiento."
        assert meta["icon_id"] == "building_10_warehouse"
    finally:
        asyncio.run(conn.close())


def test_upsert_building_catalog_updates():
    """Segundo UPSERT actualiza sin duplicar."""
    adapter, conn = _make_adapter()
    try:
        asyncio.run(adapter.upsert_building_catalog(_catalog_warehouse()))
        updated = _catalog_warehouse()
        updated["description"] = "Descripción actualizada."
        asyncio.run(adapter.upsert_building_catalog(updated))
        meta = asyncio.run(adapter.get_building_catalog(10, "1.45"))
        assert meta["description"] == "Descripción actualizada."
    finally:
        asyncio.run(conn.close())


def test_get_building_catalog_returns_none():
    """Gid no existente → None."""
    adapter, conn = _make_adapter()
    try:
        result = asyncio.run(adapter.get_building_catalog(999, "1.45"))
        assert result is None
    finally:
        asyncio.run(conn.close())


def test_get_all_building_catalog_returns_dict():
    """get_all_building_catalog devuelve dict {gid: meta}."""
    adapter, conn = _make_adapter()
    try:
        asyncio.run(adapter.upsert_building_catalog(_catalog_warehouse()))
        granary_cat = {**_catalog_warehouse(), "gid": 11, "alias": "granary"}
        asyncio.run(adapter.upsert_building_catalog(granary_cat))
        all_cat = asyncio.run(adapter.get_all_building_catalog("1.45"))
        assert 10 in all_cat
        assert 11 in all_cat
        assert all_cat[10]["alias"] == "warehouse"
        assert all_cat[11]["alias"] == "granary"
    finally:
        asyncio.run(conn.close())


def test_building_catalog_icon_id_can_be_null():
    """icon_id puede ser None (icono no capturado aún)."""
    adapter, conn = _make_adapter()
    try:
        cat = _catalog_warehouse()
        cat["icon_id"] = None
        asyncio.run(adapter.upsert_building_catalog(cat))
        meta = asyncio.run(adapter.get_building_catalog(10, "1.45"))
        assert meta["icon_id"] is None
    finally:
        asyncio.run(conn.close())
