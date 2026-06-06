"""
Router FastAPI para Ruido Humano de Navegación.

Endpoints (sin prefijo /api — el proxy de Vite lo retira):

  EP-N01  GET    /worlds/{id}/noise/config                          — leer config de ruido
  EP-N02  PUT    /worlds/{id}/noise/config                          — PATCH config de ruido
  EP-N03  GET    /worlds/{id}/noise/destinations                    — listar destinos
  EP-N04  POST   /worlds/{id}/noise/destinations                    — crear destino (201)
  EP-N05  PUT    /worlds/{id}/noise/destinations/{dest_id}          — PATCH destino
  EP-N06  DELETE /worlds/{id}/noise/destinations/{dest_id}          — borrar destino (204)
  EP-N07  GET    /worlds/{id}/noise/destinations/{dest_id}/paths     — listar rutas
  EP-N08  POST   /worlds/{id}/noise/destinations/{dest_id}/paths     — crear ruta (201)
  EP-N09  PUT    /worlds/{id}/noise/paths/{path_id}                 — PATCH ruta
  EP-N10  DELETE /worlds/{id}/noise/paths/{path_id}                 — borrar ruta (204)
  EP-N11  POST   /worlds/{id}/noise/derive-selector                 — derivar selector CSS (preview)
  EP-N12  GET    /worlds/{id}/noise/origins                         — listar anclas semilla
  EP-N13  POST   /worlds/{id}/noise/refresh-villages                — refrescar aldeas del village-switcher
  EP-N14  POST   /worlds/{id}/noise/paths/{path_id}/test            — probar ruta de navegación en vivo

Sin Accept-Language: no devuelven texto localizado.
Cache-Control: no-store en GETs de config (cambia frecuentemente).
Validación cross-world: si dest/path no pertenece al world → 404 (no 403).

Spec human-sessions.md §8 (v2.2 — EP-N01 a EP-N10).
Spec noise-path-wizard.md §8 (EP-N11, EP-N12, EP-N13 — NUEVOS).
Spec noise-path-wizard.md §16 (EP-N14 — test en vivo de ruta de navegación).
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response, status
from pydantic import BaseModel, Field, model_validator

from core.entities.noise import (
    NavigationOrigin,
    NavigationPath,
    NavigationStep,
    NoiseAction,
    NoiseConfig,
    NoiseDestination,
    ORIGIN_PATHS,
)
from core.use_cases.derive_selector import DeriveSelectorResult, derive_selector

logger = logging.getLogger(__name__)

router = APIRouter(tags=["noise"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_noise_db(request: Request):
    """Extrae noise_db del app.state."""
    noise_db = getattr(request.app.state, "noise_db_port", None)
    if noise_db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        )
    return noise_db


def _get_account_db(request: Request):
    """Extrae db_port del app.state (para verificar existencia del mundo)."""
    db = getattr(request.app.state, "db_port", None)
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        )
    return db


async def _verify_world_exists(request: Request, world_id: int) -> None:
    """Devuelve 404 si el mundo no existe."""
    db = _get_account_db(request)
    world = await db.get_world(world_id)
    if world is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mundo no encontrado.",
        )


async def _verify_destination_belongs_to_world(
    noise_db, dest_id: int, world_id: int
) -> NoiseDestination:
    """
    Devuelve el destino si existe y pertenece al mundo.
    404 si no existe o pertenece a otro mundo (no 403 — spec).
    """
    dest = await noise_db.get_destination(dest_id)
    if dest is None or dest.world_id != world_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Destino no encontrado.",
        )
    return dest


async def _verify_path_belongs_to_world(
    noise_db, path_id: int, world_id: int
) -> NavigationPath:
    """
    Devuelve la ruta si existe y su destino pertenece al mundo.
    404 si no existe o el destino es de otro mundo.
    """
    path = await noise_db.get_path(path_id)
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ruta no encontrada.",
        )
    dest = await noise_db.get_destination(path.destination_id)
    if dest is None or dest.world_id != world_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ruta no encontrada.",
        )
    return path


# ---------------------------------------------------------------------------
# Modelos Pydantic
# ---------------------------------------------------------------------------

class NoiseConfigResponse(BaseModel):
    """
    Respuesta EP-N01 / EP-N02.

    Campos v2 (intervalo en segundos). Los campos deprecated *_req_per_hour_*
    se eliminan del contrato (spec noise-frequency-and-destination-weight.md §8.1).
    """
    world_id: int
    noise_enabled: bool
    hardcore_interval_min_seconds: int
    hardcore_interval_max_seconds: int
    passive_interval_min_seconds: int
    passive_interval_max_seconds: int
    dwell_min_seconds: float
    dwell_max_seconds: float


# Piso de intervalo en la API (igual que en la entidad — defensa en profundidad).
# RN-FW02 (GUARDIAN): mínimo 30 s.
_API_MIN_INTERVAL = 30


class NoiseConfigUpdateRequest(BaseModel):
    """
    Body EP-N02 (PATCH parcial).

    Todos los campos son opcionales; al menos uno debe estar presente.
    La validación cruzada mín≤máx se hace en el handler (§10) para el caso de PATCH
    parcial donde solo llega uno de los dos (se combina con el valor actual de BD).

    RN-FW02 (GUARDIAN): piso de 30 s en los campos de intervalo.
    """
    noise_enabled: Optional[bool] = None
    hardcore_interval_min_seconds: Optional[int] = Field(default=None, ge=_API_MIN_INTERVAL)
    hardcore_interval_max_seconds: Optional[int] = Field(default=None, ge=_API_MIN_INTERVAL)
    passive_interval_min_seconds: Optional[int] = Field(default=None, ge=_API_MIN_INTERVAL)
    passive_interval_max_seconds: Optional[int] = Field(default=None, ge=_API_MIN_INTERVAL)
    dwell_min_seconds: Optional[float] = Field(default=None, ge=0)
    dwell_max_seconds: Optional[float] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "NoiseConfigUpdateRequest":
        if all(v is None for v in [
            self.noise_enabled,
            self.hardcore_interval_min_seconds,
            self.hardcore_interval_max_seconds,
            self.passive_interval_min_seconds,
            self.passive_interval_max_seconds,
            self.dwell_min_seconds,
            self.dwell_max_seconds,
        ]):
            raise ValueError(
                "El body debe contener al menos uno de los campos de configuración."
            )
        return self

    @model_validator(mode="after")
    def check_ranges_when_both_present(self) -> "NoiseConfigUpdateRequest":
        """
        Validación cruzada mín≤máx cuando AMBOS campos del par están en el body.
        Si solo llega uno, la validación se completa en el handler contra BD.
        """
        if (self.hardcore_interval_min_seconds is not None
                and self.hardcore_interval_max_seconds is not None
                and self.hardcore_interval_max_seconds < self.hardcore_interval_min_seconds):
            raise ValueError(
                "hardcore_interval_max_seconds debe ser >= hardcore_interval_min_seconds."
            )
        if (self.passive_interval_min_seconds is not None
                and self.passive_interval_max_seconds is not None
                and self.passive_interval_max_seconds < self.passive_interval_min_seconds):
            raise ValueError(
                "passive_interval_max_seconds debe ser >= passive_interval_min_seconds."
            )
        if (self.dwell_min_seconds is not None
                and self.dwell_max_seconds is not None
                and self.dwell_max_seconds < self.dwell_min_seconds):
            raise ValueError(
                "dwell_max_seconds debe ser >= dwell_min_seconds."
            )
        return self


class NoiseDestinationResponse(BaseModel):
    """
    Respuesta EP-N03/N04/N05.

    El campo interno frequency_weight se expone como navigation_weight en el contrato
    (spec noise-frequency-and-destination-weight.md §8.3–8.5, RN-FW06).

    Delta EP-N03/EP-N04 (route-templates-developer-portal.md §8.12):
    template_id (int | null) añadido al response. Null si creado a mano;
    int si fue clonado desde una plantilla. Campo nullable → retrocompatible.

    Delta route-categories-dynamic.md C-02:
    category_slug (str) reemplaza el campo category (enum string).
    """
    id: int
    world_id: int
    url_pattern: str
    label: str
    category_slug: str
    navigation_weight: float   # alias de frequency_weight — RN-FW06
    is_safe: bool
    is_dead: bool
    consecutive_failures_count: int
    template_id: Optional[int] = None  # NEW — Delta §8.12 EP-N03
    created_at: Optional[str] = None
    last_used_at: Optional[str] = None


class CreateDestinationRequest(BaseModel):
    """
    Body EP-N04.
    navigation_weight: alias de frequency_weight. Rango [0.1, 5.0] — GUARDIAN RN-FW07.

    Delta (route-templates-developer-portal.md §8.12):
    template_id: campo opcional para crear un destino con referencia explícita a una plantilla.
    Retrocompatible: default None, los clientes que no lo envían no cambian de comportamiento.

    Delta route-categories-dynamic.md §8.4:
    category_slug (str, default 'uncategorized') reemplaza category: NoiseCategory (enum).
    """
    url_pattern: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    category_slug: str = Field(default="uncategorized", min_length=1)
    navigation_weight: float = Field(
        default=1.0,
        ge=0.1,
        le=5.0,
        description="Peso de navegación. Rango [0.1, 5.0] — anti-detección (RN-FW07).",
    )
    is_safe: bool = True
    template_id: Optional[int] = None  # NEW — Delta §8.12 EP-N04


class UpdateDestinationRequest(BaseModel):
    """
    Body EP-N05 (PATCH parcial).
    navigation_weight: alias de frequency_weight. Rango [0.1, 5.0] — GUARDIAN RN-FW07.

    Delta route-categories-dynamic.md §8.4:
    category_slug (str) añadido como campo editable (se elimina la restricción de inmutabilidad).
    """
    label: Optional[str] = Field(default=None, min_length=1)
    navigation_weight: Optional[float] = Field(
        default=None,
        ge=0.1,
        le=5.0,
        description="Peso de navegación. Rango [0.1, 5.0] — anti-detección (RN-FW07).",
    )
    is_safe: Optional[bool] = None
    category_slug: Optional[str] = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "UpdateDestinationRequest":
        if all(v is None for v in [self.label, self.navigation_weight, self.is_safe, self.category_slug]):
            raise ValueError(
                "El body debe contener al menos uno de: label, navigation_weight, is_safe, category_slug."
            )
        return self


class NavigationStepRequest(BaseModel):
    step_order: int = Field(..., ge=0)
    action: NoiseAction
    selector: str = Field(..., min_length=1)
    value: str = ""
    delay_min_ms: int = Field(default=500, ge=0)
    delay_max_ms: int = Field(default=900, ge=0)
    expected_url_after_click: Optional[str] = Field(
        default=None,
        description=(
            "URL o path esperado tras el click. Si está presente, el WorldAgent "
            "verificará por containment que la URL actual contiene este valor. "
            "Solo aplica a pasos de tipo CLICK."
        ),
    )

    @model_validator(mode="after")
    def check_delay_range(self) -> "NavigationStepRequest":
        if self.delay_max_ms < self.delay_min_ms:
            raise ValueError("delay_max_ms debe ser >= delay_min_ms.")
        # ANTI-DETECCION (Capa 3): defensa en profundidad en el borde de la API.
        # Mismos límites que core.entities.noise.NavigationStep — un step sobre
        # Travian no puede encadenarse sin delay humano ni quedar "lento por miedo".
        from core.entities.noise import NavigationStep  # noqa: PLC0415
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

    @model_validator(mode="after")
    def validate_selector_not_text_based(self) -> "NavigationStepRequest":
        """EC-NP14: rechazar selectores por texto visible (no estructurales)."""
        sel = self.selector
        if ":contains(" in sel or "text()" in sel:
            raise ValueError(
                "El selector no puede usar selección por texto visible (:contains, text()). "
                "Usa selectores CSS estructurales (id, atributos, clases semánticas)."
            )
        return self


class NavigationStepResponse(BaseModel):
    id: Optional[int] = None
    path_id: Optional[int] = None
    step_order: int
    action: str
    selector: str
    value: str
    delay_min_ms: int
    delay_max_ms: int
    expected_url_after_click: Optional[str] = None


class NavigationPathResponse(BaseModel):
    id: int
    destination_id: int
    origin: str
    label: str
    is_active: bool
    is_dead: bool = False
    consecutive_failures_count: int = 0
    steps: list[NavigationStepResponse]


class CreatePathRequest(BaseModel):
    origin: str = Field(
        ...,
        min_length=1,
        description=(
            "Origen de la ruta. Puede ser un valor del enum NavigationOrigin "
            "(ej. 'STATISTICS') o una cadena 'VILLAGE_<data_id>' para anclas por-aldea."
        ),
    )
    label: str = Field(..., min_length=1)
    steps: list[NavigationStepRequest] = Field(..., min_length=1)


class UpdatePathRequest(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1)
    is_active: Optional[bool] = None
    steps: Optional[list[NavigationStepRequest]] = None  # None = conservar; [] = error

    @model_validator(mode="after")
    def steps_cannot_be_empty_list(self) -> "UpdatePathRequest":
        if self.steps is not None and len(self.steps) == 0:
            raise ValueError(
                "steps=[] no está permitido. Una ruta debe tener al menos un paso. "
                "Para eliminar la ruta, usa DELETE."
            )
        return self


# ---------------------------------------------------------------------------
# Modelos EP-N11 — derive-selector
# ---------------------------------------------------------------------------

class DeriveSelectorRequest(BaseModel):
    outer_html: str = Field(
        ...,
        min_length=1,
        description=(
            "HTML completo del elemento (outerHTML). Obtener con "
            "'Inspeccionar → Copiar outerHTML' en DevTools. Máximo 50 KB."
        ),
    )


class DeriveSelectorResponse(BaseModel):
    selector: str = Field(description="Selector CSS estructural recomendado.")
    is_unique: bool = Field(
        description=(
            "True si el selector se considera único en el fragmento analizado "
            "(heurístico — no garantiza unicidad en el documento real de Travian)."
        )
    )
    priority_level: int = Field(
        ge=1,
        le=9,
        description="Nivel de prioridad del algoritmo usado (1=id, 9=fallback). Ver RN-NP05.",
    )
    method: str = Field(
        description=(
            "Método de derivación: 'id', 'name', 'gid', 'href_exact', "
            "'href_partial', 'data_attr', 'class_combo', 'context_combo', 'fallback'."
        )
    )
    warning: Optional[str] = Field(
        default=None,
        description="Aviso si is_unique=False o si el selector tiene limitaciones conocidas.",
    )
    alternatives: list[str] = Field(
        default_factory=list,
        description="Lista de selectores alternativos (puede estar vacía).",
    )


# ---------------------------------------------------------------------------
# Modelos EP-N12 — origins
# ---------------------------------------------------------------------------

class GenericOriginItem(BaseModel):
    value: str = Field(description="Valor del enum NavigationOrigin (ej. 'STATISTICS').")
    label: str = Field(description="Etiqueta descriptiva en español.")
    path: Optional[str] = Field(
        default=None,
        description="Ruta relativa de Travian ('/dorf1.php', etc.). Null para ANY.",
    )


class VillageOriginItem(BaseModel):
    value: str = Field(description="Cadena 'VILLAGE_<data_id>' para usar como origin.")
    label: str = Field(description="Nombre de la aldea.")
    data_id: int = Field(description="Identificador de la aldea (newdid en Travian).")
    x: int = Field(description="Coordenada X de la aldea.")
    y: int = Field(description="Coordenada Y de la aldea.")
    path: str = Field(description="Ruta relativa con newdid: '/dorf1.php?newdid=<data_id>'.")


class OriginsResponse(BaseModel):
    generic_origins: list[GenericOriginItem] = Field(
        description="Las 9 anclas genéricas fijas del sistema."
    )
    village_origins: list[VillageOriginItem] = Field(
        description="Anclas por-aldea generadas desde la tabla villages del mundo."
    )
    villages_loaded: bool = Field(
        description=(
            "True si la tabla villages tiene datos para este mundo. "
            "False si está vacía (ejecutar EP-N13 para poblarla)."
        )
    )


# ---------------------------------------------------------------------------
# Modelos EP-N13 — refresh-villages
# ---------------------------------------------------------------------------

class VillageItem(BaseModel):
    data_id: int
    name: str
    x: int
    y: int


class RefreshVillagesResponse(BaseModel):
    villages_found: int = Field(description="Número de aldeas encontradas y upserteadas.")
    villages_data: list[VillageItem] = Field(
        description="Lista de aldeas actualizadas."
    )


# ---------------------------------------------------------------------------
# Modelos EP-N14 — test de ruta en vivo
# ---------------------------------------------------------------------------

class PathTestStepResultResponse(BaseModel):
    """Resultado de un paso individual en el test de la ruta."""
    step_order: int = Field(description="Índice del paso (igual que NavigationStep.step_order).")
    action: str = Field(description="Tipo de acción ejecutada (CLICK, WAIT_FOR_SELECTOR, etc.).")
    selector: str = Field(description="Selector CSS del paso.")
    status: str = Field(description='"ok" si el paso se ejecutó con éxito; "error" si falló.')
    reason: str | None = Field(
        default=None,
        description="Motivo del fallo. None si status=='ok'.",
    )
    current_url: str | None = Field(
        default=None,
        description="URL del tab TRAS ejecutar el paso. None si no se pudo leer.",
    )


class PathTestResponse(BaseModel):
    """Reporte de una ejecución de test de ruta de navegación en vivo."""
    overall: str = Field(
        description='"ok" si todos los pasos tuvieron éxito; "error" si alguno falló.',
    )
    aborted_at_step: int | None = Field(
        default=None,
        description="step_order del paso donde abortó el test. None si overall=='ok'.",
    )
    anchor_navigated_to: str | None = Field(
        default=None,
        description="URL del ancla de origen antes del primer paso. None si origin=='ANY'.",
    )
    steps: list[PathTestStepResultResponse] = Field(
        default=[],
        description="Resultados de los pasos ejecutados (solo los intentados).",
    )
    browser_note: str = Field(
        default="El browser queda en la última página visitada durante el test.",
        description="Aviso fijo sobre el estado del browser tras el test.",
    )


# ---------------------------------------------------------------------------
# Helpers de conversión entidad → response
# ---------------------------------------------------------------------------

def _dest_to_response(dest: NoiseDestination) -> NoiseDestinationResponse:
    return NoiseDestinationResponse(
        id=dest.id,
        world_id=dest.world_id,
        url_pattern=dest.url_pattern,
        label=dest.label,
        category_slug=dest.category_slug,
        navigation_weight=dest.frequency_weight,   # alias RN-FW06
        is_safe=dest.is_safe,
        is_dead=dest.is_dead,
        consecutive_failures_count=dest.consecutive_failures_count,
        template_id=getattr(dest, "template_id", None),  # Delta §8.12 EP-N03
        created_at=dest.created_at.isoformat() if dest.created_at else None,
        last_used_at=dest.last_used_at.isoformat() if dest.last_used_at else None,
    )


def _step_to_response(step: NavigationStep) -> NavigationStepResponse:
    return NavigationStepResponse(
        id=step.id,
        path_id=step.path_id,
        step_order=step.step_order,
        action=step.action.value,
        selector=step.selector,
        value=step.value,
        delay_min_ms=step.delay_min_ms,
        delay_max_ms=step.delay_max_ms,
        expected_url_after_click=step.expected_url_after_click,
    )


def _path_to_response(path: NavigationPath) -> NavigationPathResponse:
    # Guard str/enum: origin puede ser un str directo (nuevo) o un NavigationOrigin (legacy).
    # Con el cambio de tipo en la entidad, path.origin es siempre str; pero el adaptador
    # legacy podría devolver un NavigationOrigin si no se ha actualizado aún.
    origin_str = path.origin if isinstance(path.origin, str) else path.origin.value
    return NavigationPathResponse(
        id=path.id,
        destination_id=path.destination_id,
        origin=origin_str,
        label=path.label,
        is_active=path.is_active,
        is_dead=path.is_dead,
        consecutive_failures_count=path.consecutive_failures_count,
        steps=[_step_to_response(s) for s in path.steps],
    )


def _config_to_response(config: NoiseConfig) -> NoiseConfigResponse:
    return NoiseConfigResponse(
        world_id=config.world_id,
        noise_enabled=config.noise_enabled,
        hardcore_interval_min_seconds=config.hardcore_interval_min_seconds,
        hardcore_interval_max_seconds=config.hardcore_interval_max_seconds,
        passive_interval_min_seconds=config.passive_interval_min_seconds,
        passive_interval_max_seconds=config.passive_interval_max_seconds,
        dwell_min_seconds=config.dwell_min_seconds,
        dwell_max_seconds=config.dwell_max_seconds,
    )


def _steps_from_request(steps_req: list[NavigationStepRequest]) -> list[NavigationStep]:
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


# ---------------------------------------------------------------------------
# EP-N01 — GET /worlds/{id}/noise/config
# ---------------------------------------------------------------------------

@router.get(
    "/worlds/{world_id}/noise/config",
    response_model=NoiseConfigResponse,
    summary="EP-N01 — Leer configuración de ruido del mundo",
)
async def get_noise_config(
    request: Request,
    response: Response,
    world_id: int = Path(..., ge=1),
) -> NoiseConfigResponse:
    """
    Devuelve la configuración de ruido del mundo.
    Si el mundo no tiene configuración previa, devuelve los valores por defecto
    y los persiste en BD (get_or_create).
    Cache-Control: no-store (la config cambia frecuentemente).
    """
    await _verify_world_exists(request, world_id)
    noise_db = _get_noise_db(request)

    try:
        config = await noise_db.get_or_create_noise_config(world_id)
    except Exception as exc:
        logger.exception("Error leyendo noise config para mundo %d", world_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        ) from exc

    response.headers["Cache-Control"] = "no-store"
    return _config_to_response(config)


# ---------------------------------------------------------------------------
# EP-N02 — PUT /worlds/{id}/noise/config
# ---------------------------------------------------------------------------

@router.put(
    "/worlds/{world_id}/noise/config",
    response_model=NoiseConfigResponse,
    summary="EP-N02 — Actualizar configuración de ruido (PATCH parcial)",
)
async def update_noise_config(
    request: Request,
    body: NoiseConfigUpdateRequest,
    world_id: int = Path(..., ge=1),
) -> NoiseConfigResponse:
    """
    PATCH parcial de la configuración de ruido.
    Solo actualiza los campos presentes; el resto conserva su valor.
    """
    await _verify_world_exists(request, world_id)
    noise_db = _get_noise_db(request)

    try:
        existing = await noise_db.get_or_create_noise_config(world_id)
    except Exception as exc:
        logger.exception("Error leyendo noise config para mundo %d", world_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        ) from exc

    # PATCH: resolver valores finales combinando body + estado actual de BD
    new_hc_min = (
        body.hardcore_interval_min_seconds
        if body.hardcore_interval_min_seconds is not None
        else existing.hardcore_interval_min_seconds
    )
    new_hc_max = (
        body.hardcore_interval_max_seconds
        if body.hardcore_interval_max_seconds is not None
        else existing.hardcore_interval_max_seconds
    )
    new_pa_min = (
        body.passive_interval_min_seconds
        if body.passive_interval_min_seconds is not None
        else existing.passive_interval_min_seconds
    )
    new_pa_max = (
        body.passive_interval_max_seconds
        if body.passive_interval_max_seconds is not None
        else existing.passive_interval_max_seconds
    )

    # Validación cruzada PATCH parcial (§10): si solo llegó uno del par, verificar
    # contra el valor actual de BD. Cubre el caso EC-FW08 del spec.
    if new_hc_max < new_hc_min:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="hardcore_interval_max_seconds debe ser >= hardcore_interval_min_seconds.",
        )
    if new_pa_max < new_pa_min:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="passive_interval_max_seconds debe ser >= passive_interval_min_seconds.",
        )

    try:
        updated = NoiseConfig(
            world_id=world_id,
            noise_enabled=(
                body.noise_enabled if body.noise_enabled is not None
                else existing.noise_enabled
            ),
            hardcore_interval_min_seconds=new_hc_min,
            hardcore_interval_max_seconds=new_hc_max,
            passive_interval_min_seconds=new_pa_min,
            passive_interval_max_seconds=new_pa_max,
            dwell_min_seconds=(
                body.dwell_min_seconds if body.dwell_min_seconds is not None
                else existing.dwell_min_seconds
            ),
            dwell_max_seconds=(
                body.dwell_max_seconds if body.dwell_max_seconds is not None
                else existing.dwell_max_seconds
            ),
        )
    except ValueError as exc:
        # La entidad puede lanzar ValueError si algún campo < 30 s (piso guardian)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    try:
        result = await noise_db.update_noise_config(updated)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Error actualizando noise config para mundo %d", world_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        ) from exc

    return _config_to_response(result)


# ---------------------------------------------------------------------------
# EP-N03 — GET /worlds/{id}/noise/destinations
# ---------------------------------------------------------------------------

@router.get(
    "/worlds/{world_id}/noise/destinations",
    response_model=list[NoiseDestinationResponse],
    summary="EP-N03 — Listar destinos de ruido del mundo",
)
async def list_destinations(
    request: Request,
    world_id: int = Path(..., ge=1),
    category_slug: Optional[str] = Query(default=None, description="Filtrar por slug de categoría. Slug inexistente → [] (filtro silencioso, C-01)."),
    include_dead: bool = Query(default=False),
    include_unsafe: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[NoiseDestinationResponse]:
    """
    Lista los destinos de navegación de ruido del mundo.
    Filtros: category_slug (string libre), include_dead, include_unsafe, limit, offset.
    Slug inexistente en category_slug → 200 [] (filtro silencioso, C-01).
    """
    await _verify_world_exists(request, world_id)
    noise_db = _get_noise_db(request)

    try:
        destinations = await noise_db.list_destinations(
            world_id,
            category_slug=category_slug,
            include_dead=include_dead,
            include_unsafe=include_unsafe,
        )
    except Exception as exc:
        logger.exception("Error listando destinos de ruido para mundo %d", world_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        ) from exc

    # Paginación simple en memoria (el catálogo de destinos es pequeño)
    paginated = destinations[offset: offset + limit]
    return [_dest_to_response(d) for d in paginated]


# ---------------------------------------------------------------------------
# EP-N04 — POST /worlds/{id}/noise/destinations
# ---------------------------------------------------------------------------

@router.post(
    "/worlds/{world_id}/noise/destinations",
    response_model=NoiseDestinationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="EP-N04 — Crear destino de ruido",
)
async def create_destination(
    request: Request,
    body: CreateDestinationRequest,
    world_id: int = Path(..., ge=1),
) -> NoiseDestinationResponse:
    """
    Crea un nuevo destino de navegación de ruido para el mundo.
    Valida URL (RN-HS23 endurecida): solo http/https o rutas relativas que
    comiencen por '/'; el dominio debe pertenecer al servidor del mundo.
    """
    await _verify_world_exists(request, world_id)
    noise_db = _get_noise_db(request)

    # Validar que category_slug existe (C-03)
    cat_port = getattr(request.app.state, "route_category_port", None)
    if cat_port is not None:
        cat = await cat_port.get_category(body.category_slug)
        if cat is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Categoría no encontrada.",
            )

    try:
        dest = await noise_db.create_destination(
            world_id=world_id,
            url_pattern=body.url_pattern,
            label=body.label,
            category_slug=body.category_slug,
            frequency_weight=body.navigation_weight,   # alias: navigation_weight → frequency_weight
            is_safe=body.is_safe,
            template_id=body.template_id,  # Delta §8.12 EP-N04 — None si no se envía
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Error creando destino de ruido para mundo %d", world_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        ) from exc

    return _dest_to_response(dest)


# ---------------------------------------------------------------------------
# EP-N05 — PUT /worlds/{id}/noise/destinations/{dest_id}
# ---------------------------------------------------------------------------

@router.put(
    "/worlds/{world_id}/noise/destinations/{dest_id}",
    response_model=NoiseDestinationResponse,
    summary="EP-N05 — Actualizar destino de ruido (PATCH parcial)",
)
async def update_destination(
    request: Request,
    body: UpdateDestinationRequest,
    world_id: int = Path(..., ge=1),
    dest_id: int = Path(..., ge=1),
) -> NoiseDestinationResponse:
    """
    PATCH parcial del destino. url_pattern es inmutable; category_slug SÍ es editable.
    Verifica que el destino pertenece al mundo (404 si no).
    """
    await _verify_world_exists(request, world_id)
    noise_db = _get_noise_db(request)
    await _verify_destination_belongs_to_world(noise_db, dest_id, world_id)

    # Validar category_slug si se envía (C-03)
    if body.category_slug is not None:
        cat_port = getattr(request.app.state, "route_category_port", None)
        if cat_port is not None:
            cat = await cat_port.get_category(body.category_slug)
            if cat is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Categoría no encontrada.",
                )

    try:
        updated = await noise_db.update_destination(
            dest_id=dest_id,
            label=body.label,
            frequency_weight=body.navigation_weight,   # alias: navigation_weight → frequency_weight
            is_safe=body.is_safe,
            category_slug=body.category_slug,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Error actualizando destino %d", dest_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        ) from exc

    return _dest_to_response(updated)


# ---------------------------------------------------------------------------
# EP-N06 — DELETE /worlds/{id}/noise/destinations/{dest_id}
# ---------------------------------------------------------------------------

@router.delete(
    "/worlds/{world_id}/noise/destinations/{dest_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="EP-N06 — Borrar destino de ruido",
)
async def delete_destination(
    request: Request,
    world_id: int = Path(..., ge=1),
    dest_id: int = Path(..., ge=1),
) -> None:
    """
    Borra el destino y en cascada sus rutas y pasos.
    Verifica que el destino pertenece al mundo (404 si no).
    """
    await _verify_world_exists(request, world_id)
    noise_db = _get_noise_db(request)
    await _verify_destination_belongs_to_world(noise_db, dest_id, world_id)

    try:
        await noise_db.delete_destination(dest_id)
    except Exception as exc:
        logger.exception("Error borrando destino %d", dest_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        ) from exc


# ---------------------------------------------------------------------------
# EP-N07 — GET /worlds/{id}/noise/destinations/{dest_id}/paths
# ---------------------------------------------------------------------------

@router.get(
    "/worlds/{world_id}/noise/destinations/{dest_id}/paths",
    response_model=list[NavigationPathResponse],
    summary="EP-N07 — Listar rutas de un destino",
)
async def list_paths(
    request: Request,
    world_id: int = Path(..., ge=1),
    dest_id: int = Path(..., ge=1),
) -> list[NavigationPathResponse]:
    """
    Lista todas las rutas del destino, con sus pasos ordenados por step_order ASC.
    Verifica que el destino pertenece al mundo (404 si no).
    """
    await _verify_world_exists(request, world_id)
    noise_db = _get_noise_db(request)
    await _verify_destination_belongs_to_world(noise_db, dest_id, world_id)

    try:
        paths = await noise_db.list_paths(dest_id)
    except Exception as exc:
        logger.exception("Error listando rutas del destino %d", dest_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        ) from exc

    return [_path_to_response(p) for p in paths]


# ---------------------------------------------------------------------------
# EP-N08 — POST /worlds/{id}/noise/destinations/{dest_id}/paths
# ---------------------------------------------------------------------------

@router.post(
    "/worlds/{world_id}/noise/destinations/{dest_id}/paths",
    response_model=NavigationPathResponse,
    status_code=status.HTTP_201_CREATED,
    summary="EP-N08 — Crear ruta de navegación para un destino",
)
async def create_path(
    request: Request,
    body: CreatePathRequest,
    world_id: int = Path(..., ge=1),
    dest_id: int = Path(..., ge=1),
) -> NavigationPathResponse:
    """
    Crea una nueva ruta con sus pasos para el destino indicado.
    Verifica que el destino pertenece al mundo (404 si no).
    """
    await _verify_world_exists(request, world_id)
    noise_db = _get_noise_db(request)
    await _verify_destination_belongs_to_world(noise_db, dest_id, world_id)

    steps = _steps_from_request(body.steps)

    try:
        path = await noise_db.create_path(
            dest_id=dest_id,
            origin=body.origin,  # ya es str — el adaptador llama a _validate_origin
            label=body.label,
            steps=steps,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Error creando ruta para destino %d", dest_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        ) from exc

    return _path_to_response(path)


# ---------------------------------------------------------------------------
# EP-N09 — PUT /worlds/{id}/noise/paths/{path_id}
# ---------------------------------------------------------------------------

@router.put(
    "/worlds/{world_id}/noise/paths/{path_id}",
    response_model=NavigationPathResponse,
    summary="EP-N09 — Actualizar ruta de navegación (híbrido PATCH/reemplazo de steps)",
)
async def update_path(
    request: Request,
    body: UpdatePathRequest,
    world_id: int = Path(..., ge=1),
    path_id: int = Path(..., ge=1),
) -> NavigationPathResponse:
    """
    Actualización híbrida de una ruta:
    - label / is_active: PATCH parcial.
    - steps: si se pasa → reemplazo atómico; si None → se conservan.
    Verifica que la ruta pertenece al mundo (404 si no).
    """
    await _verify_world_exists(request, world_id)
    noise_db = _get_noise_db(request)
    await _verify_path_belongs_to_world(noise_db, path_id, world_id)

    steps = _steps_from_request(body.steps) if body.steps is not None else None

    try:
        path = await noise_db.update_path(
            path_id=path_id,
            label=body.label,
            is_active=body.is_active,
            steps=steps,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Error actualizando ruta %d", path_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        ) from exc

    return _path_to_response(path)


# ---------------------------------------------------------------------------
# EP-N10 — DELETE /worlds/{id}/noise/paths/{path_id}
# ---------------------------------------------------------------------------

@router.delete(
    "/worlds/{world_id}/noise/paths/{path_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="EP-N10 — Borrar ruta de navegación",
)
async def delete_path(
    request: Request,
    world_id: int = Path(..., ge=1),
    path_id: int = Path(..., ge=1),
) -> None:
    """
    Borra la ruta y en cascada sus pasos.
    Verifica que la ruta pertenece al mundo (404 si no).
    """
    await _verify_world_exists(request, world_id)
    noise_db = _get_noise_db(request)
    await _verify_path_belongs_to_world(noise_db, path_id, world_id)

    try:
        await noise_db.delete_path(path_id)
    except Exception as exc:
        logger.exception("Error borrando ruta %d", path_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        ) from exc


# ---------------------------------------------------------------------------
# EP-N11 — POST /worlds/{id}/noise/derive-selector
# ---------------------------------------------------------------------------

# Etiquetas legibles para el nivel de prioridad del algoritmo.
_ORIGIN_LABELS: dict[NavigationOrigin, str] = {
    NavigationOrigin.DORF1:              "Recursos (aldea activa)",
    NavigationOrigin.DORF2:              "Edificios (aldea activa)",
    NavigationOrigin.MAP:                "Mapa mundial",
    NavigationOrigin.STATISTICS:         "Estadísticas globales",
    NavigationOrigin.REPORTS:            "Reportes",
    NavigationOrigin.MESSAGES:           "Mensajes",
    NavigationOrigin.VILLAGE_STATISTICS: "Estadísticas de aldea",
    NavigationOrigin.OASIS_VIEW:         "Vista oasis en el mapa",
    NavigationOrigin.ANY:                "Cualquier página (sin ancla)",
}


@router.post(
    "/worlds/{world_id}/noise/derive-selector",
    response_model=DeriveSelectorResponse,
    summary="EP-N11 — Derivar selector CSS estructural desde outerHTML",
)
async def derive_selector_endpoint(
    request: Request,
    body: DeriveSelectorRequest,
    world_id: int = Path(..., ge=1),
) -> DeriveSelectorResponse:
    """
    Analiza el outerHTML de un elemento HTML y devuelve el mejor selector CSS
    estructural según la heurística priorizada (RN-NP05).

    No persiste nada. Es un endpoint de preview para el wizard de creación de rutas.

    El world_id es necesario para validar que el mundo existe; en v1 no se usa
    para la derivación del selector (pensado para validaciones futuras de dominio).

    Notas:
    - is_unique=True es heurístico: indica que el selector es estable según la
      heurística sobre el fragmento HTML proporcionado. No garantiza unicidad en
      el documento real de Travian.
    - La verificación definitiva de que el selector llegó al destino correcto se hace
      en runtime a través de expected_url_after_click.
    - Cache-Control: no-store (el resultado depende del outerHTML específico).
    """
    await _verify_world_exists(request, world_id)

    try:
        result: DeriveSelectorResult = derive_selector(body.outer_html)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Error derivando selector para mundo %d", world_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        ) from exc

    return DeriveSelectorResponse(
        selector=result.selector,
        is_unique=result.is_unique,
        priority_level=result.priority_level,
        method=result.method,
        warning=result.warning,
        alternatives=result.alternatives,
    )


# ---------------------------------------------------------------------------
# EP-N12 — GET /worlds/{id}/noise/origins
# ---------------------------------------------------------------------------

@router.get(
    "/worlds/{world_id}/noise/origins",
    response_model=OriginsResponse,
    summary="EP-N12 — Listar anclas semilla disponibles como origen de ruta",
)
async def get_noise_origins(
    request: Request,
    response: Response,
    world_id: int = Path(..., ge=1),
) -> OriginsResponse:
    """
    Devuelve las anclas semilla disponibles para usar como origen al crear rutas:

    - generic_origins: las 9 anclas genéricas fijas (constantes del sistema, no se
      borran ni editan). Siempre se devuelven las 9.
    - village_origins: una ancla por cada aldea en la tabla `villages` del mundo.
      Vacía si el parser del village-switcher nunca se ha ejecutado (villages_loaded=false).
    - villages_loaded: false si la tabla villages está vacía para este mundo. En ese caso
      el usuario puede ejecutar EP-N13 (POST refresh-villages) para poblarla.

    Cache-Control: no-store (village_origins cambia al ejecutar el parser).
    """
    await _verify_world_exists(request, world_id)
    noise_db = _get_noise_db(request)

    try:
        villages = await noise_db.get_villages_for_world(world_id)
    except Exception as exc:
        logger.exception("Error leyendo aldeas para mundo %d", world_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        ) from exc

    # Construir los 9 orígenes genéricos desde las constantes del dominio
    generic_origins = [
        GenericOriginItem(
            value=origin.value,
            label=_ORIGIN_LABELS[origin],
            path=ORIGIN_PATHS[origin] or None,  # ANY tiene "" → None en el response
        )
        for origin in NavigationOrigin
    ]

    # Construir las anclas por-aldea
    village_origins = [
        VillageOriginItem(
            value=f"VILLAGE_{v.data_id}",
            label=v.name,
            data_id=v.data_id,
            x=v.x,
            y=v.y,
            path=f"/dorf1.php?newdid={v.data_id}",
        )
        for v in villages
    ]

    response.headers["Cache-Control"] = "no-store"

    return OriginsResponse(
        generic_origins=generic_origins,
        village_origins=village_origins,
        villages_loaded=len(villages) > 0,
    )


# ---------------------------------------------------------------------------
# EP-N13 — POST /worlds/{id}/noise/refresh-villages
# ---------------------------------------------------------------------------

@router.post(
    "/worlds/{world_id}/noise/refresh-villages",
    response_model=RefreshVillagesResponse,
    summary="EP-N13 — Refrescar aldeas del village-switcher de Travian",
)
async def refresh_villages(
    request: Request,
    world_id: int = Path(..., ge=1),
) -> RefreshVillagesResponse:
    """
    Instruye al WorldAgent del mundo a ejecutar el parser del village-switcher
    de Travian y actualizar la tabla villages.

    Requisitos:
    - El mundo debe existir (404 si no).
    - El WorldAgent del mundo debe estar ACTIVO con una sesión de browser abierta.
      Si está DISCONNECTED o no existe, devuelve 409.

    Comportamiento:
    - Operación síncrona: espera a que el parser complete antes de responder.
    - El parser solo lee el DOM (tab.evaluate), no hace clicks ni navegación.
    - Las aldeas existentes se actualizan (UPSERT); las que ya no aparecen NO se borran
      (anti-detección: el bot no reacciona en caliente ante pérdidas de aldea).
    - Devuelve la lista de aldeas encontradas y upserteadas.

    Error 409: el WorldAgent está desconectado o no ha sido iniciado para este mundo.
    """
    await _verify_world_exists(request, world_id)

    # Verificar que hay un WorldAgent activo (no DISCONNECTED) para este mundo.
    # app.state.world_agents es el dict[world_id, WorldAgent] gestionado por farm.py.
    from core.scheduling.world_agent import AgentState  # import local para evitar ciclos
    agents: dict = getattr(request.app.state, "world_agents", {})
    agent = agents.get(world_id)

    if agent is None or agent.state != AgentState.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "El agente del mundo está desconectado. "
                "Inicia sesión primero para poder refrescar las aldeas."
            ),
        )

    # Delegar al WorldAgent la ejecución del parser del village-switcher.
    # Firma esperada del método (a implementar por desarrollador-funcionalidades):
    #   async def refresh_villages(self) -> list[Village]
    # Devuelve la lista de Village encontradas y upserteadas.
    # Lanza RuntimeError si el browser no está disponible en ese momento.
    try:
        villages = await agent.refresh_villages()
    except Exception as exc:
        logger.exception(
            "Error ejecutando refresh_villages para mundo %d", world_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        ) from exc

    return RefreshVillagesResponse(
        villages_found=len(villages),
        villages_data=[
            VillageItem(
                data_id=v.data_id,
                name=v.name,
                x=v.x,
                y=v.y,
            )
            for v in villages
        ],
    )


# ---------------------------------------------------------------------------
# EP-N14 — POST /worlds/{id}/noise/paths/{path_id}/test
# ---------------------------------------------------------------------------

@router.post(
    "/worlds/{world_id}/noise/paths/{path_id}/test",
    response_model=PathTestResponse,
    summary="EP-N14 — Probar ruta de navegación en vivo",
)
async def test_path(
    request: Request,
    world_id: int = Path(..., ge=1),
    path_id: int = Path(..., ge=1),
) -> PathTestResponse:
    """
    Ejecuta la ruta de navegación indicada en el Chrome real del bot y devuelve
    un reporte paso a paso del resultado.

    El test es NO DESTRUCTIVO: no modifica contadores de fallos, no marca rutas
    como is_dead, no actualiza last_used_at y no ejecuta el dwell final. Su único
    propósito es diagnóstico.

    El browser queda en la última página visitada durante el test (RN-PT06).

    Requiere que el WorldAgent del mundo esté activo (AgentState.RUNNING).

    HTTP 200 tanto si la ruta pasó (overall="ok") como si falló (overall="error"):
    el endpoint se ejecutó correctamente en ambos casos; el fallo es semántico
    (un paso de la ruta no funcionó), no un error del endpoint.

    Firma de la coroutine que implementa desarrollador-funcionalidades:

        async def execute_path_test(
            self, path: NavigationPath
        ) -> PathTestReport:
            ...

    donde PathTestReport es el dataclass de core/entities/noise_test.py:
        - overall: str              "ok" | "error"
        - steps: list[PathTestStepResult]
        - aborted_at_step: int | None
        - anchor_navigated_to: str | None

    Excepciones que el implementador DEBE lanzar para que este handler las mapee:
        - BrowserBusyError  → 409 "browser ocupado"
        - RuntimeError      → 500 "error interno del servidor"
        - cualquier otra excepción no capturada → 500

    Spec: noise-path-wizard.md §16.8 (EP-N14).
    """
    from core.exceptions import BrowserBusyError  # import local para evitar ciclos
    from core.scheduling.world_agent import AgentState  # import local para evitar ciclos

    await _verify_world_exists(request, world_id)
    noise_db = _get_noise_db(request)
    path = await _verify_path_belongs_to_world(noise_db, path_id, world_id)

    # Verificar que hay un WorldAgent activo (RUNNING) para este mundo.
    # Mismo patrón que EP-N13 (refresh_villages).
    agents: dict = getattr(request.app.state, "world_agents", {})
    agent = agents.get(world_id)

    # Que el agente esté RUNNING (loop vivo) NO implica que haya una sesión de
    # Chrome abierta: si el bloque horario es DISCONNECTED, el browser está cerrado
    # y get_browser() devolvería None → execute_path_test lanzaría RuntimeError →
    # 500. La precondición correcta es "hay una sesión de browser activa": si no la
    # hay, devolvemos un 409 claro ("inicia sesión primero"), no un error interno.
    session_active = bool(agent is not None and agent._session_active())

    if agent is None or agent.state != AgentState.RUNNING or not session_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "El agente del mundo está desconectado. "
                "Inicia sesión primero para poder probar la ruta."
            ),
        )

    # Delegar la ejecución al WorldAgent.
    # BrowserBusyError → 409 (browser ocupado con otra tarea).
    # RuntimeError → 500 (no hay browser, servidor no disponible, etc.).
    # Cualquier otra excepción inesperada → 500.
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
        logger.error(
            "execute_path_test mundo %d: RuntimeError: %s", world_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        ) from exc
    except Exception:
        logger.exception(
            "execute_path_test mundo %d: error inesperado", world_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
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
