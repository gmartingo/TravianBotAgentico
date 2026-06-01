---
name: features-split-across-unmerged-branches
description: "calculadora de combate y reportes-oasis viven en ramas distintas sin mergear a develop; causó que \"desaparecieran\" del frontend"
metadata: 
  node_type: memory
  type: project
  originSessionId: 91652a9a-96ec-40be-bfe5-34103c0d92cf
---

Al 2026-05-31, tres features están repartidas en ramas y NINGUNA está en `develop`, lo que provocó que la "Calculadora" y los "Reportes/Análisis de oasis" desaparecieran del sidebar al cambiar de rama:

- **Calculadora de combate** (Simulador): componentes `frontend/src/components/combat/{ArmyPanel,CombatCalculator,CombatResult,OptimizerPanel,OptimizerResult,TribeBar,TroopGrid}.jsx`, claves i18n `calc.*` (143), `client.js` `api.combat.{simulate,optimize}`, y el backend `adapters/api/routes/combat.py` + `core/use_cases/{combat_engine,combat_optimizer}.py` → todo en la rama **`feature/optimizador-balance-multiraid`** (commit de wiring `4bf32cc`). Hay además un `git stash` WIP sobre esa rama.
- **Reportes de oasis** (`AttackReportsPage` + `components/attack-reports/*`): ficheros **untracked** en el árbol de trabajo; su backend (`attack_reports_router`) SÍ está registrado en `main.py` de las ramas actuales.
- **Human sessions**: rama `feature/human-sessions` (la activa cuando pasó esto).

**Why:** al hacer checkout de `feature/optimizador-...` a `develop`/`feature/human-sessions`, los ficheros committeados del calculador volvieron a la versión sin ellos (desaparecieron del front); los untracked de oasis se quedaron porque git no los toca. Es el patrón de [[branch-hygiene-one-feature-per-branch]].

**How to apply:** El 2026-05-31 se restauró TODO en `feature/human-sessions` (el usuario dijo "hazlo"), sin commitear (pendiente prueba manual + git-flow-advisor):
- Front: wiring de `4bf32cc` (App.jsx rutas `/calculadora` + `/reportes-oasis`, Sidebar entradas, i18n `nav.attackReports` + bloque `calc.*` contiguo de es/en — OJO: extraer el bloque calc por RANGO contiguo, no por `grep '\''calc.'\''` línea a línea, porque hay valores multilínea) + 7 componentes `combat/*.jsx` vía `git checkout`.
- Backend `/combat`: traídos `adapters/api/routes/combat.py`, `core/entities/combat.py`, `core/use_cases/{combat_engine,combat_optimizer,nature_animal_drops}.py`, registrado `combat_router` en `main.py`. El motor depende de `GameDataPort.get_building_defense_bonus` (método añadido en la rama optimizador, traído también en `core/ports/game_data_port.py` + `adapters/db/game_data_sqlite_adapter.py` — diff puramente aditivo). Tests `tests/test_combat_api.py` + `tests/unit/test_combat_engine.py` traídos.
- Verificado: build Vite OK; 86 tests de combate verdes; suite completa 1081 passed, 2 failed (login/session de human-sessions, NO relacionados), 23 skipped.

Esto injertó casi toda la feature optimizador en human-sessions (viola higiene de ramas). La solución limpia sigue siendo mergear `feature/optimizador-balance-multiraid` a develop y commitear oasis en su rama; gestionar la reorganización con git-flow-advisor.
