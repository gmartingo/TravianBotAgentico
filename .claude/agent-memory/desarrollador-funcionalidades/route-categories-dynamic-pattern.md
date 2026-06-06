---
name: route-categories-dynamic-pattern
description: Catálogo dinámico de categorías: patrón de migración SQLite sin FK hard + UNSET sentinel para PATCH parcial de color
metadata:
  type: project
---

Catálogo dinámico de categorías implementado (2026-06-06) para `route_categories`.

**Patrón UNSET sentinel en ports:** cuando un PATCH puede poner un campo a null explícito vs no enviarlo, usar el centinela `UNSET` de `core/ports/route_category_db_port.py`. El handler pasa `color=UNSET` si el campo no está en `model_fields_set`; el adaptador lo interpreta como "conservar".

**Patrón migración SQLite con columna renombrada:** M-CAT03/M-CAT04 usan el procedimiento oficial de 12 pasos (foreign_keys=OFF, SAVEPOINT, CREATE _new, INSERT-SELECT, DROP vieja, RENAME _new). Detección de idempotencia: verificar si columna `category_slug` ya existe via `PRAGMA table_info`. Aplicar **antes** del `CREATE TABLE IF NOT EXISTS` con el DDL nuevo.

**Retrocompat en adaptadores:** `_get_category_column()` helper cacheado que detecta si la tabla tiene `category_slug` o `category`. Permite que código viejo que no pasó por M-CAT04 siga funcionando.

**Alias retrocompat en create_destination:** parámetro `category=` aceptado como alias de `category_slug=` (extrae `.value` si es enum). Útil durante migración progresiva de call-sites.

**Sin FK hard entre route_templates/noise_destinations y route_categories:** validación de existencia en la capa de aplicación (handler), no en SQLite. Permite EC-CAT09 (slug huérfano sin bloqueo).

**Inicialización en lifespan:** `RouteCategorySQLiteAdapter` debe inicializarse ANTES de `RouteTemplateSQLiteAdapter` porque las migraciones M-CAT03/M-CAT04 necesitan que la tabla `route_categories` ya exista.

**Why:** eliminar el enum `NoiseCategory` hardcodeado de 7 valores y reemplazarlo por un catálogo de usuario editable inline.
**How to apply:** para futuros catálogos dinámicos de usuario: mismo patrón de tabla con `label_lower UNIQUE`, `slugify`, `UNSET` sentinel, migración M-CAT* idempotente.
