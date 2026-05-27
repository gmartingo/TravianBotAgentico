"""
Cargador de datos de juego desde ficheros JSON versionados (seeds).

Responsabilidad: poblar las tablas de datos de juego (troop_stats, troop_upgrades,
icon_metadata) en un entorno recién clonado que no tiene BD de producción ni ha
ejecutado el scraper de kirilloid.

Flujo de arranque (llamado desde lifespan de main.py):
  1. Comprobar si troop_stats tiene filas → si sí, retornar (datos ya presentes).
  2. Si no, buscar ficheros *.json en seeds_dir.
  3. Por cada fichero, llamar al upsert correspondiente vía UPSERT_MAP.
  4. Loguear resultado por fichero.

Resiliencia: un fichero malformado o una fila con campo PK faltante NO impiden
que el resto se cargue ni que la app arranque. Los errores se loguean y continúa.

Forward-compatibility: añadir edificios al futuro = solo añadir
  "building_catalog": lambda adapter, obj: adapter.upsert_building_catalog(obj),
  "building_stats":   lambda adapter, obj: adapter.upsert_building_stats(obj),
en UPSERT_MAP y sus ficheros JSON en seeds/game_data/. Sin tocar este módulo.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from core.ports.game_data_port import GameDataPort

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mapa extensible: nombre de tabla → función de upsert
# ---------------------------------------------------------------------------

UPSERT_MAP: dict[str, object] = {
    "troop_stats": lambda adapter, obj: adapter.upsert_troop_stats(obj),
    "troop_upgrades": lambda adapter, obj: adapter.upsert_troop_upgrade(obj),
    "icon_metadata": lambda adapter, obj: adapter.upsert_icon_metadata(obj),
    # Extensión futura sin tocar este código:
    # "building_catalog": lambda adapter, obj: adapter.upsert_building_catalog(obj),
    # "building_stats":   lambda adapter, obj: adapter.upsert_building_stats(obj),
}


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------


async def load_if_empty(game_data_port: GameDataPort, seeds_dir: Path) -> None:
    """
    Carga los ficheros JSON de seeds_dir en la BD si troop_stats está vacío.

    Idempotente: si troop_stats ya tiene filas, retorna inmediatamente sin hacer nada.
    Resiliente: errores por fichero o por fila se loguean y la carga continúa.

    Args:
        game_data_port: adaptador de datos de juego (GameDataSQLiteAdapter en producción).
        seeds_dir: directorio que contiene los ficheros *.json con los datos de seed.
    """
    count = await game_data_port.count_troop_stats()
    if count > 0:
        logger.info("Seed: troop_stats ya tiene %d filas — carga omitida", count)
        return

    if not seeds_dir.exists():
        logger.warning(
            "Directorio de seeds no encontrado: %s — tablas de juego quedarán vacías",
            seeds_dir,
        )
        return

    json_files = sorted(seeds_dir.glob("*.json"))
    if not json_files:
        logger.warning(
            "No hay ficheros JSON en %s — tablas de juego quedarán vacías",
            seeds_dir,
        )
        return

    for json_path in json_files:
        table_name = json_path.stem  # "troop_stats", "troop_upgrades", etc.

        if table_name not in UPSERT_MAP:
            logger.warning("Tabla desconocida en seeds: %s — omitiendo", table_name)
            continue

        try:
            records = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error(
                "Error leyendo %s: %s — omitiendo fichero", json_path.name, exc
            )
            continue

        upsert_fn = UPSERT_MAP[table_name]
        loaded = 0
        for i, obj in enumerate(records):
            # Eliminar scraped_at si viene en el JSON (EC-08): el upsert siempre
            # rellena scraped_at con datetime.now(UTC), ignorando cualquier valor del JSON.
            obj_clean = {k: v for k, v in obj.items() if k != "scraped_at"}
            try:
                await upsert_fn(game_data_port, obj_clean)
                loaded += 1
            except Exception as exc:
                logger.warning(
                    "Fila %d de %s omitida: %s", i, table_name, exc
                )

        logger.info(
            "Seed: %d/%d filas cargadas desde %s",
            loaded,
            len(records),
            json_path.name,
        )
