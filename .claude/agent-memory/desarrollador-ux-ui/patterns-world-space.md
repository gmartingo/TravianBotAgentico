---
name: patterns-world-space
description: WorldSpacePage S9 implementada: shell con sidebar, world-header, AgentBottomBar, tabs Agentes+FarmLists, FarmListDrawer, FarmListsTab
metadata:
  type: project
---

## WorldSpacePage (S9) — shell completo implementado 2026-05-26

### Arquitectura del shell
- `WorldSpacePage.jsx` es la raíz; ruta `/mundos/:worldId`
- Layout: topbar fijo + world-header + `[sidebar 180px | contenido flex-1]` + `AgentBottomBar` fija en bottom:0
- `padding-bottom: 72px` en el área de contenido para que la barra fija no tape el scroll
- World-header: email en oro (`var(--accent-text)`) monospace 15px + badge verde "Activo" en línea 1; `server · tribu` en gris 12px línea 2
- Los datos del mundo (email, server, tribe) se obtienen haciendo `getAccounts()` y buscando el worldId en los mundos de cada cuenta

### Sidebar
- Ancho: `--sidebar-w: 180px` (constante SIDEBAR_W = 180 en el JS)
- 4 nav items: Dashboard · Agentes · Listas de vacas · Calculadora (disabled + "pronto")
- Item activo: `background: var(--accent-subtle)`, `color: var(--accent-text)`, `font-weight: 500`, barra 3px `inset-inline-start: 0` con `var(--accent)`
- `aria-current="page"` en el item activo

### AgentBottomBar
- `position: fixed; bottom: 0; height: 48px; z-index: 200`
- Sección izquierda de exactamente 180px: dot de color + label clicable (toggle agente)
- Divisor 1px × 20px
- Carrusel de pills `flex: 1; overflow-x: auto; scrollbar-width: none`
- Pill normal: 168px, `var(--border)`, `var(--surface-2)`
- Pill "is-next": 200px, borde oro `var(--accent)`, `var(--accent-subtle)` + hora exacta
- Polling del agente: `setInterval(fetchAgentStatus, 10_000)` en WorldSpacePage

### FarmListsTab (V4)
- Props: `{ farmLists, loading, onSyncNow, syncing, lastSyncTime, schedulers, onOpenDrawer }`
- Agrupación: `groupByVillage()` agrupa por `(village_name|village_x|village_y)`
- Tabla desktop: `hidden md:table` — tarjetas móvil: `md:hidden`
- Columna Rec/env: `text-align: end`, `var(--font-mono)`, `fontVariantNumeric: tabular-nums`
- Badge sondas: `probeCount(fl)` cuenta slots con `disabled_by_bot && cooldown_seconds > 0`
- Banner sync: no bloquea la UI (se muestra sobre la tabla vacía/con datos)

### FarmListDrawer (V5/V6)
- `position: fixed; inset-inline-end: 0; width: min(480px, 100vw)` — RTL correcto por propiedad lógica
- `transform: translateX(100%)` cuando cerrado, `translateX(0)` cuando abierto — transición `var(--dur-slow)`
- Focus trap con `useFocusTrap(drawerRef, open)` + ESC cierra + backdrop cierra
- `triggerRef` recibe foco al cerrar
- Pestañas internas: Slots / Historial (con `role="tab"`, `aria-selected`)
- Borde acento de la pestaña activa: `border-bottom: 2px solid var(--accent)`

### V6 — SlotDetail con ProbeMenu
- ProbeMenu es un popover inline (`position: absolute; bottom: calc(100% + 6px); inset-inline-start: 0`)
- Cerrar ProbeMenu: `document.addEventListener('mousedown', handler)` que detecta clic fuera del `menuRef`
- `aria-haspopup="menu"` en el botón, `role="menu"` en el popover, `role="menuitem"` en las opciones
- Cooldown countdown: `cooldownTargetIso(slot)` calcula ISO desde `last_raid_time + cooldown_seconds`

### Huecos de datos conocidos
1. `avg_bounty_per_send` no documentado en `/farm-lists` API — se mapea si existe, si no muestra `—`
2. `last_sync_at` no en la respuesta de `/farm-lists` — se usa fecha local del fetch como aproximación
3. `history` fields: `sent_at`/`created_at`, `slots_sent`/`slots_total`, `triggered_by` — adaptar si cambian nombres

### Sin framework de tests de front
- El proyecto no tiene `test` script en `package.json`; verificación via `npm run build` (✓) + lint (eslint no configurado aún)
