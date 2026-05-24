"""
Casos de uso de login y logout.

LoginUseCase — orquesta la apertura de una sesión autenticada:
  1. Recupera la cuenta de la BD.
  2. Localiza el mundo solicitado dentro de la cuenta.
  3. Delega la apertura de sesión en WorldRuntimePort.

LogoutUseCase — cierra la sesión activa para un mundo dado.
"""
from dataclasses import dataclass

from core.ports.db_port import DbPort
from core.ports.world_runtime_port import WorldRuntimePort
from core.entities.account import Account
from core.entities.world import World
from core.exceptions import AccountNotFoundError, WorldNotFoundError


@dataclass
class LoginUseCase:
    registry: WorldRuntimePort
    db: DbPort

    async def execute(self, account_id: int, world_id: int) -> bool:
        account = await self.db.get_account(account_id)
        if account is None:
            raise AccountNotFoundError(account_id)
        world = self._find_world(account, world_id)
        return await self.registry.login(account, world)

    def _find_world(self, account: Account, world_id: int) -> World:
        for world in account.worlds:
            if world.id == world_id:
                return world
        raise WorldNotFoundError(world_id)


@dataclass
class LogoutUseCase:
    registry: WorldRuntimePort

    async def execute(self, world_id: int) -> None:
        await self.registry.logout(world_id)
