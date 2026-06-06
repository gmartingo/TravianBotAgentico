---
name: route-composability-pregame
description: Gate de entrada para rutas componibles (origen = otra plantilla). Motor y modelo de orígenes existentes mapeados, delta identificado. Verificado 2026-06-05.
metadata:
  type: project
---

## Feature: rutas componibles — "origen = otra plantilla"

**Why:** el usuario quiere encadenar rutas: C parte de B, B parte de A → ejecutar C = A→B→C.

**How to apply:** al analizar esta feature, reutilizar el patrón ORIGIN_PATHS + execute_path_test de navegación al ancla. El delta real es la resolución recursiva de plantillas y la FK auto-referente en route_template_paths/templates.

### Lo que existe (REUTILIZAR)

- `NavigationOrigin` + `ORIGIN_PATHS` (core/entities/noise.py:34-68): 9 valores incluyendo DORF1/DORF2/MAP/STATISTICS/ANY. Mapeo directo a URLs relativas.
- Motor de ancla en `execute_path_test` (world_agent.py:1483-1535): YA navega a la URL del origin antes de ejecutar pasos. Patrón exacto: resuelve origin→URL, llama `browser.get(anchor_url)`, luego ejecuta steps. Este es el "esqueleto" de la composición.
- Motor productivo en `_execute_noise_action` (world_agent.py:1057-1120): ejecuta steps en orden sin navegación previa (asume que el origin ya fue verificado por `_select_noise_action`). La navegación al ancla no existe aquí, solo en execute_path_test.
- `_select_noise_action` (world_agent.py:858-908): filtra paths cuyo origin casa con la URL actual (vía `_get_current_origin`). ANY siempre es compatible.
- `_get_current_origin` (world_agent.py:910-929): mapea URL actual a DORF1/DORF2/MAP/ANY. Solo 3 orígenes detectables; el resto devuelve ANY.
- `NoiseOriginSelector` (frontend/src/components/world/noise/NoiseOriginSelector.jsx): selector de 2 grupos — generic_origins (los 9 enums del EP-N12) + village_origins (VILLAGE_<data_id> dinámicos). Consume datos de EP-N12 + EP-N13.

### Lo que NO existe (CREAR)

- Campo `origin_template_id` (FK nullable a route_templates.id con ON DELETE SET NULL) en `route_templates` O en `route_template_paths`. No existe en ninguna tabla.
- Resolución recursiva: ninguna función resuelve "este origin es una plantilla → ejecutarla primero".
- Validación anti-ciclos: no hay grafo de dependencias, no hay chequeo de ciclos.
- El motor productivo (`_execute_noise_action`) NO tiene lógica de navegación al ancla — solo execute_path_test la tiene. Para que la composición funcione en producción, ese patrón debe migrar o replicarse.

### Relación semántica clave

`origin` en NavigationPath/RouteTemplatePath es HOY "desde dónde parte el path" = la URL a la que navegar antes de ejecutar los steps. La composición A→B→C usa exactamente esa semántica pero donde el "ancla" no es una URL sino la secuencia de pasos de otra plantilla. El modelo conceptual es coherente; la implementación es lo que falta.

### Nota anti-detección

`_execute_noise_action` y `execute_path_test` tocan el browser real de Travian. Cualquier extensión para encadenar plantillas (navegar por la ruta A antes de ejecutar B) pasa por esas funciones → guardian debe revisar antes del commit.

[[route-catalog-portal-pregame]]
