"""
Adaptador SQLite para la gestión de cuentas y mundos (DbPort).

Implementa DbPort usando aiosqlite con SQL crudo (sin Alembic, sin ORM),
coherente con el patrón del proyecto (ver adapters/db/game_data_sqlite_adapter.py).

Tablas gestionadas:
  - accounts  — credenciales de cuentas (password como BLOB cifrado Fernet)
  - worlds    — mundos (servidores Travian) por cuenta
  - villages  — aldeas por mundo (esquema creado, sin endpoints en esta feature)

Seguridad:
  - La contraseña llega ya cifrada (bytes) desde el use case — este adaptador
    no conoce el objeto Fernet, solo almacena/recupera el token opaco.
  - PRAGMA foreign_keys=ON se activa en ensure_tables() y se mantiene durante
    toda la vida de la conexión compartida.
  - IntegrityError de aiosqlite se mapea a DuplicateAccountError/DuplicateWorldError.

Trade-off documentado (RT-03 del spec):
  - list_accounts() genera N queries adicionales (una por cuenta) para cargar
    sus mundos. Con el volumen esperado (1-10 cuentas) no es problema.
    Si crece, resolver con JOIN en el adaptador.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

import aiosqlite

from core.entities.account import Account
from core.entities.tribe import Tribe
from core.entities.world import World
from core.exceptions import DuplicateAccountError, DuplicateWorldError
from core.ports.db_port import DbPort

# ---------------------------------------------------------------------------
# DDL — ejecutado una sola vez por ensure_tables()
# ---------------------------------------------------------------------------

_CREATE_ACCOUNTS = """
CREATE TABLE IF NOT EXISTS accounts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email       TEXT    NOT NULL,
    username    TEXT    NOT NULL,
    password    BLOB    NOT NULL,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);
"""

_CREATE_UNIQUE_IDX_ACCOUNTS_EMAIL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_email ON accounts(email);
"""

_CREATE_WORLDS = """
CREATE TABLE IF NOT EXISTS worlds (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    server      TEXT    NOT NULL,
    tribe       TEXT    NOT NULL,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL,
    UNIQUE (account_id, server)
);
"""

_CREATE_IDX_WORLDS_ACCOUNT = """
CREATE INDEX IF NOT EXISTS idx_worlds_account ON worlds(account_id);
"""

_CREATE_VILLAGES = """
CREATE TABLE IF NOT EXISTS villages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id    INTEGER NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    data_id     INTEGER NOT NULL,
    name        TEXT    NOT NULL,
    x           INTEGER NOT NULL,
    y           INTEGER NOT NULL,
    UNIQUE (world_id, data_id)
);
"""

_CREATE_IDX_VILLAGES_WORLD = """
CREATE INDEX IF NOT EXISTS idx_villages_world ON villages(world_id);
"""


def _now_iso() -> str:
    """Devuelve la fecha/hora actual en ISO-8601 UTC."""
    return datetime.now(timezone.utc).isoformat()


def _row_to_world(row: aiosqlite.Row) -> World:
    """Convierte una fila de 'worlds' en una entidad World."""
    return World(
        id=row["id"],
        server=row["server"],
        tribe=Tribe(row["tribe"]),
    )


class AccountSQLiteAdapter(DbPort):
    """
    Implementación de DbPort sobre SQLite + aiosqlite.

    Recibe una conexión aiosqlite ya abierta (con WAL activado) desde el lifespan
    de la aplicación. No abre ni cierra la conexión — eso es responsabilidad del
    lifespan.
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    # ------------------------------------------------------------------
    # Inicialización del esquema
    # ------------------------------------------------------------------

    async def ensure_tables(self) -> None:
        """
        Crea las tablas accounts, worlds y villages si no existen.
        Activa PRAGMA foreign_keys=ON para que ON DELETE CASCADE funcione.
        Idempotente: se puede llamar varias veces sin efecto adverso.
        """
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute(_CREATE_ACCOUNTS)
        await self._conn.execute(_CREATE_UNIQUE_IDX_ACCOUNTS_EMAIL)
        await self._conn.execute(_CREATE_WORLDS)
        await self._conn.execute(_CREATE_IDX_WORLDS_ACCOUNT)
        await self._conn.execute(_CREATE_VILLAGES)
        await self._conn.execute(_CREATE_IDX_VILLAGES_WORLD)
        await self._conn.commit()

    # ------------------------------------------------------------------
    # Cuentas
    # ------------------------------------------------------------------

    async def save_account(self, account: Account, password_cifrada: bytes) -> Account:
        """
        Inserta una cuenta nueva en la BD.
        La contraseña se almacena como BLOB (token Fernet ya cifrado).
        Devuelve la cuenta con id asignado por la BD.

        Raises:
            DuplicateAccountError: si el email ya existe (UNIQUE constraint).
        """
        now = _now_iso()
        try:
            cursor = await self._conn.execute(
                """
                INSERT INTO accounts (email, username, password, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (account.email, account.username, password_cifrada, now, now),
            )
            await self._conn.commit()
        except aiosqlite.IntegrityError:
            raise DuplicateAccountError(account.email)

        new_id = cursor.lastrowid
        return Account(
            id=new_id,
            email=account.email,
            username=account.username,
            password=account.password,  # str descifrado en memoria
            worlds=[],
        )

    async def get_account(self, account_id: int) -> Optional[Account]:
        """Devuelve una cuenta con sus mundos cargados, o None si no existe."""
        cursor = await self._conn.execute(
            "SELECT id, email, username, password, created_at, updated_at "
            "FROM accounts WHERE id = ?",
            (account_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        worlds = await self.list_worlds(account_id)
        return Account(
            id=row["id"],
            email=row["email"],
            username=row["username"],
            # La contraseña en BD es bytes cifrados; al cargar en memoria devolvemos
            # un placeholder vacío. El login la descifra cuando la necesita.
            password="",
            worlds=worlds,
        )

    async def get_account_by_email(self, email: str) -> Optional[Account]:
        """Devuelve una cuenta por email (ya normalizado a lower+strip), o None."""
        cursor = await self._conn.execute(
            "SELECT id, email, username, password, created_at, updated_at "
            "FROM accounts WHERE email = ?",
            (email,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        worlds = await self.list_worlds(row["id"])
        return Account(
            id=row["id"],
            email=row["email"],
            username=row["username"],
            password="",
            worlds=worlds,
        )

    async def list_accounts(self) -> List[Account]:
        """
        Devuelve todas las cuentas con sus mundos.
        Nota RT-03: genera N+1 queries. Aceptado con la escala actual (1-10 cuentas).
        """
        cursor = await self._conn.execute(
            "SELECT id, email, username, password, created_at, updated_at "
            "FROM accounts ORDER BY id"
        )
        rows = await cursor.fetchall()
        accounts = []
        for row in rows:
            worlds = await self.list_worlds(row["id"])
            accounts.append(Account(
                id=row["id"],
                email=row["email"],
                username=row["username"],
                password="",
                worlds=worlds,
            ))
        return accounts

    async def update_account(
        self,
        account_id: int,
        email: str,
        username: str,
        password_cifrada: Optional[bytes],
    ) -> Account:
        """
        Actualiza email, username y opcionalmente la contraseña de una cuenta.
        Si password_cifrada es None, la contraseña almacenada NO cambia (RN-11).
        Devuelve la cuenta actualizada con worlds cargados.

        Raises:
            DuplicateAccountError: si el nuevo email ya pertenece a otra cuenta.
        """
        now = _now_iso()
        try:
            if password_cifrada is not None:
                await self._conn.execute(
                    "UPDATE accounts SET email=?, username=?, password=?, updated_at=? "
                    "WHERE id=?",
                    (email, username, password_cifrada, now, account_id),
                )
            else:
                await self._conn.execute(
                    "UPDATE accounts SET email=?, username=?, updated_at=? "
                    "WHERE id=?",
                    (email, username, now, account_id),
                )
            await self._conn.commit()
        except aiosqlite.IntegrityError:
            raise DuplicateAccountError(email)

        # Cargar y devolver la cuenta actualizada
        return await self.get_account(account_id)

    async def delete_account(self, account_id: int) -> None:
        """
        Elimina una cuenta. FK ON DELETE CASCADE borra worlds y villages en cascada.
        """
        await self._conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        await self._conn.commit()

    # ------------------------------------------------------------------
    # Mundos
    # ------------------------------------------------------------------

    async def save_world(self, account_id: int, world: World) -> World:
        """
        Inserta un mundo nuevo para la cuenta indicada.
        Devuelve el mundo con id asignado por la BD.

        Raises:
            DuplicateWorldError: si (account_id, server) ya existe.
        """
        now = _now_iso()
        try:
            cursor = await self._conn.execute(
                """
                INSERT INTO worlds (account_id, server, tribe, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (account_id, world.server, world.tribe.value, now, now),
            )
            await self._conn.commit()
        except aiosqlite.IntegrityError:
            raise DuplicateWorldError(world.server)

        return World(
            id=cursor.lastrowid,
            server=world.server,
            tribe=world.tribe,
        )

    async def get_world(self, world_id: int) -> Optional[World]:
        """Devuelve un mundo por su ID global, o None."""
        cursor = await self._conn.execute(
            "SELECT id, account_id, server, tribe, created_at, updated_at "
            "FROM worlds WHERE id = ?",
            (world_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_world(row)

    async def get_world_by_account_and_server(
        self, account_id: int, server: str
    ) -> Optional[World]:
        """Devuelve el mundo de una cuenta con el server dado, o None."""
        cursor = await self._conn.execute(
            "SELECT id, account_id, server, tribe, created_at, updated_at "
            "FROM worlds WHERE account_id = ? AND server = ?",
            (account_id, server),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_world(row)

    async def list_worlds(self, account_id: int) -> List[World]:
        """Devuelve todos los mundos de una cuenta, ordenados por id."""
        cursor = await self._conn.execute(
            "SELECT id, account_id, server, tribe, created_at, updated_at "
            "FROM worlds WHERE account_id = ? ORDER BY id",
            (account_id,),
        )
        rows = await cursor.fetchall()
        return [_row_to_world(row) for row in rows]

    async def delete_world(self, world_id: int) -> None:
        """Elimina un mundo. FK ON DELETE CASCADE borra villages en cascada."""
        await self._conn.execute("DELETE FROM worlds WHERE id = ?", (world_id,))
        await self._conn.commit()
