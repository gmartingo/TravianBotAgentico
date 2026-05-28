"""
Tests de la API de farm lists — cambios del contrato v2.

Cubre:
  - Aliases de FarmListSendEvent: sent_at, slots_sent, deactivated_slots
  - Agregados de FarmList: total_bounty, avg_bounty_per_send, last_send_time
  - Toggle scheduler: habilita/deshabilita (200) y 404 para scheduler inexistente
  - Filtro por scheduler_id en GET /worlds/{id}/slot-events

Estrategia:
  - Tests 1-3 (serialización): unidad pura — se importan y llaman las helpers directamente.
  - Tests 4-6 (toggle): TestClient con BD temporal, datos creados vía HTTP.
  - Test 7 (filtro): TestClient + BD en archivo temporal compartido con asyncio.run()
    para insertar datos de prueba que no tienen endpoint de escritura disponible.
"""
from __future__ import annotations

import asyncio
from datetime import datetime

import aiosqlite
import pytest
from fastapi.testclient import TestClient

from adapters.api.main import app
from adapters.api.routes.farm import _serialize_farm_list, _serialize_send_event
from core.entities.farm_list import FarmList, FarmSlot
from core.entities.farm_list_send_event import FarmListSendEvent


# ---------------------------------------------------------------------------
# Fixtures HTTP
# ---------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch, tmp_path):
    """TestClient con BD en archivo temporal y lifespan real."""
    db_file = tmp_path / "test_farm_api.db"
    monkeypatch.setattr("adapters.db.database.DB_PATH", str(db_file))
    for attr in ("world_runtime_port", "farm_db_port", "world_agents"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)
    with TestClient(app) as c:
        yield c, str(db_file)
    for attr in ("world_runtime_port", "farm_db_port", "world_agents"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)


def _setup_world(c: TestClient) -> int:
    """Crea account + world vía HTTP. Devuelve world_id."""
    r = c.post(
        "/accounts",
        json={"email": "farm@test.com", "username": "farmbot", "password": "secret123"},
    )
    assert r.status_code == 201, r.text
    account_id = r.json()["id"]
    r = c.post(
        f"/accounts/{account_id}/worlds",
        json={"server": "https://ts1.travian.com/", "tribe": "romans"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_scheduler(c: TestClient, world_id: int, *, is_enabled: bool = True, name: str = "Sched") -> int:
    r = c.post(
        f"/farm/worlds/{world_id}/schedulers",
        json={
            "name": name,
            "interval_min_ms": 60_000,
            "interval_max_ms": 120_000,
            "is_enabled": is_enabled,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------------------------------------------------------------------------
# Tests 1-3: serialización (unidad pura — sin HTTP)
# ---------------------------------------------------------------------------


def test_serialize_send_event_aliases():
    """_serialize_send_event usa nombres canónicos: sent_at, slots_sent, deactivated_slots."""
    ev = FarmListSendEvent(
        farm_list_id=101,
        farm_list_name="Lista A",
        world_id=1,
        timestamp=datetime(2025, 6, 1, 12, 0, 0),
        status="success",
        being_raided_current=7,
        being_raided_total=10,
        triggered_by="manual",
        bot_disabled_slots=["Aldea1", "Aldea2"],
    )
    data = _serialize_send_event(ev)

    # Nombres canónicos presentes
    assert data["sent_at"] == ev.timestamp.isoformat()
    assert data["slots_sent"] == 7
    assert data["deactivated_slots"] == ["Aldea1", "Aldea2"]
    # Nombres de dominio eliminados — un único nombre por campo (palantir)
    assert "timestamp" not in data
    assert "being_raided_current" not in data
    assert "bot_disabled_slots" not in data


def test_serialize_farm_list_aggregates():
    """_serialize_farm_list incluye total_bounty, avg_bounty_per_send y last_send_time."""
    slots = [
        FarmSlot(id=1, farm_list_id=10, target_name="A", x=1, y=1,
                 is_active=True, total_bounty=1000, average_raid_bounty=200),
        FarmSlot(id=2, farm_list_id=10, target_name="B", x=2, y=2,
                 is_active=True, total_bounty=500, average_raid_bounty=100),
        FarmSlot(id=3, farm_list_id=10, target_name="C", x=3, y=3,
                 is_active=False, total_bounty=300, average_raid_bounty=50),
    ]
    fl = FarmList(id=10, name="Lista X", owner_village_id=5, slots=slots)
    data = _serialize_farm_list(fl)

    # total_bounty suma todos los slots (activos + inactivos)
    assert data["total_bounty"] == 1800
    # avg_bounty_per_send promedia solo los activos: (200+100)/2 = 150
    assert data["avg_bounty_per_send"] == 150
    # last_send_time es None (placeholder)
    assert data["last_send_time"] is None


def test_serialize_farm_list_no_active_slots():
    """avg_bounty_per_send es 0 cuando no hay slots activos."""
    slots = [
        FarmSlot(id=1, farm_list_id=10, target_name="A", x=1, y=1,
                 is_active=False, total_bounty=500, average_raid_bounty=100),
    ]
    fl = FarmList(id=10, name="Lista X", owner_village_id=5, slots=slots)
    data = _serialize_farm_list(fl)

    assert data["avg_bounty_per_send"] == 0
    assert data["total_bounty"] == 500


# ---------------------------------------------------------------------------
# Tests 4-6: toggle scheduler (HTTP)
# ---------------------------------------------------------------------------


def test_toggle_scheduler_enables(client):
    """POST toggle sobre scheduler enabled → devuelve is_enabled=False (200)."""
    c, _ = client
    world_id = _setup_world(c)
    scheduler_id = _create_scheduler(c, world_id, is_enabled=True)

    r = c.post(f"/farm/worlds/{world_id}/schedulers/{scheduler_id}/toggle")
    assert r.status_code == 200
    assert r.json()["is_enabled"] is False


def test_toggle_scheduler_disables(client):
    """POST toggle sobre scheduler disabled → devuelve is_enabled=True (200)."""
    c, _ = client
    world_id = _setup_world(c)
    scheduler_id = _create_scheduler(c, world_id, is_enabled=False)

    r = c.post(f"/farm/worlds/{world_id}/schedulers/{scheduler_id}/toggle")
    assert r.status_code == 200
    assert r.json()["is_enabled"] is True


def test_toggle_scheduler_404(client):
    """POST toggle sobre scheduler inexistente → 404 con detail legible."""
    c, _ = client
    world_id = _setup_world(c)
    r = c.post(f"/farm/worlds/{world_id}/schedulers/99999/toggle")
    assert r.status_code == 404
    assert "99999" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Test 7: filtro por scheduler_id en GET /slot-events (HTTP)
# ---------------------------------------------------------------------------


def test_slot_events_filter_by_scheduler(client):
    """GET /slot-events?scheduler_id= devuelve solo eventos de farm lists del scheduler."""
    c, db_path = client
    world_id = _setup_world(c)

    # Insertar aldea + 2 farm lists directamente en la BD compartida.
    # FK OFF en esta conexión auxiliar para simplificar fixtures.
    async def _insert_fixtures():
        conn = await aiosqlite.connect(db_path)
        await conn.execute("PRAGMA foreign_keys = OFF")
        await conn.execute(
            "INSERT OR IGNORE INTO villages (id, world_id, data_id, name, x, y) "
            "VALUES (10, ?, 1000, 'Aldea test', 0, 0)",
            (world_id,),
        )
        await conn.execute(
            "INSERT INTO farm_lists (id, name, owner_village_id) VALUES (101, 'Lista 1', 10)"
        )
        await conn.execute(
            "INSERT INTO farm_lists (id, name, owner_village_id) VALUES (102, 'Lista 2', 10)"
        )
        await conn.commit()
        await conn.close()

    asyncio.run(_insert_fixtures())

    # Crear scheduler y asignar solo farm list 101
    scheduler_id = _create_scheduler(c, world_id)
    r = c.put(
        f"/farm/worlds/{world_id}/schedulers/{scheduler_id}/farm-lists",
        json={"farm_list_ids": [101]},
    )
    assert r.status_code == 200

    # Insertar 2 eventos para fl 101 y 1 evento para fl 102
    async def _insert_events():
        conn = await aiosqlite.connect(db_path)
        await conn.execute("PRAGMA foreign_keys = OFF")
        now = datetime.utcnow().isoformat()
        for i in range(2):
            await conn.execute(
                "INSERT INTO slot_events "
                "(timestamp, slot_id, slot_name, farm_list_id, farm_list_name, world_id, event_type) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (now, 200 + i, f"Slot {i}", 101, "Lista 1", world_id, "LOSSES_DETECTED"),
            )
        await conn.execute(
            "INSERT INTO slot_events "
            "(timestamp, slot_id, slot_name, farm_list_id, farm_list_name, world_id, event_type) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (now, 300, "Slot otro", 102, "Lista 2", world_id, "LOSSES_DETECTED"),
        )
        await conn.commit()
        await conn.close()

    asyncio.run(_insert_events())

    # Sin filtro → 3 eventos
    r = c.get(f"/farm/worlds/{world_id}/slot-events")
    assert r.status_code == 200
    assert r.json()["total"] == 3

    # Con filtro scheduler_id → solo 2 eventos de fl 101
    r = c.get(f"/farm/worlds/{world_id}/slot-events?scheduler_id={scheduler_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2
    assert all(ev["farm_list_id"] == 101 for ev in data["items"])
