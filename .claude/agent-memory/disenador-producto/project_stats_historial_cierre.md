---
name: project-stats-historial-cierre
description: Retoques de cierre sprint Estadísticas+Historial — Balance, acordeones colapsados, filtro fecha texto, historial sin tarjetas móvil. Spec ready-for-impl.
metadata:
  type: project
---

Spec de diseño en `docs/design/stats-historial-cierre.md` (estado: ready-for-impl).
Mockup en `frontend/mockups/stats-historial-cierre.playground.html` (pendiente aprobación usuario).

**Cuatro cambios independientes:**

1. **BalanceSection** (nuevo componente `BalanceSection.jsx`): encabeza la pestaña Estadísticas ANTES de `GlobalOasisStatsPanel`. Filtro de fecha propio (solo afecta al balance). Grid [Perdido | Robado] + Neto en grande con color semántico. Nota informativa si `reports_without_tribe > 0`.

2. **Acordeones globales** (`GlobalOasisStatsPanel.jsx`): `RegenRatesSection` global y `GlobalAppearancesTable` envueltos en acordeón colapsado por defecto (`useState`). El acordeón muestra una línea de resumen calculada (N animales, rango de tasas / top 3). OJO: el colapso es SOLO para las versiones globales — `RegenRatesSection` dentro de `OasisStatsPanel` individual no cambia.

3. **Filtro de fecha texto** (`HistoryFilters.jsx`): `type="date"` → `type="text"` con placeholder `YYYY-MM-DD HH:MM:SS`. Validación en vivo con regex. Borde rojo + mensaje error. Botón Aplicar disabled si hay error. Envío al backend como ISO 8601 con hora.

4. **Historial sin tarjetas** (`HistoryTable.jsx`): eliminar bloque `<div className="md:hidden">` con `ReportCard`. En móvil queda la tabla con scroll horizontal contenido + primera columna (Fecha) sticky izquierda. Columnas P2 (Desde, Bajas) siguen ocultas < md.

**Patrón de acordeón elegido:** `useState` + CSS `max-height`. Razón: coherencia con `HistoryFilters.jsx` (mismo patrón), animación de transición, resumen dinámico calculado en JS.

**Why:** usuario quería quitar las tarjetas de móvil, colapsar las secciones globales, tener filtros de fecha con hora, y un KPI de rentabilidad al inicio de Estadísticas.

**How to apply:** si en el futuro se piden nuevas secciones colapsables en GlobalOasisStatsPanel, usar el mismo patrón `useState` acordeón. El componente `BalanceSection` puede extenderse si el backend añade más métricas al endpoint de balance.
