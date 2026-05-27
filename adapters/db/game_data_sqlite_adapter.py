"""
Adaptador SQLite para datos de juego (GameDataPort).

Implementa GameDataPort usando aiosqlite con SQL crudo (sin Alembic, sin ORM),
coherente con el patrón del proyecto (ver adapters/db/database.py).

Las tablas que gestiona son:
  - troop_stats      — stats base de cada tropa (PK: server_version, tribe, ordinal)
  - troop_upgrades   — tabla de mejoras de herrería (PK: server_version, tribe, ordinal, level, stat_name)
  - icon_metadata    — metadatos de iconos PNG en disco (PK: icon_id)
  - building_stats   — costes por nivel de edificio (PK: server_version, gid, level)
  - building_catalog — metadatos de edificio: categoría, descripción, icono (PK: server_version, gid)

Todas las operaciones de escritura son UPSERT idempotentes (INSERT OR REPLACE).
"""
from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite

from core.entities.tribe import Tribe
from core.ports.game_data_port import GameDataPort

# ---------------------------------------------------------------------------
# DDL — se ejecuta una sola vez si las tablas no existen
# ---------------------------------------------------------------------------

_CREATE_TROOP_STATS = """
CREATE TABLE IF NOT EXISTS troop_stats (
    server_version  TEXT    NOT NULL,
    tribe           TEXT    NOT NULL,
    ordinal         INTEGER NOT NULL,
    is_playable     INTEGER NOT NULL DEFAULT 1,
    attack          INTEGER,
    def_infantry    INTEGER,
    def_cavalry     INTEGER,
    speed           INTEGER,
    carry           INTEGER,
    cost_wood       INTEGER,
    cost_clay       INTEGER,
    cost_iron       INTEGER,
    cost_crop       INTEGER,
    cost_sum        INTEGER,
    upkeep          INTEGER,
    train_time_s    INTEGER,
    icon_id         TEXT,
    scraped_at      TEXT NOT NULL,
    PRIMARY KEY (server_version, tribe, ordinal)
);
"""

_CREATE_TROOP_UPGRADES = """
CREATE TABLE IF NOT EXISTS troop_upgrades (
    server_version  TEXT    NOT NULL,
    tribe           TEXT    NOT NULL,
    ordinal         INTEGER NOT NULL,
    level           INTEGER NOT NULL,
    stat_name       TEXT    NOT NULL,
    stat_value      REAL    NOT NULL,
    cost_wood       INTEGER,
    cost_clay       INTEGER,
    cost_iron       INTEGER,
    cost_crop       INTEGER,
    cost_sum        INTEGER,
    upgrade_time_s  INTEGER,
    scraped_at      TEXT NOT NULL,
    PRIMARY KEY (server_version, tribe, ordinal, level, stat_name)
);
"""

_CREATE_ICON_METADATA = """
CREATE TABLE IF NOT EXISTS icon_metadata (
    icon_id         TEXT    PRIMARY KEY,
    icon_type       TEXT    NOT NULL,
    tribe           TEXT,
    ordinal         INTEGER,
    stat_name       TEXT,
    file_path       TEXT    NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    width_px        INTEGER NOT NULL,
    height_px       INTEGER NOT NULL,
    scraped_at      TEXT    NOT NULL
);
"""

_CREATE_BUILDING_STATS = """
CREATE TABLE IF NOT EXISTS building_stats (
    server_version   TEXT    NOT NULL,
    gid              INTEGER NOT NULL,
    level            INTEGER NOT NULL,
    cost_wood        INTEGER,
    cost_clay        INTEGER,
    cost_iron        INTEGER,
    cost_crop        INTEGER,
    cost_sum         INTEGER,
    upkeep           INTEGER,
    culture_points   INTEGER,
    build_time_s     INTEGER,
    effect_value     INTEGER,
    effect_label     TEXT,
    scraped_at       TEXT    NOT NULL,
    PRIMARY KEY (server_version, gid, level)
);
"""

_CREATE_BUILDING_CATALOG = """
CREATE TABLE IF NOT EXISTS building_catalog (
    server_version   TEXT    NOT NULL,
    gid              INTEGER NOT NULL,
    alias            TEXT    NOT NULL,
    category         TEXT    NOT NULL,
    description      TEXT    NOT NULL DEFAULT "",
    icon_id          TEXT,
    scraped_at       TEXT    NOT NULL,
    PRIMARY KEY (server_version, gid)
);
"""


async def _create_tables_if_not_exist(conn: aiosqlite.Connection) -> None:
    """Crea todas las tablas si no existen. Idempotente."""
    await conn.execute(_CREATE_TROOP_STATS)
    await conn.execute(_CREATE_TROOP_UPGRADES)
    await conn.execute(_CREATE_ICON_METADATA)
    await conn.execute(_CREATE_BUILDING_STATS)
    await conn.execute(_CREATE_BUILDING_CATALOG)
    await conn.commit()


# ---------------------------------------------------------------------------
# Adaptador
# ---------------------------------------------------------------------------


class GameDataSQLiteAdapter(GameDataPort):
    """
    Implementación de GameDataPort sobre SQLite con aiosqlite.

    Recibe la conexión como inyección de dependencia (no la abre internamente)
    para facilitar el testing con BD en memoria (":memory:").
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def ensure_tables(self) -> None:
        """Crea las tablas si no existen. Llamar una vez en el startup."""
        await _create_tables_if_not_exist(self._conn)

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------

    async def get_troop_stats(
        self,
        tribe: Tribe,
        ordinal: int,
        server_version: str = "1.45",
    ) -> dict | None:
        """Devuelve los stats base de una tropa, o None si no existe."""
        async with self._conn.execute(
            """
            SELECT server_version, tribe, ordinal, is_playable,
                   attack, def_infantry, def_cavalry, speed, carry,
                   cost_wood, cost_clay, cost_iron, cost_crop, cost_sum,
                   upkeep, train_time_s, icon_id
            FROM troop_stats
            WHERE server_version = ? AND tribe = ? AND ordinal = ?
            """,
            (server_version, tribe.value, ordinal),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_stats_dict(row)

    async def get_all_troop_stats(
        self,
        tribe: Tribe,
        server_version: str = "1.45",
    ) -> list[dict]:
        """Devuelve todos los stats de una tribu ordenados por ordinal."""
        async with self._conn.execute(
            """
            SELECT server_version, tribe, ordinal, is_playable,
                   attack, def_infantry, def_cavalry, speed, carry,
                   cost_wood, cost_clay, cost_iron, cost_crop, cost_sum,
                   upkeep, train_time_s, icon_id
            FROM troop_stats
            WHERE server_version = ? AND tribe = ?
            ORDER BY ordinal
            """,
            (server_version, tribe.value),
        ) as cursor:
            rows = await cursor.fetchall()
        return [_row_to_stats_dict(r) for r in rows]

    async def get_troop_upgrades(
        self,
        tribe: Tribe,
        ordinal: int,
        server_version: str = "1.45",
    ) -> list[dict]:
        """Devuelve la tabla de mejoras de herrería de una tropa."""
        async with self._conn.execute(
            """
            SELECT level, stat_name, stat_value,
                   cost_wood, cost_clay, cost_iron, cost_crop, cost_sum,
                   upgrade_time_s
            FROM troop_upgrades
            WHERE server_version = ? AND tribe = ? AND ordinal = ?
            ORDER BY level, stat_name
            """,
            (server_version, tribe.value, ordinal),
        ) as cursor:
            rows = await cursor.fetchall()
        return [_row_to_upgrade_dict(r) for r in rows]

    async def get_icon_metadata(self, icon_id: str) -> dict | None:
        """Devuelve los metadatos de un icono por su icon_id, o None."""
        async with self._conn.execute(
            """
            SELECT icon_id, icon_type, tribe, ordinal, stat_name,
                   file_path, file_size_bytes, width_px, height_px, scraped_at
            FROM icon_metadata
            WHERE icon_id = ?
            """,
            (icon_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_icon_dict(row)

    async def list_icons(
        self,
        icon_type: str | None = None,
        tribe: str | None = None,
    ) -> list[dict]:
        """
        Devuelve lista de metadatos de iconos con filtros opcionales.
        Lista vacía si ningún icono cumple los filtros.
        """
        query = """
            SELECT icon_id, icon_type, tribe, ordinal, stat_name,
                   file_path, file_size_bytes, width_px, height_px, scraped_at
            FROM icon_metadata
            WHERE 1=1
        """
        params: list = []
        if icon_type is not None:
            query += " AND icon_type = ?"
            params.append(icon_type)
        if tribe is not None:
            query += " AND tribe = ?"
            params.append(tribe)
        query += " ORDER BY icon_id"

        async with self._conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
        return [_row_to_icon_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Escrituras (UPSERT idempotentes)
    # ------------------------------------------------------------------

    async def upsert_troop_stats(self, stats: dict) -> None:
        """Inserta o actualiza los stats de una tropa."""
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            """
            INSERT OR REPLACE INTO troop_stats (
                server_version, tribe, ordinal, is_playable,
                attack, def_infantry, def_cavalry, speed, carry,
                cost_wood, cost_clay, cost_iron, cost_crop, cost_sum,
                upkeep, train_time_s, icon_id, scraped_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                stats["server_version"],
                stats["tribe"],
                stats["ordinal"],
                int(stats.get("is_playable", True)),
                stats.get("attack"),
                stats.get("def_infantry"),
                stats.get("def_cavalry"),
                stats.get("speed"),
                stats.get("carry"),
                stats.get("cost_wood"),
                stats.get("cost_clay"),
                stats.get("cost_iron"),
                stats.get("cost_crop"),
                stats.get("cost_sum"),
                stats.get("upkeep"),
                stats.get("train_time_s"),
                stats.get("icon_id"),
                now,
            ),
        )
        await self._conn.commit()

    async def upsert_troop_upgrade(self, upgrade: dict) -> None:
        """Inserta o actualiza una fila de la tabla de mejoras."""
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            """
            INSERT OR REPLACE INTO troop_upgrades (
                server_version, tribe, ordinal, level, stat_name, stat_value,
                cost_wood, cost_clay, cost_iron, cost_crop, cost_sum,
                upgrade_time_s, scraped_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                upgrade["server_version"],
                upgrade["tribe"],
                upgrade["ordinal"],
                upgrade["level"],
                upgrade["stat_name"],
                upgrade["stat_value"],
                upgrade.get("cost_wood"),
                upgrade.get("cost_clay"),
                upgrade.get("cost_iron"),
                upgrade.get("cost_crop"),
                upgrade.get("cost_sum"),
                upgrade.get("upgrade_time_s"),
                now,
            ),
        )
        await self._conn.commit()

    async def upsert_icon_metadata(self, icon: dict) -> None:
        """Inserta o actualiza los metadatos de un icono."""
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            """
            INSERT OR REPLACE INTO icon_metadata (
                icon_id, icon_type, tribe, ordinal, stat_name,
                file_path, file_size_bytes, width_px, height_px, scraped_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                icon["icon_id"],
                icon["icon_type"],
                icon.get("tribe"),
                icon.get("ordinal"),
                icon.get("stat_name"),
                icon["file_path"],
                icon["file_size_bytes"],
                icon["width_px"],
                icon["height_px"],
                now,
            ),
        )
        await self._conn.commit()

    # ------------------------------------------------------------------
    # Edificios — métodos añadidos para la feature kirilloid-edificios
    # ------------------------------------------------------------------

    async def get_building_stats(
        self,
        gid: int,
        server_version: str = "1.45",
    ) -> list[dict]:
        """Devuelve la lista de niveles de un edificio ordenados por level."""
        async with self._conn.execute(
            """
            SELECT server_version, gid, level,
                   cost_wood, cost_clay, cost_iron, cost_crop, cost_sum,
                   upkeep, culture_points, build_time_s, effect_value, effect_label
            FROM building_stats
            WHERE server_version = ? AND gid = ?
            ORDER BY level
            """,
            (server_version, gid),
        ) as cursor:
            rows = await cursor.fetchall()
        return [_row_to_building_stats_dict(r) for r in rows]

    async def get_all_building_stats(
        self,
        server_version: str = "1.45",
    ) -> dict[int, list[dict]]:
        """Devuelve {gid: [filas ordenadas por level]} para todos los edificios."""
        async with self._conn.execute(
            """
            SELECT server_version, gid, level,
                   cost_wood, cost_clay, cost_iron, cost_crop, cost_sum,
                   upkeep, culture_points, build_time_s, effect_value, effect_label
            FROM building_stats
            WHERE server_version = ?
            ORDER BY gid, level
            """,
            (server_version,),
        ) as cursor:
            rows = await cursor.fetchall()
        result: dict[int, list[dict]] = {}
        for r in rows:
            d = _row_to_building_stats_dict(r)
            result.setdefault(d["gid"], []).append(d)
        return result

    async def upsert_building_stats(self, stats: dict) -> None:
        """Inserta o actualiza una fila de building_stats (UPSERT idempotente)."""
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            """
            INSERT OR REPLACE INTO building_stats (
                server_version, gid, level,
                cost_wood, cost_clay, cost_iron, cost_crop, cost_sum,
                upkeep, culture_points, build_time_s,
                effect_value, effect_label, scraped_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                stats["server_version"],
                stats["gid"],
                stats["level"],
                stats.get("cost_wood"),
                stats.get("cost_clay"),
                stats.get("cost_iron"),
                stats.get("cost_crop"),
                stats.get("cost_sum"),
                stats.get("upkeep"),
                stats.get("culture_points"),
                stats.get("build_time_s"),
                stats.get("effect_value"),
                stats.get("effect_label", ""),
                now,
            ),
        )
        await self._conn.commit()

    # ------------------------------------------------------------------
    # Gate de seed — método añadido para la feature seed-datos-juego-tropas
    # ------------------------------------------------------------------

    async def count_troop_stats(self) -> int:
        """
        Devuelve el número de filas en troop_stats.
        0 indica que la tabla está vacía y el seed debe cargarse.
        """
        async with self._conn.execute("SELECT COUNT(*) FROM troop_stats") as cursor:
            row = await cursor.fetchone()
        return row[0]

    async def upsert_building_catalog(self, catalog: dict) -> None:
        """Inserta o actualiza un registro de building_catalog (UPSERT idempotente)."""
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            """
            INSERT OR REPLACE INTO building_catalog (
                server_version, gid, alias, category, description, icon_id, scraped_at
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                catalog["server_version"],
                catalog["gid"],
                catalog["alias"],
                catalog["category"],
                catalog.get("description", ""),
                catalog.get("icon_id"),
                now,
            ),
        )
        await self._conn.commit()

    async def get_building_catalog(
        self,
        gid: int,
        server_version: str = "1.45",
    ) -> dict | None:
        """Devuelve los metadatos de un edificio, o None si no existe."""
        async with self._conn.execute(
            """
            SELECT server_version, gid, alias, category, description, icon_id, scraped_at
            FROM building_catalog
            WHERE server_version = ? AND gid = ?
            """,
            (server_version, gid),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_building_catalog_dict(row)

    async def get_all_building_catalog(
        self,
        server_version: str = "1.45",
    ) -> dict[int, dict]:
        """Devuelve {gid: meta_dict} con los metadatos de todos los edificios."""
        async with self._conn.execute(
            """
            SELECT server_version, gid, alias, category, description, icon_id, scraped_at
            FROM building_catalog
            WHERE server_version = ?
            ORDER BY gid
            """,
            (server_version,),
        ) as cursor:
            rows = await cursor.fetchall()
        return {r[1]: _row_to_building_catalog_dict(r) for r in rows}


# ---------------------------------------------------------------------------
# Helpers de conversión row → dict
# ---------------------------------------------------------------------------


def _row_to_stats_dict(row: aiosqlite.Row) -> dict:
    """Convierte una fila de troop_stats en dict con keys tipadas."""
    # row puede ser aiosqlite.Row (acceso por índice) o sqlite3.Row (acceso por nombre)
    # Usamos índice posicional que funciona en ambos casos.
    return {
        "server_version": row[0],
        "tribe": row[1],
        "ordinal": row[2],
        "is_playable": bool(row[3]),
        "attack": row[4],
        "def_infantry": row[5],
        "def_cavalry": row[6],
        "speed": row[7],
        "carry": row[8],
        "cost_wood": row[9],
        "cost_clay": row[10],
        "cost_iron": row[11],
        "cost_crop": row[12],
        "cost_sum": row[13],
        "upkeep": row[14],
        "train_time_s": row[15],
        "icon_id": row[16],
    }


def _row_to_upgrade_dict(row: aiosqlite.Row) -> dict:
    """Convierte una fila de troop_upgrades en dict."""
    return {
        "level": row[0],
        "stat_name": row[1],
        "stat_value": row[2],
        "cost_wood": row[3],
        "cost_clay": row[4],
        "cost_iron": row[5],
        "cost_crop": row[6],
        "cost_sum": row[7],
        "upgrade_time_s": row[8],
    }


def _row_to_icon_dict(row: aiosqlite.Row) -> dict:
    """Convierte una fila de icon_metadata en dict."""
    return {
        "icon_id": row[0],
        "icon_type": row[1],
        "tribe": row[2],
        "ordinal": row[3],
        "stat_name": row[4],
        "file_path": row[5],
        "file_size_bytes": row[6],
        "width_px": row[7],
        "height_px": row[8],
        "scraped_at": row[9],
    }


def _row_to_building_stats_dict(row: aiosqlite.Row) -> dict:
    """Convierte una fila de building_stats en dict con keys tipadas."""
    return {
        "server_version": row[0],
        "gid": row[1],
        "level": row[2],
        "cost_wood": row[3],
        "cost_clay": row[4],
        "cost_iron": row[5],
        "cost_crop": row[6],
        "cost_sum": row[7],
        "upkeep": row[8],
        "culture_points": row[9],
        "build_time_s": row[10],
        "effect_value": row[11],
        "effect_label": row[12],
    }


def _row_to_building_catalog_dict(row: aiosqlite.Row) -> dict:
    """Convierte una fila de building_catalog en dict."""
    return {
        "server_version": row[0],
        "gid": row[1],
        "alias": row[2],
        "category": row[3],
        "description": row[4],
        "icon_id": row[5],
        "scraped_at": row[6],
    }
