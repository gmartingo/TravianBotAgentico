---
id: farm-lists-slot-improvements
titulo: Mejoras en la tabla de slots del FarmListDrawer
estado: implemented
fecha: 2026-05-27
autor: disenador-producto / orquestador
spec_funcional_relacionado: docs/specs/farm-lists.md
spec_diseno_base: docs/design/farm-lists-ui.md
spec_diseno_delta: docs/design/farm-lists-feedback.md
mockup_aprobado_por_usuario: si (respuestas explícitas en chat 2026-05-27)
---

# Mejoras en la tabla de slots del FarmListDrawer (V6 delta)

Este spec es un **delta puntual sobre `docs/design/farm-lists-ui.md`** y
`docs/design/farm-lists-feedback.md` (ambos en estado: implemented).
No rediseña lo ya implementado; añade cuatro mejoras concretas a la tabla de slots
del `FarmListDrawer` (componente `SlotRow` + `SlotDetail`):

1. **Ordenación por columna** — cualquier columna de la tabla de slots es sortable.
2. **Iconos de tropas** — columna de iconos de tropas enviadas en cada slot.
3. **Dropdown de 3 puntos (⋯) en la fila** — acceso rápido a acciones sin expandir el accordion.
4. **Columna "Botín acumulado"** — `total_bounty` visible directamente en la fila.
5. **Link "Ver reporte"** en la fila — `last_raid_report_id` enlazado a Travian.

Todas las decisiones siguen `frontend/DESIGN.md` y el sistema de diseño existente.

---

## 1. Contexto y problema

La tabla de slots en V6 tiene actualmente 4 columnas:
`Nombre · Dist · Botín último · Estado`

Las acciones (activar, desactivar, cancelar sonda) están **solo en el accordion expandido**.
Para ver cualquier acción, el usuario debe hacer clic en la fila para expandirla.

El usuario pidió:
- Ver los iconos de las tropas que se envían en cada slot.
- Un botón de 3 puntos en la fila para acceder a las acciones sin expandir.
- Una columna con el botín total acumulado por el bot.
- Un link directo al reporte de la última raid visible sin expandir.

---

## 2. Diseño técnico de cada mejora

### 0 — Ordenación por columna (Sort)

**Columnas sortables**: Nombre, Dist, Botín acum, Botín último, Estado.
Las columnas Tropas (iconos) y ⋯ (acciones) **no son sortables**.

**Estado en `SlotsPanel`**:
```jsx
const [sortKey, setSortKey] = useState(null)   // 'name'|'distance'|'total_bounty'|'last_raid_bounty'|'state'
const [sortDir, setSortDir] = useState('asc')  // 'asc' | 'desc'
```
El orden inicial es el que devuelve la API (sin sort activo, `sortKey = null`).

**Lógica de sort** (client-side, todos los datos están ya en memoria):
```jsx
const sortedSlots = useMemo(() => {
  if (!sortKey) return slots
  return [...slots].sort((a, b) => {
    let va = a[sortKey] ?? ''
    let vb = b[sortKey] ?? ''
    if (typeof va === 'string') va = va.toLowerCase()
    if (typeof vb === 'string') vb = vb.toLowerCase()
    if (va < vb) return sortDir === 'asc' ? -1 : 1
    if (va > vb) return sortDir === 'asc' ? 1 : -1
    return 0
  })
}, [slots, sortKey, sortDir])
```

**Interacción**: al hacer clic en una cabecera sortable:
- Si no era la columna activa → activarla en `'asc'`.
- Si era la activa en `'asc'` → cambiar a `'desc'`.
- Si era la activa en `'desc'` → resetear (`sortKey = null`).

**Indicador visual en cabecera** (`SortableHeader`):
```jsx
function SortableHeader({ label, colKey, sortKey, sortDir, onSort }) {
  const isActive = sortKey === colKey
  return (
    <th
      onClick={() => onSort(colKey)}
      style={{ cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap' }}
      aria-sort={isActive ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
    >
      {label}
      {isActive
        ? (sortDir === 'asc' ? ' ▲' : ' ▼')
        : <span style={{ color: 'var(--text-tertiary)', fontSize: '10px' }}> ⇅</span>
      }
    </th>
  )
}
```

- Columna activa: `▲` (asc) o `▼` (desc) en `var(--accent-text)`.
- Columna inactiva: `⇅` en `var(--text-tertiary)`, tamaño 10px (sutil).
- No se cambia el background de la cabecera activa (mantener minimalismo).

**Cabeceras de `Estado`**: el campo real para ordenar es `last_raid_state` (string).
El orden alfabético del estado funciona bien como proxy de orden de interés.

### A — Iconos de tropas

**Fuente de datos**: `GET /catalog/icons?icon_type=troop&tribe=<tribe>`
El endpoint devuelve `IconListResponse`:
```json
{
  "icons": [
    { "icon_id": "ROMANS_1", "ordinal": 1, "tribe": "romans",
      "url": "/static/icons/ROMANS_1.png", "width_px": 20, "height_px": 20 }
  ]
}
```

**Cómo se usa en el slot**: cada slot tiene `troops: {"t1": 2, "t4": 1}`.
Las claves `tN` son ordinales (t1 = ordinal 1, t2 = ordinal 2, etc.).
La tribu se obtiene del mundo (`worldInfo.tribe` ya disponible en `WorldSpacePage`).

**Flujo de datos**:
1. `WorldSpacePage` obtiene `worldInfo.tribe` (ya disponible).
2. `WorldSpacePage` pasa `worldServer` al drawer (detalle en §4).
3. `FarmListDrawer` recibe `tribe` (derivado de `worldInfo`) y lo pasa a `SlotsPanel`.
4. `SlotsPanel` realiza **una sola llamada** a `GET /catalog/icons?icon_type=troop&tribe=<tribe>`
   al montarse (no por cada slot). El resultado se guarda en un map `ordinal → url`.
5. `SlotRow` recibe el map `iconsByOrdinal` y muestra los iconos de `slot.troops`.

**Reglas de presentación**:
- Los iconos se muestran en la fila de la tabla (siempre visibles, no solo al expandir).
- Cada icono `<img>` tiene `width: 18px; height: 18px; object-fit: contain`.
- Mostrar los iconos en orden ascendente de ordinal (t1, t2, t3...).
- Si el slot no tiene tropas (`troops` vacío o `{}`): no se muestra ningún icono — la celda queda vacía.
- Fallback si la llamada a `/catalog/icons` falla o los iconos no existen en BD:
  mostrar texto compacto `"TN"` (ej. `"T1"`) en `--text-tertiary` tamaño 11px.
  El componente no debe lanzar error visible al usuario por un icono faltante.
- Si el mapa `iconsByOrdinal` está vacío o cargando: mostrar el fallback texto directamente
  (sin skeleton — la celda de iconos nunca bloquea la tabla).
- Los iconos **no son botones ni interactivos**: son presentación pura.
- La celda de iconos no tiene `title` explícito (los nombres de tropas no son necesarios aquí).

**Posición en la tabla**: nueva primera columna, antes del nombre del target.
La tabla queda: `Tropas · Nombre · Dist · Botín acum · Botín último · Estado · ⋯`
(ver §3 para la tabla completa con columnas reordenadas).

**Cabecera de columna**: sin cabecera textual — celda `<th>` vacía con `aria-label="Tropas"`.

**Ancho de celda**: `padding: 6px 4px 6px 8px`. Los iconos se muestran como flex row con `gap: 2px`.
Sin ancho fijo — el contenedor de iconos crece según el número de iconos (máximo ~10 iconos en un slot).

### B — Dropdown de 3 puntos (⋯) en la fila

**Propósito**: acceso rápido a las acciones del slot **sin necesidad de expandir el accordion**.
Coexiste con el accordion: el accordion sigue existiendo con el detalle completo (avg_bounty, 
total_bounty, cooldown countdown, etc.). El botón ⋯ es un acceso rápido adicional en la fila.

**Posicionamiento del dropdown**: el menú se despliega hacia la **izquierda y hacia arriba**
(o hacia abajo si hay espacio) del botón ⋯, con `min-width: 200px`.
Posición: `position: absolute; inset-inline-end: 0; top: calc(100% + 4px)`.
Si la fila está cerca del borde inferior del drawer, el menú sube: 
`bottom: calc(100% + 4px)` como fallback (lógica simple: si el botón está en la segunda mitad
del drawer, abrir hacia arriba).

**Botón ⋯**:
- `aria-haspopup="menu"`, `aria-expanded`, `aria-label={t('slot.actions.menuLabel')}`.
- Tamaño: 28×28px, `border-radius: var(--radius-sm)`.
- Contenido: `···` (unicode U+22EF) o tres puntos `...` en mono, tamaño 14px.
- Estilos: `border: 1px solid var(--border)`, `background: transparent`, hover `var(--surface-2)`.
- No es un menú de contexto nativo — es un `<button>` con un `<div role="menu">` custom
  (mismo patrón que `ProbeMenu` ya implementado).
- Detener la propagación del click: `e.stopPropagation()` para que el clic en ⋯ no expanda
  el accordion de la fila.

**Acciones en el dropdown** (las mismas que en `SlotDetail`, más rápidas):

| Acción | Condición de visibilidad | Endpoint |
|---|---|---|
| Activar | `!slot.is_active` | `POST /farm/slots/{id}/activate` |
| Desactivar | `slot.is_active && !slot.disabled_by_bot` | `POST /farm/slots/{id}/deactivate` |
| Cancelar sonda → Desactivar | `slot.disabled_by_bot && slot.cooldown_seconds > 0` | `POST /farm/slots/{id}/cancel-probe` con `mode="deactivate"` |
| Cancelar sonda → Enviar ahora | `slot.disabled_by_bot && slot.cooldown_seconds > 0` | `POST /farm/slots/{id}/cancel-probe` con `mode="send_now"` — cancela el cooldown y ataca inmediatamente |

Reglas:
- "Cancelar sonda" se muestra como dos subitems si `disabled_by_bot && cooldown > 0`.
  Estos dos items tienen el mismo estilo que `ProbeMenu` (ya implementado).
- "Activar" y "Desactivar" son mutuamente excluyentes.
- Si todas las acciones están ocultas (caso imposible en la práctica), el botón ⋯ no aparece.
- Al completar una acción desde el dropdown: `onUpdated()` igual que en `SlotDetail`.
- El dropdown se cierra al seleccionar una acción o al hacer clic fuera
  (mismo patrón que `ProbeMenu`: `document.addEventListener('mousedown', handler)`).
- Spinner de carga en el item de acción mientras está en curso; el resto de items
  se deshabilitan durante la carga (`disabled`, `opacity: 0.6`).

**Estructura visual del dropdown** (en orden):
```
┌────────────────────────────────┐
│  Activar                       │  (si !is_active)
│  ── o ──                       │
│  Desactivar                    │  (si is_active && !disabled_by_bot)
│────────────────────────────────│
│  Cancelar sonda                │  (header no-interactivo si disabled_by_bot)
│    · Desactivar indefinidamente│  → mode="deactivate"
│    · Enviar ahora              │  → mode="send_now" (ataca inmediatamente)
└────────────────────────────────┘
```

Si no hay sonda: sin separador, solo las acciones relevantes de activar/desactivar.

**Posición en la tabla**: última columna a la derecha.
La cabecera de la columna es vacía con `aria-label="Acciones"`.
Ancho de celda: `width: 36px; padding: 4px`.

### C — Columna "Botín acumulado"

**Datos**: `slot.total_bounty` — ya viene en el response de `/farm/worlds/{id}/farm-lists`.

**Posición en la tabla**: entre "Dist" y "Botín último". La tabla completa queda:
`Tropas · Nombre · Dist · Botín acum · Botín último · Estado · ⋯`

**Presentación**:
- Valor formateado con `fmtNum(slot.total_bounty)` (ya existe: `new Intl.NumberFormat`).
- Tipografía: `var(--font-mono)`, `fontVariantNumeric: tabular-nums`, `text-align: end`.
- Color: `var(--text-secondary)` para diferenciarlo visualmente del "Botín último" que está 
  en `var(--text)`.
- Si `total_bounty === 0` o `null`: mostrar `—`.
- Cabecera: `t('slot.col.totalBounty')` — clave nueva a añadir en i18n.

**El accordion mantiene "Botín total"**: la fila expandida (SlotDetail) también muestra
`total_bounty`. No eliminar esa línea del accordion — el accordion tiene más espacio y puede
mostrar la etiqueta completa "Botín total acumulado". La columna de la tabla es la versión
compacta en la fila.

**Orden de columnas en mobile**: en mobile el drawer es fullscreen y la tabla tiene menos espacio.
Ocultar "Botín acum" en mobile (P3): añadir clase `hidden-mobile` que aplique
`display: none` en `< 480px`. El botín acumulado sigue visible en el accordion expandido.

### D — Link "Ver reporte" en la fila

**Dato**: `slot.last_raid_report_id` — ya viene en el response.

**URL del reporte**: `<worldServer>report?id=<last_raid_report_id con "/" → "%7C">&s=1`

Por ejemplo, si `worldServer = "https://ts1.travian.es/"` y `last_raid_report_id = "1234/56789"`:
→ `https://ts1.travian.es/report?id=1234%7C56789&s=1`

Construcción en código:
```js
const reportUrl = `${worldServer}report?id=${slot.last_raid_report_id.replace('/', '%7C')}&s=1`
```

El `worldServer` es el `server` del mundo (ej. `"https://ts1.travian.es/"`).
Se obtiene de `worldInfo.server` en `WorldSpacePage` (ya disponible).

**Flujo de prop drilling**:
```
WorldSpacePage
  ├── worldInfo.server → prop worldServer → FarmListDrawer
  └── FarmListDrawer → SlotsPanel → SlotRow
```

**Cómo pasar worldServer**:
1. En `WorldSpacePage`, añadir `worldServer={worldInfo?.server}` al `<FarmListDrawer>`.
2. En `FarmListDrawer`, recibir `worldServer` como prop y pasarlo a `SlotsPanel`.
3. En `SlotsPanel`, pasarlo a `SlotRow`.
4. En `SlotRow`, construir la URL si `worldServer && slot.last_raid_report_id`.

**Presentación en la fila**:
- Si `last_raid_report_id` tiene valor (no `null`, no `""`):
  mostrar un enlace `<a href={reportUrl} target="_blank" rel="noopener noreferrer">`.
  Contenido del enlace: icono de enlace externo (↗ SVG inline, 12px) + texto `t('slot.viewReport')`.
  El enlace usa `color: var(--accent-text)`, `font-size: 11px`, `text-decoration: none`,
  hover con `text-decoration: underline`.
- Si `last_raid_report_id` es `null` o `""`: mostrar `—` en `--text-tertiary`.
- Si `worldServer` no está disponible (prop `null` o `undefined`): mostrar solo el ID del
  reporte en texto plano (sin enlace), `--text-tertiary`, tamaño 11px, truncado a 12 chars
  con `...` si es largo.

**Posición en la tabla**: NO es una nueva columna separada. El link se añade **dentro de la
celda de "Botín último"** como una segunda línea debajo del valor numérico, o como
elemento inline en la misma celda. Diseño recomendado:
```
┌──────────────┐
│  450          │  ← last_raid_bounty (línea 1)
│  ↗ Ver reporte│  ← link (línea 2, solo si hay report_id)
└──────────────┘
```
Así no se añade una columna extra (la tabla ya tiene muchas columnas).
La celda `last_raid_bounty` cambia de `<td>` con solo el valor a `<td>` con un `<div>`
que contiene el valor y el link.

**En el accordion (SlotDetail)**: mantener la línea "Último informe" que ya existe
(`last_raid_state · relativeTime`). El link de reporte en el accordion puede ser una
línea adicional bajo "Último informe":
```
Último informe:  Sin pérdidas · hace 3 min
                 ↗ Ver reporte
```
No es obligatorio — el link en la fila ya cubre el caso de uso principal.

---

## 3. Tabla de slots — diseño final (todas las columnas)

### Desktop (≥ 480px)

| # | Columna | Dato | Ancho | Tipografía |
|---|---|---|---|---|
| 1 | Tropas (sin cabecera) | iconos de `slot.troops` | auto | img 18×18px |
| 2 | Nombre | `slot.target_name` | flex | 13px, `var(--text)` |
| 3 | Dist | `slot.distance` | 45px | mono, 12px, `var(--text-secondary)` |
| 4 | Botín acum | `slot.total_bounty` | 60px | mono, 12px, `var(--text-secondary)` |
| 5 | Botín último + link reporte | `slot.last_raid_bounty` + link | 70px | mono, 13px |
| 6 | Estado | `SlotStatusBadge` | auto | badge 11px |
| 7 | ⋯ | dropdown de acciones | 36px | — |

### Mobile (< 480px)

Las columnas "Dist", "Botín acum" se ocultan (P3).
Quedan: `Tropas · Nombre · Botín último · Estado · ⋯`

---

## 4. Cambios en props y componentes

### WorldSpacePage (modificado)

```jsx
<FarmListDrawer
  open={drawerOpen}
  farmList={drawerFarmList}
  worldId={worldId}
  schedulerName={...}
  worldServer={worldInfo?.server ?? null}   // NUEVO
  tribe={worldInfo?.tribe ?? null}           // NUEVO
  onClose={closeDrawer}
  triggerRef={drawerTriggerRef}
/>
```

### FarmListDrawer (modificado)

Props nuevas: `worldServer: string | null`, `tribe: string | null`.

```jsx
// FarmListDrawer recibe y pasa las nuevas props:
function FarmListDrawer({ open, farmList, worldId, schedulerName, worldServer, tribe, onClose, triggerRef }) {
  // ... (la firma cambia para incluir worldServer y tribe)
  // Pasar a SlotsPanel:
  <SlotsPanel farmList={...} worldId={worldId} slots={...} loading={...}
    onRefresh={...} worldServer={worldServer} tribe={tribe} />
}
```

### SlotsPanel (modificado)

Props nuevas: `worldServer: string | null`, `tribe: string | null`.

Añade la carga de iconos al montarse:
```jsx
const [iconsByOrdinal, setIconsByOrdinal] = useState({}) // { ordinal: url }

useEffect(() => {
  if (!tribe) return
  api.getCatalogIcons({ icon_type: 'troop', tribe })
    .then(data => {
      const map = {}
      for (const icon of data.icons ?? []) {
        if (icon.ordinal != null) map[icon.ordinal] = icon.url
      }
      setIconsByOrdinal(map)
    })
    .catch(() => {}) // silencioso — fallback a texto
}, [tribe])
```

Pasa `iconsByOrdinal` y `worldServer` a `SlotRow`.

### SlotRow (modificado)

Props nuevas: `iconsByOrdinal: object`, `worldServer: string | null`.

Cambios:
1. Nueva primera celda con los iconos de tropas.
2. Nueva celda "Botín acum" entre dist y bounty.
3. Celda "Botín último" ampliada con el link de reporte.
4. Nueva última celda con el botón ⋯ y el menú de acciones.
5. El click propagation en ⋯ debe llamar `e.stopPropagation()`.
6. El `colSpan` del accordion expandido pasa de 4 a 7 (nuevas columnas).

### SlotActions (nuevo componente interno)

Componente interno del drawer para el menú ⋯. Reutiliza el patrón de `ProbeMenu`
(mismo popover, mismo patrón de cierre on-click-outside).

```jsx
function SlotActions({ slot, farmListId, worldId, onUpdated }) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const menuRef = useRef(null)
  const { t } = useI18n()
  
  // cierre on-click-outside (mismo patrón que ProbeMenu)
  // ...
  
  const hasProbe = slot.disabled_by_bot && slot.cooldown_seconds > 0
  
  return (
    <div style={{ position: 'relative', display: 'inline-block' }}>
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t('slot.actions.menuLabel')}
        onClick={e => { e.stopPropagation(); setOpen(v => !v) }}
        style={{
          width: '28px', height: '28px',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)',
          background: 'transparent',
          cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: '14px', color: 'var(--text-secondary)',
          fontFamily: 'var(--font-mono)',
          transition: 'background var(--dur-fast) var(--ease)',
        }}
        className="hover:bg-[var(--surface-2)]"
      >
        ···
      </button>
      {open && (
        <div
          ref={menuRef}
          role="menu"
          style={{
            position: 'absolute',
            insetInlineEnd: 0,
            top: 'calc(100% + 4px)',
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
            boxShadow: 'var(--shadow-lg)',
            zIndex: 600,
            minWidth: '200px',
            overflow: 'hidden',
          }}
        >
          {/* items de acciones */}
        </div>
      )}
    </div>
  )
}
```

### api.getCatalogIcons (nuevo método en client.js)

```js
getCatalogIcons({ icon_type, tribe } = {}) {
  const params = new URLSearchParams()
  if (icon_type) params.set('icon_type', icon_type)
  if (tribe)     params.set('tribe', tribe)
  return this._get(`/catalog/icons?${params}`)
},
```

Nota: el endpoint `/catalog/icons` exige `Accept-Language` (ver routes/game_data.py línea 241).
El cliente HTTP ya envía `Accept-Language` en todas las peticiones (`client.js` patrón existente).

---

## 5. Claves i18n nuevas

Añadir en `frontend/src/i18n/catalog/es.js` (y en los 24 idiomas restantes con fallback a ES):

| Clave | Texto (es) | Contexto |
|---|---|---|
| `slot.col.totalBounty` | "Acum." | Cabecera columna botín acumulado |
| `slot.col.troops` | "Tropas" | aria-label de la cabecera de iconos |
| `slot.col.actions` | "Acciones" | aria-label de la cabecera del dropdown |
| `slot.actions.menuLabel` | "Acciones del slot" | aria-label del botón ⋯ |
| `slot.actions.activate` | "Activar" | Item del dropdown |
| `slot.actions.deactivate` | "Desactivar" | Item del dropdown |
| `slot.actions.cancelProbeHeader` | "Cancelar sonda" | Sub-cabecera (no interactiva) |
| `slot.actions.probeDeactivate` | "Desactivar indefinidamente" | Sub-item |
| `slot.actions.probeSendNow` | "Enviar ahora" | Sub-item (cancela cooldown y ataca inmediatamente) |
| `slot.viewReport` | "Ver reporte" | Texto del link al reporte |

---

## 6. Accesibilidad

- **Iconos de tropas**: `<img>` con `alt=""` (decorativos, no informativos).
  El nombre de la tropa no se necesita aquí; si se necesita en el futuro, añadir `title`.
- **Botón ⋯**: `aria-haspopup="menu"`, `aria-expanded`, `aria-label` con texto descriptivo.
  El menú tiene `role="menu"` y los items `role="menuitem"`.
- **Link "Ver reporte"**: `target="_blank"` con `rel="noopener noreferrer"` (seguridad).
  El icono ↗ es `aria-hidden="true"`. El texto "Ver reporte" es el label visible.
- **colSpan del accordion**: actualizar de 4 a 7 para que el detail row span todas las columnas.
- **Tabla completa**: cabeceras con `scope="col"` en cada `<th>`. Las dos cabeceras vacías
  (Tropas y Acciones) llevan `aria-label` para lectores de pantalla.
- **Targets táctiles**: el botón ⋯ tiene 28×28px en desktop, 36×36px en mobile
  (aumentar con padding para llegar a 44px si se detecta touch).

---

## 7. Responsive

| Breakpoint | Cambios |
|---|---|
| `≥ 480px` (desktop drawer) | 7 columnas completas: Tropas · Nombre · Dist · Botín acum · Botín último · Estado · ⋯ |
| `< 480px` (mobile drawer fullscreen) | Ocultar: Dist, Botín acum. Quedan 5 columnas: Tropas · Nombre · Botín último · Estado · ⋯ |

La ocultación se implementa con CSS inline condicional o clase:
```css
@media (max-width: 479px) {
  .slot-col-dist, .slot-col-totalBounty { display: none; }
}
```

---

## 8. Edge cases y comportamientos defensivos

| Caso | Comportamiento |
|---|---|
| `tribe` es null (mundo sin tribu en BD) | `SlotsPanel` no llama a `/catalog/icons`; `iconsByOrdinal = {}`; fallback texto `"TN"` |
| `/catalog/icons` devuelve 200 con lista vacía | `iconsByOrdinal = {}`; fallback texto `"TN"` para todos los slots |
| `/catalog/icons` devuelve error HTTP | `catch` silencioso; `iconsByOrdinal = {}`; fallback texto |
| `slot.troops` es `{}` o null | Celda de tropas vacía (no fallback, no texto) |
| `worldServer` es null | Link de reporte no se renderiza; muestra `—` |
| `last_raid_report_id` es `""` o null | Muestra `—` en lugar del link |
| Más de 6 iconos en un slot | Los iconos se muestran en fila; la celda crece horizontalmente. No hay truncado. |
| El dropdown ⋯ está abierto y el usuario expande el accordion | Cerrar el dropdown (el re-render cierra el estado `open` al remontar o detectar scroll). Implementación simple: el dropdown se cierra en blur del botón. |
| Acción desde el dropdown mientras el accordion está expandido | `onUpdated()` cierra el accordion y refresca la lista (comportamiento existente en SlotDetail). |

---

## 9. Criterios de aceptación

- [ ] **CA-S-00a**: Al hacer clic en la cabecera de Nombre, Dist, Botín acum, Botín último o Estado, la tabla se ordena por esa columna en dirección ascendente.
- [ ] **CA-S-00b**: Un segundo clic en la misma cabecera invierte el orden (desc). Un tercer clic resetea al orden original de la API.
- [ ] **CA-S-00c**: La cabecera activa muestra ▲ (asc) o ▼ (desc) en color acento. Las inactivas muestran ⇅ sutil. Las cabeceras de Tropas y ⋯ no son interactivas.
- [ ] **CA-S-00d**: El estado de ordenación es local a `SlotsPanel` y no se persiste.
- [ ] **CA-S-01**: La tabla de slots muestra una celda de iconos para cada slot. Los iconos corresponden a las tropas en `slot.troops`, ordenados por ordinal ascendente.
- [ ] **CA-S-02**: Si `/catalog/icons` no devuelve iconos o falla, la celda muestra el fallback texto `"T1"`, `"T2"`, etc. en `--text-tertiary`. No se muestra ningún error al usuario.
- [ ] **CA-S-03**: El botón ⋯ aparece en cada fila. Al hacer clic, abre un dropdown con las acciones relevantes para el estado del slot (activar/desactivar/cancelar sonda). El clic en ⋯ no expande el accordion.
- [ ] **CA-S-04**: Las acciones del dropdown funcionan igual que las del accordion: llaman a los mismos endpoints y actualizan la lista tras completarse.
- [ ] **CA-S-05**: El dropdown se cierra al seleccionar una acción o al hacer clic fuera del menú.
- [ ] **CA-S-06**: La columna "Botín acum" muestra `slot.total_bounty` formateado con `fmtNum`. Si es 0 o null, muestra `—`.
- [ ] **CA-S-07**: La celda de "Botín último" incluye el link "↗ Ver reporte" cuando `last_raid_report_id` es no-vacío y `worldServer` está disponible. El link abre en nueva pestaña.
- [ ] **CA-S-08**: Si `last_raid_report_id` es null o vacío, la celda muestra `—` en lugar del link.
- [ ] **CA-S-09**: En mobile (< 480px), las columnas "Dist" y "Botín acum" están ocultas. El resto de columnas son visibles.
- [ ] **CA-S-10**: El `colSpan` del accordion expandido cubre todas las columnas (7 en desktop, 5 en mobile).
- [ ] **CA-S-11**: `WorldSpacePage` pasa `worldServer` y `tribe` al `FarmListDrawer`.
- [ ] **CA-S-12**: El dropdown ⋯ tiene `role="menu"`, `aria-haspopup="menu"` y `aria-expanded` correcto. Los items tienen `role="menuitem"`.

---

## 10. Ficheros a modificar

| Fichero | Cambio |
|---|---|
| `frontend/src/api/client.js` | Añadir `getCatalogIcons({ icon_type, tribe })` |
| `frontend/src/pages/WorldSpacePage.jsx` | Pasar `worldServer={worldInfo?.server}` y `tribe={worldInfo?.tribe}` al `FarmListDrawer` |
| `frontend/src/components/world/FarmListDrawer.jsx` | Nuevas props `worldServer` + `tribe`; `SlotsPanel` añade estado sort + lógica `sortedSlots`; `SortableHeader` nuevo componente interno; `SlotsPanel` carga iconos; `SlotRow` actualizado con 7 columnas; nuevo componente interno `SlotActions` |
| `frontend/src/i18n/catalog/es.js` | 10 claves nuevas (tabla §5) |

Ningún fichero de backend necesita cambios. Todo el trabajo es frontend.

---

## 11. Trazabilidad de decisiones

| Decisión | Origen |
|---|---|
| Iconos desde `/catalog/icons` (no rutas directas a PNG) | Usuario (respuesta A): "hay un endpoint `/catalog/icons` que ya sirve los iconos" |
| La tribu se infiere del slot/cuenta (no del slot directamente) | Usuario (respuesta A1): "la tribu se infiere del slot/cuenta" |
| Fallback = texto `"TN"` si el icono no existe | Usuario (respuesta A2): "fallback = texto 'TN'" |
| Iconos visibles en la fila de la tabla, siempre | Usuario (respuesta A3): "queremos los iconos visibles en la fila de la tabla, siempre" |
| Dropdown ampliado hacia la izquierda | Usuario (respuesta B): "el dropdown se amplíe un poco más hacia la izquierda" |
| Botín acumulado = columna adicional en la tabla | Usuario (respuesta B4, inferido): "asumir columna adicional en la tabla" |
| Orden inicial = el que devuelve la API por defecto | Usuario (respuesta B5, inferido): "asumir el orden que devuelve la API por defecto" |
| Accordion se mantiene + botón ⋯ en cada fila | Usuario (respuesta C): "mantener el accordion con el detalle completo Y añadir un botón de 3 puntos (⋯)" |
| Sin botón de envío individual (no pedido) | Usuario (respuesta C): "sin botón de 'enviar sonda individual' por ahora" |
| `worldServer` como prop del drawer | Usuario (respuesta D8): "pasar worldServer como prop al drawer" |
| Guion cuando `last_raid_report_id` es null | Usuario (respuesta D9): "mostrar un guion '—' cuando last_raid_report_id es null" |
| Link "Ver reporte" visible en la fila directamente | Usuario (respuesta D10): "el link 'Ver reporte' debe ser visible en la fila directamente" |
| Link en la celda de "Botín último" (no columna separada) | Decisión del orquestador: evitar añadir una 8ª columna a una tabla ya densa. |

---

*Spec escrito por el agente orquestador — 2026-05-27. Delta sobre docs/design/farm-lists-ui.md y
docs/design/farm-lists-feedback.md (ambos implementados). Para ser implementado por
desarrollador-ux-ui partiendo de este documento.*

---

## Registro de implementación

**Fecha:** 2026-05-27
**Implementado por:** desarrollador-ux-ui

### Ficheros creados/modificados

| Fichero | Cambios |
|---|---|
| `frontend/src/api/client.js` | Añadido `getCatalogIcons({ icon_type, tribe })` |
| `frontend/src/pages/WorldSpacePage.jsx` | Añadidos `worldServer={worldInfo?.server ?? null}` y `tribe={worldInfo?.tribe ?? null}` al `<FarmListDrawer>` |
| `frontend/src/components/world/FarmListDrawer.jsx` | Reescrito completo con: `worldServer` + `tribe` en props de `FarmListDrawer` y `SlotsPanel`; nuevo `SortableHeader` interno; estado de sort en `SlotsPanel`; carga de iconos via `api.getCatalogIcons`; `SlotRow` con 7 columnas (Tropas, Nombre, Dist, Botín acum, Botín último+link, Estado, ⋯); nuevo `SlotActions` (dropdown ⋯); `colSpan={7}` en accordion; helper `buildReportUrl`; `IconExternalLink` SVG; responsive CSS en `SlotsPanel` |
| `frontend/src/i18n/catalog/es.js` | 10 claves nuevas (§5 del spec) |
| `frontend/src/i18n/catalog/en.js` | 10 claves nuevas con traducción al inglés |
| `frontend/src/i18n/catalog/[ar,bg,cs,da,de,el,fa,fr,he,hu,it,ja,lt,lv,nl,pl,pt,rs,ru,sl,sv,tr,uk].js` | 10 claves nuevas con fallback en español (23 catálogos) |

### Comando para verificar el build

```bash
cd frontend && npm run build
```

Resultado: `✓ built in ~3s` — 0 errores, 0 warnings nuevos.

### Criterios de aceptación verificados en tiempo de implementación

- CA-S-00a/b/c/d: `SortableHeader` + `sortedSlots` en `SlotsPanel`. No verificable sin servidor.
- CA-S-01/02: Iconos con `iconsByOrdinal` y fallback `TN`. No verificable sin servidor.
- CA-S-03/04/05: `SlotActions` implementado con patrón `ProbeMenu`. No verificable sin servidor.
- CA-S-06: Columna `total_bounty` con `fmtNum` en `SlotRow`.
- CA-S-07/08: `buildReportUrl` + `IconExternalLink` en la celda de botín último.
- CA-S-09: CSS `@media (max-width: 479px)` ocultando `.slot-col-dist` y `.slot-col-totalBounty`.
- CA-S-10: `colSpan={7}` en la fila del accordion expandido.
- CA-S-11: Props `worldServer` y `tribe` añadidas en `WorldSpacePage.jsx` → `FarmListDrawer`.
- CA-S-12: `role="menu"`, `aria-haspopup="menu"`, `aria-expanded`, `role="menuitem"` en `SlotActions`.

### Desviaciones respecto al diseño

1. **`SortableHeader` recibe `className` como prop separada** (no dentro de `style`): necesario porque `className` en el objeto `style` de React no tiene efecto como atributo HTML. Desviación puramente técnica, sin impacto visual.
2. **Estilos responsive emitidos una sola vez en `SlotsPanel`** en lugar de en cada `SlotRow`: evita repetición del mismo `<style>` en cada fila. Resultado idéntico al especificado.
3. **Catálogos `en.js` lleva traducción al inglés** (no el fallback en español): mejora la UX para usuarios en inglés; el spec decía "con el mismo valor en español como fallback" pero en `en.js` ya existía la sección de slots traducida al inglés, por lo que se mantiene la consistencia del catálogo.
