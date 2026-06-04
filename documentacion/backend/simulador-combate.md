# Documentación de código — Simulador y Optimizador de combate

Módulos:
- `core/entities/combat.py` — entidades del dominio
- `core/use_cases/combat_engine.py` — motor de combate
- `core/use_cases/combat_optimizer.py` — optimizador multi-objetivo
- `core/use_cases/nature_animal_drops.py` — tabla de drops de animales NATURE
- `adapters/api/routes/combat.py` — endpoints REST

Specs: `docs/specs/simulador-combate.md`, `docs/specs/optimizador-balance-multiraid.md`
Diseño: `docs/design/simulador-combate-ui.md`
Doc de negocio: `documentacion/funcionalidades/simulador-combate.md`, `documentacion/funcionalidades/optimizador-balance-multiraid.md`

---

## Arquitectura del módulo

```
adapters/api/routes/combat.py
    ↓  valida con Pydantic, resuelve idioma con resolve_language
core/use_cases/combat_engine.simulate_combat()
    ↓  usa
core/ports/game_data_port.GameDataPort   (BD de tropas, edificios, upgrades)
core/ports/translation_port.TranslationPort  (nombres localizados)
core/use_cases/nature_animal_drops.py    (drops estáticos de animales)
    ↓  devuelve
core/entities/combat.CombatResult

adapters/api/routes/combat.py
    ↓  valida, resuelve idioma
core/use_cases/combat_optimizer.find_optimal_attack()
    ↓  evalúa candidatos llamando a simulate_combat()
    ↓  frente de Pareto / scoring ponderado
    ↓  devuelve
core/entities/combat.OptimizationResult
```

Toda la lógica del core es **pura salvo I/O de ports** — no hay efectos laterales ni estado global. Los ports se inyectan como parámetros.

---

## `core/entities/combat.py` — Entidades del dominio

Todas son `@dataclass` no persistidas. Solo existen en memoria durante el cálculo.

### Entidades de entrada

| Clase | Qué es |
|---|---|
| `TroopEntry` | Tropa con cantidad conocida (atacante o defensor) |
| `TroopTypeSpec` | Tipo de tropa sin cantidad — Modo A del optimizador |
| `TroopAvailability` | Tipo de tropa con cantidad máxima — Modo B/C del optimizador |
| `AttackerFormation` | Ejército atacante completo con todos sus modificadores |
| `DefenderFormation` | Un ejército defensor (puede haber varios en lista) |
| `WallConfig` | Configuración del muro del defensor |
| `CombatConfig` | Parámetros opcionales: `server_speed`, `distance_fields` |
| `AttackerArtifacts` | Multiplicadores de velocidad y consumo de crop |
| `DefenderArtifacts` | Multiplicadores de edificios y cranny (placeholders para v2) |
| `CatapultTarget` | Edificio objetivo de catapultas en modo "attack" |
| `RamSpec` | Arietes con nivel de herrería |
| `OptimizationConfig` | Config del optimizador: pesos, `top_n`, `scoring_mode`, `n_min`, `n_max` |
| `OptimizationWeights` | Pesos de los cuatro objetivos + `balance` |

### Entidades de resultado

| Clase | Qué es |
|---|---|
| `TroopResult` | Una tropa con su resultado: enviadas, supervivientes, bajas, nombre e icono |
| `CombatResult` | Resultado completo de un combate: ganador, tropas, botín, pérdidas, daño estructural |
| `Loot` | Botín: capacidad de carga, potencial y recursos de animales muertos |
| `AnimalResourceDrop` | Drops por recurso (wood/clay/iron/crop/total) de animales NATURE muertos |
| `ResourceLosses` / `ResourceLossesBand` | Coste en recursos de las bajas de cada bando |
| `TroopResourceLoss` | Desglose de coste por tipo de tropa perdida |
| `StructuralDamage` | Daño de catapultas a edificios y de arietes al muro (solo en modo "attack") |
| `CatapultResult` | Resultado de catapultas en un edificio: nivel antes/después, hits |
| `OptimizationResult` | Resultado del optimizador: lista de alternativas + flag `has_winning_combination` |
| `OptimizationAlternative` | Una alternativa Pareto: tropas, métricas y campos multi-raid opcionales |
| `MultiRaidAggregate` | Totales acumulados de N raids idénticas |

---

## `core/use_cases/combat_engine.py`

### `compute_k(total_units: int) -> float`

**Qué hace**: calcula el exponente K de la fórmula de bajas de Travian T4.5.

**Fórmula** (verificada contra kirilloid):
- N ≤ 1000: K = 1.5
- N > 1000: K = 2 × (1.8592 − N^0.015), rango [1.2578, 1.5]

**Por qué existe**: K es el "involved factor" que regula qué tan devastadora es la ventaja del ganador. Batallas pequeñas (N ≤ 1000) tienen K máximo — el perdedor sufre más. Batallas masivas suavizan la diferencia. No es configurable por el usuario; se deriva siempre del tamaño real del campo.

**Impacto**: Sin K correcto, las predicciones de bajas serían erróneas. El spec en versiones anteriores permitía que el usuario lo configurara, pero se eliminó tras verificar que Travian lo calcula internamente.

---

### `apply_smithy(base_stat, tribe, ordinal, smithy_level, game_data_port, warnings, stat) -> float`

**Qué hace**: aplica el modificador de nivel de herrería sobre un stat base consultando `troop_upgrades` en BD.

**Por qué existe**: en Travian, la herrería mejora los stats de las tropas nivel a nivel. El valor en `troop_upgrades` es el stat absoluto mejorado (no un delta), por lo que la función simplemente busca la fila correspondiente. Si el nivel pedido supera el máximo disponible en BD, lo clampea con warning. Si no hay datos de upgrades, devuelve el stat base sin modificar.

**Impacto de negocio**: sin este modificador, el simulador subestimaría la fuerza de tropas entrenadas en una herrería avanzada, produciendo predicciones de bajas incorrectas.

---

### `resolve_wall_multiplier(wall: WallConfig, game_data_port, warnings) -> float`

**Qué hace**: calcula el multiplicador combinado de muro y stonemason usando `GameDataPort.get_building_defense_bonus(wall_gid, level)`.

**Por qué existe**: cada tribu tiene su propio edificio de muro con valores de bonus distintos por nivel. Sin este multiplicador, los ataques a aldeas con muro alto tendrían resultados erróneos. El fallback `nivel × 3%` existe para las tribus cuyos gids de muro aún no están mapeados (Huns, Spartans, Vikings) y para cuando el usuario no especifica `wall_tribe`.

**Impacto de negocio**: el muro romano (City Wall) llega a dar bonuses de defensa de más del 100% en nivel 20. No modelarlo correctamente hace que el simulador dé resultados completamente erróneos para aldeas bien defendidas.

---

### `simulate_combat(attacker, defenders, wall, config, lang, game_data_port, translation_port) -> CombatResult`

**Qué hace**: ejecuta el cálculo completo de un combate Travian T4.5. Función principal del módulo.

**Flujo interno**:
1. Carga stats de tropas del atacante desde BD + aplica smithy → `A_base`.
2. Aplica héroe, alianza, moral → `A_efectivo`.
3. Calcula proporción caballería del atacante (para mezclar `def_inf` y `def_cav` del defensor).
4. Carga stats de todas las formaciones defensoras + aplica smithy → `D_base`.
5. Aplica héroe defensor (promedio de bonus), muro y stonemason → `D_efectiva`.
6. Calcula K según total de unidades en el campo.
7. Determina el ganador (ratio ≥ 1 → atacante).
8. Calcula supervivientes según la variante de bajas (raid vs attack).
9. Aplica la regla de "mínimo 1 superviviente" para el ganador.
10. Calcula botín, coste de bajas, daño estructural (si attack) y consumo de crop.
11. Resuelve nombres e iconos de todas las tropas via `TranslationPort` + `GameDataPort`.

**Por qué existe**: centraliza toda la lógica de combate en una sola función pura (asíncrona por los I/O de ports). Es reutilizada tanto por el simulador como por cada evaluación del optimizador.

**Impacto de negocio**: soporta la funcionalidad central del simulador. Sin ella, el bot no puede predecir resultados de combate.

**Detalles no obvios**:
- `ratio` es `None` cuando la defensa es 0 (EC-01 — oasis vacío). La UI lo presenta como "Victoria sin combate".
- En modo "raid", el perdedor también puede tener supervivientes (reparto proporcional).
- El daño estructural se calcula DESPUÉS del combate de tropas, con los supervivientes.
- `loot_potential` solo se calcula si el atacante gana Y se proporcionó `village_resources`.

---

## `core/use_cases/nature_animal_drops.py`

### `NATURE_DROPS: dict[int, dict[str, int]]`

**Qué es**: dict estático indexado por ordinal NATURE (1..10) con los recursos obtenidos al matar ese animal, desglosados por tipo.

**Por qué es un dict y no BD**: los valores de drops no se pudieron scrapear de kirilloid (campo no disponible en la fuente). Se eligió la Opción B del spec (dict estático) para no añadir columnas a `troop_stats` sin datos verificados para las 10 tropas.

**Estado de verificación**: ordinales 1–8 confirmados con reportes de batalla reales (2026-05-29). Ordinales 9 (Tigre=240) y 10 (Elefante=300) son estimaciones pendientes de confirmar.

### `get_nature_drop(ordinal: int, resource: str) -> int`

Devuelve el drop de un recurso concreto para un ordinal. Retorna 0 si el ordinal o el recurso no existen.

---

## `core/use_cases/combat_optimizer.py`

### `_dominates(a, b) -> bool`

**Qué hace**: comprueba si la solución `a` domina a `b` en el espacio de cuatro objetivos (todos a minimizar). `a` domina `b` si es mejor o igual en todos y estrictamente mejor en al menos uno.

**Por qué existe**: define la relación de dominancia del frente de Pareto. Es la pieza matemática central del optimizador multi-objetivo.

---

### `_compute_pareto_front(candidates) -> list[dict]`

**Qué hace**: filtra la lista de candidatos devolviendo solo los no dominados (el frente de Pareto).

**Por qué existe**: de entre todas las combinaciones evaluadas, el frente de Pareto son las "mejores" según cualquier combinación de pesos. El usuario elige cuál le interesa ajustando los sliders.

---

### `_balance_score(ev, available_map) -> float`

**Qué hace**: mide el desequilibrio en el uso del inventario calculando la desviación estándar de los ratios `enviadas_i / disponibles_i` para los tipos de tropa activos.

**Por qué existe**: sin penalización de balance, el optimizador tendería a usar masivamente el tipo de tropa más eficiente e ignorar el resto. Esto es subóptimo para el Modo C (multi-raid) porque vacía un tipo de tropa mucho más rápido que otros, dejando sobrantes inutilizables.

**Detalle**: retorna 0.0 para ≤ 1 tipo activo (no hay stdev definida). La función usa `ev["troop_entries"]` (cantidades enviadas antes del combate), no `ev["troops_sent"]` (post-combate con bajas). Ver divergencias en doc de negocio.

---

### `_optimize_by_sampling(troop_specs, max_quantities, ...) -> list[dict]`

**Qué hace**: busca combinaciones de tropas en tres fases:
1. **Fase gruesa** (~10% de la escala por tipo): detecta la región general donde hay victorias.
2. **Fase fina** (paso 1, adaptativo): explora ejércitos pequeños para encontrar la combinación mínima ganadora.
3. **Fase dirigida** (solo Modo C con `n_min`/`n_max`): genera candidatos específicos con N en el rango pedido.

Tiene un hard cap de 30.000 combinaciones.

**Por qué existe**: fallback cuando pymoo no está disponible o cuando N ≤ 5 tipos de tropas. Para la mayoría de casos de uso real (2–4 tipos de tropas para farmear oasis), el muestreo es suficientemente exhaustivo.

---

### `find_optimal_attack(attacker_tribe, troop_types, village_troops, ...) -> OptimizationResult`

**Qué hace**: función principal del optimizador. Orquesta la búsqueda (pymoo o muestreo), construye el frente de Pareto, ordena por score ponderado y decora las alternativas ganadoras con los campos multi-raid (`raids_possible`, `remaining_troops`, `aggregate`).

**Por qué existe**: encapsula toda la lógica de optimización. Acepta dos modos de entrada (tipos libres o inventario acotado) y siempre devuelve alternativas aunque ninguna gane.

**Detalles de la decoración multi-raid** (solo si `village_troops is not None`):
- `raids_possible = min_i floor(available_i / sent_i)` — cuántas veces se puede repetir la oleada.
- `remaining_troops` — cuántas tropas de cada tipo quedan tras `raids_possible` oleadas.
- `aggregate` — totales acumulados: drops × N, pérdidas × N, tropas enviadas × N.

---

## `adapters/api/routes/combat.py`

### `POST /combat/simulate`

**Request**: `AttackerRequest` + `list[DefenderRequest]` + `WallRequest` + `CombatConfigRequest`. `attack_type` default = `"raid"`.

**Respuesta**: `CombatResultResponse` (200) o 400 (idioma) o 422 (validación).

**Política de idioma**: `resolve_language` (precedencia `?lang=` > `Accept-Language` > error 400). El idioma es obligatorio porque la respuesta incluye nombres de tropas localizados.

**Cache**: `Cache-Control: no-store` en todas las respuestas (el resultado depende de parámetros de entrada volátiles).

### `POST /combat/optimize`

**Request**: `OptimizeRequest` con `troop_types` (Modo A) XOR `village_troops` (Modo B/C). Si se envían los dos → 422. `optimization_weights.balance` (default 0.0) y `scoring_mode` (default "single") son los campos añadidos por el spec de balance multiraid.

**Respuesta**: `OptimizationResultResponse` (200). Siempre devuelve alternativas — nunca lista vacía.

---

## Referencia de funciones → `documentacion/backend/referencia-funciones/`

Ver `documentacion/backend/referencia-funciones/combat-engine.md` (pendiente de crear) para la referencia rápida de funciones.

---

## Tests

Los tests del módulo están en `tests/unit/test_combat_optimizer.py` (10 tests unitarios del optimizador) y tests de integración del simulador. Suite completa: 911 passed, 23 skipped (2026-05-29).

🔖 Última revisión: 2026-06-04
