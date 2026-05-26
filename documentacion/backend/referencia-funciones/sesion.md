# Referencia de funciones — Feature de sesión

Módulos: `adapters/browser/session_registry.py`, `core/use_cases/login_use_case.py`,
`core/ports/world_runtime_port.py`, `core/ports/db_port.py`,
`adapters/db/account_sqlite_adapter.py`, `adapters/api/dependencies.py`

Documento de código completo: [`../sesion.md`](../sesion.md)
Referencia de API: [`../../api/sesion.md`](../../api/sesion.md)

---

## `WorldRuntimePort` — `core/ports/world_runtime_port.py`

Puerto abstracto. El core solo conoce esta interfaz.

| Método | Firma | Devuelve | Descripción |
|--------|-------|----------|-------------|
| `login` | `async (account: Account, world: World)` | `bool` | Abre sesión autenticada. Si ya existe sesión para `world.id`, la cierra antes. `True` = éxito; `False` = fallo (browser ya cerrado por `login_module`). |
| `logout` | `async (world_id: int)` | `None` | Cierra la sesión activa. Idempotente: no lanza si no hay sesión. |
| `is_active` | `(world_id: int)` | `bool` | `True` si hay sesión activa. Sincrónico. O(1). |

---

## `SessionRegistry` — `adapters/browser/session_registry.py`

Implementa `WorldRuntimePort`. Singleton en `app.state.world_runtime_port`.

Estado interno: `_sessions: dict[int, tuple[zd.Browser, World]]` (keyed por `world_id`).

| Método | Firma | Devuelve | Descripción |
|--------|-------|----------|-------------|
| `__init__` | `()` | — | Inicializa `_sessions = {}` y `_live_adapter = None`. |
| `set_live_adapter` | `(adapter)` | `None` | Inyecta ref a `LiveOverviewAdapter`. Llamar desde `lifespan` después de construir ambos objetos. |
| `login` | `async (account, world)` | `bool` | Cierra sesión previa si existe → `login_module.login(account, world)` → guarda en `_sessions` si éxito → `_invalidate_cache` (dos veces en re-login). |
| `logout` | `async (world_id)` | `None` | Si hay sesión: `browser.stop()` + elimina entrada + `_invalidate_cache`. Si no hay sesión: no-op. |
| `is_active` | `(world_id)` | `bool` | `world_id in self._sessions`. |
| `get_browser` | `(world_id)` | `zd.Browser | None` | Browser activo para `world_id`, o `None`. No forma parte de `WorldRuntimePort`. Se pasa como callable a `LiveOverviewAdapter`. |
| `get_world_server` | `(world_id)` | `str` | `world.server` para `world_id`, o `""`. No forma parte de `WorldRuntimePort`. |
| `_invalidate_cache` | `(world_id)` | `None` | Llama `_live_adapter.invalidate_cache(world_id)` si `_live_adapter` no es `None`. No-op en modo fixture o tests. |

---

## `LoginUseCase` — `core/use_cases/login_use_case.py`

Dataclass con tres campos: `registry: WorldRuntimePort`, `db: DbPort`, `fernet: Fernet`.

| Método | Firma | Devuelve | Descripción |
|--------|-------|----------|-------------|
| `execute` | `async (account_id: int, world_id: int)` | `bool` | 1) `get_account` → `AccountNotFoundError` si None. 2) `get_account_password_cipher` → `LoginFailedError` si None. 3) `decrypt_password(fernet, cipher)` → `LoginFailedError` si `InvalidToken`. 4) `_find_world` → `WorldNotFoundError` si no encontrado. 5) `registry.login(account, world)`. Nunca loguea `cipher`, `fernet`, ni `account.password`. |
| `_find_world` | `(account, world_id)` | `World` | Itera `account.worlds`; lanza `WorldNotFoundError` si no encontrado. |

## `LogoutUseCase` — `core/use_cases/login_use_case.py`

Dataclass con un campo: `registry: WorldRuntimePort`. Sin campo `fernet`.

| Método | Firma | Devuelve | Descripción |
|--------|-------|----------|-------------|
| `execute` | `async (world_id: int)` | `None` | Delega en `registry.logout(world_id)`. Sin lógica propia. |

---

## `DbPort.get_account_password_cipher` — `core/ports/db_port.py`

```python
async def get_account_password_cipher(self, account_id: int) -> Optional[bytes]
```

Devuelve el BLOB Fernet cifrado de la contraseña, o `None` si la cuenta no existe. Solo para uso en `LoginUseCase`. `get_account()` sigue devolviendo `password=""`.

## `AccountSQLiteAdapter.get_account_password_cipher` — `adapters/db/account_sqlite_adapter.py`

```python
async def get_account_password_cipher(self, account_id: int) -> Optional[bytes]:
    cursor = await self._conn.execute("SELECT password FROM accounts WHERE id = ?", (account_id,))
    row = await cursor.fetchone()
    if row is None:
        return None
    return bytes(row["password"])
```

`bytes(row["password"])` convierte el `memoryview` de aiosqlite a `bytes` estándar. El adaptador no interpreta el BLOB.

---

## `get_world_runtime_port` — `adapters/api/dependencies.py`

```python
def get_world_runtime_port(request: Request) -> SessionRegistry
```

Lee `app.state.world_runtime_port`. Lanza `HTTPException(503)` si es `None`. Simplifica los handlers: no necesitan comprobar `None`.

---

## Excepciones relacionadas

| Excepción | `error_code` | HTTP | Descripción |
|-----------|-------------|------|-------------|
| `LoginFailedError(username)` | `LOGIN_FAILED` | `401` | Login fallido por cualquier causa. `params = {"username": username}`. El `username` aparece en el mensaje de error; la contraseña nunca aparece. |

---

🔖 Última revisión: 2026-05-26
