"""
Excepciones del dominio del bot de Travian.
Toda excepción propia del core hereda de TravianBotError.
"""


class TravianBotError(Exception):
    """Base de todas las excepciones del dominio."""


class AccountNotFoundError(TravianBotError):
    def __init__(self, account_id: int) -> None:
        super().__init__(f"Cuenta {account_id} no encontrada")
        self.account_id = account_id


class DuplicateAccountError(TravianBotError):
    def __init__(self, username: str) -> None:
        super().__init__(f"Ya existe una cuenta con el username '{username}'")
        self.username = username


class WorldNotFoundError(TravianBotError):
    def __init__(self, world_id: int) -> None:
        super().__init__(f"Mundo {world_id} no encontrado")
        self.world_id = world_id


class SessionNotActiveError(TravianBotError):
    def __init__(self) -> None:
        super().__init__("No hay sesión activa — ejecuta login primero")


class InvalidCredentialsError(TravianBotError):
    def __init__(self, username: str) -> None:
        super().__init__(f"Credenciales incorrectas para '{username}'")
        self.username = username


class VillageNotFoundError(TravianBotError):
    def __init__(self, village_id: int) -> None:
        super().__init__(f"Aldea {village_id} no encontrada")
        self.village_id = village_id


class FarmListNotFoundError(TravianBotError):
    def __init__(self, farm_list_id: int) -> None:
        super().__init__(f"Lista de vacas {farm_list_id} no encontrada")
        self.farm_list_id = farm_list_id


# Las siguientes se incluyen para completitud del dominio; se usarán en features posteriores:
class LoginError(TravianBotError):
    """Error genérico durante el proceso de login en Travian."""


class BrowserError(TravianBotError):
    """Error en la capa de automatización del navegador."""


class DatabaseError(TravianBotError):
    """Error al acceder a la base de datos local."""
