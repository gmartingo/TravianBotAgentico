"""
Script CLI — Carga de datos de tropas desde travian.kirilloid.ru.

Uso:
    python scripts/load_kirilloid.py

Descripción:
    Scrapa todas las tribus de Travian T4.5 (9 tribus) desde kirilloid.ru,
    extrayendo stats numéricos, nombres en ~25 idiomas e iconos PNG.

    El script es IDEMPOTENTE: re-ejecutarlo actualiza los datos sin duplicar
    ni borrar lo ya existente (UPSERT en SQLite, merge no-destructivo en JSON).

    Requiere Chrome instalado y disponible en la ruta esperada por driver.py.
    El perfil de Chrome se usa solo para kirilloid (nunca mezcla con perfiles de juego).

Salida:
    - assets/icons/*.png — iconos de tropas y stats
    - travian_bot.db — tablas troop_stats, troop_upgrades, icon_metadata
    - core/i18n/catalog/base/troops.json — nombres de tropas en ~25 idiomas (merge)

Anti-detección:
    - Reutiliza create_browser() de adapters/browser/driver.py (driver intacto).
    - Perfil separado: profiles/scraper_kirilloid (jamás mezcla con perfiles de juego).
    - kirilloid.ru es un sitio de TERCEROS sin anti-bot: aquí NO se simula
      comportamiento humano. No hay delays humanos entre peticiones porque no
      aportan indetectabilidad ante Travian (que corre con perfil separado) y
      solo ralentizan. La única espera es un sleep fijo corto tras cambiar el
      idioma, puramente funcional (esperar el re-render del SPA), NO humana.
    - Selectores siempre estructurales (clase/atributo/id), nunca por texto:
      kirilloid es multilenguaje (~25 idiomas).
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuración de logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("load_kirilloid")

# ---------------------------------------------------------------------------
# Bootstrap del path — permite ejecutar el script directamente
# (`python scripts/load_kirilloid.py`) además de como módulo
# (`python -m scripts.load_kirilloid`). Al ejecutarse directamente, Python
# pone scripts/ en sys.path en vez de la raíz del proyecto, así que el paquete
# `adapters`/`core` no se encontraría. Insertamos la raíz al principio.
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Importaciones del proyecto (lazy — para no fallar en import si no hay Chrome)
# ---------------------------------------------------------------------------

from adapters.browser.driver import create_browser
from adapters.db.database import get_connection
from adapters.db.game_data_sqlite_adapter import (
    GameDataSQLiteAdapter,
    _create_tables_if_not_exist,
)
from adapters.scraper.kirilloid_scraper import (
    ICONS_DIR,
    KIRILLOID_BASE_URL,
    KIRILLOID_LANGUAGES,
    SERVER_VERSION,
    TRIBES_CONFIG,
    UPGRADE_NEW_ICONS,
    _capture_stat_icons,
    _capture_troop_icon,
    _capture_upgrade_icons,
    _merge_troop_names,
    _parse_main_table,
    _parse_troop_names,
    _parse_upgrade_table,
    _wait_for_element,
)
from core.exceptions import KirilloidScraperError


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------


async def main() -> None:
    """Orquesta el scraping completo de kirilloid.ru."""

    # Crear directorio de iconos si no existe
    ICONS_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Iniciando scraping de kirilloid.ru — %d tribus, %d idiomas",
                len(TRIBES_CONFIG), len(KIRILLOID_LANGUAGES))

    browser = await create_browser("profiles/scraper_kirilloid")
    conn = await get_connection()
    await _create_tables_if_not_exist(conn)
    game_data_port = GameDataSQLiteAdapter(conn)

    errors: list[str] = []
    total_troops = 0
    total_upgrades = 0
    total_icons = 0

    for tribe_id, tribe_value, is_playable in TRIBES_CONFIG:
        logger.info("── Tribu %d/%d: %s", tribe_id, len(TRIBES_CONFIG), tribe_value)

        # Sin delay humano entre tribus: kirilloid es un sitio de terceros sin
        # anti-bot. browser.get() (carga completa de página) ya separa las
        # peticiones; 9 cargas no banean la IP. Simular humano aquí solo
        # ralentizaría sin aportar indetectabilidad ante Travian.

        # kirilloid lee sus parámetros de location.hash (#...), NO de query
        # string (?...). Con '?' todas las tribus cargarían la misma vista.
        # IMPORTANTE (correctitud, no anti-detección): navegar entre URLs que
        # solo difieren en el hash puede no forzar recarga en algunos motores
        # (el SPA debe reaccionar a 'hashchange'). browser.get() de zendriver
        # hace una navegación completa, por lo que cada llamada recarga la
        # página y re-evalúa el hash. El usuario debe verificar en su prueba
        # manual que cada tribu muestra tropas DISTINTAS.
        url = (
            f"{KIRILLOID_BASE_URL}"
            f"#s={SERVER_VERSION}&tribe={tribe_id}&s_lvl=0&t_lvl=1&u_lvl=0&unit=1"
        )

        try:
            page = await browser.get(url)
            await _wait_for_element(page, "#main.wire", timeout=30)
            # NOTA: NO se añade sleep de asentamiento aquí.
            #
            # browser.get() con solo cambio de hash puede dejar la tabla #main
            # mostrando la tribu ANTERIOR (el SPA de kirilloid re-renderiza en
            # respuesta al evento 'hashchange', que puede dispararse DESPUÉS de
            # que #main.wire ya estaba en el DOM de la tribu previa).
            #
            # La solución es ejecutar primero el bucle de idiomas (paso 1 abajo):
            # cada click en una bandera del #langbar dispara el handler JS completo
            # que re-lee tribe del hash y vuelca la tribu CORRECTA en la tabla.
            # Tras el primer click la tabla ya refleja la tribu N; ENTONCES se
            # parsean stats y se capturan iconos — que por tanto son correctos.
            #
            # Esta estrategia está validada por la evidencia empírica: los nombres
            # (leídos DESPUÉS de los clicks) siempre salieron correctos; los stats
            # (leídos ANTES de los clicks) eran los de la tribu N-1.
        except KirilloidScraperError as e:
            errors.append(f"timeout/{tribe_value}: {e}")
            logger.error("Timeout cargando tribu '%s' (%s) — continuando", tribe_value, url)
            continue
        except Exception as e:
            errors.append(f"load/{tribe_value}: {e}")
            logger.error("Error cargando tribu '%s': %s — continuando", tribe_value, e)
            continue

        # ------------------------------------------------------------------
        # 1. Leer nombres por idioma  ← PRIMERO, para forzar re-render a tribu N
        #
        # El click en la primera bandera del #langbar dispara el handler JS de
        # kirilloid que re-evalúa el hash completo (#tribe=N) y re-renderiza la
        # tabla #main con las tropas de la tribu N. A partir del primer click,
        # todos los accesos posteriores a la tabla (#main, #upg_table) trabajan
        # sobre datos actualizados de la tribu correcta.
        # ------------------------------------------------------------------
        nombres_por_idioma: dict[str, dict[int, str]] = {}
        for lang_code in KIRILLOID_LANGUAGES:
            try:
                lang_flag = await page.query_selector(f"#langbar img[alt='{lang_code}']")
                if lang_flag is None:
                    errors.append(f"names/{tribe_value}/{lang_code}: bandera no encontrada en #langbar")
                    logger.warning("  Idioma '%s' no disponible en kirilloid — omitiendo", lang_code)
                    continue
                await lang_flag.click()
                # Espera FIJA y corta para el re-render del SPA de kirilloid.
                # Aquí un sleep fijo es ACEPTABLE y deseable: kirilloid NO es
                # Travian y no tiene anti-bot, así que NO simulamos humano —
                # solo damos tiempo al DOM a reflejar el nuevo idioma antes de
                # leer los nombres. No hay un selector estructural fiable que
                # señale "idioma cambiado" sin conocer los nombres previos, por
                # lo que un sleep fijo mínimo es la opción correcta y rápida.
                await asyncio.sleep(0.15)  # render kirilloid (terceros), no humano
                nombres_por_idioma[lang_code] = await _parse_troop_names(page)
            except Exception as e:
                errors.append(f"names/{tribe_value}/{lang_code}: {e}")
                logger.warning("  Error leyendo idioma '%s': %s", lang_code, e)

        logger.info("  Idiomas procesados: %d/%d", len(nombres_por_idioma), len(KIRILLOID_LANGUAGES))

        # ------------------------------------------------------------------
        # 2. Leer stats base  ← DESPUÉS del bucle de idiomas (tabla ya en tribu N)
        # ------------------------------------------------------------------
        stats_por_ordinal: dict = {}
        try:
            stats_por_ordinal = await _parse_main_table(page, tribe_value, is_playable)
            logger.info("  Stats: %d tropas encontradas", len(stats_por_ordinal))
        except Exception as e:
            errors.append(f"stats/{tribe_value}: {e}")
            logger.error("  Error parseando stats de '%s': %s", tribe_value, e)

        # (El parseo de mejoras se realiza POR UNIDAD más abajo — paso 8)

        # ------------------------------------------------------------------
        # 4. Capturar iconos de stat (solo si alguno falta)
        #    DESPUÉS del bucle de idiomas → sprites de la tribu correcta
        # ------------------------------------------------------------------
        try:
            await _capture_stat_icons(page, conn)
        except Exception as e:
            errors.append(f"stat_icons/{tribe_value}: {e}")
            logger.error("  Error capturando iconos de stat: %s", e)

        # ------------------------------------------------------------------
        # 5. Capturar iconos de mejora (mientras falten los 3 nuevos)
        #    DESPUÉS del bucle de idiomas → tabla #upg_table en tribu correcta
        # ------------------------------------------------------------------
        missing_upgrade_icons = [
            ic for ic in UPGRADE_NEW_ICONS
            if not (ICONS_DIR / f"{ic}.png").exists()
        ]
        if missing_upgrade_icons:
            logger.info("  Intentando capturar iconos de mejora faltantes: %s", missing_upgrade_icons)
            try:
                await _capture_upgrade_icons(page, conn)
            except Exception as e:
                errors.append(f"upgrade_icons/{tribe_value}: {e}")
                logger.error("  Error capturando iconos de mejora: %s", e)

        # ------------------------------------------------------------------
        # 6. Capturar iconos de tropa
        #    DESPUÉS del bucle de idiomas → sprites de la tribu correcta
        # ------------------------------------------------------------------
        for ordinal, stats in stats_por_ordinal.items():
            icon_id = f"{tribe_value}_{ordinal}"
            try:
                await _capture_troop_icon(page, tribe_value, ordinal, icon_id, conn, tribe_id)
                stats["icon_id"] = icon_id
                total_icons += 1
            except Exception as e:
                errors.append(f"troop_icon/{icon_id}: {e}")
                logger.warning("  Error capturando icono '%s': %s", icon_id, e)
                stats["icon_id"] = None

        # ------------------------------------------------------------------
        # 7. Persistir stats en SQLite
        # ------------------------------------------------------------------
        for ordinal, stats in stats_por_ordinal.items():
            try:
                await game_data_port.upsert_troop_stats(stats)
                total_troops += 1
            except Exception as e:
                errors.append(f"upsert_stats/{tribe_value}/{ordinal}: {e}")
                logger.error("  Error guardando stats '%s_%d': %s", tribe_value, ordinal, e)

        # ------------------------------------------------------------------
        # 8. Mejoras por unidad — navegación individual a troops.php#...&unit=N
        #
        # La tabla #upg_table de kirilloid es POR UNIDAD: la URL
        #   troops.php#s=1.45&tribe=T&s_lvl=0&t_lvl=1&u_lvl=0&unit=N
        # muestra el #upg_table de la unidad N exclusivamente.
        #
        # Lección SPA: navegar solo el hash no garantiza re-render en todos
        # los navegadores. El patrón correcto es:
        #   browser.get("about:blank") → browser.get(url_con_unit)
        # Así cada unidad obtiene una carga fresca de la página.
        #
        # Los iconos de mejora (eye/def_s/point) también se capturan aquí,
        # ya que solo son visibles en el #upg_table de la unidad concreta.
        # ------------------------------------------------------------------
        logger.info("  Iniciando mejoras por unidad (%d ordinales)...", len(stats_por_ordinal))
        for ordinal in sorted(stats_por_ordinal.keys()):
            unit_url = (
                f"{KIRILLOID_BASE_URL}"
                f"#s={SERVER_VERSION}&tribe={tribe_id}"
                f"&s_lvl=0&t_lvl=1&u_lvl=0&unit={ordinal}"
            )
            try:
                # Carga fresca para que el SPA lea el nuevo hash &unit=N
                await browser.get("about:blank")
                unit_page = await browser.get(unit_url)
                # Esperamos #upg_table — si no existe, la unidad no tiene mejoras
                upg_exists = False
                try:
                    await _wait_for_element(unit_page, "#upg_table", timeout=15)
                    upg_exists = True
                except Exception:
                    pass  # sin #upg_table → 0 mejoras, OK (EC-03)

                if upg_exists:
                    # Parsear mejoras
                    upgrades = await _parse_upgrade_table(unit_page, tribe_value, ordinal)
                    for upgrade in upgrades:
                        try:
                            await game_data_port.upsert_troop_upgrade(upgrade)
                            total_upgrades += 1
                        except Exception as e:
                            errors.append(f"upsert_upgrade/{tribe_value}/{ordinal}: {e}")
                            logger.error(
                                "  Error guardando mejora '%s_%d' nivel %d: %s",
                                tribe_value, ordinal, upgrade.get("level", "?"), e
                            )

                    # Capturar iconos de mejora nuevos (eye/def_s/point) si faltan
                    missing_upgrade_icons = [
                        ic for ic in UPGRADE_NEW_ICONS
                        if not (ICONS_DIR / f"{ic}.png").exists()
                    ]
                    if missing_upgrade_icons:
                        try:
                            await _capture_upgrade_icons(unit_page, conn)
                        except Exception as e:
                            errors.append(f"upgrade_icons/{tribe_value}/{ordinal}: {e}")
                            logger.error(
                                "  Error capturando iconos de mejora en %s_%d: %s",
                                tribe_value, ordinal, e
                            )

            except Exception as e:
                errors.append(f"upgrades_iter/{tribe_value}/{ordinal}: {e}")
                logger.error(
                    "  Error en iteración de mejoras '%s_%d': %s", tribe_value, ordinal, e
                )

        # ------------------------------------------------------------------
        # 9. Merge de nombres en troops.json  ← nombres capturados en paso 1
        # ------------------------------------------------------------------
        if nombres_por_idioma and stats_por_ordinal:
            try:
                _merge_troop_names(
                    tribe_value,
                    nombres_por_idioma,
                    list(stats_por_ordinal.keys()),
                )
                logger.info("  Nombres mergeados en troops.json")
            except Exception as e:
                errors.append(f"merge_json/{tribe_value}: {e}")
                logger.error("  Error mergeando nombres de '%s': %s", tribe_value, e)

    # ------------------------------------------------------------------
    # Cierre
    # ------------------------------------------------------------------
    try:
        await browser.stop()
    except Exception:
        pass

    try:
        await conn.close()
    except Exception:
        pass

    # ------------------------------------------------------------------
    # Resumen final
    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    print(f"SCRAPING COMPLETADO")
    print(f"  Tropas guardadas:     {total_troops}")
    print(f"  Filas de mejora:      {total_upgrades}")
    print(f"  Iconos capturados:    {total_icons}")
    print(f"  Iconos en disco:      {len(list(ICONS_DIR.glob('*.png'))) if ICONS_DIR.exists() else 0}")
    if errors:
        print(f"  ERRORES ({len(errors)}):")
        for err in errors:
            print(f"    - {err}")
    else:
        print("  Sin errores.")
    print("=" * 60)

    return len(errors)


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    n_errors = asyncio.run(main())
    sys.exit(1 if n_errors else 0)
