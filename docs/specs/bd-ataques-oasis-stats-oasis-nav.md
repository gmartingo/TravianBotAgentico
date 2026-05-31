---
id: bd-ataques-oasis-stats-oasis-nav
titulo: "Prueba manual bd-ataques-oasis: fix panel stats, iconos héroe, ratio regen/hora y lista de oasis navegable"
estado: implemented
fecha: 2026-05-31
autor: analista
apis_validadas_por_desarrollador_apis: true
---

# bd-ataques-oasis — Correcciones y mejoras surgidas de prueba manual

> **SPEC DE CAMBIO sobre `bd-ataques-oasis` (estado: implemented) y `bd-ataques-oasis-fix-hora-balance` (estado: ready-for-impl).**
>
> Cubre cuatro cambios descubiertos con 5 reportes reales del oasis (-70|73):
> - **BUG 1** — panel de estadísticas no muestra datos por desajuste de nombres de campo (frontend).
> - **BUG 2** — inventario del héroe usa emojis en vez de iconos del juego.
> - **MEJORA 1** — ratio de regeneración por hora por animal (nuevo campo en EP-06).
> - **MEJORA 2** — lista de oasis navegable con filtro por coordenadas (nuevo endpoint EP-08).
>
> **Dependencia:** los cálculos de `gap_seconds` en MEJORA 1 son correctos solo si
> `attacked_at` está en formato verbatim (naive). Aplicar `bd-ataques-oasis-fix-hora-balance`
> ANTES o en el mismo commit que este spec.
>
> **Pendiente de validación por `desarrollador-apis`** para:
> - Campo nuevo `animal_regen_rates` en la respuesta de EP-06 (cambio de contrato existente).
> - Endpoint nuevo EP-08 `GET /attack-reports/oasis`.

---

## 1. Objetivo de negocio

Tras la prueba manual con datos reales, emergen dos bugs visuales (panel de stats vacío,
emojis en lugar de iconos) y dos mejoras de producto:

1. El panel de estadísticas del oasis (-70|73) renderiza tablas vacías porque el frontend
   lee nombres de campo que no existen en la respuesta de la API (`count`, `avg`, `max`,
   `min`, `animal_regeneration`). Los nombres reales son `appearances`, `avg_present`,
   `max_present`, `min_present`, y la regeneración viene como lista no como dict.

2. El inventario del héroe en el drawer de detalle usa emojis del sistema operativo
   (🪵🧱⛏🌾) que rompen la coherencia visual con el resto de la app, que usa iconos
   reales de Travian desde `/api/static/icons/`.

3. El usuario quiere saber cuántos animales de cada tipo se regeneran por hora en un oasis
   (basándose en los intervalos que ya existen en `repopulation_gaps`), para optimizar la
   cadencia de ataques.

4. El usuario quiere una lista de los oasis con reportes (no solo consultar por coordenadas
   manualmente) y poder navegar directamente a las estadísticas de cada uno.

---

## 2. Actores y permisos

Sin cambios respecto a los specs base. Usuario único, local, sin autenticación.

---

## 3. Alcance

### Dentro del alcance

- **BUG 1**: Corrección de `OasisStatsPanel.jsx` — nombres de campo en `AnimalsTable` y
  transformación lista→dict en `RepopTable`.
- **BUG 2**: Sustitución de emojis por `ResIcon` en `HeroInventory` de `ReportDetailDrawer.jsx`.
- **MEJORA 1**: Añadir campo `animal_regen_rates` a la respuesta de `get_oasis_stats`
  (adaptador + puerto abstracto); actualización de EP-06 (cambio de contrato, pendiente
  gate de `desarrollador-apis`).
- **MEJORA 2**: Método `list_oasis_summaries` en el adaptador; método abstracto en el
  puerto; endpoint EP-08 `GET /attack-reports/oasis`; actualización del frontend
  (pestaña Estadísticas) delegada a `disenador-producto` + `desarrollador-ux-ui` bajo
  la regla mockup-first.

### Fuera del alcance

- Pantalla nueva de la lista de oasis navegable: el CÓMO visual lo diseña
  `disenador-producto` con su mockup editable, y lo implementa `desarrollador-ux-ui`.
  Este spec solo define el QUÉ funcional y el contrato de datos disponibles.
- Filtros adicionales en EP-08 (por tipo de animal, por fecha, por botín mínimo).
- Estadísticas comparativas entre oasis.
- Exportación o descarga de datos.

---

## 4. Reglas de negocio

### RN-BUG1-A — Nombres de campo en AnimalsTable

La respuesta de EP-06 (`GET /attack-reports/stats/oasis`) devuelve
`animal_appearances[*]` con estos campos:

| Campo API | Campo erróneo leído por el frontend | Corrección |
|---|---|---|
| `appearances` | `count` | Usar `row.appearances` |
| `avg_present` | `avg` | Usar `row.avg_present` |
| `max_present` | `max` | Usar `row.max_present` |
| `min_present` | `min` | Usar `row.min_present` |

Dato real de referencia (oasis -70|73, 5 reportes):
- Rata (`animal_ordinal=1`): `appearances=4`, `avg_present=9.25`, `max_present=14`, `min_present=7`.

**Decisión:** la API tiene tests; el frontend se alinea a ella, no al revés.

### RN-BUG1-B — Transformación lista→dict en RepopTable

La respuesta de EP-06 devuelve `repopulation_gaps[*].regenerated_animals` como **lista**:

```json
"regenerated_animals": [
  { "animal_ordinal": 1, "animal_name": "Rata", "prev_survived": 3, "present_now": 12, "regenerated": 9 },
  { "animal_ordinal": 2, "animal_name": "Araña", "prev_survived": 0, "present_now": 0, "regenerated": 0 }
]
```

El frontend (`RepopTable`) necesita acceder al valor por nombre de animal para cada columna
dinámica. Actualmente lee `row.animal_regeneration?.[name]` esperando un dict por nombre
— eso siempre es `undefined` porque el campo se llama `regenerated_animals` y es lista.

**Corrección:** antes de renderizar la tabla, transformar la lista a dict una sola vez:

```js
// Para cada gap row, construir: { "Rata": 9, "Araña": 0, ... }
const regenByName = Object.fromEntries(
  (row.regenerated_animals ?? []).map((a) => [a.animal_name, a.regenerated])
)
// Usar: regenByName[name] ?? null
```

La transformación se hace en el render de `RepopTable`, no en el cuerpo del componente
padre, para que no haya estado adicional.

### RN-BUG2 — ResIcon en HeroInventory

El componente `HeroInventory` en `ReportDetailDrawer.jsx` (~líneas 45-74) construye una
lista con emojis del OS como label de cada recurso. Debe reutilizar `ResIcon` exportado
desde `frontend/src/components/combat/TravianReport.jsx`.

`ResIcon` acepta `res` (string: "wood"/"clay"/"iron"/"crop"), `size` (default 16) y
`label` (alt text). La nueva lista queda:

```jsx
import { ResIcon } from '../combat/TravianReport.jsx'

const items = [
  { res: 'wood', value: inv.wood },
  { res: 'clay', value: inv.clay },
  { res: 'iron', value: inv.iron },
  { res: 'crop', value: inv.crop },
].filter((i) => i.value != null && i.value > 0)

// En el render:
{items.map(({ res, value }) => (
  <span key={res} style={{ display: 'flex', alignItems: 'center', gap: '3px', fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums' }}>
    {value.toLocaleString()}
    <ResIcon res={res} size={14} />
  </span>
))}
```

La key pasa de `label` (el emoji) a `res` (string estable como "wood").
El `label` del emoji deja de existir; el alt text lo provee `ResIcon` automáticamente.

### RN-REGEN1 — Definición de ratio de regeneración por hora

**Qué es:** por cada animal, el promedio de la tasa de regeneración (animales/hora) calculado
sobre todos los intervalos válidos entre ataques consecutivos al mismo oasis.

**Fórmula por intervalo válido:**

```
tasa_intervalo = regenerated / (gap_seconds / 3600)
```

**Promedio sobre intervalos válidos:**

```
avg_regen_per_hour = mean(tasa_intervalo para cada intervalo válido)
```

**Intervalo válido** = cumple TODAS estas condiciones:
1. `gap_seconds > 0` (excluir gaps nulos o cero).
2. `regenerated` no es `None` (el primer ataque por definición no tiene regeneración).
3. `regenerated >= 0` (un `regenerated` negativo — menos animales que los que sobrevivieron
   el ataque anterior — indica una irregularidad: el usuario no mató todo en el ataque
   anterior, o hubo actividad externa en el oasis. Estos intervalos se excluyen del
   promedio porque contaminan la señal de regeneración natural. Un 0 es válido: significa
   que no regeneró nada en ese intervalo).

**Animal que nunca aparece** (present siempre 0): no tendrá entradas en
`animal_appearances`, y por tanto no figurará en `animal_regen_rates`. Si tiene entradas
con `regenerated >= 0` pero `present=0` en todos los reportes, el ratio será 0.

**Oasis con < 2 ataques**: sin intervalos válidos → `animal_regen_rates = []` (lista vacía).

**Dependencia:** los `gap_seconds` son correctos solo con `attacked_at` verbatim (spec
`bd-ataques-oasis-fix-hora-balance`). Si esa corrección no está aplicada, los ratios
pueden estar desfasados hasta 2 horas por el bug de zona horaria.

### RN-REGEN2 — Dónde se calcula el ratio

**Decisión: Python puro en `get_oasis_stats`, no SQL nuevo.**

Justificación:
- `repopulation_gaps` con todos los campos necesarios (`gap_seconds`, `regenerated_animals`)
  ya está calculado y materializado en memoria en ese método.
- Añadir SQL adicional con funciones de ventana sobre ratios flotantes sería más complejo
  de mantener y testear que un bucle Python sobre los datos ya cargados.
- El volumen es pequeño (decenas a pocos cientos de filas por oasis) — sin impacto de rendimiento.
- El campo nuevo es additive (se añade a la respuesta existente sin romper nada).
- El cálculo es testeable de forma unitaria pasando fixtures de `repopulation_gaps`.

### RN-NAV1 — Resumen de oasis para la lista navegable

El método `list_oasis_summaries` devuelve una lista de oasis únicos con:

```
{ coord_x_dest, coord_y_dest, attack_count, last_attack, total_bounty }
```

- `attack_count`: número de reportes para ese oasis.
- `last_attack`: `MAX(attacked_at)` — el ataque más reciente (string verbatim).
- `total_bounty`: suma de `bounty_wood + bounty_clay + bounty_iron + bounty_crop`.
  Tipo **integer >= 0** (no float): la query usa `COALESCE(SUM(...), 0)` sobre enteros de BD.
  [Corrección desarrollador-apis #4]
- Ordenación por defecto: `last_attack DESC` (el oasis atacado más recientemente primero).

Filtros opcionales:
- `?x=` y `?y=` — si se pasan AMBOS, devuelve solo el oasis con esas coordenadas exactas
  (máximo 1 resultado). Si se pasa uno solo → 400. Si están fuera de rango → 422.

El filtro x/y en EP-08 reutiliza la validación combinatoria ya establecida en el proyecto
(ambos o ninguno → 400; fuera de -400..400 → 422).

### RN-NAV2 — Navegación a estadísticas

Al hacer clic en un oasis de la lista, la UI navega (o muestra inline) las estadísticas
de ese oasis usando EP-06 con las coordenadas seleccionadas. El spec del CÓMO visual
corresponde a `disenador-producto`.

---

## 5. Flujo principal y flujos alternativos

### BUG 1 — Flujo corregido (frontend only)

```
Usuario abre pestaña Estadísticas → StatsTab llama EP-06 →
EP-06 devuelve { animal_appearances: [...], repopulation_gaps: [...] } →
OasisStatsPanel.jsx:
  AnimalsTable lee row.appearances / row.avg_present / row.max_present / row.min_present  [CORREGIDO]
  RepopTable transforma regenerated_animals[] → dict por nombre antes de renderizar       [CORREGIDO]
→ Tabla muestra datos reales del oasis (-70|73)
```

### BUG 2 — Flujo corregido (frontend only)

```
Usuario abre ReportDetailDrawer →
HeroInventory construye items con { res: 'wood'|..., value: N } →
Renderiza con ResIcon (icono png del juego) en lugar de emoji del OS
```

### MEJORA 1 — Ratio regen/hora

```
GET /attack-reports/stats/oasis?x=-70&y=73 →
get_oasis_stats(x, y) en adaptador:
  1. Calcula repopulation_gaps (como ahora)
  2. NUEVO: calcula animal_regen_rates a partir de repopulation_gaps
  3. Añade animal_regen_rates a la respuesta
→ Response incluye campo nuevo animal_regen_rates: [...]
→ OasisStatsPanel puede mostrar ese dato (diseño UI pendiente de disenador-producto)
```

### MEJORA 2 — Lista de oasis

```
GET /attack-reports/oasis          → lista todos los oasis con reportes
GET /attack-reports/oasis?x=-70&y=73 → filtra por coordenadas exactas (1 resultado)
→ Usuario hace clic en un oasis de la lista
→ UI llama EP-06 con las coords del oasis seleccionado
→ Muestra estadísticas expandidas
```

### Flujo alternativo — oasis sin reportes

```
GET /attack-reports/oasis?x=-99&y=-99 (coords sin reportes)
→ 200 OK con lista vacía: { "items": [], "total": 0 }
```

---

## 6. Edge cases

| ID | Caso | Tratamiento |
|---|---|---|
| EC-BUG1-A | `animal_appearances` vacío (oasis con 0 ataques) | `AnimalsTable` ya maneja `appearances.length === 0` con `return null`. Sin cambios. |
| EC-BUG1-B | `regenerated_animals` vacío en un gap (primer ataque del oasis) | `Object.fromEntries([])` → `{}`. La celda lee `regenByName[name] ?? null` → `null` → `RegenCell` muestra "—". |
| EC-BUG1-C | Animal en columna no presente en `regenerated_animals` de ese gap | `regenByName[name]` → `undefined` → `?? null` → "—". Correcto. |
| EC-BUG2-A | `hero_inventory` es null (sin inventario del héroe) | `HeroInventory` ya devuelve el mensaje "Sin inventario". Sin cambios. |
| EC-BUG2-B | Valor de recurso es 0 o null en el inventario | El `.filter` de items excluye valor null y > 0. Solo los recursos con valor > 0 se muestran con icono. |
| EC-REGEN-A | `gap_seconds = 0` | Excluir del promedio. No aplicar división por cero. |
| EC-REGEN-B | `gap_seconds = null` (primer ataque: LAG devuelve NULL) | `regenerated` también será NULL. El intervalo queda excluido por la condición `regenerated is not None`. |
| EC-REGEN-C | `regenerated < 0` (bajas sin matar todo el oasis, actividad externa) | Excluir del promedio. Estos valores no representan regeneración natural y contaminarían el promedio. Nota: el dato negativo se conserva en `regenerated_animals` para quien lo quiera analizar; solo se excluye del *promedio* del ratio. |
| EC-REGEN-D | `regenerated = 0` (no regeneró en ese intervalo) | Incluir en el promedio con tasa 0. Un oasis que tardó mucho en regenerar a cero es información válida. |
| EC-REGEN-E | Oasis con exactamente 1 ataque | 0 intervalos válidos → `animal_regen_rates = []`. |
| EC-REGEN-F | Oasis con 2 ataques, pero el primer gap tiene `regenerated < 0` para todos los animales | Todos los intervalos filtrados → `animal_regen_rates = []` (o lista con `avg_regen_per_hour = null`). Decisión: si un animal tiene 0 intervalos válidos, excluirlo de la lista (no incluir null). Lista vacía es más limpia. |
| EC-REGEN-G | Oasis con 0 ataques (consultado en EP-06) | `repopulation_gaps = []` → `animal_regen_rates = []`. Ya cubierto por el cuerpo de "cero ataques" del adaptador. |
| EC-NAV-A | `GET /attack-reports/oasis` sin datos en BD | 200 OK con `{ "items": [], "total": 0 }`. |
| EC-NAV-B | `GET /attack-reports/oasis?x=-70` (falta y) | 400 con `"detail": "Parámetro 'x' requiere 'y' y viceversa."` |
| EC-NAV-C | `GET /attack-reports/oasis?x=999&y=73` (fuera de rango) | 422 (FastAPI automático, `ge=-400, le=400`). |
| EC-NAV-D | `GET /attack-reports/oasis?x=-70&y=73` con 0 reportes para esas coords | 200 con `{ "items": [], "total": 0 }`. No es 404. |

---

## 7. Modelo de datos / cambios de esquema

**No hay cambios de DDL.** Las 3 tablas existentes (`attack_reports`,
`attack_report_attacker_troops`, `attack_report_animals`) cubren todos los datos
necesarios.

Los nuevos datos (`animal_regen_rates`, `list_oasis_summaries`) se calculan en Python
o en SQL de lectura usando el esquema ya existente.

---

## 8. Contratos de API / interfaces

> **PENDIENTE DE VALIDACIÓN POR `desarrollador-apis`** (gate obligatorio antes de
> marcar este spec como `apis_validadas_por_desarrollador_apis: true`).
>
> Instrucción para el orquestador al lanzar el gate:
> "MODO REVISIÓN DE CONTRATO DE DISEÑO. No implementes nada: no escribas código ni tests
> ni toques el repositorio. Primero busca en las APIs ya existentes del proyecto y decide,
> por cada necesidad, si hay que REUTILIZAR un endpoint existente, MODIFICARLO con un
> cambio mínimo, o CREAR uno nuevo (priorizando la reutilización). Después valida —y
> corrige si hace falta— el DISEÑO del contrato resultante según tus estándares. Devuélveme:
> (1) la decisión de reutilización por necesidad, (2) veredicto CORRECTO o INCORRECTO,
> (3) los contratos corregidos si procede, (4) tu LUZ VERDE explícita para guardar el spec."

### EP-06 — Cambio de contrato (campo nuevo `animal_regen_rates`)

Endpoint existente: `GET /attack-reports/stats/oasis?x=<int>&y=<int>`

**Cambio:** adición de campo `animal_regen_rates` a la respuesta (cambio aditivo,
retrocompatible — los clientes que no lo lean siguen funcionando).

**Contrato propuesto del campo nuevo:**

```json
// En la respuesta de EP-06, añadir tras "repopulation_gaps":
"animal_regen_rates": [
  {
    "animal_ordinal": 1,
    "animal_name": "Rata",
    "avg_regen_per_hour": 4.72,
    "valid_intervals": 3
  },
  ...
]
```

Campos:
- `animal_ordinal` — integer, ordinal del animal (1-10, consistente con el resto de la respuesta).
- `animal_name` — string, nombre del animal en el idioma del catálogo.
- `avg_regen_per_hour` — float, promedio de regenerados/hora sobre los intervalos válidos,
  redondeado a 2 decimales. Nunca null (los animales sin intervalos válidos no aparecen
  en la lista, ver RN-REGEN2 / EC-REGEN-F).
- `valid_intervals` — integer, número de intervalos sobre los que se calculó el promedio.
  Útil para que el usuario sepa si el promedio es estadísticamente significativo.
  **Siempre `>= 1` cuando el animal está en la lista** (los animales sin intervalos válidos
  no se incluyen; no se emiten con `valid_intervals: 0`). [Corrección desarrollador-apis #1]

Si no hay intervalos válidos → `animal_regen_rates = []`.

**Status codes y errores de EP-06 NO cambian con esta modificación** (es un cambio
puramente aditivo): `200` siempre (incluido 0 ataques); `400` si falta `x` o `y`.
[Corrección desarrollador-apis #2]

**Caso nominal con datos reales (oasis -70|73, 5 ataques, 4 intervalos):**

```json
"animal_regen_rates": [
  { "animal_ordinal": 1, "animal_name": "Rata", "avg_regen_per_hour": 4.72, "valid_intervals": 4 }
  // (otros animales si los hay con intervalos válidos)
]
```

Nota: el valor exacto de `avg_regen_per_hour` depende de los `gap_seconds` reales de los
4 reportes del oasis. El implementador usa los datos reales para verificar.

**Respuesta de "cero ataques" (sin cambios):**

```json
{
  "coord_x_dest": -70, "coord_y_dest": 73,
  "total_attacks": 0,
  "first_attack": null, "last_attack": null,
  "animal_appearances": [],
  "repopulation_gaps": [],
  "animal_regen_rates": []    // ← nuevo, lista vacía
}
```

### EP-08 — Nuevo endpoint: lista de oasis navegable

```
GET /attack-reports/oasis

Ruta: /attack-reports/oasis
Método: GET
Auth: ninguna (local, sin autenticación)
Accept-Language: NO requerido (datos numéricos + strings de texto del juego que vienen
                  ya en el idioma del catálogo, no localizable por este endpoint)

Query params (todos opcionales):
  x   — integer, ge=-400, le=400 — coordenada X del oasis (ambos o ninguno)
  y   — integer, ge=-400, le=400 — coordenada Y del oasis
  NOTA [corrección desarrollador-apis #3]: x/y llevan ge=-400/le=400 a diferencia de EP-03
  (list_reports), que no valida rango. Divergencia INTENCIONADA: EP-08 sigue el patrón de
  EP-07 (rango como convención para endpoints de stats/filtros de oasis).

Semántica de x/y:
  - Omitidos AMBOS: lista todos los oasis con reportes, ordenados last_attack DESC.
  - Presentes AMBOS: filtra por coordenadas exactas (0 o 1 resultado).
  - Uno solo: 400 Bad Request.
  - Fuera de -400..400: 422 (FastAPI automático con ge/le).

Response 200 OK — lista de oasis:
{
  "total": 3,
  "items": [
    {
      "coord_x_dest": -70,
      "coord_y_dest": 73,
      "attack_count": 5,
      "last_attack": "2026-05-31T13:39:30",   // verbatim, sin zona
      "total_bounty": 18450
    },
    {
      "coord_x_dest": -45,
      "coord_y_dest": 12,
      "attack_count": 2,
      "last_attack": "2026-05-30T09:14:21",
      "total_bounty": 7200
    }
    // ...
  ]
}

Response 200 OK — sin resultados:
{
  "total": 0,
  "items": []
}

Response 400 Bad Request — x sin y (o y sin x):
{
  "detail": "Parámetro 'x' requiere 'y' y viceversa."
}

Response 422 Unprocessable Entity — fuera de rango (automático FastAPI):
// generado por ge=-400, le=400 en la declaración de Query params
```

**Posición en el router:** declarar ANTES de `GET /attack-reports/{id}` para evitar
colisiones de routing (el literal `/oasis` podría capturarse como `{id}` si no va antes).

**Sin paginación en la primera versión:** el número de oasis distintos es bajo
(se esperan decenas, no miles). Paginación puede añadirse en el futuro si escala.

---

## 9. Flujo lógico paso a paso

### BUG 1 — OasisStatsPanel.jsx (pseudocódigo de cambios)

```jsx
// AnimalsTable — cambiar row.count → row.appearances, row.avg → row.avg_present,
//                row.max → row.max_present, row.min → row.min_present

// ANTES:
{row.count}/{total}   // línea 107
{fmt(row.avg, lang)}  // línea 110
{row.max ?? '—'}      // línea 113
{row.min ?? '—'}      // línea 115

// DESPUÉS:
{row.appearances}/{total}
{fmt(row.avg_present, lang)}
{row.max_present ?? '—'}
{row.min_present ?? '—'}
```

```jsx
// RepopTable — añadir transformación lista→dict DENTRO del render de cada fila

// ANTES (línea 168):
const regen = row.animal_regeneration?.[name] ?? null

// DESPUÉS — antes de iterar los animalNames, transformar regenerated_animals a dict:
// (hacerlo dentro del map de rows para no mutar estado externo)
{gaps.map((row, idx) => {
  // Transformar lista → dict por nombre (O(n), n=número de animales, ≤10)
  const regenByName = Object.fromEntries(
    (row.regenerated_animals ?? []).map((a) => [a.animal_name, a.regenerated])
  )
  return (
    <tr key={idx} ...>
      ...
      {animalNames.map((name) => {
        const regen = regenByName[name] ?? null
        return <td key={name}><RegenCell value={regen} /></td>
      })}
    </tr>
  )
})}
```

### BUG 2 — ReportDetailDrawer.jsx / HeroInventory

```jsx
// Añadir import al inicio del archivo:
import { ResIcon } from '../combat/TravianReport.jsx'

// HeroInventory — cambiar items de { label: emoji, value } a { res: string, value }:

// ANTES:
const items = [
  { label: '🪵', value: inv.wood },
  { label: '🧱', value: inv.clay },
  { label: '⛏', value: inv.iron },
  { label: '🌾', value: inv.crop },
].filter((i) => i.value != null && i.value > 0)

// DESPUÉS:
const items = [
  { res: 'wood', value: inv.wood },
  { res: 'clay', value: inv.clay },
  { res: 'iron', value: inv.iron },
  { res: 'crop', value: inv.crop },
].filter((i) => i.value != null && i.value > 0)

// ANTES (render):
{items.map(({ label, value }) => (
  <span key={label} style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums' }}>
    {value.toLocaleString()} {label}
  </span>
))}

// DESPUÉS (render):
{items.map(({ res, value }) => (
  <span key={res} style={{ display: 'flex', alignItems: 'center', gap: '3px', fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums' }}>
    {value.toLocaleString()} <ResIcon res={res} size={14} />
  </span>
))}
```

### MEJORA 1 — Cálculo de animal_regen_rates en Python

```python
# Al final de get_oasis_stats, después de construir repopulation_gaps
# y antes del return final:

def _calc_regen_rates(repopulation_gaps: list[dict]) -> list[dict]:
    """
    Calcula el ratio promedio de regeneración por hora para cada animal,
    usando los intervalos válidos de repopulation_gaps.

    Intervalo válido: gap_seconds > 0, regenerated no es None, regenerated >= 0.
    """
    # Acumular tasas por animal_ordinal
    # { animal_ordinal: { "name": str, "rates": [float], "valid_count": int } }
    accum: dict[int, dict] = {}

    for gap in repopulation_gaps:
        gap_seconds = gap.get("gap_seconds")
        if not gap_seconds or gap_seconds <= 0:
            continue  # EC-REGEN-A: gap inválido o primer ataque
        for animal in gap.get("regenerated_animals", []):
            regenerated = animal.get("regenerated")
            if regenerated is None or regenerated < 0:
                continue  # EC-REGEN-B y EC-REGEN-C
            rate = regenerated / (gap_seconds / 3600)
            ordinal = animal["animal_ordinal"]
            if ordinal not in accum:
                accum[ordinal] = {"name": animal["animal_name"], "rates": [], "valid_count": 0}
            accum[ordinal]["rates"].append(rate)
            accum[ordinal]["valid_count"] += 1

    result = []
    for ordinal in sorted(accum.keys()):
        entry = accum[ordinal]
        if not entry["rates"]:
            continue  # EC-REGEN-F: sin intervalos válidos, no incluir
        avg = sum(entry["rates"]) / len(entry["rates"])
        result.append({
            "animal_ordinal": ordinal,
            "animal_name": entry["name"],
            "avg_regen_per_hour": round(avg, 2),
            "valid_intervals": entry["valid_count"],
        })
    return result

# En get_oasis_stats, antes del return:
animal_regen_rates = _calc_regen_rates(repopulation_gaps)

return {
    "coord_x_dest": x,
    "coord_y_dest": y,
    "total_attacks": total_attacks,
    "first_attack": first_attack,
    "last_attack": last_attack,
    "animal_appearances": animal_appearances,
    "repopulation_gaps": repopulation_gaps,
    "animal_regen_rates": animal_regen_rates,   # ← nuevo
}
```

La función `_calc_regen_rates` puede vivir como función de módulo privada (prefijo `_`)
o como método estático de la clase `AttackReportSQLiteAdapter`. El implementador elige;
se recomienda función de módulo (más fácil de testear en aislamiento).

### MEJORA 2 — Backend: list_oasis_summaries

```python
async def list_oasis_summaries(
    self,
    x: int | None = None,
    y: int | None = None,
) -> dict:
    """
    Devuelve la lista de oasis únicos con reportes, con resumen estadístico básico.

    Reutiliza el patrón de WHERE dinámico de list_reports.
    """
    params: list = []
    where_parts = []
    if x is not None:
        where_parts.append("coord_x_dest = ?")
        params.append(x)
    if y is not None:
        where_parts.append("coord_y_dest = ?")
        params.append(y)

    where_clause = "WHERE " + " AND ".join(where_parts) if where_parts else ""

    sql = f"""
        SELECT
            coord_x_dest,
            coord_y_dest,
            COUNT(*)                                            AS attack_count,
            MAX(attacked_at)                                    AS last_attack,
            COALESCE(
                SUM(bounty_wood + bounty_clay + bounty_iron + bounty_crop), 0
            )                                                   AS total_bounty
        FROM attack_reports
        {where_clause}
        GROUP BY coord_x_dest, coord_y_dest
        ORDER BY last_attack DESC
    """
    async with self._conn.execute(sql, params) as cursor:
        rows = await cursor.fetchall()

    items = [
        {
            "coord_x_dest": row["coord_x_dest"],
            "coord_y_dest": row["coord_y_dest"],
            "attack_count": row["attack_count"],
            "last_attack": row["last_attack"],
            "total_bounty": row["total_bounty"],
        }
        for row in rows
    ]
    return {"total": len(items), "items": items}
```

### MEJORA 2 — Router EP-08

```python
@router.get("/attack-reports/oasis")
async def list_oasis_summaries(
    request: Request,
    x: int | None = Query(
        default=None, ge=-400, le=400,
        description="Coordenada X del oasis (-400..400). Requiere 'y'."
    ),
    y: int | None = Query(
        default=None, ge=-400, le=400,
        description="Coordenada Y del oasis (-400..400). Requiere 'x'."
    ),
):
    """Lista los oasis con reportes de ataque, con resumen básico."""
    if (x is None) != (y is None):
        raise HTTPException(
            status_code=400,
            detail="Parámetro 'x' requiere 'y' y viceversa."
        )
    port = request.app.state.attack_report_port
    return await port.list_oasis_summaries(x=x, y=y)
```

**Posición en el router:** antes de `GET /attack-reports/{id}`.

---

## 10. Validaciones y reglas

| Campo | Validación | Código error |
|---|---|---|
| `x` sin `y` (o `y` sin `x`) en EP-08 | Ambos o ninguno | 400 |
| `x`, `y` en EP-08 | Enteros, rango -400..400 (`ge/le` en Query) | 422 |
| `regenerated` en cálculo de regen rate | Solo incluir si `>= 0` y `gap_seconds > 0` | (lógica interna, no HTTP) |
| Nombres de campo en `AnimalsTable` | Frontend: usar `appearances/avg_present/max_present/min_present` | (bug visual, no HTTP) |
| `regenerated_animals` en `RepopTable` | Frontend: transformar lista → dict antes de leer por nombre | (bug visual, no HTTP) |

---

## 11. Seguridad, rendimiento y concurrencia

- `list_oasis_summaries` es un `GROUP BY` sobre `attack_reports` sin joins. Cubierto por
  el índice `idx_attack_reports_coords_time` (que incluye `coord_x_dest`, `coord_y_dest`).
  Con el volumen esperado (cientos de reportes, decenas de oasis únicos) < 10 ms.
- `_calc_regen_rates` es O(n*m) donde n = número de ataques y m = número de animales
  (máx 10). Con 100 ataques: 1000 operaciones. Despreciable.
- Todos los cambios son read-only o aditivos (no hay escrituras nuevas). Sin riesgos de
  concurrencia adicionales a los ya gestionados por la BD.
- Sin nuevas rutas autenticadas ni superficies de ataque adicionales.

---

## 12. Plan de pruebas

### BUG 1 — Tests frontend

| ID | Caso | Verificación |
|---|---|---|
| T-B1-A | Renderizar `AnimalsTable` con datos reales de oasis (-70,73) | La fila de Rata muestra: "4" en apariciones, "9.3" en promedio (fmt con 1 decimal), "14" en máx, "7" en mín |
| T-B1-B | Renderizar `AnimalsTable` con `appearances=[]` | Componente devuelve null (sin tabla) |
| T-B1-C | Renderizar `RepopTable` con gap que tiene `regenerated_animals=[{animal_name:"Rata", regenerated:9}]` | La celda de Rata muestra "+9" en verde |
| T-B1-D | Gap con `regenerated_animals=[]` (primer ataque) | Todas las celdas de animales muestran "—" |
| T-B1-E | Animal en `animalNames` no presente en `regenerated_animals` del gap | Celda muestra "—" (no crash) |

### BUG 2 — Tests frontend

| ID | Caso | Verificación |
|---|---|---|
| T-B2-A | `HeroInventory` con `{ wood: 500, clay: 0, iron: 300, crop: null }` | Muestra "500 [icono wood]" y "300 [icono iron]"; clay y crop no aparecen; sin emojis del OS |
| T-B2-B | `HeroInventory` con `inv=null` | Muestra el mensaje de "sin inventario" |
| T-B2-C | `HeroInventory` con todos los valores a 0 o null | Muestra el mensaje de "sin inventario" |

### MEJORA 1 — Tests backend

| ID | Caso | Verificación |
|---|---|---|
| T-R1 | 3 intervalos válidos con `gap_seconds=3600, regenerated=5` (1/h × 3) | `avg_regen_per_hour = 5.0`, `valid_intervals = 3` |
| T-R2 | Intervalos: [válido: 3600s/5 regen, inválido: gap=0, inválido: regen=-1] | Solo el intervalo válido contribuye; `valid_intervals = 1` |
| T-R3 | Primer ataque (sin `prev_survived`, `regenerated=None`) | Excluido; no contribuye al promedio |
| T-R4 | `regenerated = 0` con `gap_seconds = 7200` | Tasa = 0.0/h; incluido. `avg_regen_per_hour = 0.0` |
| T-R5 | Oasis con 1 ataque (sin intervalos) | `animal_regen_rates = []` |
| T-R6 | Todos los intervalos tienen `regenerated < 0` | `animal_regen_rates = []` |
| T-R7 | Datos reales oasis (-70,73) — 5 ataques, 4 intervalos para Rata | `valid_intervals = 4` (asumiendo todos positivos); `avg_regen_per_hour` calculable con los timestamps reales |
| T-R8 | EP-06 con oasis sin ataques (0 reportes) | `animal_regen_rates: []` en el response |
| T-R9 | EP-06 incluye campo `animal_regen_rates` en la respuesta | Presente en el JSON, incluso si está vacío |

### MEJORA 2 — Tests backend (EP-08)

| ID | Caso | Verificación |
|---|---|---|
| T-N1 | `GET /attack-reports/oasis` con 2 oasis en BD | `total=2`, `items` contiene ambos ordenados por `last_attack DESC` |
| T-N2 | `GET /attack-reports/oasis` con BD vacía | `total=0`, `items=[]` |
| T-N3 | `GET /attack-reports/oasis?x=-70&y=73` con 5 reportes de ese oasis | `total=1`, `items[0].attack_count=5`, `last_attack` correcto |
| T-N4 | `GET /attack-reports/oasis?x=-70&y=99` (coords sin reportes) | `total=0`, `items=[]` |
| T-N5 | `GET /attack-reports/oasis?x=-70` (sin y) | 400 con detail |
| T-N6 | `GET /attack-reports/oasis?y=73` (sin x) | 400 con detail |
| T-N7 | `GET /attack-reports/oasis?x=999&y=73` (fuera de rango) | 422 |
| T-N8 | `total_bounty` = suma de `bounty_wood+clay+iron+crop` del oasis | Verificar con fixture de 2 reportes del mismo oasis con bounty conocido |
| T-N9 | `last_attack` es el `attacked_at` más reciente de ese oasis (verbatim, sin zona) | `"2026-05-31T13:39:30"` para datos reales |

---

## 13. Riesgos y trade-offs

### RT-REGEN1 — Excluir `regenerated < 0` vs incluirlo como tasa negativa

Se excluyen los valores negativos del promedio (no del campo `regenerated_animals`).

Alternativa considerada: incluirlos como tasas negativas (señal de "evento anómalo").
Descartada porque un promedio que incluye negativos daría un ratio de regeneración más
bajo que el real, llevando al usuario a atacar con menos frecuencia de la óptima. Los
eventos negativos son informativos pero no deben contaminar el KPI de cadencia óptima.

### RT-REGEN2 — `valid_intervals` como campo de confianza

Se incluye para que el usuario sepa si el promedio se calculó con 1 o con 20 datos.
Un `avg_regen_per_hour = 5.0` con `valid_intervals = 1` no es confiable; con 10, sí.
Es un campo de coste cero (ya lo calculamos) con valor informativo alto.

### RT-NAV1 — Sin paginación en EP-08

El número de oasis distintos con reportes es bajo en el contexto de uso (un jugador
ataca decenas, no miles de oasis). Si en el futuro escala, añadir `limit`/`offset`
es un cambio mínimo y retrocompatible.

### RT-NAV2 — Navegación a stats: UI pendiente de disenador-producto

La pestaña Estadísticas actual (`StatsTab.jsx`) tiene un input manual de x/y. Con EP-08
disponible, la UI puede evolucionar a lista navegable. Ese rediseño requiere:
1. `disenador-producto` diseñe el mockup editable (regla mockup-first).
2. El usuario apruebe la composición.
3. `desarrollador-ux-ui` implemente la UI real.

El implementador del backend (este spec) no toca `StatsTab.jsx` salvo los bugs corregidos
en BUG 1. El rediseño visual es un spec separado de `disenador-producto`.

---

## 14. Pasos de implementación ordenados

> Prerrequisito: aplicar `bd-ataques-oasis-fix-hora-balance.md` antes o junto con este
> spec (los `gap_seconds` deben ser correctos).

### Bloque 1 — BUG 1: OasisStatsPanel.jsx

**Archivo:** `frontend/src/components/attack-reports/OasisStatsPanel.jsx`

1. En `AnimalsTable`, líneas ~107-115: cambiar los 4 nombres de campo según RN-BUG1-A.
   - `row.count` → `row.appearances`
   - `row.avg` → `row.avg_present` (dentro de `fmt(...)`)
   - `row.max` → `row.max_present`
   - `row.min` → `row.min_present`

2. En `RepopTable`, línea ~168: cambiar la lectura de regeneración según RN-BUG1-B.
   - El `gaps.map()` pasa a construir `regenByName` por fila dentro del render.
   - `row.animal_regeneration?.[name]` → `regenByName[name] ?? null`

### Bloque 2 — BUG 2: ReportDetailDrawer.jsx / HeroInventory

**Archivo:** `frontend/src/components/attack-reports/ReportDetailDrawer.jsx`

3. Añadir import: `import { ResIcon } from '../combat/TravianReport.jsx'`
4. En `HeroInventory`, cambiar la lista `items` de emoji-label a res-string según RN-BUG2.
5. Cambiar el render de cada item: de `{value} {emoji}` a `{value} <ResIcon res={res} size={14} />`.
6. Cambiar la `key` de `label` (emoji) a `res` (string estable).

### Bloque 3 — MEJORA 1: campo animal_regen_rates en get_oasis_stats

**Archivos:** `adapters/db/attack_report_sqlite_adapter.py` y `core/ports/attack_report_port.py`

7. Añadir función de módulo privada `_calc_regen_rates(repopulation_gaps)` en el adaptador
   (justo antes de la clase o al final del módulo), siguiendo el pseudocódigo de §9.
8. En `get_oasis_stats`, llamar a `_calc_regen_rates(repopulation_gaps)` y añadir el
   resultado al dict de retorno como `"animal_regen_rates"`.
9. Actualizar el cuerpo de "cero ataques" en `get_oasis_stats` para incluir también
   `"animal_regen_rates": []`.
10. En `core/ports/attack_report_port.py`, actualizar el docstring de `get_oasis_stats`
    para documentar que la respuesta incluye `animal_regen_rates`.

### Bloque 4 — MEJORA 2: list_oasis_summaries (backend)

**Archivos:** `adapters/db/attack_report_sqlite_adapter.py` y `core/ports/attack_report_port.py`

11. Añadir método `list_oasis_summaries(self, x=None, y=None)` al adaptador,
    siguiendo el pseudocódigo de §9.
12. Añadir método abstracto `list_oasis_summaries` al puerto abstracto
    `AttackReportPort`.

### Bloque 5 — MEJORA 2: endpoint EP-08 (router)

**Archivo:** `adapters/api/routes/attack_reports.py`

13. Añadir EP-08 (`GET /attack-reports/oasis`) antes de `GET /attack-reports/{id}`,
    siguiendo el pseudocódigo de §9.

### Bloque 6 — Tests

14. Añadir tests T-R1 a T-R9 (MEJORA 1) en el archivo de tests del adaptador o del
    use case de stats.
15. Añadir tests T-N1 a T-N9 (EP-08) en el archivo de tests de la API
    (`tests/test_attack_reports_api.py`).
16. Verificar BUG 1 manualmente con los datos reales del oasis (-70|73): la tabla de
    animales muestra Rata con 4/5 apariciones, avg~9.3, máx 14, mín 7. La tabla de
    repoblación muestra los valores regenerados de cada fila.
17. Verificar BUG 2 manualmente: abrir el drawer de detalle de un reporte con héroe.
    Confirmar que aparecen iconos png del juego en lugar de emojis.

### Bloque 7 — UI: GATE de disenador-producto (NO implementar UI hasta aquí)

18. Abrir tarea para `disenador-producto`: rediseñar la pestaña Estadísticas
    (`StatsTab.jsx`) para incluir la lista navegable de oasis (EP-08 ya disponible).
    El diseñador produce mockup editable `frontend/mockups/stats-oasis-nav.playground.html`.
19. El usuario aprueba la composición del mockup.
20. `desarrollador-ux-ui` implementa la UI real según el mockup aprobado.

---

## 15. Criterios de aceptación

### BUG 1

- [ ] **CA-1A**: Con datos reales del oasis (-70|73), la tabla de animales muestra Rata
  con `4` en la columna Apariciones (no vacío, no "--", no "undefined").
- [ ] **CA-1B**: La columna Promedio de Rata muestra `9.3` (o `9.25` si no se redondea a 1
  decimal en el `fmt`). No muestra "--" ni "NaN".
- [ ] **CA-1C**: La columna Máx de Rata muestra `14`; Mín muestra `7`.
- [ ] **CA-1D**: La tabla de repoblación (segunda tabla) muestra los valores regenerados
  de al menos una fila (no todas las celdas de animales muestran "—" cuando hay datos).
- [ ] **CA-1E**: No hay errores de consola JS del tipo `TypeError: cannot read properties
  of undefined` al renderizar `OasisStatsPanel`.

### BUG 2

- [ ] **CA-2A**: En el drawer de detalle de un reporte con héroe que tiene recursos en el
  inventario, se ven iconos png del juego (imágenes `stat_wood.png`, etc.) junto a los
  números. No hay emojis del OS.
- [ ] **CA-2B**: El alt text de cada icono es el nombre del recurso (accesibilidad).
- [ ] **CA-2C**: Si el inventario del héroe no tiene recursos (o es null), se muestra el
  mensaje "sin inventario" sin errores JS.

### MEJORA 1

- [ ] **CA-3A**: `GET /attack-reports/stats/oasis?x=-70&y=73` devuelve el campo
  `animal_regen_rates` en el JSON (aunque sea `[]`).
- [ ] **CA-3B**: Con los 5 reportes reales del oasis (-70|73) y asumiendo todos los gaps
  positivos, `animal_regen_rates` contiene al menos una entrada para Rata con
  `valid_intervals = 4` (4 intervalos = 5 ataques - 1).
- [ ] **CA-3C**: `avg_regen_per_hour` es un número float positivo o 0, nunca null,
  nunca NaN.
- [ ] **CA-3D**: Con oasis sin ataques, `animal_regen_rates = []`.
- [ ] **CA-3E**: Los tests T-R1 a T-R6 pasan en verde.

### MEJORA 2

- [ ] **CA-4A**: `GET /attack-reports/oasis` devuelve los 5 reportes del oasis (-70|73)
  agrupados en 1 item con `attack_count=5`.
- [ ] **CA-4B**: `GET /attack-reports/oasis?x=-70&y=73` devuelve `total=1` con el
  item del oasis (-70|73).
- [ ] **CA-4C**: `GET /attack-reports/oasis?x=-70` devuelve 400.
- [ ] **CA-4D**: `GET /attack-reports/oasis?x=999&y=73` devuelve 422.
- [ ] **CA-4E**: `last_attack` en el item del oasis (-70|73) es `"2026-05-31T13:39:30"`
  (verbatim, sin zona).
- [ ] **CA-4F**: `total_bounty` es la suma de los 4 recursos de todos los reportes del oasis.
- [ ] **CA-4G**: EP-08 está declarado ANTES de `GET /attack-reports/{id}` en el router.
- [ ] **CA-4H**: Los tests T-N1 a T-N9 pasan en verde.

### Gate UI (no verificable hasta el mockup)

- [ ] **CA-5A**: Existe `frontend/mockups/stats-oasis-nav.playground.html` aprobado por
  el usuario antes de tocar `StatsTab.jsx`.

---

## 16. Trazabilidad

| Decisión técnica | Requisito / edge case que la origina |
|---|---|
| Alinear frontend a nombres de API (no al revés) | RN-BUG1-A; la API tiene tests automatizados que quedarían rotos si se cambiara la API |
| Transformar lista→dict en render (no en estado) | RN-BUG1-B; el estado no debe derivarse de transformaciones que ya se hacen en render |
| Reutilizar `ResIcon` (no duplicar) | RN-BUG2; mapa de palantir: ResIcon = REUTILIZAR; evita inconsistencia visual y derivación futura de la ruta del icono |
| Calcular `animal_regen_rates` en Python (no SQL) | RN-REGEN2; los datos ya están en memoria tras `repopulation_gaps`; columna de análisis sin SQL adicional |
| Excluir `regenerated < 0` del promedio de tasas | RT-REGEN1; EC-REGEN-C; un negativo indica irregularidad, no regeneración natural; contaminaría el KPI |
| Incluir `valid_intervals` en la respuesta | RT-REGEN2; campo de confianza estadística de coste cero |
| Devolver `animal_regen_rates = []` (no null) | EC-REGEN-E, EC-REGEN-F, EC-REGEN-G; coherencia con `animal_appearances` y `repopulation_gaps` que también son listas vacías en los casos sin datos |
| `GROUP BY coord_x, coord_y ORDER BY last_attack DESC` | RN-NAV1; lista navegable ordenada por actividad reciente |
| Sin paginación en EP-08 v1 | RT-NAV1; volumen bajo en caso de uso real |
| Validación combinatoria x/y → 400 idéntica a EP-07 | RN-NAV1; coherencia de la API; patrón ya establecido en el proyecto |
| Pestaña Estadísticas: gate disenador-producto antes de UI | RT-NAV2; regla mockup-first del proyecto (CLAUDE.md); no se implementa UI sin mockup aprobado |
| EP-08 declarado antes de `/{id}` en el router | RN-NAV1; FastAPI resuelve rutas por orden de declaración; evitar que "oasis" sea capturado como `{id}` |

### Reutilización (mapa de palantir)

| Pieza | Decisión | Notas |
|---|---|---|
| `ResIcon` en `TravianReport.jsx` (línea 44) | REUTILIZAR | Exportado, consume `/api/static/icons/stat_*.png` |
| Patrón WHERE dinámico de `list_reports` | REUTILIZAR | `list_oasis_summaries` replica la misma lógica de `where_parts` |
| Validación combinatoria x/y → 400 de EP-07 | REUTILIZAR | Mismo pattern en EP-08 |
| `_calc_regen_rates` | CREAR | Función nueva, sin precedente en el codebase |
| `list_oasis_summaries` | CREAR | Método nuevo en adaptador y puerto |
| EP-08 `GET /attack-reports/oasis` | CREAR | No existe endpoint equivalente (confirmado por palantir) |

### APIs

| Necesidad | Decisión | Notas |
|---|---|---|
| Campo `animal_regen_rates` en EP-06 | MODIFICAR endpoint existente | Cambio aditivo; pendiente luz verde de `desarrollador-apis` |
| EP-08 `GET /attack-reports/oasis` | CREAR | Pendiente luz verde de `desarrollador-apis` |

---

## Nota para el orquestador

**Dos contratos pendientes de validación por `desarrollador-apis`:**

1. **Modificación de EP-06**: añadir campo `animal_regen_rates` a `GET /attack-reports/stats/oasis`.
   Contrato propuesto en §8 (campo nuevo: `animal_ordinal`, `animal_name`,
   `avg_regen_per_hour`, `valid_intervals`).

2. **Creación de EP-08**: `GET /attack-reports/oasis`.
   Contrato propuesto en §8 (response: `{ total, items: [{ coord_x_dest, coord_y_dest,
   attack_count, last_attack, total_bounty }] }`).

**Una parte de UI espera gate de disenador-producto:**
- La pestaña Estadísticas (`StatsTab.jsx`) debe rediseñarse para incluir la lista
  navegable de oasis (MEJORA 2). Este rediseño sigue la regla mockup-first:
  `disenador-producto` produce `frontend/mockups/stats-oasis-nav.playground.html`,
  el usuario aprueba, y `desarrollador-ux-ui` implementa.
- Los bugs BUG 1 y BUG 2, y la MEJORA 1 de backend, **NO** necesitan ese gate: son
  correcciones sobre componentes ya existentes que no cambian la estructura de pantalla.

*Spec redactado el 2026-05-31.*

---

## Registro de implementación

**Fecha:** 2026-05-31
**Implementado por:** desarrollador-funcionalidades

### Alcance de este spec implementado (solo BACKEND)

BUG 1, BUG 2 (frontend) y Gate UI (mockup-first para StatsTab) son trabajo del agente
`desarrollador-ux-ui` y `disenador-producto`. Este registro cubre solo el backend.

### Archivos creados/modificados (backend)

| Archivo | Cambio |
|---|---|
| `adapters/db/attack_report_sqlite_adapter.py` | `_calc_regen_rates` (módulo), `get_oasis_stats` con `animal_regen_rates`, `list_oasis_summaries` |
| `core/ports/attack_report_port.py` | Métodos abstractos `list_oasis_summaries` + docstring `get_oasis_stats` actualizado |
| `adapters/api/routes/attack_reports.py` | EP-08 `GET /attack-reports/oasis` antes de `/{id}` |
| `tests/unit/test_attack_report_parser.py` | `TestCalcRegenRates` (T-R1..T-R6 + variantes) |
| `tests/test_attack_reports_api.py` | `TestOasisStatsRegen` (T-R8, T-R9, T-R1) + `TestOasisList` (T-N1..T-N9) |

### Comando para ejecutar los tests

```bash
python -m pytest tests/unit/test_attack_report_parser.py tests/test_attack_reports_api.py -v
```

### Resultado de tests

107 de 107 tests pasan (0 fallos).

### Verificación con datos reales (oasis -70|73)

- Rata: appearances=4, avg=9.25, max=14, min=7 (criterio CA-1A, CA-1B, CA-1C verificados vía consulta directa)
- `animal_regen_rates`: Rata avg_regen_per_hour=2.29, valid_intervals=4 (CA-3B verificado)
- `last_attack` en EP-08: `"2026-05-31T13:39:30"` (CA-4E verificado)
- `animal_regen_rates` incluido en EP-06 response (CA-3A verificado)

### Pendiente (gate mockup-first)

CA-5A: `frontend/mockups/stats-oasis-nav.playground.html` — aún no existe. Gate de
`disenador-producto` necesario antes de que `desarrollador-ux-ui` toque `StatsTab.jsx`.

### Desviaciones respecto al diseño

Ninguna. Implementación fiel al spec.
