# Referencia de funciones — Human Click (driver.py)

Módulo: `adapters/browser/driver.py`
Spec: `docs/specs/human-click.md` (v2.3.1)
Doc de código: `documentacion/backend/human-click.md`

---

## Estado global del módulo

| Símbolo | Tipo | Descripción |
|---|---|---|
| `_CURSOR_POS` | `dict[int, tuple[float,float]]` | Última posición del cursor por tab. Clave: `id(tab)`. Valor: `(x, y)` en CSS px. |
| `_TAB_LOCKS` | `dict[int, asyncio.Lock]` | Lock por tab para serializar clicks. Clave: `id(tab)`. Creado bajo demanda. |

---

## Funciones públicas

### `human_click`

```python
async def human_click(
    element: zd.Element,
    page: zd.Tab,
    jitter: float = 0.25,
    settle_ms: tuple[int, int] = (80, 180),
    min_duration_ms: int | None = None,
) -> None
```

Click anti-detección con cursor Bézier + timing Fitts + mousedown/up separados.
El movimiento dura `[200, 800]` ms según distancia (ley de Fitts) con jitter ±15% por waypoint.

**Raises:**
- `ElementNotClickableError` — rect inválido o elemento offscreen tras scroll.
- `ValueError` — parámetros fuera de rango o `min_duration_ms <= 0`.

---

### `human_click_at_rect`

```python
async def human_click_at_rect(
    rect: dict,           # {"x": float, "y": float, "width": float, "height": float}
    page: zd.Tab,
    jitter: float = 0.25,
    settle_ms: tuple[int, int] = (80, 180),
    min_duration_ms: int | None = None,
) -> None
```

Variante de `human_click` cuando el bounding rect ya viene de `evaluate()`. Sin scroll-into-view.
Usar en `farm_lists.py` y `farm_list_sender.py` donde el rect se obtiene con `getBoundingClientRect` en JS.

---

### `human_drift_toward`

```python
async def human_drift_toward(
    target: zd.Element | dict,   # element zendriver O dict {x,y,width,height}
    tab: zd.Tab,
    duration_ms: int,
    end_distance_px: int = 20,
) -> None
```

Mueve el cursor hacia `target` durante `duration_ms` ms **sin click**. Termina a `≤ end_distance_px` px del borde. Actualiza `_CURSOR_POS`.

**Patrón de uso:**
```python
# Mientras esperamos la respuesta AJAX (4 s), movemos el cursor hacia el botón
await human_drift_toward(submit_btn, tab, duration_ms=4000)
# Ahora el trayecto final es ~20 px → Fitts ≈ 200-250 ms
await human_click(submit_btn, tab)
```

**Raises:**
- `ValueError` — `duration_ms <= 0`.
- `ElementNotClickableError` — target offscreen e irrecuperable.
- `TypeError` — target no es element ni dict válido.

---

## Funciones privadas clave

| Función | Firma resumida | Qué hace |
|---|---|---|
| `_fitts_duration_ms` | `(distance_px, target_width_px, min_duration_ms=None) → int` | Calcula duración del movimiento. T = 100 + 80×log₂(2d/w), rango [200, 800] ms. |
| `_validate_or_reset_cursor` | `async (tab, viewport_w, viewport_h) → (x,y)` | Resetea cursor si está fuera del viewport. Emite un `mouseMoved` de anclaje. |
| `_bezier_path` | `(origin, target, n_points) → list[(x,y)]` | Genera waypoints Bézier cuadrático con curvatura 10-25% aleatoria + micro-ruido ±0.5 px. |
| `_sample_click_point` | `(rect, jitter) → (x,y)` | Samplea el punto de click: gaussiana truncada al inner 80% del rect. |
| `_sample_near_target` | `(rect, end_distance_px, vw=None, vh=None) → (x,y)` | Samplea un punto fuera del rect, a ≤ end_distance_px del borde. Clampa al viewport. |
| `_to_rect` | `(target) → dict` | Normaliza un target dict `{x,y,width,height}`. Lanza `TypeError` si no es dict válido. |
| `_perform_human_click` | `async (tab, rect, jitter, settle_ms, total_duration_ms)` | Núcleo compartido: validar cursor → Bézier → settle → click atómico. |
| `_complete_click_gesture` | `async (tab, x, y)` | Gesto atómico `mousedown → sleep(35-110ms) → mouseup`. Se ejecuta bajo `asyncio.shield`. |
| `_validate_jitter_settle` | `(jitter, settle_ms)` | Valida parámetros: `jitter ∈ [0.10, 0.45]`, `settle_ms` tuple válido. |
| `_is_offscreen` | `(rect) → bool` | True si el rect está completamente fuera del viewport (x+w<0 o y+h<0). |

---

## Excepciones relacionadas

| Excepción | Dónde se lanza | Qué indica |
|---|---|---|
| `ElementNotClickableError` (`core/exceptions.py`) | `human_click`, `_perform_human_click`, `human_drift_toward` | El elemento no puede recibir un click (oculto, fuera del DOM, o fuera del viewport tras scroll). |
| `ValueError` | `_fitts_duration_ms`, `human_click`, `human_drift_toward`, `_validate_jitter_settle` | Parámetros inválidos: `min_duration_ms <= 0`, `duration_ms <= 0`, jitter/settle_ms fuera de rango. |
| `TypeError` | `_to_rect`, `human_drift_toward` | `target` no es dict válido ni element con `apply()`. |

🔖 Última revisión: 2026-06-04 (creado — referencia de funciones human-click v2.3.1)
