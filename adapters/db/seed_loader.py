"""
Cargador de datos de juego desde ficheros JSON versionados (seeds).

Responsabilidad: poblar las tablas de datos de juego en un entorno recién
clonado que no tiene BD de producción ni ha ejecutado el scraper de kirilloid.

Flujo de arranque (llamado desde lifespan de main.py):
  1. Para cada tabla registrada en UPSERT_MAP:
     a. Comprobar si ya tiene filas → si sí, omitir esa tabla (datos ya presentes).
     b. Si no, buscar su fichero JSON en seeds_dir.
     c. Llamar al upsert correspondiente vía UPSERT_MAP.
     d. Loguear resultado por fichero.

Decisión por-tabla (2026-05-27):
  El gate original comprobaba solo troop_stats. Esto fallaba en estados parciales:
  si tropas estaban presentes pero edificios vacíos (p.ej. primer arranque tras
  añadir los seeds de edificios), los edificios no se cargaban nunca. El nuevo
  comportamiento comprueba cada tabla independientemente: si una tabla ya tiene
  datos, se omite; si está vacía y tiene fichero seed, se carga.

Resiliencia: un fichero malformado o una fila con campo PK faltante NO impiden
que el resto se cargue ni que la app arranque. Los errores se loguean y continúa.

Forward-compatibility: añadir una tabla nueva = añadir su entrada en UPSERT_MAP
y su fichero JSON en seeds/game_data/. Sin tocar el resto de este módulo.
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
    # Edificios — añadidos el 2026-05-27 tras completar el scraper kirilloid:
    "building_catalog": lambda adapter, obj: adapter.upsert_building_catalog(obj),
    "building_stats": lambda adapter, obj: adapter.upsert_building_stats(obj),
}


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------


async def load_if_empty(game_data_port: GameDataPort, seeds_dir: Path) -> None:
    """
    Carga los ficheros JSON de seeds_dir en la BD, tabla por tabla.

    Para cada tabla registrada en UPSERT_MAP:
    - Si ya tiene filas → omitir (no sobreescribe datos reales).
    - Si está vacía y hay fichero seed → cargar.

    Decisión por-tabla: permite estados parciales (p.ej. tropas presentes
    pero edificios vacíos) sin perder datos ni dejar tablas sin poblar.

    Idempotente: ejecutar dos veces produce el mismo resultado.
    Resiliente: errores por fichero o por fila se loguean y la carga continúa.

    Args:
        game_data_port: adaptador de datos de juego (GameDataSQLiteAdapter en producción).
        seeds_dir: directorio que contiene los ficheros *.json con los datos de seed.
    """
    if not seeds_dir.exists():
        logger.warning(
            "Directorio de seeds no encontrado: %s — tablas de juego quedarán vacías",
            seeds_dir,
        )
        return

    for table_name, upsert_fn in UPSERT_MAP.items():
        json_path = seeds_dir / f"{table_name}.json"

        # Gate por-tabla: si ya tiene datos, omitir independientemente de las demás.
        try:
            count = await game_data_port.count_rows(table_name)
        except Exception as exc:
            logger.warning(
                "Seed: no se pudo comprobar el conteo de %s: %s — omitiendo tabla",
                table_name,
                exc,
            )
            continue

        if count > 0:
            logger.info(
                "Seed: %s ya tiene %d filas — carga omitida",
                table_name,
                count,
            )
            continue

        if not json_path.exists():
            logger.warning(
                "Seed: fichero no encontrado: %s — tabla quedará vacía",
                json_path.name,
            )
            continue

        try:
            records = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error(
                "Error leyendo %s: %s — omitiendo fichero", json_path.name, exc
            )
            continue

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
