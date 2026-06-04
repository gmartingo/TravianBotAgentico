---
name: project-spawn-mechanics-design
description: Decisiones de diseño para los paneles de spawn mechanics en StatsTab — v2 implementada (3 paneles separados) y v2.1 iteración (tabla fusionada OasisCombatPlannerPanel + reorden)
metadata:
  type: project
---

Spec de diseño en `docs/design/oasis-spawn-mechanics.md` (v2.1 estado: ready-for-impl, gate humano pendiente — mockup v16).
Mockup en `frontend/mockups/oasis-spawn-mechanics.playground.html` (16 vistas, vistas 12-16 son las nuevas de v2.1).

## Estado v2 (implementada 2026-06-02)
- SpawnMechanicsPanel, OasisCompositionPanel, WorstCasePlannerPanel implementados y verificados.
- Orden en StatsTab: SpawnMechanics → OasisComposition → WorstCase → separador → Balance → GlobalStats → OasisList.

## Estado v2.1 (iteración pendiente de aprobación del mockup)

**Cambio 1 — Tabla fusionada:**
OasisCompositionPanel + WorstCasePlannerPanel → **OasisCombatPlannerPanel**.
- Una fila por animal, por oasis. Columnas: Animal | Típica (avg·máx) | Peor combo (×N) | Def. inf. | Def. cav.
- Cabecera de grupo por oasis: coords + badge tipo + confianza + SpawnStatusDot.
- Fila de totales al pie de cada grupo (def. inf/cav, solo suma animales sin anomalía).
- Selector de intervalo único (TimerSelector) en la cabecera del panel, compartido.
- Anomalías: badge "anom." en columna Animal, columnas Peor/Def = "—" en text-disabled, no suman en totales.
- Oasis tipo null: nota inline en lugar de tabla, sin totales.
- Componentes eliminados: OasisCompositionPanel, WorstCasePlannerPanel, AnimalCompositionChip, WorstCaseChip.

**Cambio 2 — Nuevo orden StatsTab:**
1. SpawnMechanicsPanel (leyenda/educativo, colapsable)
2. BalanceSection (pérdidas/ganancias — sube al puesto 2)
3. OasisCombatPlannerPanel (tabla fusionada)
--- separador ---
4. GlobalOasisStatsPanel (arrastrable en mockup)
5. OasisList (arrastrable en mockup)

**Decisiones clave (heredadas de v2):**
- TimerSelector = 4 botones pill (6/7/10/15 min), activo usa accent-subtle + borde accent.
- Badge anomalía = acento oro (no naranja — DESIGN.md §14 lo prohíbe).
- SpawnStatusDot: siempre texto + color (nunca solo color).
- Confianza = texto secundario "·med/·low", no en color.

**Why:** El usuario usó v2 en vivo y pidió fusionar los dos paneles operativos (misma fuente de datos, lectura más natural) y reordenar para ver Balance antes de la tabla de combate.

**How to apply:** Cuando dos paneles comparten el mismo endpoint y datos relacionados, considerar fusionarlos en tabla agrupada antes que mostrarlos en paralelo. La fila de totales al pie de grupo es el patrón de tabla densa para resúmenes.

Related: [[project-oasis-stats-design]]
