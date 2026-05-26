# Referencia de API — Gestión de cuentas y mundos

Endpoints: 8 operaciones REST sobre `/accounts` y `/accounts/{id}/worlds`
Implementación: `adapters/api/routes/accounts.py`
Spec de referencia: [`docs/specs/registro-cuentas-mundos.md`](../../docs/specs/registro-cuentas-mundos.md)
Documento de negocio: [`../funcionalidades/cuentas-mundos.md`](../funcionalidades/cuentas-mundos.md)

---

## Convenciones de la feature de cuentas/mundos

Ningún endpoint de esta sección requiere `Accept-Language`: devuelven datos operativos (emails, URLs, tribus), no catálogo localizado. La validación de los campos del body es responsabilidad de Pydantic: un body inválido produce `422 Unprocessable Entity` automáticamente.

La **contraseña es write-only**: se envía en `POST /accounts` y en `PUT /accounts/{id}` (campo opcional), pero nunca aparece en ninguna respuesta. El campo `password` está ausente del schema `AccountResponse`.

La URL base no tiene prefijo `/api`. El proxy de Vite lo retira antes de redirigir a `:8000`.

---

## Schemas compartidos

### `AccountResponse`

```json
{
  "id": 1,
  "email": "jugador@ejemplo.com",
  "username": "MiCuenta",
  "worlds": [...],
  "created_at": "2026-05-25T10:00:00",
  "updated_at": "2026-05-25T10:00:00"
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | `int` | ID autoincremental en la BD |
| `email` | `str` | Email del lobby de Travian |
| `username` | `str` | Nombre de jugador |
| `worlds` | `list[WorldResponse]` | Lista de mundos de la cuenta (puede ser vacía) |
| `created_at` | `str` | ISO 8601, UTC |
| `updated_at` | `str` | ISO 8601, UTC |
| `password` | — | **Ausente siempre**. Write-only. |

### `WorldResponse`

```json
{
  "id": 1,
  "server": "https://ts1.x1.international.travian.com/",
  "tribe": "romans",
  "created_at": "2026-05-25T10:00:00"
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | `int` | ID autoincremental en la BD |
| `server` | `str` | URL completa del servidor Travian |
| `tribe` | `str` | Una de las 7 tribus jugables (ver más abajo) |
| `created_at` | `str` | ISO 8601, UTC |

### Tribus jugables (`PlayableTribe`)

`romans` · `teutons` · `gauls` · `egyptians` · `huns` · `spartans` · `vikings`

`nature` y `natars` son tribus NPC y son rechazadas con `422` en los endpoints de creación.

---

## `POST /accounts`

Registra una nueva cuenta de Travian. La contraseña se cifra con Fernet antes de persistir.

### Request

```
POST /accounts
Content-Type: application/json
```

```json
{
  "email": "jugador@ejemplo.com",
  "username": "MiCuenta",
  "password": "contraseñaReal"
}
```

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `email` | `string` (EmailStr) | Sí | Email válido; único en la BD |
| `username` | `string` | Sí | 1–100 caracteres |
| `password` | `string` | Sí | 1–200 caracteres; nunca se devuelve |

### Response 201

```
HTTP/1.1 201 Created
Content-Type: application/json
Location: /accounts/1
```

Body: `AccountResponse` (sin campo `password`).

### Errores

| Código | Condición |
|--------|-----------|
| `409` | Email ya registrado en otra cuenta (`ACCOUNT_EMAIL_TAKEN`) |
| `422` | Body inválido (email mal formado, campos vacíos o ausentes) |

---

## `GET /accounts`

Devuelve todas las cuentas registradas con sus mundos.

### Request

```
GET /accounts
```

Sin parámetros. Sin `Accept-Language`.

### Response 200

```json
{
  "accounts": [ ...AccountResponse... ]
}
```

El array puede estar vacío si no hay cuentas. La lista de mundos de cada cuenta puede estar vacía.

---

## `GET /accounts/{account_id}`

Devuelve una cuenta por su ID, incluyendo la lista completa de sus mundos.

### Request

```
GET /accounts/1
```

| Parámetro | Tipo | Requerido |
|-----------|------|-----------|
| `account_id` | Path int | Sí |

### Response 200

Body: `AccountResponse`.

### Errores

| Código | Condición |
|--------|-----------|
| `404` | Cuenta no encontrada (`ACCOUNT_NOT_FOUND`) |
| `422` | `account_id` no es un entero válido |

---

## `PUT /accounts/{account_id}`

Actualiza los campos editables de una cuenta. El campo `password` es opcional: si se omite (o es `null`), el cifrado almacenado no cambia.

### Request

```
PUT /accounts/1
Content-Type: application/json
```

```json
{
  "email": "nuevo@ejemplo.com",
  "username": "NuevoNombre",
  "password": "nuevaContraseña"
}
```

O sin cambio de contraseña:

```json
{
  "email": "nuevo@ejemplo.com",
  "username": "NuevoNombre"
}
```

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `email` | `string` (EmailStr) | Sí | Nuevo email; único en la BD |
| `username` | `string` | Sí | 1–100 caracteres |
| `password` | `string \| null` | No | Si se omite o es `null`, se conserva el cifrado existente |

### Response 200

Body: `AccountResponse` actualizado.

### Errores

| Código | Condición |
|--------|-----------|
| `404` | Cuenta no encontrada |
| `409` | Email ya usado por otra cuenta |
| `422` | Body inválido |

---

## `DELETE /accounts/{account_id}`

Elimina una cuenta y todos sus mundos y aldeas en cascada.

### Request

```
DELETE /accounts/1
```

Sin body.

### Response 204

```
HTTP/1.1 204 No Content
```

Sin body.

### Errores

| Código | Condición |
|--------|-----------|
| `404` | Cuenta no encontrada |
| `409` | Algún mundo de la cuenta tiene sesión activa en el bot. El `detail` indica cuál. Detener las sesiones antes de borrar. |

**Nota sobre el `409`**: el `DELETE /accounts` no llama directamente a `WorldRuntimePort.is_active()` en el handler; lo delega a `DeleteAccountUseCase`. Si `world_runtime_port` no está disponible en `app.state` (arranque incompleto), el use case lo trata como "sin sesión activa" y procede con el borrado (comportamiento defensivo, no lanza 503).

---

## `POST /accounts/{account_id}/worlds`

Añade un mundo (servidor Travian) a una cuenta existente.

### Request

```
POST /accounts/1/worlds
Content-Type: application/json
```

```json
{
  "server": "https://ts1.x1.international.travian.com/",
  "tribe": "romans"
}
```

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `server` | `string` (AnyHttpUrl) | Sí | URL completa del servidor. Protocolo `http://` o `https://` obligatorio |
| `tribe` | `string` (PlayableTribe) | Sí | Una de las 7 tribus jugables |

### Response 201

```
HTTP/1.1 201 Created
Location: /accounts/1/worlds/1
```

Body: `WorldResponse`.

### Errores

| Código | Condición |
|--------|-----------|
| `404` | `account_id` no encontrado |
| `409` | Mundo con la misma URL de servidor ya existe en esa cuenta (`WORLD_ALREADY_EXISTS`) |
| `422` | URL inválida (sin protocolo, mal formada) o tribu NPC |

---

## `GET /accounts/{account_id}/worlds`

Lista los mundos de una cuenta.

### Request

```
GET /accounts/1/worlds
```

### Response 200

```json
{
  "worlds": [ ...WorldResponse... ]
}
```

El array puede ser vacío si la cuenta no tiene mundos.

### Errores

| Código | Condición |
|--------|-----------|
| `404` | `account_id` no encontrado |

---

## `DELETE /accounts/{account_id}/worlds/{world_id}`

Elimina un mundo y sus aldeas en cascada.

### Request

```
DELETE /accounts/1/worlds/1
```

Sin body.

### Response 204

```
HTTP/1.1 204 No Content
```

### Errores

| Código | Condición |
|--------|-----------|
| `404` | `account_id` o `world_id` no encontrado |
| `409` | El mundo tiene sesión activa en el bot. Detener la sesión antes de borrar. |

**Mismo comportamiento defensivo que `DELETE /accounts`**: si `world_runtime_port` no está disponible, el use case procede con el borrado.

---

## Mapa completo de códigos de error de la feature

| `error_code` | HTTP | Condición |
|---|---|---|
| `ACCOUNT_NOT_FOUND` | `404` | `account_id` no existe en la BD |
| `WORLD_NOT_FOUND` | `404` | `world_id` no existe o no pertenece a la cuenta |
| `ACCOUNT_EMAIL_TAKEN` | `409` | Email ya registrado en otra cuenta |
| `WORLD_ALREADY_EXISTS` | `409` | Servidor Travian ya registrado en la misma cuenta |
| `ACCOUNT_HAS_ACTIVE_SESSION` | `409` | Intento de borrar cuenta con sesión activa |
| `WORLD_HAS_ACTIVE_SESSION` | `409` | Intento de borrar mundo con sesión activa |

---

## Notas de diseño

**Contraseña write-only**: el BLOB Fernet nunca sale de la BD en ninguna respuesta de esta sección. El único consumidor del BLOB es `LoginUseCase` (vía `DbPort.get_account_password_cipher`). Ver [`../api/sesion.md`](sesion.md) para la gestión de sesión.

**`_account_to_response` — doble acceso a BD**: los timestamps (`created_at`, `updated_at`) no forman parte de las entidades del core (`Account`, `World`) y se obtienen con queries adicionales directas a `_conn`. Es deuda técnica reconocida: el puerto `DbPort` no expone timestamps porque el core no los necesita para su lógica; los timestamps son un detalle de presentación. Un refactor futuro podría añadirlos al puerto o a las entidades.

---

🔖 Última revisión: 2026-05-26
