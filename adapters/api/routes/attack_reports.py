"""
Endpoints de la feature "BD de ataques a oasis".

Rutas (sin prefijo /api — el proxy de Vite lo retira):
  POST   /attack-reports/parse        EP-01: parse sin guardar   (200)
  POST   /attack-reports              EP-02: guardar reporte      (201)
  GET    /attack-reports              EP-03: historial filtrable  (200)
  GET    /attack-reports/oasis        EP-08: lista oasis          (200)  ← ANTES de /{id}
  GET    /attack-reports/stats/bounty EP-07: balance recursos     (200)  ← ANTES de /{id}
  GET    /attack-reports/stats/oasis  EP-06: estadísticas oasis   (200)  ← ANTES de /{id}
  GET    /attack-reports/{id}         EP-04: detalle reporte      (200)
  DELETE /attack-reports/{id}         EP-05: borrar reporte       (204)

NOTA DE ROUTING (C6): los endpoints con rutas literales (EP-06, EP-07, EP-08)
se declaran ANTES de EP-04/{id} para que FastAPI los resuelva como literales
y no capturen "stats" u "oasis" como {id}. {id} está tipado int con ge=1.

Sin Accept-Language obligatorio en este router: los endpoints devuelven datos
numéricos e ISO 8601; el animal_name es texto crudo del usuario (validado por
desarrollador-apis).

Ver spec docs/specs/bd-ataques-oasis.md §8 para los contratos completos.
Correcciones C1–C7 del spec incorporadas.
Añadido en la feature bd-ataques-oasis (2026-05-30).
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Path, Query, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.entities.tribe import Tribe
from core.ports.attack_report_port import DuplicateReportError
from core.use_cases.attack_report_parser import (
    MultipleReportsError,
    NotNatureOasisError,
    ReportFormatError,
    UnrecognizedAnimalError,
    parse_attack_report,
)

router = APIRouter(tags=["attack-reports"])


# ---------------------------------------------------------------------------
# DTOs de REQUEST
# ---------------------------------------------------------------------------

class ParseReportRequest(BaseModel):
    """Body para EP-01 (parse) y EP-02 (save). (C1)"""
    raw_text: str = Field(..., min_length=1, max_length=50_000)


# ---------------------------------------------------------------------------
# Helper: serializar AttackReportPreview → dict para la respuesta
# ---------------------------------------------------------------------------

def _preview_to_dict(preview, attacker_cost_loss: dict | None = None) -> dict:
    """
    Serializa AttackReportPreview a dict JSON-listo.

    Garantía C2: hero_inventory es campo RAÍZ, NO dentro de bounty.
    attacker_cost_loss: coste en recursos de las tropas perdidas (o None si no
    se pudo calcular — tribu desconocida o sin datos de juego).
    """
    tribe = getattr(preview, "attacker_tribe", None)

    def _troop_icon(ordinal: int | None) -> str | None:
        # Sprite de la tribu deducida: /static/icons/{tribe}_{ordinal}.png
        if tribe and ordinal:
            return f"/static/icons/{tribe}_{ordinal}.png"
        return None

    def _animal_icon(ordinal: int | None) -> str | None:
        # Los animales viven bajo la "tribu" nature: /static/icons/nature_{ordinal}.png
        if ordinal:
            return f"/static/icons/nature_{ordinal}.png"
        return None

    return {
        "attacked_at": preview.attacked_at,
        "utc_offset": preview.utc_offset,
        "coord_x_dest": preview.coord_x_dest,
        "coord_y_dest": preview.coord_y_dest,
        "origin_village_name": preview.origin_village_name,
        "attacker_tribe": tribe,
        "attacker_troops": [
            {
                "troop_name": t.troop_name,
                "troop_ordinal": t.troop_ordinal,
                "icon_url": _troop_icon(t.troop_ordinal),
                "sent": t.sent,
                "lost": t.lost,
                "survived": t.survived,
            }
            for t in preview.attacker_troops
        ],
        "animals": [
            {
                "animal_ordinal": a.animal_ordinal,
                "animal_name": a.animal_name,
                "icon_url": _animal_icon(a.animal_ordinal),
                "present": a.present,
                "killed": a.killed,
                "survived": a.survived,
            }
            for a in preview.animals
        ],
        "bounty": {
            "wood": preview.bounty.wood,
            "clay": preview.bounty.clay,
            "iron": preview.bounty.iron,
            "crop": preview.bounty.crop,
            "capacity_used": preview.bounty.capacity_used,
            "capacity_total": preview.bounty.capacity_total,
        },
        # C2: hero_inventory en primer nivel, separado de bounty
        "hero_inventory": preview.hero_inventory,
        # Coste en recursos de las tropas perdidas (None si no calculable)
        "attacker_cost_loss": attacker_cost_loss,
        "already_exists": preview.already_exists,
        "existing_id": preview.existing_id,
    }


async def _compute_attacker_cost_loss(preview, game_data_port) -> dict | None:
    """
    Calcula el coste en recursos de las tropas atacantes perdidas.

    Para cada tropa con lost > 0 multiplica su coste unitario de entrenamiento
    (cost_wood/clay/iron/crop de los datos de kirilloid) por las bajas. Requiere
    que la tribu del atacante esté resuelta (preview.attacker_tribe).

    Devuelve {wood, clay, iron, crop, total} o None si la tribu es desconocida
    o no hay puerto de datos disponible.
    """
    tribe_str = getattr(preview, "attacker_tribe", None)
    if not tribe_str or game_data_port is None:
        return None
    try:
        tribe = Tribe(tribe_str)
    except ValueError:
        return None

    stats = await game_data_port.get_all_troop_stats(tribe)
    cost_by_ordinal = {s["ordinal"]: s for s in stats}

    wood = clay = iron = crop = 0
    for t in preview.attacker_troops:
        if not t.lost or t.troop_ordinal is None:
            continue
        s = cost_by_ordinal.get(t.troop_ordinal)
        if not s:
            continue
        wood += t.lost * (s.get("cost_wood") or 0)
        clay += t.lost * (s.get("cost_clay") or 0)
        iron += t.lost * (s.get("cost_iron") or 0)
        crop += t.lost * (s.get("cost_crop") or 0)

    return {
        "wood": wood, "clay": clay, "iron": iron, "crop": crop,
        "total": wood + clay + iron + crop,
    }


def _parse_or_422(raw_text: str) -> object:
    """
    Intenta parsear el texto; convierte excepciones del parser en 422.
    """
    try:
        return parse_attack_report(raw_text, db_port=None)
    except MultipleReportsError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except NotNatureOasisError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except UnrecognizedAnimalError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except ReportFormatError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


# ---------------------------------------------------------------------------
# EP-01 — Parse sin guardar
# ---------------------------------------------------------------------------

@router.post("/attack-reports/parse", status_code=status.HTTP_200_OK)
async def parse_report(body: ParseReportRequest, request: Request) -> dict:
    """
    Parsea el texto crudo de un reporte de ataque a oasis y devuelve un preview.

    No persiste nada. El campo already_exists indica si ya existe en BD.
    Errores 422 si el texto no es un reporte válido de ataque a oasis Nature.
    """
    port = request.app.state.attack_report_port

    # Parsear (lanza 422 si hay error de formato)
    preview = _parse_or_422(body.raw_text)

    # Verificar unicidad en BD para el preview (no guarda nada)
    existing_id = await port.report_exists(
        preview.coord_x_dest,
        preview.coord_y_dest,
        preview.attacked_at,
        preview.origin_village_name,
    )
    if existing_id is not None:
        preview.already_exists = True
        preview.existing_id = existing_id

    # Coste de las tropas perdidas (usa los datos de juego por tribu+ordinal)
    game_data_port = getattr(request.app.state, "game_data_port", None)
    cost_loss = await _compute_attacker_cost_loss(preview, game_data_port)

    return _preview_to_dict(preview, attacker_cost_loss=cost_loss)


# ---------------------------------------------------------------------------
# EP-02 — Save (guardar tras confirmación)
# ---------------------------------------------------------------------------

@router.post("/attack-reports", status_code=status.HTTP_201_CREATED)
async def save_report(body: ParseReportRequest, request: Request) -> dict:
    """
    Re-parsea el texto crudo y guarda el reporte en la BD.

    El backend es fuente de verdad: re-parsea siempre (no acepta preview del cliente).
    409 si el reporte ya existe. 422 si el texto no es válido.

    Response 201 incluye id, attacked_at, utc_offset (C3), coord_x_dest, coord_y_dest,
    origin_village_name.
    """
    port = request.app.state.attack_report_port

    # Re-parsear (fuente de verdad — RT-06)
    preview = _parse_or_422(body.raw_text)

    # Guardar (lanza DuplicateReportError si clave única viola)
    try:
        report_id = await port.save_report(preview, body.raw_text)
    except DuplicateReportError as exc:
        # Obtener el timestamp del reporte existente para el detail legible
        existing = await port.get_report(exc.existing_id)
        if existing:
            attacked_str = existing["attacked_at"]
            origin = existing["origin_village_name"]
            detail = (
                f"Reporte ya registrado (id: {exc.existing_id}, "
                f"atacado el {attacked_str} desde '{origin}')."
            )
        else:
            detail = f"Reporte ya registrado (id: {exc.existing_id})."
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        ) from exc

    return {
        "id": report_id,
        "attacked_at": preview.attacked_at,
        "utc_offset": preview.utc_offset,       # C3: incluir en 201
        "coord_x_dest": preview.coord_x_dest,
        "coord_y_dest": preview.coord_y_dest,
        "origin_village_name": preview.origin_village_name,
    }


# ---------------------------------------------------------------------------
# EP-03 — List (historial filtrable)
# ---------------------------------------------------------------------------

@router.get("/attack-reports", status_code=status.HTTP_200_OK)
async def list_reports(
    request: Request,
    x: int | None = Query(default=None, description="Coordenada X del oasis (requiere y)"),
    y: int | None = Query(default=None, description="Coordenada Y del oasis (requiere x)"),
    from_date: str | None = Query(default=None, description="Fecha desde (ISO 8601, inclusiva)"),
    to_date: str | None = Query(default=None, description="Fecha hasta (ISO 8601, inclusiva)"),
    limit: int = Query(default=50, description="Máximo de resultados (1-100)"),
    offset: int = Query(default=0, description="Desplazamiento para paginación (≥ 0)"),
) -> dict:
    """
    Historial filtrable de ataques a oasis, paginado.

    Filtros opcionales: x+y (ambos o ninguno), from_date, to_date.
    Límite máximo: 100 (C4). cumulative_bounty = suma del rango filtrado actual (C5).
    """
    # Validación de parámetros (C4 — tabla exhaustiva de 400)
    if (x is None) != (y is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parámetro 'x' requiere 'y' y viceversa.",
        )

    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El parámetro 'limit' debe estar entre 1 y 100.",
        )

    if offset < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El parámetro 'offset' no puede ser negativo.",
        )

    if from_date is not None:
        try:
            datetime.fromisoformat(from_date)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El parámetro 'from_date' no es una fecha ISO 8601 válida.",
            )

    if to_date is not None:
        try:
            datetime.fromisoformat(to_date)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El parámetro 'to_date' no es una fecha ISO 8601 válida.",
            )

    if from_date is not None and to_date is not None:
        if from_date > to_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El parámetro 'from_date' no puede ser posterior a 'to_date'.",
            )

    port = request.app.state.attack_report_port
    return await port.list_reports(
        x=x, y=y,
        from_date=from_date, to_date=to_date,
        limit=limit, offset=offset,
    )


# ---------------------------------------------------------------------------
# EP-08 — Lista de oasis navegable (ANTES de /{id} para evitar colisión de routing)
# ---------------------------------------------------------------------------

@router.get("/attack-reports/oasis", status_code=status.HTTP_200_OK)
async def list_oasis_summaries(
    request: Request,
    x: int | None = Query(
        default=None,
        ge=-400,
        le=400,
        description="Coordenada X del oasis (-400..400). Si se omite junto con y, lista todos los oasis.",
    ),
    y: int | None = Query(
        default=None,
        ge=-400,
        le=400,
        description="Coordenada Y del oasis (-400..400). Requiere 'x'.",
    ),
) -> dict:
    """
    Lista los oasis con reportes de ataque, con resumen básico.

    Sin filtros → todos los oasis ordenados por last_attack DESC.
    Con x+y → filtra por coordenadas exactas (0 o 1 resultado).
    Con x sin y (o viceversa) → 400. Fuera de -400..400 → 422.
    200 con lista vacía si no hay datos (no 404).

    Ver spec docs/specs/bd-ataques-oasis-stats-oasis-nav.md §8 EP-08.
    """
    if (x is None) != (y is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parámetro 'x' requiere 'y' y viceversa.",
        )
    port = request.app.state.attack_report_port
    return await port.list_oasis_summaries(x=x, y=y)


# ---------------------------------------------------------------------------
# EP-07 — Balance de recursos (ANTES de /{id} para evitar colisión de routing)
# ---------------------------------------------------------------------------

@router.get("/attack-reports/stats/bounty", status_code=status.HTTP_200_OK)
async def get_bounty_stats(
    request: Request,
    x: int | None = Query(
        default=None,
        ge=-400,
        le=400,
        description="Coordenada X del oasis (-400..400). Si se omite junto con y, devuelve el balance global.",
    ),
    y: int | None = Query(
        default=None,
        ge=-400,
        le=400,
        description="Coordenada Y del oasis (-400..400). Requiere 'x'.",
    ),
) -> dict:
    """
    Balance de recursos saqueados.

    Con x+y → balance del oasis específico (scope="oasis").
    Sin x ni y → balance global (scope="global").
    Con x sin y (o viceversa) → 400.
    Fuera de -400..400 → 422 (automático de FastAPI con ge/le).
    200 con todos los totales a 0 si no hay reportes.

    Ver spec docs/specs/bd-ataques-oasis-fix-hora-balance.md §8 EP-07.
    """
    if (x is None) != (y is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parámetro 'x' requiere 'y' y viceversa.",
        )
    port = request.app.state.attack_report_port
    return await port.get_bounty_stats(x=x, y=y)


# ---------------------------------------------------------------------------
# EP-06 — Estadísticas de oasis (ANTES de /{id} para evitar colisión de routing)
# ---------------------------------------------------------------------------

@router.get("/attack-reports/stats/oasis", status_code=status.HTTP_200_OK)
async def get_oasis_stats(
    request: Request,
    x: int | None = Query(default=None),
    y: int | None = Query(default=None),
) -> dict:
    """
    Estadísticas de un oasis: aparición de animales, repoblación temporal y regeneración.

    Requiere x e y (ambos obligatorios). Si no hay reportes → 200 con total_attacks=0 (C7).
    """
    if x is None or y is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Los parámetros 'x' e 'y' son obligatorios.",
        )

    port = request.app.state.attack_report_port
    return await port.get_oasis_stats(x, y)


# ---------------------------------------------------------------------------
# EP-04 — Detail de un reporte
# ---------------------------------------------------------------------------

@router.get("/attack-reports/{id}", status_code=status.HTTP_200_OK)
async def get_report(
    request: Request,
    id: int = Path(..., ge=1, description="ID del reporte (entero ≥ 1)"),  # C6
) -> dict:
    """
    Detalle completo de un reporte: cabecera + tropas + animales + botín.

    C2: hero_inventory es campo raíz, NO dentro de bounty.
    C6: {id} tipado int ge=1 → FastAPI rechaza "stats" con 422.
    """
    port = request.app.state.attack_report_port
    report = await port.get_report(id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reporte no encontrado.",
        )

    # Enriquecer re-parseando el raw_text guardado: así el detalle queda IDÉNTICO
    # al preview (iconos de tropas/animales, tribu, coste de bajas). El parser es
    # determinista, así que re-parsear no cambia los datos; solo añade lo derivado.
    raw_text = report.pop("raw_text", None)
    if raw_text:
        try:
            preview = parse_attack_report(raw_text)
            game_data_port = getattr(request.app.state, "game_data_port", None)
            cost_loss = await _compute_attacker_cost_loss(preview, game_data_port)
            enriched = _preview_to_dict(preview, attacker_cost_loss=cost_loss)
            enriched["id"] = report["id"]
            enriched["created_at"] = report.get("created_at")
            enriched["already_exists"] = True
            enriched["existing_id"] = report["id"]
            return enriched
        except Exception:
            # Si el re-parseo falla (raw_text legacy/corrupto), devolver el dict de BD.
            pass

    return report


# ---------------------------------------------------------------------------
# EP-05 — Delete
# ---------------------------------------------------------------------------

@router.delete("/attack-reports/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    request: Request,
    id: int = Path(..., ge=1, description="ID del reporte a borrar"),
) -> Response:
    """
    Borra un reporte y sus tropas y animales asociados (CASCADE).

    204 No Content si se borró. 404 si no existía.
    """
    port = request.app.state.attack_report_port
    deleted = await port.delete_report(id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reporte no encontrado.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
