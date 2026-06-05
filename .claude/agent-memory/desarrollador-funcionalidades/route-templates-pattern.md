---
name: route-templates-pattern
description: Catálogo maestro de plantillas de rutas de ruido: entidades, puerto, adaptador, migración M-RT01 y gotcha de FK SQLite en migraciones con columnas referenciadas
metadata:
  type: project
---

Spec `route-templates-developer-portal.md` implementado (Fase A — backend) el 2026-06-05.

## Estructura

- `core/entities/noise.py` — añadidas `RouteTemplatePath` y `RouteTemplate`; `NoiseDestination.template_id` nullable
- `core/ports/route_template_db_port.py` — `RouteTemplateDbPort` (CRUD + seed + conteo)
- `adapters/db/route_template_sqlite_adapter.py` — 3 tablas + `seed_route_templates()` + migración M-RT01
- `seeds/route_templates.json` — 20 plantillas JSON externas (NO usar `seeds/game_data/` que es exclusivo de kirilloid)
- Registrado en lifespan de `adapters/api/main.py` después de `NoiseSQLiteAdapter`

## Gotcha crítico: migración con FK hacia tabla nueva

**Problema**: La migración M-RT01 añade FK `REFERENCES route_templates(id)` a `noise_destinations` via ALTER TABLE. Si se ejecuta en `NoiseSQLiteAdapter.ensure_tables()` (antes de que `route_templates` exista), SQLite con `foreign_keys=ON` lanza `no such table: main.route_templates` al hacer INSERT aunque el valor sea NULL.

**Solución**: Mover la migración que añade FK hacia una tabla nueva al `ensure_tables()` del adaptador que CREA esa tabla (aquí: `RouteTemplateSQLiteAdapter.ensure_tables()`). El orden en el lifespan: Noise primero → RouteTemplate después (incluye M-RT01).

## Patrón dinámico de columnas opcionales

Para retrocompatibilidad con tests que no crean todas las tablas, `NoiseSQLiteAdapter` tiene `_has_template_id_column()` con caché en `self._template_id_col`. Los SELECTs y el INSERT de `create_destination` incluyen `template_id` dinámicamente según si la columna existe.

## Seed via JSON externo (no seed_loader.py)

`seed_route_templates(adapter)` en `route_template_sqlite_adapter.py` lee `seeds/route_templates.json` directamente (JSON externo, no `seed_loader.py` que es exclusivo de kirilloid). Idempotente por slug: si ya existe, no modifica.

## Relacionado con [[noise-navigation-pattern]], [[noise-path-wizard-pattern]], [[sqlite-rename-fk-gotcha]]
