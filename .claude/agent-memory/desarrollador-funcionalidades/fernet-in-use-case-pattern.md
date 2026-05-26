---
name: fernet-in-use-case-pattern
description: Patrón de descifrado Fernet en LoginUseCase, field(repr=False) en Account.password, y _StateOverride con fernet para tests de API
metadata:
  type: project
---

El descifrado de la contraseña ocurre exclusivamente en `LoginUseCase` (Amendment A1, 2026-05-26), NO en el adaptador SQLite.

**Arquitectura:**
- `AccountSQLiteAdapter.get_account_password_cipher(account_id)` — devuelve el BLOB Fernet opaco (bytes) o None
- `LoginUseCase` tiene 3 campos: `registry`, `db`, `fernet: Fernet` (inyectado via `get_fernet` dependency)
- `execute()` obtiene cipher → descifra → asigna `account.password` → llama `registry.login`
- `InvalidToken` y `cipher is None` → `LoginFailedError` (401, nunca 500)
- Ningún `logger.*` en LoginUseCase loguea `cipher`, `fernet`, ni `account.password`

**Account.password usa `field(repr=False)`** para que el repr() de la dataclass no imprima la contraseña en claro. El campo sigue siendo posicional (sin default), solo cambia el repr.

**Tests de API (test_session_api.py):**
- Todos los tests de POST que llegan al LoginUseCase necesitan `fernet=_TEST_FERNET` en `_StateOverride`
- `_make_db(account)` genera automáticamente un cipher con `_TEST_FERNET` por defecto cuando hay cuenta
- Tests que fallan antes del LoginUseCase (404 por cuenta no encontrada, 503 por registry None) NO necesitan fernet en el override

**Fallos preexistentes:** 9 (2 CA-20 lectura-overview + 7 test_kirilloid_scraper MagicMock vs AsyncMock)

**Why:** el adaptador almacena el BLOB opaco; inyectar Fernet en el adaptador violaría la arquitectura hexagonal (el puerto DbPort no debe conocer Fernet).

**How to apply:** si en el futuro se añade otro use case que necesita descifrar la contraseña, seguir el mismo patrón: método `get_account_password_cipher` en DbPort + Fernet inyectado en el use case.

[[session-registry-pattern]]
