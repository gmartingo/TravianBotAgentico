"""
Puerto (contrato) para la capa de persistencia.
El core solo conoce esta interfaz; nunca importa SQLite directamente.
"""
from abc import ABC, abstractmethod
from typing import List, Optional

from core.entities.account import Account
from core.entities.world import World


class DbPort(ABC):
    """Interfaz que debe implementar cualquier adaptador de base de datos."""

    # ------------------------------------------------------------------
    # Cuentas
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_account(self, account_id: int) -> Optional[Account]:
        """Devuelve una cuenta por su ID, o None si no existe."""

    @abstractmethod
    async def get_account_by_email(self, email: str) -> Optional[Account]:
        """Devuelve una cuenta por su email (ya normalizado), o None si no existe."""

    @abstractmethod
    async def list_accounts(self) -> List[Account]:
        """Devuelve todas las cuentas registradas."""

    @abstractmethod
    async def save_account(self, account: Account, password_cifrada: bytes) -> Account:
        """
        Persiste una cuenta nueva.
        Recibe la contraseña ya cifrada con Fernet para que el adaptador
        la almacene como BLOB sin requerir acceso al objeto Fernet.
        Devuelve la cuenta con ID asignado por la BD.
        """

    @abstractmethod
    async def update_account(
        self,
        account_id: int,
        email: str,
        username: str,
        password_cifrada: Optional[bytes],
    ) -> Account:
        """
        Actualiza los campos editables de una cuenta.
        Si password_cifrada es None, la contraseña almacenada NO cambia.
        Devuelve la cuenta actualizada (con worlds cargados).
        """

    @abstractmethod
    async def delete_account(self, account_id: int) -> None:
        """Elimina una cuenta por su ID. FK ON DELETE CASCADE borra worlds y villages."""

    # ------------------------------------------------------------------
    # Mundos
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_world(self, world_id: int) -> Optional[World]:
        """Devuelve un mundo por su ID global, o None."""

    @abstractmethod
    async def get_world_by_account_and_server(
        self, account_id: int, server: str
    ) -> Optional[World]:
        """Devuelve el mundo de una cuenta con el server dado, o None si no existe."""

    @abstractmethod
    async def list_worlds(self, account_id: int) -> List[World]:
        """Devuelve todos los mundos de una cuenta, ordenados por id."""

    @abstractmethod
    async def save_world(self, account_id: int, world: World) -> World:
        """Persiste un mundo nuevo. Devuelve el mundo con ID asignado por la BD."""

    @abstractmethod
    async def delete_world(self, world_id: int) -> None:
        """Elimina un mundo por su ID. FK ON DELETE CASCADE borra villages."""
