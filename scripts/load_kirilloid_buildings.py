"""
Script CLI — Carga de datos de edificios desde travian.kirilloid.ru.

Uso:
    python scripts/load_kirilloid_buildings.py

Descripción:
    Scrapa todos los edificios de Travian T4.5 desde kirilloid.ru (build.php),
    extrayendo stats numéricos por nivel, nombres en ~25 idiomas e iconos PNG.

    El script es IDEMPOTENTE: re-ejecutarlo actualiza los datos sin duplicar
    ni borrar lo ya existente (UPSERT en SQLite, merge sobrescribe en JSON).

    Requiere Chrome instalado y disponible en la ruta esperada por driver.py.
    El perfil de Chrome se usa solo para kirilloid (nunca mezcla con perfiles de juego).

Salida:
    - assets/icons/building_*.png  — iconos de edificios
    - travian_bot.db               — tablas building_stats, building_catalog, icon_metadata
    - core/i18n/catalog/base/buildings.json — nombres en ~25 idiomas (merge sobrescribe)

Anti-detección:
    - Reutiliza create_browser() de adapters/browser/driver.py (driver intacto).
    - Perfil separado: profiles/scraper_kirilloid (jamás mezcla con perfiles de juego).
    - kirilloid.ru es un sitio de TERCEROS sin anti-bot: aquí NO se simula
      comportamiento humano. No hay delays humanos entre peticiones porque no
      aportan indetectabilidad ante Travian y solo ralentizan.
    - Sleep funcional 0.15 s tras click de idioma (espera re-render del SPA).
    - Sleep funcional 0.3 s entre gids (cortesía al servidor comunitario).
    - Selectores siempre estructurales (clase/atributo/data-gid), nunca por texto:
      kirilloid es multilenguaje (~25 idiomas).
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuración de logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("load_kirilloid_buildings")

# ---------------------------------------------------------------------------
# Bootstrap del path — permite ejecutar directamente o como módulo
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Importaciones del proyecto
# ---------------------------------------------------------------------------

from adapters.browser.driver import create_browser
from adapters.db.database import get_connection
from adapters.db.game_data_sqlite_adapter import _create_tables_if_not_exist
from adapters.scraper.kirilloid_buildings_scraper import (
    BG_FILL_TOLERANCE,
    CATEGORY_BY_H3,
    ICONS_DIR,
    KIRILLOID_BUILD_URL,
    KIRILLOID_LANGUAGES,
    SERVER_VERSION,
    _capture_building_icon,
    _get_alias_from_json,
    _make_icon_id,
    _merge_building_names,
    _parse_building_detail,
    _parse_building_index,
    _parse_building_names_from_index,
)
from adapters.scraper.utils import _wait_for_element
from core.exceptions import KirilloidScraperError


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------


async def main() -> None:
    """Orquesta el scraping completo de edificios desde kirilloid.ru/build.php."""

    ICONS_DIR.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Iniciando scraping de edificios kirilloid.ru — server_version=%s, %d idiomas",
        SERVER_VERSION, len(KIRILLOID_LANGUAGES),
    )

    browser = await create_browser("profiles/scraper_kirilloid")
    conn = await get_connection()
    await _create_tables_if_not_exist(conn)

    errors: list[str] = []

    # --- Paso 2: cargar página índice en idioma base 'es' ---
    index_url = f"{KIRILLOID_BUILD_URL}#mb=1&s={SERVER_VERSION}"
    logger.info("Cargando índice: %s", index_url)
    await browser.get("about:blank")
    page = await browser.get(index_url)
    try:
        await _wait_for_element(page, "#build_list", timeout=30)
    except KirilloidScraperError as e:
        logger.error("ERROR FATAL: no cargó el índice de edificios: %s", e)
        await browser.stop()
        return

    # --- Paso 3: parsear índice en idioma 'es' ---
    gids_by_category: list[tuple[int, str, str]] = []
    try:
        gids_by_category = await _parse_building_index(page)
        logger.info("Índice cargado: %d edificios", len(gids_by_category))
    except Exception as e:
        logger.error("ERROR FATAL: no se pudo parsear el índice: %s", e)
        await browser.stop()
        return

    # --- Paso 4: leer nombres por idioma desde la página índice ---
    nombres_por_idioma: dict[str, dict[int, str]] = {
        "es": {gid: n for gid, _, n in gids_by_category}
    }

    for lang in KIRILLOID_LANGUAGES:
        if lang == "es":
            continue
        try:
            flag = await page.query_selector(f"#langbar img[alt='{lang}']")
            if flag is None:
                errors.append(f"names/index/{lang}: bandera no encontrada")
                logger.warning("Bandera '%s' no encontrada en #langbar — EC-B-04", lang)
                continue
            await flag.click()
            await asyncio.sleep(0.15)  # espera funcional del re-render SPA (RN-B-14)
            nombres_lang = await _parse_building_names_from_index(page)
            nombres_por_idioma[lang] = nombres_lang
            logger.debug("Nombres '%s': %d edificios", lang, len(nombres_lang))
        except Exception as e:
            errors.append(f"names/index/{lang}: {e}")
            logger.warning("Error leyendo nombres en idioma '%s': %s", lang, e)

    # --- Paso 4b: merge INMEDIATO de nombres en buildings.json ---
    # Se hace ANTES del bucle de gids para que _make_icon_id(gid) encuentre el 'en'
    # actualizado en el JSON. Así el icon_id se genera desde el 'en' estable del JSON
    # (no del run flaky), garantizando que gid=10 → building_10_warehouse SIEMPRE.
    logger.info("Mergeando nombres en buildings.json ANTES del bucle de gids (%d idiomas)...", len(nombres_por_idioma))
    try:
        _merge_building_names(nombres_por_idioma)
        logger.info("Merge previo completado — buildings.json actualizado con nombres frescos.")
    except Exception as e:
        errors.append(f"merge_previo/json: {e}")
        logger.error("Error en merge previo de buildings.json: %s — los icon_id usarán el JSON previo", e)

    # Resetear idioma a 'es' antes de leer los detalles: el bucle de idiomas dejó
    # la página en el último idioma (p.ej. 'uk'), y kirilloid PERSISTE el idioma.
    # Si el detalle se lee en 'uk', la cabecera "PC" no se reconoce (culture_points
    # queda None) y el effect_label sale en ucraniano. Forzamos 'es' (RN-B: detalle en es).
    try:
        es_flag = await page.query_selector("#langbar img[alt='es']")
        if es_flag is not None:
            await es_flag.click()
            await asyncio.sleep(0.15)  # espera funcional del re-render SPA
    except Exception as e:
        logger.warning("No se pudo resetear idioma a 'es' antes de los detalles: %s", e)

    # --- Paso 5: por cada gid, cargar detalle y persistir ---
    for gid, category, nombre_es in gids_by_category:
        detail_url = f"{KIRILLOID_BUILD_URL}#b={gid}&mb=1&s={SERVER_VERSION}"
        logger.info("Procesando gid=%d (%s) — %s", gid, category, nombre_es)

        # Lección SPA kirilloid (RN-B-13): about:blank → get(detalle)
        try:
            await browser.get("about:blank")
            page = await browser.get(detail_url)
            await _wait_for_element(page, "#data.wire", timeout=30)
        except KirilloidScraperError as e:
            errors.append(f"detail/gid={gid}: no cargó: {e}")
            logger.warning("gid=%d no cargó la tabla de detalle — EC-B-03", gid)
            continue
        except Exception as e:
            errors.append(f"detail/gid={gid}: error de navegación: {e}")
            logger.warning("gid=%d error de navegación: %s", gid, e)
            continue

        # Leer descripción del edificio
        description = ""
        try:
            desc_el = await page.query_selector("#data_holder-desc")
            if desc_el is not None:
                description = desc_el.text.strip()
        except Exception as e:
            errors.append(f"description/gid={gid}: {e}")

        # Leer alias desde buildings.json (el alias ya existe en el JSON base)
        alias = _get_alias_from_json(gid) or f"building_{gid}"

        # Parsear tabla de detalle
        levels_data: list[dict] = []
        effect_label = ""
        try:
            levels_data, effect_label = await _parse_building_detail(page)
            logger.debug("gid=%d: %d niveles, effect_label='%s'", gid, len(levels_data), effect_label)
        except Exception as e:
            errors.append(f"detail_parse/gid={gid}: {e}")
            logger.warning("gid=%d error parseando detalle: %s", gid, e)

        # Capturar icono — icon_id descriptivo: "building_{gid}_{slug}"
        # El merge ya corrió ANTES de este bucle (paso 4b), así que buildings.json
        # tiene los nombres 'en' frescos del run actual. _make_icon_id(gid) los lee
        # directamente del JSON → icon_id siempre consistente e independiente de si
        # el click de bandera 'en' re-renderizó a tiempo en este run.
        icon_id = _make_icon_id(gid)
        icon_id_stored: str | None = None
        try:
            await _capture_building_icon(page, gid, icon_id, conn)
            icon_id_stored = icon_id
            logger.debug("gid=%d: icono capturado", gid)
        except Exception as e:
            errors.append(f"icon/gid={gid}: {e}")
            logger.warning("gid=%d icono no capturado (error no fatal): %s", gid, e)

        # Persistir building_catalog
        now = datetime.now(timezone.utc).isoformat()
        try:
            await conn.execute(
                """
                INSERT OR REPLACE INTO building_catalog
                (server_version, gid, alias, category, description, icon_id, scraped_at)
                VALUES (?,?,?,?,?,?,?)
                """,
                (SERVER_VERSION, gid, alias, category, description, icon_id_stored, now),
            )
        except Exception as e:
            errors.append(f"catalog_upsert/gid={gid}: {e}")
            logger.warning("gid=%d error persistiendo catalog: %s", gid, e)

        # Persistir building_stats (un UPSERT por nivel)
        for level_row in levels_data:
            try:
                await conn.execute(
                    """
                    INSERT OR REPLACE INTO building_stats
                    (server_version, gid, level, cost_wood, cost_clay, cost_iron,
                     cost_crop, cost_sum, upkeep, culture_points, build_time_s,
                     effect_value, effect_label, scraped_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        SERVER_VERSION, gid, level_row.get("level"),
                        level_row.get("cost_wood"),
                        level_row.get("cost_clay"),
                        level_row.get("cost_iron"),
                        level_row.get("cost_crop"),
                        level_row.get("cost_sum"),
                        level_row.get("upkeep"),
                        level_row.get("culture_points"),
                        level_row.get("build_time_s"),
                        level_row.get("effect_value"),
                        effect_label if level_row.get("effect_value") is not None else "",
                        now,
                    ),
                )
            except Exception as e:
                errors.append(f"stats_upsert/gid={gid}/level={level_row.get('level')}: {e}")
                logger.warning("gid=%d nivel=%s error upsert: %s", gid, level_row.get("level"), e)

        await conn.commit()
        await asyncio.sleep(0.3)  # cortesía entre gids (funcional, no humano) RN-B-13

    await browser.stop()
    await conn.close()

    # --- Resumen final ---
    total_gids = len(gids_by_category)
    if errors:
        print(f"\nSCRAPING COMPLETADO CON {len(errors)} ERRORES (total gids: {total_gids}):")
        for err in errors:
            print(f"  - {err}")
    else:
        print(f"\nSCRAPING COMPLETADO SIN ERRORES. Edificios procesados: {total_gids}.")


if __name__ == "__main__":
    asyncio.run(main())
