"""
Tests unitarios del scraper de kirilloid — SIN browser, SIN Chrome.

Verifica las funciones puras de parseo y el merge de troops.json.
Las funciones que requieren browser (_capture_*, _parse_main_table, etc.)
se verifican con tests de comportamiento mock (filesystem y DOM simulado).

Los mocks de Element y Tab siguen la API REAL de zendriver:
  - Element.text es @property (str), no método async
  - Element.parent es @property (Element|None), no método async
  - Element.attrs es ContraDict; "class" se almacena como "class_"
  - Element.attrs.get("unit") devuelve str o None
  - Tab.query_selector(css) → async → Element|None
  - Tab.query_selector_all(css) → async → list[Element]
  - Element.query_selector(css) → async → Element|None
  - Element.query_selector_all(css) → async → list[Element]
  - Element.screenshot_b64(format, scale) → async → str (base64)
  - NO existe element.find / element.find_all / element.get_attribute / element.text() / element.parent()
"""
import base64
import json
import os
import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from PIL import Image

from adapters.scraper.kirilloid_scraper import (
    ICONS_DIR,
    _color_distance,
    _merge_troop_names,
    _remove_background,
)
from core.utils.parsing import parse_int as _parse_int, parse_int_or_none as _parse_int_or_none, parse_time as _parse_time


# ---------------------------------------------------------------------------
# Tests — _parse_time
# ---------------------------------------------------------------------------


def test_parse_time_valid():
    """'1:23:45' → 5025 segundos."""
    assert _parse_time("1:23:45") == 5025


def test_parse_time_zero():
    """'0:00:00' → 0 segundos (EC-02: tiempo cero es válido)."""
    assert _parse_time("0:00:00") == 0


def test_parse_time_leading_zero():
    """'0:05:30' → 330 segundos."""
    assert _parse_time("0:05:30") == 330


def test_parse_time_large_hours():
    """'2:30:00' → 9000 segundos."""
    assert _parse_time("2:30:00") == 9000


def test_parse_time_with_extra_info():
    """'0:30:00 / 2880 / jornada' → solo usa la primera parte → 1800 segundos (RN-08)."""
    assert _parse_time("0:30:00 / 2880 / jornada") == 1800


def test_parse_time_invalid_raises():
    """'no-es-tiempo' → ValueError."""
    with pytest.raises(ValueError):
        _parse_time("no-es-tiempo")


def test_parse_time_invalid_parts_raises():
    """'12:34' (solo 2 partes) → ValueError."""
    with pytest.raises(ValueError):
        _parse_time("12:34")


def test_parse_time_bare_zero():
    """'0' (entero pelado, unidad instantánea) → 0 segundos (BUG-3 / EC-02)."""
    assert _parse_time("0") == 0


def test_parse_time_bare_integer():
    """'5' (entero pelado) → 5 segundos (BUG-3: unidades NPC con tiempo en segundos)."""
    assert _parse_time("5") == 5


def test_parse_time_bare_integer_with_whitespace():
    """'  3  ' (entero pelado con espacios) → 3 segundos."""
    assert _parse_time("  3  ") == 3


def test_parse_time_invalid_non_numeric_no_colon():
    """'abc' (sin ':', no numérico) → ValueError."""
    with pytest.raises(ValueError):
        _parse_time("abc")


# ---------------------------------------------------------------------------
# Tests — _parse_int
# ---------------------------------------------------------------------------


def test_parse_int_plain():
    """'1200' → 1200."""
    assert _parse_int("1200") == 1200


def test_parse_int_dot_separator():
    """'1.200' → 1200 (separador de miles con punto)."""
    assert _parse_int("1.200") == 1200


def test_parse_int_comma_separator():
    """'1,200' → 1200 (separador de miles con coma)."""
    assert _parse_int("1,200") == 1200


def test_parse_int_small():
    """'40' → 40."""
    assert _parse_int("40") == 40


def test_parse_int_large():
    """'100.000' → 100000."""
    assert _parse_int("100.000") == 100000


# ---------------------------------------------------------------------------
# Tests — _parse_int_or_none
# ---------------------------------------------------------------------------


def test_parse_dash_returns_none():
    """'—' → None (EC-01: valor guión = NULL)."""
    assert _parse_int_or_none("—") is None


def test_parse_empty_returns_none():
    """'' → None."""
    assert _parse_int_or_none("") is None


def test_parse_hyphen_returns_none():
    """\"-\" → None."""
    assert _parse_int_or_none("-") is None


def test_parse_int_or_none_valid():
    """'500' → 500."""
    assert _parse_int_or_none("500") == 500


def test_parse_int_or_none_with_separator():
    """'2.500' → 2500."""
    assert _parse_int_or_none("2.500") == 2500


# ---------------------------------------------------------------------------
# Tests — _remove_background
# ---------------------------------------------------------------------------


def _make_solid_image(color: tuple, size: tuple = (24, 24)) -> Image.Image:
    """Crea una imagen con color uniforme en RGBA."""
    img = Image.new("RGBA", size, color)
    return img


def _make_multicolor_image(size: tuple = (24, 24)) -> Image.Image:
    """Crea una imagen con 4 esquinas de colores distintos."""
    img = Image.new("RGBA", size, (128, 128, 128, 255))
    img.putpixel((0, 0), (255, 0, 0, 255))
    img.putpixel((size[0] - 1, 0), (0, 255, 0, 255))
    img.putpixel((0, size[1] - 1), (0, 0, 255, 255))
    img.putpixel((size[0] - 1, size[1] - 1), (255, 255, 0, 255))
    return img


def test_remove_background_uniform():
    """Imagen con fondo blanco uniforme → esquinas transparentes."""
    img = _make_solid_image((255, 255, 255, 255))
    result = _remove_background(img, tolerance=30)
    # Las esquinas deben ser transparentes
    assert result.getpixel((0, 0))[3] == 0, "Esquina superior izquierda debe ser transparente"
    assert result.getpixel((result.width - 1, 0))[3] == 0, "Esquina superior derecha debe ser transparente"
    assert result.getpixel((0, result.height - 1))[3] == 0, "Esquina inferior izquierda debe ser transparente"
    assert result.getpixel((result.width - 1, result.height - 1))[3] == 0, "Esquina inferior derecha debe ser transparente"


def test_remove_background_no_uniform():
    """Imagen con 4 esquinas completamente distintas → imagen sin cambios (EC-11/EC-15)."""
    img = _make_multicolor_image()
    original_pixels = [
        img.getpixel((0, 0)),
        img.getpixel((img.width - 1, 0)),
        img.getpixel((0, img.height - 1)),
        img.getpixel((img.width - 1, img.height - 1)),
    ]
    result = _remove_background(img, tolerance=30)
    # Las esquinas no deben cambiar (imagen devuelta sin modificar)
    for i, (x, y) in enumerate([(0, 0), (img.width - 1, 0), (0, img.height - 1), (img.width - 1, img.height - 1)]):
        result_pixel = result.getpixel((x, y))
        # El canal alfa puede no ser 0 — la imagen no fue modificada
        assert result_pixel[:3] == original_pixels[i][:3], f"Píxel {i} no debería haberse modificado"


def test_remove_background_preserves_rgba_mode():
    """El resultado siempre es RGBA."""
    img = _make_solid_image((200, 200, 200, 255))
    result = _remove_background(img)
    assert result.mode == "RGBA"


def test_color_distance_same():
    """Distancia entre el mismo color es 0."""
    assert _color_distance((100, 100, 100), (100, 100, 100)) == 0.0


def test_color_distance_max():
    """Distancia entre negro y blanco."""
    d = _color_distance((0, 0, 0), (255, 255, 255))
    assert d > 400  # sqrt(3 * 255^2) ≈ 441.67


# ---------------------------------------------------------------------------
# Tests — _merge_troop_names
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_troops_json(tmp_path):
    """Crea un troops.json temporal con algunas entradas preexistentes."""
    catalog = {
        "ROMANS_1": {"es": "Legionario", "en": "Legionnaire", "de": ""},
        "NATURE_1": {"es": "", "en": "", "de": ""},
        "NATURE_2": {"es": "", "en": "", "de": ""},
    }
    path = tmp_path / "troops.json"
    path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_merge_troop_names_fills_empty(temp_troops_json):
    """Campo vacío '' → se rellena con el nombre del scraper."""
    nombres_por_idioma = {
        "es": {1: "Rata", 2: "Araña"},
        "en": {1: "Rat", 2: "Spider"},
    }
    _merge_troop_names("nature", nombres_por_idioma, [1, 2], catalog_path=temp_troops_json)

    with open(temp_troops_json, "r", encoding="utf-8") as f:
        result = json.load(f)

    assert result["NATURE_1"]["es"] == "Rata"
    assert result["NATURE_1"]["en"] == "Rat"
    assert result["NATURE_2"]["es"] == "Araña"
    assert result["NATURE_2"]["en"] == "Spider"


def test_merge_troop_names_overwrites_existing(temp_troops_json):
    """
    Campo con valor existente → SÍ se sobreescribe con el nombre de kirilloid (RN-04 revisada).

    La política cambió: kirilloid es la fuente de verdad del base. Los nombres incorrectos
    que dejó la capa i18n anterior (p.ej. ROMANS_3 = "Explorador de los Imperios") deben
    ser reemplazados por los correctos de kirilloid en cada ejecución del scraper.
    """
    nombres_por_idioma = {
        "es": {1: "Imperano"},          # reemplaza "Legionario" (nombre viejo incorrecto)
        "en": {1: "Imperian"},          # reemplaza "Legionnaire"
    }
    _merge_troop_names("romans", nombres_por_idioma, [1], catalog_path=temp_troops_json)

    with open(temp_troops_json, "r", encoding="utf-8") as f:
        result = json.load(f)

    # Los valores existentes deben ser reemplazados por los de kirilloid
    assert result["ROMANS_1"]["es"] == "Imperano"
    assert result["ROMANS_1"]["en"] == "Imperian"


def test_merge_troop_names_empty_scrape_preserves_existing(temp_troops_json):
    """
    Nombre scrapeado vacío "" → NO borra el valor existente (excepción de RN-04).

    Cuando kirilloid tiene un hueco para un idioma, se conserva el dato que ya había
    en el base (puede venir de una ejecución anterior o de relleno manual).
    """
    nombres_por_idioma = {
        "es": {1: ""},   # kirilloid no tiene nombre ES → NO sobreescribir
        "de": {1: ""},   # kirilloid no tiene nombre DE → NO sobreescribir
    }
    _merge_troop_names("romans", nombres_por_idioma, [1], catalog_path=temp_troops_json)

    with open(temp_troops_json, "r", encoding="utf-8") as f:
        result = json.load(f)

    # Los valores existentes no deben borrarse por un nombre vacío
    assert result["ROMANS_1"]["es"] == "Legionario"
    assert result["ROMANS_1"]["en"] == "Legionnaire"
    assert result["ROMANS_1"]["de"] == ""   # sigue vacío (era "" antes, sigue "")


def test_merge_troop_names_new_tribe(temp_troops_json):
    """Tribu nueva → clave creada con nombres correctos."""
    nombres_por_idioma = {
        "es": {1: "Vikingo guerrero"},
        "en": {1: "Viking warrior"},
    }
    _merge_troop_names("vikings", nombres_por_idioma, [1], catalog_path=temp_troops_json)

    with open(temp_troops_json, "r", encoding="utf-8") as f:
        result = json.load(f)

    assert "VIKINGS_1" in result
    assert result["VIKINGS_1"]["es"] == "Vikingo guerrero"
    assert result["VIKINGS_1"]["en"] == "Viking warrior"


def test_merge_troop_names_empty_name_not_written(temp_troops_json):
    """Nombre vacío del scraper → no se escribe (EC-05: nombre vacío en un idioma)."""
    nombres_por_idioma = {
        "de": {1: ""},  # nombre vacío — no debe escribirse
    }
    _merge_troop_names("nature", nombres_por_idioma, [1], catalog_path=temp_troops_json)

    with open(temp_troops_json, "r", encoding="utf-8") as f:
        result = json.load(f)

    # El campo de debe seguir vacío
    assert result["NATURE_1"]["de"] == ""


def test_merge_troop_names_partial_idioma(temp_troops_json):
    """Solo se rellena el idioma que tiene nombre, el otro queda vacío."""
    nombres_por_idioma = {
        "es": {1: "Rata"},
        "de": {1: ""},  # vacío — no se escribe
    }
    _merge_troop_names("nature", nombres_por_idioma, [1], catalog_path=temp_troops_json)

    with open(temp_troops_json, "r", encoding="utf-8") as f:
        result = json.load(f)

    assert result["NATURE_1"]["es"] == "Rata"
    assert result["NATURE_1"]["de"] == ""  # sigue vacío


def test_merge_troop_names_idempotent(temp_troops_json):
    """Re-ejecutar el merge produce el mismo resultado (EC-07)."""
    nombres_por_idioma = {
        "es": {1: "Rata"},
        "en": {1: "Rat"},
    }
    _merge_troop_names("nature", nombres_por_idioma, [1], catalog_path=temp_troops_json)
    _merge_troop_names("nature", nombres_por_idioma, [1], catalog_path=temp_troops_json)

    with open(temp_troops_json, "r", encoding="utf-8") as f:
        result = json.load(f)

    assert result["NATURE_1"]["es"] == "Rata"
    assert result["NATURE_1"]["en"] == "Rat"


def test_merge_troop_names_never_touches_override(tmp_path):
    """
    El scraper nunca toca el fichero override — solo escribe en base (RN-04).

    Crea un override falso al lado del base y verifica que su contenido no cambia
    tras ejecutar _merge_troop_names.
    """
    # Crear base y override en una carpeta temporal que imita la estructura real
    base_dir = tmp_path / "base"
    override_dir = tmp_path / "override"
    base_dir.mkdir()
    override_dir.mkdir()

    base_path = base_dir / "troops.json"
    override_path = override_dir / "troops.json"

    base_catalog = {"ROMANS_1": {"es": "", "en": ""}}
    override_catalog = {"ROMANS_1": {"es": "Nombre manual override"}}

    base_path.write_text(json.dumps(base_catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    override_path.write_text(json.dumps(override_catalog, ensure_ascii=False, indent=2), encoding="utf-8")

    nombres_por_idioma = {"es": {1: "Imperano"}, "en": {1: "Imperian"}}
    _merge_troop_names("romans", nombres_por_idioma, [1], catalog_path=base_path)

    # El override no debe haber cambiado
    with open(override_path, "r", encoding="utf-8") as f:
        override_result = json.load(f)
    assert override_result["ROMANS_1"]["es"] == "Nombre manual override"

    # El base sí debe haber cambiado
    with open(base_path, "r", encoding="utf-8") as f:
        base_result = json.load(f)
    assert base_result["ROMANS_1"]["es"] == "Imperano"


# ---------------------------------------------------------------------------
# Helpers — mocks de Element y Tab alineados con la API real de zendriver
# ---------------------------------------------------------------------------


def _make_fake_element(text="", attrs=None):
    """
    Crea un fake de Element con la API REAL de zendriver:
      - .text es @property (str)
      - .parent es @property (Element|None)
      - .attrs es un dict-like con .get()
      - .query_selector / .query_selector_all son async
      - .screenshot_b64(format, scale) es async → devuelve base64 de PNG 1x1
    """
    elem = MagicMock()
    # .text como property str
    type(elem).text = PropertyMock(return_value=text)
    # .parent como property (None por defecto)
    type(elem).parent = PropertyMock(return_value=None)
    # .attrs como dict simulado
    attrs_dict = attrs or {}
    elem.attrs = MagicMock()
    elem.attrs.get = lambda k, default=None: attrs_dict.get(k, default)
    # query_selector / query_selector_all async
    elem.query_selector = AsyncMock(return_value=None)
    elem.query_selector_all = AsyncMock(return_value=[])
    # screenshot_b64 async → base64 de PNG 1x1 transparente
    _tiny_png_b64 = _tiny_png_base64()
    elem.screenshot_b64 = AsyncMock(return_value=_tiny_png_b64)
    return elem


def _tiny_png_base64() -> str:
    """Genera un PNG 1x1 transparente y devuelve su base64."""
    img = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


# ---------------------------------------------------------------------------
# Tests — idempotencia de iconos (sin browser real — mock con API real)
# ---------------------------------------------------------------------------


def test_capture_stat_icons_skips_existing(tmp_path, monkeypatch):
    """
    Si el PNG ya existe en disco, _capture_stat_icons no hace screenshot.
    Verifica idempotencia: la función respeta archivos preexistentes.
    """
    import asyncio
    from adapters.scraper import kirilloid_scraper as ks

    # Sobrescribir ICONS_DIR con la carpeta temporal
    monkeypatch.setattr(ks, "ICONS_DIR", tmp_path)

    # Crear ficheros PNG "ya existentes" para todos los stat icons
    for _, icon_id, _ in ks.STAT_ICON_MAP:
        (tmp_path / f"{icon_id}.png").write_bytes(b"fake_png")

    # query_selector nunca debería llamarse (todos los PNG existen)
    mock_page = MagicMock()
    mock_page.query_selector = AsyncMock(return_value=None)

    mock_conn = MagicMock()

    asyncio.run(ks._capture_stat_icons(mock_page, mock_conn))

    # Como todos los PNG existen, page.query_selector nunca debería llamarse
    mock_page.query_selector.assert_not_called()


def test_capture_upgrade_icons_skips_missing_table(tmp_path, monkeypatch):
    """
    Tribu sin #upg_table → _capture_upgrade_icons retorna sin error.
    La función debe retornar sin llamar a screenshot_b64.
    """
    import asyncio
    from adapters.scraper import kirilloid_scraper as ks

    monkeypatch.setattr(ks, "ICONS_DIR", tmp_path)

    mock_page = MagicMock()
    # query_selector devuelve None → no hay tabla de mejoras
    mock_page.query_selector = AsyncMock(return_value=None)

    mock_conn = MagicMock()

    asyncio.run(ks._capture_upgrade_icons(mock_page, mock_conn))

    # Solo debería haberse llamado query_selector una vez (para #upg_table)
    mock_page.query_selector.assert_called_once_with("#upg_table")


def test_capture_upgrade_icons_skips_hidden_cell(tmp_path, monkeypatch):
    """
    Celda td.upg con display:none → se omite sin error, no se escribe PNG.
    El padre del img tiene style="display:none" en attrs (API real: .parent es property).
    """
    import asyncio
    from adapters.scraper import kirilloid_scraper as ks

    monkeypatch.setattr(ks, "ICONS_DIR", tmp_path)

    # Padre con display:none
    mock_parent = _make_fake_element(attrs={"style": "display:none"})

    # El img existe y su .parent (property) devuelve mock_parent
    mock_img = _make_fake_element()
    type(mock_img).parent = PropertyMock(return_value=mock_parent)
    # screenshot_b64 no debe llamarse nunca
    mock_img.screenshot_b64 = AsyncMock()

    async def mock_query_selector(selector):
        if selector == "#upg_table":
            # Devolvemos un objeto no-None para indicar que la tabla existe
            return _make_fake_element()
        # Para los selectores de iconos de mejora, devuelve el img simulado
        return mock_img

    mock_page = MagicMock()
    mock_page.query_selector = mock_query_selector

    mock_conn = MagicMock()

    asyncio.run(ks._capture_upgrade_icons(mock_page, mock_conn))

    # screenshot_b64 nunca debería llamarse (celda oculta)
    mock_img.screenshot_b64.assert_not_called()
    # No debe haberse creado ningún PNG en tmp_path
    for _, icon_id, _ in ks.UPGRADE_ICON_MAP:
        assert not (tmp_path / f"{icon_id}.png").exists()


# ---------------------------------------------------------------------------
# Tests — _wait_for_element con API real (query_selector)
# ---------------------------------------------------------------------------


def test_wait_for_element_found_immediately():
    """
    _wait_for_element retorna sin error cuando query_selector devuelve elemento.
    """
    import asyncio
    from adapters.scraper import kirilloid_scraper as ks

    mock_page = MagicMock()
    mock_page.query_selector = AsyncMock(return_value=_make_fake_element())

    # No debe lanzar
    asyncio.run(ks._wait_for_element(mock_page, "#main.wire", timeout=5))
    mock_page.query_selector.assert_called_with("#main.wire")


def test_wait_for_element_timeout():
    """
    _wait_for_element lanza KirilloidScraperError cuando query_selector siempre devuelve None.
    """
    import asyncio
    from adapters.scraper import kirilloid_scraper as ks
    from core.exceptions import KirilloidScraperError

    mock_page = MagicMock()
    mock_page.query_selector = AsyncMock(return_value=None)

    with pytest.raises(KirilloidScraperError):
        asyncio.run(ks._wait_for_element(mock_page, "#main.wire", timeout=0.6))


# ---------------------------------------------------------------------------
# Tests — _parse_main_table con mocks de API real
# ---------------------------------------------------------------------------


def test_parse_main_table_basic():
    """
    _parse_main_table extrae ordinal y stats de una fila simulada.
    Verifica que usa query_selector_all/query_selector y attrs.get/text (property).
    """
    import asyncio
    from adapters.scraper import kirilloid_scraper as ks

    # Celda td.name con unit="1" y texto de nombre
    name_td = _make_fake_element(text="Legionario", attrs={"unit": "1"})

    # Celda td.off con valor de ataque
    off_td = _make_fake_element(text="40")

    # Fila con name_td y off_td
    async def row_query_selector(selector):
        if selector == "td.name[unit]":
            return name_td
        if selector == "td.off":
            return off_td
        return None

    mock_row = MagicMock()
    mock_row.query_selector = row_query_selector

    # El resto de columnas del STAT_COLUMN_MAP no están en esta fila → None
    # (ya cubierto por el fallback a None en row_query_selector)

    # Fila de cabecera (índice 0) y fila de datos (índice 1)
    header_row = MagicMock()
    header_row.query_selector = AsyncMock(return_value=None)

    mock_page = MagicMock()
    mock_page.query_selector_all = AsyncMock(return_value=[header_row, mock_row])

    result = asyncio.run(ks._parse_main_table(mock_page, "romans", True))

    assert 1 in result
    assert result[1]["attack"] == 40
    assert result[1]["tribe"] == "romans"
    assert result[1]["ordinal"] == 1
    assert result[1]["is_playable"] is True


def test_parse_main_table_dash_becomes_none():
    """
    Valor "—" en una celda → stats[stat_name] = None (RN-07).
    """
    import asyncio
    from adapters.scraper import kirilloid_scraper as ks

    name_td = _make_fake_element(text="Nature beast", attrs={"unit": "2"})
    dash_td = _make_fake_element(text="—")

    async def row_query_selector(selector):
        if selector == "td.name[unit]":
            return name_td
        if selector == "td.off":
            return dash_td
        return None

    mock_row = MagicMock()
    mock_row.query_selector = row_query_selector

    header_row = MagicMock()
    header_row.query_selector = AsyncMock(return_value=None)

    mock_page = MagicMock()
    mock_page.query_selector_all = AsyncMock(return_value=[header_row, mock_row])

    result = asyncio.run(ks._parse_main_table(mock_page, "nature", False))

    assert result[2]["attack"] is None


# ---------------------------------------------------------------------------
# Tests — _parse_troop_names con mocks de API real
# ---------------------------------------------------------------------------


def test_parse_troop_names_basic():
    """
    _parse_troop_names devuelve {ordinal: nombre} usando attrs.get y text property.
    """
    import asyncio
    from adapters.scraper import kirilloid_scraper as ks

    td1 = _make_fake_element(text="Legionario", attrs={"unit": "1"})
    td2 = _make_fake_element(text="Pretoriano", attrs={"unit": "2"})

    mock_page = MagicMock()
    mock_page.query_selector_all = AsyncMock(return_value=[td1, td2])

    result = asyncio.run(ks._parse_troop_names(mock_page))

    assert result == {1: "Legionario", 2: "Pretoriano"}


# ---------------------------------------------------------------------------
# Test de orden — documenta que los nombres (re-render) preceden a los stats
# ---------------------------------------------------------------------------


def test_names_before_stats_order_in_main_loop(monkeypatch):
    """
    Documenta y verifica que en el bucle principal de load_kirilloid,
    la lectura de nombres (_parse_troop_names vía click en bandera) se ejecuta
    ANTES que el parseo de stats (_parse_main_table) y la captura de iconos.

    Este orden es la causa raíz del fix del bug off-by-one: el click en la bandera
    de idioma fuerza el re-render de la tabla #main a la tribu N; parsear stats
    DESPUÉS garantiza que los números correspondan a la tribu correcta.

    La prueba inspecciona el AST del módulo scripts.load_kirilloid para comprobar
    que, dentro de la función main(), el primer uso de _parse_troop_names aparece
    en el código antes que el primer uso de _parse_main_table.
    """
    import ast
    import sys
    from pathlib import Path

    script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "load_kirilloid.py"
    source = script_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Buscar la función main()
    main_func = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == "main":
            main_func = node
            break

    assert main_func is not None, "No se encontró la función main() en load_kirilloid.py"

    # Recoger las líneas de primera aparición de las llamadas clave
    first_line: dict[str, int] = {}

    for node in ast.walk(main_func):
        if isinstance(node, ast.Call):
            # Llamadas directas: _parse_troop_names(page)
            if isinstance(node.func, ast.Name) and node.func.id in (
                "_parse_troop_names", "_parse_main_table", "_capture_troop_icon",
                "_capture_stat_icons", "_capture_upgrade_icons",
            ):
                name = node.func.id
                if name not in first_line:
                    first_line[name] = node.lineno

    assert "_parse_troop_names" in first_line, (
        "_parse_troop_names no se llama en main() — el bucle de idiomas desapareció"
    )
    assert "_parse_main_table" in first_line, (
        "_parse_main_table no se llama en main() — el parseo de stats desapareció"
    )

    assert first_line["_parse_troop_names"] < first_line["_parse_main_table"], (
        f"BUG DE ORDEN: _parse_troop_names (línea {first_line['_parse_troop_names']}) "
        f"debe aparecer ANTES que _parse_main_table (línea {first_line['_parse_main_table']}). "
        "El click en la bandera de idioma fuerza el re-render de kirilloid; sin ese click "
        "previo, los stats y los iconos corresponderían a la tribu anterior (off-by-one)."
    )

    # Verificar también que los iconos van DESPUÉS de _parse_troop_names
    for capture_fn in ("_capture_troop_icon", "_capture_stat_icons", "_capture_upgrade_icons"):
        if capture_fn in first_line:
            assert first_line["_parse_troop_names"] < first_line[capture_fn], (
                f"BUG DE ORDEN: _parse_troop_names debe aparecer antes que {capture_fn}. "
                "Los iconos capturados antes del re-render corresponderían a la tribu anterior."
            )


# ---------------------------------------------------------------------------
# Tests — _parse_upgrade_table (URL por unidad, estructura real verificada)
# ---------------------------------------------------------------------------
#
# Estructura HTML real del #upg_table (verificada en navegador):
#   - Cabecera: fila de <tr> con 6 celdas td.upg, cada una con un
#     <img class="stats X"> donde X en {att_all, def_i, def_c, eye, def_s, point}.
#     Las que no aplican llevan style="display:none".
#   - Filas de datos: <tr> con 13 celdas en orden:
#       [0]  nivel (str dígito)
#       [1]  madera
#       [2]  barro
#       [3]  hierro
#       [4]  cereal
#       [5]  total
#       [6]  tiempo H:MM:SS
#       [7]  att_all value  (o display:none si no aplica)
#       [8]  def_i   value
#       [9]  def_c   value
#       [10] eye     value
#       [11] def_s   value
#       [12] point   value
#     El texto de las celdas de stat puede contener <small>, pero .text ya los
#     concatena: "40.5800" → se parsea como float 40.58.


def _make_upg_header_cell(img_class: str, hidden: bool = False):
    """
    Crea una celda td.upg de cabecera con un <img class="stats X">.
    Si hidden=True, la celda tiene style="display:none".
    """
    img_attrs = {"class_": f"stats {img_class}"}
    img = _make_fake_element(attrs=img_attrs)
    # La celda tiene query_selector("img.stats") → devuelve el img
    cell = _make_fake_element(
        attrs={"style": "display:none" if hidden else ""},
    )
    cell.query_selector = AsyncMock(return_value=img)
    return cell


def _make_upg_data_row(
    level: str,
    costs: tuple,          # (wood, clay, iron, crop, sum_)
    time_str: str,
    stat_values: tuple,    # 6 valores en orden att_all/def_i/def_c/eye/def_s/point
    hidden_stat_indices: frozenset = frozenset(),  # índices de stats ocultos (0-5)
):
    """
    Crea una fila de datos del #upg_table con 13 celdas.

    hidden_stat_indices: set de índices (0-5) cuyas celdas de stat
    tienen style="display:none".
    """
    # Las 13 celdas: [nivel, wood, clay, iron, crop, sum, tiempo, *6 stats]
    wood, clay, iron, crop, sum_ = costs
    cell_texts = [
        level,
        str(wood), str(clay), str(iron), str(crop), str(sum_),
        time_str,
    ] + [str(v) for v in stat_values]

    cells = []
    for i, text in enumerate(cell_texts):
        stat_offset = i - 7  # stat_offset en [-7..5]; solo >=0 son stats
        is_hidden = (stat_offset >= 0) and (stat_offset in hidden_stat_indices)
        style = "display:none" if is_hidden else ""
        cell = _make_fake_element(text=text, attrs={"style": style})
        cells.append(cell)

    row = MagicMock()
    row.query_selector_all = AsyncMock(return_value=cells)
    return row


def _build_upg_table_page(header_cells, data_rows):
    """
    Construye el mock de página con un #upg_table.
    header_cells: lista de 6 celdas td.upg (fila de cabecera)
    data_rows: lista de filas de datos (ya con query_selector_all mockeado)
    """
    # Fila de cabecera
    header_row = MagicMock()
    header_row.query_selector_all = AsyncMock(return_value=header_cells)

    # La tabla tiene cabecera + filas de datos
    all_rows = [header_row] + data_rows
    upg_table = MagicMock()
    upg_table.query_selector_all = AsyncMock(return_value=all_rows)
    upg_table.query_selector = AsyncMock(return_value=None)

    # La página tiene query_selector("#upg_table") → upg_table
    mock_page = MagicMock()

    async def page_query_selector(selector):
        if selector == "#upg_table":
            return upg_table
        return None

    mock_page.query_selector = page_query_selector
    return mock_page


def test_parse_upgrade_table_sin_tabla():
    """
    Si #upg_table no existe, devuelve lista vacía sin error (EC-03).
    """
    import asyncio
    from adapters.scraper import kirilloid_scraper as ks

    mock_page = MagicMock()
    mock_page.query_selector = AsyncMock(return_value=None)

    result = asyncio.run(ks._parse_upgrade_table(mock_page, "romans", 1))
    assert result == []


def test_parse_upgrade_table_legionario_basico():
    """
    Legionario romano (tribe=1, unit=1): att_all y def_c visibles, resto ocultos.
    Nivel 1: costes 940/800/1250/370/3360, tiempo 1:54:06, att=40.58, defc=50.65.

    Verifica:
      - Solo se capturan stats visibles (att_all y def_c)
      - Los costes y tiempo se extraen correctamente
      - stat_value es float
      - Los niveles son 1-20 (la función acepta 1 en este test)
    """
    import asyncio
    from adapters.scraper import kirilloid_scraper as ks

    # Cabecera: att_all visible, def_i oculto, def_c visible, eye/def_s/point ocultos
    header_cells = [
        _make_upg_header_cell("att_all", hidden=False),   # índice 0 → celda datos[7]
        _make_upg_header_cell("def_i",   hidden=True),    # índice 1 → celda datos[8]
        _make_upg_header_cell("def_c",   hidden=False),   # índice 2 → celda datos[9]
        _make_upg_header_cell("eye",     hidden=True),    # índice 3 → celda datos[10]
        _make_upg_header_cell("def_s",   hidden=True),    # índice 4 → celda datos[11]
        _make_upg_header_cell("point",   hidden=True),    # índice 5 → celda datos[12]
    ]

    # Una fila de nivel 1
    data_row = _make_upg_data_row(
        level="1",
        costs=(940, 800, 1250, 370, 3360),
        time_str="1:54:06",
        # stat_values en orden: att_all, def_i, def_c, eye, def_s, point
        stat_values=(40.58, 35.54, 50.65, 0.0, 0.0, 0.0),
        hidden_stat_indices=frozenset({1, 3, 4, 5}),  # ocultos def_i, eye, def_s, point
    )

    mock_page = _build_upg_table_page(header_cells, [data_row])
    result = asyncio.run(ks._parse_upgrade_table(mock_page, "romans", 1))

    # Debe haber exactamente 2 filas: attack (level=1) y def_cavalry (level=1)
    assert len(result) == 2

    by_stat = {row["stat_name"]: row for row in result}
    assert "attack" in by_stat
    assert "def_cavalry" in by_stat
    assert "def_infantry" not in by_stat
    assert "scouting" not in by_stat

    att = by_stat["attack"]
    assert att["level"] == 1
    assert att["stat_value"] == pytest.approx(40.58)
    assert att["cost_wood"] == 940
    assert att["cost_clay"] == 800
    assert att["cost_iron"] == 1250
    assert att["cost_crop"] == 370
    assert att["cost_sum"] == 3360
    assert att["upgrade_time_s"] == 6846  # 1*3600 + 54*60 + 6

    defc = by_stat["def_cavalry"]
    assert defc["stat_value"] == pytest.approx(50.65)
    assert defc["tribe"] == "romans"
    assert defc["ordinal"] == 1
    assert defc["server_version"] == "1.45"


def test_parse_upgrade_table_explorador_eye_y_def_s():
    """
    Unidad de espionaje (Equites Legati, tribe=1, unit=4):
    eye y def_s visibles, resto ocultos.
    Verifica que stat_names son "scouting" y "counter_scouting" (mapeo correcto).
    """
    import asyncio
    from adapters.scraper import kirilloid_scraper as ks

    header_cells = [
        _make_upg_header_cell("att_all", hidden=True),
        _make_upg_header_cell("def_i",   hidden=True),
        _make_upg_header_cell("def_c",   hidden=True),
        _make_upg_header_cell("eye",     hidden=False),   # visible
        _make_upg_header_cell("def_s",   hidden=False),   # visible
        _make_upg_header_cell("point",   hidden=True),
    ]

    data_row = _make_upg_data_row(
        level="1",
        costs=(500, 400, 300, 200, 1400),
        time_str="0:30:00",
        stat_values=(0.0, 0.0, 0.0, 12.5, 8.3, 0.0),
        hidden_stat_indices=frozenset({0, 1, 2, 5}),
    )

    mock_page = _build_upg_table_page(header_cells, [data_row])
    result = asyncio.run(ks._parse_upgrade_table(mock_page, "romans", 4))

    assert len(result) == 2
    stat_names = {row["stat_name"] for row in result}
    assert "scouting" in stat_names
    assert "counter_scouting" in stat_names
    assert "attack" not in stat_names

    scouting_row = next(r for r in result if r["stat_name"] == "scouting")
    assert scouting_row["stat_value"] == pytest.approx(12.5)


def test_parse_upgrade_table_catapulta_point():
    """
    Catapulta (tribe=1, unit=8): solo att_all y point visibles.
    Verifica que stat_name para point es "destructive".
    """
    import asyncio
    from adapters.scraper import kirilloid_scraper as ks

    header_cells = [
        _make_upg_header_cell("att_all", hidden=False),
        _make_upg_header_cell("def_i",   hidden=True),
        _make_upg_header_cell("def_c",   hidden=True),
        _make_upg_header_cell("eye",     hidden=True),
        _make_upg_header_cell("def_s",   hidden=True),
        _make_upg_header_cell("point",   hidden=False),   # visible
    ]

    data_row = _make_upg_data_row(
        level="1",
        costs=(1000, 800, 750, 350, 2900),
        time_str="2:00:00",
        stat_values=(60.0, 0.0, 0.0, 0.0, 0.0, 15.5),
        hidden_stat_indices=frozenset({1, 2, 3, 4}),
    )

    mock_page = _build_upg_table_page(header_cells, [data_row])
    result = asyncio.run(ks._parse_upgrade_table(mock_page, "romans", 8))

    stat_names = {row["stat_name"] for row in result}
    assert "attack" in stat_names
    assert "destructive" in stat_names

    destr = next(r for r in result if r["stat_name"] == "destructive")
    assert destr["stat_value"] == pytest.approx(15.5)


def test_parse_upgrade_table_multiples_niveles():
    """
    Verifica que se capturan exactamente los niveles 1-20 (no el nivel 0).
    """
    import asyncio
    from adapters.scraper import kirilloid_scraper as ks

    header_cells = [
        _make_upg_header_cell("att_all", hidden=False),
        _make_upg_header_cell("def_i",   hidden=True),
        _make_upg_header_cell("def_c",   hidden=True),
        _make_upg_header_cell("eye",     hidden=True),
        _make_upg_header_cell("def_s",   hidden=True),
        _make_upg_header_cell("point",   hidden=True),
    ]

    # Nivel 0 (base) + niveles 1-3
    data_rows = []
    for lvl in range(0, 4):
        data_rows.append(_make_upg_data_row(
            level=str(lvl),
            costs=(100, 100, 100, 100, 400),
            time_str="0:30:00",
            stat_values=(10.0 + lvl, 0.0, 0.0, 0.0, 0.0, 0.0),
            hidden_stat_indices=frozenset({1, 2, 3, 4, 5}),
        ))

    mock_page = _build_upg_table_page(header_cells, data_rows)
    result = asyncio.run(ks._parse_upgrade_table(mock_page, "teutons", 1))

    # Solo niveles 1, 2, 3 (no el 0)
    levels = [row["level"] for row in result]
    assert 0 not in levels
    assert sorted(set(levels)) == [1, 2, 3]


def test_parse_upgrade_table_celdas_sin_display_none_en_datos():
    """
    Si una celda de stat en la fila de datos tiene style="display:none",
    se omite esa stat para ese nivel aunque la cabecera la marque visible.
    """
    import asyncio
    from adapters.scraper import kirilloid_scraper as ks

    # Cabecera: att_all y def_c visibles
    header_cells = [
        _make_upg_header_cell("att_all", hidden=False),
        _make_upg_header_cell("def_i",   hidden=True),
        _make_upg_header_cell("def_c",   hidden=False),
        _make_upg_header_cell("eye",     hidden=True),
        _make_upg_header_cell("def_s",   hidden=True),
        _make_upg_header_cell("point",   hidden=True),
    ]

    # En la fila de datos, la celda de def_c (índice 9 = stat_offset 2) está oculta
    data_row = _make_upg_data_row(
        level="1",
        costs=(100, 100, 100, 100, 400),
        time_str="0:10:00",
        stat_values=(25.0, 0.0, 30.0, 0.0, 0.0, 0.0),
        # Ocultar en fila: def_i (1), def_c (2), eye (3), def_s (4), point (5)
        hidden_stat_indices=frozenset({1, 2, 3, 4, 5}),
    )

    mock_page = _build_upg_table_page(header_cells, [data_row])
    result = asyncio.run(ks._parse_upgrade_table(mock_page, "gauls", 1))

    # def_c está oculta en la fila de datos → solo attack debe aparecer
    stat_names = {row["stat_name"] for row in result}
    assert "attack" in stat_names
    assert "def_cavalry" not in stat_names


def test_parse_upgrade_table_sin_columnas_visibles():
    """
    Si ninguna columna de stat es visible (todas display:none en cabecera),
    devuelve lista vacía sin error.
    """
    import asyncio
    from adapters.scraper import kirilloid_scraper as ks

    # Todas las celdas ocultas
    header_cells = [
        _make_upg_header_cell("att_all", hidden=True),
        _make_upg_header_cell("def_i",   hidden=True),
        _make_upg_header_cell("def_c",   hidden=True),
        _make_upg_header_cell("eye",     hidden=True),
        _make_upg_header_cell("def_s",   hidden=True),
        _make_upg_header_cell("point",   hidden=True),
    ]

    data_row = _make_upg_data_row(
        level="1",
        costs=(100, 100, 100, 100, 400),
        time_str="0:10:00",
        stat_values=(10.0, 10.0, 10.0, 10.0, 10.0, 10.0),
        hidden_stat_indices=frozenset(range(6)),
    )

    mock_page = _build_upg_table_page(header_cells, [data_row])
    result = asyncio.run(ks._parse_upgrade_table(mock_page, "romans", 1))

    assert result == []


def test_parse_upgrade_table_fila_sin_suficientes_celdas():
    """
    Filas con menos de 13 celdas se ignoran sin error (estructura inesperada).
    """
    import asyncio
    from adapters.scraper import kirilloid_scraper as ks

    header_cells = [
        _make_upg_header_cell("att_all", hidden=False),
        _make_upg_header_cell("def_i",   hidden=True),
        _make_upg_header_cell("def_c",   hidden=True),
        _make_upg_header_cell("eye",     hidden=True),
        _make_upg_header_cell("def_s",   hidden=True),
        _make_upg_header_cell("point",   hidden=True),
    ]

    # Fila con solo 5 celdas (estructura inesperada)
    short_row = MagicMock()
    short_row.query_selector_all = AsyncMock(
        return_value=[_make_fake_element(text=str(i)) for i in range(5)]
    )

    mock_page = _build_upg_table_page(header_cells, [short_row])
    result = asyncio.run(ks._parse_upgrade_table(mock_page, "romans", 1))
    assert result == []
