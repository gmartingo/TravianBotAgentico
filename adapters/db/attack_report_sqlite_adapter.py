"""
Adaptador SQLite para reportes de ataque a oasis (AttackReportPort).

Implementa AttackReportPort usando aiosqlite con SQL crudo (sin Alembic, sin ORM),
coherente con el patrón del proyecto (ver adapters/db/database.py y
adapters/db/game_data_sqlite_adapter.py).

Tablas que gestiona:
  - attack_reports                  — cabecera del reporte
  - attack_report_attacker_troops   — tropas atacantes por reporte
  - attack_report_animals           — animales (defensor Nature) por reporte

Todas las tablas se crean con CREATE TABLE IF NOT EXISTS (DDL idempotente).
Las consultas de estadísticas usan window functions de SQLite 3.38+.

Ver spec docs/specs/bd-ataques-oasis.md §7 para el DDL completo y §7.3 para
las consultas de estadísticas.
Añadido en la feature bd-ataques-oasis (2026-05-30).
"""
from __future__ import annotations

import json
import logging
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import aiosqlite

from core.entities.attack_report import AttackReportPreview
from core.entities.tribe import Tribe
from core.ports.attack_report_port import AttackReportPort, DuplicateReportError
from core.use_cases.attack_report_parser import parse_attack_report

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DDL — idempotente
# ---------------------------------------------------------------------------

_CREATE_ATTACK_REPORTS = """
CREATE TABLE IF NOT EXISTS attack_reports (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Coordenadas del oasis atacado (destino)
    coord_x_dest        INTEGER NOT NULL,
    coord_y_dest        INTEGER NOT NULL,

    -- Aldea origen (nombre tal como aparece en el reporte)
    origin_village_name TEXT    NOT NULL,

    -- Hora local del servidor de Travian, verbatim, sin zona horaria (ISO 8601 naive): "2026-05-30T16:28:53"
    attacked_at         TEXT    NOT NULL,
    utc_offset          TEXT,           -- "+01:00", NULL si desconocido

    -- Botín de animales (recursos del drop)
    bounty_wood         INTEGER NOT NULL DEFAULT 0,
    bounty_clay         INTEGER NOT NULL DEFAULT 0,
    bounty_iron         INTEGER NOT NULL DEFAULT 0,
    bounty_crop         INTEGER NOT NULL DEFAULT 0,

    -- Capacidad de carga usada / total
    capacity_used       INTEGER NOT NULL DEFAULT 0,
    capacity_total      INTEGER NOT NULL DEFAULT 0,

    -- Inventario del héroe (JSON opaco o null)
    hero_inventory_json TEXT,

    -- Texto crudo original (para re-parseo futuro)
    raw_text            TEXT    NOT NULL,

    -- Tribu del atacante (resuelta por _resolve_attacker_tribe del parser).
    -- NULL = no resoluble o reporte pre-migración sin re-parsear aún.
    -- Valores posibles: 'gauls', 'romans', 'teutons', 'huns', 'egyptians', NULL.
    attacker_tribe      TEXT,

    -- Extensión futura (siempre NULL en MVP)
    world_id            INTEGER,

    -- Auditoría
    created_at          TEXT    NOT NULL,

    -- Clave de unicidad: mismo ataque al mismo oasis desde la misma aldea
    UNIQUE (coord_x_dest, coord_y_dest, attacked_at, origin_village_name)
);
"""

_CREATE_IDX_COORDS_TIME = """
CREATE INDEX IF NOT EXISTS idx_attack_reports_coords_time
    ON attack_reports (coord_x_dest, coord_y_dest, attacked_at);
"""

_CREATE_IDX_ATTACKED_AT = """
CREATE INDEX IF NOT EXISTS idx_attack_reports_attacked_at
    ON attack_reports (attacked_at);
"""

_CREATE_ATTACKER_TROOPS = """
CREATE TABLE IF NOT EXISTS attack_report_attacker_troops (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id       INTEGER NOT NULL REFERENCES attack_reports(id) ON DELETE CASCADE,

    troop_name      TEXT    NOT NULL,
    troop_ordinal   INTEGER,            -- NULL si nombre ambiguo entre tribus

    sent            INTEGER NOT NULL DEFAULT 0,
    lost            INTEGER NOT NULL DEFAULT 0,
    survived        INTEGER NOT NULL DEFAULT 0   -- = sent - lost, calculado al insertar
);
"""

_CREATE_IDX_ATTACKER_TROOPS = """
CREATE INDEX IF NOT EXISTS idx_attacker_troops_report
    ON attack_report_attacker_troops (report_id);
"""

_CREATE_ANIMALS = """
CREATE TABLE IF NOT EXISTS attack_report_animals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id       INTEGER NOT NULL REFERENCES attack_reports(id) ON DELETE CASCADE,

    animal_ordinal  INTEGER NOT NULL CHECK (animal_ordinal BETWEEN 1 AND 10),
    animal_name     TEXT    NOT NULL,

    -- present/killed/survived son NULL cuando el atacante pierde (cantidades desconocidas).
    -- 0 significa oasis vacío de ese tipo de animal (distinto semánticamente de NULL).
    -- §17.6 del spec bd-ataques-oasis.md.
    present         INTEGER,
    killed          INTEGER,
    survived        INTEGER
);
"""

_CREATE_IDX_ANIMALS_REPORT = """
CREATE INDEX IF NOT EXISTS idx_animals_report
    ON attack_report_animals (report_id);
"""

_CREATE_IDX_ANIMALS_ORDINAL = """
CREATE INDEX IF NOT EXISTS idx_animals_ordinal_report
    ON attack_report_animals (animal_ordinal, report_id);
"""

# Índice para filtros combinados tribu + fecha (balance stats EP-balance)
_CREATE_IDX_TRIBE_ATTACKED_AT = """
CREATE INDEX IF NOT EXISTS idx_attack_reports_tribe_attacked_at
    ON attack_reports (attacker_tribe, attacked_at);
"""


# ---------------------------------------------------------------------------
# Función de módulo — cálculo de ratios de regeneración
# ---------------------------------------------------------------------------

def _calc_regen_rates(repopulation_gaps: list[dict]) -> list[dict]:
    """
    Calcula el ratio promedio de regeneración por hora para cada animal,
    usando los intervalos válidos de repopulation_gaps.

    Intervalo válido: gap_seconds > 0, regenerated no es None, regenerated >= 0.
    Animales sin ningún intervalo válido no aparecen en la lista resultante.

    Ver spec docs/specs/bd-ataques-oasis-stats-oasis-nav.md §9 MEJORA 1.
    """
    # Acumular tasas por animal_ordinal
    # { animal_ordinal: { "name": str, "rates": [float], "valid_count": int } }
    accum: dict[int, dict] = {}

    for gap in repopulation_gaps:
        gap_seconds = gap.get("gap_seconds")
        if not gap_seconds or gap_seconds <= 0:
            continue  # EC-REGEN-A: gap inválido o primer ataque
        for animal in gap.get("regenerated_animals", []):
            regenerated = animal.get("regenerated")
            if regenerated is None or regenerated < 0:
                continue  # EC-REGEN-B y EC-REGEN-C
            rate = regenerated / (gap_seconds / 3600)
            ordinal = animal["animal_ordinal"]
            if ordinal not in accum:
                accum[ordinal] = {
                    "name": animal["animal_name"],
                    "rates": [],
                    "valid_count": 0,
                }
            accum[ordinal]["rates"].append(rate)
            accum[ordinal]["valid_count"] += 1

    result = []
    for ordinal in sorted(accum.keys()):
        entry = accum[ordinal]
        if not entry["rates"]:
            continue  # EC-REGEN-F: sin intervalos válidos, no incluir
        avg = sum(entry["rates"]) / len(entry["rates"])
        result.append({
            "animal_ordinal": ordinal,
            "animal_name": entry["name"],
            "avg_regen_per_hour": round(avg, 2),
            "valid_intervals": entry["valid_count"],
        })
    return result


# ---------------------------------------------------------------------------
# Función de módulo — conversión de utc_offset normalizado a timedelta
# ---------------------------------------------------------------------------

def _parse_utc_offset(s: str) -> timedelta:
    """
    Convierte el offset UTC normalizado del reporte (p. ej. "+01:00", "-05:30")
    a timedelta.

    El formato esperado es "+HH:MM" o "-HH:MM". Si es inesperado, devuelve
    timedelta(0) como comportamiento defensivo (EC-04: asumir UTC si NULL/inválido).

    Ejemplos:
      "+01:00" → timedelta(hours=1)
      "-05:30" → timedelta(hours=-5, minutes=-30)
      "+00:00" → timedelta(0)
    """
    try:
        sign = 1 if s.startswith("+") else -1
        parts = s[1:].split(":")
        hours = int(parts[0])
        minutes = int(parts[1])
        return timedelta(hours=sign * hours, minutes=sign * minutes)
    except Exception:
        return timedelta(0)


# ---------------------------------------------------------------------------
# Migración M-01 — añadir columna attacker_tribe y poblarla retroactivamente
# ---------------------------------------------------------------------------

async def _migrate_add_attacker_tribe(conn: aiosqlite.Connection) -> None:
    """
    Migración M-01: añade columna attacker_tribe TEXT a attack_reports y la
    rellena re-parseando raw_text de los reportes existentes.

    Estrategia:
    1. ADD COLUMN attacker_tribe TEXT (idempotente: captura OperationalError si ya existe).
    2. Recuperar todos los reportes con attacker_tribe IS NULL.
    3. Para cada uno: parse_attack_report(raw_text) → attacker_tribe → UPDATE.
    4. Si el parse falla: loguear warning + dejar NULL (no abortar).

    Idempotente: si la columna ya existe el ADD COLUMN falla silenciosamente;
    el SELECT solo retorna reportes aún sin tribu.

    Ver spec docs/specs/bd-ataques-oasis-balance-perdidos-robados.md §9.4.
    """
    # Paso 1: ADD COLUMN (idempotente)
    try:
        await conn.execute(
            "ALTER TABLE attack_reports ADD COLUMN attacker_tribe TEXT"
        )
        await conn.commit()
    except aiosqlite.OperationalError:
        pass  # columna ya existe — migración ya corrió antes

    # Paso 2: poblar retroactivamente solo los reportes sin tribu
    async with conn.execute(
        "SELECT id, raw_text FROM attack_reports WHERE attacker_tribe IS NULL"
    ) as cursor:
        rows = await cursor.fetchall()

    if not rows:
        return

    updated = skipped = 0
    for row in rows:
        try:
            preview = parse_attack_report(row["raw_text"], db_port=None)
            tribe = getattr(preview, "attacker_tribe", None)
        except Exception as exc:
            logger.warning(
                "M-01: no se pudo re-parsear reporte id=%s: %s", row["id"], exc
            )
            skipped += 1
            continue
        if tribe:
            await conn.execute(
                "UPDATE attack_reports SET attacker_tribe = ? WHERE id = ?",
                (tribe, row["id"]),
            )
            updated += 1

    await conn.commit()
    logger.info(
        "M-01 attacker_tribe: %d actualizados, %d sin tribu resoluble.",
        updated,
        skipped,
    )


# ---------------------------------------------------------------------------
# Adaptador
# ---------------------------------------------------------------------------

class AttackReportSQLiteAdapter(AttackReportPort):
    """Implementación SQLite del puerto de persistencia de reportes de ataque."""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    # -----------------------------------------------------------------------
    # DDL
    # -----------------------------------------------------------------------

    async def ensure_tables(self) -> None:
        """Crea las tablas y los índices si no existen. Ejecuta migraciones pendientes."""
        async with self._conn.executescript(
            _CREATE_ATTACK_REPORTS
            + _CREATE_IDX_COORDS_TIME
            + _CREATE_IDX_ATTACKED_AT
            + _CREATE_ATTACKER_TROOPS
            + _CREATE_IDX_ATTACKER_TROOPS
            + _CREATE_ANIMALS
            + _CREATE_IDX_ANIMALS_REPORT
            + _CREATE_IDX_ANIMALS_ORDINAL
        ):
            pass

        await _migrate_add_attacker_tribe(self._conn)

        async with self._conn.executescript(_CREATE_IDX_TRIBE_ATTACKED_AT):
            pass

        await self._conn.commit()

        # Migración M-01: añade columna attacker_tribe y la rellena retroactivamente.
        await _migrate_add_attacker_tribe(self._conn)

    # -----------------------------------------------------------------------
    # Escritura
    # -----------------------------------------------------------------------

    async def save_report(self, preview: AttackReportPreview, raw_text: str) -> int:
        """
        Persiste el reporte completo en las 3 tablas (cabecera + tropas + animales).

        Flujo:
          INSERT INTO attack_reports → lastrowid
          INSERT INTO attack_report_attacker_troops (una fila por tropa)
          INSERT INTO attack_report_animals (una fila por animal)
          COMMIT

        Si UNIQUE constraint viola → DuplicateReportError con el id existente.
        """
        created_at = datetime.now(timezone.utc).isoformat()
        hero_json = (
            json.dumps(preview.hero_inventory)
            if preview.hero_inventory is not None
            else None
        )
        attacker_tribe = getattr(preview, "attacker_tribe", None)

        # --- Insertar cabecera ---
        try:
            async with self._conn.execute(
                """
                INSERT INTO attack_reports (
                    coord_x_dest, coord_y_dest, origin_village_name,
                    attacked_at, utc_offset,
                    bounty_wood, bounty_clay, bounty_iron, bounty_crop,
                    capacity_used, capacity_total,
                    hero_inventory_json, raw_text, attacker_tribe, world_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    preview.coord_x_dest,
                    preview.coord_y_dest,
                    preview.origin_village_name,
                    preview.attacked_at,
                    preview.utc_offset,
                    preview.bounty.wood,
                    preview.bounty.clay,
                    preview.bounty.iron,
                    preview.bounty.crop,
                    preview.bounty.capacity_used,
                    preview.bounty.capacity_total,
                    hero_json,
                    raw_text,
                    attacker_tribe,
                    None,  # world_id: siempre NULL en MVP
                    created_at,
                ),
            ) as cursor:
                report_id = cursor.lastrowid
        except aiosqlite.IntegrityError:
            # UNIQUE constraint violation → buscar el id existente
            existing_id = await self.report_exists(
                preview.coord_x_dest,
                preview.coord_y_dest,
                preview.attacked_at,
                preview.origin_village_name,
            )
            raise DuplicateReportError(existing_id or 0)

        assert report_id is not None

        # --- Insertar tropas atacantes ---
        for troop in preview.attacker_troops:
            await self._conn.execute(
                """
                INSERT INTO attack_report_attacker_troops
                    (report_id, troop_name, troop_ordinal, sent, lost, survived)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    troop.troop_name,
                    troop.troop_ordinal,
                    troop.sent,
                    troop.lost,
                    troop.survived,
                ),
            )

        # --- Insertar animales ---
        for animal in preview.animals:
            await self._conn.execute(
                """
                INSERT INTO attack_report_animals
                    (report_id, animal_ordinal, animal_name, present, killed, survived)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    animal.animal_ordinal,
                    animal.animal_name,
                    animal.present,
                    animal.killed,
                    animal.survived,
                ),
            )

        await self._conn.commit()
        return report_id

    # -----------------------------------------------------------------------
    # Lectura
    # -----------------------------------------------------------------------

    async def report_exists(
        self,
        coord_x: int,
        coord_y: int,
        attacked_at: str,
        origin: str,
    ) -> int | None:
        """Devuelve el id del reporte si existe, None si no."""
        async with self._conn.execute(
            """
            SELECT id FROM attack_reports
            WHERE coord_x_dest = ? AND coord_y_dest = ?
              AND attacked_at = ? AND origin_village_name = ?
            """,
            (coord_x, coord_y, attacked_at, origin),
        ) as cursor:
            row = await cursor.fetchone()
            return row["id"] if row else None

    async def get_report(self, report_id: int) -> dict | None:
        """Devuelve el reporte completo con tropas y animales, o None si no existe."""
        # Cabecera
        async with self._conn.execute(
            "SELECT * FROM attack_reports WHERE id = ?",
            (report_id,),
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            return None

        report = dict(row)

        # Tropas atacantes
        async with self._conn.execute(
            "SELECT * FROM attack_report_attacker_troops WHERE report_id = ? ORDER BY id",
            (report_id,),
        ) as cursor:
            troops_rows = await cursor.fetchall()

        # Animales
        async with self._conn.execute(
            "SELECT * FROM attack_report_animals WHERE report_id = ? ORDER BY animal_ordinal",
            (report_id,),
        ) as cursor:
            animals_rows = await cursor.fetchall()

        # Parsear hero_inventory
        hero_inv = None
        if report.get("hero_inventory_json"):
            try:
                hero_inv = json.loads(report["hero_inventory_json"])
            except (json.JSONDecodeError, TypeError):
                hero_inv = None

        return {
            "id": report["id"],
            "attacked_at": report["attacked_at"],
            "utc_offset": report["utc_offset"],
            "coord_x_dest": report["coord_x_dest"],
            "coord_y_dest": report["coord_y_dest"],
            "origin_village_name": report["origin_village_name"],
            "bounty": {
                "wood": report["bounty_wood"],
                "clay": report["bounty_clay"],
                "iron": report["bounty_iron"],
                "crop": report["bounty_crop"],
                "capacity_used": report["capacity_used"],
                "capacity_total": report["capacity_total"],
            },
            "hero_inventory": hero_inv,  # campo raíz (C2)
            "raw_text": report["raw_text"],  # para re-parseo enriquecido en el detalle
            "attacker_troops": [
                {
                    "troop_name": t["troop_name"],
                    "troop_ordinal": t["troop_ordinal"],
                    "sent": t["sent"],
                    "lost": t["lost"],
                    "survived": t["survived"],
                }
                for t in troops_rows
            ],
            "animals": [
                {
                    "animal_ordinal": a["animal_ordinal"],
                    "animal_name": a["animal_name"],
                    "present": a["present"],
                    "killed": a["killed"],
                    "survived": a["survived"],
                }
                for a in animals_rows
            ],
            "created_at": report["created_at"],
        }

    async def list_reports(
        self,
        x: int | None = None,
        y: int | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """
        Historial paginado de reportes con filtros opcionales.

        Ver spec §7.3 (consulta "Historial con totales acumulados").

        El campo cumulative_bounty de la respuesta es la suma del bounty_total
        de todos los items del rango filtrado actual (no el total histórico global).
        """
        # Construir WHERE dinámico
        where_parts = []
        params: list = []

        if x is not None:
            where_parts.append("r.coord_x_dest = ?")
            params.append(x)
        if y is not None:
            where_parts.append("r.coord_y_dest = ?")
            params.append(y)
        if from_date is not None:
            where_parts.append("r.attacked_at >= ?")
            params.append(from_date)
        if to_date is not None:
            where_parts.append("r.attacked_at <= ?")
            params.append(to_date)

        where_clause = "WHERE " + " AND ".join(where_parts) if where_parts else ""

        # Contar total
        count_sql = f"SELECT COUNT(*) AS cnt FROM attack_reports r {where_clause}"
        async with self._conn.execute(count_sql, params) as cursor:
            count_row = await cursor.fetchone()
        total = count_row["cnt"] if count_row else 0

        # Suma acumulada del rango filtrado (cumulative_bounty = suma del rango actual)
        sum_sql = f"""
            SELECT COALESCE(SUM(r.bounty_wood + r.bounty_clay + r.bounty_iron + r.bounty_crop), 0)
                   AS cum_bounty
            FROM attack_reports r {where_clause}
        """
        async with self._conn.execute(sum_sql, params) as cursor:
            sum_row = await cursor.fetchone()
        cumulative_bounty = sum_row["cum_bounty"] if sum_row else 0

        # Paginado — incluye animales summary como JSON
        items_sql = f"""
            SELECT
                r.id,
                r.attacked_at,
                r.coord_x_dest,
                r.coord_y_dest,
                r.origin_village_name,
                r.bounty_wood,
                r.bounty_clay,
                r.bounty_iron,
                r.bounty_crop,
                (r.bounty_wood + r.bounty_clay + r.bounty_iron + r.bounty_crop) AS bounty_total,
                (
                    SELECT COALESCE(SUM(t.lost), 0)
                    FROM attack_report_attacker_troops t WHERE t.report_id = r.id
                ) AS attacker_losses_count
            FROM attack_reports r
            {where_clause}
            ORDER BY r.attacked_at DESC
            LIMIT ? OFFSET ?
        """
        async with self._conn.execute(items_sql, params + [limit, offset]) as cursor:
            item_rows = await cursor.fetchall()

        items = []
        for row in item_rows:
            # Animales summary para este reporte
            async with self._conn.execute(
                """
                SELECT animal_ordinal, animal_name, present, killed, survived
                FROM attack_report_animals
                WHERE report_id = ?
                ORDER BY animal_ordinal
                """,
                (row["id"],),
            ) as cur2:
                animal_rows = await cur2.fetchall()

            items.append({
                "id": row["id"],
                "attacked_at": row["attacked_at"],
                "coord_x_dest": row["coord_x_dest"],
                "coord_y_dest": row["coord_y_dest"],
                "origin_village_name": row["origin_village_name"],
                "bounty_total": row["bounty_total"],
                "bounty": {
                    "wood": row["bounty_wood"],
                    "clay": row["bounty_clay"],
                    "iron": row["bounty_iron"],
                    "crop": row["bounty_crop"],
                },
                "attacker_losses_count": row["attacker_losses_count"],
                "animals_summary": [
                    {
                        "animal_ordinal": a["animal_ordinal"],
                        "animal_name": a["animal_name"],
                        "present": a["present"],
                        "killed": a["killed"],
                        "survived": a["survived"],
                    }
                    for a in animal_rows
                ],
            })

        return {
            "total": total,
            "items": items,
            "cumulative_bounty": cumulative_bounty,
        }

    async def delete_report(self, report_id: int) -> bool:
        """Borra el reporte y sus hijas (CASCADE). Devuelve True si existía."""
        async with self._conn.execute(
            "DELETE FROM attack_reports WHERE id = ?",
            (report_id,),
        ) as cursor:
            deleted = cursor.rowcount > 0
        await self._conn.commit()
        return deleted

    async def get_oasis_stats(self, x: int, y: int) -> dict:
        """
        Estadísticas de un oasis: aparición de animales, repoblación temporal y regeneración.

        Ver spec §7.3 para las consultas SQL exactas (LAG, WINDOW, UNIXEPOCH).
        """
        # Total de ataques y rango temporal
        async with self._conn.execute(
            """
            SELECT COUNT(*) AS total,
                   MIN(attacked_at) AS first_attack,
                   MAX(attacked_at) AS last_attack
            FROM attack_reports
            WHERE coord_x_dest = ? AND coord_y_dest = ?
            """,
            (x, y),
        ) as cursor:
            meta = await cursor.fetchone()

        total_attacks = meta["total"] if meta else 0

        # Caso sin reportes (C7): devolver body de "cero ataques"
        if total_attacks == 0:
            return {
                "coord_x_dest": x,
                "coord_y_dest": y,
                "total_attacks": 0,
                "first_attack": None,
                "last_attack": None,
                "animal_appearances": [],
                "repopulation_gaps": [],
                "animal_regen_rates": [],
            }

        first_attack = meta["first_attack"]
        last_attack = meta["last_attack"]

        # Aparición de animales (solo con present > 0; min_present excluye present=0)
        async with self._conn.execute(
            """
            SELECT
                a.animal_ordinal,
                a.animal_name,
                COUNT(*)                    AS appearances,
                AVG(a.present)              AS avg_present,
                MAX(a.present)              AS max_present,
                MIN(CASE WHEN a.present > 0 THEN a.present END) AS min_present_nonzero
            FROM attack_report_animals a
            JOIN attack_reports r ON r.id = a.report_id
            WHERE r.coord_x_dest = ? AND r.coord_y_dest = ?
              AND a.present > 0
            GROUP BY a.animal_ordinal, a.animal_name
            ORDER BY a.animal_ordinal
            """,
            (x, y),
        ) as cursor:
            appearance_rows = await cursor.fetchall()

        animal_appearances = [
            {
                "animal_ordinal": row["animal_ordinal"],
                "animal_name": row["animal_name"],
                "appearances": row["appearances"],
                "avg_present": round(row["avg_present"], 2) if row["avg_present"] is not None else None,
                "max_present": row["max_present"],
                "min_present": row["min_present_nonzero"],
            }
            for row in appearance_rows
        ]

        # Regeneración de animales con LAG (spec §7.3)
        # Esta consulta da: por cada reporte, por cada animal, los supervivientes
        # del ataque anterior y el delta regenerado.
        regen_sql = """
            WITH ordered AS (
                SELECT
                    r.id                        AS report_id,
                    r.attacked_at,
                    a.animal_ordinal,
                    a.animal_name,
                    a.present,
                    a.survived,
                    LAG(a.survived) OVER w      AS prev_survived
                FROM attack_reports r
                JOIN attack_report_animals a ON a.report_id = r.id
                WHERE r.coord_x_dest = ? AND r.coord_y_dest = ?
                WINDOW w AS (PARTITION BY a.animal_ordinal ORDER BY r.attacked_at)
            )
            SELECT
                report_id,
                attacked_at,
                animal_ordinal,
                animal_name,
                present,
                survived,
                prev_survived,
                CASE WHEN prev_survived IS NOT NULL
                     THEN present - prev_survived
                     ELSE NULL
                END AS regenerated
            FROM ordered
            ORDER BY attacked_at, animal_ordinal
        """
        async with self._conn.execute(regen_sql, (x, y)) as cursor:
            regen_rows = await cursor.fetchall()

        # Repoblación temporal con LAG (spec §7.3)
        gap_sql = """
            SELECT
                r.id,
                r.attacked_at,
                LAG(r.attacked_at) OVER w   AS prev_attacked_at,
                (UNIXEPOCH(r.attacked_at) - UNIXEPOCH(LAG(r.attacked_at) OVER w)) AS gap_seconds
            FROM attack_reports r
            WHERE r.coord_x_dest = ? AND r.coord_y_dest = ?
            WINDOW w AS (ORDER BY r.attacked_at)
            ORDER BY r.attacked_at
        """
        async with self._conn.execute(gap_sql, (x, y)) as cursor:
            gap_rows = await cursor.fetchall()

        # Agrupar datos de regeneración por report_id
        regen_by_report: dict[int, list[dict]] = {}
        for row in regen_rows:
            rid = row["report_id"]
            if rid not in regen_by_report:
                regen_by_report[rid] = []
            regen_by_report[rid].append({
                "animal_ordinal": row["animal_ordinal"],
                "animal_name": row["animal_name"],
                "prev_survived": row["prev_survived"],
                "present_now": row["present"],
                "regenerated": row["regenerated"],
            })

        # Construir repopulation_gaps
        repopulation_gaps = []
        for gap in gap_rows:
            rid = gap["id"]
            repopulation_gaps.append({
                "attack_id": rid,
                "attacked_at": gap["attacked_at"],
                "prev_attacked_at": gap["prev_attacked_at"],
                "gap_seconds": gap["gap_seconds"],
                "regenerated_animals": regen_by_report.get(rid, []),
            })

        animal_regen_rates = _calc_regen_rates(repopulation_gaps)

        return {
            "coord_x_dest": x,
            "coord_y_dest": y,
            "total_attacks": total_attacks,
            "first_attack": first_attack,
            "last_attack": last_attack,
            "animal_appearances": animal_appearances,
            "repopulation_gaps": repopulation_gaps,
            "animal_regen_rates": animal_regen_rates,
        }

    async def get_bounty_stats(
        self,
        x: int | None = None,
        y: int | None = None,
    ) -> dict:
        """
        Balance de recursos saqueados.

        Si x e y son None → balance global (todos los reportes).
        Si x e y son enteros → balance del oasis en (x, y).

        Ver spec docs/specs/bd-ataques-oasis-fix-hora-balance.md §9.2.
        """
        params: list = []
        where = ""
        if x is not None:
            where = "WHERE coord_x_dest = ? AND coord_y_dest = ?"
            params = [x, y]

        sql = f"""
            SELECT
                COUNT(*)                       AS total_reports,
                COALESCE(SUM(bounty_wood),  0) AS wood,
                COALESCE(SUM(bounty_clay),  0) AS clay,
                COALESCE(SUM(bounty_iron),  0) AS iron,
                COALESCE(SUM(bounty_crop),  0) AS crop
            FROM attack_reports
            {where}
        """
        async with self._conn.execute(sql, params) as cursor:
            row = await cursor.fetchone()

        total_reports = row["total_reports"] if row else 0
        wood  = row["wood"]  if row else 0
        clay  = row["clay"]  if row else 0
        iron  = row["iron"]  if row else 0
        crop  = row["crop"]  if row else 0

        return {
            "scope": "oasis" if x is not None else "global",
            "coord_x_dest": x,    # None cuando global → serializa como null (C1)
            "coord_y_dest": y,    # None cuando global → serializa como null
            "total_reports": total_reports,
            "bounty": {
                "wood":  wood,
                "clay":  clay,
                "iron":  iron,
                "crop":  crop,
                "total": wood + clay + iron + crop,
            },
        }

    async def get_global_oasis_stats(self) -> dict:
        """
        Estadísticas globales de todos los oasis combinados.
        Reutiliza _calc_regen_rates con los gaps de todos los oasis concatenados.

        Ver spec docs/specs/bd-ataques-oasis-stats-global.md §9 EP-09.
        Modificado: añade eligible_reports (denominador del % de aparición) por animal.
        Ver spec docs/specs/bd-ataques-oasis-global-pct-aparicion.md §9 Paso 1b.
        """
        # ── Paso 1a: Apariciones globales (SIN CAMBIO) ────────────────────────
        # WHERE present > 0: excluye animales con 0 unidades observadas.
        # MIN(CASE WHEN present > 0 THEN present END): excluye ceros del mínimo.
        async with self._conn.execute(
            """
            SELECT
                a.animal_ordinal,
                a.animal_name,
                COUNT(*)                                              AS appearances,
                AVG(a.present)                                        AS avg_present,
                MAX(a.present)                                        AS max_present,
                MIN(CASE WHEN a.present > 0 THEN a.present END)       AS min_present_nonzero
            FROM attack_report_animals a
            JOIN attack_reports r ON r.id = a.report_id
            WHERE a.present > 0
            GROUP BY a.animal_ordinal, a.animal_name
            ORDER BY a.animal_ordinal
            """,
        ) as cursor:
            appearance_rows = await cursor.fetchall()

        # ── Paso 1b: Denominador por animal (NUEVO) ───────────────────────────
        # Para cada animal_ordinal:
        #   1. Identificar oasis donde ese animal ha aparecido alguna vez (ever_present):
        #      subconsulta DISTINCT sobre (coord_x_dest, coord_y_dest, animal_ordinal)
        #      WHERE present > 0.
        #   2. Contar TODOS los reportes de esos oasis (sin filtro de present).
        #      Incluye los reportes donde el animal estaba a 0 ese día, porque en ese
        #      oasis sí puede aparecer.
        #   3. COUNT(DISTINCT r_eligible.id) evita contar el mismo reporte dos veces
        #      (garantía formal; en este schema cada reporte tiene coords únicas).
        # present = NULL (reportes de derrota) no satisface present > 0, quedando excluido
        # tanto del numerador (appearances) como del denominador (eligible_reports).
        async with self._conn.execute(
            """
            SELECT
                a_ever.animal_ordinal,
                COUNT(DISTINCT r_eligible.id) AS eligible_reports
            FROM (
                SELECT DISTINCT
                    r2.coord_x_dest,
                    r2.coord_y_dest,
                    a2.animal_ordinal
                FROM attack_report_animals a2
                JOIN attack_reports r2 ON r2.id = a2.report_id
                WHERE a2.present > 0
            ) a_ever
            JOIN attack_reports r_eligible
                ON  r_eligible.coord_x_dest = a_ever.coord_x_dest
                AND r_eligible.coord_y_dest = a_ever.coord_y_dest
            GROUP BY a_ever.animal_ordinal
            """,
        ) as cursor:
            eligible_rows = await cursor.fetchall()

        # Construir dict ordinal → eligible_reports para join O(1)
        eligible_by_ordinal: dict[int, int] = {
            row["animal_ordinal"]: row["eligible_reports"]
            for row in eligible_rows
        }

        # ── Paso 2: Regen con LAG particionado por (oasis, animal) ────────────
        # PARTITION BY (coord_x_dest, coord_y_dest, animal_ordinal):
        # el LAG no cruza entre oasis distintos.
        regen_sql = """
            WITH ordered AS (
                SELECT
                    r.id               AS report_id,
                    r.attacked_at,
                    r.coord_x_dest,
                    r.coord_y_dest,
                    a.animal_ordinal,
                    a.animal_name,
                    a.present,
                    a.survived,
                    LAG(a.survived) OVER w  AS prev_survived
                FROM attack_reports r
                JOIN attack_report_animals a ON a.report_id = r.id
                WINDOW w AS (
                    PARTITION BY r.coord_x_dest, r.coord_y_dest, a.animal_ordinal
                    ORDER BY r.attacked_at
                )
            )
            SELECT
                report_id, attacked_at, animal_ordinal, animal_name,
                present, survived, prev_survived,
                CASE WHEN prev_survived IS NOT NULL
                     THEN present - prev_survived
                     ELSE NULL
                END AS regenerated
            FROM ordered
            ORDER BY attacked_at, coord_x_dest, coord_y_dest, animal_ordinal
        """
        async with self._conn.execute(regen_sql) as cursor:
            regen_rows = await cursor.fetchall()

        # ── Paso 3: Gaps con LAG particionado por oasis ───────────────────────
        # PARTITION BY (coord_x_dest, coord_y_dest): los gaps se calculan dentro
        # de cada oasis. El LAG NO cruza entre oasis distintos.
        gap_sql = """
            SELECT
                r.id,
                r.coord_x_dest,
                r.coord_y_dest,
                r.attacked_at,
                LAG(r.attacked_at) OVER w            AS prev_attacked_at,
                (UNIXEPOCH(r.attacked_at) - UNIXEPOCH(LAG(r.attacked_at) OVER w))
                                                     AS gap_seconds
            FROM attack_reports r
            WINDOW w AS (
                PARTITION BY r.coord_x_dest, r.coord_y_dest
                ORDER BY r.attacked_at
            )
            ORDER BY r.attacked_at
        """
        async with self._conn.execute(gap_sql) as cursor:
            gap_rows = await cursor.fetchall()

        # ── Paso 4: Construir repopulation_gaps ───────────────────────────────
        # Agrupar regen_rows por report_id
        regen_by_report: dict[int, list[dict]] = {}
        for row in regen_rows:
            rid = row["report_id"]
            if rid not in regen_by_report:
                regen_by_report[rid] = []
            regen_by_report[rid].append({
                "animal_ordinal": row["animal_ordinal"],
                "animal_name": row["animal_name"],
                "regenerated": row["regenerated"],
            })

        repopulation_gaps = [
            {
                "attack_id": gap["id"],
                "attacked_at": gap["attacked_at"],
                "prev_attacked_at": gap["prev_attacked_at"],
                "gap_seconds": gap["gap_seconds"],
                "regenerated_animals": regen_by_report.get(gap["id"], []),
            }
            for gap in gap_rows
        ]

        # ── Paso 5: Calcular rates globales ───────────────────────────────────
        animal_regen_rates = _calc_regen_rates(repopulation_gaps)

        # ── Paso 6: Construir y devolver el dict de respuesta ─────────────────
        # MODIFICADO: añadir eligible_reports a cada item de animal_appearances.
        # Si el ordinal no está en eligible_by_ordinal (caso teórico imposible porque
        # si hay appearances >= 1 hay ever_present), devuelve None.
        # El frontend maneja None como "sin denominador" (EC-P10).
        # Orden de campos: animal_ordinal, animal_name, appearances, eligible_reports,
        # avg_present, max_present, min_present (fiel al contrato openapi.yaml).
        return {
            "scope": "global",
            "animal_appearances": [
                {
                    "animal_ordinal":   row["animal_ordinal"],
                    "animal_name":      row["animal_name"],
                    "appearances":      row["appearances"],
                    "eligible_reports": eligible_by_ordinal.get(row["animal_ordinal"]),
                    "avg_present":      round(row["avg_present"], 2) if row["avg_present"] is not None else None,
                    "max_present":      row["max_present"],
                    "min_present":      row["min_present_nonzero"],  # puede ser None (guardia defensiva)
                }
                for row in appearance_rows
            ],
            "animal_regen_rates": animal_regen_rates,
        }

    async def list_oasis_summaries(
        self,
        x: int | None = None,
        y: int | None = None,
    ) -> dict:
        """
        Lista de oasis únicos con reportes de ataque, con resumen estadístico básico.

        Ordenación: last_attack DESC (oasis atacado más recientemente primero).
        Filtros opcionales: x+y exacto (ambos o ninguno).

        Ver spec docs/specs/bd-ataques-oasis-stats-oasis-nav.md §9.
        """
        params: list = []
        where_parts = []
        if x is not None:
            where_parts.append("coord_x_dest = ?")
            params.append(x)
        if y is not None:
            where_parts.append("coord_y_dest = ?")
            params.append(y)

        where_clause = "WHERE " + " AND ".join(where_parts) if where_parts else ""

        sql = f"""
            SELECT
                coord_x_dest,
                coord_y_dest,
                COUNT(*)                                            AS attack_count,
                MAX(attacked_at)                                    AS last_attack,
                COALESCE(
                    SUM(bounty_wood + bounty_clay + bounty_iron + bounty_crop), 0
                )                                                   AS total_bounty
            FROM attack_reports
            {where_clause}
            GROUP BY coord_x_dest, coord_y_dest
            ORDER BY last_attack DESC
        """
        async with self._conn.execute(sql, params) as cursor:
            rows = await cursor.fetchall()

        items = [
            {
                "coord_x_dest": row["coord_x_dest"],
                "coord_y_dest": row["coord_y_dest"],
                "attack_count": row["attack_count"],
                "last_attack": row["last_attack"],
                "total_bounty": row["total_bounty"],
            }
            for row in rows
        ]
        return {"total": len(items), "items": items}

    async def get_all_oasis_regen_comparison(self) -> dict:
        """
        Comparativa de tasas de reaparición y proyección de animales para todos los oasis.

        Reutiliza _calc_regen_rates por oasis. Una sola query SQL particionada
        (no N llamadas a get_oasis_stats). Reutiliza _parse_utc_offset para la
        conversión de hora local → UTC.

        Ver spec docs/specs/reaparicion-animales-oasis.md §8 EP-10 y §9.
        """
        computed_at = datetime.now(timezone.utc)

        # ── Paso 0: Especies que han estado presentes (present>0) en cada oasis ─
        # RN del spec: un oasis donde NUNCA apareció una especie NO debe mostrar
        # esa especie, ni con tasa 0. El parser de Travian inserta 10 filas por
        # reporte (una por especie), con present=0 para las que no existen en ese
        # oasis. Este índice pre-filtra cuáles han tenido present>0 alguna vez,
        # equivalente al filtro AND a.present > 0 de get_oasis_stats (EP-06).
        ever_present_sql = """
            SELECT DISTINCT r.coord_x_dest, r.coord_y_dest, a.animal_ordinal
            FROM attack_report_animals a
            JOIN attack_reports r ON r.id = a.report_id
            WHERE a.present > 0
        """
        async with self._conn.execute(ever_present_sql) as cursor:
            ever_present_rows = await cursor.fetchall()

        # Conjunto de tuplas (coord_x, coord_y, animal_ordinal) con presencia real
        ever_present: set[tuple] = {
            (row["coord_x_dest"], row["coord_y_dest"], row["animal_ordinal"])
            for row in ever_present_rows
        }

        # ── Paso 1: Regen con LAG particionado por (oasis, animal) ───────────
        regen_sql = """
            WITH ordered AS (
                SELECT
                    r.id               AS report_id,
                    r.attacked_at,
                    r.coord_x_dest,
                    r.coord_y_dest,
                    a.animal_ordinal,
                    a.animal_name,
                    a.present,
                    a.survived,
                    LAG(a.survived) OVER w  AS prev_survived
                FROM attack_reports r
                JOIN attack_report_animals a ON a.report_id = r.id
                WINDOW w AS (
                    PARTITION BY r.coord_x_dest, r.coord_y_dest, a.animal_ordinal
                    ORDER BY r.attacked_at
                )
            )
            SELECT
                report_id, attacked_at, coord_x_dest, coord_y_dest,
                animal_ordinal, animal_name, present, survived, prev_survived,
                CASE WHEN prev_survived IS NOT NULL
                     THEN present - prev_survived
                     ELSE NULL
                END AS regenerated
            FROM ordered
            ORDER BY coord_x_dest, coord_y_dest, attacked_at, animal_ordinal
        """
        async with self._conn.execute(regen_sql) as cursor:
            regen_rows = await cursor.fetchall()

        # ── Paso 2: Gaps con LAG particionado por oasis (incluye utc_offset) ──
        gap_sql = """
            SELECT
                r.id,
                r.coord_x_dest,
                r.coord_y_dest,
                r.attacked_at,
                r.utc_offset,
                LAG(r.attacked_at) OVER w            AS prev_attacked_at,
                (UNIXEPOCH(r.attacked_at) - UNIXEPOCH(LAG(r.attacked_at) OVER w))
                                                     AS gap_seconds
            FROM attack_reports r
            WINDOW w AS (
                PARTITION BY r.coord_x_dest, r.coord_y_dest
                ORDER BY r.attacked_at
            )
            ORDER BY r.coord_x_dest, r.coord_y_dest, r.attacked_at
        """
        async with self._conn.execute(gap_sql) as cursor:
            gap_rows = await cursor.fetchall()

        # ── Paso 3: last_survived por (oasis, animal) — último reporte ────────
        last_survived_sql = """
            WITH ranked AS (
                SELECT
                    r.coord_x_dest,
                    r.coord_y_dest,
                    a.animal_ordinal,
                    a.animal_name,
                    a.survived,
                    ROW_NUMBER() OVER (
                        PARTITION BY r.coord_x_dest, r.coord_y_dest, a.animal_ordinal
                        ORDER BY r.attacked_at DESC
                    ) AS rn
                FROM attack_report_animals a
                JOIN attack_reports r ON r.id = a.report_id
            )
            SELECT coord_x_dest, coord_y_dest, animal_ordinal, animal_name, survived
            FROM ranked
            WHERE rn = 1
        """
        async with self._conn.execute(last_survived_sql) as cursor:
            last_survived_rows = await cursor.fetchall()

        # Índice: (cx, cy, ordinal) → survived (puede ser None en derrotas §17)
        last_survived_by_key: dict[tuple, int | None] = {
            (row["coord_x_dest"], row["coord_y_dest"], row["animal_ordinal"]): row["survived"]
            for row in last_survived_rows
        }

        # ── Paso 4: Agrupar regen por report_id — filtrando ausentes ────────────
        # Solo incluir filas de especies que han tenido present>0 en ese oasis.
        # Las filas con present siempre 0 (especie nunca presente) se omiten aquí,
        # evitando que _calc_regen_rates genere tasas 0.0 para especies ausentes.
        regen_by_report: dict[int, list[dict]] = {}
        for row in regen_rows:
            oasis_species_key = (row["coord_x_dest"], row["coord_y_dest"], row["animal_ordinal"])
            if oasis_species_key not in ever_present:
                continue  # especie nunca presente en este oasis → omitir
            rid = row["report_id"]
            if rid not in regen_by_report:
                regen_by_report[rid] = []
            regen_by_report[rid].append({
                "animal_ordinal": row["animal_ordinal"],
                "animal_name": row["animal_name"],
                "regenerated": row["regenerated"],
            })

        # ── Paso 5: Agrupar gaps por oasis y rastrear metadatos ──────────────
        gaps_by_oasis: dict[tuple, list[dict]] = {}
        last_attack_info: dict[tuple, dict] = {}
        total_attacks_by_oasis: dict[tuple, int] = {}

        for gap in gap_rows:
            key = (gap["coord_x_dest"], gap["coord_y_dest"])
            if key not in gaps_by_oasis:
                gaps_by_oasis[key] = []
                total_attacks_by_oasis[key] = 0

            total_attacks_by_oasis[key] += 1
            gaps_by_oasis[key].append({
                "attack_id": gap["id"],
                "attacked_at": gap["attacked_at"],
                "prev_attacked_at": gap["prev_attacked_at"],
                "gap_seconds": gap["gap_seconds"],
                "regenerated_animals": regen_by_report.get(gap["id"], []),
            })
            # Los gaps están ordenados ASC → el último sobreescribe = más reciente
            last_attack_info[key] = {
                "attacked_at": gap["attacked_at"],
                "utc_offset": gap["utc_offset"],
            }

        # ── Paso 6: Calcular tasas por oasis ─────────────────────────────────
        oasis_rates: dict[tuple, list[dict]] = {
            key: _calc_regen_rates(gaps)
            for key, gaps in gaps_by_oasis.items()
        }

        # ── Paso 7: Calcular hours_since_last_attack por oasis ────────────────
        oasis_hours: dict[tuple, float] = {}
        computed_naive = computed_at.replace(tzinfo=None)
        for key, info in last_attack_info.items():
            last_attack_str = info["attacked_at"]
            utc_offset_str = info["utc_offset"]  # puede ser None (EC-04)

            last_attack_naive = datetime.fromisoformat(last_attack_str)
            if utc_offset_str:
                offset_td = _parse_utc_offset(utc_offset_str)
                last_attack_utc = last_attack_naive - offset_td
            else:
                # EC-04: sin offset → asumir UTC (comportamiento defensivo)
                last_attack_utc = last_attack_naive

            hours_raw = (computed_naive - last_attack_utc).total_seconds() / 3600
            oasis_hours[key] = round(max(0.0, hours_raw), 2)  # EC-09: nunca negativo

        # ── Paso 8: Construir species_columns (unión de todas las especies con tasa)
        species_cols_by_ordinal: dict[int, dict] = {}
        for rates in oasis_rates.values():
            for rate in rates:
                ordinal = rate["animal_ordinal"]
                if ordinal not in species_cols_by_ordinal:
                    species_cols_by_ordinal[ordinal] = {
                        "animal_ordinal": ordinal,
                        "animal_name": rate["animal_name"],
                        "icon_url": f"/static/icons/nature_{ordinal}.png",
                    }

        species_columns = [
            species_cols_by_ordinal[ordinal]
            for ordinal in sorted(species_cols_by_ordinal.keys())
        ]

        # ── Paso 9: Construir oasis entries ──────────────────────────────────
        oasis_entries = []
        for key in gaps_by_oasis:
            cx, cy = key
            rates = oasis_rates.get(key, [])
            has_rates = len(rates) > 0
            hours = oasis_hours.get(key, 0.0)
            last_attack_str = last_attack_info[key]["attacked_at"]

            species_list = []
            for rate in rates:
                ordinal = rate["animal_ordinal"]
                last_surv = last_survived_by_key.get((cx, cy, ordinal))

                if last_surv is None:
                    # RN-08 / EC-02: survived NULL → proyección null
                    projected_now = None
                else:
                    # RN-07: floor, mínimo 0
                    raw = last_surv + rate["avg_regen_per_hour"] * hours
                    projected_now = max(0, math.floor(raw))

                species_list.append({
                    "animal_ordinal": ordinal,
                    "animal_name": rate["animal_name"],
                    "icon_url": f"/static/icons/nature_{ordinal}.png",
                    "avg_regen_per_hour": rate["avg_regen_per_hour"],
                    "valid_intervals": rate["valid_intervals"],
                    "last_survived": last_surv,
                    "projected_now": projected_now,
                })

            oasis_entries.append({
                "coord_x_dest": cx,
                "coord_y_dest": cy,
                "total_attacks": total_attacks_by_oasis[key],
                "last_attack": last_attack_str,
                "hours_since_last_attack": hours,
                "has_rates": has_rates,
                "species": species_list,
            })

        # ── Paso 10: Ordenar — has_rates DESC, luego last_attack DESC (RN-05) ─
        oasis_entries.sort(key=lambda e: e["last_attack"], reverse=True)
        oasis_entries.sort(key=lambda e: not e["has_rates"])

        # ── Paso 11: Devolver dict de respuesta ───────────────────────────────
        return {
            "computed_at": computed_at.isoformat(),
            "species_columns": species_columns,
            "oasis": oasis_entries,
        }

    async def get_balance_stats(
        self,
        x: int | None = None,
        y: int | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        game_data_port=None,
    ) -> dict:
        """
        Cómputo balance PERDIDOS vs ROBADOS (EP-balance).

        Ver spec docs/specs/bd-ataques-oasis-balance-perdidos-robados.md §9.3.
        """
        # ── Construir WHERE dinámico (mismo patrón que list_reports) ──────────
        where_parts: list[str] = []
        params: list = []
        if x is not None:
            where_parts.append("r.coord_x_dest = ? AND r.coord_y_dest = ?")
            params.extend([x, y])
        if from_date is not None:
            where_parts.append("r.attacked_at >= ?")
            params.append(from_date)
        if to_date is not None:
            where_parts.append("r.attacked_at <= ?")
            params.append(to_date)
        where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        # ── Paso 1: ROBADO (bounty + hero_inventory) — una sola query SQL ──────
        stolen_sql = f"""
            SELECT
                COUNT(*)                                          AS total_reports,
                COALESCE(SUM(r.bounty_wood),  0)                  AS b_wood,
                COALESCE(SUM(r.bounty_clay),  0)                  AS b_clay,
                COALESCE(SUM(r.bounty_iron),  0)                  AS b_iron,
                COALESCE(SUM(r.bounty_crop),  0)                  AS b_crop,
                COALESCE(SUM(COALESCE(json_extract(r.hero_inventory_json,'$.wood'), 0)), 0)  AS h_wood,
                COALESCE(SUM(COALESCE(json_extract(r.hero_inventory_json,'$.clay'), 0)), 0)  AS h_clay,
                COALESCE(SUM(COALESCE(json_extract(r.hero_inventory_json,'$.iron'), 0)), 0)  AS h_iron,
                COALESCE(SUM(COALESCE(json_extract(r.hero_inventory_json,'$.crop'), 0)), 0)  AS h_crop,
                COUNT(CASE WHEN r.attacker_tribe IS NULL THEN 1 END) AS without_tribe
            FROM attack_reports r
            {where}
        """
        async with self._conn.execute(stolen_sql, params) as cursor:
            row = await cursor.fetchone()

        total_reports = row["total_reports"] if row else 0
        without_tribe = row["without_tribe"] if row else 0
        b_wood = row["b_wood"] if row else 0
        b_clay = row["b_clay"] if row else 0
        b_iron = row["b_iron"] if row else 0
        b_crop = row["b_crop"] if row else 0
        h_wood = row["h_wood"] if row else 0
        h_clay = row["h_clay"] if row else 0
        h_iron = row["h_iron"] if row else 0
        h_crop = row["h_crop"] if row else 0

        # ── Paso 2: PERDIDO — recuperar tropas con tribu conocida ───────────────
        # Añadimos las condiciones de tribu/lost/ordinal al WHERE de filtros.
        troop_where_parts = list(where_parts) + [
            "r.attacker_tribe IS NOT NULL",
            "t.lost > 0",
            "t.troop_ordinal IS NOT NULL",
        ]
        troop_where = "WHERE " + " AND ".join(troop_where_parts)

        troops_sql = f"""
            SELECT
                r.id           AS report_id,
                r.attacker_tribe,
                t.troop_ordinal,
                t.lost
            FROM attack_reports r
            JOIN attack_report_attacker_troops t ON t.report_id = r.id
            {troop_where}
        """
        async with self._conn.execute(troops_sql, params) as cursor:
            troop_rows = await cursor.fetchall()

        # ── Paso 3: calcular PERDIDO agrupando por tribu ───────────────────────
        lost_wood = lost_clay = lost_iron = lost_crop = 0
        if game_data_port and troop_rows:
            by_tribe: dict[str, list] = defaultdict(list)
            for tr in troop_rows:
                by_tribe[tr["attacker_tribe"]].append(tr)

            for tribe_str, rows in by_tribe.items():
                try:
                    tribe = Tribe(tribe_str)
                except ValueError:
                    continue
                stats = await game_data_port.get_all_troop_stats(tribe)
                cost_by_ord = {s["ordinal"]: s for s in stats}
                for tr in rows:
                    s = cost_by_ord.get(tr["troop_ordinal"])
                    if not s:
                        continue
                    lost_wood += tr["lost"] * (s.get("cost_wood") or 0)
                    lost_clay += tr["lost"] * (s.get("cost_clay") or 0)
                    lost_iron += tr["lost"] * (s.get("cost_iron") or 0)
                    lost_crop += tr["lost"] * (s.get("cost_crop") or 0)

        lost_total = lost_wood + lost_clay + lost_iron + lost_crop
        bounty_total = b_wood + b_clay + b_iron + b_crop
        hi_total = h_wood + h_clay + h_iron + h_crop
        stolen_total = bounty_total + hi_total
        s_wood = b_wood + h_wood
        s_clay = b_clay + h_clay
        s_iron = b_iron + h_iron
        s_crop = b_crop + h_crop

        return {
            "range": {"from": from_date, "to": to_date},
            "total_reports": total_reports,
            "reports_without_tribe": without_tribe,
            "lost": {
                "wood": lost_wood, "clay": lost_clay,
                "iron": lost_iron, "crop": lost_crop,
                "total": lost_total,
            },
            "stolen": {
                "bounty": {
                    "wood": b_wood, "clay": b_clay,
                    "iron": b_iron, "crop": b_crop,
                    "total": bounty_total,
                },
                "hero_inventory": {
                    "wood": h_wood, "clay": h_clay,
                    "iron": h_iron, "crop": h_crop,
                    "total": hi_total,
                },
                "total": {
                    "wood": s_wood, "clay": s_clay,
                    "iron": s_iron, "crop": s_crop,
                    "total": stolen_total,
                },
            },
            "net": stolen_total - lost_total,
        }

    # ---------------------------------------------------------------------------
    # EP-SPAWN — Composición, tipo inferido, peor combinación y estado cooldown
    # ---------------------------------------------------------------------------

    async def get_oasis_spawn_composition(self, timer_min: int) -> dict:
        """
        Devuelve composición típica, inferencia de tipo, peor combinación a batir
        (dado timer_min en minutos) y estado cooldown/respawn para todos los oasis.

        timer_min: 6|7|10|15 — validado en el router antes de llegar aquí.
        200 siempre, incluso con oasis: [].

        Ver spec docs/specs/oasis-spawn-mechanics-stats.md §8 EP-SPAWN y §9.
        Añadido en la feature oasis-spawn-mechanics-stats (2026-06-02).
        """
        from core.game_data.oasis_spawn_catalog import (
            SPAWN_TIMER_S,
            OASIS_TYPE_SETS,
            COOLDOWN_THRESHOLD_S,
        )

        computed_at = datetime.now(timezone.utc)
        timer_s = timer_min * 60  # convertir a segundos

        # ── Paso 1: Cargar stats de defensa de animales nature ─────────────────
        # Preferir game_data_port si está disponible (TR-07 / RN-CAT-02).
        # En el adaptador no tenemos acceso directo a app.state, así que cargamos
        # directamente del JSON. Si en el futuro se inyecta el port, se sustituye.
        # TODO(Pieza 5 fase 2): retirar avg_regen_per_hour junto con la migración de frontend
        nature_def = _load_nature_defense_stats()

        # ── Paso 2: Composición por (oasis, animal) — solo present > 0 (RN-COMP-01) ─
        comp_sql = """
            SELECT
                r.coord_x_dest,
                r.coord_y_dest,
                a.animal_ordinal,
                AVG(a.present)  AS avg_present,
                MAX(a.present)  AS max_present,
                COUNT(*)        AS burst_count
            FROM attack_report_animals a
            JOIN attack_reports r ON r.id = a.report_id
            WHERE a.present > 0
            GROUP BY r.coord_x_dest, r.coord_y_dest, a.animal_ordinal
            ORDER BY r.coord_x_dest, r.coord_y_dest, a.animal_ordinal
        """

        # ── Paso 3: Metadatos por oasis — total_attacks, last_attack, utc_offset ─
        meta_sql = """
            SELECT
                coord_x_dest,
                coord_y_dest,
                COUNT(*)         AS total_attacks,
                MAX(attacked_at) AS last_attack,
                utc_offset       AS last_utc_offset
            FROM attack_reports
            GROUP BY coord_x_dest, coord_y_dest
            ORDER BY coord_x_dest, coord_y_dest
        """
        # Nota: utc_offset de la fila con MAX(attacked_at) obtenido con subconsulta
        # correlacionada o con esta simplificación: la mayoría de oasis tienen un
        # único offset. Si varía, se toma el del último reporte de forma aproximada.
        # En v1 se acepta esta simplificación (EC-13).
        meta_sql_precise = """
            SELECT
                a.coord_x_dest,
                a.coord_y_dest,
                a.total_attacks,
                a.last_attack,
                b.utc_offset AS last_utc_offset
            FROM (
                SELECT
                    coord_x_dest,
                    coord_y_dest,
                    COUNT(*)         AS total_attacks,
                    MAX(attacked_at) AS last_attack
                FROM attack_reports
                GROUP BY coord_x_dest, coord_y_dest
            ) a
            JOIN attack_reports b
              ON b.coord_x_dest = a.coord_x_dest
             AND b.coord_y_dest = a.coord_y_dest
             AND b.attacked_at  = a.last_attack
            GROUP BY a.coord_x_dest, a.coord_y_dest
        """

        # ── Paso 3b (v2.5): Atribución por reportes — DOS queries, una sola vez ──
        # La query farm_coords_sql (JOIN farm_slots→farm_lists→villages) y el dict
        # coords_to_villages fueron ELIMINADOS en v2.5. Bug v2.4 documentado en el
        # Registro §17 del spec: aldea "05" invisible porque sus oasis aparecían en
        # farm lists de 00/01/02/03 → la regla "primario gana" los atribuía a ellas.
        # Atribución ahora EXCLUSIVAMENTE por blobs de reportes reales (RN-CITY-01 v2.5).
        # Anti N+1: dos queries ejecutadas UNA sola vez, resultado indexado en dicts
        # para cruce O(1) en Python (RN-CITY-07).

        # Villages conocidas para canonización (a) — RN-CITY-02 v2.5
        # TODO: filtrar por world_id cuando attack_reports.world_id deje de ser NULL (TR-11)
        async with self._conn.execute("SELECT name FROM villages") as cursor:
            all_village_names: list[str] = [r["name"] for r in await cursor.fetchall()]

        # Blobs de origin_village_name por oasis para canonización (a) y extracción (b) — RN-CITY-03 v2.5
        blobs_sql = """
            SELECT coord_x_dest, coord_y_dest,
                   GROUP_CONCAT(DISTINCT origin_village_name) AS blobs_raw
            FROM attack_reports
            GROUP BY coord_x_dest, coord_y_dest
        """

        async with self._conn.execute(comp_sql) as cursor:
            comp_rows = await cursor.fetchall()
        async with self._conn.execute(meta_sql_precise) as cursor:
            meta_rows = await cursor.fetchall()
        async with self._conn.execute(blobs_sql) as cursor:
            blob_rows = await cursor.fetchall()

        # Indexar blobs de origin_village_name por oasis (RN-CITY-03 v2.5)
        blobs_by_oasis: dict[tuple[int, int], list[str]] = {}
        for row in blob_rows:
            k = (row["coord_x_dest"], row["coord_y_dest"])
            raw = row["blobs_raw"] or ""
            blobs_by_oasis[k] = [b for b in raw.split(",") if b]

        # ── Paso 4: Indexar composición por (coord_x, coord_y) ────────────────
        comp_by_oasis: dict[tuple, list[dict]] = {}
        for row in comp_rows:
            key = (row["coord_x_dest"], row["coord_y_dest"])
            comp_by_oasis.setdefault(key, []).append({
                "animal_ordinal": row["animal_ordinal"],
                "avg_present":    round(row["avg_present"], 1),
                "max_present":    int(row["max_present"]),
                "burst_count":    int(row["burst_count"]),
            })

        # ── Paso 5-9: Construir la respuesta por oasis ─────────────────────────
        oasis_entries = []
        for meta in meta_rows:
            cx = meta["coord_x_dest"]
            cy = meta["coord_y_dest"]
            key = (cx, cy)
            comp_list = comp_by_oasis.get(key, [])
            observed: set[int] = {c["animal_ordinal"] for c in comp_list}

            # Inferir tipo y confianza (RN-TYP-01..05, EC-05, EC-07, EC-11)
            tipo, confidence = infer_type(observed, comp_list)

            set_base: set[int] = OASIS_TYPE_SETS.get(tipo, set()) if tipo else set()

            # Calcular elapsed_seconds (RN-CD-01, EC-09)
            last_attack_str: str = meta["last_attack"]
            utc_offset_str: str | None = meta["last_utc_offset"]
            elapsed_s = _calc_elapsed_seconds(
                last_attack_str, utc_offset_str, computed_at
            )

            # Clasificar estado (RN-CD-02..04)
            status = _spawn_status(elapsed_s, tipo, OASIS_TYPE_SETS, SPAWN_TIMER_S, COOLDOWN_THRESHOLD_S)

            # Calcular composición de especies y peor combinación
            species_list = []
            def_inf_total = 0
            def_cav_total = 0

            for comp in comp_list:
                ordinal = comp["animal_ordinal"]
                is_anomaly = (tipo is not None) and (ordinal not in set_base)

                # Peor combinación (RN-WORST-01..05)
                wc = _worst_case_count(
                    ordinal, comp["max_present"], tipo, is_anomaly, timer_s, SPAWN_TIMER_S
                )

                def_inf = nature_def.get(ordinal, {}).get("def_infantry", 0)
                def_cav = nature_def.get(ordinal, {}).get("def_cavalry", 0)
                def_inf_contrib = (wc * def_inf) if wc is not None else None
                def_cav_contrib = (wc * def_cav) if wc is not None else None

                # Acumular en summary solo animales del set base (RN-WORST-05)
                if not is_anomaly and def_inf_contrib is not None:
                    def_inf_total += def_inf_contrib
                    def_cav_total += def_cav_contrib

                species_list.append({
                    "animal_ordinal":           ordinal,
                    "icon_url":                 f"/static/icons/nature_{ordinal}.png",
                    "avg_present_per_burst":    comp["avg_present"],
                    "max_present_per_burst":    comp["max_present"],
                    "is_anomaly":               is_anomaly,
                    "spawn_timer_s":            SPAWN_TIMER_S.get(ordinal),
                    "worst_case_count":         wc,
                    "def_infantry_contribution": def_inf_contrib,
                    "def_cavalry_contribution":  def_cav_contrib,
                })

            worst_summary = (
                {"def_infantry_total": def_inf_total, "def_cavalry_total": def_cav_total}
                if tipo is not None else None
            )

            oasis_entries.append({
                "coord_x_dest":    cx,
                "coord_y_dest":    cy,
                "total_attacks":   meta["total_attacks"],
                "last_attack":     last_attack_str,
                "inferred_type":   tipo,
                "confidence":      confidence,
                "spawn_status":    status,
                "elapsed_seconds": round(max(0.0, elapsed_s), 1),
                "attackers": _infer_attackers(
                    key, blobs_by_oasis, all_village_names
                ),  # v2.6: pares (player, village) DISTINCT, ordenados A-Z (§4.7, RN-GROUP-01)
                "species":         species_list,
                "worst_case_summary": worst_summary,
            })

        # Ordenar: oasis con tipo inferido primero, luego por last_attack DESC
        oasis_entries.sort(key=lambda e: e["last_attack"], reverse=True)
        oasis_entries.sort(key=lambda e: e["inferred_type"] is None)

        return {
            "computed_at": computed_at.isoformat(),
            "timer_min":   timer_min,
            "oasis":       oasis_entries,
        }

    # ---------------------------------------------------------------------------
    # EP-TD — Distribución temporal de animales por intervalo de farmeo (v3)
    # ---------------------------------------------------------------------------

    async def get_animal_temporal_distribution(
        self,
        interval_minutes: int,
        lang: str,
        translation_port,
    ) -> dict:
        """
        Distribución empírica de animales por tipo de oasis para una cadencia dada (v4).

        interval_minutes: frecuencia en minutos. Valores válidos: 6|7|10|15|30|60|120|180|240|300.
        lang: código de idioma validado (25 soportados).
        translation_port: puerto de traducción para resolver nombres de animales.

        Binning por umbral inferior (Opción B): la ventana de F es [F*60, F_next*60) en segundos.
        Ventana de 300: [18000, ∞) abierta por arriba.
        Gaps < 360s (< 6 min) se descartan silenciosamente.

        Infiere el tipo de cada oasis (hierro/arcilla/madera/cereal/sin_clasificar) usando
        infer_type() (elevada desde _infer_type en v3). Reutiliza la misma query de
        composición que EP-SPAWN para garantizar consistencia de clasificación.

        Devuelve { interval_minutes, interval_label, window, n_reports_in_window, types }.
        types: 5 secciones fijas (hierro, arcilla, madera, cereal, sin_clasificar).
        Cada sección incluye (v4):
          - max_present: int|null en cada animal (máximo sobre n_valid)
          - total_animals: {avg, mode, max, n_valid, n_total} — suma de present por reporte,
            regla TODO-O-NADA: excluye reportes con cualquier present=NULL de n_valid
          - avg_bounty: {wood, clay, iron, crop, total} — media sobre TODOS los reportes
            de la sección (denominador = n_reports_in_section, incluye derrotas con bounty=0)
          - oasis_coords: [{x, y}] — oasis distintos del tipo ordenados (y ASC, x ASC)
        200 siempre. Ver spec docs/specs/bd-ataques-oasis-temporal-distribution.md §8 EP-TD (v4).
        """
        # ── Constantes de módulo — tabla de bins (minutos), etiquetas y tipos (v3) ─
        _WINDOWS: dict[int, tuple[int, int | None]] = {
            6:   (6,   7),
            7:   (7,   10),
            10:  (10,  15),
            15:  (15,  30),
            30:  (30,  60),
            60:  (60,  120),
            120: (120, 180),
            180: (180, 240),
            240: (240, 300),
            300: (300, None),  # abierto por arriba
        }
        _LABELS: dict[int, str] = {
            6: "6 min", 7: "7 min", 10: "10 min", 15: "15 min", 30: "30 min",
            60: "1h", 120: "2h", 180: "3h", 240: "4h", 300: "5h+",
        }
        # Labels de presentación v3 — "arcilla" → "Barro" (RN-TD18)
        _TYPE_LABELS: dict[str | None, str] = {
            "hierro": "Hierro",
            "arcilla": "Barro",
            "madera": "Madera",
            "cereal": "Cereal",
            None: "Sin clasificar",
        }
        # Orden fijo de las 5 secciones: None = sin_clasificar al final (RN-TD17)
        _TYPE_ORDER: list[str | None] = ["hierro", "arcilla", "madera", "cereal", None]

        lower_min, upper_min = _WINDOWS[interval_minutes]
        lower_sec = lower_min * 60
        upper_sec = upper_min * 60 if upper_min is not None else None
        is_open = (upper_sec is None)
        interval_label = _LABELS[interval_minutes]

        # ── Paso 1 (v3): Inferir tipo por oasis — misma query que EP-SPAWN ───────
        # Construye oasis_type_map: {(cx, cy): (tipo, confidence)} para cruzar con gaps.
        # Oasis sin ningún present>0 (solo derrotas) no aparecen → tipo=None (EC-TD20).
        comp_sql = """
            SELECT
                r.coord_x_dest,
                r.coord_y_dest,
                a.animal_ordinal,
                COUNT(*) AS burst_count
            FROM attack_report_animals a
            JOIN attack_reports r ON r.id = a.report_id
            WHERE a.present > 0
            GROUP BY r.coord_x_dest, r.coord_y_dest, a.animal_ordinal
        """
        async with self._conn.execute(comp_sql) as cursor:
            comp_rows = await cursor.fetchall()

        # Agrupar composición por oasis
        comp_by_oasis: dict[tuple[int, int], list[dict]] = defaultdict(list)
        for row in comp_rows:
            comp_by_oasis[(row["coord_x_dest"], row["coord_y_dest"])].append({
                "animal_ordinal": row["animal_ordinal"],
                "burst_count":    int(row["burst_count"]),
            })

        # Llamar a infer_type (función pública de módulo, elevada en v3 — RN-TD14)
        oasis_type_map: dict[tuple[int, int], tuple[str | None, str | None]] = {}
        for (cx, cy), comp_list in comp_by_oasis.items():
            observed: set[int] = {c["animal_ordinal"] for c in comp_list}
            tipo, confidence = infer_type(observed, comp_list)
            oasis_type_map[(cx, cy)] = (tipo, confidence)

        # ── Paso 2: Calcular gaps con LAG (ampliado con coord_x/y para cruzar con mapa) ─
        # CRÍTICO: el LAG debe calcularse a nivel de REPORTE (una fila por ataque al oasis),
        # no a nivel de animal-reporte. Si el JOIN con animals se hace ANTES del LAG,
        # attack_reports tendría múltiples filas por reporte (una por animal) y el LAG
        # tomaría el animal anterior del mismo reporte en lugar del reporte anterior.
        # Solución: CTE que calcula los gaps a nivel de reporte, luego JOIN con animals.
        # v4: la CTE incluye bounty_wood/clay/iron/crop del reporte para avg_bounty (RN-TD22,
        # RN-TD25). El botín aparece repetido en cada fila de animal del JOIN, pero se
        # deduplica en Python usando type_bounty[tipo] = dict{report_id → (w,c,i,cr)}.
        gap_sql = """
            WITH report_gaps AS (
                SELECT
                    r.id            AS report_id,
                    r.coord_x_dest,
                    r.coord_y_dest,
                    r.attacked_at,
                    r.bounty_wood,
                    r.bounty_clay,
                    r.bounty_iron,
                    r.bounty_crop,
                    CAST(
                        (UNIXEPOCH(r.attacked_at) -
                         UNIXEPOCH(LAG(r.attacked_at) OVER w)) AS INTEGER
                    ) AS gap_seconds
                FROM attack_reports r
                WINDOW w AS (
                    PARTITION BY r.coord_x_dest, r.coord_y_dest
                    ORDER BY r.attacked_at
                )
            )
            SELECT
                rg.report_id,
                rg.coord_x_dest,
                rg.coord_y_dest,
                rg.bounty_wood,
                rg.bounty_clay,
                rg.bounty_iron,
                rg.bounty_crop,
                a.animal_ordinal,
                a.animal_name,
                a.present,
                rg.gap_seconds
            FROM report_gaps rg
            JOIN attack_report_animals a ON a.report_id = rg.report_id
            ORDER BY a.animal_ordinal, rg.coord_x_dest, rg.coord_y_dest, rg.attacked_at
        """
        async with self._conn.execute(gap_sql) as cursor:
            raw_rows = await cursor.fetchall()

        # ── Paso 3: Filtrar gaps inválidos (RN-TD02, RN-TD04, EC-TD07) ──────────
        # Descarta: NULL (primer ataque), <= 0 (relojes inconsistentes), < 360 (< 6 min)
        valid_rows = [
            row for row in raw_rows
            if row["gap_seconds"] is not None
            and row["gap_seconds"] > 0
            and row["gap_seconds"] >= 360
        ]

        # ── Paso 4: Filtrar por la ventana de la frecuencia solicitada (RN-TD03) ──
        if is_open:
            window_rows = [r for r in valid_rows if r["gap_seconds"] >= lower_sec]
        else:
            window_rows = [
                r for r in valid_rows
                if lower_sec <= r["gap_seconds"] < upper_sec
            ]

        # ── Paso 5 (v3): Etiquetar cada gap con el tipo de su oasis ──────────────
        # Si el oasis no está en oasis_type_map → tipo=None → "sin_clasificar" (EC-TD20)
        def _get_tipo_confidence(row) -> tuple[str | None, str | None]:
            return oasis_type_map.get(
                (row["coord_x_dest"], row["coord_y_dest"]), (None, None)
            )

        # ── Paso 6 (v3+v4): Agrupar por (tipo, animal_ordinal) ──────────────────
        # type_oasis_ids[tipo]: set de (cx,cy) con al menos un gap en la ventana
        # type_oasis_low[tipo]: set de (cx,cy) con confidence="low"
        # type_groups[tipo][ordinal]: { n_total, valids, name_raw }
        # type_report_ids[tipo]: set de report_ids distintos en la sección
        # --- v4: estructuras auxiliares para avg_bounty y total_animals ---
        # type_bounty[tipo]: dict{report_id → (wood, clay, iron, crop)} — deduplicado
        #   por report_id (RN-TD25: el botín NO se acumula por fila de animal, sino
        #   UNA VEZ por reporte distinto dentro de la sección).
        # type_report_nulls[tipo]: dict{report_id → bool} — True si algún animal del
        #   reporte tiene present=NULL (regla TODO-O-NADA de RN-TD21).
        # type_report_sums[tipo]: dict{report_id → int} — suma de present no nulos del
        #   reporte para ese tipo (se usa solo si any_null=False al final).
        type_oasis_ids:    dict = defaultdict(set)
        type_oasis_low:    dict = defaultdict(set)
        type_groups:       dict = defaultdict(
            lambda: defaultdict(lambda: {"n_total": 0, "valids": [], "name_raw": ""})
        )
        type_report_ids:   dict = defaultdict(set)
        type_bounty:       dict = defaultdict(dict)       # {tipo: {rid: (w,c,i,cr)}}
        type_report_nulls: dict = defaultdict(dict)       # {tipo: {rid: bool}}
        type_report_sums:  dict = defaultdict(dict)       # {tipo: {rid: int}}

        for row in window_rows:
            tipo, confidence = _get_tipo_confidence(row)
            cx, cy = row["coord_x_dest"], row["coord_y_dest"]
            rid = row["report_id"]

            type_oasis_ids[tipo].add((cx, cy))
            if confidence == "low":
                type_oasis_low[tipo].add((cx, cy))
            type_report_ids[tipo].add(rid)

            # v4: botín — deduplicar por report_id (RN-TD25)
            if rid not in type_bounty[tipo]:
                type_bounty[tipo][rid] = (
                    row["bounty_wood"],
                    row["bounty_clay"],
                    row["bounty_iron"],
                    row["bounty_crop"],
                )

            # v4: total_animals — acumular sum/any_null por reporte (RN-TD21)
            present_val = row["present"]
            if rid not in type_report_nulls[tipo]:
                type_report_nulls[tipo][rid] = False
                type_report_sums[tipo][rid] = 0
            if present_val is None:
                type_report_nulls[tipo][rid] = True   # marca: este reporte tiene NULL
            else:
                type_report_sums[tipo][rid] += present_val

            ordinal = row["animal_ordinal"]
            type_groups[tipo][ordinal]["n_total"] += 1
            if present_val is not None:  # RN-TD05: NULL (derrota) excluido de media/moda
                type_groups[tipo][ordinal]["valids"].append(present_val)
            if not type_groups[tipo][ordinal]["name_raw"]:
                type_groups[tipo][ordinal]["name_raw"] = row["animal_name"]

        # ── Paso 7: Resolver nombres localizados vía translation_port ──────────
        # El dict devuelto por JsonTranslationAdapter usa la clave "nombre" (no "name").
        # El enum se accede como Tribe.NATURE (mayúsculas), no Tribe.nature.
        names_by_ordinal: dict[int, str] = {}
        try:
            name_entries = translation_port.get_troop_names_by_tribe(Tribe.NATURE, lang)
            names_by_ordinal = {entry["ordinal"]: entry["nombre"] for entry in name_entries}
        except Exception:
            logger.warning(
                "get_animal_temporal_distribution: fallo al resolver nombres para lang=%s",
                lang,
            )

        # ── Paso 8: Helpers para construir los campos de cada sección ────────────

        def _build_animals(tipo: str | None) -> list[dict]:
            """Lista de animales con estadísticas (v4: incluye max_present, RN-TD20)."""
            result = []
            for ordinal in sorted(type_groups[tipo].keys()):
                data = type_groups[tipo][ordinal]
                n_valid = len(data["valids"])

                # Media redondeada a 2 decimales (RN-TD06)
                avg_present = (
                    round(sum(data["valids"]) / n_valid, 2) if n_valid > 0 else None
                )

                # Moda en Python con Counter; empates → lista ordenada ASC (RN-TD07)
                if n_valid > 0:
                    counter = Counter(data["valids"])
                    max_count = max(counter.values())
                    mode_present = sorted(k for k, v in counter.items() if v == max_count)
                else:
                    mode_present = []

                # v4: máximo de present sobre n_valid (RN-TD20)
                max_present = max(data["valids"]) if n_valid > 0 else None

                # Nombre localizado con fallback al nombre de BD (EC-TD16)
                localized_name = names_by_ordinal.get(ordinal, data["name_raw"])

                result.append({
                    "animal_ordinal": ordinal,
                    "animal_name": localized_name,
                    "icon_url": f"/static/icons/nature_{ordinal}.png",
                    "avg_present": avg_present,
                    "mode_present": mode_present,
                    "max_present": max_present,
                    "n_total": data["n_total"],
                    "n_valid": n_valid,
                })
            return result

        def _build_avg_bounty(tipo: str | None) -> dict:
            """
            Media del botín por sección. Denominador = n_reports_in_section (RN-TD22).
            Incluye derrotas con bounty=0 (DDL NOT NULL DEFAULT 0).
            avg_bounty.total = media del total (w+c+i+cr) por reporte, NO suma de medias
            individuales (RN-TD23). Enteros redondeados (redondeo bancario Python 3).
            Sección vacía → todos a 0 (EC-TD33).
            """
            bounty_dict = type_bounty[tipo]   # {rid: (w,c,i,cr)}
            report_ids_section = type_report_ids[tipo]
            n = len(report_ids_section)
            if n == 0:
                return {"wood": 0, "clay": 0, "iron": 0, "crop": 0, "total": 0}

            sum_w = sum_c = sum_i = sum_cr = sum_total = 0
            for rid in report_ids_section:
                if rid in bounty_dict:
                    w, c, i, cr = bounty_dict[rid]
                else:
                    # El reporte cayó en la ventana pero no tiene entrada en bounty_dict
                    # (no debería ocurrir porque el SELECT incluye bounty en report_gaps,
                    # pero defensivamente tratamos como 0).
                    w = c = i = cr = 0
                sum_w  += w
                sum_c  += c
                sum_i  += i
                sum_cr += cr
                sum_total += w + c + i + cr

            return {
                "wood":  round(sum_w  / n),
                "clay":  round(sum_c  / n),
                "iron":  round(sum_i  / n),
                "crop":  round(sum_cr / n),
                "total": round(sum_total / n),
            }

        def _build_total_animals(tipo: str | None) -> dict:
            """
            Distribución del total de animales por reporte (suma de present de todos los
            animales del reporte). Regla TODO-O-NADA (RN-TD21): si cualquier animal del
            reporte tiene present=NULL, ese reporte se excluye de n_valid.
            n_total = n_reports_in_section (invariante).
            Sección vacía → {avg:null, mode:[], max:null, n_valid:0, n_total:0}.
            """
            report_ids_section = type_report_ids[tipo]
            n_total = len(report_ids_section)
            if n_total == 0:
                return {"avg": None, "mode": [], "max": None, "n_valid": 0, "n_total": 0}

            # Recoger totales válidos (reportes sin ningún NULL en sus animales)
            valid_totals: list[int] = []
            nulls_dict = type_report_nulls[tipo]
            sums_dict  = type_report_sums[tipo]
            for rid in report_ids_section:
                # Si el reporte no apareció en el bucle de window_rows para este tipo
                # (defensivo) → tratarlo como any_null=True (excluir de n_valid).
                any_null = nulls_dict.get(rid, True)
                if not any_null:
                    valid_totals.append(sums_dict.get(rid, 0))

            n_valid = len(valid_totals)
            if n_valid == 0:
                return {"avg": None, "mode": [], "max": None, "n_valid": 0, "n_total": n_total}

            avg = round(sum(valid_totals) / n_valid, 2)
            counter = Counter(valid_totals)
            max_count = max(counter.values())
            mode = sorted(k for k, v in counter.items() if v == max_count)
            maximum = max(valid_totals)

            return {"avg": avg, "mode": mode, "max": maximum, "n_valid": n_valid, "n_total": n_total}

        def _build_oasis_coords(tipo: str | None) -> list[dict]:
            """
            Lista de coordenadas de oasis distintos del tipo con al menos un gap en
            la ventana. Serializa type_oasis_ids[tipo] ordenado (y ASC, x ASC) (RN-TD24).
            Sección vacía → [].
            """
            oasis_set = type_oasis_ids[tipo]
            if not oasis_set:
                return []
            return [
                {"x": cx, "y": cy}
                for cx, cy in sorted(oasis_set, key=lambda coord: (coord[1], coord[0]))
            ]

        # ── Paso 9 (v3+v4): Construir array types con las 5 secciones fijas (RN-TD17) ─
        # Orden fijo: hierro → arcilla → madera → cereal → sin_clasificar
        # v4: cada sección incluye oasis_coords, avg_bounty, total_animals (RN-TD20..25)
        types: list[dict] = []
        for tipo in _TYPE_ORDER:
            oasis_type_key = tipo if tipo is not None else "sin_clasificar"
            types.append({
                "oasis_type":             oasis_type_key,
                "oasis_type_label":       _TYPE_LABELS[tipo],
                "n_oasis":                len(type_oasis_ids[tipo]),
                "n_oasis_low_confidence": len(type_oasis_low[tipo]),
                "n_reports_in_section":   len(type_report_ids[tipo]),
                "oasis_coords":           _build_oasis_coords(tipo),
                "avg_bounty":             _build_avg_bounty(tipo),
                "total_animals":          _build_total_animals(tipo),
                "animals":                _build_animals(tipo),
            })

        # ── Paso 10: n_reports_in_window = suma de las 5 secciones (RN-TD19) ────
        n_reports_in_window = sum(len(type_report_ids[t]) for t in _TYPE_ORDER)

        # ── Paso 11: Construir respuesta raíz ────────────────────────────────────
        return {
            "interval_minutes": interval_minutes,
            "interval_label": interval_label,
            "window": {
                "lower_min": lower_min,
                "upper_min": upper_min,
                "is_open": is_open,
            },
            "n_reports_in_window": n_reports_in_window,
            "types": types,
        }


# ---------------------------------------------------------------------------
# Helpers de módulo — EP-SPAWN (spawn composition)
# ---------------------------------------------------------------------------

def _load_nature_defense_stats() -> dict[int, dict[str, int]]:
    """
    Carga los stats de defensa de animales de naturaleza desde
    seeds/game_data/troop_stats.json (tribe == "nature").

    Devuelve { ordinal: { "def_infantry": N, "def_cavalry": N } }.

    RN-CAT-02: si el fichero no existe o es inválido, devuelve dict vacío
    (el cálculo de worst_case continúa con def=0 en lugar de fallar).
    """
    import os
    import json as _json

    # Ruta relativa al directorio raíz del proyecto (2 niveles arriba de adapters/)
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(base_dir, "seeds", "game_data", "troop_stats.json")

    try:
        with open(path, encoding="utf-8") as f:
            data = _json.load(f)
    except (FileNotFoundError, ValueError):
        logger.warning("_load_nature_defense_stats: no se pudo cargar %s", path)
        return {}

    result: dict[int, dict[str, int]] = {}
    for entry in data:
        if entry.get("tribe") == "nature":
            ordinal = entry.get("ordinal")
            if ordinal is not None:
                result[int(ordinal)] = {
                    "def_infantry": int(entry.get("def_infantry", 0)),
                    "def_cavalry":  int(entry.get("def_cavalry",  0)),
                }
    return result


def infer_type(
    observed_ordinales: set[int],
    comp_list: list[dict],
) -> tuple[str | None, str | None]:
    """
    Infiere el tipo de oasis por similitud de Jaccard |∩|/|∪| (RN-TYP-02 v2).

    Función pública de módulo (elevada desde _infer_type en v3) para que tanto
    EP-SPAWN como EP-TD la reutilicen sin duplicar el cálculo de Jaccard (RN-TD14).

    En caso de empate: tipo con menor cardinal de set; si persiste, alfabético (EC-07).
    Confianza: "low" si <3 bursts con present>0, "medium" si >=3 (RN-TYP-04/05).

    Devuelve (tipo, confidence). Si observed vacío → (None, None) (RN-TYP-05).
    """
    from core.game_data.oasis_spawn_catalog import OASIS_TYPE_SETS

    if not observed_ordinales:
        return (None, None)

    # RN-TYP-02 (v2): similitud de Jaccard (|∩| / |∪|), NO solapamiento bruto.
    # El solapamiento bruto hacía que "cereal" (set universal {1..10}) ganara casi
    # siempre y anulaba la detección de anomalías. Jaccard penaliza el set universal:
    # un oasis de hierro {1,2,4} da 1.0 con hierro y 0.3 con cereal → gana hierro; y
    # un cocodrilo en un oasis de arcilla {1,2,5,8} clasifica como arcilla con el
    # cocodrilo (ordinal 8) marcado como anomalía. Ver spec §4.2 / EC-07 / EC-11.
    scores: dict[str, float] = {}
    for tipo, set_base in OASIS_TYPE_SETS.items():
        union = observed_ordinales | set_base
        scores[tipo] = len(observed_ordinales & set_base) / len(union) if union else 0.0

    max_score = max(scores.values())
    if max_score == 0.0:
        # Sin intersección con ningún set (EC-11): elegir el más específico
        # (menor cardinal de set) y, si persiste, alfabético.
        candidates = list(OASIS_TYPE_SETS.keys())
    else:
        candidates = [t for t, s in scores.items() if s == max_score]
    candidates.sort(key=lambda t: (len(OASIS_TYPE_SETS[t]), t))
    tipo = candidates[0]

    # Confianza basada en total de bursts (sumatorio de burst_count) (RN-TYP-04)
    total_bursts = sum(c["burst_count"] for c in comp_list)
    confidence = "medium" if total_bursts >= 3 else "low"

    return (tipo, confidence)


def _calc_elapsed_seconds(
    last_attack_str: str,
    utc_offset_str: str | None,
    computed_at,
) -> float:
    """
    Calcula los segundos transcurridos entre last_attack (hora local del servidor)
    y computed_at (UTC).

    Reutiliza _parse_utc_offset (RN-CD-01 / spec §14 paso 3).
    EC-09: si el resultado es negativo (reloj adelantado), devuelve 0.0.
    """
    try:
        # attacked_at es naive (hora local del servidor), sin zona horaria
        local_dt = datetime.fromisoformat(last_attack_str)
        offset_td = _parse_utc_offset(utc_offset_str) if utc_offset_str else timedelta(0)
        # Convertir a UTC restando el offset: hora_utc = hora_local - offset
        attack_utc = local_dt - offset_td
        # Hacer aware para comparar con computed_at (UTC aware)
        attack_utc_aware = attack_utc.replace(tzinfo=timezone.utc)
        elapsed = (computed_at - attack_utc_aware).total_seconds()
    except Exception:
        logger.warning("_calc_elapsed_seconds: no se pudo parsear '%s'", last_attack_str)
        elapsed = 0.0
    return max(0.0, elapsed)


def _spawn_status(
    elapsed_s: float,
    tipo: str | None,
    oasis_type_sets: dict,
    spawn_timer_s: dict,
    cooldown_threshold_s: int,
) -> str:
    """
    Clasifica el estado de spawn del oasis (RN-CD-02..04).

    - "respawning": elapsed_s <= max(timers del set base)
    - "cooldown":   elapsed_s > cooldown_threshold_s (4h por defecto)
    - "unknown":    tipo no inferido o zona intermedia

    RN-CD-04: si tipo es None → "unknown".
    """
    if tipo is None:
        return "unknown"

    set_base = oasis_type_sets.get(tipo, set())
    relevant_timers = [spawn_timer_s[o] for o in set_base if o in spawn_timer_s]
    if not relevant_timers:
        return "unknown"

    umbral_respawning = max(relevant_timers)  # el animal más lento (RN-CD-03)
    if elapsed_s <= umbral_respawning:
        return "respawning"
    elif elapsed_s > cooldown_threshold_s:
        return "cooldown"
    else:
        return "unknown"  # zona intermedia indeterminada (RN-CD-03 nota)


def _worst_case_count(
    animal_ordinal: int,
    max_present: int,
    tipo: str | None,
    is_anomaly: bool,
    timer_s: int,
    spawn_timer_s: dict,
) -> int | None:
    """
    Calcula el conteo de animales en el peor caso para un animal del set base.

    RN-WORST-01: spawns_en_intervalo = floor(timer_s / SPAWN_TIMER_S[o])
    RN-WORST-02: peor_combo = max_present + spawns_en_intervalo
    RN-WORST-04: si tipo es None → None
    RN-WORST-05: anomalías → None (excluidas del cálculo)
    """
    if tipo is None or is_anomaly:
        return None
    spawn_t = spawn_timer_s.get(animal_ordinal, 0)
    if spawn_t == 0:
        return None
    extra_spawns = math.floor(timer_s / spawn_t)
    return max_present + extra_spawns


# ---------------------------------------------------------------------------
# Constante de marcadores "from village" multi-idioma — EP-SPAWN v2.6
# ---------------------------------------------------------------------------
# Cada entrada es el literal que precede al nombre de aldea en origin_village_name.
# Para añadir un idioma: añadir su marcador aquí sin tocar la lógica principal.
# El marcador inglés "from village" está VERIFICADO con datos reales del usuario.
# Los demás son best-effort/extensibles — ver RN-CITY-12 en el spec.
_FROM_VILLAGE_MARKERS: tuple[str, ...] = (
    "from village",      # inglés      (servidor del usuario — verificado)
    "aus dem Dorf",      # alemán
    "desde la aldea",    # español
    "du village",        # francés
    "из деревни",        # ruso
    "dalla village",     # italiano (placeholder — extender si se verifica)
    "من قرية",           # árabe
    "van het dorp",      # neerlandés
    "från byn",          # sueco
    "z vesnice",         # checo
    "из села",           # serbio/ucraniano (variante cirílica)
)


def _extract_player_village_from_blob(
    blob: str,
    all_village_names: list[str],
) -> list[tuple[str, str]]:
    """
    Extrae todos los pares (player, village) de un blob origin_village_name.

    Algoritmo v2.6 (§4.7 del spec):
      A. Quitar tag de alianza "[...] " si existe.
      B. Buscar primer marcador en _FROM_VILLAGE_MARKERS (case-insensitive).
         - Si encontrado y player+village no vacíos:
             player = texto antes del marcador (stripped)
             village_raw = texto después del marcador (stripped)
         - Si no encontrado o player/village vacíos:
             player = "Desconocido", village_raw = None
      C. Canonizar village_raw contra all_village_names (substring, mayor longitud gana).
         - Si village_raw es None: intentar canonizar el blob entero (resto).
         - Si canonización da varios de igual longitud: un par por cada canónico.
         - Si canonización no da nada: usar village_raw directamente (o "Desconocido").

    Devuelve lista de pares (player, village). Nunca vacía:
    mínimo [("Desconocido", "Desconocido")].

    RN-ACCT-01..07, RN-CITY-01..12, EC-ACCT-01..06, EC-CITY-01..12.
    """
    # A. Quitar tag de alianza
    resto = blob.strip()
    if resto.startswith("["):
        closing = resto.find("]")
        if closing != -1:
            resto = resto[closing + 1:].strip()

    # B. Buscar marcador
    resto_lower = resto.lower()
    player: str = "Desconocido"
    village_raw: str | None = None
    for marker in _FROM_VILLAGE_MARKERS:
        idx = resto_lower.find(marker.lower())
        if idx != -1:
            player_candidate = resto[:idx].strip()
            village_candidate = resto[idx + len(marker):].strip()
            if player_candidate and village_candidate:
                player = player_candidate
                village_raw = village_candidate
                break
            # Si player_candidate vacío o village_candidate vacío: blob inválido (EC-ACCT-06)

    # C. Canonizar village
    search_in = village_raw if village_raw is not None else resto
    matches = [vname for vname in all_village_names if vname in search_in]
    if matches:
        max_len = max(len(m) for m in matches)
        canonical = [m for m in matches if len(m) == max_len]
        return [(player, c) for c in canonical]

    # Sin canonización: usar village_raw o "Desconocido"
    village = village_raw if village_raw else "Desconocido"
    return [(player, village)]


def _infer_attackers(
    key: tuple[int, int],
    blobs_by_oasis: dict[tuple[int, int], list[str]],
    all_village_names: list[str],
) -> list[dict[str, str]]:
    """
    Devuelve la lista DISTINCT de pares {player, village} para un oasis,
    ordenada por player A-Z y luego village A-Z.

    Nunca vacía: mínimo [{"player":"Desconocido","village":"Desconocido"}].

    Reemplaza _infer_origin_villages() de v2.5 (§4.7 v2.6, RN-GROUP-01,
    RN-ACCT-05, RN-CITY-01 v2.6). El JOIN farm_slots sigue eliminado.
    """
    blobs = blobs_by_oasis.get(key, [])
    found: set[tuple[str, str]] = set()

    for blob in blobs:
        pairs = _extract_player_village_from_blob(blob, all_village_names)
        found.update(pairs)

    if not found:
        return [{"player": "Desconocido", "village": "Desconocido"}]

    sorted_pairs = sorted(found, key=lambda p: (p[0], p[1]))
    return [{"player": p, "village": v} for p, v in sorted_pairs]
