# Documentación de código — Human Click v2.3.1

Módulos documentados:
- `adapters/browser/driver.py` — funciones públicas `human_click`, `human_click_at_rect`, `human_drift_toward` y toda la maquinaria privada de apoyo

Spec de referencia: [`docs/specs/human-click.md`](../../docs/specs/human-click.md) (v2.3.1 — implementado)
Referencia de funciones: [`backend/referencia-funciones/human-click.md`](referencia-funciones/human-click.md)
Documento de negocio: [`funcionalidades/anti-deteccion-click.md`](../funcionalidades/anti-deteccion-click.md)

---

## Contexto de negocio

Travian detecta automatizaciones analizando eventos del DOM. Un `element.click()` de Selenium o `mousedown→mouseup` con latencia < 1 ms y sin recorrido de cursor previo es una firma trivialmente detectable. Esta feature elimina ese vector sustituyendo todos los clicks del bot por una simulación de movimiento y click humano.

La feature resuelve **dos firmas** identificadas tras el baneo de 2026-06:

1. El Bézier completaba en 50-150 ms (ráfaga concentrada). Ahora dura 200-800 ms según la distancia real al target (ley de Fitts).
2. El cursor permanecía quieto entre clicks. Ahora `human_drift_toward` permite mover el cursor hacia el próximo objetivo aprovechando tiempos de espera existentes (AJAX, dwell).

---

## Estado global del módulo

```python
# driver.py — module-level
_CURSOR_POS: dict[int, tuple[float, float]] = {}
# Última posición del cursor por tab (keyed por id(tab)).
# Permite que cada click parta del punto donde terminó el anterior.

_TAB_LOCKS: dict[int, asyncio.Lock] = {}
# Lock por tab. Serializa human_click y human_drift_toward en la misma pestaña.
# Creado bajo demanda: _TAB_LOCKS.setdefault(id(tab), asyncio.Lock()).
```

**Por qué `id(tab)` como clave:** en CPython, `id()` es la dirección de memoria del objeto. Para tabs de larga duración (la norma en este bot) es estable. Riesgo conocido: si una tab se libera y otro objeto ocupa la misma dirección, habría colisión. Pendiente para v2.4: usar el `target_id` de CDP como clave más robusta.

---

## Funciones privadas de apoyo

### `_fitts_duration_ms(distance_px, target_width_px, min_duration_ms=None) → int`

**Qué hace:** Calcula la duración total del movimiento de cursor usando la ley de Fitts: `T = 100 + 80 × log₂(2 × distance / target_width)`, capado a `[200, 800]` ms. Si `min_duration_ms` se pasa y es mayor que Fitts, se usa ese valor (también capado a 800 ms).

**Casos especiales:**
- `distance < 1` → fallback directo a 200 ms (evita `log2(0) = -inf`).
- `target_width < 1` → se usa 1.0 para el cálculo (evita división por cero).
- `min_duration_ms <= 0` → lanza `ValueError` antes de hacer nada.

**Por qué existe:** sin este cálculo el Bézier duraba siempre 50-150 ms, independientemente de la distancia — una firma estadística detectable. Fitts modela el tiempo real que un humano tarda en moverse a un target según distancia y tamaño.

**Impacto anti-detección:** produce timings en el rango 200-800 ms, que coincide con el rango de movimiento humano medido en la literatura (300-800 ms para distancias medias).

---

### `_validate_or_reset_cursor(tab, viewport_w, viewport_h) → tuple[float, float]`

**Qué hace:** Lee `_CURSOR_POS[id(tab)]` y comprueba que esté dentro del viewport actual (`0 ≤ x ≤ viewport_w`, `0 ≤ y ≤ viewport_h`). Si está fuera — o no existe — resetea a un punto aleatorio en el inner 80% del viewport y emite un `mouseMoved` de anclaje CDP antes de devolver la posición.

**Por qué existe (RN-HC18):** `CDP dispatchMouseEvent` con coordenadas fuera del viewport es un no-op silencioso en Chrome: el cursor "aparece" en el primer waypoint válido sin trayectoria intermedia. Eso equivale a un teletransporte, que es una firma detectable. Situaciones que desencadenan esto: primer click de sesión (cursor en `(0,0)` pero viewport puede ser 1280×720), cambio de tamaño de ventana, navegación a nueva URL.

---

### `_bezier_path(origin, target, n_points) → list[tuple[float, float]]`

**Qué hace:** Genera `n_points` waypoints a lo largo de una curva Bézier cuadrática con un punto de control perpendicular al segmento `origin→target`. La curvatura es un factor aleatorio uniforme en `[0.10, 0.25]` de la longitud del segmento, con signo aleatorio (±). Cada waypoint recibe un micro-ruido gaussiano de ±0.5 px. El último waypoint se fuerza al target exacto.

**Por qué existe:** Las trayectorias de cursor humanas son curvas no lineales con microtemblores. Una secuencia de `mouseMoved` en línea recta o con curvatura uniforme y fija es una firma de automatización. El rango `[0.10, 0.25]` garantiza variabilidad por trayecto.

---

### `_sample_click_point(rect, jitter) → tuple[float, float]`

**Qué hace:** Calcula el punto de aterrizaje del click usando una distribución gaussiana truncada al inner 80% del rect (margen 10% por lado). Rejection sampling con cap en 20 intentos; si todos son rechazados, usa el centro geométrico del rect.

**Por qué existe (RN-HC03):** Los bots que hacen click siempre en el centro exacto del elemento o siempre en el mismo píxel tienen distribución puntual. Los humanos hacen click en posiciones variables dentro del área del elemento.

---

### `_sample_near_target(rect, end_distance_px, viewport_w=None, viewport_h=None) → tuple[float, float]`

**Qué hace:** Calcula un punto a `≤ end_distance_px` px del borde del rect, **fuera** del rect, en una dirección aleatoria. `end_distance_px` se capa a `[5, 200]` px. Si se pasan `viewport_w/viewport_h`, el punto final se clampa al interior del viewport (margen 1 px).

**Por qué existe:** Es el punto de destino de `human_drift_toward`. El clamp al viewport es una mejora del guardian v2.3.1: un target pegado al borde de la ventana podría producir un end point fuera del viewport → no-op CDP silencioso → los últimos waypoints del drift no se renderizan → el cursor "salta" al comenzar el siguiente click.

---

### `_perform_human_click(tab, rect, jitter, settle_ms, total_duration_ms)`

**Qué hace:** Núcleo compartido de `human_click` y `human_click_at_rect`. Ejecuta la secuencia completa: validar cursor → samplear punto gaussiano → generar Bézier → recorrer waypoints con timing Fitts + jitter ±15% → settle → mousedown + pausa + mouseup.

El par `mousedown→mouseup` se envuelve en `asyncio.shield(_complete_click_gesture(...))` para que no pueda ser cancelado a mitad. Si se partiera, Chrome quedaría con el botón del ratón "presionado" a nivel CDP: el siguiente `mouseMoved` generaría eventos de drag fantasma (firma trivial de automatización).

La posición `_CURSOR_POS[id(tab)]` se actualiza tras **cada waypoint**, no solo al final. Si la coroutine se cancela a mitad del trayecto (timeout, `request_stop`), el cursor persistido es la última posición real enviada, no la posición planeada — evita el teletransporte en el siguiente click (RN-HC17).

---

### `_complete_click_gesture(tab, x, y)`

**Qué hace:** Gesto atómico `mousedown → sleep(35-110 ms) → mouseup`. Diseñado para ejecutarse bajo `asyncio.shield` desde `_perform_human_click`.

**Por qué existe:** Separar el mousedown del mouseup en el tiempo (35-110 ms) reproduce el tiempo de pulsación humano. Un par `mousedown→mouseup` con latencia < 1 ms es firma de bot.

---

## Funciones públicas

### `human_click(element, page, jitter=0.25, settle_ms=(80,180), min_duration_ms=None)`

**Qué hace:** Click anti-detección sobre un elemento de zendriver. Flujo:
1. Valida `jitter`, `settle_ms` y `min_duration_ms`.
2. Adquiere `_TAB_LOCKS[id(page)]` (serializa con `human_drift_toward`).
3. Obtiene el bounding rect via `element.apply(getBoundingClientRect)`.
4. Si rect es inválido (width o height = 0) → `ElementNotClickableError`.
5. Si el elemento está offscreen → `scroll_into_view()` + pausa 150-350 ms + re-evaluar rect.
6. Calcula `total_ms` con Fitts desde `_CURSOR_POS[id(page)]` hasta el target.
7. Delega en `_perform_human_click`.

**Firma:** `async def human_click(element, page, jitter=0.25, settle_ms=(80,180), min_duration_ms=None) → None`

**Errores:** `ElementNotClickableError` (rect inválido o elemento offscreen tras scroll), `ValueError` (parámetros fuera de rango).

**Por qué existe:** Reemplaza todos los `element.click()` y `btn.click()` del bot. Es el punto de entrada principal para cualquier click sobre Travian.

**Impacto en negocio:** Sin esta función, el bot produce clicks con firma de automatización detectable. Es la capa de anti-detección más crítica para la indetectabilidad del bot.

---

### `human_click_at_rect(rect, page, jitter=0.25, settle_ms=(80,180), min_duration_ms=None)`

**Qué hace:** Variante de `human_click` cuando el rect ya viene calculado desde JS (via `element.apply` o `evaluate`). No recibe element — toma las coordenadas del dict rect directamente. Mismo flujo a partir del paso 6.

**Por qué existe:** En `farm_lists.py` y `farm_list_sender.py` el rect se obtiene con `getBoundingClientRect()` dentro de un `evaluate()` que devuelve el dict. Crear un element solo para que `human_click` vuelva a llamar a `getBoundingClientRect` sería una llamada CDP redundante.

---

### `human_drift_toward(target, tab, duration_ms, end_distance_px=20)`

**Qué hace:** Mueve el cursor hacia `target` durante `duration_ms` ms **sin hacer click**. Termina en un punto a `≤ end_distance_px` px del borde del target. Flujo:
1. Valida `duration_ms > 0`.
2. Adquiere `_TAB_LOCKS[id(tab)]`.
3. Resuelve el rect del target (acepta element zendriver o dict `{x,y,width,height}`).
4. Si target offscreen → scroll + sleep 150-350 ms post-scroll (RN-HC19).
5. Obtiene viewport, clampa el end point al interior.
6. Valida/resetea cursor.
7. Genera waypoints Bézier y los recorre con timing `duration_ms + jitter ±15%`.
8. Actualiza `_CURSOR_POS` incremental.

**Firma:** `async def human_drift_toward(target, tab, duration_ms, end_distance_px=20) → None`

**Errores:** `ValueError` (`duration_ms <= 0`), `ElementNotClickableError` (target offscreen e irrecuperable), `TypeError` (target no es element ni dict válido).

**Por qué existe (RN-HC15):** El cursor quieto entre clicks es la segunda firma detectada. En lugar de crear una coroutine de fondo sin destino (rechazado: antinatural), `human_drift_toward` aprovecha tiempos de espera **que ya existen** (AJAX, dwell, intervals) para mover el cursor con propósito. El callerque invoque `human_click(target)` después obtiene un trayecto final corto (~20 px) → Fitts ≈ 150-300 ms — un "final approach" natural.

**Impacto anti-detección:** Elimina la firma del cursor congelado entre clicks. El patrón de uso es: `await human_drift_toward(next_btn, tab, 4000)` seguido de `await human_click(next_btn, tab)`.

**Divergencia respecto al spec:** La implementación de `_bezier_path` usa `n_points` (incluyendo el último waypoint = target exacto) mientras que el spec describe el bucle como `range(1, n_waypoints + 1)`. En la práctica el comportamiento es equivalente: se generan entre 3-8 waypoints en drift (el spec dice 3-8 también; la implementación usa `randint(4, 8)` para drift, mientras el spec dice 3-8). El mínimo de 4 en lugar de 3 es una mejora menor sin impacto anti-detección.

---

## Relación con otras funciones del módulo

| Función | Rol respecto a human-click |
|---|---|
| `human_delay(min_ms, max_ms)` | Pausa genérica usada en scroll post-click. No forma parte del motor de click |
| `human_type(element, text)` | Escritura humana (80-220 ms/carácter). Función independiente, mismo módulo |
| `ZendriverAdapter.click(element)` | Wrapper de `human_click` para cumplir el `BrowserPort` — llama `await human_click(element, self._tab)` |
| `create_browser(profile_dir)` | Crea el browser con flags anti-detección. No interactúa con human-click |

---

## Tests

**Fichero:** `tests/unit/test_human_click.py`
**Cobertura:** UT-HC01 a UT-HC30 (31 tests, 0.65 s). Los tests mockean `_dispatch_mouse_moved` y `_dispatch_mouse_event` — no arrancan Chrome.

Tests destacados:
- **UT-HC26:** cancela `human_click` mid-flight (CancelledError) y verifica que `_CURSOR_POS` refleja el último waypoint enviado, no el planeado.
- **UT-HC27/28:** cursor fuera del viewport → `_validate_or_reset_cursor` lo resetea.
- **UT-HC30:** test estadístico K-S con n=500 muestras de curvatura — verifica distribución uniforme [0.10, 0.25] con p-value > 0.05.

---

## Divergencias código/spec conocidas

| ID | Spec dice | Código hace | Impacto |
|---|---|---|---|
| DIV-HC01 | `human_drift_toward` usa `randint(3, 8)` waypoints | Usa `randint(4, 8)` — mínimo 4 en lugar de 3 | Mínimo, ninguna firma detectable |
| DIV-HC02 | `_to_rect` acepta elements de zendriver vía `.get_bounding_rect()` | En `human_drift_toward` el rect de elements se resuelve con `target.apply(getBoundingClientRect)` directamente — `_to_rect` solo acepta dicts | Sin impacto funcional; el spec describe la interfaz pública correctamente |

🔖 Última revisión: 2026-06-04 (documento creado — human-click v2.3.1 implementado en adapters/browser/driver.py, 31 tests verdes)
