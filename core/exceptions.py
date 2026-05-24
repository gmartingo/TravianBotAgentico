"""
Excepciones del dominio del bot de Travian.
Toda excepción propia del core hereda de TravianBotError.
"""


class TravianBotError(Exception):
    """Base de todas las excepciones del dominio."""


class LoginError(TravianBotError):
    """Error durante el proceso de login en Travian."""


class BrowserError(TravianBotError):
    """Error en la capa de automatización del navegador."""


class DatabaseError(TravianBotError):
    """Error al acceder a la base de datos local."""


class AccountNotFoundError(TravianBotError):
    """La cuenta solicitada no existe en la base de datos."""
