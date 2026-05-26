---
name: guardian-agent-not-invocable
description: El agente guardian-antideteccion existe como .md pero no es invocable como subagent_type en este harness
metadata: 
  node_type: memory
  type: project
  originSessionId: 4c136408-7baf-420b-b568-76e033c7168a
---

`CLAUDE.md` define un agente `guardian-antideteccion` (y su definición vive en `.claude/agents/guardian-antideteccion.md`), pero ese tipo NO está disponible como `subagent_type` en la herramienta Agent de este harness (devuelve "Agent type not found"). Los subagent_type disponibles son los genéricos (analista, palantir, desarrollador-*, git-flow-advisor, general-purpose, etc.).

**Workaround validado:** lanzar el agente `general-purpose` y en el prompt pedirle que lea y adopte `/Users/german/DEV/Travian con Agentes/.claude/agents/guardian-antideteccion.md` para aplicar sus criterios. Funcionó para auditar cambios de anti-detección.

Probablemente aplica igual a otros agentes custom del proyecto no listados como subagent_type. Verificar la lista de "Available agents" del error antes de asumir que un agente del `.claude/agents/` es invocable. Relacionado: [[autonomous-git-execution]].
