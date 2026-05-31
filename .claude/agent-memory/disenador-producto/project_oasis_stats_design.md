---
name: project-oasis-stats-design
description: Decisiones de diseño para el rediseño de la pestaña Estadísticas del módulo de reportes de oasis — lista navegable + ratio/hora
metadata:
  type: project
---

El spec de diseño `docs/design/bd-ataques-oasis-stats-oasis-nav-ui.md` (estado: ready-for-impl)
amplía el spec padre `docs/design/bd-ataques-oasis-ui.md` (estado: implemented).

**Decisión clave de layout:** expand-in-place (no drawer lateral, no nueva ruta). La fila
seleccionada de la tabla de oasis se expande in-place con colspan. El drawer ya se usa para
el detalle de reportes en la pestaña Historial — mezclar patrones confunde.

**KPI principal visible al expandir:** sección "Ritmo de regeneración" (ratio/hora por animal)
aparece antes que las tablas de aparición y repoblación. El usuario lo pidió explícitamente.

**Patrón de filtro:** debounce 300ms, sin botón "Aplicar". La lista de oasis no tiene
paginación (RT-NAV1 del spec funcional: volumen bajo, decenas de oasis).

**Componentes nuevos a crear:** `OasisList.jsx`, `NatureIcon.jsx`, `RegenRatesSection.jsx`.
`NatureIcon` es el análogo a `ResIcon` para animales (rutas `nature_N.png`).

**Mockup editable:** `frontend/mockups/stats-oasis-nav.playground.html` (10 vistas,
drag & drop, toggle tema, exportar layout JSON). Gate humano pendiente.

**Why:** El StatsTab anterior obligaba al usuario a teclear coords manualmente y el
OasisStatsPanel tenía bugs de nombres de campo. El rediseño elimina la fricción inicial
y prioriza el KPI de cadencia óptima de ataque.

**How to apply:** Al diseñar nuevas funcionalidades de análisis de datos en este proyecto,
considerar el patrón expand-in-place para master-detail cuando la lista es corta y la
comparación entre filas es relevante. El drawer se reserva para contenido que el usuario
consulta de forma aislada (no comparativa).

Related: [[project-farm-lists-design]]
