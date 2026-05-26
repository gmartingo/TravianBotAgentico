---
name: documentador-prefer-editing
description: "el documentador debe editar/ampliar docs existentes por caso de uso, no crear ficheros nuevos por defecto"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 3cb63abf-740c-4663-91de-fe22727bffcb
---

Al invocar el agente `documentador`, NO debe crear ficheros nuevos por defecto. Debe organizar la documentación **por casos de uso** y, antes de crear nada, **buscar el documento existente** que cubra esa área y **editarlo/ampliarlo**. Solo crear un fichero nuevo si no existe ya un documento del caso de uso pertinente.

**Why:** el usuario no quiere proliferación de ficheros sueltos; prefiere documentos vivos que crecen y se modifican, agrupados por caso de uso, para mantener la doc cohesionada y navegable.

**How to apply:** en cada prompt al `documentador`, incluir la instrucción explícita de "preferir editar/ampliar documentos existentes; localizar primero el doc del caso de uso y modificarlo; crear fichero nuevo solo si no existe". Relacionado con la disciplina de `documentacion/MANTENIMIENTO.md` y la marca de agua 🔖.
