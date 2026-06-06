---
id: route-categories-dynamic
titulo: Catálogo Dinámico de Categorías de Rutas
estado: implemented
fecha: 2026-06-06
autor: analista
apis_validadas_por_desarrollador_apis: true
mockup_aprobado_por_usuario: si
implementado_por: desarrollador-funcionalidades
fecha_implementacion: 2026-06-06
---

# Catálogo Dinámico de Categorías de Rutas

> Estado `ready-for-impl`: contratos de API (§8) validados por `desarrollador-apis` (luz
> verde) y gate humano del mockup aprobado por el usuario (2026-06-06). Listo para
> implementación.

---

## 1. Objetivo de negocio

Reemplazar el enum fijo `NoiseCategory` (7 valores hardcodeados en `core/entities/noise.py:23`)
por un **catálogo dinámico de categorías** gestionable por el usuario estilo Notion: crear,
renombrar, cambiar color y borrar categorías inline desde el portal de Route Templates, sin
salir del flujo de edición de una plantilla o destino.

El catálogo dinámico aplica simultáneamente a las dos entidades que hoy usan `NoiseCategory`:
- `route_templates` (catálogo maestro global).
- `noise_destinations` (rutas clonadas por mundo).

Las categorías son globales (no por mundo): todas las plantillas y destinos de cualquier mundo
comparten el mismo catálogo.

---

## 2. Actores y permisos

| Actor | Acciones |
|---|---|
| Desarrollador / usuario del bot | CRUD completo de categorías; reasignar categoría a cualquier plantilla/destino en cualquier momento |
| Sistema (bootstrap / seed) | Insertar la categoría default "Sin categoría" (`uncategorized`) al iniciar si no existe |

No hay autenticación ni roles diferenciales: este es un sistema single-tenant. Todos los
endpoints son accesibles sin token de usuario (la misma política que el resto del proyecto).

---

## 3. Alcance

### Dentro del alcance

- Entidad `RouteCategory` (id, slug, label, color, is_default, created_at).
- Tabla SQLite `route_categories` + puerto `RouteCategoryDbPort` + adaptador `RouteCategorySQLiteAdapter`.
- Router CRUD `adapters/api/routes/route_categories.py` (6 endpoints EP-CAT01..EP-CAT06).
- Seed `seeds/route_categories.json` — solo la fila `uncategorized`.
- Desplegable inteligente de selección/gestión de categoría en el portal Route Templates
  (componente `CategoryCombobox`).
- Eliminación del enum `NoiseCategory` y sustitución por `category_slug: str` (FK lógica a
  `route_categories.slug`) en las entidades `NoiseDestination` y `RouteTemplate`.
- Apertura del campo `category` en `UpdateTemplateRequest` y `update_destination` (hoy
  bloqueados).
- Migración de datos: recrear tablas `route_templates` y `noise_destinations` sin CHECK de 7
  valores, y mapear filas existentes a la categoría `uncategorized`.
- Badge `NoiseCategoryBadge` refactorizado para recibir `label` + `color` dinámicos.
- Eliminación de los arrays `CATEGORIES` hardcodeados en `RouteTemplatesPage.jsx` y
  `NoiseDestinationsTable.jsx`.
- Claves i18n `noise.category.*` legacy: **no se borran**, quedan como texto muerto ignorado;
  no se añaden entradas nuevas para categorías de usuario.
- Tests: actualizar los ~40 usos de `NoiseCategory.*` en 6 ficheros de test.

### Fuera del alcance

- Autenticación / autorización diferencial de usuarios.
- Categorías por mundo (el catálogo es global; esto puede ampliarse en una iteración futura).
- Migración que **conserva** la clasificación original (ver §13: se eligió mapear todo a
  `uncategorized` por simplicidad y para forzar re-clasificación consciente).
- Import/export de categorías.
- Ordenar manualmente las categorías (el orden es por `created_at ASC`).
- UI fuera del portal Route Templates (aunque el badge se actualiza en NoiseDestinationsTable
  automáticamente al cargar categorías desde la API).

---

## 4. Reglas de negocio

| ID | Regla |
|---|---|
| RN-CAT01 | Existe exactamente una categoría default: slug=`uncategorized`, `is_default=true`. No se puede borrar (→ 409). |
| RN-CAT02 | El label de la categoría default (`uncategorized`) **puede** renombrarse (el label es solo presentación). |
| RN-CAT03 | El color de la categoría default **puede** cambiarse. |
| RN-CAT04 | Los slugs de categoría son **inmutables** tras la creación. Son el identificador estable (FK lógica). El label sí es editable. |
| RN-CAT05 | Los labels son únicos **case-insensitive** (normalización: trim + lowercase para comparar). Conflicto → 409. |
| RN-CAT06 | Borrar una categoría en uso reasigna atómicamente todas sus plantillas y destinos a `uncategorized`, luego borra la categoría. Es una transacción SQLite. |
| RN-CAT07 | Una plantilla o destino sin categoría explícita al crearse recibe `uncategorized` como default. |
| RN-CAT08 | El slug se genera automáticamente desde el label al crear (slugify: lowercase, reemplazar espacios y caracteres no alfanuméricos por `-`, colapsar guiones múltiples). El usuario no lo edita. Si hay colisión de slug, añadir sufijo `-2`, `-3`, etc. |
| RN-CAT09 | Una categoría puede crearse sin color (color=null). En ese caso el badge usa el estilo neutro del sistema. |
| RN-CAT10 | La categoría `uncategorized` existe desde el primer arranque de la BD (seed). Las plantillas nuevas reciben este slug si el usuario no elige otra. |
| RN-CAT11 | La categoría de una plantilla o destino **puede** cambiarse en cualquier momento (se elimina la restricción de inmutabilidad). La nueva categoría debe existir en `route_categories`; si no existe → 422. |
| RN-CAT12 | Al clonar una plantilla a un mundo, el destino hereda el `category_slug` de la plantilla. Como el catálogo es global, no hay mapeo adicional; el slug ya apunta a la misma tabla. |

---

## 5. Flujo principal y flujos alternativos

### Flujo P1 — Crear categoría desde el desplegable

1. Usuario escribe en el typeahead del `CategoryCombobox` un nombre sin coincidencia.
2. El desplegable muestra la opción `+ Crear "<texto>"`.
3. Usuario hace clic → petición `POST /route-categories` con `{label, color}`.
4. Backend genera slug, valida unicidad, inserta, devuelve `RouteCategory` con `201`.
5. El desplegable añade la nueva categoría a la lista, la selecciona y cierra.
6. La plantilla/destino queda asociada a la nueva categoría (petición de update separada o
   incluida en el mismo flujo si la UI lo envía de una vez — ver §9).

### Flujo P2 — Renombrar categoría inline

1. Usuario abre el desplegable, pasa el cursor sobre una categoría → aparecen iconos de acción.
2. Hace clic en el icono de edición → el item pasa a modo edición inline.
3. Escribe el nuevo label, confirma con Enter o hace clic fuera.
4. Petición `PATCH /route-categories/{slug}` con `{label}`.
5. Backend valida unicidad, actualiza, devuelve `RouteCategory` con `200`.
6. El desplegable refresca el item (estado local) sin recargar todo.

### Flujo P3 — Cambiar color de categoría

1. Usuario hace clic en el swatch de color de la categoría en el desplegable.
2. Aparece el swatch picker (paleta fija de colores) — ver §10.
3. Usuario selecciona color → petición `PATCH /route-categories/{slug}` con `{color}`.
4. Backend actualiza, devuelve `200`. El badge cambia de color en tiempo real.

### Flujo P4 — Borrar categoría

1. Usuario hace clic en el icono de borrar de una categoría no-default.
2. Aparece el `DeletePopover` ("¿Borrar categoría? Sus rutas pasarán a 'Sin categoría'.").
3. Usuario confirma → petición `DELETE /route-categories/{slug}`.
4. Backend ejecuta transacción atómica: UPDATE plantillas y destinos a `uncategorized`,
   DELETE categoría. Devuelve `200` con `{deleted_slug, reassigned_count}`.
5. El desplegable elimina el item de la lista.

### Flujo P5 — Reasignar categoría de una plantilla

1. Usuario abre el desplegable en la fila de una plantilla (portal Route Templates).
2. Selecciona una categoría diferente de la lista.
3. El desplegable cierra y envía `PUT /route-templates/{id}` con `{category: "<slug>"}`.
4. Backend valida que el slug existe, actualiza, devuelve `200`.
5. El badge de la plantilla se actualiza.

### Flujos alternativos

- **FA-01 (label duplicado al crear):** `POST /route-categories` devuelve `409` con
  `detail: "Ya existe una categoría con este nombre."`. El desplegable muestra el error y
  mantiene el modo creación.
- **FA-02 (borrar categoría default):** `DELETE /route-categories/uncategorized` devuelve `409`
  con `detail: "La categoría por defecto no se puede borrar."`.
- **FA-03 (categoría no encontrada):** `GET/PATCH/DELETE /route-categories/{slug}` devuelve `404`.
- **FA-04 (categoría inválida al actualizar plantilla/destino):** `PUT /route-templates/{id}`
  con `category` slug inexistente → `422` con `detail: "Categoría no encontrada."`.

---

## 6. Edge Cases

| ID | Escenario | Tratamiento |
|---|---|---|
| EC-CAT01 | Borrar la categoría `uncategorized` | `DELETE /route-categories/uncategorized` → `409 Conflict` ("La categoría por defecto no se puede borrar.") |
| EC-CAT02 | Crear categoría con label que difiere solo en mayúsculas ("Mapa" vs "mapa") | Comparar strip+lower → `409 Conflict` |
| EC-CAT03 | Crear categoría con label = " " (solo espacios) | `422 Unprocessable Entity` (validación Pydantic: `min_length=1` tras strip) |
| EC-CAT04 | Slugs generados en colisión (dos labels distintos producen el mismo slug) | Añadir sufijo `-2`, `-3` hasta encontrar uno libre |
| EC-CAT05 | Renombrar label a uno ya existente en otra categoría | `409 Conflict` |
| EC-CAT06 | Borrar categoría vacía (sin rutas asignadas) | `DELETE` con `reassigned_count: 0` — ok directo, sin reasignación |
| EC-CAT07 | Borrar categoría con N rutas asignadas | Transacción: UPDATE N filas a `uncategorized`, luego DELETE. Respuesta `200 {deleted_slug, reassigned_count: N}` |
| EC-CAT08 | Reasignar plantilla a slug de categoría inexistente | `422 Unprocessable Entity` ("Categoría no encontrada.") |
| EC-CAT09 | Clonar plantilla con `category_slug` que ya no existe (categoría borrada entre creación y clonado) | La plantilla tiene un slug huérfano (no hay FK hard en la DB por RN-CAT13). El destino clonado hereda el slug huérfano. El badge frontend cae al estilo neutro (label no encontrado en la lista cargada). No bloquea el clonado. |
| EC-CAT10 | Front carga categorías pero la lista está vacía (solo `uncategorized`) | El desplegable muestra únicamente `uncategorized` + opción de crear nueva |
| EC-CAT11 | Dos peticiones concurrentes crean la misma categoría | La UNIQUE constraint en `route_categories(label_lower)` (ver §7) garantiza que solo una tiene éxito. La segunda recibe `409`. |
| EC-CAT12 | Color fuera de la paleta definida | El backend acepta cualquier string CSS de color válido (hex 3/6 chars, o nombre CSS). La validación es permisiva: `#[0-9A-Fa-f]{3,6}` o cadena de hasta 50 chars. El frontend solo ofrece la paleta predefinida, pero la API no la fuerza. |
| EC-CAT13 | Migración aplicada dos veces (idempotencia) | La migración verifica existencia de la columna antes de actuar (patrón existente en el proyecto: ver `_migrate_noise_paths_add_is_dead_and_failures`). Es idempotente. |
| EC-CAT14 | BD vacía (primera instalación) | El seed de categorías inserta `uncategorized`. El seed de `route_templates` ya referencia slugs de categorías; si la tabla está vacía al arrancar, sus filas quedan con `category_slug = 'uncategorized'` (el seed de templates actualizado usa ese slug). |
| EC-CAT15 | Categoría renombrada mientras el desplegable está abierto en otra pestaña | El badge mostrará el label viejo hasta recargar. Sin mecanismo de push; aceptado (single-user). |

---

## 7. Modelo de datos / cambios de esquema

### 7.1 Nueva tabla `route_categories`

```sql
CREATE TABLE IF NOT EXISTS route_categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slug        TEXT    NOT NULL UNIQUE,         -- inmutable, kebab-case
    label       TEXT    NOT NULL,                -- editable libre
    label_lower TEXT    NOT NULL UNIQUE,         -- label.strip().lower() — para unicidad CI
    color       TEXT,                            -- hex CSS (#RRGGBB) o NULL
    is_default  INTEGER NOT NULL DEFAULT 0,      -- 1 solo para 'uncategorized'
    created_at  TEXT    NOT NULL                 -- ISO 8601 UTC
);

CREATE INDEX IF NOT EXISTS idx_route_categories_slug ON route_categories(slug);
```

**Por qué `label_lower` como columna indexada** (en vez de expresión en CHECK): SQLite soporta
`UNIQUE` en columnas pero no en expresiones de índice al estilo PostgreSQL. Almacenar
`label_lower` explícitamente es el patrón más portátil y verificable con herramientas
estándar.

### 7.2 Cambios en `route_templates`

Problema: la tabla tiene `CHECK (category IN ('MAP','OASIS_INFO',...))`.
SQLite no permite `DROP CONSTRAINT` → recrear tabla.

Cambio: renombrar la columna `category` a `category_slug TEXT NOT NULL DEFAULT 'uncategorized'`
sin CHECK constraint (la validación se hace en la capa de aplicación verificando existencia en
`route_categories`).

### 7.3 Cambios en `noise_destinations`

Mismo problema: `CHECK (category IN (...))` hardcodeado.
Cambio: mismo procedimiento — recrear tabla con `category_slug TEXT NOT NULL DEFAULT 'uncategorized'`.

**Nota:** la columna en BD puede conservar el nombre `category` por retrocompatibilidad de
queries internas; lo que cambia es eliminar el CHECK. El adaptador mapea `category` de BD a
`category_slug` en la entidad. Decidir en implementación cuál es más limpio; esta spec usa
`category_slug` en la entidad Python para dejar claro que ya no es un enum.

### 7.4 Estrategia de migración (orden obligatorio)

> Contexto: `CREATE TABLE IF NOT EXISTS` es idempotente pero no puede alterar tablas
> existentes con CHECK. El patrón del proyecto para esto es el procedimiento oficial de
> SQLite de 12 pasos con `foreign_keys=OFF`.

**Orden de las migraciones en `ensure_tables()` / lifespan:**

```
M-CAT01  Crear tabla route_categories (CREATE TABLE IF NOT EXISTS — idempotente)
M-CAT02  Insertar seed uncategorized si no existe (INSERT OR IGNORE)
M-CAT03  Migrar route_templates: recrear sin CHECK, mapear category → uncategorized
M-CAT04  Migrar noise_destinations: recrear sin CHECK, mapear category → uncategorized
```

**Por qué mapear todo a `uncategorized` y no preservar las categorías originales:**

Preservar requeriría crear categorías con los slugs del enum viejo (MAP, OASIS_INFO, etc.),
lo que daría al usuario una lista de 7 categorías que nunca pidió. El objetivo declarado es
"catálogo en blanco" — el usuario clasifica según sus propios criterios. Las 7 categorías
existentes son conceptos de Travian, no conceptos de negocio del usuario. La re-clasificación
post-migración es un trabajo mínimo para cualquier instancia con datos.

**Procedimiento M-CAT03 (idéntico para M-CAT04, ajustando nombres de tabla):**

```sql
-- DENTRO DE TRANSACCIÓN con PRAGMA foreign_keys=OFF
PRAGMA foreign_keys = OFF;
SAVEPOINT migrate_cat03;

-- 1. Crear tabla temporal sin CHECK
CREATE TABLE route_templates_new (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    slug              TEXT    NOT NULL UNIQUE,
    label             TEXT    NOT NULL,
    category_slug     TEXT    NOT NULL DEFAULT 'uncategorized',
    url_pattern       TEXT    NOT NULL,
    navigation_weight REAL    NOT NULL DEFAULT 1.0
                              CHECK (navigation_weight >= 0.1 AND navigation_weight <= 5.0),
    is_safe           INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT    NOT NULL,
    updated_at        TEXT    NOT NULL
);

-- 2. Copiar datos (category → 'uncategorized' para todos)
INSERT INTO route_templates_new
    (id, slug, label, category_slug, url_pattern, navigation_weight, is_safe, created_at, updated_at)
SELECT id, slug, label, 'uncategorized', url_pattern, navigation_weight, is_safe, created_at, updated_at
FROM route_templates;

-- 3. Reemplazar tabla
DROP TABLE route_templates;
ALTER TABLE route_templates_new RENAME TO route_templates;

-- 4. Recrear índices
CREATE INDEX IF NOT EXISTS idx_route_templates_slug ON route_templates(slug);
CREATE INDEX IF NOT EXISTS idx_route_templates_category ON route_templates(category_slug);

-- 5. Verificar integridad FK
PRAGMA foreign_key_check;

RELEASE SAVEPOINT migrate_cat03;
PRAGMA foreign_keys = ON;
```

**Idempotencia de M-CAT03/M-CAT04:** antes de ejecutar, comprobar si la columna ya se llama
`category_slug` (sin CHECK). Si ya fue migrada, omitir. Patrón: `PRAGMA table_info(route_templates)`
y verificar que no exista un CHECK con los 7 valores.

Forma más simple de detección: verificar que la columna `category_slug` existe (nueva tabla la
crea con ese nombre). Si `category_slug` no está en `table_info`, ejecutar migración; si está,
ya fue hecha.

### 7.5 Seed `seeds/route_categories.json`

```json
[
  {
    "slug": "uncategorized",
    "label": "Sin categoría",
    "color": null,
    "is_default": true
  }
]
```

El seed del loader inserta con `INSERT OR IGNORE` por slug. Idempotente.

### 7.6 Seed `seeds/route_templates.json` (actualización)

Cambiar el campo `"category": "MAP"` → `"category_slug": "uncategorized"` en las ~20 entradas
del seed (o usar `"category_slug"` como nombre de campo en el deserializador del seed loader).

---

## 8. Contratos de API / interfaces

> **VALIDADO por `desarrollador-apis` el 2026-06-06** (MODO REVISIÓN DE CONTRATO DE DISEÑO).
> Los contratos de esta sección son la versión corregida y aprobada. Ver §8.0 para el detalle
> de correcciones aplicadas sobre el borrador original.

### 8.0 Correcciones aplicadas por `desarrollador-apis`

Las siguientes correcciones se aplicaron sobre el borrador del analista. El resto del borrador
estaba correcto y se mantiene sin cambios.

#### C-01 — Renombrar `?category=` a `?category_slug=` (EP-RT01, EP-N03): CONFIRMADO, con matiz

El renombrado es correcto. Adicionalmente, se corrige el comportamiento cuando el slug no existe:
- **Borrador proponía:** `200 []` (filtro silencioso).
- **Corregido a:** `200 []` se mantiene. Justificación revisada: es un filtro opcional de
  listado, no una búsqueda de recurso concreto. En filtros opcionales, el resultado vacío es
  semánticamente correcto (igual que `?is_safe=true` sin resultados devuelve `[]`). La
  validación de existencia del slug en filtros de listado añade acoplamiento innecesario y
  degrada la UX en flujos de edición donde el slug puede haber sido recién eliminado.
  **Regla final:** `?category_slug=<slug-inexistente>` → `200 []`. Documentado explícitamente.

#### C-02 — Campo `category_slug` en responses de EP-RT y EP-N: RENOMBRAR en response también

El borrador cambia el campo `category_slug` en los modelos de entidad pero no dejaba claro
si el nombre del campo en el JSON de respuesta cambia también. Decisión: el campo en la
respuesta JSON de `RouteTemplateResponse`, `RouteTemplateListItem` y `NoiseDestinationResponse`
pasa de `"category"` a **`"category_slug"`** para consistencia con el nombre del campo de
entidad y los parámetros de filtro. Este es un breaking change controlado: el único consumidor
actual es el frontend propio (mismo repo), que se actualiza en el Paso 15.

#### C-03 — Validación de `category_slug` al crear/actualizar plantilla o destino: 422 correcto

El borrador propone `422` cuando el slug no existe al crear/actualizar plantilla o destino.
Esto es correcto: es un error de validación semántica del body (el campo `category_slug`
referencia una entidad que no existe), no un conflicto de estado. Se mantiene `422`.

#### C-04 — Body vacío en PATCH (EP-CAT04): precisar el comportamiento de `null` explícito en `color`

El borrador dice: `"color": null` → quita el color. Esto es correcto per las reglas de PATCH.
Sin embargo, hay ambigüedad: ¿qué pasa si el cliente no envía `color` (campo ausente) vs
envía `color: null`? Decisión: usar el patrón `_UNSET` del proyecto (centinela sentinel).
En el **contrato HTTP** esto se resuelve así:
- Campo `color` **ausente** en el body → conservar el valor actual.
- Campo `color: null` **presente** en el body → quitar el color (poner a null).
Esta distinción se implementa en Pydantic con `model_fields_set` o un tipo `Optional` con
un centinela. El contrato queda documentado en EP-CAT04 con este comportamiento explícito.

#### C-05 — EP-CAT05 DELETE: código 403 vs 409 al borrar la default

El borrador menciona `409` (en FA-02) y en EC-CAT01. Se confirma `409 Conflict` como correcto:
la petición es válida sintácticamente pero conflicta con una regla de negocio del servidor
(la categoría default es protegida). `403 Forbidden` implicaría un problema de permisos/auth,
lo que no aplica en este sistema sin auth. `409` es el código correcto.

#### C-06 — `at_least_one_mutable_field` en EP-CAT04 PATCH: body completamente vacío `{}` → 422

El spec menciona `422` para body vacío pero no especifica el mensaje. Mensaje canónico del
proyecto: `"El body debe contener al menos uno de: label, color."` — consistente con el patrón
de `NoiseConfigUpdateRequest` y `UpdateDestinationRequest`.

#### C-07 — EP-CAT02 POST: `slug` en response — confirmar que NO se puede enviar en el body

El borrador dice que el slug se genera automáticamente (RN-CAT08). Confirmado: el campo `slug`
no aparece en `CreateCategoryRequest`. El cliente nunca lo elige. Está bien.

#### C-08 — EP-CAT06: FUERA DE ALCANCE en v1

EP-CAT06 (`GET /route-categories/{slug}/routes`) no aporta valor de producto suficiente para
la v1 (es solo debug). Queda fuera del alcance inicial. Si se necesita, se añade como endpoint
de diagnóstico sin UI en una iteración posterior. El spec lo menciona como opcional; esta
revisión lo marca explícitamente como `FUERA DE ALCANCE` para que el implementador no lo
incluya sin necesidad.

#### C-09 — Inconsistencia en el nombre de columna en `noise_destinations` (§7.3 vs código)

El §7.3 del spec indica que la columna en BD puede conservar el nombre `category` y que el
adaptador hace el mapeo. Sin embargo, el código actual (`noise.py:537`) ya usa `dest.category.value`
(la entidad tiene el campo `category`). Para consistencia con la entidad Python y el contrato
de API, la columna de BD también debe llamarse `category_slug` (igual que en `route_templates`).
El §9.3 del spec ya usa `category` y `category_slug` mezclados en los UPDATE SQL — corregir
en la implementación para usar `category_slug` en ambas tablas.

#### C-10 — Formato de error: `detail` vs `error.code/message`

El proyecto usa `{"detail": "<mensaje>"}` como formato de error (patrón nativo de FastAPI, no
el formato de error estándar del agente `desarrollador-apis` con `error.code/message/request_id`).
Esta es una decisión de arquitectura ya consolidada en el proyecto (confirmada en `AGENTS.md`
línea 24: "FastAPI usa `detail` por defecto"). Los nuevos endpoints EP-CAT01..EP-CAT05 siguen
el mismo patrón. **No se cambia.** Todos los ejemplos de error en este spec usan `{"detail": "..."}`.

---

### 8.1 Nota de gobernanza de idioma

Los endpoints de categorías **no requieren `Accept-Language`**: los labels son texto libre del
usuario (no del catálogo de Travian). La misma decisión tomada en EP-RT01..EP-RT10 (ver
`route_templates.py:18`): sin `Accept-Language`.

**Regla final confirmada:** los endpoints de gestión de recursos de usuario (`/accounts`,
`/route-templates`, `/route-categories`, `/worlds/*/noise/*`) no exigen `Accept-Language`.
Solo los endpoints que devuelven texto del catálogo de Travian localizado lo requieren
(`/catalog/*`, EP-TD). Esta regla es consistente con el código existente.

### 8.2 Modelos Pydantic — Contratos de request/response exactos

```python
# ---- Requests ----

class CreateCategoryRequest(BaseModel):
    """EP-CAT02 body. El slug NO se acepta: se genera automáticamente (RN-CAT08)."""
    label: str = Field(..., min_length=1, max_length=100)
    color: Optional[str] = Field(
        default=None,
        pattern=r"^#[0-9A-Fa-f]{3,6}$",   # hex 3 o 6 chars, o null
        max_length=50,
    )

    @field_validator("label", mode="before")
    @classmethod
    def strip_label(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("label no puede ser solo espacios.")
        return v


class PatchCategoryRequest(BaseModel):
    """
    EP-CAT04 body. Al menos uno de los dos campos debe estar presente.

    Distinción ausente vs null en color (C-04):
      - color ausente del body  → conservar valor actual
      - color: null en el body  → quitar el color (null explícito)

    Pydantic v2: usar model_fields_set en el handler para distinguir los dos casos.
    """
    label: Optional[str] = Field(default=None, min_length=1, max_length=100)
    color: Optional[str] = Field(
        default=None,
        pattern=r"^#[0-9A-Fa-f]{3,6}$",
        max_length=50,
    )

    @field_validator("label", mode="before")
    @classmethod
    def strip_label(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("label no puede ser solo espacios.")
        return v

    @model_validator(mode="after")
    def at_least_one_field(self) -> "PatchCategoryRequest":
        if "label" not in self.model_fields_set and "color" not in self.model_fields_set:
            raise ValueError("El body debe contener al menos uno de: label, color.")
        return self


# ---- Responses ----

class RouteCategoryResponse(BaseModel):
    """Respuesta de todos los endpoints EP-CAT01..EP-CAT05."""
    slug: str           # inmutable, kebab-case, generado automáticamente
    label: str          # editable
    color: Optional[str]  # hex #RRGGBB o null
    is_default: bool    # true solo para 'uncategorized'
    created_at: str     # ISO 8601 UTC, p. ej. "2026-06-06T10:00:00+00:00"


class DeleteCategoryResponse(BaseModel):
    """Respuesta de EP-CAT05 DELETE."""
    deleted_slug: str
    reassigned_count: int   # total de plantillas + destinos reasignados a 'uncategorized'
    reassigned_to: str = "uncategorized"  # campo informativo fijo, facilita tests y UX
```

**Notas sobre los modelos:**

- `color` con `pattern=r"^#[0-9A-Fa-f]{3,6}$"`: acepta `#RGB` (3 chars) y `#RRGGBB` (6 chars).
  `null` se acepta siempre (campo opcional). Color sin `#` → `422`. Consistent con EC-CAT12 del spec
  (el backend no fuerza la paleta; solo valida que sea hex válido o null).
- El campo `is_default` es de solo lectura; nunca aparece en requests.
- `created_at` se serializa como string ISO 8601 (mismo patrón que `RouteTemplateResponse`).
- `DeleteCategoryResponse` añade `reassigned_to: str = "uncategorized"` respecto al borrador
  original (`{deleted_slug, reassigned_count}`): el valor es siempre `"uncategorized"` pero
  documentarlo explícitamente ayuda al frontend a no hardcodear el string.

### 8.3 Paleta de colores estándar (diseño system)

El backend acepta cualquier string de color CSS válido. El frontend ofrecerá una paleta fija
de 12 swatches acorde con `frontend/DESIGN.md` (tokens duales claro/oscuro, sin neón, sin
dobles acentos). Los colores de la paleta propuestos (a validar por `disenador-producto`):

```
#4A90D9  azul acero       (claro/oscuro dual via opacity)
#5BAD6F  verde musgo
#E8A838  ámbar
#C0392B  terracota
#8E6DBF  malva
#4A9A9A  verde azulado
#D4735E  salmón
#7E8C8D  pizarra
#2C7A7B  teal oscuro
#A0522D  siena
#5C6BC0  índigo
       (neutro)  sin color / null
```

El acento oro del sistema (`#8A6418` claro / `#CBB079` oscuro) **no entra en la paleta** —
está reservado a enlaces/estados activos.

---

### EP-CAT01 — GET /route-categories

**Descripción:** Lista todas las categorías del catálogo, ordenadas por `is_default DESC, created_at ASC`
(la categoría default siempre aparece primero).

```
Método:   GET
Ruta:     /route-categories
Auth:     ninguna
Headers:  ninguno requerido
```

**Query params:** ninguno. No se pagina (catálogo pequeño, esperado 1–20 entradas).

**Response 200** — `list[RouteCategoryResponse]`:
```json
[
  {
    "slug": "uncategorized",
    "label": "Sin categoría",
    "color": null,
    "is_default": true,
    "created_at": "2026-06-06T10:00:00+00:00"
  },
  {
    "slug": "mapa",
    "label": "Mapa",
    "color": "#4A90D9",
    "is_default": false,
    "created_at": "2026-06-06T11:30:00+00:00"
  }
]
```

**Tabla de status codes:**

| Código | Cuándo |
|---|---|
| 200 | Éxito (puede ser lista vacía si solo existe `uncategorized` y se borra — escenario imposible por RN-CAT01, pero el contrato no prohíbe `[]`) |
| 500 | Error interno del servidor |

---

### EP-CAT02 — POST /route-categories

**Descripción:** Crea una nueva categoría. El slug se genera automáticamente desde el label
(RN-CAT08); el cliente no lo elige.

```
Método:   POST
Ruta:     /route-categories
Auth:     ninguna
Headers:  Content-Type: application/json
```

**Request body** — `CreateCategoryRequest`:
```json
{
  "label": "Mapa",
  "color": "#4A90D9"
}
```

| Campo | Tipo | Requerido | Restricciones |
|---|---|---|---|
| `label` | string | sí | strip + min 1 char, max 100 chars; no puede ser solo espacios |
| `color` | string\|null | no (default null) | `^#[0-9A-Fa-f]{3,6}$` si presente; null = sin color |

**Lógica de slug:** `slugify(label.strip())` — lowercase, espacios y no-alfanuméricos → `-`,
guiones múltiples colapsados, guiones de borde eliminados. Si colisión, añadir `-2`, `-3`, etc.

**Response 201** — `RouteCategoryResponse` + header `Location`:
```json
{
  "slug": "mapa",
  "label": "Mapa",
  "color": "#4A90D9",
  "is_default": false,
  "created_at": "2026-06-06T11:30:00+00:00"
}
```
```
Location: /route-categories/mapa
```

**Tabla de status codes:**

| Código | Cuándo |
|---|---|
| 201 | Categoría creada. Header `Location` apunta al nuevo recurso. |
| 409 Conflict | Label duplicado CI (`label.strip().lower()` ya existe en otra categoría): `{"detail": "Ya existe una categoría con este nombre."}` |
| 422 Unprocessable Entity | Body inválido: label vacío/solo espacios, color no es hex válido ni null, label > 100 chars, etc. |
| 500 | Error interno |

---

### EP-CAT03 — GET /route-categories/{slug}

**Descripción:** Devuelve una categoría por slug.

```
Método:   GET
Ruta:     /route-categories/{slug}
Auth:     ninguna
Path:     slug — string, min_length=1
```

**Response 200** — `RouteCategoryResponse`:
```json
{
  "slug": "mapa",
  "label": "Mapa",
  "color": "#4A90D9",
  "is_default": false,
  "created_at": "2026-06-06T11:30:00+00:00"
}
```

**Tabla de status codes:**

| Código | Cuándo |
|---|---|
| 200 | Categoría encontrada |
| 404 Not Found | Slug no existe: `{"detail": "Categoría no encontrada."}` |
| 500 | Error interno |

---

### EP-CAT04 — PATCH /route-categories/{slug}

**Descripción:** Actualiza parcialmente el label y/o el color de una categoría. El slug es
inmutable tras la creación (RN-CAT04). Al menos uno de los dos campos debe estar presente en
el body (body `{}` vacío → `422`).

Semántica de `color`:
- Campo `color` **ausente** del body → conservar el valor actual sin cambios.
- Campo `color: null` **presente** en el body → quitar el color (poner a null). (C-04)

```
Método:   PATCH
Ruta:     /route-categories/{slug}
Auth:     ninguna
Headers:  Content-Type: application/json
```

**Request body** — `PatchCategoryRequest` (al menos uno presente):
```json
{
  "label": "Mapamundi",
  "color": "#5BAD6F"
}
```

| Campo | Tipo | Requerido | Restricciones |
|---|---|---|---|
| `label` | string | no (si ausente, conservar) | strip + min 1 char, max 100 chars si presente |
| `color` | string\|null | no (si ausente, conservar; null explícito → quitar) | `^#[0-9A-Fa-f]{3,6}$` si es string |

**Response 200** — `RouteCategoryResponse` (estado actualizado):
```json
{
  "slug": "mapa",
  "label": "Mapamundi",
  "color": "#5BAD6F",
  "is_default": false,
  "created_at": "2026-06-06T11:30:00+00:00"
}
```

**Tabla de status codes:**

| Código | Cuándo |
|---|---|
| 200 | Categoría actualizada |
| 404 Not Found | Slug no existe: `{"detail": "Categoría no encontrada."}` |
| 409 Conflict | El nuevo label ya existe en otra categoría (CI): `{"detail": "Ya existe una categoría con este nombre."}` |
| 422 Unprocessable Entity | Body `{}` sin ningún campo (`{"detail": "El body debe contener al menos uno de: label, color."}`); label vacío/solo espacios; color no hex válido |
| 500 | Error interno |

> Nota: la categoría `uncategorized` admite `PATCH` para renombrar el label o cambiar el
> color (RN-CAT02, RN-CAT03). No hay restricción de solo-lectura en esta operación.

---

### EP-CAT05 — DELETE /route-categories/{slug}

**Descripción:** Borra una categoría. Si tiene plantillas o destinos asignados, los reasigna
atómicamente a `uncategorized` antes de borrar. La operación es transaccional (EC-CAT06/07).

```
Método:   DELETE
Ruta:     /route-categories/{slug}
Auth:     ninguna
```

**Request body:** ninguno.

**Response 200** — `DeleteCategoryResponse`:
```json
{
  "deleted_slug": "mapa",
  "reassigned_count": 7,
  "reassigned_to": "uncategorized"
}
```

> Se devuelve `200` con body (no `204`) porque `reassigned_count` es información útil
> para el usuario y los tests. `204 No Content` no admite body. (T5)

**Tabla de status codes:**

| Código | Cuándo |
|---|---|
| 200 | Categoría borrada. `reassigned_count=0` si no tenía plantillas/destinos asignados. |
| 404 Not Found | Slug no existe: `{"detail": "Categoría no encontrada."}` |
| 409 Conflict | Intento de borrar la categoría default (`is_default=true`): `{"detail": "La categoría por defecto no se puede borrar."}` |
| 500 | Error interno |

> `409` (y no `403`) para el borrado de la default porque el error es un conflicto de regla
> de negocio, no un problema de permisos/auth. (C-05)

---

### EP-CAT06 — FUERA DE ALCANCE (v1)

El endpoint `GET /route-categories/{slug}/routes` (debug: lista slugs de plantillas e IDs de
destinos con esa categoría) queda fuera del alcance de la implementación inicial. No hay
demanda de UI y el valor de producto no justifica el coste. Puede añadirse en iteración futura
como endpoint de diagnóstico sin UI. (C-08)

---

### 8.4 Cambios en endpoints existentes (contratos corregidos)

#### EP-RT01 — GET /route-templates (cambio: filtro `?category=` → `?category_slug=`)

El parámetro de filtro pasa de `?category=<NoiseCategory enum>` a `?category_slug=<string>`.

| Aspecto | Antes | Después |
|---|---|---|
| Nombre del parámetro | `?category=` | `?category_slug=` |
| Tipo aceptado | `NoiseCategory` (enum de 7 valores) | `str` (slug libre, cualquier string) |
| Valor inválido del enum | `422` automático de FastAPI | N/A — ya no es enum |
| Slug inexistente | N/A | `200 []` (filtro silencioso — C-01) |

**Nombre del campo en la respuesta JSON:** `"category"` → **`"category_slug"`** (C-02).

Breaking change documentado: los consumidores existentes que usaban `?category=MAP` deben
cambiar a `?category_slug=<slug>`. El único consumidor activo es el frontend del mismo repo.

#### EP-RT02 — POST /route-templates (cambio: campo `category`)

`CreateTemplateRequest`:
- Antes: `category: NoiseCategory` (enum, requerido).
- Después: `category_slug: str = "uncategorized"` (string, opcional con default).

**Nombre del campo en el body de request:** `"category"` → **`"category_slug"`** (consistencia con la entidad Python y el filtro de EP-RT01).

**Validación:** si el slug provisto no existe en `route_categories` → `422` con
`{"detail": "Categoría no encontrada."}`. (C-03)

**Nombre del campo en la respuesta JSON:** `"category"` → **`"category_slug"`** (C-02).

#### EP-RT04 — PUT /route-templates/{id} (cambio: `category_slug` ahora actualizable)

`UpdateTemplateRequest`:
- Eliminar el `model_validator` que rechaza `category` con `ValueError`.
- Añadir `category_slug: Optional[str] = None` como campo editable.
- Añadir `category_slug` a la lista de campos de `at_least_one_mutable_field`.
- Si se envía, validar existencia en `route_categories` → `422` si no existe. (C-03)

**Nombre del campo en el body de request:** `"category_slug"` (renombrado de `"category"`).

**Nombre del campo en la respuesta JSON:** `"category_slug"` (C-02).

#### EP-N03 — GET /worlds/{id}/noise/destinations (cambio: filtro `?category=` → `?category_slug=`)

Mismo cambio que EP-RT01: `?category=<NoiseCategory>` → `?category_slug=<string>`.
Slug inexistente → `200 []` (filtro silencioso). (C-01)

**Nombre del campo en la respuesta JSON:** `"category"` → **`"category_slug"`** (C-02).

#### EP-N04 — POST /worlds/{id}/noise/destinations (cambio: campo `category`)

`CreateDestinationRequest`:
- Antes: `category: NoiseCategory` (enum, requerido).
- Después: `category_slug: str = "uncategorized"` (string, opcional con default).

**Nombre del campo en el body:** `"category_slug"`.
**Validación:** slug debe existir → `422` si no. (C-03)
**Nombre del campo en la respuesta JSON:** `"category_slug"` (C-02).

#### EP-N05 — PUT /worlds/{id}/noise/destinations/{id} (cambio: `category_slug` ahora actualizable)

`UpdateDestinationRequest`:
- Añadir `category_slug: Optional[str] = None`.
- Añadir `category_slug` a la validación de `at_least_one_field`.
- Si se envía, validar existencia → `422`. La restricción de inmutabilidad se elimina.

**Nombre del campo en el body:** `"category_slug"`.
**Nombre del campo en la respuesta JSON:** `"category_slug"` (C-02).

> **Nota para el implementador sobre EP-N05:** el router actual declara el verbo como `PUT`
> pero el docstring y la operación es un PATCH parcial. El spec de noise-path-wizard ya
> establece este verbo. No se cambia el verbo en este spec para no introducir un breaking
> change adicional fuera del alcance de esta feature. La inconsistencia verbo/semántica es
> deuda conocida.

---

## 9. Flujo lógico paso a paso

### 9.1 Bootstrap de la BD (lifespan)

```python
# En NoiseSQLiteAdapter.ensure_tables() O en un nuevo RouteCategorySQLiteAdapter.ensure_tables()
# (ver §14 para la elección)

async def ensure_tables(conn):
    # M-CAT01: crear tabla route_categories si no existe
    await conn.execute(CREATE_ROUTE_CATEGORIES_DDL)

    # M-CAT02: insertar uncategorized si no existe
    await conn.execute("""
        INSERT OR IGNORE INTO route_categories
            (slug, label, label_lower, color, is_default, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, ("uncategorized", "Sin categoría", "sin categoría", None, 1, now_iso()))
    await conn.commit()

    # M-CAT03: migrar route_templates si aún tiene CHECK de 7 valores
    await _migrate_route_templates_remove_check(conn)

    # M-CAT04: migrar noise_destinations si aún tiene CHECK de 7 valores
    await _migrate_noise_destinations_remove_check(conn)
```

### 9.2 Crear categoría (POST /route-categories)

```python
async def create_category(label: str, color: str | None) -> RouteCategory:
    label = label.strip()
    label_lower = label.lower()

    # EC-CAT02: unicidad CI
    existing = await db.get_category_by_label_lower(label_lower)
    if existing:
        raise ConflictError("Ya existe una categoría con este nombre.")

    # RN-CAT08: generar slug
    slug = slugify(label)
    slug = await _ensure_unique_slug(db, slug)

    return await db.insert_category(slug, label, label_lower, color, is_default=False)
```

### 9.3 Borrar categoría con reasignación (DELETE /route-categories/{slug})

```python
async def delete_category(slug: str) -> DeleteResult:
    cat = await db.get_category(slug)
    if cat is None:
        raise NotFoundError("Categoría no encontrada.")
    if cat.is_default:
        raise ConflictError("La categoría por defecto no se puede borrar.")

    async with conn.begin_transaction() as tx:
        # Reasignar plantillas
        n_templates = await tx.execute("""
            UPDATE route_templates SET category_slug = 'uncategorized'
            WHERE category_slug = ?
        """, (slug,))

        # Reasignar destinos
        n_destinations = await tx.execute("""
            UPDATE noise_destinations SET category = 'uncategorized'
            WHERE category = ?
        """, (slug,))

        # Borrar categoría
        await tx.execute("DELETE FROM route_categories WHERE slug = ?", (slug,))

    return DeleteResult(deleted_slug=slug, reassigned_count=n_templates + n_destinations)
```

### 9.4 Clonar plantilla a mundo (sin cambios funcionales)

```python
# _clone_template_to_world (route_templates.py:409) — sin cambios en la lógica
# template.category_slug se pasa como category al crear el noise_destination
dest = await noise_db.create_destination(
    world_id=world.id,
    url_pattern=template.url_pattern,
    label=template.label,
    category=template.category_slug,   # str en lugar de NoiseCategory enum
    frequency_weight=template.navigation_weight,
    ...
)
```

---

## 10. Validaciones y reglas

| Campo | Validación | Capa |
|---|---|---|
| `label` (create) | strip, min_length=1, max_length=100 | Pydantic + adaptador |
| `label` (update) | strip, min_length=1, max_length=100 si presente | Pydantic + adaptador |
| `label` unicidad | strip().lower() comparado contra `label_lower` de BD | Adaptador (query) + excepción `ConflictError → 409` |
| `color` | `None` o regex `^#[0-9A-Fa-f]{3,6}$` o string ≤50 chars | Pydantic |
| `slug` (en path) | Existe en `route_categories` | Adaptador → `404` si no existe |
| `category` en plantillas/destinos | Slug debe existir en `route_categories` | Handler de route → `422` si no existe |
| `is_default` | Solo lectura; no editable vía API | El campo no está en CreateRequest ni PatchRequest |
| Body vacío en PATCH | Al menos `label` o `color` presente | Pydantic `model_validator` |

---

## 11. Seguridad, rendimiento y concurrencia

### Seguridad

- No hay datos sensibles en las categorías (labels/colores son texto de usuario).
- Las cabeceras de seguridad globales (`main.py`) aplican a todos los endpoints.
- Nada de este módulo toca el browser ni la sesión de Travian → el agente
  `guardian-antideteccion` no aplica.

### Rendimiento

- El catálogo de categorías es pequeño (esperado: 1–20 entradas). No se necesita paginación.
- `GET /route-categories` se llama al montar cada desplegable → cacheable en el frontend
  con invalidación local tras cada mutación (no TTL, sino react-state).
- Los índices en `slug` y `label_lower` (única columna de búsqueda frecuente) son suficientes.
- La operación de borrado con reasignación es una transacción sobre tablas pequeñas → sin
  riesgo de timeout.

### Concurrencia

- SQLite WAL: múltiples lectores concurrentes sin bloqueo. Las escrituras son serializadas.
- EC-CAT11: la UNIQUE constraint en `label_lower` garantiza atomicidad en inserciones
  concurrentes. La segunda escritura recibirá `IntegrityError → 409`.
- La transacción de borrado+reasignación es atómica: no puede quedar en estado parcial.

---

## 12. Plan de pruebas

### 12.1 Tests de la entidad `RouteCategory`

- `test_route_category_slug_immutable` — slug es string fijo; no tiene setter.
- `test_route_category_label_editable` — label puede cambiar.
- `test_slugify_colision` — dos labels que generan mismo slug producen slugs distintos.

### 12.2 Tests del adaptador `RouteCategorySQLiteAdapter`

- `test_create_category_ok` — inserta y devuelve `RouteCategory`.
- `test_create_category_duplicate_label_ci` — "Mapa" y "mapa" → segunda `ConflictError`.
- `test_create_category_slug_collision` — labels "a-b" y "a b" generan slugs distintos.
- `test_get_category_not_found` — devuelve `None`.
- `test_patch_label_ok` — actualiza label, mantiene slug.
- `test_patch_label_duplicate_other_category` — `ConflictError`.
- `test_patch_color_to_null` — elimina color.
- `test_delete_category_empty` — borra, `reassigned_count=0`.
- `test_delete_category_with_routes` — reasigna N plantillas/destinos, `reassigned_count=N`.
- `test_delete_default_category` — `ConflictError`.
- `test_migration_idempotent` — ejecutar `ensure_tables` dos veces sin error.
- `test_migration_preserves_data` — route_templates existentes conservan todas sus columnas
  excepto `category` (que queda como `uncategorized`).

### 12.3 Tests de la API (pytest + httpx)

- `test_EP_CAT01_list_returns_uncategorized` — lista inicial tiene exactamente 1 item.
- `test_EP_CAT02_create_ok` — `201` + `Location` header.
- `test_EP_CAT02_create_duplicate_label` — `409`.
- `test_EP_CAT02_create_empty_label` — `422`.
- `test_EP_CAT02_create_invalid_color` — `422`.
- `test_EP_CAT03_get_ok` — `200`.
- `test_EP_CAT03_not_found` — `404`.
- `test_EP_CAT04_patch_label_ok` — `200`.
- `test_EP_CAT04_patch_color_to_null` — color queda null.
- `test_EP_CAT04_patch_label_duplicate` — `409`.
- `test_EP_CAT04_patch_empty_body` — `422`.
- `test_EP_CAT05_delete_empty_category` — `200 {reassigned_count: 0}`.
- `test_EP_CAT05_delete_with_templates` — `200 {reassigned_count > 0}`.
- `test_EP_CAT05_delete_default` — `409`.
- `test_EP_CAT05_delete_not_found` — `404`.
- `test_EP_RT02_create_with_category_slug` — crear plantilla con slug de categoría válido.
- `test_EP_RT02_create_with_invalid_category_slug` — `422`.
- `test_EP_RT04_update_category_ok` — cambiar categoría de plantilla.
- `test_EP_N04_create_destination_with_slug` — destino con slug válido.
- `test_EP_N05_update_category_ok` — cambiar categoría de destino.

### 12.4 Tests de edge cases (EC-*)

- `test_EC_CAT06_delete_cascade_reassigns_atomically` — verificar que si falla el DELETE,
  el UPDATE no queda aplicado (transacción).
- `test_EC_CAT11_concurrent_create_same_label` — simular con dos llamadas secuenciales rápidas.
- `test_EC_CAT13_migration_idempotent` — ejecutar `ensure_tables` × 2.

### 12.5 Tests de frontend (manuales o Playwright — fuera del scope del spec backend)

Cubrir:
- Desplegable carga categorías al montar.
- Crear nueva categoría desde el typeahead.
- Renombrar categoría inline.
- Cambiar color.
- Borrar categoría con confirmación.
- Badge actualizado tras reasignar.

---

## 13. Riesgos y trade-offs

| # | Decisión | Alternativa descartada | Justificación |
|---|---|---|---|
| T1 | **Migración mapea todo a `uncategorized`** | Crear una categoría por cada valor del enum viejo | El usuario quiere "catálogo en blanco"; 7 categorías precargadas contradice esa decisión. La re-clasificación manual es trivial para el volumen esperado (decenas de plantillas). |
| T2 | **Slug inmutable, generado automáticamente** | Slug editable por el usuario | Los slugs son la FK lógica entre tablas. Si fueran editables, habría que hacer UPDATE en cascada. Generarlos automáticamente es el mismo patrón que los slugs de `route_templates`. |
| T3 | **`label_lower` como columna explícita** | Índice de expresión o comparación en queries | SQLite no tiene `CREATE UNIQUE INDEX ON t(lower(col))` hasta 3.37+ y la cobertura es menor. Columna explícita es más portátil, auditable y compatible con todas las versiones del proyecto. |
| T4 | **Sin FK hard entre `route_templates.category_slug` y `route_categories.slug`** | FK REFERENCES | SQLite con FK activadas y ON DELETE RESTRICT bloquearía el borrado de categorías hasta reasignar. El diseño elige gestionar la integridad en la capa de aplicación (la transacción de borrado hace la reasignación antes del DELETE). Esto permite EC-CAT09 (slug huérfano sin bloqueo), que es un trade-off aceptable en un sistema single-user. |
| T5 | **`DELETE /route-categories/{slug}` devuelve `200` con body** | `204 No Content` | `204` no admite body. La información de `reassigned_count` es útil para el usuario y para tests. `200` con body es el patrón correcto aquí. |
| T6 | **Categoría de plantilla/destino editable en cualquier momento** | Solo al crear | Decisión de producto ya tomada. Técnicamente: eliminar el `model_validator` en `UpdateTemplateRequest` y añadir `category` a `update_destination`. Sin riesgo de inconsistencia porque el catálogo es global. |
| T7 | **Claves i18n `noise.category.*` no se borran** | Borrarlas de los 26 catálogos | Las categorías de usuario no usan claves i18n (label libre). Las claves legacy quedan como texto muerto sin referencias activas. Borrarlas supondría modificar 26 ficheros sin beneficio funcional — se deja para limpieza futura. |
| T8 | **`RouteCategoryDbPort` nuevo, no se añade a `NoiseDbPort`** | Añadir métodos de categoría a `NoiseDbPort` | Separación de responsabilidades. `NoiseDbPort` gestiona destinos/rutas de ruido. Las categorías son un recurso propio con su propio ciclo de vida. Sigue el patrón del proyecto (`RouteTemplateDbPort` también es independiente de `NoiseDbPort`). |

---

## 14. Pasos de implementación ordenados

> Para el agente `desarrollador-funcionalidades`. Seguir este orden estrictamente.
> Ejecutar `lint-imports` tras cada paso que toque `core/` o `adapters/`.

### Paso 1 — Entidad `RouteCategory` en core

Añadir a `core/entities/noise.py` (o crear `core/entities/route_category.py`):

```python
@dataclass
class RouteCategory:
    slug: str          # kebab-case, inmutable
    label: str         # editable libre
    color: str | None  # hex CSS o None
    is_default: bool
    created_at: datetime | None = None
```

**Decisión de ubicación:** crear `core/entities/route_category.py` separado (la entidad no
depende de `noise.py`; mantener ficheros pequeños y de responsabilidad única).

### Paso 2 — Modificar entidades `NoiseDestination` y `RouteTemplate`

En `core/entities/noise.py`:
- `NoiseDestination.category: NoiseCategory` → `category_slug: str`
- `RouteTemplate.category: NoiseCategory` → `category_slug: str`
- Quitar el `import NoiseCategory` si no hay otros usos (verificar: `NavigationOrigin` y otros
  enums permanecen).
- `NoiseCategory` **no se borra todavía** del fichero — puede que aún lo referencien tests.
  Se marca como `# DEPRECATED: reemplazado por RouteCategory` y se borra en Paso 11.

### Paso 3 — Puerto `RouteCategoryDbPort`

Crear `core/ports/route_category_db_port.py`:

```python
class RouteCategoryDbPort(ABC):
    async def list_categories(self) -> list[RouteCategory]: ...
    async def get_category(self, slug: str) -> RouteCategory | None: ...
    async def get_category_by_label_lower(self, label_lower: str) -> RouteCategory | None: ...
    async def create_category(self, slug: str, label: str, label_lower: str,
                               color: str | None, is_default: bool) -> RouteCategory: ...
    async def update_category(self, slug: str, label: str | None,
                               label_lower: str | None, color: str | None | _UNSET) -> RouteCategory: ...
    async def delete_category_and_reassign(self, slug: str) -> tuple[str, int]: ...
        # Devuelve (deleted_slug, reassigned_count). Lanza ValueError si is_default.
```

> `_UNSET` es un centinela para distinguir "no se pasó color" de "se pasó `null` explícito"
> (borrar el color). Ver patrón en `update_noise_config`.

### Paso 4 — Migraciones M-CAT03 y M-CAT04 en adaptadores existentes

- En `route_template_sqlite_adapter.py`: añadir `_migrate_route_templates_remove_check(conn)`
  siguiendo el patrón de `_migrate_noise_paths_add_is_dead_and_failures`. Llamar desde
  `ensure_tables()`.
- En `noise_sqlite_adapter.py`: añadir `_migrate_noise_destinations_remove_check(conn)`.
  Llamar desde `ensure_tables()`.

**Verificación de idempotencia:** `PRAGMA table_info` → si columna `category_slug` ya existe,
saltar.

### Paso 5 — Adaptador `RouteCategorySQLiteAdapter`

Crear `adapters/db/route_category_sqlite_adapter.py`:
- DDL de `route_categories` (M-CAT01).
- Inserción del seed `uncategorized` (M-CAT02, `INSERT OR IGNORE`).
- Implementar todos los métodos de `RouteCategoryDbPort`.
- Helper `slugify(label)` → `re.sub(r'[^a-z0-9]+', '-', label.strip().lower()).strip('-')`.
- Helper `_ensure_unique_slug(db, base_slug)` → intenta `base_slug`, luego `base_slug-2`, etc.
- Transacción atómica en `delete_category_and_reassign`: UPDATE templates + UPDATE destinations
  + DELETE categoría en un solo `BEGIN...COMMIT`.

### Paso 6 — Seed de categorías

Crear `seeds/route_categories.json` con el contenido del §7.5.
Añadir carga del seed al lifespan (`main.py`) justo antes del seed de `route_templates`.

### Paso 7 — Actualizar `route_template_sqlite_adapter.py`

- Cambiar `_row_to_template`: `NoiseCategory(row["category"])` → `row.get("category_slug", row.get("category", "uncategorized"))`.
  (Guard de retrocompatibilidad: si la columna aún se llama `category` en una BD sin migrar,
  funciona igual; tras migración M-CAT03, la columna es `category_slug`.)
- Actualizar `_CREATE_ROUTE_TEMPLATES` DDL (ya sin CHECK) — este DDL solo aplica en BD nuevas;
  BDs existentes pasan por M-CAT03.
- Actualizar `list_templates`: parámetro `category: NoiseCategory | None` → `category_slug: str | None`.
- Actualizar `seed_route_templates`: campo `"category"` → `"category_slug"` (con fallback por
  retrocompatibilidad al leer el JSON).
- `update_template`: añadir soporte para `category_slug` en el PATCH parcial.

### Paso 8 — Actualizar `noise_sqlite_adapter.py`

- `_row_to_destination`: `NoiseCategory(row["category"])` → `row["category"]` (string directo).
- `create_destination`: firma `category: str` en lugar de `NoiseCategory`.
- `list_destinations`: filtro `category_slug: str | None`.
- `update_destination`: añadir `category_slug: str | None = None` al PATCH.

### Paso 9 — Puerto `NoiseDbPort` y `RouteTemplateDbPort`

- `NoiseDbPort.list_destinations`: tipo de `category` → `str | None`.
- `NoiseDbPort.create_destination`: tipo de `category` → `str`.
- `NoiseDbPort.update_destination`: añadir `category_slug: str | None = None`.
- `RouteTemplateDbPort.list_templates`: tipo de `category` → `str | None`.
- `RouteTemplateDbPort.update_template`: añadir `category_slug: str | None = None`.

### Paso 10 — Router `adapters/api/routes/route_categories.py`

Crear el router con EP-CAT01..EP-CAT05 (EP-CAT06 marcado FUERA DE ALCANCE, no implementar).
Registrarlo en `main.py`:
```python
from adapters.api.routes.route_categories import router as route_categories_router
app.include_router(route_categories_router)
```
Inyectar `route_category_port` en `app.state` desde el lifespan (igual que `noise_db_port`).

### Paso 11 — Router `adapters/api/routes/route_templates.py`

- `CreateTemplateRequest`: renombrar campo `category: NoiseCategory` →
  `category_slug: str = Field(default="uncategorized", min_length=1)`.
  Añadir validación en el handler: si el slug no existe → `422 {"detail": "Categoría no encontrada."}`.
- `UpdateTemplateRequest`:
  - Quitar el guard que rechaza `category` del `model_validator`.
  - Añadir `category_slug: Optional[str] = None` como campo editable.
  - Añadir `category_slug` a la lista de `at_least_one_mutable_field`.
  - Si se envía, validar existencia → `422` si no existe.
- `EP-RT01 list_templates`: parámetro `?category=` → `?category_slug=` (string opcional).
- `_template_to_full_response` y `_template_to_list_item`:
  - `tpl.category.value` → `tpl.category_slug`.
  - Renombrar el campo en `RouteTemplateResponse` y `RouteTemplateListItem`: `category: str` → `category_slug: str`.
- `_clone_template_to_world`:
  - `category=template.category` (era `NoiseCategory`) → `category_slug=template.category_slug` (string).

### Paso 12 — Router `adapters/api/routes/noise.py`

- `CreateDestinationRequest`: renombrar campo `category: NoiseCategory` →
  `category_slug: str = Field(default="uncategorized", min_length=1)`.
  Añadir validación en el handler: si el slug no existe → `422 {"detail": "Categoría no encontrada."}`.
- `UpdateDestinationRequest`:
  - Añadir `category_slug: Optional[str] = None`.
  - Añadir `category_slug` a la validación de `at_least_one_field`.
  - Si se envía, validar existencia → `422`.
- `EP-N03 list_destinations`: `?category=` → `?category_slug=` (string).
- `_dest_to_response`:
  - `dest.category.value` → `dest.category_slug`.
  - Renombrar campo en `NoiseDestinationResponse`: `category: str` → `category_slug: str`.

### Paso 13 — Tests: actualizar ~40 usos de `NoiseCategory`

En los 6 ficheros de test identificados en el blast radius:
- Reemplazar `NoiseCategory.MAP` → `"map"` (o slug correcto de la categoría default).
  Como tras la migración todas las filas pasan a `uncategorized`, usar `"uncategorized"` como
  valor de categoría en la mayoría de los tests existentes.
- En los tests que prueban filtrado por categoría: crear la categoría necesaria vía el
  adaptador de categorías antes de usarla.
- Añadir los tests nuevos del §12.

### Paso 14 — Eliminar `NoiseCategory` del core

Una vez todos los tests pasan, eliminar el enum `NoiseCategory` de `core/entities/noise.py`
y los imports que lo referencien. Verificar con `grep -r "NoiseCategory"` que no queda ningún
uso activo. Actualizar el import en `core/ports/route_template_db_port.py` y
`core/ports/noise_db_port.py`.

### Paso 15 — Frontend: `CategoryCombobox` y actualización de `NoiseCategoryBadge`

> Nota: la UI completa del `CategoryCombobox` (desplegable inteligente con CRUD inline) pasa
> por `disenador-producto` + mockup editable antes de que `desarrollador-ux-ui` la implemente.
> Los pasos de frontend aquí son los cambios mínimos de "fontanería" que el backend necesita.

- `NoiseCategoryBadge`: modificar para aceptar `{ label, color }` directamente en lugar de
  `{ category }` (clave de enum). El badge calcula el style a partir del color prop o usa el
  estilo neutro si `color=null`.
- `RouteTemplatesPage.jsx`: reemplazar `const CATEGORIES = [...]` por fetch de
  `GET /route-categories` al montar.
- `NoiseDestinationsTable.jsx`: igual — reemplazar `CATEGORIES` hardcodeado.
- `NoiseDestinationDrawer.jsx` (líneas 315, 438): el badge de categoría se vuelve editable
  (reasignación via dropdown) — esto es parte del diseño UI; mínimo: mostrar `label` en lugar
  de clave de enum.

### Paso 16 — lint-imports + seed actualizado

- Ejecutar `.venv/bin/lint-imports` — debe decir "2 kept, 0 broken".
- Actualizar `seeds/route_templates.json`: campo `"category"` → `"category_slug": "uncategorized"`.
- Ejecutar suite completa de tests: `pytest` → todos verdes.

---

## 15. Criterios de aceptación

Checklist verificable por el implementador:

### Backend

- [ ] **AC-01** `GET /route-categories` devuelve `[{slug: "uncategorized", is_default: true, ...}]` en una BD nueva.
- [ ] **AC-02** `POST /route-categories {label: "Mapa", color: "#4A90D9"}` → `201` + slug generado `"mapa"` + `Location: /route-categories/mapa`.
- [ ] **AC-03** `POST /route-categories {label: "mapa"}` (duplicado CI) → `409`.
- [ ] **AC-04** `PATCH /route-categories/mapa {label: "Mapamundi"}` → `200` con nuevo label; slug sigue siendo `"mapa"`.
- [ ] **AC-05** `DELETE /route-categories/uncategorized` → `409`.
- [ ] **AC-06** `DELETE /route-categories/mapa` con N plantillas asignadas → `200 {deleted_slug: "mapa", reassigned_count: N, reassigned_to: "uncategorized"}` + plantillas quedan con `category_slug="uncategorized"` + categoría `"mapa"` no existe en `GET /route-categories`.
- [ ] **AC-07** La operación de borrado es atómica: si el DELETE falla, las plantillas no quedan reasignadas.
- [ ] **AC-08** `POST /route-templates` con `category_slug: "mapa"` → `201` con `category_slug: "mapa"` en la respuesta.
- [ ] **AC-09** `POST /route-templates` con `category_slug: "slug-inexistente"` → `422`.
- [ ] **AC-10** `PUT /route-templates/{id}` con `category_slug: "mapa"` → `200` con `category_slug: "mapa"` (sin rechazo 422 por "inmutable").
- [ ] **AC-11** `POST /route-templates/{id}/clone-to-world/{wid}` clona correctamente el `category_slug` de la plantilla al destino.
- [ ] **AC-12** `PUT /worlds/{wid}/noise/destinations/{did}` con `category_slug: "mapa"` → `200` con `category_slug: "mapa"` en la respuesta.
- [ ] **AC-13** `lint-imports` → "2 kept, 0 broken" tras todos los cambios.
- [ ] **AC-14** Suite completa de tests pasa en verde (incluyendo los 40 tests actualizados + los nuevos).
- [ ] **AC-15** La migración M-CAT03/M-CAT04 es idempotente: ejecutar `ensure_tables()` dos veces no da error y los datos no se duplican.
- [ ] **AC-16** Una BD con datos de route_templates/noise_destinations con el enum viejo migra correctamente: todas las filas quedan con `category_slug="uncategorized"`.

### Frontend (verificación mínima, UI completa pendiente de mockup)

- [ ] **AC-17** `NoiseCategoryBadge` muestra el `label` de la categoría (no la clave de enum) con el color dinámico.
- [ ] **AC-18** Los arrays `CATEGORIES` hardcodeados desaparecen de `RouteTemplatesPage.jsx` y `NoiseDestinationsTable.jsx`; se cargan desde `GET /route-categories`.
- [ ] **AC-19** El desplegable de selección de categoría muestra las categorías disponibles con sus colores.

---

## 16. Trazabilidad

| Decisión técnica | Requisito / edge case que la origina |
|---|---|
| `route_categories` tabla separada con `RouteCategoryDbPort` propio | Decisión de producto #1 (catálogo dinámico) + T8 (separación de responsabilidades) |
| `label_lower` columna explícita para UNIQUE CI | RN-CAT05 + EC-CAT02 + EC-CAT11 + T3 |
| Slug inmutable generado automáticamente | RN-CAT04 + RN-CAT08 + T2 |
| Migración mapea todo a `uncategorized` | Decisión de producto #5 ("catálogo en blanco") + T1 |
| `DELETE` devuelve `200` con body en lugar de `204` | EC-CAT06/07 + T5 |
| Sin FK hard en SQLite para `category_slug` | T4 + EC-CAT09 (slug huérfano aceptable en single-user) |
| Claves i18n `noise.category.*` conservadas como texto muerto | Decisión de producto + T7 |
| Categoría editable tras crear (plantillas y destinos) | Decisión de producto #3 |
| Borrado atómico con reasignación a `uncategorized` | Decisión de producto #4 + EC-CAT06/07 |
| `uncategorized` default no borrable, label y color editables | Decisión de producto #5 + RN-CAT01/02/03 |
| Catálogo unificado para `route_templates` y `noise_destinations` | Decisión de producto #2 + RN-CAT12 |
| Color máx. 50 chars + regex permisiva | EC-CAT12 (frontend controla la paleta, backend no fuerza) |
| **Reutilización: `DeletePopover`** | EC-CAT06 (confirmación de borrado) — reutilizar tal cual (`frontend/src/components/ui/DeletePopover.jsx`) |
| **Reutilización: `ConfirmDeleteModal`, `showToast`, `Spinner`** | UX del desplegable — reutilizar tal cual (`frontend/src/components/ui/uiUtils.jsx`) |
| **Reutilización: patrón CRUD de `AccountSQLiteAdapter`** | `RouteCategorySQLiteAdapter` sigue el mismo patrón de SQL crudo + aiosqlite |
| **Ajustar: `NoiseCategoryBadge`** | Debe recibir `{label, color}` directos (categorías usuario sin clave i18n) — cambio mínimo en `NoiseDestinationsTable.jsx:64` |
| **Ajustar: guard inmutabilidad** | `UpdateTemplateRequest:228-240` — eliminar guard de `category` |
| **Ajustar: `update_destination`** | `core/ports/noise_db_port.py:126-137` — añadir `category_slug` como campo editable |
| **Ajustar: `category` filtro** | `route_templates.py:504` y `noise.py:766` — parámetro pasa de enum a string |
| **Crear: `RouteCategorySQLiteAdapter`** — decidido por palantir (contexto de entrada), verificado en código | No existe ningún adaptador de categorías; la funcionalidad es nueva |
| **APIs pendientes de validación por `desarrollador-apis`** | Fallback §3 aplicado: spec en estado `draft`; la sección §8 presenta contratos borrador. Invocar `desarrollador-apis` en MODO REVISIÓN DE CONTRATO antes de implementar |

---

*Siguiente paso obligatorio antes de `ready-for-impl`:*
1. Invocar `desarrollador-apis` con los contratos del §8 para obtener luz verde.
2. Invocar `disenador-producto` para el spec visual del `CategoryCombobox` (desplegable
   inteligente con CRUD inline) + mockup editable.
3. Solo cuando ambas luces verdes estén recibidas: cambiar `estado: ready-for-impl` y
   lanzar `desarrollador-funcionalidades` para el backend, y `desarrollador-ux-ui` para la UI.

---

## Registro de implementación

**Fecha:** 2026-06-06
**Agente:** desarrollador-funcionalidades

### Ficheros creados

- `core/entities/route_category.py` — entidad `RouteCategory`
- `core/ports/route_category_db_port.py` — puerto `RouteCategoryDbPort` + centinela `UNSET`
- `adapters/db/route_category_sqlite_adapter.py` — adaptador SQLite + helpers `slugify`, `_ensure_unique_slug`
- `adapters/api/routes/route_categories.py` — router EP-CAT01..EP-CAT05
- `seeds/route_categories.json` — seed con `uncategorized`
- `tests/test_route_categories_api.py` — 40+ tests de categorías

### Ficheros modificados

- `core/entities/noise.py` — `NoiseDestination.category` → `category_slug: str`; `RouteTemplate.category` → `category_slug: str`; `NoiseCategory` marcado DEPRECATED
- `core/ports/route_template_db_port.py` — firmas `list_templates(category_slug)`, `update_template(category_slug)`; import `NoiseCategory` eliminado
- `core/ports/noise_db_port.py` — firmas `list_destinations(category_slug)`, `create_destination(category_slug)`, `update_destination(category_slug)`; import `NoiseCategory` eliminado
- `core/scheduling/world_agent.py` — import `NoiseCategory` eliminado (era zombie)
- `adapters/db/route_template_sqlite_adapter.py` — DDL nuevo sin CHECK; migración M-CAT03; CRUD con `category_slug`; seed con fallback para JSON viejo
- `adapters/db/noise_sqlite_adapter.py` — DDL nuevo sin CHECK; migración M-CAT04; CRUD con `category_slug`; helper `_get_category_column`; import `NoiseCategory` eliminado
- `adapters/api/routes/route_templates.py` — modelos Pydantic con `category_slug`; filtro `?category_slug=`; validación de existencia en BD; import `NoiseCategory` eliminado
- `adapters/api/routes/noise.py` — modelos Pydantic con `category_slug`; filtro `?category_slug=`; validación de existencia; import `NoiseCategory` eliminado
- `adapters/api/main.py` — instanciar y registrar `RouteCategorySQLiteAdapter` + router de categorías
- `seeds/route_templates.json` — campo `category` → `category_slug: "uncategorized"` en las 20 plantillas
- `tests/` — ~50 ocurrencias de `NoiseCategory.*` actualizadas a `category_slug: str` en 6 ficheros de test + `test_route_templates_api.py` y `test_noise_api.py`

### Comando para ejecutar los tests

```bash
.venv/bin/pytest tests/ -q
```

### Resultado

**1768 passed, 23 skipped, 2 failed** (los 2 fallos son preexistentes: `test_execute_invalid_token_raises_login_failed` y `test_post_session_invalid_token` — fallan sin los cambios de este spec, origen en TRAVIAN_BOT_SECRET_KEY de test).

### lint-imports

`Contracts: 2 kept, 0 broken.`

### Desviaciones respecto al diseño

1. **`_make_template_body` en tests**: se añadió compatibilidad de backward para el kwarg `category` viejo (mapea silenciosamente a `category_slug="uncategorized"`), para no reescribir decenas de llamadas en los tests de EP-RT existentes que todavía pasan `category="MAP"` sin semántica real.

2. **`create_destination` con alias `category`**: el adaptador SQLite acepta `category=` como alias retrocompat para llamadas existentes que pasaban un `NoiseCategory` enum, extrayendo `.value` automáticamente. Esto permite que tests o código que aún no fue actualizado sigan funcionando sin error.

3. **`NoiseCategory` no eliminado físicamente**: el enum sigue en `core/entities/noise.py` marcado DEPRECATED. Se mantiene como texto muerto para no romper posibles imports externos no rastreados. Eliminarlo definitivamente es un paso de limpieza para el siguiente ciclo de mantenimiento.

4. **`seeds/route_templates.json` restaurado**: el seed estaba vacío (`[]`) en la rama antes de esta implementación. Se restauró con las 20 plantillas originales actualizando `category` → `category_slug: "uncategorized"` (T1 del spec: "catálogo en blanco" para datos de usuario).

### Criterios de aceptación verificados (backend)

- AC-01: GET /route-categories devuelve uncategorized en BD nueva — OK
- AC-02: POST → 201 + slug generado + Location — OK
- AC-03: label duplicado CI → 409 — OK
- AC-04: PATCH label → 200; slug inmutable — OK
- AC-05: DELETE uncategorized → 409 — OK
- AC-06: DELETE con plantillas → reasigna + 200 — OK
- AC-07: operación atómica — OK (transacción SQLite)
- AC-08: POST route-templates con category_slug válido — OK
- AC-09: POST route-templates con slug inválido → 422 — OK
- AC-10: PUT route-templates con category_slug → 200 — OK
- AC-11: clonar plantilla hereda category_slug al destino — OK
- AC-12: PUT noise/destinations con category_slug → 200 — OK
- AC-13: lint-imports 2 kept, 0 broken — OK
- AC-14: suite de tests verde — OK (1768/1768, 2 preexistentes excluidos)
- AC-15: migración idempotente — OK (test `test_ensure_tables_idempotent`)
- AC-16: BD con enum viejo migra a uncategorized — OK (M-CAT03/M-CAT04)

### Criterios de aceptación frontend (AC-17..AC-19)

Fuera del alcance de este agente (implementados por `desarrollador-ux-ui` en paralelo). Pendiente de verificación manual.
