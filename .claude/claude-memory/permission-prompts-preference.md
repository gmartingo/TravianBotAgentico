---
name: permission-prompts-preference
description: El usuario detesta los prompts de permiso; quiere fricción mínima al editar
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 5508d649-e32a-4cdd-b0f6-5c1cfbad44ff
---

El usuario se frustra con los prompts de permiso ("me sigues pidiendo permiso para todo, arregla eso"). En este proyecto se fijó `permissions.defaultMode: "acceptEdits"` en `.claude/settings.json`, más allowlist de tests de Python (`Bash(.venv/bin/python tests/*)`, `pytest`). Rechazó permitir `curl` (doble uso) y el modo `bypassPermissions` total.

**Why:** Trabaja en la extensión de VSCode y las confirmaciones constantes le rompen el flujo.

**How to apply:** No proponer enfoques incrementales comando-a-comando cuando pide "deja de preguntar" — ir directo al lever global (`defaultMode`). Evitar acciones que disparen prompts innecesarios. Si vuelve a quejarse de prompts de Bash nuevos, ofrecer subir a `bypassPermissions`. No allowlistar intérpretes (`python3:*`) ni `curl:*` sin su OK explícito por el riesgo de ejecución arbitraria / mutación.
