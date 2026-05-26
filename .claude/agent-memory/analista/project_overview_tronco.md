---
name: project-overview-tronco
description: Decisiones cerradas del tronco compartido para lectura de overview de Travian (port, caché, fixture adapter, village map, utils parseo)
metadata:
  type: project
---

Tronco común para los 4 endpoints de lectura del estado dinámico del jugador.
Spec: `docs/specs/lectura-overview-tronco-comun.md` (estado: ready-for-impl, 2026-05-25)

**Decisiones clave:**
- `OverviewHtmlSourcePort` en `core/ports/` con `get_page_html(world_id, OverviewPage, village_game_id)` e `invalidate_cache(world_id)`.
- `OverviewPage` enum con 5 valores: OVERVIEW_ALL_VILLAGES, OVERVIEW_VILLAGE, RESOURCES_VILLAGE, CULTURE_POINTS_VILLAGE, TROOPS_VILLAGE.
- `LiveOverviewAdapter` en `adapters/browser/`: recibe browser vía callable inyectado (`get_browser: Callable[[int], Browser | None]`). Hoy lambda → None. Se cablea al SessionRegistry cuando exista. TTL en memoria, double-checked locking asyncio.
- `FixtureOverviewAdapter` en `adapters/browser/`: devuelve HTML desde `tests/fixtures/overview/`. Plenamente funcional hoy, base de todos los tests de los 4 bloques.
- `VillageInfo(game_id, name, x, y)` frozen dataclass en `core/use_cases/village_map.py`.
- `VillageOverviewParser.extract_villages` tiene `NotImplementedError` hasta recibir fixture HTML real del usuario.
- `_parse_int`, `_parse_int_or_none`, `_parse_time` se mueven de `adapters/scraper/kirilloid_scraper.py` a `core/utils/parsing.py` (renombradas sin guion bajo).
- Variable de entorno `OVERVIEW_SOURCE=live|fixture` (default fixture) selecciona el adaptador en el lifespan.
- Prefijo `/game/` (no `/catalog/`) para evitar que el middleware de caché de 1h afecte datos vivos.
- Nuevas excepciones: `OverviewPageNotLoadedError`, `OverviewFixtureNotFoundError`.
- `get_html_source_port` dependency añadida a `adapters/api/dependencies.py`.
- TTL default 60s configurable via `OVERVIEW_CACHE_TTL_SECONDS`.

**Bloqueado hasta HTML real:** selectores de VillageOverviewParser y URLs exactas de _build_url. El usuario debe capturar HTML de Travian siguiendo sección 17 del spec.

**Why:** SessionRegistry diferido (no existe aún); los 4 bloques necesitan poder testearse sin Chrome desde hoy.
**How to apply:** Cuando alguien pregunte por bloques de overview, este tronco ya está especificado. Los 4 bloques heredan port, fixture adapter, utils de parseo y convenciones de esta spec. [[project-arch-conventions]]
