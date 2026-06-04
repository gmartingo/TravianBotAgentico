---
name: binning-patterns
description: Patrón de binning por umbral inferior (Opción B) para distribuciones temporales en este proyecto
metadata:
  type: project
---

Para distribuciones temporales con conjunto discreto de valores `{F1, F2, ..., Fn}`:

**Opción B — umbral inferior (elegida en bd-ataques-oasis-temporal-distribution v2):**
- Cada bin `Fi` corresponde a la ventana `[Fi, Fi+1)` (inclusiva inferior, exclusiva superior).
- El último bin `Fn` es abierto: `[Fn, ∞)`.
- Un gap `g` pertenece al bin `Fi` si `Fi * unit <= g < Fi+1 * unit`.

**Por qué es mejor que vecino-más-cercano:**
- Monótona: no hay zonas de ambigüedad.
- Robusta al ruido de lag: un timer de 7 min que tarda 9 min sigue en bin 7, no salta al 10.
- El vecino-más-cercano crea empates exactos en el punto medio que exigen desempate arbitrario.

**Gaps fuera de rango:** descartar silenciosamente (no incluir en ningún bin).
Justificación: no distorsionar el bin más bajo con anomalías de reloj o datos corruptos.

**Frontera:** inclusiva por abajo `[`, exclusiva por arriba `)`.
- Gap exactamente igual al límite inferior → pertenece a ese bin.
- Gap exactamente igual al límite superior → pertenece al bin siguiente.

**Aplicación en este proyecto:**
- Conjunto: `{6,7,10,15,30,60,120,180,240,300}` minutos.
- Gaps < 6 min (< 360s) descartados.
- Gaps nulos o ≤ 0 descartados (primer ataque del oasis / relojes inconsistentes).
- Constante `WINDOWS` en el adapter: `{F: (F, F_next)}` con `F_next=None` para `300`.
