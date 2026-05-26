---
name: patterns-account-detail
description: Patrones implementados en S4 AccountDetailPage y modales S5-S8: sesión por mundo, menú contextual, modales reutilizables, utils compartidas
metadata:
  type: project
---

## uiUtils.jsx — utilidades compartidas

Fichero: `frontend/src/components/ui/uiUtils.jsx`
Exporta: `parseServerUrl`, `isValidServerUrl`, `Spinner` (14px), `BadgeSpinner` (11px inline),
`useFocusTrap(ref, active)`, `showToast(msg)`, `FOCUSABLE` (selector CSS).

- `showToast` crea un nodo DOM `#__travianbot-toast` si no existe; 3s auto-hide.
- `useFocusTrap` usa el selector `FOCUSABLE` con Tab/Shift-Tab.
- `BadgeSpinner` es un span con border CSS animado (11px), para badges inline de sesión.

## Máquina de estados de sesión (AccountDetailPage)

Estado: `sessions` = objeto plano `{ [worldId]: 'idle'|'connecting'|'active'|'error'|'stopping' }`.
- Inicializado como `idle` para todos los mundos al cargar.
- `fetchSessionState(accountId, worldId)` = GET /session, silencioso (cualquier error → idle).
- `handleStart` → `connecting` → `active` (nav `/mundos/:id`) | `error`.
- `handleStop` → `stopping` → `idle` | revertir a `active` si falla.
- `handleRetry` rellama a `handleStart`.
- `hasActiveSession` deshabilita el botón "Borrar cuenta" si algún mundo está en `active|connecting`.

## RowMenu — menú contextual de fila

NO usar `overflow-hidden` en el contenedor wrapper — recorta el popover.
Patrón: `<div className="relative inline-flex">` + `useEffect` con `mousedown` + `keydown`
para cerrar al hacer clic fuera o presionar ESC.
El popover usa `absolute end-0 top-[calc(100%+4px)] z-[300]`.

## Modales S5-S8

- Todos usan `useFocusTrap(modalRef, true)` + ESC + backdrop click.
- `triggerRef?.current?.focus()` al cerrar para devolver foco al elemento disparador.
- `EditAccountModal`: contraseña oculta tras enlace; una vez desplegada no se puede re-ocultar.
- `ConfirmDeleteModal`: reutilizable para cuenta (S7) y mundo (S8) via props `title/question/warning/onConfirm`.
  Estado 409: `errorState === 'active'` muestra error-block inline y reemplaza "Borrar" por "Cerrar".
  `ApiError` debe importarse en el top del fichero (no dynamic import).
- `AddWorldModal`: vista previa parseada con 200ms debounce sobre `parseServerUrl`.

## Claves i18n añadidas en Etapa 3

- `modal.edit.closeBtn` — aria-label del botón "×" del modal de edición
- `modal.edit.error409` — email duplicado en otra cuenta (409 en PUT /accounts/:id)

**Why:** Evitar hardcodear strings; toda cadena al catálogo.
**How to apply:** Al añadir cualquier modal nuevo, buscar primero las claves existentes en es.js antes de crear nuevas.
