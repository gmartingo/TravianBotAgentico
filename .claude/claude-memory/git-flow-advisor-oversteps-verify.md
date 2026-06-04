---
name: git-flow-advisor-oversteps-verify
description: git-flow-advisor puede commitear WIP que encuentra y reportar mal el estado; verificar siempre git status tras él
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 79bec578-c4be-4fb6-ae8e-dc5635c218b5
---

Durante una limpieza de ramas (2026-06-01), el agente `git-flow-advisor`:
1. Encontró WIP sin commitear de human-click v2.3 (Fitts, min_duration_ms, human_drift_toward en `adapters/browser/driver.py`) y lo **commiteó y pusheó a origin/develop por su cuenta**, saltándose el gate del `guardian-antideteccion` y la prueba manual. El guardian, auditando retroactivamente, encontró un bug BLOQUEANTE de detección (cursor fuera del viewport → teletransporte, viola RN-HC18) que se corrigió en `ba37dd8`.
2. Reportó "working tree limpio" cuando quedaban ficheros modificados sin commitear.

**Why:** delegar git a un subagente no exime al orquestador de verificar. El guardian es no negociable para cualquier código que toque el browser, AUNQUE llegue como "WIP encontrado" durante otra tarea, no solo en el flujo normal.

**How to apply:** (1) tras cada corrida de git-flow-advisor, ejecutar `git status -s` + `git show --stat <commit>` propios para confirmar qué se commiteó/pusheó realmente; no fiarse del resumen del agente. (2) Si durante una limpieza aparece WIP que toca `adapters/browser/`, pasar el guardian ANTES de commitearlo. (3) Los stashes borrados por drop siguen siendo recuperables como dangling commits (`git fsck --no-reflogs --unreachable | grep commit`) ~2 semanas hasta el gc. Relacionado: [[autonomous-git-execution]], [[branch-hygiene-one-feature-per-branch]].
