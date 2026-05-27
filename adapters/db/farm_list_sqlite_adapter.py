"""
Adaptador SQLite para farm lists (FarmListDbPort).

Implementa FarmListDbPort usando aiosqlite con SQL crudo (sin ORM),
coherente con el patrón del proyecto.

Tablas gestionadas:
  - farm_schedulers        — schedulers de envío periódico
  - farm_lists             — listas de vacas por aldea
  - farm_slots             — vacas individuales (PK compuesta id+farm_list_id)
  - farm_list_send_history — historial de envíos (TTL 7 días)
  - slot_events            — eventos de cambio de estado de slots

Decisiones de diseño:
  - Las fechas de FarmScheduler se almacenan como VARCHAR(30) en ISO (consistencia
    con el bot de referencia).
  - sync_farm_list hace matching de slots por coordenadas (x,y) para preservar
    total_bounty y estado bot aunque Travian reasigne IDs (RN-15).
  - add_farm_list_send_event purga automáticamente los registros >7 días (RN-13).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import aiosqlite

from core.entities.farm_list import BotSlotStatus, FarmList, FarmSlot, SlotEvent
from core.entities.farm_list_send_event import FarmListSendEvent
from core.entities.farm_scheduler import FarmScheduler
from core.entities.village import Village
from core.exceptions import (
    FarmListNotFoundError,
    FarmSlotNotFoundError,
    SchedulerNotFoundError,
)
from core.ports.farm_list_db_port import FarmListDbPort

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_CREATE_FARM_SCHEDULERS = """
CREATE TABLE IF NOT EXISTS farm_schedulers (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id         INTEGER NOT NULL REFERENCES worlds(id),
    name             TEXT    NOT NULL,
    interval_min_ms  INTEGER NOT NULL,
    interval_max_ms  INTEGER NOT NULL,
    is_enabled       INTEGER NOT NULL DEFAULT 1,
    last_run         TEXT    NOT NULL DEFAULT '',
    next_run         TEXT    NOT NULL DEFAULT '',
    execution_count  INTEGER NOT NULL DEFAULT 0
);
"""

_CREATE_IDX_FARM_SCHEDULERS_WORLD = """
CREATE INDEX IF NOT EXISTS idx_farm_schedulers_world ON farm_schedulers(world_id);
"""

_CREATE_FARM_LISTS = """
CREATE TABLE IF NOT EXISTS farm_lists (
    id               INTEGER PRIMARY KEY,
    name             TEXT    NOT NULL,
    owner_village_id INTEGER NOT NULL REFERENCES villages(id),
    scheduler_id     INTEGER REFERENCES farm_schedulers(id) ON DELETE SET NULL
);
"""

_CREATE_IDX_FARM_LISTS_VILLAGE = """
CREATE INDEX IF NOT EXISTS idx_farm_lists_village ON farm_lists(owner_village_id);
"""

_CREATE_IDX_FARM_LISTS_SCHEDULER = """
CREATE INDEX IF NOT EXISTS idx_farm_lists_scheduler ON farm_lists(scheduler_id);
"""

_CREATE_FARM_SLOTS = """
CREATE TABLE IF NOT EXISTS farm_slots (
    id                   INTEGER NOT NULL,
    farm_list_id         INTEGER NOT NULL REFERENCES farm_lists(id) ON DELETE CASCADE,
    target_name          TEXT    NOT NULL,
    x                    INTEGER NOT NULL,
    y                    INTEGER NOT NULL,
    population           INTEGER NOT NULL DEFAULT 0,
    troops               TEXT    NOT NULL DEFAULT '{}',
    is_active            INTEGER NOT NULL DEFAULT 1,
    disabled_by_bot      INTEGER NOT NULL DEFAULT 0,
    last_raid_state      TEXT    NOT NULL DEFAULT '',
    last_raid_time       TEXT    NOT NULL DEFAULT '',
    last_raid_report_id  TEXT    NOT NULL DEFAULT '',
    last_raid_bounty     INTEGER NOT NULL DEFAULT 0,
    average_raid_bounty  INTEGER NOT NULL DEFAULT 0,
    total_bounty         INTEGER NOT NULL DEFAULT 0,
    distance             REAL    NOT NULL DEFAULT 0.0,
    disabled_at          TEXT,
    cooldown_seconds     INTEGER NOT NULL DEFAULT 3600,
    report_id_at_disable TEXT    NOT NULL DEFAULT '',
    PRIMARY KEY (id, farm_list_id)
);
"""

_CREATE_IDX_FARM_SLOTS_LIST = """
CREATE INDEX IF NOT EXISTS idx_farm_slots_list ON farm_slots(farm_list_id);
"""

_CREATE_FARM_LIST_SEND_HISTORY = """
CREATE TABLE IF NOT EXISTS farm_list_send_history (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    farm_list_id         INTEGER NOT NULL,
    farm_list_name       TEXT    NOT NULL,
    world_id             INTEGER NOT NULL,
    timestamp            TEXT    NOT NULL,
    status               TEXT    NOT NULL,
    being_raided_current INTEGER,
    being_raided_total   INTEGER,
    triggered_by         TEXT    NOT NULL,
    scheduler_id         INTEGER,
    bot_disabled_slots   TEXT    NOT NULL DEFAULT '[]',
    loot_wood            INTEGER NOT NULL DEFAULT 0,
    loot_clay            INTEGER NOT NULL DEFAULT 0,
    loot_iron            INTEGER NOT NULL DEFAULT 0,
    loot_crop            INTEGER NOT NULL DEFAULT 0
);
"""

_CREATE_IDX_FARM_HISTORY_WORLD = """
CREATE INDEX IF NOT EXISTS idx_farm_history_world ON farm_list_send_history(world_id, timestamp);
"""

_CREATE_SLOT_EVENTS = """
CREATE TABLE IF NOT EXISTS slot_events (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp            TEXT    NOT NULL,
    slot_id              INTEGER NOT NULL,
    slot_name            TEXT    NOT NULL,
    farm_list_id         INTEGER NOT NULL,
    farm_list_name       TEXT    NOT NULL,
    world_id             INTEGER NOT NULL,
    event_type           TEXT    NOT NULL,
    last_raid_state      TEXT    NOT NULL DEFAULT '',
    cooldown_seconds     INTEGER NOT NULL DEFAULT 3600,
    last_raid_report_id  TEXT    NOT NULL DEFAULT ''
);
"""

_CREATE_IDX_SLOT_EVENTS_WORLD = """
CREATE INDEX IF NOT EXISTS idx_slot_events_world ON slot_events(world_id, timestamp);
"""

# ---------------------------------------------------------------------------
# Helpers de conversión
# ---------------------------------------------------------------------------

_HISTORY_TTL_DAYS = 7


def _dt_to_str(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.isoformat()


def _str_to_dt(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _to_slot(row: aiosqlite.Row) -> FarmSlot:
    return FarmSlot(
        id=row["id"],
        farm_list_id=row["farm_list_id"],
        target_name=row["target_name"],
        x=row["x"],
        y=row["y"],
        population=row["population"],
        troops=json.loads(row["troops"] or "{}"),
        is_active=bool(row["is_active"]),
        disabled_by_bot=bool(row["disabled_by_bot"]),
        last_raid_state=row["last_raid_state"] or "",
        last_raid_time=row["last_raid_time"] or "",
        last_raid_report_id=row["last_raid_report_id"] or "",
        last_raid_bounty=row["last_raid_bounty"] or 0,
        average_raid_bounty=row["average_raid_bounty"] or 0,
        total_bounty=row["total_bounty"] or 0,
        distance=float(row["distance"] or 0.0),
        disabled_at=_str_to_dt(row["disabled_at"] or ""),
        cooldown_seconds=row["cooldown_seconds"] or 3600,
        report_id_at_disable=row["report_id_at_disable"] or "",
    )


def _to_scheduler(row: aiosqlite.Row, farm_list_ids: list[int]) -> FarmScheduler:
    return FarmScheduler(
        id=row["id"],
        world_id=row["world_id"],
        name=row["name"],
        interval_min_ms=row["interval_min_ms"],
        interval_max_ms=row["interval_max_ms"],
        is_enabled=bool(row["is_enabled"]),
        last_run=_str_to_dt(row["last_run"] or ""),
        next_run=_str_to_dt(row["next_run"] or ""),
        execution_count=row["execution_count"] or 0,
        farm_list_ids=farm_list_ids,
    )


def _to_farm_list(row: aiosqlite.Row) -> FarmList:
    return FarmList(
        id=row["id"],
        name=row["name"],
        owner_village_id=row["owner_village_id"],
        scheduler_id=row["scheduler_id"],
    )


def _to_send_event(row: aiosqlite.Row) -> FarmListSendEvent:
    return FarmListSendEvent(
        id=row["id"],
        farm_list_id=row["farm_list_id"],
        farm_list_name=row["farm_list_name"],
        world_id=row["world_id"],
        timestamp=_str_to_dt(row["timestamp"]) or datetime.utcnow(),
        status=row["status"],
        being_raided_current=row["being_raided_current"] or 0,
        being_raided_total=row["being_raided_total"] or 0,
        triggered_by=row["triggered_by"],
        scheduler_id=row["scheduler_id"],
        bot_disabled_slots=json.loads(row["bot_disabled_slots"] or "[]"),
        loot_wood=row["loot_wood"] or 0,
        loot_clay=row["loot_clay"] or 0,
        loot_iron=row["loot_iron"] or 0,
        loot_crop=row["loot_crop"] or 0,
    )


def _to_slot_event(row: aiosqlite.Row) -> SlotEvent:
    return SlotEvent(
        id=row["id"],
        timestamp=_str_to_dt(row["timestamp"]) or datetime.utcnow(),
        slot_id=row["slot_id"],
        slot_name=row["slot_name"],
        farm_list_id=row["farm_list_id"],
        farm_list_name=row["farm_list_name"],
        world_id=row["world_id"],
        event_type=row["event_type"],
        last_raid_state=row["last_raid_state"] or "",
        cooldown_seconds=row["cooldown_seconds"] or 3600,
        last_raid_report_id=row["last_raid_report_id"] or "",
    )


# ---------------------------------------------------------------------------
# Adaptador
# ---------------------------------------------------------------------------

class FarmListSQLiteAdapter(FarmListDbPort):
    """
    Implementación de FarmListDbPort sobre SQLite + aiosqlite.

    Recibe una conexión aiosqlite ya abierta (con WAL activado) del lifespan.
    No abre ni cierra la conexión.
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    # ------------------------------------------------------------------
    # Inicialización del esquema
    # ------------------------------------------------------------------

    async def ensure_tables(self) -> None:
        """
        Crea las tablas de farm lists si no existen.
        Idempotente. Se llama desde el lifespan de la aplicación.
        """
        await self._conn.execute("PRAGMA foreign_keys = ON")
        for ddl in [
            _CREATE_FARM_SCHEDULERS,
            _CREATE_IDX_FARM_SCHEDULERS_WORLD,
            _CREATE_FARM_LISTS,
            _CREATE_IDX_FARM_LISTS_VILLAGE,
            _CREATE_IDX_FARM_LISTS_SCHEDULER,
            _CREATE_FARM_SLOTS,
            _CREATE_IDX_FARM_SLOTS_LIST,
            _CREATE_FARM_LIST_SEND_HISTORY,
            _CREATE_IDX_FARM_HISTORY_WORLD,
            _CREATE_SLOT_EVENTS,
            _CREATE_IDX_SLOT_EVENTS_WORLD,
        ]:
            await self._conn.execute(ddl)
        await self._conn.commit()

    # ------------------------------------------------------------------
    # Farm lists
    # ------------------------------------------------------------------

    async def sync_farm_lists(
        self, village_id: int, farm_lists: list[FarmList]
    ) -> list[FarmList]:
        """
        Sincroniza todas las farm lists de una aldea.
        - Inserta/actualiza las que llegan del DOM.
        - Borra las que ya no están en Travian.
        """
        incoming_ids = {fl.id for fl in farm_lists}

        # Obtener IDs existentes en BD para esta aldea.
        cursor = await self._conn.execute(
            "SELECT id FROM farm_lists WHERE owner_village_id = ?", (village_id,)
        )
        rows = await cursor.fetchall()
        existing_ids = {r["id"] for r in rows}

        # Borrar las que ya no existen.
        to_delete = existing_ids - incoming_ids
        for fl_id in to_delete:
            await self._conn.execute("DELETE FROM farm_lists WHERE id = ?", (fl_id,))

        # Sincronizar cada lista.
        result: list[FarmList] = []
        for fl in farm_lists:
            synced = await self._sync_one_farm_list(fl, village_id)
            result.append(synced)

        await self._conn.commit()
        return result

    async def _sync_one_farm_list(self, fl: FarmList, village_id: int) -> FarmList:
        """INSERT OR REPLACE de una farm list (sin modificar scheduler_id)."""
        await self._conn.execute(
            """
            INSERT INTO farm_lists (id, name, owner_village_id)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name             = excluded.name,
                owner_village_id = excluded.owner_village_id
            """,
            (fl.id, fl.name, village_id),
        )
        # Sincronizar slots.
        fl_with_slots = FarmList(
            id=fl.id,
            name=fl.name,
            owner_village_id=village_id,
            slots=fl.slots,
        )
        return await self._sync_slots(fl_with_slots)

    async def sync_farm_list(self, farm_list: FarmList) -> FarmList:
        """
        Sincroniza una sola farm list por ID, haciendo matching de slots por (x, y).
        Preserva total_bounty y estado bot si las coordenadas coinciden (RN-15, EC-05).
        EC-06: si el DOM marca is_active=True y había disabled_by_bot=True, resetea el estado bot.
        """
        # Asegurar que la farm list existe en BD.
        cursor = await self._conn.execute(
            "SELECT id, owner_village_id, scheduler_id FROM farm_lists WHERE id = ?",
            (farm_list.id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise FarmListNotFoundError(farm_list.id)

        # Actualizar nombre si cambió.
        await self._conn.execute(
            "UPDATE farm_lists SET name = ? WHERE id = ?",
            (farm_list.name, farm_list.id),
        )

        synced = await self._sync_slots(farm_list)
        await self._conn.commit()
        return synced

    async def _sync_slots(self, farm_list: FarmList) -> FarmList:
        """
        Sincroniza los slots de una farm list. Matching por (x, y) para preservar
        total_bounty y estado bot aunque Travian reasigne IDs (RN-15, EC-05).

        EC-06: si el DOM devuelve is_active=True y el slot en BD tiene
        disabled_by_bot=True, resetea: disabled_by_bot=False, disabled_at=None,
        cooldown_seconds=3600.
        """
        # Cargar slots existentes en BD.
        cursor = await self._conn.execute(
            "SELECT * FROM farm_slots WHERE farm_list_id = ?", (farm_list.id,)
        )
        rows = await cursor.fetchall()
        existing_by_coords: dict[tuple[int, int], FarmSlot] = {}
        existing_by_id: dict[int, FarmSlot] = {}
        for r in rows:
            s = _to_slot(r)
            existing_by_coords[(s.x, s.y)] = s
            existing_by_id[s.id] = s

        incoming_ids = {s.id for s in farm_list.slots}

        # Borrar slots que ya no aparecen en el DOM.
        for old_id in list(existing_by_id.keys()):
            if old_id not in incoming_ids:
                # Puede que el ID haya cambiado pero las coords sean las mismas;
                # en ese caso lo reemplazamos abajo. Borramos el antiguo aquí.
                await self._conn.execute(
                    "DELETE FROM farm_slots WHERE id = ? AND farm_list_id = ?",
                    (old_id, farm_list.id),
                )

        synced_slots: list[FarmSlot] = []
        for slot in farm_list.slots:
            # Buscar slot existente por coords para preservar estado bot.
            existing = existing_by_coords.get((slot.x, slot.y))
            if existing is None:
                existing = existing_by_id.get(slot.id)

            # EC-06: si el DOM dice is_active=True y el slot tenía disabled_by_bot=True,
            # resetear el estado bot (el usuario lo reactivó directamente en Travian).
            disabled_by_bot = existing.disabled_by_bot if existing else False
            disabled_at = existing.disabled_at if existing else None
            cooldown_seconds = (existing.cooldown_seconds if existing else 3600)
            report_id_at_disable = existing.report_id_at_disable if existing else ""
            total_bounty = existing.total_bounty if existing else 0

            if slot.is_active and disabled_by_bot:
                disabled_by_bot = False
                disabled_at = None
                cooldown_seconds = 3600
                report_id_at_disable = ""
                logger.info(
                    "Slot (%d,%d) reactivado en Travian por el usuario — resetando estado bot",
                    slot.x, slot.y,
                )

            await self._conn.execute(
                """
                INSERT INTO farm_slots (
                    id, farm_list_id, target_name, x, y, population, troops,
                    is_active, disabled_by_bot, last_raid_state, last_raid_time,
                    last_raid_report_id, last_raid_bounty, average_raid_bounty,
                    total_bounty, distance, disabled_at, cooldown_seconds,
                    report_id_at_disable
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id, farm_list_id) DO UPDATE SET
                    target_name          = excluded.target_name,
                    x                    = excluded.x,
                    y                    = excluded.y,
                    population           = excluded.population,
                    troops               = excluded.troops,
                    is_active            = excluded.is_active,
                    last_raid_state      = excluded.last_raid_state,
                    last_raid_time       = excluded.last_raid_time,
                    last_raid_report_id  = excluded.last_raid_report_id,
                    last_raid_bounty     = excluded.last_raid_bounty,
                    average_raid_bounty  = excluded.average_raid_bounty,
                    distance             = excluded.distance,
                    disabled_by_bot      = ?,
                    disabled_at          = ?,
                    cooldown_seconds     = ?,
                    report_id_at_disable = ?,
                    total_bounty         = total_bounty
                """,
                (
                    slot.id, farm_list.id, slot.target_name, slot.x, slot.y,
                    slot.population, json.dumps(slot.troops),
                    int(slot.is_active), int(disabled_by_bot),
                    slot.last_raid_state, slot.last_raid_time,
                    slot.last_raid_report_id, slot.last_raid_bounty,
                    slot.average_raid_bounty, total_bounty,
                    slot.distance, _dt_to_str(disabled_at) or None,
                    cooldown_seconds, report_id_at_disable,
                    # Parámetros para el UPDATE SET
                    int(disabled_by_bot),
                    _dt_to_str(disabled_at) or None,
                    cooldown_seconds,
                    report_id_at_disable,
                ),
            )
            synced_slots.append(FarmSlot(
                id=slot.id,
                farm_list_id=farm_list.id,
                target_name=slot.target_name,
                x=slot.x,
                y=slot.y,
                population=slot.population,
                troops=slot.troops,
                is_active=slot.is_active,
                disabled_by_bot=disabled_by_bot,
                last_raid_state=slot.last_raid_state,
                last_raid_time=slot.last_raid_time,
                last_raid_report_id=slot.last_raid_report_id,
                last_raid_bounty=slot.last_raid_bounty,
                average_raid_bounty=slot.average_raid_bounty,
                total_bounty=total_bounty,
                distance=slot.distance,
                disabled_at=disabled_at,
                cooldown_seconds=cooldown_seconds,
                report_id_at_disable=report_id_at_disable,
            ))

        farm_list_out = FarmList(
            id=farm_list.id,
            name=farm_list.name,
            owner_village_id=farm_list.owner_village_id,
            slots=synced_slots,
        )
        # Recuperar scheduler_id de BD.
        cursor = await self._conn.execute(
            "SELECT scheduler_id FROM farm_lists WHERE id = ?", (farm_list.id,)
        )
        row = await cursor.fetchone()
        if row:
            farm_list_out.scheduler_id = row["scheduler_id"]
        return farm_list_out

    async def get_farm_lists_by_village(self, village_id: int) -> list[FarmList]:
        cursor = await self._conn.execute(
            "SELECT * FROM farm_lists WHERE owner_village_id = ?", (village_id,)
        )
        rows = await cursor.fetchall()
        result = []
        for r in rows:
            fl = _to_farm_list(r)
            fl.slots = await self._load_slots(fl.id)
            result.append(fl)
        return result

    async def get_farm_lists_by_world(self, world_id: int) -> list[FarmList]:
        cursor = await self._conn.execute(
            """
            SELECT fl.* FROM farm_lists fl
            JOIN villages v ON fl.owner_village_id = v.id
            WHERE v.world_id = ?
            ORDER BY fl.id
            """,
            (world_id,),
        )
        rows = await cursor.fetchall()
        result = []
        for r in rows:
            fl = _to_farm_list(r)
            fl.slots = await self._load_slots(fl.id)
            result.append(fl)
        return result

    async def get_farm_list_by_id(self, farm_list_id: int) -> FarmList:
        cursor = await self._conn.execute(
            "SELECT * FROM farm_lists WHERE id = ?", (farm_list_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            raise FarmListNotFoundError(farm_list_id)
        fl = _to_farm_list(row)
        fl.slots = await self._load_slots(fl.id)
        return fl

    async def _load_slots(self, farm_list_id: int) -> list[FarmSlot]:
        cursor = await self._conn.execute(
            "SELECT * FROM farm_slots WHERE farm_list_id = ? ORDER BY id",
            (farm_list_id,),
        )
        rows = await cursor.fetchall()
        return [_to_slot(r) for r in rows]

    async def get_villages_by_world(self, world_id: int) -> list[Village]:
        cursor = await self._conn.execute(
            "SELECT id, world_id, data_id, name, x, y FROM villages WHERE world_id = ?",
            (world_id,),
        )
        rows = await cursor.fetchall()
        return [
            Village(
                id=r["id"],
                world_id=r["world_id"],
                data_id=r["data_id"],
                name=r["name"],
                x=r["x"],
                y=r["y"],
            )
            for r in rows
        ]

    async def upsert_village(self, world_id: int, data_id: int, name: str) -> Village:
        await self._conn.execute(
            """
            INSERT INTO villages (world_id, data_id, name, x, y)
            VALUES (?, ?, ?, 0, 0)
            ON CONFLICT(world_id, data_id) DO UPDATE SET name = excluded.name
            """,
            (world_id, data_id, name),
        )
        await self._conn.commit()
        cursor = await self._conn.execute(
            "SELECT id, world_id, data_id, name, x, y FROM villages WHERE world_id = ? AND data_id = ?",
            (world_id, data_id),
        )
        row = await cursor.fetchone()
        return Village(id=row["id"], world_id=row["world_id"], data_id=row["data_id"],
                       name=row["name"], x=row["x"], y=row["y"])

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    async def get_slot_by_id(self, slot_id: int, farm_list_id: int) -> FarmSlot:
        cursor = await self._conn.execute(
            "SELECT * FROM farm_slots WHERE id = ? AND farm_list_id = ?",
            (slot_id, farm_list_id),
        )
        row = await cursor.fetchone()
        if row is None:
            raise FarmSlotNotFoundError(slot_id)
        return _to_slot(row)

    async def update_slot_flags(
        self,
        slot_id: int,
        farm_list_id: int,
        *,
        is_active: bool | None = None,
        disabled_by_bot: bool | None = None,
    ) -> FarmSlot:
        parts = []
        params = []
        if is_active is not None:
            parts.append("is_active = ?")
            params.append(int(is_active))
        if disabled_by_bot is not None:
            parts.append("disabled_by_bot = ?")
            params.append(int(disabled_by_bot))

        if not parts:
            return await self.get_slot_by_id(slot_id, farm_list_id)

        params.extend([slot_id, farm_list_id])
        await self._conn.execute(
            f"UPDATE farm_slots SET {', '.join(parts)} WHERE id = ? AND farm_list_id = ?",
            params,
        )
        await self._conn.commit()
        return await self.get_slot_by_id(slot_id, farm_list_id)

    async def update_slot_cooldown_state(
        self,
        slot_id: int,
        farm_list_id: int,
        *,
        disabled_at: datetime | None,
        cooldown_seconds: int,
        report_id_at_disable: str,
        disabled_by_bot: bool,
        is_active: bool,
    ) -> FarmSlot:
        await self._conn.execute(
            """
            UPDATE farm_slots SET
                disabled_at          = ?,
                cooldown_seconds     = ?,
                report_id_at_disable = ?,
                disabled_by_bot      = ?,
                is_active            = ?
            WHERE id = ? AND farm_list_id = ?
            """,
            (
                _dt_to_str(disabled_at) or None,
                cooldown_seconds,
                report_id_at_disable,
                int(disabled_by_bot),
                int(is_active),
                slot_id,
                farm_list_id,
            ),
        )
        await self._conn.commit()
        return await self.get_slot_by_id(slot_id, farm_list_id)

    async def get_bot_status_slots(self, world_id: int) -> list[BotSlotStatus]:
        cursor = await self._conn.execute(
            """
            SELECT fs.id, fs.farm_list_id, fs.target_name, fs.disabled_by_bot,
                   fs.disabled_at, fs.cooldown_seconds, fs.last_raid_state,
                   fs.last_raid_report_id, fs.report_id_at_disable
            FROM farm_slots fs
            JOIN farm_lists fl ON fs.farm_list_id = fl.id
            JOIN villages v ON fl.owner_village_id = v.id
            WHERE v.world_id = ?
            ORDER BY fs.farm_list_id, fs.id
            """,
            (world_id,),
        )
        rows = await cursor.fetchall()
        return [
            BotSlotStatus(
                slot_id=r["id"],
                farm_list_id=r["farm_list_id"],
                target_name=r["target_name"],
                disabled_by_bot=bool(r["disabled_by_bot"]),
                disabled_at=_str_to_dt(r["disabled_at"] or ""),
                cooldown_seconds=r["cooldown_seconds"] or 3600,
                last_raid_state=r["last_raid_state"] or "",
                last_raid_report_id=r["last_raid_report_id"] or "",
                report_id_at_disable=r["report_id_at_disable"] or "",
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Eventos de slot
    # ------------------------------------------------------------------

    async def add_slot_event(self, event: SlotEvent) -> None:
        await self._conn.execute(
            """
            INSERT INTO slot_events (
                timestamp, slot_id, slot_name, farm_list_id, farm_list_name,
                world_id, event_type, last_raid_state, cooldown_seconds,
                last_raid_report_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                _dt_to_str(event.timestamp),
                event.slot_id,
                event.slot_name,
                event.farm_list_id,
                event.farm_list_name,
                event.world_id,
                event.event_type,
                event.last_raid_state,
                event.cooldown_seconds,
                event.last_raid_report_id,
            ),
        )
        await self._conn.commit()

    async def get_slot_events(
        self,
        world_id: int,
        *,
        scheduler_id: int | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[list[SlotEvent], int]:
        conditions = ["world_id = ?"]
        params: list = [world_id]
        if scheduler_id is not None:
            conditions.append(
                "farm_list_id IN (SELECT id FROM farm_lists WHERE scheduler_id = ?)"
            )
            params.append(scheduler_id)
        if from_dt is not None:
            conditions.append("timestamp >= ?")
            params.append(_dt_to_str(from_dt))
        if to_dt is not None:
            conditions.append("timestamp <= ?")
            params.append(_dt_to_str(to_dt))
        where = " AND ".join(conditions)

        count_cursor = await self._conn.execute(
            f"SELECT COUNT(*) FROM slot_events WHERE {where}", params
        )
        total = (await count_cursor.fetchone())[0]

        offset = (page - 1) * page_size
        cursor = await self._conn.execute(
            f"SELECT * FROM slot_events WHERE {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            params + [page_size, offset],
        )
        rows = await cursor.fetchall()
        return [_to_slot_event(r) for r in rows], total

    # ------------------------------------------------------------------
    # Schedulers
    # ------------------------------------------------------------------

    async def create_scheduler(self, scheduler: FarmScheduler) -> FarmScheduler:
        cursor = await self._conn.execute(
            """
            INSERT INTO farm_schedulers (
                world_id, name, interval_min_ms, interval_max_ms, is_enabled,
                last_run, next_run, execution_count
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                scheduler.world_id,
                scheduler.name,
                scheduler.interval_min_ms,
                scheduler.interval_max_ms,
                int(scheduler.is_enabled),
                _dt_to_str(scheduler.last_run),
                _dt_to_str(scheduler.next_run),
                scheduler.execution_count,
            ),
        )
        await self._conn.commit()
        new_id = cursor.lastrowid
        return FarmScheduler(
            id=new_id,
            world_id=scheduler.world_id,
            name=scheduler.name,
            interval_min_ms=scheduler.interval_min_ms,
            interval_max_ms=scheduler.interval_max_ms,
            is_enabled=scheduler.is_enabled,
            farm_list_ids=[],
        )

    async def get_scheduler(self, scheduler_id: int) -> FarmScheduler:
        cursor = await self._conn.execute(
            "SELECT * FROM farm_schedulers WHERE id = ?", (scheduler_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            raise SchedulerNotFoundError(scheduler_id)
        farm_list_ids = await self._get_farm_list_ids_by_scheduler(scheduler_id)
        return _to_scheduler(row, farm_list_ids)

    async def get_schedulers_by_world(self, world_id: int) -> list[FarmScheduler]:
        cursor = await self._conn.execute(
            "SELECT * FROM farm_schedulers WHERE world_id = ? ORDER BY id",
            (world_id,),
        )
        rows = await cursor.fetchall()
        result = []
        for r in rows:
            farm_list_ids = await self._get_farm_list_ids_by_scheduler(r["id"])
            result.append(_to_scheduler(r, farm_list_ids))
        return result

    async def _get_farm_list_ids_by_scheduler(self, scheduler_id: int) -> list[int]:
        cursor = await self._conn.execute(
            "SELECT id FROM farm_lists WHERE scheduler_id = ? ORDER BY id",
            (scheduler_id,),
        )
        rows = await cursor.fetchall()
        return [r["id"] for r in rows]

    async def update_scheduler(self, scheduler: FarmScheduler) -> FarmScheduler:
        cursor = await self._conn.execute(
            "SELECT id FROM farm_schedulers WHERE id = ?", (scheduler.id,)
        )
        if await cursor.fetchone() is None:
            raise SchedulerNotFoundError(scheduler.id)
        await self._conn.execute(
            """
            UPDATE farm_schedulers SET
                name             = ?,
                interval_min_ms  = ?,
                interval_max_ms  = ?,
                is_enabled       = ?
            WHERE id = ?
            """,
            (
                scheduler.name,
                scheduler.interval_min_ms,
                scheduler.interval_max_ms,
                int(scheduler.is_enabled),
                scheduler.id,
            ),
        )
        await self._conn.commit()
        return await self.get_scheduler(scheduler.id)

    async def delete_scheduler(self, scheduler_id: int) -> None:
        cursor = await self._conn.execute(
            "SELECT id FROM farm_schedulers WHERE id = ?", (scheduler_id,)
        )
        if await cursor.fetchone() is None:
            raise SchedulerNotFoundError(scheduler_id)
        # Desvincular farm lists (RN-14): scheduler_id → NULL.
        await self._conn.execute(
            "UPDATE farm_lists SET scheduler_id = NULL WHERE scheduler_id = ?",
            (scheduler_id,),
        )
        await self._conn.execute(
            "DELETE FROM farm_schedulers WHERE id = ?", (scheduler_id,)
        )
        await self._conn.commit()

    async def assign_farm_lists_to_scheduler(
        self, scheduler_id: int, farm_list_ids: list[int]
    ) -> FarmScheduler:
        # Verificar que el scheduler existe.
        await self.get_scheduler(scheduler_id)

        # Verificar que todas las farm lists existen.
        for fl_id in farm_list_ids:
            cursor = await self._conn.execute(
                "SELECT id FROM farm_lists WHERE id = ?", (fl_id,)
            )
            if await cursor.fetchone() is None:
                from core.exceptions import FarmListNotFoundError
                raise FarmListNotFoundError(fl_id)

        # Desvincular scheduler de las listas que ya tenía asignadas.
        await self._conn.execute(
            "UPDATE farm_lists SET scheduler_id = NULL WHERE scheduler_id = ?",
            (scheduler_id,),
        )
        # Asignar las nuevas.
        for fl_id in farm_list_ids:
            await self._conn.execute(
                "UPDATE farm_lists SET scheduler_id = ? WHERE id = ?",
                (scheduler_id, fl_id),
            )
        await self._conn.commit()
        return await self.get_scheduler(scheduler_id)

    async def update_scheduler_run_state(
        self,
        scheduler_id: int,
        last_run: datetime | None,
        next_run: datetime | None,
        execution_count: int,
    ) -> None:
        await self._conn.execute(
            """
            UPDATE farm_schedulers SET
                last_run        = ?,
                next_run        = ?,
                execution_count = ?
            WHERE id = ?
            """,
            (
                _dt_to_str(last_run),
                _dt_to_str(next_run),
                execution_count,
                scheduler_id,
            ),
        )
        await self._conn.commit()

    # ------------------------------------------------------------------
    # Historial de envíos
    # ------------------------------------------------------------------

    async def add_farm_list_send_event(self, event: FarmListSendEvent) -> None:
        await self._conn.execute(
            """
            INSERT INTO farm_list_send_history (
                farm_list_id, farm_list_name, world_id, timestamp, status,
                being_raided_current, being_raided_total, triggered_by,
                scheduler_id, bot_disabled_slots,
                loot_wood, loot_clay, loot_iron, loot_crop
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                event.farm_list_id,
                event.farm_list_name,
                event.world_id,
                _dt_to_str(event.timestamp),
                event.status,
                event.being_raided_current,
                event.being_raided_total,
                event.triggered_by,
                event.scheduler_id,
                json.dumps(event.bot_disabled_slots),
                event.loot_wood,
                event.loot_clay,
                event.loot_iron,
                event.loot_crop,
            ),
        )
        # Purga automática de registros con más de 7 días (RN-13, EC-15).
        cutoff = datetime.utcnow() - timedelta(days=_HISTORY_TTL_DAYS)
        await self._conn.execute(
            "DELETE FROM farm_list_send_history WHERE world_id = ? AND timestamp < ?",
            (event.world_id, _dt_to_str(cutoff)),
        )
        await self._conn.commit()

    async def get_farm_list_send_history(
        self,
        world_id: int,
        *,
        scheduler_id: int | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[list[FarmListSendEvent], int]:
        conditions = ["world_id = ?"]
        params: list = [world_id]
        if scheduler_id is not None:
            conditions.append("scheduler_id = ?")
            params.append(scheduler_id)
        if from_dt is not None:
            conditions.append("timestamp >= ?")
            params.append(_dt_to_str(from_dt))
        if to_dt is not None:
            conditions.append("timestamp <= ?")
            params.append(_dt_to_str(to_dt))
        where = " AND ".join(conditions)

        count_cursor = await self._conn.execute(
            f"SELECT COUNT(*) FROM farm_list_send_history WHERE {where}", params
        )
        total = (await count_cursor.fetchone())[0]

        offset = (page - 1) * page_size
        cursor = await self._conn.execute(
            f"SELECT * FROM farm_list_send_history WHERE {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            params + [page_size, offset],
        )
        rows = await cursor.fetchall()
        return [_to_send_event(r) for r in rows], total
