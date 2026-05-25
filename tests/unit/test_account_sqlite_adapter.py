"""
Tests de integración del AccountSQLiteAdapter con BD real en memoria (:memory:).
IT-01 a IT-07 del Plan de pruebas.

Patrón: abrimos una conexión aiosqlite en cada test (asyncio.run) para aislar el estado.
El patrón `asyncio.run(coro)` es consistente con el resto del proyecto
(ver test_login_use_case.py, test_building_sqlite_adapter.py).
"""
import asyncio

import aiosqlite
import pytest

from adapters.db.account_sqlite_adapter import AccountSQLiteAdapter
from core.entities.account import Account
from core.entities.tribe import Tribe
from core.entities.world import World
from core.exceptions import DuplicateAccountError, DuplicateWorldError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_adapter() -> tuple[AccountSQLiteAdapter, aiosqlite.Connection]:
    """Crea un adaptador con BD :memory: y tablas ya creadas."""
    conn = await aiosqlite.connect(":memory:")
    await conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = aiosqlite.Row
    adapter = AccountSQLiteAdapter(conn)
    await adapter.ensure_tables()
    return adapter, conn


async def _save_test_account(adapter, email="a@b.com", username="user", password=b"fake_token"):
    account = Account(id=None, email=email, username=username, password="plain")
    return await adapter.save_account(account, password)


# ---------------------------------------------------------------------------
# IT-01: ensure_tables crea las 3 tablas
# ---------------------------------------------------------------------------

def test_ensure_tables_crea_tablas():
    """IT-01: tras ensure_tables, accounts, worlds y villages existen."""
    async def _run():
        adapter, conn = await _make_adapter()
        try:
            for table in ("accounts", "worlds", "villages"):
                cursor = await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
                )
                row = await cursor.fetchone()
                assert row is not None, f"Tabla '{table}' no fue creada"
        finally:
            await conn.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# IT-02: FK ON DELETE CASCADE activo
# ---------------------------------------------------------------------------

def test_delete_account_borra_worlds_en_cascada():
    """IT-02: PRAGMA foreign_keys activado → DELETE account borra worlds en cascada."""
    async def _run():
        adapter, conn = await _make_adapter()
        try:
            account = await _save_test_account(adapter)
            world = World(id=0, server="https://ts1.travian.com/", tribe=Tribe.ROMANS)
            await adapter.save_world(account.id, world)

            worlds_before = await adapter.list_worlds(account.id)
            assert len(worlds_before) == 1

            await adapter.delete_account(account.id)

            # Verificar directamente en la BD que no quedan worlds
            cursor = await conn.execute("SELECT COUNT(*) FROM worlds")
            count = (await cursor.fetchone())[0]
            assert count == 0
        finally:
            await conn.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# IT-03: UNIQUE constraint en email
# ---------------------------------------------------------------------------

def test_unique_email_constraint():
    """IT-03: segundo INSERT con mismo email → IntegrityError mapeado a DuplicateAccountError."""
    async def _run():
        adapter, conn = await _make_adapter()
        try:
            await _save_test_account(adapter, email="dup@example.com")
            with pytest.raises(DuplicateAccountError) as exc_info:
                await _save_test_account(adapter, email="dup@example.com")
            assert "dup@example.com" in str(exc_info.value)
        finally:
            await conn.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# IT-04: UNIQUE constraint (account_id, server)
# ---------------------------------------------------------------------------

def test_unique_account_server_constraint():
    """IT-04: mismo (account_id, server) → DuplicateWorldError."""
    async def _run():
        adapter, conn = await _make_adapter()
        try:
            account = await _save_test_account(adapter)
            world = World(id=0, server="https://ts1.travian.com/", tribe=Tribe.ROMANS)
            await adapter.save_world(account.id, world)
            with pytest.raises(DuplicateWorldError):
                await adapter.save_world(account.id, World(id=0, server="https://ts1.travian.com/", tribe=Tribe.GAULS))
        finally:
            await conn.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# IT-05: save_account devuelve id autoincrement
# ---------------------------------------------------------------------------

def test_save_account_devuelve_id_autoincrement():
    """IT-05: id asignado > 0."""
    async def _run():
        adapter, conn = await _make_adapter()
        try:
            account = await _save_test_account(adapter, email="first@example.com")
            assert account.id is not None
            assert account.id > 0
            account2 = await _save_test_account(adapter, email="second@example.com")
            assert account2.id > account.id
        finally:
            await conn.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# IT-06: list_accounts carga mundos de cada cuenta (relación 1:N)
# ---------------------------------------------------------------------------

def test_list_accounts_con_mundos():
    """IT-06: list_accounts carga correctamente la relación 1:N."""
    async def _run():
        adapter, conn = await _make_adapter()
        try:
            a1 = await _save_test_account(adapter, email="a1@example.com")
            a2 = await _save_test_account(adapter, email="a2@example.com")
            world1 = World(id=0, server="https://ts1.travian.com/", tribe=Tribe.ROMANS)
            world2 = World(id=0, server="https://ts2.travian.com/", tribe=Tribe.GAULS)
            await adapter.save_world(a1.id, world1)
            await adapter.save_world(a1.id, world2)

            accounts = await adapter.list_accounts()
            assert len(accounts) == 2
            acc_with_worlds = next(a for a in accounts if a.id == a1.id)
            assert len(acc_with_worlds.worlds) == 2
            acc_without = next(a for a in accounts if a.id == a2.id)
            assert len(acc_without.worlds) == 0
        finally:
            await conn.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# IT-07: delete_account borra worlds
# ---------------------------------------------------------------------------

def test_delete_account_borra_worlds():
    """IT-07: tras delete_account, la lista de worlds de esa cuenta está vacía."""
    async def _run():
        adapter, conn = await _make_adapter()
        try:
            account = await _save_test_account(adapter)
            world = World(id=0, server="https://ts1.travian.com/", tribe=Tribe.ROMANS)
            await adapter.save_world(account.id, world)
            await adapter.delete_account(account.id)

            cursor = await conn.execute("SELECT COUNT(*) FROM worlds WHERE account_id=?", (account.id,))
            count = (await cursor.fetchone())[0]
            assert count == 0
        finally:
            await conn.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Extra: update_account sin password no cambia el token cifrado
# ---------------------------------------------------------------------------

def test_update_account_sin_password_no_cambia_token():
    """UT-20 / EC-22: update_account con password_cifrada=None → token en BD sin cambio."""
    async def _run():
        adapter, conn = await _make_adapter()
        try:
            original_token = b"original_fernet_token"
            account = await _save_test_account(adapter, password=original_token)

            await adapter.update_account(account.id, "a@b.com", "nuevo_nombre", None)

            cursor = await conn.execute("SELECT password FROM accounts WHERE id=?", (account.id,))
            row = await cursor.fetchone()
            assert row["password"] == original_token
        finally:
            await conn.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Extra: UT-20 — IntegrityError en save_account → DuplicateAccountError
# ---------------------------------------------------------------------------

def test_integrity_error_mapeado_a_duplicate_account_error():
    """UT-20: IntegrityError en save_account se mapea a DuplicateAccountError."""
    async def _run():
        adapter, conn = await _make_adapter()
        try:
            await _save_test_account(adapter, email="x@example.com")
            with pytest.raises(DuplicateAccountError):
                await _save_test_account(adapter, email="x@example.com")
        finally:
            await conn.close()

    asyncio.run(_run())
