"""
Use cases de gestión de cuentas: Create, Update, Delete.

Reglas clave:
  - Sin lógica de presentación: no saben de HTTP, FastAPI ni Pydantic.
  - El cifrado de contraseñas se delega en core/crypto.py (Fernet).
  - La persistencia se delega en DbPort (inyectado).
  - La comprobación de sesión activa se delega en WorldRuntimePort (opcional —
    degrada con seguridad si no está disponible: EC-15, RT-05).
  - La normalización de email tiene una ÚNICA fuente de verdad: Account.normalize_email
    (la usa Account.__post_init__ y la reutilizamos aquí para la búsqueda de unicidad).
"""
from __future__ import annotations

import logging
from typing import Optional

from cryptography.fernet import Fernet

from core.crypto import encrypt_password
from core.entities.account import Account
from core.exceptions import (
    AccountNotFoundError,
    ActiveSessionConflictError,
    DuplicateAccountError,
)
from core.ports.db_port import DbPort

logger = logging.getLogger(__name__)


class CreateAccountUseCase:
    """
    Registra una cuenta nueva: valida unicidad de email, cifra la contraseña
    y persiste en la BD.
    """

    def __init__(self, db: DbPort, fernet: Fernet) -> None:
        self._db = db
        self._fernet = fernet

    async def execute(self, email: str, username: str, password_plain: str) -> Account:
        """
        Crea una cuenta.

        Args:
            email:          Dirección de email del lobby (se normaliza a lower+strip).
            username:       Nombre visible (no debe ser único).
            password_plain: Contraseña en claro (se cifra antes de persistir).

        Returns:
            Account con id asignado y worlds=[].

        Raises:
            DuplicateAccountError: si el email ya está registrado.
        """
        # La entidad normaliza el email en __post_init__ (fuente única de verdad).
        # Usamos account.email para la búsqueda de unicidad → mismo valor que se persiste.
        account = Account(id=None, email=email, username=username, password=password_plain)
        existing = await self._db.get_account_by_email(account.email)
        if existing is not None:
            raise DuplicateAccountError(account.email)

        password_cifrada = encrypt_password(self._fernet, password_plain)
        # El adaptador recibe la contraseña ya cifrada para almacenarla como BLOB
        saved = await self._db.save_account(account, password_cifrada)
        return saved


class UpdateAccountUseCase:
    """
    Actualiza los campos editables de una cuenta (email, username, password).
    Si password es None, la contraseña almacenada no cambia (RN-11).
    """

    def __init__(self, db: DbPort, fernet: Fernet) -> None:
        self._db = db
        self._fernet = fernet

    async def execute(
        self,
        account_id: int,
        email: str,
        username: str,
        password_plain: Optional[str] = None,
    ) -> Account:
        """
        Actualiza una cuenta.

        Args:
            account_id:     ID de la cuenta a actualizar.
            email:          Nuevo email (se normaliza).
            username:       Nuevo nombre visible.
            password_plain: Nueva contraseña en claro, o None para no cambiarla.

        Returns:
            Account actualizado con worlds cargados.

        Raises:
            AccountNotFoundError:  si la cuenta no existe.
            DuplicateAccountError: si el nuevo email ya pertenece a otra cuenta.
        """
        existing = await self._db.get_account(account_id)
        if existing is None:
            raise AccountNotFoundError(account_id)

        email = Account.normalize_email(email)
        if email != existing.email:
            duplicate = await self._db.get_account_by_email(email)
            if duplicate is not None and duplicate.id != account_id:
                raise DuplicateAccountError(email)

        password_cifrada: Optional[bytes] = None
        if password_plain is not None:
            password_cifrada = encrypt_password(self._fernet, password_plain)

        updated = await self._db.update_account(account_id, email, username, password_cifrada)
        return updated


class DeleteAccountUseCase:
    """
    Borra una cuenta y todos sus mundos/aldeas en cascada.
    Verifica que no haya sesiones activas antes de borrar.
    Si WorldRuntimePort no está disponible, degrada con seguridad (EC-15, RT-05).
    """

    def __init__(self, db: DbPort, runtime_port=None) -> None:
        self._db = db
        self._runtime_port = runtime_port

    async def execute(self, account_id: int) -> None:
        """
        Borra una cuenta.

        Raises:
            AccountNotFoundError:       si la cuenta no existe.
            ActiveSessionConflictError: si algún mundo tiene sesión activa.
        """
        account = await self._db.get_account(account_id)
        if account is None:
            raise AccountNotFoundError(account_id)

        worlds = await self._db.list_worlds(account_id)
        for world in worlds:
            if self._runtime_port is not None:
                active = self._runtime_port.is_active(world.id)
                if active:
                    raise ActiveSessionConflictError(world.id)
            else:
                logger.warning(
                    "WorldRuntimePort no disponible en app.state; asumiendo sesión "
                    "inactiva para world_id=%s. Revisar cuando se implemente "
                    "SessionRegistry.",
                    world.id,
                )

        await self._db.delete_account(account_id)
