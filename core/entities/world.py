"""
Entidad World — representa un mundo (servidor) de Travian en el que juega una cuenta.
"""
import re
from dataclasses import dataclass, field

from core.entities.tribe import Tribe
from core.entities.village import Village

_SERVER_SPEED_RE = re.compile(r'\.x(\d+)\.', re.IGNORECASE)


@dataclass
class World:
    id: int
    server: str      # URL base del servidor, ej: "https://ts1.x1.international.travian.com/"
    tribe: Tribe
    villages: list[Village] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.server = self.server.strip().rstrip("/") + "/"

    @property
    def server_speed(self) -> float:
        """Extrae la velocidad del servidor del dominio (x1, x3, x5...). Default 1.0."""
        m = _SERVER_SPEED_RE.search(self.server or "")
        return float(m.group(1)) if m else 1.0
