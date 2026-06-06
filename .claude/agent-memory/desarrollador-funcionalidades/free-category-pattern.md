---
name: free-category-pattern
description: category libre (str, no enum): migraciones M-RT04+M-ND02, normalización en entidades, _dest_to_response
metadata:
  type: project
---

## Patrón: categoría libre en route_templates y noise_destinations

**Situación:** `category` era enum `NoiseCategory` con CHECK IN(7 valores) en BD. Convertida a `str` libre (≤50 chars) para admitir "Estadísticas", "Top 10", etc.

### Migraciones necesarias (ambas usan foreign_keys=OFF + SAVEPOINT)

- **M-RT04** en `adapters/db/route_template_sqlite_adapter.py`: Detecta `CHECK (category IN` en `sqlite_master` de `route_templates`. Si existe, recrea la tabla sin el CHECK. Idempotente. Se llama en `ensure_tables()` tras M-RT03.
- **M-ND02** (`_migrate_noise_destinations_free_category`) en `adapters/db/noise_sqlite_adapter.py`: Misma lógica para `noise_destinations`. Detecta presencia de `template_id` antes de reconstruir para incluirla o no. Idempotente. Se llama al final de `ensure_tables()`.

### Capas modificadas (de dentro a fuera)

1. **`core/entities/noise.py`**:
   - `RouteTemplate.category`: `NoiseCategory` → `str`, validación `≤50 chars`, normaliza `NoiseCategory` enum en `__post_init__` con `object.__setattr__`.
   - `NoiseDestination.category`: `NoiseCategory | str`, normaliza enum→str en `__post_init__`.

2. **Adaptadores SQLite**:
   - `_row_to_template`: `category=row_dict["category"]` (sin `NoiseCategory(...)`).
   - `create_template`: `str(template.category)` (no `.value`).
   - `update_template`: nuevo parámetro `category: str | None = None`.
   - `_row_to_destination`: `category=row_dict["category"]` (sin enum).
   - `create_destination`: `category: "NoiseCategory | str"`, normaliza con `category.value if isinstance(...) else str(category)`.
   - `list_templates/list_destinations`: mismo patrón de normalización en filtro.

3. **Puerto** (`core/ports/route_template_db_port.py`): `category` en `list_templates` y `update_template` actualizado a `str | None`.

4. **Router API** (`adapters/api/routes/route_templates.py`):
   - `CreateTemplateRequest.category`: `str`, `min_length=1`, `max_length=50`.
   - `UpdateTemplateRequest`: `category` como campo **editable** (no inmutable), `Optional[str]`.
   - `check_immutable_fields`: solo bloquea `slug` y `url_pattern`, ya no bloquea `category`.
   - `_template_to_full_response` y `_template_to_list_item`: `str(tpl.category)` (no `.value`).
   - `list_templates` query param: `Optional[str]` (no `NoiseCategory`).

5. **Router noise** (`adapters/api/routes/noise.py`):
   - `_dest_to_response`: `category=dest.category.value if hasattr(dest.category, "value") else str(dest.category)`.

### Frontend
- `CATEGORIES` en `RouteTemplatesPage.jsx`: añadir "Estadísticas" y "Top 10".
- Campo categoría (crear + filtrar): `<input type="text" list="category-datalist">` + `<datalist>` con sugerencias.
- `NoiseDestinationDrawer.jsx` en `mode="template"`: campo categoría editable con datalist; incluir `category` en `handleSaveDest` y en `isDirty`.

### Gotcha principal
`_dest_to_response` en noise.py llamaba a `.value` en `dest.category`. Al pasar `category` a `str`, lanza `AttributeError`. Usar `hasattr(dest.category, "value")` como guard.

**Why:** Extender categorías requería tocar el código; con str libre el usuario puede añadir "Estadísticas" o "Top 10" sin cambios en backend.

**How to apply:** En futuros cambios de enum→str en BD, seguir el patrón M-RT04 (reconstrucción con foreign_keys=OFF, detección idempotente via `sqlite_master`). Buscar siempre `.value` en los helpers de respuesta de la API.
