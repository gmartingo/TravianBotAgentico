---
name: patterns-wizard-modal
description: Patrón de wizard modal (S3) y routing de overlay sobre shell — cómo se implementan en este proyecto
metadata:
  type: project
---

## Wizard modal (S3) sobre el shell

El wizard se implementa como una ruta `/cuentas/nueva` que renderiza `NewAccountPage.jsx`.
Esta página renderiza dos componentes apilados:
1. `AccountsListPage` — como fondo (el backdrop del wizard la atenúa visualmente)
2. `WizardModal` — en capa superior con `position: fixed + z-[400]`

Esto hace que Topbar + Sidebar permanezcan visibles detrás del backdrop, exactamente como en el mockup.

## Routing de rutas de overlay

La ruta `/cuentas/nueva` debe ir ANTES de `/cuentas/:id` en App.jsx.
Sin este orden, React Router v6 trata "nueva" como un id y abre el detalle de cuenta.

```jsx
<Route path="/cuentas/nueva"  element={<NewAccountPage />} />   // PRIMERO
<Route path="/cuentas/:id"    element={<AccountDetailPage />} /> // DESPUÉS
```

## Focus trap en modales

Se usa un hook `useFocusTrap(ref, active)` que escucha `Tab`/`Shift+Tab` y cicla el foco
dentro del modal usando los selectores FOCUSABLE estándar. Ver `WizardModal.jsx`.

## Parseo de URL de servidor Travian

```js
// ts1.x1.international.travian.com → "ts1 · x1 · international"
function parseServerUrl(raw) { ... }  // en WizardModal.jsx
```

Extrae: partes[0] = server, segmento que matches /^x\d+/ = speed, segmento entre speed
y "travian" que no sea server ni speed = region.

## Spinner inline en botones

El spinner se anima con un keyframe inline `@keyframes wizard-spin` dentro del componente.
No usa una clase CSS global para no contaminar el ámbito.

## Llamadas a la API en el wizard

Secuencia en dos pasos separados:
- "Siguiente" → `POST /accounts` → guarda el `id` en estado
- "Crear cuenta" → `POST /accounts/:id/worlds { server: url, tribe: valor }`

El campo del mundo se llama `server` (NO `server_url`). Ver client.js `createWorld`.

## Claves i18n añadidas en esta sesión

- `wizard.error.tribe.required` — "Selecciona una tribu"
- `wizard.btn.showPassword` / `wizard.btn.hidePassword`
- `wizard.toast.created` — "Cuenta creada" (reservada para futura integración de toast)

Añadidas en `es.js` y `en.js`. Los 23 idiomas restantes usan fallback automático.
