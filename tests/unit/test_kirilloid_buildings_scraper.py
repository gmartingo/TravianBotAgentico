"""
Tests unitarios del scraper de edificios kirilloid — SIN browser, SIN Chrome.

Verifica las funciones puras de parseo y el merge de buildings.json.
Las funciones que requieren browser (_capture_building_icon) se verifican
con mocks de DOM siguiendo la API REAL de zendriver.

Convención de mocks de DOM (misma que test_kirilloid_scraper.py):
  - Element.text es @property (str), NO método async
  - Element.parent es @property (Element|None), NO método async
  - Element.attrs es ContraDict; "class" se almacena como "class_" o "class"
  - Tab.query_selector(css) → async → Element|None
  - Tab.query_selector_all(css) → async → list[Element]
  - Element.query_selector(css) → async → Element|None
  - Element.query_selector_all(css) → async → list[Element]
  - Element.screenshot_b64(format, scale) → async → str (base64)
  - NO existe element.find / element.find_all / element.get_attribute
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from adapters.scraper.kirilloid_buildings_scraper import (
    _capture_building_icon,
    _make_icon_id,
    _merge_building_names,
    _parse_building_detail,
    _parse_building_index,
    _parse_building_names_from_index,
    _slugify,
)


# ---------------------------------------------------------------------------
# Helpers para construir mocks de DOM zevendriver-style
# ---------------------------------------------------------------------------


def _make_element(text: str = "", attrs: dict | None = None) -> MagicMock:
    """Crea un mock de Element con .text como @property y .attrs como dict."""
    el = MagicMock()
    type(el).text = PropertyMock(return_value=text)
    el.attrs = attrs or {}
    # query_selector y query_selector_all son async
    el.query_selector = AsyncMock(return_value=None)
    el.query_selector_all = AsyncMock(return_value=[])
    return el


def _make_column_with_h3(h3_text: str, items: list) -> MagicMock:
    """
    Crea un mock de columna .build_list__column con <h3> y lista de items.
    query_selector("h3") → h3 element
    query_selector_all("div.build_list__item[data-gid]") → items
    """
    col = MagicMock()
    h3 = _make_element(text=h3_text)

    async def _qs(selector):
        if "h3" in selector:
            return h3
        return None

    async def _qsa(selector):
        if "build_list__item" in selector:
            return items
        return []

    col.query_selector = AsyncMock(side_effect=_qs)
    col.query_selector_all = AsyncMock(side_effect=_qsa)
    return col


def _make_browser(*args) -> MagicMock:
    """Crea un mock de browser/Tab."""
    browser = MagicMock()
    browser.query_selector = AsyncMock(return_value=None)
    browser.query_selector_all = AsyncMock(return_value=[])
    return browser


# ---------------------------------------------------------------------------
# Tests — _parse_building_index
# ---------------------------------------------------------------------------


def test_parse_building_index_three_columns_real_order():
    """
    El parser lee el <h3> REAL de cada columna y acumula los 3 grupos.

    Orden real de kirilloid en idioma 'es':
      columna 0: h3="recursos"        → category="resources"
      columna 1: h3="militar"         → category="military"
      columna 2: h3="infraestructura" → category="infrastructure"
    """
    browser = _make_browser()

    # (h3_text, gids_in_column)
    col_specs = [
        ("recursos",        [1, 2]),
        ("militar",         [10, 11]),
        ("infraestructura", [20, 21]),
    ]

    columns = []
    for h3_text, gids in col_specs:
        items = [
            _make_element(text=f"Edificio {g}", attrs={"data-gid": str(g)})
            for g in gids
        ]
        columns.append(_make_column_with_h3(h3_text, items))

    browser.query_selector_all = AsyncMock(return_value=columns)

    result = asyncio.run(_parse_building_index(browser))

    assert len(result) == 6

    # columna 0 → resources
    assert result[0] == (1, "resources", "Edificio 1")
    assert result[1] == (2, "resources", "Edificio 2")
    # columna 1 → military  (orden real: militar es la segunda)
    assert result[2] == (10, "military", "Edificio 10")
    assert result[3] == (11, "military", "Edificio 11")
    # columna 2 → infrastructure
    assert result[4] == (20, "infrastructure", "Edificio 20")
    assert result[5] == (21, "infrastructure", "Edificio 21")


def test_parse_building_index_category_from_h3_not_position():
    """
    La categoría se lee del h3, no de la posición.
    Si las columnas estuvieran en orden diferente, las categorías siguen siendo correctas.
    """
    browser = _make_browser()

    # Orden inverso al habitual para verificar que NO se usa posición
    col_specs = [
        ("infraestructura", [20]),
        ("recursos",        [1]),
        ("militar",         [10]),
    ]

    columns = []
    for h3_text, gids in col_specs:
        items = [
            _make_element(text=f"E{g}", attrs={"data-gid": str(g)})
            for g in gids
        ]
        columns.append(_make_column_with_h3(h3_text, items))

    browser.query_selector_all = AsyncMock(return_value=columns)

    result = asyncio.run(_parse_building_index(browser))

    assert len(result) == 3
    # El primer item viene de la columna "infraestructura" → infrastructure
    assert result[0] == (20, "infrastructure", "E20")
    # El segundo viene de "recursos" → resources
    assert result[1] == (1, "resources", "E1")
    # El tercero de "militar" → military
    assert result[2] == (10, "military", "E10")


def test_parse_building_index_ignores_non_int_gid():
    """Items con data-gid no entero se ignoran; el válido se incluye."""
    browser = _make_browser()
    bad_item = _make_element(text="Mal", attrs={"data-gid": "abc"})
    good_item = _make_element(text="Bueno", attrs={"data-gid": "5"})
    col = _make_column_with_h3("recursos", [bad_item, good_item])
    browser.query_selector_all = AsyncMock(return_value=[col])

    result = asyncio.run(_parse_building_index(browser))
    assert len(result) == 1
    assert result[0][0] == 5
    assert result[0][1] == "resources"


# ---------------------------------------------------------------------------
# Tests — _slugify
# ---------------------------------------------------------------------------


def test_slugify_simple_ascii():
    """Nombre ASCII simple → minúsculas sin cambio."""
    assert _slugify("Warehouse") == "warehouse"


def test_slugify_with_accents():
    """Nombre con acentos → ASCII sin diacríticos."""
    assert _slugify("Almacén") == "almacen"


def test_slugify_with_spaces():
    """Espacios → guiones bajos."""
    assert _slugify("Gran Almacén") == "gran_almacen"
    assert _slugify("Edificio principal") == "edificio_principal"


def test_slugify_treasury_alias():
    """'treasury' ya es ASCII limpio → sin cambio."""
    assert _slugify("treasury") == "treasury"


def test_slugify_empty_string():
    """Cadena vacía → cadena vacía."""
    assert _slugify("") == ""


def test_slugify_special_chars():
    """Caracteres no alfanuméricos (salvo guión bajo) se eliminan."""
    # Guión → guión bajo; paréntesis eliminado
    assert _slugify("Gran (Almacén)") == "gran_almacen"


# ---------------------------------------------------------------------------
# Tests — _make_icon_id  (firma: _make_icon_id(gid, name=None, catalog_path=None))
# ---------------------------------------------------------------------------
# BUG-2 FIX: _make_icon_id ahora acepta `name` como argumento explícito con
# máxima prioridad. El campo "alias" del JSON estaba desalineado con los gids
# (datos viejos). El nombre inglés recién scrapeado SÍ está alineado.


def test_make_icon_id_with_name_argument(tmp_path):
    """Cuando se pasa name → slug desde el name, sin leer el JSON."""
    # El JSON tiene alias erróneo (desalineado, como el bug real)
    catalog = {"10": {"alias": "wrong_alias", "en": "AlsoWrong"}}
    p = tmp_path / "buildings.json"
    p.write_text(__import__("json").dumps(catalog), encoding="utf-8")

    result = _make_icon_id(10, name="Warehouse", catalog_path=p)
    assert result == "building_10_warehouse"


def test_make_icon_id_name_with_accents(tmp_path):
    """Nombre con acentos pasado como argumento → slugificado correctamente."""
    p = tmp_path / "buildings.json"
    p.write_text(__import__("json").dumps({}), encoding="utf-8")

    result = _make_icon_id(10, name="Almacén", catalog_path=p)
    assert result == "building_10_almacen"


def test_make_icon_id_name_empty_falls_back_to_json_en(tmp_path):
    """name="" o None → cae al nombre 'en' del JSON."""
    catalog = {"15": {"en": "Main Building"}}
    p = tmp_path / "buildings.json"
    p.write_text(__import__("json").dumps(catalog), encoding="utf-8")

    # name vacío — debe usar el "en" del JSON
    result = _make_icon_id(15, name="", catalog_path=p)
    assert result == "building_15_main_building"

    # name None — igual
    result = _make_icon_id(15, name=None, catalog_path=p)
    assert result == "building_15_main_building"


def test_make_icon_id_name_empty_falls_back_to_json_alias(tmp_path):
    """Cuando no hay 'en' en el JSON pero hay 'alias' → usa alias como último recurso."""
    catalog = {"27": {"alias": "treasury"}}
    p = tmp_path / "buildings.json"
    p.write_text(__import__("json").dumps(catalog), encoding="utf-8")

    result = _make_icon_id(27, name=None, catalog_path=p)
    assert result == "building_27_treasury"


def test_make_icon_id_fallback_no_name_no_json(tmp_path):
    """Sin name ni datos en JSON → fallback 'building_{gid}'."""
    catalog = {"99": {"es": "Edificio desconocido"}}
    p = tmp_path / "buildings.json"
    p.write_text(__import__("json").dumps(catalog), encoding="utf-8")

    result = _make_icon_id(99, name=None, catalog_path=p)
    assert result == "building_99"


def test_make_icon_id_gid_not_in_catalog(tmp_path):
    """Gid no existe en el JSON y no se pasa name → fallback 'building_{gid}'."""
    catalog = {}
    p = tmp_path / "buildings.json"
    p.write_text(__import__("json").dumps(catalog), encoding="utf-8")

    result = _make_icon_id(42, catalog_path=p)
    assert result == "building_42"


def test_make_icon_id_real_gids_previously_misaligned(tmp_path):
    """
    Verifica los gids que estaban mal alineados con el alias viejo (BUG-2 real).
    Con name correcto:
      gid=10 (Almacén/Warehouse)   → building_10_warehouse
      gid=13 (Herrería/Smithy)     → building_13_smithy
      gid=19 (Cuartel/Barracks)    → building_19_barracks
      gid=27 (Tesoro/Treasury)     → building_27_treasury
    """
    p = tmp_path / "buildings.json"
    p.write_text(__import__("json").dumps({}), encoding="utf-8")

    assert _make_icon_id(10, name="Warehouse",  catalog_path=p) == "building_10_warehouse"
    assert _make_icon_id(13, name="Smithy",     catalog_path=p) == "building_13_smithy"
    assert _make_icon_id(19, name="Barracks",   catalog_path=p) == "building_19_barracks"
    assert _make_icon_id(27, name="Treasury",   catalog_path=p) == "building_27_treasury"


# ---------------------------------------------------------------------------
# Tests — _parse_building_names_from_index
# ---------------------------------------------------------------------------


def test_parse_building_names_from_index():
    """Releer el índice devuelve {gid: nombre} correcto."""
    browser = _make_browser()
    items = [
        _make_element(text="Almacén", attrs={"data-gid": "10"}),
        _make_element(text="Granero", attrs={"data-gid": "11"}),
    ]
    browser.query_selector_all = AsyncMock(return_value=items)

    result = asyncio.run(_parse_building_names_from_index(browser))
    assert result[10] == "Almacén"
    assert result[11] == "Granero"


# ---------------------------------------------------------------------------
# Tests — _parse_building_detail
# ---------------------------------------------------------------------------


def _build_detail_browser(
    cells_config: list[dict],
    rows_data: list[list[str]],
) -> MagicMock:
    """
    Construye un browser mock con tabla de detalle.

    IMPORTANTE: kirilloid usa <td> en la fila de cabecera <tr class="rbg">, NO <th>.
    El mock refleja el HTML real: query_selector_all("td") en el header_row devuelve
    las celdas de cabecera (antes el mock usaba "th" y ocultaba el bug BUG-1).

    cells_config: lista de dicts con {text: str, img_class: str|None}
    rows_data: lista de filas; cada fila es lista de strings de texto por td.
    """
    browser = _make_browser()

    # Header row — las celdas son <td>, NO <th> (HTML real de kirilloid)
    header_row = MagicMock()
    header_cells = []
    for cfg in cells_config:
        cell = MagicMock()
        type(cell).text = PropertyMock(return_value=cfg.get("text", ""))
        if cfg.get("img_class"):
            img = _make_element(attrs={"class": cfg["img_class"]})
            cell.query_selector = AsyncMock(return_value=img)
        else:
            cell.query_selector = AsyncMock(return_value=None)
        header_cells.append(cell)

    # query_selector_all("td") devuelve las celdas de cabecera
    async def _header_qsa(selector):
        if selector == "td":
            return header_cells
        return []

    header_row.query_selector_all = AsyncMock(side_effect=_header_qsa)

    # Tbody rows
    tbody_rows = []
    for row_texts in rows_data:
        tr = MagicMock()
        tds = []
        for cell_text in row_texts:
            td = _make_element(text=cell_text)
            tds.append(td)
        tr.query_selector_all = AsyncMock(return_value=tds)
        tbody_rows.append(tr)

    # browser.query_selector para el header y browser.query_selector_all para tbody
    async def _qs(selector):
        if "thead tr.rbg" in selector:
            return header_row
        return None

    async def _qsa(selector):
        if "tbody tr" in selector:
            return tbody_rows
        return []

    browser.query_selector = AsyncMock(side_effect=_qs)
    browser.query_selector_all = AsyncMock(side_effect=_qsa)

    return browser


def test_parse_building_detail_maps_columns_by_header():
    """Las columnas se mapean por clase del img de cabecera, no por posición fija."""
    # niv | madera (r1) | barro (r2) | PC | tiempo (r7) | Efecto
    ths_config = [
        {"text": "niv.", "img_class": None},
        {"text": "", "img_class": "res r1"},
        {"text": "", "img_class": "res r2"},
        {"text": "PC", "img_class": None},
        {"text": "", "img_class": "res r7"},
        {"text": "Almacena", "img_class": None},
    ]
    rows_data = [
        ["1", "130", "160", "1", "0:16:40", "1200"],
    ]
    browser = _build_detail_browser(ths_config, rows_data)
    levels, effect_label = asyncio.run(_parse_building_detail(browser))
    assert len(levels) == 1
    lvl = levels[0]
    assert lvl["level"] == 1
    assert lvl["cost_wood"] == 130
    assert lvl["cost_clay"] == 160
    assert lvl["culture_points"] == 1
    assert lvl["build_time_s"] == 1000  # 0:16:40 = 1000 s
    assert lvl["effect_value"] == 1200
    assert effect_label == "Almacena"


def test_parse_building_detail_omits_g10_g11():
    """Columnas building g10 y building g11 se omiten del resultado."""
    ths_config = [
        {"text": "niv.", "img_class": None},
        {"text": "", "img_class": "res r1"},
        {"text": "", "img_class": "building g10"},   # cap almacén → omitir
        {"text": "", "img_class": "building g11"},   # cap granero → omitir
        {"text": "PC", "img_class": None},
    ]
    rows_data = [
        ["1", "130", "999", "888", "1"],
    ]
    browser = _build_detail_browser(ths_config, rows_data)
    levels, _ = asyncio.run(_parse_building_detail(browser))
    assert len(levels) == 1
    lvl = levels[0]
    # Las columnas g10 y g11 NO deben aparecer como campos del nivel
    assert "cap_warehouse" not in lvl
    assert "cap_granary" not in lvl
    # Solo los campos correctos
    assert lvl["cost_wood"] == 130
    assert lvl["culture_points"] == 1


def test_parse_building_detail_effect_label():
    """Última columna con texto → capturado en effect_label."""
    ths_config = [
        {"text": "niv.", "img_class": None},
        {"text": "", "img_class": "res r1"},
        {"text": "Velocidad", "img_class": None},
    ]
    rows_data = [["1", "100", "25"]]
    browser = _build_detail_browser(ths_config, rows_data)
    levels, effect_label = asyncio.run(_parse_building_detail(browser))
    assert effect_label == "Velocidad"
    assert levels[0]["effect_value"] == 25


def test_parse_building_detail_dash_returns_null():
    """"—" en cualquier celda → None en el dict."""
    ths_config = [
        {"text": "niv.", "img_class": None},
        {"text": "", "img_class": "res r1"},
        {"text": "", "img_class": "res r2"},
    ]
    rows_data = [["1", "—", "160"]]
    browser = _build_detail_browser(ths_config, rows_data)
    levels, _ = asyncio.run(_parse_building_detail(browser))
    assert levels[0]["cost_wood"] is None
    assert levels[0]["cost_clay"] == 160


def test_parse_building_detail_time_format():
    """"0:16:40" → 1000 segundos."""
    ths_config = [
        {"text": "niv.", "img_class": None},
        {"text": "", "img_class": "res r7"},
    ]
    rows_data = [["1", "0:16:40"]]
    browser = _build_detail_browser(ths_config, rows_data)
    levels, _ = asyncio.run(_parse_building_detail(browser))
    assert levels[0]["build_time_s"] == 1000


def test_parse_building_detail_empty_table():
    """Tabla sin filas de datos → lista vacía, no excepción."""
    ths_config = [
        {"text": "niv.", "img_class": None},
        {"text": "", "img_class": "res r1"},
    ]
    rows_data = []
    browser = _build_detail_browser(ths_config, rows_data)
    levels, effect_label = asyncio.run(_parse_building_detail(browser))
    assert levels == []
    assert effect_label == ""


def test_parse_building_detail_no_header_row():
    """Si no hay <thead tr.rbg>, devuelve ([], '')."""
    browser = _make_browser()
    browser.query_selector = AsyncMock(return_value=None)
    browser.query_selector_all = AsyncMock(return_value=[])
    levels, label = asyncio.run(_parse_building_detail(browser))
    assert levels == []
    assert label == ""


def test_parse_building_detail_variable_levels():
    """Itera todas las filas del tbody — no asume máximo fijo de 20 (EC-B-12)."""
    ths_config = [
        {"text": "niv.", "img_class": None},
        {"text": "", "img_class": "res r1"},
    ]
    rows_data = [[str(i), str(i * 100)] for i in range(1, 26)]  # 25 filas
    browser = _build_detail_browser(ths_config, rows_data)
    levels, _ = asyncio.run(_parse_building_detail(browser))
    assert len(levels) == 25
    assert levels[-1]["level"] == 25


def test_parse_building_detail_real_html_almacen_20_levels():
    """
    Test con estructura HTML REAL de kirilloid (verificada en navegador):
    - 12 columnas en cabecera, todas <td> (NO <th>) — BUG-1 fix.
    - Columnas g10 y g11 se omiten (RN-B-08).
    - 20 niveles en tbody.
    - nivel 1: wood=130 clay=160 iron=90 crop=40 sum=420 upkeep=1
               culture_points=1 build_time_s=1000 effect_value=1200

    Estructura de cabecera (12 <td>):
      0: "niv."        → level
      1: img.res.r1    → cost_wood
      2: img.res.r2    → cost_clay
      3: img.res.r3    → cost_iron
      4: img.res.r4    → cost_crop
      5: img.res.r6    → cost_sum
      6: img.res.r5    → upkeep
      7: img.building.g10 → OMITIR
      8: img.building.g11 → OMITIR
      9: "PC"          → culture_points
     10: img.res.r7    → build_time_s
     11: "Almacena"    → effect_value  (última col con texto)
    """
    cells_config = [
        {"text": "niv.",     "img_class": None},
        {"text": "",         "img_class": "icon--scalable res r1"},
        {"text": "",         "img_class": "icon--scalable res r2"},
        {"text": "",         "img_class": "icon--scalable res r3"},
        {"text": "",         "img_class": "icon--scalable res r4"},
        {"text": "",         "img_class": "icon--scalable res r6"},
        {"text": "",         "img_class": "icon--scalable res r5"},
        {"text": "",         "img_class": "icon--scalable building g10"},
        {"text": "",         "img_class": "icon--scalable building g11"},
        {"text": "PC",       "img_class": None},
        {"text": "",         "img_class": "icon--scalable res r7"},
        {"text": "Almacena", "img_class": None},
    ]
    # 20 filas: nivel 1 con valores conocidos, resto escalados
    # nivel 1: wood=130 clay=160 iron=90 crop=40 sum=420 upkeep=1 g10=1 g11=1 PC=1 time=0:16:40 effect=1200
    rows_data = []
    for lvl in range(1, 21):
        rows_data.append([
            str(lvl),           # level
            str(130 * lvl),     # cost_wood
            str(160 * lvl),     # cost_clay
            str(90 * lvl),      # cost_iron
            str(40 * lvl),      # cost_crop
            str(420 * lvl),     # cost_sum
            str(lvl),           # upkeep
            str(lvl),           # g10 → OMITIR
            str(lvl),           # g11 → OMITIR
            str(lvl),           # culture_points (PC)
            "0:16:40",          # build_time_s (1000 s para todos los niveles en este test)
            str(1200 * lvl),    # effect_value (Almacena)
        ])

    browser = _build_detail_browser(cells_config, rows_data)
    levels, effect_label = asyncio.run(_parse_building_detail(browser))

    # Verificar que se extraen los 20 niveles (el bug devolvía 0)
    assert len(levels) == 20, f"Se esperaban 20 niveles, se obtuvieron {len(levels)}"
    assert effect_label == "Almacena"

    # Verificar nivel 1 con los valores exactos del HTML real
    lvl1 = levels[0]
    assert lvl1["level"] == 1
    assert lvl1["cost_wood"] == 130
    assert lvl1["cost_clay"] == 160
    assert lvl1["cost_iron"] == 90
    assert lvl1["cost_crop"] == 40
    assert lvl1["cost_sum"] == 420
    assert lvl1["upkeep"] == 1
    assert lvl1["culture_points"] == 1
    assert lvl1["build_time_s"] == 1000
    assert lvl1["effect_value"] == 1200

    # Las columnas g10 y g11 NO deben aparecer
    assert "cap_warehouse" not in lvl1
    assert "cap_granary" not in lvl1
    # No debe haber claves __OMIT__ ni __UNKNOWN__ en los datos
    for key in lvl1:
        assert not key.startswith("__"), f"Clave inesperada en nivel 1: {key}"

    # Verificar nivel 20
    lvl20 = levels[19]
    assert lvl20["level"] == 20
    assert lvl20["cost_wood"] == 130 * 20
    assert lvl20["effect_value"] == 1200 * 20


# ---------------------------------------------------------------------------
# Tests — _merge_building_names
# ---------------------------------------------------------------------------


def _make_temp_buildings_json(content: dict) -> Path:
    """Crea un buildings.json temporal con el contenido dado."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        encoding="utf-8",
        delete=False,
    )
    json.dump(content, tmp, ensure_ascii=False, indent=2)
    tmp.close()
    return Path(tmp.name)


def test_merge_building_names_overwrites_existing():
    """Valor existente + nombre nuevo no-vacío → sobrescribir (política sobrescribe)."""
    catalog_path = _make_temp_buildings_json({
        "10": {"alias": "warehouse", "es": "Almacen viejo"}
    })
    try:
        _merge_building_names({"es": {10: "Almacén correcto"}}, catalog_path=catalog_path)
        with open(catalog_path, encoding="utf-8") as f:
            result = json.load(f)
        assert result["10"]["es"] == "Almacén correcto"
    finally:
        catalog_path.unlink(missing_ok=True)


def test_merge_building_names_keeps_existing_if_new_empty():
    """Valor existente + nombre nuevo vacío → conservar existente (EC-B-05)."""
    catalog_path = _make_temp_buildings_json({
        "10": {"alias": "warehouse", "es": "Almacén"}
    })
    try:
        _merge_building_names({"es": {10: ""}}, catalog_path=catalog_path)
        with open(catalog_path, encoding="utf-8") as f:
            result = json.load(f)
        assert result["10"]["es"] == "Almacén"  # no se sobrescribe
    finally:
        catalog_path.unlink(missing_ok=True)


def test_merge_building_names_creates_new_gid():
    """Gid no existe en JSON → crear entrada."""
    catalog_path = _make_temp_buildings_json({})
    try:
        _merge_building_names({"es": {10: "Almacén"}, "en": {10: "Warehouse"}}, catalog_path=catalog_path)
        with open(catalog_path, encoding="utf-8") as f:
            result = json.load(f)
        assert "10" in result
        assert result["10"]["es"] == "Almacén"
        assert result["10"]["en"] == "Warehouse"
    finally:
        catalog_path.unlink(missing_ok=True)


def test_merge_building_names_preserves_alias():
    """El campo 'alias' del JSON nunca se modifica."""
    catalog_path = _make_temp_buildings_json({
        "10": {"alias": "warehouse", "es": "Almacén"}
    })
    try:
        _merge_building_names({"es": {10: "Almacén Nuevo"}}, catalog_path=catalog_path)
        with open(catalog_path, encoding="utf-8") as f:
            result = json.load(f)
        assert result["10"]["alias"] == "warehouse"
    finally:
        catalog_path.unlink(missing_ok=True)


def test_merge_building_names_atomic_write():
    """Si el JSON resultante es válido, usa escritura tmp+rename (sin tmp residual)."""
    catalog_path = _make_temp_buildings_json({"10": {"alias": "warehouse"}})
    try:
        _merge_building_names({"es": {10: "Almacén"}}, catalog_path=catalog_path)
        tmp_path = catalog_path.with_suffix(".tmp")
        assert not tmp_path.exists(), "El fichero .tmp no debe quedar en disco tras la escritura atómica"
        # El JSON resultante debe ser válido
        with open(catalog_path, encoding="utf-8") as f:
            parsed = json.load(f)
        assert isinstance(parsed, dict)
    finally:
        catalog_path.unlink(missing_ok=True)


def test_merge_building_names_string_keys():
    """Las claves del JSON deben ser strings (EC-B-14)."""
    catalog_path = _make_temp_buildings_json({})
    try:
        _merge_building_names({"es": {10: "Almacén", 11: "Granero"}}, catalog_path=catalog_path)
        with open(catalog_path, encoding="utf-8") as f:
            result = json.load(f)
        # Las claves deben ser strings en el JSON resultante
        assert "10" in result
        assert "11" in result
        assert 10 not in result  # no int keys
    finally:
        catalog_path.unlink(missing_ok=True)


def test_merge_building_names_multiple_langs():
    """Merge con múltiples idiomas actualiza correctamente todos."""
    catalog_path = _make_temp_buildings_json({
        "10": {"alias": "warehouse", "es": "Almacén"}
    })
    try:
        nombres = {
            "en": {10: "Warehouse"},
            "de": {10: "Lager"},
            "fr": {10: "Entrepôt"},
        }
        _merge_building_names(nombres, catalog_path=catalog_path)
        with open(catalog_path, encoding="utf-8") as f:
            result = json.load(f)
        assert result["10"]["es"] == "Almacén"  # intacto
        assert result["10"]["en"] == "Warehouse"
        assert result["10"]["de"] == "Lager"
        assert result["10"]["fr"] == "Entrepôt"
    finally:
        catalog_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Tests — _make_icon_id con merge-first (Fix A)
# ---------------------------------------------------------------------------


def test_make_icon_id_merge_first_pattern(tmp_path):
    """
    Verifica el patrón merge-first: _make_icon_id(gid) sin name usa el 'en'
    del JSON, que ya fue mergeado antes del bucle de gids.

    Simula el escenario real: el run recogió 'en' = 'Warehouse' para gid=10,
    el merge lo escribió en el JSON, y luego _make_icon_id(10) lo lee del JSON.
    El resultado es siempre 'building_10_warehouse', sin depender del run flaky.
    """
    # Simula buildings.json tras el merge previo
    catalog = {
        "10": {"alias": "warehouse", "es": "Almacén", "en": "Warehouse"},
        "13": {"alias": "rally_point", "es": "Herrería", "en": "Smithy"},
    }
    p = tmp_path / "buildings.json"
    p.write_text(json.dumps(catalog), encoding="utf-8")

    # Sin name — lee del JSON (estado post-merge)
    assert _make_icon_id(10, catalog_path=p) == "building_10_warehouse"
    assert _make_icon_id(13, catalog_path=p) == "building_13_smithy"


def test_make_icon_id_no_name_no_en_uses_alias(tmp_path):
    """
    Sin 'en' en el JSON pero con 'alias' → usa alias (prioridad 3).
    Cubre el caso de gids sin nombre inglés disponible.
    """
    catalog = {"27": {"alias": "treasury"}}
    p = tmp_path / "buildings.json"
    p.write_text(json.dumps(catalog), encoding="utf-8")

    result = _make_icon_id(27, catalog_path=p)
    assert result == "building_27_treasury"


def test_make_icon_id_gids_without_sprite_in_t45(tmp_path):
    """
    gids 48/49/50 existen en buildings.json pero su sprite no está en T4.5.
    _make_icon_id debe devolver un icon_id válido (no falla); la captura fallará
    después (en _capture_building_icon) y quedará icon_id=None en catalog.
    """
    catalog = {
        "48": {"alias": "building_48", "en": "Sapartans hosptial"},
        "49": {"alias": "building_49", "en": "Harbor"},
        "50": {"alias": "building_50", "en": "Barricade"},
    }
    p = tmp_path / "buildings.json"
    p.write_text(json.dumps(catalog), encoding="utf-8")

    assert _make_icon_id(48, catalog_path=p) == "building_48_sapartans_hosptial"
    assert _make_icon_id(49, catalog_path=p) == "building_49_harbor"
    assert _make_icon_id(50, catalog_path=p) == "building_50_barricade"


# ---------------------------------------------------------------------------
# Tests — _capture_building_icon reintentos (Fix B)
# ---------------------------------------------------------------------------


def _make_conn_mock() -> MagicMock:
    """Mock de aiosqlite.Connection con execute y commit async."""
    conn = MagicMock()
    conn.execute = AsyncMock()
    conn.commit = AsyncMock()
    return conn


def _make_png_b64() -> str:
    """Genera un PNG 4x4 rojo RGBA mínimo en base64 para tests."""
    import base64
    from io import BytesIO

    from PIL import Image

    img = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
    buf = BytesIO()
    img.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def test_capture_building_icon_success_first_try(tmp_path):
    """screenshot_b64 funciona en el primer intento — escribe PNG y llama a conn.execute."""
    import asyncio

    browser = _make_browser()
    element = _make_element()
    element.screenshot_b64 = AsyncMock(return_value=_make_png_b64())

    # _capture_building_icon busca primero #data_holder img.building.gN
    async def _qs(selector):
        if "data_holder" in selector or "img.building" in selector:
            return element
        return None

    browser.query_selector = AsyncMock(side_effect=_qs)
    conn = _make_conn_mock()

    icons_dir = tmp_path / "icons"
    asyncio.run(
        _capture_building_icon(browser, 10, "building_10_warehouse", conn, icons_dir=icons_dir)
    )

    out_png = icons_dir / "building_10_warehouse.png"
    assert out_png.exists(), "El PNG debe haberse escrito"
    conn.execute.assert_called_once()
    conn.commit.assert_called_once()


def test_capture_building_icon_retries_on_position_error(tmp_path):
    """
    screenshot_b64 falla con 'could not find position' los primeros intentos
    y tiene éxito en el tercero → PNG escrito correctamente.
    """
    import asyncio

    browser = _make_browser()
    element = _make_element()

    call_count = 0

    async def _screenshot_b64(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RuntimeError("could not find position")
        return _make_png_b64()

    element.screenshot_b64 = _screenshot_b64

    async def _qs(selector):
        return element

    browser.query_selector = AsyncMock(side_effect=_qs)
    conn = _make_conn_mock()
    icons_dir = tmp_path / "icons"

    asyncio.run(
        _capture_building_icon(browser, 10, "building_10_warehouse", conn, icons_dir=icons_dir)
    )

    assert call_count == 3, f"Debería haber intentado 3 veces, intentó {call_count}"
    assert (icons_dir / "building_10_warehouse.png").exists()
    conn.execute.assert_called_once()


def test_capture_building_icon_raises_after_all_retries(tmp_path):
    """
    screenshot_b64 falla siempre → RuntimeError tras max_retries intentos.
    Ningún PNG se escribe, conn.execute no se llama.
    """
    import asyncio

    browser = _make_browser()
    element = _make_element()
    element.screenshot_b64 = AsyncMock(side_effect=RuntimeError("could not find position"))

    async def _qs(selector):
        return element

    browser.query_selector = AsyncMock(side_effect=_qs)
    conn = _make_conn_mock()
    icons_dir = tmp_path / "icons"

    with pytest.raises(RuntimeError, match="no se pudo capturar screenshot"):
        asyncio.run(
            _capture_building_icon(browser, 48, "building_48_sapartans_hosptial", conn,
                                   icons_dir=icons_dir, max_retries=3)
        )

    # Ningún PNG debe existir
    assert not (icons_dir / "building_48_sapartans_hosptial.png").exists()
    # conn.execute no debe haberse llamado (no se registra un icono inexistente)
    conn.execute.assert_not_called()


def test_capture_building_icon_element_not_found_raises(tmp_path):
    """
    El elemento img.building.gN no existe en la página (gid 48/49/50 en T4.5)
    → RuntimeError inmediato sin intentar screenshot.
    """
    import asyncio

    browser = _make_browser()
    # query_selector siempre devuelve None
    browser.query_selector = AsyncMock(return_value=None)
    conn = _make_conn_mock()
    icons_dir = tmp_path / "icons"

    with pytest.raises(RuntimeError, match="no encontrado"):
        asyncio.run(
            _capture_building_icon(browser, 48, "building_48_sapartans_hosptial", conn,
                                   icons_dir=icons_dir)
        )

    conn.execute.assert_not_called()


def test_capture_building_icon_consistency_no_png_no_icon_metadata(tmp_path):
    """
    Fix C: si la captura falla, NO se escribe PNG y NO se llama a conn.execute.
    El caller queda con icon_id_stored=None → building_catalog.icon_id=None.
    El PNG no existe → no hay puntero roto.
    """
    import asyncio

    browser = _make_browser()
    browser.query_selector = AsyncMock(return_value=None)  # elemento no encontrado
    conn = _make_conn_mock()
    icons_dir = tmp_path / "icons"

    with pytest.raises(RuntimeError):
        asyncio.run(
            _capture_building_icon(browser, 49, "building_49_harbor", conn,
                                   icons_dir=icons_dir)
        )

    # No debe existir el PNG (no hay puntero roto)
    assert not (icons_dir / "building_49_harbor.png").exists()
    # No debe haber entrada en icon_metadata
    conn.execute.assert_not_called()
    conn.commit.assert_not_called()
