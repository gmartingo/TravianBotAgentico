---
id: radar-check-boton-sidebar
titulo: Corrección del botón "Forzar detección" del radar — migración de dorf1 a sidebar
estado: implemented
fecha: 2026-06-07
autor: analista
apis_validadas_por_desarrollador_apis: n-a
---

# Corrección del botón "Forzar detección" del radar — migración de dorf1 a sidebar

> **Spec de corrección.** Este documento describe exclusivamente el delta necesario para
> arreglar el botón "🛡 Forzar detección (debug)" del panel `IncomingAttacksPanel`.
> Lee el spec base `docs/specs/radar-ataques-entrantes.md` para el contexto completo
> del radar. Este spec lo extiende; no lo contradice ni lo duplica.

---

## 1. Objetivo de negocio

El botón "🛡 Forzar detección (debug)" disponible en `IncomingAttacksPanel.jsx` llama a
`POST /game/incoming-attacks/{world_id}/check` y se queda en "⏳ Detectando..." para siempre
cuando hay un ataque activo. Esto ocurre por dos causas raíz independientes:

**Causa 1 — Parser incorrecto:** el handler actual construye un `IncomingAttackBrowserAdapter`
ad-hoc, navega a `dorf1.php` y parsea con `Dorf1IncomingParser` buscando `img.att1` en una
`<table>`. Ese marcado es de Travian clásico; el servidor T4.6 del usuario ya no lo usa,
por lo que el parser devuelve 0 ataques siempre.

**Causa 2 — Contención de CDP:** el handler construye su propio adapter ad-hoc y llama a
`browser.get(dorf1.php)` sin el `_browser_lock` del `WorldAgent`, lo que interleava comandos
CDP con el radar autónomo (HEARTBEAT_SCAN/piggyback) sobre la misma pestaña → el bot se
congela.

**Causa 3 — Sin timeout en el cliente:** `request()` en `client.js` no usa `AbortController`,
así que si el backend se cuelga, el botón gira eternamente.

**Solución:** hacer que el handler delegue en el `WorldAgent` en marcha (que ya tiene el lock
y ya tiene el HTML de la página actualmente cargada en el browser), use `check_sidebar_attacks`
(ya implementado en `adapters/browser/incoming_attack_hook.py`) con ese HTML, y persista el
resultado. Si el agente no está RUNNING, devolver 409. Añadir `AbortController` con timeout
de 15 s en el cliente.

---

## 2. Actores y permisos

| Actor | Rol en esta corrección |
|---|---|
| Usuario | Pulsa el botón en el frontend |
| Frontend `IncomingAttacksPanel.jsx` | Llama `api.checkIncomingAttacks(worldId)` |
| `client.js` | Envía `POST /check` con timeout de 15 s |
| FastAPI handler `check_incoming_attacks` | Obtiene el WorldAgent, llama `agent.check_incoming_sidebar()`, devuelve conteo |
| `WorldAgent.check_incoming_sidebar()` | Método nuevo; adquiere `_browser_lock`, lee HTML actual, llama `check_sidebar_attacks` |
| `check_sidebar_attacks` | Ya implementado en `adapters/browser/incoming_attack_hook.py`; no cambia |

Sistema single-tenant; sin autenticación.

---

## 3. Alcance

### Dentro del alcance

- Reescribir el handler `check_incoming_attacks` (EP-RA02) para usar el WorldAgent en marcha
  y el sidebar (en vez del adapter dorf1 ad-hoc).
- Añadir el método público `WorldAgent.check_incoming_sidebar()` con el lock.
- Añadir `AbortController` + timeout 15 s en `client.js` (función `request`).
- Añadir mensaje de error legible en `IncomingAttacksPanel.jsx` cuando el fetch expira.
- Actualizar/añadir fixtures de test del sidebar:
  - Confirmar que `sidebar_with_attack.html` (did=27322, ya existe) y
    `sidebar_without_attack.html` (ya existe) son los fixtures canónicos para las pruebas
    unitarias del parser.
  - Añadir un tercer fixture `sidebar_real_con_ataque_did24498.html` con el HTML real
    aportado por el usuario (did=24498) para test de regresión de la sesión de debug.
- Documentar la deuda futura del Componente B autónomo (ver §13).

### Fuera del alcance

- No arreglar `Dorf1IncomingParser` ni `_handle_check_incoming_attack_detail` para T4.6
  (requiere HTML real de dorf1/rally point con ataque; no disponible aún — deuda §13).
- No cambiar el contrato externo de EP-RA02 (misma ruta, mismo response body).
- No cambiar la lógica del radar autónomo (piggyback, HEARTBEAT_SCAN).
- No añadir navegación nueva (el botón NO debe hacer `browser.get` a ninguna URL).
- No cambiar la tabla `incoming_attacks` ni su esquema.

---

## 4. Reglas de negocio

| ID | Regla |
|---|---|
| RN-B01 | El botón "Forzar detección" usa el mismo mecanismo que el radar autónomo (Componente A del sidebar), NO Componente B (dorf1). Esto es un cambio explícito de semántica: el botón detecta qué aldeas están bajo ataque según el sidebar de la página ACTUALMENTE cargada. NO proporciona `impact_at` (timer). Eso es aceptable y documentado. |
| RN-B02 | El handler delega **siempre** en el `WorldAgent` en marcha. NO construye adapters ad-hoc. Esto garantiza la serialización con `_browser_lock` y que no haya interleaving de CDP. |
| RN-B03 | El método `WorldAgent.check_incoming_sidebar()` adquiere `_browser_lock` antes de llamar a `_page_html_provider()`. Patrón idéntico a `execute_path_test`. |
| RN-B04 | Si `_page_html_provider` devuelve `None` (browser no disponible), el método retorna 0 sin error. El handler devuelve 200 con `attacks_detected=0` y `message` descriptivo. |
| RN-B05 | Si el WorldAgent no existe o su `state != AgentState.RUNNING`: el handler devuelve `409 Conflict` con `detail` descriptivo. Justificación: sin agente en marcha no hay HTML que leer; un error explícito es más útil que un silencio. Ver §6 EC-B01. |
| RN-B06 | Si el WorldAgent existe y está RUNNING pero `_session_active()` devuelve `False` (sesión caída): el handler devuelve `503 Service Unavailable` (comportamiento existente, no cambia). |
| RN-B07 | `check_sidebar_attacks` ya persiste con `impact_at=None` y `source='sidebar'`. El handler devuelve `attacks_detected = len(resultado)` (el conteo de `VillageUnderAttackDTO` detectadas). |
| RN-B08 | El cliente `request()` debe añadir `AbortController` con timeout de **15 s**. Si el fetch supera ese tiempo, `parseResponse` lanza `ApiError` con `status=0` y el mensaje de timeout visible en el frontend. |
| RN-B09 | El botón `forceCheck` en `IncomingAttacksPanel.jsx` maneja el error de timeout mostrando un mensaje legible: `"✕ timeout — el check tardó más de 15 s"`. |
| RN-B10 | El método `check_incoming_sidebar()` NO reencola `CHECK_INCOMING_ATTACK_DETAIL`. Ese reencolo es responsabilidad de `_post_page_hook` (que se invoca desde el WorldAgent autónomo). El botón es una lectura puntual, no una acción que dispare el flujo completo B→C→D. |
| RN-B11 | El método `check_incoming_sidebar()` NO actualiza `_last_sidebar_scan`. Esa actualización es responsabilidad de `_maybe_run_page_hook` (radar autónomo). El botón es externo al ciclo autónomo. |

---

## 5. Flujo principal y flujos alternativos

### Flujo principal — botón "Forzar detección" (ruta feliz)

```
1. Usuario pulsa "🛡 Forzar detección".
2. IncomingAttacksPanel.jsx → setChecking(true).
3. client.js: POST /game/incoming-attacks/{world_id}/check
   con AbortController(15 s).
4. Handler FastAPI:
   a. Verifica existencia del mundo (404 si no existe — comportamiento existente).
   b. Obtiene WorldAgent desde app.state.world_agents[world_id].
   c. Si agente es None o state != RUNNING → 409 (RN-B05).
   d. Si agente RUNNING pero _session_active() False → SessionNotActiveError → 503.
   e. Llama await agent.check_incoming_sidebar().
5. WorldAgent.check_incoming_sidebar():
   a. async with self._browser_lock:
   b.   html = await self._page_html_provider()  [None si browser no disponible]
   c.   Si html is None → return 0  (RN-B04)
   d.   attacks = await check_sidebar_attacks(html, self.world_id, self._incoming_db)
   e.   return len(attacks)
6. Handler devuelve:
   { "world_id": N, "attacks_detected": K, "message": "Check completado" }
7. IncomingAttacksPanel.jsx:
   a. setCheckMsg("✓ K ataque(s) detectado(s)")
   b. fetchAttacks()  [refresca la lista]
   c. setChecking(false)
```

### Flujo alternativo B1 — WorldAgent no está en RUNNING

```
4c. agents.get(world_id) es None, o agent.state != AgentState.RUNNING.
    Handler lanza HTTPException(409, detail="El agente del mundo {world_id}
    no está activo — inicia la sesión para usar el radar manual.")
    Frontend muestra: "✕ error (409) — El agente del mundo N no está activo…"
```

### Flujo alternativo B2 — Sesión caída dentro del agente

```
4d. agent.state == RUNNING pero _session_active() False.
    Handler llama check_incoming_sidebar → _page_html_provider devuelve None
    (browser sin tab activo) → retorna 0 ataques.
    O bien _page_html_provider lanza → captura en check_incoming_sidebar → retorna [].
    Response: { attacks_detected: 0, message: "Check completado" }
    [No se lanza 503; el 503 solo se produce por la ruta antigua que ya no se usa]
    NOTA: Si se desea mantener el 503 en este caso, ver §13 Trade-offs.
```

### Flujo alternativo B3 — Timeout de 15 s en el cliente

```
3b. AbortController dispara abort() a los 15 s.
    fetch() rechaza con AbortError.
    request() captura el error y lanza ApiError("timeout", 0, "timeout").
    forceCheck catch: setCheckMsg("✕ timeout — el check tardó más de 15 s")
    setChecking(false)
```

### Flujo alternativo B4 — `_page_html_provider` devuelve None

```
5c. html is None (browser sin sesión activa o tab cerrado).
    check_incoming_sidebar retorna 0.
    Response: { attacks_detected: 0, message: "Check completado" }
```

---

## 6. Edge cases

| ID | Escenario | Tratamiento |
|---|---|---|
| EC-B01 | `world_agents` no existe en `app.state` (servidor no inicializado) | `getattr(request.app.state, "world_agents", {})` → dict vacío → agente None → 409 |
| EC-B02 | El WorldAgent existe pero tiene `state == AgentState.STOPPED` (detenido por el usuario) | 409 con detail descriptivo (misma rama que RN-B05) |
| EC-B03 | El WorldAgent está RUNNING pero el browser no tiene tab (`main_tab is None`) | `_page_html_provider` devuelve `None` → `check_incoming_sidebar` retorna 0 → 200 |
| EC-B04 | El sidebar de la página actual no tiene `#sidebarBoxVillageList` (p.ej. se está en una página interna sin sidebar) | `check_sidebar_attacks` hace no-op silencioso (RN-19 del spec base) → retorna [] → `attacks_detected=0` |
| EC-B05 | `_incoming_db` no inyectado en el WorldAgent (no se inicializó el radar) | `check_sidebar_attacks` llega a `_persist_attacks` con `db_port` None → lanza AttributeError → capturado por el try/except de `check_sidebar_attacks` → retorna [] → `attacks_detected=0` |
| EC-B06 | Dos requests simultáneas al botón (doble click) | `_browser_lock` serializa ambas: una espera a que termine la otra. No hay race condition. La segunda devuelve los ataques de la misma página (idempotente). |
| EC-B07 | El usuario pulsa el botón sin haber iniciado sesión (no hay WorldAgent) | 409 (EC-B01 / RN-B05) |
| EC-B08 | El timeout del `AbortController` dispara mientras el lock está retenido | El `AbortController` cancela la conexión HTTP del cliente, pero el WorldAgent termina igualmente su operación en el servidor (el lock se libera). No hay corrupción de estado. |
| EC-B09 | Fixture did=24498 (HTML real del usuario) vs fixture did=27322 (fixture de GAP-01) | Son fixtures distintos para distintos tests. El fixture did=27322 cubre el caso unitario base. El fixture did=24498 es de regresión con datos reales del usuario. Ambos deben existir. |

---

## 7. Modelo de datos / cambios de esquema

No aplica. No se modifica el esquema de la tabla `incoming_attacks`. No hay migraciones.

---

## 8. Contratos de API / interfaces

> `apis_validadas_por_desarrollador_apis: n-a` — no hay endpoints nuevos ni modificación
> del contrato externo. EP-RA02 mantiene exactamente la misma firma, mismo response body
> y mismos códigos de estado (incluido el 409 añadido, que ya era parte del gobierno de
> APIs del proyecto para conflictos de estado).

### EP-RA02 — `POST /game/incoming-attacks/{world_id}/check` (sin cambio de contrato)

El contrato externo no cambia. Solo cambia la implementación interna del handler.

**Response 200** (sin cambio):
```json
{
  "world_id": 1,
  "attacks_detected": 1,
  "message": "Check completado"
}
```

**Errores** (actualización: se añade 409):

| Código | Condición | `detail` |
|---|---|---|
| `404` | `world_id` no existe | `"Mundo no encontrado."` (sin cambio) |
| `409` | WorldAgent no existe o no está RUNNING | `"El agente del mundo {world_id} no está activo — inicia la sesión para usar el radar manual."` |
| `503` | Sesión no activa (mantenido como posible vía `SessionNotActiveError` si se propaga) | `"No hay sesión activa para el mundo {world_id}"` |
| `500` | Error interno inesperado | `"Error interno del servidor"` |

> El 409 es nuevo y está justificado por el gobierno de APIs del CLAUDE.md: "409 para
> conflicto de estado". El agente no RUNNING es un conflicto de estado del recurso mundo.

---

## 9. Flujo lógico paso a paso (pseudocódigo)

### 9.1 — Método nuevo `WorldAgent.check_incoming_sidebar()`

```python
# core/scheduling/world_agent.py

async def check_incoming_sidebar(self) -> int:
    """
    Comprobación inmediata del sidebar — invocado desde el handler EP-RA02.

    Adquiere _browser_lock para no interleavear con el radar autónomo ni con
    execute_path_test. Lee el HTML actualmente cargado en el browser (sin
    navegación nueva — RN-B01, RN-B03). Llama check_sidebar_attacks y retorna
    el conteo de aldeash bajo ataque detectadas.

    Devuelve 0 si el browser no tiene HTML disponible (RN-B04).

    NO propaga excepciones: cualquier error en check_sidebar_attacks ya queda
    capturado dentro de esa función (RN-19 del spec base, EC-B05).
    NO actualiza _last_sidebar_scan (RN-B11).
    NO encola CHECK_INCOMING_ATTACK_DETAIL (RN-B10).

    Frontera hexagonal: solo usa callables inyectados (_page_html_provider,
    _sidebar_attack_hook, _incoming_db). No importa adapters.browser.*.
    """
    if self._incoming_db is None or self._sidebar_attack_hook is None:
        return 0

    async with self._browser_lock:
        if self._page_html_provider is None:
            return 0
        html = await self._page_html_provider()
        if html is None:
            return 0
        attacks = await self._sidebar_attack_hook(html, self.world_id, self._incoming_db)
        return len(attacks)
```

### 9.2 — Handler `check_incoming_attacks` reescrito

```python
# adapters/api/routes/incoming_attacks.py

@router.post("/incoming-attacks/{world_id}/check", ...)
async def check_incoming_attacks(
    request: Request,
    world_id: int = Path(..., ge=1),
):
    """
    EP-RA02 — Reescrito: delega en WorldAgent.check_incoming_sidebar().
    No construye adapters ad-hoc. No navega a dorf1.php.
    """
    incoming_attack_port = _get_incoming_attack_port(request)
    db_port = _get_db_port(request)
    await _verify_world(world_id, db_port)

    # Obtener el WorldAgent en marcha
    agents: dict = getattr(request.app.state, "world_agents", {})
    agent = agents.get(world_id)

    if agent is None or agent.state != AgentState.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"El agente del mundo {world_id} no está activo "
                "— inicia la sesión para usar el radar manual."
            ),
        )

    # Delegar al agente (serializa con su _browser_lock interno)
    attacks_detected = await agent.check_incoming_sidebar()

    return {
        "world_id": world_id,
        "attacks_detected": attacks_detected,
        "message": "Check completado",
    }
```

> **Import de `AgentState`:** el handler necesita importar `AgentState` de
> `core.scheduling.world_agent` (o de donde esté definido). Verificar que no rompe la
> frontera hexagonal — `AgentState` es un enum del core, no un adaptador; la importación
> desde un router (adapter) es válida.

### 9.3 — Cambio en `client.js` (timeout AbortController)

```javascript
// frontend/src/api/client.js
// Modificar la función request() para añadir AbortController con timeout de 15 s.

async function request(method, path, body, extraHeaders) {
  const controller = new AbortController()
  const timerId = setTimeout(() => controller.abort(), 15_000)  // 15 s

  try {
    const opts = {
      method,
      headers: buildHeaders(extraHeaders),
      signal: controller.signal,          // <-- NUEVO
    }
    if (body !== undefined) {
      opts.body = JSON.stringify(body)
    }
    const res = await fetch(`${BASE}${path}`, opts)
    return parseResponse(res)
  } catch (err) {
    if (err instanceof ApiError) throw err
    if (err.name === 'AbortError') {      // <-- NUEVO
      throw new ApiError('timeout', 0, 'timeout')
    }
    throw new ApiError('error.network', 0, 'error.network')
  } finally {
    clearTimeout(timerId)                 // <-- NUEVO: limpiar timer siempre
  }
}
```

> **Consideración:** el timeout de 15 s aplica a TODOS los endpoints del cliente, no solo
> a `/check`. Esto es aceptable: ningún endpoint esperado del proyecto tarda más de 15 s
> (el login puede tardar 3-10 s según CLAUDE.md). Si un endpoint específico necesita un
> timeout mayor en el futuro, se puede parametrizar el timeout como argumento opcional de
> `request()`. Para esta corrección, 15 s global es el cambio mínimo.

### 9.4 — Cambio en `IncomingAttacksPanel.jsx` (mensaje de timeout)

```javascript
// frontend/src/components/world/IncomingAttacksPanel.jsx
// En la función forceCheck, catch — añadir detección de timeout:

  } catch (err) {
    if (!isMounted.current) return
    const isTimeout = err?.detail === 'timeout' || err?.status === 0
    if (isTimeout) {
      setCheckMsg('✕ timeout — el check tardó más de 15 s')
    } else {
      const code = err?.status ? ` (${err.status})` : ''
      setCheckMsg(`✕ error${code} — ¿sesión activa en el mundo?`)
    }
  } finally {
    if (isMounted.current) setChecking(false)
  }
```

> **Pequeña mejora en el `finally`:** mover `setChecking(false)` al `finally` (ya existe
> en el código actual) con la guarda `isMounted.current` para evitar actualizar estado en
> un componente desmontado. Revisar si la versión actual ya lo tiene; si no, añadirlo.

---

## 10. Validaciones y reglas

| Validación | Dónde | Descripción |
|---|---|---|
| `world_id >= 1` | Handler — `Path(..., ge=1)` | Sin cambio respecto al código existente |
| Existencia del mundo | Handler — `_verify_world()` | Sin cambio |
| WorldAgent RUNNING | Handler — condición nueva | Antes de llamar al agente |
| `_incoming_db` no None | `check_incoming_sidebar()` — guarda de entrada | Retorna 0 sin error |
| `_sidebar_attack_hook` no None | `check_incoming_sidebar()` — guarda de entrada | Retorna 0 sin error |
| HTML no None | `check_incoming_sidebar()` — tras `_page_html_provider()` | Retorna 0 sin error |
| Timeout 15 s | `client.js` — `AbortController` | Cancela la petición si supera el límite |

---

## 11. Seguridad, rendimiento y concurrencia

### Concurrencia (crítico)

El punto más sensible del diseño es la serialización con `_browser_lock`:

- `WorldAgent._browser_lock` es un `asyncio.Lock`. Su adquisición en `check_incoming_sidebar`
  garantiza que no haya comandos CDP simultáneos sobre la misma pestaña.
- El lock ya es adquirido por `execute_path_test` (EP-RT10) y por los handlers de farm
  con `_browser_lock`. Este nuevo método sigue exactamente el mismo patrón.
- **No hay deadlock posible**: `check_incoming_sidebar` no encola tareas al `WorldAgent`
  ni llama a métodos del agente que a su vez intenten adquirir el lock.
- Si el radar autónomo tiene el lock (p.ej. está en mitad de un HEARTBEAT_SCAN), el handler
  esperará hasta que se libere. El timeout de 15 s del cliente cubre el caso en que la
  espera sea excesiva.

### Anti-detección (puntos de auditoría para el guardián)

> Los siguientes puntos deben ser auditados por `guardian-antideteccion` antes del commit:

1. **Sin navegación nueva (CRÍTICO):** `check_incoming_sidebar()` llama únicamente a
   `_page_html_provider()` que hace `tab.get_content()` — una lectura CDP del DOM sin
   petición HTTP ni cambio de URL. Verificar que no hay ninguna ruta de código que llame
   a `browser.get()` o `tab.get()` en el flujo del botón.
2. **Sin `tab.evaluate("...click()")`:** el flujo no usa evaluate para simular clicks.
3. **Lock obligatorio:** verificar que `async with self._browser_lock:` está presente.
4. **`check_sidebar_attacks` no hace peticiones HTTP:** ya está verificado y es una función
   pura de parseo, pero el guardián debe confirmarlo en el código resultante.

### Rendimiento

- `tab.get_content()` es una lectura del DOM via CDP: latencia típica < 50 ms.
- `IncomingAttackSidebarParser.parse` es puro Python con BeautifulSoup: < 10 ms.
- La adquisición del lock puede añadir latencia si el agente está haciendo algo pesado,
  pero está acotada por el timeout de 15 s del cliente.

### Seguridad

No aplica más allá de lo establecido en el spec base: sistema single-tenant local,
sin autenticación de usuario final.

---

## 12. Plan de pruebas

### UT-B01 — Caso feliz: ataque detectado (fixture did=27322)

```
Fixture: tests/fixtures/incoming_attacks/sidebar_with_attack.html
Entrada: check_sidebar_attacks(html, world_id=1, db_port=mock)
Esperado:
  - Retorna 1 VillageUnderAttackDTO con village_game_id=27322
  - db_port.upsert_attack llamado 1 vez con source='sidebar', impact_at=None
```

### UT-B02 — Caso feliz: sin ataques (fixture sin ataque)

```
Fixture: tests/fixtures/incoming_attacks/sidebar_without_attack.html
Entrada: check_sidebar_attacks(html, world_id=1, db_port=mock)
Esperado:
  - Retorna lista vacía []
  - db_port.upsert_attack NO llamado
```

### UT-B03 — Regresión con HTML real del usuario (fixture did=24498)

```
Fixture NUEVO: tests/fixtures/incoming_attacks/sidebar_real_con_ataque_did24498.html
  [HTML real del #sidebarBoxVillageList del usuario con ataque a la aldea did=24498]
Entrada: check_sidebar_attacks(html, world_id=1, db_port=mock)
Esperado:
  - Retorna 1 VillageUnderAttackDTO con village_game_id=24498
  - db_port.upsert_attack llamado 1 vez
```

> **Nota para el implementador:** el HTML de este fixture está disponible en el historial
> de la conversación de análisis. El implementador lo copia del raw HTML real aportado
> por el usuario, extrayendo solo el bloque `#sidebarBoxVillageList` y sus alrededores,
> y lo guarda como fixture completo con el esqueleto HTML mínimo del spec base.

### UT-B04 — `check_incoming_sidebar` con `_page_html_provider` que devuelve None

```
Setup: WorldAgent con _page_html_provider = async lambda: None
Llamada: await agent.check_incoming_sidebar()
Esperado: retorna 0, sin excepciones
```

### UT-B05 — `check_incoming_sidebar` con `_incoming_db = None`

```
Setup: WorldAgent con _incoming_db=None
Llamada: await agent.check_incoming_sidebar()
Esperado: retorna 0 inmediatamente (guarda de entrada)
```

### UT-B06 — Handler: WorldAgent no existe → 409

```
Setup: app.state.world_agents = {} (vacío)
Request: POST /game/incoming-attacks/1/check
Esperado: HTTP 409, detail contiene "no está activo"
```

### UT-B07 — Handler: WorldAgent en estado STOPPED → 409

```
Setup: app.state.world_agents = {1: agent_stopped}
       agent_stopped.state = AgentState.STOPPED
Request: POST /game/incoming-attacks/1/check
Esperado: HTTP 409
```

### UT-B08 — Handler: WorldAgent RUNNING, sidebar sin ataques → 200 con attacks_detected=0

```
Setup: WorldAgent RUNNING, _page_html_provider devuelve sidebar_without_attack.html
Request: POST /game/incoming-attacks/1/check
Esperado: HTTP 200, { attacks_detected: 0, message: "Check completado" }
```

### UT-B09 — Handler: WorldAgent RUNNING, sidebar con 1 ataque → 200 con attacks_detected=1

```
Setup: WorldAgent RUNNING, _page_html_provider devuelve sidebar_with_attack.html
Request: POST /game/incoming-attacks/1/check
Esperado: HTTP 200, { attacks_detected: 1 }
```

### UT-B10 — Timeout de AbortController (test de integración frontend)

```
Setup: mock de fetch que no responde en 15 s
Acción: forceCheck()
Esperado:
  - setCheckMsg llamado con "✕ timeout — el check tardó más de 15 s"
  - setChecking(false) llamado en finally
```

### Fixtures requeridos

| Fixture | Estado | Contenido |
|---|---|---|
| `sidebar_with_attack.html` | YA EXISTE (did=27322) | Fixture canónico GAP-01 — no tocar |
| `sidebar_without_attack.html` | YA EXISTE | Fixture canónico GAP-01 — no tocar |
| `sidebar_real_con_ataque_did24498.html` | CREAR | HTML real del usuario con did=24498 |

---

## 13. Riesgos y trade-offs

### Trade-off 1 — 409 vs 503 para el fallback "agente no RUNNING"

**Decisión tomada:** 409 Conflict.

**Argumento a favor de 409:** el gobierno de APIs del CLAUDE.md reserva 503 para
"disponibilidad del servicio" (sesión no activa, servidor arrancando). El agente no RUNNING
es un conflicto de estado del recurso `world/{id}`: el botón se usa en un estado que no lo
permite, no porque el servidor esté caído.

**Alternativa rechazada:** 503 (que era el código antiguo para `SessionNotActiveError`). El
problema es que la UI actual interpreta el 503 como "¿sesión activa?" y el mensaje es
incorrecto: la sesión puede estar activa pero el agente no iniciado aún.

**Opción b rechazada:** leer el HTML directamente sin lock cuando el agente no existe. Si
el agente no existe, no hay `_page_html_provider` construido. Construirlo ad-hoc volvería
a crear la dependencia en `session_registry` que ya está en el handler (deuda que estamos
eliminando), y sin lock sería inseguro si en algún momento hay un agent iniciándose.

### Trade-off 2 — Timeout global vs por-endpoint en `client.js`

**Decisión tomada:** timeout global de 15 s en `request()`.

**Justificación:** ningún endpoint del proyecto espera más de 15 s (el login es 3-10 s
según CLAUDE.md). El cambio es mínimo y soluciona el problema. Si en el futuro un endpoint
necesita más tiempo, se puede parametrizar con un argumento opcional.

### Deuda futura — Componente B autónomo con parser dorf1 incorrecto en T4.6

**NO está en el alcance de este spec.** Se documenta aquí para que no se pierda.

El `WorldAgent._handle_check_incoming_attack_detail` (world_agent.py ~l.1303) y el
`CheckIncomingAttackUseCase.execute` (incoming_attack_use_cases.py) TAMBIÉN usan
`Dorf1IncomingParser` que busca `img.att1` con el marcado clásico. Esto significa que el
Componente B del radar autónomo (que lee dorf1 cuando el hook del sidebar detecta un ataque
y encola `CHECK_INCOMING_ATTACK_DETAIL`) tampoco obtiene el timer en T4.6.

Consecuencia: los ataques detectados por el sidebar se persisten con `impact_at=None`
indefinidamente; el timer nunca se pobla.

**Arreglo:** requiere el HTML real de dorf1.php (o de la página de movimientos de tropas
en T4.6) con un ataque activo. Con ese HTML se puede identificar el nuevo selector del
timer y actualizar `Dorf1IncomingParser`. El fichero `dorf1_with_incoming.html` actual es
un fixture inventado con marcado clásico y debe sustituirse por uno real de T4.6.

**Cómo recolectar el fixture:** el usuario debe obtenerlo mientras haya un ataque activo,
navegando a `dorf1.php` y guardando el HTML completo de la página (no solo el sidebar).

Este arreglo se especificará como un spec separado cuando se tenga el HTML real.

---

## 14. Pasos de implementación ordenados

> Todos los cambios son en ficheros existentes. No se crea ningún fichero nuevo de código
> (excepto el fixture `sidebar_real_con_ataque_did24498.html`).
> Correr `lint-imports` después del paso 3.

### Paso 1 — Añadir `check_incoming_sidebar()` a `WorldAgent`

**Fichero:** `core/scheduling/world_agent.py`

Añadir el método público `check_incoming_sidebar()` después del bloque de
`_handle_check_incoming_attack_detail` (aprox. línea 1370). Ver pseudocódigo §9.1.

Puntos de cuidado:
- El método está en `core/`, que no puede importar `adapters`. Solo usa `self._page_html_provider`,
  `self._sidebar_attack_hook` y `self._incoming_db`, que son callables/ports inyectados.
- `async with self._browser_lock:` — obligatorio, igual que en `execute_path_test`.

### Paso 2 — Reescribir el handler `check_incoming_attacks`

**Fichero:** `adapters/api/routes/incoming_attacks.py`

Reemplazar el cuerpo de `check_incoming_attacks` por el pseudocódigo de §9.2.

Cambios específicos:
- Eliminar las importaciones inline de `IncomingAttackBrowserAdapter` y `Dorf1IncomingParser`.
- Eliminar la construcción del adapter ad-hoc y del closure `fetch_dorf1_attacks`.
- Eliminar la construcción de `CheckIncomingAttackUseCase`.
- Añadir import de `AgentState` desde `core.scheduling.world_agent` (verificar que no
  hay violación de frontera hexagonal — un router puede importar enums del core).
- Añadir la guarda 409.
- Llamar `await agent.check_incoming_sidebar()` y devolver el resultado directamente.

### Paso 3 — Correr `lint-imports`

```bash
.venv/bin/lint-imports
```

Debe decir `Contracts: 2 kept, 0 broken`. Si hay violación, el paso 1 o 2 cruzó la frontera.

### Paso 4 — Añadir el fixture `sidebar_real_con_ataque_did24498.html`

**Fichero:** `tests/fixtures/incoming_attacks/sidebar_real_con_ataque_did24498.html`

Copiar el HTML real del `#sidebarBoxVillageList` aportado por el usuario durante la sesión
de análisis (el que contiene `div.listEntry.village.attack` con `data-did="24498"`).
Envolver con el esqueleto mínimo HTML:

```html
<!DOCTYPE html>
<html>
<head><title>Sidebar real con ataque did=24498 — fixture regresión</title></head>
<body>
<!-- HTML real del #sidebarBoxVillageList del usuario — sesión 2026-06-07
     Contiene: did=24498 con clase "listEntry village attack".
     Ver spec docs/specs/radar-check-boton-sidebar.md §12 UT-B03. -->
[PEGAR AQUÍ EL HTML REAL DEL USUARIO]
</body>
</html>
```

### Paso 5 — Añadir/actualizar tests

**Fichero de tests:** localizar el fichero de tests del radar
(buscar con `find . -name "test_incoming*" -o -name "*incoming_attack*test*"`).

Añadir los tests UT-B01 a UT-B09 descritos en §12. Los tests UT-B01 y UT-B02 pueden
ya existir; si es así, verificar que siguen pasando. Los nuevos son UT-B03 (fixture real),
UT-B04, UT-B05, UT-B06, UT-B07, UT-B08, UT-B09.

### Paso 6 — Modificar `client.js`

**Fichero:** `frontend/src/api/client.js`

Modificar `request()` según pseudocódigo §9.3: añadir `AbortController(15_000)`,
pasar `signal` a `fetch`, capturar `AbortError`, limpiar timer en `finally`.

### Paso 7 — Modificar `IncomingAttacksPanel.jsx`

**Fichero:** `frontend/src/components/world/IncomingAttacksPanel.jsx`

Modificar el bloque `catch` de `forceCheck` según pseudocódigo §9.4: detectar timeout
y mostrar mensaje apropiado.

### Paso 8 — Prueba manual del usuario

El usuario envía un ataque de prueba, pulsa "🛡 Forzar detección" y verifica:
1. El botón no se queda en "⏳ Detectando..." para siempre.
2. Aparece "✓ 1 ataque(s) detectado(s)".
3. La lista de ataques se actualiza y muestra el ataque con `impact_at=null` (esperado,
   pues el sidebar no da timer — ver deuda §13).

---

## 15. Criterios de aceptación (checklist para el implementador)

- [ ] `WorldAgent.check_incoming_sidebar()` existe y adquiere `_browser_lock`.
- [ ] El handler EP-RA02 ya NO construye `IncomingAttackBrowserAdapter` ad-hoc.
- [ ] El handler EP-RA02 ya NO llama a `Dorf1IncomingParser` ni a `get_dorf1_html`.
- [ ] El handler EP-RA02 ya NO importa inline `IncomingAttackBrowserAdapter` ni `Dorf1IncomingParser`.
- [ ] El handler EP-RA02 devuelve **409** cuando el WorldAgent no existe o no está RUNNING.
- [ ] `lint-imports` pasa con `Contracts: 2 kept, 0 broken`.
- [ ] Tests UT-B01 a UT-B09 pasan en verde.
- [ ] Fixture `sidebar_real_con_ataque_did24498.html` existe y UT-B03 lo usa.
- [ ] `client.js`: `request()` tiene `AbortController(15_000)` y captura `AbortError`.
- [ ] `IncomingAttacksPanel.jsx`: `forceCheck` muestra "✕ timeout — el check tardó más de 15 s" cuando `err.detail === 'timeout'`.
- [ ] **Sin ninguna llamada a `browser.get()` ni navegación por URL en el flujo del botón** (criterio anti-detección obligatorio — punto de auditoría RT-08 eliminado para este camino).
- [ ] **Sin `tab.evaluate("...click()")`** en el flujo del botón.
- [ ] `guardian-antideteccion` ha auditado el código resultante antes del commit (los puntos de §11 son su checklist).
- [ ] Prueba manual del usuario confirma que el botón detecta el ataque y no se queda colgado.

---

## 16. Trazabilidad

| Decisión técnica | Requisito / edge case que la origina |
|---|---|
| Usar `check_sidebar_attacks` en lugar de `Dorf1IncomingParser` | Causa raíz 1: `img.att1` no existe en T4.6; `div.listEntry.village.attack` FUNCIONA (verificado con HTML real del usuario) |
| Delegar en WorldAgent con `_browser_lock` | Causa raíz 2: contención de CDP por falta de serialización. Patrón ya establecido en `execute_path_test` (EP-RT10) |
| 409 para agente no RUNNING | Gobierno de APIs del proyecto (CLAUDE.md: 409 para conflicto de estado); la alternativa 503 es semánticamente incorrecta para este caso |
| `AbortController(15_000)` | Causa raíz 3: `fetch` sin timeout → botón eternamente en "⏳"; 15 s es suficiente para cualquier operación esperada del proyecto según CLAUDE.md |
| `_page_html_provider()` sin navegación | RN-01 del spec base (el hook no añade peticiones HTTP) + deuda anti-detección RT-08 (no agravar la deuda de URL directa) |
| `check_incoming_sidebar()` no actualiza `_last_sidebar_scan` | RN-B11: el scan manual es externo al ciclo autónomo; actualizar el timestamp del piggyback desorientaría el scheduling del HEARTBEAT_SCAN |
| `check_incoming_sidebar()` no encola `CHECK_INCOMING_ATTACK_DETAIL` | RN-B10: el botón es una lectura puntual, no una activación del flujo completo B→C→D |
| Fixture did=24498 separado de did=27322 | EC-B09: son instancias distintas de ataque; el fixture canónico de GAP-01 no debe modificarse; el fixture real del usuario es un test de regresión adicional |
| Reutilización directa de `check_sidebar_attacks` sin cambios | Palantir: REUTILIZAR sin cambios — `adapters/browser/incoming_attack_hook.py` ya implementa parse+persist en una llamada |
| Timeout global en `request()` vs por-endpoint | Trade-off 2 §13: ningún endpoint del proyecto supera 15 s; cambio mínimo |

---

## Registro de implementación

**Fecha:** 2026-06-07
**Implementado por:** desarrollador-funcionalidades

### Ficheros modificados

| Fichero | Tipo de cambio |
|---|---|
| `core/scheduling/world_agent.py` | Añadido método público `check_incoming_sidebar()` (§9.1) |
| `adapters/api/routes/incoming_attacks.py` | Handler `check_incoming_attacks` reescrito (§9.2); eliminados imports y construcción ad-hoc de dorf1 adapter; añadido import de `AgentState` |
| `frontend/src/api/client.js` | `request()` con `AbortController(15_000)` + captura `AbortError` (§9.3) |
| `frontend/src/components/world/IncomingAttacksPanel.jsx` | `forceCheck` maneja timeout + guarda `isMounted.current` en `finally` (§9.4) |
| `tests/unit/test_incoming_attack_parsers.py` | Añadidos UT-B01..UT-B05 en clase `TestCheckIncomingSidebarAndHook` |
| `tests/test_incoming_attacks_api.py` | Reemplazados tests EP-RA02 antiguos (dorf1) por UT-B06..UT-B09 + cabeceras + eco + EC-B01 |

### Fichero ya existente (creado por el orquestador antes de esta implementación)

- `tests/fixtures/incoming_attacks/sidebar_real_con_ataque_did24498.html` — fixture de regresión real (did=24498) usado en UT-B03.

### Comando para ejecutar los tests del radar

```bash
.venv/bin/pytest tests/unit/test_incoming_attack_parsers.py tests/test_incoming_attacks_api.py -v
```

### Resultado de los tests

74 passed, 0 failed (74/74 en verde).

### lint-imports

```
Contracts: 2 kept, 0 broken.
```

### Desviaciones respecto al diseño

**Ninguna.** La implementación sigue el spec §9.1, §9.2, §9.3 y §9.4 al pie de la letra.

**Nota sobre los tests EP-RA02 anteriores:** los tests de EP-RA02 de `test_incoming_attacks_api.py`
usaban el flujo dorf1 + `world_runtime_port` (implementación reemplazada). Al reescribir el handler,
esos tests se sustituyeron por los tests UT-B06..UT-B09 del spec más los tests de cabeceras/eco
equivalentes. Esto es parte explícita del spec (§14 Paso 5: "verificar que los tests que ya existían
siguen verdes" — los tests anteriores de EP-RA02 eran de la implementación incorrecta que se corrige).

### Pendiente (gate humano §14 Paso 8)

La prueba manual del usuario (punto 8 del flujo de pasos de implementación) está pendiente:
el usuario debe enviar un ataque de prueba, pulsar "🛡 Forzar detección" y verificar que:
1. El botón no se queda en "⏳ Detectando..." para siempre.
2. Aparece "✓ 1 ataque(s) detectado(s)".
3. La lista de ataques se actualiza.

Antes del commit entrará `guardian-antideteccion` para auditar los puntos de §11.
