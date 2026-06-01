"""
Tests de integración para Human Sessions — IT-HS01 … IT-HS10.

Spec §12 — Pruebas de integración (con BD SQLite, sin browser).

Estrategia:
  - TestClient con BD temporal (monkeypatch de DB_PATH).
  - Lifespan real (con TestClient en modo context manager).
  - Crea account+world vía HTTP antes de cada test que lo necesite.
  - Los tests IT-HS05 y IT-HS07 (override y transiciones de modo)
    verifican tanto la API como el adaptador de BD.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import aiosqlite
import pytest
from fastapi.testclient import TestClient

from adapters.api.main import app


# ---------------------------------------------------------------------------
# Fixture de cliente HTTP con BD temporal
# ---------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch, tmp_path):
    """TestClient con BD en archivo temporal y lifespan real."""
    db_file = tmp_path / "test_session_api.db"
    monkeypatch.setattr("adapters.db.database.DB_PATH", str(db_file))
    # Limpiar state residual de tests anteriores
    for attr in ("world_runtime_port", "farm_db_port", "world_agents",
                 "session_db_port", "db_port"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)
    with TestClient(app) as c:
        yield c, str(db_file)
    for attr in ("world_runtime_port", "farm_db_port", "world_agents",
                 "session_db_port", "db_port"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)


def _setup_world(c: TestClient) -> tuple[int, int]:
    """Crea account + world vía HTTP. Devuelve (account_id, world_id)."""
    r = c.post(
        "/accounts",
        json={"email": "session_test@example.com", "username": "sessionbot", "password": "pass123"},
    )
    assert r.status_code == 201, r.text
    account_id = r.json()["id"]

    r = c.post(
        f"/accounts/{account_id}/worlds",
        json={"server": "https://ts1.travian.com/", "tribe": "romans"},
    )
    assert r.status_code == 201, r.text
    world_id = r.json()["id"]
    return account_id, world_id


# ---------------------------------------------------------------------------
# IT-HS01 — PUT timeline con bloques parciales → GET devuelve huecos rellenados
# ---------------------------------------------------------------------------

def test_IT_HS01_put_partial_timeline_fills_gaps(client):
    """Envía solo [09:00-18:00 HARDCORE], lee de vuelta, verifica 3 bloques."""
    c, _ = client
    _, world_id = _setup_world(c)

    r = c.put(
        f"/worlds/{world_id}/session/timeline/0",
        json={
            "jitter_minutes": 15,
            "blocks": [
                {"start": "09:00", "end": "18:00", "mode": "HARDCORE"},
            ],
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    blocks = data["blocks"]
    assert len(blocks) == 3, f"Esperaba 3 bloques, hubo {len(blocks)}: {blocks}"

    # Verificar el orden y modos
    assert blocks[0]["start"] == "00:00" and blocks[0]["end"] == "09:00" and blocks[0]["mode"] == "DISCONNECTED"
    assert blocks[1]["start"] == "09:00" and blocks[1]["end"] == "18:00" and blocks[1]["mode"] == "HARDCORE"
    assert blocks[2]["start"] == "18:00" and blocks[2]["end"] == "24:00" and blocks[2]["mode"] == "DISCONNECTED"
    assert data["is_default"] is False


# ---------------------------------------------------------------------------
# IT-HS02 — PUT timeline con blocks:[] → GET devuelve 24h DISCONNECTED
# ---------------------------------------------------------------------------

def test_IT_HS02_put_empty_timeline_returns_full_disconnected(client):
    """Envía lista vacía → 1 bloque 00:00-24:00 DISCONNECTED."""
    c, _ = client
    _, world_id = _setup_world(c)

    r = c.put(
        f"/worlds/{world_id}/session/timeline/1",
        json={"jitter_minutes": 15, "blocks": []},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["blocks"]) == 1
    b = data["blocks"][0]
    assert b["start"] == "00:00" and b["end"] == "24:00" and b["mode"] == "DISCONNECTED"


# ---------------------------------------------------------------------------
# IT-HS03 — PUT timeline con solape → 422, BD no modificada
# ---------------------------------------------------------------------------

def test_IT_HS03_put_timeline_with_overlap_returns_422(client):
    """Dos bloques que se solapan → 422 con detail descriptivo."""
    c, _ = client
    _, world_id = _setup_world(c)

    r = c.put(
        f"/worlds/{world_id}/session/timeline/2",
        json={
            "jitter_minutes": 10,
            "blocks": [
                {"start": "08:00", "end": "12:00", "mode": "HARDCORE"},
                {"start": "11:00", "end": "14:00", "mode": "PASIVO"},
            ],
        },
    )
    assert r.status_code == 422, r.text
    assert "solapan" in r.json().get("detail", "").lower() or "overlap" in r.json().get("detail", "").lower()


# ---------------------------------------------------------------------------
# IT-HS04 — PUT timeline completo sin huecos → round-trip idéntico
# ---------------------------------------------------------------------------

def test_IT_HS04_put_complete_timeline_round_trip(client):
    """8 bloques que cubren 24h → respuesta 200, round-trip idéntico."""
    c, _ = client
    _, world_id = _setup_world(c)

    blocks_in = [
        {"start": "00:00", "end": "08:00", "mode": "DISCONNECTED"},
        {"start": "08:00", "end": "11:00", "mode": "HARDCORE"},
        {"start": "11:00", "end": "11:30", "mode": "PASIVO"},
        {"start": "11:30", "end": "14:00", "mode": "HARDCORE"},
        {"start": "14:00", "end": "16:00", "mode": "DISCONNECTED"},
        {"start": "16:00", "end": "19:00", "mode": "HARDCORE"},
        {"start": "19:00", "end": "20:30", "mode": "DISCONNECTED"},
        {"start": "20:30", "end": "24:00", "mode": "HARDCORE"},
    ]

    r = c.put(
        f"/worlds/{world_id}/session/timeline/0",
        json={"jitter_minutes": 15, "blocks": blocks_in},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # El round-trip debe ser idéntico (sin bloques extra, mismos modos)
    assert len(data["blocks"]) == len(blocks_in)
    for expected, actual in zip(blocks_in, data["blocks"]):
        assert actual["start"] == expected["start"]
        assert actual["end"] == expected["end"]
        assert actual["mode"] == expected["mode"]


# ---------------------------------------------------------------------------
# IT-HS05 — SET override → GET session muestra override
# ---------------------------------------------------------------------------

def test_IT_HS05_set_override_visible_in_get_session(client):
    """Escribir override PASIVO → GET /session refleja el override."""
    c, _ = client
    _, world_id = _setup_world(c)

    # Configurar un día entero HARDCORE para que el estado base sea HARDCORE
    c.put(
        f"/worlds/{world_id}/session/timeline/0",
        json={"jitter_minutes": 0, "blocks": [
            {"start": "00:00", "end": "24:00", "mode": "HARDCORE"}
        ]},
    )

    # Override a PASIVO
    r = c.put(
        f"/worlds/{world_id}/session/mode",
        json={"mode": "PASIVO"},
    )
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["already_active"] is False
    assert result["requires_relogin"] is False
    assert result["chrome_action"] == "none"

    # GET session debe mostrar el override
    r = c.get(f"/worlds/{world_id}/session")
    assert r.status_code == 200, r.text
    data = r.json()
    # El override está en BD → current_mode devuelve PASIVO
    assert data["mode"] == "PASIVO"
    assert data["override"] is not None
    assert data["override"]["mode"] == "PASIVO"


# ---------------------------------------------------------------------------
# IT-HS06 — Override expirado → get_override devuelve None y limpia BD
# ---------------------------------------------------------------------------

def test_IT_HS06_expired_override_cleaned_up(client):
    """Override con expires_at en el pasado → GET session no muestra override."""
    c, db_path = client
    _, world_id = _setup_world(c)

    # Insertar override expirado directamente en BD
    past_dt = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

    async def _insert():
        conn = await aiosqlite.connect(db_path)
        await conn.execute("PRAGMA journal_mode=WAL;")
        await conn.execute(
            "INSERT OR REPLACE INTO world_session_override (world_id, mode, expires_at) VALUES (?,?,?)",
            (world_id, "PASIVO", past_dt),
        )
        await conn.commit()
        await conn.close()

    asyncio.run(_insert())

    # GET session: el override expirado debe ser limpiado y no aparecer
    r = c.get(f"/worlds/{world_id}/session")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["override"] is None


# ---------------------------------------------------------------------------
# IT-HS07 — Ciclo: HARDCORE → PASIVO (override) → verificar transición
# ---------------------------------------------------------------------------

def test_IT_HS07_override_cycle(client):
    """
    Simula un ciclo de override:
    1. Timeline dice HARDCORE.
    2. Override manual a PASIVO → current_mode devuelve PASIVO.
    3. Override hacia DISCONNECTED → chrome_action='close'.
    """
    c, _ = client
    _, world_id = _setup_world(c)

    # Configurar timeline todo HARDCORE
    c.put(
        f"/worlds/{world_id}/session/timeline/0",
        json={"jitter_minutes": 0, "blocks": [
            {"start": "00:00", "end": "24:00", "mode": "HARDCORE"}
        ]},
    )

    # Override a PASIVO
    r = c.put(f"/worlds/{world_id}/session/mode", json={"mode": "PASIVO"})
    assert r.status_code == 200
    assert r.json()["mode"] == "PASIVO"
    assert r.json()["chrome_action"] == "none"

    # GET session: modo debe ser PASIVO
    r = c.get(f"/worlds/{world_id}/session")
    assert r.json()["mode"] == "PASIVO"

    # Override a DISCONNECTED
    r = c.put(f"/worlds/{world_id}/session/mode", json={"mode": "DISCONNECTED"})
    assert r.status_code == 200
    assert r.json()["chrome_action"] == "close"
    assert r.json()["requires_relogin"] is False


# ---------------------------------------------------------------------------
# IT-HS08 — Timeline default devuelto para día sin configurar
# ---------------------------------------------------------------------------

def test_IT_HS08_default_timeline_for_unconfigured_day(client):
    """Sin filas en BD para martes → GET devuelve is_default=true."""
    c, _ = client
    _, world_id = _setup_world(c)

    r = c.get(f"/worlds/{world_id}/session/timeline")
    assert r.status_code == 200, r.text
    timelines = r.json()["timelines"]

    # Los 7 días deben estar presentes
    assert len(timelines) == 7

    # Todos deben ser is_default=True (ninguno fue configurado)
    for tl in timelines:
        assert tl["is_default"] is True, f"weekday {tl['weekday']} debería ser is_default"
        assert len(tl["blocks"]) > 0


# ---------------------------------------------------------------------------
# IT-HS09 — PUT /session/config → GET round-trip
# ---------------------------------------------------------------------------

def test_IT_HS09_put_config_round_trip(client):
    """Escribe factor=3.0, probability=0.10 → lee de vuelta, verifica valores."""
    c, _ = client
    _, world_id = _setup_world(c)

    r = c.put(
        f"/worlds/{world_id}/session/config",
        json={"passive_interval_factor": 3.0, "passive_send_probability": 0.10},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["passive_interval_factor"] == 3.0
    assert data["passive_send_probability"] == 0.10

    # Leer de vuelta
    r = c.get(f"/worlds/{world_id}/session/config")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["passive_interval_factor"] == 3.0
    assert data["passive_send_probability"] == 0.10


# ---------------------------------------------------------------------------
# IT-HS10 — PUT /session/config con valor fuera de rango → 422
# ---------------------------------------------------------------------------

def test_IT_HS10_put_config_out_of_range_returns_422(client):
    """factor=6.0 (> 5.0) → 422."""
    c, _ = client
    _, world_id = _setup_world(c)

    r = c.put(
        f"/worlds/{world_id}/session/config",
        json={"passive_interval_factor": 6.0},
    )
    assert r.status_code == 422, r.text
    assert "passive_interval_factor" in r.json().get("detail", "")

    # También para probability
    r = c.put(
        f"/worlds/{world_id}/session/config",
        json={"passive_send_probability": 0.99},
    )
    assert r.status_code == 422, r.text
    assert "passive_send_probability" in r.json().get("detail", "")


# ---------------------------------------------------------------------------
# Tests adicionales de validación (edge cases del spec)
# ---------------------------------------------------------------------------

def test_IT_extra_timeline_404_unknown_world(client):
    """GET /session para mundo inexistente → 404."""
    c, _ = client
    r = c.get("/worlds/9999/session")
    assert r.status_code == 404


def test_IT_extra_already_active_override(client):
    """PUT /session/mode con modo ya activo → 200 + already_active=true."""
    c, _ = client
    _, world_id = _setup_world(c)

    # Timeline todo HARDCORE
    c.put(
        f"/worlds/{world_id}/session/timeline/0",
        json={"jitter_minutes": 0, "blocks": [
            {"start": "00:00", "end": "24:00", "mode": "HARDCORE"}
        ]},
    )

    # Solicitar HARDCORE cuando ya está en HARDCORE
    r = c.put(f"/worlds/{world_id}/session/mode", json={"mode": "HARDCORE"})
    assert r.status_code == 200
    data = r.json()
    assert data["already_active"] is True
    assert data["chrome_action"] == "none"


def test_IT_extra_config_patch_partial(client):
    """PUT /session/config con solo un campo → el otro conserva su valor."""
    c, _ = client
    _, world_id = _setup_world(c)

    # Escribir ambos campos
    c.put(
        f"/worlds/{world_id}/session/config",
        json={"passive_interval_factor": 3.0, "passive_send_probability": 0.20},
    )

    # Actualizar solo factor → probability debe conservarse en 0.20
    r = c.put(
        f"/worlds/{world_id}/session/config",
        json={"passive_interval_factor": 4.0},
    )
    assert r.status_code == 200
    assert r.json()["passive_interval_factor"] == 4.0
    assert r.json()["passive_send_probability"] == 0.20


def test_IT_extra_put_config_no_fields_422(client):
    """PUT /session/config sin ningún campo → 422."""
    c, _ = client
    _, world_id = _setup_world(c)

    r = c.put(f"/worlds/{world_id}/session/config", json={})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# IT-HS11 — DELETE /session/override cancelar override existente → 204 + modo recuperado
# ---------------------------------------------------------------------------

def test_IT_HS11_delete_override_cancels_active_override(client):
    """Pone override PASIVO y luego lo cancela: 204 + GET session ya no muestra override."""
    c, _ = client
    _, world_id = _setup_world(c)

    # Configurar timeline todo HARDCORE
    c.put(
        f"/worlds/{world_id}/session/timeline/0",
        json={"jitter_minutes": 0, "blocks": [
            {"start": "00:00", "end": "24:00", "mode": "HARDCORE"}
        ]},
    )

    # Poner override a PASIVO
    r = c.put(f"/worlds/{world_id}/session/mode", json={"mode": "PASIVO"})
    assert r.status_code == 200

    # Verificar que el override está activo
    r = c.get(f"/worlds/{world_id}/session")
    assert r.json()["override"] is not None

    # Cancelar el override
    r = c.delete(f"/worlds/{world_id}/session/override")
    assert r.status_code == 204
    assert r.content == b""  # 204 no tiene body

    # Verificar que el override ya no existe y el modo vuelve al calendario
    r = c.get(f"/worlds/{world_id}/session")
    assert r.status_code == 200
    data = r.json()
    assert data["override"] is None
    assert data["mode"] == "HARDCORE"  # vuelve al bloque del calendario


# ---------------------------------------------------------------------------
# IT-HS12 — DELETE /session/override idempotente sin override previo → 204
# ---------------------------------------------------------------------------

def test_IT_HS12_delete_override_idempotente_sin_override(client):
    """Borrar override cuando no hay ninguno activo → 204 igualmente."""
    c, _ = client
    _, world_id = _setup_world(c)

    # Sin haber puesto override, el DELETE debe responder 204
    r = c.delete(f"/worlds/{world_id}/session/override")
    assert r.status_code == 204
    assert r.content == b""

    # Llamar dos veces seguidas también es 204
    r = c.delete(f"/worlds/{world_id}/session/override")
    assert r.status_code == 204


# ---------------------------------------------------------------------------
# IT-HS13 — DELETE /session/override mundo inexistente → 404
# ---------------------------------------------------------------------------

def test_IT_HS13_delete_override_mundo_inexistente_devuelve_404(client):
    """DELETE /session/override para world_id inexistente → 404."""
    c, _ = client
    r = c.delete("/worlds/9999/session/override")
    assert r.status_code == 404
    assert "Mundo no encontrado" in r.json().get("detail", "")


def test_IT_extra_disconnected_to_hardcore_override_requires_relogin(client):
    """Override hacia HARDCORE estando en DISCONNECTED → requires_relogin=true, chrome_action=open."""
    c, _ = client
    _, world_id = _setup_world(c)

    # Configurar TODOS los días como DISCONNECTED (para que el día actual sea DISCONNECTED)
    for weekday in range(7):
        c.put(
            f"/worlds/{world_id}/session/timeline/{weekday}",
            json={"jitter_minutes": 0, "blocks": [
                {"start": "00:00", "end": "24:00", "mode": "DISCONNECTED"}
            ]},
        )

    # Verificar que el estado actual es DISCONNECTED
    r = c.get(f"/worlds/{world_id}/session")
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "DISCONNECTED"

    # Forzar override a HARDCORE desde DISCONNECTED
    r = c.put(f"/worlds/{world_id}/session/mode", json={"mode": "HARDCORE"})
    assert r.status_code == 200
    data = r.json()
    assert data["requires_relogin"] is True
    assert data["chrome_action"] == "open"
