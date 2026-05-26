"""
Router del bloque resources: GET /game/resources/{world_id}.

Devuelve recursos almacenados, producción bruta por hora y capacidades de
almacén/granero para todas las aldeas del jugador en el mundo dado.

Las tres páginas de /village/statistics/resources se agregan en una sola
respuesta JSON (decisión de diseño TR-02 del spec lectura-resources):
  - Un único endpoint → 1 petición HTTP del cliente → hasta 3 navegaciones
    internas (con caché de 60 s); vs 3 sub-rutas → 3 peticiones en ráfaga.
  - Reduce el riesgo de detección y simplifica el estado del cliente.

Errores: las TravianBotError (SessionNotActiveError, OverviewPageNotLoadedError,
OverviewFixtureNotFoundError) PROPAGAN al handler global de main.py, que traduce
el `detail` al idioma del Accept-Language y mapea el código HTTP. No se capturan
aquí ni se relanzcan como HTTPException con texto fijo.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from adapters.api.dependencies import (
    get_html_source_port,
    get_language,
    get_translation_port,
)
from adapters.browser.parsers.resources_parser import ResourcesParser
from core.ports.overview_html_source_port import OverviewHtmlSourcePort, OverviewPage
from core.ports.translation_port import TranslationPort
from core.use_cases.resources_use_case import ResourcesUseCase

router = APIRouter(prefix="/game", tags=["game-resources"])


@router.get("/resources/{world_id}")
async def get_resources(
    world_id: int,
    lang: str = Depends(get_language),
    port: OverviewHtmlSourcePort = Depends(get_html_source_port),
    translation_port: TranslationPort = Depends(get_translation_port),
):
    """
    Devuelve almacenado, producción bruta por hora y capacidades de todas
    las aldeas del jugador en el mundo `world_id`.

    El parseo HTML ocurre aquí (adapter→adapter es permitido); el use case del
    core recibe los datos estructurales ya parseados + el idioma + el
    translation_port y devuelve el DTO enriquecido con nombres de recurso localizados.

    Localización:
      - `Accept-Language` es OBLIGATORIA (400 si falta o idioma no soportado).
      - Los nombres de recurso (wood, clay, iron, crop) se localizan al idioma
        del cliente y se exponen en el bloque `resource_names` al nivel raíz.
      - Los campos numéricos usan nombres semánticos en inglés (estables para
        el bot independientemente del idioma del cliente).

    Producción:
      - Los valores de producción son BRUTOS (no restan consumo del ejército).
      - Un valor de `crop` menor que el consumo del ejército es correcto y
        esperado; este bloque solo expone la producción bruta.

    Errores propagados al handler global:
      - SessionNotActiveError        → 503 (sin sesión activa / world_id desconocido)
      - OverviewPageNotLoadedError   → 503 (timeout al cargar la página)
      - OverviewFixtureNotFoundError → 500 (fixture no encontrado, solo en tests)
    """
    # Fetch + parse (las tres llamadas son secuenciales; LiveOverviewAdapter usa
    # caché con double-checked locking — la 2ª y 3ª son cache hits dentro del TTL)
    html_stored = await port.get_page_html(world_id, OverviewPage.RESOURCES)
    villages_stored, stored_totals = ResourcesParser.parse_stored(html_stored)

    html_production = await port.get_page_html(world_id, OverviewPage.RESOURCES_PRODUCTION)
    villages_production, production_totals = ResourcesParser.parse_production(html_production)

    html_capacity = await port.get_page_html(world_id, OverviewPage.RESOURCES_CAPACITY)
    villages_capacity, capacity_totals = ResourcesParser.parse_capacity(html_capacity)

    return ResourcesUseCase.execute(
        villages_stored=villages_stored,
        stored_totals=stored_totals,
        villages_production=villages_production,
        production_totals=production_totals,
        villages_capacity=villages_capacity,
        capacity_totals=capacity_totals,
        lang=lang,
        translation_port=translation_port,
    )
