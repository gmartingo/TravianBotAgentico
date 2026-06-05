---
name: project-route-templates
description: Portal desarrollador rutas — RouteTemplate global, clonado a mundos, re-sync explícito, seed 20 plantillas, 10 endpoints nuevos EP-RT01..RT10; gates apis+palantir completados 2026-06-05
metadata:
  type: project
---

## Portal de Desarrollador de Rutas (`docs/specs/route-templates-developer-portal.md`)

**Estado:** `ready-for-impl` (gates desarrollador-apis + palantir completados el 2026-06-05)

### Modelo de datos clave

- Nueva entidad `RouteTemplate` (global, sin world_id) + `RouteTemplatePath` → `core/entities/noise.py`
- Reutiliza `NavigationStep` existente sin cambios
- 3 tablas nuevas: `route_templates`, `route_template_paths`, `route_template_steps`
- Nuevo adaptador: `adapters/db/route_template_sqlite_adapter.py`
- Nuevo puerto: `core/ports/route_template_db_port.py`
- Migración M-RT01: `template_id INTEGER REFERENCES route_templates(id) ON DELETE SET NULL` en `noise_destinations`

### Decisiones cerradas

1. **Instancias independientes** tras clonar: re-sync solo explícito (EP-RT09). No hay push automático.
2. **Colisión de clonado** (UNIQUE world_id+url_pattern): 409 con `conflicting_destination_id`; `force=true` hace UPSERT.
3. **Borrado de plantilla**: instancias quedan con `template_id=NULL` (ON DELETE SET NULL). No destructivo.
4. **Re-sync (EP-RT09)**: reemplaza paths/steps atómicamente; preserva `navigation_weight`, `is_dead`, `consecutive_failures_count`, `last_used_at` de la instancia.
5. **Idempotencia de clon**: misma plantilla + mismo mundo → 200 (ya existe), no 201.

### Endpoints nuevos EP-RT01..RT10

- EP-RT01: `GET /route-templates` (lista, filtro category, include_paths)
- EP-RT02: `POST /route-templates` (crear)
- EP-RT03: `GET /route-templates/{id}` (detalle con paths+steps)
- EP-RT04: `PUT /route-templates/{id}` (PATCH; slug/category/url_pattern inmutables)
- EP-RT05: `DELETE /route-templates/{id}` (instancias quedan huérfanas)
- EP-RT06: `GET /route-templates/{id}/paths`
- EP-RT07: `POST /route-templates/{id}/clone-to-world/{world_id}?force=`
- EP-RT08: `POST /worlds/{id}/noise/apply-templates` (bulk, no atómico)
- EP-RT09: `POST /route-templates/{id}/sync-to-world/{world_id}`
- EP-RT10: `POST /route-templates/{id}/test` (wrapper de EP-N14 existente)

### Modificaciones a endpoints existentes

- EP-N03 response: añade campo `template_id` (null o int)
- EP-N04 request: acepta `template_id` opcional

### Seed inicial (~20 plantillas)

Categorías: navegación estándar (6), edificios (10 con gids verificados), perfil/oasis (4).
Gids clave del catálogo:
- rally_point=13, academy=14, barracks=15, stable=16, trade_office=20
- great_market=21, embassy=22, hero_mansion=23, warehouse=10, granary=11
- Farm list = submenú de rally_point (gid=13), NO gid propio

### Frontend — mapa de reutilización de componentes (palantir gate cierre)

- Nueva ruta `/rutas` en `App.jsx` bajo `ManagementShell`
- Nuevo fichero `frontend/src/pages/RouteTemplatesPage.jsx` (stub; orquesta hijos directamente)
- `NoiseTab` NO se monta en `/rutas` (sus efectos dependen de `worldId`)
- REUTILIZAR sin tocar: `NoisePathWizard`, `NoiseStepEditor`, `NoiseWizardStepForm`,
  `NoiseDerivedSelectorFeedback`, `NoiseOriginSelector` (pasar origins por prop en modo controlled)
- AJUSTAR con prop `mode: "world"|"template"` sin duplicar: `NoiseDestinationsTable`,
  `NoiseDestinationDrawer` (hoy fetcha `getNoisePaths(worldId, dest.id)` internamente)

### Notas anti-detección

- Steps de plantillas siguen las mismas restricciones: delay_min_ms >= 200, delay_max_ms <= 5000
- navigation_weight en plantillas usa el mismo rango [0.1, 5.0] blindado en la entidad
- Sin Accept-Language en endpoints de plantillas (datos del desarrollador, no localizados)

### Extensiones al subsistema de noise (palantir gate cierre)

- `NoiseDbPort.create_destination` → añadir `template_id: int | None = None` (retrocompatible)
- `NoiseSQLiteAdapter.create_destination` → igual; actualizar INSERT para incluir la columna
- `NoiseDbPort` + `NoiseSQLiteAdapter` → añadir métodos nuevos:
  - `find_destination_by_url(world_id, url_pattern) → NoiseDestination | None`
  - `find_destination_by_template(world_id, template_id) → NoiseDestination | None`
- `_validate_url_pattern` y `_same_or_subdomain` (≈línea 570 de noise_sqlite_adapter.py)
  ya existen → REUTILIZAR en el handler de clonado, NO copiar. Opción A: importar directamente;
  opción B: extraer a `adapters/db/_url_validation.py`. Decisión para el implementador.

### Seed

- Datos en `seeds/route_templates.json` (NO en `seeds/game_data/` ni constantes Python)
- `seed_route_templates()` lee el JSON; no usa `seed_loader.py` (exclusivo de kirilloid)

### EP-RT10 test en vivo

- Estrategia: clonar temporal → leer NavigationPath real de BD → execute_path_test → borrar (try/finally)
- Si ya existe instancia clonada del mundo: usar esa, no clonar temporal

**Why:** El usuario quiere curar un catálogo maestro de rutas de Travian de forma global y clonarlas a cada mundo.
**How to apply:** Al diseñar futuros endpoints de ruido o templates, verificar este modelo primero. La entidad RouteTemplate vive en noise.py.
