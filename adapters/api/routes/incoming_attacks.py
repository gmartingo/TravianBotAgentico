"""
Router del radar de ataques entrantes.

Endpoints (sin prefijo /api — el proxy de Vite lo retira):

  GET  /game/incoming-attacks/{world_id}        EP-RA01: lista ataques entrantes
  POST /game/incoming-attacks/{world_id}/check  EP-RA02: dispara lectura inmediata

SIN Accept-Language: ningún campo devuelto es texto localizado.
Esta es una desviación consciente documentada en el spec
docs/specs/radar-ataques-entrantes.md §8.

Los errores de dominio (WorldNotFoundError → 404, SessionNotActiveError → 503)
se propagan al handler global de main.py, que los mapea vía ERROR_HTTP_MAP.
No se capturan en este router.

Ver spec docs/specs/radar-ataques-entrantes.md §8 para los contratos completos.
Añadido en la feature radar-ataques-entrantes (2026-06-05).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Query, Request, status

from core.scheduling.world_agent import AgentState
from core.use_cases.incoming_attack_use_cases import (
    ListIncomingAttacksUseCase,
    SummaryIncomingAttacksUseCase,
)

router = APIRouter(prefix="/game", tags=["incoming-attacks"])


# ---------------------------------------------------------------------------
# Helpers de dependencias
# ---------------------------------------------------------------------------

def _get_incoming_attack_port(request: Request):
    """Extrae incoming_attack_port de app.state. 500 si no está inicializado."""
    port = getattr(request.app.state, "incoming_attack_port", None)
    if port is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        )
    return port


def _get_db_port(request: Request):
    """Extrae db_port (AccountSQLiteAdapter) de app.state para verificar mundos."""
    port = getattr(request.app.state, "db_port", None)
    if port is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor.",
        )
    return port


async def _verify_world(world_id: int, db_port) -> None:
    """
    Lanza HTTPException 404 si el mundo no existe.
    Sigue el mismo patrón que session.py._verify_world.
    """
    try:
        world = await db_port.get_world(world_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Mundo no encontrado.")
    if world is None:
        raise HTTPException(status_code=404, detail="Mundo no encontrado.")


# ---------------------------------------------------------------------------
# EP-RA03 — GET /game/incoming-attacks/summary
#
# ORDEN OBLIGATORIO: esta ruta literal DEBE declararse ANTES que la ruta
# dinámica /incoming-attacks/{world_id} para que FastAPI no intente parsear
# el segmento "summary" como un int de world_id.
# ---------------------------------------------------------------------------

@router.get(
    "/incoming-attacks/summary",
    summary="Resumen de ataques pendientes por mundo (badge)",
    description=(
        "Devuelve el recuento de ataques pendientes agrupado por mundo. "
        "Diseñado para badgear la lista de Mundos del frontend con una sola petición. "
        "Se incluyen todos los mundos conocidos, incluso los de 0 ataques. "
        "pending_attacks cuenta filas con impact_at IS NULL (sidebar sin timer) "
        "o impact_at > ahora. Sin Accept-Language: datos numéricos."
    ),
    responses={
        200: {
            "description": "Recuento de ataques pendientes por mundo",
            "content": {
                "application/json": {
                    "example": [
                        {"world_id": 1, "pending_attacks": 3},
                        {"world_id": 2, "pending_attacks": 0},
                    ]
                }
            },
        },
        500: {"description": "Error interno del servidor"},
    },
)
async def summary_incoming_attacks(request: Request):
    """
    EP-RA03 — Resumen de ataques pendientes agrupado por mundo.

    Sin world_id en la ruta: no hay 404. Si no hay mundos → lista vacía [].
    Lógica de negocio en SummaryIncomingAttacksUseCase; el handler solo valida,
    llama al use case y serializa.
    """
    incoming_attack_port = _get_incoming_attack_port(request)
    use_case = SummaryIncomingAttacksUseCase(db_port=incoming_attack_port)
    return await use_case.execute()


# ---------------------------------------------------------------------------
# EP-RA01 — GET /game/incoming-attacks/{world_id}
# ---------------------------------------------------------------------------

@router.get(
    "/incoming-attacks/{world_id}",
    summary="Lista ataques entrantes de un mundo",
    description=(
        "Devuelve la lista paginada de ataques entrantes detectados para el mundo indicado. "
        "Por defecto solo incluye ataques pendientes (sin impactar o sin timer). "
        "Usa `include_past=true` para ver también ataques pasados. "
        "Sin Accept-Language: los datos son numéricos o texto crudo del juego, "
        "no texto localizado."
    ),
    responses={
        200: {
            "description": "Lista de ataques entrantes",
            "content": {
                "application/json": {
                    "example": {
                        "items": [
                            {
                                "id": 1,
                                "village_game_id": 12345,
                                "village_name": "Mi Aldea",
                                "village_coord_x": 100,
                                "village_coord_y": -50,
                                "attack_count": 2,
                                "impact_at": "2026-06-05T18:30:00+00:00",
                                "seconds_remaining": 3600,
                                "rally_point_href": "/build.php?gid=16&id=1",
                                "attacker_name": None,
                                "origin_village_name": None,
                                "origin_village_coord_x": None,
                                "origin_village_coord_y": None,
                                "operation_type": None,
                                "attacker_snapshot": None,
                                "source": "dorf1",
                                "detected_at": "2026-06-05T17:30:00+00:00",
                            }
                        ],
                        "total": 1,
                        "limit": 50,
                        "offset": 0,
                    }
                }
            },
        },
        404: {"description": "Mundo no encontrado"},
        422: {"description": "Parámetros de query inválidos"},
    },
)
async def list_incoming_attacks(
    request: Request,
    world_id: int = Path(..., ge=1, description="ID del mundo en la BD local"),
    include_past: bool = Query(
        False,
        description=(
            "Si es true, incluye ataques cuyo impact_at ya ha pasado. "
            "Por defecto solo muestra ataques pendientes o sin timer."
        ),
    ),
    village_game_id: int | None = Query(
        None,
        ge=1,
        description="Filtro opcional: solo ataques a esta aldea (game_id de Travian).",
    ),
    limit: int = Query(
        50,
        ge=1,
        le=100,
        description="Número máximo de registros a devolver (1–100).",
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Desplazamiento para paginación.",
    ),
):
    """
    EP-RA01 — Lista ataques entrantes para un mundo.

    Calcula seconds_remaining en el use case:
      - null si impact_at es None (ataque detectado sin timer todavía)
      - max(0, int(delta)) si impact_at no es None

    Lanza HTTP 404 si el mundo no existe (validado en el router, antes del use case).
    """
    incoming_attack_port = _get_incoming_attack_port(request)
    db_port = _get_db_port(request)

    # Verificar existencia del mundo en el router (patrón de session.py)
    await _verify_world(world_id, db_port)

    use_case = ListIncomingAttacksUseCase(db_port=incoming_attack_port)
    result = await use_case.execute(
        world_id=world_id,
        include_past=include_past,
        village_game_id=village_game_id,
        limit=limit,
        offset=offset,
        db_port_for_world_check=None,  # ya verificado arriba
    )
    return result


# ---------------------------------------------------------------------------
# EP-RA02 — POST /game/incoming-attacks/{world_id}/check
# ---------------------------------------------------------------------------

@router.post(
    "/incoming-attacks/{world_id}/check",
    summary="Dispara lectura inmediata del radar de ataques",
    description=(
        "Fuerza una lectura inmediata del radar de ataques entrantes para el mundo "
        "indicado. Navega dorf1 con el browser autenticado y devuelve cuántos ataques "
        "se detectaron en esta lectura. "
        "Requiere sesión activa para el mundo (login previo). "
        "Sin body ni Accept-Language."
    ),
    responses={
        200: {
            "description": "Resultado de la lectura del radar",
            "content": {
                "application/json": {
                    "example": {
                        "world_id": 1,
                        "attacks_detected": 3,
                        "message": "Check completado",
                    }
                }
            },
        },
        404: {"description": "Mundo no encontrado"},
        503: {"description": "No hay sesión activa para este mundo"},
    },
)
async def check_incoming_attacks(
    request: Request,
    world_id: int = Path(..., ge=1, description="ID del mundo en la BD local"),
):
    """
    EP-RA02 — Dispara la lectura del radar para el mundo indicado.

    Reescrito (spec radar-check-boton-sidebar §9.2): delega en
    WorldAgent.check_incoming_sidebar() en lugar de construir un adapter ad-hoc
    y navegar a dorf1.php. Esto elimina la contención de CDP (causa raíz 2) y
    usa el parser correcto del sidebar en T4.6 (causa raíz 1).

    Lanza HTTP 404 si el mundo no existe.
    Lanza HTTP 409 si el WorldAgent no existe o no está en estado RUNNING.
    """
    db_port = _get_db_port(request)

    # Verificar existencia del mundo (comportamiento existente)
    await _verify_world(world_id, db_port)

    # Obtener el WorldAgent en marcha (RN-B02, RN-B05, EC-B01)
    agents: dict = getattr(request.app.state, "world_agents", {})
    agent = agents.get(world_id)

    if agent is None or agent.state != AgentState.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"El agente del mundo {world_id} no está activo "
                "— inicia la sesión para usar el radar manual."
            ),
        )

    # Delegar al agente (serializa con su _browser_lock interno — RN-B03)
    attacks_detected = await agent.check_incoming_sidebar()

    return {
        "world_id": world_id,
        "attacks_detected": attacks_detected,
        "message": "Check completado",
    }
