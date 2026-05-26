---
name: branch-hygiene-one-feature-per-branch
description: Una feature = una rama bien nombrada; git-flow-advisor debe avisar si el contenido no encaja con el nombre/alcance de la rama activa
metadata: 
  node_type: memory
  type: feedback
  originSessionId: e82e3551-50d4-4464-85df-1652fc4e450f
---

No acumular trabajo no relacionado en una rama mal nombrada. Pasó que `feature/kirilloid-buildings` acabó conteniendo login-sesión + todo el frontend + docs (cuando existía incluso un `feature/login` sin usar). Resultado funcional correcto, pero higiene de ramas floja.

**Why:** Git Flow del proyecto usa develop (integración) + feature/* + main (release). Mezclar features en una rama mal nombrada confunde el historial, dificulta revisar/revertir por feature y rompe la trazabilidad nombre↔contenido.

**How to apply:** Antes de empezar trabajo de una feature nueva, crear/cambiar a una rama `feature/<nombre-acorde>` (reutilizar la existente si ya hay una, p.ej. feature/login). El git-flow-advisor debe, ANTES de commitear, comprobar si el contenido encaja con el nombre/alcance de la rama activa y AVISAR si no (proponer rama nueva), no commitear ciegamente en la rama checkouteada. El orquestador tampoco debe seguir commiteando en la rama activa sin verificar que corresponde. Relacionado: [[autonomous-git-execution]], [[registro-cuentas-mundos-feature]].
