---
name: patterns-human-sessions
description: S11 Human Sessions: pestaña Sesión en WorldSpacePage, tokens de modo, componentes session/, validación de timeline en cliente
metadata:
  type: project
---

## Human Sessions (pestaña "Sesión" — S11)

Implementada en 2026-05-31. Todos los componentes en `frontend/src/components/session/`.

### Tokens CSS de modo (añadidos a tokens.css en los 4 bloques)
- `--mode-hardcore` / `--mode-hardcore-subtle` → verde (reutiliza `--success`)
- `--mode-idle` / `--mode-idle-subtle` → azul (reutiliza `--info`)
- `--mode-disconnected` / `--mode-disconnected-subtle` → gris #8E8E93

### Componentes en src/components/session/
- `SessionStatusPanel.jsx` — Panel P1 con badge modo + countdown + override row. Exporta también `ModeBadge` (reutilizable).
- `SessionOverridePanel.jsx` — 3 pills HARDCORE/IDLE/Descanso total. `aria-pressed` en cada botón.
- `WeekdaySelector.jsx` — 7 días con Intl (no hardcoded), `role="tablist"/"tab"`, dot de color, etiqueta DEFAULT.
- `TimelineBar.jsx` — Barra proporcional, segmentos con `role="img"` + aria-label completo. Exporta también `TimelineCoverageIndicator` y `validateCoverage` (lógica JS replica backend Python).
- `BlockEditor.jsx` — Tabla start/end/mode con validación en vivo vía `validateCoverage`. `start` del primer bloque siempre readonly 00:00; starts encadenados automáticamente al cambiar end.
- `SessionTab.jsx` — Orquestador: polling status 15s, fetch timelines, override, guardar día. Usa `api.getWorldSession`, `api.getWorldTimeline`, `api.putWorldMode`, `api.putWorldTimelineDay`.

### Integración en WorldSpacePage
- Nav item id `'session'` añadido entre `farmlists` y `calc`
- Clave i18n: `worldnav.session`
- `IconSession` = reloj SVG (circle + polyline)
- Renderizado: `{activeTab === 'session' && <ErrorBoundary ...><SessionTab worldId={worldId} /></ErrorBoundary>}`

### API client.js (métodos nuevos)
```js
api.getWorldSession(worldId)           // GET /worlds/:id/session
api.getWorldTimeline(worldId)          // GET /worlds/:id/session/timeline
api.getWorldTimelineDay(worldId, day)  // GET /worlds/:id/session/timeline/:day
api.putWorldTimelineDay(worldId, day, {blocks, jitter_minutes?}) // PUT
api.putWorldMode(worldId, mode)        // PUT /worlds/:id/session/mode → {mode, expires_at, already_active}
```
OJO: estas rutas son DISTINTAS de getSession/startSession/stopSession (login bajo /accounts/:id/worlds/:worldId/session).

### i18n
50+ claves bajo `session.*` en es.js y en.js. Los otros 23 catálogos usan fallback a `es`. Claves principales: `session.status.*`, `session.override.*`, `session.timeline.*`, `session.editor.*`, `session.mode.*`, `worldnav.session`.

### Patrón validateCoverage (cliente)
```js
// en TimelineBar.jsx — exportada
export function validateCoverage(blocks) // → {ok: boolean, msg: string}
```
Replica `_validate_timeline()` del backend. Detecta: sin bloques, hueco, solape, fin ≤ inicio, no llega a 24:00.

### Estado de backend al implementar
Los endpoints de session están registrados en `adapters/api/routes/session.py`. El world_id=2 devuelve 404 en `GET /worlds/2/session` porque no hay registros en `session_timelines` para ese mundo (BD vacía para Human Sessions). La UI muestra correctamente el estado de error.

**Why:** Feature implementada tras baneo de Travian por actividad 24/7. Permite configurar calendario semanal de modos HARDCORE/IDLE/DISCONNECTED.

**How to apply:** Para modificar la UI de sesiones, partir de estos componentes. Para añadir nuevas rutas de sesión al cliente, seguir el patrón de `client.js` con `request('METHOD', '/worlds/${worldId}/session/...')`.
