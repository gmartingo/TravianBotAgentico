---
name: feedback-no-gitignore-icons-graphify
description: "No añadir all_icons_dump.json ni archivos de graphify (.graphify_detect.json, .graphify_python) al .gitignore — el usuario quiere que estén trackeados"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: bdfde8de-e410-496e-a974-046baa766b55
---

No proponer nunca añadir `all_icons_dump.json` ni ningún artefacto de graphify (`.graphify_detect.json`, `.graphify_python`, etc.) al `.gitignore`.

**Why:** El usuario los considera parte del proyecto y quiere que estén trackeados en git. Lo dejó claro explícitamente cuando git-flow-advisor los propuso ignorar.

**How to apply:** Nunca sugerir `.gitignore` para estos ficheros, ni en commits, ni en revisiones de código, ni en ningún otro contexto.
