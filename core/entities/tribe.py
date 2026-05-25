"""
Entidad Tribe — enumeración de las tribus de Travian T4.5.

Las 5 primeras son tribus jugables por el usuario.
Las 4 añadidas en la feature kirilloid-tropas-scraper incluyen tribus NPC
(NATURE, NATARS) y las nuevas tribus jugables de expansiones (SPARTANS, VIKINGS).

PLAYABLE_TRIBES (frozenset) y Tribe.is_playable se usan en la feature
registro-cuentas-mundos para validar la tribu al crear un mundo.
"""
from __future__ import annotations

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

    @property
    def is_playable(self) -> bool:
        """True si la tribu puede ser jugada por un humano (no NPC)."""
        return self in PLAYABLE_TRIBES


# Definido después del enum para que pueda referenciar sus valores.
# Fuente de verdad de qué tribus son jugables — usada por Tribe.is_playable
# y por PlayableTribe enum en la capa API.
PLAYABLE_TRIBES: frozenset[Tribe] = frozenset({
    Tribe.ROMANS,
    Tribe.TEUTONS,
    Tribe.GAULS,
    Tribe.EGYPTIANS,
    Tribe.HUNS,
    Tribe.SPARTANS,
    Tribe.VIKINGS,
})
