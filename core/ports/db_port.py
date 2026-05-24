"""
Puerto (contrato) para la capa de persistencia.
El core solo conoce esta interfaz; nunca importa SQLite directamente.
"""
from abc import ABC, abstractmethod
from typing import List, Optional

from core.entities.account import Account


class DbPort(ABC):
    """Interfaz que debe implementar cualquier adaptador de base de datos."""

    @abstractmethod
    async def get_account(self, account_id: int) -> Optional[Account]:
        """Devuelve una cuenta por su ID, o None si no existe."""

    @abstractmethod
    async def list_accounts(self) -> List[Account]:
        """Devuelve todas las cuentas registradas."""

    @abstractmethod
    async def save_account(self, account: Account) -> Account:
        """Persiste una cuenta (crea o actualiza). Devuelve la cuenta con ID asignado."""

    @abstractmethod
    async def delete_account(self, account_id: int) -> None:
        """Elimina una cuenta por su ID."""
