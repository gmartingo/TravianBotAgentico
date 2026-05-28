---
name: patterns-farm-feedback
description: S10 Farm Lists Feedback: accordion sub-panel en scheduler, SchedulerDashboard drill-down, SendFeedback, StatsPanel — patrones y huecos API conocidos
metadata:
  type: project
---

## Componentes implementados (spec: docs/design/farm-lists-feedback.md, estado: implemented)

### SchedulerSubPanel.jsx (NUEVO)
- Accordion sub-panel dentro de cada SchedulerCard en AgentsTab
- Polling `api.getWorldHistory` + `api.getSlotEvents` cada 10s con `clearInterval` cleanup
- Detecta filas nuevas via `prevEventIdsRef` (Set de IDs); resaltado dorado `--accent-subtle` 2-3s
- `ElapsedTimer`: tick por segundo con `aria-live="off"` (no announce al lector de pantalla)
- `AlertsPanel`: conteo de no-leídas local con `readAt` timestamp; NO hay endpoint backend para "marcar leído"
- `AlertRow`: panel de confirmación inline (NO modal) — estado `confirming` dentro del componente
- `SubPanelSkeleton`: 3 rectángulos pulse para KPIs + 2 bloques para feed/alertas

### SchedulerDashboard.jsx (NUEVO)
- Vista dedicada v10, drill-down desde SchedulerCard vía prop `onOpenDashboard`
- Wiring en WorldSpacePage: estado `schedulerDashboard`; render condicional dentro de pestaña 'agents'
- Import muerto detectado y corregido: `import { AlertsPanel } from './SchedulerSubPanel.jsx'` era dead (AlertsPanel no exportada)
- `AlertsPanelDash`: versión local simplificada del panel de alertas (no reutiliza del sub-panel)
- `listsSummary`: calculado localmente desde `farmLists` + `historyItems`, sin endpoint extra

### FarmListDrawer.jsx (MODIFICADO — V6-delta 2026-05-27)
- Tercera pestaña "Stats" añadida (Slots · Stats · Historial) con role=tablist/tab/tabpanel ARIA
- `StatsPanel`: métricas calculadas solo desde `farmList` + `slots` ya cargados — sin nueva llamada API
  - Barras de distribución: `width: (count/totalSlots)*100%` con CSS logical props
  - Top 5 slots por `average_raid_bounty > 0`, sorted DESC
  - Empty state cuando `!hasData`
- `SendFeedback`: panel post-envío con `role="status"` + `aria-live="polite"`; animación `feedback-fadein`
  - `lastSendResult` en estado local; se resetea al abrir nuevo farmList
  - `handleSendNow` ahora captura el response y llama `setLastSendResult`
  - Si API devuelve null (204), normaliza a `{ status: 'success' }`

#### V6-delta: mejoras en la tabla de slots (spec: farm-lists-slot-improvements.md)
- Tabla ampliada de 4 a 7 columnas: `Tropas · Nombre · Dist · Botín acum · Botín último+link · Estado · ⋯`
- `SortableHeader`: componente interno con `className` como prop separada (no dentro de `style`)
  - Sort toggle: null → asc → desc → null
  - `aria-sort="ascending/descending/none"` en cada `<th>`
- `SlotsPanel` recibe `worldServer` y `tribe` como props nuevas
- `iconsByOrdinal`: mapa ordinal→url cargado una sola vez con `api.getCatalogIcons({ icon_type: 'troop', tribe })`
  - URL prepende `/api` si no empieza con `http` (para proxy de Vite en dev, nginx en prod)
  - Fallback silencioso: `catch(() => {})` → celdas muestran `T{ordinal}`
- `SlotRow` recibe `iconsByOrdinal` y `worldServer`
  - `slot.troops` = `{ t1: qty, t2: qty }` → ordenado por ordinal ascendente
  - `buildReportUrl(worldServer, reportId)` → reemplaza `/` por `%7C`, añade `/` final si falta
  - `colSpan={7}` en accordion expandido
  - `e.stopPropagation()` en celda de acciones (y en link de reporte) para no expandir accordion
- `SlotActions`: dropdown ⋯ con patrón ProbeMenu (mousedown-outside)
  - `zIndex: 600`, `insetInlineEnd: 0`, `top: calc(100% + 4px)`
  - Botones con `role="menuitem"`, wrapper con `role="menu"`, botón con `aria-haspopup="menu"` + `aria-expanded`
  - Spinner en el botón ⋯ mientras la acción está en curso
- Estilos responsive emitidos UNA SOLA VEZ en `SlotsPanel` (no en cada `SlotRow`)
- `api.getCatalogIcons` añadido en `client.js`
- `WorldSpacePage` pasa `worldServer` y `tribe` al `<FarmListDrawer>`

## Huecos API / deuda técnica conocida

1. `POST /farm/farm-lists/:id/send` NO devuelve `sent_at` → DA-F-19 sin timestamp en SendFeedback
2. `POST /farm/schedulers/:id/toggle` NO existe → workaround `api.updateScheduler({ is_enabled: !enabled })`
3. i18n: solo `es.js` tiene las ~70 claves nuevas; los 24 idiomas restantes heredan fallback ES

## Patrones de polling

```js
// Cleanup correcto — siempre guardar el id y limpiar
useEffect(() => {
  fetchData()
  const id = setInterval(fetchData, 10_000)
  return () => clearInterval(id)
}, [fetchData]) // fetchData memoizado con useCallback
```

## Drill-down dentro de pestaña (sin cambiar tab activo)

```jsx
// WorldSpacePage
const [schedulerDashboard, setSchedulerDashboard] = useState(null)
// ...
{activeTab === 'agents' && (
  schedulerDashboard ? (
    <SchedulerDashboard onBack={() => setSchedulerDashboard(null)} ... />
  ) : (
    <AgentsTab onOpenSchedulerDashboard={(s) => setSchedulerDashboard(s)} ... />
  )
)}
// Al cambiar tab, resetear siempre: setSchedulerDashboard(null)
```

Relacionado con: [[patterns-world-space]]
