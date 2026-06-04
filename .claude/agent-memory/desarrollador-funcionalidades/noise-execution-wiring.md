---
name: noise-execution-wiring
description: Gap cierre v2.2.1 del ruido: _execute_noise_action real + seed wiring en run() y transiciones + touch_last_used_at
metadata:
  type: project
---

## Cierre de gaps v2.2.1 — Ruido de navegación real

### Gap 1 — _execute_noise_action real

Reemplazado el stub `TODO(v2.2.1)` en `core/scheduling/world_agent.py`.

- **Cómo acceder al browser**: `self._session_registry.get_browser(self.world_id)` via duck typing (WorldRuntimePort no declara `get_browser`, pero SessionRegistry lo tiene; se accede con `hasattr`).
- **_execute_noise_step**: helper privado que despacha por `NoiseAction`. Imports diferidos de `adapters.browser.driver` (evita dependencia circular core→adapters en tiempo de carga).
- **JS evaluate pattern**: usa `tab.evaluate(f"(() => {{ const el = document.querySelector({selector!r}); ... }})()") ` — importante el `!r` para escapar el selector en el JS.
- **NoiseStepError**: añadida en `core/exceptions.py`. Capturada junto con `asyncio.TimeoutError` en el try/except de `_execute_noise_action`.
- **touch_last_used_at**: añadido a `NoiseDbPort` y `NoiseSQLiteAdapter` (`UPDATE noise_destinations SET last_used_at = ? WHERE id = ?`). Llamado en el flujo feliz junto con `reset_destination_failures`.

### Gap 2 — seed_noise_loop_on_session_start wiring

**Opción B implementada** (en `run()` directamente, no en el endpoint):
- En `run()`: `if self._active_mode in (HARDCORE, PASIVO): await self._safe_seed_noise_loop()`
- En `_check_mode_transition` tras DISCONNECTED → activo: `if not self._queue.has_task_type(NOISE_NAVIGATION): await self._safe_seed_noise_loop()`
- `_safe_seed_noise_loop()`: wrapper que captura excepciones, patrón idéntico a `_safe_seed_oasis`.
- `has_task_type(TaskType)`: añadido a `TaskQueue` (evita duplicar la primera NOISE_NAVIGATION).

### Tests existentes que se rompieron (y cómo se adaptaron)

Los 3 tests originales de `TestExecuteNoiseAction` usaban `asyncio.sleep` patch para simular fallos. Con la nueva implementación, el código falla antes de llegar a `asyncio.sleep` (porque `browser is None`). Se adaptaron para inyectar un browser mock vía `_make_registry_with_browser(tab)`.

### Fallo preexistente a ignorar

`test_UT_HS16_hardcore_executes_farm_task` (test_session.py) cuelga entre las 00:00–07:55 porque `run()` recalcula el modo al inicio con `compute_current_mode` y a esas horas el timeline por defecto da DISCONNECTED. El test seteaba `_active_mode` directamente pero `run()` lo pisa. No es regresión de estos cambios.

**Why:** El WorldAgent.run() siempre recalcula el modo al inicio — diseño correcto. El test no parcha `_load_timeline` ni `compute_current_mode`.

**How to apply:** Al ejecutar la suite completa de noche, ignorar o excluir `test_session.py` si hay fallos de timeout. Los 2 fallos Fernet + 4 fallos session_api son preexistentes conocidos.
