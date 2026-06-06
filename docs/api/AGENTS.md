# Referencia de APIs para agentes — TravianBot

## Convenciones globales

- **Base URL (desarrollo):** `http://localhost:8000`
- **Sin prefijo `/api`** — el proxy de Vite retira `/api` antes de redirigir a `:8000`.
  En producción la base URL es la misma (sin prefijo adicional).
- **Autenticación:** ninguno de los endpoints actuales requiere auth (bot personal de un solo usuario).
- **Content-Type:** `application/json` en requests con body.
- **Accept-Language:** requerido en EP-TD (`/attack-reports/stats/oasis/temporal-distribution`)
  porque devuelve nombres de animal localizados. Los demás endpoints del router `attack-reports`
  no lo requieren (datos numéricos + texto crudo). Obligatorio también en endpoints de catálogo (`/catalog/*`).
  Los endpoints de `session` y `noise` NO requieren `Accept-Language` (no devuelven texto localizado).
- **EP-TD v4 (2026-06-02):** respuesta agrupada en 5 secciones fijas por tipo de oasis inferido (`types[]`). v4 añade por sección: `oasis_coords`, `avg_bounty`, `total_animals`; por animal: `max_present`. Ver sección EP-TD abajo.

## Formato de error estándar

```json
{
  "detail": "<mensaje legible>"
}
```

FastAPI usa `detail` por defecto. Los endpoints de attack-reports no devuelven stack traces.

---

## Endpoints documentados

### EP-10 — Comparativa de tasas de reaparición por oasis

**Endpoint:** `GET /attack-reports/stats/oasis/comparison`
Devuelve la tasa bruta de reaparición de animales y la proyección del número acumulado
en el momento de la petición, para todos los oasis conocidos en BD.

**Auth:** ninguna.

**Headers requeridos:** ninguno.

**Request:** sin body, sin query params.

**Response OK (200):**
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

**Errores:**
- `500` → error inesperado de BD (detail genérico, sin stack trace).
- BD vacía → `200` con `oasis: []` y `species_columns: []` (no es un error).

**Reglas de negocio clave:**
- `species_columns`: unión de todas las especies con tasa en AL MENOS UN oasis. Orden por `animal_ordinal` ASC.
- `species[]` de cada oasis: solo especies con tasa válida. Si una especie no está, significa "—" (ausencia), NO cero.
- `projected_now = null` si `last_survived` es null (derrota en último reporte) o si `hours_since_last_attack < 0`.
- `projected_now = floor(last_survived + avg_regen_per_hour × hours_since_last_attack)`, mínimo 0.
- Oasis con `has_rates: true` aparecen antes; dentro del grupo, `last_attack DESC`.
- `last_attack` es hora local de Travian (naive, sin zona).
- `hours_since_last_attack` se calcula ajustando por `utc_offset` del último reporte; si es null, se asume UTC.

**Ejemplo:**
```bash
curl http://localhost:8000/attack-reports/stats/oasis/comparison
```

**Detalle:** `docs/api/openapi.yaml` → paths `/attack-reports/stats/oasis/comparison`

---

### EP-SPAWN — Composición de spawn, peor combinación a batir y estado cooldown/respawn por oasis

**Endpoint:** `GET /attack-reports/stats/oasis/spawn-composition`
Devuelve, para todos los oasis con reportes en BD, la composición típica de animales por especie,
la peor combinación defensiva para el intervalo de timer elegido, el tipo de oasis inferido y
el estado cooldown/respawn. El campo `attackers` permite agrupar en el frontend: Jugador → Aldea → Oasis.

**Auth:** ninguna.

**Headers requeridos:** ninguno (sin `Accept-Language` — datos numéricos; nombres de animal los resuelve el frontend con el ordinal vía i18n).

**Request:** sin body.

| Parámetro (query) | Tipo | Req | Valores válidos |
|-------------------|------|-----|-----------------|
| `timer_min` | integer | Sí | `6, 7, 10, 15` |

**Response OK (200):**
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

`oasis: []` si BD vacía. Oasis con tipo inferido van antes; dentro del grupo, `last_attack DESC`.

**Errores:**
- `400` → `timer_min` no está en `{6, 7, 10, 15}` · detail legible con el valor recibido
- `422` → `timer_min` ausente o tipo no entero (FastAPI automático)
- `500` → error inesperado de BD (detail genérico, sin stack trace)

**Campos clave:**
- `inferred_type`: `"hierro"` | `"arcilla"` | `"madera"` | `"cereal"` | `null`
- `confidence`: `"low"` (<3 reportes con `present>0`) | `"medium"` (≥3) | `null` (sin tipo)
- `spawn_status`: `"respawning"` | `"cooldown"` | `"unknown"`
- `attackers`: lista DISTINCT de pares `{player, village}`, ordenada A-Z. Nunca vacía.
- `species[].worst_case_count`: `null` si `inferred_type=null` o la especie es anomalía
- `worst_case_summary`: `null` si `inferred_type=null`

**Ejemplo:**
```bash
curl "http://localhost:8000/attack-reports/stats/oasis/spawn-composition?timer_min=6"
```

**Detalle:** `docs/api/openapi.yaml` → `paths./attack-reports/stats/oasis/spawn-composition`

---

### EP-TD — Estadísticas de animales por frecuencia de farmeo, por tipo de oasis (v4)

**Endpoint:** `GET /attack-reports/stats/oasis/temporal-distribution` — El cliente elige UNA frecuencia de farmeo (`interval_minutes`) y recibe las estadísticas de aparición de animales agrupadas en **5 secciones fijas por tipo de oasis inferido** (hierro, arcilla, madera, cereal, sin_clasificar). Binning por umbral inferior: el bin F cubre gaps `[F*60, F_next*60)` segundos. El tipo de oasis se infiere por Jaccard (reutiliza `infer_type` de EP-SPAWN). v4 añade por sección: `oasis_coords`, `avg_bounty`, `total_animals`; por animal: `max_present`.

**Auth:** ninguna.

**Headers requeridos:** `Accept-Language: <código>` (25 idiomas soportados en `SUPPORTED_LANGUAGES`).

**Request:** sin body.

| Parámetro (query) | Tipo | Req | Default | Valores válidos |
|-------------------|------|-----|---------|-----------------|
| `interval_minutes` | integer | No | `240` | `6, 7, 10, 15, 30, 60, 120, 180, 240, 300` |

**Tabla rápida de bins:**
`6→[6,7)` · `7→[7,10)` · `10→[10,15)` · `15→[15,30)` · `30→[30,60)` · `60→[60,120)` · `120→[120,180)` · `180→[180,240)` · `240→[240,300)` · `300→[300,∞)` (abierto, `is_open=true`). Unidades en minutos.

**Response OK (200):** — 5 secciones siempre presentes, algunas pueden estar vacías.
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
      "oasis_coords": [{"x": -15, "y": 23}, {"x": -12, "y": 28}, {"x": -8, "y": 31}],
      "avg_bounty": {"wood": 45, "clay": 12, "iron": 318, "crop": 22, "total": 397},
      "total_animals": {"avg": 12.50, "mode": [10, 12], "max": 24, "n_valid": 15, "n_total": 18},
      "animals": [
        { "animal_ordinal": 1, "animal_name": "Rata", "icon_url": "/static/icons/nature_1.png",
          "avg_present": 2.50, "mode_present": [2], "max_present": 6, "n_total": 18, "n_valid": 15 }
      ]
    },
    {
      "oasis_type": "arcilla", "oasis_type_label": "Barro",
      "n_oasis": 2, "n_oasis_low_confidence": 0, "n_reports_in_section": 14,
      "oasis_coords": [{"x": 5, "y": -8}, {"x": 10, "y": 2}],
      "avg_bounty": {"wood": 30, "clay": 205, "iron": 18, "crop": 10, "total": 263},
      "total_animals": {"avg": 8.00, "mode": [8], "max": 14, "n_valid": 12, "n_total": 14},
      "animals": [...]
    },
    { "oasis_type": "madera",       "oasis_type_label": "Madera",        "n_oasis": 0, "n_oasis_low_confidence": 0, "n_reports_in_section": 0, "oasis_coords": [], "avg_bounty": {"wood":0,"clay":0,"iron":0,"crop":0,"total":0}, "total_animals": {"avg":null,"mode":[],"max":null,"n_valid":0,"n_total":0}, "animals": [] },
    { "oasis_type": "cereal",       "oasis_type_label": "Cereal",        "n_oasis": 0, "n_oasis_low_confidence": 0, "n_reports_in_section": 0, "oasis_coords": [], "avg_bounty": {"wood":0,"clay":0,"iron":0,"crop":0,"total":0}, "total_animals": {"avg":null,"mode":[],"max":null,"n_valid":0,"n_total":0}, "animals": [] },
    { "oasis_type": "sin_clasificar","oasis_type_label": "Sin clasificar","n_oasis": 1, "n_oasis_low_confidence": 0, "n_reports_in_section": 3,  "oasis_coords": [{"x":-5,"y":10}], "avg_bounty": {"wood":0,"clay":0,"iron":0,"crop":0,"total":0}, "total_animals": {"avg":null,"mode":[],"max":null,"n_valid":0,"n_total":3}, "animals": [] }
  ]
}
```

**Notas clave:**
- Las 5 secciones se devuelven **siempre** aunque estén vacías (`n_reports_in_section: 0`, `animals: []`, `oasis_coords: []`).
- Orden fijo: `types[0]=hierro`, `types[1]=arcilla`, `types[2]=madera`, `types[3]=cereal`, `types[4]=sin_clasificar`.
- La clave interna `"arcilla"` tiene `oasis_type_label: "Barro"` (terminología del usuario).
- `n_reports_in_window` = suma de `n_reports_in_section` de las 5 secciones.
- Oasis con solo derrotas (sin `present > 0` nunca) → tipo `None` → `"sin_clasificar"`.
- Oasis con < 3 bursts observados (`confidence="low"`) → incluidos en su sección de tipo + `n_oasis_low_confidence` incrementado (no se mueven a `sin_clasificar`).
- La coherencia de `inferred_type` con EP-SPAWN está garantizada: ambos usan la misma `infer_type`.
- **[v4] `oasis_coords`**: coordenadas de los oasis con datos en la sección. Orden `y ASC, x ASC`. `[]` si vacío. Enteros crudos — el frontend formatea `(-15|23)`.
- **[v4] `avg_bounty`**: denominador = `n_reports_in_section` (incluye derrotas con `bounty=0`). `avg_bounty.total` ≠ suma de `wood+clay+iron+crop` (redondeo independiente, puede diferir en ±1).
- **[v4] `total_animals`**: regla todo-o-nada — reporte excluido de `n_valid` si cualquier animal tiene `present=NULL`. `n_total` = `n_reports_in_section`.
- **[v4] `max_present`**: por animal, `null` si `n_valid=0`. Misma regla que `avg_present`.

**Errores:**
- `400` → `interval_minutes` no en `{6,7,10,15,30,60,120,180,240,300}` (detail lista los 10 valores) · `Accept-Language` ausente · idioma no soportado
- `422` → `interval_minutes` no es entero (FastAPI automático)
- `500` → error inesperado de BD

**Ejemplo:**
```bash
# Default 4h, en español
curl "http://localhost:8000/attack-reports/stats/oasis/temporal-distribution" \
  -H "Accept-Language: es"

# Frecuencia 7 min, en inglés
curl "http://localhost:8000/attack-reports/stats/oasis/temporal-distribution?interval_minutes=7" \
  -H "Accept-Language: en"
```

**Detalle:** `docs/api/openapi.yaml` → `paths./attack-reports/stats/oasis/temporal-distribution`

---

### EP-06 — Estadísticas de un oasis + balance de recursos

**Endpoint:** `GET /attack-reports/stats/oasis`
Devuelve historial de animales, intervalos de repoblación, tasas de regeneración y **balance de recursos** (bajas + botín + neto) del oasis identificado por `x` e `y`.

**Auth:** ninguna

**Headers requeridos:** ninguno

**Request:** parámetros de query

| Parámetro | Tipo | Obligatorio |
|-----------|------|-------------|
| `x` | integer | Sí |
| `y` | integer | Sí |

**Response OK:** `200`
```json
{
  "coord_x_dest": -59, "coord_y_dest": 25,
  "total_attacks": 1,
  "first_attack": "2026-05-15T08:30:00", "last_attack": "2026-05-15T08:30:00",
  "animal_appearances": [...],
  "repopulation_gaps": [...],
  "animal_regen_rates": [...],
  "balance": {
    "range": { "from": "...", "to": "..." },
    "total_reports": 1,
    "reports_without_tribe": 0,
    "lost":   { "wood": 980, "clay": 1200, "iron": 830, "crop": 240, "total": 3250 },
    "stolen": {
      "bounty":         { "wood": 0, "clay": 0, "iron": 0, "crop": 0, "total": 0 },
      "hero_inventory": { "wood": 240, "clay": 240, "iron": 240, "crop": 240, "total": 960 },
      "total":          { "wood": 240, "clay": 240, "iron": 240, "crop": 240, "total": 960 }
    },
    "net": -2290
  }
}
```
Sin reportes → `total_attacks: 0`, `balance` con todos los valores a 0.

**Errores:**
- `400` → falta `x` o `y`

**Ejemplo:**
```bash
curl "http://localhost:8000/attack-reports/stats/oasis?x=-59&y=25"
```

**Detalle:** `docs/api/openapi.yaml` → paths `/attack-reports/stats/oasis`

---

---

### EP-09 — Estadísticas globales de todos los oasis

**Endpoint:** `GET /attack-reports/stats/global`
Agrega estadísticas de aparición de animales y tasas de regeneración para todos los oasis conocidos.

**Auth:** ninguna.

**Headers requeridos:** ninguno.

**Request:** sin body, sin query params.

**Response OK (200):**
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

**Semántica de `eligible_reports`:**
Denominador del % de aparición por especie. Es el número de reportes que pertenecen a oasis donde esa especie ha aparecido alguna vez (`present > 0` en algún reporte del oasis). Invariante garantizado: `eligible_reports >= appearances`. El frontend calcula el porcentaje como `Math.round(appearances / eligible_reports * 100)`.

**Errores:**
- `500` → error inesperado de BD (detail genérico, sin stack trace).
- BD vacía → `200` con `animal_appearances: []` y `animal_regen_rates: []` (no es un error).

**Ejemplo:**
```bash
curl http://localhost:8000/attack-reports/stats/global
```

**Detalle:** `docs/api/openapi.yaml` → paths `/attack-reports/stats/global`

---

> Para el contrato de otros endpoints (EP-01..EP-05, EP-07, EP-08) ver los specs en `docs/specs/bd-ataques-oasis.md`
> y relacionados. Se documentarán aquí en futuras iteraciones del agente `desarrollador-apis`.

---

## EP-N11 — Derivar selector CSS estructural

**Endpoint:** `POST /worlds/{world_id}/noise/derive-selector` — Preview del selector para el wizard de rutas de ruido.

**Auth:** ninguna.

**Headers requeridos:** `Content-Type: application/json`.

**Request:**
```json
{ "outer_html": "<a href=\"/statistics\" class=\"nav-link\">Stats</a>" }
```
| Campo | Tipo | Req | Descripción |
|-------|------|-----|-------------|
| `outer_html` | string (min 1) | Sí | outerHTML del elemento. Máximo 50 KB. |

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

**Errores:**
- `404` → Mundo no encontrado
- `422` → outer_html vacío / no parsea como HTML / excede 50 KB
- `500` → Error interno

**Ejemplo:**
```bash
curl -X POST http://localhost:8000/worlds/1/noise/derive-selector \
  -H "Content-Type: application/json" \
  -d '{"outer_html": "<a id=\"stats\" href=\"/statistics\">Stats</a>"}'
```

**Detalle:** `docs/api/openapi.yaml` → paths `/worlds/{world_id}/noise/derive-selector`

---

## EP-N12 — Listar anclas semilla de ruido

**Endpoint:** `GET /worlds/{world_id}/noise/origins` — Lista de orígenes disponibles para crear rutas de ruido. Incluye 9 genéricos fijos + anclas por-aldea desde la tabla `villages`.

**Auth:** ninguna.

**Headers requeridos:** ninguno.

**Request:** sin body, sin query params.

**Response OK (200):**
```json
{
  "generic_origins": [
    {"value": "DORF1", "label": "Recursos (aldea activa)", "path": "/dorf1.php"},
    {"value": "ANY",   "label": "Cualquier página (sin ancla)", "path": null}
  ],
  "village_origins": [
    {"value": "VILLAGE_12345", "label": "Merlinia", "data_id": 12345, "x": 42, "y": -17, "path": "/dorf1.php?newdid=12345"}
  ],
  "villages_loaded": true
}
```
Si `villages` está vacía: `village_origins: []`, `villages_loaded: false`. Ejecutar EP-N13 para poblar.

**Errores:**
- `404` → Mundo no encontrado
- `500` → Error interno

**Ejemplo:**
```bash
curl http://localhost:8000/worlds/1/noise/origins
```

**Detalle:** `docs/api/openapi.yaml` → paths `/worlds/{world_id}/noise/origins`

---

## EP-N13 — Refrescar aldeas del village-switcher

**Endpoint:** `POST /worlds/{world_id}/noise/refresh-villages` — Ejecuta el parser del village-switcher de Travian y actualiza la tabla `villages` del mundo.

**Auth:** ninguna.

**Headers requeridos:** ninguno. Body vacío o `{}`.

**Requisito:** el WorldAgent del mundo debe estar RUNNING (sesión activa). Si no → 409.

**Request:** body vacío o `{}`.

**Response OK (200):**
```json
{
  "villages_found": 2,
  "villages_data": [
    {"data_id": 12345, "name": "Merlinia", "x": 42, "y": -17},
    {"data_id": 12346, "name": "Forticia",  "x": 43, "y": -17}
  ]
}
```

**Errores:**
- `409` → WorldAgent DISCONNECTED o no iniciado (inicia sesión primero)
- `404` → Mundo no encontrado
- `500` → Error interno

**Ejemplo:**
```bash
curl -X POST http://localhost:8000/worlds/1/noise/refresh-villages \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Detalle:** `docs/api/openapi.yaml` → paths `/worlds/{world_id}/noise/refresh-villages`

---

## EP-N14 — Probar ruta de navegación en vivo

**Endpoint:** `POST /worlds/{world_id}/noise/paths/{path_id}/test` — Ejecuta la ruta de navegación indicada en el Chrome real del bot y devuelve un reporte paso a paso del resultado. Permite al usuario verificar que una ruta funciona antes de dejarla en producción.

**Auth:** ninguna.

**Headers requeridos:** ninguno. Sin body.

**Requisito:** el WorldAgent del mundo debe estar RUNNING (sesión activa). Si no → 409.
Si el browser está ocupado con otra tarea (ruido en ejecución, refresh-villages) → 409.

**Request:** sin body — la ruta a probar se identifica por `path_id` en la URL.

**Response OK (200):**
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

**IMPORTANTE:** HTTP 200 tanto si `overall="ok"` (todos los pasos pasaron) como si
`overall="error"` (algún paso falló). El fallo es semántico. El test no escribe nada en BD.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `overall` | `"ok"` \| `"error"` | Resultado global. |
| `aborted_at_step` | int \| null | `step_order` del paso que falló; null si ok. |
| `anchor_navigated_to` | string \| null | URL del ancla antes del primer paso; null si origin=="ANY". |
| `steps[].step_order` | int | Índice del paso. |
| `steps[].action` | string | Tipo de acción (CLICK, WAIT_FOR_SELECTOR, etc.). |
| `steps[].selector` | string | Selector CSS del paso. |
| `steps[].status` | `"ok"` \| `"error"` | Resultado del paso. |
| `steps[].reason` | string \| null | Motivo del fallo. null si ok. |
| `steps[].current_url` | string \| null | URL del tab tras el paso. null si no se pudo leer. |
| `browser_note` | string | Aviso fijo: "El browser queda en la última página visitada durante el test." |

**Errores:**
- `404` → Mundo no encontrado
- `404` → Ruta no encontrada (o pertenece a otro mundo)
- `409` → WorldAgent DISCONNECTED o no iniciado (inicia sesión primero)
- `409` → Browser ocupado con otra tarea (espera a que finalice)
- `500` → Error interno (browser no disponible, servidor del mundo no accesible)

**Ejemplo:**
```bash
# Probar la ruta con path_id=42 del mundo 1
curl -X POST http://localhost:8000/worlds/1/noise/paths/42/test
```

**Detalle:** `docs/api/openapi.yaml` → paths `/worlds/{world_id}/noise/paths/{path_id}/test`

---

## Human Sessions — EP-HS01 a EP-HS07

> Sin `Accept-Language`: no devuelven texto localizado.
> Todos verifican que `world_id` existe → `404` si no.

---

### EP-HS01 — Estado actual de la sesión

**Endpoint:** `GET /worlds/{world_id}/session`
Devuelve el modo activo, bloque en curso y tiempo hasta el próximo cambio de modo.

**Auth:** ninguna.

**Headers requeridos:** ninguno.

**Request:** sin body, sin query params.

**Response OK (200):**
```json
{
  "mode": "HARDCORE",
  "block": {"start": "08:00", "end": "11:00", "mode": "HARDCORE"},
  "jitter_minutes": 15,
  "next_block_ends_at": "2026-05-30T10:53:00Z",
  "seconds_to_next_block": 4692,
  "override": null
}
```
`override` es `null` si no hay override activo; si lo hay: `{"mode": "PASIVO", "expires_at": "..."}`.

**Errores:** `404` mundo no encontrado · `500` error interno.

**Ejemplo:**
```bash
curl http://localhost:8000/worlds/1/session
```

**Detalle:** `docs/api/openapi.yaml` → paths `/worlds/{world_id}/session`

---

### EP-HS02 — Timeline completo (7 días)

**Endpoint:** `GET /worlds/{world_id}/session/timeline`
Devuelve los 7 timelines (0=lunes..6=domingo). Los días no configurados devuelven `is_default: true`.

**Auth:** ninguna. **Headers requeridos:** ninguno. **Request:** sin body.

**Response OK (200):**
```json
{
  "timelines": [
    {"weekday": 0, "is_default": false, "jitter_minutes": 15,
     "blocks": [{"start": "00:00", "end": "09:00", "mode": "DISCONNECTED"},
                {"start": "09:00", "end": "18:00", "mode": "HARDCORE"},
                {"start": "18:00", "end": "24:00", "mode": "DISCONNECTED"}]},
    {"weekday": 1, "is_default": true, "jitter_minutes": 15,
     "blocks": [{"start": "00:00", "end": "24:00", "mode": "DISCONNECTED"}]}
  ]
}
```

**Errores:** `404` mundo · `500` error interno.

**Ejemplo:**
```bash
curl http://localhost:8000/worlds/1/session/timeline
```

**Detalle:** `docs/api/openapi.yaml` → paths `/worlds/{world_id}/session/timeline`

---

### EP-HS03 — Reemplazar timeline de un día

**Endpoint:** `PUT /worlds/{world_id}/session/timeline/{weekday}`
Reemplaza los bloques de un día. Huecos se rellenan con DISCONNECTED. Solapados → 422.

**Auth:** ninguna. **Headers requeridos:** `Content-Type: application/json`.

**Request:** `weekday` en path (0–6).
```json
{"jitter_minutes": 15, "blocks": [{"start": "09:00", "end": "18:00", "mode": "HARDCORE"}]}
```

**Response OK (200):** timeline completo tras guardar (con huecos rellenados).

**Errores:** `404` mundo · `422` solapado/weekday fuera de rango/hora inválida/mode desconocido · `500`.

**Ejemplo:**
```bash
curl -X PUT http://localhost:8000/worlds/1/session/timeline/0 \
  -H "Content-Type: application/json" \
  -d '{"jitter_minutes": 15, "blocks": [{"start": "09:00", "end": "18:00", "mode": "HARDCORE"}]}'
```

**Detalle:** `docs/api/openapi.yaml` → paths `/worlds/{world_id}/session/timeline/{weekday}`

---

### EP-HS04 — Override manual de modo

**Endpoint:** `PUT /worlds/{world_id}/session/mode`
Fuerza un modo hasta el próximo borde de bloque. Idempotente si ya está en ese modo.

**Auth:** ninguna. **Headers requeridos:** `Content-Type: application/json`.

**Request:**
```json
{"mode": "PASIVO"}
```

**Response OK (200):**
```json
{
  "mode": "PASIVO",
  "expires_at": "2026-05-30T11:08:00Z",
  "already_active": false,
  "requires_relogin": false,
  "chrome_action": "none",
  "message": "Override applied. Takes effect on the next WorldAgent cycle."
}
```
`chrome_action`: `"open"` (desde DISCONNECTED), `"close"` (hacia DISCONNECTED), `"none"` (sin cambio).

**Errores:** `404` mundo · `422` mode desconocido · `500`.

**Ejemplo:**
```bash
curl -X PUT http://localhost:8000/worlds/1/session/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "PASIVO"}'
```

**Detalle:** `docs/api/openapi.yaml` → paths `/worlds/{world_id}/session/mode`

---

### EP-HS05 — Cancelar override activo

**Endpoint:** `DELETE /worlds/{world_id}/session/override`
Borra el override de modo activo. Idempotente: 204 aunque no haya override.

**Auth:** ninguna. **Headers requeridos:** ninguno. **Request:** sin body.

**Response OK (204):** sin body.

**Errores:** `404` mundo · `500`.

**Ejemplo:**
```bash
curl -X DELETE http://localhost:8000/worlds/1/session/override
```

**Detalle:** `docs/api/openapi.yaml` → paths `/worlds/{world_id}/session/override`

---

### EP-HS06 — Leer configuración PASIVO

**Endpoint:** `GET /worlds/{world_id}/session/config`
Devuelve los parámetros del modo PASIVO. Defaults si nunca fue configurado.

**Auth:** ninguna. **Headers requeridos:** ninguno. **Request:** sin body.

**Response OK (200):**
```json
{"passive_interval_factor": 2.0, "passive_send_probability": 0.05}
```

**Errores:** `404` mundo · `500`.

**Ejemplo:**
```bash
curl http://localhost:8000/worlds/1/session/config
```

**Detalle:** `docs/api/openapi.yaml` → paths `/worlds/{world_id}/session/config`

---

### EP-HS07 — Actualizar configuración PASIVO (PATCH parcial)

**Endpoint:** `PUT /worlds/{world_id}/session/config`
Actualiza uno o ambos parámetros. Campos no enviados conservan su valor.

**Auth:** ninguna. **Headers requeridos:** `Content-Type: application/json`.

**Request:** al menos uno de los dos campos.
```json
{"passive_interval_factor": 3.0}
```

| Campo | Tipo | Rango |
|-------|------|-------|
| `passive_interval_factor` | float (opcional) | [1.5, 5.0] |
| `passive_send_probability` | float (opcional) | [0.01, 0.50] |

**Response OK (200):** configuración completa tras actualizar.

**Errores:** `404` mundo · `422` fuera de rango o ningún campo enviado · `500`.

**Ejemplo:**
```bash
curl -X PUT http://localhost:8000/worlds/1/session/config \
  -H "Content-Type: application/json" \
  -d '{"passive_interval_factor": 3.0}'
```

**Detalle:** `docs/api/openapi.yaml` → paths `/worlds/{world_id}/session/config`

---

## Noise (ruido de navegación) — EP-N01 a EP-N10

> Sin `Accept-Language`. Todos verifican `world_id` → `404` si no existe.
> Validación cross-world: si dest/path no pertenece al world → `404` (no `403`).
> Anti-detección: `delay_min_ms >= 300 ms`, `delay_max_ms <= 5000 ms`. Selectores sin `:contains()` ni `text()`.

---

### EP-N01 — Leer configuración de ruido

**Endpoint:** `GET /worlds/{world_id}/noise/config`
Devuelve la configuración de ruido del mundo. Si no existe la crea con defaults (get_or_create).

**v2 (noise-frequency-and-destination-weight.md):** los campos `*_req_per_hour_*` se reemplazaron
por campos de intervalo en segundos (`*_interval_*_seconds`). Los campos deprecated se conservan
en BD pero ya no aparecen en el contrato.

**Auth:** ninguna. **Headers requeridos:** ninguno. **Request:** sin body.

**Response OK (200):** `Cache-Control: no-store`
```json
{
  "world_id": 1,
  "noise_enabled": true,
  "hardcore_interval_min_seconds": 30,
  "hardcore_interval_max_seconds": 90,
  "passive_interval_min_seconds": 180,
  "passive_interval_max_seconds": 1200,
  "dwell_min_seconds": 2.0,
  "dwell_max_seconds": 30.0
}
```

**Errores:** `404` mundo · `500`.

**Ejemplo:**
```bash
curl http://localhost:8000/worlds/1/noise/config
```

**Detalle:** `docs/api/openapi.yaml` → paths `/worlds/{world_id}/noise/config`

---

### EP-N02 — Actualizar configuración de ruido (PATCH parcial)

**Endpoint:** `PUT /worlds/{world_id}/noise/config`
PATCH parcial. Solo actualiza los campos presentes. Validación cruzada: `max >= min` por par,
incluyendo cuando solo llega uno de los dos (se valida contra el valor actual de BD).

**Piso mínimo (guardian anti-detección):** cualquier campo de intervalo debe ser >= 30 s.
Valores < 30 s → `422`.

**Auth:** ninguna. **Headers requeridos:** `Content-Type: application/json`.

**Request:** al menos un campo.
```json
{
  "hardcore_interval_min_seconds": 300,
  "hardcore_interval_max_seconds": 440
}
```

| Campo | Tipo | Req | Constraint |
|-------|------|-----|-----------|
| `noise_enabled` | bool | No | — |
| `hardcore_interval_min_seconds` | int | No | >= 30 |
| `hardcore_interval_max_seconds` | int | No | >= 30, >= hc_min actual |
| `passive_interval_min_seconds` | int | No | >= 30 |
| `passive_interval_max_seconds` | int | No | >= 30, >= pa_min actual |
| `dwell_min_seconds` | float | No | >= 0 |
| `dwell_max_seconds` | float | No | >= dwell_min |

**Response OK (200):** configuración completa actualizada.

**Errores:** `404` mundo · `422` intervalo < 30, max < min o ningún campo · `500`.

**Ejemplo:**
```bash
curl -X PUT http://localhost:8000/worlds/1/noise/config \
  -H "Content-Type: application/json" \
  -d '{"hardcore_interval_min_seconds": 300, "hardcore_interval_max_seconds": 440}'
```

**Detalle:** `docs/api/openapi.yaml` → paths `/worlds/{world_id}/noise/config`

---

### EP-N03 — Listar destinos de ruido

**Endpoint:** `GET /worlds/{world_id}/noise/destinations`
Lista destinos con filtros opcionales. Paginación limit/offset.

**Auth:** ninguna. **Headers requeridos:** ninguno.

**Query params:**
| Parámetro | Tipo | Default |
|-----------|------|---------|
| `category` | string | — (todos) |
| `include_dead` | bool | `false` |
| `include_unsafe` | bool | `false` |
| `limit` | int [1,500] | `100` |
| `offset` | int ≥ 0 | `0` |

**Response OK (200):** array de `NoiseDestinationResponse`.

**Errores:** `404` mundo · `500`.

**Ejemplo:**
```bash
curl "http://localhost:8000/worlds/1/noise/destinations?include_dead=false&limit=50"
```

**Detalle:** `docs/api/openapi.yaml` → paths `/worlds/{world_id}/noise/destinations`

---

### EP-N04 — Crear destino de ruido

**Endpoint:** `POST /worlds/{world_id}/noise/destinations`
Crea un destino. URL: http/https o ruta relativa `/...`. Dominio debe ser del servidor del mundo.

**Auth:** ninguna. **Headers requeridos:** `Content-Type: application/json`.

**Request:**
```json
{"url_pattern": "/statistics", "label": "Estadísticas", "category": "STATISTICS", "navigation_weight": 1.0, "is_safe": true}
```

**v2:** `frequency_weight` se renombró a `navigation_weight` en el contrato (alias; la columna
de BD y la entidad interna siguen siendo `frequency_weight`). Rango: [0.1, 5.0] (guardian anti-detección).

| Campo | Tipo | Req | Constraint |
|-------|------|-----|-----------|
| `url_pattern` | string | Sí | http/https o ruta relativa, dominio del servidor |
| `label` | string | Sí | — |
| `category` | string (NoiseCategory) | Sí | — |
| `navigation_weight` | float | No (default 1.0) | 0.1 ≤ valor ≤ 5.0 |
| `is_safe` | bool | No (default true) | — |

**Response OK (201):** destino creado.

**Errores:** `404` mundo · `422` URL inválida o campo fuera de rango · `500`.

**Ejemplo:**
```bash
curl -X POST http://localhost:8000/worlds/1/noise/destinations \
  -H "Content-Type: application/json" \
  -d '{"url_pattern": "/statistics", "label": "Estadísticas", "category": "STATISTICS"}'
```

**Detalle:** `docs/api/openapi.yaml` → paths `/worlds/{world_id}/noise/destinations`

---

### EP-N05 — Actualizar destino de ruido (PATCH parcial)

**Endpoint:** `PUT /worlds/{world_id}/noise/destinations/{dest_id}`
PATCH parcial. Solo `label`, `navigation_weight`, `is_safe` son mutables. `url_pattern` y `category` son inmutables.

**Auth:** ninguna. **Headers requeridos:** `Content-Type: application/json`.

**Request:** al menos uno de los tres campos mutables.

**Response OK (200):** destino actualizado.

**Errores:** `404` mundo/destino (o de otro mundo) · `422` ningún campo · `500`.

**Ejemplo:**
```bash
curl -X PUT http://localhost:8000/worlds/1/noise/destinations/5 \
  -H "Content-Type: application/json" \
  -d '{"is_safe": false}'
```

**Detalle:** `docs/api/openapi.yaml` → paths `/worlds/{world_id}/noise/destinations/{dest_id}`

---

### EP-N06 — Borrar destino de ruido

**Endpoint:** `DELETE /worlds/{world_id}/noise/destinations/{dest_id}`
Borra el destino en cascada con sus rutas y pasos.

**Auth:** ninguna. **Request:** sin body.

**Response OK (204):** sin body.

**Errores:** `404` mundo/destino · `500`.

**Ejemplo:**
```bash
curl -X DELETE http://localhost:8000/worlds/1/noise/destinations/5
```

**Detalle:** `docs/api/openapi.yaml` → paths `/worlds/{world_id}/noise/destinations/{dest_id}`

---

### EP-N07 — Listar rutas de un destino

**Endpoint:** `GET /worlds/{world_id}/noise/destinations/{dest_id}/paths`
Lista las rutas del destino con sus pasos ordenados por `step_order ASC`.

**Auth:** ninguna. **Request:** sin body.

**Response OK (200):** array de `NavigationPathResponse`.

**Errores:** `404` mundo/destino · `500`.

**Ejemplo:**
```bash
curl http://localhost:8000/worlds/1/noise/destinations/5/paths
```

**Detalle:** `docs/api/openapi.yaml` → paths `/worlds/{world_id}/noise/destinations/{dest_id}/paths`

---

### EP-N08 — Crear ruta de navegación

**Endpoint:** `POST /worlds/{world_id}/noise/destinations/{dest_id}/paths`
Crea una ruta con pasos para el destino. `origin` es un valor de `NavigationOrigin` (ej. `STATISTICS`) o `VILLAGE_<data_id>`.

**Auth:** ninguna. **Headers requeridos:** `Content-Type: application/json`.

**Request:**
```json
{
  "origin": "STATISTICS",
  "label": "Ir a estadísticas",
  "steps": [
    {"step_order": 0, "action": "CLICK", "selector": "a[href='/statistics']",
     "delay_min_ms": 500, "delay_max_ms": 900, "expected_url_after_click": "/statistics"}
  ]
}
```

**Response OK (201):** ruta creada con pasos.

**Errores:** `404` mundo/destino · `422` origin inválido/steps vacío/delay fuera de rango/selector textual · `500`.

**Ejemplo:**
```bash
curl -X POST http://localhost:8000/worlds/1/noise/destinations/5/paths \
  -H "Content-Type: application/json" \
  -d '{"origin": "ANY", "label": "Navegar a stats", "steps": [{"step_order": 0, "action": "CLICK", "selector": "a[href*=\"statistics\"]", "delay_min_ms": 500, "delay_max_ms": 900}]}'
```

**Detalle:** `docs/api/openapi.yaml` → paths `/worlds/{world_id}/noise/destinations/{dest_id}/paths`

---

### EP-N09 — Actualizar ruta de navegación (PATCH + reemplazo de steps)

**Endpoint:** `PUT /worlds/{world_id}/noise/paths/{path_id}`
`label` e `is_active`: PATCH parcial. `steps`: si se envía → reemplazo atómico; si `null` → se conservan. `steps=[]` no permitido.

**Auth:** ninguna. **Headers requeridos:** `Content-Type: application/json`.

**Request:**
```json
{"is_active": false}
```

**Response OK (200):** ruta actualizada.

**Errores:** `404` mundo/ruta · `422` steps vacío/delay fuera de rango/selector textual · `500`.

**Ejemplo:**
```bash
curl -X PUT http://localhost:8000/worlds/1/noise/paths/42 \
  -H "Content-Type: application/json" \
  -d '{"is_active": false}'
```

**Detalle:** `docs/api/openapi.yaml` → paths `/worlds/{world_id}/noise/paths/{path_id}`

---

### EP-N10 — Borrar ruta de navegación

**Endpoint:** `DELETE /worlds/{world_id}/noise/paths/{path_id}`
Borra la ruta en cascada con sus pasos.

**Auth:** ninguna. **Request:** sin body.

**Response OK (204):** sin body.

**Errores:** `404` mundo/ruta · `500`.

**Ejemplo:**
```bash
curl -X DELETE http://localhost:8000/worlds/1/noise/paths/42
```

---

## Portal de Desarrollador de Rutas — EP-RT01..EP-RT12

> Sin `Accept-Language` en ningún EP-RT. Los labels/slugs son texto libre del desarrollador, no del catálogo de Travian.
> v2: `origin_template_id` (int|null) en todos los responses de plantilla; `navigation_weight` ELIMINADO de plantillas (vive en `NoiseDestination.frequency_weight` por-mundo).
> v2 GAP-4: selectores por texto visible (`:has-text(`, `:contains(`, `text()=`, `contains(text(),`) → 422.
> v3: EP-RT10 no requiere WorldAgent activo (ensure_session login on-demand idempotente). EP-RT12 nuevo.
> Colisiones: `conflicting_destination_id` va DENTRO del dict `detail` en 409 de EP-RT07 y EP-RT09.

### EP-RT01 — Listar plantillas

**Endpoint:** `GET /route-templates` — lista el catálogo maestro de plantillas globales.

**Auth:** ninguna. **Headers:** ninguno.

**Query params:** `category` (enum: MAP|OASIS_INFO|PLAYER_PROFILE|MESSAGES|REPORTS|BUILDING_VIEW|OTHER, opcional) · `include_paths` (bool, default false) · `limit` (int, default 100, [1,500]) · `offset` (int, default 0).

**Response OK (200):** lista de objetos `{id, slug, label, category, url_pattern, is_safe, origin_template_id, paths_count, paths?, created_at, updated_at}`. Sin `navigation_weight` (v2 rev.2).

**Errores:** `422` category inválida (FastAPI auto).

**Ejemplo:**
```bash
curl http://localhost:8000/route-templates?category=MAP&include_paths=true
```

---

### EP-RT02 — Crear plantilla

**Endpoint:** `POST /route-templates` — crea una nueva plantilla global.

**Auth:** ninguna. **Headers:** `Content-Type: application/json`.

**Request:** `{slug (kebab-case, UNIQUE), label, category, url_pattern, is_safe? (bool), origin_template_id? (int|null), paths? [...]}`. Sin `navigation_weight` (se fija al clonar a un mundo, no en la plantilla).

**Response OK (201):** objeto completo `{id, slug, label, category, url_pattern, is_safe, origin_template_id, paths, created_at, updated_at}`. Header `Location: /route-templates/{id}`.

**Errores:** `404` origen no encontrado · `409` slug duplicado / ciclo en origen · `422` slug no kebab-case / delay_min_ms < 200 ms / selector por texto visible.

**Ejemplo:**
```bash
curl -X POST http://localhost:8000/route-templates \
  -H "Content-Type: application/json" \
  -d '{"slug":"map-explore","label":"Explorar mapa","category":"MAP","url_pattern":"/karte.php"}'
```

---

### EP-RT03 — Obtener plantilla

**Endpoint:** `GET /route-templates/{id}` — devuelve la plantilla con paths+steps completos.

**Auth:** ninguna. **Request:** sin body.

**Response OK (200):** objeto completo con `origin_template_id` y `paths[{id, template_id, origin, label, is_active, steps[...]}]`. Sin `navigation_weight`.

**Errores:** `404` plantilla no encontrada.

---

### EP-RT04 — Actualizar plantilla (PATCH parcial)

**Endpoint:** `PUT /route-templates/{id}` — actualiza label, origin_template_id, is_safe o paths.

**Auth:** ninguna. **Headers:** `Content-Type: application/json`.

**Request (al menos un campo):** `{label?, origin_template_id?, is_safe?, paths?}`. `slug`, `category` y `url_pattern` son inmutables (422 si se incluyen). Sin `navigation_weight`.

**Response OK (200):** objeto completo actualizado con `origin_template_id`.

**Errores:** `404` plantilla/origen · `409` ciclo en origen / cadena demasiado profunda · `422` body vacío / campos inmutables / delay < 200 ms / selector por texto visible.

---

### EP-RT05 — Borrar plantilla

**Endpoint:** `DELETE /route-templates/{id}` — borra la plantilla; los destinos clonados quedan con `template_id=null`, las plantillas hijas quedan con `origin_template_id=null`.

**Auth:** ninguna. **Request:** sin body.

**Response OK (204):** sin body.

**Errores:** `404`.

---

### EP-RT06 — Listar paths de una plantilla

**Endpoint:** `GET /route-templates/{id}/paths` — lista los paths con steps de la plantilla.

**Auth:** ninguna. **Request:** sin body.

**Response OK (200):** lista `[{id, template_id, origin, label, is_active, steps[...]}]`.

**Errores:** `404` plantilla no encontrada.

---

### EP-RT07 — Clonar plantilla a un mundo

**Endpoint:** `POST /route-templates/{id}/clone-to-world/{world_id}` — clona la plantilla al mundo.

**Auth:** ninguna. **Headers:** `Content-Type: application/json` (body opcional). **Query:** `force` (bool, default false).

**Request body (opcional):** `{navigation_weight?: float}` — peso de ruta en ESE mundo (default 1.0, rango [0.1, 5.0]). El peso viene del REQUEST, NO de la plantilla.

**Response OK (201):** `{result:"cloned", destination_id, world_id, template_id, url_pattern, navigation_weight}`. Header `Location`.

**Response OK (200):** `{result:"already_exists", destination_id, world_id, template_id}` — misma plantilla ya estaba clonada.

**Errores:** `404` plantilla/mundo · `409` `{"detail": {"message":"...", "conflicting_destination_id": N}}` URL conflictiva · `422` URL absoluta incompatible / navigation_weight fuera de rango.

**Ejemplo:**
```bash
curl -X POST http://localhost:8000/route-templates/1/clone-to-world/3 \
  -H "Content-Type: application/json" \
  -d '{"navigation_weight": 2.0}'
curl -X POST "http://localhost:8000/route-templates/1/clone-to-world/3?force=true"
```

---

### EP-RT08 — Bulk clone (apply-templates)

**Endpoint:** `POST /worlds/{world_id}/noise/apply-templates` — clona en masa múltiples plantillas.

**Auth:** ninguna. **Headers:** `Content-Type: application/json`.

**Request:** `{template_ids: [1,2,3], force?: bool, default_navigation_weight?: float (default 1.0, [0.1,5.0])}`. `template_ids` no puede estar vacío. El peso se aplica uniformemente a todos los ítems.

**Response OK (200):** `{results: [{template_id, result:"cloned"|"already_exists"|"conflict", destination_id?, navigation_weight?, conflicting_destination_id?, error?}]}`. `navigation_weight` presente solo en ítems `"cloned"`. No es atómico.

**Errores:** `404` mundo · `422` `template_ids` vacío / `default_navigation_weight` fuera de rango.

**Ejemplo:**
```bash
curl -X POST http://localhost:8000/worlds/3/noise/apply-templates \
  -H "Content-Type: application/json" \
  -d '{"template_ids":[1,2,3],"default_navigation_weight":1.5}'
```

---

### EP-RT09 — Re-sincronizar instancia con la plantilla

**Endpoint:** `POST /route-templates/{id}/sync-to-world/{world_id}` — actualiza los paths/steps del destino clonado con los de la plantilla maestra. Preserva `navigation_weight` (frequency_weight), `is_dead`, `consecutive_failures_count` y `last_used_at`.

**Auth:** ninguna. **Request:** sin body.

**Response OK (200):** `{result:"synced", destination_id, paths_replaced}` — instancia existente actualizada.

**Response OK (201):** `{result:"created", destination_id}` — no había instancia, se creó. Header `Location`.

**Errores:** `404` plantilla/mundo · `409` `{"detail": {"message":"...", "conflicting_destination_id": N}}` URL ocupada por otra plantilla.

---

### EP-RT10 — Probar plantilla en vivo (v3)

**Endpoint:** `POST /route-templates/{id}/test` — ejecuta la plantilla en el Chrome real. v3: login on-demand idempotente (no requiere WorldAgent activo).

**Auth:** ninguna. **Headers:** `Content-Type: application/json`.

**Request:** `{world_id: int, path_index?: int (default 0)}`.

**Response OK (200):** `{overall:"ok"|"error", aborted_at_step, anchor_navigated_to, steps[{step_order, action, selector, status, reason, current_url}], browser_note}`. HTTP 200 aunque `overall="error"`.

**Errores:** `401` Fernet indescifrables / login fallido · `404` plantilla/mundo/sin cuenta asociada · `409 BROWSER_BUSY` browser ocupado con otra tarea · `409 COLD_START_ABORT` Chrome no está en página de Travian (detail incluye URL actual; llevar Chrome al mundo y reintentar) · `422` `path_index` fuera de rango · `500`.

**Nota v3:** si no hay sesión activa, se hace login automático. La sesión se mantiene entre tests (no se cierra). Para cerrarla usar EP-RT12.

**Ejemplo:**
```bash
curl -X POST http://localhost:8000/route-templates/1/test \
  -H "Content-Type: application/json" \
  -d '{"world_id": 3, "path_index": 0}'
```

---

### EP-RT11 — Cadena resuelta de pasos (v2 NUEVO)

**Endpoint:** `GET /route-templates/{id}/chain` — devuelve la cadena de pasos en orden de ejecución (raíz→hoja). Uso: mostrar en tabla los pasos heredados cuando se selecciona un origen.

**Auth:** ninguna. **Request:** sin body.

**Response OK (200):**
```json
{
  "template_id": 7,
  "template_slug": "top10-alianza-rivales",
  "depth": 3,
  "steps": [
    {"position": 0, "template_id": 1, "template_slug": "statistics", "label": "...", "selector": "a[href*='/statistics']", "expected_url": "/statistics", "delay_min_ms": 400, "delay_max_ms": 800, "is_root": true},
    {"position": 1, ...},
    {"position": 2, "is_root": false}
  ]
}
```
`depth` cuenta solo nodos con step definido. `steps` vacío si la plantilla no tiene paths/steps. `is_root: true` solo en el primer elemento.

**Errores:** `404` plantilla no encontrada · `409` ciclo/profundidad excesiva (defensivos — solo con datos corruptos en BD).

**Ejemplo:**
```bash
curl http://localhost:8000/route-templates/7/chain
```

---

### EP-RT12 — Cerrar sesión Chrome de un mundo (v3 NUEVO)

**Endpoint:** `DELETE /worlds/{world_id}/session` — cierra la sesión Chrome de un mundo. No requiere WorldAgent activo. Idempotente: si no hay sesión → 204 igualmente.

**Auth:** ninguna. **Request:** sin body.

**Response OK (204):** sin body.

**Errores:** `404` mundo no encontrado.

**Ejemplo:**
```bash
curl -X DELETE http://localhost:8000/worlds/3/session
```

---

### EP-N03/EP-N04 — Modificaciones retrocompatibles

**Delta EP-N03** (`GET /worlds/{id}/noise/destinations`): campo `template_id` (int|null) añadido al response de cada destino. `null` si creado a mano; `int` si fue clonado desde una plantilla.

**Delta EP-N04** (`POST /worlds/{id}/noise/destinations`): campo `template_id` (int|null, opcional, default null) añadido al request body para crear destinos con referencia explícita a una plantilla.

**Detalle:** `docs/api/openapi.yaml` → paths `/worlds/{world_id}/noise/paths/{path_id}`
