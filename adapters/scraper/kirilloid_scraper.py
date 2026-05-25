"""
Lógica de scraping de travian.kirilloid.ru.

Este módulo contiene SOLO las funciones puras de parseo y las funciones que
interactúan con el browser (para capturas de iconos). El script CLI en
scripts/load_kirilloid.py orquesta el flujo completo.

Funciones sin dependencias de browser (testables sin Chrome):
  - _parse_time        — "H:MM:SS" → segundos enteros
  - _parse_int         — "1.200" / "1,200" → 1200
  - _parse_int_or_none — igual pero devuelve None para "—" / vacío
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
from collections import Counter
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw

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

# ---------------------------------------------------------------------------
# Utilidades de parseo puro (sin browser — testables)
# ---------------------------------------------------------------------------


def _parse_time(text: str) -> int:
    """
    Convierte "H:MM:SS" a segundos enteros.

    El texto puede tener espacios u otras partes (p.ej. "0:30:00 / 2880 / jornada").
    Solo se usa la primera parte antes del espacio (RN-08).

    Caso especial (EC-02 / BUG-3): algunas unidades NPC o instantáneas muestran
    el tiempo como un entero pelado sin ":" (p.ej. "0", "5"). Se interpreta
    directamente como ese número de segundos, sin lanzar excepción.
    Esto ocurre en natars reales y en otras tribus mientras la corrección del
    off-by-one (BUG-1) no haya sido aplicada aún.

    Lanza ValueError si el formato no es válido.
    """
    text = text.strip().split()[0]
    # Entero pelado sin ":" → segundos directos (p.ej. "0" → 0, "5" → 5)
    if ":" not in text:
        try:
            return int(text)
        except ValueError:
            raise ValueError(f"Formato de tiempo inesperado: '{text}'")
    parts = text.split(":")
    if len(parts) != 3:
        raise ValueError(f"Formato de tiempo inesperado: '{text}'")
    try:
        h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        raise ValueError(f"Formato de tiempo inesperado: '{text}'")
    return h * 3600 + m * 60 + s


def _parse_int(text: str) -> int:
    """
    Convierte un entero con separadores de miles a int.

    Acepta tanto "." como "," como separadores (p.ej. "1.200" → 1200, "1,200" → 1200).
    Lanza ValueError si el texto no es numérico tras eliminar separadores.
    """
    cleaned = text.strip().replace(".", "").replace(",", "")
    return int(cleaned)


def _parse_int_or_none(text: str) -> int | None:
    """
    Como _parse_int pero devuelve None para "—", vacío o texto no numérico.
    Conforme a RN-07: valores "—" → NULL/None, nunca 0.
    """
    stripped = text.strip()
    if stripped in ("—", "", "-"):
        return None
    try:
        return _parse_int(stripped)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Eliminación de fondo con Pillow (sin browser — testable)
# ---------------------------------------------------------------------------


def _color_distance(c1: tuple, c2: tuple) -> float:
    """Distancia euclidiana entre dos colores RGBA."""
    return sum((a - b) ** 2 for a, b in zip(c1[:3], c2[:3])) ** 0.5


def _remove_background(img: Image.Image, tolerance: int = BG_FILL_TOLERANCE) -> Image.Image:
    """
    Elimina el fondo de un icono usando flood-fill desde las 4 esquinas.

    Estrategia:
    1. Lee el color de las 4 esquinas.
    2. El color de fondo es el más frecuente entre las 4 esquinas.
    3. Si las 4 esquinas tienen colores completamente distintos (len(set) == 4),
       no hay fondo uniforme detectable → devuelve la imagen sin cambios (EC-11/EC-15).
    4. Para cada esquina cuyo color esté dentro de la tolerancia del color de fondo,
       aplica ImageDraw.floodfill con fill=(0,0,0,0) para hacerlo transparente.

    La imagen debe estar en modo RGBA antes de llamar a esta función.
    """
    img = img.convert("RGBA")
    corners = [
        img.getpixel((0, 0)),
        img.getpixel((img.width - 1, 0)),
        img.getpixel((0, img.height - 1)),
        img.getpixel((img.width - 1, img.height - 1)),
    ]
    # Color de fondo = más frecuente entre las 4 esquinas
    # (si empate, max() toma el primero en orden de aparición)
    corner_rgb = [c[:3] for c in corners]
    counts = Counter(corner_rgb)
    bg_color = counts.most_common(1)[0][0]

    # Si todas las esquinas son distintas → no hay fondo uniforme → devolver sin cambios
    if len(counts) == 4:
        return img

    fill_coords = [
        (0, 0),
        (img.width - 1, 0),
        (0, img.height - 1),
        (img.width - 1, img.height - 1),
    ]
    for (x, y) in fill_coords:
        corner_color = img.getpixel((x, y))[:3]
        if _color_distance(corner_color, bg_color) <= tolerance:
            ImageDraw.floodfill(img, (x, y), (0, 0, 0, 0), thresh=tolerance)

    return img


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


async def _wait_for_element(page, selector: str, timeout: int = 30) -> None:
    """
    Espera a que un elemento sea visible en la página.
    Lanza KirilloidScraperError si el timeout expira.
    """
    from core.exceptions import KirilloidScraperError
    import asyncio

    elapsed = 0
    interval = 0.5
    while elapsed < timeout:
        try:
            el = await page.query_selector(selector)
            if el is not None:
                return
        except Exception:
            pass
        await asyncio.sleep(interval)
        elapsed += interval
    raise KirilloidScraperError(
        message=f"Timeout esperando selector '{selector}' ({timeout}s)",
    )


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
                    stats[stat_name] = _parse_time(text)
                except ValueError as e:
                    logger.warning("Tiempo inválido en tribu '%s' ordinal %d: %s", tribe_value, ordinal, e)
                    stats[stat_name] = None
            else:
                try:
                    stats[stat_name] = _parse_int(text)
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
) -> dict[int, list[dict]]:
    """
    Lee la tabla #upg_table y extrae las mejoras de herrería.

    Solo procesa columnas visibles (sin display:none) — RN-09.
    Ignora filas cuyo primer td no sea entero 0-20 — EC-13.
    Detecta el ordinal de cada tropa desde las filas de cabecera de grupo.

    Devuelve: {ordinal: [upgrade_dict, ...]}
    """
    upg_table = await page.query_selector("#upg_table")
    if upg_table is None:
        return {}

    resultado: dict[int, list[dict]] = {}
    current_ordinal: int | None = None

    rows = await upg_table.query_selector_all("tr")
    for row in rows:
        # Detectar filas de cabecera de grupo: tienen img.unit.uN
        # que indica el ordinal de las tropas que siguen
        try:
            # Buscar la primera img con clase unit que tenga uN
            unit_imgs = await row.query_selector_all("img.unit")
            for img in unit_imgs:
                # attrs["class"] se almacena como "class_" en ContraDict (zendriver remap)
                classes = (img.attrs.get("class_") or img.attrs.get("class") or "").split()
                for cls in classes:
                    if cls.startswith("u") and cls[1:].isdigit():
                        current_ordinal = int(cls[1:])
                        break
        except Exception:
            pass

        # Detectar columnas visibles en filas de cabecera de tabla (th)
        # y filas de datos (td)
        tds = await row.query_selector_all("td")
        if not tds or current_ordinal is None:
            continue

        level_text = ""
        try:
            level_text = tds[0].text.strip()
        except Exception:
            continue

        if not level_text.isdigit():
            continue
        level = int(level_text)
        if level < 0 or level > 20:
            logger.warning(
                "Nivel de mejora fuera de rango (%d) en tribu '%s' ordinal %d — ignorando",
                level, tribe_value, current_ordinal
            )
            continue

        # Leer columnas de upg (son las celdas td.upg visibles)
        upg_tds = []
        for td in tds:
            try:
                cls = td.attrs.get("class_") or td.attrs.get("class") or ""
                style = td.attrs.get("style") or ""
                if "upg" in cls and "display:none" not in style:
                    text = td.text.strip()
                    if text not in ("—", ""):
                        upg_tds.append((cls, text))
            except Exception:
                pass

        # Leer costes y tiempo (columnas fijas de la fila)
        cost_wood = cost_clay = cost_iron = cost_crop = cost_sum = upgrade_time_s = None
        for td in tds:
            try:
                cls = td.attrs.get("class_") or td.attrs.get("class") or ""
                text = td.text.strip()
                if "res1" in cls:
                    cost_wood = _parse_int_or_none(text)
                elif "res2" in cls:
                    cost_clay = _parse_int_or_none(text)
                elif "res3" in cls:
                    cost_iron = _parse_int_or_none(text)
                elif "res4" in cls:
                    cost_crop = _parse_int_or_none(text)
                elif "res_sum" in cls:
                    cost_sum = _parse_int_or_none(text)
                elif "time" in cls:
                    try:
                        upgrade_time_s = _parse_time(text) if text and text != "—" else None
                    except ValueError:
                        upgrade_time_s = None
            except Exception:
                pass

        for cls, value_text in upg_tds:
            # Mapear clase CSS de la celda upg al nombre de stat
            stat_name = _upg_class_to_stat_name(cls)
            if stat_name is None:
                continue
            try:
                stat_value = float(value_text.replace(",", "."))
            except ValueError:
                continue

            upgrade: dict = {
                "server_version": SERVER_VERSION,
                "tribe": tribe_value,
                "ordinal": current_ordinal,
                "level": level,
                "stat_name": stat_name,
                "stat_value": stat_value,
                "cost_wood": cost_wood,
                "cost_clay": cost_clay,
                "cost_iron": cost_iron,
                "cost_crop": cost_crop,
                "cost_sum": cost_sum,
                "upgrade_time_s": upgrade_time_s,
            }
            resultado.setdefault(current_ordinal, []).append(upgrade)

    return resultado


def _upg_class_to_stat_name(cls: str) -> str | None:
    """Mapea la clase CSS de una celda td.upg al nombre de stat."""
    # Mapeo basado en las clases que kirilloid usa en #upg_table
    _MAP = {
        "off":    "attack",
        "def_i":  "def_infantry",
        "def_c":  "def_cavalry",
        "eye":    "spy",
        "def_s":  "destructive",   # counter_scouting en kirilloid = destructive en el modelo
        "point":  "carry",
    }
    for key, stat in _MAP.items():
        if key in cls:
            return stat
    return None


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
