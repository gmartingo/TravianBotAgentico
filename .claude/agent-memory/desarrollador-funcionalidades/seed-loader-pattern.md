---
name: seed-loader-pattern
description: Patrón seed de datos de juego (tropas + iconos + edificios): export JSON + load_if_empty por-tabla; UPSERT_MAP; count_rows() genérico
metadata:
  type: project
---

El mecanismo de seed (feature seed-datos-juego-tropas, ampliado 2026-05-27) funciona así:

- `scripts/export_game_data_seed.py`: script CLI async que lee `travian_bot.db` y escribe
  `seeds/game_data/{troop_stats,troop_upgrades,icon_metadata,building_catalog,building_stats}.json`.
  Escritura atómica `.tmp`→rename. Columnas explícitas, sin `scraped_at`, ordenado por PK.
  Tablas vacías se omiten (no se crea fichero JSON vacío).

- `adapters/db/seed_loader.py`: `load_if_empty(game_data_port, seeds_dir)` — gate **por-tabla**:
  para cada tabla en `UPSERT_MAP`, llama a `count_rows(table_name)`; si ya tiene filas, omite
  esa tabla; si está vacía, busca su JSON y carga. Permite estados parciales (tropas con datos,
  edificios vacíos → solo carga edificios). Elimina `scraped_at` del JSON antes del upsert (EC-08).

- Enganche en `adapters/api/main.py` lifespan: DESPUÉS de `ensure_tables()`, ANTES de
  `app.state.game_data_port = ...`.

- `count_rows(table_name: str) -> int` añadido como abstracto en `GameDataPort` e implementado en
  `GameDataSQLiteAdapter` con allowlist `_ALLOWED_COUNT_TABLES` (rechaza `accounts`/`worlds` con
  ValueError). `count_troop_stats()` se mantiene intacto por retrocompatibilidad.

- JSON versionados en `seeds/game_data/` (no en `.gitignore`; la regla `*.db` no alcanza a JSON).

- Conteos reales en la BD del dev: troop_stats=90, troop_upgrades=1780, icon_metadata=140,
  building_catalog=50, building_stats=1003.

**Why:** clon fresco (Pi, VM, Mac nuevo) necesita datos sin ejecutar el scraper. El gate por-tabla
corrige el bug "estado parcial" donde tropas presentes bloqueaban la carga de edificios.

**How to apply:** añadir una tabla nueva al seed = añadir su fichero JSON en `seeds/game_data/`
y una entrada en `UPSERT_MAP` en `seed_loader.py`. El método `count_rows()` ya la soporta si
se añade a `_ALLOWED_COUNT_TABLES`. [[game-data-port-pattern]]
