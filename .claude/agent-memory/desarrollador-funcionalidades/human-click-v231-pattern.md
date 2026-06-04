---
name: human-click-v231-pattern
description: Patron de implementacion del motor de click humano (Bezier+Fitts+Drift) — helpers privados, locks por tab, cursor incremental, antideteccion guardian
metadata:
  type: project
---

El modulo `adapters/browser/driver.py` contiene el motor de click humano. Claves para implementaciones futuras:

- `_CURSOR_POS: dict[int, tuple[float,float]]` — keyed por `id(tab)`. Actualizar DENTRO del bucle de waypoints (RN-HC17), no solo al final.
- `_TAB_LOCKS: dict[int, asyncio.Lock]` — creado bajo demanda con `setdefault(id(tab), asyncio.Lock())`. Usado en `human_click`, `human_click_at_rect` y `human_drift_toward`.
- `_validate_or_reset_cursor(tab, vw, vh)` — llamar ANTES de calcular el Bezier; si el cursor está fuera del viewport CDP hace no-op silencioso = teletransporte detectable.
- `_fitts_duration_ms(dist, width, min_duration_ms=None)` — rango [200, 800] ms; guards dist<1→200 y width<1→usar 1.
- `_sample_near_target(rect, end_distance_px, viewport_w=None, viewport_h=None)` — punto FUERA del rect; clamping al viewport si se pasan dimensiones.
- `_bezier_path` usa curvatura `random.uniform(0.10, 0.25)` (antes 5-20%).

Test guardian de git: `tests/antideteccion/test_session_antideteccion.py::test_login_y_driver_no_modificados_respecto_a_head` SIEMPRE falla cuando driver.py tiene cambios no comiteados. Es por diseño — no es regresion.

scipy no estaba en requirements.txt antes de v2.3.1 aunque el spec decía que sí. Fue añadido durante esta implementacion.

**Why:** las firmas RN-HC17/18 del guardian son críticas anti-detección; sin actualización incremental de _CURSOR_POS el cursor parte de posición fantasma tras cualquier cancelación.

**How to apply:** al tocar driver.py, verificar que _CURSOR_POS se actualiza dentro del bucle (no solo al final) y que _validate_or_reset_cursor se llama antes del Bezier.
