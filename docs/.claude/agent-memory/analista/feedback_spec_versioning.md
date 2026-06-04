---
name: feedback-spec-versioning
description: Cómo actualizar un spec cuando una feature ya implementada se rediseña (v1→v2)
metadata:
  type: feedback
---

Cuando un spec está en estado `implemented` y el usuario solicita un rediseño significativo:
- Cambiar `estado: ready-for-impl` (el código implementado ya no corresponde al spec).
- Cambiar `apis_validadas_por_desarrollador_apis: false` si el contrato de API cambia.
- Añadir historial en el frontmatter (comentario YAML) con lo que había en v1 y qué cambia en v2.
- Añadir una sección destacada "REVISIÓN v2" al inicio del spec (antes de la sección 1), visible de inmediato.
- Actualizar TODAS las secciones del spec para reflejar v2 (no dejar mezcla de v1 y v2).
- Añadir sección "Qué cambia respecto a v1" al final, como guía de migración para el implementador.
- Conservar el "Registro de implementación v1" como histórico (renombrarlo, no borrarlo).

**Why:** el implementador lee el spec en frío. Si hay mezcla de v1 y v2, o si los criterios de aceptación son de v1, implementará mal.

**How to apply:** en cualquier spec con `estado: implemented` que reciba un redesign.
