"""
Entidad Village — representa una aldea de Travian perteneciente a un mundo.
"""
from dataclasses import dataclass


@dataclass
class Village:
    id: int
    world_id: int
    game_id: int   # ID interno de Travian (usado en URLs: gid=N)
    name: str
    x: int         # Coordenada X en el mapa
    y: int         # Coordenada Y en el mapa
