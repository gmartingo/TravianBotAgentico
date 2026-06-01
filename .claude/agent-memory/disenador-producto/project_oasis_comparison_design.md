---
name: project-oasis-comparison-design
description: diseño de OasisComparisonPanel (tabla comparativa de reaparición por oasis): toggle tasa/proyección, sticky column, tarjetas en móvil, spec ready-for-impl
metadata:
  type: project
---

Diseño de `OasisComparisonPanel` — tabla comparativa multi-oasis × especie con columnas dinámicas.

**Decisiones clave:**
- Toggle Tasa /h ↔ Proyección (modo proyección = `projected_now` del response EP-10; sin nueva llamada a la API).
- Primera columna sticky (`inset-inline-start: 0`, propiedad lógica RTL-safe).
- Celdas: valor numérico con `tabular-nums`, "—" para ausencia semántica, "?" para `projected_now: null` (derrota en último reporte).
- Oasis `has_rates: false` al final de la tabla, con badge "Datos insuficientes" + ⚠.
- `valid_intervals` en tooltip (divulgación progresiva), NO inline en la celda.
- Móvil (< md): tabla → tarjetas apiladas por oasis.
- NO reutiliza `RegenRatesSection` (contrato incompatible). SÍ reutiliza `NatureIcon` y patrón loading/error/empty de `GlobalOasisStatsPanel`.
- `StatsTab` se modifica (cambio mínimo): añade `OasisComparisonPanel` encima de `GlobalOasisStatsPanel`.

**Artefactos:**
- Spec: `docs/design/oasis-comparison.md` (estado: ready-for-impl, pendiente aprobación mockup)
- Mockup: `frontend/mockups/oasis-comparison.playground.html`
- Spec funcional: `docs/specs/reaparicion-animales-oasis.md`

**Why:** feature de comparativa de oasis multi-especie (EP-10); diseño acordado con el usuario sin reabrir decisiones de producto.

**How to apply:** si se pide modificar o extender `OasisComparisonPanel`, partir de este diseño y del spec. El gate humano del mockup sigue pendiente.
