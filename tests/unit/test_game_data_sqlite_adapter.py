"""
Tests unitarios de GameDataSQLiteAdapter.

Usa BD en memoria (":memory:") — sin ficheros en disco, sin Chrome.
Verifica UPSERT idempotente, getters y manejo de NULL.

Convención del proyecto: tests síncronos que llaman a asyncio.run() directamente,
coherente con test_login_use_case.py y test_logout_use_case.py.
"""
import asyncio

import aiosqlite
import pytest

from adapters.db.game_data_sqlite_adapter import GameDataSQLiteAdapter
from core.entities.tribe import Tribe


# ---------------------------------------------------------------------------
# Helpers para crear adaptador con BD en memoria
# ---------------------------------------------------------------------------


def _make_adapter():
    """
    Crea un adaptador con BD en memoria de forma síncrona.
    Devuelve (adapter, conn) — el llamador debe cerrar conn con asyncio.run(conn.close()).
    """
    async def _create():
        conn = await aiosqlite.connect(":memory:")
        conn.row_factory = aiosqlite.Row
        adapter = GameDataSQLiteAdapter(conn)
        await adapter.ensure_tables()
        return adapter, conn

    return asyncio.run(_create())


# ---------------------------------------------------------------------------
# Datos de prueba
# ---------------------------------------------------------------------------

def _stats_romans_1() -> dict:
    return {
        "server_version": "1.45",
        "tribe": "romans",
        "ordinal": 1,
        "is_playable": True,
        "attack": 40,
        "def_infantry": 35,
        "def_cavalry": 50,
        "speed": 6,
        "carry": 50,
        "cost_wood": 120,
        "cost_clay": 100,
        "cost_iron": 150,
        "cost_crop": 30,
        "cost_sum": 400,
        "upkeep": 1,
        "train_time_s": 1600,
        "icon_id": "romans_1",
    }


def _upgrade_romans_1_lvl0() -> dict:
    return {
        "server_version": "1.45",
        "tribe": "romans",
        "ordinal": 1,
        "level": 0,
        "stat_name": "attack",
        "stat_value": 1.0,
        "cost_wood": 0,
        "cost_clay": 0,
        "cost_iron": 0,
        "cost_crop": 0,
        "cost_sum": 0,
        "upgrade_time_s": 0,
    }


def _icon_troop() -> dict:
    return {
        "icon_id": "romans_1",
        "icon_type": "troop",
        "tribe": "romans",
        "ordinal": 1,
        "stat_name": None,
        "file_path": "assets/icons/romans_1.png",
        "file_size_bytes": 1024,
        "width_px": 24,
        "height_px": 24,
    }


def _icon_stat() -> dict:
    return {
        "icon_id": "stat_attack",
        "icon_type": "stat",
        "tribe": None,
        "ordinal": None,
        "stat_name": "attack",
        "file_path": "assets/icons/stat_attack.png",
        "file_size_bytes": 512,
        "width_px": 20,
        "height_px": 20,
    }


# ---------------------------------------------------------------------------
# Tests — troop_stats
# ---------------------------------------------------------------------------


def test_upsert_troop_stats_creates():
    """El primer UPSERT crea la fila correctamente."""
    adapter, conn = _make_adapter()
    try:
        asyncio.run(adapter.upsert_troop_stats(_stats_romans_1()))
        result = asyncio.run(adapter.get_troop_stats(Tribe.ROMANS, 1))
        assert result is not None
        assert result["ordinal"] == 1
        assert result["tribe"] == "romans"
        assert result["attack"] == 40
        assert result["is_playable"] is True
    finally:
        asyncio.run(conn.close())


def test_upsert_troop_stats_updates():
    """El segundo UPSERT con datos distintos actualiza sin duplicar."""
    adapter, conn = _make_adapter()
    try:
        asyncio.run(adapter.upsert_troop_stats(_stats_romans_1()))
        updated = {**_stats_romans_1(), "attack": 99}
        asyncio.run(adapter.upsert_troop_stats(updated))
        result = asyncio.run(adapter.get_troop_stats(Tribe.ROMANS, 1))
        assert result["attack"] == 99
        # Verificar que no hay duplicados
        all_stats = asyncio.run(adapter.get_all_troop_stats(Tribe.ROMANS))
        romans_1_rows = [r for r in all_stats if r["ordinal"] == 1]
        assert len(romans_1_rows) == 1
    finally:
        asyncio.run(conn.close())


def test_get_troop_stats_returns_none_stats():
    """NULL en BD → None en dict devuelto (EC-01: valor '—' → NULL)."""
    adapter, conn = _make_adapter()
    try:
        stats_with_null = {**_stats_romans_1(), "attack": None, "def_infantry": None}
        asyncio.run(adapter.upsert_troop_stats(stats_with_null))
        result = asyncio.run(adapter.get_troop_stats(Tribe.ROMANS, 1))
        assert result["attack"] is None
        assert result["def_infantry"] is None
        assert result["speed"] == 6
    finally:
        asyncio.run(conn.close())


def test_get_all_troop_stats_empty():
    """Sin datos → lista vacía (no excepción)."""
    adapter, conn = _make_adapter()
    try:
        result = asyncio.run(adapter.get_all_troop_stats(Tribe.ROMANS))
        assert result == []
    finally:
        asyncio.run(conn.close())


def test_get_all_troop_stats_ordered():
    """Los stats se devuelven ordenados por ordinal."""
    adapter, conn = _make_adapter()
    try:
        for ordinal in [3, 1, 2]:
            asyncio.run(adapter.upsert_troop_stats({**_stats_romans_1(), "ordinal": ordinal}))
        result = asyncio.run(adapter.get_all_troop_stats(Tribe.ROMANS))
        assert [r["ordinal"] for r in result] == [1, 2, 3]
    finally:
        asyncio.run(conn.close())


def test_get_troop_stats_not_found_returns_none():
    """Tropa inexistente devuelve None."""
    adapter, conn = _make_adapter()
    try:
        result = asyncio.run(adapter.get_troop_stats(Tribe.ROMANS, 999))
        assert result is None
    finally:
        asyncio.run(conn.close())


# ---------------------------------------------------------------------------
# Tests — troop_upgrades
# ---------------------------------------------------------------------------


def test_get_troop_upgrades_empty():
    """Sin mejoras → lista vacía."""
    adapter, conn = _make_adapter()
    try:
        result = asyncio.run(adapter.get_troop_upgrades(Tribe.ROMANS, 1))
        assert result == []
    finally:
        asyncio.run(conn.close())


def test_upsert_troop_upgrade_creates_and_reads():
    """Primer UPSERT crea la fila de mejora correctamente."""
    adapter, conn = _make_adapter()
    try:
        asyncio.run(adapter.upsert_troop_upgrade(_upgrade_romans_1_lvl0()))
        result = asyncio.run(adapter.get_troop_upgrades(Tribe.ROMANS, 1))
        assert len(result) == 1
        assert result[0]["level"] == 0
        assert result[0]["stat_name"] == "attack"
        assert result[0]["stat_value"] == 1.0
    finally:
        asyncio.run(conn.close())


def test_upsert_troop_upgrade_idempotent():
    """Re-ejecutar no duplica filas."""
    adapter, conn = _make_adapter()
    try:
        asyncio.run(adapter.upsert_troop_upgrade(_upgrade_romans_1_lvl0()))
        asyncio.run(adapter.upsert_troop_upgrade({**_upgrade_romans_1_lvl0(), "stat_value": 1.5}))
        result = asyncio.run(adapter.get_troop_upgrades(Tribe.ROMANS, 1))
        assert len(result) == 1
        assert result[0]["stat_value"] == 1.5
    finally:
        asyncio.run(conn.close())


# ---------------------------------------------------------------------------
# Tests — icon_metadata
# ---------------------------------------------------------------------------


def test_upsert_icon_metadata_creates():
    """El primer UPSERT de icono crea la fila."""
    adapter, conn = _make_adapter()
    try:
        asyncio.run(adapter.upsert_icon_metadata(_icon_troop()))
        result = asyncio.run(adapter.get_icon_metadata("romans_1"))
        assert result is not None
        assert result["icon_type"] == "troop"
        assert result["tribe"] == "romans"
        assert result["ordinal"] == 1
        assert result["stat_name"] is None
    finally:
        asyncio.run(conn.close())


def test_upsert_icon_metadata_updates():
    """Segundo UPSERT con datos distintos actualiza sin duplicar."""
    adapter, conn = _make_adapter()
    try:
        asyncio.run(adapter.upsert_icon_metadata(_icon_troop()))
        asyncio.run(adapter.upsert_icon_metadata({**_icon_troop(), "file_size_bytes": 2048}))
        result = asyncio.run(adapter.get_icon_metadata("romans_1"))
        assert result["file_size_bytes"] == 2048
    finally:
        asyncio.run(conn.close())


def test_upsert_icon_stat_null_tribe_ordinal():
    """Iconos de stat tienen tribe=None y ordinal=None."""
    adapter, conn = _make_adapter()
    try:
        asyncio.run(adapter.upsert_icon_metadata(_icon_stat()))
        result = asyncio.run(adapter.get_icon_metadata("stat_attack"))
        assert result["tribe"] is None
        assert result["ordinal"] is None
        assert result["stat_name"] == "attack"
    finally:
        asyncio.run(conn.close())


def test_list_icons_no_filter():
    """Sin filtros devuelve todos los iconos."""
    adapter, conn = _make_adapter()
    try:
        asyncio.run(adapter.upsert_icon_metadata(_icon_troop()))
        asyncio.run(adapter.upsert_icon_metadata(_icon_stat()))
        result = asyncio.run(adapter.list_icons())
        assert len(result) == 2
    finally:
        asyncio.run(conn.close())


def test_list_icons_filter_type_troop():
    """Filtro icon_type='troop' devuelve solo iconos de tropa."""
    adapter, conn = _make_adapter()
    try:
        asyncio.run(adapter.upsert_icon_metadata(_icon_troop()))
        asyncio.run(adapter.upsert_icon_metadata(_icon_stat()))
        result = asyncio.run(adapter.list_icons(icon_type="troop"))
        assert len(result) == 1
        assert result[0]["icon_id"] == "romans_1"
    finally:
        asyncio.run(conn.close())


def test_list_icons_filter_tribe():
    """Filtro tribe devuelve solo iconos de esa tribu."""
    adapter, conn = _make_adapter()
    try:
        asyncio.run(adapter.upsert_icon_metadata(_icon_troop()))
        other = {**_icon_troop(), "icon_id": "teutons_1", "tribe": "teutons"}
        asyncio.run(adapter.upsert_icon_metadata(other))
        result = asyncio.run(adapter.list_icons(tribe="romans"))
        assert len(result) == 1
        assert result[0]["tribe"] == "romans"
    finally:
        asyncio.run(conn.close())


def test_list_icons_empty_returns_empty_list():
    """Sin iconos → lista vacía (no excepción, no 404)."""
    adapter, conn = _make_adapter()
    try:
        result = asyncio.run(adapter.list_icons(icon_type="troop"))
        assert result == []
    finally:
        asyncio.run(conn.close())


def test_get_icon_metadata_not_found():
    """icon_id inexistente devuelve None."""
    adapter, conn = _make_adapter()
    try:
        result = asyncio.run(adapter.get_icon_metadata("no_existe"))
        assert result is None
    finally:
        asyncio.run(conn.close())


# ---------------------------------------------------------------------------
# T-15 y T-16 — count_troop_stats (gate de seed)
# ---------------------------------------------------------------------------


def test_t15_count_troop_stats_empty_db():
    """
    T-15: BD recién creada sin datos → count_troop_stats() == 0.
    """
    adapter, conn = _make_adapter()
    try:
        count = asyncio.run(adapter.count_troop_stats())
        assert count == 0, f"BD vacía debería devolver 0; devolvió {count}"
    finally:
        asyncio.run(conn.close())


def test_t16_count_troop_stats_after_upsert():
    """
    T-16: tras insertar 1 fila con upsert_troop_stats → count_troop_stats() == 1.
    """
    adapter, conn = _make_adapter()
    try:
        asyncio.run(adapter.upsert_troop_stats(_stats_romans_1()))
        count = asyncio.run(adapter.count_troop_stats())
        assert count == 1, f"Después de 1 upsert debería devolver 1; devolvió {count}"
    finally:
        asyncio.run(conn.close())


# ---------------------------------------------------------------------------
# count_rows() — gate por-tabla para edificios (añadido 2026-05-27)
# ---------------------------------------------------------------------------


def _building_catalog_row() -> dict:
    return {
        "server_version": "1.45",
        "gid": 1,
        "alias": "woodcutter",
        "category": "resources",
        "description": "Produces wood",
        "icon_id": "building_1",
    }


def _building_stats_row() -> dict:
    return {
        "server_version": "1.45",
        "gid": 1,
        "level": 1,
        "cost_wood": 40,
        "cost_clay": 50,
        "cost_iron": 30,
        "cost_crop": 10,
        "cost_sum": 130,
        "upkeep": 2,
        "culture_points": 1,
        "build_time_s": 360,
        "effect_value": 2,
        "effect_label": "Production",
    }


def test_count_rows_troop_stats_empty():
    """count_rows('troop_stats') en BD vacía → 0."""
    adapter, conn = _make_adapter()
    try:
        count = asyncio.run(adapter.count_rows("troop_stats"))
        assert count == 0, f"Esperado 0; devolvió {count}"
    finally:
        asyncio.run(conn.close())


def test_count_rows_troop_stats_after_upsert():
    """count_rows('troop_stats') tras insertar 1 fila → 1."""
    adapter, conn = _make_adapter()
    try:
        asyncio.run(adapter.upsert_troop_stats(_stats_romans_1()))
        count = asyncio.run(adapter.count_rows("troop_stats"))
        assert count == 1, f"Esperado 1; devolvió {count}"
    finally:
        asyncio.run(conn.close())


def test_count_rows_building_catalog_empty():
    """count_rows('building_catalog') en BD vacía → 0."""
    adapter, conn = _make_adapter()
    try:
        count = asyncio.run(adapter.count_rows("building_catalog"))
        assert count == 0, f"Esperado 0; devolvió {count}"
    finally:
        asyncio.run(conn.close())


def test_count_rows_building_catalog_after_upsert():
    """count_rows('building_catalog') tras insertar 1 fila → 1."""
    adapter, conn = _make_adapter()
    try:
        asyncio.run(adapter.upsert_building_catalog(_building_catalog_row()))
        count = asyncio.run(adapter.count_rows("building_catalog"))
        assert count == 1, f"Esperado 1; devolvió {count}"
    finally:
        asyncio.run(conn.close())


def test_count_rows_building_stats_empty():
    """count_rows('building_stats') en BD vacía → 0."""
    adapter, conn = _make_adapter()
    try:
        count = asyncio.run(adapter.count_rows("building_stats"))
        assert count == 0, f"Esperado 0; devolvió {count}"
    finally:
        asyncio.run(conn.close())


def test_count_rows_building_stats_after_upsert():
    """count_rows('building_stats') tras insertar 1 fila → 1."""
    adapter, conn = _make_adapter()
    try:
        asyncio.run(adapter.upsert_building_stats(_building_stats_row()))
        count = asyncio.run(adapter.count_rows("building_stats"))
        assert count == 1, f"Esperado 1; devolvió {count}"
    finally:
        asyncio.run(conn.close())


def test_count_rows_invalid_table_raises_value_error():
    """count_rows con tabla no permitida → ValueError (seguridad: no expone accounts/worlds)."""
    adapter, conn = _make_adapter()
    try:
        try:
            asyncio.run(adapter.count_rows("accounts"))
            assert False, "Debería haber lanzado ValueError"
        except ValueError as exc:
            assert "accounts" in str(exc), f"Mensaje de error incorrecto: {exc}"
    finally:
        asyncio.run(conn.close())


def test_count_rows_worlds_raises_value_error():
    """count_rows('worlds') → ValueError (worlds es dato sensible, no de juego)."""
    adapter, conn = _make_adapter()
    try:
        try:
            asyncio.run(adapter.count_rows("worlds"))
            assert False, "Debería haber lanzado ValueError"
        except ValueError as exc:
            assert "worlds" in str(exc), f"Mensaje de error incorrecto: {exc}"
    finally:
        asyncio.run(conn.close())
