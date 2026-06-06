---
name: project-route-categories
description: Catálogo dinámico de categorías de rutas — entidad RouteCategory, migración de enum NoiseCategory, blast radius 25 puntos, patrón label_lower para unicidad CI
metadata:
  type: project
---

# Catálogo Dinámico de Categorías de Rutas

## Spec: `docs/specs/route-categories-dynamic.md` (estado: draft — pendiente gate desarrollador-apis + disenador-producto)

## Decisiones clave cerradas

- `RouteCategory`: slug (inmutable, generado auto), label (editable libre), color (hex CSS o null), is_default, created_at.
- Tabla `route_categories` con columna `label_lower TEXT UNIQUE` para unicidad case-insensitive en SQLite (sin expresiones en índices).
- Slug generado automáticamente con slugify(label); colisiones → sufijo -2, -3 etc.
- Catálogo **global** (no por mundo): `route_templates` y `noise_destinations` comparten el mismo catálogo.
- Default `uncategorized` (is_default=true): no borrable, label y color editables.
- **Migración mapea TODO a `uncategorized`** — no se preservan las 7 categorías del enum (decisión "catálogo en blanco").
- Sin FK hard SQLite entre `category_slug` y `route_categories.slug` (la integridad se gestiona en capa de aplicación; slug huérfano es aceptable en single-user).
- `DELETE /route-categories/{slug}` → `200` con body `{deleted_slug, reassigned_count}` (no 204).
- Endpoints sin `Accept-Language` (labels son texto libre de usuario, no catálogo de Travian).

## Blast radius del enum `NoiseCategory`

25 puntos de cambio en 6 ficheros de código y ~40 tests en 6 ficheros. Ver spec §14 para el orden de 16 pasos de implementación.

Puntos críticos:
- CHECK constraints hardcodeados en DDL de `noise_destinations` y `route_templates` → recrear tablas (SQLite no admite DROP CONSTRAINT).
- Patrón de migración idempotente: `PRAGMA table_info` → si columna `category_slug` ya existe, saltar.
- `NoiseCategory` enum se mantiene en el fichero marcado como DEPRECATED hasta que todos los tests pasen; se borra en el Paso 14.

## Patrón de port

`RouteCategoryDbPort` nuevo y separado (no añadir a `NoiseDbPort` — separación de responsabilidades). Sigue el patrón de `RouteTemplateDbPort`.

## Registro en main.py / lifespan

Inicializar `RouteCategorySQLiteAdapter` y registrar en `app.state.route_category_port`. Seed de categorías corre ANTES del seed de route_templates.

## Pendiente antes de ready-for-impl

1. Gate `desarrollador-apis` — validar/corregir EP-CAT01..EP-CAT06 + cambios a EP-RT01/02/04 y EP-N03/04/05.
2. Gate `disenador-producto` — spec visual + mockup editable del `CategoryCombobox` (desplegable inteligente CRUD inline estilo Notion).

**Why:** decisión de producto de convertir el enum fijo NoiseCategory en catálogo dinámico gestionable por el usuario.
**How to apply:** cuando se toque cualquier código que referencie `NoiseCategory`, revisar si ya fue migrado o si necesita actualizarse.
