"""
Casos de uso de login y logout.

LoginUseCase — orquesta la apertura de una sesión autenticada:
  1. Recupera la cuenta de la BD.
  2. Obtiene el token Fernet cifrado de la BD (get_account_password_cipher).
  3. Descifra la contraseña con el objeto Fernet inyectado.
  4. Localiza el mundo solicitado dentro de la cuenta.
  5. Delega la apertura de sesión en WorldRuntimePort con la contraseña en claro.

LogoutUseCase — cierra la sesión activa para un mundo dado.

Seguridad (condiciones del guardian-antideteccion):
  - Ningún logger.* loguea cipher, fernet, ni account.password.
  - Los únicos datos identificativos en logs son account_id y account.username.
  - El except InvalidToken y el caso cipher=None loguean solo account_id, nivel error.
  - account.password se asigna justo antes de pasar a registry.login(); ventana mínima.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken

from core.crypto import decrypt_password
from core.entities.account import Account
from core.entities.world import World
from core.exceptions import AccountNotFoundError, FernetDecryptionError, LoginFailedError, WorldNotFoundError
from core.ports.db_port import DbPort
from core.ports.world_runtime_port import WorldRuntimePort

logger = logging.getLogger(__name__)


@dataclass
class LoginUseCase:
    registry: WorldRuntimePort
    db: DbPort
    fernet: Fernet                  # inyectado desde el endpoint via get_fernet

    async def execute(self, account_id: int, world_id: int) -> bool:
        # 1. Verificar que la cuenta existe
        account = await self.db.get_account(account_id)
        if account is None:
            raise AccountNotFoundError(account_id)

        # 2. Obtener token cifrado — si None, la cuenta no existe o BD está corrupta.
        #    La cuenta existía en el paso anterior (NOT NULL en DDL), pero se trata
        #    igual que un login fallido (401) para no lanzar 500 nunca.
        cipher = await self.db.get_account_password_cipher(account_id)
        if cipher is None:
            # Situación imposible si la BD no está corrupta: la cuenta existía en el paso 1.
            logger.error(
                "Cipher nulo para account_id=%s — posible corrupción de BD",
                account_id,
            )
            raise LoginFailedError(account.username)

        # 3. Descifrar — la contraseña en claro existe solo en este scope.
        #    PROHIBIDO: loguear cipher, fernet, ni account.password.
        try:
            account.password = decrypt_password(self.fernet, cipher)
        except InvalidToken:
            # La clave Fernet activa no coincide con la usada al cifrar.
            # Es un error de configuración (no transitorio): se lanza
            # FernetDecryptionError para que el WorldAgent pueda distinguirlo
            # de un error de red y NO aplique backoff (EC-HS15, RN-HS13).
            # No loguear el token ni la clave. Solo account_id.
            logger.error(
                "InvalidToken al descifrar contraseña para account_id=%s "
                "— la clave Fernet puede haber rotado",
                account_id,
            )
            raise FernetDecryptionError(account_id)

        # 4. Localizar el mundo dentro de la cuenta
        world = self._find_world(account, world_id)

        # 5. Delegar en el registry → login.py → human_type con la contraseña real
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
