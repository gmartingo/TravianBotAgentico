---
name: route-templates-seed-intentionally-empty
description: "el usuario VACIÓ a propósito seeds/route_templates.json ([]); no restaurarlo ni re-sembrar plantillas sin preguntar"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 86034ada-b138-4896-879f-7f733fefe65a
---

El usuario vació deliberadamente `seeds/route_templates.json` a `[]` y borró las 20 plantillas estándar del portal de rutas. Quiere curar su propio catálogo (tenía creadas: dorf2, estadísticas, estadísticas-tropas — perdidas en un reset previo, NO recuperables del freelist SQLite).

**Why:** yo asumí que el seed vacío era una regresión accidental, hice `git checkout HEAD -- seeds/route_templates.json` y al reiniciar el backend `seed_route_templates()` (idempotente por slug, corre en startup, [adapters/api/main.py:256]) reinsertó las 20 en la tabla vacía. El usuario se molestó: "¿por qué están las 20 que borré?".

**How to apply:** NO restaurar un fichero que el usuario vació a propósito sin preguntar primero. Ante un fichero modificado/vaciado en el working tree, surface la discrepancia en vez de "arreglarla". El seed de route_templates debe quedarse `[]` salvo que el usuario diga lo contrario. Las plantillas del usuario viven solo en `travian_bot.db` (gitignored); no hay backup → si se borran, se recrean a mano. Relacionado: [[subagentes-off-script-commits-y-radar]], [[route-templates-developer-portal-feature]].
