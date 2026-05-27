---
name: deferred-game-data-layer
description: La capa de datos de juego (niveles/costes/stats de edificios y tropas) YA está implementada vía scraper de kirilloid y versionada como seed JSON con autocarga
metadata: 
  node_type: memory
  type: project
  originSessionId: 86a504b6-afa5-4d74-af61-2f20bcc1e568
---

**ESTADO ACTUAL (2026-05-27): el aplazamiento se cerró.** La capa de datos de juego ya existe: el scraper de kirilloid (`adapters/scraper/kirilloid_scraper.py` tropas, `kirilloid_buildings_scraper.py` edificios; lanzados con `scripts/load_kirilloid.py` y `scripts/load_kirilloid_buildings.py`) puebla `travian_bot.db` con `troop_stats` (90), `troop_upgrades` (1780), `icon_metadata` (140), `building_catalog` (50), `building_stats` (1003). Los nombres traducidos viven en `core/i18n/catalog/base/{troops,buildings}.json` (versionados). Ver [[kirilloid-scraper-gotchas]] y [[third-party-scraper-no-antidetection]].

**Versionado de esos datos (clave):** `travian_bot.db` está y SEGUIRÁ gitignored porque mezcla `accounts` (email lobby + contraseña cifrada Fernet) y `worlds` con los datos de juego — subir el .db filtraría las credenciales. El vehículo de migración a git y a todos los entornos (Pi, VM, otra PC) es un **seed JSON**: `seeds/game_data/*.json` (un fichero por tabla, sin `scraped_at`). El loader `adapters/db/seed_loader.py` (`load_if_empty`, gate POR-TABLA vía `count_rows()` con allowlist que rechaza accounts/worlds) carga cada tabla en el `lifespan` de `adapters/api/main.py` solo si está vacía — nunca pisa datos reales. Spec: `docs/specs/seed-datos-juego-tropas.md`. Implementado en la rama `chore/version-game-icons` (también versiona los 151 iconos PNG de `assets/icons/`), aún SIN fusionar a `develop` a fecha 2026-05-27.

**How to apply:** (1) Para regenerar el seed tras re-scrapear (nueva versión kirilloid / otro server): `python scripts/export_game_data_seed.py` → reescribe los JSON; el loader los recoge solo. (2) Iconos de gid 48/49/50 (Spartans hospital, Harbor, Barricade) no existen en T4.5: su sprite falla pero los stats sí se guardan — error no fatal esperado. (3) `/catalog/*` es la capa ligera de solo-nombres (TranslationPort); los datos pesados (stats/costes) salen también por `/catalog/buildings`, `/catalog/troops/{tribe}` y `/catalog/icons` leyendo del GameDataPort — NO meter datos de juego en endpoints nuevos sin consultar al usuario.

**Why:** El usuario fue explícito en que los datos de juego son "core del programa" y deben viajar a git y a todos los entornos, pero la BD viva no puede subir por los secretos. El seed JSON da ese resultado (datos en cada entorno) sin filtrar credenciales.
