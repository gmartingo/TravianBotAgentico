"""
Entidad Account — representa una cuenta de Travian gestionada por el bot.
Solo contiene credenciales y la lista de mundos en los que participa.
"""
from dataclasses import dataclass, field
from typing import Optional

from core.entities.world import World


@dataclass
class Account:
    id: Optional[int]
    username: str
    password: str
    worlds: list[World] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.username:
            raise ValueError("El nombre de usuario no puede estar vacío.")
