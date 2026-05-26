"""
Tests unitarios de FixtureOverviewAdapter — sin Chrome, sin red.

Cubre los casos de la sección 12.1 del spec lectura-overview-tronco-comun.
Usa los fixtures reales de tests/fixtures/overview/ y fixtures sintéticos en tmp_path.
"""
import asyncio
from pathlib import Path

import pytest

from adapters.browser.fixture_overview_adapter import FixtureOverviewAdapter
from core.exceptions import OverviewFixtureNotFoundError
from core.ports.overview_html_source_port import OverviewPage

# Ruta a los fixtures reales del proyecto
REAL_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "overview"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_adapter(fixtures_dir: Path) -> FixtureOverviewAdapter:
    return FixtureOverviewAdapter(fixtures_dir=fixtures_dir)


def _create_fixture(directory: Path, page: OverviewPage, content: str = "<html></html>") -> None:
    """Crea un fichero {page.value}.html en directory con content."""
    (directory / f"{page.value}.html").write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Test 12.1.1 — test_fixture_returns_html
# ---------------------------------------------------------------------------


def test_fixture_returns_html(tmp_path):
    """
    Fixture existe → get_page_html devuelve el contenido del fichero.
    """
    html_content = "<html><body>overview test</body></html>"
    _create_fixture(tmp_path, OverviewPage.OVERVIEW, html_content)

    adapter = _make_adapter(tmp_path)
    result = asyncio.run(adapter.get_page_html(world_id=1, page=OverviewPage.OVERVIEW))

    assert result == html_content


# ---------------------------------------------------------------------------
# Test 12.1.2 — test_fixture_not_found
# ---------------------------------------------------------------------------


def test_fixture_not_found(tmp_path):
    """
    Fichero {page.value}.html no existe → lanza OverviewFixtureNotFoundError.
    """
    adapter = _make_adapter(tmp_path)

    with pytest.raises(OverviewFixtureNotFoundError):
        asyncio.run(adapter.get_page_html(world_id=1, page=OverviewPage.RESOURCES))


def test_fixture_not_found_carries_page(tmp_path):
    """
    OverviewFixtureNotFoundError lleva el page que no se encontró.
    """
    adapter = _make_adapter(tmp_path)
    page = OverviewPage.CULTURE_POINTS

    with pytest.raises(OverviewFixtureNotFoundError) as exc_info:
        asyncio.run(adapter.get_page_html(world_id=1, page=page))

    assert exc_info.value.page == page


# ---------------------------------------------------------------------------
# Test 12.1.3 — test_fixture_invalidate_noop
# ---------------------------------------------------------------------------


def test_fixture_invalidate_noop(tmp_path):
    """
    invalidate_cache no lanza ni falla — es no-op en el adaptador de fixtures.
    """
    adapter = _make_adapter(tmp_path)
    # No debe lanzar ninguna excepción
    adapter.invalidate_cache(world_id=42)
    adapter.invalidate_cache(world_id=0)


# ---------------------------------------------------------------------------
# Test 12.1.4 — test_fixture_all_pages
# ---------------------------------------------------------------------------


def test_fixture_all_pages():
    """
    Con los 10 fixtures reales presentes, cada OverviewPage devuelve HTML no vacío.
    Usa los fixtures reales de tests/fixtures/overview/.
    """
    adapter = _make_adapter(REAL_FIXTURES_DIR)

    for page in OverviewPage:
        html = asyncio.run(adapter.get_page_html(world_id=99, page=page))
        assert html, f"El fixture de {page.value} devolvió HTML vacío"
        assert len(html.strip()) > 0, f"El fixture de {page.value} es solo whitespace"


# ---------------------------------------------------------------------------
# Tests adicionales de robustez
# ---------------------------------------------------------------------------


def test_fixture_world_id_ignored(tmp_path):
    """
    El world_id no afecta al resultado — el adaptador lo ignora.
    """
    html_content = "<html><body>troops_own</body></html>"
    _create_fixture(tmp_path, OverviewPage.TROOPS_OWN, html_content)

    adapter = _make_adapter(tmp_path)
    r1 = asyncio.run(adapter.get_page_html(world_id=1, page=OverviewPage.TROOPS_OWN))
    r2 = asyncio.run(adapter.get_page_html(world_id=999, page=OverviewPage.TROOPS_OWN))

    assert r1 == r2 == html_content


def test_fixture_filename_convention(tmp_path):
    """
    Convención de nombre verificada: {page.value}.html
    Crea ficheros con los nombres correctos e incorrectos y verifica cuál funciona.
    """
    # Crear con nombre correcto
    (tmp_path / "culturepoints.html").write_text("<html>cp</html>", encoding="utf-8")
    # NO crear "culture_points.html" — el enum value es "culturepoints"

    adapter = _make_adapter(tmp_path)

    # Debe funcionar con OverviewPage.CULTURE_POINTS (value = "culturepoints")
    result = asyncio.run(adapter.get_page_html(world_id=1, page=OverviewPage.CULTURE_POINTS))
    assert "<html>cp</html>" in result


def test_fixture_enum_values_match_filenames():
    """
    Verifica que los 10 valores del enum coinciden con los 10 nombres de fixture.
    Esta es la fuente de verdad del contrato de naming.
    """
    expected = {
        "overview", "resources", "resources_production", "resources_capacity",
        "culturepoints", "troops_own", "troops_support", "troops_smithy",
        "troops_hospital", "troops_training",
    }
    actual = {page.value for page in OverviewPage}
    assert actual == expected, f"Valores del enum no coinciden: {actual ^ expected}"
