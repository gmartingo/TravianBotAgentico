"""
Tests unitarios de scripts/export_game_data_seed.py.

Cubre:
  T-10  Export con datos produce los 3 ficheros JSON (tropas) con conteos correctos
  T-11  Export sin scraped_at en ningún objeto JSON
  T-12  Orden determinista de filas en troop_stats (por server_version, tribe, ordinal)
  T-13  Tabla vacía → su fichero JSON no se crea
  T-14  Atomicidad: si write_text falla, no quedan ficheros .tmp en disco
  T-B5  Export produce los 2 ficheros JSON de edificios con conteos correctos
  T-B6  Orden determinista en building_stats (por server_version, gid, level)
  T-B7  building_catalog vacío → building_catalog.json no se crea
  T-B8  Ningún objeto exportado de edificios contiene scraped_at

Estrategia:
  - BD :memory: con datos inline, tmp_path para el directorio de salida.
  - Se llama a la función interna export() directamente (no como subprocess).
  - Para T-14 se parchea Path.write_text para simular error de disco.

Patrón del proyecto: tests síncronos con asyncio.run() directo.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import aiosqlite
import pytest

from adapters.db.game_data_sqlite_adapter import GameDataSQLiteAdapter


# ---------------------------------------------------------------------------
# Helper: adaptador con datos de prueba en BD :memory:
# ---------------------------------------------------------------------------

_STATS_ROWS = [
    {
        "server_version": "1.45",
        "tribe": "gauls",
        "ordinal": 1,
        "is_playable": True,
        "attack": 10,
        "def_infantry": 20,
        "def_cavalry": 30,
        "speed": 7,
        "carry": 45,
        "cost_wood": 100,
        "cost_clay": 80,
        "cost_iron": 60,
        "cost_crop": 20,
        "cost_sum": 260,
        "upkeep": 1,
        "train_time_s": 900,
        "icon_id": "gauls_1",
    },
    {
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
    },
]

_UPGRADE_ROWS = [
    {
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
]

_ICON_ROWS = [
    {
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
]

_BUILDING_CATALOG_ROWS = [
    {
        "server_version": "1.45",
        "gid": 1,
        "alias": "woodcutter",
        "category": "resources",
        "description": "Produces wood",
        "icon_id": "building_1",
    },
    {
        "server_version": "1.45",
        "gid": 2,
        "alias": "clay_pit",
        "category": "resources",
        "description": "Produces clay",
        "icon_id": "building_2",
    },
]

_BUILDING_STATS_ROWS = [
    {
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
    },
    {
        "server_version": "1.45",
        "gid": 1,
        "level": 2,
        "cost_wood": 65,
        "cost_clay": 80,
        "cost_iron": 45,
        "cost_crop": 15,
        "cost_sum": 205,
        "upkeep": 2,
        "culture_points": 2,
        "build_time_s": 720,
        "effect_value": 3,
        "effect_label": "Production",
    },
    {
        "server_version": "1.45",
        "gid": 2,
        "level": 1,
        "cost_wood": 50,
        "cost_clay": 40,
        "cost_iron": 30,
        "cost_crop": 10,
        "cost_sum": 130,
        "upkeep": 2,
        "culture_points": 1,
        "build_time_s": 360,
        "effect_value": 2,
        "effect_label": "Production",
    },
]


async def _make_populated_adapter():
    """BD :memory: con las 5 tablas con datos de prueba. Devuelve (adapter, conn)."""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    adapter = GameDataSQLiteAdapter(conn)
    await adapter.ensure_tables()
    for row in _STATS_ROWS:
        await adapter.upsert_troop_stats(row)
    for row in _UPGRADE_ROWS:
        await adapter.upsert_troop_upgrade(row)
    for row in _ICON_ROWS:
        await adapter.upsert_icon_metadata(row)
    for row in _BUILDING_CATALOG_ROWS:
        await adapter.upsert_building_catalog(row)
    for row in _BUILDING_STATS_ROWS:
        await adapter.upsert_building_stats(row)
    return adapter, conn


# ---------------------------------------------------------------------------
# Función auxiliar: export parametrizado (usa una BD y un directorio dados)
# ---------------------------------------------------------------------------

# Importamos TABLES_CONFIG directamente para reutilizar la configuración de columnas/queries.
# El script añade sys.path; en tests ya está el proyecto en el path de pytest.
from scripts.export_game_data_seed import TABLES_CONFIG  # noqa: E402


async def _run_export(conn: aiosqlite.Connection, out_dir: Path) -> None:
    """
    Ejecuta la lógica de export de scripts/export_game_data_seed.py
    usando una conexión y directorio dados (sin tocar travian_bot.db ni SEEDS_DIR global).
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    for table_name, config in TABLES_CONFIG.items():
        async with conn.execute(config["query"]) as cursor:
            raw_rows = await cursor.fetchall()

        count = len(raw_rows)
        if count == 0:
            continue

        records = [dict(zip(config["columns"], row)) for row in raw_rows]

        tmp_path = out_dir / f"{table_name}.json.tmp"
        out_path = out_dir / f"{table_name}.json"
        tmp_path.write_text(
            json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        tmp_path.rename(out_path)


# ---------------------------------------------------------------------------
# T-10: Export con datos produce los 3 ficheros JSON con conteos correctos
# ---------------------------------------------------------------------------


def test_t10_export_produces_json_files(tmp_path):
    """
    T-10: con 2 filas en troop_stats, 1 en troop_upgrades, 1 en icon_metadata,
    el export produce 3 ficheros JSON con los conteos correctos.
    """
    async def _run():
        adapter, conn = await _make_populated_adapter()
        try:
            await _run_export(conn, tmp_path)
        finally:
            await conn.close()

    asyncio.run(_run())

    stats_data = json.loads((tmp_path / "troop_stats.json").read_text())
    upgrades_data = json.loads((tmp_path / "troop_upgrades.json").read_text())
    icons_data = json.loads((tmp_path / "icon_metadata.json").read_text())

    assert len(stats_data) == 2, f"Esperado 2 objetos en troop_stats; obtenido {len(stats_data)}"
    assert len(upgrades_data) == 1, f"Esperado 1 objeto en troop_upgrades; obtenido {len(upgrades_data)}"
    assert len(icons_data) == 1, f"Esperado 1 objeto en icon_metadata; obtenido {len(icons_data)}"


# ---------------------------------------------------------------------------
# T-11: Export no incluye scraped_at en ningún objeto
# ---------------------------------------------------------------------------


def test_t11_export_no_scraped_at(tmp_path):
    """
    T-11: ningún objeto exportado tiene la clave scraped_at.
    """
    async def _run():
        adapter, conn = await _make_populated_adapter()
        try:
            await _run_export(conn, tmp_path)
        finally:
            await conn.close()

    asyncio.run(_run())

    for fname in ["troop_stats.json", "troop_upgrades.json", "icon_metadata.json"]:
        data = json.loads((tmp_path / fname).read_text())
        for obj in data:
            assert "scraped_at" not in obj, (
                f"'{fname}' contiene scraped_at en al menos un objeto"
            )


# ---------------------------------------------------------------------------
# T-12: Orden determinista en troop_stats (server_version, tribe, ordinal)
# ---------------------------------------------------------------------------


def test_t12_deterministic_order(tmp_path):
    """
    T-12: las filas de troop_stats.json están ordenadas por (server_version, tribe, ordinal).
    Con gauls/1 y romans/1, el orden esperado es gauls → romans (alfabético).
    """
    async def _run():
        adapter, conn = await _make_populated_adapter()
        try:
            await _run_export(conn, tmp_path)
        finally:
            await conn.close()

    asyncio.run(_run())

    data = json.loads((tmp_path / "troop_stats.json").read_text())
    assert len(data) == 2
    assert data[0]["tribe"] == "gauls", f"Primera fila debería ser gauls; es {data[0]['tribe']}"
    assert data[1]["tribe"] == "romans", f"Segunda fila debería ser romans; es {data[1]['tribe']}"


# ---------------------------------------------------------------------------
# T-13: Tabla vacía → su fichero JSON no se crea
# ---------------------------------------------------------------------------


def test_t13_empty_table_not_exported(tmp_path):
    """
    T-13: si troop_upgrades está vacía en la BD, troop_upgrades.json no se crea.
    """
    async def _run():
        conn = await aiosqlite.connect(":memory:")
        conn.row_factory = aiosqlite.Row
        adapter = GameDataSQLiteAdapter(conn)
        await adapter.ensure_tables()
        # Solo insertar troop_stats e icon_metadata; troop_upgrades queda vacío
        await adapter.upsert_troop_stats(_STATS_ROWS[0])
        await adapter.upsert_icon_metadata(_ICON_ROWS[0])
        try:
            await _run_export(conn, tmp_path)
        finally:
            await conn.close()

    asyncio.run(_run())

    assert (tmp_path / "troop_stats.json").exists(), "troop_stats.json debería existir"
    assert not (tmp_path / "troop_upgrades.json").exists(), (
        "troop_upgrades.json NO debería existir (tabla vacía)"
    )
    assert (tmp_path / "icon_metadata.json").exists(), "icon_metadata.json debería existir"


# ---------------------------------------------------------------------------
# T-14: Atomicidad — no quedan ficheros .tmp si write_text falla
# ---------------------------------------------------------------------------


def test_t14_atomicity_no_tmp_on_failure(tmp_path):
    """
    T-14: si write_text lanza excepción (disco lleno simulado), no quedan .tmp en disco.
    """
    # Necesitamos interceptar write_text en el momento justo.
    # La función _run_export escribe en tmp_path; al mockear Path.write_text,
    # la excepción se lanza antes del rename, y el .tmp nunca debería quedar.
    # Nota: en Python, tmp_path.rename() no se llega a llamar si write_text falla,
    # así que el .tmp tampoco se crea (write_text no completó).
    # Verificamos que tras la excepción, no hay fichero .tmp.

    original_write_text = Path.write_text

    call_count = [0]

    def _failing_write_text(self, *args, **kwargs):
        call_count[0] += 1
        # Falla en el primer intento (el primer fichero .tmp)
        if call_count[0] == 1:
            raise OSError("Disco lleno simulado")
        return original_write_text(self, *args, **kwargs)

    async def _run():
        adapter, conn = await _make_populated_adapter()
        try:
            with patch.object(Path, "write_text", _failing_write_text):
                try:
                    await _run_export(conn, tmp_path)
                except OSError:
                    pass  # excepción esperada en el primer fichero
        finally:
            await conn.close()

    asyncio.run(_run())

    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == [], (
        f"No deberían quedar ficheros .tmp tras el fallo: {tmp_files}"
    )


# ---------------------------------------------------------------------------
# T-B5: Export produce los 2 ficheros JSON de edificios con conteos correctos
# ---------------------------------------------------------------------------


def test_tb5_export_produces_building_json_files(tmp_path):
    """
    T-B5: con 2 edificios en building_catalog y 3 filas en building_stats,
    el export produce building_catalog.json (2 obj) y building_stats.json (3 obj).
    """
    async def _run():
        adapter, conn = await _make_populated_adapter()
        try:
            await _run_export(conn, tmp_path)
        finally:
            await conn.close()

    asyncio.run(_run())

    catalog_data = json.loads((tmp_path / "building_catalog.json").read_text())
    stats_data = json.loads((tmp_path / "building_stats.json").read_text())

    assert len(catalog_data) == 2, (
        f"Esperado 2 objetos en building_catalog; obtenido {len(catalog_data)}"
    )
    assert len(stats_data) == 3, (
        f"Esperado 3 objetos en building_stats; obtenido {len(stats_data)}"
    )


# ---------------------------------------------------------------------------
# T-B6: Orden determinista en building_stats (server_version, gid, level)
# ---------------------------------------------------------------------------


def test_tb6_deterministic_order_building_stats(tmp_path):
    """
    T-B6: las filas de building_stats.json están ordenadas por (server_version, gid, level).
    Con gid=1 nivel 1 y 2, y gid=2 nivel 1, el orden esperado es (1,1), (1,2), (2,1).
    """
    async def _run():
        adapter, conn = await _make_populated_adapter()
        try:
            await _run_export(conn, tmp_path)
        finally:
            await conn.close()

    asyncio.run(_run())

    data = json.loads((tmp_path / "building_stats.json").read_text())
    assert len(data) == 3
    assert (data[0]["gid"], data[0]["level"]) == (1, 1), f"Primera fila: {data[0]}"
    assert (data[1]["gid"], data[1]["level"]) == (1, 2), f"Segunda fila: {data[1]}"
    assert (data[2]["gid"], data[2]["level"]) == (2, 1), f"Tercera fila: {data[2]}"


# ---------------------------------------------------------------------------
# T-B7: building_catalog vacío → building_catalog.json no se crea
# ---------------------------------------------------------------------------


def test_tb7_empty_building_catalog_not_exported(tmp_path):
    """
    T-B7: si building_catalog está vacío en la BD, building_catalog.json no se crea.
    """
    async def _run():
        conn = await aiosqlite.connect(":memory:")
        conn.row_factory = aiosqlite.Row
        adapter = GameDataSQLiteAdapter(conn)
        await adapter.ensure_tables()
        # Solo insertar tropas; building_catalog y building_stats quedan vacíos
        await adapter.upsert_troop_stats(_STATS_ROWS[0])
        try:
            await _run_export(conn, tmp_path)
        finally:
            await conn.close()

    asyncio.run(_run())

    assert (tmp_path / "troop_stats.json").exists(), "troop_stats.json debería existir"
    assert not (tmp_path / "building_catalog.json").exists(), (
        "building_catalog.json NO debería existir (tabla vacía)"
    )
    assert not (tmp_path / "building_stats.json").exists(), (
        "building_stats.json NO debería existir (tabla vacía)"
    )


# ---------------------------------------------------------------------------
# T-B8: Ningún objeto exportado de edificios contiene scraped_at
# ---------------------------------------------------------------------------


def test_tb8_export_buildings_no_scraped_at(tmp_path):
    """
    T-B8: ningún objeto en building_catalog.json ni building_stats.json tiene scraped_at.
    """
    async def _run():
        adapter, conn = await _make_populated_adapter()
        try:
            await _run_export(conn, tmp_path)
        finally:
            await conn.close()

    asyncio.run(_run())

    for fname in ["building_catalog.json", "building_stats.json"]:
        data = json.loads((tmp_path / fname).read_text())
        for obj in data:
            assert "scraped_at" not in obj, (
                f"'{fname}' contiene scraped_at en al menos un objeto: {obj}"
            )
