---
name: multiraid-optimizer-pattern
description: Patrón de decoración multi-raid en el optimizador; balance_score; rama base vs rama feature
metadata:
  type: project
---

## Patrón multi-raid (feature/optimizador-balance-multiraid)

### Relación de ramas
`feature/optimizador-balance-multiraid` parte de `develop`, pero los ficheros del simulador (combat.py, combat_optimizer.py, routes/combat.py) solo existen en `feature/simulador-combate`. Al implementar hay que hacer `git merge feature/simulador-combate --no-commit --no-ff` primero para tener los ficheros base. El merge fue limpio (sin conflictos).

### _balance_score
- Vive en `core/use_cases/combat_optimizer.py`
- Usa `ev["troop_entries"]` (lista de TroopEntry con .tribe/.ordinal/.quantity), NO ev["troops_sent"]
- available_map clave: `(tribe, ordinal)` → quantity_available
- Retorna 0.0 si len(ratios) <= 1 (single-type o sin inventario)

### Decoración multi-raid
- Se aplica a TODAS las alternativas cuando `village_troops is not None` (ganadoras y perdedoras)
- raids_possible = min(avail // sent) para tipos con sent > 0
- Para alternativas perdedoras: aggregate.total_resources_gained.total = 0 (oleada_drop es None)
- available_map se construye antes del bloque de Pareto, reutilizado en _score y en decoración

### Frontend: propagación de inputMode
- `OptimizerPanel` tiene estado local `inputMode` + notifica al padre vía `onInputModeChange` prop
- `CombatCalculator` guarda `optimizerInputMode` y lo pasa a `OptimizerResult` como prop `inputMode`
- `OptimizerResult` pasa `inputMode` a `DetailPanel` → renderiza `MultiRaidBlock` condicionalmente

### Preset Modo C
- Se aplica SOLO si `weightsUserTouched === false` al entrar a Modo C
- Cualquier cambio manual en sliders previo a entrar a Modo C preserva los valores del usuario

**Why:** La rama feature/optimizador-balance-multiraid se creó desde develop (sin el simulador), por eso el merge es necesario como paso 0 de implementación.
**How to apply:** En futuras features que extiendan el optimizador: verificar primero qué rama tiene los ficheros base y hacer merge limpio si es necesario.
