---
name: route-catalog-portal-pregame
description: Gate de entrada para el portal de desarrollador de catálogo de rutas Travian — qué reutilizar, ajustar y crear. Verificado 2026-06-05.
metadata:
  type: project
---

# Gate entrada: portal de desarrollador — catálogo de rutas Travian

Fecha verificación: 2026-06-05

## Lo que YA EXISTE (piezas reutilizables)

### Subsistema de ruido — completo y maduro

El subsistema de ruido YA ES un catálogo de rutas de Travian. No es una aproximación,
es el concepto central del portal:

**Entidades del dominio** — `core/entities/noise.py`:
- `NoiseDestination`: url_pattern + label + category (MAP/OASIS_INFO/PLAYER_PROFILE/
  MESSAGES/REPORTS/BUILDING_VIEW/OTHER) + frequency_weight [0.1,5.0] + is_safe/is_dead
- `NavigationPath`: origin (9 orígenes genéricos + VILLAGE_<data_id>) + steps ordenados
- `NavigationStep`: action (CLICK/WAIT_FOR_SELECTOR/SCROLL_TO/HOVER) + selector CSS + delays humanizados
- `NoiseConfig`: intervalos hardcore/pasivo + dwell time
- `NavigationOrigin` enum: DORF1/DORF2/MAP/STATISTICS/REPORTS/MESSAGES/VILLAGE_STATISTICS/OASIS_VIEW/ANY
- `ORIGIN_PATHS` dict: enum → ruta relativa ("/dorf1.php", "/karte.php", etc.)

**Puerto de BD** — `core/ports/noise_db_port.py`:
- CRUD completo: destinations + paths (con steps anidados) + config
- `pick_random_safe_destination()` con ponderación + clamp anti-detección 60%
- `get_villages_for_world()` / `upsert_village()` para anclas por-aldea
- Contadores de fallos / mark_dead idempotente

**Adaptador SQLite** — `adapters/db/noise_sqlite_adapter.py`:
- 4 tablas: noise_destinations, noise_navigation_paths, noise_navigation_steps, world_noise_config
- FK CASCADE, migraciones incrementales idempotentes (M-NP01/02/03, M-FW01/04)
- Validación de URL (segura, anti-XSS, verifica dominio vs world_server)
- `_validate_origin()` con soporte "VILLAGE_<data_id>"
- `ensure_tables()` llamado en el lifespan de main.py

**Router FastAPI** — `adapters/api/routes/noise.py`:
14 endpoints implementados (EP-N01 a EP-N14):
- EP-N01/N02: GET/PUT config de ruido
- EP-N03..N06: CRUD destinos
- EP-N07..N10: CRUD rutas + steps
- EP-N11: `POST derive-selector` — derivación de selector CSS desde outerHTML
- EP-N12: `GET origins` — 9 anclas genéricas + anclas por-aldea
- EP-N13: `POST refresh-villages` — leer aldeas del DOM via WorldAgent
- EP-N14: `POST paths/{id}/test` — probar ruta en vivo en Chrome real

**Motor de ejecución** — `core/scheduling/world_agent.py` (lineas ~858-1130, ~1431-1614):
- `_select_noise_action()`: selección ponderada + filtro de compatibilidad por origin actual
- `_execute_noise_step()`: ejecuta CLICK/WAIT/SCROLL/HOVER en el tab Chrome real
- `_execute_noise_action()`: recorre pasos + dwell + contadores de fallos
- `execute_path_test()`: modo diagnóstico no destructivo, mismo código que producción
- `_get_current_origin()`: mapea URL actual del browser → NavigationOrigin

**Primitivas de navegación humana** — `adapters/browser/driver.py`:
- `human_click(element, tab)`: gaussiana truncada + Bézier + cursor persistente + mousedown/up separados
- `human_click_at_rect(rect, tab)`: variante cuando rect viene de JS evaluate()
- `human_drift_toward()`: para HOVER
- `human_delay(min_ms, max_ms)`: delays humanizados entre acciones

**Frontend** — 10 componentes React en `frontend/src/components/world/noise/`:
- NoiseTab.jsx: orquesta carga paralela EP-N01 + EP-N03
- NoiseConfigPanel.jsx: edición de configuración
- NoiseDestinationsTable.jsx: tabla de destinos
- NoiseDestinationDrawer.jsx: panel lateral
- NoisePathWizard.jsx: wizard multi-paso de creación de ruta
- NoiseWizardStepForm.jsx: editor de pasos individuales
- NoiseStepEditor.jsx: editor inline
- NoiseOriginSelector.jsx: selector de origen (genérico + por-aldea)
- NoiseDerivedSelectorFeedback.jsx: feedback del derive-selector
- PathTestResultPanel.jsx: resultado del test en vivo

**Cliente HTTP** — `frontend/src/api/client.js` líneas 420-478: 14 métodos api.getNoiseConfig,
api.createNoiseDestination, api.testNoisePath, etc., todos implementados.

### Catálogo de edificios (seed)

`seeds/game_data/building_catalog.json`: 50 edificios con gid (1..50) + alias descriptivo
+ category (resources/military/infrastructure). Este es el mapa completo de gids de Travian.
El rally_point es gid=13, el mercado es gid=16 (farm_lists.py lo usa con `a[href*='gid=16']`).

No existe una constante centralizada de rutas "gid=X" — solo `_FARM_LIST_PATH = "/build.php?gid=16&tt=99"`
en `adapters/browser/farm_lists.py:34`. Cada acceso a un edificio por gid está hardcodeado donde se usa.

### Patrón de persistencia reutilizable

El patrón `SomeSQLiteAdapter` con `ensure_tables()` + `app.state.x_port` está repetido
en main.py y es el modelo estándar del proyecto. Ver `adapters/api/main.py` líneas 128-241.

### Patrón de página React

Ruta `/mundos/:worldId` → `WorldSpacePage.jsx` con tabs laterales.
`ManagementShell` con sidebar para páginas de gestión global.
`frontend/src/api/client.js`: cliente HTTP centralizado, `Accept-Language` automático.

## Lo que HAY QUE CREAR

### El portal de desarrollador como tal

Lo que NO existe es una vista/herramienta donde el desarrollador pueda:
1. Ver el catálogo canónico de ~80% de rutas conocidas de Travian (pre-poblado por él)
2. Editar/curar ese catálogo maestro de rutas (independiente de un mundo concreto)
3. Asociar rutas del catálogo a un mundo con un click (en vez de crearlas de cero cada vez)

Lo que existe es un editor de rutas por-mundo (el NoiseTab), pero:
- Las rutas son específicas de un world_id (UNIQUE world_id+url_pattern)
- No hay noción de "plantilla/catálogo global" de rutas
- No hay seeding/importación masiva desde un catálogo maestro

### Delta a construir (si se adopta la arquitectura correcta)

OPCIÓN A — ampliar el modelo existente con rutas "plantilla":
- Añadir tabla `route_templates` sin world_id: template global que el dev curate
- Endpoint para importar/clonar templates → noise_destinations de un mundo
- Vista de developer: pantalla nueva (fuera de WorldSpacePage, no por-mundo)

OPCIÓN B — pre-poblar el catálogo de ruido de un mundo desde seed CSV/JSON:
- Endpoint `POST /worlds/{id}/noise/destinations/bulk-import`
- El dev mantiene un seed externo; al crear un mundo se pre-populan las rutas
- No requiere nueva tabla, pero tampoco da vista de editor del catálogo maestro

La elección entre A y B es decisión del analista.

## Advertencia de acoplamiento

NoiseCategory tiene solo 7 categorías. El catálogo de 80% de rutas de Travian puede
requerir categorías más granulares (ej: BUILDING_RALLY_POINT vs BUILDING_MARKET vs
BUILDING_GENERIC) o un campo extra `gid: int | None`. Cambiar la categoría es un ALTER
TABLE con migración (ya hay 3-4 precedentes en noise_sqlite_adapter.py) — factible.
