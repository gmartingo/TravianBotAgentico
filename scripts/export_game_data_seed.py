"""
Script CLI — Exporta datos de juego de la BD SQLite a ficheros JSON versionados.

Uso:
    python scripts/export_game_data_seed.py

Descripción:
    Lee las tablas troop_stats, troop_upgrades e icon_metadata de travian_bot.db
    y escribe seeds/game_data/{troop_stats,troop_upgrades,icon_metadata}.json.

    Solo necesita ejecutarse cuando el desarrollador ha hecho un nuevo scraping y
    quiere versionar los datos actualizados en git. Los clones frescos leen estos
    ficheros al arrancar (via seed_loader.load_if_empty).

Seguridad:
    - Solo lee las tablas de datos de juego: troop_stats, troop_upgrades, icon_metadata.
    - Las tablas accounts y worlds NUNCA se tocan ni se exportan.
    - Las queries SQL usan columnas explícitas (sin SELECT *).
    - scraped_at se omite del JSON; el loader lo rellena con datetime.now(UTC) al cargar.

Atomicidad:
    Cada fichero se escribe primero en un .tmp y se renombra al final.
    Si el proceso se interrumpe, no quedan ficheros parciales en disco.

Determinismo:
    Las filas se ordenan por su PK antes de escribir, para git diff limpio y legible.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

# Añadir la raíz del proyecto al path (igual que load_kirilloid.py)
# para que las importaciones de adapters/ y core/ funcionen desde cualquier CWD.
_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from adapters.db.database import get_connection  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Directorio de salida
# ---------------------------------------------------------------------------

SEEDS_DIR = _PROJECT_ROOT / "seeds" / "game_data"

# ---------------------------------------------------------------------------
# Configuración de tablas: query + columnas (sin scraped_at)
# ---------------------------------------------------------------------------

TABLES_CONFIG: dict[str, dict] = {
    "troop_stats": {
        "query": (
            "SELECT server_version, tribe, ordinal, is_playable, attack, "
            "def_infantry, def_cavalry, speed, carry, cost_wood, cost_clay, "
            "cost_iron, cost_crop, cost_sum, upkeep, train_time_s, icon_id "
            "FROM troop_stats "
            "ORDER BY server_version, tribe, ordinal"
        ),
        "columns": [
            "server_version", "tribe", "ordinal", "is_playable", "attack",
            "def_infantry", "def_cavalry", "speed", "carry", "cost_wood",
            "cost_clay", "cost_iron", "cost_crop", "cost_sum", "upkeep",
            "train_time_s", "icon_id",
        ],
    },
    "troop_upgrades": {
        "query": (
            "SELECT server_version, tribe, ordinal, level, stat_name, stat_value, "
            "cost_wood, cost_clay, cost_iron, cost_crop, cost_sum, upgrade_time_s "
            "FROM troop_upgrades "
            "ORDER BY server_version, tribe, ordinal, level, stat_name"
        ),
        "columns": [
            "server_version", "tribe", "ordinal", "level", "stat_name",
            "stat_value", "cost_wood", "cost_clay", "cost_iron", "cost_crop",
            "cost_sum", "upgrade_time_s",
        ],
    },
    "icon_metadata": {
        "query": (
            "SELECT icon_id, icon_type, tribe, ordinal, stat_name, "
            "file_path, file_size_bytes, width_px, height_px "
            "FROM icon_metadata "
            "ORDER BY icon_id"
        ),
        "columns": [
            "icon_id", "icon_type", "tribe", "ordinal", "stat_name",
            "file_path", "file_size_bytes", "width_px", "height_px",
        ],
    },
}


# ---------------------------------------------------------------------------
# Lógica de exportación
# ---------------------------------------------------------------------------


async def export() -> None:
    """
    Lee las tablas en scope de travian_bot.db y escribe los ficheros JSON en SEEDS_DIR.

    Tablas fuera de scope (accounts, worlds, building_catalog, building_stats)
    nunca se tocan. Las tablas del scope con 0 filas se omiten (no se crea fichero vacío).
    """
    SEEDS_DIR.mkdir(parents=True, exist_ok=True)
    conn = await get_connection()

    try:
        for table_name, config in TABLES_CONFIG.items():
            async with conn.execute(config["query"]) as cursor:
                raw_rows = await cursor.fetchall()

            count = len(raw_rows)

            if count == 0:
                logger.info("%s: 0 filas — omitida del seed (no se crea fichero JSON)", table_name)
                continue

            # Convertir filas a lista de dicts (usando columnas explícitas del config)
            records = [
                dict(zip(config["columns"], row))
                for row in raw_rows
            ]

            # Escritura atómica: escribir en .tmp y renombrar (EC-07)
            tmp_path = SEEDS_DIR / f"{table_name}.json.tmp"
            out_path = SEEDS_DIR / f"{table_name}.json"

            tmp_path.write_text(
                json.dumps(records, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp_path.rename(out_path)  # operación atómica en el mismo sistema de ficheros

            logger.info("%s: %d filas exportadas → %s", table_name, count, out_path)
    finally:
        await conn.close()


def main() -> None:
    asyncio.run(export())


if __name__ == "__main__":
    main()
