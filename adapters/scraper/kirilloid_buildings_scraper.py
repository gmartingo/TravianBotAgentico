"""
Lógica de scraping de edificios desde travian.kirilloid.ru (build.php).

Este módulo contiene las funciones que interactúan con el browser para capturar
datos de edificios. El script CLI scripts/load_kirilloid_buildings.py orquesta el
flujo completo.

Funciones sin dependencias de browser (testables sin Chrome):
  - _parse_building_index           — lee el índice de edificios (3 columnas)
  - _parse_building_names_from_index — relectura del índice solo para nombres
  - _parse_building_detail          — tabla #data.wire de un edificio
  - _merge_building_names           — merge en buildings.json (política sobrescribe)
  - _slugify                        — nombre → slug ASCII para icon_id descriptivo
  - _make_icon_id                   — construye "building_{gid}_{slug}" desde catalog

Funciones que requieren browser (NO testadas aquí, integración manual):
  - _capture_building_icon          — screenshot + remove_background

Lección SPA kirilloid (RN-B-13): para cada gid, hacer
  await browser.get("about:blank") → await browser.get(url_detalle) → esperar #data.wire
El cambio de solo el hash NO re-renderiza kirilloid.

REGLA ANTI-DETECCIÓN: Todos los selectores son estructurales (clase/atributo/data-gid).
Nunca se usan selectores por texto visible — kirilloid es multilenguaje.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

from adapters.scraper.utils import _remove_background
from core.utils.parsing import parse_int_or_none, parse_time

if TYPE_CHECKING:
    import aiosqlite

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

KIRILLOID_BUILD_URL = "http://travian.kirilloid.ru/build.php"
SERVER_VERSION = "1.45"
PROFILE_DIR = "profiles/scraper_kirilloid"
ICONS_DIR = Path("assets/icons")
BG_FILL_TOLERANCE = 30

# Mapeo del texto del <h3> (en idioma base 'es') → categoría canónica.
# Si el h3 no está en el mapa se usa el h3 lowercased como fallback.
CATEGORY_BY_H3: dict[str, str] = {
    "recursos":         "resources",
    "militar":          "military",
    "infraestructura":  "infrastructure",
}

# Mismo listado de 25 idiomas que en kirilloid_scraper.py
KIRILLOID_LANGUAGES: list[str] = [
    "ar", "bg", "cs", "da", "de", "el", "en", "es", "fa", "fr",
    "he", "hu", "it", "ja", "lt", "lv", "nl", "pl", "pt", "rs",
    "ru", "sl", "sv", "tr", "uk",
]

# Mapeo clase CSS del <img> en la cabecera <th> → nombre de campo en building_stats
# Las claves deben coincidir exactamente con la clase CSS del <img> (strip).
BUILDING_HEADER_MAP: dict[str, str] = {
    "icon--scalable res r1": "cost_wood",
    "res r1":                "cost_wood",
    "res r2":                "cost_clay",
    "res r3":                "cost_iron",
    "res r4":                "cost_crop",
    "res r6":                "cost_sum",
    "res r5":                "upkeep",
    "res r7":                "build_time_s",
    # "building g10" y "building g11" → OMITIR (RN-B-08 / DECISION-PENDIENTE-#3)
}

# ---------------------------------------------------------------------------
# Parseo del índice (sin browser — testable con HTML estático)
# ---------------------------------------------------------------------------


async def _parse_building_index(browser) -> list[tuple[int, str, str]]:
    """
    Lee el <div id="build_list"> y extrae (gid, category, nombre) por edificio.

    Selector de columnas: #build_list > div.build_list__column
    Selector h3 de categoría: h3 dentro de cada columna (texto lowercased → CATEGORY_BY_H3)
    Selector de items:    div.build_list__item[data-gid]
    GID: int(item.attrs["data-gid"]).
    Nombre: texto del div (strip).

    El orden REAL de columnas en kirilloid (idioma base 'es') es:
      columna 0: <h3>recursos</h3>       → "resources"
      columna 1: <h3>militar</h3>        → "military"
      columna 2: <h3>infraestructura</h3>→ "infrastructure"

    La categoría se obtiene siempre leyendo el <h3> real de cada columna, no por
    posición hardcodeada, para ser robusta ante reordenamientos futuros.

    Devuelve [(gid, category, nombre), ...]  — acumula las 3 columnas (≈50 items).
    """
    result: list[tuple[int, str, str]] = []
    columns = await browser.query_selector_all("#build_list > div.build_list__column")
    for column in columns:
        # Obtener categoría leyendo el <h3> real de la columna
        h3 = await column.query_selector("h3")
        if h3 is not None:
            h3_text = h3.text.strip().lower()
            category = CATEGORY_BY_H3.get(h3_text, h3_text)
        else:
            category = "unknown"
            logger.warning("Columna de build_list sin <h3> — categoría marcada 'unknown'")

        items = await column.query_selector_all("div.build_list__item[data-gid]")
        for item in items:
            gid_str = item.attrs.get("data-gid", "")
            if not str(gid_str).isdigit():
                logger.warning("data-gid no entero: '%s' — ignorando", gid_str)
                continue
            gid = int(gid_str)
            name = item.text.strip()
            result.append((gid, category, name))
    return result


async def _parse_building_names_from_index(browser) -> dict[int, str]:
    """
    Relectura del índice solo para obtener nombres (tras cambio de idioma).
    Devuelve {gid: nombre} sin categoría.
    """
    result: dict[int, str] = {}
    items = await browser.query_selector_all(
        "#build_list div.build_list__item[data-gid]"
    )
    for item in items:
        gid_str = item.attrs.get("data-gid", "")
        if not str(gid_str).isdigit():
            continue
        gid = int(gid_str)
        name = item.text.strip()
        result[gid] = name
    return result


# ---------------------------------------------------------------------------
# Parseo del detalle (sin browser — testable con HTML estático)
# ---------------------------------------------------------------------------


async def _parse_building_detail(browser) -> tuple[list[dict], str]:
    """
    Lee la tabla #data.wire del detalle de un edificio.

    Estrategia de mapeo de columnas (robusta ante reordenamientos de kirilloid):
    1. Lee la fila <thead><tr class="rbg"> y localiza cada <th>.
    2. Por cada <th>:
       - Si tiene <img>: usa su clase CSS para mapear mediante BUILDING_HEADER_MAP.
         Si la clase contiene "building g10" o "building g11" → OMITIR (RN-B-08).
         Si la clase no está en el mapa → __UNKNOWN__ (warning, columna nueva).
       - Si NO tiene <img>: lee el texto del <th>.
         Si el texto es "PC" / "CP" / "KULTUR" → culture_points.
         Si es la última columna con texto no vacío → effect_label + effect_value.
    3. Guarda la posición (índice 0-based) de cada campo.
    4. Lee filas del <tbody>: asigna valores por índice de columna.

    Devuelve:
      - lista de dicts: {level, cost_wood, ..., effect_value}
      - effect_label: str (texto del <th> de la última col, o "")
    """
    result: list[dict] = []
    effect_label = ""

    # --- Leer cabecera y construir mapa posición → campo ---
    header_row = await browser.query_selector("#data.wire thead tr.rbg")
    if header_row is None:
        return [], ""

    # BUG FIX: kirilloid usa <td> en la fila de cabecera <tr class="rbg">, NO <th>
    ths = await header_row.query_selector_all("td")
    col_map: dict[int, str] = {}  # {índice_columna: campo}

    for idx, th in enumerate(ths):
        if idx == 0:
            col_map[idx] = "level"  # primera columna siempre es el nivel
            continue

        img = await th.query_selector("img")
        if img is not None:
            # Obtener clase CSS del img (puede estar como "class" o "class_" en ContraDict)
            img_class_str = (
                img.attrs.get("class_")
                or img.attrs.get("class")
                or ""
            ).strip()

            # Normalizar clases quitando "icon--scalable " si está presente como prefijo
            # para unificar las variantes que kirilloid puede emitir
            normalized = img_class_str
            for prefix in ("icon--scalable ", "icon--scalable"):
                if normalized.startswith(prefix):
                    normalized = normalized[len(prefix):].strip()

            # Comprobar si es una de las omitidas (RN-B-08)
            if "building g10" in img_class_str or "building g11" in img_class_str:
                col_map[idx] = "__OMIT__"
            elif img_class_str in BUILDING_HEADER_MAP:
                col_map[idx] = BUILDING_HEADER_MAP[img_class_str]
            elif normalized in BUILDING_HEADER_MAP:
                col_map[idx] = BUILDING_HEADER_MAP[normalized]
            else:
                logger.warning(
                    "Columna de cabecera desconocida (clase img: '%s') — ignorando (EC-B-08)",
                    img_class_str,
                )
                col_map[idx] = "__UNKNOWN__"
        else:
            # Sin imagen: leer texto del <th>
            th_text = th.text.strip()
            if th_text.upper() in ("PC", "CP", "KULTUR"):
                col_map[idx] = "culture_points"
            elif th_text != "" and idx == len(ths) - 1:
                # Última columna con texto → efecto del edificio (DECISION-PENDIENTE-#6)
                col_map[idx] = "effect_value"
                effect_label = th_text
            else:
                col_map[idx] = "__UNKNOWN__"

    # --- Leer filas de datos ---
    tbody_rows = await browser.query_selector_all("#data.wire tbody tr")
    for tr in tbody_rows:
        tds = await tr.query_selector_all("td")
        if not tds:
            continue

        row_data: dict = {}
        for idx, td in enumerate(tds):
            campo = col_map.get(idx, "__UNKNOWN__")
            if campo in ("__OMIT__", "__UNKNOWN__"):
                continue

            # Para el text de los <td>, zendriver expone .text como @property
            cell_text = td.text.strip()

            if campo == "level":
                if not str(cell_text).isdigit():
                    break  # fila no es de datos de nivel
                row_data["level"] = int(cell_text)
            elif campo == "build_time_s":
                # Intentar parse_int_or_none primero; si falla, parse_time (H:MM:SS)
                val = parse_int_or_none(cell_text)
                if val is None and cell_text not in ("—", ""):
                    try:
                        val = parse_time(cell_text)
                    except (ValueError, AttributeError):
                        val = None
                row_data["build_time_s"] = val
            else:
                row_data[campo] = parse_int_or_none(cell_text)

        if "level" in row_data:
            result.append(row_data)

    return result, effect_label


# ---------------------------------------------------------------------------
# Merge en buildings.json (sin browser — testable)
# ---------------------------------------------------------------------------


def _merge_building_names(
    nombres_por_idioma: dict[str, dict[int, str]],
    catalog_path: Path | None = None,
) -> None:
    """
    Actualiza nombres de edificios en buildings.json con la fuente de kirilloid.

    Política (RN-B-04 / DECISION-PENDIENTE-#5):
    - Para cada gid y cada idioma: si el nombre nuevo es no-vacío → sobrescribir.
    - Si el nombre nuevo es vacío → conservar el existente (EC-B-05).
    - El campo "alias" del JSON NO se toca.
    - Si el gid no existe en el JSON → crear la entrada con los nombres disponibles.
    - Solo modifica catalog/base/buildings.json, NUNCA override/.
    - Escritura atómica: carga → modifica en memoria → volcado con tmp+rename.
    - Valida JSON antes de escribir (EC-B-14: claves string).

    Args:
        nombres_por_idioma: {lang_code: {gid: nombre}}
        catalog_path: ruta inyectable para testing; default = path real del proyecto.
    """
    if catalog_path is None:
        catalog_path = Path("core/i18n/catalog/base/buildings.json")

    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog: dict = json.load(f)

    for lang_code, gid_to_name in nombres_por_idioma.items():
        for gid, nombre in gid_to_name.items():
            key = str(gid)  # EC-B-14: claves string
            if key not in catalog:
                catalog[key] = {"alias": f"building_{gid}"}
            if nombre and nombre.strip():  # solo sobrescribir si no es vacío
                catalog[key][lang_code] = nombre
            # Si nombre vacío → conservar existente (RN-B-04 / EC-B-05)

    # Validar JSON antes de escribir
    json_str = json.dumps(catalog, ensure_ascii=False, indent=2)
    json.loads(json_str)  # lanza ValueError si el JSON no es válido

    # Escritura atómica: tmp + rename
    tmp_path = catalog_path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(json_str)
    tmp_path.replace(catalog_path)


# ---------------------------------------------------------------------------
# Helpers de icon_id descriptivo (sin dependencias externas)
# ---------------------------------------------------------------------------


def _slugify(name: str) -> str:
    """
    Convierte un nombre de edificio a un slug ASCII estable para usar en icon_id.

    Pasos:
      1. NFD + eliminar diacríticos (unicodedata): "Almacén" → "Almacen"
      2. ASCII puro: descartar cualquier carácter no-ASCII residual
      3. Minúsculas
      4. Espacios y guiones → guión bajo; eliminar caracteres no alfanuméricos

    Ejemplos:
      "Warehouse"          → "warehouse"
      "Almacén"            → "almacen"
      "Gran Almacén"       → "gran_almacen"
      "Edificio principal" → "edificio_principal"
      ""                   → ""
    """
    # Normalizar unicode: separar carácter base del diacrítico
    normalized = unicodedata.normalize("NFD", name)
    # Quedarse solo con caracteres ASCII (elimina diacríticos que son non-ASCII)
    ascii_str = normalized.encode("ascii", "ignore").decode("ascii")
    # Minúsculas
    lower = ascii_str.lower()
    # Espacios y guiones → guión bajo
    with_underscores = re.sub(r"[\s\-]+", "_", lower)
    # Eliminar cualquier carácter que no sea alfanumérico ni guión bajo
    slug = re.sub(r"[^a-z0-9_]", "", with_underscores)
    # Colapsar guiones bajos múltiples y eliminar extremos
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug


def _make_icon_id(gid: int, name: str | None = None, catalog_path: Path | None = None) -> str:
    """
    Construye un icon_id descriptivo y estable para un edificio.

    Formato: "building_{gid}_{slug}"

    Prioridad del slug (de mayor a menor):
      1. `name` pasado como argumento (nombre recién scrapeado, alineado por gid) — preferido.
      2. Nombre en inglés ("en") del JSON (fallback si name no se pasa).
      3. Alias del JSON (legado, desalineado — solo si no hay nada mejor).
      4. Fallback "building_{gid}" si ninguna fuente produce un slug válido.

    NOTA: el campo "alias" del JSON estaba desalineado con los gids reales (datos viejos).
    Pasar `name` con el nombre inglés recién scrapeado garantiza alineación correcta.

    Ejemplos:
      gid=10, name="Warehouse"        → "building_10_warehouse"
      gid=13, name="Smithy"           → "building_13_smithy"
      gid=19, name="Barracks"         → "building_19_barracks"
      gid=27, name="Treasury"         → "building_27_treasury"
      gid=99, name="" (o None)        → "building_99" (fallback)
    """
    # Prioridad 1: nombre pasado como argumento
    if name:
        slug = _slugify(name)
        if slug:
            return f"building_{gid}_{slug}"

    # Prioridad 2 y 3: nombre del JSON ("en" preferido sobre "alias")
    if catalog_path is None:
        catalog_path = Path("core/i18n/catalog/base/buildings.json")
    try:
        with open(catalog_path, "r", encoding="utf-8") as f:
            catalog = json.load(f)
        entry = catalog.get(str(gid), {})
        # "en" recién actualizado es más fiable que alias (que puede estar desalineado)
        json_name = entry.get("en", "") or entry.get("alias", "")
        if json_name:
            slug = _slugify(json_name)
            if slug:
                return f"building_{gid}_{slug}"
    except Exception:
        pass
    return f"building_{gid}"


# ---------------------------------------------------------------------------
# Captura de icono (requiere browser)
# ---------------------------------------------------------------------------


def _get_alias_from_json(gid: int, catalog_path: Path | None = None) -> str:
    """
    Lee el alias del edificio desde buildings.json.
    Devuelve "" si el gid no existe o el campo alias no está.
    """
    if catalog_path is None:
        catalog_path = Path("core/i18n/catalog/base/buildings.json")
    try:
        with open(catalog_path, "r", encoding="utf-8") as f:
            catalog = json.load(f)
        return catalog.get(str(gid), {}).get("alias", "")
    except Exception:
        return ""


async def _capture_building_icon(
    browser,
    gid: int,
    icon_id: str,
    conn: "aiosqlite.Connection",
    icons_dir: Path = ICONS_DIR,
    tolerance: int = BG_FILL_TOLERANCE,
    max_retries: int = 3,
) -> None:
    """
    Captura el icono del edificio desde la página de detalle (#data_holder).

    Selector estructural: img.building.g{gid}
    Misma lógica que _capture_troop_icon en kirilloid_scraper.py.

    Estrategia de robustez ante "could not find position":
    -------------------------------------------------------
    El sprite `img.building.g{gid}` en la página de detalle a veces no tiene
    posición calculada aún cuando se intenta el screenshot (el SPA no ha
    terminado de renderizar el layout). En ese caso `screenshot_b64` lanza
    RuntimeError("could not find position").

    Solución elegida:
    1. Buscar primero el img dentro de `#data_holder` (contenedor del título/
       cabecera del detalle), donde el sprite suele tener layout estable antes
       que en el cuerpo de la tabla.
    2. Si no hay elemento en #data_holder, buscar en toda la página (fallback).
    3. Reintentar screenshot_b64 hasta `max_retries` veces con 0.25 s de espera
       entre intentos para dar tiempo al layout del SPA.
    4. Si tras todos los reintentos sigue fallando, relanzar la excepción para
       que el caller registre icon_id_stored=None y building_catalog.icon_id=None
       — nunca se escribe un PNG parcial ni se apunta a un fichero inexistente.

    Edificios sin sprite en T4.5 (gid 48 Spartans hospital, 49 Harbor,
    50 Barricade): su sprite no está en el sprite sheet → el elemento no
    aparece o screenshot_b64 falla siempre. Tras los reintentos se relanza
    la excepción con mensaje explicativo; el caller los omite limpiamente.

    Lanza RuntimeError si la captura falla tras todos los reintentos (no fatal
    en el caller — el script CLI lo captura como error no fatal y guarda
    icon_id=None en catalog).
    """
    import asyncio
    import base64
    from datetime import datetime, timezone

    from PIL import Image

    out_path = icons_dir / f"{icon_id}.png"

    # --- Localizar el elemento: primero en #data_holder, luego en toda la página ---
    # #data_holder contiene el encabezado del edificio (título + icono) y suele
    # tener layout completo antes que el cuerpo de la tabla de stats.
    element = await browser.query_selector(f"#data_holder img.building.g{gid}")
    if element is None:
        element = await browser.query_selector(f"img.building.g{gid}")
    if element is None:
        raise RuntimeError(
            f"img.building.g{gid} no encontrado en la página de detalle"
            f" (gid {gid} puede no existir en T4.5, p.ej. 48/49/50)"
        )

    # --- Reintentar screenshot_b64 hasta max_retries veces ---
    # El SPA puede tardar en calcular la posición del sprite tras la navegación.
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            # screenshot_b64 devuelve base64; format y scale según API real de zendriver
            png_b64 = await element.screenshot_b64(format="png", scale=1)
            last_exc = None
            break
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries:
                logger.debug(
                    "gid=%d: screenshot_b64 falló (intento %d/%d): %s — reintentando...",
                    gid, attempt, max_retries, exc,
                )
                await asyncio.sleep(0.25)
            else:
                logger.warning(
                    "gid=%d: screenshot_b64 falló tras %d intentos: %s"
                    " (si es gid 48/49/50, el sprite no existe en T4.5 — omitiendo)",
                    gid, max_retries, exc,
                )

    if last_exc is not None:
        raise RuntimeError(
            f"gid={gid}: no se pudo capturar screenshot tras {max_retries} intentos: {last_exc}"
        ) from last_exc

    png_bytes = base64.b64decode(png_b64)

    img = Image.open(BytesIO(png_bytes)).convert("RGBA")
    if img.width == 0 or img.height == 0:
        raise RuntimeError(
            f"icono building_{gid} con dimensiones 0x0 — EC-B-09"
        )

    img = _remove_background(img, tolerance=tolerance)

    icons_dir.mkdir(parents=True, exist_ok=True)
    img.save(str(out_path), "PNG")

    w, h = img.size
    size = out_path.stat().st_size

    await conn.execute(
        "INSERT OR REPLACE INTO icon_metadata VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            icon_id, "building", None, gid, None,
            f"assets/icons/{icon_id}.png", size, w, h,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    await conn.commit()
