"""
Carga mínima de building_catalog desde los iconos de assets/icons/.

Los PNG de edificio están en assets/icons/ con el patrón `building_{gid}_{alias}.png`
(el gid del juego va en el nombre del fichero — fuente fiable, a diferencia del campo
`alias` de buildings.json que está desalineado a partir de gid 13).

Este loader rellena building_catalog con {gid, alias, icon_id} para que el flujo ya
cableado (get_building_catalog(gid).icon_id → /static/icons/{icon_id}.png) sirva el
icono del edificio en /game/troops/training y donde haya gid.

Es idempotente (UPSERT). Forward-compatible: cuando el scraper de kirilloid-edificios
cargue building_catalog con stats/categoría/descripción completos, los upserts añaden
esos campos sin romper esto.

Uso:  python scripts/load_building_icons.py
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

from adapters.db.database import get_connection
from adapters.db.game_data_sqlite_adapter import GameDataSQLiteAdapter

_ASSETS = Path(__file__).resolve().parent.parent / "assets" / "icons"
_PATTERN = re.compile(r"^building_(\d+)_(.+)\.png$")
_SERVER_VERSION = "1.45"


async def main() -> None:
    conn = await get_connection()
    adapter = GameDataSQLiteAdapter(conn)
    await adapter.ensure_tables()

    cargados = 0
    for png in sorted(_ASSETS.glob("building_*.png")):
        m = _PATTERN.match(png.name)
        if not m:
            continue
        gid = int(m.group(1))
        alias = m.group(2)
        icon_id = png.stem  # building_{gid}_{alias}
        await adapter.upsert_building_catalog({
            "server_version": _SERVER_VERSION,
            "gid": gid,
            "alias": alias,
            "category": None,
            "description": None,
            "icon_id": icon_id,
        })
        cargados += 1

    await conn.close()
    print(f"building_catalog poblado: {cargados} edificios desde assets/icons/")


if __name__ == "__main__":
    asyncio.run(main())
