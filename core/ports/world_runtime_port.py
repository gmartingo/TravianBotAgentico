"""
Puerto WorldRuntimePort — contrato para el registro de sesiones activas del bot.
El core solo conoce esta interfaz; la implementación concreta (SessionRegistry)
vive en adapters y se define en la feature de orquestación.
"""
from abc import ABC, abstractmethod

from core.entities.account import Account
from core.entities.world import World


class WorldRuntimePort(ABC):
    """
    Puerto para el registro de sesiones activas del bot.
    Abstrae el ciclo de vida de los browsers por mundo.
    """

    @abstractmethod
    async def login(self, account: Account, world: World) -> bool:
        """
        Abre una sesión autenticada para account en world.
        Devuelve True si el login fue exitoso, False en caso contrario.
        Si ya existe una sesión para world.id, la cierra antes de abrir una nueva.
        """

    @abstractmethod
    async def logout(self, world_id: int) -> None:
        """
        Cierra la sesión activa para world_id.
        Idempotente: no lanza excepción si no hay sesión activa.
        """

    @abstractmethod
    def is_active(self, world_id: int) -> bool:
        """
        Devuelve True si hay una sesión activa para world_id.
        """
