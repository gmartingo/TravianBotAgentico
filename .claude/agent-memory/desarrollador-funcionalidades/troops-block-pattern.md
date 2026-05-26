---
name: troops-block-pattern
description: Bloque TROOPS implementado — patrones del parser, use case y router para las 5 sub-pestañas
metadata:
  type: project
---

Bloque TROOPS (`lectura-troops.md`) implementado en 2026-05-26.

**Por qué:** Las 5 sub-pestañas de `/village/statistics/troops` (own/support/smithy/hospital/training) exponen el estado completo de tropas del jugador. Cada una tiene una estructura HTML distinta pero todas usan el tronco OverviewHtmlSourcePort.

**Patrones clave:**

- `TroopsParser` en `adapters/browser/parsers/troops_parser.py` — 5 `@staticmethod`. El parser NO llama a translation_port; devuelve `troop_types: list[str]` y `buildings=[]`/`troop_names={}` vacíos. El use case los enriquece.
- `TroopsUseCase` en `core/use_cases/troops_use_case.py` — importa `TroopsParser` (desviación hexagonal menor aceptada, alineada con `game_overview.py`).
- Router en `adapters/api/routes/game_troops.py` — `prefix="/game/troops"`, 5 endpoints. El coordinador registra el router en `main.py` (el agente NO lo toca).
- `_resolve_troop_name` — función compartida en use case: `unit_class_to_tribe_ordinal` + `get_troop_name` + fallback a `unit_class`. Misma función que en overview_use_case.

**Estructuras HTML observadas en fixtures:**
- `own`: `table#troops` — thead usa `td.unit` (no `th.unit`); filas con `td.villageName`; tr.sum con `td.vil`.
- `support`: `div.troops_wrapper > table.vil_troops` — `tbody.troops` con pares (iconos, cantidades); `tbody.upkeep` con `div.consumption span` + `div.inlineIcon.strength`.
- `smithy`/`hospital`/`training`: `table.under_progress`. Smithy thead segunda fila `th.unit`; hospital `th.villageName > i.tribe3_medium`; training `th.unit > i.building_small.tribeN.typeNN`.
- En training los gids se leen del `a[href*='gid=']` de la primera fila de datos, con fallback a `typeNN` del thead cuando la primera fila tiene `span.none`.

**Valores de fixtures de las 6 aldeas (game_ids):**
`[19040, 24341, 25306, 25875, 26421, 24498]`

**How to apply:** Usar como referencia al implementar bloque 4 (overview con troops) o cualquier bloque que use `table.under_progress`.
