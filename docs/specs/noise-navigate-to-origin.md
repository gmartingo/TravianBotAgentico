# Spec — "Ir al inicio": llevar el Chrome del bot a la pantalla del ancla de origen

> **Feature:** noise-navigate-to-origin (anexo del Noise Path Wizard)
> **Estado:** `ready-for-impl` — sin preguntas abiertas bloqueantes (ver §11; las preguntas son confirmaciones de UX, no bloquean el contrato ni el dominio).
> **APIs validadas por desarrollador-apis:** `false` — el contrato de §5 está completo y listo; **pendiente de revisión por `desarrollador-apis` en MODO REVISIÓN DE CONTRATO antes del primer commit** (este analista no tiene el subagente disponible en este contexto).
> **Gate guardian-antideteccion:** `OBLIGATORIO` — esta feature ejecuta `browser.get()` real contra Travian (toca `core/scheduling/world_agent.py` y el browser vivo). Ver §8.
> **Gate mockup-first:** `LIGERO` — añade un único botón + estados de feedback a un componente existente (`NoiseOriginSelector.jsx`). Ver §9.
> **Relación con specs previas:** delta sobre `noise-path-wizard.md` (en especial §16 / EP-N14 "Probar ruta", del que reutiliza casi toda la infraestructura). NO modifica entidades de datos, ni tablas, ni contratos existentes. Añade **un endpoint** (EP-N15) y **un método** en `WorldAgent` (`navigate_to_origin`), más un **helper compartido** (`_origin_to_relative_url`) que extrae lógica ya existente inline en `execute_path_test`.

---

## 1. Contexto y objetivo de negocio

### 1.1 La necesidad

En el **wizard de creación de rutas de ruido** (`frontend/src/components/world/noise/NoisePathWizard.jsx` + `NoiseOriginSelector.jsx`), el usuario selecciona un **origen / ancla** (la pantalla de Travian desde la que arranca la ruta de navegación) y luego graba los **pasos** (clicks) pegando el `outerHTML` de cada elemento que quiere clicar. Ese flujo de `derive-selector` (EP-N11) parte de elementos que el usuario inspecciona **en la página del ancla**.

Hoy el usuario tiene que llevar el Chrome del bot manualmente a esa pantalla para poder inspeccionar elementos. Esta feature añade un **botón explícito "Ir al inicio"** junto al selector de origen: al pulsarlo, el Chrome real del bot (la sesión viva del mundo) **navega a la URL del ancla seleccionada**, de modo que el usuario vea esa página y pueda copiar desde ahí el `outerHTML` de los siguientes clicks.

### 1.2 Lo que NO es

- **No** graba clicks ni automatiza la inspección: solo deja el browser en la pantalla correcta.
- **No** ejecuta la ruta (eso es EP-N14 "Probar ruta").
- **No** es destructivo: no toca contadores, ni `is_dead`, ni `last_used_at`, ni dwell, ni BD.

### 1.3 Decisiones YA tomadas con el usuario (NO reabrir)

| # | Decisión | Razón |
|---|---|---|
| D1 | **Disparador = botón explícito** "Ir al inicio". El Chrome navega SOLO al pulsarlo. **NUNCA** automáticamente al cambiar el desplegable de origen. | Anti-detección: evitar navegaciones reales involuntarias cada vez que el usuario explora el selector. |
| D2 | **Mecanismo = `browser.get(URL_del_ancla)`** — exactamente el patrón ya aceptado por el guardian en `execute_path_test` (RN-PT03). NO se navega "clicando el menú". | Patrón ya auditado y aprobado para EP-N14. |

---

## 2. Actores

| Actor | Rol |
|---|---|
| Usuario | Selecciona un origen en el wizard y pulsa "Ir al inicio". Lee el feedback. |
| Frontend (`NoiseOriginSelector.jsx`) | Renderiza el botón, gestiona estados (disabled/loading/éxito/error), llama a `api.navigateNoiseToOrigin`. |
| Backend (FastAPI, `routes/noise.py`) | Valida el `origin`, verifica sesión activa, delega en el agente, mapea errores a HTTP. |
| WorldAgent (`core/scheduling/world_agent.py`) | Calcula la URL del ancla (helper compartido), adquiere el lock de browser y ejecuta `browser.get()`. |
| Chrome del bot | Browser real donde ocurre la navegación. |

No hay roles de autorización diferenciados: sesión única por mundo, igual que el resto del subsistema de ruido.

---

## 3. Reglas de negocio (RN)

**RN-NO01 — Requiere sesión de browser activa (agente RUNNING + `_session_active()`).**
La navegación usa el Chrome real del bot. Precondición idéntica a EP-N14 (ver `routes/noise.py:1287-1296`): si el `WorldAgent` no existe para el mundo, o `agent.state != AgentState.RUNNING`, o `not agent._session_active()` → **409** con `detail` legible ("inicia sesión primero"). Que el agente esté RUNNING no implica que el browser esté abierto (en un bloque horario DISCONNECTED el browser está cerrado), por eso se comprueba también `_session_active()`.

**RN-NO02 — Solo navega, NO destructivo.**
La ejecución NO modifica ningún dato persistente: no incrementa `consecutive_failures_count`, no marca `is_dead`, no actualiza `last_used_at`, no ejecuta dwell, no escribe en `NoiseDbPort`. Verificable por grep: `navigate_to_origin` no llama a ningún método write del puerto de BD.

**RN-NO03 — Validación del `origin` contra las anclas válidas y las aldeas del mundo.**
El `origin` del body se valida con `_validate_origin(origin, [v.data_id for v in villages])` — el **mismo helper ya existente** en `adapters/db/noise_sqlite_adapter.py:399`. Acepta los 9 genéricos del enum `NavigationOrigin` y `VILLAGE_<data_id>` donde `data_id` esté en las aldeas del mundo. Cualquier otro valor → **422** con `detail` legible. La lista de aldeas se obtiene con `noise_db.get_villages_for_world(world_id)` (igual que EP-N12).

**RN-NO04 — Caso `origin == "ANY"`: no hay ancla, no se navega.**
`ANY` significa "el bot parte de donde esté" (no tiene URL de ancla, `ORIGIN_PATHS[ANY] == ""`). El endpoint **no navega** y responde **200** con `navigated: false` y `navigated_to: null` (mensaje semántico "sin ancla; el bot parte de la página actual"). El frontend **deshabilita** el botón cuando `origin == "ANY"` (ver §6), de modo que en la práctica este 200-sin-navegar es una salvaguarda del backend, no el camino normal.

**RN-NO05 — Concurrencia: lock de browser compartido.**
La navegación adquiere `WorldAgent._browser_lock` (el `asyncio.Lock` ya introducido en §16, que serializa `_execute_noise_action`, `refresh_villages` y `execute_path_test`). Se adquiere con `asyncio.wait_for(lock.acquire(), timeout=NAVIGATE_TO_ORIGIN_TIMEOUT_SECONDS)`; si vence el timeout (el browser está ocupado ejecutando ruido o un test) → `BrowserBusyError` → handler → **409** "el bot está ocupado, espera".

**RN-NO06 — Anti-detección: navegación humanizada idéntica a EP-N14.**
Tras `browser.get(anchor_url)` se aplica `await human_delay(500, 900)` (mismo patrón que `execute_path_test`, `world_agent.py:1496-1497`). NO se hacen clicks sintéticos ni se manipula el menú. Una sola navegación de URL directa, exactamente como el patrón ya aprobado por el guardian.

**RN-NO07 — Reutilización del cálculo origin→URL (CERO duplicación).**
El bloque que mapea `origin` → URL relativa vive hoy **inline** en `execute_path_test` (`world_agent.py:1476-1489`: `VILLAGE_<id>` → `/dorf1.php?newdid=<id>`; enum genérico → `ORIGIN_PATHS[...]`; desconocido → `""`). DEBE **extraerse a un helper compartido** `WorldAgent._origin_to_relative_url(origin: str) -> str` (o función de módulo), y `execute_path_test` debe pasar a usarlo. `navigate_to_origin` usa el mismo helper. Resultado: un solo punto de verdad para el parsing origin→URL. La construcción absoluta sigue siendo `build_url(server, relative)` (`adapters/browser/url_utils.py:6`).

**RN-NO08 — Servidor del mundo disponible.**
Para construir la URL absoluta se necesita el servidor del mundo vía `session_registry.get_world_server(world_id)`. Si devuelve vacío/None (no debería si la sesión está activa, pero se blinda igual que `world_agent.py:1470-1474`) → `RuntimeError` → **500**. En la práctica RN-NO01 ya garantiza sesión activa, así que el servidor estará disponible.

**RN-NO09 — Fallo de la navegación real → 500 (no 200 con error).**
A diferencia de EP-N14 (que reporta el fallo de navegación como un "paso sintético" dentro de un reporte 200), aquí **no hay reporte paso a paso**: la operación es atómica "navega o no". Si `browser.get()` lanza (URL inalcanzable, error CDP/zendriver) → el agente propaga `RuntimeError` → handler → **500** con `detail` legible. El éxito es **200**. *(Decisión de diseño: ver §10, justifica por qué aquí el fallo de navegación es 500 y no un 200 semántico.)*

**RN-NO10 — Estado final del browser no se restaura.**
Tras la navegación, el browser queda en la página del ancla — que es precisamente el objetivo (que el usuario inspeccione esa página). No se restaura la página previa. Documentado para el usuario.

---

## 4. Flujo principal y alternativos

### 4.1 Flujo principal (origen genérico o por-aldea válido, sesión activa)

1. Usuario selecciona un origen (p.ej. `MAP` o `VILLAGE_12345`) en `NoiseOriginSelector`.
2. Usuario pulsa **"Ir al inicio"**. El botón pasa a `loading`.
3. Frontend → `POST /worlds/{id}/noise/navigate-to-origin` con body `{ "origin": "<valor>" }` y `Accept-Language`.
4. Backend: `_verify_world_exists` → gate RUNNING + `_session_active()` → valida `origin` con `_validate_origin` → delega en `agent.navigate_to_origin(origin)`.
5. Agente: calcula `relative = _origin_to_relative_url(origin)`; obtiene `server`; `anchor_url = build_url(server, relative)`; adquiere `_browser_lock` (con timeout); `await browser.get(anchor_url)`; `await human_delay(500, 900)`; libera lock; devuelve `anchor_url`.
6. Backend responde **200** `{ "navigated": true, "navigated_to": "<anchor_url>", "origin": "<valor>" }`.
7. Frontend muestra feedback breve de éxito ("Chrome en la pantalla de inicio").

### 4.2 Alternativos

| Flujo | Condición | Resultado |
|---|---|---|
| A1 | `origin == "ANY"` | Backend responde **200** `{ navigated: false, navigated_to: null }`. (UI ya deshabilita el botón; salvaguarda.) |
| A2 | No hay agente / `state != RUNNING` / `not _session_active()` | **409** "inicia sesión primero". |
| A3 | Browser ocupado (lock no adquirido en `NAVIGATE_TO_ORIGIN_TIMEOUT_SECONDS`) → `BrowserBusyError` | **409** "el bot está ocupado, espera". |
| A4 | `origin` inválido (no enum y no `VILLAGE_<id>` válido) | **422** con `detail` del `ValueError` de `_validate_origin`. |
| A5 | Mundo inexistente | **404** "Mundo no encontrado." |
| A6 | `browser.get()` falla (URL inalcanzable, error CDP) | **500** "Error interno del servidor." |

---

## 5. Contrato de API — EP-N15

> **PENDIENTE de validación por `desarrollador-apis`** (MODO REVISIÓN DE CONTRATO). Instrucción para el orquestador: *"MODO REVISIÓN DE CONTRATO DE DISEÑO. Decide si EP-N15 puede reutilizar algo o debe crearse tal cual; valida el contrato; devuelve luz verde + tests."*

### 5.1 Endpoint

```
POST /worlds/{world_id}/noise/navigate-to-origin
```

- **Sin prefijo `/api`** (convención del proyecto; el proxy de Vite lo retira).
- **`Accept-Language` obligatorio** (convención global; sin él → 400 del middleware de idioma, igual que el resto de endpoints).
- Path param: `world_id: int = Path(..., ge=1)`.
- Cohesión: va en el **router existente** `adapters/api/routes/noise.py`, después de EP-N14. NO se crea router nuevo.

### 5.2 Request body

```jsonc
{
  "origin": "MAP"            // o "VILLAGE_12345", "DORF1", "ANY", ...
}
```

Modelo Pydantic nuevo (junto a los demás de `noise.py`):

```python
class NavigateToOriginRequest(BaseModel):
    origin: str = Field(
        ...,
        min_length=1,
        description=(
            "Ancla de origen: un valor de NavigationOrigin "
            "(DORF1, DORF2, MAP, STATISTICS, REPORTS, MESSAGES, "
            "VILLAGE_STATISTICS, OASIS_VIEW, ANY) o 'VILLAGE_<data_id>'."
        ),
    )
```

> El body acepta **el mismo conjunto de valores que `origin` en `CreatePathRequest`** (`noise.py:299-310`), de modo que el front puede pasar directamente el `origin` que ya tiene en estado en el wizard sin transformación.

### 5.3 Respuesta de éxito — 200

```python
class NavigateToOriginResponse(BaseModel):
    navigated: bool                    # true si se navegó; false solo para ANY
    navigated_to: Optional[str] = None # URL absoluta del ancla; null si ANY
    origin: str                        # eco del origin solicitado
```

Ejemplos:

```jsonc
// Genérico / por-aldea válido con sesión activa
{ "navigated": true, "navigated_to": "https://ts1.x1.europe.travian.com/karte.php", "origin": "MAP" }

// ANY
{ "navigated": false, "navigated_to": null, "origin": "ANY" }
```

> **200 (no 201/204):** no se crea ni borra ningún recurso; es una acción imperativa sobre el browser que devuelve un cuerpo informativo. 200 es el código correcto.

### 5.4 Errores

| Código | Cuándo | `detail` (texto legible, no stack trace) |
|---|---|---|
| **400** | Falta `Accept-Language` o idioma no soportado | (lo gestiona el middleware/dependencia de idioma; no lo maneja este handler) |
| **404** | Mundo inexistente | `"Mundo no encontrado."` (vía `_verify_world_exists`) |
| **409** | No hay sesión activa (sin agente / no RUNNING / `not _session_active()`) | `"El agente del mundo está desconectado. Inicia sesión primero para poder ir a la pantalla de inicio."` |
| **409** | Browser ocupado (`BrowserBusyError`) | `"El browser está ocupado con otra tarea. Espera a que finalice e inténtalo de nuevo."` |
| **422** | `origin` inválido (`ValueError` de `_validate_origin`) | El mensaje del `ValueError` (p.ej. `"Aldea con data_id=999 no encontrada para este mundo."` o `"origin 'XXX' no es un valor válido..."`). |
| **500** | `browser.get()` falla, servidor del mundo no disponible, error inesperado | `"Error interno del servidor."` |

> **422 vs FastAPI:** la validación de Pydantic (body mal formado, `origin` ausente) ya devuelve 422 automáticamente. La validación semántica de `_validate_origin` se hace en el handler y se traduce a 422 con `HTTPException(status_code=422, detail=str(exc))`. Mismo criterio: ambos casos de "origin no aceptable" son 422.

### 5.5 Handler — patrón calcando EP-N14 (`test_path`, `noise.py:1224-1330`)

```python
class NavigateToOriginRequest(BaseModel): ...   # §5.2
class NavigateToOriginResponse(BaseModel): ...  # §5.3

@router.post(
    "/worlds/{world_id}/noise/navigate-to-origin",
    response_model=NavigateToOriginResponse,
    summary="EP-N15 — Llevar el Chrome del bot a la pantalla del ancla de origen",
)
async def navigate_to_origin(
    request: Request,
    body: NavigateToOriginRequest,
    world_id: int = Path(..., ge=1),
) -> NavigateToOriginResponse:
    from core.exceptions import BrowserBusyError
    from core.scheduling.world_agent import AgentState

    await _verify_world_exists(request, world_id)
    noise_db = _get_noise_db(request)

    # Validar el origin contra las anclas válidas + aldeas del mundo (RN-NO03).
    villages = await noise_db.get_villages_for_world(world_id)
    try:
        _validate_origin(body.origin, [v.data_id for v in villages])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Gate de sesión activa — idéntico a EP-N14 (RN-NO01).
    agents: dict = getattr(request.app.state, "world_agents", {})
    agent = agents.get(world_id)
    session_active = bool(agent is not None and agent._session_active())
    if agent is None or agent.state != AgentState.RUNNING or not session_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=("El agente del mundo está desconectado. "
                    "Inicia sesión primero para poder ir a la pantalla de inicio."),
        )

    # Delegar la navegación. ANY → navigated=false sin navegar (RN-NO04).
    try:
        navigated_to = await agent.navigate_to_origin(body.origin)
    except BrowserBusyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=("El browser está ocupado con otra tarea. "
                    "Espera a que finalice e inténtalo de nuevo."),
        )
    except RuntimeError as exc:
        logger.error("navigate_to_origin mundo %d: RuntimeError: %s", world_id, exc)
        raise HTTPException(status_code=500, detail="Error interno del servidor.") from exc
    except Exception:
        logger.exception("navigate_to_origin mundo %d: error inesperado", world_id)
        raise HTTPException(status_code=500, detail="Error interno del servidor.")

    return NavigateToOriginResponse(
        navigated=navigated_to is not None,
        navigated_to=navigated_to,
        origin=body.origin,
    )
```

> Nota de diseño: `navigate_to_origin` del agente devuelve `str | None` — la URL si navegó, `None` si `origin == "ANY"` (RN-NO04). El handler deriva `navigated` de eso. _Importar `_validate_origin` en `noise.py` desde `adapters/db/noise_sqlite_adapter.py`; ya se usa allí indirectamente vía el adaptador en `create_path`, así que `desarrollador-apis` debe decidir si conviene exponerlo desde un módulo de validación compartido en lugar de importarlo del adaptador (limpieza opcional, no bloqueante)._

---

## 6. Frontend — botón "Ir al inicio" y estados

### 6.1 Dónde

En `NoiseOriginSelector.jsx`, junto al desplegable de origen (es el componente que ya conoce `value`=origin y `worldId`). El botón vive al lado del `<select>` (sección de §6.4 layout). El estado de sesión activa lo necesita el componente para decidir `disabled`; hoy `NoiseOriginSelector` recibe `disabled` del padre — se añade una prop `sessionActive` (boolean) o se reutiliza el `disabled` existente si el padre ya lo deriva del estado de sesión del mundo (a confirmar en mockup; ver §11 PA-2).

### 6.2 Cliente HTTP — nuevo helper en `client.js`

Junto a `testNoisePath` (`client.js:475-477`):

```js
/** EP-N15 POST /worlds/:worldId/noise/navigate-to-origin → lleva el Chrome al ancla */
navigateNoiseToOrigin: (worldId, origin) =>
  request('POST', `/worlds/${worldId}/noise/navigate-to-origin`, { origin }),
```

(`request` ya inyecta `Accept-Language` automáticamente — patrón del cliente, CLAUDE.md.)

### 6.3 Estados del botón

| Estado | Condición | Apariencia / texto |
|---|---|---|
| **Deshabilitado (sin ancla)** | `origin === "ANY"` | Botón disabled + tooltip/hint "ANY no tiene pantalla de inicio". |
| **Deshabilitado (sin sesión)** | `!sessionActive` (agente no RUNNING / sin browser) | Botón disabled + hint "Inicia sesión para usar esto". |
| **Habilitado** | `origin !== "ANY"` y `sessionActive` | Botón activo, texto "Ir al inicio". |
| **Loading** | mientras se resuelve la petición | Spinner + "Yendo…" (botón disabled). |
| **Éxito** | 200 con `navigated: true` | Feedback breve (toast/línea) "Chrome en la pantalla de inicio." Se autolimpia. |
| **Éxito ANY** | 200 con `navigated: false` | (no debería ocurrir porque está disabled; si ocurre, hint "ANY parte de la página actual"). |
| **Error 409 sesión** | `ApiError.status === 409` con `detail` de sesión | "El bot está desconectado. Inicia sesión primero." |
| **Error 409 ocupado** | `ApiError.status === 409` con `detail` de browser ocupado | "El bot está ocupado, espera un momento." |
| **Error 422** | `ApiError.status === 422` | Mostrar `e.detail` (origin inválido). |
| **Error 500 / red** | otro | "No se pudo ir a la pantalla de inicio. Reintenta." |

> Diferenciar los dos 409 (sesión vs ocupado): como ambos son 409, el front se apoya en el `detail` del backend para el texto, o el backend podría devolver un campo discriminador. **Decisión:** mantener un solo código 409 y diferenciar el mensaje por `detail` (mismo criterio que EP-N13/N14, que ya usan `e.detail`). El front muestra el `detail` del backend cuando está disponible y cae al texto i18n genérico si no.

### 6.4 Textos i18n (es / en) — añadir a `frontend/src/i18n/catalog/{es,en}.js`

Bajo el namespace `noise.wizard.*` (coherente con `refreshVillages`, `originField`…):

| Clave | es | en |
|---|---|---|
| `noise.wizard.goToOrigin` | `Ir al inicio` | `Go to start screen` |
| `noise.wizard.goingToOrigin` | `Yendo…` | `Going…` |
| `noise.wizard.goToOriginSuccess` | `Chrome en la pantalla de inicio.` | `Chrome is on the start screen.` |
| `noise.wizard.goToOriginAnyDisabled` | `«Cualquier página» no tiene pantalla de inicio.` | `“Any page” has no start screen.` |
| `noise.wizard.goToOriginNoSession` | `Inicia sesión para llevar el bot a esta pantalla.` | `Start a session to take the bot to this screen.` |
| `noise.wizard.goToOriginError409Session` | `El bot está desconectado. Inicia sesión primero.` | `The bot is disconnected. Start a session first.` |
| `noise.wizard.goToOriginError409Busy` | `El bot está ocupado. Espera un momento e inténtalo de nuevo.` | `The bot is busy. Wait a moment and try again.` |
| `noise.wizard.goToOriginError422` | `Ese origen no es válido para este mundo.` | `That origin is not valid for this world.` |
| `noise.wizard.goToOriginError` | `No se pudo ir a la pantalla de inicio. Reintenta.` | `Couldn’t go to the start screen. Try again.` |

> Reutilizar `noise.wizard.refreshError409` como referencia de tono. Mantener los mismos endónimos/registros de los textos existentes.

---

## 7. Piezas a reutilizar vs crear

### 7.1 Reutilizar (NO rediseñar)

| Pieza | Ubicación (file:line) | Uso |
|---|---|---|
| Mapeo `origin → URL relativa` (extraer a helper) | `core/scheduling/world_agent.py:1476-1489` (inline en `execute_path_test`) | Extraer a `_origin_to_relative_url`; `execute_path_test` pasa a usarlo. **RN-NO07.** |
| `ORIGIN_PATHS` + enum `NavigationOrigin` | `core/entities/noise.py:32-66` | Mapa genéricos → ruta; `ANY` → `""`. |
| `build_url(base, path)` | `adapters/browser/url_utils.py:6` | URL absoluta del ancla. |
| `_validate_origin(origin, village_ids)` | `adapters/db/noise_sqlite_adapter.py:399` | Validación 422 del origin. |
| `noise_db.get_villages_for_world(world_id)` | usado en EP-N12 (`noise.py:1110`) | Lista de aldeas para validar `VILLAGE_<id>`. |
| `session_registry.get_browser / get_world_server` | `adapters/browser/session_registry.py:149,158` | Browser vivo + servidor del mundo. |
| `WorldAgent._browser_lock` (asyncio.Lock) | introducido en §16 | Serializa con ruido/test (RN-NO05). |
| `WorldAgent._session_active()` | `core/scheduling/world_agent.py:403` | Gate de sesión (RN-NO01). |
| `BrowserBusyError` | `core/exceptions.py` (creada en §16) | 409 browser ocupado. |
| `human_delay(500, 900)` | usado en `world_agent.py:1497` | Humanización post-navegación (RN-NO06). |
| Patrón de handler EP-N14 `test_path` | `adapters/api/routes/noise.py:1224-1330` | Plantilla del handler EP-N15. |
| Patrón handler sin body EP-N13 `refresh_villages` | `adapters/api/routes/noise.py:1146-1217` | Referencia de gate RUNNING. |
| `_verify_world_exists` | `adapters/api/routes/noise.py:80` | 404 mundo inexistente. |
| `NoiseOriginSelector.jsx` | `frontend/src/components/world/noise/` | Componente donde vive el botón. |
| Helpers `api.refreshNoiseVillages` / `api.testNoisePath` | `frontend/src/api/client.js:471-477` | Plantilla de `api.navigateNoiseToOrigin`. |

### 7.2 Crear (mínimo nuevo)

| Pieza | Ubicación | Qué |
|---|---|---|
| `WorldAgent._origin_to_relative_url(origin: str) -> str` | `core/scheduling/world_agent.py` | Helper extraído (RN-NO07). Refactor de `execute_path_test` para usarlo. |
| `WorldAgent.navigate_to_origin(origin: str) -> str \| None` | `core/scheduling/world_agent.py` | Lógica: ANY→None; resto→lock + `browser.get` + `human_delay`; devuelve URL o None. |
| `NAVIGATE_TO_ORIGIN_TIMEOUT_SECONDS` (constante) | `core/scheduling/world_agent.py` | Timeout de adquisición de lock. Sugerido: reutilizar `PATH_TEST_TIMEOUT_SECONDS` (60 s) o un valor menor (la navegación es más corta; 30 s suficiente). **Ver §11 PA-1.** |
| `NavigateToOriginRequest` / `NavigateToOriginResponse` | `adapters/api/routes/noise.py` | Modelos Pydantic. |
| Handler `navigate_to_origin` (EP-N15) | `adapters/api/routes/noise.py` | §5.5. |
| `api.navigateNoiseToOrigin(worldId, origin)` | `frontend/src/api/client.js` | §6.2. |
| Botón + estados + i18n | `NoiseOriginSelector.jsx` + catálogos | §6. |
| Tests | `tests/` | §12. |

---

## 8. Anti-detección — gate guardian-antideteccion (OBLIGATORIO)

Esta feature ejecuta `browser.get()` real contra Travian desde `core/scheduling/world_agent.py` y el browser vivo → **toca la interacción con la web de Travian**. Por CLAUDE.md, el `guardian-antideteccion` DEBE auditar `navigate_to_origin` y el refactor de `_origin_to_relative_url` **antes del primer commit**.

Puntos a verificar por el guardian:
- La navegación es **una sola `browser.get(url)` directa** + `human_delay(500, 900)`, idéntica al patrón ya aprobado en `execute_path_test` (RN-PT03). NO hay clicks sintéticos ni manipulación de menú.
- **D1**: solo se navega al pulsar el botón explícito, nunca automáticamente al cambiar el desplegable. Verificar en el front que `onChange` del select NO dispara la navegación.
- No se introduce ningún selector por texto visible.
- El lock `_browser_lock` impide que la navegación pise una sesión de ruido en curso (no se solapan gestos en el mismo tab).
- No se altera la config del browser ni timings globales.

---

## 9. Gate mockup-first (UI)

La feature añade **un único botón + estados de feedback a un componente existente** (`NoiseOriginSelector.jsx`), no una vista nueva. Por la regla mockup-first del proyecto, antes de implementar la UI hay que pasar por el `disenador-producto`/mockup editable, pero el cambio es **lo bastante pequeño como para un mockup ligero**: basta con un `frontend/mockups/noise-origin-selector.playground.html` (o ampliar el del wizard si existe) que muestre el botón en sus estados (habilitado / disabled-ANY / disabled-sin-sesión / loading / éxito / error) junto al `<select>` de origen, para que el usuario apruebe posición y microcopy. No requiere rediseño completo de pantalla.

> **Gate humano de prueba manual** (CLAUDE.md paso 8): tras implementar, el usuario prueba en Chrome real + Travian real (selecciona un origen, pulsa "Ir al inicio", verifica que el Chrome del bot navega a la pantalla correcta) y da OK explícito **antes** de cualquier commit.

---

## 10. Decisiones de diseño y trade-offs

**D-10.1 — Fallo de navegación = 500, no 200 semántico (RN-NO09).**
EP-N14 devuelve 200 incluso cuando la ruta falla, porque su producto es un *reporte diagnóstico* paso a paso (el fallo de un paso es información útil, no un error del endpoint). EP-N15 es distinto: su único producto es "el browser quedó en la pantalla X". No hay reporte que entregar. Si `browser.get()` falla, no hay nada semántico que devolver con éxito → 500 es correcto y más simple. Mantener la asimetría con EP-N14 es intencionado.

**D-10.2 — Validar `origin` en el backend aunque la UI ya restrinja el desplegable.**
El desplegable solo ofrece orígenes válidos, pero el endpoint es público dentro del backend y debe ser robusto (defensa en profundidad). Reutilizar `_validate_origin` no cuesta nada y cierra el 422.

**D-10.3 — ANY responde 200 sin navegar en vez de 422.**
ANY es un origin **válido** (existe en el enum), simplemente no tiene ancla. Rechazarlo con 422 sería incorrecto semánticamente. El front lo deshabilita; el backend lo trata como no-op explícito (`navigated: false`).

**D-10.4 — Reutilizar `_browser_lock` y no crear uno nuevo.**
El lock de §16 ya serializa toda interacción con el tab. Crear otro abriría la puerta a que navegación y ruido se entrelacen. Reutilizar es lo correcto.

**D-10.5 — Estado final del browser no se restaura (RN-NO10).**
Dejar el browser en la pantalla del ancla **es** el objetivo de la feature, así que no hay nada que restaurar. (En EP-N14 también se acepta no restaurar.)

---

## 11. Preguntas abiertas (confirmaciones de UX — NO bloquean el contrato)

> Ninguna bloquea el dominio ni el contrato de API. Son afinados de UX que el orquestador puede confirmar con el usuario en el mockup ligero; con los defaults propuestos la feature es implementable tal cual.

- **PA-1 (timeout del lock):** ¿`NAVIGATE_TO_ORIGIN_TIMEOUT_SECONDS` = 60 s (reutilizar `PATH_TEST_TIMEOUT_SECONDS`) o un valor menor (p.ej. 30 s) dado que la navegación es más corta que un test completo? *Default propuesto: 30 s.*
- **PA-2 (fuente de `sessionActive` en el front):** ¿`NoiseOriginSelector` ya recibe del padre un indicador de sesión activa del mundo (para deshabilitar el botón), o hay que cablear una prop nueva `sessionActive` desde `NoisePathWizard`/`NoiseTab`? *Default propuesto: añadir prop `sessionActive` derivada del estado del mundo que ya consume `NoiseTab`.*
- **PA-3 (microcopy y posición del botón):** texto exacto ("Ir al inicio" vs "Ir a esta pantalla") y si va inline junto al `<select>` o debajo. A decidir en el mockup ligero. *Default propuesto: "Ir al inicio", inline a la derecha del select.*

---

## 12. Criterios de aceptación (CA)

### Backend / dominio

- **CA-01** — `POST /worlds/{id}/noise/navigate-to-origin` con `origin` genérico válido, agente RUNNING + sesión activa → 200, `navigated: true`, `navigated_to` = `build_url(server, ORIGIN_PATHS[origin])`, y se llamó a `browser.get(anchor_url)` + `human_delay`.
- **CA-02** — `origin == "VILLAGE_<id>"` con aldea existente → 200, `navigated_to` termina en `/dorf1.php?newdid=<id>`.
- **CA-03** — `origin == "ANY"` → 200, `navigated: false`, `navigated_to: null`, y NO se llamó a `browser.get`.
- **CA-04** — Sin agente / `state != RUNNING` / `not _session_active()` → 409 con `detail` de sesión.
- **CA-05** — Browser ocupado (lock no adquirido) → `BrowserBusyError` → 409 con `detail` de ocupado.
- **CA-06** — `origin` inválido (`"XXX"` o `VILLAGE_<id>` inexistente) → 422 con el mensaje de `_validate_origin`.
- **CA-07** — Mundo inexistente → 404.
- **CA-08** — `browser.get()` lanza → 500 con `detail` legible (no stack trace).
- **CA-09** — No-destructivo: tras la llamada no cambian `consecutive_failures_count`, `is_dead`, `last_used_at` de ninguna ruta/destino, ni se escribe en BD (verificable: `navigate_to_origin` no invoca métodos write del puerto).
- **CA-10** — `_origin_to_relative_url` es el único punto de cálculo origin→URL: `execute_path_test` lo usa (sin duplicar el bloque inline) y los tests existentes de EP-N14 siguen verdes.
- **CA-11** — `Accept-Language` ausente → 400 (igual que el resto de endpoints).

### Frontend

- **CA-12** — El botón "Ir al inicio" está **deshabilitado** si `origin === "ANY"` o `!sessionActive`.
- **CA-13** — Al pulsar con origen válido y sesión activa: estado loading → éxito con feedback breve.
- **CA-14** — 409 de sesión y 409 de ocupado muestran mensajes distintos (vía `detail` o i18n).
- **CA-15** — Cambiar el desplegable de origen **NO** dispara ninguna navegación (D1 / anti-detección).
- **CA-16** — `api.navigateNoiseToOrigin` envía `Accept-Language` (heredado de `request`).

### Gates de proceso

- **CA-17** — `guardian-antideteccion` ha auditado `navigate_to_origin` + refactor antes del commit (§8).
- **CA-18** — `desarrollador-apis` ha validado el contrato EP-N15 (§5) antes del commit.
- **CA-19** — Mockup ligero aprobado por el usuario (§9) antes de implementar la UI.
- **CA-20** — Prueba manual del usuario en Travian real con OK explícito antes del commit.

---

## 13. Plan de pruebas (resumen)

| ID | Caso | Setup |
|---|---|---|
| UT-NO01 | `_origin_to_relative_url("MAP")` → `/karte.php` | unit |
| UT-NO02 | `_origin_to_relative_url("VILLAGE_123")` → `/dorf1.php?newdid=123` | unit |
| UT-NO03 | `_origin_to_relative_url("ANY")` → `""` | unit |
| UT-NO04 | `_origin_to_relative_url("DESCONOCIDO")` → `""` (sin romper) | unit |
| UT-NO05 | `navigate_to_origin("ANY")` → devuelve `None`, no llama a `browser.get` | unit con browser mock |
| UT-NO06 | `navigate_to_origin("MAP")` → llama `browser.get(url)` + `human_delay`, devuelve url | unit con browser mock |
| UT-NO07 | lock ocupado → `BrowserBusyError` | unit con lock tomado |
| UT-NO08 | `browser.get` lanza → propaga `RuntimeError` | unit |
| IT-NO01..08 | mapeo HTTP de cada fila de §5.4 (200, 200-ANY, 409×2, 422, 404, 500, 400 sin Accept-Language) | API |
| RT-NO01 | tests EP-N14 existentes siguen verdes tras el refactor de `_origin_to_relative_url` | regresión |

---

## 14. Trazabilidad

| Decisión | Origen |
|---|---|
| Botón explícito, navegación solo al pulsar (D1) | Decisión cerrada con el usuario. |
| `browser.get(URL)` como mecanismo (D2) | Patrón ya aprobado por guardian en EP-N14 / RN-PT03. |
| Reutilizar mapeo origin→URL extrayéndolo a helper | Análisis de palantir (`world_agent.py:1461-1498`). |
| Gate de sesión RUNNING + `_session_active()` | Igual que EP-N14 (`noise.py:1287-1296`). |
| `_validate_origin` para 422 | `adapters/db/noise_sqlite_adapter.py:399`. |
| Lock compartido `_browser_lock` | Introducido en §16, reutilizado aquí. |

🔖 Última revisión: 2026-06-02 (analista — spec inicial `ready-for-impl`, pendiente de validación de contrato por `desarrollador-apis` y gates guardian/mockup/prueba-manual).
