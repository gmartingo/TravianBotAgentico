---
id: bd-ataques-oasis-temporal-distribution
titulo: "Distribución empírica de animales por frecuencia de farmeo (Animal Temporal Distribution)"
estado: implemented
fecha: 2026-06-02
autor: analista
apis_validadas_por_desarrollador_apis: false
# HISTORIAL:
# v1 (2026-06-02): estado=implemented. Gate desarrollador-apis ejecutado (CORRECTO).
#   Contratos validados: bucket_hours en {1,2,4,8,12,24}, matriz animal x franja, Accept-Language oblig.
#   Implementacion completada: 33/33 tests, sin regresiones en suite completa (166 tests).
# v2 (2026-06-02): redesign funcional. interval_minutes sustituye a bucket_hours.
#   Binning umbral inferior (Opcion B). Respuesta de una sola frecuencia (no matriz).
#   39 tests en verde. UI rediseno separado (disenador-producto + mockup). Gate desarrollador-apis pendiente.
# v3 (2026-06-02): segmentacion por tipo de oasis inferido.
#   Response agrupado en 5 secciones fijas (hierro/arcilla/madera/cereal/sin_clasificar).
#   Reutiliza _infer_type y OASIS_TYPE_SETS (elevada a funcion de modulo en el adapter).
#   UI rediseno separado (disenador-producto). Gate desarrollador-apis pendiente.
#   Implementacion completada: 41/41 tests, EP-SPAWN 52/52 sin regresion.
# v4 (2026-06-02): datos adicionales por seccion.
#   max_present por animal, total_animals por seccion, avg_bounty por seccion, oasis_coords por seccion.
#   Solo se ANADEN campos; v3 intacta. Gate desarrollador-apis pendiente.
---

# Distribución empírica de animales por frecuencia de farmeo

---

## REVISIÓN v4 — Peor caso + botín + total de animales + coordenadas de oasis

> Esta sección documenta los 4 campos nuevos que se AÑADEN sobre la implementación v3
> ya en verde (41 tests EP-TD + 52 tests EP-SPAWN). No se cambia ningún campo existente:
> todo lo de v3 permanece intacto. Solo se agregan nuevas claves al schema.
> El resto del spec (secciones 1-16) se actualiza al final de esta sección.
> El apartado "Qué cambia respecto a v3" al final del spec lista los cambios concretos
> para desarrollador-apis y desarrollador-funcionalidades.

### Motivación

El usuario quiere más contexto por sección para calibrar sus ataques:
1. Saber el **peor escenario** de cada animal (máximo de unidades observadas).
2. Saber cuántos **recursos medios** aporta atacar a esa cadencia.
3. Saber cuántos **animales totales** tiene un reporte típico (para dimensionar las tropas).
4. Saber **qué oasis concretos** aportan datos a cada sección (para identificarlos en el mapa).

### Campo 1 — `max_present` por animal (dentro de `animals[]`)

**Decisión:** añadir `max_present: integer | null` a cada elemento de `animals[]`.
Es el máximo de `present` observado en los gaps de la ventana + tipo para ese animal.

**Regla de NULL:** misma que `avg_present` y `mode_present`.
- Se calcula sobre los valores de `present` no nulos (`n_valid > 0`).
- Si `n_valid = 0` → `max_present = null`.
- NULL en `present` (derrota) se excluye del cálculo: cuenta en `n_total`, no en `n_valid`.

**Fuente de reutilización (palantir):** el valor se deriva de `max(valids)` sobre la lista
`data["valids"]` que ya se acumula en el helper `_build_animals`. Son 2-3 líneas extra;
no requiere SQL nuevo ni query adicional.

**Posición en el schema:** inmediatamente después de `mode_present`, antes de `n_total`.

### Campo 2 — `total_animals` por sección (en `types[]`, nivel de sección)

**Decisión:** añadir `total_animals: object` a cada objeto del array `types[]`.
Representa la distribución del **número total de animales en un reporte** (suma de `present`
de todos los animales de ese reporte) dentro de la ventana+tipo.

#### Definición del "total de un reporte"

Un reporte puede tener algunos animales con `present` no nulo y otros con `present = NULL`
(derrota parcial sería raro, pero puede ocurrir si el parser registró filas mixtas).
**Decisión de NULL en el total:**

> **Un reporte entra en `total_animals.n_valid` si y solo si TODOS sus animales observados
> en esa sección tienen `present` no nulo.** Si cualquier animal del reporte tiene
> `present = NULL`, ese reporte se excluye de `n_valid` y del cálculo de avg/mode/max
> del total. Se cuenta siempre en `n_total`.

**Justificación:** sumar los animals no nulos de un reporte parcialmente desconocido
produciría un total sesgado a la baja (ej. si hay 3 ratas y 0 murciélagos nulos → 3,
cuando en realidad el total era desconocido). Es más honesto excluir el reporte completo
del total que fingir que el total parcial es representativo. El campo `n_total` siempre
informa cuántos reportes hay en la ventana, incluyendo los excluidos.

En la práctica, los reportes de derrota tienen TODOS los animales a NULL (el parser
los detecta así), por lo que la regla de exclusión es equivalente a "excluir reportes
de derrota del cálculo del total". El caso de "derrota parcial" (algunos NULL, algunos
enteros) es teóricamente posible si el parser falla, pero el tratamiento es el mismo.

**Estructura del objeto `total_animals`:**

```json
"total_animals": {
  "avg": 12.50,
  "mode": [10, 12],
  "max": 24,
  "n_valid": 12,
  "n_total": 15
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `avg` | `number \| null` | Media del total de animales por reporte (redondeada a 2 decimales). `null` si `n_valid = 0`. |
| `mode` | `array[integer]` | Moda(s) del total. `[]` si `n_valid = 0`. Empates: todos ASC. |
| `max` | `integer \| null` | Máximo del total. `null` si `n_valid = 0`. |
| `n_valid` | `integer` | Reportes con TODOS los animales no nulos (victorias completas). |
| `n_total` | `integer` | Total de report_ids distintos en la sección (= `n_reports_in_section`). |

**Nota:** `total_animals.n_total` es siempre igual a `n_reports_in_section` de la misma
sección. Se incluye en el objeto por consistencia con el patrón `n_valid`/`n_total` del
proyecto, y para que el front pueda mostrar la tasa de reportes válidos sin consultar
el campo de la sección padre.

**Sección vacía:** si `n_reports_in_section = 0` → `total_animals = { avg: null, mode: [], max: null, n_valid: 0, n_total: 0 }`.

**Nivel de cálculo:** es un campo a nivel de SECCIÓN (por tipo), no por animal.
El total de un reporte es la suma de los `present` de todos los animales de ese reporte,
independientemente del ordinal. No tiene sentido calcular el total por animal.

**Implementación en Python:** se necesita una estructura auxiliar adicional por tipo:
`type_report_totals[tipo]: dict[report_id → list[int]]` que acumula los valores de
`present` no nulos por reporte. Al cerrar el bucle de `window_rows`, para cada
`(tipo, report_id)` se comprueba si alguna fila de ese reporte tiene `present = None`;
si ninguna → se suma la lista y se acumula en la distribución del total.

La forma eficiente: acumular por reporte `{report_id: {"sum": int, "any_null": bool}}`.
Al final, para cada reporte con `any_null = False`, se añade `sum` a la lista de totales.
La lista de totales del tipo se usa para calcular `avg`, `mode`, `max`.

### Campo 3 — `avg_bounty` por sección (en `types[]`, nivel de sección)

**Decisión:** añadir `avg_bounty: object` a cada objeto del array `types[]`.

#### Denominador del botín

Las columnas `bounty_wood/clay/iron/crop` son `INTEGER NOT NULL DEFAULT 0` en el DDL
(confirmado en el código real, líneas 58-61 del adapter). Una derrota guarda `0`, no NULL.
Por tanto, el denominador es **todos los reportes de la sección en la ventana**
(`n_reports_in_section`), incluidas las derrotas con botín = 0.

**Justificación:** promediar solo sobre "ataques con botín > 0" inflaría la media y
ocultaría el coste de los ataques fallidos. El usuario calibra una cadencia real que
incluye derrotas; la media honesta incluye los ceros. Esta decisión es consistente con
cómo `get_bounty_stats` suma el botín total sin excluir derrotas (líneas 854-858 del adapter).

**Estructura del objeto `avg_bounty`:**

```json
"avg_bounty": {
  "wood": 145,
  "clay": 98,
  "iron": 312,
  "crop": 67,
  "total": 622
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `wood` | `integer` | Media de `bounty_wood` redondeada al entero más cercano. |
| `clay` | `integer` | Media de `bounty_clay` redondeada al entero más cercano. |
| `iron` | `integer` | Media de `bounty_iron` redondeada al entero más cercano. |
| `crop` | `integer` | Media de `bounty_crop` redondeada al entero más cercano. |
| `total` | `integer` | Media de `(bounty_wood + bounty_clay + bounty_iron + bounty_crop)` redondeada al entero más cercano. No es la suma de los cuatro campos anteriores (puede diferir por el redondeo independiente). |

**Redondeo:** `round(sum / count)` en Python (redondeo bancario de Python 3, al entero
par en .5 exacto). El campo es `integer` (no float) porque el botín son recursos enteros
y la precisión sub-unidad no aporta valor.

**Sección vacía:** si `n_reports_in_section = 0` → `avg_bounty = { wood: 0, clay: 0, iron: 0, crop: 0, total: 0 }`.
Se usa `0` (no `null`) porque el denominador es `n_reports_in_section` y si es 0 no hay
media que calcular; devolver `0` es consistente con `get_bounty_stats` (que usa COALESCE
con 0 para las sumas vacías).

**Implementación:** la CTE `report_gaps` de la query LAG ya une con `attack_reports`.
Para añadir el botín se extiende el SELECT de la CTE para incluir `r.bounty_wood`,
`r.bounty_clay`, `r.bounty_iron`, `r.bounty_crop` en `report_gaps`. Dado que la CTE
agrupa por `report_id` (una fila por gap), no hay riesgo de conteo múltiple del botín.
Se acumula `type_bounty[tipo][report_id] = (wood, clay, iron, crop)` (dict deduplicado
por report_id, ya que varios animales del mismo reporte no deben sumar el botín varias
veces). Al construir la sección, se promedia sobre el conjunto de reportes del tipo.

### Campo 4 — `oasis_coords` por sección (en `types[]`, nivel de sección)

**Decisión:** añadir `oasis_coords: array[{ x: integer, y: integer }]` a cada objeto
del array `types[]`.

Lista de las coordenadas de los oasis distintos de ese tipo que aportan al menos un gap
en la ventana. Son exactamente los oasis del set `type_oasis_ids[tipo]` que ya se
construye en v3, serializado como lista de objetos `{x, y}`.

**Formato:** enteros crudos. El formateo `(-15|23)` es responsabilidad del frontend
(ver coordUtils.js — recomendación de palantir: centralizar las 5 copias del formateador
existentes en OasisList, HistoryTable, ReportPreview, OasisStatsPanel y
OasisCombatPlannerPanel → tarea para desarrollador-ux-ui en la iteración de UI v5).
El backend devuelve `x` e `y` como enteros, sin formateo, sin signo especial.

**Orden:** `ORDER BY y ASC, x ASC` (determinista para tests; el orden absoluto no es
semánticamente significativo, pero la determinismo evita flakiness en tests).

**Cap:** sin límite en v4. El número de oasis distintos por tipo de oasis en Travian
es siempre pequeño (el usuario tiene acceso a unos pocos oasis del mapa cercano).
Si en el futuro hubiera muchos oasis (escenario improbable en este caso de uso),
se puede añadir un cap con un campo `oasis_coords_truncated: boolean`. Por ahora,
sin cap.

**Sección vacía:** si `n_oasis = 0` → `oasis_coords = []`.

**Fuente de reutilización (palantir):** el set `type_oasis_ids[tipo]` ya contiene
exactamente las tuplas `(cx, cy)` necesarias. Solo hay que serializar el set como lista
ordenada de dicts `{x: cx, y: cy}`. Son 2-3 líneas extra en el builder de la sección.

### Schema completo v4

La estructura raíz no cambia. Los cambios son dentro de cada elemento de `types[]`.

**Schema de una sección (tipos modificados respecto a v3 marcados con `[NUEVO v4]`):**

```json
{
  "oasis_type": "hierro",
  "oasis_type_label": "Hierro",
  "n_oasis": 3,
  "n_oasis_low_confidence": 1,
  "n_reports_in_section": 18,
  "oasis_coords": [
    { "x": -15, "y": 23 },
    { "x": -12, "y": 28 },
    { "x": -8, "y": 31 }
  ],
  "avg_bounty": {
    "wood": 45,
    "clay": 12,
    "iron": 318,
    "crop": 22,
    "total": 397
  },
  "total_animals": {
    "avg": 12.50,
    "mode": [10, 12],
    "max": 24,
    "n_valid": 15,
    "n_total": 18
  },
  "animals": [
    {
      "animal_ordinal": 1,
      "animal_name": "Rata",
      "icon_url": "/static/icons/nature_1.png",
      "avg_present": 2.50,
      "mode_present": [2],
      "max_present": 6,
      "n_total": 18,
      "n_valid": 15
    },
    {
      "animal_ordinal": 2,
      "animal_name": "Araña",
      "icon_url": "/static/icons/nature_2.png",
      "avg_present": 1.80,
      "mode_present": [2],
      "max_present": 4,
      "n_total": 18,
      "n_valid": 15
    },
    {
      "animal_ordinal": 4,
      "animal_name": "Murciélago",
      "icon_url": "/static/icons/nature_4.png",
      "avg_present": 1.20,
      "mode_present": [1],
      "max_present": 3,
      "n_total": 12,
      "n_valid": 10
    }
  ]
}
```

**Ejemplo de sección vacía (sin datos):**

```json
{
  "oasis_type": "madera",
  "oasis_type_label": "Madera",
  "n_oasis": 0,
  "n_oasis_low_confidence": 0,
  "n_reports_in_section": 0,
  "oasis_coords": [],
  "avg_bounty": { "wood": 0, "clay": 0, "iron": 0, "crop": 0, "total": 0 },
  "total_animals": { "avg": null, "mode": [], "max": null, "n_valid": 0, "n_total": 0 },
  "animals": []
}
```

**Ejemplo de sección con solo reportes de derrota (n_reports_in_section > 0 pero n_valid = 0):**

```json
{
  "oasis_type": "sin_clasificar",
  "oasis_type_label": "Sin clasificar",
  "n_oasis": 1,
  "n_oasis_low_confidence": 0,
  "n_reports_in_section": 3,
  "oasis_coords": [{ "x": -5, "y": 10 }],
  "avg_bounty": { "wood": 0, "clay": 0, "iron": 0, "crop": 0, "total": 0 },
  "total_animals": { "avg": null, "mode": [], "max": null, "n_valid": 0, "n_total": 3 },
  "animals": []
}
```

### Resumen del contrato v4 — campos nuevos y denominadores

| Campo | Nivel | Tipo | Denominador / regla de NULL |
|-------|-------|------|-----------------------------|
| `animals[].max_present` | animal | `integer \| null` | `max(present)` sobre `n_valid`. `null` si `n_valid = 0`. |
| `total_animals` | sección | objeto | Reportes con TODOS los animales no nulos. Excluye reportes con cualquier `present = NULL`. |
| `total_animals.avg` | — | `number \| null` | Media sobre `n_valid` reportes. `null` si `n_valid = 0`. |
| `total_animals.mode` | — | `array[int]` | Moda sobre `n_valid`. `[]` si `n_valid = 0`. |
| `total_animals.max` | — | `integer \| null` | `null` si `n_valid = 0`. |
| `total_animals.n_valid` | — | `integer` | Reportes con victoria completa (ningún `present = NULL`). |
| `total_animals.n_total` | — | `integer` | = `n_reports_in_section`. |
| `avg_bounty` | sección | objeto | Todos los reportes de la sección (`n_reports_in_section`), incl. derrotas con bounty=0. |
| `avg_bounty.wood/clay/iron/crop/total` | — | `integer` | Media redondeada al entero. `0` si `n_reports_in_section = 0`. |
| `oasis_coords` | sección | `array[{x,y}]` | Oasis con al menos un gap en la ventana. Ordenados `y ASC, x ASC`. `[]` si sección vacía. |

### Reglas de negocio nuevas (v4)

**RN-TD20 — max_present por animal: máximo sobre n_valid.**
`max_present = max(present for present not null)`. Si `n_valid = 0` → `max_present = null`.
Consistente con la exclusión de NULL ya establecida en RN-TD05, RN-TD06, RN-TD07.

**RN-TD21 — total_animals: denominador = reportes con TODOS los animales no nulos.**
El total de animales de un reporte se computa SOLO si ningún animal de ese reporte tiene
`present = NULL`. Si hay cualquier NULL en el reporte → reporte excluido de `n_valid`
del total (pero incluido en `n_total`). `avg/mode/max` calculados sobre `n_valid`.

**RN-TD22 — avg_bounty: denominador = n_reports_in_section (incluye derrotas).**
`bounty_wood/clay/iron/crop` son `NOT NULL DEFAULT 0` en el DDL. Una derrota guarda 0.
El denominador incluye todos los reportes de la sección, incluidas las derrotas con
botín = 0. `0` si `n_reports_in_section = 0`.

**RN-TD23 — avg_bounty.total: media del bounty total del reporte.**
`avg_bounty.total = round(mean(bounty_wood + bounty_clay + bounty_iron + bounty_crop))`.
No es la suma aritmética de `avg_bounty.wood + clay + iron + crop` (pueden diferir
en ±1 por el redondeo independiente). El campo `total` se calcula directamente sobre
la suma por reporte, no sobre los promedios individuales.

**RN-TD24 — oasis_coords: lista de oasis distintos con gap en la ventana.**
Las coordenadas provienen de `type_oasis_ids[tipo]` (ya construido en v3). Se serializa
como `[{x: cx, y: cy}]` ordenado por `(cy ASC, cx ASC)`. Formato: enteros crudos.
El frontend formatea como `(-15|23)` o el formato que prefiera. Sin cap en v4.

**RN-TD25 — avg_bounty: botín acumulado por report_id (no por fila de animal).**
La CTE `report_gaps` tiene una fila por reporte. El JOIN con `attack_report_animals`
produce múltiples filas por reporte (una por animal). El botín debe leerse del nivel
del reporte, no sumarse por cada fila de animal. Implementación: añadir
`bounty_wood, bounty_clay, bounty_iron, bounty_crop` al SELECT de `report_gaps` (la CTE
ya opera a nivel de reporte), y acceder a esos campos desde las filas del JOIN result.
Dado que `report_gaps` ya garantiza una fila por reporte, el botín aparece repetido en
cada fila de animal del JOIN — usar deduplicación por `report_id` para el botín
(`type_bounty[tipo]` como `dict[report_id → (w, c, i, cr)]`).

### Edge cases nuevos (v4)

| # | Edge case | Tratamiento |
|---|-----------|-------------|
| EC-TD28 | Todos los reportes de la sección son derrotas (`present = NULL` en todos) | `total_animals = {avg: null, mode: [], max: null, n_valid: 0, n_total: N}`. `avg_bounty = {wood: 0, ...}` (bounty = 0 en derrotas). `animals = []` (ya era así en v3). |
| EC-TD29 | Reporte con algunos animales `present = NULL` y otros no nulos ("derrota parcial") | El reporte se excluye de `total_animals.n_valid`. Se incluye en `total_animals.n_total`. Sigue siendo un edge case teórico; el parser normal produce toda la fila NULL en derrota. |
| EC-TD30 | Sección con un solo reporte y `present` no nulo en todos sus animales | `total_animals = {avg: <total>, mode: [<total>], max: <total>, n_valid: 1, n_total: 1}`. |
| EC-TD31 | Botín totalmente 0 en todos los reportes de la sección (todos ataques en vacío o derrotas) | `avg_bounty = {wood: 0, clay: 0, iron: 0, crop: 0, total: 0}`. No es un error. |
| EC-TD32 | Un oasis de tipo "hierro" con un solo report_id en la ventana | `oasis_coords` contiene exactamente 1 elemento. |
| EC-TD33 | Sección vacía (`n_reports_in_section = 0`) | `oasis_coords: []`, `avg_bounty` con todos a 0, `total_animals` con todos a null/0/[]. |
| EC-TD34 | Empate en `mode` del total de animales | `mode: [v1, v2]` (todos los empatados ASC), consistente con RN-TD07. |
| EC-TD35 | Dos oasis del mismo tipo con coordenadas distintas | `oasis_coords` contiene ambos, ordenados `(y ASC, x ASC)`. |

### Notas para la UI (v5 — tarea separada)

- La UI (`AnimalFrequencyPanel.jsx`) requiere nuevo rediseño por el agente `disenador-producto`
  (v5) para mostrar los 4 campos nuevos: `max_present` en la fila de animal, zona de
  "resumen del tipo" con `total_animals` + `avg_bounty` + `oasis_coords`.
- Antes de implementar la UI, se requiere nuevo mockup editable + gate humano de aprobación
  (regla "mockup-first" del proyecto).
- El agente `desarrollador-ux-ui` debe centralizar el formateador de coordenadas en un
  módulo compartido `coordUtils.js` (actualmente hay 5 copias identificadas por palantir:
  OasisList:45, HistoryTable:29, ReportPreview:22, OasisStatsPanel:27,
  OasisCombatPlannerPanel:124). Esta centralización forma parte de la tarea de UI v5,
  no del backend v4.

---

## REVISIÓN v3 — Segmentación por tipo de oasis inferido

> Esta sección documenta el nuevo diseño sobre v2 ya implementado (39 tests en verde).
> El resto del spec (secciones 1-16) ha sido actualizado para reflejar v3.
> El §"Qué cambia respecto a v2" al final del spec lista los cambios concretos para cada agente.

### Motivación

El usuario quiere entender cómo varía la composición de animales según el **tipo de oasis**
(Hierro, Arcilla, Madera, Cereal) a una cadencia dada. Un oasis de madera respawna lobos y osos;
uno de hierro respawna ratas y murciélagos. Mezclarlos en una sola lista oculta esa señal.

### Principio de diseño: inferencia por oasis, reutilización total de lógica existente

El tipo de oasis **no está almacenado** en la BD. Se **infiere** en tiempo de consulta a partir
de los animales observados, reutilizando sin duplicar la lógica ya implementada en EP-SPAWN:

- **`_infer_type(observed_ordinales, comp_list)`** — función en
  `adapters/db/attack_report_sqlite_adapter.py` (~línea 1953). Usa similitud de Jaccard
  contra `OASIS_TYPE_SETS`. Devuelve `(tipo: str|None, confidence: "low"|"medium"|None)`.
  Confianza "medium" si `sum(burst_count) >= 3`, "low" si < 3.
- **`OASIS_TYPE_SETS`** — en `core/game_data/oasis_spawn_catalog.py` (~línea 54):
  - `"hierro":  {1, 2, 4}`   — rata, araña, murciélago
  - `"arcilla": {1, 2, 5}`   — rata, araña, jabalí
  - `"madera":  {5, 6, 7}`   — jabalí, lobo, oso
  - `"cereal":  {1..10}`     — todos (set universal)

**Regla de elevación:** `_infer_type` es actualmente privada (prefijo `_`). Para que EP-TD
pueda llamarla, el implementador debe **renombrarla a `infer_type` (sin guión bajo)** o
extraerla a un módulo compartido (p.ej. `adapters/db/_oasis_type_utils.py`). Lo que NO debe
hacer es reimplementar el cálculo de Jaccard: un tercer Jaccard divergente sería un bug
esperando explotar. La decisión de elevación (renombrar vs. módulo) se deja al implementador,
pero debe documentarse en el Registro de implementación v3.

### Clasificación de cada oasis: una vez, sobre el agregado

La inferencia se hace **una vez por oasis** sobre el conjunto de todos sus animales observados
con `present > 0`, no por reporte individual. Cada gap de ese oasis hereda el tipo inferido
de su oasis.

El proceso exacto de obtención de `observed_ordinales` y `comp_list` por oasis es el mismo
que ya hace EP-SPAWN en `get_oasis_spawn_composition` (~línea 1539-1651):

```sql
-- Composicion por (oasis, animal) — solo present > 0
SELECT
    r.coord_x_dest,
    r.coord_y_dest,
    a.animal_ordinal,
    COUNT(*) AS burst_count
FROM attack_report_animals a
JOIN attack_reports r ON r.id = a.report_id
WHERE a.present > 0
GROUP BY r.coord_x_dest, r.coord_y_dest, a.animal_ordinal
```

De este resultado se construye por oasis:
- `observed_ordinales: set[int]` — set de ordinales con `present > 0`
- `comp_list: list[dict]` — lista con `{"animal_ordinal": int, "burst_count": int, ...}`

Y se llama `tipo, confidence = infer_type(observed_ordinales, comp_list)`.

**Resultado:** cada par `(coord_x_dest, coord_y_dest)` queda etiquetado con su `tipo` e `confidence`.
Este mapa `{(cx, cy): (tipo, confidence)}` se usa luego en el paso de agrupación de gaps.

### Gestión de baja confianza y oasis no clasificables

| Situación | Tratamiento |
|-----------|-------------|
| `confidence = "medium"` (>=3 bursts con present>0) | Oasis incluido en su sección de tipo con plena confianza. |
| `confidence = "low"` (<3 bursts con present>0) | Oasis incluido en su sección de tipo **con marca de baja confianza** (el n_oasis de esa sección cuenta los de low también). La sección expone `n_oasis_low_confidence` para que el front pueda mostrar un disclaimer. |
| `tipo = None` (sin ningún animal observado con present>0, p.ej. solo derrotas) | Oasis y todos sus gaps van a la sección `"sin_clasificar"`. |
| Oasis con todos los gaps descartados (< 6 min, o < 2 reportes) | No genera gaps en la ventana — no aparece en ninguna sección. No es necesario clasificarlo. |

**Justificación de incluir low-confidence en su sección:** excluirlos crearía la ilusión de
que ciertos tipos de oasis están "vacíos" cuando en realidad hay datos, aunque pocos. Es más
honesto mostrar el dato con su señal de confianza que ocultarlo. El front puede elegir añadir
un icono o nota "pocos datos" junto a la cifra.

### Problema del cereal y cómo lo resuelve Jaccard

El set de cereal es `{1..10}` (universal). Si usáramos solapamiento bruto, cualquier oasis
clasificaría como cereal con alta puntuación. Jaccard penaliza el set universal porque
`|∩| / |∪|` crece más lentamente cuando el denominador es grande:

- Oasis con animales `{1,2,4}` (hierro): Jaccard(hierro)=1.0, Jaccard(cereal)=3/10=0.30 → **hierro gana**.
- Oasis con animales `{5,6,7}` (madera): Jaccard(madera)=1.0, Jaccard(cereal)=3/10=0.30 → **madera gana**.
- Oasis con animales `{1,2,4,5,6,7,8,9,10}` (9 tipos muy variados): Jaccard(cereal)=9/10=0.90 → **cereal** — correcto, es un oasis cereal.

**Limitación del cereal que el frontend debe comunicar:** un oasis con animales muy diversos
puede clasificarse como cereal correctamente, pero la etiqueta "Cereal" cubre el 100% de los
tipos de animal. El frontend debe añadir una nota junto a la sección "Cereal" del estilo
"Oasis con composición variada — incluye todos los tipos de animal". Esto no es un bug; es
la naturaleza del oasis cereal en Travian.

### Response schema v3: agrupado por tipo

La respuesta añade el campo `types` (lista de secciones) en lugar del campo `animals` (plano).
El campo `animals` v2 **desaparece** del nivel raíz y queda dentro de cada sección de tipo.

**Schema completo v3:**

```json
{
  "interval_minutes": 240,
  "interval_label": "4h",
  "window": {
    "lower_min": 240,
    "upper_min": 300,
    "is_open": false
  },
  "n_reports_in_window": 42,
  "types": [
    {
      "oasis_type": "hierro",
      "oasis_type_label": "Hierro",
      "n_oasis": 3,
      "n_oasis_low_confidence": 1,
      "n_reports_in_section": 18,
      "animals": [
        {
          "animal_ordinal": 1,
          "animal_name": "Rata",
          "icon_url": "/static/icons/nature_1.png",
          "avg_present": 2.50,
          "mode_present": [2],
          "n_total": 18,
          "n_valid": 15
        }
      ]
    },
    {
      "oasis_type": "arcilla",
      "oasis_type_label": "Barro",
      "n_oasis": 2,
      "n_oasis_low_confidence": 0,
      "n_reports_in_section": 14,
      "animals": [...]
    },
    {
      "oasis_type": "madera",
      "oasis_type_label": "Madera",
      "n_oasis": 4,
      "n_oasis_low_confidence": 2,
      "n_reports_in_section": 7,
      "animals": [...]
    },
    {
      "oasis_type": "cereal",
      "oasis_type_label": "Cereal",
      "n_oasis": 1,
      "n_oasis_low_confidence": 0,
      "n_reports_in_section": 3,
      "animals": [...]
    },
    {
      "oasis_type": "sin_clasificar",
      "oasis_type_label": "Sin clasificar",
      "n_oasis": 1,
      "n_oasis_low_confidence": 0,
      "n_reports_in_section": 0,
      "animals": []
    }
  ]
}
```

**Descripción de los campos nuevos y modificados:**

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `n_reports_in_window` | `integer` | Total de gaps en la ventana (suma de `n_reports_in_section` de todas las secciones). Campo raiz, igual que en v2. |
| `types` | `array[5]` | Siempre exactamente 5 elementos (uno por tipo). Ver orden abajo. |
| `types[].oasis_type` | `string` | Clave canonica interna: `"hierro"`, `"arcilla"`, `"madera"`, `"cereal"`, `"sin_clasificar"`. |
| `types[].oasis_type_label` | `string` | Etiqueta de presentacion (fija, no localizada): `"Hierro"`, `"Barro"`, `"Madera"`, `"Cereal"`, `"Sin clasificar"`. OJO: la clave interna sigue siendo `"arcilla"` (del catalogo) pero el label es `"Barro"` (el usuario usa ese nombre). |
| `types[].n_oasis` | `integer` | Numero de oasis distintos de este tipo que tienen al menos un gap en la ventana. |
| `types[].n_oasis_low_confidence` | `integer` | Cuantos de esos oasis tienen `confidence = "low"`. `0` si ninguno. |
| `types[].n_reports_in_section` | `integer` | Numero de gaps (report_ids distintos) de oasis de este tipo en la ventana. `0` si no hay datos. |
| `types[].animals` | `array` | Lista de animales con estadisticas (mismos campos que en v2: `animal_ordinal`, `animal_name`, `icon_url`, `avg_present`, `mode_present`, `n_total`, `n_valid`). `[]` si `n_reports_in_section=0`. Orden: `animal_ordinal ASC`. |

**Nota importante sobre `n_total` dentro de animals en v3:** `n_total` de un animal dentro
de una seccion de tipo es el numero de gaps de oasis de ESE tipo en la ventana donde aparece
ese animal (incluye derrotas). No es el total global. La suma de `n_total` de todos los
animales de una seccion puede ser mayor que `n_reports_in_section` porque un mismo ataque
puede tener varios tipos de animal.

**Orden de las secciones (fijo):** `hierro`, `arcilla`, `madera`, `cereal`, `sin_clasificar`.
Este orden coincide con la progresion de los sets de especificidad (de mas especificos a mas
generales) y es predecible para el frontend.

**Las 5 secciones se devuelven siempre**, aunque esten vacias (`n_reports_in_section=0`,
`animals=[]`). Justificacion: el frontend necesita estructuras predecibles para renderizar
"Sin datos para este tipo a esta cadencia" sin hacer comprobaciones de presencia de clave.
Una seccion vacia es semanticamente diferente de una clave ausente.

**Sin parametro de filtro por tipo:** el endpoint siempre devuelve las 5 secciones. No se
anade un param `oasis_type` opcional porque el usuario eligio "todos los tipos a la vez"
y la complejidad adicional no aportaria valor.

---

## REVISIÓN v2 — Frecuencias en minutos + lista simple + binning umbral-inferior

> Esta seccion documenta el rediseno completo respecto a la implementacion v1.
> El resto del spec ha sido actualizado para reflejar v3 (que incluye v2).
> El apartado "Que cambia respecto a v2" al final del spec lista los cambios concretos para cada agente.

### Nuevo parámetro: `interval_minutes`

Sustituye a `bucket_hours`. El usuario elige UNA frecuencia discreta en minutos entre las
siguientes (conjunto cerrado, sin excepciones):

| Valor | Etiqueta | Significado |
|-------|----------|-------------|
| `6`   | `"6 min"` | Cadencia ultrarrápida |
| `7`   | `"7 min"` | Cadencia rápida |
| `10`  | `"10 min"` | |
| `15`  | `"15 min"` | |
| `30`  | `"30 min"` | Media hora |
| `60`  | `"1h"` | Hora |
| `120` | `"2h"` | |
| `180` | `"3h"` | |
| `240` | `"4h"` | Default (ventana de sueño del usuario) |
| `300` | `"5h"` | |

- Valor fuera del conjunto (p.ej. `interval_minutes=45`) → `400` con detail legible.
- Valor no entero o formato inválido → `422` (FastAPI validation automática).
- `interval_minutes` ausente → `200` con default `240` (4 horas).

### Binning por umbral inferior (Opción B)

Cada valor `F` del conjunto corresponde a una ventana `[F, F_next)` donde `F_next` es el
siguiente valor del conjunto en orden ascendente. La ventana de `300` (el último) es abierta
por arriba: `[300, ∞)`.

**Tabla de bins completa:**

| `interval_minutes` | Ventana | `lower_min` | `upper_min` | `is_open` |
|--------------------|---------|-------------|-------------|-----------|
| `6`   | `[6, 7)`    | 6   | 7   | false |
| `7`   | `[7, 10)`   | 7   | 10  | false |
| `10`  | `[10, 15)`  | 10  | 15  | false |
| `15`  | `[15, 30)`  | 15  | 30  | false |
| `30`  | `[30, 60)`  | 30  | 60  | false |
| `60`  | `[60, 120)` | 60  | 120 | false |
| `120` | `[120, 180)`| 120 | 180 | false |
| `180` | `[180, 240)`| 180 | 240 | false |
| `240` | `[240, 300)`| 240 | 300 | false |
| `300` | `[300, ∞)`  | 300 | null| true  |

**Frontera: inclusiva por abajo, exclusiva por arriba `[F, F_next)`.**

Un gap de exactamente `F` minutos pertenece al bin `F`, no al bin anterior.
Un gap de `F_next - ε` minutos pertenece al bin `F`, no al bin `F_next`.

**Justificación de Opción B vs. vecino-más-cercano:**

La asignación por umbral inferior es monótona y robusta al ruido de lag: un timer configurado
a 7 min que por latencia o imprecisión del reloj tarda 9 min sigue contando como cadencia de
7 min (cae en `[7, 10)`), sin saltar al bin de 10 min. El vecino-más-cercano rompería esa
propiedad: un gap de 8.5 min estaría a 1.5 min del umbral 7 y a 1.5 min del umbral 10, y la
decisión de asignación dependería del ruido, no de la intención del usuario. La Opción B
elimina esa ambigüedad: el bin es el umbral inferior de la ventana en que cae el gap, sin
excepción.

### Gaps fuera de rango (< 6 min)

Gaps con `gap_seconds < 360` (< 6 minutos) quedan **fuera de todos los bins** del conjunto.
Se **descartan silenciosamente** (no se cuentan en ninguna ventana).

Justificación: no existe ninguna frecuencia inferior a 6 min en el conjunto de valores
permitidos. Incluirlos en el bin de 6 min distorsionaría las estadísticas de esa cadencia
(mezclaría gaps genuinamente rápidos con anomalías de reloj o duplicados). Se anota en el
log de diagnóstico pero no se devuelve al cliente.

Adicionalmente, los gaps nulos (primer ataque por oasis) y los gaps ≤ 0 (relojes
inconsistentes) siguen descartándose como en v1 (RN-TD02 y EC-TD07).

### Response schema de UNA frecuencia (v2)

La respuesta ya no es una matriz por franja: el cliente elige UNA frecuencia y recibe la
estadística de la ventana correspondiente. Schema definitivo:

```json
{
  "interval_minutes": 240,
  "interval_label": "4h",
  "window": {
    "lower_min": 240,
    "upper_min": 300,
    "is_open": false
  },
  "n_reports_in_window": 18,
  "animals": [
    {
      "animal_ordinal": 6,
      "animal_name": "Lobo",
      "icon_url": "/static/icons/nature_6.png",
      "avg_present": 3.40,
      "mode_present": [3],
      "n_total": 18,
      "n_valid": 15
    }
  ]
}
```

**Descripción de campos:**

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `interval_minutes` | `integer` | Frecuencia solicitada (echo del parámetro). |
| `interval_label` | `string` | Etiqueta legible: `"6 min"`, `"7 min"`, `"10 min"`, `"15 min"`, `"30 min"`, `"1h"`, `"2h"`, `"3h"`, `"4h"`, `"5h+"`. El bin `300` lleva `"5h+"` para indicar que es abierto. |
| `window.lower_min` | `integer` | Límite inferior de la ventana en minutos (inclusive). |
| `window.upper_min` | `integer\|null` | Límite superior en minutos (exclusive). `null` para `interval_minutes=300`. |
| `window.is_open` | `boolean` | `true` solo para `interval_minutes=300`. |
| `n_reports_in_window` | `integer` | Número de gaps (ataques) que caen en la ventana. Incluye reportes con `present=null`. `0` si la ventana está vacía. |
| `animals` | `array` | Lista de animales con observaciones en la ventana. Orden: `animal_ordinal ASC`. `[]` si `n_reports_in_window=0`. |
| `animals[].animal_ordinal` | `integer` | Ordinal del animal (1-10, catálogo NATURE). |
| `animals[].animal_name` | `string` | Nombre localizado del animal. |
| `animals[].icon_url` | `string` | `/static/icons/nature_{ordinal}.png` |
| `animals[].avg_present` | `number\|null` | Media de `present` redondeada a 2 decimales. `null` si `n_valid=0`. |
| `animals[].mode_present` | `array[integer]` | Moda(s) de `present`. `[]` si `n_valid=0`. Empates: todos ASC. |
| `animals[].n_total` | `integer` | Reportes en la ventana para este animal (incluye derrotas con `present=null`). |
| `animals[].n_valid` | `integer` | Reportes con `present IS NOT NULL` en la ventana. |

**Estado "frecuencia sin datos":** si `n_reports_in_window = 0`, se devuelve
`200` con `animals: []`. El frontend mostrará el empty state: *"Aún no tienes suficientes
ataques con esta cadencia"*. Nunca `404`.

**Nota sobre `n_total` a nivel de `animals[]`:** cada animal puede tener un `n_total`
distinto porque no todos los animales aparecen en todos los reportes. La suma de
`animals[i].n_total` para todos los animales no tiene por qué ser igual a
`n_reports_in_window` (que cuenta reportes/gaps, no apariciones).

---

## 1. Objetivo de negocio

El usuario ataca oasis repetidamente y necesita saber **cuántos animales suelen aparecer**
en función de la cadencia de farmeo que utiliza. Con esa información puede calibrar la
frecuencia de sus ataques a cada oasis para maximizar el botín y evitar ataques en vacío.

El endpoint calcula, para una cadencia concreta elegida por el usuario (p.ej. "cada 4h"),
cuántas veces apareció cada tipo de animal en reportes cuyo gap con el ataque anterior cae
en la ventana correspondiente a esa cadencia, junto con la media y la moda del número de
unidades observadas. Esto permite responder preguntas como: "si farmeo cada 4h,
¿cuántos lobos suelen aparecer?"

## 2. Actores y permisos

- **Usuario del dashboard** (único actor). Solo lectura. Sin autenticación adicional más allá
  de la que ya protege la aplicación.

## 3. Alcance

### Dentro del alcance

- Modificar el endpoint `GET /attack-reports/stats/oasis/temporal-distribution` (EP-TD):
  cambiar el schema de respuesta de lista plana (`animals[]`) a lista agrupada por tipo
  (`types[]` con 5 secciones fijas: hierro, arcilla, madera, cereal, sin_clasificar).
- Elevar `_infer_type` a funcion publica/modulo en `adapters/db/attack_report_sqlite_adapter.py`
  (renombrar a `infer_type` o extraer a modulo compartido) para que EP-TD pueda reutilizarla
  sin duplicar el calculo de Jaccard.
- Modificar el metodo abstracto en `AttackReportPort`:
  `get_animal_temporal_distribution(interval_minutes, lang)` — la firma no cambia pero el
  tipo de retorno incluye `types` en lugar de `animals`.
- Modificar la implementacion en `AttackReportSQLiteAdapter`: nueva query de composicion por
  oasis, mapa de tipo por oasis con `infer_type`, agrupacion de gaps por tipo, calculo de
  estadisticas por (tipo x animal).
- **La UI** (componente `AnimalFrequencyPanel.jsx`) requiere **rediseno completo** por el
  agente `disenador-producto` (la vista pasa de lista plana a secciones por tipo de oasis)
  + **nuevo mockup editable aprobado** por el usuario **antes de implementarse**.
  Este spec cubre unicamente el backend + contrato de API.

### Dentro del alcance (delta v4)

- Añadir `max_present` a cada elemento de `animals[]` dentro de cada sección de tipo.
- Añadir `total_animals` (objeto con avg/mode/max/n_valid/n_total) a cada sección de tipo.
- Añadir `avg_bounty` (objeto con wood/clay/iron/crop/total) a cada sección de tipo.
- Añadir `oasis_coords` (lista de `{x, y}`) a cada sección de tipo.
- Extender la CTE `report_gaps` del adapter para incluir los campos de botín.
- Añadir estructura auxiliar `type_bounty` y `type_report_totals` al paso de agrupación.
- Actualizar el response model / schema de la API.
- Actualizar los tests del módulo (añadir casos nuevos, sin eliminar los existentes de v3).

### Fuera del alcance (v4)

- Consulta simultanea de multiples frecuencias (el cliente pide una por request).
- Filtro por oasis especifico (solo global).
- Filtro por rango de fechas.
- Filtro por tipo de oasis como parametro de query (el endpoint devuelve siempre las 5 secciones).
- Agrupacion individual por oasis dentro de una seccion.
- Paginacion.
- Comparativa entre oasis.
- Percentiles o histogramas de distribucion de unidades (solo media y moda).
- Exposicion de gaps descartados (< 6 min) al cliente.
- Localizacion de `oasis_type_label` (etiqueta fija en castellano: "Hierro", "Barro", "Madera", "Cereal", "Sin clasificar").
- `oasis_coords` con cap explícito (sin límite en v4; ver RN-TD24).
- Detalle de confianza individual por oasis dentro de `oasis_coords` (solo coords en v4).
- Centralización de coordUtils.js (tarea de UI v5, no del backend).
- Rediseño de la UI (AnimalFrequencyPanel.jsx): requiere disenador-producto v5 + mockup editable + gate humano.

## 4. Reglas de negocio

**RN-TD01 — Base temporal: gap empírico entre ataques consecutivos.**
El gap de un reporte se calcula como la diferencia en segundos entre `attacked_at` del reporte
actual y `attacked_at` del reporte inmediatamente anterior al mismo oasis
(`PARTITION BY coord_x_dest, coord_y_dest ORDER BY attacked_at`), usando `LAG()`.
`attacked_at` se trata como naive (sin zona horaria) — todos los timestamps están en el mismo
reloj de servidor, por lo que las diferencias son correctas sin conversión.

**RN-TD02 — Primer ataque a cada oasis: descartado.**
El primer reporte de un oasis no tiene ataque previo → su gap es `NULL` → se descarta.
No contribuye a ninguna ventana.

**RN-TD03 — Binning por umbral inferior (Opción B).**
Dado `interval_minutes = F`, la ventana es `[F * 60, F_next * 60)` en segundos, donde
`F_next` es el siguiente valor del conjunto `{6,7,10,15,30,60,120,180,240,300}` en orden
ascendente. Para `F = 300` la ventana es `[18000, ∞)` (abierta por arriba).

La asignación es determinista y monótona: un gap `g` en segundos pertenece a la ventana `F`
si y solo si `F * 60 <= g < F_next * 60` (o `g >= 18000` para el bin `300`).

El cálculo del bin es en Python (no en SQL). SQL devuelve los gaps en segundos y Python
determina si caen en la ventana de la frecuencia solicitada.

**RN-TD04 — Gaps fuera de rango (< 6 min) descartados.**
Gaps con `gap_seconds < 360` no pertenecen a ningún bin del conjunto (no existe bin menor que
6 min). Se descartan silenciosamente. No se devuelven al cliente ni se cuentan en
`n_reports_in_window`.

**RN-TD05 — NULL en present (derrota): se excluye de media y moda, se cuenta en n_total.**
Cuando el resultado del combate fue derrota, `present = NULL` (desconocido). Para un animal:
- Se cuenta en `n_total` (el reporte ocurrió, tiene gap en la ventana → pertenece).
- No se cuenta en `n_valid` (no hay dato de cuántos animales había).
- No contribuye a `avg_present` ni a `mode_present`.

**RN-TD06 — Media: redondeada a 2 decimales.**
`avg_present = round(mean(present) for present not null, 2)`. Si `n_valid = 0` →
`avg_present = null`.

**RN-TD07 — Moda: calculada en Python, empates como lista.**
SQLite no tiene `MODE()`. La moda se calcula en Python con `collections.Counter` sobre los
valores de `present` no nulos. Si hay un único valor máximo → `mode_present = [valor]`.
Si hay empate → `mode_present` contiene todos los valores empatados, ordenados ASC.
Si `n_valid = 0` → `mode_present = []`.

**RN-TD08 — n_reports_in_window y n_total/n_valid por animal.**
- `n_reports_in_window` (nivel raíz): número de gaps (ataques al mismo oasis) que caen en
  la ventana. Incluye reportes con `present=null`. Es el denominador de "cuántos ataques
  tienes en esta cadencia".
- `animals[].n_total`: reportes en la ventana para ese animal (incluye derrotas).
- `animals[].n_valid`: reportes con `present IS NOT NULL`.
La suma de `animals[i].n_total` puede ser distinta de `n_reports_in_window` porque no todos
los animales aparecen en todos los reportes.

**RN-TD09 — Orden de resultados.**
Animales: por `animal_ordinal ASC` (coherente con el catálogo Nature).

**RN-TD10 — Nombres de animal localizados por Accept-Language.**
`Accept-Language` es obligatorio. Se resuelve con la dependencia `get_language` de
`adapters/api/dependencies.py`. El nombre localizado se obtiene de
`translation_port.get_troop_names_by_tribe(Tribe.nature, lang)` y se indexa por ordinal.
Fallback: si el ordinal no tiene nombre en el catálogo para ese idioma, se usa el nombre
guardado en `animal_name` de la BD (texto crudo).

**RN-TD11 — Scope: solo global.**
El cálculo agrega todos los oasis. Usa el mismo patrón LAG de EP-09: `PARTITION BY
coord_x_dest, coord_y_dest` garantiza que los gaps no cruzan oasis distintos.

**RN-TD12 — Estado vacío: 200 con n_reports_in_window=0 y animals=[].**
Si ningún gap cae en la ventana solicitada (BD vacía, sin datos suficientes, o frecuencia
sin observaciones) → `200` con `n_reports_in_window: 0` y `animals: []`.
Nunca `404`.

**RN-TD13 — Valores válidos de interval_minutes.**
`interval_minutes` ∈ `{6, 7, 10, 15, 30, 60, 120, 180, 240, 300}`.
Cualquier otro valor entero → `400` con detail legible que enumera los valores aceptados.
Valor no entero → `422` (FastAPI validation automática).
Ausente → `200` con default `240` (4 horas).

**RN-TD14 — Inferencia de tipo por oasis (v3).**
El tipo de cada oasis se infiere UNA sola vez sobre el agregado de todos sus animales observados
con `present > 0`, usando `infer_type(observed_ordinales, comp_list)` (funcion elevada desde
`_infer_type` del adapter). La inferencia usa Jaccard contra `OASIS_TYPE_SETS`. Devuelve
`(tipo, confidence)` donde `tipo` es `"hierro"|"arcilla"|"madera"|"cereal"|None` y
`confidence` es `"medium"` (>= 3 bursts) o `"low"` (< 3 bursts) o `None` (sin datos).
Cada gap de ese oasis hereda ese `tipo`. Este calculo precede a la agrupacion de gaps.

**RN-TD15 — Oasis sin tipo inferido van a "sin_clasificar" (v3).**
Un oasis con `tipo = None` (sin ningun animal observado con `present > 0`, p.ej. solo
reportes de derrota) no puede clasificarse. Todos sus gaps se agrupan bajo `"sin_clasificar"`.

**RN-TD16 — Oasis de baja confianza se incluyen en su seccion de tipo (v3).**
Un oasis con `confidence = "low"` (< 3 bursts con `present > 0`) se incluye en la seccion
correspondiente a su tipo inferido, no en `"sin_clasificar"`. El campo
`n_oasis_low_confidence` de la seccion informa cuantos oasis tienen baja confianza, para
que el frontend pueda mostrar un disclaimer. Excluir oasis de baja confianza ocultaria datos
reales; incluirlos con marca de confianza es mas honesto.

**RN-TD17 — Cinco secciones fijas, siempre presentes (v3).**
La respuesta siempre contiene exactamente 5 secciones en orden fijo:
`hierro`, `arcilla`, `madera`, `cereal`, `sin_clasificar`.
Una seccion sin datos se devuelve con `n_oasis=0`, `n_oasis_low_confidence=0`,
`n_reports_in_section=0`, `animals=[]`. Nunca se omite una seccion del array.

**RN-TD18 — Etiqueta "Barro" para la clave canonica "arcilla" (v3).**
La clave interna del catalogo es `"arcilla"` (de `OASIS_TYPE_SETS`). La etiqueta de
presentacion es `"Barro"` (terminologia del usuario). Nunca se cambia la clave interna;
solo el `oasis_type_label`. Esto se resuelve con un dict de labels en el adapter:
`{"hierro": "Hierro", "arcilla": "Barro", "madera": "Madera", "cereal": "Cereal", None: "Sin clasificar"}`.

**RN-TD19 — n_reports_in_window es la suma de todas las secciones (v3).**
`n_reports_in_window` (campo raiz) = suma de `n_reports_in_section` de las 5 secciones.
Mantiene el mismo significado semantico de v2 (numero total de gaps en la ventana).

**RN-TD20 — max_present por animal: máximo sobre n_valid (v4).**
Ver definición completa en §REVISIÓN v4, campo 1.

**RN-TD21 — total_animals: denominador = reportes con TODOS los animales no nulos (v4).**
Ver definición completa en §REVISIÓN v4, campo 2.

**RN-TD22 — avg_bounty: denominador = n_reports_in_section, incluye derrotas (v4).**
Ver definición completa en §REVISIÓN v4, campo 3.

**RN-TD23 — avg_bounty.total: media del bounty total del reporte (no suma de medias) (v4).**
Ver definición completa en §REVISIÓN v4, campo 3.

**RN-TD24 — oasis_coords: lista de oasis distintos con gap en la ventana (v4).**
Ver definición completa en §REVISIÓN v4, campo 4.

**RN-TD25 — avg_bounty: botín acumulado por report_id (no por fila de animal) (v4).**
Ver definición completa en §REVISIÓN v4, campo 3.

## 5. Flujo principal y flujos alternativos

### Flujo principal (v3)
1. Cliente envía `GET /attack-reports/stats/oasis/temporal-distribution?interval_minutes=240`
   con cabecera `Accept-Language: es`.
2. FastAPI valida `interval_minutes` (entero, tipo). Si ausente → usa default `240`.
3. El router valida manualmente que `interval_minutes` ∈ `{6,7,10,15,30,60,120,180,240,300}`
   → `400` si no está.
4. El router resuelve `lang` con `get_language`.
5. El router llama a `port.get_animal_temporal_distribution(interval_minutes=240, lang="es")`.
6. **[NUEVO v3]** El adapter ejecuta la query de composicion por oasis (`present > 0`) para
   construir el mapa de tipos: `{(cx, cy): (tipo, confidence)}` usando `infer_type`.
7. El adapter ejecuta la query LAG en SQLite para obtener todos los gaps validos con sus
   datos de animal y las coordenadas del oasis.
8. El adapter filtra en Python: descarta `gap_seconds IS NULL`, `gap_seconds <= 0` y
   `gap_seconds < 360` (< 6 min).
9. El adapter filtra los gaps que caen en la ventana `[240*60, 300*60)` (en segundos).
10. **[NUEVO v3]** El adapter etiqueta cada gap con el tipo de su oasis usando el mapa del paso 6.
    Gaps de oasis sin tipo en el mapa (sin ningun `present > 0`) → tipo `None` → "sin_clasificar".
11. **[NUEVO v3]** El adapter agrupa los gaps por tipo, luego por animal_ordinal dentro de cada
    tipo, y calcula `n_oasis`, `n_oasis_low_confidence`, `n_reports_in_section`, `n_total`,
    `n_valid`, `avg_present`, `mode_present` por (tipo, animal).
    **[NUEVO v4]** En el mismo bucle acumula también:
    - `type_bounty[tipo][report_id] = (w, c, i, cr)` — botín por reporte (deduplicado por report_id).
    - `type_report_animal_nulls[tipo][report_id] = any_null_flag` — si el reporte tiene algún `present = NULL`.
    - `type_report_animal_sums[tipo][report_id] = sum_present` — suma de `present` no nulos del reporte.
12. El adapter resuelve nombres localizados via `translation_port`.
13. **[NUEVO v3]** El adapter construye el array `types` con las 5 secciones fijas en orden
    `hierro → arcilla → madera → cereal → sin_clasificar`. Secciones vacias incluidas.
    **[NUEVO v4]** Para cada sección, calcula:
    - `max_present` por animal (de `data["valids"]`).
    - `total_animals` (avg/mode/max/n_valid/n_total) sobre los report_ids con `any_null = False`.
    - `avg_bounty` (wood/clay/iron/crop/total) sobre todos los report_ids de la sección.
    - `oasis_coords` serializando `type_oasis_ids[tipo]` como lista `{x, y}` ordenada.
14. El adapter construye la respuesta raiz con `n_reports_in_window` (suma de secciones) y `types`.
15. El router serializa y responde `200`.

### Flujos alternativos
- **`interval_minutes` fuera del set permitido** → `400` antes de llegar al adapter.
- **`interval_minutes` ausente** → `200` con default `240`.
- **`Accept-Language` ausente o idioma no soportado** → `400` (comportamiento estandar de
  `get_language`).
- **Ningún gap en la ventana solicitada** → adapter devuelve respuesta con `n_reports_in_window: 0`
  y las 5 secciones vacias (`n_reports_in_section: 0`, `animals: []`) → router responde `200`.
- **BD vacia o todos los oasis sin `present > 0`** → mapa de tipos vacio → todos los gaps
  van a "sin_clasificar" o no hay gaps → las 5 secciones estan vacias → `200`.
- **Error inesperado de BD** → capturado en el router, responde `500` con detail generico
  (sin stack trace).

## 6. Edge cases

| # | Edge case | Tratamiento |
|---|-----------|-------------|
| EC-TD01 | Primer ataque a un oasis (sin previo) | Gap = NULL → descartado |
| EC-TD02 | `present = NULL` (derrota) | Cuenta en `n_total` del animal, excluido de `n_valid`, `avg_present`, `mode_present` |
| EC-TD03 | Todos los reportes de la ventana para un animal son derrotas (`n_valid = 0`) | `avg_present = null`, `mode_present = []`, `n_total > 0` |
| EC-TD04 | Empate en la moda (ej. present=[2,2,3,3]) | `mode_present = [2, 3]` (todos los empatados, ASC) |
| EC-TD05 | Animal sin ningún reporte en la ventana solicitada | El animal no aparece en `animals[]` |
| EC-TD06 | Ningún animal tiene reportes en la ventana | `n_reports_in_window=0`, `animals=[]` |
| EC-TD07 | Gap negativo o cero (relojes inconsistentes en la BD) | `gap_seconds <= 0` → descartado silenciosamente |
| EC-TD08 | Gap < 6 min (< 360s), p.ej. 300s | Descartado silenciosamente; no pertenece a ningún bin |
| EC-TD09 | Gap exactamente en el límite inferior del bin (ej. gap=7*60=420s con `interval_minutes=7`) | Pertenece al bin 7 `[420, 600)` — frontera inclusiva |
| EC-TD10 | Gap de 9 min (540s) con `interval_minutes=7` — ruido de lag | Cae en `[420, 600)` → bin 7. No salta al bin 10. Esto es la robustez de Opción B |
| EC-TD11 | Gap de exactamente 10 min (600s) | Cae en bin 10 `[600, 900)`, no en bin 7. La frontera superior es exclusiva |
| EC-TD12 | Gap de 5 min (300s, exactamente < 6 min) | Descartado. No entra en ningún bin |
| EC-TD13 | Gap de 86400s (24h) con `interval_minutes=240` | `86400 = 1440*60`. La ventana 240 es `[14400, 18000)`. `86400 >= 18000` → no cae en 240. Cae en la ventana 300 `[18000, ∞)`. |
| EC-TD14 | Gap de 86400s con `interval_minutes=300` | `86400 >= 18000` → pertenece al bin 300 abierto. Se cuenta |
| EC-TD15 | BD vacía | `200` con `n_reports_in_window=0`, `animals: []` |
| EC-TD16 | Idioma sin nombre para un ordinal en el catálogo | Fallback a `animal_name` de la BD |
| EC-TD17 | Oasis con un solo reporte (no puede generar gap) | El reporte se descarta; el oasis no aporta datos |
| EC-TD18 | `interval_minutes` ausente | `200` con default `240` |
| EC-TD19 | `interval_minutes=45` (valor entero pero fuera del set) | `400` con detail que lista los valores válidos |
| EC-TD20 | Oasis con solo reportes de derrota (`present=NULL` en todos sus reportes) | `tipo=None` → gap va a "sin_clasificar". No tiene `present>0` → `infer_type` recibe `observed=set()` → devuelve `(None, None)` |
| EC-TD21 | Oasis con 1 o 2 bursts observados (`burst_count` total < 3) | Tipo inferido con `confidence="low"`. Va a su seccion de tipo. Se cuenta en `n_oasis_low_confidence` de esa seccion |
| EC-TD22 | Todos los oasis de la BD son del mismo tipo (p.ej. todos hierro) | Las 4 secciones restantes devuelven `n_oasis=0`, `n_reports_in_section=0`, `animals=[]`. No se omiten del array `types` |
| EC-TD23 | BD con oasis de 3 tipos distintos; usuario pide `interval_minutes=6` y ninguno tiene gaps en esa ventana | `n_reports_in_window=0`, las 5 secciones vacias. `200` |
| EC-TD24 | Oasis con animales muy variados (ej. `{1,2,4,5,6,7}`) que Jaccard clasifica como cereal | Va a la seccion "cereal". La limitacion esta documentada (set universal). No es un bug |
| EC-TD25 | Dos oasis con tipo inferido "arcilla"; ambos tienen gaps en la ventana pero distintos animales observados | La seccion "arcilla" agrega los gaps de AMBOS oasis. `n_oasis=2`. Los animales se calculan sobre el conjunto unido de gaps de esos 2 oasis |
| EC-TD26 | Oasis con `presente>0` en la query de composicion pero ninguno de sus gaps cae en la ventana solicitada | El oasis tiene tipo inferido, pero como no aporta gaps a la ventana, no incrementa `n_oasis` ni `n_reports_in_section` de ninguna seccion |
| EC-TD27 | Empate de Jaccard entre dos tipos (mismo score) | `infer_type` resuelve por menor cardinal de set y luego alfabetico (comportamiento ya implementado). Determinista |
| EC-TD28 | Todos los reportes de la sección son derrotas (todos `present = NULL`) | `total_animals = {avg: null, mode: [], max: null, n_valid: 0, n_total: N}`. `avg_bounty` = todos a 0 (bounty = 0 en derrotas, DDL NOT NULL DEFAULT 0). `animals = []` (ya en v3). |
| EC-TD29 | Reporte con algunos animales `present = NULL` y otros no nulos (derrota parcial) | El reporte se excluye de `total_animals.n_valid` (cualquier NULL → excluir). Incluido en `total_animals.n_total`. El botín sí se incluye en `avg_bounty` (bounty es del reporte, no del animal). |
| EC-TD30 | Sección con un solo reporte y todos sus animales no nulos | `total_animals = {avg: <total>, mode: [<total>], max: <total>, n_valid: 1, n_total: 1}`. |
| EC-TD31 | Botín = 0 en todos los reportes de la sección | `avg_bounty = {wood: 0, clay: 0, iron: 0, crop: 0, total: 0}`. No es un error. |
| EC-TD32 | Un oasis de tipo "hierro" con un solo report_id en la ventana | `oasis_coords` contiene exactamente 1 elemento con las coords de ese oasis. |
| EC-TD33 | Sección vacía (`n_reports_in_section = 0`) | `oasis_coords: []`, `avg_bounty` todos a 0, `total_animals` avg/mode/max null/[]/null, n_valid=0, n_total=0. |
| EC-TD34 | Empate en mode del total de animales (ej. reportes con total 10 y 12 cada uno 2 veces) | `total_animals.mode = [10, 12]` (todos los empatados ASC). |
| EC-TD35 | Dos oasis del mismo tipo con coordenadas distintas en la ventana | `oasis_coords` contiene ambos, ordenados `(y ASC, x ASC)`. |

## 7. Modelo de datos / cambios de esquema

**No hay cambios de esquema.** Se reutilizan las tablas existentes:

```sql
-- Tablas reutilizadas (sin modificacion)
attack_reports          -- cabecera: coord_x_dest, coord_y_dest, attacked_at, id,
                        -- bounty_wood, bounty_clay, bounty_iron, bounty_crop (NOT NULL DEFAULT 0)
attack_report_animals   -- filas de animal: report_id → animal_ordinal, animal_name, present
```

El calculo es 100% derivado en tiempo de consulta. En v4 se siguen usando las mismas DOS
queries que en v3, con una extensión mínima a la CTE `report_gaps`:

1. **Query de composicion por oasis** (para inferir tipos): sin cambio desde v3.

2. **Query de gaps LAG** (CTE `report_gaps` + JOIN con animals): el SELECT de la CTE se
   amplía para incluir `r.bounty_wood, r.bounty_clay, r.bounty_iron, r.bounty_crop`.
   Dado que la CTE produce una fila por `report_id` (una por ataque), estos campos
   se devuelven una vez por reporte — sin riesgo de doble conteo al hacer el JOIN
   posterior con `attack_report_animals`.

No se necesita columna nueva ni índice adicional para v4.

## 8. Contratos de API / interfaces

<!-- PENDIENTE VALIDACION POR desarrollador-apis (v4) -->
<!-- La v1 fue validada y declarada CORRECTA. Este contrato AÑADE campos a v3 ya implementado. -->
<!-- Requiere gate de desarrollador-apis antes de implementar cliente HTTP (v4). -->

### EP-TD — GET /attack-reports/stats/oasis/temporal-distribution

> **DECISIÓN DE REUTILIZACIÓN:** Endpoint existente (implementado en v1). Se MODIFICA
> para sustituir `bucket_hours` por `interval_minutes` y cambiar el schema de respuesta.
> No se crea un endpoint nuevo.

**Método y ruta:** `GET /attack-reports/stats/oasis/temporal-distribution`

**Query parameters:**

| Parámetro | Tipo | Obligatorio | Default | Validación |
|-----------|------|-------------|---------|-----------|
| `interval_minutes` | `integer` | No | `240` | Valores exactos: `6\|7\|10\|15\|30\|60\|120\|180\|240\|300`. Otro entero → `400`. No entero → `422`. Ausente → `200` con default `240`. |

**Headers de request:**

| Header | Obligatorio | Descripción |
|--------|-------------|-------------|
| `Accept-Language` | Sí | Código de idioma (25 soportados en `SUPPORTED_LANGUAGES`). Ausente o código no soportado → `400`. |

**Response 200 — exito (v4):**

```json
{
  "interval_minutes": 240,
  "interval_label": "4h",
  "window": {
    "lower_min": 240,
    "upper_min": 300,
    "is_open": false
  },
  "n_reports_in_window": 42,
  "types": [
    {
      "oasis_type": "hierro",
      "oasis_type_label": "Hierro",
      "n_oasis": 3,
      "n_oasis_low_confidence": 1,
      "n_reports_in_section": 18,
      "oasis_coords": [
        { "x": -15, "y": 23 },
        { "x": -12, "y": 28 },
        { "x": -8, "y": 31 }
      ],
      "avg_bounty": {
        "wood": 45,
        "clay": 12,
        "iron": 318,
        "crop": 22,
        "total": 397
      },
      "total_animals": {
        "avg": 12.50,
        "mode": [10, 12],
        "max": 24,
        "n_valid": 15,
        "n_total": 18
      },
      "animals": [
        {
          "animal_ordinal": 1,
          "animal_name": "Rata",
          "icon_url": "/static/icons/nature_1.png",
          "avg_present": 2.50,
          "mode_present": [2],
          "max_present": 6,
          "n_total": 18,
          "n_valid": 15
        },
        {
          "animal_ordinal": 4,
          "animal_name": "Murciélago",
          "icon_url": "/static/icons/nature_4.png",
          "avg_present": 1.20,
          "mode_present": [1],
          "max_present": 3,
          "n_total": 12,
          "n_valid": 10
        }
      ]
    },
    {
      "oasis_type": "arcilla",
      "oasis_type_label": "Barro",
      "n_oasis": 2,
      "n_oasis_low_confidence": 0,
      "n_reports_in_section": 14,
      "oasis_coords": [{ "x": 5, "y": -10 }, { "x": 8, "y": -10 }],
      "avg_bounty": { "wood": 80, "clay": 290, "iron": 30, "crop": 15, "total": 415 },
      "total_animals": { "avg": 8.00, "mode": [8], "max": 15, "n_valid": 12, "n_total": 14 },
      "animals": [...]
    },
    {
      "oasis_type": "madera",
      "oasis_type_label": "Madera",
      "n_oasis": 0,
      "n_oasis_low_confidence": 0,
      "n_reports_in_section": 0,
      "oasis_coords": [],
      "avg_bounty": { "wood": 0, "clay": 0, "iron": 0, "crop": 0, "total": 0 },
      "total_animals": { "avg": null, "mode": [], "max": null, "n_valid": 0, "n_total": 0 },
      "animals": []
    },
    {
      "oasis_type": "cereal",
      "oasis_type_label": "Cereal",
      "n_oasis": 1,
      "n_oasis_low_confidence": 0,
      "n_reports_in_section": 3,
      "oasis_coords": [{ "x": 20, "y": 5 }],
      "avg_bounty": { "wood": 110, "clay": 90, "iron": 85, "crop": 200, "total": 485 },
      "total_animals": { "avg": 22.33, "mode": [20], "max": 30, "n_valid": 3, "n_total": 3 },
      "animals": [...]
    },
    {
      "oasis_type": "sin_clasificar",
      "oasis_type_label": "Sin clasificar",
      "n_oasis": 1,
      "n_oasis_low_confidence": 0,
      "n_reports_in_section": 7,
      "oasis_coords": [{ "x": -5, "y": 10 }],
      "avg_bounty": { "wood": 0, "clay": 0, "iron": 0, "crop": 0, "total": 0 },
      "total_animals": { "avg": null, "mode": [], "max": null, "n_valid": 0, "n_total": 7 },
      "animals": []
    }
  ]
}
```

**Ejemplo — ventana vacia (frecuencia sin datos):**

```json
{
  "interval_minutes": 6,
  "interval_label": "6 min",
  "window": { "lower_min": 6, "upper_min": 7, "is_open": false },
  "n_reports_in_window": 0,
  "types": [
    {
      "oasis_type": "hierro", "oasis_type_label": "Hierro",
      "n_oasis": 0, "n_oasis_low_confidence": 0, "n_reports_in_section": 0,
      "oasis_coords": [], "avg_bounty": {"wood":0,"clay":0,"iron":0,"crop":0,"total":0},
      "total_animals": {"avg":null,"mode":[],"max":null,"n_valid":0,"n_total":0}, "animals": []
    },
    {
      "oasis_type": "arcilla", "oasis_type_label": "Barro",
      "n_oasis": 0, "n_oasis_low_confidence": 0, "n_reports_in_section": 0,
      "oasis_coords": [], "avg_bounty": {"wood":0,"clay":0,"iron":0,"crop":0,"total":0},
      "total_animals": {"avg":null,"mode":[],"max":null,"n_valid":0,"n_total":0}, "animals": []
    },
    {
      "oasis_type": "madera", "oasis_type_label": "Madera",
      "n_oasis": 0, "n_oasis_low_confidence": 0, "n_reports_in_section": 0,
      "oasis_coords": [], "avg_bounty": {"wood":0,"clay":0,"iron":0,"crop":0,"total":0},
      "total_animals": {"avg":null,"mode":[],"max":null,"n_valid":0,"n_total":0}, "animals": []
    },
    {
      "oasis_type": "cereal", "oasis_type_label": "Cereal",
      "n_oasis": 0, "n_oasis_low_confidence": 0, "n_reports_in_section": 0,
      "oasis_coords": [], "avg_bounty": {"wood":0,"clay":0,"iron":0,"crop":0,"total":0},
      "total_animals": {"avg":null,"mode":[],"max":null,"n_valid":0,"n_total":0}, "animals": []
    },
    {
      "oasis_type": "sin_clasificar", "oasis_type_label": "Sin clasificar",
      "n_oasis": 0, "n_oasis_low_confidence": 0, "n_reports_in_section": 0,
      "oasis_coords": [], "avg_bounty": {"wood":0,"clay":0,"iron":0,"crop":0,"total":0},
      "total_animals": {"avg":null,"mode":[],"max":null,"n_valid":0,"n_total":0}, "animals": []
    }
  ]
}
```

**Ejemplo — bin abierto (`interval_minutes=300`):**

```json
{
  "interval_minutes": 300,
  "interval_label": "5h+",
  "window": {
    "lower_min": 300,
    "upper_min": null,
    "is_open": true
  },
  "n_reports_in_window": 5,
  "types": [...]
}
```

**Campos del response (v4 — campos nuevos marcados con [v4]):**

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `interval_minutes` | `integer` | Frecuencia solicitada (echo del parametro; `240` si se uso el default). |
| `interval_label` | `string` | Etiqueta legible. Valores: `"6 min"`, `"7 min"`, `"10 min"`, `"15 min"`, `"30 min"`, `"1h"`, `"2h"`, `"3h"`, `"4h"`, `"5h+"`. El bin `300` lleva `"5h+"`. |
| `window.lower_min` | `integer` | Limite inferior de la ventana en minutos (inclusive). |
| `window.upper_min` | `integer\|null` | Limite superior en minutos (exclusive). `null` para `interval_minutes=300`. |
| `window.is_open` | `boolean` | `true` solo para `interval_minutes=300`. |
| `n_reports_in_window` | `integer` | Numero total de gaps en la ventana. Suma de `n_reports_in_section` de las 5 secciones. `0` si ninguna seccion tiene datos. |
| `types` | `array[5]` | Siempre exactamente 5 elementos. Orden fijo: hierro, arcilla, madera, cereal, sin_clasificar. |
| `types[].oasis_type` | `string` | Clave canonica: `"hierro"`, `"arcilla"`, `"madera"`, `"cereal"`, `"sin_clasificar"`. |
| `types[].oasis_type_label` | `string` | Etiqueta de presentacion fija: `"Hierro"`, `"Barro"`, `"Madera"`, `"Cereal"`, `"Sin clasificar"`. |
| `types[].n_oasis` | `integer` | Numero de oasis distintos de este tipo con al menos un gap en la ventana. `0` si seccion vacia. |
| `types[].n_oasis_low_confidence` | `integer` | Cuantos de esos oasis tienen `confidence="low"`. `0` si ninguno o seccion vacia. |
| `types[].n_reports_in_section` | `integer` | Numero de gaps (report_ids distintos) de oasis de este tipo en la ventana. `0` si seccion vacia. |
| `types[].oasis_coords` **[v4]** | `array[{x,y}]` | Coordenadas de los oasis distintos de este tipo con al menos un gap en la ventana. `{x: integer, y: integer}`. Orden: `y ASC, x ASC`. `[]` si seccion vacia. |
| `types[].avg_bounty` **[v4]** | `object` | Recursos medios por reporte en la ventana. Ver subcampos abajo. |
| `types[].avg_bounty.wood` | `integer` | Media de `bounty_wood` (redondeada al entero). `0` si `n_reports_in_section=0`. |
| `types[].avg_bounty.clay` | `integer` | Media de `bounty_clay`. `0` si `n_reports_in_section=0`. |
| `types[].avg_bounty.iron` | `integer` | Media de `bounty_iron`. `0` si `n_reports_in_section=0`. |
| `types[].avg_bounty.crop` | `integer` | Media de `bounty_crop`. `0` si `n_reports_in_section=0`. |
| `types[].avg_bounty.total` | `integer` | Media del total `(wood+clay+iron+crop)` por reporte. Calculado directamente sobre la suma por reporte, no sumando las medias individuales. `0` si `n_reports_in_section=0`. |
| `types[].total_animals` **[v4]** | `object` | Distribución del total de animales por reporte (suma de todos los `present` del reporte). Solo reportes sin ningún `present=NULL`. Ver subcampos abajo. |
| `types[].total_animals.avg` | `number\|null` | Media del total por reporte (2 decimales). `null` si `n_valid=0`. |
| `types[].total_animals.mode` | `array[integer]` | Moda(s) del total. `[]` si `n_valid=0`. Empates: todos ASC. |
| `types[].total_animals.max` | `integer\|null` | Máximo del total. `null` si `n_valid=0`. |
| `types[].total_animals.n_valid` | `integer` | Reportes con TODOS los animales no nulos (victorias completas). |
| `types[].total_animals.n_total` | `integer` | = `n_reports_in_section`. Incluye derrotas. |
| `types[].animals` | `array` | Lista de animales observados en esta seccion. `[]` si `n_reports_in_section=0`. Orden: `animal_ordinal ASC`. |
| `types[].animals[].animal_ordinal` | `integer` | Ordinal del animal (1-10, catalogo NATURE). |
| `types[].animals[].animal_name` | `string` | Nombre localizado del animal (via `Accept-Language`). |
| `types[].animals[].icon_url` | `string` | `/static/icons/nature_{ordinal}.png` |
| `types[].animals[].avg_present` | `number\|null` | Media de `present` redondeada a 2 decimales. `null` si `n_valid=0`. |
| `types[].animals[].mode_present` | `array[integer]` | Moda(s) de `present`. `[]` si `n_valid=0`. Empates: todos ASC. |
| `types[].animals[].max_present` **[v4]** | `integer\|null` | Máximo de `present` observado. `null` si `n_valid=0`. |
| `types[].animals[].n_total` | `integer` | Gaps de este tipo donde aparece este animal (incluye derrotas con `present=null`). |
| `types[].animals[].n_valid` | `integer` | Gaps con `present IS NOT NULL` en esta seccion para este animal. |

**Tabla de etiquetas por valor de `interval_minutes`:**

| `interval_minutes` | `interval_label` | `window.lower_min` | `window.upper_min` | `window.is_open` |
|--------------------|------------------|--------------------|--------------------|------------------|
| `6`   | `"6 min"` | 6   | 7   | false |
| `7`   | `"7 min"` | 7   | 10  | false |
| `10`  | `"10 min"`| 10  | 15  | false |
| `15`  | `"15 min"`| 15  | 30  | false |
| `30`  | `"30 min"`| 30  | 60  | false |
| `60`  | `"1h"`    | 60  | 120 | false |
| `120` | `"2h"`    | 120 | 180 | false |
| `180` | `"3h"`    | 180 | 240 | false |
| `240` | `"4h"`    | 240 | 300 | false |
| `300` | `"5h+"`   | 300 | null| true  |

**Errores:**

| Código | Condición |
|--------|-----------|
| `400` | `interval_minutes` no está en `{6,7,10,15,30,60,120,180,240,300}`. Detail: `"interval_minutes debe ser uno de: 6, 7, 10, 15, 30, 60, 120, 180, 240, 300. Recibido: <valor>"`. |
| `400` | `Accept-Language` ausente. Detail estándar de `get_language`. |
| `400` | `Accept-Language` con código no soportado (ej. `zh`). |
| `422` | `interval_minutes` no es entero (FastAPI validation automática). |
| `500` | Error inesperado de BD. Detail genérico: `"Error interno al calcular la distribución temporal de animales."` |

**Posición en el router (orden de declaración):**

El endpoint debe declararse ANTES de `EP-06` (`/stats/oasis` sin subruta) para que FastAPI
lo resuelva como literal. Posición relativa con `comparison` y `spawn-composition`: sin
colisión (paths distintos). Orden recomendado para legibilidad:
`comparison` → `spawn-composition` → `temporal-distribution` → EP-06.

**Relación con otros endpoints:**
- Reutiliza el mismo patrón LAG de EP-09 (`get_global_oasis_stats`) con
  `PARTITION BY coord_x_dest, coord_y_dest`.
- Añade `Accept-Language` + `translation_port`, a diferencia de EP-09 que no los usa.
- No hay solapamiento funcional con EP-09, EP-10 ni EP-SPAWN.

## 9. Flujo lógico paso a paso

```
# Constantes de modulo (sin cambio desde v2)
VALID_INTERVALS = [6, 7, 10, 15, 30, 60, 120, 180, 240, 300]

WINDOWS = {
    6: (6, 7), 7: (7, 10), 10: (10, 15), 15: (15, 30), 30: (30, 60),
    60: (60, 120), 120: (120, 180), 180: (180, 240), 240: (240, 300), 300: (300, None),
}

LABELS = {
    6: "6 min", 7: "7 min", 10: "10 min", 15: "15 min", 30: "30 min",
    60: "1h", 120: "2h", 180: "3h", 240: "4h", 300: "5h+",
}

# Labels de presentacion para cada tipo (v3)
TYPE_LABELS = {
    "hierro": "Hierro", "arcilla": "Barro", "madera": "Madera",
    "cereal": "Cereal", None: "Sin clasificar",
}

# Orden fijo de secciones (v3): None = sin_clasificar al final
TYPE_ORDER = ["hierro", "arcilla", "madera", "cereal", None]

FUNCION get_animal_temporal_distribution(interval_minutes: int, lang: str) -> dict:

    lower_min, upper_min = WINDOWS[interval_minutes]
    lower_sec = lower_min * 60
    upper_sec = upper_min * 60 if upper_min is not None else None
    is_open = (upper_sec is None)

    # ─── Paso 1 (NUEVO v3): Inferir tipo por oasis ────────────────────────────
    # Misma query que usa EP-SPAWN para la composicion (solo present > 0).
    comp_sql = """
        SELECT r.coord_x_dest, r.coord_y_dest, a.animal_ordinal, COUNT(*) AS burst_count
        FROM attack_report_animals a
        JOIN attack_reports r ON r.id = a.report_id
        WHERE a.present > 0
        GROUP BY r.coord_x_dest, r.coord_y_dest, a.animal_ordinal
    """
    # Construir comp_by_oasis: {(cx, cy): [{"animal_ordinal": int, "burst_count": int}]}
    comp_by_oasis = defaultdict(list)
    for row in comp_rows:  # comp_rows = resultado de comp_sql
        comp_by_oasis[(row["coord_x_dest"], row["coord_y_dest"])].append({
            "animal_ordinal": row["animal_ordinal"],
            "burst_count":    row["burst_count"],
        })

    # Mapa de tipo e confidence por oasis: {(cx, cy): (tipo, confidence)}
    # infer_type = _infer_type elevada a funcion publica (RN-TD14)
    oasis_type_map = {}
    for (cx, cy), comp_list in comp_by_oasis.items():
        observed = {c["animal_ordinal"] for c in comp_list}
        tipo, confidence = infer_type(observed, comp_list)
        oasis_type_map[(cx, cy)] = (tipo, confidence)
    # Oasis con present=0 en todos sus reportes (solo derrotas) no aparecen en comp_by_oasis
    # → no estan en oasis_type_map → tipo sera None cuando se cruce con los gaps (EC-TD20).

    # ─── Paso 2: Calcular gaps con LAG (v2 + coords v3 + bounty v4) ──────────
    # NOTA: Se usa CTE para garantizar que el LAG opera sobre reportes, no sobre
    # filas de animales (ver Desviacion de v3). La CTE añade bounty en v4.
    gap_sql = """
        WITH report_gaps AS (
            SELECT
                r.id            AS report_id,
                r.coord_x_dest,
                r.coord_y_dest,
                r.attacked_at,
                r.bounty_wood,
                r.bounty_clay,
                r.bounty_iron,
                r.bounty_crop,
                CAST(
                    (UNIXEPOCH(r.attacked_at) -
                     UNIXEPOCH(LAG(r.attacked_at) OVER w)) AS INTEGER
                ) AS gap_seconds
            FROM attack_reports r
            WINDOW w AS (
                PARTITION BY r.coord_x_dest, r.coord_y_dest
                ORDER BY r.attacked_at
            )
        )
        SELECT
            rg.report_id,
            rg.coord_x_dest,
            rg.coord_y_dest,
            rg.bounty_wood,
            rg.bounty_clay,
            rg.bounty_iron,
            rg.bounty_crop,
            a.animal_ordinal,
            a.animal_name,
            a.present,
            rg.gap_seconds
        FROM report_gaps rg
        JOIN attack_report_animals a ON a.report_id = rg.report_id
        ORDER BY a.animal_ordinal, rg.coord_x_dest, rg.coord_y_dest, rg.attacked_at
    """

    # ─── Paso 3: Filtrar gaps invalidos (igual que v2) ────────────────────────
    valid_rows = [
        row for row in raw_rows
        if row["gap_seconds"] is not None
        and row["gap_seconds"] > 0
        and row["gap_seconds"] >= 360
    ]

    # ─── Paso 4: Filtrar por ventana (igual que v2) ───────────────────────────
    if is_open:
        window_rows = [r for r in valid_rows if r["gap_seconds"] >= lower_sec]
    else:
        window_rows = [r for r in valid_rows if lower_sec <= r["gap_seconds"] < upper_sec]

    # ─── Paso 5 (NUEVO v3): Etiquetar cada gap con el tipo de su oasis ────────
    # Si el oasis no esta en oasis_type_map → tipo=None → "sin_clasificar".
    def get_tipo(row):
        return oasis_type_map.get((row["coord_x_dest"], row["coord_y_dest"]), (None, None))[0]

    def get_confidence(row):
        return oasis_type_map.get((row["coord_x_dest"], row["coord_y_dest"]), (None, None))[1]

    # ─── Paso 6 (v3 + v4): Agrupar por (tipo, animal_ordinal) ───────────────
    # Estructuras auxiliares (v3):
    # - type_oasis_ids[tipo]: set de (cx,cy) con al menos un gap en la ventana
    # - type_oasis_low[tipo]: set de (cx,cy) con confidence="low"
    # - type_groups[tipo][ordinal]: {"n_total", "valids", "name_raw"}
    # - type_report_ids[tipo]: set de report_ids distintos en la seccion
    # Estructuras auxiliares nuevas (v4):
    # - type_bounty[tipo]: dict{report_id -> (wood, clay, iron, crop)} — deduplicado
    # - type_report_nulls[tipo]: dict{report_id -> bool} — True si algún present=NULL
    # - type_report_sums[tipo]: dict{report_id -> int} — suma de present no nulos del reporte
    type_oasis_ids    = defaultdict(set)
    type_oasis_low    = defaultdict(set)
    type_groups       = defaultdict(lambda: defaultdict(lambda: {"n_total": 0, "valids": [], "name_raw": ""}))
    type_report_ids   = defaultdict(set)
    type_bounty       = defaultdict(dict)   # {tipo: {report_id: (w,c,i,cr)}}
    type_report_nulls = defaultdict(dict)   # {tipo: {report_id: bool}}
    type_report_sums  = defaultdict(dict)   # {tipo: {report_id: int}}

    for row in window_rows:
        tipo = get_tipo(row)
        cx, cy = row["coord_x_dest"], row["coord_y_dest"]
        confidence = get_confidence(row)
        rid = row["report_id"]
        type_oasis_ids[tipo].add((cx, cy))
        if confidence == "low":
            type_oasis_low[tipo].add((cx, cy))
        type_report_ids[tipo].add(rid)
        ordinal = row["animal_ordinal"]
        type_groups[tipo][ordinal]["n_total"] += 1
        if row["present"] is not None:
            type_groups[tipo][ordinal]["valids"].append(row["present"])
        if not type_groups[tipo][ordinal]["name_raw"]:
            type_groups[tipo][ordinal]["name_raw"] = row["animal_name"]

        # v4 — botín: deduplicado por report_id (bounty es del reporte, no del animal)
        if rid not in type_bounty[tipo]:
            type_bounty[tipo][rid] = (
                row["bounty_wood"], row["bounty_clay"],
                row["bounty_iron"], row["bounty_crop"]
            )

        # v4 — total de animales: marcar NULL si algún animal del reporte tiene present=NULL
        if rid not in type_report_nulls[tipo]:
            type_report_nulls[tipo][rid] = False
            type_report_sums[tipo][rid] = 0
        if row["present"] is None:
            type_report_nulls[tipo][rid] = True  # este reporte queda excluido de n_valid
        else:
            type_report_sums[tipo][rid] += row["present"]

    # ─── Paso 7: Resolver nombres localizados (igual que v2) ──────────────────
    names_by_ordinal = {
        entry["ordinal"]: entry["nombre"]
        for entry in translation_port.get_troop_names_by_tribe(Tribe.NATURE, lang)
    }

    # ─── Paso 8: Helpers para construir datos de una sección ──────────────────

    def build_animals(tipo):
        """v3 + v4: añade max_present a cada animal."""
        result = []
        for ordinal in sorted(type_groups[tipo].keys()):
            data = type_groups[tipo][ordinal]
            n_valid = len(data["valids"])
            avg_present = round(sum(data["valids"]) / n_valid, 2) if n_valid > 0 else None
            if n_valid > 0:
                counter = Counter(data["valids"])
                max_count = max(counter.values())
                mode_present = sorted(k for k, v in counter.items() if v == max_count)
                max_present  = max(data["valids"])  # [v4]
            else:
                mode_present = []
                max_present  = None  # [v4]
            result.append({
                "animal_ordinal": ordinal,
                "animal_name":    names_by_ordinal.get(ordinal, data["name_raw"]),
                "icon_url":       f"/static/icons/nature_{ordinal}.png",
                "avg_present":    avg_present,
                "mode_present":   mode_present,
                "max_present":    max_present,  # [v4]
                "n_total":        data["n_total"],
                "n_valid":        n_valid,
            })
        return result

    def build_avg_bounty(tipo):
        """[v4] Media del botín por tipo. Denominador = n_reports_in_section (incluye derrotas)."""
        bounties = list(type_bounty[tipo].values())  # lista de (w,c,i,cr)
        n = len(bounties)
        if n == 0:
            return {"wood": 0, "clay": 0, "iron": 0, "crop": 0, "total": 0}
        return {
            "wood":  round(sum(b[0] for b in bounties) / n),
            "clay":  round(sum(b[1] for b in bounties) / n),
            "iron":  round(sum(b[2] for b in bounties) / n),
            "crop":  round(sum(b[3] for b in bounties) / n),
            "total": round(sum(b[0]+b[1]+b[2]+b[3] for b in bounties) / n),
        }

    def build_total_animals(tipo):
        """[v4] Distribución del total de animales por reporte (solo reportes sin ningún NULL)."""
        n_total = len(type_report_ids[tipo])
        # Reportes válidos: los que no tienen ningún present=NULL
        valid_totals = [
            type_report_sums[tipo][rid]
            for rid in type_report_ids[tipo]
            if not type_report_nulls[tipo].get(rid, False)
        ]
        n_valid = len(valid_totals)
        if n_valid == 0:
            return {"avg": None, "mode": [], "max": None, "n_valid": 0, "n_total": n_total}
        counter = Counter(valid_totals)
        max_count = max(counter.values())
        return {
            "avg":    round(sum(valid_totals) / n_valid, 2),
            "mode":   sorted(k for k, v in counter.items() if v == max_count),
            "max":    max(valid_totals),
            "n_valid": n_valid,
            "n_total": n_total,
        }

    def build_oasis_coords(tipo):
        """[v4] Lista de coords de oasis con gap en la ventana, ordenada (y ASC, x ASC)."""
        return [
            {"x": cx, "y": cy}
            for cx, cy in sorted(type_oasis_ids[tipo], key=lambda c: (c[1], c[0]))
        ]

    # ─── Paso 9 (v3 + v4): Construir array types con las 5 secciones ──────────
    types = []
    for tipo in TYPE_ORDER:  # hierro, arcilla, madera, cereal, None
        oasis_type_key = tipo if tipo is not None else "sin_clasificar"
        types.append({
            "oasis_type":              oasis_type_key,
            "oasis_type_label":        TYPE_LABELS[tipo],
            "n_oasis":                 len(type_oasis_ids[tipo]),
            "n_oasis_low_confidence":  len(type_oasis_low[tipo]),
            "n_reports_in_section":    len(type_report_ids[tipo]),
            "oasis_coords":            build_oasis_coords(tipo),  # [v4]
            "avg_bounty":              build_avg_bounty(tipo),    # [v4]
            "total_animals":           build_total_animals(tipo), # [v4]
            "animals":                 build_animals(tipo),
        })

    # ─── Paso 10: Construir respuesta raiz ────────────────────────────────────
    n_reports_in_window = sum(len(type_report_ids[t]) for t in TYPE_ORDER)

    return {
        "interval_minutes": interval_minutes,
        "interval_label":   LABELS[interval_minutes],
        "window": {
            "lower_min": lower_min,
            "upper_min": upper_min,
            "is_open":   is_open,
        },
        "n_reports_in_window": n_reports_in_window,
        "types": types,
    }
```

**Nota sobre las dos queries en paralelo:** la query de composicion (Paso 1) y la query LAG
(Paso 2) pueden ejecutarse de forma secuencial o con `asyncio.gather` si el conector SQLite
lo permite. Para el volumen esperado (<10.000 reportes), la diferencia es negligible. Lo que
no debe hacerse es ejecutar la query de composicion dentro del loop de gaps (N+1).

**Nota sobre `None` como clave de dict:** Python permite `None` como clave de dict. El
`defaultdict` con clave `None` funciona correctamente para agrupar oasis sin tipo inferido.
El implementador puede usar `None` o la string `"sin_clasificar"` como clave interna; lo
importante es que en el output final `oasis_type` sea `"sin_clasificar"` (string).

## 10. Validaciones y reglas

| Capa | Validación | Respuesta ante fallo |
|------|-----------|----------------------|
| Router (FastAPI) | `interval_minutes` es `integer` (tipo) | `422` automático |
| Router (manual) | `interval_minutes` ∈ `{6,7,10,15,30,60,120,180,240,300}` | `400` con detail legible que lista los valores válidos |
| Router (manual) | `interval_minutes` ausente → usar default `240` | `200` con `interval_minutes: 240` |
| Router (`get_language`) | `Accept-Language` presente y código soportado | `400` |
| Adapter (Python) | `gap_seconds IS NULL` (primer ataque) | Filtrado silencioso |
| Adapter (Python) | `gap_seconds <= 0` (relojes inconsistentes) | Filtrado silencioso |
| Adapter (Python) | `gap_seconds < 360` (< 6 min) | Filtrado silencioso |
| Adapter (Python) | Gap fuera de la ventana `[lower_sec, upper_sec)` | No se incluye en `window_rows` |
| Adapter (Python) | `present IS NULL` (derrota) | Cuenta en `n_total`, excluido de calculos de `avg`/`mode` |
| Adapter (Python) | Catalogo sin nombre para un ordinal | Fallback a `animal_name` de BD |
| Adapter (Python v3) | Oasis no en `oasis_type_map` (sin `present>0` nunca) | Tipo `None` → seccion "sin_clasificar" |
| Adapter (Python v3) | `confidence="low"` (< 3 bursts) | Incluido en su seccion de tipo; incrementa `n_oasis_low_confidence` |
| Adapter (Python v3) | Oasis con gaps en la ventana pero ausente del mapa de tipos | Se trata como tipo `None` (EC-TD20). No lanza excepcion |
| Adapter (Python v4) | `present=NULL` en cálculo de `max_present` | Excluido de `max(valids)`. `null` si `n_valid=0`. Misma regla que `avg_present`. |
| Adapter (Python v4) | Reporte con cualquier animal con `present=NULL` en `total_animals` | Ese reporte se excluye de `n_valid` del total. Se incluye en `n_total`. |
| Adapter (Python v4) | Botín del reporte repetido en múltiples filas del JOIN (una por animal) | Deduplicado por `report_id` en `type_bounty[tipo]`: solo la primera aparición se registra. |
| Adapter (Python v4) | `n_reports_in_section = 0` → `avg_bounty` | Todos los subcampos a `0` (no `null`). Consistente con COALESCE de `get_bounty_stats`. |
| Adapter (Python v4) | `n_valid = 0` en `total_animals` | `avg=null`, `mode=[]`, `max=null`. `n_valid=0`, `n_total` = valor correcto. |

## 11. Seguridad, rendimiento y concurrencia

**Seguridad:**
- `interval_minutes` validado contra whitelist estricta (no arithmetic injection).
- `lang` validado por `get_language` contra `SUPPORTED_LANGUAGES` (sin interpolacion SQL).
- Las queries no aceptan parametros de coordenadas ni de tipo → sin inyeccion SQL.
- No se expone `raw_text` ni datos personales.

**Rendimiento (v3):**
- En v3 se ejecutan DOS queries en vez de una: la query de composicion (Paso 1) y la query
  LAG (Paso 2). Para el volumen esperado (<10.000 reportes y pocos oasis distintos), el
  coste adicional es negligible.
- La inferencia de tipo se hace en Python en O(|oasis| x |tipos|) = O(n x 4) — despreciable.
- El agrupamiento por (tipo, animal) es O(|window_rows|) en Python — adecuado.
- Si en el futuro la tabla crece (>100.000 filas), considerar un indice parcial en
  `(coord_x_dest, coord_y_dest, attacked_at)` sobre `attack_reports`. No es necesario en v3.
- Los nombres localizados se cargan en memoria una sola vez por request (lista de 10 animales).

**Concurrencia:**
- SQLite en modo WAL: la query de lectura es compatible con escrituras concurrentes.
- Sin estado mutable en el adapter para este endpoint.

## 12. Plan de pruebas

### Casos felices (v3)

| ID | Caso | Verificacion |
|----|------|-------------|
| T-TD01 | `interval_minutes=240` (default), lang=`es`, BD con reportes de oasis hierro con gaps en `[14400, 18000)` | 200, `n_reports_in_window>0`, `types` tiene 5 elementos, seccion "hierro" tiene `n_reports_in_section>0` y `animals` con rat/spider/murciélago ordenados por `animal_ordinal ASC` |
| T-TD02 | `interval_minutes=60`, lang=`en` | 200, `interval_label="1h"`, `window={lower_min:60, upper_min:120}` |
| T-TD03 | `interval_minutes=300` | 200, `interval_label="5h+"`, `window.is_open=true`, `window.upper_min=null` |
| T-TD04 | BD con reportes de derrota (`present=null`) en la ventana para un oasis | `n_total > n_valid` para el animal en su seccion, `avg_present=null` si todos son derrota, `mode_present=[]` |
| T-TD05 | Empate en moda (ej. present=[2,2,3,3]) para un animal en una seccion | `mode_present=[2,3]` |
| T-TD06 | Animal con un unico valor de `present` | `mode_present=[valor]` |
| T-TD07 | BD vacia | 200, `n_reports_in_window=0`, `types` con 5 secciones todas con `n_reports_in_section=0` y `animals=[]` |
| T-TD08 | BD con exactamente 1 reporte por oasis (sin gaps) | 200, `n_reports_in_window=0`, 5 secciones vacias |
| T-TD09 | lang=`it` (idioma italiano) | Nombres en italiano dentro de `types[].animals[].animal_name` |
| T-TD10 | Ordinal sin nombre en catalogo para el idioma | `animal_name` = valor de la BD |
| T-TD11 | `interval_minutes` ausente | 200 con `interval_minutes=240` (default) |
| T-TD28 | BD con oasis de tipo "hierro" (animales {1,2,4}) y "madera" (animales {5,6,7}); gaps de ambos en ventana | `types` tiene 5 elementos; seccion "hierro" y "madera" con datos; secciones "arcilla", "cereal", "sin_clasificar" vacias (`n_reports_in_section=0`) |
| T-TD29 | Oasis con solo reportes de derrota (todos `present=NULL`) y con gap en ventana | Ese oasis no esta en `oasis_type_map` → su gap va a seccion "sin_clasificar". `types[4].n_reports_in_section >= 1` |
| T-TD30 | Oasis con 1 burst observable (`burst_count_total=1`, confidence="low") y gap en ventana | Oasis incluido en su seccion de tipo. `n_oasis_low_confidence=1` en esa seccion |
| T-TD31 | Oasis con 3 o mas bursts (`confidence="medium"`) | `n_oasis_low_confidence=0` para ese oasis en su seccion |
| T-TD32 | Dos oasis del mismo tipo con gaps en la ventana | `n_oasis=2` en esa seccion; `animals` agrega los gaps de ambos |
| T-TD33 | `n_reports_in_window` == suma de `n_reports_in_section` de las 5 secciones | Invariante de integridad |
| T-TD34 | Secciones en orden fijo: hierro[0], arcilla[1], madera[2], cereal[3], sin_clasificar[4] | `types[0].oasis_type="hierro"`, `types[1].oasis_type="arcilla"`, ..., `types[4].oasis_type="sin_clasificar"` |
| T-TD35 | `oasis_type_label` de arcilla es "Barro" (no "Arcilla") | `types[1].oasis_type_label=="Barro"` |

### Casos felices — nuevos campos v4

| ID | Caso | Verificacion |
|----|------|-------------|
| T-TD36 | BD con reportes de victorias (todos `present` no nulos) en un oasis hierro con gaps en la ventana | `animals[i].max_present >= animals[i].avg_present`, `max_present` es un entero no nulo |
| T-TD37 | Todos los reportes de la ventana son derrotas (todos `present=NULL`) para un tipo | `animals[i].max_present=null` para todos. `total_animals.avg=null`, `mode=[]`, `max=null`, `n_valid=0`. `avg_bounty` todos a 0. |
| T-TD38 | Reportes de victoria con bounty > 0 en la ventana para un tipo | `avg_bounty.wood > 0` (o iron/etc. según el tipo). `avg_bounty.total` = media del total por reporte (no suma de medias). |
| T-TD39 | Sección con un solo oasis visible en la ventana | `oasis_coords` contiene exactamente 1 elemento con las coords correctas. |
| T-TD40 | Sección con dos oasis con coords distintas | `oasis_coords` contiene 2 elementos ordenados por `(y ASC, x ASC)`. |
| T-TD41 | Sección vacía | `oasis_coords=[]`, `avg_bounty` todos 0, `total_animals.n_valid=0`, `total_animals.n_total=0`. |
| T-TD42 | Fixture con 3 reportes de victoria en un oasis: totales 10, 12, 10 | `total_animals.avg=10.67`, `total_animals.mode=[10]`, `total_animals.max=12`, `n_valid=3`. |
| T-TD43 | Fixture con 2 reportes de victoria (total 10) y 1 derrota | `total_animals.mode=[10]`, `n_valid=2`, `n_total=3`. |
| T-TD44 | Fixture con un reporte de victoria parcial (animal A present=5, animal B present=NULL) | Reporte excluido de `total_animals.n_valid`. `total_animals.n_valid < n_total`. |
| T-TD45 | `max_present` de un animal con un solo valor de `present` (ej. siempre 3) | `max_present=3`, `avg_present=3.0`, `mode_present=[3]`. |
| T-TD46 | `avg_bounty.total` vs. suma de medias | Verificar que `total` == `round(mean(w+c+i+cr per report))`, distinto de `avg_bounty.wood + clay + iron + crop` cuando hay redondeo. |

### Edge cases — binning de frontera (críticos para Opción B)

| ID | Caso | Verificación |
|----|------|-------------|
| T-TD12 | Gap exactamente `7*60=420s` con `interval_minutes=7` | Cae en bin 7 `[420,600)` — frontera inclusiva inferior. `n_reports_in_window>=1` |
| T-TD13 | Gap de `9*60=540s` con `interval_minutes=7` | Cae en bin 7 `[420,600)`. No salta al bin 10. `n_reports_in_window>=1` |
| T-TD14 | Gap de `10*60=600s` con `interval_minutes=7` | Cae en bin 10 `[600,900)`. NO en bin 7. Frontera superior exclusiva |
| T-TD15 | Gap de `5*60=300s` (< 6 min) | Descartado. Con `interval_minutes=6` → `n_reports_in_window=0` |
| T-TD16 | Gap de `86400s` (24h) con `interval_minutes=240` | `86400 >= 18000` → no cae en ventana 240. Con `interval_minutes=300` sí cuenta |
| T-TD17 | Gap de `86400s` con `interval_minutes=300` | `86400 >= 18000` → `n_reports_in_window>=1` |
| T-TD18 | Gap exactamente en límite superior: `upper_min * 60` exacto | No pertenece al bin. Pertenece al bin siguiente |
| T-TD19 | Gap de `0s` (relojes iguales) | Descartado. No aparece en ninguna ventana |

### Edge cases y errores de validación

| ID | Caso | Verificación |
|----|------|-------------|
| T-TD20 | `interval_minutes=45` (entero pero fuera del set) | 400, detail menciona los 10 valores válidos |
| T-TD21 | `interval_minutes=0` | 400 |
| T-TD22 | `interval_minutes=301` | 400 |
| T-TD23 | `interval_minutes` no entero (ej. `"cuatro"`) | 422 (FastAPI) |
| T-TD24 | `Accept-Language` ausente | 400 |
| T-TD25 | `Accept-Language: zh` (no soportado) | 400 |
| T-TD26 | Dos oasis con el mismo animal; gaps de oasis A no cruzan a oasis B | Verificar que el LAG usa PARTITION BY coords correctamente |
| T-TD27 | Ventana solicitada sin datos (frecuencia inusual, ej. `interval_minutes=6` con BD típica) | 200, `n_reports_in_window=0`, `animals=[]` |

## 13. Riesgos y trade-offs

**Trade-off: Opción B (umbral inferior) vs. vecino-más-cercano.**
Se eligió **umbral inferior** (Opción B) porque:
- Es monótono: un gap `g` pertenece al bin `F` si y solo si `F ≤ g/60 < F_next`. No hay
  ambigüedad ni zonas de incertidumbre.
- Es robusto al ruido de lag: un timer configurado a 7 min que tarda 9 min por latencia
  sigue en el bin 7 (`[7, 10)`), no salta al 10.
- El vecino-más-cercano crea zonas de empate exactas (p.ej. gap de 8.5 min, equidistante
  de 7 y 10) que exigen desempate arbitrario.
*Contra:* el usuario debe saber que "bin 7 min" incluye gaps de hasta justo antes de 10 min.
*Mitigación:* la etiqueta en la UI puede mostrar el rango real `"7–10 min"` para claridad.

**Trade-off: conjunto discreto vs. rango continuo.**
El usuario elige una frecuencia discreta del conjunto `{6,7,10,15,30,60,120,180,240,300}`,
que son las cadencias reales del juego (respawn intervals habituales). Esto hace la UI más
intuitiva (selector de opciones, no slider) y evita ventanas huecas con cero datos.

**Trade-off: respuesta de una frecuencia vs. matriz completa.**
En v1 se devolvía la matriz completa de todas las franjas. En v2 se devuelve solo la
frecuencia solicitada. Esto reduce el payload, simplifica el frontend y permite al usuario
explorar interactivamente las frecuencias sin cargar datos que no va a usar.
*Contra:* si el frontend necesita mostrar comparativa entre frecuencias, necesita múltiples
requests. *Mitigación v2:* si se necesita en el futuro, añadir endpoint de resumen
multi-frecuencia o query param `include_all=true`.

**Trade-off: gaps < 6 min descartados vs. incluidos en bin 6.**
Se descartan porque mezclarlos con el bin de 6 min distorsionaría la estadística de esa
cadencia (incluiría anomalías de reloj, duplicados accidentales o datos corruptos).
El bin de 6 min debe representar ataques deliberadamente rápidos, no ruido de sistema.

**Trade-off: solo global vs. por oasis.**
Se eligió **solo global** porque el número de oasis distintos suele ser pequeño y los datos
por oasis son insuficientes para una distribución significativa. El patrón LAG con
`PARTITION BY` es extensible a filtro por coordenadas si se necesita en v3.

**Trade-off: moda en Python vs. en SQL.**
SQLite no tiene `MODE()`. Se eligió **Python** con `Counter`: más legible, maneja empates
elegantemente y tiene rendimiento suficiente para el volumen esperado (<10.000 reportes).

**Riesgo: `attacked_at` como string naive.**
Los timestamps se almacenan como strings ISO 8601 naive. `UNIXEPOCH()` de SQLite sobre
strings naive funciona correctamente siempre que todos estén en el mismo reloj de servidor
(confirmado en specs anteriores). Si en el futuro se mezclan timestamps de distintos
servidores con offsets diferentes, el LAG produciría gaps erróneos. No es un problema porque
el bot solo ataca a un servidor a la vez.

**Riesgo: velocidad de servidor NO se ajusta.**
Los gaps se miden en tiempo real de servidor, no ajustados por la velocidad de servidor
(x1..x10). El endpoint trabaja siempre con tiempo real. Si el usuario juega en un servidor
x3 y ataca cada 2h, su cadencia de farmeo "efectiva" en terminos de juego seria 2h/3=40min,
pero el endpoint la registra como 2h. Esto es correcto: el usuario configura sus timers en
tiempo real, no en tiempo de juego. No hay ajuste que implementar.

**Trade-off v3: incluir oasis de baja confianza en su seccion vs. excluirlos o moverlos a "sin_clasificar".**
Se eligio **incluir con marca** porque ocultar datos con pocos bursts crearia la ilusion de
que ciertos tipos de oasis estan vacios cuando en realidad hay datos (solo insuficientes).
El campo `n_oasis_low_confidence` permite al frontend mostrar un disclaimer sin complicar
la logica del backend.
*Contra:* un oasis con 2 bursts clasificado incorrectamente puede contaminar su seccion.
*Mitigacion:* Jaccard es robusto incluso con pocos datos si los animales observados son
caracteristicos del tipo. La marca de baja confianza es la senal al usuario para tomar
el dato con reservas.

**Trade-off v3: cereal como tipo "borroso" — documentar la limitacion en la UI.**
El set cereal ({1..10}) es universal. Jaccard evita que anule a los demas tipos (ver §REVISION v3),
pero un oasis con composicion verdaderamente variada (muchos tipos de animal) sera clasificado
como cereal correctamente. El frontend debe mostrar junto a la seccion "Cereal" la nota:
"Oasis de cereal — puede contener todos los tipos de animal". No requiere cambio en el backend.

**Trade-off v3: no exponer `confidence` por oasis en el response de EP-TD.**
Se podria exponer la confidence individual de cada oasis dentro de la seccion (p.ej.
`oasis_details: [{cx, cy, confidence}]`). Se descarta por complejidad de UI innecesaria:
`n_oasis_low_confidence` es suficiente para mostrar un disclaimer agregado.
En v4 se añade `oasis_coords` (coords sin confidence). Si en v5 se necesita el tooltip
"X de Y oasis tienen pocos datos por coord", se puede enriquecer `oasis_coords` con
`{x, y, low_confidence: bool}` — decisión diferida a v5.

**Trade-off v4: denominador de `avg_bounty` = todos los reportes (incluidas derrotas con bounty=0).**
La alternativa sería promediar solo sobre "reportes con bounty > 0" (excluir ataques fallidos).
Se rechaza porque inflaría la media artificialmente y escondería el coste de los ataques vacíos.
El DDL confirma `bounty_* NOT NULL DEFAULT 0`, por lo que las derrotas ya están representadas
con 0. El usuario que calibra su cadencia debe ver el botín real promedio incluyendo los vacíos.
*Contra:* si el usuario quiere saber "cuánto obtiene cuando SÍ le salen animales", necesitaría
un filtro. *Mitigación:* con `total_animals.n_valid` puede deducir la tasa de victorias.
No se añade un campo extra para ello en v4.

**Trade-off v4: `total_animals` excluye reportes con cualquier `present=NULL` ("todo o nada").**
La alternativa sería sumar los `present` no nulos aunque haya algunos NULL ("suma parcial").
Se rechaza porque el total parcial induciría a error: 3 ratas + ? murciélagos = 3, cuando
el total real es desconocido. La regla "todo o nada" es más conservadora pero honesta.
El campo `n_valid` informa cuántos reportes completos hay; si `n_valid << n_total` es señal
de muchas derrotas y el total no es representativo.

**Trade-off v4: `oasis_coords` sin cap ni paginación.**
Los oasis de un jugador en Travian son pocos (el mapa cercano tiene decenas, no miles).
Un cap arbitrario (ej. 50) añadiría complejidad sin valor práctico. Si en el futuro
el conjunto crece, se puede añadir `oasis_coords_truncated: bool` y un parámetro
`?include_coords=false` para suprimir la lista. Diferido a v5+.

**Trade-off v3: elevar `_infer_type` vs. duplicar Jaccard.**
Se eleva la funcion porque duplicar el calculo de Jaccard crearia dos implementaciones que
podrian divergir silenciosamente (un bug en una no se detectaria con los tests de la otra).
El costo de la elevacion es minimo (renombrar o mover un metodo). Ver RN-TD14.

## 14. Pasos de implementación ordenados

> **Prerrequisito v4:** Los pasos 1-4 de v3 ya están implementados (41 tests en verde).
> Los pasos de v4 son INCREMENTALES sobre esa implementación: solo se añaden campos nuevos
> al adapter, response model y tests. No hay reescritura de la lógica existente.
>
> **Gate de APIs (v4):** antes de implementar el cliente HTTP del frontend, `desarrollador-apis`
> debe revisar el contrato v4 de §8 y emitir luz verde. El estado del spec es
> `ready-for-impl` para backend v4.
>
> **Gate UI (v5):** La UI (`AnimalFrequencyPanel.jsx`) requiere rediseño por
> `disenador-producto` v5 + nuevo mockup editable aprobado por el usuario. No implementar
> sin ese gate.

**[YA IMPLEMENTADO v3] Paso 1 — Elevar `_infer_type` a `infer_type`**
(`adapters/db/attack_report_sqlite_adapter.py`)
Completado en v3. `infer_type` ya es función pública. EP-SPAWN en verde.

**[YA IMPLEMENTADO v3] Paso 2 — Actualizar el port abstracto**
(`core/ports/attack_report_port.py`)
Docstring actualizado en v3. La firma no cambia en v4.

**Paso 3 — Extender la implementación del adapter (DELTA v4)**
(`adapters/db/attack_report_sqlite_adapter.py`)

Cambios sobre la implementación v3 existente:

1. **Extender la CTE `report_gaps`** para incluir los campos de botín:
   añadir `r.bounty_wood, r.bounty_clay, r.bounty_iron, r.bounty_crop` al SELECT.
   El JOIN posterior con `attack_report_animals` expone estos campos en cada fila,
   pero el botín es del reporte — se deduplicará en Python.

2. **Añadir 3 estructuras auxiliares** al Paso 6 (bucle de `window_rows`):
   - `type_bounty[tipo]`: `dict[report_id → (w,c,i,cr)]` — primera aparición por reporte.
   - `type_report_nulls[tipo]`: `dict[report_id → bool]` — True si algún `present=NULL`.
   - `type_report_sums[tipo]`: `dict[report_id → int]` — suma de `present` no nulos del reporte.

3. **Añadir `max_present`** al helper `_build_animals`:
   `max_present = max(data["valids"]) if n_valid > 0 else None`.

4. **Añadir helpers `_build_avg_bounty`, `_build_total_animals`, `_build_oasis_coords`**
   (ver pseudocódigo del §9) y llamarlos en el constructor de secciones del Paso 9.

5. **Añadir los 4 campos nuevos** al dict de cada sección en el Paso 9:
   `"oasis_coords"`, `"avg_bounty"`, `"total_animals"` y `"max_present"` (dentro de cada animal).

El docstring del método debe actualizarse para referenciar v4 en el spec.

**Paso 4 — Actualizar el port abstracto (DELTA v4)**
(`core/ports/attack_report_port.py`)

Solo actualizar el docstring del método abstracto para referenciar v4:

```python
    """
    Distribucion empirica de animales por tipo de oasis para una cadencia de farmeo dada (v4).

    interval_minutes: frecuencia en minutos. Valores validos: 6|7|10|15|30|60|120|180|240|300.
    lang: codigo de idioma validado (25 soportados).
    translation_port: puerto de traduccion para resolver nombres de animales.

    Devuelve { interval_minutes, interval_label, window, n_reports_in_window, types }.
    types: lista de 5 secciones fijas (hierro, arcilla, madera, cereal, sin_clasificar).
    Cada seccion incluye: oasis_coords, avg_bounty, total_animals, animals (con max_present).
    200 siempre. Ver spec docs/specs/bd-ataques-oasis-temporal-distribution.md §8 EP-TD (v4).
    """
```

**Paso 5 — Actualizar el router (DELTA v4)**
(`adapters/api/routes/attack_reports.py`)

Sin cambios funcionales. Solo actualizar el comentario de cabecera del endpoint para referenciar v4.

**Paso 6 — Actualizar el comentario del cliente JS (DELTA v4)**
(`frontend/src/api/client.js`)

Actualizar el comentario del método para referenciar v4:

```js
export async function getAnimalTemporalDistribution(intervalMinutes = 240) {
  // v4: response incluye types[5] con oasis_coords, avg_bounty, total_animals y max_present por animal
  const params = new URLSearchParams({ interval_minutes: intervalMinutes });
  const res = await fetch(
    `/api/attack-reports/stats/oasis/temporal-distribution?${params}`,
    { headers: buildHeaders() }
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
```

El componente `AnimalFrequencyPanel.jsx` NO se actualiza aquí (solo tiene un stub).
Su implementación queda bloqueada hasta el rediseño del `disenador-producto` v5.

**Paso 7 — Actualizar el stub en StatsTab (DELTA v4)**
(`frontend/src/components/attack-reports/StatsTab.jsx`)

Actualizar el comentario del placeholder `<AnimalFrequencyPanel />`:
`{/* TODO: redisenar UI tras spec de disenador-producto (v4: max_present, total_animals, avg_bounty, oasis_coords) */}`

**Paso 8 — Añadir tests v4 al archivo de tests existente (NO ELIMINAR los v3)**
(`tests/test_animal_temporal_distribution_api.py`)

Los 41 tests v3 se conservan. Se AÑADEN los tests v4 (T-TD36..T-TD46):

- T-TD36..T-TD46 del §12 (nuevos campos: max_present, avg_bounty, total_animals, oasis_coords).
- Usar fixtures SQLite en memoria que combinan victorias, derrotas y coordenadas distintas.
- Los fixtures deben cubrir:
  - Victoria completa (todos los `present` no nulos): verifica `max_present`, `total_animals.n_valid`, `avg_bounty > 0`.
  - Solo derrotas: verifica `max_present=null`, `total_animals.avg=null`, `avg_bounty` todos 0.
  - Derrota parcial (un animal NULL, otro no nulo): verifica reporte excluido de `total_animals.n_valid`.
  - Dos oasis distintos del mismo tipo: verifica `oasis_coords` con 2 elementos ordenados.
  - `avg_bounty.total` calculado sobre la suma por reporte (no sobre las medias individuales).

**Paso 9 — Actualizar la documentación técnica (DELTA v4)**
(`documentacion/backend/referencia-funciones/attack-report-temporal-distribution.md`)

Actualizar a v4: añadir los 4 campos nuevos, los denominadores, la tabla de campos del §8,
y la nota sobre la extensión de la CTE `report_gaps` para incluir bounty.

## 15. Criterios de aceptacion

Checklist verificable por el implementador:

**Contrato y parametros (sin cambio desde v2):**
- [ ] `GET /attack-reports/stats/oasis/temporal-distribution?interval_minutes=240` con `Accept-Language: es` responde `200` con `interval_minutes: 240`, `interval_label: "4h"`, `window: {lower_min:240, upper_min:300, is_open:false}`.
- [ ] `interval_minutes` ausente → `200` con `interval_minutes: 240` (default).
- [ ] Frontera inclusiva inferior: gap `7*60=420s` con `interval_minutes=7` → cuenta.
- [ ] Frontera exclusiva superior: gap `10*60=600s` con `interval_minutes=7` → NO cuenta.
- [ ] Robustez al ruido: gap `9*60=540s` con `interval_minutes=7` → cuenta en ventana 7.
- [ ] Gaps < 6 min descartados: gap `5*60=300s` no aparece en ninguna ventana.
- [ ] Gap 86400s con `interval_minutes=300` → cuenta (ventana abierta).
- [ ] Gap 86400s con `interval_minutes=240` → NO cuenta.
- [ ] Gap 0s o negativo → descartado.
- [ ] Primer ataque a oasis → no genera gap.
- [ ] `interval_minutes=45` (fuera del set) → `400` con detail que lista los 10 valores validos.
- [ ] `interval_minutes` no entero → `422`.
- [ ] `Accept-Language` ausente → `400`.
- [ ] `Accept-Language: zh` → `400`.
- [ ] `interval_minutes=300` → `interval_label: "5h+"`, `window.upper_min: null`, `window.is_open: true`.
- [ ] El endpoint esta declarado ANTES de EP-06 (`/stats/oasis`) en el router.

**Estructura v3 — agrupacion por tipo:**
- [ ] La respuesta tiene campo `types` (NO `animals` en el nivel raiz).
- [ ] `types` contiene exactamente 5 elementos.
- [ ] Orden fijo: `types[0].oasis_type="hierro"`, `types[1].oasis_type="arcilla"`, `types[2].oasis_type="madera"`, `types[3].oasis_type="cereal"`, `types[4].oasis_type="sin_clasificar"`.
- [ ] `types[1].oasis_type_label="Barro"` (no "Arcilla").
- [ ] `n_reports_in_window` == suma de `n_reports_in_section` de las 5 secciones.
- [ ] Secciones sin datos: `n_oasis=0`, `n_oasis_low_confidence=0`, `n_reports_in_section=0`, `animals=[]`. No se omiten del array.
- [ ] BD vacia o ventana sin datos → `200` con `n_reports_in_window: 0`, 5 secciones vacias.

**Clasificacion por tipo:**
- [ ] Oasis con animales `{1,2,4}` (rata, arana, murcielago) → clasificado como "hierro".
- [ ] Oasis con animales `{5,6,7}` (jabali, lobo, oso) → clasificado como "madera".
- [ ] Oasis con solo reportes de derrota (todos `present=NULL`) → sus gaps van a "sin_clasificar".
- [ ] Oasis con 1-2 bursts observados (`confidence="low"`) → incluido en su seccion de tipo, no en "sin_clasificar"; `n_oasis_low_confidence` de esa seccion = 1.
- [ ] Oasis con >= 3 bursts (`confidence="medium"`) → `n_oasis_low_confidence` no se incrementa para ese oasis.

**Estadisticas dentro de cada seccion:**
- [ ] `animals` dentro de cada seccion ordenados por `animal_ordinal ASC`.
- [ ] `n_total` incluye gaps con `present=null` (derrotas). `n_valid` los excluye.
- [ ] Si `n_valid=0` para un animal en una seccion → `avg_present: null`, `mode_present: []`.
- [ ] Empate en moda dentro de una seccion → `mode_present` con todos los valores empatados ASC.

**Reutilizacion de logica:**
- [ ] `_infer_type` ha sido elevada a `infer_type` (o equivalente en modulo compartido) — ya completado en v3.
- [ ] EP-SPAWN sigue funcionando tras la elevacion (sus tests existentes en verde) — ya verificado en v3.
- [ ] NO hay un tercer calculo de Jaccard en el adapter (no duplicacion).

**Nuevos campos v4 — max_present:**
- [ ] Cada elemento de `animals[]` dentro de cada seccion tiene el campo `max_present`.
- [ ] `max_present` es `null` si `n_valid=0`. Si `n_valid>0` es un entero `>= avg_present` (por construccion).
- [ ] Animal con `present` siempre igual (ej. siempre 3): `max_present=3`, `avg_present=3.0`, `mode_present=[3]`.
- [ ] `max_present` excluye `present=NULL` (misma regla que avg y mode).

**Nuevos campos v4 — avg_bounty:**
- [ ] Cada seccion tiene campo `avg_bounty` con subcampos `wood, clay, iron, crop, total`.
- [ ] Todos los subcampos son enteros (no floats).
- [ ] `avg_bounty` de seccion vacia (`n_reports_in_section=0`) → todos los subcampos a `0`.
- [ ] `avg_bounty.total` = media del `(w+c+i+cr)` por reporte, no la suma de `avg_bounty.wood + clay + iron + crop`.
- [ ] Incluye derrotas con botín 0 en el denominador (DDL `NOT NULL DEFAULT 0`).
- [ ] El botín no se cuenta múltiples veces por animal del mismo reporte (deduplicado por `report_id`).

**Nuevos campos v4 — total_animals:**
- [ ] Cada seccion tiene campo `total_animals` con subcampos `avg, mode, max, n_valid, n_total`.
- [ ] `total_animals.n_total` == `n_reports_in_section` de la misma seccion.
- [ ] `total_animals.n_valid` <= `n_total`. Si todos son derrotas → `n_valid=0`.
- [ ] Reporte de derrota total (todos `present=NULL`) → excluido de `n_valid`.
- [ ] Reporte con UN animal `present=NULL` → excluido de `n_valid` (regla "todo o nada").
- [ ] Si `n_valid=0` → `avg=null`, `mode=[]`, `max=null`.
- [ ] Empate en moda del total → `mode` con todos los valores empatados ASC.
- [ ] `avg` redondeado a 2 decimales.

**Nuevos campos v4 — oasis_coords:**
- [ ] Cada seccion tiene campo `oasis_coords` como lista de `{x: int, y: int}`.
- [ ] Seccion vacia → `oasis_coords=[]`.
- [ ] Dos oasis distintos del mismo tipo → `oasis_coords` contiene los 2, ordenados `(y ASC, x ASC)`.
- [ ] Las coordenadas son enteros crudos (sin formateo `(-15|23)` — eso es tarea del frontend).
- [ ] `len(oasis_coords)` == `n_oasis` de la misma seccion.

**Port y cliente:**
- [ ] Metodo abstracto `get_animal_temporal_distribution` tiene docstring actualizado con v4.
- [ ] `getAnimalTemporalDistribution(intervalMinutes=240)` en `frontend/src/api/client.js` tiene comentario indicando la estructura v4 con los campos nuevos.
- [ ] El componente `AnimalFrequencyPanel.jsx` NO esta implementado (solo stub); su implementacion queda bloqueada hasta el rediseno del `disenador-producto` v5.

## 16. Trazabilidad

| Decisión técnica | Requisito / edge case que la origina |
|-----------------|--------------------------------------|
| Base temporal = LAG sobre `attacked_at` | Decisión del usuario: gap empírico entre ataques consecutivos al mismo oasis |
| Scope = solo global | Decisión del usuario: alcance = solo global |
| Tipos de animal = todos por separado | Decisión del usuario |
| Reutilizar `attack_reports` + `attack_report_animals` | Datos ya existen; no hay cambio de esquema |
| Patrón LAG con `PARTITION BY coords` | RN-TD11: gaps no deben cruzar oasis distintos — patrón confirmado en EP-09 |
| `interval_minutes` ∈ `{6,7,10,15,30,60,120,180,240,300}`, default `240` | Decisión del usuario (v2): frecuencias discretas reales del juego; 240 = ventana de sueño |
| Binning Opción B (umbral inferior) | Decisión del usuario (v2): monotonicidad y robustez al ruido de lag (§13) |
| Gaps < 6 min descartados | RN-TD04: no existe bin menor que 6 min; incluirlos distorsionaría el bin de 6 min |
| Respuesta de una sola frecuencia (no matriz) | Decisión del usuario (v2): UX más simple, payload menor, exploración interactiva |
| `n_reports_in_window` a nivel raíz | RN-TD08: denominador de "cuántos ataques tienes en esta cadencia" — señal de confianza |
| `present = NULL` → cuenta en `n_total`, excluido de cálculos | EC-TD02: derrotas son válidas como observaciones de timing pero no de cantidad |
| `n_total` y `n_valid` por animal | EC-TD02, EC-TD03: señal de confianza a nivel de especie |
| Moda en Python con `Counter` | RN-TD07: SQLite no tiene `MODE()`; empates como lista |
| Media redondeada a 2 decimales | RN-TD06: precisión suficiente para unidades de animales |
| `Accept-Language` obligatorio via `get_language` | RN-TD10: nombres de animal localizados — consistente con convención del proyecto |
| Nombres via `translation_port.get_troop_names_by_tribe(Tribe.nature, lang)` | RN-TD10: catálogo NATURE_1..10 en 25 idiomas verificado |
| `icon_url = /static/icons/nature_{ordinal}.png` | Patrón existente de EP-06 y otros endpoints de animales |
| `400` para `interval_minutes` semánticamente inválido | RN-TD13: valor fuera del conjunto es error de negocio, no de tipo; `422` es para errores de tipo/formato |
| `200` con `n_reports_in_window=0`, `animals=[]` si ventana vacía | RN-TD12: consistente con todos los endpoints de stats del proyecto; nunca `404` |
| UI bloqueada hasta rediseño del `disenador-producto` | Regla "mockup-first" del proyecto (CLAUDE.md): la vista pasa de matriz a lista simple |
| Endpoint declarado antes de EP-06 | Evitar colisión de routing con ruta literal vs. ruta dinámica |
| **Reutilizacion (v2):** modificar endpoint existente, no crear nuevo | El endpoint EP-TD fue creado en v1; v2 es una modificacion del mismo |
| **APIs (v2/v3):** contrato pendiente de gate de `desarrollador-apis` | `apis_validadas_por_desarrollador_apis: false` — v3 cambia schema radicalmente; gate necesario antes de implementar cliente HTTP |
| Velocidad de servidor no se ajusta | Decision acordada: el endpoint trabaja con tiempo real; el usuario configura timers en tiempo real |
| **v3: segmentacion por tipo de oasis** | Feedback del usuario: necesita distinguir la composicion por tipo de oasis (hierro/arcilla/madera/cereal) a una cadencia dada |
| **v3: inferencia por oasis (no por reporte)** | Una vez por oasis sobre el agregado de `present>0` — mas robusta que por reporte individual; un animal "sorpresa" en un reporte no cambia el tipo inferido del oasis |
| **v3: reutilizacion de `_infer_type` elevada** | RN-TD14: un segundo Jaccard divergente seria un bug silencioso. Decision: elevar a `infer_type` publica — confirmada por palantir (aviso de duplicacion en el analisis del gate) |
| **v3: oasis de baja confianza incluidos en su seccion** | RN-TD16: excluirlos ocultaria datos reales. La marca `n_oasis_low_confidence` es suficiente para que el front informe al usuario |
| **v3: 5 secciones fijas siempre presentes** | RN-TD17: el frontend necesita estructuras predecibles para renderizar el empty state sin comprobar si la clave existe |
| **v3: `oasis_type_label` "Barro" para clave "arcilla"** | RN-TD18: la terminologia del usuario es "Barro"; la clave interna del catalogo es "arcilla". Se desacoplan para no cambiar el catalogo |
| **v3: sin parametro de filtro por tipo** | Decision acordada: el endpoint devuelve siempre las 5 secciones; el filtrado es responsabilidad del frontend |
| **v3: cereal borroso — limitacion documentada** | El set cereal es universal {1..10}; Jaccard lo penaliza pero oasis muy variados se clasifican correctamente como cereal. La nota en la UI es obligatoria (§13 trade-offs) |
| **v3: UI rediseno separado** | Regla "mockup-first" del proyecto: la vista pasa de lista plana a secciones por tipo — requiere nuevo spec de disenador-producto y mockup aprobado por el usuario |
| **v4: max_present por animal** | Feedback del usuario: necesita el peor caso de animales por especie. Reutilización: `max(data["valids"])` — misma lista `valids` ya acumulada en v3. Verificado en código. |
| **v4: avg_bounty por sección — denominador = todos los reportes** | RN-TD22: DDL confirma `bounty_* NOT NULL DEFAULT 0`. Denominador incluye derrotas. Consistente con `get_bounty_stats`. Trade-off documentado en §13. |
| **v4: avg_bounty.total calculado sobre suma por reporte** | RN-TD23: evitar error de ±1 por redondeo independiente de cada recurso. El total es la media de la suma por reporte. |
| **v4: botín deduplicado por report_id en type_bounty** | RN-TD25: la CTE produce una fila por reporte, pero el JOIN con animals duplica esa fila por cada animal. El botín es del reporte y no debe sumarse N veces. |
| **v4: total_animals — regla "todo o nada" para NULL** | RN-TD21: suma parcial de `present` con ausencias silenciosas es engañosa. Un total sin todos los animales no representa el tamaño real del oasis. Trade-off documentado en §13. |
| **v4: total_animals a nivel de sección, no por animal** | El total = suma de todos los animales del reporte. Es un dato del reporte, no de un animal individual. Por animal no tiene sentido semántico. |
| **v4: oasis_coords serializa type_oasis_ids** | RN-TD24: reutilización total del set `type_oasis_ids[tipo]` ya construido en v3 (palantir confirmó que se descartaba). Costo: 2-3 líneas de serialización. |
| **v4: oasis_coords sin cap** | RN-TD24: número de oasis accesibles en Travian siempre pequeño. Cap diferido a v5 si se necesita. Trade-off documentado en §13. |
| **v4: oasis_coords ordenados (y ASC, x ASC)** | Determinismo para tests. El orden no es semánticamente relevante para el frontend. |
| **v4: oasis_coords con enteros crudos (sin formatear)** | Consistencia con el resto de endpoints que devuelven coords (OasisList, EP-06, EP-08). El formato `(-15|23)` lo hace el frontend. Palantir identificó 5 copias del formateador → centralizar en coordUtils.js (tarea UI v5). |
| **v4: CTE report_gaps extendida con bounty** | La CTE ya existe en v3. Añadir 4 campos al SELECT es el cambio mínimo y retrocompatible. No requiere nueva query. Reutilización verificada en código del adapter. |
| **v4: gate desarrollador-apis pendiente** | Se añaden campos nuevos al response — el contrato v3 queda obsoleto. Requiere validación de desarrollador-apis antes de que el cliente HTTP lea los campos nuevos. |
| **v4: UI rediseño separado (v5)** | Regla "mockup-first" del proyecto. El panel pasa a tener: max_present por animal, zona "resumen del tipo" con total_animals + avg_bounty + oasis_coords. Requiere nuevo spec de disenador-producto v5 + mockup editable + gate humano. |

## Registro de implementación v1 (histórico)

**Fecha:** 2026-06-02
**Implementado por:** desarrollador-funcionalidades

### Ficheros creados
- `tests/test_animal_temporal_distribution_api.py` — 33 tests (T-TD01..T-TD20 + criterios de aceptación)

### Ficheros modificados
- `core/ports/attack_report_port.py` — método abstracto `get_animal_temporal_distribution` añadido (~línea 180, tras `get_oasis_spawn_composition`)
- `adapters/db/attack_report_sqlite_adapter.py` — método `get_animal_temporal_distribution` implementado en `AttackReportSQLiteAdapter`; añadido `Counter` a los imports de `collections`
- `adapters/api/routes/attack_reports.py` — endpoint EP-TD declarado antes de EP-06; imports de `get_language`, `get_translation_port` y `Depends` añadidos; comentario de cabecera actualizado
- `frontend/src/api/client.js` — método `getAnimalTemporalDistribution(bucketHours=2)` añadido
- `frontend/src/components/attack-reports/StatsTab.jsx` — comentario stub de `AnimalFrequencyPanel` añadido (bloqueado hasta spec de diseño)

### Resultado v1
**33 de 33 tests pasan.**
Suite completa del módulo: 166/166 tests en `test_attack_reports_api.py` + `test_oasis_spawn_composition_api.py` sin regresiones.

### Desviaciones de diseño registradas en v1
- **Cálculo de bucket en test_TD20 corregido**: el spec describe que un gap de 10h con `bucket_hours=2` cae en `[10h, 12h)` (`lower_h=10`), no en `[8h, 10h)` como el test inicial asumía. El cálculo `floor(36000 / 7200) * 2 = 10` es correcto conforme a la fórmula del §9. El test fue corregido para reflejar la expectativa correcta — no hay desviación en la implementación, sino en el test.
- **getAnimalTemporalDistribution en client.js usa buildHeaders()**: la función `buildHeaders()` del cliente ya inyecta `Accept-Language` automáticamente desde `localStorage.getItem('lang')`, por lo que no es necesario pasar el header explícitamente como en el pseudocódigo del §14. El comportamiento es idéntico al contrato acordado.

---

## Qué cambia respecto a la implementación v1 (guía para el implementador)

> Esta sección es la hoja de ruta de migración v1 → v2. El implementador debe seguir
> esta lista en orden. Los ficheros afectados son exactamente los mismos que en v1.

### Para `desarrollador-apis` (revalidar contrato)

1. **Parámetro renombrado:** `bucket_hours` → `interval_minutes`.
2. **Conjunto de valores:** `{1,2,4,8,12,24}` (horas) → `{6,7,10,15,30,60,120,180,240,300}` (minutos).
3. **Default:** `2` (horas) → `240` (minutos).
4. **Semántica de `400`:** el detail debe listar los 10 nuevos valores válidos.
5. **Schema de response completamente nuevo:** de `{bucket_hours, animals[{..., buckets[...]}]}` (matriz) a `{interval_minutes, interval_label, window, n_reports_in_window, animals[{..., avg, mode, n_total, n_valid}]}` (lista plana de una frecuencia). Ver §8 para el schema completo y la tabla de etiquetas.
6. **Campo `interval_label`** como string semántico (ej. `"4h"`, `"5h+"`, `"7 min"`).
7. **Campo `window`** con `lower_min`, `upper_min` (en minutos, no horas), `is_open`.
8. **Campo `n_reports_in_window`** a nivel raíz.
9. **El bin 300 es abierto:** `upper_min: null`, `is_open: true`, `interval_label: "5h+"`.
10. El contrato v1 en `openapi.yaml`, `API.md` y `AGENTS.md` debe actualizarse para reflejar el nuevo schema.

### Para `desarrollador-funcionalidades` (cambios de implementación)

#### `core/ports/attack_report_port.py`
- Cambiar la firma del método abstracto: `bucket_hours: int` → `interval_minutes: int`.
- Actualizar el docstring para reflejar los nuevos valores válidos y el nuevo schema de retorno.

#### `adapters/db/attack_report_sqlite_adapter.py`
- Reescribir el método `get_animal_temporal_distribution` completamente (ver pseudocódigo §9):
  - Añadir constantes `VALID_INTERVALS`, `WINDOWS`, `LABELS` (o importarlas de un módulo compartido).
  - Calcular `lower_sec` / `upper_sec` desde `WINDOWS[interval_minutes]`.
  - **Nuevo filtro:** descartar `gap_seconds < 360` (< 6 min) — no existía en v1.
  - **Nuevo filtro de ventana:** seleccionar solo gaps en `[lower_sec, upper_sec)`.
  - **Eliminar el agrupamiento por bucket:** ahora se agrupa solo por `animal_ordinal`.
  - **Calcular `n_reports_in_window`** a nivel raíz (count de `report_id` distintos).
  - **Devolver el nuevo schema** (sin campo `buckets` dentro de cada animal; los campos `avg_present`, `mode_present`, `n_total`, `n_valid` suben al nivel del animal directamente).

#### `adapters/api/routes/attack_reports.py`
- Cambiar `bucket_hours: int = Query(default=2)` → `interval_minutes: int = Query(default=240)`.
- Cambiar la whitelist de `{1,2,4,8,12,24}` → `{6,7,10,15,30,60,120,180,240,300}`.
- Actualizar el detail del `400`.
- Actualizar la llamada al adapter.

#### `frontend/src/api/client.js`
- Renombrar la función o el parámetro: `bucketHours=2` → `intervalMinutes=240`.
- Cambiar el nombre del query param de `bucket_hours` a `interval_minutes`.

#### `tests/test_animal_temporal_distribution_api.py`
- **Eliminar los 33 tests v1** (basados en `bucket_hours` y la matriz).
- **Escribir los 27 tests v2** (T-TD01..T-TD27 del §12), incluyendo obligatoriamente los casos
  de binning de frontera T-TD12..T-TD18.
- Los tests de frontera son los más críticos para verificar la Opción B:
  - T-TD12: gap exactamente en límite inferior → cuenta.
  - T-TD13: gap con ruido dentro del bin → cuenta en el bin correcto, no salta.
  - T-TD14: gap exactamente en límite superior → cae en el bin siguiente, no en el actual.
  - T-TD15: gap < 6 min → descartado.

### Nota sobre la UI
El componente `AnimalFrequencyPanel.jsx` y su stub en `StatsTab.jsx` no se tocan en esta
iteración, salvo actualizar el comentario del stub para indicar que es una vista de lista
simple (no matriz). El rediseño completo de la UI es responsabilidad del `disenador-producto`
en una iteración separada.

---

## Registro de implementación v2

**Fecha:** 2026-06-02
**Implementado por:** desarrollador-funcionalidades

### Ficheros modificados
- `core/ports/attack_report_port.py` — firma del método abstracto `get_animal_temporal_distribution`: `bucket_hours` → `interval_minutes`; docstring actualizado con los 10 valores válidos y el nuevo schema de retorno.
- `adapters/db/attack_report_sqlite_adapter.py` — reescritura completa del método `get_animal_temporal_distribution`: constantes `_WINDOWS`/`_LABELS` locales, binning umbral inferior, filtro `gap_seconds < 360`, ventana `[lower_sec, upper_sec)` o `[lower_sec, ∞)`, `n_reports_in_window` por report_ids distintos, schema plano de una sola frecuencia sin `buckets`. Bug fixes: `Tribe.NATURE` (mayúsculas) y clave `"nombre"` del JsonTranslationAdapter.
- `adapters/api/routes/attack_reports.py` — `bucket_hours: int = Query(default=2)` → `interval_minutes: int = Query(default=240)`; whitelist `{1,2,4,8,12,24}` → `{6,7,10,15,30,60,120,180,240,300}`; detail del 400 actualizado con los 10 valores; llamada al adapter actualizada.
- `frontend/src/api/client.js` — `getAnimalTemporalDistribution(bucketHours=2)` → `getAnimalTemporalDistribution(intervalMinutes=240)`; query param `bucket_hours` → `interval_minutes`.
- `tests/test_animal_temporal_distribution_api.py` — 33 tests v1 eliminados; 39 tests v2 escritos (T-TD01..T-TD27 + CA).
- `documentacion/backend/referencia-funciones/attack-report-temporal-distribution.md` — actualizado a v2 con nueva firma, tabla de bins, algoritmo y cliente JS.

### Comando para ejecutar los tests
```bash
source .venv/bin/activate && pytest tests/test_animal_temporal_distribution_api.py -v
```
Suite completa (sin regresiones):
```bash
source .venv/bin/activate && pytest tests/ --ignore=tests/unit --ignore=tests/antideteccion -q
```

### Resultado
**39 de 39 tests del módulo pasan.**
Suite completa: 541 passed, 11 skipped (resources_api — dependencia de browser, no aplica), 0 failed.

### Desviaciones de diseño registradas en v2
- `Tribe.NATURE` en mayusculas: el pseudocodigo del §9 usa `Tribe.nature` pero el enum Python usa `Tribe.NATURE`. La v1 fallaba silenciosamente al resolver nombres (los capturaba el `except Exception`); en v2 se corrige y se cubre con T-TD09.
- Clave `"nombre"` en el dict del translation_port: el pseudocodigo del §9 usa `entry["name"]` pero `JsonTranslationAdapter.get_troop_names_by_tribe` devuelve `entry["nombre"]`. Corregido en la implementacion v2.
- 39 tests en lugar de 27: el §12 describe 27 tests (T-TD01..T-TD27) pero la implementacion anade 12 tests CA adicionales (criterios de aceptacion §15 y validaciones de metadatos de ventana). Los 27 del spec estan todos presentes y en verde.

---

## Que cambia respecto a la implementacion v2 (guia para el implementador v3)

> Esta seccion es la hoja de ruta de migracion v2 → v3.
> Los ficheros de la implementacion v2 son exactamente los que hay que modificar.

### Para `desarrollador-apis` (revalidar contrato v3)

1. **El campo raiz `animals` desaparece.** Se sustituye por `types` (array de 5 secciones).
2. **Campo `types` nuevo:** array con 5 elementos fijos (hierro, arcilla, madera, cereal, sin_clasificar).
3. **Cada seccion tiene:** `oasis_type`, `oasis_type_label`, `n_oasis`, `n_oasis_low_confidence`,
   `n_reports_in_section`, `animals[]` (mismo schema que el array plano de v2).
4. **`oasis_type_label` de "arcilla" es "Barro"** — no "Arcilla".
5. **`n_reports_in_window` en el raiz** sigue presente; ahora es la suma de `n_reports_in_section`.
6. **Secciones vacias siempre presentes** — nunca ausentes del array.
7. **Sin nuevo query param.** El endpoint no anade `oasis_type` como parametro de filtro.
8. El contrato v2 en `openapi.yaml`, `API.md` y `AGENTS.md` debe actualizarse para reflejar el schema v3.

### Para `desarrollador-funcionalidades` (cambios de implementacion v2 → v3)

#### `adapters/db/attack_report_sqlite_adapter.py` (cambio principal)

Pasos 1-7 del §14:
- **Elevar `_infer_type` a `infer_type`** (Paso 1 del §14) — no reimplementar Jaccard.
- **Anadir query de composicion** (misma que EP-SPAWN, Paso 1 del §9 pseudocodigo).
- **Ampliar query LAG** para devolver `coord_x_dest` y `coord_y_dest` (Paso 2 del §9).
- **Sustituir agrupamiento por `animal_ordinal`** por agrupamiento por `(tipo, animal_ordinal)`.
- **Construir array `types` con 5 secciones** (Paso 9 del §9).
- **Eliminar el campo `animals` del retorno raiz** — ahora va dentro de cada seccion.
- **Anadir constantes `TYPE_LABELS` y `TYPE_ORDER`** al modulo.

Bugs de v2 que siguen vigentes (NO regresar): `Tribe.NATURE` (mayusculas), clave `"nombre"`.

#### `core/ports/attack_report_port.py`
- Actualizar el docstring del metodo abstracto: el retorno tiene `types` (no `animals`).
- La firma `(interval_minutes, lang, translation_port)` no cambia.

#### `adapters/api/routes/attack_reports.py`
- Sin cambios funcionales. Solo actualizar el comentario de cabecera a v3.

#### `frontend/src/api/client.js`
- Sin cambios funcionales en la firma. Anadir comentario sobre el schema v3 con `types[]`.

#### `tests/test_animal_temporal_distribution_api.py`
- **Eliminar los 39 tests v2** (verifican `animals` en el raiz).
- **Escribir los tests v3** cubriendo T-TD01..T-TD35 del §12.
- Mantener todos los casos de binning de frontera (T-TD12..T-TD18) sin modificacion.
- Anadir fixtures con oasis de tipos diferenciados para los casos T-TD28..T-TD35.

### Nota sobre la UI
El componente `AnimalFrequencyPanel.jsx` y su stub en `StatsTab.jsx` no se tocan en v3,
salvo actualizar el comentario del stub a "(v3: secciones por tipo de oasis)".
El rediseno completo de la UI (secciones por tipo, etiquetas, disclaimer de cereal,
indicador de baja confianza) es responsabilidad del `disenador-producto` + nuevo mockup
editable aprobado por el usuario. No implementar la UI sin ese gate.

---

## Registro de implementacion v3

**Fecha:** 2026-06-02
**Implementado por:** desarrollador-funcionalidades

### Ficheros modificados
- `adapters/db/attack_report_sqlite_adapter.py` — `_infer_type` renombrada a `infer_type` (pública); `get_oasis_spawn_composition` actualizado para usar `infer_type`; `get_animal_temporal_distribution` reescrito con: constantes `_TYPE_LABELS`/`_TYPE_ORDER`, query de composición (Paso 1), query LAG con CTE (Paso 2), agrupación por `(tipo, animal_ordinal)` (Paso 6), construcción del array `types` con 5 secciones (Paso 9), `n_reports_in_window` como suma de secciones (Paso 10).
- `core/ports/attack_report_port.py` — docstring del método abstracto `get_animal_temporal_distribution` actualizado a v3 (retorno `types` en lugar de `animals`).
- `adapters/api/routes/attack_reports.py` — comentarios de cabecera actualizados a v3.
- `frontend/src/api/client.js` — comentario del método `getAnimalTemporalDistribution` actualizado con schema v3 (`types[]`).
- `frontend/src/components/attack-reports/StatsTab.jsx` — comentarios stub actualizados a v3.
- `tests/test_animal_temporal_distribution_api.py` — 39 tests v2 eliminados; 41 tests v3 escritos (T-TD01..T-TD35 + 6 tests CA).
- `documentacion/backend/referencia-funciones/attack-report-temporal-distribution.md` — actualizado a v3 con nueva estructura types[], tabla de etiquetas, algoritmo CTE, helper infer_type.

### Comando para ejecutar los tests
```bash
source .venv/bin/activate && pytest tests/test_animal_temporal_distribution_api.py -v
```
Suite completa (sin regresiones):
```bash
source .venv/bin/activate && pytest tests/ --ignore=tests/unit --ignore=tests/antideteccion -q
```

### Resultado
**41 de 41 tests del módulo pasan.**
Suite completa: 543 passed, 11 skipped, 0 failed.
EP-SPAWN: 52/52 en verde (sin regresión tras elevar `_infer_type` → `infer_type`).

### Desviaciones de diseño registradas en v3

1. **CTE para query LAG:** el spec §9 describe la query LAG como un JOIN directo con `attack_report_animals`. En la implementación se usa una CTE que primero calcula los gaps a nivel de reporte y luego hace JOIN con los animales. Esto es necesario porque sin CTE, el WINDOW LAG toma la fila anterior del JOIN (el animal anterior del mismo reporte) en lugar del reporte anterior. La CTE garantiza el comportamiento correcto sin alterar la semántica del spec. Ver código y comentario en el adapter.

2. **Test T-TD30 ajustado:** el spec describe el test como "oasis con 1 burst observable". En el fixture final se usa Murciélago (ordinal=4) como único animal del oasis (que solo pertenece al set hierro, con Jaccard estrictamente superior a otros tipos), forzando clasificación unívoca con low confidence (2 bursts < 3). Oasis con solo Rata (ordinal=1) da empate Jaccard hierro=arcilla (ambos tienen {1} en sus sets), lo que lo clasifica como arcilla (alfabético gana en el desempate) en lugar de hierro. El test fue corregido para reflejar el comportamiento real y determinístico de `infer_type`.

3. **39 tests v2 eliminados:** el spec §14 paso 7 indica "eliminar los 39 tests v2". Los nuevos tests incluyen T-TD01..T-TD35 más 6 tests CA, para un total de 41 (2 más que los 35 del spec). Los tests extra son criterios de aceptación del §15 convertidos a tests explícitos.

---

## Que cambia respecto a la implementacion v3 (guia para el implementador v4)

> Esta sección es la hoja de ruta de delta v3 → v4.
> La implementación v3 está en verde (41 tests). Los cambios son INCREMENTALES:
> solo se añaden campos; no se elimina ni reescribe nada de v3.

### Para `desarrollador-apis` (revalidar contrato v4)

1. **Nuevo campo `types[].oasis_coords`**: array de `{x: integer, y: integer}`. `[]` si sección vacía.
2. **Nuevo campo `types[].avg_bounty`**: objeto con `wood, clay, iron, crop, total` (todos `integer`). `0` si sección vacía.
3. **Nuevo campo `types[].total_animals`**: objeto con `avg (number|null)`, `mode (array[int])`, `max (int|null)`, `n_valid (int)`, `n_total (int)`.
4. **Nuevo campo `types[].animals[].max_present`**: `integer|null`. Aparece después de `mode_present`, antes de `n_total`.
5. **El contrato v3 en `openapi.yaml`, `API.md` y `AGENTS.md` debe actualizarse** para reflejar los 4 campos nuevos.
6. **Parámetros, errores, cabeceras y semántica del endpoint**: sin cambio. Solo se añaden campos al response.

### Para `desarrollador-funcionalidades` (cambios de implementacion v3 → v4)

#### `adapters/db/attack_report_sqlite_adapter.py` (cambio principal)

1. **Extender la CTE `report_gaps`**: añadir `r.bounty_wood, r.bounty_clay, r.bounty_iron, r.bounty_crop` al SELECT de la CTE. El SELECT exterior del JOIN también debe exponer estos campos.

2. **Añadir 3 estructuras auxiliares** en el bucle de `window_rows` (Paso 6):
   ```python
   type_bounty       = defaultdict(dict)  # {tipo: {rid: (w,c,i,cr)}}
   type_report_nulls = defaultdict(dict)  # {tipo: {rid: bool}}  — True = algún NULL
   type_report_sums  = defaultdict(dict)  # {tipo: {rid: int}}   — suma present no nulos
   ```
   Por cada `row` en `window_rows`:
   - Si `rid` no está en `type_bounty[tipo]` → insertar `(bounty_wood, bounty_clay, bounty_iron, bounty_crop)`.
   - Si `rid` no está en `type_report_nulls[tipo]` → inicializar a `False`, sum a `0`.
   - Si `row["present"] is None` → `type_report_nulls[tipo][rid] = True`.
   - Si `row["present"] is not None` → `type_report_sums[tipo][rid] += row["present"]`.

3. **Añadir `max_present`** en el helper `_build_animals`:
   ```python
   max_present = max(data["valids"]) if n_valid > 0 else None
   ```
   Añadir al dict resultado del animal: `"max_present": max_present`.

4. **Añadir helpers** en el Paso 8 (antes de `_build_animals`):
   - `_build_avg_bounty(tipo)` — ver pseudocódigo §9.
   - `_build_total_animals(tipo)` — ver pseudocódigo §9.
   - `_build_oasis_coords(tipo)` — ver pseudocódigo §9.

5. **Añadir los 4 campos nuevos** al dict de la sección en el Paso 9:
   ```python
   "oasis_coords":  _build_oasis_coords(tipo),
   "avg_bounty":    _build_avg_bounty(tipo),
   "total_animals": _build_total_animals(tipo),
   ```
   Y `"max_present"` ya queda dentro de cada animal via `_build_animals`.

#### `core/ports/attack_report_port.py`
- Actualizar el docstring para referenciar v4 (campos nuevos en el retorno).

#### `adapters/api/routes/attack_reports.py`
- Sin cambios funcionales. Solo actualizar el comentario de cabecera a v4.

#### `frontend/src/api/client.js`
- Sin cambios funcionales. Actualizar el comentario del método a v4.

#### `tests/test_animal_temporal_distribution_api.py`
- **NO eliminar los 41 tests v3**: siguen siendo válidos (max_present es un campo nuevo, no reemplaza nada).
- **AÑADIR los tests T-TD36..T-TD46** del §12.
- Los fixtures deben cubrir: victoria completa, solo derrotas, derrota parcial (un animal NULL), dos oasis distintos del mismo tipo, `avg_bounty.total` vs. suma de medias.

#### `documentacion/backend/referencia-funciones/attack-report-temporal-distribution.md`
- Actualizar a v4: añadir los 4 campos nuevos, los denominadores, la extensión de la CTE.

---

## Registro de implementación v4

**Fecha:** 2026-06-02
**Implementado por:** desarrollador-funcionalidades

### Ficheros modificados

| Fichero | Tipo de cambio |
|---------|----------------|
| `adapters/db/attack_report_sqlite_adapter.py` | Cambio principal: CTE ampliada + 3 estructuras auxiliares + 4 helpers + campos v4 en sección |
| `adapters/api/routes/attack_reports.py` | Añadidos 7 modelos Pydantic v4 + `response_model=_TDResponse` en EP-TD + comentario actualizado a v4 |
| `core/ports/attack_report_port.py` | Docstring de `get_animal_temporal_distribution` actualizado a v4 |
| `frontend/src/api/client.js` | Comentario del método `getAnimalTemporalDistribution` actualizado a v4 |
| `tests/test_animal_temporal_distribution_api.py` | Añadidos 13 tests T-TD36..T-TD48 (v3 intactos) |

### Comando para ejecutar los tests

```bash
.venv/bin/python -m pytest tests/test_animal_temporal_distribution_api.py -v
```

### Resultado de los tests

- **EP-TD v4:** 54/54 en verde (41 v3 + 13 v4 nuevos).
- **EP-SPAWN:** 52/52 sin regresión.
- **test_attack_reports_api:** 114/114 sin regresión.
- **Suite completa:** 1575 passed, 23 skipped, 3 failed (los 3 fallos son preexistentes no relacionados con esta feature: guardian-antideteccion con cambios sin commitear y 2 fallos de sesiones/login preexistentes).

### Desviaciones de diseño registradas en v4

1. **`_build_avg_bounty` usa `type_report_ids[tipo]` como denominador**, no `len(type_bounty[tipo])`. Esto garantiza que las derrotas (cuyos bounty=0 entran en `type_bounty` al leer la CTE) no queden fuera del denominador por ningún bug defensivo. Comportamiento fiel a RN-TD22 (denominador = n_reports_in_section).

2. **T-TD48 añadido como test adicional** más allá del rango T-TD36..T-TD46 indicado en el spec (el spec listaba hasta T-TD46 en §12; en la guía de implementación del §"Qué cambia" indica hasta T-TD46). Se añadió T-TD47 y T-TD48 para cubrir EC-TD33 (campos v4 en sección vacía) y EC-TD26+EC-TD33 (oasis_coords vacío cuando el oasis no tiene gaps en la ventana solicitada). Son tests de criterio de aceptación no debilitan v3 y mejoran la cobertura.

3. **Modelos Pydantic con prefijo `_TD`** para evitar colisiones en el espacio de nombres del módulo (el router tiene muchos modelos). Son clases privadas del módulo (convenio de prefijo `_`), no exportadas.
