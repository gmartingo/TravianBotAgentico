"""
Router del bloque culture-points: GET /game/culture-points/{world_id}.

Devuelve los culture points, fiestas activas y slots de fundación de todas las
aldeas del jugador en el mundo world_id, leídos de /village/statistics/culturepoints.

Accept-Language obligatoria: 400 si falta o idioma no soportado.
Los datos son exclusivamente numéricos — no se inyecta translation_port (TR-03, RN-07).
El idioma resuelto se expone en el campo `lang` de la respuesta para trazabilidad.

Errores: SessionNotActiveError, OverviewPageNotLoadedError y OverviewFixtureNotFoundError
PROPAGAN al handler global de main.py (travian_bot_error_handler), que los traduce al
idioma del Accept-Language y asigna el HTTP status correcto via ERROR_HTTP_MAP.
No se capturan aquí ni se re-lanzan como HTTPException con texto fijo — esto garantiza
que los mensajes de error 503/500 también salgan localizados (corrección de diseño).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from adapters.api.dependencies import get_html_source_port, get_language
from adapters.browser.parsers.culture_points_parser import CulturePointsParser
from core.ports.overview_html_source_port import OverviewHtmlSourcePort, OverviewPage
from core.use_cases.culture_points_use_case import CulturePointsUseCase

router = APIRouter(prefix="/game", tags=["game-culture-points"])


@router.get("/culture-points/{world_id}")
async def get_culture_points(
    world_id: int,
    lang: str = Depends(get_language),
    port: OverviewHtmlSourcePort = Depends(get_html_source_port),
):
    """
    Devuelve los culture points, fiestas activas y slots de fundación
    de todas las aldeas del jugador en world_id.

    El parseo HTML ocurre aquí (adapter→adapter); el use case del core recibe
    el CulturePointsSummary ya parseado y lo devuelve (patrón consistente con
    los otros 3 bloques).

    Accept-Language obligatoria (400 si falta o no soportada).

    Los datos son exclusivamente numéricos; el idioma se expone en `lang`
    para trazabilidad pero no altera los valores de los campos.

    SessionNotActiveError, OverviewPageNotLoadedError y OverviewFixtureNotFoundError
    se dejan PROPAGAR al handler global de main.py, que traduce el detail al idioma
    del cliente y mapea el código HTTP. No se capturan aquí.
    """
    html = await port.get_page_html(world_id=world_id, page=OverviewPage.CULTURE_POINTS)
    parsed = CulturePointsParser.parse(html)
    summary = CulturePointsUseCase.execute(parsed)

    return {
        "world_id": world_id,
        "lang": lang,
        "cp_total_per_day": summary.cp_total_per_day,
        "slots_used_total": summary.slots_used_total,
        "slots_total": summary.slots_total,
        "villages": [
            {
                "game_id": v.game_id,
                "name": v.name,
                "cp_per_day": v.cp_per_day,
                "celebration_seconds_remaining": v.celebration_seconds_remaining,
                "slots_used": v.slots_used,
                "slots_total": v.slots_total,
            }
            for v in summary.villages
        ],
    }
