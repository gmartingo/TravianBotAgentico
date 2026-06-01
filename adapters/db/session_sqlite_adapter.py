"""
Adaptador SQLite para Human Sessions (SessionTimelineDbPort).

Tablas gestionadas (DDL inline, patrón del proyecto):
  - world_session_timeline   — bloques horarios por (world_id, weekday, block_index)
  - world_session_override   — override manual activo, 1 fila por world_id máximo
  - world_session_config     — config PASIVO por world_id

Decisiones de diseño:
  - Una fila por bloque (no JSON blob): permite CHECK constraints de SQLite y
    consultas individuales sin deserializar.
  - jitter_minutes se almacena a nivel de fila para compatibilidad futura con
    jitter diferente por bloque. En esta versión todos los bloques del día
    usan el mismo jitter (tomado del primer bloque o de la request del PUT).
  - La validación de solapes ocurre ANTES del relleno de huecos, sobre los
    bloques crudos del usuario.
  - Los overrides expirados se borran de BD en el momento de la lectura
    (get_override), no en un job periódico.
  - expires_at se almacena como TEXT ISO-8601 UTC (patrón del proyecto).

Spec §7.6, §7.7, §7.8, §9.6.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import aiosqlite

from core.entities.session import (
    SessionBlock,
    SessionConfig,
    SessionMode,
    SessionOverride,
    SessionTimeline,
)
from core.ports.session_timeline_db_port import SessionTimelineDbPort

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_CREATE_WORLD_SESSION_TIMELINE = """
CREATE TABLE IF NOT EXISTS world_session_timeline (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id      INTEGER NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    weekday       INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    block_index   INTEGER NOT NULL,
    start_hour    INTEGER NOT NULL CHECK (start_hour BETWEEN 0 AND 23),
    start_minute  INTEGER NOT NULL CHECK (start_minute BETWEEN 0 AND 59),
    end_hour      INTEGER NOT NULL CHECK (end_hour BETWEEN 0 AND 24),
    end_minute    INTEGER NOT NULL CHECK (end_minute BETWEEN 0 AND 59),
    mode          TEXT    NOT NULL CHECK (mode IN ('HARDCORE','PASIVO','DISCONNECTED')),
    jitter_minutes INTEGER NOT NULL DEFAULT 15 CHECK (jitter_minutes >= 0),
    UNIQUE (world_id, weekday, block_index)
);
"""

_CREATE_IDX_TIMELINE = """
CREATE INDEX IF NOT EXISTS idx_world_session_timeline_world_day
    ON world_session_timeline(world_id, weekday);
"""

_CREATE_WORLD_SESSION_OVERRIDE = """
CREATE TABLE IF NOT EXISTS world_session_override (
    world_id    INTEGER PRIMARY KEY REFERENCES worlds(id) ON DELETE CASCADE,
    mode        TEXT    NOT NULL CHECK (mode IN ('HARDCORE','PASIVO','DISCONNECTED')),
    expires_at  TEXT    NOT NULL
);
"""

_CREATE_WORLD_SESSION_CONFIG = """
CREATE TABLE IF NOT EXISTS world_session_config (
    world_id                  INTEGER PRIMARY KEY REFERENCES worlds(id) ON DELETE CASCADE,
    passive_interval_factor   REAL    NOT NULL DEFAULT 2.0
                                      CHECK (passive_interval_factor BETWEEN 1.5 AND 5.0),
    passive_send_probability  REAL    NOT NULL DEFAULT 0.05
                                      CHECK (passive_send_probability BETWEEN 0.01 AND 0.50)
);
"""


# ---------------------------------------------------------------------------
# Helpers internos (funciones puras de validación y relleno)
# Spec §9.6 — se ubican en el adaptador, no en el core (SRP).
# ---------------------------------------------------------------------------

def _to_minutes(hour: int, minute: int) -> int:
    """Convierte (hora, minuto) a minutos desde 00:00. 24:00 → 1440."""
    return hour * 60 + minute if not (hour == 24 and minute == 0) else 1440


def _validate_no_overlaps(blocks: list[SessionBlock]) -> None:
    """
    Valida que la lista de bloques NO tiene solapes.
    Los huecos son legítimos (se rellenan después con DISCONNECTED).
    Lanza ValueError con mensaje descriptivo si hay solapes o si end <= start.

    Spec §9.6.
    """
    intervals: list[tuple[int, int]] = []
    for b in blocks:
        start = _to_minutes(b.start_hour, b.start_minute)
        end   = _to_minutes(b.end_hour,   b.end_minute)
        # end == 0 significa end_hour=24 → ya manejado por _to_minutes devolviendo 1440
        if end <= start:
            raise ValueError(
                "end debe ser mayor que start. "
                "Los bloques que cruzan medianoche no están soportados: "
                "divide en dos bloques (HH:MM-24:00 y 00:00-HH:MM)."
            )
        intervals.append((start, end))

    intervals.sort(key=lambda x: x[0])
    for i in range(len(intervals) - 1):
        _, end_a = intervals[i]
        start_b, _ = intervals[i + 1]
        if end_a > start_b:
            # Calcular el rango de solape para el mensaje
            overlap_s = start_b
            overlap_e = end_a
            hs, ms = overlap_s // 60, overlap_s % 60
            he, me = overlap_e // 60, overlap_e % 60
            raise ValueError(
                f"Los bloques se solapan en {hs:02d}:{ms:02d}-{he:02d}:{me:02d}."
            )


def _fill_gaps_with_disconnected(blocks: list[SessionBlock]) -> list[SessionBlock]:
    """
    Dado un conjunto de bloques (posiblemente incompleto), devuelve el timeline
    completo de 24h rellenando los huecos con bloques DISCONNECTED.

    PRE: los bloques no tienen solapes (ya validado antes de llamar).
    Los bloques de entrada pueden estar en cualquier orden; se ordenan internamente.

    Spec §8.3 — pseudocódigo de relleno de huecos.
    """
    # Ordenar por inicio
    sorted_blocks = sorted(blocks, key=lambda b: _to_minutes(b.start_hour, b.start_minute))

    result: list[SessionBlock] = []
    cursor = 0  # minutos desde 00:00; avanza hasta 1440 (24:00)

    for block in sorted_blocks:
        start_m = _to_minutes(block.start_hour, block.start_minute)
        end_m   = _to_minutes(block.end_hour,   block.end_minute)

        if start_m > cursor:
            # Hueco antes de este bloque → rellenar con DISCONNECTED
            result.append(SessionBlock(
                start_hour=cursor // 60,
                start_minute=cursor % 60,
                end_hour=start_m // 60,
                end_minute=start_m % 60,
                mode=SessionMode.DISCONNECTED,
            ))

        result.append(block)
        cursor = end_m

    # Hueco al final del día
    if cursor < 1440:
        result.append(SessionBlock(
            start_hour=cursor // 60,
            start_minute=cursor % 60,
            end_hour=24,
            end_minute=0,
            mode=SessionMode.DISCONNECTED,
        ))

    return result


def _row_to_block(row: aiosqlite.Row) -> SessionBlock:
    return SessionBlock(
        start_hour=row["start_hour"],
        start_minute=row["start_minute"],
        end_hour=row["end_hour"],
        end_minute=row["end_minute"],
        mode=SessionMode(row["mode"]),
    )


# ---------------------------------------------------------------------------
# Adaptador
# ---------------------------------------------------------------------------

class SessionSQLiteAdapter(SessionTimelineDbPort):
    """
    Implementa SessionTimelineDbPort con aiosqlite.
    Comparte la misma conexión SQLite (WAL) que el resto de adaptadores.
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def ensure_tables(self) -> None:
        """
        Crea las tablas si no existen. Llamar en el lifespan de la app,
        DESPUÉS de AccountSQLiteAdapter.ensure_tables() (que crea la tabla worlds).
        No activa PRAGMA foreign_keys aquí: AccountSQLiteAdapter ya lo activa
        en la conexión compartida.
        """
        await self._conn.execute(_CREATE_WORLD_SESSION_TIMELINE)
        await self._conn.execute(_CREATE_IDX_TIMELINE)
        await self._conn.execute(_CREATE_WORLD_SESSION_OVERRIDE)
        await self._conn.execute(_CREATE_WORLD_SESSION_CONFIG)
        await self._conn.commit()
        logger.debug("SessionSQLiteAdapter: tablas aseguradas")

    # ------------------------------------------------------------------
    # Timeline
    # ------------------------------------------------------------------

    async def get_timeline(self, world_id: int, weekday: int) -> SessionTimeline | None:
        """
        Devuelve el timeline del día. None si no existe configuración explícita.
        """
        rows = await self._conn.execute_fetchall(
            """
            SELECT start_hour, start_minute, end_hour, end_minute, mode, jitter_minutes
              FROM world_session_timeline
             WHERE world_id = ? AND weekday = ?
             ORDER BY block_index ASC
            """,
            (world_id, weekday),
        )
        if not rows:
            return None

        blocks = [_row_to_block(r) for r in rows]
        jitter = rows[0]["jitter_minutes"]

        return SessionTimeline(
            world_id=world_id,
            weekday=weekday,
            blocks=blocks,
            jitter_minutes=jitter,
            is_default=False,
        )

    async def upsert_timeline(self, timeline: SessionTimeline) -> SessionTimeline:
        """
        Reemplaza los bloques del (world_id, weekday):
        1. Valida no-solapes.
        2. Rellena huecos con DISCONNECTED.
        3. Borra los bloques antiguos y escribe los nuevos.
        Devuelve el timeline completo tras la operación.
        """
        # 1. Validar solapes sobre los bloques crudos del usuario
        _validate_no_overlaps(timeline.blocks)

        # 2. Rellenar huecos
        complete_blocks = _fill_gaps_with_disconnected(timeline.blocks)

        # 3. Persistir (DELETE + INSERT en transacción)
        async with self._conn.execute("BEGIN"):
            await self._conn.execute(
                "DELETE FROM world_session_timeline WHERE world_id = ? AND weekday = ?",
                (timeline.world_id, timeline.weekday),
            )
            for idx, block in enumerate(complete_blocks):
                await self._conn.execute(
                    """
                    INSERT INTO world_session_timeline
                      (world_id, weekday, block_index,
                       start_hour, start_minute, end_hour, end_minute,
                       mode, jitter_minutes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        timeline.world_id,
                        timeline.weekday,
                        idx,
                        block.start_hour,
                        block.start_minute,
                        block.end_hour,
                        block.end_minute,
                        block.mode.value,
                        timeline.jitter_minutes,
                    ),
                )
        await self._conn.commit()

        return SessionTimeline(
            world_id=timeline.world_id,
            weekday=timeline.weekday,
            blocks=complete_blocks,
            jitter_minutes=timeline.jitter_minutes,
            is_default=False,
        )

    # ------------------------------------------------------------------
    # Override
    # ------------------------------------------------------------------

    async def get_override(self, world_id: int) -> SessionOverride | None:
        """
        Devuelve el override activo. Si ya expiró, lo borra de BD y devuelve None.
        """
        row = await self._conn.execute_fetchall(
            "SELECT mode, expires_at FROM world_session_override WHERE world_id = ?",
            (world_id,),
        )
        if not row:
            return None

        row = row[0]
        expires_at = datetime.fromisoformat(row["expires_at"])
        now = datetime.now(timezone.utc)

        # Normalizar timezone para comparar
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if now >= expires_at:
            # Override expirado → limpiar BD
            await self.clear_override(world_id)
            return None

        return SessionOverride(
            world_id=world_id,
            mode=SessionMode(row["mode"]),
            expires_at=expires_at,
        )

    async def set_override(self, override: SessionOverride) -> None:
        """Escribe o reemplaza el override activo para el mundo."""
        expires_str = override.expires_at.isoformat()
        await self._conn.execute(
            """
            INSERT INTO world_session_override (world_id, mode, expires_at)
            VALUES (?, ?, ?)
            ON CONFLICT(world_id) DO UPDATE SET mode=excluded.mode, expires_at=excluded.expires_at
            """,
            (override.world_id, override.mode.value, expires_str),
        )
        await self._conn.commit()

    async def clear_override(self, world_id: int) -> None:
        """Borra el override activo. Idempotente."""
        await self._conn.execute(
            "DELETE FROM world_session_override WHERE world_id = ?",
            (world_id,),
        )
        await self._conn.commit()

    # ------------------------------------------------------------------
    # Config PASIVO
    # ------------------------------------------------------------------

    async def get_session_config(self, world_id: int) -> SessionConfig:
        """
        Devuelve la config PASIVO. Si no hay fila, devuelve los defaults.
        """
        rows = await self._conn.execute_fetchall(
            """
            SELECT passive_interval_factor, passive_send_probability
              FROM world_session_config
             WHERE world_id = ?
            """,
            (world_id,),
        )
        if not rows:
            return SessionConfig(world_id=world_id)  # defaults: 2.0 y 0.05

        row = rows[0]
        return SessionConfig(
            world_id=world_id,
            passive_interval_factor=row["passive_interval_factor"],
            passive_send_probability=row["passive_send_probability"],
        )

    async def upsert_session_config(self, config: SessionConfig) -> SessionConfig:
        """
        UPSERT idempotente de la config PASIVO.
        Escribe los valores que trae config; si no había fila, inserta con los valores dados.
        """
        await self._conn.execute(
            """
            INSERT INTO world_session_config
              (world_id, passive_interval_factor, passive_send_probability)
            VALUES (?, ?, ?)
            ON CONFLICT(world_id) DO UPDATE SET
              passive_interval_factor  = excluded.passive_interval_factor,
              passive_send_probability = excluded.passive_send_probability
            """,
            (
                config.world_id,
                config.passive_interval_factor,
                config.passive_send_probability,
            ),
        )
        await self._conn.commit()
        return config
