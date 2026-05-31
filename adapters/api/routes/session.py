"""
Router FastAPI para Human Sessions.

Endpoints (sin prefijo /api — el proxy de Vite lo retira):

  GET    /worlds/{world_id}/session                      — estado actual de sesión
  GET    /worlds/{world_id}/session/timeline             — timeline completo (7 días)
  GET    /worlds/{world_id}/session/timeline/{weekday}   — timeline de un día
  PUT    /worlds/{world_id}/session/timeline/{weekday}   — actualizar un día
  PUT    /worlds/{world_id}/session/mode                 — override manual de modo
  DELETE /worlds/{world_id}/session/override             — cancelar override activo
  GET    /worlds/{world_id}/session/config               — leer config PASIVO
  PUT    /worlds/{world_id}/session/config               — actualizar config PASIVO

Sin Accept-Language: no devuelven texto localizado (§8 del spec).
Spec §8.1–§8.7.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from adapters.db.session_sqlite_adapter import _fill_gaps_with_disconnected, _validate_no_overlaps
from core.entities.session import (
    SessionBlock,
    SessionConfig,
    SessionMode,
    SessionOverride,
    SessionTimeline,
    _block_end_as_datetime,
    _find_active_block,
    calculate_jitter_fin_for_now,
    current_mode as compute_current_mode,
    get_default_timeline,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["session"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_session_db(request: Request):
    """Extrae session_db del app.state."""
    session_db = getattr(request.app.state, "session_db_port", None)
    if session_db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        )
    return session_db


def _get_db(request: Request):
    """Extrae db_port (para verificar que el world existe)."""
    db = getattr(request.app.state, "db_port", None)
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        )
    return db


async def _verify_world(world_id: int, db) -> None:
    """Lanza 404 si el mundo no existe."""
    try:
        world = await db.get_world(world_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Mundo no encontrado.")
    if world is None:
        raise HTTPException(status_code=404, detail="Mundo no encontrado.")


async def _get_timeline_for_day(world_id: int, weekday: int, session_db) -> SessionTimeline:
    """Carga el timeline del día desde BD o devuelve el default."""
    timeline = await session_db.get_timeline(world_id, weekday)
    if timeline is None:
        return get_default_timeline(world_id, weekday)
    return timeline


def _block_to_response(block: SessionBlock) -> dict:
    start = f"{block.start_hour:02d}:{block.start_minute:02d}"
    if block.end_hour == 24:
        end = "24:00"
    else:
        end = f"{block.end_hour:02d}:{block.end_minute:02d}"
    return {"start": start, "end": end, "mode": block.mode.value}


def _timeline_to_response(timeline: SessionTimeline) -> dict:
    return {
        "weekday": timeline.weekday,
        "is_default": timeline.is_default,
        "jitter_minutes": timeline.jitter_minutes,
        "blocks": [_block_to_response(b) for b in timeline.blocks],
    }


def _parse_hhmm(value: str, field_name: str) -> tuple[int, int]:
    """Parsea 'HH:MM' o '24:00'. Lanza ValueError si no es válido."""
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError(f"{field_name}: formato inválido — debe ser HH:MM")
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        raise ValueError(f"{field_name}: debe ser un número entero")
    return h, m


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class BlockInput(BaseModel):
    start: str   # "HH:MM"
    end: str     # "HH:MM" o "24:00"
    mode: SessionMode

    def to_session_block(self) -> SessionBlock:
        sh, sm = _parse_hhmm(self.start, "start")
        eh, em = _parse_hhmm(self.end, "end")
        return SessionBlock(
            start_hour=sh, start_minute=sm,
            end_hour=eh, end_minute=em,
            mode=self.mode,
        )


class TimelinePutBody(BaseModel):
    blocks: list[BlockInput]
    jitter_minutes: int = Field(default=15, ge=0)


class SessionModeBody(BaseModel):
    mode: SessionMode


class SessionConfigBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    passive_interval_factor: Optional[float] = Field(
        default=None,
        description="Multiplicador del intervalo en PASIVO. Rango [1.5, 5.0].",
    )
    passive_send_probability: Optional[float] = Field(
        default=None,
        description="Probabilidad de disparo en PASIVO. Rango [0.01, 0.50].",
    )

    @model_validator(mode="after")
    def at_least_one_field(self) -> "SessionConfigBody":
        if self.passive_interval_factor is None and self.passive_send_probability is None:
            raise ValueError(
                "El body debe contener al menos uno de: "
                "passive_interval_factor, passive_send_probability."
            )
        return self


class SessionOverrideResponse(BaseModel):
    mode: str
    expires_at: str


# ---------------------------------------------------------------------------
# 8.1  GET /worlds/{world_id}/session — Estado actual
# ---------------------------------------------------------------------------

@router.get("/worlds/{world_id}/session")
async def get_session_status(world_id: int, request: Request):
    """
    Estado actual de la sesión: modo activo, bloque en curso y tiempo hasta
    el próximo cambio de modo.
    """
    db = _get_db(request)
    session_db = _get_session_db(request)

    await _verify_world(world_id, db)

    try:
        now = datetime.now()
        weekday = now.weekday()

        timeline = await _get_timeline_for_day(world_id, weekday, session_db)
        override = await session_db.get_override(world_id)

        active_mode, jitter_fin = compute_current_mode(now, timeline, override)
        active_block = _find_active_block(timeline.blocks, now)

        # Asegurar tz-aware para jitter_fin
        if jitter_fin.tzinfo is None:
            jitter_fin_utc = jitter_fin.replace(tzinfo=timezone.utc)
        else:
            jitter_fin_utc = jitter_fin.astimezone(timezone.utc)

        seconds_to_next = max(0, int((jitter_fin_utc - datetime.now(timezone.utc)).total_seconds()))

        override_resp = None
        if override is not None:
            override_resp = {
                "mode": override.mode.value,
                "expires_at": override.expires_at.isoformat(),
            }

        return {
            "mode": active_mode.value,
            "block": _block_to_response(active_block),
            "jitter_minutes": timeline.jitter_minutes,
            "next_block_ends_at": jitter_fin_utc.isoformat().replace("+00:00", "Z"),
            "seconds_to_next_block": seconds_to_next,
            "override": override_resp,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error en GET /worlds/%d/session", world_id)
        raise HTTPException(status_code=500, detail="Error interno del servidor.")


# ---------------------------------------------------------------------------
# 8.2  GET /worlds/{world_id}/session/timeline — Timeline completo (7 días)
# ---------------------------------------------------------------------------

@router.get("/worlds/{world_id}/session/timeline")
async def get_session_timeline(world_id: int, request: Request):
    """Devuelve los 7 timelines (uno por día de la semana)."""
    db = _get_db(request)
    session_db = _get_session_db(request)

    await _verify_world(world_id, db)

    try:
        timelines = []
        for weekday in range(7):
            tl = await _get_timeline_for_day(world_id, weekday, session_db)
            timelines.append(_timeline_to_response(tl))
        return {"timelines": timelines}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error en GET /worlds/%d/session/timeline", world_id)
        raise HTTPException(status_code=500, detail="Error interno del servidor.")


# ---------------------------------------------------------------------------
# 8.3  PUT /worlds/{world_id}/session/timeline/{weekday}
# ---------------------------------------------------------------------------

@router.put("/worlds/{world_id}/session/timeline/{weekday}")
async def put_session_timeline(
    world_id: int,
    weekday: int = Path(ge=0, le=6),
    body: TimelinePutBody = ...,
    request: Request = ...,
):
    """
    Reemplaza los bloques de un día de la semana.
    Rellena huecos con DISCONNECTED. Rechaza solapes con 422.
    """
    db = _get_db(request)
    session_db = _get_session_db(request)

    await _verify_world(world_id, db)

    # Convertir input a SessionBlock
    blocks: list[SessionBlock] = []
    for bi in body.blocks:
        try:
            block = bi.to_session_block()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        blocks.append(block)

    # Validar no-solapes (incluye end <= start)
    try:
        _validate_no_overlaps(blocks)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    timeline = SessionTimeline(
        world_id=world_id,
        weekday=weekday,
        blocks=blocks,
        jitter_minutes=body.jitter_minutes,
        is_default=False,
    )

    try:
        saved = await session_db.upsert_timeline(timeline)
        return _timeline_to_response(saved)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        logger.exception("Error en PUT /worlds/%d/session/timeline/%d", world_id, weekday)
        raise HTTPException(status_code=500, detail="Error interno del servidor.")


# ---------------------------------------------------------------------------
# 8.4  PUT /worlds/{world_id}/session/mode — Override manual de modo
# ---------------------------------------------------------------------------

@router.put("/worlds/{world_id}/session/mode")
async def put_session_mode(world_id: int, body: SessionModeBody, request: Request):
    """
    Fuerza un modo para el mundo hasta el próximo borde de bloque.
    Idempotente: si el mundo ya está en el modo solicitado, devuelve 200
    informativo sin modificar el override en BD.
    """
    db = _get_db(request)
    session_db = _get_session_db(request)

    await _verify_world(world_id, db)

    try:
        now = datetime.now()
        weekday = now.weekday()
        timeline = await _get_timeline_for_day(world_id, weekday, session_db)
        existing_override = await session_db.get_override(world_id)

        # Calcular el modo activo actual (con override vigente si existe)
        current_m, current_jitter_fin = compute_current_mode(now, timeline, existing_override)

        # Caso EC-HS05: ya está en el modo solicitado
        if current_m == body.mode:
            return {
                "mode": body.mode.value,
                "expires_at": None,
                "already_active": True,
                "requires_relogin": False,
                "chrome_action": "none",
                "message": f"World already in {body.mode.value} mode. No changes made.",
            }

        # Calcular expires_at = jitter_fin del bloque del calendario (sin override)
        # El override dura hasta el próximo borde del bloque del calendario.
        _, expires_at = compute_current_mode(now, timeline, override=None)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        else:
            expires_at = expires_at.astimezone(timezone.utc)

        # Determinar requires_relogin y chrome_action (tabla de transiciones §8.4)
        # Se basa en current_m (modo efectivo actual) y body.mode (modo destino).
        requires_relogin = (
            current_m == SessionMode.DISCONNECTED
            and body.mode != SessionMode.DISCONNECTED
        )
        if body.mode == SessionMode.DISCONNECTED:
            chrome_action = "close"
        elif current_m == SessionMode.DISCONNECTED:
            chrome_action = "open"
        else:
            chrome_action = "none"

        # Escribir override en BD
        override = SessionOverride(
            world_id=world_id,
            mode=body.mode,
            expires_at=expires_at,
        )
        await session_db.set_override(override)

        return {
            "mode": body.mode.value,
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            "already_active": False,
            "requires_relogin": requires_relogin,
            "chrome_action": chrome_action,
            "message": "Override applied. Takes effect on the next WorldAgent cycle.",
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error en PUT /worlds/%d/session/mode", world_id)
        raise HTTPException(status_code=500, detail="Error interno del servidor.")


# ---------------------------------------------------------------------------
# 8.5  DELETE /worlds/{world_id}/session/override — Cancelar override activo
# ---------------------------------------------------------------------------

@router.delete(
    "/worlds/{world_id}/session/override",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancelar override de modo activo",
    description=(
        "Borra el override de modo activo para el mundo dado. "
        "Idempotente: si no hay override activo, responde igualmente 204. "
        "Tras la llamada, el sistema recupera el modo que dicte el calendario."
    ),
)
async def delete_session_override(world_id: int, request: Request):
    db = _get_db(request)
    session_db = _get_session_db(request)

    await _verify_world(world_id, db)

    try:
        await session_db.clear_override(world_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error en DELETE /worlds/%d/session/override", world_id)
        raise HTTPException(status_code=500, detail="Error interno del servidor.")


# ---------------------------------------------------------------------------
# 8.7  GET /worlds/{world_id}/session/config — Leer config PASIVO
# ---------------------------------------------------------------------------

@router.get("/worlds/{world_id}/session/config")
async def get_session_config(world_id: int, request: Request):
    """Devuelve los parámetros de configuración del modo PASIVO."""
    db = _get_db(request)
    session_db = _get_session_db(request)

    await _verify_world(world_id, db)

    try:
        config = await session_db.get_session_config(world_id)
        return {
            "passive_interval_factor": config.passive_interval_factor,
            "passive_send_probability": config.passive_send_probability,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error en GET /worlds/%d/session/config", world_id)
        raise HTTPException(status_code=500, detail="Error interno del servidor.")


# ---------------------------------------------------------------------------
# 8.8  PUT /worlds/{world_id}/session/config — Actualizar config PASIVO
# ---------------------------------------------------------------------------

@router.put("/worlds/{world_id}/session/config")
async def put_session_config(world_id: int, body: SessionConfigBody, request: Request):
    """
    Actualiza uno o ambos parámetros del modo PASIVO (PATCH parcial semántico).
    Los campos ausentes conservan su valor actual (o el default si nunca fue configurado).
    """
    db = _get_db(request)
    session_db = _get_session_db(request)

    await _verify_world(world_id, db)

    # Validaciones de rango (complementan la CHECK constraint de SQLite)
    if body.passive_interval_factor is not None:
        if not (1.5 <= body.passive_interval_factor <= 5.0):
            raise HTTPException(
                status_code=422,
                detail="passive_interval_factor debe estar entre 1.5 y 5.0.",
            )
    if body.passive_send_probability is not None:
        if not (0.01 <= body.passive_send_probability <= 0.50):
            raise HTTPException(
                status_code=422,
                detail="passive_send_probability debe estar entre 0.01 y 0.50.",
            )

    try:
        # Leer config actual (para PATCH parcial: conservar campos no enviados)
        current = await session_db.get_session_config(world_id)

        new_factor = (
            body.passive_interval_factor
            if body.passive_interval_factor is not None
            else current.passive_interval_factor
        )
        new_prob = (
            body.passive_send_probability
            if body.passive_send_probability is not None
            else current.passive_send_probability
        )

        new_config = SessionConfig(
            world_id=world_id,
            passive_interval_factor=new_factor,
            passive_send_probability=new_prob,
        )
        saved = await session_db.upsert_session_config(new_config)
        return {
            "passive_interval_factor": saved.passive_interval_factor,
            "passive_send_probability": saved.passive_send_probability,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error en PUT /worlds/%d/session/config", world_id)
        raise HTTPException(status_code=500, detail="Error interno del servidor.")
