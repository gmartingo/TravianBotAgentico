"""
Tests unitarios para farm-stats-y-metadata-scheduler (spec sección 12).

Cubre los cuatro gaps:
  Gap A: last_send_time en GET /farm/worlds/{world_id}/farm-lists
  Gap B: metadata del scheduler desnormalizada en historial de envíos
  Gap C: slot_bounty_history + total_bounty calculado
  Gap D: endpoint GET /farm/worlds/{world_id}/schedulers/{scheduler_id}/stats

Patrón: asyncio.run() directo (coherente con test_farm_lists.py).
BD: aiosqlite :memory: con FK deshabilitadas para simplificar fixtures.
"""
from __future__ import annotations

import asyncio
import json as _json
from datetime import datetime, timedelta

import aiosqlite
import pytest

from adapters.db.account_sqlite_adapter import AccountSQLiteAdapter
from adapters.db.farm_list_sqlite_adapter import FarmListSQLiteAdapter
from core.entities.farm_list import FarmList, FarmSlot, SlotBountyRecord
from core.entities.farm_list_send_event import FarmListSendEvent
from core.entities.farm_scheduler import FarmScheduler
from core.exceptions import SchedulerNotFoundError
from core.use_cases.farm_lists import GetSchedulerStatsUseCase


# ---------------------------------------------------------------------------
# Helpers — reutilizamos el mismo patrón de test_farm_lists.py
# ---------------------------------------------------------------------------

async def _make_db() -> tuple[FarmListSQLiteAdapter, aiosqlite.Connection]:
    """Crea un adaptador con BD :memory:, tablas de cuentas + farm lists."""
    conn = await aiosqlite.connect(":memory:")
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=OFF")
    conn.row_factory = aiosqlite.Row

    account_adapter = AccountSQLiteAdapter(conn)
    await account_adapter.ensure_tables()

    farm_adapter = FarmListSQLiteAdapter(conn)
    await farm_adapter.ensure_tables()

    return farm_adapter, conn


async def _seed_world(conn: aiosqlite.Connection, world_id: int = 1) -> None:
    now = datetime.utcnow().isoformat()
    await conn.execute(
        "INSERT OR IGNORE INTO accounts (id, email, username, password, created_at, updated_at) "
        "VALUES (1, 'test@test.com', 'tester', X'', ?, ?)",
        (now, now),
    )
    await conn.execute(
        "INSERT OR IGNORE INTO worlds (id, account_id, server, tribe, created_at, updated_at) "
        "VALUES (?, 1, 'https://ts1.travian.com/', 'romans', ?, ?)",
        (world_id, now, now),
    )
    await conn.commit()


async def _seed_village(
    conn: aiosqlite.Connection,
    village_id: int = 10,
    world_id: int = 1,
) -> None:
    await _seed_world(conn, world_id)
    await conn.execute(
        "INSERT OR IGNORE INTO villages (id, world_id, data_id, name, x, y) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (village_id, world_id, village_id * 100, "Aldea principal", 5, -3),
    )
    await conn.commit()


def _make_slot(
    slot_id: int = 200,
    farm_list_id: int = 101,
    x: int = 10,
    y: int = -3,
    last_raid_report_id: str = "",
    last_raid_bounty: int = 0,
) -> FarmSlot:
    return FarmSlot(
        id=slot_id,
        farm_list_id=farm_list_id,
        target_name="Aldea Vacía",
        x=x,
        y=y,
        population=0,
        troops={"t1": 5},
        is_active=True,
        last_raid_report_id=last_raid_report_id,
        last_raid_bounty=last_raid_bounty,
    )


def _make_farm_list(
    fl_id: int = 101,
    slots: list[FarmSlot] | None = None,
    owner_village_id: int = 10,
    scheduler_id: int | None = None,
) -> FarmList:
    return FarmList(
        id=fl_id,
        name=f"Lista {fl_id}",
        owner_village_id=owner_village_id,
        slots=slots or [_make_slot(farm_list_id=fl_id)],
        scheduler_id=scheduler_id,
    )


async def _insert_farm_list_raw(
    conn: aiosqlite.Connection, fl: FarmList
) -> None:
    """Inserta farm_list y sus slots directamente en BD (sin total_bounty)."""
    await conn.execute(
        "INSERT OR REPLACE INTO farm_lists (id, name, owner_village_id, scheduler_id) "
        "VALUES (?, ?, ?, ?)",
        (fl.id, fl.name, fl.owner_village_id, fl.scheduler_id),
    )
    for slot in fl.slots:
        await conn.execute(
            """INSERT OR REPLACE INTO farm_slots
               (id, farm_list_id, target_name, x, y, population, troops,
                is_active, disabled_by_bot, last_raid_state, last_raid_time,
                last_raid_report_id, last_raid_bounty, average_raid_bounty,
                distance, disabled_at, cooldown_seconds, report_id_at_disable)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                slot.id, slot.farm_list_id, slot.target_name, slot.x, slot.y,
                slot.population, _json.dumps(slot.troops),
                int(slot.is_active), int(slot.disabled_by_bot),
                slot.last_raid_state, slot.last_raid_time,
                slot.last_raid_report_id, slot.last_raid_bounty,
                slot.average_raid_bounty, slot.distance,
                None, slot.cooldown_seconds, slot.report_id_at_disable,
            ),
        )
    await conn.commit()


async def _insert_send_event(
    conn: aiosqlite.Connection,
    farm_list_id: int,
    farm_list_name: str,
    world_id: int,
    timestamp: datetime,
    status: str = "success",
    scheduler_id: int | None = None,
    being_raided_total: int | None = 5,
    scheduler_name: str | None = None,
    scheduler_interval_min_ms: int | None = None,
    scheduler_interval_max_ms: int | None = None,
    scheduler_execution_count: int | None = None,
) -> None:
    """Inserta un evento de envío directamente en BD."""
    await conn.execute(
        """INSERT INTO farm_list_send_history
           (farm_list_id, farm_list_name, world_id, timestamp, status,
            being_raided_current, being_raided_total, triggered_by, scheduler_id,
            bot_disabled_slots, scheduler_name, scheduler_interval_min_ms,
            scheduler_interval_max_ms, scheduler_execution_count,
            loot_wood, loot_clay, loot_iron, loot_crop)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            farm_list_id, farm_list_name, world_id, timestamp.isoformat(), status,
            being_raided_total, being_raided_total,
            "scheduler" if scheduler_id else "manual",
            scheduler_id, "[]",
            scheduler_name, scheduler_interval_min_ms,
            scheduler_interval_max_ms, scheduler_execution_count,
            0, 0, 0, 0,
        ),
    )
    await conn.commit()


# ===========================================================================
# Gap A: last_send_time en GET /farm/worlds/{world_id}/farm-lists
# ===========================================================================

def test_get_farm_lists_last_send_time_populated():
    """Lista con 2 envíos en historial → last_send_time es el más reciente (CA-S01)."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)
        fl = _make_farm_list()
        await _insert_farm_list_raw(conn, fl)

        ts_old = datetime.utcnow() - timedelta(hours=2)
        ts_new = datetime.utcnow() - timedelta(hours=1)
        await _insert_send_event(conn, fl.id, fl.name, 1, ts_old)
        await _insert_send_event(conn, fl.id, fl.name, 1, ts_new)

        result = await db.get_last_send_times_by_world(1, [fl.id])
        assert fl.id in result
        last_ts = result[fl.id]
        assert last_ts is not None
        # El timestamp devuelto debe ser el más reciente (margen de 1 segundo)
        assert abs((last_ts - ts_new).total_seconds()) < 1.0

        await conn.close()

    asyncio.run(_run())


def test_get_farm_lists_last_send_time_null():
    """Lista sin envíos → last_send_time = None (CA-S01, RN-A02)."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)
        fl = _make_farm_list()
        await _insert_farm_list_raw(conn, fl)

        result = await db.get_last_send_times_by_world(1, [fl.id])
        # Si no hay historial, la clave puede estar ausente o tener None
        assert result.get(fl.id) is None

        await conn.close()

    asyncio.run(_run())


def test_get_last_send_times_multiple_lists():
    """3 listas, cada una con N envíos → cada una devuelve su propio MAX(timestamp)."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)

        fl1 = _make_farm_list(fl_id=101)
        fl2 = _make_farm_list(fl_id=102)
        fl3 = _make_farm_list(fl_id=103)
        for fl in [fl1, fl2, fl3]:
            await _insert_farm_list_raw(conn, fl)

        now = datetime.utcnow()
        ts1 = now - timedelta(hours=3)
        ts2 = now - timedelta(hours=2)
        ts3 = now - timedelta(hours=1)

        await _insert_send_event(conn, 101, "Lista 101", 1, now - timedelta(hours=5))
        await _insert_send_event(conn, 101, "Lista 101", 1, ts1)
        await _insert_send_event(conn, 102, "Lista 102", 1, ts2)
        await _insert_send_event(conn, 103, "Lista 103", 1, now - timedelta(hours=4))
        await _insert_send_event(conn, 103, "Lista 103", 1, ts3)

        result = await db.get_last_send_times_by_world(1, [101, 102, 103])
        assert len(result) == 3
        assert abs((result[101] - ts1).total_seconds()) < 1.0
        assert abs((result[102] - ts2).total_seconds()) < 1.0
        assert abs((result[103] - ts3).total_seconds()) < 1.0

        await conn.close()

    asyncio.run(_run())


# ===========================================================================
# Gap B: metadata del scheduler desnormalizada en historial
# ===========================================================================

def test_send_event_scheduler_metadata_populated():
    """Envío de scheduler → historial tiene metadata del scheduler correcta (CA-S02, CA-S03)."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)
        fl = _make_farm_list()
        await _insert_farm_list_raw(conn, fl)

        event = FarmListSendEvent(
            farm_list_id=fl.id,
            farm_list_name=fl.name,
            world_id=1,
            timestamp=datetime.utcnow(),
            status="success",
            triggered_by="scheduler",
            scheduler_id=42,
            scheduler_name="Scheduler Alfa",
            scheduler_interval_min_ms=180_000,
            scheduler_interval_max_ms=240_000,
            scheduler_execution_count=47,
        )
        await db.add_farm_list_send_event(event)

        items, total = await db.get_farm_list_send_history(1)
        assert total == 1
        ev = items[0]
        assert ev.scheduler_name == "Scheduler Alfa"
        assert ev.scheduler_interval_min_ms == 180_000
        assert ev.scheduler_interval_max_ms == 240_000
        assert ev.scheduler_execution_count == 47

        await conn.close()

    asyncio.run(_run())


def test_send_event_manual_metadata_null():
    """Envío manual → los 4 campos de metadata de scheduler son NULL (CA-S02, EC-B01)."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)
        fl = _make_farm_list()
        await _insert_farm_list_raw(conn, fl)

        event = FarmListSendEvent(
            farm_list_id=fl.id,
            farm_list_name=fl.name,
            world_id=1,
            timestamp=datetime.utcnow(),
            status="success",
            triggered_by="manual",
            scheduler_id=None,
            # metadata fields default a None
        )
        await db.add_farm_list_send_event(event)

        items, _ = await db.get_farm_list_send_history(1)
        ev = items[0]
        assert ev.scheduler_name is None
        assert ev.scheduler_interval_min_ms is None
        assert ev.scheduler_interval_max_ms is None
        assert ev.scheduler_execution_count is None

        await conn.close()

    asyncio.run(_run())


def test_history_response_includes_scheduler_fields():
    """get_farm_list_send_history incluye los 4 campos nuevos en cada evento."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)
        fl = _make_farm_list()
        await _insert_farm_list_raw(conn, fl)

        await _insert_send_event(
            conn, fl.id, fl.name, 1, datetime.utcnow(),
            scheduler_id=5,
            scheduler_name="Mi Scheduler",
            scheduler_interval_min_ms=60_000,
            scheduler_interval_max_ms=120_000,
            scheduler_execution_count=10,
        )

        items, _ = await db.get_farm_list_send_history(1)
        assert len(items) == 1
        ev = items[0]
        assert ev.scheduler_name == "Mi Scheduler"
        assert ev.scheduler_interval_min_ms == 60_000
        assert ev.scheduler_interval_max_ms == 120_000
        assert ev.scheduler_execution_count == 10

        await conn.close()

    asyncio.run(_run())


# ===========================================================================
# Gap C: slot_bounty_history + total_bounty calculado
# ===========================================================================

def test_sync_slot_new_report_inserts_bounty():
    """sync_farm_list con nuevo last_raid_report_id y bounty > 0 → fila en slot_bounty_history (CA-S09, RN-C01)."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)

        # Slot inicial en BD con report_id vacío
        slot_old = _make_slot(last_raid_report_id="", last_raid_bounty=0)
        fl = _make_farm_list(slots=[slot_old])
        await _insert_farm_list_raw(conn, fl)

        # DOM devuelve el mismo slot con nuevo report_id y bounty
        slot_new = _make_slot(last_raid_report_id="rpt_001", last_raid_bounty=1500)
        fl_new = _make_farm_list(slots=[slot_new])

        synced = await db.sync_farm_list(fl_new, world_id=1)

        # Verificar fila en slot_bounty_history
        cursor = await conn.execute(
            "SELECT * FROM slot_bounty_history WHERE farm_list_id = ?", (fl.id,)
        )
        rows = await cursor.fetchall()
        assert len(rows) == 1
        assert rows[0]["bounty"] == 1500
        assert rows[0]["raid_report_id"] == "rpt_001"

        # total_bounty calculado en el slot devuelto
        assert synced.slots[0].total_bounty == 1500

        await conn.close()

    asyncio.run(_run())


def test_total_bounty_computed_from_history():
    """Tras 3 syncs con bounty → FarmSlot.total_bounty = suma de los 3 (CA-S08, CA-S09)."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)

        slot = _make_slot(last_raid_report_id="", last_raid_bounty=0)
        fl = _make_farm_list(slots=[slot])
        await _insert_farm_list_raw(conn, fl)

        for i, (rpt, bounty) in enumerate([
            ("rpt_001", 1000),
            ("rpt_002", 2000),
            ("rpt_003", 3000),
        ]):
            slot_dom = _make_slot(last_raid_report_id=rpt, last_raid_bounty=bounty)
            fl_dom = _make_farm_list(slots=[slot_dom])
            synced = await db.sync_farm_list(fl_dom, world_id=1)

        # Después del tercer sync: total = 1000 + 2000 + 3000
        assert synced.slots[0].total_bounty == 6000

        # Verificar con _load_slots también
        loaded = await db.get_farm_list_by_id(fl.id)
        assert loaded.slots[0].total_bounty == 6000

        await conn.close()

    asyncio.run(_run())


def test_total_bounty_zero_bounty_not_recorded():
    """last_raid_bounty = 0 → no se inserta en slot_bounty_history (CA-S10, EC-C01)."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)

        slot = _make_slot(last_raid_report_id="", last_raid_bounty=0)
        fl = _make_farm_list(slots=[slot])
        await _insert_farm_list_raw(conn, fl)

        # DOM con bounty = 0
        slot_dom = _make_slot(last_raid_report_id="rpt_001", last_raid_bounty=0)
        fl_dom = _make_farm_list(slots=[slot_dom])
        await db.sync_farm_list(fl_dom, world_id=1)

        cursor = await conn.execute("SELECT COUNT(*) FROM slot_bounty_history")
        count = (await cursor.fetchone())[0]
        assert count == 0

        await conn.close()

    asyncio.run(_run())


def test_total_bounty_empty_report_id_not_recorded():
    """last_raid_report_id = '' → no se inserta en slot_bounty_history (CA-S11, EC-C02)."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)

        slot = _make_slot(last_raid_report_id="old_rpt", last_raid_bounty=0)
        fl = _make_farm_list(slots=[slot])
        await _insert_farm_list_raw(conn, fl)

        # DOM con report_id vacío y bounty > 0 (inconsistencia real del DOM)
        slot_dom = _make_slot(last_raid_report_id="", last_raid_bounty=999)
        fl_dom = _make_farm_list(slots=[slot_dom])
        await db.sync_farm_list(fl_dom, world_id=1)

        cursor = await conn.execute("SELECT COUNT(*) FROM slot_bounty_history")
        count = (await cursor.fetchone())[0]
        assert count == 0

        await conn.close()

    asyncio.run(_run())


def test_slot_id_reassignment_preserves_bounty():
    """Travian reasigna ID del slot (mismo x,y) → slot_bounty_history apunta al nuevo ID (CA-S12, EC-C03)."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)

        slot_old = _make_slot(slot_id=200, x=10, y=-3, last_raid_report_id="rpt_001", last_raid_bounty=0)
        fl = _make_farm_list(slots=[slot_old])
        await _insert_farm_list_raw(conn, fl)

        # Insertar bounty histórico para el slot viejo
        await conn.execute(
            "INSERT INTO slot_bounty_history (slot_id, farm_list_id, world_id, timestamp, bounty, raid_report_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (200, fl.id, 1, datetime.utcnow().isoformat(), 5000, "rpt_001"),
        )
        await conn.commit()

        # Travian reasigna ID: mismo x,y pero id=999
        slot_new = _make_slot(slot_id=999, x=10, y=-3, last_raid_report_id="rpt_001", last_raid_bounty=0)
        fl_new = _make_farm_list(slots=[slot_new])
        synced = await db.sync_farm_list(fl_new, world_id=1)

        # slot_bounty_history debe apuntar al nuevo ID (CA-S12)
        cursor = await conn.execute(
            "SELECT slot_id FROM slot_bounty_history WHERE farm_list_id = ?", (fl.id,)
        )
        rows = await cursor.fetchall()
        assert all(r["slot_id"] == 999 for r in rows)

        # total_bounty preservado
        assert synced.slots[0].total_bounty == 5000

        await conn.close()

    asyncio.run(_run())


def test_slot_bounty_history_ttl_purge():
    """Bounty con timestamp > 7 días → purgado en el siguiente insert (CA-S13, RN-C02)."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)

        fl = _make_farm_list()
        await _insert_farm_list_raw(conn, fl)

        # Insertar bounty antiguo (> 7 días)
        old_ts = (datetime.utcnow() - timedelta(days=8)).isoformat()
        await conn.execute(
            "INSERT INTO slot_bounty_history (slot_id, farm_list_id, world_id, timestamp, bounty, raid_report_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (200, fl.id, 1, old_ts, 9999, "rpt_old"),
        )
        await conn.commit()

        # Trigger de purga: insertar un nuevo bounty vía sync_farm_list
        slot_dom = _make_slot(last_raid_report_id="rpt_new", last_raid_bounty=100)
        fl_dom = _make_farm_list(slots=[slot_dom])
        synced = await db.sync_farm_list(fl_dom, world_id=1)

        # El registro antiguo debe haber sido purgado
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM slot_bounty_history WHERE raid_report_id = 'rpt_old'"
        )
        count = (await cursor.fetchone())[0]
        assert count == 0

        # Solo queda el registro nuevo
        assert synced.slots[0].total_bounty == 100

        await conn.close()

    asyncio.run(_run())


def test_load_slots_total_bounty_single_query():
    """_load_slots con N slots → enriquece total_bounty desde slot_bounty_history (RN-C04)."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)

        # Crear 3 slots en la misma lista
        slots = [
            _make_slot(slot_id=200 + i, x=10 + i, y=-3, farm_list_id=101)
            for i in range(3)
        ]
        fl = _make_farm_list(slots=slots)
        await _insert_farm_list_raw(conn, fl)

        now = datetime.utcnow()
        # Insertar bounty para 2 de los 3 slots
        await conn.execute(
            "INSERT INTO slot_bounty_history (slot_id, farm_list_id, world_id, timestamp, bounty, raid_report_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (200, fl.id, 1, now.isoformat(), 1000, "rpt1"),
        )
        await conn.execute(
            "INSERT INTO slot_bounty_history (slot_id, farm_list_id, world_id, timestamp, bounty, raid_report_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (201, fl.id, 1, now.isoformat(), 2000, "rpt2"),
        )
        await conn.commit()

        # _load_slots debe enriquecer total_bounty en una sola pasada
        loaded_fl = await db.get_farm_list_by_id(fl.id)
        slot_map = {s.id: s for s in loaded_fl.slots}

        assert slot_map[200].total_bounty == 1000
        assert slot_map[201].total_bounty == 2000
        assert slot_map[202].total_bounty == 0   # sin bounty

        await conn.close()

    asyncio.run(_run())


# ===========================================================================
# Gap C: CA-S14 y CA-S15 — idempotencia de migraciones
# ===========================================================================

def test_drop_column_total_bounty_idempotent():
    """ensure_tables() llamado dos veces → sin error (CA-S14)."""
    async def _run():
        db, conn = await _make_db()
        # Llamar por segunda vez — no debe lanzar excepción
        await db.ensure_tables()

        # Verificar que total_bounty ya no existe (CA-S15)
        cursor = await conn.execute("PRAGMA table_info(farm_slots)")
        cols = {row["name"] for row in await cursor.fetchall()}
        assert "total_bounty" not in cols

        await conn.close()

    asyncio.run(_run())


def test_add_column_scheduler_metadata_idempotent():
    """ensure_tables() llamado con columnas ya presentes → sin error (CA-S14)."""
    async def _run():
        db, conn = await _make_db()
        # Segunda llamada idempotente
        await db.ensure_tables()

        # Verificar que las columnas existen
        cursor = await conn.execute("PRAGMA table_info(farm_list_send_history)")
        cols = {row["name"] for row in await cursor.fetchall()}
        for col in ["scheduler_name", "scheduler_interval_min_ms",
                    "scheduler_interval_max_ms", "scheduler_execution_count"]:
            assert col in cols, f"Columna '{col}' no encontrada en farm_list_send_history"

        await conn.close()

    asyncio.run(_run())


# ===========================================================================
# Gap D: estadísticas del scheduler
# ===========================================================================

def test_get_scheduler_stats_success():
    """Scheduler con 2 listas y envíos → métricas correctas (CA-S04, CA-S16)."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)

        fl1 = _make_farm_list(fl_id=101)
        fl2 = _make_farm_list(fl_id=102)
        for fl in [fl1, fl2]:
            await _insert_farm_list_raw(conn, fl)

        sched = await db.create_scheduler(FarmScheduler(
            id=0, world_id=1, name="Scheduler Test",
            interval_min_ms=180_000, interval_max_ms=240_000,
            execution_count=10,
        ))
        await db.assign_farm_lists_to_scheduler(sched.id, [101, 102])

        now = datetime.utcnow()
        # 4 envíos: 3 success, 1 error para fl1
        for i in range(3):
            await _insert_send_event(conn, 101, "Lista 101", 1, now - timedelta(hours=3 - i),
                                     status="success", scheduler_id=sched.id, being_raided_total=8)
        await _insert_send_event(conn, 101, "Lista 101", 1, now - timedelta(minutes=30),
                                 status="error", scheduler_id=sched.id, being_raided_total=None)
        # 2 envíos success para fl2
        for i in range(2):
            await _insert_send_event(conn, 102, "Lista 102", 1, now - timedelta(hours=2 - i),
                                     status="success", scheduler_id=sched.id, being_raided_total=5)

        uc = GetSchedulerStatsUseCase(db=db)
        stats = await uc.execute(sched.id, world_id=1)

        assert stats.scheduler_id == sched.id
        assert stats.scheduler_name == "Scheduler Test"
        assert stats.world_id == 1
        assert stats.execution_count == 10  # RN-D05
        # success_rate global: 5 success / 6 total = ~0.8333
        assert 0.8 < stats.success_rate <= 1.0
        assert len(stats.per_list) == 2
        assert stats.total_bounty >= 0

        await conn.close()

    asyncio.run(_run())


def test_get_scheduler_stats_empty():
    """Scheduler sin farm lists → todas las métricas en cero (CA-S07, EC-D01)."""
    async def _run():
        db, conn = await _make_db()
        await _seed_world(conn)

        sched = await db.create_scheduler(FarmScheduler(
            id=0, world_id=1, name="Vacío",
            interval_min_ms=60_000, interval_max_ms=120_000,
        ))

        uc = GetSchedulerStatsUseCase(db=db)
        stats = await uc.execute(sched.id, world_id=1)

        assert stats.success_rate == 0.0
        assert stats.active_slots_avg == 0.0
        assert stats.total_bounty == 0
        assert stats.bounty_per_hour == 0.0
        assert stats.last_send_time is None
        assert stats.per_list == []

        await conn.close()

    asyncio.run(_run())


def test_get_scheduler_stats_no_history():
    """Scheduler con listas pero sin envíos → métricas en cero, last_send_time = null."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)

        fl = _make_farm_list()
        await _insert_farm_list_raw(conn, fl)

        sched = await db.create_scheduler(FarmScheduler(
            id=0, world_id=1, name="Sin historial",
            interval_min_ms=60_000, interval_max_ms=120_000,
        ))
        await db.assign_farm_lists_to_scheduler(sched.id, [fl.id])

        uc = GetSchedulerStatsUseCase(db=db)
        stats = await uc.execute(sched.id, world_id=1)

        assert stats.last_send_time is None
        assert stats.success_rate == 0.0
        assert stats.bounty_per_hour == 0.0
        # per_list tiene 1 entrada pero con métricas en cero
        assert len(stats.per_list) == 1
        assert stats.per_list[0].last_send_time is None

        await conn.close()

    asyncio.run(_run())


def test_get_scheduler_stats_execution_count():
    """execution_count refleja farm_schedulers.execution_count directamente (RN-D05)."""
    async def _run():
        db, conn = await _make_db()
        await _seed_world(conn)

        sched = await db.create_scheduler(FarmScheduler(
            id=0, world_id=1, name="Con contador",
            interval_min_ms=60_000, interval_max_ms=120_000,
            execution_count=99,
        ))

        uc = GetSchedulerStatsUseCase(db=db)
        stats = await uc.execute(sched.id, world_id=1)

        assert stats.execution_count == 99

        await conn.close()

    asyncio.run(_run())


def test_get_scheduler_stats_per_list_breakdown():
    """Respuesta incluye per_list con métricas por cada farm list (CA-S04, RN-D06)."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)

        fl1 = _make_farm_list(fl_id=101)
        fl2 = _make_farm_list(fl_id=102)
        for fl in [fl1, fl2]:
            await _insert_farm_list_raw(conn, fl)

        sched = await db.create_scheduler(FarmScheduler(
            id=0, world_id=1, name="Multi-lista",
            interval_min_ms=60_000, interval_max_ms=120_000,
        ))
        await db.assign_farm_lists_to_scheduler(sched.id, [101, 102])

        now = datetime.utcnow()
        await _insert_send_event(conn, 101, "Lista 101", 1, now - timedelta(hours=1),
                                 status="success", scheduler_id=sched.id)
        await _insert_send_event(conn, 102, "Lista 102", 1, now - timedelta(hours=2),
                                 status="success", scheduler_id=sched.id)

        uc = GetSchedulerStatsUseCase(db=db)
        stats = await uc.execute(sched.id, world_id=1)

        farm_list_ids_in_per_list = {ls.farm_list_id for ls in stats.per_list}
        assert 101 in farm_list_ids_in_per_list
        assert 102 in farm_list_ids_in_per_list

        for ls in stats.per_list:
            assert isinstance(ls.success_rate, float)
            assert isinstance(ls.bounty_per_hour, float)
            assert isinstance(ls.total_bounty, int)

        await conn.close()

    asyncio.run(_run())


# ===========================================================================
# Gap D — Edge cases
# ===========================================================================

def test_get_scheduler_stats_wrong_world_id():
    """Scheduler existe pero world_id no coincide → SchedulerNotFoundError → 404 (CA-S06, EC-D03)."""
    async def _run():
        db, conn = await _make_db()
        await _seed_world(conn, world_id=1)
        await _seed_world(conn, world_id=2)

        sched = await db.create_scheduler(FarmScheduler(
            id=0, world_id=1, name="World 1",
            interval_min_ms=60_000, interval_max_ms=120_000,
        ))

        uc = GetSchedulerStatsUseCase(db=db)
        try:
            await uc.execute(sched.id, world_id=2)
            assert False, "Debería lanzar SchedulerNotFoundError"
        except SchedulerNotFoundError:
            pass

        await conn.close()

    asyncio.run(_run())


def test_get_scheduler_stats_not_found():
    """Scheduler ID inexistente → SchedulerNotFoundError → 404 (CA-S05)."""
    async def _run():
        db, conn = await _make_db()
        await _seed_world(conn)

        uc = GetSchedulerStatsUseCase(db=db)
        try:
            await uc.execute(999, world_id=1)
            assert False, "Debería lanzar SchedulerNotFoundError"
        except SchedulerNotFoundError:
            pass

        await conn.close()

    asyncio.run(_run())


def test_scheduler_deleted_race_condition():
    """ProcessFarmListUseCase con scheduler borrado en carrera → metadata NULL en historial (EC-B02)."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)

        # La farm list se inserta sin scheduler (ninguno existe aún en BD).
        fl = _make_farm_list(scheduler_id=None)
        await _insert_farm_list_raw(conn, fl)

        # Simular race condition: ProcessFarmListUseCase detectó scheduler_id=99 en
        # el objeto en memoria pero get_scheduler lanzó SchedulerNotFoundError → NULL.
        # El evento se graba con scheduler_id=99 pero sin metadata (FK en historial
        # no referencia farm_schedulers, así que el INSERT es válido).
        event = FarmListSendEvent(
            farm_list_id=fl.id,
            farm_list_name=fl.name,
            world_id=1,
            timestamp=datetime.utcnow(),
            status="success",
            triggered_by="scheduler",
            scheduler_id=99,          # scheduler ya no existe → race condition
            scheduler_name=None,      # EC-B02: metadata NULL
            scheduler_interval_min_ms=None,
            scheduler_interval_max_ms=None,
            scheduler_execution_count=None,
        )
        await db.add_farm_list_send_event(event)

        items, _ = await db.get_farm_list_send_history(1)
        assert len(items) == 1
        assert items[0].scheduler_name is None
        assert items[0].scheduler_interval_min_ms is None

        await conn.close()

    asyncio.run(_run())


def test_bounty_per_hour_single_send():
    """Un solo envío → horas_en_rango = MAX(1, ~0) = 1, sin división por cero (EC-D02)."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)

        fl = _make_farm_list()
        await _insert_farm_list_raw(conn, fl)

        sched = await db.create_scheduler(FarmScheduler(
            id=0, world_id=1, name="Un envío",
            interval_min_ms=60_000, interval_max_ms=120_000,
        ))
        await db.assign_farm_lists_to_scheduler(sched.id, [fl.id])

        # Insertar bounty en slot_bounty_history para que total_bounty > 0
        now = datetime.utcnow()
        await conn.execute(
            "INSERT INTO slot_bounty_history (slot_id, farm_list_id, world_id, timestamp, bounty, raid_report_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (200, fl.id, 1, now.isoformat(), 3600, "rpt_1"),
        )
        await conn.commit()

        # Un solo envío (ahora mismo)
        await _insert_send_event(conn, fl.id, fl.name, 1, now,
                                 status="success", scheduler_id=sched.id)

        uc = GetSchedulerStatsUseCase(db=db)
        stats = await uc.execute(sched.id, world_id=1)

        # No debe lanzar excepción; bounty_per_hour debe ser >= 0.0
        assert stats.bounty_per_hour >= 0.0
        # total_bounty debe ser 3600
        assert stats.total_bounty == 3600

        await conn.close()

    asyncio.run(_run())


def test_get_scheduler_stats_success_rate():
    """success_rate = envíos success / total (CA-S16)."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)

        fl = _make_farm_list()
        await _insert_farm_list_raw(conn, fl)

        sched = await db.create_scheduler(FarmScheduler(
            id=0, world_id=1, name="Tasa éxito",
            interval_min_ms=60_000, interval_max_ms=120_000,
        ))
        await db.assign_farm_lists_to_scheduler(sched.id, [fl.id])

        now = datetime.utcnow()
        # 3 success, 1 error → success_rate = 0.75
        for i in range(3):
            await _insert_send_event(conn, fl.id, fl.name, 1, now - timedelta(hours=4 - i),
                                     status="success", scheduler_id=sched.id)
        await _insert_send_event(conn, fl.id, fl.name, 1, now - timedelta(minutes=30),
                                 status="error", scheduler_id=sched.id)

        uc = GetSchedulerStatsUseCase(db=db)
        stats = await uc.execute(sched.id, world_id=1)

        assert abs(stats.success_rate - 0.75) < 0.01

        await conn.close()

    asyncio.run(_run())


def test_bounty_per_hour_no_history():
    """Scheduler sin historial de envíos → bounty_per_hour = 0.0 (CA-S17)."""
    async def _run():
        db, conn = await _make_db()
        await _seed_world(conn)

        sched = await db.create_scheduler(FarmScheduler(
            id=0, world_id=1, name="Sin historial",
            interval_min_ms=60_000, interval_max_ms=120_000,
        ))

        uc = GetSchedulerStatsUseCase(db=db)
        stats = await uc.execute(sched.id, world_id=1)

        assert stats.bounty_per_hour == 0.0

        await conn.close()

    asyncio.run(_run())
