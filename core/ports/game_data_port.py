"""
Puerto de datos de juego — interfaz del core para stats de tropas, mejoras e iconos.

El core usa esta interfaz para acceder a datos numéricos de tropas (ataque, defensa,
velocidad, costes, etc.) extraídos de kirilloid.ru y persistidos en SQLite.
El adaptador concreto (GameDataSQLiteAdapter) resuelve las queries.

NOTA: Este puerto no extiende TranslationPort — son responsabilidades separadas.
TranslationPort es solo texto (nombres localizados).
GameDataPort es solo datos numéricos y metadatos (SRP, arquitectura hexagonal).
"""
from abc import ABC, abstractmethod

from core.entities.tribe import Tribe


class GameDataPort(ABC):
    """
    Puerto de datos de juego del core.
    Proporciona acceso a stats de tropas, tablas de mejoras de herrería
    y metadatos de iconos, independientemente de la fuente de persistencia.
    """

    @abstractmethod
    async def get_troop_stats(
        self,
        tribe: Tribe,
        ordinal: int,
        server_version: str = "1.45",
    ) -> dict | None:
        """
        Devuelve los stats base de una tropa, o None si no existe.

        El dict devuelto contiene las keys:
          ordinal, tribe, is_playable, attack, def_infantry, def_cavalry,
          speed, carry, cost_wood, cost_clay, cost_iron, cost_crop, cost_sum,
          upkeep, train_time_s, icon_id.

        Los stats opcionales (NULL en BD) se devuelven como None.
        """

    @abstractmethod
    async def get_all_troop_stats(
        self,
        tribe: Tribe,
        server_version: str = "1.45",
    ) -> list[dict]:
        """
        Devuelve todos los stats de una tribu ordenados por ordinal.
        Devuelve lista vacía si la tribu no tiene datos.
        """

    @abstractmethod
    async def get_troop_upgrades(
        self,
        tribe: Tribe,
        ordinal: int,
        server_version: str = "1.45",
    ) -> list[dict]:
        """
        Devuelve la tabla de mejoras de herrería de una tropa.

        Cada item del resultado:
          {level, stat_name, stat_value, cost_wood, cost_clay,
           cost_iron, cost_crop, cost_sum, upgrade_time_s}

        Devuelve lista vacía si no hay datos de mejora para esa tropa.
        """

    @abstractmethod
    async def upsert_troop_stats(self, stats: dict) -> None:
        """
        Inserta o actualiza los stats de una tropa (UPSERT idempotente).

        El dict stats debe incluir: server_version, tribe, ordinal y todos
        los campos de troop_stats. El adaptador rellena scraped_at con UTC ahora.
        """

    @abstractmethod
    async def upsert_troop_upgrade(self, upgrade: dict) -> None:
        """
        Inserta o actualiza una fila de la tabla de mejoras (UPSERT idempotente).

        El dict upgrade debe incluir: server_version, tribe, ordinal, level,
        stat_name, stat_value y los campos de coste/tiempo.
        """

    @abstractmethod
    async def upsert_icon_metadata(self, icon: dict) -> None:
        """
        Inserta o actualiza los metadatos de un icono (UPSERT idempotente).

        El dict icon debe incluir:
          icon_id, icon_type, tribe (o None), ordinal (o None),
          stat_name (o None), file_path, file_size_bytes, width_px, height_px.
        El adaptador rellena scraped_at con UTC ahora.
        """

    @abstractmethod
    async def get_icon_metadata(self, icon_id: str) -> dict | None:
        """
        Devuelve los metadatos de un icono por su icon_id, o None si no existe.
        """

    @abstractmethod
    async def list_icons(
        self,
        icon_type: str | None = None,
        tribe: str | None = None,
    ) -> list[dict]:
        """
        Devuelve la lista de metadatos de iconos.

        Filtros opcionales:
          icon_type: "troop" | "stat" | "upgrade" — filtra por tipo.
          tribe: valor de Tribe.value — solo tiene efecto con icon_type="troop".

        Si ningún icono cumple los filtros, devuelve lista vacía (nunca lanza excepción).
        """
