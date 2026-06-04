---
name: project-noise-path-wizard
description: Noise Path Wizard v2 — anclas, wizard, derive-selector (implementado) + §16 "Probar ruta" EP-N14 (ready-for-impl)
metadata:
  type: project
---

Spec `docs/specs/noise-path-wizard.md`.
- §1-§15: estado `implemented` (2026-06-02). 150 tests noise, 0 failed.
- §16 "Probar ruta": estado `ready-for-impl` (2026-06-02). apis_validadas: false.

Anexo `docs/specs/noise-navigate-to-origin.md` (EP-N15 "Ir al inicio"):
- estado `ready-for-impl` (2026-06-02). apis_validadas: false. Gate guardian OBLIGATORIO (browser.get real).
- Botón explícito en NoiseOriginSelector.jsx lleva el Chrome vivo al ancla del origin via browser.get+human_delay.
- Reutiliza TODO de §16/EP-N14: gate RUNNING+_session_active, _browser_lock, BrowserBusyError, _validate_origin.
- CLAVE: extraer el mapeo inline origin→URL de execute_path_test (world_agent.py:1476-1489) a helper compartido
  _origin_to_relative_url; execute_path_test pasa a usarlo (cero duplicación). RN-NO07.
- ANY → 200 navigated:false sin navegar (no 422). Fallo browser.get → 500 (no 200 semántico como EP-N14, D-10.1).
- 3 preguntas abiertas son solo UX (timeout lock, fuente de sessionActive en front, microcopy) — no bloquean.

**Why §16:** el usuario no puede saber si una ruta es correcta hasta que el bot la ejecuta
y la mata tras 3 fallos. El botón "Probar ruta" ejecuta la ruta en vivo y devuelve un
reporte paso a paso (no destructivo: no modifica contadores ni BD).

---

### Decisiones clave §16 ("Probar ruta")

- **`_browser_lock: asyncio.Lock`** nuevo en `WorldAgent.__init__` — protege el acceso al tab
  en `_execute_noise_action`, `refresh_villages` y `execute_path_test`. El único lock previo
  (`_TAB_LOCKS` en driver.py) serializa gestos individuales de mouse, no sesiones completas.
  Sin el nuevo lock, los awaits de ruido y test se entrelazan sobre el mismo tab.
- **`asyncio.wait_for(lock.acquire(), 60s)`** en `execute_path_test` → `BrowserBusyError` → 409.
  En `_execute_noise_action` y `refresh_villages` usar `async with self._browser_lock:` (sin timeout).
- **No-destructivo**: `execute_path_test` no llama a ningún método write de NoiseDbPort.
  Verificable con grep en el commit.
- **HTTP 200 aunque overall=="error"**: el endpoint ejecutó; el fallo es semántico.
- **`tab.url` es sincrónico** en zendriver (verificado en login.py:59 y en _execute_noise_step ya implementado).
- **Navegación al ancla** usa `build_url(server, ORIGIN_PATHS[origin])` para genéricos,
  `/dorf1.php?newdid=<id>` para VILLAGE_, nada para ANY.
- **`PATH_TEST_TIMEOUT_SECONDS = 60`** como constante de módulo.
- **`_execute_noise_step`** se reutiliza sin cambio (lanza `NoiseStepError` en cualquier fallo).
- **Estado final del browser**: no se restaura (aceptado, documentado en `browser_note`).
- **R-PT02**: `_execute_noise_action` y `refresh_villages` existentes NO tenían `_browser_lock`;
  el implementador de §16 los actualiza como parte de la feature.

### Nuevas piezas §16
- `core/entities/noise_test.py`: dataclasses `PathTestStepResult`, `PathTestReport`.
- `core/exceptions.py`: nueva excepción `BrowserBusyError(RuntimeError)`.
- `core/scheduling/world_agent.py`: `_browser_lock`, método `execute_path_test`, constante `PATH_TEST_TIMEOUT_SECONDS`.
- `adapters/api/routes/noise.py`: modelos `PathTestStepResultResponse`, `PathTestResponse`, handler `test_path` (EP-N14).
- Tests: `tests/unit/test_noise_path_test.py` (UT-PT01..15), `tests/test_noise_path_test_api.py` (IT-PT01..08).

### Gate obligatorio §16
- `desarrollador-apis` debe revisar EP-N14 antes del primer commit (apis_validadas: false).
- `guardian-antideteccion` debe auditar `execute_path_test` y `_browser_lock` en `_execute_noise_action`.

### Riesgo principal §16
- Dwell largo (hasta 30 s) puede hacer que el test espere el lock y devuelva 409.
  Documentar en UI: "si el bot está en dwell largo, el test puede tardar o devolver 409".

[[project-human-sessions]]
