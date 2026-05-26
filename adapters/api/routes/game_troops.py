"""
Router del bloque troops: 5 sub-rutas GET /game/troops/{world_id}/<vista>.

Vistas disponibles:
  - /own       → tropas totales (ejército) por aldea
  - /support   → tropas presentes en cada aldea
  - /smithy    → nivel de mejora en herrería por aldea
  - /hospital  → heridos por tipo y estado del hospital por aldea
  - /training  → tiempo de cola en edificios de entrenamiento por aldea

Política de errores:
  Las TravianBotError (SessionNotActiveError, OverviewPageNotLoadedError,
  OverviewFixtureNotFoundError) PROPAGAN al handler global de main.py, que
  traduce el `detail` al idioma del Accept-Language y mapea el HTTP status
  via ERROR_HTTP_MAP. No se capturan aquí (sección 9.7 del spec).

Localización FUNCIONAL (RN-09):
  Accept-Language es obligatoria. El idioma resuelto governa troop_types[].name,
  troop_names y buildings[].name via translation_port en el use case.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from adapters.api.dependencies import (
    get_game_data_port,
    get_html_source_port,
    get_language,
    get_translation_port,
)
from adapters.browser.parsers.troops_parser import TroopsParser
from core.ports.game_data_port import GameDataPort
from core.ports.overview_html_source_port import OverviewHtmlSourcePort, OverviewPage
from core.ports.translation_port import TranslationPort
from core.use_cases.troops_use_case import TroopsUseCase

router = APIRouter(prefix="/game/troops", tags=["game-troops"])


@router.get("/{world_id}/own")
async def get_troops_own(
    world_id: int,
    lang: str = Depends(get_language),
    port: OverviewHtmlSourcePort = Depends(get_html_source_port),
    translation_port: TranslationPort = Depends(get_translation_port),
    game_data_port: GameDataPort = Depends(get_game_data_port),
):
    """
    Tropas totales (ejército máximo) por aldea y por tipo.

    Devuelve TroopsOwnResponse: troop_types (con nombres localizados e icon_url),
    villages y totals.
    Accept-Language: obligatoria (400 si falta o no soportada).
    """
    html = await port.get_page_html(world_id, OverviewPage.TROOPS_OWN)
    raw = TroopsParser.parse_own(html)
    return await TroopsUseCase.get_own(raw, lang, translation_port, game_data_port)


@router.get("/{world_id}/support")
async def get_troops_support(
    world_id: int,
    lang: str = Depends(get_language),
    port: OverviewHtmlSourcePort = Depends(get_html_source_port),
    translation_port: TranslationPort = Depends(get_translation_port),
    game_data_port: GameDataPort = Depends(get_game_data_port),
):
    """
    Tropas presentes en cada aldea en el momento de la consulta.

    Devuelve TroopsSupportResponse: troop_names (uNN → nombre localizado) y villages.
    Incluye tropas propias, de naturaleza (u31-u40) y héroe.
    Accept-Language: obligatoria.
    """
    html = await port.get_page_html(world_id, OverviewPage.TROOPS_SUPPORT)
    raw = TroopsParser.parse_support(html)
    return await TroopsUseCase.get_support(raw, lang, translation_port, game_data_port)


@router.get("/{world_id}/smithy")
async def get_troops_smithy(
    world_id: int,
    lang: str = Depends(get_language),
    port: OverviewHtmlSourcePort = Depends(get_html_source_port),
    translation_port: TranslationPort = Depends(get_translation_port),
    game_data_port: GameDataPort = Depends(get_game_data_port),
):
    """
    Nivel de mejora de tropas en herrería por aldea + investigación activa.

    Devuelve TroopsSmithyResponse: troop_types (con nombres localizados e icon_url)
    y villages.
    Accept-Language: obligatoria.
    """
    html = await port.get_page_html(world_id, OverviewPage.TROOPS_SMITHY)
    raw = TroopsParser.parse_smithy(html)
    return await TroopsUseCase.get_smithy(raw, lang, translation_port, game_data_port)


@router.get("/{world_id}/hospital")
async def get_troops_hospital(
    world_id: int,
    lang: str = Depends(get_language),
    port: OverviewHtmlSourcePort = Depends(get_html_source_port),
    translation_port: TranslationPort = Depends(get_translation_port),
    game_data_port: GameDataPort = Depends(get_game_data_port),
):
    """
    Heridos por tipo y estado del hospital de cada aldea.

    Devuelve TroopsHospitalResponse: player_tribe, troop_types (con icon_url)
    y villages.
    Accept-Language: obligatoria.
    """
    html = await port.get_page_html(world_id, OverviewPage.TROOPS_HOSPITAL)
    raw = TroopsParser.parse_hospital(html)
    return await TroopsUseCase.get_hospital(raw, lang, translation_port, game_data_port)


@router.get("/{world_id}/training")
async def get_troops_training(
    world_id: int,
    lang: str = Depends(get_language),
    port: OverviewHtmlSourcePort = Depends(get_html_source_port),
    translation_port: TranslationPort = Depends(get_translation_port),
    game_data_port: GameDataPort = Depends(get_game_data_port),
):
    """
    Tiempo de cola restante en edificios de entrenamiento por aldea.

    Devuelve TroopsTrainingResponse: buildings (con nombres localizados e icon_url),
    building_gids y villages.
    icon_url de edificios es None hoy (building_catalog vacío en BD) —
    se rellenará al cargar el catálogo kirilloid.
    Accept-Language: obligatoria.
    """
    html = await port.get_page_html(world_id, OverviewPage.TROOPS_TRAINING)
    raw = TroopsParser.parse_training(html)
    return await TroopsUseCase.get_training(raw, lang, translation_port, game_data_port)
