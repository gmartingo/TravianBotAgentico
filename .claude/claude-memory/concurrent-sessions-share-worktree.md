---
name: concurrent-sessions-share-worktree
description: dos sesiones de Claude sobre el mismo repo comparten un único working tree → colisiones de rama/stash; NO es culpa de los subagentes
metadata: 
  node_type: memory
  type: project
  originSessionId: 9651a264-00ca-4a77-8440-cb70320c1e78
---

Si dos sesiones de Claude Code trabajan a la vez sobre el MISMO repositorio (`/Users/german/DEV/Travian con Agentes`), comparten **un único working tree de git**. Una sesión que cambia de rama o hace `git stash` se lleva por delante el trabajo sin commitear de la otra.

**Pasó (2026-06-05):** mientras esta sesión construía la feature [[radar-ataques-entrantes-feature]] en `feature/radar-ataques-entrantes`, otra sesión ("portal 2148", trabajando en `feature/route-templates-portal`) hizo stash del trabajo del radar y cambió de rama VARIAS veces. Esto se diagnosticó erróneamente al principio como "subagentes haciendo git off-script" — los subagentes eran inocentes; era la sesión concurrente. El trabajo nunca se perdió (quedó en stashes: `stash@{0}` "radar WIP #2", `stash@{1}` original contaminado con leftovers).

**Why:** git no aísla working trees por proceso; el índice y el directorio de trabajo son globales al repo.

**How to apply:** (1) No correr dos sesiones de Claude sobre el mismo working tree a la vez — usar `git worktree add` para una de ellas, o turnarse. (2) Si hay que convivir, **commitear pronto** el trabajo en su rama (un commit es durable; un stash/checkout de la otra sesión no lo toca). (3) Ante un working tree que "se vacía" o una rama que "salta" sola, mirar `git stash list` y el reflog ANTES de culpar a los subagentes. [[git-flow-advisor-oversteps-verify]]
