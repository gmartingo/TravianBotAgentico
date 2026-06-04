---
name: noise-path-wizard-pattern
description: Patrón noise-path-wizard: migraciones de BD en noise_sqlite_adapter, villages queries en NoiseDbPort (Opción A), tab.url sincrónico, is_dead en NavigationPath, _make_noise_db_mock helper
metadata:
  type: project
---

Implementación del spec noise-path-wizard.md (2026-06-02).

## Migraciones idempotentes en NoiseSQLiteAdapter

Dos migraciones en `ensure_tables()` del adaptador (no en fichero separado):
- M-NP01: RENAME+CREATE+INSERT+DROP de `noise_navigation_paths` (añade `is_dead`, `consecutive_failures_count`, elimina CHECK de origin). Usa `PRAGMA table_info` para detectar si ya se aplicó.
- M-NP02: `ALTER TABLE noise_navigation_steps ADD COLUMN expected_url_after_click TEXT DEFAULT NULL`. Idempotente via `try/except aiosqlite.OperationalError`.

**Why:** SQLite no soporta ALTER COLUMN ni DROP CONSTRAINT. RENAME+CREATE es el patrón estándar.
**How to apply:** seguir el mismo patrón para migraciones futuras que requieran cambios estructurales en tablas de noise.

## tab.url sincrónico en zendriver

`tab.url` es una **propiedad sincrónica** en zendriver, NO awaitable. Verificado en `adapters/browser/login.py:59` donde se usa como `page.url` (sin await).

El spec §9.4 dice `await tab.url` — es un error del spec, el código real NO debe usar await.

**Why:** la API real de zendriver difiere del pseudocódigo del spec.
**How to apply:** cuando el spec use `await tab.url` o `await tab.alguna_propiedad`, verificar primero en login.py si es sincrónica.

## is_dead en NavigationPath

El spec §7.5 no incluye `is_dead` en la dataclass `NavigationPath`, pero es necesario para que `_select_noise_action` pueda filtrar a nivel de entidad. Se añadió con `is_dead: bool = False`.

Mismo patrón que `NoiseDestination` que sí tiene `is_dead`.

## _make_noise_db_mock helper en tests

Los tests de WorldAgent que ejercen `_execute_noise_action` necesitan un `noise_db` mock con los 7 métodos async:
- `reset_destination_failures`, `bump_destination_failures`, `mark_destination_dead`, `touch_last_used_at`
- `increment_path_failures`, `reset_path_failures`, `mark_path_dead` (nuevos de noise-path-wizard)

Helper `_make_noise_db_mock(bump_path_return, bump_dest_return)` en `tests/unit/test_noise.py` crea el mock completo. Si se añaden más métodos async al noise_db, actualizar también este helper.

## _validate_origin en noise_sqlite_adapter

`_validate_origin(origin: str, village_data_ids: list[int]) -> None` vive en `adapters/db/noise_sqlite_adapter.py` (no en core/). Se importa de `_VALID_GENERIC_ORIGINS` (frozenset de los 9 valores del enum). Se llama en `create_path` después de verificar que el destino existe y obtener las aldeas del mundo.

## Villages en NoiseDbPort (Opción A)

`get_villages_for_world` y `upsert_village` están en `NoiseDbPort`/`NoiseSQLiteAdapter` (no en AccountDbPort). Los imports de `Village` son locales dentro de los métodos para evitar ciclos.

`upsert_village` usa `ON CONFLICT(world_id, data_id) DO UPDATE SET name=..., x=..., y=...`.

## Fallos preexistentes en la suite

Los 2 fallos preexistentes post-implementación son:
- `test_login_use_case.py::test_execute_invalid_token_raises_login_failed`
- `test_session_api.py::test_post_session_invalid_token`

Son de Fernet/login, no relacionados con noise-path-wizard.

## Tests de integración de BD

Para tests de BD directos (sin HTTP), la creación de cuenta+mundo usa:
```python
from core.entities.account import Account
from core.entities.tribe import Tribe
from core.entities.world import World
account = await account_adapter.save_account(Account(id=None, email=..., username=..., password=""), password_cifrada=b"dummy")
world = await account_adapter.save_world(account_id=account.id, world=World(id=0, server="https://ts1.travian.es/", tribe=Tribe.ROMANS))
```

Ver [[async-tests-pattern]] para el patrón asyncio.run() directo.
