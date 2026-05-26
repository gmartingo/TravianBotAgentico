---
name: resources-block-pattern
description: Patrón del bloque RESOURCES — use case llama al parser internamente (diferente de overview donde el handler llama al parser)
metadata:
  type: project
---

El bloque RESOURCES (lectura-resources.md) tiene una diferencia arquitectónica respecto al bloque OVERVIEW:

- **OVERVIEW**: el handler (game_overview.py) llama a `OverviewParser.extract_overview_data(html)` directamente, y el use case recibe datos ya parseados.
- **RESOURCES**: el use case (`ResourcesUseCase.execute`) recibe el port y llama al `ResourcesParser` internamente (3 llamadas: parse_stored, parse_production, parse_capacity).

Esto implica que el use case de resources **importa desde `adapters/browser/parsers/`**, lo cual rompe la pureza hexagonal estricta pero está explícitamente indicado en el spec (sección 9.2) y se acepta por diseño.

**Why:** El spec justifica este diseño porque las 3 páginas se agregan en 1 endpoint; el use case orquesta la secuencia completa (port → parse → port → parse → port → parse → enriquecer → DTO).

**How to apply:** Cuando el coordinador pida implementar los bloques TROOPS y CULTURE-POINTS, verificar el spec de cada bloque — pueden seguir el patrón overview (parser en handler) o el patrón resources (parser en use case).

**Valores de los fixtures (resources, ts20.x2.america.travian.com, 6 aldeas Galos):**
- game_ids: [19040, 24341, 25306, 25875, 26421, 24498]
- stored_totals: wood=53682, clay=72335, iron=76682, crop=309069, merchants free=37/total=40
- production_totals: wood=11171, clay=12862, iron=10700, crop=64163, total_all=98896
- capacity_totals: warehouse=274700, granary=498200
- Aldea 26421: la pequeña (merchants 0/0, warehouse=7800, granary=5000)

Relacionado con: [[overview-trunk-pattern]]
