---
name: patterns-noise-tab
description: S-NOISE: pestaña Ruido, wizard de rutas, Toggle/MinMaxInput, DeletePopover inline, EP-N01..N14 (incl. Probar ruta v3, Editar ruta v4)
metadata:
  type: project
---

Pestaña "Ruido" (Noise Catalog) implementada en `frontend/src/components/world/noise/`.

## Componentes creados

- `NoiseTab.jsx` — raíz, carga EP-N01+EP-N03 en paralelo con Promise.all
- `NoiseConfigPanel.jsx` — panel colapsable: toggle noise_enabled (PUT inmediato) + 6 campos numéricos + guardar
- `NoiseDestinationsTable.jsx` — tabla densa + `NoiseCategoryBadge` + formulario inline `NoiseAddDestinationForm`
- `NoiseDestinationDrawer.jsx` — drawer lateral (patrón [[patterns-world-space]] FarmListDrawer: overlay+panel+focus trap+ESC)
- `NoisePathWizard.jsx` — wizard multi-paso (origin → step form → lista pasos acumulados → guardar)
- `NoiseOriginSelector.jsx` — desplegable EP-N12 con botón "Actualizar aldeas" EP-N13 + 409 inline
- `NoiseWizardStepForm.jsx` — formulario outerHTML → POST EP-N11 derive-selector
- `NoiseDerivedSelectorFeedback.jsx` — 3 estados: único (verde), no-único (ámbar+alternativas+input manual), error (rojo)
- `NoisePathList.jsx` — tarjetas rutas existentes: is_dead badge, botón Reactivar EP-N09, botón Probar EP-N14 con PathTestResultPanel, resumen R/O, editor avanzado
- `PathTestResultPanel.jsx` — panel inline ok/error/no-ejecutado con `role="region"`, filas por paso, browser_note, duración formatada, botón "Cerrar resultado" + devolución de foco
- `NoiseStepEditor.jsx` — editor patrón BlockEditor + columna `expected_url_after_click` (EP-N09 reemplazo atómico)

## Componentes UI reutilizables nuevos

- `Toggle.jsx` (ui/) — toggle macOS ON/OFF: `role="switch"`, `aria-checked`, track `--success`/`--border-strong`
- `MinMaxInput.jsx` (ui/) — par de inputs numéricos con validación max≥min inline

## API client (client.js)

14 métodos `noise.*` añadidos: `getNoiseConfig`, `putNoiseConfig`, `getNoiseDestinations`, `createNoiseDestination`, `updateNoiseDestination`, `deleteNoiseDestination`, `getNoisePaths`, `createNoisePath`, `updateNoisePath`, `deleteNoisePath`, `deriveNoiseSelector`, `getNoiseOrigins`, `refreshNoiseVillages`, `testNoisePath(worldId, pathId)` (EP-N14, POST sin body ni Accept-Language).

## Patrones clave

- **DeletePopover**: se renderiza directamente cuando `deletePopoverOpen===true` (no tiene prop `open`). El padre gestiona el estado booleano y renderiza condicionalmente.
- **Wizard**: estado interno `phase: 'origin' | 'addstep'` + array `steps` local. Guardar = POST EP-N08 con steps completos.
- **Rutas is_dead**: botón Reactivar llama EP-N09 `{is_active: true}`; el backend resetea `consecutive_failures_count`.
- **Derive selector EC-NP14**: validación client-side con regex `/:contains|text\(\)/i` antes de confirmar selector manual.

## Patrón "Probar ruta" EP-N14 (v3)

- **Estado local PathCard**: `testing`, `testResult`, `testDurationMs`, `testError409`, `testError5xx` + `testBtnRef` / `liveRef`.
- **handleTest**: limpia estado previo → `testing=true` → `api.testNoisePath` → guarda result o error → `testing=false`.
- **Duración**: `Date.now()` antes/después del POST. Formato: < 1000 ms → "N ms"; ≥ 1000 → "N.N s".
- **409 inline**: `role="alert"` en segunda línea de cabecera. Texto = `e.detail` del backend, NO hardcodeado.
- **5xx inline**: `--danger 12px` bajo el botón.
- **PathTestResultPanel**: `role="region"` + `aria-label`. Pasos no ejecutados se infieren cruzando `result.steps` (ejecutados) con `path.steps` (definición) filtrando `step_order > aborted_at_step`.
- **Foco**: `handleCloseResult` llama `testBtnRef.current.focus()` tras cerrar el panel.
- **aria-live**: nodo `position:absolute; width:1px; height:1px; overflow:hidden` en PathCard. Se escribe al llegar el resultado para anuncio SR sin mover el foco.

## Patrón "Editar ruta" EP-N09 (v4) — renombrar label inline + acciones descubribles

- **Estado local PathCard añadido**: `renamingLabel`, `renameValue`, `renameSaving`, `renameError`, `overflowMenuOpen` + refs `renameBtnRef`, `labelBtnRef`, `overflowBtnRef`, `overflowMenuRef`.
- **Icono ✎**: `<button class="rename-pencil">` con `opacity:0` en idle. CSS en `app.css`: `.path-header:hover .rename-pencil, .path-header:focus-within .rename-pencil { opacity:1 }`. También visible en foco directo (a11y teclado).
- **Input inline**: cuando `renamingLabel=true`, el label se reemplaza por `<input>` con `autoFocus` + `aria-describedby` al nodo de error. Los botones [Probar] y [Editar pasos] se ocultan con `!renamingLabel` condition (no en DOM).
- **handleRenameConfirm**: (1) vacío → setRenameError; (2) sin cambio → cancelar sin API; (3) PUT EP-N09 `{label: trimmed}` → onUpdate + toast + cerrar; error → setRenameError con detail o genérico.
- **handleRenameCancel**: restaura `renameValue` a `path.label`, `setRenamingLabel(false)`, foco a `renameBtnRef`.
- **useEffect**: sincroniza `renameValue` con `path.label` cuando `!renamingLabel` (para actualización externa).
- **Botón "Editar pasos" en cabecera**: `setExpanded(true); setEditingSteps(true)` — ambos idempotentes, funciona con tarjeta colapsada o expandida.
- **Botón ⋯**: `aria-haspopup="menu"`, `aria-expanded`. Menú `role="menu"` con item `role="menuitem"`. useEffect con listeners `keydown(Escape)` + `mousedown(fuera)` para cerrar. Al elegir "Eliminar ruta": cierra menú, abre `deletePopoverOpen` (mismo DeletePopover de v3).
- **Tab order en modo edición**: `input → ✓ → ✕ → ▼ → ⋯` ([Probar]/[Editar pasos] no en DOM).
- **Devolución de foco**: cancelar → `renameBtnRef.focus()`; confirmar OK → `labelBtnRef.focus()`.
- **Script de verificación visual**: `frontend/scripts/test_pathcard_v4.mjs` (puppeteer desde el directorio frontend). Inyecta 5 estados en el DOM de `/mundos/1` usando los tokens CSS del proyecto.

## i18n

~149 claves `noise.*` totales en `es.js` y `en.js` (~130 noise.* base + 11 `noise.test.*` v3 + 8 `noise.paths.rename*`/`moreActions` v4). Los demás idiomas hacen fallback al español (catálogo base).

## Optimización de rendimiento (v2 — segunda iteración)

### Diagnóstico real del cuello
La medición anterior (6-11ms) era **falsa positiva**: el drawer siempre está en el DOM, `waitForSelector('[role="dialog"]')` resolvía instantáneamente. El cuello real se detectó con CDP `Performance.getMetrics`:
- **RecalcStyle**: 12x por apertura, 9.4ms duration → causado por re-render de todos los siblings de NoiseTab sin memoización
- **TaskDuration**: ~22ms por apertura
- **Animación CSS**: 150ms de slide → percepción de lentitud antes de que el usuario pueda interactuar

### Optimizaciones aplicadas (todos los ficheros de `noise/`)

**`NoiseTab.jsx`**:
- `openDrawer`, `closeDrawer`, `handleDestCreated`, `handleDestDeleted`, `handleDestUpdated` → `useCallback` estabilizados
- `onOpenDrawer` pasado directamente (no como arrow wrapper) a `NoiseDestinationsTable`

**`NoiseConfigPanel.jsx`**:
- `export function` → `export const = memo(function ...)` para evitar re-render cuando cambia el estado del drawer

**`NoiseDestinationsTable.jsx`**:
- `export function` → `export const = memo(function ...)` con `)` de cierre correspondiente

**`NoisePathList.jsx`**:
- `PathCard` → `memo(function PathCard(...))` para evitar re-render de todas las cards cuando `paths` no cambia
- `handlePathCreated/Updated/Deleted` en el drawer son `useCallback` → los refs son estables

**`NoiseDestinationDrawer.jsx`**:
- `handlePathCreated/Updated/Deleted` → `useCallback([], [])` para estabilizar refs de PathCard memo
- `SectionSkeleton` component con `memo` — se muestra solo durante `loadingPaths` en sección rutas
- Animación reducida de 150ms → 100ms con `ease-out`
- Añadido `will-change: transform` para promover el panel a GPU compositor y reducir main-thread recalcs
- **Skeleton de rutas**: `loadingPaths ? <SectionSkeleton/> : <NoisePathList loading={false}.../>` — el panel aparece instantáneamente con el contenido del form y wizard; solo la sección de rutas muestra skeleton durante el fetch

### Script de profiling
`frontend/scripts/profile-noise-drawer.mjs` — mide con MutationObserver + CDP `Performance.getMetrics` (correcto para drawer siempre-montado)

### Resultados antes/después
| Métrica | Antes | Después |
|---|---|---|
| RecalcStyle count | 12x | 5x avg |
| RecalcStyle duration | 9.4ms | 1.4ms |
| TaskDuration | 22ms | 12.7ms avg (5.9ms caliente) |
| Animación CSS | 150ms | 100ms |
| Panel interactivo (inputs) | ~10ms React | ~10ms React (sin cambio) |

El cuello principal era los recalcs de estilo por re-render de siblings sin memo. React render en sí siempre fue rápido (<15ms).
