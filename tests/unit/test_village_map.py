"""
Tests unitarios de VillageMapUseCase y VillageOverviewParser — sin Chrome, sin red.

Cubre los casos de la sección 12.3 del spec lectura-overview-tronco-comun.
Usa el fixture real tests/fixtures/overview/overview.html para test_village_map_from_fixture,
y HTML sintético para los casos edge.

Fixture real: servidor ts20.x2.america.travian.com, tribu Galos (tribe3).
6 aldeas: game_ids [19040, 24341, 25306, 25875, 26421, 24498], nombres ['00'..'05'].
"""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from adapters.browser.fixture_overview_adapter import FixtureOverviewAdapter
from core.exceptions import SessionNotActiveError
from core.ports.overview_html_source_port import OverviewHtmlSourcePort, OverviewPage
from core.use_cases.village_map import VillageInfo, VillageMapUseCase, VillageOverviewParser

# Ruta al fixture real
REAL_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "overview"

# Datos esperados del fixture real (verificados con el HTML real)
EXPECTED_VILLAGES = [
    VillageInfo(game_id=19040, name="00", x=0, y=0),
    VillageInfo(game_id=24341, name="01", x=0, y=0),
    VillageInfo(game_id=25306, name="02", x=0, y=0),
    VillageInfo(game_id=25875, name="03", x=0, y=0),
    VillageInfo(game_id=26421, name="04", x=0, y=0),
    VillageInfo(game_id=24498, name="05", x=0, y=0),
]


# ---------------------------------------------------------------------------
# Helpers — HTML sintético
# ---------------------------------------------------------------------------


def _make_overview_html(villages: list[tuple[int, str]]) -> str:
    """
    Construye un HTML mínimo con la estructura que espera VillageOverviewParser.
    villages: lista de (game_id, name).
    """
    rows = ""
    for game_id, name in villages:
        rows += f"""
        <tr>
          <td class="vil fc">
            <a href="/dorf1.php?newdid={game_id}">{name}</a>
          </td>
        </tr>
        """
    # Añadir tr.sum (fila de totales que debe ignorarse).
    # En el HTML real de Travian la tr.sum tiene una <td> pero SIN las clases "vil fc",
    # por eso el parser no la incluye en la lista (el filtro es td.vil.fc).
    rows += """
    <tr class="sum">
      <td class="total">Suma total</td>
    </tr>
    """
    return f"""
    <html><body>
      <table id="overview">
        <tbody>{rows}</tbody>
      </table>
    </body></html>
    """


class _FakePort(OverviewHtmlSourcePort):
    """Port fake que devuelve un HTML fijo."""

    def __init__(self, html: str) -> None:
        self._html = html

    async def get_page_html(self, world_id: int, page: OverviewPage) -> str:
        return self._html

    def invalidate_cache(self, world_id: int) -> None:
        pass


class _ErrorPort(OverviewHtmlSourcePort):
    """Port fake que lanza SessionNotActiveError."""

    async def get_page_html(self, world_id: int, page: OverviewPage) -> str:
        raise SessionNotActiveError()

    def invalidate_cache(self, world_id: int) -> None:
        pass


# ---------------------------------------------------------------------------
# Test 12.3.1 — test_village_map_from_fixture
# ---------------------------------------------------------------------------


def test_village_map_from_fixture():
    """
    Usando el fixture real overview.html → lista de 6 VillageInfo correctos.
    Verifica game_id, name y que x=0, y=0 en todos.
    """
    adapter = FixtureOverviewAdapter(fixtures_dir=REAL_FIXTURES_DIR)
    use_case = VillageMapUseCase()

    villages = asyncio.run(use_case.execute(port=adapter, world_id=1))

    assert len(villages) == 6, f"Se esperaban 6 aldeas, se obtuvieron {len(villages)}"
    assert villages == EXPECTED_VILLAGES

    # Verificar x=0, y=0 en todas (placeholder documentado)
    for v in villages:
        assert v.x == 0, f"Aldea {v.name}: x debe ser 0, es {v.x}"
        assert v.y == 0, f"Aldea {v.name}: y debe ser 0, es {v.y}"


# ---------------------------------------------------------------------------
# Test 12.3.2 — test_village_map_single_village
# ---------------------------------------------------------------------------


def test_village_map_single_village():
    """
    HTML sintético con 1 fila tr con td.vil.fc → lista de 1 VillageInfo correcto.
    """
    html = _make_overview_html([(12345, "Mi Aldea")])
    result = VillageOverviewParser.extract_villages(html)

    assert len(result) == 1
    assert result[0].game_id == 12345
    assert result[0].name == "Mi Aldea"
    assert result[0].x == 0
    assert result[0].y == 0


# ---------------------------------------------------------------------------
# Test 12.3.3 — test_village_map_multiple_villages
# ---------------------------------------------------------------------------


def test_village_map_multiple_villages():
    """
    HTML sintético con N filas tr con td.vil.fc → lista de N VillageInfo.
    La tr.sum es ignorada.
    """
    villages_input = [(1001, "Aldea A"), (1002, "Aldea B"), (1003, "Aldea C")]
    html = _make_overview_html(villages_input)
    result = VillageOverviewParser.extract_villages(html)

    assert len(result) == 3, f"Se esperaban 3 aldeas, se obtuvieron {len(result)}"
    assert result[0].game_id == 1001
    assert result[1].game_id == 1002
    assert result[2].game_id == 1003

    # La fila tr.sum no debe aparecer
    assert len(result) == 3, (
        "La fila tr.sum (sin td.vil.fc) no debe incluirse en el resultado"
    )


def test_village_map_tr_sum_ignored():
    """
    La fila tr.sum no tiene td.vil.fc → se omite sin error.
    HTML con 2 aldeas + 1 tr.sum.
    """
    html = _make_overview_html([(2001, "Norte"), (2002, "Sur")])
    result = VillageOverviewParser.extract_villages(html)
    assert len(result) == 2
    names = {v.name for v in result}
    assert "Norte" in names
    assert "Sur" in names
    # La tr.sum sin td.vil.fc no debe aparecer
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Test 12.3.4 — test_village_map_empty_page
# ---------------------------------------------------------------------------


def test_village_map_empty_page():
    """
    HTML sin filas td.vil.fc (cuenta recién creada sin aldeas) → lista vacía, sin excepción.
    """
    html = """
    <html><body>
      <table id="overview"><tbody></tbody></table>
    </body></html>
    """
    result = VillageOverviewParser.extract_villages(html)
    assert result == []


def test_village_map_no_overview_table():
    """
    HTML sin table#overview → lista vacía, sin excepción.
    """
    html = "<html><body><p>Sin tabla overview</p></body></html>"
    result = VillageOverviewParser.extract_villages(html)
    assert result == []


# ---------------------------------------------------------------------------
# Test 12.3.5 — test_village_map_port_error_propagates
# ---------------------------------------------------------------------------


def test_village_map_port_error_propagates():
    """
    Port lanza SessionNotActiveError → la excepción se propaga sin envolver.
    VillageMapUseCase no debe capturar ni envolver la excepción.
    """
    use_case = VillageMapUseCase()
    error_port = _ErrorPort()

    with pytest.raises(SessionNotActiveError):
        asyncio.run(use_case.execute(port=error_port, world_id=1))


# ---------------------------------------------------------------------------
# Tests adicionales
# ---------------------------------------------------------------------------


def test_village_map_use_case_calls_overview_page():
    """
    VillageMapUseCase siempre solicita OverviewPage.OVERVIEW al port.
    """
    requested_pages = []

    class _TrackingPort(OverviewHtmlSourcePort):
        async def get_page_html(self, world_id: int, page: OverviewPage) -> str:
            requested_pages.append(page)
            return _make_overview_html([])

        def invalidate_cache(self, world_id: int) -> None:
            pass

    use_case = VillageMapUseCase()
    asyncio.run(use_case.execute(port=_TrackingPort(), world_id=1))

    assert requested_pages == [OverviewPage.OVERVIEW], (
        f"El use case debe solicitar OverviewPage.OVERVIEW, solicitó: {requested_pages}"
    )


def test_village_info_is_frozen():
    """
    VillageInfo es frozen=True → no se puede modificar.
    """
    v = VillageInfo(game_id=1, name="Test", x=0, y=0)
    with pytest.raises(Exception):  # FrozenInstanceError o AttributeError
        v.game_id = 999  # type: ignore


def test_village_info_equality():
    """
    VillageInfo es un dataclass: dos instancias con mismos valores son iguales.
    """
    v1 = VillageInfo(game_id=100, name="A", x=0, y=0)
    v2 = VillageInfo(game_id=100, name="A", x=0, y=0)
    assert v1 == v2


def test_village_map_parser_strips_name():
    """
    El nombre de la aldea se extrae con strip() — sin espacios extra.
    """
    html = """
    <html><body>
      <table id="overview">
        <tbody>
          <tr>
            <td class="vil fc">
              <a href="/dorf1.php?newdid=555">  Mi Aldea  </a>
            </td>
          </tr>
        </tbody>
      </table>
    </body></html>
    """
    result = VillageOverviewParser.extract_villages(html)
    assert len(result) == 1
    assert result[0].name == "Mi Aldea"
