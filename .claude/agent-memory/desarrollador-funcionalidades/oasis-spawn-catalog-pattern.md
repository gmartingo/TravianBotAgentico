---
name: oasis-spawn-catalog-pattern
description: catálogo de spawn en core/game_data/; inferencia de tipo oasis; gap de cereal={1..10}; formato tab de múltiples animales en tests
metadata:
  type: project
---

## core/game_data/ — paquete de constantes de juego

`core/game_data/oasis_spawn_catalog.py` creado en oasis-spawn-mechanics-stats (2026-06-02).
Contiene `SPAWN_TIMER_S` (ordinal→segundos), `OASIS_TYPE_SETS` (4 tipos), `COOLDOWN_THRESHOLD_S`.
Regla: SPAWN_TIMER_S es la única fuente de verdad de timers; ningún otro módulo los hardcodea.

## Valores reales de defensa de animales (troop_stats.json, tribe=nature)

| Ordinal | Nombre     | def_infantry | def_cavalry |
|---------|-----------|-------------|------------|
| 1       | Rat        | 25          | 20         |
| 2       | Spider     | 35          | 40         |
| 3       | Serpent    | 40          | 60         |
| 4       | Bat        | 66          | 50         |
| 5       | Wild boar  | 70          | 33         |
| 6       | Wolf       | 80          | 70         |
| 7       | Bear       | 140         | 200        |
| 8       | Crocodile  | 380         | 240        |
| 9       | Tiger      | 170         | 250        |
| 10      | Elephant   | 440         | 520        |

## Gap de diseño — OASIS_TYPE_SETS["cereal"] = {1..10}

Con cereal abarcando todos los ordinales, en cuanto el oasis tiene 4+ animales distintos,
cereal siempre supera en score a cualquier tipo específico. Las anomalías solo ocurren
cuando el tipo gana por empate de score (exactamente los animales del set base de ese tipo).
Este gap debe revisarse con el analista (quizás cereal debería ser {8,9,10}).
Los tests de is_anomaly se resolvieron unitariamente sobre los helpers.

## Formato de reportes con múltiples animales en tests

El parser de Travian usa TABS para separar múltiples animales:
- Línea de nombres: "Rat\tSpider\tBat"
- Línea de presente: "3\t2\t1"
- Línea de matados: "3\t2\t1"

Con newlines NO funciona (el parser interpreta el primero y descarta el resto).
Patrón helper en tests: `_make_report(x, y, date_str, animals=[(name, present, killed), ...])`.

## Helpers del adaptador creados (ataque-oasis spawn)

En `adapters/db/attack_report_sqlite_adapter.py` (funciones de módulo, no métodos de clase):
- `_load_nature_defense_stats()` — carga troop_stats.json filtrando tribe=nature
- `_infer_type(observed, comp_list)` — heurística max-solapamiento con desempate por cardinal
- `_calc_elapsed_seconds(last_attack_str, utc_offset_str, computed_at)` — reutiliza _parse_utc_offset
- `_spawn_status(elapsed_s, tipo, oasis_type_sets, spawn_timer_s, cooldown_threshold_s)` — clasifica respawning/cooldown/unknown
- `_worst_case_count(ordinal, max_present, tipo, is_anomaly, timer_s, spawn_timer_s)` — cota superior peor caso

**Why:** cereal-gap hace que is_anomaly sea raramente True en integración; tests unitarios de helpers son la única forma de cubrir esos escenarios.
**How to apply:** cuando el analista actualice OASIS_TYPE_SETS["cereal"] a un subconjunto, los tests de integración de anomalía funcionarán automáticamente sin cambiar el código del adaptador.
