# Referencia de APIs para agentes — TravianBot

## Convenciones globales

- **Base URL (desarrollo):** `http://localhost:8000`
- **Sin prefijo `/api`** — el proxy de Vite retira `/api` antes de redirigir a `:8000`.
  En producción la base URL es la misma (sin prefijo adicional).
- **Autenticación:** ninguno de los endpoints de `attack-reports` requiere auth.
- **Content-Type:** `application/json` en requests con body.
- **Accept-Language:** requerido en EP-TD (`/attack-reports/stats/oasis/temporal-distribution`)
  porque devuelve nombres de animal localizados. Los demás endpoints del router `attack-reports`
  no lo requieren (datos numéricos + texto crudo). Obligatorio también en endpoints de catálogo (`/catalog/*`).
- **EP-TD v3 (2026-06-02):** respuesta agrupada en 5 secciones fijas por tipo de oasis inferido (`types[]`); sustituye la lista plana `animals[]` de v2. `interval_minutes` sin cambios. Ver sección EP-TD abajo.

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

### EP-TD — Estadísticas de animales por frecuencia de farmeo, por tipo de oasis (v3)

**Endpoint:** `GET /attack-reports/stats/oasis/temporal-distribution` — El cliente elige UNA frecuencia de farmeo (`interval_minutes`) y recibe las estadísticas de aparición de animales agrupadas en **5 secciones fijas por tipo de oasis inferido** (hierro, arcilla, madera, cereal, sin_clasificar). Binning por umbral inferior: el bin F cubre gaps `[F*60, F_next*60)` segundos. El tipo de oasis se infiere por Jaccard (reutiliza `infer_type` de EP-SPAWN).

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
      "animals": [
        { "animal_ordinal": 1, "animal_name": "Rata", "icon_url": "/static/icons/nature_1.png",
          "avg_present": 2.50, "mode_present": [2], "n_total": 18, "n_valid": 15 }
      ]
    },
    {
      "oasis_type": "arcilla", "oasis_type_label": "Barro",
      "n_oasis": 2, "n_oasis_low_confidence": 0, "n_reports_in_section": 14,
      "animals": [...]
    },
    { "oasis_type": "madera",       "oasis_type_label": "Madera",        "n_oasis": 0, "n_oasis_low_confidence": 0, "n_reports_in_section": 0, "animals": [] },
    { "oasis_type": "cereal",       "oasis_type_label": "Cereal",        "n_oasis": 0, "n_oasis_low_confidence": 0, "n_reports_in_section": 0, "animals": [] },
    { "oasis_type": "sin_clasificar","oasis_type_label": "Sin clasificar","n_oasis": 1, "n_oasis_low_confidence": 0, "n_reports_in_section": 0, "animals": [] }
  ]
}
```

**Notas clave:**
- Las 5 secciones se devuelven **siempre** aunque estén vacías (`n_reports_in_section: 0`, `animals: []`).
- Orden fijo: `types[0]=hierro`, `types[1]=arcilla`, `types[2]=madera`, `types[3]=cereal`, `types[4]=sin_clasificar`.
- La clave interna `"arcilla"` tiene `oasis_type_label: "Barro"` (terminología del usuario).
- `n_reports_in_window` = suma de `n_reports_in_section` de las 5 secciones.
- Oasis con solo derrotas (sin `present > 0` nunca) → tipo `None` → `"sin_clasificar"`.
- Oasis con < 3 bursts observados (`confidence="low"`) → incluidos en su sección de tipo + `n_oasis_low_confidence` incremetado (no se mueven a `sin_clasificar`).
- La coherencia de `inferred_type` con EP-SPAWN está garantizada: ambos usan la misma `infer_type`.

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
