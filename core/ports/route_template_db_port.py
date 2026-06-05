"""
Puerto de acceso a BD para el catálogo maestro de Plantillas de Rutas.

ABC RouteTemplateDbPort — contrato que el adaptador SQLite debe implementar.
Las plantillas son globales (sin world_id) y se clonan a mundos concretos
a través del subsistema de noise (NoiseDbPort.create_destination).

Spec route-templates-developer-portal.md §7.1, §8, §14 Paso 2.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.entities.noise import (
    NoiseCategory,
    RouteTemplate,
    RouteTemplatePath,
)


class RouteTemplateDbPort(ABC):
    """Contrato de acceso a BD para el catálogo maestro de plantillas de rutas."""

    # ------------------------------------------------------------------
    # CRUD de plantillas
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_template(self, template_id: int) -> RouteTemplate | None:
        """Devuelve la plantilla con sus paths y steps. None si no existe."""

    @abstractmethod
    async def get_template_by_slug(self, slug: str) -> RouteTemplate | None:
        """Devuelve la plantilla por slug. None si no existe."""

    @abstractmethod
    async def list_templates(
        self,
        category: NoiseCategory | None = None,
        include_paths: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RouteTemplate]:
        """
        Lista plantillas globales con filtros opcionales.

        - category: filtra por categoría si se pasa.
        - include_paths: si True, carga paths y steps de cada plantilla.
        - limit / offset: paginación (limit en [1, 500]).

        Si include_paths=False, las plantillas se devuelven con paths=[].
        """

    @abstractmethod
    async def create_template(self, template: RouteTemplate) -> RouteTemplate:
        """
        Crea una nueva plantilla global con sus paths y steps.

        Lanza ValueError si ya existe una plantilla con el mismo slug.
        La entidad RouteTemplate ya valida slug, label, navigation_weight y url_pattern
        en __post_init__; el puerto no duplica esas validaciones.
        """

    @abstractmethod
    async def update_template(
        self,
        template_id: int,
        label: str | None = None,
        navigation_weight: float | None = None,
        is_safe: bool | None = None,
        paths: list[RouteTemplatePath] | None = None,
    ) -> RouteTemplate:
        """
        PATCH parcial de una plantilla.

        slug, category y url_pattern son inmutables (RN-RT02, §10).
        Si se pasa paths (no None), es un reemplazo ATÓMICO de los paths+steps.
        Lanza ValueError si template_id no existe.
        """

    @abstractmethod
    async def delete_template(self, template_id: int) -> None:
        """
        Borra la plantilla y en cascada sus paths y steps.

        Los noise_destinations clonados de esta plantilla quedan con template_id=NULL
        (FK ON DELETE SET NULL en noise_destinations.template_id).
        Idempotente: no lanza si la plantilla no existe.
        """

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------

    @abstractmethod
    async def list_paths_for_template(self, template_id: int) -> list[RouteTemplatePath]:
        """
        Lista los paths de una plantilla con sus steps.
        Devuelve [] si la plantilla no existe.
        """

    # ------------------------------------------------------------------
    # Seed
    # ------------------------------------------------------------------

    @abstractmethod
    async def seed_templates(self, templates: list[RouteTemplate]) -> int:
        """
        Inserta cada plantilla de la lista si NO existe ya una con el mismo slug.
        Idempotente: las plantillas ya presentes se ignoran (no se modifican).
        Devuelve el número de plantillas insertadas efectivamente.

        Spec route-templates-developer-portal.md §9.4.
        """

    # ------------------------------------------------------------------
    # Conteo (para paths_count en EP-RT01)
    # ------------------------------------------------------------------

    @abstractmethod
    async def count_paths_for_template(self, template_id: int) -> int:
        """Devuelve el número de paths de una plantilla sin cargarlos. 0 si no existe."""
