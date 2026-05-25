"""
Lógica de scraping de travian.kirilloid.ru.

Este módulo contiene las funciones que interactúan con el browser (para capturas
de iconos). El script CLI en scripts/load_kirilloid.py orquesta el flujo completo.

Las funciones puras de parseo han sido movidas a core.utils.parsing para ser
compartidas con los parsers de overview: parse_time, parse_int, parse_int_or_none.

Funciones sin dependencias de browser (testables sin Chrome):
  - _remove_background — Pillow flood-fill para quitar fondo de iconos
  - _merge_troop_names — base = fuente kirilloid (sobrescribe), override = manual intocable

Funciones que requieren browser (NO testadas aquí, integración manual):
  - _parse_main_table
  - _parse_upgrade_table
  - _capture_troop_icon
  - _capture_stat_icons
  - _capture_upgrade_icons

REGLA ANTI-DETECCIÓN: Todos los selectores son estructurales (clase/atributo/id).
Nunca se usan selectores por texto visible — kirilloid es multilenguaje.
"""
from __future__ import annotations

import json
import logging
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

# _color_distance, _remove_background y _wait_for_element viven en utils.py y se
# re-exportan aquí para compatibilidad hacia atrás con los tests existentes.
from adapters.scraper.utils import _color_distance, _remove_background, _wait_for_element  # noqa: F401
from core.utils.parsing import parse_int, parse_int_or_none, parse_time

if TYPE_CHECKING:
    # Importaciones solo en type-checking para no requerir zendriver en tests
    import aiosqlite

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes del scraper
# ---------------------------------------------------------------------------

KIRILLOID_BASE_URL = "http://travian.kirilloid.ru/troops.php"
SERVER_VERSION = "1.45"
PROFILE_DIR = "profiles/scraper_kirilloid"
ICONS_DIR = Path("assets/icons")
BG_FILL_TOLERANCE = 30  # tolerancia flood-fill Pillow (configurable)

# (tribe_id_kirilloid, tribe_value, is_playable)
TRIBES_CONFIG: list[tuple[int, str, bool]] = [
    (1, "romans",    True),
    (2, "teutons",   True),
    (3, "gauls",     True),
    (4, "nature",    False),
    (5, "natars",    False),
    (6, "egyptians", True),
    (7, "huns",      True),
    (8, "spartans",  True),
    (9, "vikings",   True),
]

# Códigos de idioma que se pasan al selector alt= de #langbar
# (el alt es el código de idioma — estable entre versiones de kirilloid)
KIRILLOID_LANGUAGES: list[str] = [
    "ar", "bg", "cs", "da", "de", "el", "en", "es", "fa", "fr",
    "he", "hu", "it", "ja", "lt", "lv", "nl", "pl", "pt", "rs",
    "ru", "sl", "sv", "tr", "uk",
]

# Mapeo clase CSS de td → nombre de stat en modelo de datos
STAT_COLUMN_MAP: dict[str, str] = {
    "off":     "attack",
    "def_i":   "def_infantry",
    "def_c":   "def_cavalry",
    "speed":   "speed",
    "cap":     "carry",
    "res1":    "cost_wood",
    "res2":    "cost_clay",
    "res3":    "cost_iron",
    "res4":    "cost_crop",
    "res_sum": "cost_sum",
    "cu":      "upkeep",
    "time":    "train_time_s",
}

# Mapeo selector CSS del img → (icon_id, stat_name) para los 12 iconos de #main
STAT_ICON_MAP: list[tuple[str, str, str]] = [
    ("td.off img.stats.att_all",   "stat_attack",        "attack"),
    ("td.def_i img.stats.def_i",   "stat_def_infantry",  "def_infantry"),
    ("td.def_c img.stats.def_c",   "stat_def_cavalry",   "def_cavalry"),
    ("td.speed img.stats.speed",   "stat_speed",         "speed"),
    ("td.cap img.stats.cap",       "stat_carry",         "carry"),
    ("td.res1 img.res.r1",         "stat_wood",          "wood"),
    ("td.res2 img.res.r2",         "stat_clay",          "clay"),
    ("td.res3 img.res.r3",         "stat_iron",          "iron"),
    ("td.res4 img.res.r4",         "stat_crop",          "crop"),
    ("td.res_sum img.res.r6",      "stat_resources_sum", "resources_sum"),
    ("td.cu img.res.r5",           "stat_upkeep",        "upkeep"),
    ("td.time img.res.r7",         "stat_time",          "time"),
]

# Iconos NUEVOS exclusivos de #upg_table (los compartidos att_all/def_i/def_c no se duplican)
# (clase CSS del img dentro de td.upg, icon_id, stat_name)
UPGRADE_ICON_MAP: list[tuple[str, str, str]] = [
    ("stats eye",   "upgrade_scouting",         "scouting"),
    ("stats def_s", "upgrade_counter_scouting", "counter_scouting"),
    ("stats point", "upgrade_destructive",      "destructive"),
]

UPGRADE_NEW_ICONS: frozenset[str] = frozenset(
    icon_id for _, icon_id, _ in UPGRADE_ICON_MAP
)

# _color_distance, _remove_background y _wait_for_element se importan de
# adapters/scraper/utils.py y se re-exportan desde el import de arriba.


# ---------------------------------------------------------------------------
# Merge de nombres en troops.json (sin browser — testable)
# ---------------------------------------------------------------------------


def _merge_troop_names(
    tribe_value: str,
    nombres_por_idioma: dict[str, dict[int, str]],
    ordinals: list[int],
    catalog_path: Path | None = None,
) -> None:
    """
    Actualiza nombres de tropas en troops.json con la fuente de kirilloid (RN-04).

    Política (RN-04 — revisada):
    - El catálogo BASE es la fuente de verdad de kirilloid: los nombres scrapeados
      SOBRESCRIBEN el valor existente (incluso si ya tenía contenido).
    - EXCEPCIÓN: si el nombre scrapeado para un idioma viene vacío (""), NO se
      sobrescribe el valor existente — preserva datos de respaldo cuando kirilloid
      tiene un hueco para ese idioma.
    - Crea la clave de tropa si no existe.
    - Solo modifica core/i18n/catalog/base/troops.json, NUNCA override/.
      El JsonTranslationAdapter aplica override con mayor prioridad; las correcciones
      manuales viven ahí.
    - Escribe de forma atómica: carga → modifica en memoria → vuelca completo.
    - Valida JSON antes de escribir.

    Motivo del cambio: la capa i18n anterior dejó nombres ES incorrectos en el base
    (p.ej. ROMANS_3 = "Explorador de los Imperios" en lugar de "Imperano"). El merge
    no-destructivo conservaba esos errores. Al declarar kirilloid como fuente de verdad
    del base, los nombres correctos sobreescriben los viejos en cada ejecución.

    Args:
        tribe_value: valor del Tribe enum (ej. "romans", "nature")
        nombres_por_idioma: {lang_code: {ordinal: nombre}}
        ordinals: lista de ordinales de tropas de esta tribu
        catalog_path: ruta del fichero (inyectada para testing; default = path real del proyecto)
    """
    if catalog_path is None:
        catalog_path = Path("core/i18n/catalog/base/troops.json")

    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog: dict = json.load(f)

    for ordinal in ordinals:
        key = f"{tribe_value.upper()}_{ordinal}"
        if key not in catalog:
            catalog[key] = {}
        for lang_code, nombres in nombres_por_idioma.items():
            nombre = nombres.get(ordinal, "")
            # Solo sobrescribir cuando kirilloid tiene un nombre no vacío.
            # Si viene vacío, dejar el valor existente (evita borrar datos de respaldo).
            if nombre != "":
                catalog[key][lang_code] = nombre

    # Validar JSON antes de escribir (RN-10: escritura del JSON)
    json_str = json.dumps(catalog, ensure_ascii=False, indent=2)
    json.loads(json_str)  # lanza ValueError si el JSON no es válido

    with open(catalog_path, "w", encoding="utf-8") as f:
        f.write(json_str)


# ---------------------------------------------------------------------------
# Funciones que requieren browser (implementación para el CLI)
# Las interfaces están aquí; las importaciones de zendriver solo se resuelven
# en runtime cuando el script CLI las invoca (no se importan a nivel de módulo).
# ---------------------------------------------------------------------------



async def _parse_main_table(
    page,
    tribe_value: str,
    is_playable: bool,
) -> dict[int, dict]:
    """
    Lee la tabla #main.wire y extrae los stats de cada tropa.

    Devuelve: {ordinal: stats_dict}
    Los valores "—" se convierten a None (RN-07).
    El tiempo se convierte de H:MM:SS a segundos (RN-08).
    Las columnas no reconocidas se ignoran con warning (flujo alternativo col desconocida).
    """
    resultado: dict[int, dict] = {}
    rows = await page.query_selector_all("#main.wire tr")
    # La fila 0 es la de cabecera con iconos — la saltamos
    for row in rows[1:]:
        try:
            name_td = await row.query_selector("td.name[unit]")
            if name_td is None:
                continue
            ordinal = int(name_td.attrs.get("unit") or "")
        except (TypeError, ValueError):
            logger.warning("Fila con ordinal no entero en tribu '%s' — ignorando", tribe_value)
            continue

        stats: dict = {
            "server_version": SERVER_VERSION,
            "tribe": tribe_value,
            "ordinal": ordinal,
            "is_playable": is_playable,
        }

        for css_class, stat_name in STAT_COLUMN_MAP.items():
            td = await row.query_selector(f"td.{css_class}")
            if td is None:
                continue
            text = td.text.strip()
            if text in ("—", ""):
                stats[stat_name] = None
            elif stat_name == "train_time_s":
                try:
                    stats[stat_name] = parse_time(text)
                except ValueError as e:
                    logger.warning("Tiempo inválido en tribu '%s' ordinal %d: %s", tribe_value, ordinal, e)
                    stats[stat_name] = None
            else:
                try:
                    stats[stat_name] = parse_int(text)
                except ValueError as e:
                    logger.warning(
                        "Valor no numérico en tribu '%s' ordinal %d stat '%s': '%s' — %s",
                        tribe_value, ordinal, stat_name, text, e
                    )
                    stats[stat_name] = None

        resultado[ordinal] = stats

    return resultado


async def _parse_troop_names(page) -> dict[int, str]:
    """
    Lee los nombres de tropa del idioma actual de la página.

    Devuelve: {ordinal: nombre}
    """
    nombres: dict[int, str] = {}
    name_tds = await page.query_selector_all("td.name[unit]")
    for td in name_tds:
        try:
            ordinal = int(td.attrs.get("unit") or "")
            nombre = td.text.strip()
            nombres[ordinal] = nombre
        except (TypeError, ValueError):
            pass
    return nombres


async def _parse_upgrade_table(
    page,
    tribe_value: str,
    ordinal: int,
) -> list[dict]:
    """
    Lee el #upg_table de la página actual (URL ya cargada para la unidad concreta).

    La URL debe ser:
        troops.php#s=1.45&tribe=T&s_lvl=0&t_lvl=1&u_lvl=0&unit=N

    El #upg_table en esa URL muestra solo la unidad N — NO agrupa varias unidades.

    Estructura real del HTML (verificada en navegador):
    - Cabecera: 6 celdas td.upg con un <img class="stats X"> donde X es uno de:
        att_all, def_i, def_c, eye, def_s, point
      Las columnas que no aplican a la unidad llevan style="display:none".
    - Filas de datos: <tr> con exactamente 13 celdas en este orden:
        [0]  nivel (int 0-20)
        [1]  madera (r1)
        [2]  barro  (r2)
        [3]  hierro (r3)
        [4]  cereal (r4)
        [5]  total  (r6)
        [6]  tiempo (H:MM:SS o variante)
        [7-12] valores de las 6 stats (en el mismo orden que la cabecera)
               Las ocultas pueden tener style="display:none" en la fila de datos.
               El valor viene como texto "40.5800" con posible <small> (se lee via .text).
    - La fila de nivel 0 tiene primera celda vacía (la base ya está en troop_stats) →
      se detecta por celdas[0].text vacío o "0" explícito; se trata como nivel 0 y
      puede omitirse (solo capturamos niveles 1-20).

    Solo procesa columnas VISIBLES (sin display:none) — RN-09.
    Ignora filas cuyo primer td no sea dígito 1-20 — EC-13.

    Devuelve: lista de upgrade_dicts (puede estar vacía si no hay tabla o 0 datos)
    """
    upg_table = await page.query_selector("#upg_table")
    if upg_table is None:
        return []

    # ------------------------------------------------------------------
    # 1. Detectar qué columnas de stat están VISIBLES desde la cabecera.
    #    Las 6 celdas td.upg están en la primera fila (<tr>) del #upg_table.
    #    Cada una tiene un <img class="stats X">.  Si la celda tiene
    #    style="display:none" la columna no aplica a esta unidad.
    # ------------------------------------------------------------------
    # Mapa clase-img → nombre de stat canónico (según spec)
    _IMG_CLASS_TO_STAT: dict[str, str] = {
        "att_all": "attack",
        "def_i":   "def_infantry",
        "def_c":   "def_cavalry",
        "eye":     "scouting",
        "def_s":   "counter_scouting",
        "point":   "destructive",
    }

    header_rows = await upg_table.query_selector_all("tr")
    if not header_rows:
        return []

    # Los td.upg SOLO existen en la fila de cabecera (las filas de datos usan <td>
    # sin clase). OJO: la PRIMERA fila del #upg_table es un título con
    # <td colspan="12" class="rbg">mejoras...</td> (sin td.upg); la cabecera real
    # con los 6 td.upg es la 2ª fila. Por eso buscamos los td.upg en TODA la tabla
    # (devuelve exactamente las 6 celdas de cabecera, en orden att_all..point).
    header_cells = await upg_table.query_selector_all("td.upg")

    # visible_stats: lista ordenada de (indice_posicional_en_fila_datos, stat_name)
    # El índice en la fila de datos es 7 + posición en la cabecera (6 posiciones: 0-5)
    visible_stats: list[tuple[int, str]] = []
    for i, cell in enumerate(header_cells):
        # Comprobar si la celda está oculta
        cell_style = (cell.attrs.get("style") or "").replace(" ", "")
        if "display:none" in cell_style:
            continue
        # Buscar el img con clase stats
        img = await cell.query_selector("img.stats")
        if img is None:
            continue
        # Obtener las clases del img (ContraDict: "class" → "class_")
        img_classes = (img.attrs.get("class_") or img.attrs.get("class") or "").split()
        stat_name: str | None = None
        for cls in img_classes:
            if cls in _IMG_CLASS_TO_STAT:
                stat_name = _IMG_CLASS_TO_STAT[cls]
                break
        if stat_name is None:
            logger.warning(
                "Columna de mejora con clase img desconocida %s en tribu '%s' ordinal %d",
                img_classes, tribe_value, ordinal
            )
            continue
        data_col_index = 7 + i  # las 7 primeras celdas son nivel + costes + tiempo
        visible_stats.append((data_col_index, stat_name))

    if not visible_stats:
        # No hay columnas visibles → unidad sin mejoras detectables
        return []

    # ------------------------------------------------------------------
    # 2. Leer filas de datos (niveles 1-20)
    # ------------------------------------------------------------------
    result: list[dict] = []

    for row in header_rows[1:]:
        tds = await row.query_selector_all("td")
        if len(tds) < 13:
            continue

        # Celda 0: nivel
        level_text = tds[0].text.strip()
        if not level_text.isdigit():
            continue  # cabecera de grupo, fila vacía u otra estructura
        level = int(level_text)
        if level < 1 or level > 20:
            # Nivel 0 = base (ya en troop_stats) o fuera de rango → saltar
            if level != 0:
                logger.warning(
                    "Nivel de mejora fuera de rango (%d) en tribu '%s' ordinal %d — ignorando",
                    level, tribe_value, ordinal
                )
            continue

        # Costes fijos: celdas 1-5 (madera, barro, hierro, cereal, total)
        cost_wood     = parse_int_or_none(tds[1].text.strip())
        cost_clay     = parse_int_or_none(tds[2].text.strip())
        cost_iron     = parse_int_or_none(tds[3].text.strip())
        cost_crop     = parse_int_or_none(tds[4].text.strip())
        cost_sum      = parse_int_or_none(tds[5].text.strip())

        # Tiempo: celda 6 (H:MM:SS)
        time_text = tds[6].text.strip()
        try:
            upgrade_time_s = parse_time(time_text) if time_text and time_text != "—" else None
        except ValueError:
            upgrade_time_s = None

        # Stats visibles: celdas en los índices detectados desde la cabecera
        for data_col_index, stat_name in visible_stats:
            if data_col_index >= len(tds):
                continue

            td_stat = tds[data_col_index]

            # Comprobar si esta celda específica está oculta en esta fila
            td_style = (td_stat.attrs.get("style") or "").replace(" ", "")
            if "display:none" in td_style:
                continue

            # El valor viene como "40.<small>5800</small>". OJO: `.text` devuelve SOLO
            # el nodo inmediato ("40.", → 40.0, pierde el decimal). Hay que usar
            # `.text_all` (concatena descendientes), PERO une los nodos con ESPACIO
            # ("40. 5800"), así que quitamos espacios para reconstruir "40.5800".
            value_text = (td_stat.text_all or "").replace(" ", "").strip()
            if not value_text or value_text == "—":
                continue

            try:
                stat_value = float(value_text.replace(",", "."))
            except ValueError:
                logger.warning(
                    "Valor de stat '%s' no parseable '%s' en tribu '%s' ordinal %d nivel %d",
                    stat_name, value_text, tribe_value, ordinal, level
                )
                continue

            result.append({
                "server_version": SERVER_VERSION,
                "tribe":          tribe_value,
                "ordinal":        ordinal,
                "level":          level,
                "stat_name":      stat_name,
                "stat_value":     stat_value,
                "cost_wood":      cost_wood,
                "cost_clay":      cost_clay,
                "cost_iron":      cost_iron,
                "cost_crop":      cost_crop,
                "cost_sum":       cost_sum,
                "upgrade_time_s": upgrade_time_s,
            })

    return result


async def _capture_troop_icon(
    page,
    tribe_value: str,
    ordinal: int,
    icon_id: str,
    conn: "aiosqlite.Connection",
    tribe_id: int,
) -> None:
    """
    Captura el icono de una tropa vía screenshot del elemento DOM.

    OJO con la numeración: el atributo `td.name[unit]` es POR TRIBU (1..10), pero la
    CLASE del icono `img.unit.uN` usa el id GLOBAL de kirilloid (romanos u1-u10,
    germanos u11-u20, galos u21-u30, ...). Por eso `img.unit.u{ordinal}` solo acierta
    en romanos. Capturamos el icono RELATIVO a la fila de la tropa (robusto ante la
    numeración), con fallback a la fórmula del id global (tribe_id-1)*10 + ordinal.

    NUNCA se cae a la celda del nombre (td.name): capturaría el TEXTO en vez del sprite
    (bug observado: egyptians_1.png salía como "Пікейщик"). Si no hay sprite, se lanza
    y el caller registra icon_id=None.
    """
    import base64
    from datetime import datetime, timezone

    element = None
    name_cell = await page.query_selector(f"#main.wire td.name[unit='{ordinal}']")
    if name_cell is not None:
        try:
            row = name_cell.parent  # el <tr> de la tropa
            if row is not None:
                element = await row.query_selector("img.unit")
        except Exception:
            element = None
    if element is None:
        # Fallback: id global de kirilloid
        global_unit = (tribe_id - 1) * 10 + ordinal
        element = await page.query_selector(f"img.unit.u{global_unit}")
    if element is None:
        raise RuntimeError(
            f"sprite de la tropa '{icon_id}' no encontrado (ni por fila ni por id global)"
        )

    png_bytes = base64.b64decode(await element.screenshot_b64(format="png", scale=1))

    img = Image.open(BytesIO(png_bytes)).convert("RGBA")
    if img.width == 0 or img.height == 0:
        raise RuntimeError(f"sprite de '{icon_id}' con dimensiones 0x0")

    img = _remove_background(img, tolerance=BG_FILL_TOLERANCE)

    out_path = ICONS_DIR / f"{icon_id}.png"
    img.save(str(out_path), "PNG")

    w, h = img.size
    size = out_path.stat().st_size

    await conn.execute(
        "INSERT OR REPLACE INTO icon_metadata VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            icon_id, "troop", tribe_value, ordinal, None,
            f"assets/icons/{icon_id}.png", size, w, h,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    await conn.commit()


async def _capture_stat_icons(
    page,
    conn: "aiosqlite.Connection",
) -> None:
    """
    Captura los 12 iconos de la fila de cabecera de la tabla #main.

    Los selectores son estructurales (clase CSS del img, nunca alt/texto).
    Si el PNG ya existe en disco, lo salta (idempotencia).
    Errores no fatales: registra warning y continúa.
    """
    import base64
    from datetime import datetime, timezone

    for (selector, icon_id, stat_name) in STAT_ICON_MAP:
        out_path = ICONS_DIR / f"{icon_id}.png"
        if out_path.exists():
            continue

        try:
            # BUG-2: la primera fila de #main.wire es el selector de tribu
            # (<tr><td colspan="14"><select id="tribe">...) — NO la cabecera de iconos.
            # Los iconos de stat viven en la SEGUNDA fila (la cabecera real).
            # El selector directo "#main.wire td.off img.stats.att_all" (sin
            # tr:first-child) funciona sin ambigüedad: el <img> de stat solo
            # aparece en la fila de cabecera; las filas de tropa tienen números
            # en td.off, nunca un <img>.
            full_selector = f"#main.wire {selector}"
            element = await page.query_selector(full_selector)
            if element is None:
                logger.warning("Icono de stat '%s' no encontrado (selector: '%s')", icon_id, full_selector)
                continue

            png_bytes = base64.b64decode(await element.screenshot_b64(format="png", scale=1))
            img = Image.open(BytesIO(png_bytes)).convert("RGBA")
            img = _remove_background(img, tolerance=BG_FILL_TOLERANCE)

            img.save(str(out_path), "PNG")
            w, h = img.size
            size = out_path.stat().st_size

            await conn.execute(
                "INSERT OR REPLACE INTO icon_metadata VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    icon_id, "stat", None, None, stat_name,
                    f"assets/icons/{icon_id}.png", size, w, h,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await conn.commit()
        except Exception as e:
            logger.error("stat_icon/%s: %s", icon_id, e)


async def _capture_upgrade_icons(
    page,
    conn: "aiosqlite.Connection",
) -> None:
    """
    Captura los 3 iconos NUEVOS de la fila de cabecera de #upg_table.

    Solo captura upgrade_scouting, upgrade_counter_scouting, upgrade_destructive.
    Los iconos compartidos (att_all/def_i/def_c) NO se capturan aquí — ya existen
    como stat_attack / stat_def_infantry / stat_def_cavalry (RN-11).

    Los selectores son por clase CSS del img (estables entre idiomas).
    Si la celda está oculta (display:none), la omite sin error.
    Si la tribu no tiene #upg_table, retorna sin error.
    """
    import base64
    from datetime import datetime, timezone

    upg_table = await page.query_selector("#upg_table")
    if upg_table is None:
        return

    for (img_class, icon_id, stat_name) in UPGRADE_ICON_MAP:
        out_path = ICONS_DIR / f"{icon_id}.png"
        if out_path.exists():
            continue

        try:
            # Selector estructural: clase CSS del img dentro de td.upg
            # "stats eye" → "stats.eye" para el selector CSS
            css_classes = img_class.replace(" ", ".")
            selector = f"#upg_table td.upg img.{css_classes}"
            element = await page.query_selector(selector)
            if element is None:
                # Esta tribu no tiene esa columna visible — omitir sin error
                continue

            # Verificar que la celda padre td.upg no está oculta
            # element.parent es una @property, no un método async
            parent_td = element.parent
            parent_style = (parent_td.attrs.get("style") or "") if parent_td else ""
            if "display:none" in parent_style:
                continue

            png_bytes = base64.b64decode(await element.screenshot_b64(format="png", scale=1))
            img = Image.open(BytesIO(png_bytes)).convert("RGBA")
            img = _remove_background(img, tolerance=BG_FILL_TOLERANCE)

            img.save(str(out_path), "PNG")
            w, h = img.size
            size = out_path.stat().st_size

            await conn.execute(
                "INSERT OR REPLACE INTO icon_metadata VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    icon_id, "upgrade", None, None, stat_name,
                    f"assets/icons/{icon_id}.png", size, w, h,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await conn.commit()
        except Exception as e:
            logger.error("upgrade_icon/%s: %s", icon_id, e)
