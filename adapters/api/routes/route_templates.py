"""
Router FastAPI para el Portal de Desarrollador de Rutas — Catálogo Maestro de Plantillas.

Endpoints (sin prefijo /api — el proxy de Vite lo retira):

  EP-RT01  GET    /route-templates                                   — listar plantillas
  EP-RT02  POST   /route-templates                                   — crear plantilla (201 + Location)
  EP-RT03  GET    /route-templates/{id}                              — obtener plantilla con paths+steps
  EP-RT04  PUT    /route-templates/{id}                              — PATCH parcial de plantilla
  EP-RT05  DELETE /route-templates/{id}                              — borrar plantilla (204)
  EP-RT06  GET    /route-templates/{id}/paths                        — listar paths de una plantilla
  EP-RT07  POST   /route-templates/{id}/clone-to-world/{world_id}   — clonar plantilla a un mundo
  EP-RT08  POST   /worlds/{world_id}/noise/apply-templates           — bulk clone a un mundo
  EP-RT09  POST   /route-templates/{id}/sync-to-world/{world_id}    — re-sincronizar instancia
  EP-RT10  POST   /route-templates/{id}/test                        — probar plantilla en vivo (v3)
  EP-RT11  GET    /route-templates/{id}/chain                        — cadena resuelta de pasos
  EP-RT12  DELETE /worlds/{world_id}/session                        — cerrar sesión Chrome de un mundo (v3)

v2: origin_template_id en request/response; navigation_weight ELIMINADO de plantilla.
    validate_no_cycle y validate_selector_is_structural en EP-RT02/EP-RT04.
    EP-RT07: navigation_weight del REQUEST (default 1.0).
    EP-RT08: default_navigation_weight en BulkApplyRequest.
v3: EP-RT10 usa _ensure_session (login on-demand idempotente) + execute_path_test_standalone.

Sin Accept-Language: labels y slugs son texto del desarrollador, no del catálogo de Travian.
Spec route-templates-developer-portal.md §8, §v2.8, §v3.4.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response, status
from pydantic import BaseModel, Field, field_validator, model_validator

from adapters.db.noise_sqlite_adapter import _validate_url_pattern  # Opción A: importar privado
from core.entities.noise import (
    NavigationStep,
    NoiseAction,
    NoiseCategory,
    RouteTemplate,
    RouteTemplatePath,
)
from core.exceptions import (
    AccountNotFoundError,
    FernetDecryptionError,
    LoginFailedError,
    WorldNotFoundError,
    WorldOrphanError,
)
from core.use_cases.route_template_service import (
    CyclicOriginError,
    TemplateNotFoundError,
    resolve_origin_chain,
    to_world_relative_url,
    validate_chain_integrity,
    validate_no_cycle,
    validate_selector_is_structural,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["route-templates", "session-management"])


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
    """Extrae db_port del app.state (para verificar existencia del mundo y obtener account_id)."""
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
# Helper v3 — ensure_session (login on-demand idempotente)
# ---------------------------------------------------------------------------

async def _ensure_session(
    world_id: int,
    session_registry,
    accounts_db,
    fernet,
) -> None:
    """
    Asegura que hay una sesión Chrome activa para world_id de forma idempotente.

    Flujo (spec §v3.3):
      1. Si session_registry.is_active(world_id) → retornar (idempotente).
      2. Si no → buscar account_id vía accounts_db.get_account_id_for_world(world_id).
         None → WorldOrphanError (→ 404).
      3. Instanciar LoginUseCase y llamar execute(account_id, world_id).
         Excepciones → mapear a HTTP (ver §v3.3).

    NOTA DE SEGURIDAD: no loguear cipher, fernet ni password.
    Solo world_id y account_id. Heredado de LoginUseCase.
    ANTI-DETECCIÓN: el login real usa human_click, delays, y navegación humana.
    Esta función delega en LoginUseCase que ya fue auditado por el guardian.

    GATE GUARDIAN: revisar antes de commitear.
    """
    if session_registry is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="session_registry no disponible — el servidor puede estar iniciándose.",
        )
    if fernet is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fernet no disponible. Verifica TRAVIAN_BOT_SECRET_KEY.",
        )

    if session_registry.is_active(world_id):
        return  # sesión ya activa — idempotente

    account_id = await accounts_db.get_account_id_for_world(world_id)
    if account_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"El mundo {world_id} no tiene cuenta asociada.",
        )

    from core.use_cases.login_use_case import LoginUseCase  # import local para evitar ciclos

    login_uc = LoginUseCase(
        registry=session_registry,
        db=accounts_db,
        fernet=fernet,
    )
    try:
        await login_uc.execute(account_id, world_id)
    except (AccountNotFoundError, WorldNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except FernetDecryptionError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Credenciales indescifrables. Verifica que TRAVIAN_BOT_SECRET_KEY "
                "es la misma que usaste al registrar la cuenta."
            ),
        )
    except LoginFailedError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                f"Login fallido para el mundo {world_id}. "
                "Verifica las credenciales en la configuración de la cuenta."
            ),
        )
    except Exception as exc:
        logger.exception("_ensure_session: error inesperado en world_id=%d", world_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al abrir la sesión.",
        ) from exc


# ---------------------------------------------------------------------------
# Helpers de validación de selectores (v2 GAP-4)
# ---------------------------------------------------------------------------

def _validate_steps_selectors(paths_req: list) -> None:
    """
    Valida que ningún selector de step en los paths contiene patrones de texto visible.
    Lanza HTTPException 422 si algún selector viola la regla estructural (GAP-4).
    Spec §v2-REGLA-SELECTORES, EC-RT12.
    """
    for path in paths_req:
        for step in path.steps:
            try:
                validate_selector_is_structural(step.selector)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=str(exc),
                ) from exc


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
    """
    Item de lista EP-RT01 — sin paths (a menos que include_paths=true).
    v2 rev.2: navigation_weight eliminado. El peso vive en NoiseDestination por-mundo.
    """
    id: int
    slug: str
    label: str
    category: str
    url_pattern: str
    is_safe: bool
    origin_template_id: Optional[int] = None  # v2 — null=raíz, int=ruta origen
    paths_count: int
    paths: Optional[list[TemplatePathResponse]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class RouteTemplateResponse(BaseModel):
    """
    Respuesta completa EP-RT02/03/04 — con paths+steps.
    v2 rev.2: navigation_weight eliminado. El peso vive en NoiseDestination por-mundo.
    """
    id: int
    slug: str
    label: str
    category: str
    url_pattern: str
    is_safe: bool
    origin_template_id: Optional[int] = None  # v2 — null=raíz, int=ruta origen
    paths: list[TemplatePathResponse]
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CreateTemplateRequest(BaseModel):
    """
    EP-RT02 — Crear plantilla.
    v2 rev.2: navigation_weight eliminado del request.
    v2: origin_template_id opcional — null=raíz libre, int=plantilla origen.
    v2-cat-libre: category es texto libre (≤ 50 chars). Acepta los 7 valores
      históricos del enum NoiseCategory y cualquier valor nuevo ("Estadísticas", etc.).
    """
    slug: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1, max_length=50)
    url_pattern: str = Field(..., min_length=1)
    is_safe: bool = True
    origin_template_id: Optional[int] = None  # v2 — default null (raíz)
    paths: list[TemplatePathRequest] = Field(default_factory=list)


class UpdateTemplateRequest(BaseModel):
    """
    EP-RT04 — PATCH parcial.
    - slug y url_pattern son inmutables (RN-RT02, §10).
    - category es EDITABLE desde v2-cat-libre (texto libre ≤ 50 chars).
    - v2 rev.2: navigation_weight eliminado de los campos editables.
    - v2: origin_template_id es editable (puede reasignarse o ponerse a null).
    """
    # Detectar si el cliente intenta cambiar campos estrictamente inmutables
    slug: Optional[str] = None
    url_pattern: Optional[str] = None
    # Campos actualizables
    label: Optional[str] = Field(default=None, min_length=1)
    is_safe: Optional[bool] = None
    category: Optional[str] = Field(default=None, min_length=1, max_length=50)
    origin_template_id: Optional[int] = None  # v2 — None = quitar origen (pasa a raíz)
    paths: Optional[list[TemplatePathRequest]] = None

    model_config = {"arbitrary_types_allowed": True}

    @model_validator(mode="after")
    def check_immutable_fields(self) -> "UpdateTemplateRequest":
        if self.slug is not None:
            raise ValueError("slug no se puede cambiar tras la creación.")
        if self.url_pattern is not None:
            raise ValueError("url_pattern no se puede cambiar tras la creación.")
        return self

    @model_validator(mode="after")
    def at_least_one_mutable_field(self) -> "UpdateTemplateRequest":
        mutable = [self.label, self.is_safe, self.paths, self.category]
        if all(v is None for v in mutable) and \
                "origin_template_id" not in (self.model_fields_set or set()):
            raise ValueError(
                "El body debe contener al menos uno de: label, category, origin_template_id, is_safe, paths."
            )
        return self


# ---------------------------------------------------------------------------
# Modelos Pydantic — Clone / Sync / Bulk
# ---------------------------------------------------------------------------

class CloneTemplateBody(BaseModel):
    """
    Body opcional de EP-RT07. El peso viene del REQUEST, no de la plantilla (v2 rev.2).
    Spec §v2.8 EP-RT07 corrección crítica.
    """
    navigation_weight: float = Field(default=1.0, ge=0.1, le=5.0)


class CloneResultResponse(BaseModel):
    result: str  # "cloned" | "already_exists"
    destination_id: int
    world_id: int
    template_id: int
    url_pattern: Optional[str] = None
    navigation_weight: Optional[float] = None  # presente en result="cloned"


class BulkApplyRequest(BaseModel):
    template_ids: list[int] = Field(..., min_length=1)
    force: bool = False
    default_navigation_weight: float = Field(default=1.0, ge=0.1, le=5.0)  # v2

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
    navigation_weight: Optional[float] = None  # presente solo en result="cloned" (v2)
    conflicting_destination_id: Optional[int] = None
    error: Optional[str] = None


class BulkApplyResponse(BaseModel):
    results: list[BulkResultItem]


class SyncResultResponse(BaseModel):
    result: str  # "synced" | "created"
    destination_id: int
    paths_replaced: Optional[int] = None


# ---------------------------------------------------------------------------
# Modelos Pydantic — EP-RT11 Chain
# ---------------------------------------------------------------------------

class ChainStepResponse(BaseModel):
    """Un paso resuelto en la cadena de ejecución. Spec §v2.8 EP-RT11."""
    position: int
    template_id: int
    template_slug: str
    label: str
    selector: str
    expected_url: Optional[str] = None   # alias de expected_url_after_click
    delay_min_ms: int
    delay_max_ms: int
    is_root: bool


class ChainResponse(BaseModel):
    """Respuesta de EP-RT11. Spec §v2.8 EP-RT11."""
    template_id: int
    template_slug: str
    depth: int            # len(steps) — nodos con step definido
    steps: list[ChainStepResponse]


# ---------------------------------------------------------------------------
# Modelos Pydantic — Test en vivo EP-RT10 (mismo shape que EP-N14)
# ---------------------------------------------------------------------------

class TemplateTestRequest(BaseModel):
    world_id: int = Field(..., ge=1)
    path_index: int = Field(default=0, ge=0)


# Re-exporta los mismos modelos de respuesta que EP-N14 (PathTestResponse)
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
        category=str(tpl.category),  # texto libre — no .value
        url_pattern=tpl.url_pattern,
        is_safe=tpl.is_safe,
        origin_template_id=tpl.origin_template_id,  # v2
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
        category=str(tpl.category),  # texto libre — no .value
        url_pattern=tpl.url_pattern,
        is_safe=tpl.is_safe,
        origin_template_id=tpl.origin_template_id,  # v2
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
            # URL world-relative: si el dev pega la URL completa del mundo, se guarda
            # solo la parte relativa (se quita scheme+host). El mundo se antepone al asignar.
            expected_url_after_click=to_world_relative_url(s.expected_url_after_click),
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
    navigation_weight: float = 1.0,  # v2: peso del REQUEST, no de la plantilla
) -> dict:
    """
    Clona una plantilla a un mundo siguiendo §9.1.
    Devuelve un dict con: result, destination_id, y opcionalmente conflicting_destination_id.

    result puede ser: "cloned" | "already_exists"
    Lanza HTTPException 409 si hay colisión sin force=true.
    Lanza HTTPException 422 si la URL absoluta no pertenece al servidor del mundo.

    v2: navigation_weight viene del REQUEST (del llamador), NO de template.navigation_weight.
    """
    # Validar url_pattern contra world.server (EC-RT13)
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
    # v2: frequency_weight viene del parámetro navigation_weight (del REQUEST).
    dest = await noise_db.create_destination(
        world_id=world.id,
        url_pattern=template.url_pattern,
        label=template.label,
        category=template.category,
        frequency_weight=navigation_weight,
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

    return {"result": "cloned", "destination_id": dest.id, "navigation_weight": navigation_weight}


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
    category: Optional[str] = Query(default=None, description="Filtra por categoría (texto libre). Sin validación: devuelve [] si no hay coincidencias."),
    include_paths: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[RouteTemplateListItem]:
    """
    Lista el catálogo maestro de plantillas de rutas de navegación de ruido.

    Filtros: category (texto libre — acepta valores nuevos y los 7 históricos),
    include_paths (boolean), limit, offset.
    Si include_paths=true, cada item incluye paths+steps. Por defecto solo metadata.
    origin_template_id añadido en v2.
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
    navigation_weight eliminado (v2 rev.2): el peso se fija al clonar a un mundo.
    origin_template_id opcional (v2): null=raíz libre, int=plantilla origen con validación anti-ciclos.
    Los steps respetan las mismas restricciones anti-detección que los de producción.
    v2 GAP-4: rechaza selectores por texto visible con 422.
    """
    rt_port = _get_rt_port(request)

    # v2 GAP-4: validar selectores antes de todo
    if body.paths:
        _validate_steps_selectors(body.paths)

    # v2: validar origen si se proporciona
    if body.origin_template_id is not None:
        origin = await rt_port.get_template(body.origin_template_id)
        if origin is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"La plantilla origen con id {body.origin_template_id} no existe.",
            )
        # En creación: verificar integridad de la cadena del origen (no ciclos entre terceros)
        try:
            await validate_chain_integrity(body.origin_template_id, rt_port)
        except CyclicOriginError as exc:
            # Profundidad excesiva
            if len(exc.cycle_path) > 20:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "message": "Cadena de orígenes demasiado profunda (máx. 20).",
                        "depth_reached": len(exc.cycle_path),
                    },
                ) from exc
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "El origin_template_id crea un ciclo en la cadena de orígenes.",
                    "cycle_path": exc.cycle_path,
                },
            ) from exc

    # Construir la entidad (validación en __post_init__)
    try:
        tpl = RouteTemplate(
            id=None,
            slug=body.slug,
            label=body.label,
            category=body.category,
            # URL world-relative: se quita el scheme+host del mundo si el dev pega la URL completa.
            url_pattern=to_world_relative_url(body.url_pattern),
            is_safe=body.is_safe,
            origin_template_id=body.origin_template_id,  # v2
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
    """Devuelve la plantilla con sus paths y steps completos. origin_template_id incluido (v2)."""
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
    origin_template_id editable en v2: puede reasignarse o ponerse a null.
    v2 GAP-4: rechaza selectores por texto visible con 422.
    v2: valida anti-ciclos si se cambia origin_template_id.
    """
    rt_port = _get_rt_port(request)
    await _require_template(rt_port, template_id)  # 404 si no existe

    # v2 GAP-4: validar selectores
    if body.paths is not None:
        _validate_steps_selectors(body.paths)

    # v2: validar origen si se cambia
    if "origin_template_id" in (body.model_fields_set or set()):
        new_origin = body.origin_template_id
        if new_origin is not None:
            origin = await rt_port.get_template(new_origin)
            if origin is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"La plantilla origen con id {new_origin} no existe.",
                )
            # En edición: comprobar que template_id no aparece en la cadena del nuevo origen
            try:
                await validate_no_cycle(
                    new_template_id=template_id,
                    proposed_origin_id=new_origin,
                    db=rt_port,
                )
            except CyclicOriginError as exc:
                if len(exc.cycle_path) > 20:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={
                            "message": "Cadena de orígenes demasiado profunda (máx. 20).",
                            "depth_reached": len(exc.cycle_path),
                        },
                    ) from exc
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "message": "El origin_template_id crea un ciclo en la cadena de orígenes.",
                        "cycle_path": exc.cycle_path,
                    },
                ) from exc

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

    # origin_template_id: solo enviar al adaptador si estaba en el body del request
    origin_sentinel = (
        ... if "origin_template_id" not in (body.model_fields_set or set())
        else body.origin_template_id
    )

    try:
        updated = await rt_port.update_template(
            template_id=template_id,
            label=body.label,
            is_safe=body.is_safe,
            category=body.category,           # None = no cambiar; str = actualizar
            origin_template_id=origin_sentinel,
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
    Las plantillas hijas quedan con origin_template_id=NULL (ON DELETE SET NULL, v2).
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
# EP-RT11 — GET /route-templates/{id}/chain (NUEVO v2)
# ---------------------------------------------------------------------------

@router.get(
    "/route-templates/{template_id}/chain",
    response_model=ChainResponse,
    summary="EP-RT11 — Cadena de pasos resuelta raíz→hoja",
)
async def get_template_chain(
    request: Request,
    template_id: int = Path(..., ge=1),
) -> ChainResponse:
    """
    Devuelve la cadena de pasos resuelta para una plantilla, en orden de ejecución
    (raíz → hoja). Cada elemento es un clic atómico.

    Uso principal: render en tabla en la UI cuando el usuario selecciona un origen.
    Una plantilla raíz devuelve una cadena de 1 elemento (o 0 si no tiene path/step).
    Una plantilla con origen borrado devuelve solo su propio clic (ON DELETE SET NULL actuó).

    Los 409 defensivos solo ocurren si la BD contiene datos corruptos (el gate de
    escritura ya previene ciclos).

    Spec §v2.8 EP-RT11.
    """
    rt_port = _get_rt_port(request)
    tpl = await _require_template(rt_port, template_id)

    try:
        resolved_steps = await resolve_origin_chain(template_id, rt_port)
    except TemplateNotFoundError as exc:
        # Un nodo intermedio de la cadena fue borrado sin SET NULL (datos corruptos)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plantilla {exc.template_id} no encontrada en la cadena.",
        ) from exc
    except CyclicOriginError as exc:
        # Ciclo en datos corruptos (defensivo)
        if len(exc.cycle_path) > 20:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Cadena de orígenes demasiado profunda (máx. 20).",
                    "depth_reached": len(exc.cycle_path),
                },
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Ciclo detectado en cadena de orígenes.",
                "cycle_path": exc.cycle_path,
            },
        ) from exc
    except Exception as exc:
        logger.exception("Error resolviendo cadena de plantilla %d", template_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        ) from exc

    # Construir response: is_root = True solo para el primer elemento de la cadena
    # (el que no tiene origen, es decir, la raíz global de la cadena)
    chain_steps = []
    for pos, rs in enumerate(resolved_steps):
        # is_root: True si esta plantilla no tiene origin_template_id (es raíz)
        # Hay que consultar la plantilla real para saberlo
        # Nota: la cadena está resuelta desde la raíz; el primer elemento siempre
        # tiene origin_template_id=None en una cadena bien formada.
        is_root = (pos == 0)
        chain_steps.append(ChainStepResponse(
            position=pos,
            template_id=rs.template_id,
            template_slug=rs.template_slug,
            label=rs.label,
            selector=rs.step.selector,
            expected_url=rs.expected_url,
            delay_min_ms=rs.step.delay_min_ms,
            delay_max_ms=rs.step.delay_max_ms,
            is_root=is_root,
        ))

    return ChainResponse(
        template_id=tpl.id,
        template_slug=tpl.slug,
        depth=len(chain_steps),
        steps=chain_steps,
    )


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
    body: Optional[CloneTemplateBody] = None,
):
    """
    Clona la plantilla al mundo indicado.

    Resultado según RN-RT05:
      - 201 + Location: clon nuevo creado (o force=true sobreescribiendo).
      - 200: misma plantilla ya estaba clonada (idempotente).
      - 409: URL ocupada por otro destino (sin force=true).
      - 422: URL absoluta no compatible con el servidor del mundo, o navigation_weight fuera de rango.

    v2: navigation_weight del REQUEST (default 1.0 si se omite el body).
    Spec §v2.8 EP-RT07 corrección crítica.
    """
    rt_port = _get_rt_port(request)
    noise_db = _get_noise_db(request)

    template = await _require_template(rt_port, template_id)
    world = await _require_world(request, world_id)

    # v2: peso del REQUEST, no de la plantilla
    nav_weight = body.navigation_weight if body is not None else 1.0

    result = await _clone_template_to_world(
        template, world, noise_db, force=force, navigation_weight=nav_weight
    )

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
        "navigation_weight": result.get("navigation_weight", nav_weight),
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

    v2: default_navigation_weight en el body (default 1.0) aplicado uniformemente.
    Cada ítem "cloned" incluye su navigation_weight.
    Spec §v2.8 EP-RT08.
    """
    rt_port = _get_rt_port(request)
    noise_db = _get_noise_db(request)
    world = await _require_world(request, world_id)

    nav_weight = body.default_navigation_weight

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
            res = await _clone_template_to_world(
                template, world, noise_db, force=body.force, navigation_weight=nav_weight
            )
            item = BulkResultItem(
                template_id=tid,
                result=res["result"],
                destination_id=res["destination_id"],
            )
            if res["result"] == "cloned":
                item.navigation_weight = res.get("navigation_weight", nav_weight)
            results.append(item)
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
        existing_by_url = await noise_db.find_destination_by_url(world_id, template.url_pattern)
        if existing_by_url is not None and existing_by_url.template_id != template_id:
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

        result = await _clone_template_to_world(template, world, noise_db, force=False)
        dest_id = result["destination_id"]
        response.headers["Location"] = f"/worlds/{world_id}/noise/destinations/{dest_id}"
        response.status_code = status.HTTP_201_CREATED
        return {
            "result": "created",
            "destination_id": dest_id,
        }

    # Instancia existe: re-sincronizar paths/steps
    existing_paths = await noise_db.list_paths(instance.id)
    for path in existing_paths:
        await noise_db.delete_path(path.id)

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
# EP-RT10 — POST /route-templates/{id}/test (v3 — con ensure_session)
# ---------------------------------------------------------------------------

@router.post(
    "/route-templates/{template_id}/test",
    response_model=PathTestResponse,
    summary="EP-RT10 — Probar plantilla de ruta en vivo (v3: ensure_session)",
)
async def test_template(
    request: Request,
    body: TemplateTestRequest,
    template_id: int = Path(..., ge=1),
) -> PathTestResponse:
    """
    Ejecuta una plantilla en vivo contra un mundo.

    v3 — flujo interno ajustado (spec §v3.4.1):
    1. Obtener plantilla → 404.
    2. Obtener world → 404.
    3. NUEVO v3: _ensure_session(world_id) → login on-demand idempotente.
       → 404 si no hay cuenta; 401 si Fernet/login falla; 500 si error inesperado.
    4. Decidir si hay WorldAgent en RUNNING:
       4a. Si sí → usar WorldAgent.execute_path_test (serialización con su lock).
       4b. Si no → usar execute_path_test_standalone con lock ad-hoc.
    5. Buscar instancia ya clonada (find_destination_by_template).
       5a. Si existe → usar path[path_index]. NO borrar.
       5b. Si no → clonar temporalmente con label="[TEST TEMPORAL]".
    6. Obtener NavigationPath real de BD [path_index]. → 422 si fuera de rango.
    7. Ejecutar el test con el helper adecuado.
    8. Si se creó instancia temporal → borrarla en try/finally.
    9. Devolver PathTestResult (mismo shape que EP-N14).

    HTTP 200 tanto si la ruta pasó (overall="ok") como si falló (overall="error").
    """
    from core.exceptions import BrowserBusyError  # import local para evitar ciclos
    from core.scheduling.world_agent import AgentState, execute_path_test_standalone

    rt_port = _get_rt_port(request)
    noise_db = _get_noise_db(request)

    template = await _require_template(rt_port, template_id)
    world = await _require_world(request, body.world_id)

    # v3: ensure_session — login on-demand idempotente
    session_registry = getattr(request.app.state, "world_runtime_port", None)
    accounts_db = _get_account_db(request)
    fernet = getattr(request.app.state, "fernet", None)

    await _ensure_session(body.world_id, session_registry, accounts_db, fernet)

    # v3: decidir qué helper usar
    agents: dict = getattr(request.app.state, "world_agents", {})
    agent = agents.get(body.world_id)
    use_agent = (
        agent is not None
        and agent.state == AgentState.RUNNING
        and agent._session_active()
    )

    # Paso 5: buscar instancia ya clonada
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
            frequency_weight=1.0,
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
        # Paso 6: obtener NavigationPath real de BD
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

        # El test de plantilla SIEMPRE es atómico: forzamos el origen del path al id de
        # ESTA plantilla para que el motor resuelva la cadena COMPLETA (raíz→hoja) con
        # resolve_origin_chain(template.id). Para una ruta raíz (origen guardado "ANY"),
        # la cadena resuelta es solo su propio clic. Evita el RuntimeError "no soporta
        # rutas v1 clásicas" que saltaba cuando path.origin no empezaba por "ROUTE_TEMPLATE:".
        path.origin = f"ROUTE_TEMPLATE:{template.id}"

        # Paso 7: ejecutar el test
        try:
            if use_agent:
                # 4a: usar WorldAgent (serializa con su lock interno)
                report = await agent.execute_path_test(path)
            else:
                # 4b: sin WorldAgent — usar standalone con lock ad-hoc
                browser = session_registry.get_browser(body.world_id)
                if browser is None:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="No se pudo obtener el browser activo tras ensure_session.",
                    )
                ad_hoc_lock = asyncio.Lock()
                # world_server para la verificación de arranque en frío (ColdStartAbortError)
                world_server = getattr(world, "server", "")
                report = await execute_path_test_standalone(
                    browser=browser,
                    path=path,
                    lock=ad_hoc_lock,
                    world_id=body.world_id,
                    world_server=world_server,
                    route_template_db=rt_port,
                )
        except BrowserBusyError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "El browser está ocupado con otra tarea. "
                    "Espera a que finalice e inténtalo de nuevo."
                ),
            )
        except RuntimeError as exc:
            logger.error(
                "execute_path_test RT10 mundo %d: RuntimeError: %s", body.world_id, exc
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error interno del servidor.",
            ) from exc
        except HTTPException:
            raise
        except Exception:
            logger.exception(
                "execute_path_test RT10 mundo %d: error inesperado", body.world_id
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error interno del servidor.",
            )

    finally:
        # Paso 8: borrar instancia temporal siempre (incluso si hubo excepción)
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


# ---------------------------------------------------------------------------
# EP-RT12 — DELETE /worlds/{world_id}/session (v3 NUEVO)
# ---------------------------------------------------------------------------

@router.delete(
    "/worlds/{world_id}/session",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="EP-RT12 — Cerrar sesión Chrome de un mundo",
)
async def close_world_session(
    request: Request,
    world_id: int = Path(..., ge=1),
) -> None:
    """
    Cierra la sesión Chrome de un mundo desde cualquier contexto (incluyendo
    el panel global /rutas), sin necesidad de que haya un WorldAgent activo.

    Idempotente: si no hay sesión activa, devuelve 204 igualmente.
    404 si world_id no existe en BD (para evitar operaciones sobre mundos fantasma).

    Reutiliza session_registry.close_session(world_id) (alias de logout).
    Spec route-templates-developer-portal.md §v3.4.2.
    """
    # Verificar que el mundo existe en BD
    await _require_world(request, world_id)  # 404 si no existe

    session_registry = getattr(request.app.state, "world_runtime_port", None)
    if session_registry is None:
        # No hay registry: no hay sesión que cerrar → idempotente
        return

    try:
        await session_registry.close_session(world_id)
    except Exception:
        logger.warning(
            "EP-RT12: error cerrando sesión Chrome para world_id=%d", world_id
        )
        # Idempotente: no relanzar la excepción
