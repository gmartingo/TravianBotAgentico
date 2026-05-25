"""
Entidad Tribe — enumeración de las tribus de Travian T4.5.

Las 5 primeras son tribus jugables por el usuario.
Las 4 añadidas en la feature kirilloid-tropas-scraper incluyen tribus NPC
(NATURE, NATARS) y las nuevas tribus jugables de expansiones (SPARTANS, VIKINGS).
"""
from enum import Enum


class Tribe(Enum):
    ROMANS = "romans"
    TEUTONS = "teutons"
    GAULS = "gauls"
    EGYPTIANS = "egyptians"
    HUNS = "huns"
    # Tribus añadidas en la feature kirilloid-tropas-scraper (Fase 1)
    NATURE = "nature"      # NPC — is_playable=False
    NATARS = "natars"      # NPC — is_playable=False
    SPARTANS = "spartans"  # Jugable — expansión
    VIKINGS = "vikings"    # Jugable — expansión
