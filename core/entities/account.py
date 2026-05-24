"""
Entidad Account — representa una cuenta de Travian gestionada por el bot.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Account:
    """Cuenta de Travian con sus credenciales y estado."""

    id: Optional[int]
    username: str
    password: str
    server_url: str
    active: bool = True

    def __post_init__(self) -> None:
        if not self.username:
            raise ValueError("El nombre de usuario no puede estar vacío.")
        if not self.server_url:
            raise ValueError("La URL del servidor no puede estar vacía.")
