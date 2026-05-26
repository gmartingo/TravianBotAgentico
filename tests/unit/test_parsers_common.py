"""
Tests unitarios para adapters/browser/parsers/_common.py.

Usa fragmentos HTML reales extraídos de los fixtures de tests/fixtures/overview/
más fragmentos sintéticos para cubrir los casos de retorno None / (0, 0).

Cada función de _common.py tiene su propia clase de tests.
"""
import pytest
from bs4 import BeautifulSoup

from adapters.browser.parsers._common import (
    extract_game_id_from_vil_cell,
    extract_game_id_from_village_name_cell,
    extract_unit_class,
    parse_merchants_text,
)


# ---------------------------------------------------------------------------
# Helpers de construcción de Tags desde HTML
# ---------------------------------------------------------------------------

def _tag(html: str):
    """Devuelve el primer elemento raíz del fragmento HTML."""
    return BeautifulSoup(html, "html.parser").contents[0]


# ---------------------------------------------------------------------------
# extract_game_id_from_vil_cell
# ---------------------------------------------------------------------------

class TestExtractGameIdFromVilCell:

    def test_real_overview_fragment(self):
        """Fragmento real de overview.html — td.vil.fc con newdid=19040."""
        html = (
            '<td class="vil fc">\n'
            '<a href="/dorf1.php?newdid=19040">\n'
            '                    00                </a>\n'
            '</td>'
        )
        cell = _tag(html)
        assert extract_game_id_from_vil_cell(cell) == 19040

    def test_real_resources_fragment(self):
        """Fragmento estilo resources.html — misma estructura td.vil.fc."""
        html = '<td class="vil fc"><a href="/dorf1.php?newdid=24341">01</a></td>'
        cell = _tag(html)
        assert extract_game_id_from_vil_cell(cell) == 24341

    def test_newdid_with_extra_params(self):
        """href con parámetros adicionales después de newdid=."""
        html = '<td class="vil fc"><a href="/build.php?newdid=25306&amp;gid=1">02</a></td>'
        cell = _tag(html)
        assert extract_game_id_from_vil_cell(cell) == 25306

    def test_no_link_returns_none(self):
        """Celda sin enlace → None."""
        html = '<td class="vil fc"><span>Sin aldea</span></td>'
        cell = _tag(html)
        assert extract_game_id_from_vil_cell(cell) is None

    def test_link_without_newdid_returns_none(self):
        """Enlace sin parámetro newdid= → None."""
        html = '<td class="vil fc"><a href="/dorf1.php?gid=5">X</a></td>'
        cell = _tag(html)
        assert extract_game_id_from_vil_cell(cell) is None

    def test_empty_cell_returns_none(self):
        """Celda vacía → None."""
        html = '<td class="vil fc"></td>'
        cell = _tag(html)
        assert extract_game_id_from_vil_cell(cell) is None


# ---------------------------------------------------------------------------
# extract_game_id_from_village_name_cell
# ---------------------------------------------------------------------------

class TestExtractGameIdFromVillageNameCell:

    def test_real_troops_own_fragment(self):
        """Fragmento real de troops_own.html — td.villageName con newdid=19040."""
        html = (
            '<td class="villageName">'
            '<a href="/build.php?newdid=19040&amp;id=39#td">00</a>'
            '</td>'
        )
        cell = _tag(html)
        assert extract_game_id_from_village_name_cell(cell) == 19040

    def test_second_village(self):
        """Segunda aldea del fixture troops_own."""
        html = (
            '<td class="villageName">'
            '<a href="/build.php?newdid=24341&amp;id=39#td">01</a>'
            '</td>'
        )
        cell = _tag(html)
        assert extract_game_id_from_village_name_cell(cell) == 24341

    def test_no_link_returns_none(self):
        """Celda sin enlace → None."""
        html = '<td class="villageName"><span>Sin aldea</span></td>'
        cell = _tag(html)
        assert extract_game_id_from_village_name_cell(cell) is None

    def test_link_without_newdid_returns_none(self):
        """Enlace sin newdid= → None."""
        html = '<td class="villageName"><a href="/build.php?id=39">X</a></td>'
        cell = _tag(html)
        assert extract_game_id_from_village_name_cell(cell) is None

    def test_empty_cell_returns_none(self):
        html = '<td class="villageName"></td>'
        cell = _tag(html)
        assert extract_game_id_from_village_name_cell(cell) is None


# ---------------------------------------------------------------------------
# parse_merchants_text
# ---------------------------------------------------------------------------

class TestParseMerchantsText:

    def test_bidi_14_14(self):
        """Texto bidi real de overview.html: ‭‭14‬/‭14‬‬ → (14, 14)."""
        raw = "‭‭14‬/‭14‬‬"
        assert parse_merchants_text(raw, "game_id=19040") == (14, 14)

    def test_bidi_9_12(self):
        """Texto bidi real: ‭‭9‬/‭12‬‬ → (9, 12)."""
        raw = "‭‭9‬/‭12‬‬"
        assert parse_merchants_text(raw, "game_id=24341") == (9, 12)

    def test_bidi_0_0(self):
        """Texto bidi real (span sin enlace): ‭‭0‬/‭0‬‬ → (0, 0)."""
        raw = "‭‭0‬/‭0‬‬"
        assert parse_merchants_text(raw, "game_id=26421") == (0, 0)

    def test_plain_text(self):
        """Texto sin bidi — también debe funcionar."""
        assert parse_merchants_text("3/10") == (3, 10)

    def test_plain_text_zero(self):
        assert parse_merchants_text("0/0") == (0, 0)

    def test_no_slash_returns_zero_zero(self):
        """Texto sin '/' → (0, 0) con warning."""
        assert parse_merchants_text("14", "ctx") == (0, 0)

    def test_empty_string_returns_zero_zero(self):
        assert parse_merchants_text("") == (0, 0)

    def test_multiple_slashes_uses_first_and_last(self):
        """EC-15: más de un '/' → first y last token."""
        # "1/2/3" → free=1, total=3
        assert parse_merchants_text("1/2/3") == (1, 3)

    def test_non_numeric_returns_zero_zero(self):
        """Texto no numérico → (0, 0) con warning."""
        assert parse_merchants_text("a/b") == (0, 0)

    def test_context_parameter_is_optional(self):
        """context es opcional; no debe fallar si se omite."""
        assert parse_merchants_text("5/15") == (5, 15)

    def test_with_thousands_separator(self):
        """Mercaderes con separador de miles (hipotético, p.ej. 1.000 mercaderes)."""
        assert parse_merchants_text("1.000/1.000") == (1000, 1000)

    def test_bidi_1_1(self):
        """Texto bidi real: ‭‭1‬/‭1‬‬ → (1, 1) — aldea con 1 mercader."""
        raw = "‭‭1‬/‭1‬‬"
        assert parse_merchants_text(raw, "game_id=25306") == (1, 1)

    def test_bidi_12_12(self):
        """Texto bidi real: ‭‭12‬/‭12‬‬ → (12, 12)."""
        raw = "‭‭12‬/‭12‬‬"
        assert parse_merchants_text(raw, "game_id=24498") == (12, 12)


# ---------------------------------------------------------------------------
# extract_unit_class
# ---------------------------------------------------------------------------

class TestExtractUnitClass:

    def test_unit_u22_real_fixture(self):
        """Fragmento real: img.unit.u22 de overview.html td.tro."""
        html = '<img alt="71x Swordsman" class="unit u22" src="/img/x.gif"/>'
        img = _tag(html)
        assert extract_unit_class(img) == "u22"

    def test_unit_u24(self):
        html = '<img alt="22x Theutates Thunder" class="unit u24" src="/img/x.gif"/>'
        img = _tag(html)
        assert extract_unit_class(img) == "u24"

    def test_unit_u26(self):
        html = '<img alt="30x Haeduan" class="unit u26" src="/img/x.gif"/>'
        img = _tag(html)
        assert extract_unit_class(img) == "u26"

    def test_uhero(self):
        """uhero también es una clase de unidad válida."""
        html = '<img alt="1x Hero" class="unit uhero" src="/img/x.gif"/>'
        img = _tag(html)
        assert extract_unit_class(img) == "uhero"

    def test_first_unit_class_wins(self):
        """Cuando hay varias clases de unidad, devuelve la primera."""
        html = '<img class="u22 u24" src="/img/x.gif"/>'
        img = _tag(html)
        assert extract_unit_class(img) == "u22"

    def test_no_unit_class_returns_none(self):
        """Imagen sin clase de unidad → None."""
        html = '<img class="bau" alt="Barracks" src="/img/x.gif"/>'
        img = _tag(html)
        assert extract_unit_class(img) is None

    def test_img_with_only_unit_class_no_unn_returns_none(self):
        """img con clase 'unit' pero sin uNN → None."""
        html = '<img class="unit" src="/img/x.gif"/>'
        img = _tag(html)
        assert extract_unit_class(img) is None

    def test_img_no_classes_returns_none(self):
        """img sin atributo class → None."""
        html = '<img src="/img/x.gif"/>'
        img = _tag(html)
        assert extract_unit_class(img) is None

    def test_class_def1_not_unit_class(self):
        """Clases como 'def1' no son clases de unidad uNN."""
        html = '<img class="def1" alt="618x troops" src="/img/x.gif"/>'
        img = _tag(html)
        assert extract_unit_class(img) is None

    def test_class_att2_not_unit_class(self):
        html = '<img class="att2" alt="381x troops" src="/img/x.gif"/>'
        img = _tag(html)
        assert extract_unit_class(img) is None

    def test_unit_u1_first_roman(self):
        """u1 es válida (primer romano)."""
        html = '<img class="unit u1" src="/img/x.gif"/>'
        img = _tag(html)
        assert extract_unit_class(img) == "u1"

    def test_unit_u91_last_viking(self):
        """u91 es válida (último vikingo)."""
        html = '<img class="unit u91" src="/img/x.gif"/>'
        img = _tag(html)
        assert extract_unit_class(img) == "u91"

    def test_unit_class_uNN_pattern_only(self):
        """Clases que parecen uNN pero no lo son exactamente → None."""
        html = '<img class="u1a" src="/img/x.gif"/>'
        img = _tag(html)
        assert extract_unit_class(img) is None
