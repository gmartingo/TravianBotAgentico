---
name: route-templates-pattern
description: Catálogo maestro de plantillas de rutas de ruido v1+v2: entidades, puerto, adaptador, migraciones M-RT01/02/03, servicio de dominio anti-ciclos, validación selectores
metadata:
  type: project
---

Spec `route-templates-developer-portal.md` implementado en dos fases:
- Fase A v1 (2026-06-05): backend base — 3 tablas, CRUD, seed, M-RT01.
- Fase A v2 (2026-06-05): rutas atómicas componibles — `origin_template_id`, M-RT02/M-RT03, servicio de dominio.

## Estructura

- `core/entities/noise.py` — `RouteTemplate` sin `navigation_weight` (v2 rev.2); con `origin_template_id: int | None = None` (v2)
- `core/ports/route_template_db_port.py` — `RouteTemplateDbPort`: `update_template` sin `navigation_weight`, sentinel `...` para `origin_template_id`; `get_templates_by_origin` (v2)
- `core/use_cases/route_template_service.py` — servicio puro: `CyclicOriginError`, `validate_no_cycle`, `validate_chain_integrity`, `resolve_origin_chain` → `list[ResolvedStep]`, `validate_selector_is_structural`
- `adapters/db/route_template_sqlite_adapter.py` — 3 tablas sin `navigation_weight`; M-RT02 (origin_template_id), M-RT03 (DROP navigation_weight); seed con 2 pasadas (raíces + hijas resolviendo `origin_slug → id`)
- `seeds/route_templates.json` — actualmente `[]` en v2; poblarlo con rutas atómicas (field `origin_slug` para dependencias)
- Registrado en lifespan de `adapters/api/main.py` después de `NoiseSQLiteAdapter`

## Gotcha crítico: migración con FK hacia tabla nueva

**Problema**: La migración M-RT01 añade FK `REFERENCES route_templates(id)` a `noise_destinations`. Si se ejecuta en `NoiseSQLiteAdapter.ensure_tables()` (antes de que `route_templates` exista), SQLite falla.

**Solución**: Mover la migración al `ensure_tables()` del adaptador que CREA la tabla referenciada (`RouteTemplateSQLiteAdapter.ensure_tables()`). Orden en lifespan: Noise primero → RouteTemplate después (incluye M-RT01).

## PRAGMA foreign_keys = ON — obligatorio

`RouteTemplateSQLiteAdapter.ensure_tables()` y `NoiseSQLiteAdapter.ensure_tables()` activan `PRAGMA foreign_keys = ON`. Sin esto, `ON DELETE SET NULL` no actúa en SQLite y las hijas no quedan NULL al borrar el origen.

## Servicio puro sin imports de adapters

`core/use_cases/route_template_service.py` no importa nada de `adapters/`. Recibe el puerto como parámetro. La detección de ciclos usa `O(d)` queries con `d <= 20`. El router llama al servicio antes de persistir.

## Sentinel Ellipsis en update_template

El parámetro `origin_template_id` del puerto usa `type[...] = ...` (Ellipsis) como sentinel para "no cambiar". `None` = quitar origen (pasar a raíz). El router resuelve el sentinel con `model_fields_set` de Pydantic v2 antes de llamar al puerto.

## Seed con 2 pasadas

`seed_route_templates()` hace 2 pasadas: (1) inserta raíces (`origin_slug=null`), construye `{slug: id}`; (2) inserta hijas resolviendo `origin_slug → id`. El JSON usa `origin_slug` (string) no `origin_template_id` (int) para independencia de IDs autoincrementales.

## navigation_weight eliminado de RouteTemplate (v2 rev.2)

El peso vive en `NoiseDestination.frequency_weight` (por-mundo). `_clone_template_to_world` recibe `navigation_weight: float = 1.0` como parámetro del request (no de la entidad plantilla).

## Relacionado con [[noise-navigation-pattern]], [[noise-path-wizard-pattern]], [[sqlite-rename-fk-gotcha]]
