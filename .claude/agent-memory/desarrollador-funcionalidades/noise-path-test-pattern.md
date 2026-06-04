---
name: noise-path-test-pattern
description: Patrón del test en vivo de rutas (EP-N14): _browser_lock, execute_path_test, entidades PathTestReport en core/entities/noise_test.py
metadata:
  type: project
---

## Feature: Probar ruta (EP-N14) — §16 de noise-path-wizard.md

### Arquitectura
- `core/entities/noise_test.py`: `PathTestStepResult` + `PathTestReport` (dataclasses, no Pydantic)
- `WorldAgent.execute_path_test(path) -> PathTestReport`: no-destructivo, reutiliza `_execute_noise_step` sin cambio
- `_browser_lock: asyncio.Lock` en `WorldAgent.__init__`: serializa acceso al tab de Chrome
- `PATH_TEST_TIMEOUT_SECONDS: int = 60`: constante de módulo en `world_agent.py`

### Patrón de lock
- `_execute_noise_action` y `refresh_villages`: usan `async with self._browser_lock:` (context manager, sin timeout)
- `execute_path_test`: usa `asyncio.wait_for(lock.acquire(), PATH_TEST_TIMEOUT_SECONDS)` → lanza `BrowserBusyError` si timeout
- Orden de adquisición siempre: `_browser_lock` → `_TAB_LOCKS[tab]` (nunca al revés). No deadlock.
- Las operaciones de BD (reset_failures, touch_last_used_at) van FUERA del lock en `_execute_noise_action`

### No-destructividad
- `execute_path_test` NO llama a: `mark_path_dead`, `increment_path_failures`, `reset_path_failures`, `touch_last_used_at`, `bump_destination_failures`
- NO incrementa `_noise_recent_count`
- NO ejecuta el dwell final de `NoiseConfig`

### Tests
- `tests/unit/test_noise_path_test.py`: 21 tests unitarios con `asyncio.run()` directo
- `tests/test_noise_path_test_api.py`: 8 tests IT-PT (complementa los 14 de `test_ep_n14_test_path_api.py`)
- Gotcha: `NavigationStep` requiere `delay_min_ms >= 200` (anti-detección). Los tests deben usar 200+.

### Handler HTTP
- Ya implementado por desarrollador-apis en `adapters/api/routes/noise.py` (línea ~1221)
- `BrowserBusyError` → 409 "browser ocupado"
- `RuntimeError` → 500
- `overall "error"` → HTTP 200 (fallo semántico, no de API)

**Why:** el WorldAgent es asyncio single-threaded pero `execute_path_test` llega como coroutine externa desde el handler HTTP → sin `_browser_lock`, comandos CDP se entrelazan en los `await`.

**How to apply:** cualquier nuevo método de WorldAgent que acceda al tab de Chrome debe adquirir `_browser_lock` (con `async with` si no necesita timeout, con `wait_for` si debe devolver 409 cuando está ocupado).
