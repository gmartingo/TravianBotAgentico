"""
Router FastAPI para el Portal de Desarrollador de Rutas — Catálogo Maestro de Plantillas.

Endpoints (sin prefijo /api — el proxy de Vite lo retira):

  EP-RT01  GET    /route-templates                                   — listar plantillas (filtro por category, include_paths, limit, offset)
  EP-RT02  POST   /route-templates                                   — crear plantilla (201 + Location)
  EP-RT03  GET    /route-templates/{id}                              — obtener plantilla con paths+steps
  EP-RT04  PUT    /route-templates/{id}                              — PATCH parcial de plantilla
  EP-RT05  DELETE /route-templates/{id}                              — borrar plantilla (204)
  EP-RT06  GET    /route-templates/{id}/paths                        — listar paths de una plantilla
  EP-RT07  POST   /route-templates/{id}/clone-to-world/{world_id}   — clonar plantilla a un mundo (201/200/409)
  EP-RT08  POST   /worlds/{world_id}/noise/apply-templates           — bulk clone a un mundo
  EP-RT09  POST   /route-templates/{id}/sync-to-world/{world_id}    — re-sincronizar instancia con plantilla
  EP-RT10  POST   /route-templates/{id}/test                        — probar plantilla en vivo

Sin Accept-Language: los labels y slugs son texto del desarrollador, no del catálogo de Travian.
Gobernanza de idioma: decisión validada en spec §8 (apis_validadas_por_desarrollador_apis: true).

Spec route-templates-developer-portal.md §8 (EP-RT01..RT10).
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response, status
from pydantic import BaseModel, Field, field_validator, model_validator

from adapters.db.noise_sqlite_adapter import _validate_url_pattern  # Opción A: importar privado del mismo paquete
from core.entities.noise import (
    NavigationStep,
    NoiseAction,
    NoiseCategory,
    RouteTemplate,
    RouteTemplatePath,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["route-templates"])


# ---------------------------------------------------------------------------
# Helpers — acceso a ports desde app.state
# ---------------------------------------------------------------------------

def _get_rt_port(request: Request):
    """Extrae route_template_port del app.state."""
    port = getattr(request.app.state, "route_template_port", None)
    if port is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        )
    return port


def _get_noise_db(request: Request):
    """Extrae noise_db_port del app.state."""
    port = getattr(request.app.state, "noise_db_port", None)
    if port is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        )
    return port


def _get_account_db(request: Request):
    """Extrae db_port del app.state (para verificar existencia del mundo)."""
    db = getattr(request.app.state, "db_port", None)
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        )
    return db


async def _require_template(rt_port, template_id: int) -> RouteTemplate:
    """404 si la plantilla no existe."""
    tpl = await rt_port.get_template(template_id)
    if tpl is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plantilla no encontrada.",
        )
    return tpl


async def _require_world(request: Request, world_id: int):
    """404 si el mundo no existe. Devuelve la entidad World."""
    db = _get_account_db(request)
    world = await db.get_world(world_id)
    if world is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mundo no encontrado.",
        )
    return world


# ---------------------------------------------------------------------------
# Modelos Pydantic — Steps
# ---------------------------------------------------------------------------

class TemplateStepRequest(BaseModel):
    """Step de una ruta de plantilla. Mismas restricciones anti-detección que NavigationStep."""
    step_order: int = Field(..., ge=0)
    action: NoiseAction
    selector: str = Field(..., min_length=1)
    value: str = ""
    delay_min_ms: int = Field(default=500, ge=0)
    delay_max_ms: int = Field(default=900, ge=0)
    expected_url_after_click: Optional[str] = None

    @model_validator(mode="after")
    def check_delay_range(self) -> "TemplateStepRequest":
        if self.delay_max_ms < self.delay_min_ms:
            raise ValueError("delay_max_ms debe ser >= delay_min_ms.")
        # Anti-detección: mismos límites que NavigationStep
        if self.delay_min_ms < NavigationStep.NOISE_STEP_DELAY_FLOOR_MS:
            raise ValueError(
                f"delay_min_ms debe ser >= {NavigationStep.NOISE_STEP_DELAY_FLOOR_MS} ms "
                "(anti-detección)."
            )
        if self.delay_max_ms > NavigationStep.NOISE_STEP_DELAY_CEILING_MS:
            raise ValueError(
                f"delay_max_ms debe ser <= {NavigationStep.NOISE_STEP_DELAY_CEILING_MS} ms "
                "(anti-detección)."
            )
        return self


class TemplateStepResponse(BaseModel):
    id: Optional[int] = None
    step_order: int
    action: str
    selector: str
    value: str
    delay_min_ms: int
    delay_max_ms: int
    expected_url_after_click: Optional[str] = None


# ---------------------------------------------------------------------------
# Modelos Pydantic — Paths de plantilla
# ---------------------------------------------------------------------------

class TemplatePathRequest(BaseModel):
    origin: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    is_active: bool = True
    steps: list[TemplateStepRequest] = Field(default_factory=list)


class TemplatePathResponse(BaseModel):
    id: Optional[int] = None
    template_id: Optional[int] = None
    origin: str
    label: str
    is_active: bool
    steps: list[TemplateStepResponse]


# ---------------------------------------------------------------------------
# Modelos Pydantic — Plantillas
# ---------------------------------------------------------------------------

class RouteTemplateListItem(BaseModel):
    """Item de lista EP-RT01 — sin paths (a menos que include_paths=true)."""
    id: int
    slug: str
    label: str
    category: str
    url_pattern: str
    navigation_weight: float
    is_safe: bool
    paths_count: int
    paths: Optional[list[TemplatePathResponse]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class RouteTemplateResponse(BaseModel):
    """Respuesta completa EP-RT02/03/04 — con paths+steps."""
    id: int
    slug: str
    label: str
    category: str
    url_pattern: str
    navigation_weight: float
    is_safe: bool
    paths: list[TemplatePathResponse]
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CreateTemplateRequest(BaseModel):
    slug: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    category: NoiseCategory
    url_pattern: str = Field(..., min_length=1)
    navigation_weight: float = Field(
        default=1.0,
        ge=0.1,
        le=5.0,
        description="Peso de navegación inicial sugerido al clonar. Rango [0.1, 5.0] (anti-detección).",
    )
    is_safe: bool = True
    paths: list[TemplatePathRequest] = Field(default_factory=list)


class UpdateTemplateRequest(BaseModel):
    """EP-RT04 — PATCH parcial. slug, category y url_pattern son inmutables."""
    # Detectar si el cliente intenta cambiar campos inmutables
    slug: Optional[str] = None
    category: Optional[str] = None
    url_pattern: Optional[str] = None
    # Campos actualizables
    label: Optional[str] = Field(default=None, min_length=1)
    navigation_weight: Optional[float] = Field(default=None, ge=0.1, le=5.0)
    is_safe: Optional[bool] = None
    paths: Optional[list[TemplatePathRequest]] = None

    @model_validator(mode="after")
    def check_immutable_fields(self) -> "UpdateTemplateRequest":
        if self.slug is not None:
            raise ValueError(
                "slug no se puede cambiar tras la creación."
            )
        if self.category is not None:
            raise ValueError(
                "category no se puede cambiar tras la creación."
            )
        if self.url_pattern is not None:
            raise ValueError(
                "url_pattern no se puede cambiar tras la creación."
            )
        return self

    @model_validator(mode="after")
    def at_least_one_mutable_field(self) -> "UpdateTemplateRequest":
        if all(v is None for v in [self.label, self.navigation_weight, self.is_safe, self.paths]):
            raise ValueError(
                "El body debe contener al menos uno de: label, navigation_weight, is_safe, paths."
            )
        return self


# ---------------------------------------------------------------------------
# Modelos Pydantic — Clone / Sync / Bulk
# ---------------------------------------------------------------------------

class CloneResultResponse(BaseModel):
    result: str  # "cloned" | "already_exists"
    destination_id: int
    world_id: int
    template_id: int
    url_pattern: Optional[str] = None


class BulkApplyRequest(BaseModel):
    template_ids: list[int] = Field(..., min_length=1)
    force: bool = False

    @field_validator("template_ids")
    @classmethod
    def template_ids_not_empty(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("template_ids no puede estar vacío.")
        return v


class BulkResultItem(BaseModel):
    template_id: int
    result: str  # "cloned" | "already_exists" | "conflict"
    destination_id: Optional[int] = None
    conflicting_destination_id: Optional[int] = None
    error: Optional[str] = None


class BulkApplyResponse(BaseModel):
    results: list[BulkResultItem]


class SyncResultResponse(BaseModel):
    result: str  # "synced" | "created"
    destination_id: int
    paths_replaced: Optional[int] = None


# ---------------------------------------------------------------------------
# Modelos Pydantic — Test en vivo EP-RT10 (mismo shape que EP-N14)
# ---------------------------------------------------------------------------

class TemplateTestRequest(BaseModel):
    world_id: int = Field(..., ge=1)
    path_index: int = Field(default=0, ge=0)


# Re-exporta los mismos modelos de respuesta que EP-N14 (PathTestResponse)
# importados desde noise.py para reutilizar el shape exacto
from adapters.api.routes.noise import (  # noqa: E402
    PathTestResponse,
    PathTestStepResultResponse,
)


# ---------------------------------------------------------------------------
# Helpers de conversión entidad → response
# ---------------------------------------------------------------------------

def _step_to_response(step: NavigationStep) -> TemplateStepResponse:
    return TemplateStepResponse(
        id=step.id,
        step_order=step.step_order,
        action=step.action.value,
        selector=step.selector,
        value=step.value,
        delay_min_ms=step.delay_min_ms,
        delay_max_ms=step.delay_max_ms,
        expected_url_after_click=step.expected_url_after_click,
    )


def _path_to_response(path: RouteTemplatePath) -> TemplatePathResponse:
    return TemplatePathResponse(
        id=path.id,
        template_id=path.template_id,
        origin=path.origin,
        label=path.label,
        is_active=path.is_active,
        steps=[_step_to_response(s) for s in path.steps],
    )


def _template_to_full_response(tpl: RouteTemplate) -> RouteTemplateResponse:
    return RouteTemplateResponse(
        id=tpl.id,
        slug=tpl.slug,
        label=tpl.label,
        category=tpl.category.value,
        url_pattern=tpl.url_pattern,
        navigation_weight=tpl.navigation_weight,
        is_safe=tpl.is_safe,
        paths=[_path_to_response(p) for p in tpl.paths],
        created_at=tpl.created_at.isoformat() if tpl.created_at else None,
        updated_at=tpl.updated_at.isoformat() if tpl.updated_at else None,
    )


def _template_to_list_item(
    tpl: RouteTemplate,
    paths_count: int,
    include_paths: bool,
) -> RouteTemplateListItem:
    return RouteTemplateListItem(
        id=tpl.id,
        slug=tpl.slug,
        label=tpl.label,
        category=tpl.category.value,
        url_pattern=tpl.url_pattern,
        navigation_weight=tpl.navigation_weight,
        is_safe=tpl.is_safe,
        paths_count=paths_count,
        paths=[_path_to_response(p) for p in tpl.paths] if include_paths else None,
        created_at=tpl.created_at.isoformat() if tpl.created_at else None,
        updated_at=tpl.updated_at.isoformat() if tpl.updated_at else None,
    )


def _steps_from_request(steps_req: list[TemplateStepRequest]) -> list[NavigationStep]:
    return [
        NavigationStep(
            id=None,
            path_id=None,
            step_order=s.step_order,
            action=s.action,
            selector=s.selector,
            value=s.value,
            delay_min_ms=s.delay_min_ms,
            delay_max_ms=s.delay_max_ms,
            expected_url_after_click=s.expected_url_after_click,
        )
        for s in steps_req
    ]


def _paths_from_request(paths_req: list[TemplatePathRequest]) -> list[RouteTemplatePath]:
    return [
        RouteTemplatePath(
            id=None,
            template_id=None,
            origin=p.origin,
            label=p.label,
            is_active=p.is_active,
            steps=_steps_from_request(p.steps),
        )
        for p in paths_req
    ]


# ---------------------------------------------------------------------------
# Lógica de clonado (spec §9.1) — reutilizada por EP-RT07, EP-RT08, EP-RT09
# ---------------------------------------------------------------------------

async def _clone_template_to_world(
    template: RouteTemplate,
    world,
    noise_db,
    force: bool = False,
) -> dict:
    """
    Clona una plantilla a un mundo siguiendo §9.1.
    Devuelve un dict con: result, destination_id, y opcionalmente conflicting_destination_id.

    result puede ser: "cloned" | "already_exists"
    Lanza HTTPException 409 si hay colisión sin force=true.
    Lanza HTTPException 422 si la URL absoluta no pertenece al servidor del mundo.
    """
    # Validar url_pattern contra world.server (EC-RT13)
    # Solo si la URL es absoluta. Las relativas (/build.php?gid=13) son siempre válidas.
    if "://" in template.url_pattern:
        try:
            _validate_url_pattern(template.url_pattern, world.server)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

    # Verificar colisión UNIQUE(world_id, url_pattern) — RN-RT05
    existing = await noise_db.find_destination_by_url(world.id, template.url_pattern)

    if existing is not None:
        if existing.template_id == template.id:
            # Caso B: idempotente — misma plantilla ya clonada
            return {"result": "already_exists", "destination_id": existing.id}
        elif not force:
            # Caso A o C: colisión
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": (
                        f"Ya existe un destino con url_pattern '{template.url_pattern}' "
                        f"en el mundo {world.id}."
                    ),
                    "conflicting_destination_id": existing.id,
                },
            )
        else:
            # force=True: borrar instancia conflictiva y continuar
            await noise_db.delete_destination(existing.id)

    # Crear noise_destination desde la plantilla
    dest = await noise_db.create_destination(
        world_id=world.id,
        url_pattern=template.url_pattern,
        label=template.label,
        category=template.category,
        frequency_weight=template.navigation_weight,
        is_safe=template.is_safe,
        template_id=template.id,
    )

    # Clonar paths y steps atómicamente
    for tpath in template.paths:
        await noise_db.create_path(
            dest_id=dest.id,
            origin=tpath.origin,
            label=tpath.label,
            steps=[
                NavigationStep(
                    id=None,
                    path_id=None,
                    step_order=s.step_order,
                    action=s.action,
                    selector=s.selector,
                    value=s.value,
                    delay_min_ms=s.delay_min_ms,
                    delay_max_ms=s.delay_max_ms,
                    expected_url_after_click=s.expected_url_after_click,
                )
                for s in tpath.steps
            ],
        )

    return {"result": "cloned", "destination_id": dest.id}


# ---------------------------------------------------------------------------
# EP-RT01 — GET /route-templates
# ---------------------------------------------------------------------------

@router.get(
    "/route-templates",
    response_model=list[RouteTemplateListItem],
    summary="EP-RT01 — Listar plantillas de rutas",
)
async def list_templates(
    request: Request,
    category: Optional[NoiseCategory] = Query(default=None),
    include_paths: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[RouteTemplateListItem]:
    """
    Lista el catálogo maestro de plantillas de rutas de navegación de ruido.

    Filtros: category (enum), include_paths (boolean), limit, offset.
    Si include_paths=true, cada item incluye paths+steps. Por defecto solo metadata.
    Nota: category inválida → 422 automático de FastAPI (no 400).
    """
    rt_port = _get_rt_port(request)

    try:
        templates = await rt_port.list_templates(
            category=category,
            include_paths=include_paths,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        logger.exception("Error listando plantillas de rutas")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        ) from exc

    result = []
    for tpl in templates:
        if include_paths:
            paths_count = len(tpl.paths)
        else:
            # paths=[] cuando include_paths=False; contar desde BD
            try:
                paths_count = await rt_port.count_paths_for_template(tpl.id)
            except Exception:
                paths_count = 0
        result.append(_template_to_list_item(tpl, paths_count, include_paths))
    return result


# ---------------------------------------------------------------------------
# EP-RT02 — POST /route-templates
# ---------------------------------------------------------------------------

@router.post(
    "/route-templates",
    response_model=RouteTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="EP-RT02 — Crear plantilla de ruta",
)
async def create_template(
    request: Request,
    response: Response,
    body: CreateTemplateRequest,
) -> RouteTemplateResponse:
    """
    Crea una nueva plantilla global de ruta de navegación.
    slug debe ser kebab-case y único globalmente.
    navigation_weight rango [0.1, 5.0] (anti-detección).
    Los steps respetan las mismas restricciones anti-detección que los de producción.
    """
    rt_port = _get_rt_port(request)

    # Construir la entidad (validación en __post_init__)
    try:
        tpl = RouteTemplate(
            id=None,
            slug=body.slug,
            label=body.label,
            category=body.category,
            url_pattern=body.url_pattern,
            navigation_weight=body.navigation_weight,
            is_safe=body.is_safe,
            paths=_paths_from_request(body.paths),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    try:
        created = await rt_port.create_template(tpl)
    except ValueError as exc:
        # ValueError de slug duplicado → 409
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Error creando plantilla de ruta")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        ) from exc

    response.headers["Location"] = f"/route-templates/{created.id}"
    return _template_to_full_response(created)


# ---------------------------------------------------------------------------
# EP-RT03 — GET /route-templates/{id}
# ---------------------------------------------------------------------------

@router.get(
    "/route-templates/{template_id}",
    response_model=RouteTemplateResponse,
    summary="EP-RT03 — Obtener plantilla de ruta con paths+steps",
)
async def get_template(
    request: Request,
    template_id: int = Path(..., ge=1),
) -> RouteTemplateResponse:
    """Devuelve la plantilla con sus paths y steps completos."""
    rt_port = _get_rt_port(request)
    tpl = await _require_template(rt_port, template_id)
    return _template_to_full_response(tpl)


# ---------------------------------------------------------------------------
# EP-RT04 — PUT /route-templates/{id}
# ---------------------------------------------------------------------------

@router.put(
    "/route-templates/{template_id}",
    response_model=RouteTemplateResponse,
    summary="EP-RT04 — Actualizar plantilla de ruta (PATCH parcial)",
)
async def update_template(
    request: Request,
    body: UpdateTemplateRequest,
    template_id: int = Path(..., ge=1),
) -> RouteTemplateResponse:
    """
    PATCH parcial de la plantilla.
    slug, category y url_pattern son inmutables (RN-RT02, §10).
    Si se pasa paths (no None), es un reemplazo ATÓMICO de los paths+steps.
    """
    rt_port = _get_rt_port(request)
    await _require_template(rt_port, template_id)  # 404 si no existe

    # Convertir paths a entidades si se pasan
    paths_entities: list[RouteTemplatePath] | None = None
    if body.paths is not None:
        try:
            paths_entities = _paths_from_request(body.paths)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

    try:
        updated = await rt_port.update_template(
            template_id=template_id,
            label=body.label,
            navigation_weight=body.navigation_weight,
            is_safe=body.is_safe,
            paths=paths_entities,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Error actualizando plantilla %d", template_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        ) from exc

    return _template_to_full_response(updated)


# ---------------------------------------------------------------------------
# EP-RT05 — DELETE /route-templates/{id}
# ---------------------------------------------------------------------------

@router.delete(
    "/route-templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="EP-RT05 — Borrar plantilla de ruta",
)
async def delete_template(
    request: Request,
    template_id: int = Path(..., ge=1),
) -> None:
    """
    Borra la plantilla y en cascada sus paths y steps.
    Los noise_destinations clonados quedan con template_id=NULL (ON DELETE SET NULL).
    """
    rt_port = _get_rt_port(request)
    await _require_template(rt_port, template_id)  # 404 si no existe

    try:
        await rt_port.delete_template(template_id)
    except Exception as exc:
        logger.exception("Error borrando plantilla %d", template_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        ) from exc


# ---------------------------------------------------------------------------
# EP-RT06 — GET /route-templates/{id}/paths
# ---------------------------------------------------------------------------

@router.get(
    "/route-templates/{template_id}/paths",
    response_model=list[TemplatePathResponse],
    summary="EP-RT06 — Listar paths de una plantilla",
)
async def list_template_paths(
    request: Request,
    template_id: int = Path(..., ge=1),
) -> list[TemplatePathResponse]:
    """
    Lista los paths de la plantilla con sus steps.
    404 si la plantilla no existe.
    """
    rt_port = _get_rt_port(request)
    await _require_template(rt_port, template_id)  # 404 si no existe

    try:
        paths = await rt_port.list_paths_for_template(template_id)
    except Exception as exc:
        logger.exception("Error listando paths de plantilla %d", template_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        ) from exc

    return [_path_to_response(p) for p in paths]


# ---------------------------------------------------------------------------
# EP-RT07 — POST /route-templates/{id}/clone-to-world/{world_id}
# ---------------------------------------------------------------------------

@router.post(
    "/route-templates/{template_id}/clone-to-world/{world_id}",
    summary="EP-RT07 — Clonar plantilla a un mundo",
)
async def clone_to_world(
    request: Request,
    response: Response,
    template_id: int = Path(..., ge=1),
    world_id: int = Path(..., ge=1),
    force: bool = Query(default=False),
):
    """
    Clona la plantilla al mundo indicado.

    Resultado según RN-RT05:
      - 201 + Location: clon nuevo creado (o force=true sobreescribiendo).
      - 200: misma plantilla ya estaba clonada (idempotente).
      - 409: URL ocupada por otro destino (sin force=true).
      - 422: URL absoluta de la plantilla no compatible con el servidor del mundo.
    """
    rt_port = _get_rt_port(request)
    noise_db = _get_noise_db(request)

    template = await _require_template(rt_port, template_id)
    world = await _require_world(request, world_id)

    result = await _clone_template_to_world(template, world, noise_db, force=force)

    if result["result"] == "already_exists":
        return {
            "result": "already_exists",
            "destination_id": result["destination_id"],
            "world_id": world_id,
            "template_id": template_id,
        }

    # result == "cloned"
    dest_id = result["destination_id"]
    response.headers["Location"] = f"/worlds/{world_id}/noise/destinations/{dest_id}"
    response.status_code = status.HTTP_201_CREATED
    return {
        "result": "cloned",
        "destination_id": dest_id,
        "world_id": world_id,
        "template_id": template_id,
        "url_pattern": template.url_pattern,
    }


# ---------------------------------------------------------------------------
# EP-RT08 — POST /worlds/{world_id}/noise/apply-templates
# ---------------------------------------------------------------------------

@router.post(
    "/worlds/{world_id}/noise/apply-templates",
    response_model=BulkApplyResponse,
    summary="EP-RT08 — Bulk clone: aplicar múltiples plantillas a un mundo",
)
async def apply_templates(
    request: Request,
    body: BulkApplyRequest,
    world_id: int = Path(..., ge=1),
) -> BulkApplyResponse:
    """
    Clona en masa una lista de plantillas al mundo indicado.
    No es atómica: si una plantilla falla, las demás siguen.
    Resultado por plantilla: cloned | already_exists | conflict.
    """
    rt_port = _get_rt_port(request)
    noise_db = _get_noise_db(request)
    world = await _require_world(request, world_id)

    results: list[BulkResultItem] = []

    for tid in body.template_ids:
        template = await rt_port.get_template(tid)
        if template is None:
            results.append(BulkResultItem(
                template_id=tid,
                result="conflict",
                error=f"Plantilla {tid} no encontrada.",
            ))
            continue

        try:
            res = await _clone_template_to_world(template, world, noise_db, force=body.force)
            results.append(BulkResultItem(
                template_id=tid,
                result=res["result"],
                destination_id=res["destination_id"],
            ))
        except HTTPException as exc:
            if exc.status_code == status.HTTP_409_CONFLICT:
                detail = exc.detail
                conflicting_id = None
                error_msg = str(detail)
                if isinstance(detail, dict):
                    conflicting_id = detail.get("conflicting_destination_id")
                    error_msg = detail.get("message", error_msg)
                results.append(BulkResultItem(
                    template_id=tid,
                    result="conflict",
                    conflicting_destination_id=conflicting_id,
                    error=error_msg,
                ))
            else:
                results.append(BulkResultItem(
                    template_id=tid,
                    result="conflict",
                    error=exc.detail if isinstance(exc.detail, str) else str(exc.detail),
                ))
        except Exception as exc:
            logger.exception("Error clonando plantilla %d a mundo %d", tid, world_id)
            results.append(BulkResultItem(
                template_id=tid,
                result="conflict",
                error="Error interno del servidor.",
            ))

    return BulkApplyResponse(results=results)


# ---------------------------------------------------------------------------
# EP-RT09 — POST /route-templates/{id}/sync-to-world/{world_id}
# ---------------------------------------------------------------------------

@router.post(
    "/route-templates/{template_id}/sync-to-world/{world_id}",
    summary="EP-RT09 — Re-sincronizar instancia de mundo con la plantilla maestra",
)
async def sync_to_world(
    request: Request,
    response: Response,
    template_id: int = Path(..., ge=1),
    world_id: int = Path(..., ge=1),
):
    """
    Re-sincroniza la instancia de un mundo con la plantilla maestra (§9.2).
    - Si hay instancia: reemplaza paths/steps. Preserva navigation_weight, is_dead, failures.
    - Si NO hay instancia: actúa como clone (EC-RT04). Devuelve 201.
    - 409 si hay URL conflictiva con template_id distinto (igual que EP-RT07).
    """
    rt_port = _get_rt_port(request)
    noise_db = _get_noise_db(request)

    template = await _require_template(rt_port, template_id)
    world = await _require_world(request, world_id)

    # Buscar instancia existente con template_id
    instance = await noise_db.find_destination_by_template(world_id, template_id)

    if instance is None:
        # EC-RT04: no existe instancia → comportarse como clone
        # Verificar colisión de URL antes de crear
        existing_by_url = await noise_db.find_destination_by_url(world_id, template.url_pattern)
        if existing_by_url is not None and existing_by_url.template_id != template_id:
            # URL ocupada por destino con template_id distinto (o sin template_id)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": (
                        "Ya existe un destino con esa url_pattern en el mundo "
                        "pero pertenece a otra plantilla."
                    ),
                    "conflicting_destination_id": existing_by_url.id,
                },
            )

        # Crear la instancia
        result = await _clone_template_to_world(template, world, noise_db, force=False)
        dest_id = result["destination_id"]
        response.headers["Location"] = f"/worlds/{world_id}/noise/destinations/{dest_id}"
        response.status_code = status.HTTP_201_CREATED
        return {
            "result": "created",
            "destination_id": dest_id,
        }

    # Instancia existe: re-sincronizar paths/steps
    # 1. Borrar todos los paths de la instancia (CASCADE borra los steps)
    existing_paths = await noise_db.list_paths(instance.id)
    for path in existing_paths:
        await noise_db.delete_path(path.id)

    # 2. Re-crear paths+steps desde la plantilla
    paths_replaced = 0
    for tpath in template.paths:
        await noise_db.create_path(
            dest_id=instance.id,
            origin=tpath.origin,
            label=tpath.label,
            steps=[
                NavigationStep(
                    id=None,
                    path_id=None,
                    step_order=s.step_order,
                    action=s.action,
                    selector=s.selector,
                    value=s.value,
                    delay_min_ms=s.delay_min_ms,
                    delay_max_ms=s.delay_max_ms,
                    expected_url_after_click=s.expected_url_after_click,
                )
                for s in tpath.steps
            ],
        )
        paths_replaced += 1

    return SyncResultResponse(
        result="synced",
        destination_id=instance.id,
        paths_replaced=paths_replaced,
    )


# ---------------------------------------------------------------------------
# EP-RT10 — POST /route-templates/{id}/test
# ---------------------------------------------------------------------------

@router.post(
    "/route-templates/{template_id}/test",
    response_model=PathTestResponse,
    summary="EP-RT10 — Probar plantilla de ruta en vivo",
)
async def test_template(
    request: Request,
    body: TemplateTestRequest,
    template_id: int = Path(..., ge=1),
) -> PathTestResponse:
    """
    Ejecuta una plantilla en vivo contra un mundo (wrapper de EP-N14).

    Estrategia (spec §8.11, §9.1):
    1. Obtener plantilla → 404.
    2. Obtener world → 404.
    3. Buscar instancia ya clonada (find_destination_by_template).
       3a. Si existe → usar path[path_index] de esa instancia. NO borrar.
       3b. Si no existe → clonar temporalmente con label="[TEST TEMPORAL]".
    4. Obtener NavigationPath real de BD (list_paths(dest_id))[path_index].
       → 422 si path_index >= len(paths).
    5. Llamar execute_path_test(world_id, path).
    6. Si se creó instancia temporal → borrarla en try/finally.
    7. Devolver PathTestResult con mismo shape que EP-N14.

    HTTP 200 tanto si la ruta pasó (overall="ok") como si falló (overall="error").
    """
    from core.exceptions import BrowserBusyError  # import local para evitar ciclos
    from core.scheduling.world_agent import AgentState  # import local para evitar ciclos

    rt_port = _get_rt_port(request)
    noise_db = _get_noise_db(request)

    template = await _require_template(rt_port, template_id)
    world = await _require_world(request, body.world_id)

    # Verificar que hay un WorldAgent activo con sesión de browser
    agents: dict = getattr(request.app.state, "world_agents", {})
    agent = agents.get(body.world_id)
    session_active = bool(agent is not None and agent._session_active())

    if agent is None or agent.state != AgentState.RUNNING or not session_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "El agente del mundo está desconectado. "
                "Inicia sesión primero para poder probar la ruta."
            ),
        )

    # Paso 3: buscar instancia ya clonada
    instance = await noise_db.find_destination_by_template(body.world_id, template_id)
    temporal_dest_id: int | None = None

    if instance is not None:
        dest_id = instance.id
    else:
        # Clonar temporalmente
        dest = await noise_db.create_destination(
            world_id=body.world_id,
            url_pattern=template.url_pattern,
            label="[TEST TEMPORAL]",
            category=template.category,
            frequency_weight=template.navigation_weight,
            is_safe=False,
            template_id=template.id,
        )
        dest_id = dest.id
        temporal_dest_id = dest.id

        # Clonar paths y steps
        for tpath in template.paths:
            await noise_db.create_path(
                dest_id=dest_id,
                origin=tpath.origin,
                label=tpath.label,
                steps=[
                    NavigationStep(
                        id=None,
                        path_id=None,
                        step_order=s.step_order,
                        action=s.action,
                        selector=s.selector,
                        value=s.value,
                        delay_min_ms=s.delay_min_ms,
                        delay_max_ms=s.delay_max_ms,
                        expected_url_after_click=s.expected_url_after_click,
                    )
                    for s in tpath.steps
                ],
            )

    try:
        # Paso 4: obtener NavigationPath real de BD
        paths = await noise_db.list_paths(dest_id)
        if body.path_index >= len(paths):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"path_index {body.path_index} fuera de rango — "
                    f"la plantilla tiene {len(paths)} path(s)."
                ),
            )
        path = paths[body.path_index]

        # Paso 5: ejecutar el test
        try:
            report = await agent.execute_path_test(path)
        except BrowserBusyError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "El browser está ocupado con otra tarea. "
                    "Espera a que finalice e inténtalo de nuevo."
                ),
            )
        except RuntimeError as exc:
            logger.error("execute_path_test RT10 mundo %d: RuntimeError: %s", body.world_id, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error interno del servidor.",
            ) from exc
        except Exception:
            logger.exception("execute_path_test RT10 mundo %d: error inesperado", body.world_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error interno del servidor.",
            )

    finally:
        # Paso 6: borrar instancia temporal siempre (incluso si hubo excepción)
        if temporal_dest_id is not None:
            try:
                await noise_db.delete_destination(temporal_dest_id)
            except Exception:
                logger.warning(
                    "EP-RT10: no se pudo borrar instancia temporal %d", temporal_dest_id
                )

    return PathTestResponse(
        overall=report.overall,
        aborted_at_step=report.aborted_at_step,
        anchor_navigated_to=report.anchor_navigated_to,
        steps=[
            PathTestStepResultResponse(
                step_order=s.step_order,
                action=s.action,
                selector=s.selector,
                status=s.status,
                reason=s.reason,
                current_url=s.current_url,
            )
            for s in report.steps
        ],
    )
