---
name: project-attack-reports-design
description: Diseño de la página Reportes de oasis (BD de ataques) — spec ready-for-impl, mockup generado
metadata:
  type: project
---

Spec de diseño creado en docs/design/bd-ataques-oasis-ui.md (estado: ready-for-impl).
Mockup editable: frontend/mockups/bd-ataques-oasis.playground.html (pendiente aprobación del usuario).

**Estructura de la página**: ManagementShell + Sidebar (ítem nuevo "Reportes de oasis") + AttackReportsPage con 3 tabs: Ingresar / Historial / Estadísticas. Una sola entrada en el sidebar, sin rutas anidadas.

**Patrón de flujo Ingresar**: textarea (foco auto) → botón Analizar → preview con TravianReport reutilizado → Guardar/Descartar. Textarea se colapsa al mostrar el preview (bloque A). Aviso de duplicado en banner dorado sobre el preview (no modal).

**Componentes CREAR**: AttackReportsPage, TabBar, IngestTab, ReportPreview, HistoryTab, HistoryTable, HistoryFilters, ReportDetailDrawer, StatsTab, OasisStatsPanel, DeletePopover.

**TravianReport**: REUTILIZAR sin cambios (mapeo en ReportPreview — animals.present → defenderTroops.quantity_initial, etc.).
**Sidebar.jsx**: MODIFICAR (añadir ítem al array NAV_ITEMS — retrocompatible).

**Drawer de detalle**: patrón §19.11 DESIGN.md, 480px desktop / 100vw móvil.
**Borrado**: popover inline (no modal de pantalla completa) — menos intrusivo.
**Paginación**: explícita (Anterior / 1–50 de N / Siguiente), no scroll infinito.
**Tab activo**: persiste en localStorage.

**Tabla de animales regenerados en Stats**: columnas dinámicas (solo animales vistos en ese oasis); intervalos formateados como "6 h 14 min" no segundos raw; regenerados null → "—" (--text-tertiary), positivos → "+N" (--success).

**Why:** spec funcional (docs/specs/bd-ataques-oasis.md) ya en ready-for-impl.
**How to apply:** el desarrollador-ux-ui debe leer el spec de diseño antes de implementar. El mockup debe ser aprobado por el usuario (gate obligatorio) antes de implementar la UI real.
