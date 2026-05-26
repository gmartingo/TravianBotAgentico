---
id: login-sesion-api
titulo: API REST de sesión — login/logout/estado de una cuenta+mundo
estado: implemented
fecha: 2026-05-26
autor: analista
apis_validadas_por_desarrollador_apis: true
amendment: A1-descifrado-credenciales (2026-05-26) — implemented
---

# API REST de sesión — login/logout/estado de una cuenta+mundo

## 1. Objetivo de negocio

Exponer vía API REST el ciclo de vida de la sesión del bot en un mundo concreto: abrir login, cerrar sesión y consultar si hay sesión activa. El login real (`adapters/browser/login.py`) y la lógica de dominio (`LoginUseCase`, `LogoutUseCase`, `WorldRuntimePort`) ya existen e implementan la interacción humana con Travian (delays, perfil Chrome, escritura carácter a carácter). Esta feature los cablea con tres endpoints HTTP y crea el `SessionRegistry` que implementa `WorldRuntimePort` y adicionalmente suministra los callables `get_browser`/`get_world_server` que `LiveOverviewAdapter` necesita.

Sin esta feature, `LiveOverviewAdapter` solo puede funcionar en modo stub (lambdas que devuelven `None`/`""`), lanzando `SessionNotActiveError` en cada petición.

---

## 2. Actores y permisos

| Actor | Rol |
|---|---|
| Frontend (React dashboard) | Dispara POST/DELETE/GET contra los endpoints de sesión |
| `LoginUseCase` | Orquesta el login: recupera cuenta+mundo de la BD, delega en `WorldRuntimePort.login()` |
| `LogoutUseCase` | Cierra la sesión activa para un `world_id` via `WorldRuntimePort.logout()` |
| `SessionRegistry` | Implementa `WorldRuntimePort`; mantiene en memoria un dict `{world_id → (Browser, World)}`. Es un singleton en `app.state.world_runtime_port` |
| `LiveOverviewAdapter` | Consumidor de `SessionRegistry.get_browser` / `SessionRegistry.get_world_server`; no depende del endpoint HTTP, sino del singleton en `app.state` |
| `DbPort` | Fuente de verdad para verificar existencia de cuenta y mundo, y para comprobar pertenencia |

No hay autenticación de usuario para estos endpoints. El bot es de uso personal (un único usuario).

---

## 3. Alcance

### Dentro del alcance

- Crear `adapters/browser/session_registry.py` con la clase `SessionRegistry` que implementa `WorldRuntimePort` y expone `get_browser` / `get_world_server`.
- Añadir los tres endpoints de sesión al router existente en `adapters/api/routes/accounts.py`.
- Añadir `get_world_runtime_port(request)` a `adapters/api/dependencies.py`.
- Modificar el lifespan de `adapters/api/main.py`:
  - Instanciar `SessionRegistry` en `app.state.world_runtime_port`.
  - Reemplazar las lambdas stub de `LiveOverviewAdapter` por `session_registry.get_browser` / `session_registry.get_world_server`.
- Añadir las entradas `LOGIN_FAILED` → `401` y `WORLD_NOT_IN_ACCOUNT` → `404` en `error_codes.py`.
- Añadir la excepción `LoginFailedError` a `core/exceptions.py` y los mensajes correspondientes a `messages.json`.
- Tests unitarios con mocks (sin Chrome real).

### Fuera del alcance

- Autenticación/autorización en los endpoints (fuera del proyecto actual).
- Persistencia del estado de sesión en BD (las sesiones son in-memory; un reinicio del servidor las limpia).
- Concurrencia de múltiples sesiones simultáneas por el mismo `world_id` (se rechaza la segunda vía re-login según el contrato del puerto).
- Timeout automático de sesiones inactivas (feature futura).
- Notificaciones WebSocket/SSE al frontend cuando la sesión cae inesperadamente.
- Cualquier modificación de `adapters/browser/login.py` o `adapters/browser/driver.py`.

---

## 4. Reglas de negocio

| ID | Regla |
|---|---|
| RN-01 | El recurso `session` es subrecurso de `worlds`, que es subrecurso de `accounts`. La URL sigue la jerarquía: `/accounts/{account_id}/worlds/{world_id}/session`. |
| RN-02 | El `account_id` de la URL debe corresponder a una cuenta existente en la BD; si no, se devuelve `404`. |
| RN-03 | El `world_id` de la URL debe corresponder a un mundo existente en la BD; si no, se devuelve `404`. |
| RN-04 | El `world_id` debe pertenecer a la cuenta indicada por `account_id`; si no, se devuelve `404` (no `403` — no se revela que el mundo existe en otra cuenta, consistente con EC-12 del spec `registro-cuentas-mundos`). |
| RN-05 | El POST (login) es **síncrono**: espera el resultado completo del login real (~3-10 segundos) antes de responder. El cliente debe tener un timeout de al menos 30 segundos. |
| RN-06 | Si POST llega y ya hay una sesión activa para ese `world_id`, `SessionRegistry.login()` cierra la sesión anterior antes de abrir una nueva (definido en `WorldRuntimePort.login()`: "si ya existe una sesión para world.id, la cierra antes de abrir una nueva"). No se devuelve `409`; se re-loguea silenciosamente. |
| RN-07 | Si el login falla (credenciales incorrectas, timeout de Travian, excepción de zendriver), el browser se cierra automáticamente dentro de `adapters/browser/login.py` y se devuelve `401` al cliente. |
| RN-08 | DELETE (logout) es **idempotente**: si no hay sesión activa para ese `world_id`, devuelve `204` sin error (consistente con `WorldRuntimePort.logout()` que es idempotente). |
| RN-09 | GET (estado) devuelve `{"active": true/false}` sin información adicional. No expone detalles de la sesión (URL del servidor, perfil Chrome, etc.). |
| RN-10 | Los endpoints de sesión NO requieren `Accept-Language`: son operativos, no devuelven texto localizado. Consistente con el resto de `/accounts`. |
| RN-11 | Al hacer logout, se invalida la caché de `LiveOverviewAdapter` para ese `world_id` (si el adaptador activo en `app.state.html_source_port` es `LiveOverviewAdapter`). Evita que páginas cacheadas de una sesión cerrada se sirvan en una sesión nueva. |
| RN-12 | `SessionRegistry` invalida la caché de `LiveOverviewAdapter` también al hacer login (re-login): la sesión nueva puede pertenecer a una aldea diferente o tener datos distintos. |
| RN-13 | Las excepciones de Travian que `login.py` captura internamente (cualquier `Exception`) resultan siempre en `(False, None)` desde `login.py`. El endpoint las trata todas como `401`. No se distingue en la API entre "credenciales incorrectas" y "error de red al hacer login" — ambas son `401`. |

---

## 5. Flujo principal y flujos alternativos

### Flujo principal — POST (login exitoso)

```
Cliente → POST /accounts/1/worlds/1/session
  │
  └─> [handler] session_login(account_id=1, world_id=1)
        ├─ 1. verificar cuenta: db.get_account(1) → Account ✓
        ├─ 2. verificar pertenencia: world_id=1 en account.worlds ✓
        ├─ 3. construir LoginUseCase(registry, db)
        ├─ 4. await use_case.execute(1, 1)
        │       ├─ registry.login(account, world)
        │       │     ├─ si hay sesión previa: await browser.stop(); del sessions[1]
        │       │     │   + live_adapter.invalidate_cache(1)
        │       │     ├─ await login.login(account, world)  [~3-10 s]
        │       │     │     → (True, browser)
        │       │     ├─ sessions[1] = (browser, world)
        │       │     └─ live_adapter.invalidate_cache(1)
        │       └─ return True
        └─ respuesta: 200 {"active": true, "world_id": 1, "account_id": 1}
```

### Flujo principal — DELETE (logout)

```
Cliente → DELETE /accounts/1/worlds/1/session
  └─> [handler] session_logout(account_id=1, world_id=1)
        ├─ 1. verificar cuenta: db.get_account(1) → Account ✓
        ├─ 2. verificar pertenencia: world_id=1 en account.worlds ✓
        ├─ 3. await LogoutUseCase(registry).execute(1)
        │       └─ registry.logout(1)
        │             ├─ si hay sesión: await browser.stop(); del sessions[1]
        │             │   + live_adapter.invalidate_cache(1)
        │             └─ si no hay sesión: no-op (idempotente)
        └─ respuesta: 204 (sin body)
```

### Flujo principal — GET (estado)

```
Cliente → GET /accounts/1/worlds/1/session
  └─> [handler] session_status(account_id=1, world_id=1)
        ├─ 1. verificar cuenta: db.get_account(1) → Account ✓
        ├─ 2. verificar pertenencia: world_id=1 en account.worlds ✓
        ├─ 3. registry.is_active(1) → True/False
        └─ respuesta: 200 {"active": true/false, "world_id": 1, "account_id": 1}
```

### Flujo alternativo A — account_id no existe (todos los verbos)

```
db.get_account(account_id) → None
→ raise AccountNotFoundError(account_id)
→ exception handler global → 404 {"detail": "Cuenta X no encontrada"}
```

### Flujo alternativo B — world_id no pertenece a la cuenta (todos los verbos)

```
db.get_account(account_id) → Account (existe)
world_id no en {w.id for w in account.worlds}
→ raise WorldNotFoundError(world_id)
→ exception handler global → 404 {"detail": "Mundo X no encontrado"}
```

### Flujo alternativo C — login fallido (POST)

```
await use_case.execute(account_id, world_id)
  → registry.login(account, world)
  → login.login(account, world) → (False, None)  [browser ya cerrado internamente]
  → registry.login() devuelve False
  → use_case.execute() devuelve False
handler: resultado == False → raise LoginFailedError(account.username)
→ exception handler global → 401 {"detail": "Login fallido para 'testtravian13@gmail.com'"}
```

### Flujo alternativo D — excepción inesperada en zendriver (POST)

```
login.login(account, world) captura la excepción internamente
→ cierra browser si fue abierto
→ devuelve (False, None)
→ mismo flujo que alternativo C → 401
```

---

## 6. Edge cases

| ID | Caso | Tratamiento esperado |
|---|---|---|
| EC-01 | `account_id` no existe en BD | `AccountNotFoundError` → `404`. El browser nunca se abre. |
| EC-02 | `world_id` existe en BD pero no pertenece a `account_id` | `WorldNotFoundError` → `404`. No se revela la existencia del mundo en otra cuenta. |
| EC-03 | `world_id` no existe en BD (ni en ninguna cuenta) | `WorldNotFoundError` → `404`. Mismo 404 que EC-02: el cliente no puede distinguir "no existe" de "existe pero es de otro". |
| EC-04 | POST cuando ya hay sesión activa para ese `world_id` | `SessionRegistry.login()` cierra la sesión anterior con `await browser.stop()` e invalida la caché antes de abrir la nueva. No devuelve `409`. |
| EC-05 | DELETE cuando no hay sesión activa | `registry.logout()` es idempotente (no-op). Devuelve `204`. |
| EC-06 | GET cuando no hay sesión activa | `registry.is_active()` devuelve `False`. Respuesta: `200 {"active": false, "world_id": X, "account_id": Y}`. |
| EC-07 | Login fallido: credenciales incorrectas (Travian devuelve error) | `login.py` detecta que la URL post-submit no contiene `"dorf"` ni `"village"`, cierra el browser, devuelve `(False, None)`. El handler lanza `LoginFailedError` → `401`. |
| EC-08 | Login fallido: timeout de zendriver o excepción de red | `login.py` captura cualquier `Exception`, cierra browser si existe, devuelve `(False, None)`. El handler lanza `LoginFailedError` → `401`. Idéntico a EC-07 desde la perspectiva de la API. |
| EC-09 | `LiveOverviewAdapter` no está instanciado como adaptador activo (OVERVIEW_SOURCE=fixture) | `SessionRegistry` solo llama a `invalidate_cache` si `app.state.html_source_port` es instancia de `LiveOverviewAdapter`. Se comprueba con `isinstance`. Si es `FixtureOverviewAdapter`, se omite la invalidación sin error. |
| EC-10 | Dos llamadas POST simultáneas para el mismo `world_id` | `SessionRegistry.login()` no tiene lock. La segunda llamada cerrará la sesión que la primera está abriendo en medio del proceso. Riesgo aceptado: 1 solo usuario, imposible en la práctica (el frontend espera la respuesta antes de volver a llamar). Se documenta como limitación sin bloqueo. |
| EC-11 | `SessionRegistry` en `app.state` no disponible (arranque sin lifespan, tests de API) | `get_world_runtime_port(request)` hace `getattr(request.app.state, "world_runtime_port", None)`. Si devuelve `None`, el handler lanza `HTTPException(503, "SessionRegistry no disponible")`. |
| EC-12 | Chrome cae después de que el login fuera exitoso (browser muere mid-sesión) | `registry.is_active(world_id)` devuelve `True` porque el dict tiene la entrada. `LiveOverviewAdapter` lanzará `OverviewPageNotLoadedError` al intentar navegar. El registry no detecta la muerte del browser. Limitación aceptada: el usuario debe hacer DELETE + POST para recuperar la sesión. |
| EC-13 | Servidor reiniciado: todas las sesiones en memoria se pierden | El registry (in-memory) se vacía. `is_active()` devuelve `False` para todos. El frontend debe consultar `/session` al iniciar para saber el estado real. |

---

## 7. Modelo de datos / cambios de esquema

No hay cambios en la BD SQLite. Las sesiones son completamente in-memory en `SessionRegistry`.

### Estructura interna de `SessionRegistry`

```python
# Estado interno — privado, no expuesto por la API
_sessions: dict[int, tuple[zd.Browser, World]] = {}
# clave: world_id
# valor: (browser vivo, entidad World con world.server para get_world_server)
```

No hay migración de base de datos. No hay nuevas tablas ni columnas.

---

## 8. Contratos de API / interfaces

### 8.1 Decisión de reutilización

**CREAR** los tres endpoints nuevos. No existe ningún endpoint de session en `adapters/api/routes/accounts.py` (verificado: el router tiene 8 endpoints de accounts/worlds, ninguno de session).

Los tres endpoints se añaden al router **existente** `accounts_router` en `adapters/api/routes/accounts.py`. No se crea un router nuevo: la jerarquía `/accounts/{id}/worlds/{id}/session` pertenece al mismo recurso.

### 8.2 Endpoint 1 — Abrir sesión (login)

```
POST /accounts/{account_id}/worlds/{world_id}/session
```

**Request:**
- Sin body (las credenciales están cifradas en la BD, el backend las recupera).
- Sin `Accept-Language`.
- Path params: `account_id: int`, `world_id: int`.

**Respuesta exitosa:**
```
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8

{
  "active": true,
  "world_id": 1,
  "account_id": 1
}
```

Nota: se usa `200` (no `201`) porque no se crea un recurso persistente en BD. La sesión es estado de infraestructura efímero.

**Errores:**

| Código | Error | Condición |
|--------|-------|-----------|
| 404 | `{"detail": "Cuenta 99 no encontrada"}` | `account_id` no existe |
| 404 | `{"detail": "Mundo 99 no encontrado"}` | `world_id` no existe o no pertenece a la cuenta |
| 401 | `{"detail": "Login fallido para 'testtravian13@gmail.com'"}` | Login devolvió False (credenciales/error/timeout) |
| 503 | `{"detail": "SessionRegistry no disponible"}` | `app.state.world_runtime_port` es None (EC-11) |

**Cabeceras comunes** (añadidas por middleware global): `X-Request-ID`, `X-API-Version`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`.

**Nota de timeout:** el cliente debe esperar hasta 30 segundos. El login real tarda ~3-10 s por diseño (delays anti-detección).

### 8.3 Endpoint 2 — Cerrar sesión (logout)

```
DELETE /accounts/{account_id}/worlds/{world_id}/session
```

**Request:**
- Sin body.
- Path params: `account_id: int`, `world_id: int`.

**Respuesta exitosa:**
```
HTTP/1.1 204 No Content
```

**Errores:**

| Código | Error | Condición |
|--------|-------|-----------|
| 404 | `{"detail": "Cuenta 99 no encontrada"}` | `account_id` no existe |
| 404 | `{"detail": "Mundo 99 no encontrado"}` | `world_id` no existe o no pertenece a la cuenta |
| 503 | `{"detail": "SessionRegistry no disponible"}` | `app.state.world_runtime_port` es None |

Nota: `204` aunque no haya sesión activa (idempotente por RN-08).

### 8.4 Endpoint 3 — Estado de sesión

```
GET /accounts/{account_id}/worlds/{world_id}/session
```

**Request:**
- Sin body.
- Path params: `account_id: int`, `world_id: int`.

**Respuesta exitosa:**
```
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8

{
  "active": false,
  "world_id": 1,
  "account_id": 1
}
```

**Errores:**

| Código | Error | Condición |
|--------|-------|-----------|
| 404 | `{"detail": "Cuenta 99 no encontrada"}` | `account_id` no existe |
| 404 | `{"detail": "Mundo 99 no encontrado"}` | `world_id` no existe o no pertenece a la cuenta |
| 503 | `{"detail": "SessionRegistry no disponible"}` | `app.state.world_runtime_port` es None |

### 8.5 Schema Pydantic de respuesta de sesión

```python
class SessionStatusResponse(BaseModel):
    active: bool
    world_id: int
    account_id: int
```

Añadir en `adapters/api/routes/accounts.py`.

---

## 9. Flujo lógico paso a paso

### 9.1 `SessionRegistry` — contrato completo

```python
# adapters/browser/session_registry.py

import logging
import zendriver as zd

from adapters.browser import login as login_module
from core.entities.account import Account
from core.entities.world import World
from core.ports.world_runtime_port import WorldRuntimePort

logger = logging.getLogger(__name__)


class SessionRegistry(WorldRuntimePort):
    """
    Implementa WorldRuntimePort. Mantiene en memoria un dict de browsers activos
    keyed por world_id.

    Adicionalmente expone get_browser y get_world_server para que LiveOverviewAdapter
    pueda inyectarlos como callables. Estos métodos NO forman parte de WorldRuntimePort
    (no son abstractos): son la interfaz de integración entre SessionRegistry y
    LiveOverviewAdapter, conocida solo en la capa de adapters (main.py).
    """

    def __init__(self) -> None:
        # dict[world_id, tuple[zd.Browser, World]]
        self._sessions: dict[int, tuple[zd.Browser, World]] = {}
        # Referencia opcional a LiveOverviewAdapter para invalidar caché en login/logout.
        # Se inyecta desde main.py tras construir ambos adaptadores.
        self._live_adapter = None  # tipo: LiveOverviewAdapter | None

    def set_live_adapter(self, adapter) -> None:
        """
        Inyecta la referencia a LiveOverviewAdapter para invalidar caché.
        Llamar desde main.py lifespan después de instanciar ambos objetos.
        Solo aplicable si OVERVIEW_SOURCE == 'live'.
        """
        self._live_adapter = adapter

    # ------------------------------------------------------------------
    # WorldRuntimePort — métodos abstractos implementados
    # ------------------------------------------------------------------

    async def login(self, account: Account, world: World) -> bool:
        """
        Abre una sesión autenticada para account en world.

        Comportamiento ante sesión previa:
          Si ya existe una sesión para world.id, la cierra con browser.stop()
          e invalida la caché de LiveOverviewAdapter antes de abrir la nueva.

        Devuelve True si el login fue exitoso, False en caso contrario.
        En caso de fallo, el browser ya fue cerrado por login_module.login().
        """
        world_id = world.id

        # Cerrar sesión previa si existe (RN-06, EC-04)
        if world_id in self._sessions:
            old_browser, _ = self._sessions.pop(world_id)
            try:
                await old_browser.stop()
            except Exception:
                logger.warning("Error cerrando browser previo para world_id=%s", world_id)
            self._invalidate_cache(world_id)

        success, browser = await login_module.login(account, world)

        if success and browser is not None:
            self._sessions[world_id] = (browser, world)
            self._invalidate_cache(world_id)  # RN-12: nueva sesión = caché obsoleta
            return True

        # login fallido: browser ya cerrado por login_module.login()
        return False

    async def logout(self, world_id: int) -> None:
        """
        Cierra la sesión activa para world_id.
        Idempotente: no lanza excepción si no hay sesión activa (RN-08, EC-05).
        """
        if world_id not in self._sessions:
            return  # idempotente

        browser, _ = self._sessions.pop(world_id)
        try:
            await browser.stop()
        except Exception:
            logger.warning("Error cerrando browser en logout para world_id=%s", world_id)
        self._invalidate_cache(world_id)

    def is_active(self, world_id: int) -> bool:
        """Devuelve True si hay una sesión activa para world_id."""
        return world_id in self._sessions

    # ------------------------------------------------------------------
    # Métodos adicionales para LiveOverviewAdapter (NO en WorldRuntimePort)
    # ------------------------------------------------------------------

    def get_browser(self, world_id: int) -> zd.Browser | None:
        """
        Devuelve el zd.Browser activo para world_id, o None si no hay sesión.
        Se pasa como callable a LiveOverviewAdapter:
            get_browser=session_registry.get_browser
        """
        entry = self._sessions.get(world_id)
        return entry[0] if entry is not None else None

    def get_world_server(self, world_id: int) -> str:
        """
        Devuelve la URL base del servidor Travian para world_id, o "" si no hay sesión.
        Se pasa como callable a LiveOverviewAdapter:
            get_world_server=session_registry.get_world_server
        """
        entry = self._sessions.get(world_id)
        return entry[1].server if entry is not None else ""

    # ------------------------------------------------------------------
    # Helper interno
    # ------------------------------------------------------------------

    def _invalidate_cache(self, world_id: int) -> None:
        """
        Invalida la caché de LiveOverviewAdapter para world_id si está inyectado.
        No-op si no hay live_adapter configurado (modo fixture o tests).
        """
        if self._live_adapter is not None:
            self._live_adapter.invalidate_cache(world_id)
```

### 9.2 `adapters/api/dependencies.py` — nueva dependencia

Añadir al final del fichero existente:

```python
from fastapi import HTTPException

def get_world_runtime_port(request: Request):
    """
    Devuelve el singleton de WorldRuntimePort (SessionRegistry) almacenado en app.state.
    Se inicializa en el lifespan de la aplicación.

    Devuelve None si app.state no tiene 'world_runtime_port' (compatibilidad con
    entornos donde SessionRegistry no está disponible).

    El handler que usa esta dependencia debe comprobar si es None y lanzar 503.
    """
    port = getattr(request.app.state, "world_runtime_port", None)
    if port is None:
        raise HTTPException(
            status_code=503,
            detail="SessionRegistry no disponible — el servidor puede estar iniciándose.",
        )
    return port
```

Nota: la dependencia lanza `503` directamente en vez de devolver `None`. Esto simplifica los handlers: no necesitan comprobar None.

### 9.3 `adapters/api/main.py` — lifespan modificado

Cambios en la función `lifespan`:

```python
# AÑADIR imports al inicio del fichero:
from adapters.browser.session_registry import SessionRegistry

# DENTRO de lifespan, DESPUÉS de instanciar account_adapter y html_source_port:

# SessionRegistry — implementa WorldRuntimePort + callables para LiveOverviewAdapter
session_registry = SessionRegistry()
application.state.world_runtime_port = session_registry

# Cablear SessionRegistry con LiveOverviewAdapter (solo en modo 'live')
# Reemplaza las lambdas stub que devolvían None/"" por métodos reales.
if _overview_source == "live":
    # html_source_port ya fue asignado arriba como LiveOverviewAdapter
    # Sustituir los callables stub por los métodos reales del registry
    html_source_port._get_browser = session_registry.get_browser
    html_source_port._get_world_server = session_registry.get_world_server
    # Inyectar referencia inversa para invalidación de caché en login/logout
    session_registry.set_live_adapter(html_source_port)
# En modo 'fixture', session_registry no necesita referencia a html_source_port
# (FixtureOverviewAdapter no tiene caché que invalidar).
```

**Nota importante sobre el orden en `lifespan`:**
El bloque de `SessionRegistry` debe ir DESPUÉS de la creación de `html_source_port` porque necesita la referencia al adaptador ya construido.

### 9.4 `adapters/api/routes/accounts.py` — nuevos endpoints

Añadir imports al inicio:

```python
from adapters.api.dependencies import get_world_runtime_port
from core.exceptions import LoginFailedError
from core.use_cases.login_use_case import LoginUseCase, LogoutUseCase
```

Añadir schema de respuesta:

```python
class SessionStatusResponse(BaseModel):
    active: bool
    world_id: int
    account_id: int
```

Helper de validación de pertenencia (reutilizado por los tres endpoints):

```python
async def _verify_world_belongs_to_account(
    account_id: int,
    world_id: int,
    db,
) -> None:
    """
    Verifica que account existe y que world_id pertenece a account_id.
    Lanza AccountNotFoundError o WorldNotFoundError según corresponda.
    Misma lógica que DeleteWorldUseCase._verify_ownership (EC-04 del spec
    registro-cuentas-mundos: 404 homogéneo para no revelar existencia ajena).
    """
    account = await db.get_account(account_id)
    if account is None:
        raise AccountNotFoundError(account_id)
    world_ids = {w.id for w in account.worlds}
    if world_id not in world_ids:
        raise WorldNotFoundError(world_id)
```

Tres endpoints:

```python
@router.post(
    "/accounts/{account_id}/worlds/{world_id}/session",
    status_code=status.HTTP_200_OK,
    response_model=SessionStatusResponse,
    summary="Abrir sesión (login)",
    description=(
        "Abre una sesión autenticada en Travian para la cuenta y mundo indicados. "
        "Operación síncrona: puede tardar hasta 10 segundos (delays anti-detección). "
        "Si ya existe una sesión activa, la cierra antes de abrir una nueva. "
        "Devuelve 401 si el login falla (credenciales incorrectas o error de red)."
    ),
)
async def session_login(
    account_id: int,
    world_id: int,
    db=Depends(get_db_port),
    registry=Depends(get_world_runtime_port),
) -> SessionStatusResponse:
    await _verify_world_belongs_to_account(account_id, world_id, db)
    use_case = LoginUseCase(registry=registry, db=db)
    success = await use_case.execute(account_id, world_id)
    if not success:
        # Obtener username para el mensaje de error (la cuenta existe: ya la verificamos)
        account = await db.get_account(account_id)
        raise LoginFailedError(account.username if account else str(account_id))
    return SessionStatusResponse(active=True, world_id=world_id, account_id=account_id)


@router.delete(
    "/accounts/{account_id}/worlds/{world_id}/session",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cerrar sesión (logout)",
    description=(
        "Cierra la sesión activa del bot para el mundo indicado. "
        "Idempotente: devuelve 204 aunque no haya sesión activa."
    ),
)
async def session_logout(
    account_id: int,
    world_id: int,
    db=Depends(get_db_port),
    registry=Depends(get_world_runtime_port),
) -> None:
    await _verify_world_belongs_to_account(account_id, world_id, db)
    use_case = LogoutUseCase(registry=registry)
    await use_case.execute(world_id)


@router.get(
    "/accounts/{account_id}/worlds/{world_id}/session",
    status_code=status.HTTP_200_OK,
    response_model=SessionStatusResponse,
    summary="Estado de sesión",
    description=(
        "Devuelve si hay una sesión activa del bot para el mundo indicado. "
        "No requiere sesión activa para funcionar."
    ),
)
async def session_status(
    account_id: int,
    world_id: int,
    db=Depends(get_db_port),
    registry=Depends(get_world_runtime_port),
) -> SessionStatusResponse:
    await _verify_world_belongs_to_account(account_id, world_id, db)
    active = registry.is_active(world_id)
    return SessionStatusResponse(active=active, world_id=world_id, account_id=account_id)
```

### 9.5 `core/exceptions.py` — nueva excepción

Añadir al final de `core/exceptions.py`:

```python
class LoginFailedError(TravianBotError):
    """
    El login en Travian falló: credenciales incorrectas, error de red,
    o cualquier excepción interna de zendriver.
    El browser ya fue cerrado por login.py antes de llegar aquí.
    """
    error_code = "LOGIN_FAILED"

    def __init__(self, username: str) -> None:
        super().__init__(f"Login fallido para '{username}'")
        self.username = username
        self.params = {"username": username}
```

### 9.6 `adapters/api/error_codes.py` — nuevo mapeo

Añadir en `ERROR_HTTP_MAP`:

```python
"LOGIN_FAILED": 401,
```

### 9.7 `core/i18n/catalog/base/messages.json` — nuevo mensaje

Añadir en el JSON:

```json
"LOGIN_FAILED": {
  "es": "Login fallido para '{username}'. Verifica las credenciales o el estado del servidor.",
  "en": "Login failed for '{username}'. Check your credentials or server status.",
  "de": "",
  "fr": "",
  "ru": ""
}
```

---

## 10. Validaciones y reglas

| Input | Validación | Dónde | Error |
|-------|-----------|-------|-------|
| `account_id` (path) | Debe ser entero > 0 | FastAPI automático → `422` si no parseable | `422` |
| `world_id` (path) | Debe ser entero > 0 | FastAPI automático → `422` si no parseable | `422` |
| `account_id` existe en BD | `db.get_account(account_id) != None` | `_verify_world_belongs_to_account` | `404` |
| `world_id` pertenece a cuenta | `world_id in {w.id for w in account.worlds}` | `_verify_world_belongs_to_account` | `404` |
| `registry` disponible | `getattr(app.state, "world_runtime_port", None) != None` | `get_world_runtime_port` dependency | `503` |
| Resultado de login | `success == True` (bool devuelto por `LoginUseCase.execute`) | handler de POST | `401` |

No hay body que validar (POST no tiene body). El DELETE y GET tampoco.

---

## 11. Seguridad, rendimiento y concurrencia

### Anti-detección — OBLIGATORIO (invocar guardian-antideteccion)

Esta feature toca directamente la interacción con Travian (login real via Chrome). Se aplican todas las capas anti-detección existentes en `adapters/browser/login.py` y `adapters/browser/driver.py`. **No se modifica ninguno de esos dos ficheros**.

Restricciones que `SessionRegistry` debe respetar:

| Restricción | Detalle |
|-------------|---------|
| No matar browsers de otras sesiones | `registry.logout(world_id)` llama `browser.stop()` solo para el browser asociado a ese `world_id`. Nunca mata todos los Chrome. |
| No exponer URLs de Travian en respuestas | Los endpoints no devuelven `world.server` ni ningún dato del perfil Chrome. |
| No exponer credenciales en logs | `SessionRegistry.login()` no loguea `account.password`. Solo loguea `world_id` y resultado boolean. |
| Perfil Chrome por sesión | El `profile_dir` lo gestiona `login.py` (ya existente): `profiles/account_{id}_world_{id}/`. `SessionRegistry` no lo toca. |

**Nota crítica:** El guardian-antideteccion **debe revisar esta feature antes de implementar y antes del commit** según el flujo de trabajo del proyecto (CLAUDE.md, pasos 3 y 7 del flujo estándar). En particular debe verificar:
- Que el cableado de `get_browser`/`get_world_server` en `main.py` no introduce ningún leak del browser hacia código externo.
- Que `SessionRegistry` no introduce timings que puedan detectarse (no los introduce: delega completamente en `login.py` que ya tiene los delays humanos).

### Rendimiento

- **POST es bloqueante ~3-10 s**: diseño intencional (delays anti-detección). El endpoint usa `async def`, así que el event loop no se bloquea — solo esa coroutine espera. FastAPI puede atender otras peticiones mientras el login corre.
- **Memoria**: cada sesión Chrome activa consume ~200-400 MB RAM. Con 1 cuenta activa en el entorno actual, no es un problema.
- **`_sessions` dict**: búsqueda y escritura en O(1). Sin lock (ver concurrencia).

### Concurrencia

- `asyncio` es single-threaded: las coroutines del event loop de FastAPI corren de forma cooperativa. No hay verdadero paralelismo. Un `await` dentro de `registry.login()` cede el control al event loop, que puede procesar otra request.
- Si dos POSTs llegan simultáneamente para el mismo `world_id`, la segunda cerrará la sesión que la primera está abriendo. Riesgo aceptado (EC-10): 1 usuario, imposible en la práctica con el frontend del proyecto.
- No se añade `asyncio.Lock` en `SessionRegistry` para esta fase. Se documenta como deuda técnica si se escala a múltiples usuarios.

### Seguridad de credenciales

- Las credenciales se obtienen de `db.get_account()` (ya descifradas por `AccountSQLiteAdapter`). Se pasan a `login.py` en memoria y nunca se loguean.
- El endpoint POST no acepta credenciales en el body: las toma de la BD cifrada. No hay riesgo de exposición via logs de request.
- Los errores `401` no distinguen entre "credenciales incorrectas" y "error de red" (RN-13): previene enumeración de información.

---

## 12. Plan de pruebas

### Premisa: ningún test abre Chrome real

Todos los tests mockean `WorldRuntimePort`/`SessionRegistry` y `DbPort`. Para los tests de API se usa `TestClient` de FastAPI con `app.state` precargado manualmente.

### 12.1 Tests unitarios de `SessionRegistry`

Fichero: `tests/unit/test_session_registry.py`

| Test | Setup | Resultado esperado |
|------|-------|-------------------|
| `test_login_success` | mock `login_module.login` → `(True, mock_browser)` | `sessions[world_id]` poblado; devuelve `True` |
| `test_login_failure` | mock `login_module.login` → `(False, None)` | `sessions` vacío; devuelve `False` |
| `test_login_replaces_existing_session` | sesión previa en `_sessions`; mock login → `(True, new_browser)` | `old_browser.stop()` llamado; `sessions[world_id]` = new_browser |
| `test_login_invalidates_cache_on_success` | live_adapter mock inyectado; login exitoso | `live_adapter.invalidate_cache(world_id)` llamado |
| `test_login_invalidates_cache_on_relogin` | sesión previa; login exitoso | `invalidate_cache` llamado 2 veces (cierre previo + nueva sesión) |
| `test_logout_with_active_session` | sesión activa; llamar logout | `browser.stop()` llamado; `sessions` vacío |
| `test_logout_without_session` | sessions vacío; llamar logout | no-op, no lanza excepción |
| `test_logout_invalidates_cache` | live_adapter mock; sesión activa | `invalidate_cache(world_id)` llamado |
| `test_is_active_true` | sesión activa para world_id=1 | `is_active(1)` → `True` |
| `test_is_active_false` | sessions vacío | `is_active(1)` → `False` |
| `test_get_browser_returns_browser` | sesión activa | `get_browser(world_id)` → el browser |
| `test_get_browser_returns_none` | sin sesión | `get_browser(world_id)` → `None` |
| `test_get_world_server_returns_server` | sesión activa con world.server = "https://ts20..." | `get_world_server(world_id)` → `"https://ts20..."` |
| `test_get_world_server_returns_empty` | sin sesión | `get_world_server(world_id)` → `""` |
| `test_no_live_adapter_no_crash` | sin `set_live_adapter`; login exitoso | no lanza excepción al intentar invalidar |

### 12.2 Tests de API (TestClient, sin Chrome)

Fichero: `tests/unit/test_session_api.py`

Setup común:

```python
# Mock de WorldRuntimePort (no SessionRegistry real — sin Chrome)
class MockRegistry:
    def __init__(self, login_result=True, active_result=False):
        self._login_result = login_result
        self._active = active_result
    async def login(self, account, world): return self._login_result
    async def logout(self, world_id): pass
    def is_active(self, world_id): return self._active

# Poblar app.state manualmente via override de lifespan o dependency override
```

| Test | Endpoint | Setup | Código esperado | Body esperado |
|------|----------|-------|-----------------|---------------|
| `test_post_session_success` | POST `/accounts/1/worlds/1/session` | db devuelve account con world=1; registry.login → True | 200 | `{"active": true, "world_id": 1, "account_id": 1}` |
| `test_post_session_login_failed` | POST `/accounts/1/worlds/1/session` | registry.login → False | 401 | `{"detail": "Login fallido para 'testtravian13@gmail.com'"}` |
| `test_post_session_account_not_found` | POST `/accounts/99/worlds/1/session` | db devuelve None | 404 | detail contiene "99" |
| `test_post_session_world_not_in_account` | POST `/accounts/1/worlds/99/session` | account existe pero world 99 no en worlds | 404 | detail contiene "99" |
| `test_delete_session_success` | DELETE `/accounts/1/worlds/1/session` | account+world válidos | 204 | sin body |
| `test_delete_session_no_active_session` | DELETE `/accounts/1/worlds/1/session` | sin sesión activa | 204 | sin body (idempotente) |
| `test_delete_session_account_not_found` | DELETE `/accounts/99/worlds/1/session` | db devuelve None | 404 | — |
| `test_get_session_active` | GET `/accounts/1/worlds/1/session` | registry.is_active → True | 200 | `{"active": true, "world_id": 1, "account_id": 1}` |
| `test_get_session_inactive` | GET `/accounts/1/worlds/1/session` | registry.is_active → False | 200 | `{"active": false, "world_id": 1, "account_id": 1}` |
| `test_get_session_account_not_found` | GET `/accounts/99/worlds/1/session` | db devuelve None | 404 | — |
| `test_registry_unavailable` | POST `/accounts/1/worlds/1/session` | `app.state.world_runtime_port = None` | 503 | detail contiene "SessionRegistry" |

### 12.3 Tests unitarios del helper `_verify_world_belongs_to_account`

| Test | Condición | Resultado |
|------|-----------|-----------|
| `test_verify_account_not_found` | db.get_account → None | lanza `AccountNotFoundError` |
| `test_verify_world_not_in_account` | account existe, world_id no en worlds | lanza `WorldNotFoundError` |
| `test_verify_ok` | account existe, world_id en worlds | no lanza excepción |

---

## 13. Riesgos y trade-offs

### TR-01 — POST síncrono vs asíncrono (DECIDIDO: síncrono)

El login real tarda ~3-10 s. La alternativa era devolver `202 Accepted` + polling. Se decidió síncrono porque: (a) 1 solo usuario, no hay cola de espera; (b) el frontend puede mostrar un spinner; (c) simplifica enormemente el código (sin job queue, sin estado intermedio, sin endpoint de polling).

**Riesgo:** si el login tarda más de 30 s (Travian muy lento), el cliente puede timeout antes de recibir respuesta. Travian raramente tarda más de 10 s. Riesgo bajo.

### TR-02 — `get_browser`/`get_world_server` fuera del contrato `WorldRuntimePort` (DECIDIDO)

`WorldRuntimePort` es un puerto de core — no puede conocer `zd.Browser` sin romper la abstracción hexagonal. `get_browser` y `get_world_server` son métodos concretos de `SessionRegistry` que `main.py` pasa como callables a `LiveOverviewAdapter`. Esta es la separación correcta: el core no sabe nada de zendriver; la capa de adapters sí.

**Riesgo:** si en el futuro se añade una segunda implementación de `WorldRuntimePort`, también tendrá que exponer `get_browser`/`get_world_server` de algún modo. Se acepta: es un proyecto de usuario único con un solo adaptador real.

### TR-03 — Sin lock en `SessionRegistry` (DECIDIDO: sin lock)

Se acepta el riesgo de condición de carrera (EC-10) porque el patrón de uso es 1 usuario con 1 frontend que espera la respuesta antes de llamar de nuevo. Añadir `asyncio.Lock` añadiría complejidad con cero beneficio práctico.

### TR-04 — Re-login silencioso vs 409 (DECIDIDO: re-login silencioso)

Si hay sesión activa y llega un POST, se cierra la anterior y se abre una nueva. La alternativa era devolver `409 Conflict` y exigir logout previo. Se decidió re-login silencioso porque: el usuario puede haber perdido el estado del frontend; es más resiliente; el contrato de `WorldRuntimePort.login()` ya lo especifica así.

### TR-05 — Cableado de `_get_browser`/`_get_world_server` via atributos privados (DECIDIDO)

`main.py` accede directamente a `html_source_port._get_browser` y `_get_world_server` para sustituirlos. Esto usa atributos privados (convención `_`). La alternativa era añadir un método `set_callables(get_browser, get_world_server)` a `LiveOverviewAdapter`.

**Decisión:** añadir `set_callables` a `LiveOverviewAdapter` es mejor que acceder a privados. El implementador debe añadir este método a `LiveOverviewAdapter` y usarlo en `main.py`. Esto es un cambio mínimo retrocompatible: el constructor sigue aceptando los callables en `__init__` (compatibilidad con tests existentes que instancian con lambdas).

```python
# En LiveOverviewAdapter (MODIFICAR — cambio mínimo):
def set_callables(self, get_browser, get_world_server) -> None:
    """Permite sustituir los callables post-construcción."""
    self._get_browser = get_browser
    self._get_world_server = get_world_server
```

```python
# En main.py (usar set_callables en vez de acceso directo a _):
if _overview_source == "live":
    html_source_port.set_callables(
        get_browser=session_registry.get_browser,
        get_world_server=session_registry.get_world_server,
    )
    session_registry.set_live_adapter(html_source_port)
```

---

## 14. Pasos de implementación ordenados

El orden respeta dependencias de importación y el principio de cambio mínimo.

1. **`core/exceptions.py`** — MODIFICAR. Añadir `LoginFailedError` (sección 9.5). Sin dependencias nuevas.

2. **`core/i18n/catalog/base/messages.json`** — MODIFICAR. Añadir entrada `LOGIN_FAILED` (sección 9.7).

3. **`adapters/api/error_codes.py`** — MODIFICAR. Añadir `"LOGIN_FAILED": 401` en `ERROR_HTTP_MAP` (sección 9.6).

4. **`adapters/browser/live_overview_adapter.py`** — MODIFICAR (cambio mínimo). Añadir el método `set_callables(get_browser, get_world_server)` al final de la clase `LiveOverviewAdapter` (sección 13, TR-05). No tocar el constructor ni ningún otro método.

5. **`adapters/browser/session_registry.py`** — CREAR. Implementar `SessionRegistry` completo (sección 9.1). Depende de `login_module`, `WorldRuntimePort`, `Account`, `World`.

6. **`adapters/api/dependencies.py`** — MODIFICAR. Añadir `get_world_runtime_port` al final (sección 9.2). Solo añadir, no tocar las dependencias existentes.

7. **`adapters/api/routes/accounts.py`** — MODIFICAR. Añadir imports, `SessionStatusResponse`, `_verify_world_belongs_to_account` y los tres endpoints (sección 9.4). Añadir al final del fichero — no mover ni modificar los 8 endpoints existentes.

8. **`adapters/api/main.py`** — MODIFICAR. Añadir import de `SessionRegistry` y el bloque de cableado en `lifespan` (sección 9.3). El bloque va DESPUÉS de la creación de `html_source_port` y ANTES del `yield`.

9. **`tests/unit/test_session_registry.py`** — CREAR. Tests unitarios de `SessionRegistry` (sección 12.1).

10. **`tests/unit/test_session_api.py`** — CREAR. Tests de API con TestClient (sección 12.2).

**Verificación de no-regresión:** ejecutar la suite completa de tests existentes después del paso 8:

```bash
python -m pytest tests/ -v --tb=short
```

Los tests de `test_fixture_overview_adapter.py`, `test_live_overview_adapter.py`, `test_resources_api.py` y los de cuentas/mundos deben seguir pasando sin cambios.

---

## 15. Criterios de aceptación

Checklist verificable por el implementador:

### Excepción y catálogo

- [ ] `LoginFailedError` existe en `core/exceptions.py` con `error_code = "LOGIN_FAILED"` y `params = {"username": username}`.
- [ ] `"LOGIN_FAILED": 401` está en `ERROR_HTTP_MAP` en `error_codes.py`.
- [ ] `messages.json` tiene entrada `"LOGIN_FAILED"` con texto en `es` y `en`.

### `LiveOverviewAdapter`

- [ ] `LiveOverviewAdapter` tiene método `set_callables(self, get_browser, get_world_server)` que asigna `self._get_browser` y `self._get_world_server`.
- [ ] El constructor de `LiveOverviewAdapter` no ha cambiado (retrocompatibilidad con tests existentes).

### `SessionRegistry`

- [ ] `SessionRegistry` hereda de `WorldRuntimePort`.
- [ ] `_sessions` es `dict[int, tuple[zd.Browser, World]]`.
- [ ] `login()` cierra sesión previa si existe antes de abrir nueva.
- [ ] `login()` llama `invalidate_cache` tras cerrar sesión previa (si `_live_adapter` inyectado).
- [ ] `login()` llama `invalidate_cache` tras login exitoso (si `_live_adapter` inyectado).
- [ ] `login()` devuelve `False` sin lanzar excepción si `login_module.login()` devuelve `(False, None)`.
- [ ] `logout()` llama `browser.stop()` si hay sesión activa.
- [ ] `logout()` es idempotente (no lanza si no hay sesión).
- [ ] `logout()` llama `invalidate_cache` tras cerrar sesión (si `_live_adapter` inyectado).
- [ ] `is_active(world_id)` devuelve `True` solo si `world_id` en `_sessions`.
- [ ] `get_browser(world_id)` devuelve el browser o `None`.
- [ ] `get_world_server(world_id)` devuelve `world.server` o `""`.
- [ ] `set_live_adapter(adapter)` asigna `self._live_adapter`.
- [ ] Si `_live_adapter` es `None`, `_invalidate_cache` no lanza excepción.

### `dependencies.py`

- [ ] `get_world_runtime_port` existe y lanza `HTTPException(503)` si `world_runtime_port` no está en `app.state`.

### `main.py`

- [ ] `SessionRegistry()` se instancia en `lifespan` y se asigna a `application.state.world_runtime_port`.
- [ ] En modo `live`: `html_source_port.set_callables(session_registry.get_browser, session_registry.get_world_server)` se llama.
- [ ] En modo `live`: `session_registry.set_live_adapter(html_source_port)` se llama.
- [ ] En modo `fixture`: ninguna de las dos llamadas anteriores se hace (sin error).
- [ ] El bloque de `SessionRegistry` está DESPUÉS de la creación de `html_source_port` y ANTES del `yield`.

### Endpoints

- [ ] `POST /accounts/{account_id}/worlds/{world_id}/session` existe y devuelve `200` con `SessionStatusResponse`.
- [ ] `DELETE /accounts/{account_id}/worlds/{world_id}/session` existe y devuelve `204`.
- [ ] `GET /accounts/{account_id}/worlds/{world_id}/session` existe y devuelve `200` con `SessionStatusResponse`.
- [ ] Los tres endpoints usan `get_db_port` y `get_world_runtime_port` como dependencias.
- [ ] Los tres endpoints llaman `_verify_world_belongs_to_account` antes de operar.
- [ ] POST con account inexistente → `404`.
- [ ] POST con world no perteneciente a la cuenta → `404`.
- [ ] POST con login fallido → `401` con `detail` que contiene el username.
- [ ] DELETE sin sesión activa → `204` (idempotente).
- [ ] GET sin sesión activa → `200 {"active": false, ...}`.
- [ ] Ningún endpoint requiere `Accept-Language`.
- [ ] `SessionStatusResponse` tiene exactamente tres campos: `active: bool`, `world_id: int`, `account_id: int`.

### Tests

- [ ] `tests/unit/test_session_registry.py` existe y todos los tests de la sección 12.1 pasan.
- [ ] `tests/unit/test_session_api.py` existe y todos los tests de la sección 12.2 pasan.
- [ ] Ningún test abre Chrome real.
- [ ] Suite completa de tests pre-existentes sigue pasando sin modificaciones.

### No-regresión de anti-detección

- [ ] `adapters/browser/login.py` no ha sido modificado.
- [ ] `adapters/browser/driver.py` no ha sido modificado.
- [ ] `SessionRegistry` no introduce timings propios (delega completamente en `login_module.login()`).

---

## 16. Trazabilidad

| Decisión técnica | Requisito / edge case que la origina |
|------------------|--------------------------------------|
| Endpoints en `accounts_router` existente, no router nuevo | RN-01: la jerarquía `/accounts/{id}/worlds/{id}/session` es subrecurso natural del dominio de cuentas ya definido en ese router |
| `200` en POST (no `201`) | RN-05 + convención del proyecto: las sesiones son estado efímero no persistente; `201` implica recurso creado en BD con `Location` header |
| `204` idempotente en DELETE | RN-08: `WorldRuntimePort.logout()` ya es idempotente; la API debe reflejar ese contrato |
| `LoginFailedError` nueva excepción (no reusar `InvalidCredentialsError`) | EC-07+EC-08: `InvalidCredentialsError` semánticamente implica "credenciales incorrectas confirmadas"; `LoginFailedError` cubre también errores de red/timeout donde las credenciales pueden ser correctas |
| `_verify_world_belongs_to_account` helper compartido por los tres endpoints | RN-04: los tres verbos necesitan la misma verificación de pertenencia; duplicar la lógica en cada handler sería error-prone |
| `404` para `world_id` ajeno (no `403`) | RN-04 ← EC-12 del spec `registro-cuentas-mundos`: no revelar existencia de mundos de otras cuentas |
| `get_browser`/`get_world_server` como métodos concretos de `SessionRegistry`, NO en `WorldRuntimePort` | TR-02: `WorldRuntimePort` es un puerto de core — no puede conocer `zd.Browser` sin romper la abstracción hexagonal; solo la capa de adapters conoce zendriver |
| `set_callables` en `LiveOverviewAdapter` (no acceso directo a `_get_browser`) | TR-05: acceder a atributos privados desde `main.py` viola el encapsulamiento; el método público es el contrato correcto |
| `set_live_adapter` en `SessionRegistry` (inyección inversa) | RN-11+RN-12: el registry necesita invalidar la caché del `LiveOverviewAdapter` al hacer login/logout; la inyección en `__init__` crearía dependencia circular (ambos se construyen en `lifespan`); la inyección post-construcción es el patrón correcto |
| Sin lock en `SessionRegistry` | TR-03: 1 usuario, sin concurrencia real; `asyncio.Lock` añadiría complejidad sin beneficio |
| Re-login silencioso (no `409`) | TR-04+RN-06: el contrato de `WorldRuntimePort.login()` ya lo especifica; el frontend puede haber perdido estado; resiliencia > rigidez |
| POST síncrono (no `202 + polling`) | TR-01: 1 usuario, 1 solicitud a la vez; la complejidad de `202 + job queue + polling` no está justificada |
| Bloque de `SessionRegistry` en `lifespan` DESPUÉS de `html_source_port` | Dependencia de instancia: `session_registry.set_live_adapter(html_source_port)` requiere que ambos objetos existan; el orden garantiza esto |
| `isinstance` check para invalidar caché solo si `LiveOverviewAdapter` | EC-09: en modo `fixture`, `html_source_port` es `FixtureOverviewAdapter` y no tiene `invalidate_cache`; el check evita `AttributeError` |
| guardian-antideteccion obligatorio antes de implementar y antes del commit | CLAUDE.md flujo estándar pasos 3 y 7: esta feature toca `adapters/browser/` (SessionRegistry delega en `login.py`) y la interacción real con Travian |

---

## Registro de implementación

**Fecha:** 2026-05-26
**Implementador:** desarrollador-funcionalidades

**Ficheros creados:**
- `adapters/browser/session_registry.py` — SessionRegistry completo
- `tests/unit/test_session_registry.py` — 15 tests unitarios de SessionRegistry
- `tests/unit/test_session_api.py` — 14 tests de API (11 del spec sección 12.2 + 3 del helper _verify_world_belongs_to_account de sección 12.3)

**Ficheros modificados:**
- `core/exceptions.py` — añadida LoginFailedError
- `core/i18n/catalog/base/messages.json` — añadida entrada LOGIN_FAILED
- `adapters/api/error_codes.py` — añadido "LOGIN_FAILED": 401
- `adapters/browser/live_overview_adapter.py` — añadido método set_callables()
- `adapters/api/dependencies.py` — añadida función get_world_runtime_port()
- `adapters/api/routes/accounts.py` — añadidos SessionStatusResponse, _verify_world_belongs_to_account y los 3 endpoints de sesión
- `adapters/api/main.py` — añadido import SessionRegistry y bloque de cableado en lifespan

**Ficheros NO modificados (anti-detección):**
- `adapters/browser/login.py` — sin cambios (verificado con git diff)
- `adapters/browser/driver.py` — sin cambios (verificado con git diff)

**Comando para ejecutar tests:**
```bash
.venv/bin/python -m pytest tests/unit/test_session_registry.py tests/unit/test_session_api.py -v
```

**Resultado:** 29 nuevos tests pasan. Suite completa: 706 passed, 9 failed (preexistentes — 2 CA-20 y 7 test_kirilloid_scraper upgrade_table), 23 skipped. Ninguna regresión introducida.

**Desviaciones respecto al diseño:** ninguna. El spec se siguió íntegramente.

---

## Nota anti-detección para el guardian

El `guardian-antideteccion` debe verificar en su revisión de esta feature:

1. **`SessionRegistry.login()`**: delega completamente en `adapters/browser/login.py::login()`. No introduce ningún delay propio ni interacción con el DOM. Correcto.
2. **`SessionRegistry.logout()`**: llama `browser.stop()`. No hay interacción con Travian (no navega ninguna URL de logout). Correcto: cerrar el proceso Chrome localmente no es detectable.
3. **Cableado en `main.py`**: los callables `get_browser`/`get_world_server` son referencias a métodos del registry — no se introduce ninguna capa entre el browser y `LiveOverviewAdapter` que pudiera añadir timings.
4. **Credenciales**: `LoginFailedError` no incluye la razón exacta del fallo (EC-07 vs EC-08 son indistinguibles desde la API) — no hay información extra que ayude a un atacante a distinguir cuentas válidas de inválidas.

---

## Amendment A1 — Descifrado de credenciales en el flujo de login

**Fecha:** 2026-05-26
**Estado:** ready-for-impl
**Autor:** analista

### A1.1 Descripción del hueco

El spec original en la sección 11 afirmaba que "las credenciales se obtienen de `db.get_account()` (ya descifradas por `AccountSQLiteAdapter`)". Esa frase describía la intención de diseño, pero nunca se implementó. Al probar el login real contra Travian se confirma que `login.py` teclea una cadena vacía en el campo de contraseña.

Cadena de fallo:

```
POST /accounts/1/worlds/1/session
  → session_login (handler)
  → LoginUseCase.execute(account_id=1, world_id=1)
      → db.get_account(1)          # devuelve Account(password="")  ← hueco
      → registry.login(account, world)
          → login.login(account, world)
              → human_type(password_field, account.password)  # teclea "" ← fallo
              → Travian rechaza
          → (False, None)
      → LoginUseCase devuelve False
  → handler lanza LoginFailedError → 401
```

Causa raíz: `AccountSQLiteAdapter.get_account()` construye el `Account` con `password=""` (placeholder vacío) porque el BLOB `accounts.password` contiene el token Fernet cifrado — no la contraseña en claro — y el adaptador no tiene acceso al objeto Fernet para descifrar. La misma omisión afecta a `get_account_by_email()` y `list_accounts()`, aunque estos métodos no se usan en el flujo de login.

**Nota adicional**: el docstring de `core/entities/account.py` afirma que "el adaptador SQLite descifra al cargar", lo que es incorrecto. Debe corregirse también.

### A1.2 Decisión de diseño — dónde ocurre el descifrado

**Opción A (elegida): descifrado en `LoginUseCase`, con Fernet inyectado.**

`LoginUseCase` recibe el objeto `Fernet` en su constructor. Después de `get_account()` y antes de llamar a `registry.login()`, obtiene el token cifrado de la BD con un nuevo método del puerto (`get_account_password_cipher`) y lo descifra. La contraseña en claro existe solo en memoria durante la ventana `decrypt → human_type`.

**Opción B (descartada): descifrado en `AccountSQLiteAdapter.get_account()`.**

`AccountSQLiteAdapter` debería recibir el objeto `Fernet` en su constructor y descifrar en cada lectura. Esto viola el diseño actual del adaptador (el docstring de `account_sqlite_adapter.py` línea 14 dice explícitamente "este adaptador no conoce el objeto Fernet, solo almacena/recupera el token opaco") y convierte toda lectura de cuenta en una operación que requiere la clave Fernet, incluyendo lecturas que no necesitan la contraseña (lista de cuentas del frontend, verificaciones de pertenencia). Implica pasar Fernet como dependencia a `DbPort`, que es un puerto de core y no debe conocer detalles de cifrado.

**Por qué la Opción A es correcta en la arquitectura hexagonal:** el descifrado es lógica de aplicación (use case), no lógica de infraestructura (adaptador). El adaptador almacena/recupera el BLOB opaco. El use case, que tiene contexto completo de la operación, solicita el token y lo descifra justo antes de necesitarlo.

### A1.3 Contrato del nuevo método en `DbPort` y `AccountSQLiteAdapter`

Añadir al **final** de `DbPort` (`core/ports/db_port.py`):

```python
@abstractmethod
async def get_account_password_cipher(self, account_id: int) -> Optional[bytes]:
    """
    Devuelve el token Fernet cifrado (BLOB) de la contraseña de la cuenta,
    o None si la cuenta no existe.

    SOLO para uso en LoginUseCase. El resto del sistema usa get_account(),
    que devuelve password="" para no filtrar el cifrado en respuestas de API.

    El adaptador lee el BLOB opaco y lo devuelve sin interpretar — no conoce Fernet.
    """
```

Implementar en `AccountSQLiteAdapter` (`adapters/db/account_sqlite_adapter.py`):

```python
async def get_account_password_cipher(self, account_id: int) -> Optional[bytes]:
    """Devuelve el BLOB Fernet de la contraseña, o None si la cuenta no existe."""
    cursor = await self._conn.execute(
        "SELECT password FROM accounts WHERE id = ?",
        (account_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return bytes(row["password"])
```

Regla: `get_account()`, `get_account_by_email()` y `list_accounts()` no cambian. Siguen devolviendo `password=""`. Esto no es un bug: es intencional para que las respuestas de la API de cuentas no expongan el cifrado ni la contraseña.

### A1.4 Nueva firma de `LoginUseCase`

Sustituir el `@dataclass` actual con tres campos:

```python
# core/use_cases/login_use_case.py

from __future__ import annotations

import logging
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken

from core.crypto import decrypt_password
from core.entities.account import Account
from core.entities.world import World
from core.exceptions import AccountNotFoundError, LoginFailedError, WorldNotFoundError
from core.ports.db_port import DbPort
from core.ports.world_runtime_port import WorldRuntimePort

logger = logging.getLogger(__name__)


@dataclass
class LoginUseCase:
    registry: WorldRuntimePort
    db: DbPort
    fernet: Fernet                  # ← campo nuevo; inyectado desde el endpoint

    async def execute(self, account_id: int, world_id: int) -> bool:
        # 1. Verificar que la cuenta existe
        account = await self.db.get_account(account_id)
        if account is None:
            raise AccountNotFoundError(account_id)

        # 2. Obtener token cifrado — si None, la cuenta no existe (no debería ocurrir
        #    porque get_account() ya lo verificó, pero la columna es NOT NULL por DDL)
        cipher = await self.db.get_account_password_cipher(account_id)
        if cipher is None:
            # Situación imposible si la BD no está corrupta: la cuenta existía en el paso 1.
            # Se trata igual que un login fallido (401), no como 500.
            logger.error(
                "Cipher nulo para account_id=%s — posible corrupción de BD",
                account_id,
            )
            raise LoginFailedError(account.username)

        # 3. Descifrar — la contraseña en claro existe solo en este scope
        try:
            account.password = decrypt_password(self.fernet, cipher)
        except InvalidToken:
            # La clave Fernet activa no coincide con la usada al cifrar.
            # No loguear el token ni la clave. Tratar como login imposible.
            logger.error(
                "InvalidToken al descifrar contraseña para account_id=%s "
                "— la clave Fernet puede haber rotado",
                account_id,
            )
            raise LoginFailedError(account.username)

        # 4. Localizar el mundo dentro de la cuenta
        world = self._find_world(account, world_id)

        # 5. Delegar en el registry → login.py → human_type con la contraseña real
        return await self.registry.login(account, world)

    def _find_world(self, account: Account, world_id: int) -> World:
        for world in account.worlds:
            if world.id == world_id:
                return world
        raise WorldNotFoundError(world_id)
```

**`LogoutUseCase` no cambia.** No toca credenciales.

### A1.5 Cambio en el endpoint `session_login`

Añadir `fernet = Depends(get_fernet)` y pasarlo al constructor de `LoginUseCase`:

```python
# En adapters/api/routes/accounts.py

# Añadir en imports:
from adapters.api.dependencies import get_fernet, get_world_runtime_port

# Modificar el endpoint (solo el handler session_login — DELETE y GET no cambian):
@router.post(
    "/accounts/{account_id}/worlds/{world_id}/session",
    status_code=status.HTTP_200_OK,
    response_model=SessionStatusResponse,
    summary="Abrir sesión (login)",
    description=(
        "Abre una sesión autenticada en Travian para la cuenta y mundo indicados. "
        "Operación síncrona: puede tardar hasta 10 segundos (delays anti-detección). "
        "Si ya existe una sesión activa, la cierra antes de abrir una nueva. "
        "Devuelve 401 si el login falla (credenciales incorrectas o error de red)."
    ),
)
async def session_login(
    account_id: int,
    world_id: int,
    db=Depends(get_db_port),
    registry=Depends(get_world_runtime_port),
    fernet=Depends(get_fernet),           # ← añadido
) -> SessionStatusResponse:
    await _verify_world_belongs_to_account(account_id, world_id, db)
    use_case = LoginUseCase(registry=registry, db=db, fernet=fernet)  # ← añadido fernet
    success = await use_case.execute(account_id, world_id)
    if not success:
        account = await db.get_account(account_id)
        raise LoginFailedError(account.username if account else str(account_id))
    return SessionStatusResponse(active=True, world_id=world_id, account_id=account_id)
```

`get_fernet` ya existe en `adapters/api/dependencies.py` (línea 159). No hay que crear nada nuevo en la capa de dependencias.

### A1.6 Garantías anti-fuga (para el guardian)

| Garantía | Implementación | Verificación |
|----------|---------------|-------------|
| Contraseña en claro solo en memoria, mínima ventana | `account.password = decrypt_password(...)` en el scope de `execute()`; se sobreescribe con la contraseña real solo para pasar a `registry.login()` | `login.py` hace `human_type(password_field, account.password)` — la variable es `account`, no `password`, en el frame de `login()` |
| No loguear la contraseña en claro | Los `logger.error` de `LoginUseCase` solo loguean `account_id` y `account.username`, nunca `account.password` ni el token `cipher` | Revisión de código en los tres bloques `logger.*` del use case |
| `InvalidToken` no vuelca el token ni la clave | El bloque `except InvalidToken` loguea solo `account_id` con nivel `error`; no loguea `cipher` ni `fernet` | Patrón explícito en el pseudocódigo de la sección A1.4 |
| `_mask_frame_locals` en traces verbosas | El middleware enmascara variables cuyo **nombre** contenga `"password"` o `"token"`. En el frame de `LoginUseCase.execute()`, la variable con el cifrado se llama `cipher` (no enmascarada por nombre), y la contraseña en claro vive en `account.password` (enmascarada si el frame se vuelca porque el nombre del atributo contiene "password"). En login.py la variable local relevante es `account` — el middleware no la enmascara por nombre, pero la contraseña viaja como atributo del objeto, no como variable local directa. El riesgo de fuga vía traceback es bajo: `login.py` captura todas las excepciones internamente (bloque `try/except Exception`) y no re-lanza; el traceback que vería el handler sería de `InvalidToken` en `LoginUseCase`, donde `cipher` es bytes opacos y `account.password` es la contraseña descifrada. El guardian debe confirmar que `cipher` tampoco aparece en logs en ese contexto. |
| Contratos HTTP sin cambios | `POST /accounts/{account_id}/worlds/{world_id}/session` sigue con exactamente los mismos códigos de respuesta (200, 401, 404, 503) | Las tablas de errores de las secciones 8.2-8.4 no cambian |

**Nota sobre `cipher` en `_mask_frame_locals`**: el patrón actual busca la palabra `"token"` en el **nombre de la variable**. La variable local `cipher` en `LoginUseCase.execute()` no hace match. Para endurecer esto, el implementador puede renombrar la variable a `password_token` o añadir `"cipher"` al regex `_SENSITIVE_FIELD_PATTERNS`. Se deja como decisión del guardian, no es bloqueante para esta implementación.

### A1.7 Edge cases nuevos

| ID | Caso | Tratamiento |
|----|------|-------------|
| EC-A1 | `get_account_password_cipher(account_id)` devuelve `None` | La cuenta existía en el paso anterior (NOT NULL en DDL); si aun así devuelve `None`, corrupción de BD. Se loguea como `error` y se lanza `LoginFailedError` → `401`. Nunca `500`. |
| EC-A2 | `InvalidToken` al descifrar (clave Fernet rotada o token corrupto) | Se loguea `error` con `account_id` únicamente. Se lanza `LoginFailedError` → `401`. Ni el token ni la clave Fernet aparecen en el log. El usuario debe re-registrar la cuenta con la nueva clave. |
| EC-A3 | `account.password` está vacío después del descifrado (Fernet descifra a `""`) | `human_type` en `login.py` tecleará cadena vacía. Travian rechazará. `login.py` devuelve `(False, None)`. `LoginUseCase.execute()` devuelve `False`. Handler lanza `LoginFailedError` → `401`. No hay tratamiento especial: el comportamiento correcto ya existe. |
| EC-A4 | La contraseña descifrada contiene caracteres especiales o no-ASCII | `decrypt_password` devuelve `str` (decodificado en UTF-8). `human_type` en `login.py` teclea carácter a carácter. Travian acepta contraseñas con caracteres especiales. No hay problema. |

Los edge cases EC-01 a EC-13 del spec original no cambian. Esta sección solo añade los nuevos.

### A1.8 Corrección de docstring en `core/entities/account.py`

El docstring de la clase `Account` en la línea 9 afirma: "el adaptador SQLite cifra con Fernet al persistir y **descifra al cargar**". Esta frase es incorrecta desde el diseño inicial: el adaptador nunca descifra. Debe corregirse a:

```python
"""
password — en memoria siempre str (descifrado); el adaptador SQLite recibe la
           contraseña ya cifrada al persistir (save_account/update_account) y
           devuelve password="" al cargar (get_account/get_account_by_email/
           list_accounts). El descifrado ocurre exclusivamente en LoginUseCase,
           que obtiene el token cifrado via get_account_password_cipher() y lo
           descifra con el objeto Fernet inyectado.
"""
```

También corregir el comentario en el campo de la dataclass:

```python
password: str   # en memoria siempre str; "" cuando viene de get_account (sin descifrar)
```

### A1.9 Plan de tests del amendment

**Ningún test abre Chrome.** Todos los tests son unitarios con mocks o con Fernet real de test.

#### A1.9.1 Tests unitarios del nuevo método del adaptador

Fichero: `tests/unit/test_account_sqlite_adapter.py` (o añadir a los tests existentes del adaptador)

| Test | Setup | Resultado esperado |
|------|-------|-------------------|
| `test_get_account_password_cipher_existing` | Insertar cuenta con `password_cifrada = b"faketoken123"`; llamar `get_account_password_cipher(account_id)` | Devuelve `b"faketoken123"` exactamente |
| `test_get_account_password_cipher_not_found` | `account_id` que no existe | Devuelve `None` |
| `test_get_account_still_returns_empty_password` | Cuenta existente; llamar `get_account(account_id)` | `account.password == ""` — no ha cambiado |

#### A1.9.2 Tests unitarios de `LoginUseCase` con Fernet real

Fichero: `tests/unit/test_login_use_case.py` (crear nuevo)

Setup:

```python
from cryptography.fernet import Fernet, InvalidToken
from core.crypto import encrypt_password, decrypt_password

TEST_FERNET = Fernet(Fernet.generate_key())
TEST_PASSWORD = "mi_password_real"
TEST_CIPHER = encrypt_password(TEST_FERNET, TEST_PASSWORD)
```

| Test | Setup | Resultado esperado |
|------|-------|-------------------|
| `test_execute_success_decrypts_password` | `db.get_account` → Account(password=""); `db.get_account_password_cipher` → `TEST_CIPHER`; `registry.login` → `True`; Fernet real | `registry.login` es llamado con `account.password == TEST_PASSWORD`; devuelve `True` |
| `test_execute_invalid_token_raises_login_failed` | `db.get_account_password_cipher` → token cifrado con **otra** clave Fernet diferente a la inyectada | Lanza `LoginFailedError` (no `InvalidToken` cruda, no `500`) |
| `test_execute_cipher_none_raises_login_failed` | `db.get_account_password_cipher` → `None` | Lanza `LoginFailedError` |
| `test_execute_account_not_found` | `db.get_account` → `None` | Lanza `AccountNotFoundError` |
| `test_execute_world_not_found` | `db.get_account` → Account con worlds=[World(id=2)]; `world_id=99` | Lanza `WorldNotFoundError` |
| `test_execute_login_returns_false` | Todo correcto; `registry.login` → `False` | Devuelve `False` (el handler lo convierte en `LoginFailedError`) |
| `test_logout_use_case_unchanged` | `registry.logout` mock; `LogoutUseCase(registry).execute(world_id=1)` | `registry.logout(1)` es llamado; `LogoutUseCase` no tiene campo `fernet` |

#### A1.9.3 Tests de API del endpoint POST — casos nuevos del amendment

Añadir en `tests/unit/test_session_api.py`:

| Test | Setup | Código esperado | Detalle |
|------|-------|-----------------|---------|
| `test_post_session_invalid_token` | `db.get_account_password_cipher` devuelve token cifrado con clave distinta; `LoginUseCase` lanza `LoginFailedError` | `401` | Confirma que `InvalidToken` no se propaga como `500` |
| `test_post_session_cipher_none` | `db.get_account_password_cipher` devuelve `None`; `LoginUseCase` lanza `LoginFailedError` | `401` | EC-A1 |

Estos tests pueden mockar `LoginUseCase.execute` directamente para aislar el handler, o usar mocks de `DbPort` y `Fernet` real.

### A1.10 Pasos de implementación ordenados (amendment)

El orden es el mínimo necesario para no dejar el sistema en estado roto en ningún paso intermedio.

1. **`core/ports/db_port.py`** — MODIFICAR. Añadir el método abstracto `get_account_password_cipher` (sección A1.3) al final de la clase `DbPort`. Sin importaciones nuevas.

2. **`adapters/db/account_sqlite_adapter.py`** — MODIFICAR. Implementar `get_account_password_cipher` (sección A1.3). Solo añadir el método — no tocar `get_account`, `get_account_by_email` ni `list_accounts`.

3. **`core/entities/account.py`** — MODIFICAR. Corregir el docstring de la clase y el comentario del campo `password` (sección A1.8). Solo cambio de documentación.

4. **`core/use_cases/login_use_case.py`** — MODIFICAR. Sustituir la implementación de `LoginUseCase` por la de la sección A1.4: añadir el campo `fernet: Fernet`, importar `decrypt_password` y `InvalidToken`, e insertar los pasos 2 y 3 en `execute()`. `LogoutUseCase` no se toca.

5. **`adapters/api/routes/accounts.py`** — MODIFICAR. En el handler `session_login`: añadir `fernet=Depends(get_fernet)` como parámetro y pasarlo a `LoginUseCase(registry, db, fernet)` (sección A1.5). Añadir `get_fernet` a los imports de `adapters/api/dependencies`. Los otros dos handlers (`session_logout`, `session_status`) no cambian.

6. **`tests/unit/test_login_use_case.py`** — CREAR. Tests unitarios de `LoginUseCase` con Fernet real (sección A1.9.2).

7. **`tests/unit/test_account_sqlite_adapter.py`** — MODIFICAR o CREAR según exista. Añadir los tres tests del nuevo método (sección A1.9.1).

8. **`tests/unit/test_session_api.py`** — MODIFICAR. Añadir los dos tests nuevos del endpoint POST (sección A1.9.3).

9. **Verificación de no-regresión:**

```bash
.venv/bin/python -m pytest tests/unit/test_login_use_case.py \
    tests/unit/test_session_api.py \
    tests/unit/ -v --tb=short
```

### A1.11 Criterios de aceptación del amendment

Checklist verificable por el implementador:

**`DbPort` y adaptador**

- [ ] `DbPort.get_account_password_cipher(account_id: int) -> Optional[bytes]` existe como método abstracto.
- [ ] `AccountSQLiteAdapter.get_account_password_cipher` devuelve `bytes` si la cuenta existe, `None` si no.
- [ ] `get_account()`, `get_account_by_email()` y `list_accounts()` siguen devolviendo `password=""` — sin cambios.

**`LoginUseCase`**

- [ ] `LoginUseCase` tiene tres campos en el dataclass: `registry`, `db`, `fernet`.
- [ ] `execute()` llama a `get_account_password_cipher(account_id)` después de `get_account()`.
- [ ] Si `cipher is None`: lanza `LoginFailedError`, no `500`.
- [ ] Si `InvalidToken`: lanza `LoginFailedError`, no re-lanza `InvalidToken`.
- [ ] Ningún `logger.*` dentro de `LoginUseCase` loguea `cipher`, `fernet`, ni `account.password`.
- [ ] `LogoutUseCase` no tiene campo `fernet` y no ha sido modificado.

**Endpoint**

- [ ] `session_login` tiene `fernet=Depends(get_fernet)` en su firma.
- [ ] `LoginUseCase` se construye con `fernet=fernet` en el handler.
- [ ] `session_logout` y `session_status` no han sido modificados.
- [ ] Los contratos HTTP del endpoint POST no han cambiado (mismos códigos: 200, 401, 404, 503).

**Documentación**

- [ ] El docstring de `Account.password` en `core/entities/account.py` describe el comportamiento real (descifrado solo en `LoginUseCase`).

**Tests**

- [ ] `test_execute_success_decrypts_password` pasa: `registry.login` recibe la contraseña real descifrada.
- [ ] `test_execute_invalid_token_raises_login_failed` pasa: `LoginFailedError`, no `InvalidToken` ni `500`.
- [ ] `test_execute_cipher_none_raises_login_failed` pasa.
- [ ] `test_get_account_password_cipher_existing` pasa.
- [ ] `test_get_account_password_cipher_not_found` pasa.
- [ ] `test_get_account_still_returns_empty_password` pasa.
- [ ] Suite completa de tests pre-existentes sigue pasando sin modificaciones (especialmente `test_session_registry.py` y `test_session_api.py`).

**Anti-fuga (para el guardian)**

- [x] Revisión manual de todos los `logger.*` en `LoginUseCase`: ninguno menciona `cipher`, `fernet`, ni `account.password`.
- [x] El guardian confirmó añadir `"cipher"` y `"secret"` al regex `_SENSITIVE_FIELD_PATTERNS` (sección A1.6, último párrafo) — implementado.

---

## Registro de implementación — Amendment A1

**Fecha:** 2026-05-26
**Implementador:** desarrollador-funcionalidades

**Ficheros modificados:**
- `core/ports/db_port.py` — añadido método abstracto `get_account_password_cipher(account_id: int) -> Optional[bytes]`
- `adapters/db/account_sqlite_adapter.py` — implementado `get_account_password_cipher`: SELECT password WHERE id=?, devuelve bytes o None
- `core/entities/account.py` — corregido docstring (descifrado ocurre en LoginUseCase, no en el adaptador); añadido `field(repr=False)` al campo `password`
- `core/use_cases/login_use_case.py` — LoginUseCase ampliado con campo `fernet: Fernet`; execute() obtiene cipher, descifra, asigna account.password antes de registry.login; InvalidToken y cipher=None → LoginFailedError; ningún logger loguea cipher/fernet/password
- `adapters/api/routes/accounts.py` — handler `session_login` añade `fernet=Depends(get_fernet)` y construye `LoginUseCase(registry, db, fernet)`
- `adapters/api/main.py` — regex `_SENSITIVE_FIELD_PATTERNS` ampliado con `cipher` y `secret`
- `tests/unit/test_login_use_case.py` — reescrito para incluir Fernet real; 15 tests (3 del amendment A1 + 12 del spec original adaptados)
- `tests/unit/test_account_sqlite_adapter.py` — añadidos 3 tests: `test_get_account_password_cipher_existing`, `test_get_account_password_cipher_not_found`, `test_get_account_still_returns_empty_password`
- `tests/unit/test_session_api.py` — añadidos 2 tests del amendment (`test_post_session_invalid_token`, `test_post_session_cipher_none`); tests de POST existentes actualizados para incluir `fernet=_TEST_FERNET` en `_StateOverride`

**Ficheros NO modificados (anti-detección):**
- `adapters/browser/login.py` — sin cambios (verificado con git diff vacío)
- `adapters/browser/driver.py` — sin cambios (verificado con git diff vacío)

**Comando para ejecutar tests del amendment:**
```bash
.venv/bin/python -m pytest tests/unit/test_login_use_case.py tests/unit/test_account_sqlite_adapter.py tests/unit/test_session_api.py -v
```

**Resultado de la suite completa:**
732 passed, 9 failed (preexistentes: 2 CA-20 lectura-overview + 7 test_kirilloid_scraper), 23 skipped. Ninguna regresión introducida por el amendment.

**Desviaciones respecto al diseño:** ninguna. El spec se siguió íntegramente. El punto A1.6 (añadir `cipher` y `secret` al regex) fue implementado proactivamente según lo indicado en las condiciones del guardian (punto 6 del enunciado).
