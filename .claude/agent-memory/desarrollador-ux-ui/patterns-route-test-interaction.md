---
name: patterns-route-test-interaction
description: Patrón ▶ inline por fila + WorldBottomBar sticky + TestExpandRow en RouteTemplatesPage; mundo global, sesión global, resultado inline sin path_index
metadata:
  type: project
---

## Patrón "Probar ruta" inline (spec route-test-interaction.md, 2026-06-06)

### Estructura de componentes

- **`WorldBottomBar`** — barra J sticky bottom (`position:fixed; inset-inline:0; bottom:0; height:48px; z-index:200`). Contiene: icono globo, label "Mundo para test:", `<select>` de mundos (max-width:360px; flex:1), hint en `--accent-text` cuando no hay mundo, indicador de sesión (dot verde/gris + texto + botón "Cerrar sesión"), indicador "Ejecutando slug…" con spinner cuando hay test en curso. Patrón derivado de AgentBottomBar (DESIGN.md §19.4).
- **`TestExpandRow`** — `<tr>` insertado como hermano inmediato después de la fila activa. Usa `colSpan={5}` (columnas de la tabla: Plantilla, Categoría, Pasos, Estado, Acciones). El interior tiene `paddingInlineStart:40px` para alinear con contenido de la fila padre. Estados: `running` (spinner + texto), `done`+ok (badge verde, pasos con ✓), `done`+error (badge rojo, pasos con ✗ + reason).
- **`TemplateRow`** — wrappea en `<>...</>` (fragmento) la fila normal + `<TestExpandRow>`. El ▶ es `btn-play`: 28×28px ghost, `minHeight:44px` para target táctil, `padding:8px`. Se deshabilita con `opacity:0.4` si sin paths O sin mundo elegido.

### Estado en RouteTemplatesPage

```js
const [selectedWorldId, setSelectedWorldId] = useState('')      // string ID del mundo
const [sessionStatus, setSessionStatus] = useState(null)        // {active: boolean} | null
const [loadingSession, setLoadingSession] = useState(false)
const [closingSession, setClosingSession] = useState(false)
const [testStates, setTestStates] = useState({})                // {[tplId]: {status,result,durationMs,worldLabel,apiError}}
const [activeTestTplId, setActiveTestTplId] = useState(null)   // solo una fila expand a la vez
```

### Lógica clave

- `handlePlayTest(tpl)`: borra resultado de `activeTestTplId` anterior → pone `{status:'running'}` para el nuevo → llama `api.testRouteTemplate(id, {world_id})` SIN `path_index` → pone `{status:'done', result, durationMs}`. Tras el test, `setSessionStatus({active:true})`.
- `handleCloseSession()`: `api.closeWorldSession(worldId)` → `setSessionStatus({active:false})`.
- Efecto de sesión: `useEffect([selectedWorldId, worlds])` → `api.getSession(account_id, world_id)` → `setSessionStatus`.
- Al cambiar de mundo: limpia `activeTestTplId` y `testStates`.

### Payload de test (sin path_index)

```js
api.testRouteTemplate(tpl.id, { world_id: parseInt(selectedWorldId) })
// El backend aplica path_index=0 por defecto — correcto para rutas componibles (cadena raíz→hoja)
```

### Divisor hairline en columna Acciones

```jsx
{/* ▶ */}
<button className="rt-btn-play" .../>
<div style={{width:'1px',height:'16px',background:'var(--border)',marginInline:'2px'}} aria-hidden/>
{/* editar, clonar, borrar */}
```

### Desviaciones conocidas del spec

- `TestExpandRow` renderiza pasos inline en lugar de reutilizar `PathTestResultPanel` (el panel existente tiene botón "cerrar" y `t()` que no encajan en fila compacta). El spec decía "o adáptalo".
- Icono globo 🌐 en barra J es emoji, no SVG.

Véase [[patterns-route-templates]] para el resto de RouteTemplatesPage.
