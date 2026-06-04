# Referencia de API — Ruido de Navegación (Noise)

Endpoints: `GET`, `PUT`, `POST`, `DELETE /worlds/{world_id}/noise/...`
Spec de referencia: [`docs/specs/noise-path-wizard.md`](../../docs/specs/noise-path-wizard.md)
Implementación: `adapters/api/routes/noise.py`

---

## Propósito

El sistema de ruido simula navegación humana en Travian: el bot visita URLs del servidor
del mundo de forma periódica y aleatoria para que su tráfico no se distinga del de un
usuario real. Los endpoints de este módulo permiten configurar qué páginas visitar (destinos),
cómo llegar a ellas (rutas con pasos de click), y desde qué página partir (anclas semilla).

---

## Convenciones de la feature

- **Sin `Accept-Language`**: ningún endpoint devuelve texto localizado.
- **Prefijo de ruta**: `/worlds/{world_id}/noise/...` (sin `/api`).
- **Verificación de mundo**: todos comprueban que `world_id` existe → `404` si no.
- **Cross-world 404**: si `dest_id` o `path_id` pertenece a otro mundo → `404` (no `403`).
- **Anti-detección (innegociable)**:
  - `delay_min_ms >= 300 ms` y `delay_max_ms <= 5000 ms` en todos los pasos.
  - Los selectores CSS no pueden usar `:contains()` ni `text()` (solo estructurales).
  - Las URLs deben pertenecer al servidor del mundo (no navegación externa).

---

## EP-N01 — `GET /worlds/{world_id}/noise/config`

Devuelve la configuración global de ruido del mundo. Si no existe, la crea con valores
por defecto (get_or_create). `Cache-Control: no-store`.

```
GET /worlds/1/noise/config
```

**Response 200:**
```json
{
  "world_id": 1,
  "noise_enabled": true,
  "hardcore_total_req_per_hour_min": 3,
  "hardcore_total_req_per_hour_max": 8,
  "passive_total_req_per_hour_min": 1,
  "passive_total_req_per_hour_max": 3,
  "dwell_min_seconds": 3.0,
  "dwell_max_seconds": 8.0
}
```

| Código | Condición |
|--------|-----------|
| `404` | `world_id` no existe |
| `500` | Error interno |

---

## EP-N02 — `PUT /worlds/{world_id}/noise/config`

PATCH parcial de la configuración de ruido. Solo actualiza los campos presentes.
Validación cruzada: `max >= min` para cada par.

```
PUT /worlds/1/noise/config
Content-Type: application/json

{"noise_enabled": true, "dwell_min_seconds": 3.0}
```

| Código | Condición |
|--------|-----------|
| `404` | `world_id` no existe |
| `422` | `max < min` en algún par; ningún campo enviado |
| `500` | Error interno |

---

## EP-N03 — `GET /worlds/{world_id}/noise/destinations`

Lista destinos con filtros. Paginación: `limit` (max 500) y `offset`.

Query params: `category`, `include_dead` (false), `include_unsafe` (false), `limit` (100), `offset` (0).

| Código | Condición |
|--------|-----------|
| `404` | `world_id` no existe |
| `500` | Error interno |

---

## EP-N04 — `POST /worlds/{world_id}/noise/destinations`

Crea un destino. URL absoluta (http/https) o relativa (`/...`). Dominio debe ser del servidor del mundo.

```
POST /worlds/1/noise/destinations
Content-Type: application/json

{"url_pattern": "/statistics", "label": "Estadísticas", "category": "STATISTICS"}
```

Campos opcionales: `frequency_weight` (default 1.0, > 0), `is_safe` (default true).

| Código | Condición |
|--------|-----------|
| `404` | `world_id` no existe |
| `422` | URL inválida; dominio incorrecto; campo fuera de rango |
| `500` | Error interno |

**Response 201:** destino creado.

---

## EP-N05 — `PUT /worlds/{world_id}/noise/destinations/{dest_id}`

PATCH parcial. Campos mutables: `label`, `frequency_weight`, `is_safe`.
`url_pattern` y `category` son inmutables.

| Código | Condición |
|--------|-----------|
| `404` | `world_id` no existe o `dest_id` no encontrado / de otro mundo |
| `422` | Ningún campo enviado |
| `500` | Error interno |

---

## EP-N06 — `DELETE /worlds/{world_id}/noise/destinations/{dest_id}`

Borra el destino en cascada con sus rutas y pasos.

| Código | Condición |
|--------|-----------|
| `404` | `world_id` no existe o destino no encontrado / de otro mundo |
| `500` | Error interno |

**Response 204:** sin body.

---

## EP-N07 — `GET /worlds/{world_id}/noise/destinations/{dest_id}/paths`

Lista rutas del destino con pasos ordenados por `step_order ASC`.

| Código | Condición |
|--------|-----------|
| `404` | `world_id` no existe o destino no encontrado / de otro mundo |
| `500` | Error interno |

---

## EP-N08 — `POST /worlds/{world_id}/noise/destinations/{dest_id}/paths`

Crea una ruta para el destino. `origin`: valor de `NavigationOrigin` (ej. `STATISTICS`, `ANY`)
o `VILLAGE_<data_id>` para anclas por-aldea.

Restricciones anti-detección: `delay_min_ms >= 300`, `delay_max_ms <= 5000`,
selectores no textuales.

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

| Código | Condición |
|--------|-----------|
| `404` | `world_id` no existe o destino no encontrado / de otro mundo |
| `422` | `origin` inválido; `steps` vacío; delay fuera de rango; selector textual |
| `500` | Error interno |

**Response 201:** ruta creada.

---

## EP-N09 — `PUT /worlds/{world_id}/noise/paths/{path_id}`

Actualización híbrida:
- `label`, `is_active`: PATCH parcial.
- `steps`: si presente (no null) → reemplazo atómico. `steps=[]` → `422`.

| Código | Condición |
|--------|-----------|
| `404` | `world_id` no existe o ruta no encontrada / de otro mundo |
| `422` | `steps=[]`; delay fuera de rango; selector textual |
| `500` | Error interno |

---

## EP-N10 — `DELETE /worlds/{world_id}/noise/paths/{path_id}`

Borra la ruta y sus pasos en cascada.

| Código | Condición |
|--------|-----------|
| `404` | `world_id` no existe o ruta no encontrada / de otro mundo |
| `500` | Error interno |

**Response 204:** sin body.

---

## EP-N11 a EP-N14

Ver `docs/api/API.md` para EP-N11 (derive-selector), EP-N12 (origins),
EP-N13 (refresh-villages) y EP-N14 (test en vivo de ruta).

---

🔖 Última revisión: 2026-06-04 (documento creado; cubre EP-N01..EP-N10; EP-N11..EP-N14 en docs/api/API.md)
