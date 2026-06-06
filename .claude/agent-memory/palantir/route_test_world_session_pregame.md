---
name: route-test-world-session-pregame
description: Gate entrada "probar ruta con selección de mundo + sesión reutilizable + cerrar al parar mundo". Infraestructura existente y delta. Verificado 2026-06-05.
metadata:
  type: project
---

## Infraestructura existente (verificada en código real)

### 1. SessionRegistry (REUTILIZAR tal cual)
- `adapters/browser/session_registry.py` — singleton en `app.state.world_runtime_port`.
- `_sessions: dict[int, tuple[zd.Browser, World]]` keyed por `world_id`.
- Métodos relevantes (todos ya implementados):
  - `is_active(world_id)` / `has_active_session(world_id)` — consulta si hay sesión viva.
  - `login(account, world)` — abre Chrome + autentica.
  - `logout(world_id)` / `close_session(world_id)` — cierra Chrome. Idempotente.
  - `get_browser(world_id)` → `zd.Browser | None`.
  - `get_world_server(world_id)` → URL base del servidor.

### 2. Login/Logout use cases (REUTILIZAR tal cual)
- `core/use_cases/login_use_case.py` — `LoginUseCase.execute(account_id, world_id)`.
  - Obtiene cuenta de BD, descifra Fernet, localiza mundo, llama `registry.login(account, world)`.
- `LogoutUseCase.execute(world_id)` → `registry.logout(world_id)`.
- Endpoints HTTP:
  - `PUT /accounts/{account_id}/worlds/{world_id}/session` → login (200/401).
  - `DELETE /accounts/{account_id}/worlds/{world_id}/session` → logout (204).
  - `GET /accounts/{account_id}/worlds/{world_id}/session` → estado (active bool).
  - En `adapters/api/routes/accounts.py` líneas 394–460.

### 3. Execute_path_test / EP-RT10 (REUTILIZAR tal cual)
- `WorldAgent.execute_path_test(path)` en `core/scheduling/world_agent.py:1431`.
  - Obtiene browser de `session_registry.get_browser(world_id)` — duck typing.
  - Requiere `agent._session_active()` → True (líneas 1452–1457).
  - Adquiere `_browser_lock` con timeout 60s → `BrowserBusyError` si ocupado.
- EP-RT10 en `adapters/api/routes/route_templates.py:963–1118`.
  - Recibe `world_id` en el body (`TemplateTestRequest`).
  - Verifica `agent.state == RUNNING AND agent._session_active()` → 409 si no.
  - Llama `agent.execute_path_test(path)` directamente.

### 4. Start/Stop WorldAgent (REUTILIZAR tal cual)
- `POST /worlds/{world_id}/agent/start` — crea WorldAgent inyectando session_registry,
  login_use_case, noise_db, etc. Lanza `asyncio.Task`. En `farm.py:805–882`.
- `POST /worlds/{world_id}/agent/stop` — llama `agent.request_stop()`. Solo detiene
  el bucle de tareas. **NO cierra la sesión de Chrome**. Está separado del logout.
  En `farm.py:885–901`.
- "PARAR MUNDO" en WorldSpacePage llama `api.stopAgent(worldId)` (línea 291) → solo
  detiene el agente. No llama logout. Sesión queda viva.

### 5. Selector de mundo en /rutas (REUTILIZAR tal cual)
- `RouteTemplatesPage.jsx` ya tiene `loadWorlds()` (línea 1052): recorre cuentas →
  por cada cuenta llama `api.getWorlds(acc.id)` → flatten. Resultado en `worlds` state.
- `TestRoutePanel` (línea 584) usa ese `worlds` prop para renderizar un `<select>`
  con `w.server_url + w.account_email`. **El selector de mundo YA EXISTE en el panel
  de test**.
- `worlds` se carga en el useEffect inicial junto con las plantillas.

## Delta a crear

### CRÍTICO: "ensure_session" idempotente
EP-RT10 hoy falla con 409 si el agente no está RUNNING o no tiene sesión activa.
No existe ninguna lógica "si no hay sesión → login automático antes del test".
Hay que crear un flujo:
1. Comprobar `registry.is_active(world_id)`.
2. Si no → llamar `LoginUseCase.execute(account_id, world_id)` para abrir Chrome.
3. Si no hay WorldAgent → ¿crearlo o requerirlo separado? — esto decide el analista.

La pregunta clave: ¿el "probar ruta desde /rutas" debe arrancar el WorldAgent si no existe,
o solo asegurar la sesión de Chrome (sin el bucle de tareas)?
`execute_path_test` lo tiene el WorldAgent; si no hay agente, no hay método al que llamar.

### Enganchar cierre de sesión al "parar mundo"
`stop_agent` solo llama `agent.request_stop()`. La sesión de Chrome queda viva.
Para "cerrar al parar mundo" habría que, en `stop_agent`, llamar también
`registry.close_session(world_id)` después del stop, O dejar que el WorldAgent
lo haga en su `finally` al detenerse. Hoy no hace ninguna de las dos cosas.
Es un delta pequeño pero requiere decisión de diseño (¿cuándo exactamente?).

### Sin riesgo de duplicar selectores
El `<select>` de mundos de `TestRoutePanel` es local al componente y no está
extraído como componente reutilizable. Si hay otros lugares que necesiten el mismo
selector, se podría extraer — pero no es un bloqueante.
