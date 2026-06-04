---
name: project-noise-catalog-design
description: Diseño pestaña Ruido — v4 añade edición inline de label de ruta (✎) + rediseño cabecera PathCard (Editar pasos en cabecera, ⋯ overflow menu). Mockup 30 vistas.
metadata:
  type: project
---

Spec de diseño en `docs/design/noise-catalog-ui.md` (v4, estado: ready-for-impl).
Mockup en `frontend/mockups/noise-catalog.playground.html` (30 vistas, v4).

## Decisiones clave v4 — EDITAR RUTA (renombrar + acciones descubribles)
- **Renombrar label**: icono ✎ (pencil, 12px, `--text-tertiary`) visible en hover de la cabecera.
  - Al pulsar: label → `<input>` inline con `autoFocus`. Botones ✓/✕ mini a la derecha.
  - Confirmar con Enter o ✓ → `api.updateNoisePath(worldId, path.id, { label })` (EP-N09).
  - Cancelar con Escape o ✕ → sin llamada API, label restaurado.
  - Si label vacío: botón ✓ deshabilitado + mensaje "El nombre no puede estar vacío."
  - Error API (422/500): input con borde rojo + mensaje del `detail` del response.
  - Durante el guardado: input deshabilitado, spinner 10px en lugar del ✓.
  - Durante la edición: botones [Probar] y [Editar pasos] se ocultan para reducir ruido.
  - Patrón: mismo que edición de label de destino en `NoiseDestinationDrawer` pero comprimido.
- **"Editar pasos" sube a la cabecera** (siempre visible, no solo en cuerpo expandido).
  - Al pulsar con tarjeta colapsada: expande Y activa editor (`expanded=true`, `editingSteps=true`).
  - Al pulsar con tarjeta expandida: solo activa editor.
- **✕ → ⋯ (overflow menu)**:
  - Botón ghost 26×26px con `⋯`. Al pulsar: mini-popover con "Eliminar ruta" en `--danger`.
  - Se cierra con Escape o click fuera.
  - El `DeletePopover` existente sigue siendo el que confirma antes de ejecutar.
- Nuevas claves i18n: `noise.paths.renameBtn/renameInput/renameConfirm/renameCancel/
  renameEmptyError/renameError/renamed/moreActions`.
- `origin` de la ruta: INMUTABLE (no editable, solo badge R/O en cabecera). EP-N09 no lo acepta.

## Decisiones clave v3 — PROBAR RUTA (EP-N14)
- Botón "Probar" en cada `PathCard` (MODIFICAR, no nuevo componente): entre badge-estado y chevron.
  - Estilo = igual que "Reactivar" (secundario mini 24px). Color NEUTRO, NO oro, NO verde.
  - Disponible en rutas activas Y muertas (EC-PT01 del spec §16).
  - Estado loading: "Probando..." + spinner + caption "Puede tardar hasta 60 s" como segunda línea en la cabecera.
- `PathTestResultPanel` (CREAR): panel inline bajo la cabecera, fondo `--surface-2`.
  - 3 estados: OK (chip verde "✓ Ruta OK") / ERROR (chip rojo "✕ Falló en el paso N") / cerrado.
  - Filas de pasos: icono ✓/✕/─ + número + badge acción + selector mono + URL mono.
  - Pasos no ejecutados inferidos de `path.steps` - `result.steps` (no vienen en el response).
  - `browser_note` del response se muestra tal cual (no hardcodeado).
  - Duración calculada en el frontend (Date.now antes/después del POST), formateada: < 1s → "N ms", ≥ 1s → "N.N s".
  - `role="region"` + `aria-label`. Nodo `aria-live="polite"` oculto para anunciar resultado.
- Error 409: aviso inline segunda línea en la cabecera (NO panel separado, NO toast). `role="alert"`.
  - Texto viene del `detail` del response (no hardcodeado). Desaparece al reintentar o cerrar.
  - Dos mensajes 409 posibles: "El agente del mundo está desconectado..." / "El browser está ocupado...".
- Error 5xx: mensaje inline bajo el botón "Error del servidor. Reintenta."
- API cliente: `api.testNoisePath(worldId, pathId)` → POST sin body, sin Accept-Language.
- Claves i18n nuevas: `noise.test.testBtn`, `noise.test.testing`, `noise.test.loadingHint`,
  `noise.test.closeResult`, `noise.test.resultOk`, `noise.test.resultError`, `noise.test.stepNotRun`,
  `noise.test.resultLabel`, `noise.test.error5xx`.

## Decisiones clave v1 (sin cambios)
- Pestaña "Ruido" en WorldSpacePage.jsx: navItem con `IconNoise` (SVG ondas wifi).
- Config global COLAPSABLE (off por defecto). Toggle `noise_enabled` siempre visible en cabecera.
- Tabla destinos densa: Nombre/URL · Categoría · Peso · Seguro · Rutas · Borrar.
- Destinos `is_dead=true`: fondo `--danger-subtle` + badge "Muerto · N fallos". Ocultos por defecto.
- Drawer lateral (patrón `FarmListDrawer.jsx`) para gestión de rutas. 4 niveles jerarquía.
- `Toggle`: ON/OFF macOS. Color ON = `--success`. `role="switch"`.
- `MinMaxInput`: dos inputs numéricos " — " validación max >= min.
- `NoiseCategoryBadge`: colores semánticos por categoría.
- url_pattern y category INMUTABLES (solo lectura en drawer).

## Decisiones clave v2 — WIZARD MANUAL (spec noise-path-wizard.md)
- El usuario RECHAZÓ el editor directo de selectores CSS. El wizard es el protagonista.
- **Wizard** ocupa la parte SUPERIOR del drawer. Rutas existentes van debajo (secundarias).
- **Origen**: desplegable precargado (no input libre). 9 genéricas + aldeas por-aldea dinámicas.
  - Fuente: EP-N12 GET /noise/origins (se llama al abrir el drawer).
  - `villages_loaded=false` → aviso + botón "Actualizar aldeas" (EP-N13 POST /noise/refresh-villages).
  - EP-N13 puede responder 409 si bot desconectado → inline error (no toast).
- **Por cada paso CLICK**: formulario de 3 campos (URL ctx + label + outerHTML textarea).
  - El campo "URL esperada tras click" (`expected_url_after_click`) es colapsable (opcional).
  - Botón "Derivar selector" llama EP-N11 POST /noise/derive-selector.
  - 3 estados de feedback: ÚNICO (checkmark verde) / NO-ÚNICO (aviso + alternativas + input manual) / ERROR 422.
  - El usuario puede confirmar, elegir alternativa, o escribir selector manual (validación: no :contains ni text()).
- **Lista de pasos acumulados**: muestra los pasos añadidos con botón ✕ por paso.
- `is_dead` en RUTAS (no solo en destinos):
  - Badge "Muerta · N fallos" en `--danger-subtle`.
  - Botón "Reactivar" → EP-N09 con is_active=true → backend resetea consecutive_failures_count.
  - DIFERENCIA con is_dead de destino: rutas SÍ tienen "Reactivar". Destinos NO.
- Editor avanzado de pasos (BlockEditor) es secundario: se abre desde "Editar pasos" en ruta expandida.
  - Nueva columna: `expected_url_after_click` (input mono, vacío = sin verificación).
- `NoiseOriginBadge`: muestra nombre de aldea para VILLAGE_N.

## Componentes nuevos añadidos en v2
- `NoisePathWizard`: wizard multi-paso (origen + formulario paso + lista acumulada + guardar).
- `NoiseOriginSelector`: desplegable de anclas (genéricas+aldeas) + botón actualizar (EP-N13).
- `NoiseDerivedSelectorFeedback`: panel feedback EP-N11 (3 estados).
- `NoiseWizardStepForm`: formulario de un paso del wizard.

Spec funcional wizard: `docs/specs/noise-path-wizard.md` (implementado 2026-06-02).
Spec funcional base: `docs/specs/human-sessions.md` §17 (implementado).
Backend completo: EP-N01..N13 en `adapters/api/routes/noise.py`.

**Why:** [[project-worldspace-ui]]
