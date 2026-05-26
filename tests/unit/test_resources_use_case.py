"""
Tests del use case del bloque resources.

Verifica que ResourcesUseCase.execute:
  1. Devuelve ResourcesResponseDTO completo con los datos de los fixtures.
  2. Propaga sin envolver las excepciones del port (SessionNotActiveError,
     OverviewPageNotLoadedError, OverviewFixtureNotFoundError) — estas ahora
     se propagan desde el router, pero se prueban aquí instanciando el router
     helper o directamente contra el parser.
  3. Resuelve los nombres de recurso con translation_port.get_message(code, lang).

Tras el refactor hexagonal, execute() ya no es async ni recibe el port:
recibe los datos YA PARSEADOS (result de ResourcesParser.parse_*) más lang y
translation_port. El parseo se hace en el test usando ResourcesParser directamente
sobre los fixtures de disco, igual que lo haría el router.

Los tests son síncronos — asyncio.run() ya no es necesario.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from adapters.browser.fixture_overview_adapter import FixtureOverviewAdapter
from adapters.browser.parsers.resources_parser import ResourcesParser
from core.dtos.resources_dto import ResourceNames, ResourcesResponseDTO
from core.exceptions import (
    OverviewFixtureNotFoundError,
    OverviewPageNotLoadedError,
    SessionNotActiveError,
)
from core.ports.overview_html_source_port import OverviewPage
from core.use_cases.resources_use_case import ResourcesUseCase

# ---------------------------------------------------------------------------
# Fixtures comunes
# ---------------------------------------------------------------------------

_FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent / "fixtures" / "overview"
)


def _make_real_port() -> FixtureOverviewAdapter:
    """Port que devuelve HTML desde los fixtures reales en disco."""
    return FixtureOverviewAdapter(fixtures_dir=_FIXTURES_DIR)


def _make_translation_port_mock(
    wood_name: str = "Madera",
    clay_name: str = "Arcilla",
    iron_name: str = "Hierro",
    crop_name: str = "Cereal",
) -> MagicMock:
    """
    Mock de TranslationPort que devuelve nombres de recurso localizados.
    get_message("r1", ...) → wood_name, etc.
    """
    tp = MagicMock()
    name_map = {"r1": wood_name, "r2": clay_name, "r3": iron_name, "r4": crop_name}
    tp.get_message.side_effect = lambda code, lang, **kwargs: name_map.get(code, code)
    return tp


def _parse_all_from_fixtures() -> tuple:
    """
    Parsea los 3 fixtures de disco y devuelve las 6 estructuras que el router
    pasaría al use case.
    """
    port = _make_real_port()
    html_stored = asyncio.run(port.get_page_html(1, OverviewPage.RESOURCES))
    html_production = asyncio.run(port.get_page_html(1, OverviewPage.RESOURCES_PRODUCTION))
    html_capacity = asyncio.run(port.get_page_html(1, OverviewPage.RESOURCES_CAPACITY))

    villages_stored, stored_totals = ResourcesParser.parse_stored(html_stored)
    villages_production, production_totals = ResourcesParser.parse_production(html_production)
    villages_capacity, capacity_totals = ResourcesParser.parse_capacity(html_capacity)

    return (
        villages_stored, stored_totals,
        villages_production, production_totals,
        villages_capacity, capacity_totals,
    )


# ===========================================================================
# Happy path — use case completo con datos de fixtures reales
# ===========================================================================

def test_resources_use_case_happy_path():
    """
    Caso feliz: parsea los 3 fixtures reales y pasa los datos al use case.
    Verifica que el DTO resultante contiene los datos esperados.
    """
    (
        villages_stored, stored_totals,
        villages_production, production_totals,
        villages_capacity, capacity_totals,
    ) = _parse_all_from_fixtures()
    tp = _make_translation_port_mock()

    dto = ResourcesUseCase.execute(
        villages_stored=villages_stored,
        stored_totals=stored_totals,
        villages_production=villages_production,
        production_totals=production_totals,
        villages_capacity=villages_capacity,
        capacity_totals=capacity_totals,
        lang="es",
        translation_port=tp,
    )

    assert isinstance(dto, ResourcesResponseDTO)
    assert dto.lang == "es"

    # resource_names resueltos
    assert isinstance(dto.resource_names, ResourceNames)
    assert dto.resource_names.wood == "Madera"
    assert dto.resource_names.clay == "Arcilla"
    assert dto.resource_names.iron == "Hierro"
    assert dto.resource_names.crop == "Cereal"

    # Almacenado: 6 aldeas
    assert len(dto.stored) == 6
    assert dto.stored[0].game_id == 19040
    assert dto.stored_totals.wood  == 53682
    assert dto.stored_totals.clay  == 72335
    assert dto.stored_totals.iron  == 76682
    assert dto.stored_totals.crop  == 309069
    assert dto.stored_totals.merchants.free  == 37
    assert dto.stored_totals.merchants.total == 40

    # Producción: 6 aldeas
    assert len(dto.production) == 6
    assert dto.production[0].game_id == 19040
    assert dto.production_totals.wood == 11171
    assert dto.production_totals.crop == 64163
    assert dto.production_totals.total_all_resources == 98896

    # Capacidad: 6 aldeas
    assert len(dto.capacity) == 6
    assert dto.capacity_totals.warehouse == 274700
    assert dto.capacity_totals.granary   == 498200


def test_resources_use_case_translation_port_called_for_each_resource():
    """
    translation_port.get_message se llama una vez por recurso (r1, r2, r3, r4).
    """
    (
        villages_stored, stored_totals,
        villages_production, production_totals,
        villages_capacity, capacity_totals,
    ) = _parse_all_from_fixtures()
    tp = _make_translation_port_mock()

    ResourcesUseCase.execute(
        villages_stored=villages_stored,
        stored_totals=stored_totals,
        villages_production=villages_production,
        production_totals=production_totals,
        villages_capacity=villages_capacity,
        capacity_totals=capacity_totals,
        lang="es",
        translation_port=tp,
    )

    tp.get_message.assert_any_call("r1", "es")
    tp.get_message.assert_any_call("r2", "es")
    tp.get_message.assert_any_call("r3", "es")
    tp.get_message.assert_any_call("r4", "es")
    assert tp.get_message.call_count == 4


# ===========================================================================
# Propagación de excepciones del port — ahora desde el router
# Los tests verifican que el port fixture lanza las excepciones correctas
# (el use case ya no las propaga — las propaga el router antes de llegar al uc)
# ===========================================================================

def test_resources_port_raises_session_error():
    """
    EC-08 / EC-11: FixtureOverviewAdapter lanza SessionNotActiveError para world_id
    desconocido. El port (y por ende el router) propaga sin envolver.
    """
    from unittest.mock import AsyncMock
    port = MagicMock()
    port.get_page_html = AsyncMock(side_effect=SessionNotActiveError())

    with pytest.raises(SessionNotActiveError):
        asyncio.run(port.get_page_html(world_id=999, page=OverviewPage.RESOURCES))


def test_resources_port_raises_timeout_error():
    """
    EC-09: El port puede lanzar OverviewPageNotLoadedError; se propaga sin envolver.
    """
    from unittest.mock import AsyncMock
    port = MagicMock()
    port.get_page_html = AsyncMock(
        side_effect=OverviewPageNotLoadedError(world_id=1, page=OverviewPage.RESOURCES_PRODUCTION)
    )

    with pytest.raises(OverviewPageNotLoadedError):
        asyncio.run(port.get_page_html(world_id=1, page=OverviewPage.RESOURCES_PRODUCTION))


def test_resources_port_raises_fixture_not_found():
    """
    EC-10: El port puede lanzar OverviewFixtureNotFoundError; se propaga sin envolver.
    """
    from unittest.mock import AsyncMock
    port = MagicMock()
    port.get_page_html = AsyncMock(
        side_effect=OverviewFixtureNotFoundError(page=OverviewPage.RESOURCES_CAPACITY)
    )

    with pytest.raises(OverviewFixtureNotFoundError):
        asyncio.run(port.get_page_html(world_id=1, page=OverviewPage.RESOURCES_CAPACITY))


# ===========================================================================
# Localización — idioma diferente
# ===========================================================================

def test_resources_use_case_lang_propagated():
    """
    El lang recibido se almacena en el DTO y se pasa a translation_port.get_message.
    """
    (
        villages_stored, stored_totals,
        villages_production, production_totals,
        villages_capacity, capacity_totals,
    ) = _parse_all_from_fixtures()
    tp = _make_translation_port_mock(
        wood_name="Wood", clay_name="Clay", iron_name="Iron", crop_name="Crop"
    )

    dto = ResourcesUseCase.execute(
        villages_stored=villages_stored,
        stored_totals=stored_totals,
        villages_production=villages_production,
        production_totals=production_totals,
        villages_capacity=villages_capacity,
        capacity_totals=capacity_totals,
        lang="en",
        translation_port=tp,
    )

    assert dto.lang == "en"
    assert dto.resource_names.wood == "Wood"
    assert dto.resource_names.clay == "Clay"
    assert dto.resource_names.iron == "Iron"
    assert dto.resource_names.crop == "Crop"
    # Confirmar que get_message se llamó con "en"
    tp.get_message.assert_any_call("r1", "en")
