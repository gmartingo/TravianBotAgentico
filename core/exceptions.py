"""
Excepciones del dominio del bot de Travian.
Toda excepción propia del core hereda de TravianBotError.

Cada subclase concreta declara:
  - error_code: str  — código SCREAMING_SNAKE_CASE para lookup en catálogo de mensajes
  - params: dict     — valores para interpolar en la plantilla del catálogo

El mensaje humano de str(err) se mantiene en español para compatibilidad
con los tests existentes (T-3 del spec i18n-backend).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.entities.tribe import Tribe


class TravianBotError(Exception):
    """Base de todas las excepciones del dominio."""

    error_code: str = "TRAVIAN_BOT_ERROR"
    params: dict = {}


class AccountNotFoundError(TravianBotError):
    error_code = "ACCOUNT_NOT_FOUND"

    def __init__(self, account_id: int) -> None:
        super().__init__(f"Cuenta {account_id} no encontrada")
        self.account_id = account_id
        self.params = {"account_id": account_id}


class DuplicateAccountError(TravianBotError):
    error_code = "DUPLICATE_ACCOUNT"

    def __init__(self, username: str) -> None:
        super().__init__(f"Ya existe una cuenta con el username '{username}'")
        self.username = username
        self.params = {"username": username}


class WorldNotFoundError(TravianBotError):
    error_code = "WORLD_NOT_FOUND"

    def __init__(self, world_id: int) -> None:
        super().__init__(f"Mundo {world_id} no encontrado")
        self.world_id = world_id
        self.params = {"world_id": world_id}


class SessionNotActiveError(TravianBotError):
    error_code = "SESSION_NOT_ACTIVE"

    def __init__(self) -> None:
        super().__init__("No hay sesión activa — ejecuta login primero")
        self.params = {}


class InvalidCredentialsError(TravianBotError):
    error_code = "INVALID_CREDENTIALS"

    def __init__(self, username: str) -> None:
        super().__init__(f"Credenciales incorrectas para '{username}'")
        self.username = username
        self.params = {"username": username}


class VillageNotFoundError(TravianBotError):
    error_code = "VILLAGE_NOT_FOUND"

    def __init__(self, village_id: int) -> None:
        super().__init__(f"Aldea {village_id} no encontrada")
        self.village_id = village_id
        self.params = {"village_id": village_id}


class FarmListNotFoundError(TravianBotError):
    error_code = "FARM_LIST_NOT_FOUND"

    def __init__(self, farm_list_id: int) -> None:
        super().__init__(f"Lista de vacas {farm_list_id} no encontrada")
        self.farm_list_id = farm_list_id
        self.params = {"farm_list_id": farm_list_id}


# Las siguientes se incluyen para completitud del dominio; se usarán en features posteriores:
class LoginError(TravianBotError):
    """Error genérico durante el proceso de login en Travian."""

    error_code = "LOGIN_ERROR"

    def __init__(self, message: str = "") -> None:
        super().__init__(message or "Error durante el proceso de login en Travian")
        self.params = {}


class BrowserError(TravianBotError):
    """Error en la capa de automatización del navegador."""

    error_code = "BROWSER_ERROR"

    def __init__(self, message: str = "") -> None:
        super().__init__(message or "Error en la capa de automatización del navegador")
        self.params = {}


class DatabaseError(TravianBotError):
    """Error al acceder a la base de datos local."""

    error_code = "DATABASE_ERROR"

    def __init__(self, message: str = "") -> None:
        super().__init__(message or "Error al acceder a la base de datos local")
        self.params = {}


# --- Nuevas excepciones añadidas en la feature i18n-backend ---

class TroopNotFoundError(TravianBotError):
    error_code = "TROOP_NOT_FOUND"

    def __init__(self, tribe: "Tribe", ordinal: int | None = None) -> None:
        super().__init__(f"Tropa {ordinal} de {tribe.value} no encontrada")
        self.tribe = tribe
        self.ordinal = ordinal
        self.params = {"tribe": tribe.value, "ordinal": str(ordinal or "")}


class BuildingNotFoundError(TravianBotError):
    error_code = "BUILDING_NOT_FOUND"

    def __init__(self, gid: int) -> None:
        super().__init__(f"Edificio gid={gid} no encontrado")
        self.gid = gid
        self.params = {"gid": gid}
