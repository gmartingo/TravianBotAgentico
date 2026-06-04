---
name: project-animal-frequency-panel
description: AnimalFrequencyPanel v2 — usuario rechazó la matriz, se rediseñó como lista simple con una frecuencia a la vez
metadata:
  type: project
---

La v1 del AnimalFrequencyPanel era una **matriz animal × franja temporal** (todos
los intervalos visibles a la vez). El usuario la rechazó: "no me gusta cómo presentas
las cosas porque no la entiendo, ¿puedes hacerla más sencilla?".

**Por qué:** la matriz requería comparar dos ejes simultáneamente, demasiada carga
cognitiva para un usuario no técnico en estadística.

**Rediseño v2 (aprobado conceptualmente):** lista simple, una frecuencia a la vez.
- El usuario elige UNA cadencia con un FrequencySelector de 10 opciones en 2 grupos.
- Ve una lista limpia de animales con lenguaje humano ("Normalmente hay 3–4",
  "Lo más habitual: 3", "Basado en 15 de 18 ataques").
- Sin scroll horizontal en ningún breakpoint — ventaja clave vs. la matriz en móvil.

**Frecuencias (decisión cerrada):** 6, 7, 10, 15, 30 min (grupo min) + 1h, 2h, 3h,
4h, 5h+ (grupo h). Default: 4h. Granularidad de minutos solicitada explícitamente
por el usuario (v1 era en horas: 1h..24h).

**Spec:** `docs/design/animal-frequency-panel.md` (reemplaza v1).
**Mockup:** `frontend/mockups/animal-frequency-panel.playground.html` (regenerado).
**Estado:** `ready-for-impl` — pendiente gate humano (usuario debe aprobar mockup).

**How to apply:** si se diseña otro panel de stats, preferir lista simple sobre
matrices. El usuario de este proyecto es visual y no técnico en estadística — el
lenguaje humano ("normalmente", "lo más habitual") es obligatorio.
