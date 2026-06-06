---
name: stats-overview-direct-url-debt
description: deuda anti-detección — la lectura de estadísticas/overview navega por URL directa sin clicks humanos; cambiar cuando esté el sistema de rutas in-game
metadata: 
  node_type: memory
  type: project
  originSessionId: 3ed298aa-2c8b-4f57-84ee-970ad92e4b07
---

La recolección de estadísticas/overview en `adapters/browser/live_overview_adapter.py` navega por **URL directa** (`browser.get(url)` en `_navigate_and_get`, línea ~214) a 10 páginas profundas de `village/statistics/...` (overview, resources, resources/production, resources/capacity, culturepoints, troops/own|support|smithy|hospital|training — ver `_PAGE_PATHS` líneas 61-72). Única defensa: `human_delay(500, 900)`. **NO usa `human_click`** para llegar a las páginas, a diferencia del resto del proyecto (ruido en `world_agent.py` y farm lists sí navegan con clicks humanos por menús).

**Why:** Es la pieza con peor higiene anti-detección del proyecto. Riesgos: (1) aterrizar en URLs profundas sin Referer ni secuencia de navegación interna que genera un humano; (2) "barrido" si se piden varias de las 10 páginas seguidas separadas solo 0.5-0.9s (ningún humano abre 10 pestañas de stats en ~8s); (3) rompe el patrón humano del resto del bot. Mitigado parcialmente por caché TTL 60s + lock por página.

**How to apply:** El usuario (2026-06-05) decidió NO tocarlo de momento porque está construyendo en otro agente un **sistema de rutas dentro de Travian** (navegación in-game por clicks). Cuando ese sistema esté listo, migrar la recolección de estadísticas para que llegue a esas páginas vía clicks humanos por menús (o, como mínimo, limitar el barrido y subir los delays a tiempos de lectura humanos). Flujo: palantir → analista → guardian-antideteccion antes de implementar. Relacionado: [[travian-lectura-overview-endpoints]].
