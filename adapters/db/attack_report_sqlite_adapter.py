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
from datetime import datetime, timezone

import aiosqlite

from core.entities.attack_report import AttackReportPreview
from core.ports.attack_report_port import AttackReportPort, DuplicateReportError


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
        """Crea las 3 tablas y los 4 índices si no existen."""
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
        await self._conn.commit()

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

        # --- Insertar cabecera ---
        try:
            async with self._conn.execute(
                """
                INSERT INTO attack_reports (
                    coord_x_dest, coord_y_dest, origin_village_name,
                    attacked_at, utc_offset,
                    bounty_wood, bounty_clay, bounty_iron, bounty_crop,
                    capacity_used, capacity_total,
                    hero_inventory_json, raw_text, world_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        """
        # ── Paso 1: Apariciones globales ──────────────────────────────────────
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
        return {
            "scope": "global",
            "animal_appearances": [
                {
                    "animal_ordinal": row["animal_ordinal"],
                    "animal_name": row["animal_name"],
                    "appearances": row["appearances"],
                    "avg_present": round(row["avg_present"], 2) if row["avg_present"] is not None else None,
                    "max_present": row["max_present"],
                    "min_present": row["min_present_nonzero"],  # puede ser None (guardia defensiva)
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
