---
name: human-sessions-pattern
description: Patrones de implementación de Human Sessions (timeline de modos HARDCORE/PASIVO/DISCONNECTED en WorldAgent)
metadata:
  type: project
---

## Patrón implementado (2026-05-31)

### Estructura
- `core/entities/session.py` — entidades puras + funciones puras de cálculo de modo (sin IO)
- `core/ports/session_timeline_db_port.py` — puerto abstracto
- `adapters/db/session_sqlite_adapter.py` — implementación SQLite; tablas `world_session_timeline`, `world_session_override`, `world_session_config`
- `adapters/api/routes/session.py` — 6 endpoints en `/worlds/{world_id}/session/...`
- `tests/unit/test_session.py` — UT-HS01..34
- `tests/test_session_api.py` — IT-HS01..10

### Claves del patrón
- `session_db_port` se instancia en el lifespan de `main.py` DESPUÉS de `AccountSQLiteAdapter` (que crea la tabla `worlds` referenciada)
- `ensure_tables()` del adaptador de sesión NO activa `PRAGMA foreign_keys = ON` (ya lo activa AccountSQLiteAdapter en la conexión compartida)
- `current_mode()` normaliza timezone naive vs aware al comparar `now` con `override.expires_at`
- `pop_farm_ready(now)` añadido a `TaskQueue` para filtrar solo `SEND_FARM_LIST_GROUP` en modo PASIVO
- `FernetDecryptionError` distingue error de configuración (sin backoff) de errores transitorios en relogin
- `close_session` y `has_active_session` son alias en `SessionRegistry` de `logout` e `is_active`
- El modo activo NUNCA se persiste — se deriva siempre de `current_mode(now, timeline, override)`
- Tests de integración: configurar TODOS los weekdays cuando se necesita que el modo actual sea DISCONNECTED (el día real puede ser cualquiera de los 7)

### Fallos preexistentes en suite (sin relación con esta feature)
- `test_combat_optimizer.py` — `ImportError: core.entities.combat` (módulo no publicado)
- `test_game_data_api.py` — `sqlite3.OperationalError` (preexistente)
- `tests/unit/test_session_api.py` (login) — `database is locked` al correr en suite completa (preexistente)
- Total preexistente: 40 failed + 121 errors

**Why:** la memoria previa decía "9 fallos preexistentes" pero la suite completa tiene más; al correr en aislamiento con `--ignore=tests/unit/test_combat_optimizer.py` sin los nuevos tests el conteo base es el mismo.

**How to apply:** al verificar regresiones, comparar conteo de fallos SIN los tests nuevos vs CON los tests nuevos. Si el delta es 0 en failed/errors → sin regresión.
