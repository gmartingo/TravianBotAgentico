"""
Router del bloque overview: GET /game/overview/{world_id}.

Devuelve el estado de todas las aldeas (movimientos entrantes, construcción en curso,
tropas presentes y mercaderes) leído de /village/statistics/overview.

Errores: las TravianBotError (SessionNotActiveError, OverviewPageNotLoadedError,
OverviewFixtureNotFoundError) PROPAGAN al handler global de main.py, que traduce el
`detail` al idioma del Accept-Language y mapea el código HTTP. No se capturan aquí.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from adapters.api.dependencies import (
    get_game_data_port,
    get_html_source_port,
    get_language,
    get_translation_port,
)
from adapters.browser.parsers.overview_parser import OverviewParser
from core.ports.game_data_port import GameDataPort
from core.ports.overview_html_source_port import OverviewHtmlSourcePort, OverviewPage
from core.ports.translation_port import TranslationPort
from core.use_cases.overview_use_case import OverviewUseCase
from core.use_cases.village_map import VillageMapUseCase

router = APIRouter(prefix="/game", tags=["game-overview"])


@router.get("/overview/{world_id}")
async def get_overview(
    world_id: int,
    lang: str = Depends(get_language),
    port: OverviewHtmlSourcePort = Depends(get_html_source_port),
    translation_port: TranslationPort = Depends(get_translation_port),
    game_data_port: GameDataPort = Depends(get_game_data_port),
):
    """
    Estado agregado de todas las aldeas del jugador en el mundo `world_id`.

    El parseo HTML ocurre en el adapter (OverviewParser); el use case del core recibe
    los datos estructurales + el idioma + translation_port + game_data_port y devuelve
    los DTOs enriquecidos con nombres de aldea, nombres de tropa localizados e iconos.

    Las tropas presentes en cada aldea incluyen:
      - unit_class: código estable uNN
      - name: nombre localizado según Accept-Language
      - icon_url: "/static/icons/{icon_id}.png" o None si sin datos en BD
    """
    html = await port.get_page_html(world_id, OverviewPage.OVERVIEW)
    parsed = OverviewParser.extract_overview_data(html)
    village_infos = await VillageMapUseCase().execute(port, world_id)
    names = {v.game_id: v.name for v in village_infos}
    return await OverviewUseCase.execute(
        world_id=world_id,
        parsed_villages=parsed,
        village_names=names,
        lang=lang,
        translation_port=translation_port,
        game_data_port=game_data_port,
    )
