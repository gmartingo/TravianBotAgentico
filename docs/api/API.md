# Referencia de API — TravianBot

> **FastAPI genera el OpenAPI automáticamente** en `http://localhost:8000/docs` (Swagger UI)
> y `http://localhost:8000/openapi.json`. Consultar esa URL para el contrato completo de
> los endpoints existentes (EP-01..EP-09). Este archivo documenta EP-10 como primer
> artefacto permanente; el resto se irá completando en futuras iteraciones.

## Índice

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| `GET` | `/attack-reports/stats/global` | Estadísticas globales de todos los oasis + % de aparición por animal | No |
| `GET` | `/attack-reports/stats/oasis/comparison` | Comparativa de reaparición por oasis | No |
| `GET` | `/attack-reports/stats/oasis/spawn-composition` | Composición de spawn, peor combinación a batir y estado cooldown/respawn | No |
| `GET` | `/attack-reports/stats/oasis/temporal-distribution` | Estadísticas de animales por tipo de oasis para una frecuencia de farmeo elegida (v3) | No (Accept-Language obligatorio) |
| `GET` | `/attack-reports/stats/oasis` | Estadísticas de un oasis + balance de recursos | No |
| `POST` | `/worlds/{id}/noise/refresh-villages` | Refrescar aldeas del village-switcher | No |
| `POST` | `/worlds/{id}/noise/paths/{path_id}/test` | Probar ruta de navegación en vivo | No |

---

## EP-09 — Estadísticas globales de todos los oasis

**`GET /attack-reports/stats/global`**

### Descripción de negocio

Devuelve estadísticas agregadas de aparición de animales y tasas de regeneración para
todos los oasis conocidos en BD, combinados en una sola vista global.

El campo `eligible_reports` por especie corrige el denominador del porcentaje de aparición:
en lugar de usar "todos los reportes de la BD" (que diluye el % porque incluye reportes de
oasis irrelevantes para esa especie), usa solo los reportes de oasis donde la especie ha
aparecido alguna vez. Ejemplo: si la rata aparece en oasis A (10 reportes) y B (5 reportes)
pero nunca en oasis C (20 reportes de madera), `eligible_reports = 15` (no 35).

El frontend calcula el porcentaje como `Math.round(appearances / eligible_reports * 100)` y
muestra la celda como `"8/15 (53%)"`. Si `eligible_reports` es null o 0 (servidor antiguo /
backward-compat), muestra solo `appearances` sin denominador.

### Request

```
GET /attack-reports/stats/global
```

Sin query params. Sin headers requeridos. Sin body.

### Response 200

```json
{
  "scope": "global",
  "animal_appearances": [
    {
      "animal_ordinal": 1,
      "animal_name": "Rat",
      "appearances": 8,
      "eligible_reports": 15,
      "avg_present": 7.50,
      "max_present": 15,
      "min_present": 3
    },
    {
      "animal_ordinal": 2,
      "animal_name": "Spider",
      "appearances": 4,
      "eligible_reports": 4,
      "avg_present": 4.33,
      "max_present": 9,
      "min_present": 2
    }
  ],
  "animal_regen_rates": [
    {
      "animal_ordinal": 1,
      "animal_name": "Rat",
      "avg_regen_per_hour": 3.45,
      "valid_intervals": 18
    }
  ]
}
```

| Campo | Tipo | Nullable | Descripción |
|-------|------|----------|-------------|
| `scope` | string | No | Siempre `"global"` |
| `animal_appearances` | array | No | Una entrada por especie con appearances ≥ 1. Vacío si BD vacía. |
| `animal_appearances[].animal_ordinal` | integer 1..10 | No | Identificador de la especie |
| `animal_appearances[].animal_name` | string | No | Texto crudo de la BD |
| `animal_appearances[].appearances` | integer ≥ 1 | No | Reportes donde `present > 0` |
| `animal_appearances[].eligible_reports` | integer ≥ 1 | No | Denominador del %; invariante: `eligible_reports >= appearances` |
| `animal_appearances[].avg_present` | float | Sí | Media de presentes en reportes con `present > 0`; null si sin datos |
| `animal_appearances[].max_present` | integer ≥ 1 | No | Máximo presentes |
| `animal_appearances[].min_present` | integer ≥ 1 | Sí | Mínimo presentes; null si sin datos |
| `animal_regen_rates` | array | No | Sin cambio respecto al shape previo de EP-09 |
| `animal_regen_rates[].avg_regen_per_hour` | float | No | Redondeado a 2 decimales |
| `animal_regen_rates[].valid_intervals` | integer ≥ 1 | No | Intervalos válidos que contribuyeron a la tasa |

BD vacía → `200` con `animal_appearances: []` y `animal_regen_rates: []`.

### Response de error

| Código | Condición |
|--------|-----------|
| `200` | Siempre (incluso BD vacía) |
| `500` | Error inesperado de BD |

### Ejemplo curl

```bash
curl http://localhost:8000/attack-reports/stats/global
```

**Enlace OpenAPI:** `docs/api/openapi.yaml` → `paths./attack-reports/stats/global`

---

## EP-10 — Comparativa de tasas de reaparición por oasis

**`GET /attack-reports/stats/oasis/comparison`**

### Descripción de negocio

Devuelve, para todos los oasis conocidos en BD, la tasa bruta de reaparición de animales
(animales/hora por especie) y la proyección del número de animales acumulados en el
momento exacto de la petición. Permite al usuario comparar qué oasis regeneran más rápido
y decidir cuándo volver a atacar.

- La proyección es lineal: `floor(survived_último_ataque + tasa × horas_transcurridas)`.
- Si el último ataque fue una derrota (survived=null), la proyección de esa especie es null.
- Un oasis con un solo reporte no tiene intervalos válidos → `has_rates: false`, `species: []`.
- Un oasis donde nunca apareció la especie X **no la incluye en su `species[]`** (ausencia semántica, no cero).
- `species_columns` son las columnas dinámicas de la tabla UI: unión de todas las especies
  con tasa en algún oasis. La UI infiere "—" cuando un oasis no tiene la especie en su array.

### Request

```
GET /attack-reports/stats/oasis/comparison
```

Sin query params. Sin headers requeridos. Sin body.

### Response 200

```json
{
  "computed_at": "2026-06-01T12:34:56.789012+00:00",
  "species_columns": [
    { "animal_ordinal": 1, "animal_name": "Rat",    "icon_url": "/static/icons/nature_1.png" },
    { "animal_ordinal": 7, "animal_name": "Tiger",  "icon_url": "/static/icons/nature_7.png" }
  ],
  "oasis": [
    {
      "coord_x_dest": -70,
      "coord_y_dest": 73,
      "total_attacks": 8,
      "last_attack": "2026-05-30T20:15:00",
      "hours_since_last_attack": 16.3,
      "has_rates": true,
      "species": [
        {
          "animal_ordinal": 7,
          "animal_name": "Tiger",
          "icon_url": "/static/icons/nature_7.png",
          "avg_regen_per_hour": 1.25,
          "valid_intervals": 6,
          "last_survived": 3,
          "projected_now": 23
        },
        {
          "animal_ordinal": 3,
          "animal_name": "Spider",
          "icon_url": "/static/icons/nature_3.png",
          "avg_regen_per_hour": 0.80,
          "valid_intervals": 4,
          "last_survived": null,
          "projected_now": null
        }
      ]
    },
    {
      "coord_x_dest": 12,
      "coord_y_dest": -45,
      "total_attacks": 1,
      "last_attack": "2026-05-28T10:00:00",
      "hours_since_last_attack": 50.6,
      "has_rates": false,
      "species": []
    }
  ]
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `computed_at` | string ISO 8601 UTC | Momento en que se calculó la proyección |
| `species_columns` | array | Columnas dinámicas de la tabla (unión de especies con tasa) |
| `species_columns[].icon_url` | string | `/static/icons/nature_{ordinal}.png` |
| `oasis[].last_attack` | string ISO 8601 naive | Hora local de Travian (sin zona horaria) |
| `oasis[].hours_since_last_attack` | float ≥ 0 | Horas entre `last_attack` (ajustado a UTC) y `computed_at` |
| `oasis[].has_rates` | bool | True si ≥1 especie tiene tasa calculada |
| `species[].last_survived` | int \| null | Survived del último reporte; null si fue derrota |
| `species[].projected_now` | int \| null | `floor(last_survived + rate × hours)`, mínimo 0; null si `last_survived` es null |

### Response de error

| Código | Condición |
|--------|-----------|
| `200` | Siempre (incluso BD vacía: `oasis: []`) |
| `500` | Error inesperado de BD |

### Ejemplo curl

```bash
curl http://localhost:8000/attack-reports/stats/oasis/comparison
```

---

## EP-SPAWN — Composición de spawn, peor combinación a batir y estado cooldown/respawn

**`GET /attack-reports/stats/oasis/spawn-composition`**

### Descripción de negocio

Reemplaza la métrica `avg_regen_per_hour` (engañosa: mezclaba ráfaga de spawn con cooldown) por
métricas coherentes con la mecánica real de Travian. El juego genera animales **en ráfaga** con
timers fijos por especie (5-14 min en servidor x1), luego entra en cooldown (horas o días).

El endpoint calcula tres cosas por oasis:

1. **Composición típica** (Pieza 2): para cada especie observada con `present > 0`, cuántos
   animales suelen aparecer de media y como máximo en una ráfaga. Permite al usuario saber qué
   esperar cuando llega a un oasis activo.

2. **Peor combinación a batir** (Pieza 3): dado un intervalo entre envíos (`timer_min`), calcula
   cuántos animales pueden haberse acumulado entre el raid anterior y el nuevo: los sobrantes del
   máximo histórico más los que respawnean durante el intervalo. Para cada especie del set base
   del oasis (no anomalías), calcula su contribución defensiva (`worst_case_count × def_infantry/cavalry`).
   El resumen `worst_case_summary` es la fuerza total a batir.

3. **Estado cooldown/respawn** (Pieza 4): clasifica cada oasis como `"respawning"` (genera
   animales activamente), `"cooldown"` (inactivo >4 horas) o `"unknown"` (sin tipo inferido).

El **tipo de oasis** se infiere por similitud de Jaccard sobre los ordinales de animales observados.
Los animales fuera del set base del tipo inferido se marcan como `is_anomaly: true` y se excluyen
del cálculo del peor caso (RN-WORST-05).

El campo `attackers` (v2.6) extrae post-hoc de los blobs `origin_village_name` los pares
`{player, village}` para que el frontend pueda agrupar en dos niveles: **Jugador → Aldea → Oasis**.
La extracción busca marcadores multi-idioma ("from village", "aus dem Dorf", etc.) y canoniza el
nombre de aldea contra la tabla `villages`. Un oasis con varios atacantes aparece bajo cada jugador
en el frontend; sus estadísticas se calculan con todos sus reportes.

Los **nombres de animal no se devuelven**: el frontend los resuelve con el `animal_ordinal` vía
`core/i18n/catalog/base/troops.json` (clave `NATURE_{ordinal}`). Esta política es coherente con
EP-06, EP-09 y EP-10.

### Parámetros de query

| Parámetro | Tipo | Obligatorio | Valores válidos | Descripción |
|-----------|------|-------------|-----------------|-------------|
| `timer_min` | integer | Sí | `6, 7, 10, 15` | Intervalo de timer en minutos. Fuera del conjunto → `400`. Ausente o no-entero → `422`. |

### Cabeceras

Sin `Accept-Language` (datos numéricos + ordinales).

### Response 200

```json
{
  "computed_at": "2026-06-02T10:00:00.000000+00:00",
  "timer_min": 6,
  "oasis": [
    {
      "coord_x_dest": -70,
      "coord_y_dest": 73,
      "total_attacks": 15,
      "last_attack": "2026-06-01T22:15:00",
      "inferred_type": "cereal",
      "confidence": "medium",
      "spawn_status": "respawning",
      "elapsed_seconds": 43200.0,
      "attackers": [
        {"player": "CrazyMouse", "village": "05 Caesar On Leave"},
        {"player": "GonnaDie",   "village": "05"}
      ],
      "species": [
        {
          "animal_ordinal": 9,
          "icon_url": "/static/icons/nature_9.png",
          "avg_present_per_burst": 4.5,
          "max_present_per_burst": 7,
          "is_anomaly": false,
          "spawn_timer_s": 780,
          "worst_case_count": 7,
          "def_infantry_contribution": 980,
          "def_cavalry_contribution": 1400
        },
        {
          "animal_ordinal": 10,
          "icon_url": "/static/icons/nature_10.png",
          "avg_present_per_burst": 2.0,
          "max_present_per_burst": 3,
          "is_anomaly": false,
          "spawn_timer_s": 840,
          "worst_case_count": 3,
          "def_infantry_contribution": 1320,
          "def_cavalry_contribution": 1560
        }
      ],
      "worst_case_summary": {
        "def_infantry_total": 2300,
        "def_cavalry_total": 2960
      }
    },
    {
      "coord_x_dest": 12,
      "coord_y_dest": -45,
      "total_attacks": 1,
      "last_attack": "2026-05-28T10:00:00",
      "inferred_type": null,
      "confidence": null,
      "spawn_status": "unknown",
      "elapsed_seconds": 360000.0,
      "attackers": [{"player": "GonnaDie", "village": "02"}],
      "species": [],
      "worst_case_summary": null
    }
  ]
}
```

| Campo | Tipo | Nullable | Descripción |
|-------|------|----------|-------------|
| `computed_at` | string ISO 8601 UTC | No | Momento exacto del cálculo en el servidor |
| `timer_min` | integer | No | Eco del parámetro recibido |
| `oasis[].coord_x_dest` / `coord_y_dest` | integer | No | Coordenadas del oasis |
| `oasis[].total_attacks` | integer ≥ 1 | No | Ataques registrados en BD |
| `oasis[].last_attack` | string ISO 8601 naive | No | Hora local Travian del último ataque (sin zona) |
| `oasis[].inferred_type` | string \| null | Sí | `"hierro"` \| `"arcilla"` \| `"madera"` \| `"cereal"` \| `null` |
| `oasis[].confidence` | string \| null | Sí | `"low"` (<3 reportes con `present>0`) \| `"medium"` (≥3) \| `null` |
| `oasis[].spawn_status` | string | No | `"respawning"` \| `"cooldown"` \| `"unknown"` |
| `oasis[].elapsed_seconds` | float ≥ 0 | No | Segundos desde `last_attack` hasta `computed_at`. Mínimo 0. |
| `oasis[].attackers` | array (minItems 1) | No | Pares `{player, village}` DISTINCT, ordenados A-Z. Nunca vacío. |
| `oasis[].species` | array | No | Solo animales con `present > 0` alguna vez. Array vacío si ninguno. |
| `species[].animal_ordinal` | integer 1–10 | No | Ordinal (1=rata..10=elefante) |
| `species[].icon_url` | string | No | `/static/icons/nature_{ordinal}.png` |
| `species[].avg_present_per_burst` | float | No | Media de `present` en reportes con `present > 0`. Redondeado a 1 decimal. |
| `species[].max_present_per_burst` | integer ≥ 1 | No | Máximo de `present` observado |
| `species[].is_anomaly` | boolean | No | `true` si el ordinal no pertenece al set base del `inferred_type` |
| `species[].spawn_timer_s` | integer \| null | Sí | Timer de spawn en segundos (catálogo `SPAWN_TIMER_S`) |
| `species[].worst_case_count` | integer \| null | Sí | `null` si `inferred_type=null` o especie es anomalía |
| `species[].def_infantry_contribution` | integer \| null | Sí | `worst_case_count × def_infantry`. `null` si `worst_case_count=null` |
| `species[].def_cavalry_contribution` | integer \| null | Sí | `worst_case_count × def_cavalry`. `null` si `worst_case_count=null` |
| `oasis[].worst_case_summary` | object \| null | Sí | `null` si `inferred_type=null` |
| `worst_case_summary.def_infantry_total` | integer ≥ 0 | No | Suma de `def_infantry_contribution` del set base |
| `worst_case_summary.def_cavalry_total` | integer ≥ 0 | No | Suma de `def_cavalry_contribution` del set base |

BD vacía → `200` con `oasis: []`. Los oasis con tipo inferido aparecen antes (null al final);
dentro de cada grupo, ordenados por `last_attack DESC`.

### Errores

| Código | Condición |
|--------|-----------|
| `200` | Siempre (incluso BD vacía) |
| `400` | `timer_min` no está en `{6, 7, 10, 15}` |
| `422` | `timer_min` ausente o tipo no entero (FastAPI automático) |
| `500` | Error inesperado de BD |

### Ejemplo curl

```bash
# Timer de 6 minutos
curl "http://localhost:8000/attack-reports/stats/oasis/spawn-composition?timer_min=6"

# Timer de 15 minutos
curl "http://localhost:8000/attack-reports/stats/oasis/spawn-composition?timer_min=15"
```

**Enlace OpenAPI:** `docs/api/openapi.yaml` → `paths./attack-reports/stats/oasis/spawn-composition`

---

## EP-TD — Estadísticas de animales por frecuencia de farmeo, por tipo de oasis (v3)

**`GET /attack-reports/stats/oasis/temporal-distribution`**

### Descripción de negocio

Responde a la pregunta: "Si ataco cada 4 horas, ¿cuántos lobos suelen aparecer en los oasis de madera, y cuántas ratas en los de hierro?". El usuario elige UNA frecuencia de farmeo discreta (`interval_minutes`) y recibe las estadísticas de la ventana de gaps **agrupadas en 5 secciones fijas por tipo de oasis inferido**: hierro, arcilla, madera, cereal y sin clasificar.

El tipo de oasis **no está almacenado** en la BD: se infiere en tiempo de consulta usando similitud de Jaccard sobre los animales observados con `present > 0` (misma lógica que EP-SPAWN: `infer_type` + `OASIS_TYPE_SETS`). Un oasis de hierro respawna principalmente ratas, arañas y murciélagos ({1,2,4}); uno de madera, jabalíes, lobos y osos ({5,6,7}); cereal es el set universal {1..10} — Jaccard evita que eclipse a los demás tipos.

Los oasis con menos de 3 observaciones (confidence="low") se incluyen en su sección con la marca `n_oasis_low_confidence` para que el frontend pueda mostrar un disclaimer. Los oasis donde todos los reportes son derrota (sin ningún `present > 0`) van a "sin_clasificar".

Las **5 secciones se devuelven siempre**, aunque estén vacías. Esto garantiza estructura predecible al frontend. `n_reports_in_window` (raíz) es la suma de `n_reports_in_section` de las 5 secciones.

El gap de un reporte se calcula como la diferencia en segundos entre `attacked_at` del reporte actual y el `attacked_at` del reporte inmediatamente anterior **al mismo oasis** (LAG con `PARTITION BY coord_x_dest, coord_y_dest`). Binning por umbral inferior (Opción B): la frecuencia `F` corresponde a la ventana `[F*60, F_next*60)` segundos. El bin `300` es abierto `[18000, ∞)`. Gaps < 360 s (< 6 min) se descartan silenciosamente.

Los nombres de animal se devuelven **localizados** en el idioma solicitado por `Accept-Language`.

### Parámetros

| Parámetro | Tipo | Obligatorio | Default | Validación |
|-----------|------|-------------|---------|-----------|
| `interval_minutes` (query) | integer | No | `240` | Valores exactos: `6\|7\|10\|15\|30\|60\|120\|180\|240\|300`. Otro entero → `400` (detail lista los 10 valores). No entero → `422`. Ausente → `200` con default `240`. |
| `Accept-Language` (header) | string | Sí | — | 25 códigos de `SUPPORTED_LANGUAGES`. Ausente o código inválido → `400`. |

### Tabla completa de valores válidos

| `interval_minutes` | `interval_label` | Ventana (`lower_min`-`upper_min`) | `is_open` |
|--------------------|------------------|-----------------------------------|-----------|
| `6`   | `"6 min"`  | 6 – 7      | false |
| `7`   | `"7 min"`  | 7 – 10     | false |
| `10`  | `"10 min"` | 10 – 15    | false |
| `15`  | `"15 min"` | 15 – 30    | false |
| `30`  | `"30 min"` | 30 – 60    | false |
| `60`  | `"1h"`     | 60 – 120   | false |
| `120` | `"2h"`     | 120 – 180  | false |
| `180` | `"3h"`     | 180 – 240  | false |
| `240` | `"4h"`     | 240 – 300  | false — **default** |
| `300` | `"5h+"`    | 300 – ∞    | true  |

Frontera: **inclusiva por abajo, exclusiva por arriba** `[F, F_next)`. Un gap de exactamente `F` minutos pertenece al bin `F`, no al anterior.

### Tipos de oasis y sus etiquetas

| `oasis_type` (clave interna) | `oasis_type_label` (presentación) | Set de animales base |
|------------------------------|-----------------------------------|---------------------|
| `"hierro"` | `"Hierro"` | {1, 2, 4} — rata, araña, murciélago |
| `"arcilla"` | `"Barro"` | {1, 2, 5} — rata, araña, jabalí |
| `"madera"` | `"Madera"` | {5, 6, 7} — jabalí, lobo, oso |
| `"cereal"` | `"Cereal"` | {1..10} — set universal |
| `"sin_clasificar"` | `"Sin clasificar"` | Sin animales observados (solo derrotas) |

OJO: la clave interna `"arcilla"` tiene label `"Barro"` (terminología del usuario). El orden en `types[]` es siempre: hierro[0], arcilla[1], madera[2], cereal[3], sin_clasificar[4].

### Semántica de contadores

- `n_reports_in_window` (raíz): suma de `n_reports_in_section` de las 5 secciones. Total de ataques (report_ids) cuyo gap cae en la ventana. Incluye derrotas.
- `types[].n_oasis`: oasis distintos de ese tipo con al menos un gap en la ventana.
- `types[].n_oasis_low_confidence`: cuántos de esos oasis tienen < 3 observaciones (`confidence="low"`). Se incluyen en la sección (no en sin_clasificar), pero el frontend puede mostrar un aviso.
- `types[].n_reports_in_section`: gaps (report_ids) de oasis de ese tipo en la ventana. `0` si sección vacía.
- `types[].animals[].n_total`: gaps de oasis de ese tipo donde aparece ese animal (incluye derrotas). La suma de `n_total` de todos los animales de una sección puede superar `n_reports_in_section` porque un ataque puede tener varios tipos de animal.
- `types[].animals[].n_valid`: gaps con `present IS NOT NULL`. Son el denominador de `avg_present` y `mode_present`.

### Request

```
GET /attack-reports/stats/oasis/temporal-distribution?interval_minutes=240
Accept-Language: es
```

### Response 200 — con datos (hierro y arcilla poblados, resto vacíos)

```json
{
  "interval_minutes": 240,
  "interval_label": "4h",
  "window": { "lower_min": 240, "upper_min": 300, "is_open": false },
  "n_reports_in_window": 32,
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
        },
        {
          "animal_ordinal": 4,
          "animal_name": "Murciélago",
          "icon_url": "/static/icons/nature_4.png",
          "avg_present": 1.20,
          "mode_present": [1],
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
      "animals": [
        {
          "animal_ordinal": 1,
          "animal_name": "Rata",
          "icon_url": "/static/icons/nature_1.png",
          "avg_present": 3.10,
          "mode_present": [3],
          "n_total": 14,
          "n_valid": 12
        }
      ]
    },
    {
      "oasis_type": "madera",
      "oasis_type_label": "Madera",
      "n_oasis": 0,
      "n_oasis_low_confidence": 0,
      "n_reports_in_section": 0,
      "animals": []
    },
    {
      "oasis_type": "cereal",
      "oasis_type_label": "Cereal",
      "n_oasis": 0,
      "n_oasis_low_confidence": 0,
      "n_reports_in_section": 0,
      "animals": []
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

### Response 200 — ventana vacía (5 secciones vacías, no es error)

```json
{
  "interval_minutes": 6,
  "interval_label": "6 min",
  "window": { "lower_min": 6, "upper_min": 7, "is_open": false },
  "n_reports_in_window": 0,
  "types": [
    { "oasis_type": "hierro",        "oasis_type_label": "Hierro",          "n_oasis": 0, "n_oasis_low_confidence": 0, "n_reports_in_section": 0, "animals": [] },
    { "oasis_type": "arcilla",       "oasis_type_label": "Barro",           "n_oasis": 0, "n_oasis_low_confidence": 0, "n_reports_in_section": 0, "animals": [] },
    { "oasis_type": "madera",        "oasis_type_label": "Madera",          "n_oasis": 0, "n_oasis_low_confidence": 0, "n_reports_in_section": 0, "animals": [] },
    { "oasis_type": "cereal",        "oasis_type_label": "Cereal",          "n_oasis": 0, "n_oasis_low_confidence": 0, "n_reports_in_section": 0, "animals": [] },
    { "oasis_type": "sin_clasificar","oasis_type_label": "Sin clasificar",  "n_oasis": 0, "n_oasis_low_confidence": 0, "n_reports_in_section": 0, "animals": [] }
  ]
}
```

### Response 200 — bin abierto (`interval_minutes=300`)

```json
{
  "interval_minutes": 300,
  "interval_label": "5h+",
  "window": { "lower_min": 300, "upper_min": null, "is_open": true },
  "n_reports_in_window": 5,
  "types": [...]
}
```

### Campos del response

| Campo | Tipo | Nullable | Descripción |
|-------|------|----------|-------------|
| `interval_minutes` | integer | No | Eco del parámetro (240 si se usó el default) |
| `interval_label` | string | No | Etiqueta legible. Ver tabla de valores arriba |
| `window.lower_min` | integer | No | Límite inferior en minutos (inclusive) |
| `window.upper_min` | integer\|null | Sí | Límite superior en minutos (exclusive). `null` para `interval_minutes=300` |
| `window.is_open` | boolean | No | `true` solo para `interval_minutes=300` |
| `n_reports_in_window` | integer | No | Total de gaps en la ventana. Suma de `n_reports_in_section` de las 5 secciones |
| `types` | array[5] | No | Siempre 5 secciones en orden fijo: hierro, arcilla, madera, cereal, sin_clasificar |
| `types[].oasis_type` | string | No | Clave canónica: `"hierro"`, `"arcilla"`, `"madera"`, `"cereal"`, `"sin_clasificar"` |
| `types[].oasis_type_label` | string | No | Etiqueta fija: `"Hierro"`, `"Barro"`, `"Madera"`, `"Cereal"`, `"Sin clasificar"` |
| `types[].n_oasis` | integer | No | Oasis distintos de este tipo con al menos un gap en la ventana. `0` si vacío |
| `types[].n_oasis_low_confidence` | integer | No | Oasis con < 3 observaciones (`confidence="low"`). `0` si ninguno |
| `types[].n_reports_in_section` | integer | No | Gaps (report_ids) de oasis de este tipo en la ventana. `0` si vacío |
| `types[].animals` | array | No | Animales con `n_total > 0` en esta sección. `[]` si sección vacía. Orden: `animal_ordinal ASC` |
| `types[].animals[].animal_ordinal` | integer | No | Ordinal 1-10 (catálogo NATURE) |
| `types[].animals[].animal_name` | string | No | Nombre localizado (Accept-Language) con fallback a texto crudo de BD |
| `types[].animals[].icon_url` | string | No | `/static/icons/nature_{ordinal}.png` |
| `types[].animals[].avg_present` | float\|null | Sí | Media a 2 decimales. `null` si `n_valid=0` |
| `types[].animals[].mode_present` | array[int] | No | Moda(s) ASC. `[]` si `n_valid=0`. Empates: todos los valores empatados |
| `types[].animals[].n_total` | integer | No | Gaps de este tipo donde aparece este animal (incluye derrotas) |
| `types[].animals[].n_valid` | integer | No | Gaps con `present IS NOT NULL` en esta sección para este animal |

### Errores

| Código | Cuándo |
|--------|--------|
| `400` | `interval_minutes` no está en `{6,7,10,15,30,60,120,180,240,300}` — detail enumera los 10 valores válidos |
| `400` | `Accept-Language` ausente |
| `400` | `Accept-Language` con código no soportado (ej. `zh`) |
| `422` | `interval_minutes` no es entero (FastAPI automático, ej. `"cuatro"`) |
| `500` | Error inesperado de BD |

### Ejemplo curl

```bash
# Frecuencia default (4h), en español
curl "http://localhost:8000/attack-reports/stats/oasis/temporal-distribution" \
  -H "Accept-Language: es"

# Frecuencia 7 min, en inglés
curl "http://localhost:8000/attack-reports/stats/oasis/temporal-distribution?interval_minutes=7" \
  -H "Accept-Language: en"

# Bin abierto (5h+), en italiano
curl "http://localhost:8000/attack-reports/stats/oasis/temporal-distribution?interval_minutes=300" \
  -H "Accept-Language: it"

# interval_minutes fuera del set → 400
curl "http://localhost:8000/attack-reports/stats/oasis/temporal-distribution?interval_minutes=45" \
  -H "Accept-Language: es"
```

**Enlace OpenAPI:** `docs/api/openapi.yaml` → `paths./attack-reports/stats/oasis/temporal-distribution`

---

## EP-06 — Estadísticas de un oasis + balance de recursos

**`GET /attack-reports/stats/oasis`**

### Descripción de negocio

Devuelve toda la información conocida sobre un oasis concreto identificado por sus coordenadas `x` e `y`:

- Historial de aparición de animales por ataque (especie, presentes, muertos, supervivientes).
- Intervalos de repoblación entre ataques consecutivos, con estimación de animales regenerados.
- Tasas medias de regeneración por especie (animales/hora), calculadas a partir de los intervalos válidos.
- **Balance de recursos** del oasis: coste en recursos de las tropas atacantes muertas (campo `lost`), recursos robados al oasis —botín y objetos del héroe— (campo `stolen`) y neto resultante (`net = stolen.total.total − lost.total`).

El campo `balance` sigue **exactamente el mismo shape** que el endpoint `GET /attack-reports/stats/balance?x=…&y=…` filtrado por esas coordenadas. Ambos devolverán los mismos valores numéricos.

### Parámetros de query

| Parámetro | Tipo | Obligatorio | Descripción |
|-----------|------|-------------|-------------|
| `x` | integer | Sí | Coordenada X del oasis |
| `y` | integer | Sí | Coordenada Y del oasis |

### Cabeceras de respuesta

Sin `Accept-Language` (los datos son numéricos; `animal_name` es texto crudo del usuario).

### Response 200

```json
{
  "coord_x_dest": -59,
  "coord_y_dest": 25,
  "total_attacks": 1,
  "first_attack": "2026-05-15T08:30:00",
  "last_attack": "2026-05-15T08:30:00",
  "animal_appearances": [
    { "attacked_at": "2026-05-15T08:30:00", "animal_name": "Rat", "present": null, "killed": null, "survived": null }
  ],
  "repopulation_gaps": [
    { "attacked_at": "2026-05-15T08:30:00", "prev_attacked_at": null, "gap_seconds": null, "regenerated_animals": [] }
  ],
  "animal_regen_rates": [],
  "balance": {
    "range": { "from": "2026-05-15T08:30:00", "to": "2026-05-15T08:30:00" },
    "total_reports": 1,
    "reports_without_tribe": 0,
    "lost":   { "wood": 980, "clay": 1200, "iron": 830, "crop": 240, "total": 3250 },
    "stolen": {
      "bounty":         { "wood": 0,   "clay": 0,   "iron": 0,   "crop": 0,   "total": 0 },
      "hero_inventory": { "wood": 240, "clay": 240, "iron": 240, "crop": 240, "total": 960 },
      "total":          { "wood": 240, "clay": 240, "iron": 240, "crop": 240, "total": 960 }
    },
    "net": -2290
  }
}
```

Si no hay reportes → `total_attacks: 0`, `balance.total_reports: 0`, todos los totales a 0.

### Errores

| Código | Cuándo |
|--------|--------|
| `400` | Falta `x` o `y` (o solo uno de los dos) |

### Ejemplo curl

```bash
# Oasis en (-59, 25)
curl "http://localhost:8000/attack-reports/stats/oasis?x=-59&y=25"
```

**Enlace OpenAPI:** `docs/api/openapi.yaml` → `paths./attack-reports/stats/oasis`

---

---

## EP-N11 — Derivar selector CSS estructural

**Endpoint:** `POST /worlds/{world_id}/noise/derive-selector`

Analiza el outerHTML de un elemento HTML (obtenido con "Inspeccionar → Copiar outerHTML" en DevTools de Chrome) y devuelve el mejor selector CSS estructural según una heurística priorizada. Es el endpoint de preview del wizard de creación de rutas de ruido: el usuario pega el HTML, ve el selector recomendado, y lo acepta o sobreescribe antes de guardar la ruta.

No persiste nada. Opera solo sobre el fragmento HTML proporcionado.

**Auth:** ninguna.

**Headers requeridos:** `Content-Type: application/json`.

**Request body:**

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `outer_html` | string (min 1) | Sí | HTML completo del elemento. Máximo 50 KB. |

**Response OK (200):**
```json
{
  "selector": "a[href='/statistics']",
  "is_unique": true,
  "priority_level": 4,
  "method": "href_exact",
  "warning": null,
  "alternatives": []
}
```

Con aviso (is_unique=false):
```json
{
  "selector": "a.nav-link.statistics",
  "is_unique": false,
  "priority_level": 7,
  "method": "class_combo",
  "warning": "Selector basado en clases CSS. Puede no ser único en el documento real de Travian.",
  "alternatives": ["a.nav-link"]
}
```

**Errores:**

| Código | Cuándo |
|--------|--------|
| `422` | `outer_html` vacío, no parsea como HTML válido, o excede 50 KB |
| `404` | Mundo no encontrado |
| `500` | Error interno |

**Nota sobre `is_unique`:** el flag es heurístico. Indica que el selector es estructuralmente estable según la heurística sobre el fragmento proporcionado; no garantiza unicidad en el documento real de Travian. La verificación definitiva ocurre en runtime via `expected_url_after_click` (RN-NP05).

**Prioridad del algoritmo (RN-NP05):**

| Nivel | Método | Ejemplo |
|-------|--------|---------|
| 1 | `id` | `#statistics` |
| 2 | `name` | `input[name='username']` |
| 3 | `gid` | `a[href*='gid=2']` |
| 4 | `href_exact` | `a[href='/statistics']` |
| 5 | `href_partial` | `a[href*='/village/statistics']` |
| 6 | `data_attr` | `li[data-gid='2']` |
| 7 | `class_combo` | `a.nav-link.statistics` |
| 9 | `fallback` | `a` (sin atributos estructurales) |

**Ejemplo curl:**
```bash
curl -X POST http://localhost:8000/worlds/1/noise/derive-selector \
  -H "Content-Type: application/json" \
  -d '{"outer_html": "<a href=\"/statistics\" class=\"nav-link\">Estadísticas</a>"}'
```

**Enlace OpenAPI:** `docs/api/openapi.yaml` → `paths./worlds/{world_id}/noise/derive-selector`

---

## EP-N12 — Listar anclas semilla de ruido

**Endpoint:** `GET /worlds/{world_id}/noise/origins`

Devuelve las anclas semilla disponibles para usar como `origin` al crear rutas de ruido. Incluye:
- **9 anclas genéricas fijas**: constantes del sistema (DORF1, DORF2, MAP, STATISTICS, etc.). No se pueden borrar ni editar.
- **Anclas por-aldea dinámicas**: una por cada aldea en la tabla `villages` del mundo, construidas al vuelo. Si la tabla está vacía, `village_origins` es `[]` y `villages_loaded=false` — ejecutar EP-N13 para poblarla.

**Auth:** ninguna.

**Headers requeridos:** ninguno.

**Response OK (200):**
```json
{
  "generic_origins": [
    {"value": "DORF1",              "label": "Recursos (aldea activa)",      "path": "/dorf1.php"},
    {"value": "DORF2",              "label": "Edificios (aldea activa)",     "path": "/dorf2.php"},
    {"value": "MAP",                "label": "Mapa mundial",                  "path": "/karte.php"},
    {"value": "STATISTICS",         "label": "Estadísticas globales",         "path": "/statistics"},
    {"value": "REPORTS",            "label": "Reportes",                      "path": "/report"},
    {"value": "MESSAGES",           "label": "Mensajes",                      "path": "/messages"},
    {"value": "VILLAGE_STATISTICS", "label": "Estadísticas de aldea",         "path": "/village/statistics"},
    {"value": "OASIS_VIEW",         "label": "Vista oasis en el mapa",        "path": "/karte.php"},
    {"value": "ANY",                "label": "Cualquier página (sin ancla)",  "path": null}
  ],
  "village_origins": [
    {"value": "VILLAGE_12345", "label": "Merlinia", "data_id": 12345, "x": 42, "y": -17, "path": "/dorf1.php?newdid=12345"}
  ],
  "villages_loaded": true
}
```

Si `villages` está vacía: `village_origins: []`, `villages_loaded: false`.

**Errores:**

| Código | Cuándo |
|--------|--------|
| `404` | Mundo no encontrado |
| `500` | Error interno |

**Cache-Control:** `no-store` (village_origins cambia al ejecutar el parser).

**Ejemplo curl:**
```bash
curl http://localhost:8000/worlds/1/noise/origins
```

**Enlace OpenAPI:** `docs/api/openapi.yaml` → `paths./worlds/{world_id}/noise/origins`

---

## EP-N13 — Refrescar aldeas del village-switcher

**Endpoint:** `POST /worlds/{world_id}/noise/refresh-villages`

Instruye al WorldAgent del mundo a ejecutar el parser del village-switcher de Travian y actualizar la tabla `villages` con las aldeas propias del usuario. El parser lee el DOM de la página activa (sin clicks ni navegación) y hace UPSERT de las aldeas encontradas.

Úsalo cuando la pestaña de orígenes muestre `villages_loaded: false` o cuando el usuario haya conquistado/perdido aldeas desde el último login.

**Auth:** ninguna.

**Headers requeridos:** ninguno. Body vacío o `{}`.

**Requisito:** el WorldAgent del mundo debe estar activo (RUNNING). Si no hay sesión iniciada, usa primero el endpoint de login del mundo.

**Response OK (200):**
```json
{
  "villages_found": 3,
  "villages_data": [
    {"data_id": 12345, "name": "Merlinia", "x": 42, "y": -17},
    {"data_id": 12346, "name": "Forticia",  "x": 43, "y": -17},
    {"data_id": 12347, "name": "Minevia",   "x": 44, "y": -17}
  ]
}
```

`villages_found: 0` es válido (si el parser no encontró aldeas — ver EC-NP11).

**Errores:**

| Código | Cuándo |
|--------|--------|
| `409` | El WorldAgent está DISCONNECTED o no ha sido iniciado para este mundo |
| `404` | Mundo no encontrado |
| `500` | Error interno |

**Aldeas no se borran:** las aldeas que ya no aparecen en el sidebar no se eliminan de BD (anti-detección: el bot no reacciona en caliente ante pérdidas de aldea). La limpieza es manual.

**Ejemplo curl:**
```bash
curl -X POST http://localhost:8000/worlds/1/noise/refresh-villages \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Enlace OpenAPI:** `docs/api/openapi.yaml` → `paths./worlds/{world_id}/noise/refresh-villages`

---

## EP-N14 — Probar ruta de navegación en vivo

**Endpoint:** `POST /worlds/{world_id}/noise/paths/{path_id}/test`

Ejecuta la ruta de navegación indicada en el Chrome real del bot y devuelve un reporte paso a paso del resultado. Permite al usuario verificar que una ruta funciona (los selectores son correctos, el orden de los pasos es válido, la URL esperada coincide) antes de dejarla correr en producción.

**El test es no destructivo:** no modifica contadores de fallos (`consecutive_failures_count`), no marca la ruta como `is_dead`, no actualiza `last_used_at` y no ejecuta el dwell final. Cualquier fallo descubierto durante el test es solo informativo.

**Efecto secundario conocido:** el browser queda en la última página visitada durante el test (no se restaura la página original). Esto es intencionado — restaurar requeriría una navegación adicional que también podría fallar, y para un diagnóstico es aceptable.

**Concurrencia:** si el bot está ejecutando una ruta de ruido o un `refresh-villages` en ese momento, el test devuelve 409 ("browser ocupado"). No hay deadlock.

**Auth:** ninguna.

**Headers requeridos:** ninguno. Sin body.

**Requisito:** el WorldAgent del mundo debe estar RUNNING. Si no hay sesión → 409.

**Response OK (200) — ruta pasó:**
```json
{
  "overall": "ok",
  "aborted_at_step": null,
  "anchor_navigated_to": "https://ts1.travian.es/statistics",
  "steps": [
    {
      "step_order": 0,
      "action": "CLICK",
      "selector": "a[href='/statistics']",
      "status": "ok",
      "reason": null,
      "current_url": "https://ts1.travian.es/statistics"
    }
  ],
  "browser_note": "El browser queda en la última página visitada durante el test."
}
```

**Response OK (200) — ruta falló en el paso 1:**
```json
{
  "overall": "error",
  "aborted_at_step": 1,
  "anchor_navigated_to": "https://ts1.travian.es/statistics",
  "steps": [
    {"step_order": 0, "action": "CLICK", "selector": "a[href='/statistics']", "status": "ok", "reason": null, "current_url": "https://ts1.travian.es/statistics"},
    {"step_order": 1, "action": "CLICK", "selector": "a[href*='gid=2']", "status": "error", "reason": "elemento no encontrado en el DOM", "current_url": "https://ts1.travian.es/statistics"}
  ],
  "browser_note": "El browser queda en la última página visitada durante el test."
}
```

**IMPORTANTE:** el código HTTP es **200 en ambos casos** — el endpoint ejecutó correctamente su responsabilidad. El campo `overall` es el que indica si la ruta pasó o no. Este patrón es estándar para endpoints de diagnóstico/dry-run.

**Errores:**

| Código | Cuándo |
|--------|--------|
| `404` | Mundo no encontrado |
| `404` | Ruta no encontrada (o pertenece a otro mundo) |
| `409` | WorldAgent DISCONNECTED o no iniciado (inicia sesión primero) |
| `409` | Browser ocupado con otra tarea (ruido en ejecución o refresh-villages en curso) |
| `500` | Error interno (browser no disponible, servidor del mundo no accesible) |

**Ejemplo curl:**
```bash
# Probar la ruta 42 del mundo 1
curl -X POST http://localhost:8000/worlds/1/noise/paths/42/test
```

**Enlace OpenAPI:** `docs/api/openapi.yaml` → `paths./worlds/{world_id}/noise/paths/{path_id}/test`

---

🔖 Última revisión: 2026-06-02 (añadido EP-SPAWN spawn-composition con composición típica, peor combinación a batir, estado cooldown/respawn y atacantes por oasis; spec oasis-spawn-mechanics-stats.md v2.6; añadido EP-N14 probar ruta de navegación en vivo)
