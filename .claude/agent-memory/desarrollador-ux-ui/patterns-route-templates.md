---
name: patterns-route-templates
description: RouteTemplatesPage (/rutas): portal global de plantillas, reglas v2+v3, componentes reutilizados, huecos de API pendientes
metadata:
  type: project
---

## Página /rutas — RouteTemplatesPage

`frontend/src/pages/RouteTemplatesPage.jsx` bajo `ManagementShell`.
Implementa spec `docs/specs/route-templates-developer-portal.md` (v1+v2+v3).

### Regla crítica v2 rev.2: SIN peso en plantilla
`navigation_weight` NO existe en `RouteTemplate`. El peso se fija SOLO al clonar a un mundo:
- `NewTemplateModal`: sin campo de peso.
- `CloneToWorldModal`: slider + input [0.1–5.0], default 1.0. Label: "Frecuencia en [nombre mundo]".
- `TemplateRow`: sin columna Peso en la tabla.
- `NoiseDestinationDrawer` modo template: campo peso oculto con `{mode !== 'template' && ...}`; `handleSaveDest` no envía `navigation_weight` al PATCH.

### Campo Origen = DESPLEGABLE (no negociable)
`origin_template_id` se edita via `<select>` en `NewTemplateModal`:
- Opción "Libre (sin origen)" → `null`
- Grupo "Rutas existentes" → lista de plantillas del catálogo (prop `templates`).
- Manejo de 409 por ciclo de origen: muestra el mensaje del campo `detail.message`.

### Badge "encadenada" en TemplateRow
Si `tpl.origin_template_id != null` → badge "↗ encadenada" en `var(--accent-subtle)`.

### Tabla de pasos heredados (EP-RT11)
- `InheritedStepsPanelDrawer` (en `NoiseDestinationDrawer.jsx`): carga EP-RT11 `GET /route-templates/{id}/chain` cuando `dest.origin_template_id != null`. Muestra raíz→hoja con el último clic resaltado.
- `InheritedStepsPanel` (en `RouteTemplatesPage.jsx`): versión independiente para uso fuera del drawer.
- Aviso cuando origen eliminado (EC-V2-03): "Ejecutará desde cualquier punto".

### TestRoutePanel v3 (estado de sesión + cerrar sesión)
- Al seleccionar mundo: llama `getAgentStatus(worldId)` para inferir sesión activa.
- Badge verde si `state === 'running'` o `session_active === true`.
- Botón "Cerrar sesión" visible si sesión activa → llama `api.closeWorldSession(worldId)`.
- Texto del botón de ejecutar: "Abriendo sesión / probando…" si sesión estaba cerrada.
- La sesión persiste entre tests (no se cierra tras cada test).

### Métodos client.js añadidos
- `cloneRouteTemplate(id, worldId, force, navigationWeight)`: envía `{ navigation_weight }` en body.
- `getRouteTemplateChain(id)`: `GET /route-templates/{id}/chain` (EP-RT11).
- `closeWorldSession(worldId)`: `DELETE /worlds/{worldId}/session` (EP-RT12).

### Componentes reutilizados SIN ficheros gemelos
- `NoiseDestinationDrawer mode="template"`: paths via EP-RT06; sin peso; con InheritedStepsPanelDrawer.
- `PathTestResultPanel`: reutilizado sin cambios.
- `NoiseCategoryBadge`: reutilizado sin cambios.

### Huecos de API pendientes (backend debe implementarlos)
- EP-RT11 `/chain`: sin este endpoint el InheritedStepsPanel muestra error de red (correcto).
- EP-RT12 `DELETE /worlds/{id}/session`: gates desarrollador-apis + guardian pendientes.

### NoiseTab existente NO se rompe
Todos los cambios en `NoiseDestinationDrawer` son `{mode !== 'template' && ...}`. El `mode` default es `'world'`, así que el flujo de `WorldSpacePage` > `NoiseTab` no se toca.
