"""
Tests unitarios de farm lists (spec sección 12).

Cubre:
  - Casos felices: ciclo de envío, pérdidas, reactivación, sonda, grupos,
    sincronización, WorldAgent seed/reschedule/run-now, cancel-probe, activate.
  - Edge cases: scheduler deshabilitado, cooldown máximo, losses_already_seen,
    lista vacía de farm_list_ids, slot desactivado manualmente no tocado.

Patrón: asyncio.run() directo (coherente con el resto del proyecto).
BD: aiosqlite :memory: con FK deshabilitadas para simplificar fixtures
    (las FK no son el objetivo de estos tests — la lógica de dominio sí lo es).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest

from adapters.db.account_sqlite_adapter import AccountSQLiteAdapter
from adapters.db.farm_list_sqlite_adapter import FarmListSQLiteAdapter
from core.entities.farm_list import FarmList, FarmSlot, SlotEvent
from core.entities.farm_list_send_event import FarmListSendEvent
from core.entities.farm_list_send_result import FarmListSendResult
from core.entities.farm_scheduler import FarmScheduler
from core.entities.task import Task, TaskType
from core.entities.village import Village
from core.exceptions import SchedulerNotFoundError
from core.ports.farm_list_browser_port import FarmListBrowserPort
from core.ports.farm_list_db_port import FarmListDbPort
from core.scheduling.task_queue import TaskQueue
from core.scheduling.world_agent import AgentState, WorldAgent
from core.use_cases.farm_lists import (
    ActivateSlotInTravianUseCase,
    CancelProbeUseCase,
    ProcessFarmListUseCase,
    ReadFarmListsUseCase,
    SendFarmListUseCase,
    SendSchedulerGroupUseCase,
)


# ---------------------------------------------------------------------------
# Helpers de BD en memoria
# ---------------------------------------------------------------------------

async def _make_db() -> tuple[FarmListSQLiteAdapter, aiosqlite.Connection]:
    """Crea un adaptador con BD :memory:, tablas de cuentas + farm lists."""
    conn = await aiosqlite.connect(":memory:")
    # Desactivar PRAGMA foreign_keys para simplificar fixtures en tests
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=OFF")
    conn.row_factory = aiosqlite.Row

    # Tablas base (accounts, worlds, villages)
    account_adapter = AccountSQLiteAdapter(conn)
    await account_adapter.ensure_tables()

    # Tablas farm lists
    farm_adapter = FarmListSQLiteAdapter(conn)
    await farm_adapter.ensure_tables()

    return farm_adapter, conn


async def _seed_world(conn: aiosqlite.Connection, world_id: int = 1) -> None:
    """Inserta una row en worlds para satisfacer la FK de farm_schedulers."""
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
    name: str = "Aldea principal",
    x: int = 5,
    y: int = -3,
) -> None:
    """Inserta una row en villages para satisfacer la FK de farm_lists."""
    await _seed_world(conn, world_id)
    await conn.execute(
        "INSERT OR IGNORE INTO villages (id, world_id, data_id, name, x, y) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (village_id, world_id, village_id * 100, name, x, y),
    )
    await conn.commit()


# ---------------------------------------------------------------------------
# Stubs de FarmListBrowserPort
# ---------------------------------------------------------------------------

class StubBrowser(FarmListBrowserPort):
    """Stub de FarmListBrowserPort para tests (sin browser real)."""

    def __init__(
        self,
        farm_lists: list[FarmList] | None = None,
        send_result: FarmListSendResult | None = None,
    ):
        self._farm_lists = farm_lists or []
        self._send_result = send_result or FarmListSendResult(
            farm_list_id=101,
            status="success",
            being_raided_current=5,
            being_raided_total=5,
        )
        self.activated_slots: list[tuple[int, int]] = []
        self.deactivated_slots: list[tuple[int, int]] = []
        self.sent_lists: list[int] = []
        self._read_farm_list_by_id: dict[int, FarmList] = {}

    def set_farm_list(self, fl: FarmList) -> None:
        self._read_farm_list_by_id[fl.id] = fl

    async def read_farm_lists(self) -> list[FarmList]:
        return self._farm_lists

    async def read_farm_list(self, farm_list_id: int) -> FarmList:
        if farm_list_id in self._read_farm_list_by_id:
            return self._read_farm_list_by_id[farm_list_id]
        if self._farm_lists:
            return self._farm_lists[0]
        raise KeyError(f"StubBrowser: farm_list_id={farm_list_id} no configurado")

    async def send_farm_list(self, farm_list_id: int) -> FarmListSendResult:
        self.sent_lists.append(farm_list_id)
        result = self._send_result
        return FarmListSendResult(
            farm_list_id=farm_list_id,
            status=result.status,
            being_raided_current=result.being_raided_current,
            being_raided_total=result.being_raided_total,
        )

    async def activate_slot_in_travian(self, slot_id: int, farm_list_id: int) -> None:
        self.activated_slots.append((slot_id, farm_list_id))

    async def deactivate_slot_in_travian(self, slot_id: int, farm_list_id: int) -> None:
        self.deactivated_slots.append((slot_id, farm_list_id))


def _make_slot(
    slot_id: int = 200,
    farm_list_id: int = 101,
    x: int = 10,
    y: int = -3,
    is_active: bool = True,
    disabled_by_bot: bool = False,
    last_raid_state: str = "withoutLosses",
    last_raid_report_id: str = "rpt1",
    disabled_at: datetime | None = None,
    cooldown_seconds: int = 3600,
    report_id_at_disable: str = "",
) -> FarmSlot:
    return FarmSlot(
        id=slot_id,
        farm_list_id=farm_list_id,
        target_name="Aldea Vacía",
        x=x,
        y=y,
        population=0,
        troops={"t1": 5},
        is_active=is_active,
        disabled_by_bot=disabled_by_bot,
        last_raid_state=last_raid_state,
        last_raid_report_id=last_raid_report_id,
        disabled_at=disabled_at,
        cooldown_seconds=cooldown_seconds,
        report_id_at_disable=report_id_at_disable,
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


async def _insert_farm_list(
    db: FarmListSQLiteAdapter, conn: aiosqlite.Connection, fl: FarmList
) -> FarmList:
    """Inserta directamente en BD sin pasar por sync (para setup de tests)."""
    await conn.execute(
        "INSERT OR REPLACE INTO farm_lists (id, name, owner_village_id, scheduler_id) "
        "VALUES (?, ?, ?, ?)",
        (fl.id, fl.name, fl.owner_village_id, fl.scheduler_id),
    )
    for slot in fl.slots:
        import json as _json
        await conn.execute(
            """INSERT OR REPLACE INTO farm_slots
               (id, farm_list_id, target_name, x, y, population, troops,
                is_active, disabled_by_bot, last_raid_state, last_raid_time,
                last_raid_report_id, last_raid_bounty, average_raid_bounty,
                total_bounty, distance, disabled_at, cooldown_seconds, report_id_at_disable)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                slot.id, slot.farm_list_id, slot.target_name, slot.x, slot.y,
                slot.population, _json.dumps(slot.troops),
                int(slot.is_active), int(slot.disabled_by_bot),
                slot.last_raid_state, slot.last_raid_time,
                slot.last_raid_report_id, slot.last_raid_bounty,
                slot.average_raid_bounty, slot.total_bounty, slot.distance,
                slot.disabled_at.isoformat() if slot.disabled_at else None,
                slot.cooldown_seconds, slot.report_id_at_disable,
            ),
        )
    await conn.commit()
    return fl


# ===========================================================================
# Tests de ProcessFarmListUseCase
# ===========================================================================

def test_process_farm_list_no_losses():
    """Slot activo sin pérdidas → se envía la lista, no hay cambios en el slot."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)
        fl = _make_farm_list(slots=[_make_slot(last_raid_state="withoutLosses")])
        await _insert_farm_list(db, conn, fl)

        browser = StubBrowser()
        browser.set_farm_list(fl)
        uc = ProcessFarmListUseCase(browser=browser, db=db)
        await uc.execute(fl.id, world_id=1)

        # Se envió la lista
        assert fl.id in browser.sent_lists
        # No se desactivó ningún slot
        assert len(browser.deactivated_slots) == 0
        # Historial registrado
        items, total = await db.get_farm_list_send_history(1)
        assert total == 1
        assert items[0].status == "success"

        await conn.close()

    asyncio.run(_run())


def test_process_farm_list_losses_detected():
    """Slot activo con withLosses → desactivado, evento LOSSES_DETECTED."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)
        slot = _make_slot(last_raid_state="withLosses", last_raid_report_id="rpt_loss")
        fl = _make_farm_list(slots=[slot])
        await _insert_farm_list(db, conn, fl)

        browser = StubBrowser()
        browser.set_farm_list(fl)
        uc = ProcessFarmListUseCase(browser=browser, db=db)
        await uc.execute(fl.id, world_id=1)

        # Slot desactivado en browser
        assert (slot.id, fl.id) in browser.deactivated_slots
        # Slot en BD con disabled_by_bot=True
        updated = await db.get_slot_by_id(slot.id, fl.id)
        assert updated.disabled_by_bot is True
        assert updated.is_active is False
        assert updated.cooldown_seconds == 3600

        # Evento LOSSES_DETECTED
        events, total = await db.get_slot_events(1)
        assert total == 1
        assert events[0].event_type == "LOSSES_DETECTED"

        await conn.close()

    asyncio.run(_run())


def test_process_farm_list_reactivated():
    """Slot disabled_by_bot + nuevo informe withoutLosses → REACTIVATED."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)
        # Slot estaba desactivado por bot, con report distinto al del DOM
        slot = _make_slot(
            is_active=False,
            disabled_by_bot=True,
            last_raid_state="withoutLosses",
            last_raid_report_id="rpt_new",
            report_id_at_disable="rpt_old",  # distinto → new_raid=True
        )
        fl = _make_farm_list(slots=[slot])
        await _insert_farm_list(db, conn, fl)

        browser = StubBrowser()
        browser.set_farm_list(fl)
        uc = ProcessFarmListUseCase(browser=browser, db=db)
        await uc.execute(fl.id, world_id=1)

        # Slot activado en browser
        assert (slot.id, fl.id) in browser.activated_slots
        # Slot en BD con disabled_by_bot=False, is_active=True
        updated = await db.get_slot_by_id(slot.id, fl.id)
        assert updated.disabled_by_bot is False
        assert updated.is_active is True

        # Evento REACTIVATED
        events, _ = await db.get_slot_events(1)
        assert any(e.event_type == "REACTIVATED" for e in events)

        await conn.close()

    asyncio.run(_run())


def test_process_farm_list_probe_sent():
    """Slot disabled_by_bot + cooldown expirado + sin informe nuevo → PROBE_SENT, cooldown *2."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)
        # Cooldown expirado: disabled_at hace más de cooldown_seconds
        expired_at = datetime.utcnow() - timedelta(seconds=4000)
        slot = _make_slot(
            is_active=False,
            disabled_by_bot=True,
            last_raid_state="withoutLosses",
            last_raid_report_id="rpt1",
            report_id_at_disable="rpt1",  # mismo → no hay raid nuevo
            disabled_at=expired_at,
            cooldown_seconds=3600,
        )
        fl = _make_farm_list(slots=[slot])
        await _insert_farm_list(db, conn, fl)

        browser = StubBrowser()
        browser.set_farm_list(fl)
        uc = ProcessFarmListUseCase(browser=browser, db=db)
        await uc.execute(fl.id, world_id=1)

        # Slot activado para la sonda
        assert (slot.id, fl.id) in browser.activated_slots
        # Lista enviada
        assert fl.id in browser.sent_lists
        # Slot desactivado tras envío de sonda
        assert (slot.id, fl.id) in browser.deactivated_slots
        # Cooldown duplicado
        updated = await db.get_slot_by_id(slot.id, fl.id)
        assert updated.cooldown_seconds == 7200  # 3600*2

        # Evento PROBE_SENT
        events, _ = await db.get_slot_events(1)
        assert any(e.event_type == "PROBE_SENT" for e in events)

        await conn.close()

    asyncio.run(_run())


def test_cooldown_max_not_exceeded():
    """EC-09: cooldown nunca supera 86400s."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)
        expired_at = datetime.utcnow() - timedelta(seconds=90000)
        slot = _make_slot(
            is_active=False,
            disabled_by_bot=True,
            last_raid_report_id="rpt1",
            report_id_at_disable="rpt1",
            disabled_at=expired_at,
            cooldown_seconds=50000,  # *2 = 100000 > 86400 → debe quedar en 86400
        )
        fl = _make_farm_list(slots=[slot])
        await _insert_farm_list(db, conn, fl)

        browser = StubBrowser()
        browser.set_farm_list(fl)
        uc = ProcessFarmListUseCase(browser=browser, db=db)
        await uc.execute(fl.id, world_id=1)

        updated = await db.get_slot_by_id(slot.id, fl.id)
        assert updated.cooldown_seconds == 86400

        await conn.close()

    asyncio.run(_run())


def test_losses_already_seen_no_double_disable():
    """RN-09: pérdidas en slot ya desactivado con mismo report_id → no doble desactivación."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)
        slot = _make_slot(
            is_active=False,
            disabled_by_bot=True,
            last_raid_state="withLosses",
            last_raid_report_id="rpt_same",
            report_id_at_disable="rpt_same",  # mismo → losses_already_seen=True
            disabled_at=datetime.utcnow(),
            cooldown_seconds=3600,
        )
        fl = _make_farm_list(slots=[slot])
        await _insert_farm_list(db, conn, fl)

        browser = StubBrowser()
        browser.set_farm_list(fl)  # el stub devuelve esta farm list al leer el DOM
        uc = ProcessFarmListUseCase(browser=browser, db=db)
        await uc.execute(fl.id, world_id=1)

        # NO se llamó deactivate (el slot ya está desactivado con el mismo report)
        assert len(browser.deactivated_slots) == 0
        # No hay eventos LOSSES_DETECTED nuevos
        events, total = await db.get_slot_events(1)
        assert total == 0

        await conn.close()

    asyncio.run(_run())


def test_slot_manually_disabled_not_touched():
    """RN-04: slot con is_active=False y disabled_by_bot=False → el bot no lo toca."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)
        slot = _make_slot(is_active=False, disabled_by_bot=False, last_raid_state="withLosses")
        fl = _make_farm_list(slots=[slot])
        await _insert_farm_list(db, conn, fl)

        browser = StubBrowser()
        browser.set_farm_list(fl)
        uc = ProcessFarmListUseCase(browser=browser, db=db)
        await uc.execute(fl.id, world_id=1)

        assert len(browser.deactivated_slots) == 0
        assert len(browser.activated_slots) == 0
        events, total = await db.get_slot_events(1)
        assert total == 0

        await conn.close()

    asyncio.run(_run())


# ===========================================================================
# Tests de SendSchedulerGroupUseCase
# ===========================================================================

def test_send_scheduler_group_success():
    """2 farm lists en grupo → ambas procesadas, sin errores."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)

        fl1 = _make_farm_list(fl_id=101)
        fl2 = _make_farm_list(fl_id=102)
        await _insert_farm_list(db, conn, fl1)
        await _insert_farm_list(db, conn, fl2)

        # Crear scheduler
        sched = await db.create_scheduler(FarmScheduler(
            id=0, world_id=1, name="grupo",
            interval_min_ms=60000, interval_max_ms=120000,
        ))
        await db.assign_farm_lists_to_scheduler(sched.id, [101, 102])

        browser = StubBrowser()
        browser.set_farm_list(fl1)
        browser.set_farm_list(fl2)
        # Patch del sleep anti-detección para no esperar 2-5 s en tests
        with patch("core.use_cases.farm_lists.asyncio.sleep", new_callable=AsyncMock):
            uc = SendSchedulerGroupUseCase(browser=browser, db=db)
            count = await uc.execute(sched.id)

        assert count == 2
        assert 101 in browser.sent_lists
        assert 102 in browser.sent_lists

        await conn.close()

    asyncio.run(_run())


def test_send_scheduler_group_empty():
    """EC-03: scheduler sin farm lists → devuelve 0 sin hacer nada."""
    async def _run():
        db, conn = await _make_db()
        await _seed_world(conn)

        sched = await db.create_scheduler(FarmScheduler(
            id=0, world_id=1, name="vacío",
            interval_min_ms=60000, interval_max_ms=120000,
        ))

        browser = StubBrowser()
        uc = SendSchedulerGroupUseCase(browser=browser, db=db)
        count = await uc.execute(sched.id)

        assert count == 0
        assert len(browser.sent_lists) == 0

        await conn.close()

    asyncio.run(_run())


# ===========================================================================
# Tests de SendFarmListUseCase (envío manual)
# ===========================================================================

def test_send_farm_list_manual():
    """Envío manual → FarmListSendEvent con triggered_by='manual'."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)
        fl = _make_farm_list()
        await _insert_farm_list(db, conn, fl)

        browser = StubBrowser()
        uc = SendFarmListUseCase(browser=browser, db=db, world_id=1)
        event = await uc.execute(fl.id)

        assert event.triggered_by == "manual"
        assert event.farm_list_id == fl.id
        assert fl.id in browser.sent_lists

        await conn.close()

    asyncio.run(_run())


# ===========================================================================
# Tests de sincronización (sync_farm_lists / sync_farm_list)
# ===========================================================================

def test_sync_farm_lists_new_list():
    """Lista nueva en DOM → insertada en BD."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)
        fl = _make_farm_list()

        synced = await db.sync_farm_lists(10, [fl])
        assert len(synced) == 1
        assert synced[0].id == fl.id

        # Está en BD
        from_db = await db.get_farm_list_by_id(fl.id)
        assert from_db.id == fl.id

        await conn.close()

    asyncio.run(_run())


def test_sync_farm_lists_deleted_list():
    """Lista eliminada en Travian → borrada en BD."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)
        fl = _make_farm_list()
        await _insert_farm_list(db, conn, fl)

        # Sincronizar con lista vacía → la lista debe borrarse
        synced = await db.sync_farm_lists(10, [])
        assert synced == []

        # No está en BD
        from core.exceptions import FarmListNotFoundError
        try:
            await db.get_farm_list_by_id(fl.id)
            assert False, "Debería haber lanzado FarmListNotFoundError"
        except FarmListNotFoundError:
            pass

        await conn.close()

    asyncio.run(_run())


def test_sync_farm_list_slot_reordered():
    """EC-05 / RN-15: Travian reasigna ID de slot (mismo x,y) → preserva total_bounty."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)
        slot_old = _make_slot(slot_id=200, x=10, y=-3)
        slot_old.total_bounty = 5000  # acumulado
        fl = _make_farm_list(slots=[slot_old])
        await _insert_farm_list(db, conn, fl)

        # Travian reasigna ID del slot: mismo x,y pero id=999
        slot_new = _make_slot(slot_id=999, x=10, y=-3)
        fl_new = _make_farm_list(slots=[slot_new])

        synced = await db.sync_farm_list(fl_new)
        updated_slot = synced.slots[0]
        assert updated_slot.id == 999           # nuevo ID de Travian
        assert updated_slot.total_bounty == 5000  # total_bounty preservado

        await conn.close()

    asyncio.run(_run())


def test_sync_farm_list_ec06_bot_reset():
    """EC-06: slot disabled_by_bot=True en BD + is_active=True del DOM → resetea estado bot."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)
        slot = _make_slot(is_active=False, disabled_by_bot=True)
        fl = _make_farm_list(slots=[slot])
        await _insert_farm_list(db, conn, fl)

        # DOM devuelve is_active=True para el mismo slot (usuario lo reactivó en Travian)
        slot_dom = _make_slot(is_active=True, disabled_by_bot=False)
        fl_dom = _make_farm_list(slots=[slot_dom])

        synced = await db.sync_farm_list(fl_dom)
        updated = synced.slots[0]
        assert updated.disabled_by_bot is False
        assert updated.is_active is True

        await conn.close()

    asyncio.run(_run())


# ===========================================================================
# Tests de ReadFarmListsUseCase
# ===========================================================================

def test_read_farm_lists_success():
    """Navega a la plaza (stub), lee 1 lista, la sincroniza."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn, name="Aldea principal")

        fl = FarmList(
            id=101, name="Lista 1", owner_village_id=0,
            slots=[_make_slot()], village_name="Aldea principal",
        )
        browser = StubBrowser(farm_lists=[fl])
        uc = ReadFarmListsUseCase(browser=browser, db=db)
        result = await uc.execute(world_id=1)

        assert len(result) == 1
        assert result[0].id == 101

        await conn.close()

    asyncio.run(_run())


# ===========================================================================
# Tests de WorldAgent
# ===========================================================================

def test_world_agent_seed_and_reschedule():
    """Scheduler habilitado → encolado en seed; reencolado tras ejecución."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)

        sched = await db.create_scheduler(FarmScheduler(
            id=0, world_id=1, name="sch",
            interval_min_ms=60000, interval_max_ms=120000,
            is_enabled=True,
        ))

        browser = StubBrowser()
        agent = WorldAgent(world_id=1, browser=browser, db=db)
        seeded = await agent.seed_from_schedulers()

        assert seeded == 1
        assert len(agent._queue) == 1
        task = agent._queue.peek_next()
        assert task is not None
        assert task.payload["scheduler_id"] == sched.id

        await conn.close()

    asyncio.run(_run())


def test_world_agent_scheduler_disabled():
    """EC-07: scheduler deshabilitado → no reencola en _reschedule_farm."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)

        sched = await db.create_scheduler(FarmScheduler(
            id=0, world_id=1, name="disabled",
            interval_min_ms=60000, interval_max_ms=120000,
            is_enabled=False,
        ))

        browser = StubBrowser()
        agent = WorldAgent(world_id=1, browser=browser, db=db)
        seeded = await agent.seed_from_schedulers()

        # Scheduler deshabilitado → no se encola
        assert seeded == 0
        assert len(agent._queue) == 0

        await conn.close()

    asyncio.run(_run())


def test_world_agent_reschedule_disabled_at_runtime():
    """EC-07: scheduler deshabilitado en BD durante la ejecución → no reencola."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)

        sched = await db.create_scheduler(FarmScheduler(
            id=0, world_id=1, name="sch",
            interval_min_ms=60000, interval_max_ms=120000,
            is_enabled=True,
        ))

        browser = StubBrowser()
        agent = WorldAgent(world_id=1, browser=browser, db=db)
        # Construir tarea manualmente
        task = agent._build_task_at(sched.id, datetime.utcnow())

        # Deshabilitar antes de _reschedule_farm
        sched.is_enabled = False
        await db.update_scheduler(sched)

        q_before = len(agent._queue)
        await agent._reschedule_farm(task)
        # No debe añadir nada a la cola
        assert len(agent._queue) == q_before

        await conn.close()

    asyncio.run(_run())


def test_world_agent_reschedule_scheduler_deleted():
    """EC-08: scheduler borrado durante la ejecución → no reencola."""
    async def _run():
        db, conn = await _make_db()
        await _seed_world(conn)

        sched = await db.create_scheduler(FarmScheduler(
            id=0, world_id=1, name="sch",
            interval_min_ms=60000, interval_max_ms=120000,
        ))

        browser = StubBrowser()
        agent = WorldAgent(world_id=1, browser=browser, db=db)
        task = agent._build_task_at(sched.id, datetime.utcnow())

        # Borrar el scheduler
        await db.delete_scheduler(sched.id)

        # No debe lanzar excepción y no debe añadir a la cola
        await agent._reschedule_farm(task)
        assert len(agent._queue) == 0

        await conn.close()

    asyncio.run(_run())


def test_world_agent_run_now():
    """run_now(scheduler_id) → tarea adelantada a now, notify_event activado."""
    async def _run():
        db, conn = await _make_db()
        await _seed_world(conn)

        sched = await db.create_scheduler(FarmScheduler(
            id=0, world_id=1, name="sch",
            interval_min_ms=3_600_000, interval_max_ms=7_200_000,
        ))

        browser = StubBrowser()
        agent = WorldAgent(world_id=1, browser=browser, db=db)
        # Poner una tarea en cola con execute_at en el futuro
        # Usar datetime.now() (no utcnow) para ser coherente con WorldAgent.run_now()
        future_task = agent._build_task_at(sched.id, datetime.now() + timedelta(hours=1))
        agent._queue.add(future_task)

        before = agent._queue.peek_next().execute_at

        agent.run_now(sched.id)

        after = agent._queue.peek_next().execute_at
        assert after < before  # se adelantó a now
        assert agent._notify_event.is_set()

        await conn.close()

    asyncio.run(_run())


# ===========================================================================
# Tests de CancelProbeUseCase
# ===========================================================================

def test_cancel_probe_deactivate():
    """mode=deactivate → disabled_by_bot=False, is_active=False, PROBE_CANCELLED."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)

        slot = _make_slot(
            is_active=False,
            disabled_by_bot=True,
            disabled_at=datetime.utcnow(),
            cooldown_seconds=3600,
        )
        fl = _make_farm_list(slots=[slot])
        await _insert_farm_list(db, conn, fl)

        uc = CancelProbeUseCase(db=db)
        updated = await uc.execute(slot.id, fl.id, world_id=1, mode="deactivate")

        assert updated.disabled_by_bot is False
        assert updated.is_active is False

        events, total = await db.get_slot_events(1)
        assert total == 1
        assert events[0].event_type == "PROBE_CANCELLED"

        await conn.close()

    asyncio.run(_run())


def test_cancel_probe_send_now():
    """mode=send_now → cooldown expirado (disabled_at en el pasado)."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)

        now = datetime.utcnow()
        slot = _make_slot(
            is_active=False,
            disabled_by_bot=True,
            disabled_at=now,
            cooldown_seconds=3600,
        )
        fl = _make_farm_list(slots=[slot])
        await _insert_farm_list(db, conn, fl)

        uc = CancelProbeUseCase(db=db)
        updated = await uc.execute(slot.id, fl.id, world_id=1, mode="send_now")

        # El cooldown_seconds se mantiene; disabled_at queda en el pasado (expirado)
        assert updated.disabled_by_bot is True
        assert updated.disabled_at is not None
        elapsed = (datetime.utcnow() - updated.disabled_at).total_seconds()
        assert elapsed > updated.cooldown_seconds  # ya expirado

        await conn.close()

    asyncio.run(_run())


# ===========================================================================
# Tests de ActivateSlotInTravianUseCase
# ===========================================================================

def test_activate_slot_was_bot_disabled():
    """ActivateSlotInTravianUseCase con disabled_by_bot=True → evento REACTIVATED."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)

        slot = _make_slot(is_active=False, disabled_by_bot=True)
        fl = _make_farm_list(slots=[slot])
        await _insert_farm_list(db, conn, fl)

        browser = StubBrowser()
        uc = ActivateSlotInTravianUseCase(browser=browser, db=db)
        updated = await uc.execute(slot.id, fl.id, world_id=1)

        assert updated.is_active is True
        assert updated.disabled_by_bot is False
        assert (slot.id, fl.id) in browser.activated_slots

        events, total = await db.get_slot_events(1)
        assert total == 1
        assert events[0].event_type == "REACTIVATED"

        await conn.close()

    asyncio.run(_run())


def test_activate_slot_not_bot_disabled():
    """ActivateSlotInTravianUseCase con disabled_by_bot=False → NO registra REACTIVATED."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)

        slot = _make_slot(is_active=False, disabled_by_bot=False)
        fl = _make_farm_list(slots=[slot])
        await _insert_farm_list(db, conn, fl)

        browser = StubBrowser()
        uc = ActivateSlotInTravianUseCase(browser=browser, db=db)
        updated = await uc.execute(slot.id, fl.id, world_id=1)

        assert updated.is_active is True
        events, total = await db.get_slot_events(1)
        assert total == 0  # sin evento REACTIVATED

        await conn.close()

    asyncio.run(_run())


# ===========================================================================
# Tests del adaptador SQLite
# ===========================================================================

def test_farm_db_ensure_tables():
    """ensure_tables crea las 5 tablas de farm lists."""
    async def _run():
        db, conn = await _make_db()
        for table in (
            "farm_schedulers", "farm_lists", "farm_slots",
            "farm_list_send_history", "slot_events",
        ):
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
            )
            row = await cursor.fetchone()
            assert row is not None, f"Tabla '{table}' no fue creada"
        await conn.close()

    asyncio.run(_run())


def test_farm_db_scheduler_crud():
    """CRUD de schedulers: create, get, update, delete."""
    async def _run():
        db, conn = await _make_db()
        await _seed_world(conn)

        # CREATE
        s = await db.create_scheduler(FarmScheduler(
            id=0, world_id=1, name="test",
            interval_min_ms=60000, interval_max_ms=120000,
        ))
        assert s.id > 0

        # GET
        fetched = await db.get_scheduler(s.id)
        assert fetched.name == "test"

        # UPDATE
        fetched.name = "updated"
        updated = await db.update_scheduler(fetched)
        assert updated.name == "updated"

        # DELETE
        await db.delete_scheduler(s.id)
        try:
            await db.get_scheduler(s.id)
            assert False, "Debería lanzar SchedulerNotFoundError"
        except SchedulerNotFoundError:
            pass

        await conn.close()

    asyncio.run(_run())


def test_farm_db_history_ttl_purge():
    """RN-13 / EC-15: registros >7 días se purgan automáticamente."""
    async def _run():
        import json as _json
        db, conn = await _make_db()
        await _seed_village(conn)
        fl = _make_farm_list()
        await _insert_farm_list(db, conn, fl)

        # Insertar evento antiguo directamente (>7 días)
        old_ts = (datetime.utcnow() - timedelta(days=8)).isoformat()
        await conn.execute(
            "INSERT INTO farm_list_send_history "
            "(farm_list_id, farm_list_name, world_id, timestamp, status, triggered_by, bot_disabled_slots) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (fl.id, fl.name, 1, old_ts, "success", "scheduler", "[]"),
        )
        await conn.commit()

        # Insertar nuevo evento (trigger de purga)
        event = FarmListSendEvent(
            farm_list_id=fl.id,
            farm_list_name=fl.name,
            world_id=1,
            timestamp=datetime.utcnow(),
            status="success",
            being_raided_current=5,
            being_raided_total=5,
            triggered_by="scheduler",
        )
        await db.add_farm_list_send_event(event)

        items, total = await db.get_farm_list_send_history(1)
        # Solo debe quedar el evento nuevo (el antiguo purgado)
        assert total == 1
        assert items[0].status == "success"

        await conn.close()

    asyncio.run(_run())


def test_farm_db_assign_farm_lists():
    """assign_farm_lists_to_scheduler vincula correctamente las listas."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)

        fl1 = _make_farm_list(fl_id=101)
        fl2 = _make_farm_list(fl_id=102)
        await _insert_farm_list(db, conn, fl1)
        await _insert_farm_list(db, conn, fl2)

        sched = await db.create_scheduler(FarmScheduler(
            id=0, world_id=1, name="s",
            interval_min_ms=60000, interval_max_ms=120000,
        ))
        updated = await db.assign_farm_lists_to_scheduler(sched.id, [101, 102])
        assert set(updated.farm_list_ids) == {101, 102}

        # Reasignar con solo una
        updated2 = await db.assign_farm_lists_to_scheduler(sched.id, [101])
        assert updated2.farm_list_ids == [101]

        # La lista 102 debe tener scheduler_id=NULL
        fl2_db = await db.get_farm_list_by_id(102)
        assert fl2_db.scheduler_id is None

        await conn.close()

    asyncio.run(_run())


def test_farm_db_delete_scheduler_nulls_farm_lists():
    """RN-14: al borrar scheduler, farm_lists quedan con scheduler_id=NULL."""
    async def _run():
        db, conn = await _make_db()
        await _seed_village(conn)

        fl = _make_farm_list()
        await _insert_farm_list(db, conn, fl)

        sched = await db.create_scheduler(FarmScheduler(
            id=0, world_id=1, name="s",
            interval_min_ms=60000, interval_max_ms=120000,
        ))
        await db.assign_farm_lists_to_scheduler(sched.id, [fl.id])

        # Borrar scheduler → farm list queda con scheduler_id=NULL
        await db.delete_scheduler(sched.id)

        fl_db = await db.get_farm_list_by_id(fl.id)
        assert fl_db.scheduler_id is None

        await conn.close()

    asyncio.run(_run())


# ===========================================================================
# Tests de TaskQueue
# ===========================================================================

def test_task_queue_ordering():
    """TaskQueue ordena por (priority, execute_at)."""
    from core.entities.task import Task, TaskType

    now = datetime.utcnow()
    t1 = Task(
        task_type=TaskType.SEND_FARM_LIST_GROUP, world_id=1,
        execute_at=now + timedelta(minutes=2), priority=1,
        payload={}, recurring=True, source_scheduler_id=1,
    )
    t2 = Task(
        task_type=TaskType.SEND_FARM_LIST_GROUP, world_id=1,
        execute_at=now + timedelta(minutes=1), priority=1,
        payload={}, recurring=True, source_scheduler_id=2,
    )

    q = TaskQueue()
    q.add(t1)
    q.add(t2)

    # t2 tiene execute_at menor → primero
    assert q.pop_ready(now + timedelta(minutes=5)).source_scheduler_id == 2
    assert q.pop_ready(now + timedelta(minutes=5)).source_scheduler_id == 1


def test_task_queue_remove_by_scheduler():
    """remove_by_scheduler elimina todas las tareas del scheduler."""
    from core.entities.task import Task, TaskType

    now = datetime.utcnow()
    q = TaskQueue()
    for i in range(3):
        q.add(Task(
            task_type=TaskType.SEND_FARM_LIST_GROUP, world_id=1,
            execute_at=now + timedelta(minutes=i), priority=1,
            payload={}, recurring=True, source_scheduler_id=1,
        ))
    q.add(Task(
        task_type=TaskType.SEND_FARM_LIST_GROUP, world_id=1,
        execute_at=now, priority=1,
        payload={}, recurring=True, source_scheduler_id=2,
    ))

    removed = q.remove_by_scheduler(1)
    assert removed == 3
    assert len(q) == 1
    assert q.peek_next().source_scheduler_id == 2


def test_task_queue_pop_ready_future():
    """pop_ready no devuelve tareas en el futuro."""
    from core.entities.task import Task, TaskType

    now = datetime.utcnow()
    q = TaskQueue()
    q.add(Task(
        task_type=TaskType.SEND_FARM_LIST_GROUP, world_id=1,
        execute_at=now + timedelta(minutes=10), priority=1,
        payload={}, recurring=True, source_scheduler_id=1,
    ))
    assert q.pop_ready(now) is None
