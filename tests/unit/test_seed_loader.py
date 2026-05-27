"""
Tests unitarios de adapters/db/seed_loader.py.

Cubre:
  T-01  Carga sobre BD vacía (tropas + edificios)
  T-02  Idempotencia — no duplica
  T-03  BD ya poblada — skip completo
  T-04  Directorio de seeds ausente
  T-05  Fichero JSON malformado
  T-06  Tabla desconocida en el directorio de seeds
  T-07  Objeto con campo PK faltante
  T-08  Aislamiento accounts/worlds
  T-09  scraped_at del JSON ignorado (se sobreescribe con datetime.now)
  T-B1  Carga de edificios sobre BD vacía — building_catalog y building_stats
  T-B2  Estado parcial — tropas presentes + edificios vacíos carga solo edificios
  T-B3  Idempotencia por-tabla — tabla llena no se pisa aunque otra esté vacía
  T-B4  Aislamiento accounts/worlds también con seeds de edificios presentes

Patrón del proyecto: tests síncronos con asyncio.run() directo, BD :memory:.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import aiosqlite
import pytest

from adapters.db.game_data_sqlite_adapter import GameDataSQLiteAdapter
from adapters.db.seed_loader import load_if_empty


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_adapter():
    """BD :memory: con tablas creadas. Devuelve (adapter, conn)."""
    async def _create():
        conn = await aiosqlite.connect(":memory:")
        conn.row_factory = aiosqlite.Row
        adapter = GameDataSQLiteAdapter(conn)
        await adapter.ensure_tables()
        return adapter, conn
    return asyncio.run(_create())


# ---------------------------------------------------------------------------
# Datos de seed mínimos para los tests (1 fila por tabla)
# ---------------------------------------------------------------------------

_TROOP_STATS_ROW = {
    "server_version": "1.45",
    "tribe": "romans",
    "ordinal": 1,
    "is_playable": 1,
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

_TROOP_UPGRADES_ROW = {
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

_ICON_METADATA_ROW = {
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


_BUILDING_CATALOG_ROW = {
    "server_version": "1.45",
    "gid": 1,
    "alias": "woodcutter",
    "category": "resources",
    "description": "Produces wood",
    "icon_id": "building_1",
}

_BUILDING_STATS_ROW = {
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


def _write_minimal_seeds(seeds_dir: Path) -> None:
    """Crea los 5 ficheros JSON (tropas + edificios) con 1 fila cada uno en seeds_dir."""
    seeds_dir.mkdir(parents=True, exist_ok=True)
    (seeds_dir / "troop_stats.json").write_text(
        json.dumps([_TROOP_STATS_ROW], ensure_ascii=False), encoding="utf-8"
    )
    (seeds_dir / "troop_upgrades.json").write_text(
        json.dumps([_TROOP_UPGRADES_ROW], ensure_ascii=False), encoding="utf-8"
    )
    (seeds_dir / "icon_metadata.json").write_text(
        json.dumps([_ICON_METADATA_ROW], ensure_ascii=False), encoding="utf-8"
    )
    (seeds_dir / "building_catalog.json").write_text(
        json.dumps([_BUILDING_CATALOG_ROW], ensure_ascii=False), encoding="utf-8"
    )
    (seeds_dir / "building_stats.json").write_text(
        json.dumps([_BUILDING_STATS_ROW], ensure_ascii=False), encoding="utf-8"
    )


def _write_troop_seeds_only(seeds_dir: Path) -> None:
    """Crea solo los 3 ficheros JSON de tropas (sin edificios) en seeds_dir."""
    seeds_dir.mkdir(parents=True, exist_ok=True)
    (seeds_dir / "troop_stats.json").write_text(
        json.dumps([_TROOP_STATS_ROW], ensure_ascii=False), encoding="utf-8"
    )
    (seeds_dir / "troop_upgrades.json").write_text(
        json.dumps([_TROOP_UPGRADES_ROW], ensure_ascii=False), encoding="utf-8"
    )
    (seeds_dir / "icon_metadata.json").write_text(
        json.dumps([_ICON_METADATA_ROW], ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# T-01: Carga sobre BD vacía
# ---------------------------------------------------------------------------


def test_t01_load_on_empty_db(tmp_path):
    """
    T-01: BD vacía + seeds completos → count_troop_stats == 1, list_icons != [].
    """
    _write_minimal_seeds(tmp_path)
    adapter, conn = _make_adapter()
    try:
        asyncio.run(load_if_empty(adapter, tmp_path))
        count = asyncio.run(adapter.count_troop_stats())
        assert count == 1, f"Esperado 1, obtenido {count}"
        icons = asyncio.run(adapter.list_icons())
        assert len(icons) > 0, "Esperaba al menos 1 icono cargado"
    finally:
        asyncio.run(conn.close())


# ---------------------------------------------------------------------------
# T-02: Idempotencia — segunda llamada no duplica
# ---------------------------------------------------------------------------


def test_t02_idempotent_double_load(tmp_path):
    """
    T-02: Llamar load_if_empty dos veces sobre la misma BD no duplica filas.
    """
    _write_minimal_seeds(tmp_path)
    adapter, conn = _make_adapter()
    try:
        asyncio.run(load_if_empty(adapter, tmp_path))
        count_after_first = asyncio.run(adapter.count_troop_stats())

        # Segunda carga: como troop_stats ya tiene filas, debe saltarse
        asyncio.run(load_if_empty(adapter, tmp_path))
        count_after_second = asyncio.run(adapter.count_troop_stats())

        assert count_after_first == count_after_second, (
            f"La segunda carga duplicó filas: {count_after_first} → {count_after_second}"
        )
    finally:
        asyncio.run(conn.close())


# ---------------------------------------------------------------------------
# T-03: BD ya poblada — skip total
# ---------------------------------------------------------------------------


def test_t03_skip_when_db_already_populated(tmp_path):
    """
    T-03: Si ya hay 1 fila en troop_stats (insertada por el scraper),
    load_if_empty no debe añadir las filas del seed.
    """
    # Seeds con una fila diferente a la ya insertada
    seeds_dir = tmp_path / "seeds"
    seeds_dir.mkdir()
    seed_row = {**_TROOP_STATS_ROW, "ordinal": 99}  # fila distinta
    (seeds_dir / "troop_stats.json").write_text(
        json.dumps([seed_row], ensure_ascii=False), encoding="utf-8"
    )
    (seeds_dir / "troop_upgrades.json").write_text("[]", encoding="utf-8")
    (seeds_dir / "icon_metadata.json").write_text("[]", encoding="utf-8")

    adapter, conn = _make_adapter()
    try:
        # Precargar 1 fila "de scraper"
        asyncio.run(adapter.upsert_troop_stats(_TROOP_STATS_ROW))
        count_before = asyncio.run(adapter.count_troop_stats())
        assert count_before == 1

        # load_if_empty debe saltar (count > 0)
        asyncio.run(load_if_empty(adapter, seeds_dir))
        count_after = asyncio.run(adapter.count_troop_stats())

        # Si hubiera cargado el seed, count sería 2 (fila scraper + ordinal 99).
        # Como debe saltar, sigue siendo 1.
        assert count_after == 1, (
            f"load_if_empty no debería cargar cuando ya hay datos: count={count_after}"
        )
    finally:
        asyncio.run(conn.close())


# ---------------------------------------------------------------------------
# T-04: Directorio de seeds ausente
# ---------------------------------------------------------------------------


def test_t04_missing_seeds_dir(tmp_path):
    """
    T-04: seeds_dir que no existe → no lanza excepción, tablas quedan vacías.
    """
    missing_dir = tmp_path / "nonexistent"
    adapter, conn = _make_adapter()
    try:
        # No debe lanzar excepción
        asyncio.run(load_if_empty(adapter, missing_dir))
        count = asyncio.run(adapter.count_troop_stats())
        assert count == 0, "Las tablas deben quedar vacías cuando seeds_dir no existe"
    finally:
        asyncio.run(conn.close())


# ---------------------------------------------------------------------------
# T-05: Fichero JSON malformado
# ---------------------------------------------------------------------------


def test_t05_malformed_json_file(tmp_path):
    """
    T-05: troop_stats.json con JSON inválido no lanza excepción;
    los otros ficheros (troop_upgrades, icon_metadata) sí se cargan.
    """
    seeds_dir = tmp_path
    seeds_dir.mkdir(exist_ok=True)

    # troop_stats.json malformado
    (seeds_dir / "troop_stats.json").write_text("{broken json !!!", encoding="utf-8")
    # troop_upgrades.json válido con 1 fila
    (seeds_dir / "troop_upgrades.json").write_text(
        json.dumps([_TROOP_UPGRADES_ROW], ensure_ascii=False), encoding="utf-8"
    )
    # icon_metadata.json válido con 1 fila
    (seeds_dir / "icon_metadata.json").write_text(
        json.dumps([_ICON_METADATA_ROW], ensure_ascii=False), encoding="utf-8"
    )

    adapter, conn = _make_adapter()
    try:
        # No debe lanzar excepción
        asyncio.run(load_if_empty(adapter, seeds_dir))

        # troop_stats quedó vacío (fichero malformado)
        count = asyncio.run(adapter.count_troop_stats())
        assert count == 0, "troop_stats debería estar vacío (fichero malformado)"

        # icon_metadata sí se cargó
        icons = asyncio.run(adapter.list_icons())
        assert len(icons) == 1, "icon_metadata debería tener 1 fila (cargada correctamente)"
    finally:
        asyncio.run(conn.close())


# ---------------------------------------------------------------------------
# T-06: Tabla desconocida en el directorio de seeds
# ---------------------------------------------------------------------------


def test_t06_unknown_table_in_seeds_dir(tmp_path):
    """
    T-06: fichero de tabla desconocida se omite sin excepción.
    Los ficheros de tablas conocidas sí se procesan.
    """
    seeds_dir = tmp_path
    seeds_dir.mkdir(exist_ok=True)

    # Fichero de tabla desconocida
    (seeds_dir / "unknown_table.json").write_text(
        json.dumps([{"foo": "bar"}], ensure_ascii=False), encoding="utf-8"
    )
    # Seeds válidos
    (seeds_dir / "troop_stats.json").write_text(
        json.dumps([_TROOP_STATS_ROW], ensure_ascii=False), encoding="utf-8"
    )
    (seeds_dir / "troop_upgrades.json").write_text(
        json.dumps([_TROOP_UPGRADES_ROW], ensure_ascii=False), encoding="utf-8"
    )
    (seeds_dir / "icon_metadata.json").write_text(
        json.dumps([_ICON_METADATA_ROW], ensure_ascii=False), encoding="utf-8"
    )

    adapter, conn = _make_adapter()
    try:
        # No debe lanzar excepción
        asyncio.run(load_if_empty(adapter, seeds_dir))
        count = asyncio.run(adapter.count_troop_stats())
        assert count == 1, "troop_stats debería tener 1 fila (tabla conocida cargada)"
    finally:
        asyncio.run(conn.close())


# ---------------------------------------------------------------------------
# T-07: Objeto con campo PK faltante en el JSON
# ---------------------------------------------------------------------------


def test_t07_row_missing_pk_field(tmp_path):
    """
    T-07: fila sin campo 'tribe' en troop_stats.json → esa fila se omite;
    las demás filas del mismo fichero sí se cargan.
    """
    seeds_dir = tmp_path
    seeds_dir.mkdir(exist_ok=True)

    row_ok = _TROOP_STATS_ROW.copy()
    row_bad = {k: v for k, v in _TROOP_STATS_ROW.items() if k != "tribe"}  # falta 'tribe'
    # Cambiamos ordinal de la fila OK para que sea distinta de la fila mala
    row_ok = {**row_ok, "ordinal": 2}

    (seeds_dir / "troop_stats.json").write_text(
        json.dumps([row_bad, row_ok], ensure_ascii=False), encoding="utf-8"
    )
    (seeds_dir / "troop_upgrades.json").write_text("[]", encoding="utf-8")
    (seeds_dir / "icon_metadata.json").write_text("[]", encoding="utf-8")

    adapter, conn = _make_adapter()
    try:
        # No debe lanzar excepción
        asyncio.run(load_if_empty(adapter, seeds_dir))
        count = asyncio.run(adapter.count_troop_stats())
        # La fila con tribe= debería haber fallado; la fila OK (ordinal=2) debería cargarse
        assert count == 1, (
            f"Esperado 1 fila cargada (la OK); obtenido {count}"
        )
    finally:
        asyncio.run(conn.close())


# ---------------------------------------------------------------------------
# T-08: Aislamiento accounts/worlds
# ---------------------------------------------------------------------------


def test_t08_accounts_worlds_isolation(tmp_path):
    """
    T-08: después de load_if_empty las tablas accounts y worlds tienen 0 filas.
    Verifica que el seed nunca toca esas tablas.
    """
    _write_minimal_seeds(tmp_path)

    # Necesitamos la conexión directa para crear las tablas accounts/worlds
    # y poder verificar que están vacías.
    async def _run():
        conn = await aiosqlite.connect(":memory:")
        conn.row_factory = aiosqlite.Row
        game_adapter = GameDataSQLiteAdapter(conn)
        await game_adapter.ensure_tables()

        # Crear tablas accounts y worlds (para poder hacer COUNT sin error)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY,
                email TEXT,
                password TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS worlds (
                id INTEGER PRIMARY KEY,
                account_id INTEGER,
                server TEXT
            )
        """)
        await conn.commit()

        await load_if_empty(game_adapter, tmp_path)

        async with conn.execute("SELECT COUNT(*) FROM accounts") as cur:
            accounts_count = (await cur.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM worlds") as cur:
            worlds_count = (await cur.fetchone())[0]
        await conn.close()
        return accounts_count, worlds_count

    accounts_count, worlds_count = asyncio.run(_run())
    assert accounts_count == 0, f"accounts debe estar vacía; tiene {accounts_count} filas"
    assert worlds_count == 0, f"worlds debe estar vacía; tiene {worlds_count} filas"


# ---------------------------------------------------------------------------
# T-09: scraped_at del JSON se ignora (el adaptador lo sobreescribe)
# ---------------------------------------------------------------------------


def test_t09_scraped_at_from_json_is_ignored(tmp_path):
    """
    T-09: si un objeto JSON contiene scraped_at, el loader lo elimina antes
    del upsert y la BD tiene el scraped_at de datetime.now(UTC), no el del JSON.
    """
    seeds_dir = tmp_path
    seeds_dir.mkdir(exist_ok=True)

    # icon_metadata con scraped_at fosilizado del pasado
    icon_with_old_scraped = {
        **_ICON_METADATA_ROW,
        "scraped_at": "2020-01-01T00:00:00+00:00",  # timestamp antiguo
    }
    (seeds_dir / "icon_metadata.json").write_text(
        json.dumps([icon_with_old_scraped], ensure_ascii=False), encoding="utf-8"
    )
    (seeds_dir / "troop_stats.json").write_text(
        json.dumps([_TROOP_STATS_ROW], ensure_ascii=False), encoding="utf-8"
    )
    (seeds_dir / "troop_upgrades.json").write_text(
        json.dumps([_TROOP_UPGRADES_ROW], ensure_ascii=False), encoding="utf-8"
    )

    adapter, conn = _make_adapter()
    try:
        asyncio.run(load_if_empty(adapter, seeds_dir))
        icon = asyncio.run(adapter.get_icon_metadata("romans_1"))
        assert icon is not None, "El icono debería haberse cargado"
        # El scraped_at debe ser "ahora" (2026...), NO "2020-..."
        assert not icon["scraped_at"].startswith("2020"), (
            f"scraped_at del JSON no debería haberse usado: {icon['scraped_at']}"
        )
        assert icon["scraped_at"].startswith("2026"), (
            f"scraped_at debería ser del momento de carga (2026...): {icon['scraped_at']}"
        )
    finally:
        asyncio.run(conn.close())


# ---------------------------------------------------------------------------
# T-B1: Carga de edificios sobre BD vacía
# ---------------------------------------------------------------------------


def test_tb1_buildings_loaded_on_empty_db(tmp_path):
    """
    T-B1: BD vacía + seeds completos (tropas + edificios) → building_catalog
    y building_stats se cargan correctamente.
    """
    _write_minimal_seeds(tmp_path)
    adapter, conn = _make_adapter()
    try:
        asyncio.run(load_if_empty(adapter, tmp_path))
        # Verificar building_catalog
        catalog_count = asyncio.run(adapter.count_rows("building_catalog"))
        assert catalog_count == 1, f"building_catalog esperaba 1 fila; obtuvo {catalog_count}"
        # Verificar building_stats
        stats_count = asyncio.run(adapter.count_rows("building_stats"))
        assert stats_count == 1, f"building_stats esperaba 1 fila; obtuvo {stats_count}"
        # Verificar que el contenido es correcto
        building = asyncio.run(adapter.get_building_catalog(1))
        assert building is not None, "Edificio gid=1 debería existir"
        assert building["alias"] == "woodcutter"
        levels = asyncio.run(adapter.get_building_stats(1))
        assert len(levels) == 1, "Edificio gid=1 debería tener 1 nivel"
        assert levels[0]["level"] == 1
    finally:
        asyncio.run(conn.close())


# ---------------------------------------------------------------------------
# T-B2: Estado parcial — tropas presentes, edificios vacíos → solo edificios se cargan
# ---------------------------------------------------------------------------


def test_tb2_partial_state_loads_only_empty_tables(tmp_path):
    """
    T-B2: estado parcial: tropas ya presentes (scraper corrió) + edificios vacíos.
    load_if_empty debe cargar SOLO los edificios, sin tocar las tropas.
    """
    _write_minimal_seeds(tmp_path)
    adapter, conn = _make_adapter()
    try:
        # Simular scraper previo: tropas ya presentes con datos "distintos" del seed
        troop_from_scraper = {**_TROOP_STATS_ROW, "attack": 999}  # distinto del seed
        asyncio.run(adapter.upsert_troop_stats(troop_from_scraper))
        # Verificar estado inicial
        assert asyncio.run(adapter.count_rows("troop_stats")) == 1
        assert asyncio.run(adapter.count_rows("building_catalog")) == 0
        assert asyncio.run(adapter.count_rows("building_stats")) == 0

        # Ejecutar loader — debería cargar edificios pero NO pisar tropas
        asyncio.run(load_if_empty(adapter, tmp_path))

        # Las tropas NO se tocan: el valor del scraper (999) debe mantenerse
        troop = asyncio.run(adapter.get_troop_stats(__import__("core.entities.tribe", fromlist=["Tribe"]).Tribe.ROMANS, 1))
        assert troop is not None
        assert troop["attack"] == 999, (
            f"El loader pisó los datos del scraper: attack={troop['attack']} (esperado 999)"
        )
        # Los edificios SÍ se cargan (estaban vacíos)
        assert asyncio.run(adapter.count_rows("building_catalog")) == 1, \
            "building_catalog debería haberse cargado"
        assert asyncio.run(adapter.count_rows("building_stats")) == 1, \
            "building_stats debería haberse cargado"
    finally:
        asyncio.run(conn.close())


# ---------------------------------------------------------------------------
# T-B3: Idempotencia por-tabla — tabla llena no se pisa aunque otra esté vacía
# ---------------------------------------------------------------------------


def test_tb3_per_table_idempotency(tmp_path):
    """
    T-B3: si building_catalog ya tiene datos, load_if_empty no lo sobreescribe,
    aunque building_stats esté vacío (o viceversa). Cada tabla decide por sí sola.
    """
    # Crear seeds con 2 edificios en building_catalog y 1 en building_stats
    seeds_dir = tmp_path
    seeds_dir.mkdir(exist_ok=True)

    catalog_row_1 = _BUILDING_CATALOG_ROW.copy()
    catalog_row_2 = {**_BUILDING_CATALOG_ROW, "gid": 2, "alias": "clay_pit"}

    (seeds_dir / "troop_stats.json").write_text(
        json.dumps([_TROOP_STATS_ROW], ensure_ascii=False), encoding="utf-8"
    )
    (seeds_dir / "troop_upgrades.json").write_text("[]", encoding="utf-8")
    (seeds_dir / "icon_metadata.json").write_text("[]", encoding="utf-8")
    (seeds_dir / "building_catalog.json").write_text(
        json.dumps([catalog_row_1, catalog_row_2], ensure_ascii=False), encoding="utf-8"
    )
    (seeds_dir / "building_stats.json").write_text(
        json.dumps([_BUILDING_STATS_ROW], ensure_ascii=False), encoding="utf-8"
    )

    adapter, conn = _make_adapter()
    try:
        # Precargar building_catalog con datos "del scraper" (distintos del seed)
        catalog_from_scraper = {**catalog_row_1, "description": "SCRAPER_DATA"}
        asyncio.run(adapter.upsert_building_catalog(catalog_from_scraper))
        assert asyncio.run(adapter.count_rows("building_catalog")) == 1

        # Ejecutar loader
        asyncio.run(load_if_empty(adapter, seeds_dir))

        # building_catalog sigue en 1 (el loader no lo cargó porque ya tenía datos)
        count_catalog = asyncio.run(adapter.count_rows("building_catalog"))
        assert count_catalog == 1, (
            f"building_catalog no debería haber sido tocado (esperado 1, obtenido {count_catalog})"
        )
        # La descripción del scraper se conserva (no fue pisada por el seed)
        building = asyncio.run(adapter.get_building_catalog(1))
        assert building is not None
        assert building["description"] == "SCRAPER_DATA", (
            f"El seed pisó datos del scraper: description='{building['description']}'"
        )
        # building_stats sí se cargó (estaba vacío)
        count_stats = asyncio.run(adapter.count_rows("building_stats"))
        assert count_stats == 1, (
            f"building_stats debería haberse cargado (esperado 1, obtenido {count_stats})"
        )
    finally:
        asyncio.run(conn.close())


# ---------------------------------------------------------------------------
# T-B4: Aislamiento accounts/worlds también con seeds de edificios
# ---------------------------------------------------------------------------


def test_tb4_accounts_worlds_isolation_with_buildings(tmp_path):
    """
    T-B4: después de load_if_empty con seeds de tropas + edificios,
    accounts y worlds siguen teniendo 0 filas.
    """
    _write_minimal_seeds(tmp_path)

    async def _run():
        conn = await aiosqlite.connect(":memory:")
        conn.row_factory = aiosqlite.Row
        game_adapter = GameDataSQLiteAdapter(conn)
        await game_adapter.ensure_tables()

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY,
                email TEXT,
                password TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS worlds (
                id INTEGER PRIMARY KEY,
                account_id INTEGER,
                server TEXT
            )
        """)
        await conn.commit()

        await load_if_empty(game_adapter, tmp_path)

        async with conn.execute("SELECT COUNT(*) FROM accounts") as cur:
            accounts_count = (await cur.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM worlds") as cur:
            worlds_count = (await cur.fetchone())[0]
        await conn.close()
        return accounts_count, worlds_count

    accounts_count, worlds_count = asyncio.run(_run())
    assert accounts_count == 0, f"accounts debe estar vacía; tiene {accounts_count} filas"
    assert worlds_count == 0, f"worlds debe estar vacía; tiene {worlds_count} filas"
