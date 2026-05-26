"""
Tests del parser del bloque resources.

Todos los tests cargan los fixtures reales desde tests/fixtures/overview/:
  - resources.html          → parse_stored
  - resources_production.html → parse_production
  - resources_capacity.html   → parse_capacity

Los valores esperados se han verificado contra esos fixtures reales
(ts20.x2.america.travian.com, T4.x, tribu Galos → 6 aldeas).

Nomenclatura de los tests:
  test_parse_stored_*      → tabla #ressources (almacenado)
  test_parse_production_*  → tabla #production (producción bruta por hora)
  test_parse_capacity_*    → tabla #capacity   (capacidad almacén/granero)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from adapters.browser.parsers.resources_parser import ResourcesParser
from core.dtos.resources_dto import (
    StoredTotals,
    VillageStoredResources,
    VillageProductionResources,
    ProductionTotals,
    VillageCapacity,
    CapacityTotals,
    VillageMerchants,
)

# ---------------------------------------------------------------------------
# Rutas absolutas a los fixtures
# ---------------------------------------------------------------------------

_FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent / "fixtures" / "overview"
)
_STORED_FIXTURE     = _FIXTURES_DIR / "resources.html"
_PRODUCTION_FIXTURE = _FIXTURES_DIR / "resources_production.html"
_CAPACITY_FIXTURE   = _FIXTURES_DIR / "resources_capacity.html"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_stored_data():
    """Parsea el fixture de almacenado (cached para no releer en cada test)."""
    return ResourcesParser.parse_stored(_read(_STORED_FIXTURE))


def _get_production_data():
    return ResourcesParser.parse_production(_read(_PRODUCTION_FIXTURE))


def _get_capacity_data():
    return ResourcesParser.parse_capacity(_read(_CAPACITY_FIXTURE))


# ===========================================================================
# SECCIÓN 1 — parse_stored (tabla #ressources)
# ===========================================================================

def test_parse_stored_village_count():
    """Debe haber exactamente 6 aldeas en la lista (sin la fila sum)."""
    villages, _ = _get_stored_data()
    assert len(villages) == 6


def test_parse_stored_village_game_ids():
    """Los game_id de las 6 aldeas deben coincidir con los del fixture."""
    villages, _ = _get_stored_data()
    ids = [v.game_id for v in villages]
    assert ids == [19040, 24341, 25306, 25875, 26421, 24498]


def test_parse_stored_first_village():
    """Primera aldea (19040): valores completos de recursos y mercaderes."""
    villages, _ = _get_stored_data()
    v = villages[0]
    assert v.game_id == 19040
    assert v.wood   == 8786
    assert v.clay   == 16423
    assert v.iron   == 1445
    assert v.crop   == 36881
    assert v.merchants.free  == 14
    assert v.merchants.total == 14


def test_parse_stored_third_village_merchants():
    """Aldea 25306: mercaderes con libres == totales (caso 1/1)."""
    villages, _ = _get_stored_data()
    v = next(v for v in villages if v.game_id == 25306)
    assert v.merchants.free  == 1
    assert v.merchants.total == 1


def test_parse_stored_zero_merchants():
    """Aldea 26421: sin mercado → 0/0 (EC-01 y RN-06: no es error)."""
    villages, _ = _get_stored_data()
    v = next(v for v in villages if v.game_id == 26421)
    assert v.merchants.free  == 0
    assert v.merchants.total == 0


def test_parse_stored_totals():
    """Fila tr.sum: totales globales de recursos y mercaderes."""
    _, totals = _get_stored_data()
    assert totals.wood  == 53682
    assert totals.clay  == 72335
    assert totals.iron  == 76682
    assert totals.crop  == 309069
    assert totals.merchants.free  == 37
    assert totals.merchants.total == 40


def test_parse_stored_no_sum_link():
    """
    Los mercaderes en la fila sum NO tienen <a> (texto directo en td.tra).
    Verifica EC-03 y RN-02: _parse_merchants maneja ambos casos.
    Los valores son los mismos que en test_parse_stored_totals.
    """
    _, totals = _get_stored_data()
    # Si _parse_merchants falla con texto directo (sin <a>), devolvería 0/0
    assert totals.merchants.free  != 0 or totals.merchants.total != 0  # no son 0/0
    assert totals.merchants.free  == 37
    assert totals.merchants.total == 40


def test_parse_stored_bidi_numbers():
    """
    Los números del fixture tienen caracteres bidi U+202D/U+202C.
    parse_int los limpia antes de convertir; el resultado es un int limpio.
    Ningún campo de recursos debe contener caracteres de control.
    """
    villages, totals = _get_stored_data()
    for v in villages:
        for field in (v.wood, v.clay, v.iron, v.crop):
            assert isinstance(field, int), f"Esperado int, obtenido {type(field)}: {field}"
    assert isinstance(totals.wood, int)
    assert isinstance(totals.clay, int)


def test_parse_stored_all_villages_are_dataclass():
    """Todos los elementos de la lista son VillageStoredResources frozen."""
    villages, _ = _get_stored_data()
    for v in villages:
        assert isinstance(v, VillageStoredResources)
    # frozen=True: no se puede modificar
    v = villages[0]
    with pytest.raises((AttributeError, TypeError)):
        v.wood = 999  # type: ignore[misc]


def test_parse_stored_totals_is_dataclass():
    """Los totales son StoredTotals frozen."""
    _, totals = _get_stored_data()
    assert isinstance(totals, StoredTotals)


# ===========================================================================
# SECCIÓN 2 — parse_production (tabla #production)
# ===========================================================================

def test_parse_production_village_count():
    """Debe haber exactamente 6 aldeas en la lista de producción."""
    villages, _ = _get_production_data()
    assert len(villages) == 6


def test_parse_production_first_village():
    """Primera aldea (19040): valores completos de producción bruta."""
    villages, _ = _get_production_data()
    v = villages[0]
    assert v.game_id == 19040
    assert v.wood == 3500
    assert v.clay == 4200
    assert v.iron == 3500
    assert v.crop == 5487


def test_parse_production_totals_per_resource():
    """Totales de producción bruta por recurso (fila tr.sum)."""
    _, totals = _get_production_data()
    assert totals.wood == 11171
    assert totals.clay == 12862
    assert totals.iron == 10700
    assert totals.crop == 64163


def test_parse_production_total_all_resources():
    """
    Campo total_all_resources de tr.sum > td.vil > span.total.
    Suma global de todos los recursos de todas las aldeas.
    """
    _, totals = _get_production_data()
    assert totals.total_all_resources == 98896


def test_parse_production_crop_is_gross():
    """
    RN-01: la producción de crop es BRUTA — no resta consumo del ejército.
    El valor parseado debe coincidir exactamente con el del fixture (sin ajuste).
    Este test documenta el comportamiento esperado, no hay ajuste de negocio.
    """
    villages, _ = _get_production_data()
    v = next(v for v in villages if v.game_id == 19040)
    # El valor es el del fixture: producción bruta tal cual aparece en Travian
    assert v.crop == 5487  # valor bruto, puede ser menor que el consumo del ejército


def test_parse_production_no_span_total():
    """
    EC-07: si span.total no existe en tr.sum, total_all_resources debe ser None.
    Se construye un HTML mínimo sin ese elemento.
    """
    html_sin_span = """
    <table id="production">
      <tbody>
        <tr>
          <td class="vil fc"><a href="?newdid=1">Aldea</a></td>
          <td class="lum">100</td><td class="clay">200</td>
          <td class="iron">150</td><td class="crop">300</td>
        </tr>
        <tr class="empty"><td colspan="5"></td></tr>
        <tr class="sum">
          <td class="vil"><span>Sin span.total aquí</span></td>
          <td class="lum">100</td><td class="clay">200</td>
          <td class="iron">150</td><td class="crop">300</td>
        </tr>
      </tbody>
    </table>
    """
    _, totals = ResourcesParser.parse_production(html_sin_span)
    assert totals.total_all_resources is None


def test_parse_production_all_villages_are_dataclass():
    """Todos los elementos son VillageProductionResources frozen."""
    villages, _ = _get_production_data()
    for v in villages:
        assert isinstance(v, VillageProductionResources)


def test_parse_production_totals_is_dataclass():
    """Los totales son ProductionTotals frozen."""
    _, totals = _get_production_data()
    assert isinstance(totals, ProductionTotals)


# ===========================================================================
# SECCIÓN 3 — parse_capacity (tabla #capacity)
# ===========================================================================

def test_parse_capacity_village_count():
    """Debe haber exactamente 6 aldeas en la lista de capacidades."""
    villages, _ = _get_capacity_data()
    assert len(villages) == 6


def test_parse_capacity_first_village():
    """Primera aldea (19040): capacidad almacén y granero."""
    villages, _ = _get_capacity_data()
    v = villages[0]
    assert v.game_id   == 19040
    assert v.warehouse == 80000
    assert v.granary   == 80000


def test_parse_capacity_second_village():
    """Segunda aldea (24341): capacidades altas (almacén y granero diferentes)."""
    villages, _ = _get_capacity_data()
    v = villages[1]
    assert v.game_id   == 24341
    assert v.warehouse == 105900
    assert v.granary   == 320000


def test_parse_capacity_small_village():
    """Aldea 26421 (pequeña): capacidades bajas (EC-12: números sin separadores)."""
    villages, _ = _get_capacity_data()
    v = next(v for v in villages if v.game_id == 26421)
    assert v.warehouse == 7800
    assert v.granary   == 5000


def test_parse_capacity_totals():
    """Totales de capacidad (fila tr.sum)."""
    _, totals = _get_capacity_data()
    assert totals.warehouse == 274700
    assert totals.granary   == 498200


def test_parse_capacity_all_villages_are_dataclass():
    """Todos los elementos son VillageCapacity frozen."""
    villages, _ = _get_capacity_data()
    for v in villages:
        assert isinstance(v, VillageCapacity)


def test_parse_capacity_totals_is_dataclass():
    """Los totales son CapacityTotals frozen."""
    _, totals = _get_capacity_data()
    assert isinstance(totals, CapacityTotals)


# ===========================================================================
# SECCIÓN 4 — Robustez: selectores estructurales (no por texto)
# ===========================================================================

def test_parse_stored_ignores_empty_rows():
    """
    EC-02: las filas tr.empty (separadores visuales) no producen entradas en la lista.
    Ya verificado implícitamente porque el count correcto es 6 (no 7 u 8).
    """
    villages, _ = _get_stored_data()
    # Si las filas empty se contaran, habría más de 6 aldeas
    assert len(villages) == 6


def test_parse_stored_sum_not_in_villages():
    """
    RN-03: la fila tr.sum no debe aparecer en la lista de aldeas.
    Los game_id de la lista no incluyen None ni valores de la fila sum.
    """
    villages, totals = _get_stored_data()
    # La fila sum no tiene td.vil.fc con newdid, así que no debe estar en la lista
    assert all(v.game_id is not None for v in villages)
    assert len(villages) == 6  # exactamente las 6 aldeas, no más


def test_parse_stored_game_ids_are_ints():
    """Los game_id son todos enteros (no strings ni None)."""
    villages, _ = _get_stored_data()
    for v in villages:
        assert isinstance(v.game_id, int)


def test_parse_merchants_dataclass():
    """Los merchants de cada aldea son VillageMerchants frozen."""
    villages, _ = _get_stored_data()
    for v in villages:
        assert isinstance(v.merchants, VillageMerchants)
