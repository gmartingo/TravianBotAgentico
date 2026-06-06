"""
Entidad del dominio para el catálogo dinámico de categorías de rutas.

Las categorías son globales (no por mundo) y gestionadas por el usuario:
se pueden crear, renombrar, cambiar color y borrar inline desde el portal
de Route Templates.

Spec route-categories-dynamic.md §7.1, §1, §4 (RN-CAT01..RN-CAT12).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class RouteCategory:
    """
    Categoría de ruta de navegación de ruido.

    slug      — kebab-case, inmutable tras la creación (RN-CAT04). Es el
                identificador estable y la FK lógica desde route_templates y
                noise_destinations.
    label     — texto libre editable por el usuario (RN-CAT02).
    color     — hex CSS (#RGB o #RRGGBB) o None si sin color (RN-CAT09).
    is_default — True solo para 'uncategorized' (RN-CAT01). Solo lectura vía API.
    created_at — ISO 8601 UTC; None durante la construcción antes de persistir.
    """
    slug: str                    # kebab-case, inmutable
    label: str                   # editable libre
    color: str | None            # hex CSS o None
    is_default: bool
    created_at: datetime | None = None
