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
    _parse_int,
    _parse_int_or_none,
    _parse_time,
    _remove_background,
)


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
