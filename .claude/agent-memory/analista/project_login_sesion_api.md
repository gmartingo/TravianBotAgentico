---
name: project-login-sesion-api
description: Decisiones cerradas del spec login-sesion-api — SessionRegistry, cableado LiveOverviewAdapter, 3 endpoints session, LoginFailedError, amendment A1 descifrado
metadata:
  type: project
---

Feature `login-sesion-api` spec en `docs/specs/login-sesion-api.md` (estado: ready-for-impl con Amendment A1, 2026-05-26).

**Decisiones principales:**

- `SessionRegistry` CREA en `adapters/browser/session_registry.py`. Implementa `WorldRuntimePort`. Mantiene `dict[world_id, (zd.Browser, World)]`.
- `get_browser(world_id)` y `get_world_server(world_id)` son métodos CONCRETOS de `SessionRegistry`, NO están en `WorldRuntimePort` (que es core y no puede conocer `zd.Browser`). Se pasan como callables a `LiveOverviewAdapter`.
- `LiveOverviewAdapter` tiene `set_callables(get_browser, get_world_server)` para que `main.py` sustituya lambdas stub sin acceder a atributos privados.
- Cableado en `main.py lifespan`: SessionRegistry DESPUÉS de html_source_port, ANTES de yield.
- Re-login silencioso (no 409), POST síncrono, DELETE idempotente (204), sin Accept-Language.
- `LoginFailedError`: cubre credenciales incorrectas Y errores de red/timeout indistintamente.
- `_verify_world_belongs_to_account`: 404 homogéneo (no revela existencia de mundos ajenos).
- `get_world_runtime_port` lanza 503 si no hay registry en app.state.

**Amendment A1 — Descifrado de credenciales (hueco crítico confirmado 2026-05-26):**

- `AccountSQLiteAdapter.get_account()` devuelve SIEMPRE `password=""`. Intencional para no filtrar cifrado en respuestas de API. No es un bug nuevo: era el diseño, pero NADIE implementó el descifrado posterior.
- Solución: `LoginUseCase` recibe `fernet: Fernet` como tercer campo del dataclass. En `execute()` llama `db.get_account_password_cipher(account_id)` (nuevo método) → descifra → asigna a `account.password` antes de llamar a `registry.login()`.
- `DbPort` añade `get_account_password_cipher(account_id) -> Optional[bytes]`: lee solo el BLOB de la columna `accounts.password`, sin conocer Fernet. El adaptador sigue siendo agnóstico al cifrado.
- `InvalidToken` (clave Fernet diferente) → `LoginFailedError` → 401. Nunca 500. Nunca loguear el token ni la clave.
- El endpoint `session_login` añade `fernet=Depends(get_fernet)`. `get_fernet` ya existía en `dependencies.py`. No hay cambios de contrato HTTP.
- `LogoutUseCase`: sin cambios.
- Advertencia para futuros specs: en este proyecto, `get_account()` NUNCA devuelve la contraseña descifrada. El descifrado es responsabilidad exclusiva de `LoginUseCase` via el método cipher dedicado.

**Why (Amendment):** El login real tecleaba cadena vacía porque `get_account()` devuelve `password=""` por diseño de seguridad, y nadie añadió el paso de descifrado en LoginUseCase.

**How to apply:** Cualquier use case futuro que necesite la contraseña real de una cuenta debe: (1) obtener el cipher con `get_account_password_cipher`, (2) recibir `fernet` inyectado, (3) descifrar en el propio use case. Nunca esperarlo de `get_account()`.
