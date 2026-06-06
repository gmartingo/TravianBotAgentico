---
name: project-route-templates-design
description: Página global /rutas (ManagementShell): portal de desarrollador de plantillas de ruta. Mockup playground creado. Spec funcional ready-for-impl.
metadata:
  type: project
---

Página global `/rutas` bajo ManagementShell (topbar + sidebar de 200px, sin info de mundo).
Es un catálogo maestro global de `RouteTemplate` sin `world_id`.

**Why:** El desarrollador cura las rutas una vez y las clona a cualquier mundo para que el bot navegue con ruido humano.

**How to apply:** Al diseñar UI relacionada con rutas/noise, tener en cuenta que:
- `NoiseTab` NO se puede montar en `/rutas` (depende de `worldId`)
- `NoiseDestinationsTable` y `NoiseDestinationDrawer` se AJUSTAN con prop `mode="template"` sin duplicar fichero
- `NoisePathWizard`, `NoiseStepEditor`, `NoiseWizardStepForm` se reutilizan sin cambios
- Columnas de la tabla: label/slug, categoría (7: MAP/OASIS_INFO/PLAYER_PROFILE/MESSAGES/REPORTS/BUILDING_VIEW/OTHER), nº pasos, peso (0.1–5.0), estado (segura/muerta), acciones (editar/probar/clonar/borrar)

Mockup: `frontend/mockups/rutas.playground.html` (creado 2026-06-05, actualizado 2026-06-06)
- 10 vistas en el selector (ampliado de 7)
- Bloques A (cabecera) B (filtros) C (tabla con datos + ▶ por fila + filas expand) D (vacío) E (drawer edición) F (modal clonar) G [OBSOLETO] H (re-sync panel) I (seed banner)
- Barra J sticky bottom: WorldSelector bar (fija, no arrastrable)
- Andamiaje drag&drop reutilizado de noise-catalog.playground.html
- ManagementShell: sidebar 200px (vs WorldSpace que es 180px)

**Interacción "Probar ruta" rediseñada (2026-06-06):**
- Bloque G (panel con path_index + selector de mundo propio + botón "Ejecutar") ELIMINADO.
  Razón: provocaba error "path_index N fuera de rango / 0 path(s)" en rutas compuestas.
- Reemplazado por: ▶ por fila (P1, siempre visible) + barra J sticky bottom (selector global) + fila expand inline bajo la fila activa.
- Un solo selector de mundo para TODOS los ▶ — no se repite por fila.
- Spec de diseño de la nueva interacción: `docs/design/route-test-interaction.md` (ready-for-impl, gate humano pendiente)

Spec funcional: `docs/specs/route-templates-developer-portal.md` (ready-for-impl, gate desarrollador-apis completado 2026-06-05)
