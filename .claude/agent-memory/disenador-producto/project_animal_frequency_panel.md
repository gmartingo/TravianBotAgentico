---
name: project-animal-frequency-panel
description: AnimalFrequencyPanel v5 — peor caso + TypeSummaryCard (total animales, botín, coords). Actitud macintosh preservada. coordUtils.js pendiente de crear.
metadata:
  type: project
---

Spec de diseño en `docs/design/animal-frequency-panel.md` (estado: ready-for-impl, v5).
Mockup editable en `frontend/mockups/animal-frequency-panel.playground.html` (gate humano pendiente — usuario debe aprobar v5).
Spec funcional relacionado: `docs/specs/bd-ataques-oasis-temporal-distribution.md` (estado: implemented).

## Historial de versiones

- **v1 (rechazada):** matriz animal×franja temporal. Rechazada: "no la entiendo, ¿puedes hacerla más sencilla?".
- **v2 (superada):** lista simple de una frecuencia, todos los animales sin tipo. El lenguaje humano y la simplicidad se aprobaron.
- **v3 (rechazada):** FrequencySelector + 5 secciones acordeón por tipo. Rechazada: "demasiado recargado", "fuera los acordeones", "las filas no me cuadran".
- **v4 (aprobada estéticamente):** FrequencySelector + segmented control (pestañas) por tipo + lista limpia. El usuario aprobó: "está mejor".
- **v5 (actual):** añade 4 datos (max_present, total_animals, avg_bounty, oasis_coords) sin romper el aire macOS. TypeSummaryCard encima de la lista. Fila de animal v5 con "peor: N" en caption terciaria.

## Decisiones clave v4 (base, preservadas en v5)

**Pestañas en vez de acordeones:** patrón macOS. Una sola lista protagoniza en pantalla.
**Cifra protagonista:** `avg_present` a 22px/600/mono.
**Sin marcos por fila, sin marco del panel:** solo hairline entre animales, vive sobre StatsTab.
**Confianza discreta:** punto 5px + caption `--text-tertiary`.
**Móvil:** FrequencySelector en dos filas, TypeTabSelector scroll horizontal.

## Decisiones clave v5 (datos nuevos sin saturar)

**TypeSummaryCard:** bloque sin marco ni fondo propio. Hairline inferior. Posición: encima de la lista de animales (dentro del tabpanel activo). Tres zonas:
1. Frase cabecera + confianza + coord chips pill `(x|y)` inline (máx 3 + "y N más"). Chips: `--surface-2`, `--border`, `--radius-full`, mono 11px, NO interactivos.
2. Total animales: `avg` 17px/600/mono + "de media" + "lo normal X" + "peor Y" — todos 12px/`--text-tertiary`. Si max null → omitir "peor".
3. Botín: iconos Lucide 14px + cifra mono. Si todos 0 → "Sin datos de botín" texto tenue.

**Fila de animal v5:** caption: `lo normal: X · peor: Y · N ataques` — 12px/`--text-tertiary`. Max null → omitir "peor: —". La media (22px) sigue siendo el único protagonista.

**Ficha oculta cuando tipo vacío:** solo aparece con datos. Si el tipo está vacío → TypeEmptyState directamente, sin ficha.

**coordUtils.js:** crear `frontend/src/utils/coordUtils.js` con `formatCoord(x, y) → "(x|y)"`. Refactorizar los 5 componentes existentes que duplican este formateador (OasisList, OasisStatsPanel, OasisCombatPlannerPanel, y otros). TypeSummaryCard es el 6to usuario.

**Componentes v5:**
- REUTILIZA: `NatureIcon.jsx`, patrón FrequencySelector.
- CREA: `AnimalFrequencyPanel.jsx` (con TypeSummaryCard, TypeTabSelector, AnimalFrequencyRow, TypeEmptyState internos).
- CREA: `coordUtils.js` (deduplicación).

**Claves i18n v5 nuevas:** `ar.freq.worst_label`, `ar.freq.summary_total_label`, `ar.freq.summary_bounty_label`, `ar.freq.summary_bounty_total`, `ar.freq.summary_bounty_no_data`, `ar.freq.summary_coords_more`, etc. Ver §9 del spec.

**Posición en StatsTab:** 4 (sin cambios).

**Why:** añadir datos sin saturar = jerarquía + separación física. La ficha es el contexto del tipo, la lista es el detalle. Primero el contexto (macOS Activity Monitor pattern), luego el desglose. Max en caption terciaria = mismo nivel que moda, nunca protagonista.

**How to apply:** patrón TypeSummaryCard reutilizable para "ficha de resumen de una categoría" encima de su lista. Coords siempre via coordUtils.formatCoord.

Related: [[project-spawn-mechanics-design]], [[project-oasis-stats-design]], [[project-noise-catalog-design]]
