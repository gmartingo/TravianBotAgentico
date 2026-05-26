# Documentación de código — Feature de sesión (login / logout / estado)

Módulos documentados:
- `adapters/browser/session_registry.py` — `SessionRegistry`
- `core/use_cases/login_use_case.py` — `LoginUseCase`, `LogoutUseCase`
- `adapters/api/routes/accounts.py` — endpoints de sesión + helper de validación
- `adapters/api/dependencies.py` — `get_world_runtime_port`
- `adapters/api/main.py` — cableado en `lifespan`
- `core/ports/world_runtime_port.py` — `WorldRuntimePort` (puerto)
- `core/ports/db_port.py` — método `get_account_password_cipher`
- `adapters/db/account_sqlite_adapter.py` — `get_account_password_cipher`
- `core/exceptions.py` — `LoginFailedError`
- `adapters/api/error_codes.py` — mapeo `LOGIN_FAILED`
- `core/entities/account.py` — campo `password` con `repr=False`

Spec de referencia: [`docs/specs/login-sesion-api.md`](../../docs/specs/login-sesion-api.md)
Documento de negocio: [`funcionalidades/sesion.md`](../funcionalidades/sesion.md)
Referencia de API: [`api/sesion.md`](../api/sesion.md)

---

## Contexto de negocio

La feature de sesión cablea el login real de Travian (que ya existía en `adapters/browser/login.py`) con tres endpoints HTTP que el frontend puede invocar. Sin esta feature, `LiveOverviewAdapter` no tiene acceso a un browser autenticado y lanza `SessionNotActiveError` en cada lectura.

El flujo completo de una solicitud de login atraviesa cinco capas:

```
Handler HTTP
  → LoginUseCase     (descifra contraseña, localiza mundo)
  → SessionRegistry  (gestiona el dict de browsers activos)
  → login_module     (interacción humana real con Chrome y Travian)
```

---

## `core/ports/world_runtime_port.py` — `WorldRuntimePort`

Puerto abstracto que define el ciclo de vida de los browsers del bot. El core solo conoce esta interfaz; la implementación concreta (`SessionRegistry`) vive en `adapters/browser/`.

| Método | Firma | Descripción |
|--------|-------|-------------|
| `login` | `async (account, world) → bool` | Abre sesión autenticada. Devuelve `True` si tuvo éxito. Si ya existe sesión para `world.id`, la cierra antes de abrir la nueva. |
| `logout` | `async (world_id: int) → None` | Cierra la sesión activa. Idempotente: no lanza si no hay sesión. |
| `is_active` | `(world_id: int) → bool` | Consulta si hay sesión activa. Sincrónico. |

**Por qué existe**: el core no puede depender de `zd.Browser` de zendriver (eso violaría la abstracción hexagonal). El puerto permite que `LoginUseCase` opere sobre una interfaz sin conocer el adaptador real. Ver referencia de funciones: [`referencia-funciones/sesion.md`](referencia-funciones/sesion.md).

---

## `adapters/browser/session_registry.py` — `SessionRegistry`

Implementa `WorldRuntimePort`. Mantiene en memoria un `dict[int, tuple[zd.Browser, World]]` keyed por `world_id`. Es un singleton instanciado en `lifespan` y almacenado en `app.state.world_runtime_port`.

### Estado interno

```python
_sessions: dict[int, tuple[zd.Browser, World]] = {}
_live_adapter: LiveOverviewAdapter | None = None
```

`_sessions` nunca se serializa a BD — las sesiones son completamente efímeras. Un reinicio del servidor las borra todas (limitación aceptada, EC-13 del spec).

### `__init__(self)`

Inicializa `_sessions` vacío y `_live_adapter = None`. Sin parámetros. El `_live_adapter` se inyecta post-construcción vía `set_live_adapter()` porque ambos objetos (registry y `LiveOverviewAdapter`) se crean en el mismo `lifespan` y hay dependencia circular si se inyectan en los constructores.

### `set_live_adapter(adapter)`

Inyecta la referencia al `LiveOverviewAdapter` para que el registry pueda invalidar su caché en login/logout. Se llama desde `lifespan` en `main.py` **después** de construir ambos objetos.

**Por qué existe**: `SessionRegistry` necesita invalidar la caché de `LiveOverviewAdapter` cuando la sesión cambia (nueva sesión = datos de otra aldea potencialmente distintos). La inyección post-construcción evita la dependencia circular en los constructores. No-op si `OVERVIEW_SOURCE != 'live'`.

### `login(account, world) → bool` (async)

**Qué hace:**
1. Si `world.id` ya tiene sesión activa: llama `old_browser.stop()` y `_invalidate_cache(world_id)`.
2. Llama `login_module.login(account, world)` (el login real con Chrome y Travian).
3. Si éxito: guarda `(browser, world)` en `_sessions[world_id]` y llama `_invalidate_cache(world_id)`.
4. Devuelve `True` (éxito) o `False` (fallo; el browser ya fue cerrado por `login_module`).

**Log emitido:** solo `world_id` y resultado booleano. Nunca loguea credenciales, `world.server`, ni perfil de Chrome (restricción del guardian).

**Por qué invalida la caché dos veces en re-login:** la primera invalidación (al cerrar la sesión previa) evita que páginas de la sesión anterior se sirvan durante el intervalo de apertura. La segunda (tras el login exitoso) garantiza que la primera petición de datos cargue desde la nueva sesión.

**Impacto de negocio:** cumple RN-06 (re-login silencioso) y RN-12 (caché invalidada en nueva sesión).

### `logout(world_id) → None` (async)

**Qué hace:**
- Si no hay sesión para `world_id`: retorna inmediatamente (idempotente).
- Si hay sesión: llama `browser.stop()`, elimina la entrada de `_sessions`, llama `_invalidate_cache(world_id)`.

**Por qué solo `browser.stop()`:** cerrar el proceso Chrome localmente no es detectable por Travian. Navegar una URL de logout de Travian sería detectable y además innecesario — la sesión del bot acaba cuando el proceso muere.

**Impacto de negocio:** cumple RN-08 (idempotencia) y RN-11 (caché invalidada al cerrar sesión).

### `is_active(world_id) → bool`

Devuelve `world_id in self._sessions`. O(1). Sincrónico.

**Limitación conocida (EC-12 del spec):** si Chrome muere inesperadamente después de que el login fuera exitoso, `is_active()` sigue devolviendo `True` porque el dict tiene la entrada. El registry no detecta la muerte del browser. El usuario debe hacer DELETE + POST para recuperar la sesión.

### `get_browser(world_id) → zd.Browser | None`

Devuelve el `zd.Browser` activo para `world_id`, o `None` si no hay sesión. Se pasa como callable a `LiveOverviewAdapter` en el lifespan. **No forma parte de `WorldRuntimePort`**: es un contrato de integración solo conocido en la capa de adapters.

### `get_world_server(world_id) → str`

Devuelve `world.server` (URL base del servidor Travian) para `world_id`, o `""` si no hay sesión. Mismo patrón que `get_browser`.

### `_invalidate_cache(world_id)`

Helper interno. Llama `self._live_adapter.invalidate_cache(world_id)` si `_live_adapter` no es `None`. No-op si no hay live adapter configurado (modo `fixture` o tests). Nunca lanza excepción.

---

## `core/use_cases/login_use_case.py`

### `LoginUseCase`

Dataclass con tres campos: `registry: WorldRuntimePort`, `db: DbPort`, `fernet: Fernet`. El campo `fernet` se añadió en el Amendment A1 cuando se detectó que `get_account()` devuelve `password=""` (el adaptador no descifra al cargar — la decisión de diseño es que el descifrado es responsabilidad del use case, no del adaptador).

**Flujo de `execute(account_id, world_id) → bool`:**

```
1. db.get_account(account_id)          → Account (password="") | None
2. db.get_account_password_cipher(id)  → bytes (BLOB Fernet) | None
3. decrypt_password(fernet, cipher)    → str (contraseña en claro)  [ventana mínima]
4. _find_world(account, world_id)      → World | WorldNotFoundError
5. registry.login(account, world)      → bool
```

**Manejo de errores:**
- `account is None` → `AccountNotFoundError`
- `cipher is None` → `LoginFailedError` (no `500`) — situación de corrupción de BD; la cuenta existía en paso 1 pero no hay BLOB (imposible si el DDL tiene NOT NULL)
- `InvalidToken` → `LoginFailedError` (no re-lanza `InvalidToken`) — ocurre cuando `TRAVIAN_BOT_SECRET_KEY` ha cambiado desde que se guardó la contraseña
- `registry.login()` devuelve `False` → el use case devuelve `False`; el handler convierte esto en `LoginFailedError` → 401

**Regla de no-log:** ningún `logger.*` en `LoginUseCase` menciona `cipher`, `fernet`, ni `account.password`. Solo loguea `account_id` con nivel `error` en los casos de fallo de descifrado.

**Por qué el descifrado ocurre aquí (no en el adaptador):** el descifrado es lógica de aplicación — el adaptador solo almacena/recupera BLOBs opacos sin conocer Fernet. Pasar `fernet` como dependencia a `DbPort` contaminaría el puerto de core con un detalle de infraestructura. Ver sección A1.2 del spec.

**Impacto de negocio:** garantiza que la contraseña en claro existe solo en el scope de `execute()` durante el intervalo mínimo `decrypt → human_type`, sin persistirse en logs ni en BD.

### `LogoutUseCase`

Dataclass con un campo: `registry: WorldRuntimePort`. `execute(world_id)` simplemente llama `await self.registry.logout(world_id)`. No toca credenciales. No ha cambiado desde la implementación original.

---

## `core/ports/db_port.py` — `get_account_password_cipher`

Método abstracto añadido en Amendment A1:

```python
async def get_account_password_cipher(self, account_id: int) -> Optional[bytes]
```

**Qué hace:** devuelve el BLOB Fernet cifrado de la contraseña de la cuenta, o `None` si la cuenta no existe.

**Por qué existe separado de `get_account`:** `get_account()` devuelve `password=""` intencionalmente para que las respuestas de API de cuentas nunca expongan el cifrado. Un método separado, marcado "solo para LoginUseCase", hace explícita la restricción de uso y evita que otros handlers accedan al token cifrado sin necesidad.

---

## `adapters/db/account_sqlite_adapter.py` — `get_account_password_cipher`

```python
async def get_account_password_cipher(self, account_id: int) -> Optional[bytes]:
    cursor = await self._conn.execute(
        "SELECT password FROM accounts WHERE id = ?", (account_id,)
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return bytes(row["password"])
```

**Qué hace:** SELECT directo de la columna `password` (BLOB) de la tabla `accounts`. El `bytes(row["password"])` convierte el tipo `memoryview` de aiosqlite a `bytes` estándar de Python.

**Lo que NO hace:** no interpreta el BLOB. No conoce Fernet. El adaptador es opaco al contenido del BLOB.

**`get_account()` no cambia:** sigue devolviendo `password=""`. Esto no es un bug; es el comportamiento correcto para todas las lecturas que no son el flujo de login.

---

## `core/entities/account.py` — campo `password`

El campo `password` de la dataclass tiene `field(repr=False)` para que la contraseña en claro **nunca aparezca en el repr del objeto** cuando este se incluya en logs de trazas o excepciones.

```python
password: str = field(repr=False)  # en memoria siempre str; "" cuando viene de get_account
```

**Docstring actualizado (Amendment A1.8):** el docstring corrige la afirmación anterior ("el adaptador SQLite descifra al cargar") que era incorrecta desde el diseño inicial. El descifrado ocurre exclusivamente en `LoginUseCase`.

---

## `core/exceptions.py` — `LoginFailedError`

```python
class LoginFailedError(TravianBotError):
    error_code = "LOGIN_FAILED"
    def __init__(self, username: str) -> None:
        super().__init__(f"Login fallido para '{username}'")
        self.username = username
        self.params = {"username": username}
```

**Por qué no reusar `InvalidCredentialsError`:** `InvalidCredentialsError` implica semánticamente "credenciales incorrectas confirmadas". `LoginFailedError` cubre también errores de red, timeouts y cualquier excepción interna de zendriver, donde las credenciales pueden ser correctas. La API no distingue entre ambas situaciones (RN-13) para prevenir enumeración de información.

---

## `adapters/api/dependencies.py` — `get_world_runtime_port`

```python
def get_world_runtime_port(request: Request):
    port = getattr(request.app.state, "world_runtime_port", None)
    if port is None:
        raise HTTPException(503, "SessionRegistry no disponible — el servidor puede estar iniciándose.")
    return port
```

**Qué hace:** lee `app.state.world_runtime_port` (el singleton `SessionRegistry`) y lo devuelve. Lanza `503` directamente si no está disponible.

**Por qué lanza 503 aquí (no en el handler):** simplifica los handlers — no necesitan comprobar `None`. El 503 es correcto: si el registry no está disponible, el servicio de sesión está en un estado no operativo (EC-11 del spec).

---

## `adapters/api/routes/accounts.py` — endpoints de sesión

### Schema de respuesta

```python
class SessionStatusResponse(BaseModel):
    active: bool
    world_id: int
    account_id: int
```

Usado por `POST` (login) y `GET` (estado). El `DELETE` (logout) devuelve `204 No Content` sin body.

### Helper `_verify_world_belongs_to_account(account_id, world_id, db)`

```python
async def _verify_world_belongs_to_account(account_id, world_id, db) -> None:
    account = await db.get_account(account_id)
    if account is None:
        raise AccountNotFoundError(account_id)
    world_ids = {w.id for w in account.worlds}
    if world_id not in world_ids:
        raise WorldNotFoundError(world_id)
```

**Por qué devuelve `WorldNotFoundError` (y no un 403) cuando el mundo existe pero es de otra cuenta:** no se revela que el mundo existe en otra cuenta (RN-04, coherente con EC-12 del spec `registro-cuentas-mundos`). Un `403` revelaría que el recurso existe pero es inaccesible. Un `404` homogéneo oculta esa información.

**Reutilización:** los tres endpoints (POST, DELETE, GET) llaman a este helper antes de operar. La lógica de validación está en un único punto.

### `session_login` — `POST /accounts/{account_id}/worlds/{world_id}/session`

**Dependencias inyectadas:** `db` (DbPort), `registry` (SessionRegistry), `fernet` (Fernet).

**Flujo:**
1. `_verify_world_belongs_to_account` → 404 si cuenta/mundo no existen o no pertenecen.
2. `LoginUseCase(registry, db, fernet).execute(account_id, world_id)` → `bool`.
3. Si `False`: recupera el username para el mensaje y lanza `LoginFailedError` → 401.
4. Si `True`: devuelve `SessionStatusResponse(active=True, world_id, account_id)` → 200.

**Nota de diseño — por qué recupera la cuenta dos veces:** `_verify_world_belongs_to_account` hace una primera lectura para validar la pertenencia. Si el login falla, el handler hace una segunda lectura para obtener el `username` del mensaje de error. Esta redundancia es aceptable: ocurre solo en el camino de error, que es infrecuente y no es sensible al rendimiento.

**Tiempo de respuesta:** ~3-10 s por diseño (delays humanos en `login.py`). El endpoint es `async def`, así que no bloquea el event loop — solo esa coroutine espera. El cliente debe configurar un timeout de al menos 30 s.

### `session_logout` — `DELETE /accounts/{account_id}/worlds/{world_id}/session`

**Flujo:** `_verify_world_belongs_to_account` → `LogoutUseCase(registry).execute(world_id)` → `204`.

**Idempotencia:** si no hay sesión activa, `logout` es no-op y se devuelve igualmente `204`. Esto refleja el contrato de `WorldRuntimePort.logout()`.

### `session_status` — `GET /accounts/{account_id}/worlds/{world_id}/session`

**Flujo:** `_verify_world_belongs_to_account` → `registry.is_active(world_id)` → `SessionStatusResponse(active, world_id, account_id)` → 200.

**No requiere sesión activa para funcionar:** el GET no lanza error si `active == False`; siempre devuelve 200.

---

## `adapters/api/main.py` — cableado en `lifespan`

El bloque de `SessionRegistry` en `lifespan` debe ejecutarse **después** de crear `html_source_port` porque `set_live_adapter()` requiere la referencia al adaptador ya construido:

```python
# 1. Crear html_source_port (LiveOverviewAdapter o FixtureOverviewAdapter)
html_source_port = LiveOverviewAdapter(
    get_browser=lambda wid: None,      # stubs temporales
    get_world_server=lambda wid: "",
) if _overview_source == "live" else FixtureOverviewAdapter(...)

application.state.html_source_port = html_source_port

# 2. Crear SessionRegistry DESPUÉS
session_registry = SessionRegistry()
application.state.world_runtime_port = session_registry

# 3. Cablear en modo 'live' — sustituye los stubs por métodos reales
if _overview_source == "live":
    html_source_port.set_callables(
        get_browser=session_registry.get_browser,
        get_world_server=session_registry.get_world_server,
    )
    session_registry.set_live_adapter(html_source_port)
```

**Por qué `LiveOverviewAdapter` se crea primero con lambdas stub:** en modo `live`, `LiveOverviewAdapter` se construye antes de que exista `SessionRegistry`. Los stubs (`lambda wid: None / ""`) devuelven resultados "sin sesión" controlados: `LiveOverviewAdapter` los interpretará como `SessionNotActiveError`. Cuando `SessionRegistry` esté listo, los stubs se reemplazan vía `set_callables()`.

**`_SENSITIVE_FIELD_PATTERNS` ampliado (Amendment A1.6):** el regex incluye `cipher` y `secret` además de los patrones previos (`password`, `token`, `api_key`, `authorization`), para que los frames de `LoginUseCase.execute()` enmascaren el token Fernet si aparecen en un trace verbose.

---

## `adapters/api/error_codes.py` — mapeo `LOGIN_FAILED`

```python
"LOGIN_FAILED": 401,
```

Añadido en la sección de "Excepciones añadidas en la feature login-sesion-api". El 401 cubre tanto credenciales incorrectas como errores de red/timeout (RN-13: no se distingue en la API para prevenir enumeración).

---

## Restricciones anti-detección aplicadas

| Restricción | Dónde se aplica | Por qué |
|-------------|-----------------|---------|
| No loguear credenciales | `SessionRegistry.login()`, `LoginUseCase.execute()` | Una credencial en log = exposición en cualquier sistema de observabilidad |
| No loguear `world.server` | `SessionRegistry.login()` | Las URLs de Travian son suficientemente específicas para identificar la cuenta |
| `logout()` solo llama `browser.stop()` | `SessionRegistry.logout()` | Navegar una URL de logout de Travian es detectable; cerrar el proceso no lo es |
| Sin timings propios en el registry | `SessionRegistry.login()` | Los delays humanos viven exclusivamente en `login_module` — el registry no introduce ninguno |
| `get_browser`/`get_world_server` son referencias directas | `main.py` | Sin wrappers que midan tiempos o transformen datos — no hay capa intermedia entre el browser y `LiveOverviewAdapter` |
| `login.py` y `driver.py` no se modifican | Feature entera | Preservar las capas de anti-detección existentes ya auditadas por el guardian |

---

## Limitaciones conocidas y deuda técnica

| Limitación | EC del spec | Tratamiento |
|------------|-------------|-------------|
| Browser muerto no detectado | EC-12 | `is_active()` devuelve `True` aunque Chrome haya muerto. El usuario debe hacer DELETE + POST. |
| Sesiones perdidas en reinicio | EC-13 | El registry es in-memory; un reinicio borra todo. El frontend debe consultar GET /session al iniciar. |
| Sin lock en `_sessions` | EC-10 / TR-03 | Dos POSTs simultáneos al mismo `world_id` pueden interferir. Aceptado: 1 usuario, no ocurre en la práctica. |
| Timeout del login no configurable | TR-01 | El cliente debe tener timeout ≥ 30 s. El login real puede tardar 3-10 s. |

---

## Divergencias código/spec

Ninguna. El spec se siguió íntegramente, incluyendo el Amendment A1. El docstring de `core/entities/account.py` fue corregido en la implementación (A1.8) y ya coincide con el comportamiento real del código.

**Nota:** en el registro de implementación del spec original (sección 16, antes del Amendment) se afirmaba que "las credenciales se obtienen de `db.get_account()` (ya descifradas por `AccountSQLiteAdapter`)". Esa afirmación era incorrecta y quedó corregida por el Amendment A1, que documentó y solucionó el hueco antes de que el sistema llegara a producción.

---

## Tests relacionados

| Fichero | Qué cubre |
|---------|-----------|
| `tests/unit/test_session_registry.py` | 15 tests unitarios de `SessionRegistry` (login exitoso/fallido, re-login, invalidación de caché, logout idempotente, is_active, get_browser, get_world_server) |
| `tests/unit/test_session_api.py` | 14 tests (spec original) + 2 del Amendment A1 + 3 del helper `_verify_world_belongs_to_account` = 19 tests de API con TestClient |
| `tests/unit/test_login_use_case.py` | 15 tests de `LoginUseCase` con Fernet real (descifrado, InvalidToken, cipher nulo, account/world not found, login fallido) |
| `tests/unit/test_account_sqlite_adapter.py` | 3 tests del método `get_account_password_cipher` |

Ningún test abre Chrome real. Suite completa: 732 passed tras la implementación completa (incluyendo Amendment A1), 9 fallos preexistentes no relacionados.

---

🔖 Última revisión: 2026-05-26
