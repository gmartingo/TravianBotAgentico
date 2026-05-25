"""
Puerto de traducciones — interfaz del core.

El core usa esta interfaz para obtener textos localizados.
El adaptador concreto (JsonTranslationAdapter) decide la fuente (JSON, BD, etc.).
"""
from abc import ABC, abstractmethod

from core.entities.tribe import Tribe


class TranslationPort(ABC):
    """
    Puerto de traducciones. El core usa esta interfaz para obtener textos
    localizados. El adaptador concreto decide la fuente (JSON, BD, etc.).
    """

    @abstractmethod
    def get_building_name(self, gid: int, lang: str) -> str:
        """
        Devuelve el nombre del edificio con el gid dado en el idioma solicitado.
        Si la traducción falta para ese idioma, hace fallback a 'es'.
        Nunca lanza excepción por traducción faltante.
        Si el gid no existe en el catálogo, devuelve f"building_{gid}" como fallback.
        """

    @abstractmethod
    def get_all_buildings(self, lang: str) -> list[dict]:
        """
        Devuelve todos los edificios del catálogo con el idioma efectivamente servido
        por cada item.

        Cada elemento del resultado:
            {
                "gid": int,
                "alias": str,
                "lang_servido": str,   # idioma real usado (puede diferir de lang por fallback)
                "nombre": str
            }

        Fallback granular a 'es' por entrada. El router construye el campo `language`
        del response a partir de lang_servido + nombre.
        """

    @abstractmethod
    def get_troop_name(self, tribe: Tribe, ordinal: int, lang: str) -> str:
        """
        Devuelve el nombre de la tropa en la posición ordinal de la tribu dada.
        Fallback a 'es' si falta la traducción.
        Lanza TroopNotFoundError si el ordinal no existe para esa tribu.
        """

    @abstractmethod
    def get_troop_names_by_tribe(self, tribe: Tribe, lang: str) -> list[dict]:
        """
        Devuelve todas las tropas de una tribu con el idioma efectivamente servido
        por cada item.

        Cada elemento del resultado:
            {
                "ordinal": int,
                "key": str,
                "lang_servido": str,   # idioma real usado (puede diferir de lang por fallback)
                "nombre": str
            }

        Fallback granular a 'es' por entrada. El router construye el campo `language`
        del response a partir de lang_servido + nombre.
        Lanza TroopNotFoundError (con ordinal=None) si la tribu no tiene tropas
        definidas en el catálogo.
        """

    @abstractmethod
    def get_troop_all_langs_by_tribe(self, tribe: Tribe) -> list[dict]:
        """
        Devuelve todas las tropas de una tribu con TODOS los idiomas disponibles
        para cada tropa (todas las claves no vacías del catálogo).

        Cada elemento del resultado:
            {
                "ordinal": int,
                "key": str,
                "language": dict[str, str]   # {lang: nombre} para todos los idiomas no vacíos
            }

        A diferencia de get_troop_names_by_tribe, NO aplica fallback a 'es':
        simplemente incluye todos los pares (idioma, nombre) cuyo valor sea no vacío.
        Lanza TroopNotFoundError (ordinal=None) si la tribu no tiene tropas en el catálogo.
        """

    @abstractmethod
    def get_message(self, code: str, lang: str, **params) -> str:
        """
        Devuelve el mensaje de error para el code dado en el idioma solicitado.
        Interpola los params con .format(**params).
        Fallback a 'es' si falta la traducción en el idioma pedido.
        Si el code no existe en el catálogo, devuelve f"{code} {params}" como fallback.
        Nunca lanza excepción.
        """
