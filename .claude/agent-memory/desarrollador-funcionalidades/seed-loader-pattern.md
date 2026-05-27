---
name: seed-loader-pattern
description: Patrón seed de datos de juego: export JSON + load_if_empty en lifespan; UPSERT_MAP extensible; count_troop_stats como gate
metadata:
  type: project
---

El mecanismo de seed (feature seed-datos-juego-tropas) funciona así:

- `scripts/export_game_data_seed.py`: script CLI async que lee `travian_bot.db` y escribe `seeds/game_data/{troop_stats,troop_upgrades,icon_metadata}.json`. Escritura atómica `.tmp`→rename. Columnas explícitas, sin `scraped_at`, ordenado por PK.
- `adapters/db/seed_loader.py`: `load_if_empty(game_data_port, seeds_dir)` — gate por `count_troop_stats() > 0`, `UPSERT_MAP` extensible (comentarios para edificios futuros). Elimina `scraped_at` del JSON antes del upsert (EC-08).
- Enganche en `adapters/api/main.py` lifespan: DESPUÉS de `ensure_tables()`, ANTES de `app.state.game_data_port = ...`.
- `count_troop_stats()` añadido como método abstracto en `GameDataPort` e implementado en `GameDataSQLiteAdapter`.
- JSON versionados en `seeds/game_data/` (no en `.gitignore`; la regla `*.db` no alcanza a JSON).

**Why:** clon fresco (Pi, VM, Mac nuevo) necesita datos de tropas sin ejecutar el scraper. Los JSON se versionan en git para distribuirlos.

**How to apply:** cuando se implemente el seed de edificios (building_catalog/building_stats), solo añadir sus ficheros JSON en `seeds/game_data/` y dos entradas en `UPSERT_MAP` en `seed_loader.py`. El gate sigue siendo `count_troop_stats()` (si troop_stats está vacío, se asume entorno sin datos). [[game-data-port-pattern]]
