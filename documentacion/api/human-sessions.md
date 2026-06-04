# Referencia de API — Human Sessions (Timeline horario de actividad)

Endpoints: `GET`, `PUT`, `DELETE /worlds/{world_id}/session/...`
Spec de referencia: [`docs/specs/human-sessions.md`](../../docs/specs/human-sessions.md) (v2.2)
Implementación: `adapters/api/routes/session.py`

---

## Convenciones de la feature

- **Sin `Accept-Language`**: ninguno de estos endpoints devuelve texto localizado. Los valores de modo son enums (`HARDCORE`, `PASIVO`, `DISCONNECTED`) y los campos numéricos/temporales no requieren localización.
- **Prefijo de ruta**: `/worlds/{world_id}/session/...` (sin `/api` — el proxy de Vite lo retira).
- **Verificación de mundo**: todos los endpoints comprueban que `world_id` existe; si no → `404 "Mundo no encontrado."`.

---

## `GET /worlds/{world_id}/session` — Estado actual de la sesión

Devuelve el modo activo, el bloque en curso y el tiempo hasta el próximo cambio de modo.
Si hay un override activo, el campo `override` lo refleja; si no, es `null`.

```
GET /worlds/1/session
```

**Response 200:**
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

| Código | Condición |
|--------|-----------|
| `404` | `world_id` no existe |
| `500` | Error interno |

---

## `GET /worlds/{world_id}/session/timeline` — Timeline completo (7 días)

Devuelve los 7 timelines (weekday 0=lunes … 6=domingo). Los días sin configuración explícita
devuelven `is_default: true` con el timeline por defecto (24h DISCONNECTED).

```
GET /worlds/1/session/timeline
```

**Response 200:**
```json
{
  "timelines": [
    {
      "weekday": 0,
      "is_default": false,
      "jitter_minutes": 15,
      "blocks": [
        {"start": "00:00", "end": "09:00", "mode": "DISCONNECTED"},
        {"start": "09:00", "end": "18:00", "mode": "HARDCORE"},
        {"start": "18:00", "end": "24:00", "mode": "DISCONNECTED"}
      ]
    }
  ]
}
```

| Código | Condición |
|--------|-----------|
| `404` | `world_id` no existe |
| `500` | Error interno |

---

> **Nota:** no existe un endpoint de lectura por día (`GET .../session/timeline/{weekday}`).
> Para obtener un día concreto, el cliente filtra el array `timelines` de la respuesta de
> `GET /worlds/{world_id}/session/timeline` por el campo `weekday`. La escritura sí es por
> día (`PUT .../session/timeline/{weekday}`, abajo).

## `PUT /worlds/{world_id}/session/timeline/{weekday}` — Actualizar timeline de un día

Reemplaza los bloques de un día de la semana. Los huecos entre bloques se rellenan
automáticamente con `DISCONNECTED`. Los bloques que se solapan producen `422`.

```
PUT /worlds/1/session/timeline/0
Content-Type: application/json

{
  "jitter_minutes": 15,
  "blocks": [
    {"start": "09:00", "end": "18:00", "mode": "HARDCORE"}
  ]
}
```

**Response 200:** timeline completo tras guardar (con huecos rellenados).

| Código | Condición |
|--------|-----------|
| `404` | `world_id` no existe |
| `422` | Bloques solapados, `weekday` fuera de rango [0-6], formato de hora inválido, `mode` desconocido |
| `500` | Error interno |

---

## `PUT /worlds/{world_id}/session/mode` — Override manual de modo

Fuerza un modo hasta el próximo borde de bloque del calendario. Si el mundo ya está
en el modo solicitado, devuelve `already_active: true` sin escribir en BD.

```
PUT /worlds/1/session/mode
Content-Type: application/json

{"mode": "PASIVO"}
```

**Response 200:**
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

`chrome_action` puede ser `"open"` (transición desde DISCONNECTED), `"close"` (hacia DISCONNECTED) o `"none"` (sin cambio de Chrome).

| Código | Condición |
|--------|-----------|
| `404` | `world_id` no existe |
| `422` | `mode` no reconocido |
| `500` | Error interno |

---

## `DELETE /worlds/{world_id}/session/override` — Cancelar override activo

Borra el override de modo activo para el mundo. Tras la llamada, el WorldAgent recupera
el modo del calendario en su próximo ciclo.

**Idempotente:** si no hay override activo (porque expiró, nunca existió o ya fue cancelado),
responde igualmente `204`. Borrar sin override previo no es un error.

Añadido en v2.2 para dar soporte robusto al botón "Cancelar override" del frontend.
La capacidad de borrado ya existía en `SessionTimelineDbPort.clear_override` y en el
adaptador SQLite; este endpoint la expone a través de la API.

```bash
curl -X DELETE http://localhost:8000/worlds/1/session/override
```

**Response 204:** sin body.

| Código | Condición |
|--------|-----------|
| `404` | `world_id` no existe |
| `500` | Error interno |

---

## `GET /worlds/{world_id}/session/config` — Leer config PASIVO

Devuelve los parámetros de configuración del modo PASIVO. Si el mundo no tiene configuración
explícita, devuelve los defaults (`passive_interval_factor: 2.0`, `passive_send_probability: 0.05`).

```
GET /worlds/1/session/config
```

**Response 200:**
```json
{
  "passive_interval_factor": 2.0,
  "passive_send_probability": 0.05
}
```

| Código | Condición |
|--------|-----------|
| `404` | `world_id` no existe |
| `500` | Error interno |

---

## `PUT /worlds/{world_id}/session/config` — Actualizar config PASIVO

Actualiza uno o ambos parámetros del modo PASIVO. Semántica PATCH parcial: los campos no
enviados conservan su valor actual.

```
PUT /worlds/1/session/config
Content-Type: application/json

{"passive_interval_factor": 3.0}
```

**Response 200:** estado completo tras la actualización.

| Código | Condición |
|--------|-----------|
| `404` | `world_id` no existe |
| `422` | `passive_interval_factor` fuera de [1.5, 5.0]; `passive_send_probability` fuera de [0.01, 0.50]; ningún campo enviado |
| `500` | Error interno |

---

🔖 Última revisión: 2026-06-04 (corregida divergencia: eliminado de la doc el endpoint inexistente GET /session/timeline/{weekday}. La lectura es solo GET /session/timeline —los 7 días— y el cliente filtra por weekday; la escritura sí es por día con PUT. Verificado contra adapters/api/routes/session.py)
