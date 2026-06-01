---
name: project-human-click
description: Human-click anti-detección: helper gaussiano standalone, regla project-wide, refactor 6 sitios JS/CDP
metadata:
  type: project
---

Spec cerrado en `docs/specs/human-click.md` (estado: ready-for-impl, 2026-06-01).

## Decisiones clave

- `human_click(element, page, jitter=0.25, settle_ms=(50,150))` y
  `human_click_at_rect(rect, page, ...)` como funciones **standalone** en
  `adapters/browser/driver.py` — mismo patrón que `human_delay` / `human_type`.
  NO se añade a `BrowserPort` (el contrato no debe prescribir detalles CDP de zendriver).
- Distribución gaussiana truncada: sigma = jitter × dim, clip inner 80% (margen 10% por lado),
  rejection sampling max 20 intentos, fallback al centro si se supera.
- jitter ∈ [0.10, 0.45], default 0.25. Fuera de rango → ValueError.
- `mouse.move(px, py)` CDP + sleep(50-150 ms) + `mouse.click(px, py)` CDP. Nunca `element.click()`.
- `ElementNotClickableError(selector_or_tag, reason)` en `core/exceptions.py`.

## 6 sitios a refactorizar

- `adapters/browser/driver.py:318` — `ZendriverAdapter.click()` (CDP-based, trivial)
- `adapters/browser/login.py:55` — `submit_button.click()` (CDP-based, trivial)
- `adapters/browser/farm_lists.py` — 3 helpers JS: `_js_click_expand`, `_js_open_context_menu`,
  `_js_click_menu_entry` → pasan a devolver rect, no hacen `.click()`
- `adapters/browser/farm_list_sender.py` — `_JS_START_FARM_LIST` → `_JS_GET_START_BUTTON_RECT`

## Regla project-wide

RN-HC01: prohibido `element.click()` en producción que toque Travian.
RN-HC02: prohibido `btn.click()` dentro de JS evaluado en Travian vía `evaluate()`.
Los helpers JS solo localizan y devuelven rect; Python hace el click vía CDP.

## Dependencias salientes

- `human-sessions` v2.2 (en paralelo): debe referenciar `human_click()` como obligatorio
  para cada click del generador de ruido de sesiones humanas.
- `oasis-farming`: al implementar, verificar que todos los clicks usan `human_click`.

**Why:** El bot fue baneado (causa: clicks en centro geométrico exacto sin mousemove previo).
**How to apply:** Todo nuevo spec o feature que tenga clicks en la sesión de Travian debe
referenciar este spec y usar `human_click()` / `human_click_at_rect()`.
