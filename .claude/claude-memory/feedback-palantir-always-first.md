---
name: feedback-palantir-always-first
description: "palantir SIEMPRE debe invocarse antes de cualquier tarea — sin excepciones, aunque el trabajo llegue ya especificado"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: cae7bea2-9d66-4712-952f-882536868b25
---

Invocar palantir ANTES de cualquier trabajo, sin excepción.

**Why:** El usuario lo exige explícitamente y con énfasis. Aunque la tarea llegue completamente especificada (código exacto incluido), palantir debe revisarla igualmente porque su misión va más allá de detectar duplicados: también audita si los cambios propuestos reutilizan infraestructura existente, siguen patrones establecidos o rompen la coherencia del mapa de código. Saltárselo aunque "parezca obvio" es un error de proceso inaceptable.

**How to apply:** Ante cualquier tarea —feature nueva, cambio de API, refactor, test, endpoint, serialización— el primer paso es SIEMPRE lanzar el agente `palantir` con `subagent_type: "palantir"`. Solo después proceder. No hay excepción por "la tarea ya viene especificada" ni por "parece trivial".
