"""
Use cases de gestión de mundos: Add, Delete.

Reglas clave:
  - Sin lógica de presentación: no saben de HTTP, FastAPI ni Pydantic.
  - La normalización de server_url (trailing slash) la hace World.__post_init__.
  - La validación de tribu jugable llega validada desde Pydantic (PlayableTribe).
    El use case añade una defensa extra (ValueError) por "defense in depth".
  - La comprobación de sesión activa delega en WorldRuntimePort (opcional).
"""
from __future__ import annotations

import logging

from core.entities.tribe import PLAYABLE_TRIBES, Tribe
from core.entities.world import World
from core.exceptions import (
    AccountNotFoundError,
    ActiveSessionConflictError,
    DuplicateWorldError,
    WorldNotFoundError,
)
from core.ports.db_port import DbPort

logger = logging.getLogger(__name__)


class AddWorldUseCase:
    """
    Registra un mundo nuevo bajo una cuenta existente.
    Valida unicidad de (account_id, server_url) y normaliza la URL.
    """

    def __init__(self, db: DbPort) -> None:
        self._db = db

    async def execute(self, account_id: int, server_raw: str, tribe: Tribe) -> World:
        """
        Añade un mundo.

        Args:
            account_id:  ID de la cuenta propietaria.
            server_raw:  URL del servidor (se normaliza con trailing slash).
            tribe:       Tribu elegida (debe ser jugable).

        Returns:
            World persistido con id asignado.

        Raises:
            AccountNotFoundError: si la cuenta no existe.
            ValueError:           si la tribu no es jugable (defensa en profundidad;
                                  normalmente Pydantic lo atrapa antes en la capa API).
            DuplicateWorldError:  si (account_id, server) ya existe.
        """
        account = await self._db.get_account(account_id)
        if account is None:
            raise AccountNotFoundError(account_id)

        # Defensa en profundidad: Pydantic lo valida antes, pero el use case
        # no debe aceptar tribus NPC si alguien llama directamente.
        if tribe not in PLAYABLE_TRIBES:
            raise ValueError(f"Tribu '{tribe.value}' no es jugable")

        # World.__post_init__ normaliza el server (strip + rstrip("/") + "/").
        # Fuente única: usamos world.server para la búsqueda de unicidad → mismo
        # valor que se persiste (evita duplicados silenciosos por normalización divergente).
        # id=0 como placeholder; la BD asigna el real.
        world = World(id=0, server=server_raw, tribe=tribe)

        existing = await self._db.get_world_by_account_and_server(account_id, world.server)
        if existing is not None:
            raise DuplicateWorldError(world.server)

        saved = await self._db.save_world(account_id, world)
        return saved


class DeleteWorldUseCase:
    """
    Elimina un mundo de una cuenta.
    Verifica que el mundo pertenece a la cuenta y que no hay sesión activa.
    """

    def __init__(self, db: DbPort, runtime_port=None) -> None:
        self._db = db
        self._runtime_port = runtime_port

    async def execute(self, account_id: int, world_id: int) -> None:
        """
        Borra un mundo.

        Raises:
            AccountNotFoundError:       si la cuenta no existe.
            WorldNotFoundError:         si el mundo no existe o no pertenece a la cuenta.
            ActiveSessionConflictError: si hay sesión activa para el mundo.
        """
        account = await self._db.get_account(account_id)
        if account is None:
            raise AccountNotFoundError(account_id)

        world = await self._db.get_world(world_id)
        # Comprobamos que el mundo existe Y pertenece a esta cuenta.
        # Si no pertenece a la cuenta indicada devolvemos 404 (EC-12: no filtrar
        # por cuenta expone existencia de mundos ajenos — se oculta con 404).
        if world is None:
            raise WorldNotFoundError(world_id)

        # Verificar pertenencia: la BD almacena account_id en la fila, pero la
        # entidad World no lo expone. La comprobación se hace consultando los
        # mundos de la cuenta y verificando si world_id está entre ellos.
        worlds_of_account = await self._db.list_worlds(account_id)
        world_ids = {w.id for w in worlds_of_account}
        if world_id not in world_ids:
            raise WorldNotFoundError(world_id)

        if self._runtime_port is not None:
            active = self._runtime_port.is_active(world_id)
            if active:
                raise ActiveSessionConflictError(world_id)
        else:
            logger.warning(
                "WorldRuntimePort no disponible en app.state; asumiendo sesión "
                "inactiva para world_id=%s. Revisar cuando se implemente "
                "SessionRegistry.",
                world_id,
            )

        await self._db.delete_world(world_id)
