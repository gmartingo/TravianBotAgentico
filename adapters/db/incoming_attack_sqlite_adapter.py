"""
Adaptador SQLite para el radar de ataques entrantes (IncomingAttackDbPort).

Implementa IncomingAttackDbPort usando aiosqlite con SQL crudo (sin Alembic, sin ORM),
coherente con el patrón del proyecto (ver adapters/db/database.py y
adapters/db/attack_report_sqlite_adapter.py).

Tabla que gestiona:
  - incoming_attacks  — ataques entrantes pre-combate por mundo

DDL idempotente. FK world_id → worlds(id) ON DELETE CASCADE.
Índice (world_id, impact_at) para consultas eficientes.

Ver spec docs/specs/radar-ataques-entrantes.md §7 para el DDL completo.
Añadido en la feature radar-ataques-entrantes (2026-06-05).
"""
from __future__ import annotations

import logging

import aiosqlite

from core.ports.incoming_attack_db_port import IncomingAttackDbPort, IncomingAttackRecord

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DDL — idempotente
# ---------------------------------------------------------------------------

_CREATE_INCOMING_ATTACKS = """
CREATE TABLE IF NOT EXISTS incoming_attacks (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id               INTEGER NOT NULL
                               REFERENCES worlds(id) ON DELETE CASCADE,

    -- Aldea propia atacada
    village_game_id        INTEGER NOT NULL,
    village_name           TEXT,
    village_coord_x        INTEGER,
    village_coord_y        INTEGER,

    -- Datos del ataque (Componente B)
    attack_count           INTEGER NOT NULL DEFAULT 1,
    impact_at              TEXT,
    rally_point_href       TEXT,

    -- Datos del atacante (Componentes C+D — NULL hasta que estén disponibles)
    attacker_name          TEXT,
    origin_village_name    TEXT,
    origin_village_coord_x INTEGER,
    origin_village_coord_y INTEGER,
    operation_type         TEXT,
    origin_village_href    TEXT,

    -- Snapshot de la aldea atacante (Componente D — NULL hasta que esté disponible)
    attacker_snapshot_json TEXT,

    -- Metadatos
    detected_at            TEXT NOT NULL,
    source                 TEXT NOT NULL,
    updated_at             TEXT NOT NULL,

    -- Unicidad: un ataque = una aldea + un momento de impacto, en un mundo
    UNIQUE (world_id, village_game_id, impact_at)
);
"""

_CREATE_IDX_WORLD_IMPACT = """
CREATE INDEX IF NOT EXISTS idx_incoming_attacks_world_impact
    ON incoming_attacks (world_id, impact_at);
"""


# ---------------------------------------------------------------------------
# Adaptador
# ---------------------------------------------------------------------------

class IncomingAttackSQLiteAdapter(IncomingAttackDbPort):
    """Implementación SQLite del puerto de persistencia del radar de ataques entrantes."""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    # -----------------------------------------------------------------------
    # DDL
    # -----------------------------------------------------------------------

    async def ensure_tables(self) -> None:
        """Crea la tabla y el índice si no existen. DDL idempotente."""
        async with self._conn.executescript(
            _CREATE_INCOMING_ATTACKS + _CREATE_IDX_WORLD_IMPACT
        ):
            pass
        await self._conn.commit()

    # -----------------------------------------------------------------------
    # Escritura
    # -----------------------------------------------------------------------

    async def upsert_attack(self, record: IncomingAttackRecord) -> int:
        """
        Inserta o actualiza un ataque entrante.

        Unicidad: (world_id, village_game_id, impact_at).
        ON CONFLICT DO UPDATE: actualiza campos mutables y updated_at.

        Devuelve el id del registro insertado o actualizado.
        """
        async with self._conn.execute(
            """
            INSERT INTO incoming_attacks (
                world_id, village_game_id, village_name,
                village_coord_x, village_coord_y,
                attack_count, impact_at, rally_point_href,
                attacker_name, origin_village_name,
                origin_village_coord_x, origin_village_coord_y,
                operation_type, origin_village_href,
                attacker_snapshot_json,
                detected_at, source, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (world_id, village_game_id, impact_at) DO UPDATE SET
                attack_count           = excluded.attack_count,
                village_name           = COALESCE(excluded.village_name, incoming_attacks.village_name),
                village_coord_x        = COALESCE(excluded.village_coord_x, incoming_attacks.village_coord_x),
                village_coord_y        = COALESCE(excluded.village_coord_y, incoming_attacks.village_coord_y),
                rally_point_href       = COALESCE(excluded.rally_point_href, incoming_attacks.rally_point_href),
                attacker_name          = COALESCE(excluded.attacker_name, incoming_attacks.attacker_name),
                origin_village_name    = COALESCE(excluded.origin_village_name, incoming_attacks.origin_village_name),
                origin_village_coord_x = COALESCE(excluded.origin_village_coord_x, incoming_attacks.origin_village_coord_x),
                origin_village_coord_y = COALESCE(excluded.origin_village_coord_y, incoming_attacks.origin_village_coord_y),
                operation_type         = COALESCE(excluded.operation_type, incoming_attacks.operation_type),
                origin_village_href    = COALESCE(excluded.origin_village_href, incoming_attacks.origin_village_href),
                attacker_snapshot_json = COALESCE(excluded.attacker_snapshot_json, incoming_attacks.attacker_snapshot_json),
                source                 = excluded.source,
                updated_at             = excluded.updated_at
            """,
            (
                record.world_id,
                record.village_game_id,
                record.village_name,
                record.village_coord_x,
                record.village_coord_y,
                record.attack_count,
                record.impact_at,
                record.rally_point_href,
                record.attacker_name,
                record.origin_village_name,
                record.origin_village_coord_x,
                record.origin_village_coord_y,
                record.operation_type,
                record.origin_village_href,
                record.attacker_snapshot_json,
                record.detected_at,
                record.source,
                record.updated_at,
            ),
        ) as cursor:
            row_id = cursor.lastrowid

        await self._conn.commit()

        # lastrowid puede ser None si el ON CONFLICT DO UPDATE no inserta una fila nueva.
        # En ese caso recuperamos el id de la fila existente.
        if row_id is None or row_id == 0:
            async with self._conn.execute(
                """
                SELECT id FROM incoming_attacks
                WHERE world_id = ? AND village_game_id = ?
                  AND (impact_at = ? OR (impact_at IS NULL AND ? IS NULL))
                """,
                (record.world_id, record.village_game_id, record.impact_at, record.impact_at),
            ) as cur2:
                existing = await cur2.fetchone()
            row_id = existing["id"] if existing else 0

        return row_id or 0

    # -----------------------------------------------------------------------
    # Lectura
    # -----------------------------------------------------------------------

    async def list_attacks(
        self,
        world_id: int,
        include_past: bool = False,
        village_game_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """
        Lista ataques entrantes para un mundo, con paginación y filtros opcionales.

        include_past=False: solo ataques con impact_at IS NULL (sin timer todavía)
            o impact_at > datetime('now') (aún no han impactado).
            Postura conservadora (RT-05): los ataques sin timer se muestran como pendientes.
        include_past=True: todos los registros sin filtro temporal.

        Devuelve: { total: int, items: list[dict] }
        """
        where_parts = ["world_id = ?"]
        params: list = [world_id]

        if not include_past:
            # Usar datetime(impact_at) para parsear correctamente el ISO-8601 con zona
            # (Python genera "2026-06-05T14:30:18+00:00" que SQLite no compara bien
            # directamente con datetime('now'). datetime() normaliza ambos a UTC).
            where_parts.append(
                "(impact_at IS NULL OR datetime(impact_at) > datetime('now'))"
            )

        if village_game_id is not None:
            where_parts.append("village_game_id = ?")
            params.append(village_game_id)

        where_clause = "WHERE " + " AND ".join(where_parts)

        # Total
        count_sql = f"SELECT COUNT(*) AS cnt FROM incoming_attacks {where_clause}"
        async with self._conn.execute(count_sql, params) as cursor:
            count_row = await cursor.fetchone()
        total = count_row["cnt"] if count_row else 0

        # Items paginados
        items_sql = f"""
            SELECT
                id, world_id, village_game_id, village_name,
                village_coord_x, village_coord_y,
                attack_count, impact_at, rally_point_href,
                attacker_name, origin_village_name,
                origin_village_coord_x, origin_village_coord_y,
                operation_type, origin_village_href,
                attacker_snapshot_json,
                detected_at, source, updated_at
            FROM incoming_attacks
            {where_clause}
            ORDER BY impact_at ASC NULLS LAST
            LIMIT ? OFFSET ?
        """
        async with self._conn.execute(items_sql, params + [limit, offset]) as cursor:
            rows = await cursor.fetchall()

        items = [
            {
                "id":                     row["id"],
                "world_id":               row["world_id"],
                "village_game_id":        row["village_game_id"],
                "village_name":           row["village_name"],
                "village_coord_x":        row["village_coord_x"],
                "village_coord_y":        row["village_coord_y"],
                "attack_count":           row["attack_count"],
                "impact_at":              row["impact_at"],
                "rally_point_href":       row["rally_point_href"],
                "attacker_name":          row["attacker_name"],
                "origin_village_name":    row["origin_village_name"],
                "origin_village_coord_x": row["origin_village_coord_x"],
                "origin_village_coord_y": row["origin_village_coord_y"],
                "operation_type":         row["operation_type"],
                "origin_village_href":    row["origin_village_href"],
                "attacker_snapshot_json": row["attacker_snapshot_json"],
                "detected_at":            row["detected_at"],
                "source":                 row["source"],
                "updated_at":             row["updated_at"],
            }
            for row in rows
        ]

        return {"total": total, "items": items}
