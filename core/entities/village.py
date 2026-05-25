"""
Entidad Village — representa una aldea de Travian perteneciente a un mundo.
"""
from dataclasses import dataclass


@dataclass
class Village:
    id: int
    world_id: int
    data_id: int   # ID de aldea en Travian (atributo HTML data-did; en URLs: newdid=N). NO confundir con gid, que es el tipo de edificio.
    name: str
    x: int         # Coordenada X en el mapa
    y: int         # Coordenada Y en el mapa
