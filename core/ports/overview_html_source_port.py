"""
Puerto e enumeración de páginas de overview de Travian.

Define:
  - OverviewPage — enum de las 10 pestañas de /village/statistics
  - OverviewHtmlSourcePort — contrato abstracto para obtener el HTML de esas páginas

El port no conoce ni importa zendriver. Recibe y devuelve solo tipos básicos de Python
(str, int, enum), lo que permite sustituir la implementación concreta sin tocar el core.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum


class OverviewPage(Enum):
    """
    Identifica la pestaña de /village/statistics de Travian que se quiere leer.
    Cada valor mapea a una URL agregada (todas las aldeas en una sola página).

    La URL concreta la construye el LiveOverviewAdapter — el port no la expone.
    Convención de nombre de fixture: {page.value}.html
    """
    OVERVIEW             = "overview"              # /village/statistics/overview
    RESOURCES            = "resources"             # /village/statistics/resources
    RESOURCES_PRODUCTION = "resources_production"  # /village/statistics/resources/production
    RESOURCES_CAPACITY   = "resources_capacity"    # /village/statistics/resources/capacity
    CULTURE_POINTS       = "culturepoints"         # /village/statistics/culturepoints
    TROOPS_OWN           = "troops_own"            # /village/statistics/troops/own
    TROOPS_SUPPORT       = "troops_support"        # /village/statistics/troops/support
    TROOPS_SMITHY        = "troops_smithy"         # /village/statistics/troops/smithy
    TROOPS_HOSPITAL      = "troops_hospital"       # /village/statistics/troops/hospital
    TROOPS_TRAINING      = "troops_training"       # /village/statistics/troops/training


class OverviewHtmlSourcePort(ABC):
    """
    Puerto que abstrae la fuente de HTML de las páginas de overview de Travian.

    Permite testear parsers con ficheros HTML (FixtureOverviewAdapter) y
    navegar Travian en producción (LiveOverviewAdapter) sin cambiar el código
    de los parsers ni de los use cases.

    Contrato:
      - get_page_html devuelve siempre HTML como str no vacío.
      - Si no puede obtener el HTML, lanza una excepción del dominio
        (nunca devuelve None ni str vacío).
      - Es seguro llamarlo concurrentemente para el mismo world_id
        (los adaptadores son responsables del locking si lo necesitan).
    """

    @abstractmethod
    async def get_page_html(
        self,
        world_id: int,
        page: OverviewPage,
    ) -> str:
        """
        Devuelve el HTML crudo de la pestaña de statistics solicitada.

        Las páginas son agregadas: cada pestaña contiene TODAS las aldeas del jugador.
        No existe el concepto de "página por aldea" — el parser extrae las filas
        de cada aldea del HTML devuelto.

        Parámetros:
          world_id — ID del mundo (de la entidad World) que identifica la sesión.
          page     — Qué pestaña de /village/statistics se quiere (enum OverviewPage).

        Devuelve:
          str — HTML completo de la página. Nunca vacío, nunca None.

        Lanza:
          SessionNotActiveError        — si no hay browser/sesión activa (Live).
          OverviewPageNotLoadedError   — si la página no cargó en el timeout (Live).
          OverviewFixtureNotFoundError — si el fichero fixture no existe (Fixture).
        """

    @abstractmethod
    def invalidate_cache(self, world_id: int) -> None:
        """
        Invalida todas las entradas de caché para world_id.

        Seguro de llamar aunque no haya entradas (idempotente).
        En FixtureOverviewAdapter es no-op (no hay caché).
        """
