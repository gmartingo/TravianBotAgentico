"""
Puerto de acceso a BD para el catálogo dinámico de Categorías de Rutas.

ABC RouteCategoryDbPort — contrato que el adaptador SQLite debe implementar.
Las categorías son globales (sin world_id): todas las plantillas y destinos
de cualquier mundo comparten el mismo catálogo.

Spec route-categories-dynamic.md §7.1, §3 (T8), §14 Pasos 3 y 5.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


# Centinela para distinguir "color ausente del body" de "color=null explícito"
# en el método update_category. Ver C-04 del spec §8.0.
class _UnsetType:
    """Centinela: campo no enviado en el PATCH body."""
    _instance: "_UnsetType | None" = None

    def __new__(cls) -> "_UnsetType":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "UNSET"


UNSET: Any = _UnsetType()


from core.entities.route_category import RouteCategory  # noqa: E402


class RouteCategoryDbPort(ABC):
    """
    Contrato de acceso a BD para el catálogo de categorías de rutas.

    Separado de NoiseDbPort y RouteTemplateDbPort: las categorías tienen su
    propio ciclo de vida y no son por-mundo (T8 del spec).
    """

    @abstractmethod
    async def list_categories(self) -> list[RouteCategory]:
        """
        Lista todas las categorías, ordenadas por is_default DESC, created_at ASC.
        La categoría default ('uncategorized') siempre aparece primera.
        """

    @abstractmethod
    async def get_category(self, slug: str) -> RouteCategory | None:
        """Devuelve la categoría por slug. None si no existe."""

    @abstractmethod
    async def get_category_by_label_lower(self, label_lower: str) -> RouteCategory | None:
        """
        Devuelve la categoría cuyo label_lower coincide (unicidad CI).
        None si no existe.
        """

    @abstractmethod
    async def create_category(
        self,
        slug: str,
        label: str,
        label_lower: str,
        color: str | None,
        is_default: bool,
    ) -> RouteCategory:
        """
        Inserta una nueva categoría y la devuelve con el id y created_at asignados.
        Lanza ValueError si hay colisión de slug o label_lower (UNIQUE constraint).
        """

    @abstractmethod
    async def update_category(
        self,
        slug: str,
        label: str | None = None,
        label_lower: str | None = None,
        color: "_UnsetType | str | None" = UNSET,
    ) -> RouteCategory:
        """
        PATCH parcial de una categoría.

        - label / label_lower: se actualizan si no son None.
        - color: semántica de centinela (C-04 del spec):
            * UNSET (default)  → conservar el valor actual de color.
            * None (explícito) → quitar el color (poner a null en BD).
            * str (hex)        → actualizar el color.

        Lanza ValueError si slug no existe.
        Lanza ValueError si el nuevo label_lower ya existe en otra categoría (CI).
        """

    @abstractmethod
    async def delete_category_and_reassign(self, slug: str) -> tuple[str, int]:
        """
        Borra una categoría y reasigna atómicamente todas sus plantillas y
        destinos a 'uncategorized'. La operación es transaccional (EC-CAT06/07).

        Devuelve (deleted_slug, reassigned_count) donde reassigned_count es el
        total de filas actualizadas en route_templates + noise_destinations.

        Lanza ValueError si el slug no existe.
        Lanza ValueError si la categoría es la default (is_default=True).
        """
