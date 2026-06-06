---
name: route-templates-developer-portal-feature
description: "feature \"portal de desarrollador de rutas\" — catálogo maestro global de rutas sobre el subsistema de ruido; spec ready-for-impl, sin implementar aún"
metadata: 
  node_type: memory
  type: project
  originSessionId: 8e601f05-1f3a-46c3-8a7b-64fbae223be5
---

El usuario quiere un "portal de desarrollador de rutas": una pantalla global donde ÉL mapea a mano el catálogo de rutas navegables de Travian (~80%), y el usuario final solo clica "qué quiere hacer" para que el bot las recorra metiendo RUIDO (navegación humana de fondo anti-detección).

Hallazgo clave de palantir: el subsistema de "ruido" YA ES el catálogo de rutas (entidades `NoiseDestination`/`NavigationPath`/`NavigationStep` en [[travian-lectura-overview-endpoints]] vecindario, 4 tablas, 14 endpoints EP-N01..N14, motor en `world_agent.py`, UI en `frontend/src/components/world/noise/`). Lo único que faltaba: una capa de plantillas GLOBALES independientes de mundo.

Decisiones del usuario (2026-06-05): (1) catálogo maestro GLOBAL `route_templates` sin world_id + clonado a mundo; (2) mapeo MANUAL por formulario (reutiliza wizard + EP-N14 test + EP-N11 derive-selector), NO grabación en vivo; (3) uso final = selección de rutas + ruido de fondo con el motor de frequency_weight ya existente.

Spec: `docs/specs/route-templates-developer-portal.md`, estado `ready-for-impl`, `apis_validadas_por_desarrollador_apis: true`. Define entidad `RouteTemplate`/`RouteTemplatePath`, 3 tablas nuevas + migración M-RT01 (`template_id` en `noise_destinations`), 10 endpoints EP-RT01..RT10, re-sync explícito (instancias independientes), seed ~20 plantillas en `seeds/route_templates.json`, página global `/rutas` bajo `ManagementShell`.

ESTADO 2026-06-05: IMPLEMENTADO completo (backend Fase A + API Fase B + UI Fase C) y commiteado en la rama `feature/route-templates-portal` (commits 069fae7 + 3426235). 95/95 tests del portal en verde; mockup `frontend/mockups/rutas.playground.html` aprobado por el usuario. PENDIENTE: prueba manual del usuario (gate), y limpieza git (069fae7 es un commit "cajón de sastre" que mezcla portal + noise residual + reorg seeds + restos). Gap funcional menor: panel re-sync necesita un endpoint `GET /route-templates/{id}/instances` para badges fieles por mundo (no bloqueante).

**Why:** evita re-descubrir que el portal NO se construye de cero sino sobre el subsistema de ruido; y registra dónde quedó el trabajo (rama propia) y la deuda git/funcional pendiente.
**How to apply:** para retomar, `git checkout feature/route-templates-portal`. Respetar los 6 ajustes anti-duplicación de palantir ya aplicados. Limpiar el commit cajón-de-sastre con git-flow-advisor (+OK usuario). Ver [[subagentes-off-script-commits-y-radar]] (incidente de gobernanza de esta sesión) y [[branch-hygiene-one-feature-per-branch]].
