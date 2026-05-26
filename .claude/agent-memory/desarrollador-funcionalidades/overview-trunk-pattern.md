---
name: overview-trunk-pattern
description: Patrón del tronco común de lectura de overview — port, adaptadores, caché, VillageMapUseCase
metadata:
  type: project
---

El tronco de lectura de overview sigue este patrón (implementado en feature lectura-overview-tronco-comun):

- `OverviewHtmlSourcePort` (ABC) en `core/ports/overview_html_source_port.py` con `OverviewPage` enum (10 valores).
- `FixtureOverviewAdapter` en `adapters/browser/fixture_overview_adapter.py` — lee HTML de `tests/fixtures/overview/{page.value}.html`.
- `LiveOverviewAdapter` en `adapters/browser/live_overview_adapter.py` — caché TTL + double-checked locking asyncio; inyecta `get_browser` y `get_world_server` como callables (actualmente lambdas que devuelven None hasta que exista SessionRegistry).
- `VillageMapUseCase` + `VillageInfo` + `VillageOverviewParser` en `core/use_cases/village_map.py`.
- Dependency FastAPI `get_html_source_port` en `adapters/api/dependencies.py`.
- Wiring en lifespan de `adapters/api/main.py` controlado por `OVERVIEW_SOURCE=live|fixture` (default fixture).
- Los cuatro bloques futuros (overview, resources, culture-points, troops) usan este port como entrada; sus parsers viven en `adapters/browser/parsers/` y sus routers en `adapters/api/routes/game_overview.py` etc. con prefijo `/game/`.

**Why:** arquitectura hexagonal — parsers testables sin Chrome desde el día 1; caché in-memory TTL 60 s.

**How to apply:** al implementar cualquier bloque de los cuatro, reusar el port e inyectar FixtureOverviewAdapter en los tests. Los tests de VillageMap usan fixture real en `tests/fixtures/overview/overview.html` (6 aldeas: 19040/00, 24341/01, 25306/02, 25875/03, 26421/04, 24498/05).

[[game-data-port-pattern]]
