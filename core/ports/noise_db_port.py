"""
Puerto de acceso a BD para el subsistema de Ruido Humano de Navegación.

ABC NoiseDbPort — contrato que el adaptador SQLite debe implementar.
Spec human-sessions.md §7 (sección v2.2).
Spec noise-path-wizard.md §7.6 (ampliación: villages + path failures).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from core.entities.noise import (
    NavigationPath,
    NavigationStep,
    NoiseConfig,
    NoiseDestination,
    NavigationOrigin,
)


class NoiseDbPort(ABC):
    """Contrato de acceso a BD para destinos, rutas y configuración de ruido."""

    # ------------------------------------------------------------------
    # Configuración de ruido
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_or_create_noise_config(self, world_id: int) -> NoiseConfig:
        """
        Devuelve la configuración de ruido del mundo.
        Si no existe fila, la crea con los valores por defecto y la devuelve.
        """

    @abstractmethod
    async def update_noise_config(self, config: NoiseConfig) -> NoiseConfig:
        """
        PATCH parcial de la configuración de ruido.
        Solo actualiza los campos presentes en config; el resto conserva su valor en BD.
        Devuelve el estado completo de la config tras la operación.
        """

    # ------------------------------------------------------------------
    # Destinos
    # ------------------------------------------------------------------

    @abstractmethod
    async def list_destinations(
        self,
        world_id: int,
        category_slug: str | None = None,
        include_dead: bool = False,
        include_unsafe: bool = False,
    ) -> list[NoiseDestination]:
        """
        Lista destinos del mundo, con filtros opcionales.

        Por defecto excluye muertos (is_dead=True) y no seguros (is_safe=False).
        category_slug: filtrar por slug de RouteCategory (antes era NoiseCategory enum).
        """

    @abstractmethod
    async def get_destination(self, dest_id: int) -> NoiseDestination | None:
        """Devuelve el destino por ID. None si no existe."""

    @abstractmethod
    async def create_destination(
        self,
        world_id: int,
        url_pattern: str,
        label: str,
        category_slug: str = "uncategorized",
        frequency_weight: float = 1.0,
        is_safe: bool = True,
        template_id: int | None = None,
    ) -> NoiseDestination:
        """
        Crea un nuevo destino de navegación de ruido.

        Valida:
          - url_pattern: solo http/https si absoluta; o ruta relativa que empiece por '/';
            sin javascript:/data:/file:, sin protocol-relative (//...), sin control chars.
          - El dominio de la URL debe pertenecer al world_server del mundo.
          - frequency_weight > 0.
          - UNIQUE (world_id, url_pattern): si ya existe, lanza ValueError.

        template_id (opcional, default None): FK a route_templates.id para rastrear
          el origen del clon (M-RT01). Retrocompatible: los call-sites existentes
          que no lo pasan reciben None y el comportamiento no cambia.

        Lanza ValueError con mensaje descriptivo en caso de validación fallida.

        Spec route-templates-developer-portal.md §14 Paso 4.
        """

    @abstractmethod
    async def find_destination_by_url(
        self, world_id: int, url_pattern: str
    ) -> NoiseDestination | None:
        """
        Devuelve el primer NoiseDestination de ese mundo con esa url_pattern,
        o None si no existe.

        Usado para detectar colisiones UNIQUE(world_id, url_pattern) antes de
        clonar una plantilla (RN-RT05, §9.1).

        Spec route-templates-developer-portal.md §14 Paso 4.
        """

    @abstractmethod
    async def find_destination_by_template(
        self, world_id: int, template_id: int
    ) -> NoiseDestination | None:
        """
        Devuelve el NoiseDestination de ese mundo cuyo template_id coincide,
        o None si no existe.

        Usado por EP-RT09 (sync) para localizar la instancia a re-sincronizar (§9.2).

        Spec route-templates-developer-portal.md §14 Paso 4.
        """

    @abstractmethod
    async def update_destination(
        self,
        dest_id: int,
        label: str | None = None,
        frequency_weight: float | None = None,
        is_safe: bool | None = None,
        category_slug: str | None = None,
    ) -> NoiseDestination:
        """
        PATCH parcial de un destino.
        url_pattern NO se puede cambiar.
        category_slug SÍ se puede cambiar (spec route-categories-dynamic.md RN-CAT11).
        Lanza ValueError si dest_id no existe.
        """

    @abstractmethod
    async def delete_destination(self, dest_id: int) -> None:
        """
        Borra el destino y en cascada sus paths y steps (via FK CASCADE).
        Idempotente: no lanza si el dest no existe.
        """

    @abstractmethod
    async def mark_destination_dead(self, dest_id: int) -> None:
        """Marca el destino como muerto (is_dead=True). Idempotente."""

    @abstractmethod
    async def bump_destination_failures(self, dest_id: int) -> int:
        """
        Incrementa consecutive_failures_count en 1.
        Devuelve el nuevo valor del contador.
        """

    @abstractmethod
    async def reset_destination_failures(self, dest_id: int) -> None:
        """Resetea consecutive_failures_count a 0. Idempotente."""

    @abstractmethod
    async def touch_last_used_at(self, dest_id: int, now: datetime) -> None:
        """
        Actualiza last_used_at del destino a now.
        Idempotente y no lanza si el destino no existe.
        """

    @abstractmethod
    async def pick_random_safe_destination(
        self, world_id: int
    ) -> NoiseDestination | None:
        """
        Selecciona aleatoriamente un destino seguro y activo,
        ponderado por frequency_weight.

        Excluye is_dead=True y is_safe=False.
        Devuelve None si no hay destinos válidos.
        """

    # ------------------------------------------------------------------
    # Rutas (NavigationPath con pasos anidados)
    # ------------------------------------------------------------------

    @abstractmethod
    async def list_paths(self, dest_id: int) -> list[NavigationPath]:
        """
        Lista todas las rutas del destino, con sus steps anidados
        ordenados por step_order ASC.
        """

    @abstractmethod
    async def get_path(self, path_id: int) -> NavigationPath | None:
        """Devuelve la ruta con sus steps. None si no existe."""

    @abstractmethod
    async def create_path(
        self,
        dest_id: int,
        origin: NavigationOrigin,
        label: str,
        steps: list[NavigationStep],
    ) -> NavigationPath:
        """
        Crea una nueva ruta con sus pasos.
        steps no puede estar vacío (al menos 1 paso).
        Lanza ValueError si dest_id no existe o steps está vacío.
        """

    @abstractmethod
    async def update_path(
        self,
        path_id: int,
        label: str | None = None,
        is_active: bool | None = None,
        steps: list[NavigationStep] | None = None,
    ) -> NavigationPath:
        """
        Actualización híbrida de una ruta:
          - label / is_active: PATCH parcial (solo si se pasan).
          - steps: reemplazo ATÓMICO si se pasa (borra los anteriores e inserta los nuevos).
            Si steps=None  → conserva los steps existentes.
            Si steps=[]    → lanza ValueError (una ruta sin steps no es válida).
            Si steps=[...] → reemplaza atómicamente.

        Lanza ValueError si path_id no existe.
        """

    @abstractmethod
    async def delete_path(self, path_id: int) -> None:
        """
        Borra la ruta y en cascada sus steps.
        Idempotente: no lanza si el path no existe.
        """

    # ------------------------------------------------------------------
    # Path failures (spec noise-path-wizard.md §7.6 + RN-NP07)
    # ------------------------------------------------------------------

    @abstractmethod
    async def mark_path_dead(self, path_id: int) -> None:
        """
        Marca la ruta como muerta (is_dead=True). Idempotente.
        Llamar cuando consecutive_failures_count >= NOISE_PATH_DEAD_THRESHOLD.
        Spec noise-path-wizard.md RN-NP07, CA-NP31.
        """

    @abstractmethod
    async def increment_path_failures(self, path_id: int) -> int:
        """
        Incrementa consecutive_failures_count en 1.
        Devuelve el nuevo valor del contador.
        Spec noise-path-wizard.md RN-NP07, CA-NP30.
        """

    @abstractmethod
    async def reset_path_failures(self, path_id: int) -> None:
        """
        Resetea consecutive_failures_count a 0. Idempotente.
        Llamar cuando un paso CLICK tiene éxito.
        Spec noise-path-wizard.md RN-NP07, CA-NP32.
        """

    # ------------------------------------------------------------------
    # Villages (spec noise-path-wizard.md §7.6 — Opción A)
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_villages_for_world(self, world_id: int) -> list[Any]:
        """
        Devuelve todas las aldeas de la tabla villages para el mundo dado.
        Tipo de retorno: list[Village] (tipado como list[Any] para evitar
        dependencia de Village en el puerto abstracto).

        Se usa para construir la lista de anclas por-aldea (EP-N12) y para
        validar origin=VILLAGE_<data_id> en create_path / update_path.
        Spec noise-path-wizard.md §7.6, RN-NP02, EC-NP06.
        """

    @abstractmethod
    async def upsert_village(self, village: Any) -> Any:
        """
        UPSERT de una aldea en la tabla villages.
        Tipo de parámetro/retorno: Village (tipado como Any para evitar
        dependencia circular en el puerto abstracto).

        Usada por el parser del village-switcher tras cada refresh (EP-N13).
        Si la aldea ya existe (UNIQUE world_id+data_id), actualiza name, x, y.
        No borra aldeas que ya no aparecen (RN-NP03 — anti-detección).
        Spec noise-path-wizard.md §7.6, RN-NP03.
        """
