"""
Router FastAPI para el Catálogo Dinámico de Categorías de Rutas.

Endpoints (sin prefijo /api — el proxy de Vite lo retira):

  EP-CAT01  GET    /route-categories                    — listar categorías
  EP-CAT02  POST   /route-categories                    — crear categoría (201 + Location)
  EP-CAT03  GET    /route-categories/{slug}             — obtener categoría
  EP-CAT04  PATCH  /route-categories/{slug}             — actualizar label/color parcial
  EP-CAT05  DELETE /route-categories/{slug}             — borrar + reasignar a uncategorized

EP-CAT06 (GET /route-categories/{slug}/routes) queda FUERA DE ALCANCE v1 (C-08 del spec).

Sin Accept-Language: los labels son texto libre del usuario, no del catálogo de Travian (§8.1).
Sin autenticación: sistema single-tenant (§2 del spec).

Spec route-categories-dynamic.md §8 (EP-CAT01..EP-CAT05).
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Request, Response, status
from pydantic import BaseModel, Field, field_validator, model_validator

from adapters.db.route_category_sqlite_adapter import slugify, _ensure_unique_slug
from core.ports.route_category_db_port import UNSET

logger = logging.getLogger(__name__)

router = APIRouter(tags=["route-categories"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_cat_port(request: Request):
    """Extrae route_category_port del app.state."""
    port = getattr(request.app.state, "route_category_port", None)
    if port is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        )
    return port


async def _require_category(cat_port, slug: str):
    """404 si la categoría no existe."""
    cat = await cat_port.get_category(slug)
    if cat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Categoría no encontrada.",
        )
    return cat


# ---------------------------------------------------------------------------
# Modelos Pydantic — Requests
# ---------------------------------------------------------------------------

class CreateCategoryRequest(BaseModel):
    """EP-CAT02 body. El slug NO se acepta: se genera automáticamente (RN-CAT08)."""
    label: str = Field(..., min_length=1, max_length=100)
    color: Optional[str] = Field(
        default=None,
        pattern=r"^#[0-9A-Fa-f]{3,6}$",
        max_length=50,
    )

    @field_validator("label", mode="before")
    @classmethod
    def strip_label(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("label no puede ser solo espacios.")
        return v


class PatchCategoryRequest(BaseModel):
    """
    EP-CAT04 body. Al menos uno de los dos campos debe estar presente.

    Distinción ausente vs null en color (C-04 del spec):
      - color ausente del body  → conservar valor actual
      - color: null en el body  → quitar el color (null explícito)
    Pydantic v2: usar model_fields_set en el handler para distinguir los dos casos.
    """
    label: Optional[str] = Field(default=None, min_length=1, max_length=100)
    color: Optional[str] = Field(
        default=None,
        pattern=r"^#[0-9A-Fa-f]{3,6}$",
        max_length=50,
    )

    @field_validator("label", mode="before")
    @classmethod
    def strip_label(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("label no puede ser solo espacios.")
        return v

    @model_validator(mode="after")
    def at_least_one_field(self) -> "PatchCategoryRequest":
        if "label" not in self.model_fields_set and "color" not in self.model_fields_set:
            raise ValueError("El body debe contener al menos uno de: label, color.")
        return self


# ---------------------------------------------------------------------------
# Modelos Pydantic — Responses
# ---------------------------------------------------------------------------

class RouteCategoryResponse(BaseModel):
    """Respuesta de todos los endpoints EP-CAT01..EP-CAT05."""
    slug: str           # inmutable, kebab-case, generado automáticamente
    label: str          # editable
    color: Optional[str]  # hex #RRGGBB o null
    is_default: bool    # true solo para 'uncategorized'
    created_at: str     # ISO 8601 UTC


class DeleteCategoryResponse(BaseModel):
    """Respuesta de EP-CAT05 DELETE."""
    deleted_slug: str
    reassigned_count: int
    reassigned_to: str = "uncategorized"


# ---------------------------------------------------------------------------
# Helper de conversión entidad → response
# ---------------------------------------------------------------------------

def _cat_to_response(cat) -> RouteCategoryResponse:
    from datetime import datetime, timezone
    created_at = cat.created_at
    if created_at is None:
        created_at_str = datetime.now(timezone.utc).isoformat()
    elif isinstance(created_at, str):
        created_at_str = created_at
    else:
        created_at_str = created_at.isoformat()
    return RouteCategoryResponse(
        slug=cat.slug,
        label=cat.label,
        color=cat.color,
        is_default=cat.is_default,
        created_at=created_at_str,
    )


# ---------------------------------------------------------------------------
# EP-CAT01 — GET /route-categories
# ---------------------------------------------------------------------------

@router.get(
    "/route-categories",
    response_model=list[RouteCategoryResponse],
    summary="EP-CAT01 — Listar categorías de rutas",
)
async def list_categories(request: Request) -> list[RouteCategoryResponse]:
    """
    Lista todas las categorías del catálogo, ordenadas por is_default DESC, created_at ASC.
    La categoría 'uncategorized' siempre aparece primera.
    """
    cat_port = _get_cat_port(request)
    try:
        cats = await cat_port.list_categories()
    except Exception as exc:
        logger.exception("Error listando categorías")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        ) from exc
    return [_cat_to_response(c) for c in cats]


# ---------------------------------------------------------------------------
# EP-CAT02 — POST /route-categories
# ---------------------------------------------------------------------------

@router.post(
    "/route-categories",
    response_model=RouteCategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="EP-CAT02 — Crear categoría de ruta",
)
async def create_category(
    request: Request,
    response: Response,
    body: CreateCategoryRequest,
) -> RouteCategoryResponse:
    """
    Crea una nueva categoría. El slug se genera automáticamente desde el label (RN-CAT08).
    Unicidad CI: label.strip().lower() único (RN-CAT05).
    """
    cat_port = _get_cat_port(request)

    label = body.label.strip()
    label_lower = label.lower()

    # Verificar unicidad CI (EC-CAT02)
    existing = await cat_port.get_category_by_label_lower(label_lower)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una categoría con este nombre.",
        )

    # Generar slug único (RN-CAT08, EC-CAT04)
    base_slug = slugify(label)
    # Acceder a la conexión interna para usar _ensure_unique_slug
    conn = cat_port._conn
    slug = await _ensure_unique_slug(conn, base_slug)

    try:
        cat = await cat_port.create_category(
            slug=slug,
            label=label,
            label_lower=label_lower,
            color=body.color,
            is_default=False,
        )
    except ValueError as exc:
        # UNIQUE constraint en BD — puede ser colisión de slug (rara carrera)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una categoría con este nombre.",
        ) from exc
    except Exception as exc:
        logger.exception("Error creando categoría")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        ) from exc

    response.headers["Location"] = f"/route-categories/{cat.slug}"
    return _cat_to_response(cat)


# ---------------------------------------------------------------------------
# EP-CAT03 — GET /route-categories/{slug}
# ---------------------------------------------------------------------------

@router.get(
    "/route-categories/{slug}",
    response_model=RouteCategoryResponse,
    summary="EP-CAT03 — Obtener categoría por slug",
)
async def get_category(
    request: Request,
    slug: str = Path(..., min_length=1),
) -> RouteCategoryResponse:
    """Devuelve una categoría por slug. 404 si no existe."""
    cat_port = _get_cat_port(request)
    cat = await _require_category(cat_port, slug)
    return _cat_to_response(cat)


# ---------------------------------------------------------------------------
# EP-CAT04 — PATCH /route-categories/{slug}
# ---------------------------------------------------------------------------

@router.patch(
    "/route-categories/{slug}",
    response_model=RouteCategoryResponse,
    summary="EP-CAT04 — Actualizar parcialmente una categoría",
)
async def patch_category(
    request: Request,
    body: PatchCategoryRequest,
    slug: str = Path(..., min_length=1),
) -> RouteCategoryResponse:
    """
    Actualiza parcialmente label y/o color de una categoría.
    El slug es inmutable (RN-CAT04).
    body vacío → 422 (C-06).
    Semántica de color: ausente → conservar; null explícito → quitar (C-04).
    """
    cat_port = _get_cat_port(request)
    await _require_category(cat_port, slug)  # 404 si no existe

    # Preparar argumentos de actualización
    new_label = None
    new_label_lower = None
    if "label" in body.model_fields_set and body.label is not None:
        new_label = body.label.strip()
        new_label_lower = new_label.lower()

        # Verificar unicidad CI (excepto sobre la misma categoría — EC-CAT05)
        existing_by_label = await cat_port.get_category_by_label_lower(new_label_lower)
        if existing_by_label is not None and existing_by_label.slug != slug:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya existe una categoría con este nombre.",
            )

    # Semántica de color C-04: UNSET si no está en el body, None/str si está
    if "color" in body.model_fields_set:
        color_arg = body.color  # puede ser None (borrar) o str (actualizar)
    else:
        color_arg = UNSET  # conservar valor actual

    try:
        updated = await cat_port.update_category(
            slug=slug,
            label=new_label,
            label_lower=new_label_lower,
            color=color_arg,
        )
    except ValueError as exc:
        exc_str = str(exc)
        if "no encontrada" in exc_str:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc_str) from exc
        if "ya existe" in exc_str.lower():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya existe una categoría con este nombre.") from exc
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc_str) from exc
    except Exception as exc:
        logger.exception("Error actualizando categoría %s", slug)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        ) from exc

    return _cat_to_response(updated)


# ---------------------------------------------------------------------------
# EP-CAT05 — DELETE /route-categories/{slug}
# ---------------------------------------------------------------------------

@router.delete(
    "/route-categories/{slug}",
    response_model=DeleteCategoryResponse,
    status_code=status.HTTP_200_OK,
    summary="EP-CAT05 — Borrar categoría y reasignar a uncategorized",
)
async def delete_category(
    request: Request,
    slug: str = Path(..., min_length=1),
) -> DeleteCategoryResponse:
    """
    Borra la categoría. Reasigna atómicamente todas las plantillas y destinos
    asignados a 'uncategorized' (EC-CAT06/07).
    Devuelve 200 con {deleted_slug, reassigned_count, reassigned_to}.
    Borrar la default → 409 (C-05, EC-CAT01).
    """
    cat_port = _get_cat_port(request)
    cat = await _require_category(cat_port, slug)  # 404 si no existe

    # RN-CAT01: la categoría default no se puede borrar (EC-CAT01)
    if cat.is_default:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La categoría por defecto no se puede borrar.",
        )

    try:
        deleted_slug, reassigned_count = await cat_port.delete_category_and_reassign(slug)
    except ValueError as exc:
        exc_str = str(exc)
        if "no encontrada" in exc_str:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc_str) from exc
        if "por defecto" in exc_str:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc_str) from exc
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc_str) from exc
    except Exception as exc:
        logger.exception("Error borrando categoría %s", slug)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        ) from exc

    return DeleteCategoryResponse(
        deleted_slug=deleted_slug,
        reassigned_count=reassigned_count,
        reassigned_to="uncategorized",
    )
