# Referencia de API — Sesión del bot (login / logout / estado)

Endpoints: `POST`, `DELETE` y `GET /accounts/{account_id}/worlds/{world_id}/session`
Spec de referencia: [`docs/specs/login-sesion-api.md`](../../docs/specs/login-sesion-api.md) (incluye Amendment A1)
Implementación: `adapters/api/routes/accounts.py`, `adapters/api/dependencies.py`, `adapters/api/main.py`
Documento de código: [`backend/sesion.md`](../backend/sesion.md)

---

## Convenciones de la feature de sesión

Los tres endpoints de sesión **no requieren `Accept-Language`**: operan sobre datos internos del bot (browsers en memoria, credenciales cifradas en BD), no sobre catálogos localizados. Son operativos, no de consulta de datos de Travian.

La jerarquía de URLs refleja el dominio: `session` es subrecurso de `worlds`, que es subrecurso de `accounts`. Los path params `account_id` y `world_id` se validan en todos los verbos mediante el helper `_verify_world_belongs_to_account`.

---

## Schema de respuesta compartido

Los endpoints `POST` y `GET` devuelven `SessionStatusResponse`:

```json
{
  "active": true,
  "world_id": 1,
  "account_id": 1
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `active` | `bool` | `true` si hay sesión activa para ese mundo; `false` si no la hay |
| `world_id` | `int` | El `world_id` tal como fue enviado en la URL |
| `account_id` | `int` | El `account_id` tal como fue enviado en la URL |

El `DELETE` devuelve `204 No Content` sin body.

---

## `POST /accounts/{account_id}/worlds/{world_id}/session`

Abre una sesión autenticada en Travian para la cuenta y mundo indicados.

### Request

```
POST /accounts/1/worlds/1/session
```

Sin body. Sin `Accept-Language`.

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `account_id` | Path int | Sí | ID de la cuenta en la BD |
| `world_id` | Path int | Sí | ID del mundo en la BD |

### Response 200 — login exitoso

```
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
X-Request-ID: <uuid>
X-API-Version: 0.1.0
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
```

```json
{
  "active": true,
  "world_id": 1,
  "account_id": 1
}
```

**Nota de tiempo**: la operación tarda entre 3 y 10 segundos por diseño (delays anti-detección en el proceso de login real). El cliente debe configurar un timeout de al menos 30 segundos. El endpoint es `async`; no bloquea el event loop de FastAPI durante la espera.

**Re-login silencioso**: si ya hay sesión activa para el mismo `world_id`, se cierra antes de abrir la nueva. No se devuelve `409`.

### Errores

| Código | Condición | Body |
|--------|-----------|------|
| `401` | Login fallido: credenciales incorrectas, timeout de Travian o excepción interna de zendriver | `{"detail": "Login fallido para 'usuario@ejemplo.com'"}` |
| `404` | `account_id` no existe en la BD | `{"detail": "Cuenta 99 no encontrada"}` |
| `404` | `world_id` no existe o no pertenece a `account_id` | `{"detail": "Mundo 99 no encontrado"}` |
| `503` | `SessionRegistry` no disponible (arranque incompleto) | `{"detail": "SessionRegistry no disponible — el servidor puede estar iniciándose."}` |
| `422` | `account_id` o `world_id` no son enteros válidos | Body estándar de FastAPI (Unprocessable Entity) |

**Nota sobre el `401`**: el error no distingue entre "credenciales incorrectas" y "error de red". Ambas situaciones producen el mismo `401`. Esto es intencional (RN-13 del spec): no revelar si las credenciales son correctas o no cuando el fallo puede ser de red.

**Nota sobre el `404` de mundo ajeno**: si `world_id` existe en la BD pero pertenece a otra cuenta, el error es igualmente `404` (no `403`). Así no se revela que el mundo existe en otra cuenta (RN-04).

**Causa frecuente de `401` sin abrir Chrome**: la clave `TRAVIAN_BOT_SECRET_KEY` ha cambiado desde que se guardó la contraseña. Ver sección "Gotcha operativo" más abajo.

---

## `DELETE /accounts/{account_id}/worlds/{world_id}/session`

Cierra la sesión activa del bot para el mundo indicado.

### Request

```
DELETE /accounts/1/worlds/1/session
```

Sin body. Sin `Accept-Language`.

### Response 204 — logout completado (o no había sesión)

```
HTTP/1.1 204 No Content
```

**Idempotente**: si no hay sesión activa para ese `world_id`, la operación finaliza con `204` igualmente. No hay error si no había sesión.

### Errores

| Código | Condición | Body |
|--------|-----------|------|
| `404` | `account_id` no existe en la BD | `{"detail": "Cuenta 99 no encontrada"}` |
| `404` | `world_id` no existe o no pertenece a `account_id` | `{"detail": "Mundo 99 no encontrado"}` |
| `503` | `SessionRegistry` no disponible | `{"detail": "SessionRegistry no disponible — el servidor puede estar iniciándose."}` |

---

## `GET /accounts/{account_id}/worlds/{world_id}/session`

Consulta si hay sesión activa del bot para el mundo indicado.

### Request

```
GET /accounts/1/worlds/1/session
```

Sin body. Sin `Accept-Language`.

### Response 200 — estado consultado

```
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
```

**Sesión activa**:
```json
{"active": true,  "world_id": 1, "account_id": 1}
```

**Sin sesión activa**:
```json
{"active": false, "world_id": 1, "account_id": 1}
```

El GET nunca devuelve error por ausencia de sesión. Siempre responde `200` (con `active: false` si no hay sesión).

### Errores

| Código | Condición | Body |
|--------|-----------|------|
| `404` | `account_id` no existe en la BD | `{"detail": "Cuenta 99 no encontrada"}` |
| `404` | `world_id` no existe o no pertenece a `account_id` | `{"detail": "Mundo 99 no encontrado"}` |
| `503` | `SessionRegistry` no disponible | `{"detail": "SessionRegistry no disponible — el servidor puede estar iniciándose."}` |

**Limitación conocida (EC-12 del spec)**: si Chrome muere inesperadamente después de un login exitoso, el GET sigue devolviendo `active: true`. El registry no detecta la muerte del proceso. La recuperación es hacer `DELETE` + `POST`.

---

## Mapa completo de códigos de error de la feature

| `error_code` | HTTP | Excepción | Condición |
|---|---|---|---|
| `LOGIN_FAILED` | `401` | `LoginFailedError` | Login fallido por cualquier causa (credenciales, red, zendriver, clave Fernet rotada) |
| `ACCOUNT_NOT_FOUND` | `404` | `AccountNotFoundError` | `account_id` no existe en la BD |
| `WORLD_NOT_FOUND` | `404` | `WorldNotFoundError` | `world_id` no existe en la BD o no pertenece a la cuenta |

Los mensajes de error `LOGIN_FAILED` están en `core/i18n/catalog/base/messages.json` con plantilla en `es` y `en`. El exception handler global los traduce según el `Accept-Language` de la request (con fallback a `es`).

---

## Gotcha operativo — clave Fernet estable

La contraseña de cada cuenta se guarda cifrada con `TRAVIAN_BOT_SECRET_KEY`. Si esta variable cambia (rotación de clave, reinstalación del servidor, cambio de máquina), todas las contraseñas guardadas quedan indescifrables.

**Síntoma**: `POST .../session` devuelve `401` aunque las credenciales sean correctas. Chrome no llega a abrirse. En los logs del servidor: `"InvalidToken al descifrar contraseña para account_id=X"`.

**Recuperación**: actualizar la contraseña de la cuenta afectada vía `PUT /accounts/{id}` con las credenciales en claro. El sistema las guardará cifradas con la clave actual.

**Prevención**: persistir `TRAVIAN_BOT_SECRET_KEY` en `~/.zshrc` (macOS/Linux) o como variable de entorno de sistema (Windows). No rotarla salvo causa mayor. Hacer copia de seguridad de la clave.

---

## Notas para el frontend

- El `POST` puede tardar hasta 10 s: mostrar spinner o indicador de carga antes de recibir respuesta.
- El cliente debe configurar un timeout HTTP de al menos 30 s para las llamadas al `POST`.
- El `GET /session` es la fuente de verdad del estado; consultarlo al iniciar el dashboard o tras un reinicio del servidor (las sesiones son in-memory y desaparecen con el servidor).
- Tras un `DELETE` exitoso (`204`), el `GET` devolverá `active: false`.
- No es necesario hacer `DELETE` antes de un nuevo `POST`; el re-login es silencioso.

---

🔖 Última revisión: 2026-05-26
