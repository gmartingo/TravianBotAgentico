---
name: autonomous-git-execution
description: El usuario quiere que ejecute commit/merge de git de forma autónoma sin pedir permiso cuando ya autorizó la tarea
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 4c136408-7baf-420b-b568-76e033c7168a
---

El usuario pidió ejecutar commit + merge (feature/login → develop) "sin pedir permisos", apoyándose en que para eso configuraron el `settings.json` del proyecto. Solo quiere que me detenga si algo falla o un agente marca un problema.

**Why:** valora la ejecución fluida y ya da autorización explícita por adelantado; preguntar de nuevo es fricción innecesaria.

**How to apply:** cuando autorice explícitamente una secuencia de git (commit/push/merge), ejecútala directamente vía Bash (no hace falta git-flow-advisor salvo que lo pida). Aun así: hago el commit/merge local sin pedir permiso, pero el **push a GitHub requiere credenciales que no están configuradas** (no hay `gh` ni token en osxkeychain) — ese punto sí lo debe resolver el usuario. Relacionado: [[guardian-agent-not-invocable]].
