# Referencia de funciones — Motor de combate y Optimizador

Módulos: `core/use_cases/combat_engine.py`, `core/use_cases/combat_optimizer.py`, `core/use_cases/nature_animal_drops.py`
Doc completo: `documentacion/backend/simulador-combate.md`

---

## `combat_engine.py`

### `compute_k(total_units: int) -> float`

Calcula el exponente K (involved factor) de Travian T4.5.
- N ≤ 1000 → 1.5
- N > 1000 → 2 × (1.8592 − N^0.015), rango [1.2578, 1.5]

---

### `apply_smithy(base_stat, tribe, ordinal, smithy_level, game_data_port, warnings, stat, server_version) -> float`

Aplica el nivel de herrería sobre un stat base consultando `troop_upgrades` en BD. Clampea al máximo disponible si el nivel pedido supera el techo en BD.

---

### `is_cavalry(tribe, ordinal) -> bool`

True si la tropa es caballería para la tribu dada. Usa `_CAVALRY_ORDINALS`.

---

### `is_infantry(tribe, ordinal) -> bool`

True si la tropa es infantería (todo lo que no es caballería).

---

### `is_ram(tribe, ordinal) -> bool`

True si la tropa es un ariet para la tribu dada. Ordinal 7 en todas las tribus jugables T4.5.

---

### `is_catapult(tribe, ordinal) -> bool`

True si la tropa es una catapulta. Ordinal 8 en todas las tribus jugables T4.5.

---

### `resolve_wall_multiplier(wall: WallConfig, game_data_port, warnings) -> float`

Calcula `(1 + bonus_muro) × (1 + 0.05 × nivel_stonemason)`. Usa `GameDataPort.get_building_defense_bonus(wall_gid, level)` o fallback `nivel × 0.03` con warning.

---

### `build_troop_results(enriched, survived, lang, translation_port, game_data_port) -> list[TroopResult]`

Construye la lista de `TroopResult` con nombres localizados e iconos a partir de las listas internas de tropas enriquecidas y sus supervivientes.

---

### `simulate_combat(attacker, defenders, wall, config, lang, game_data_port, translation_port, server_version) -> CombatResult`

Función principal. Simula un combate completo según fórmula Travian T4.5. Ver `documentacion/backend/simulador-combate.md` para el flujo de 11 pasos.

**Parámetros**:

| Parámetro | Tipo | Descripción |
|---|---|---|
| `attacker` | `AttackerFormation` | Ejército atacante completo |
| `defenders` | `list[DefenderFormation]` | Lista de formaciones defensoras (mínimo 1) |
| `wall` | `WallConfig` | Configuración del muro |
| `config` | `CombatConfig` | Server speed y distancia opcionales |
| `lang` | `str` | Código de idioma (de `SUPPORTED_LANGUAGES`) para nombres de tropas |
| `game_data_port` | `GameDataPort` | Puerto a la BD de datos del juego |
| `translation_port` | `TranslationPort` | Puerto a las traducciones de nombres |

**Retorna**: `CombatResult` con todos los campos o eleva `ValueError` si una tropa no tiene datos en BD.

---

## `nature_animal_drops.py`

### `NATURE_DROPS: dict[int, dict[str, int]]`

Dict estático `{ordinal → {wood, clay, iron, crop}}` para las 10 tropas NATURE (ordinales 1–10). Ordinales 1–8 confirmados con reportes reales. Ordinales 9–10 estimados.

---

### `get_nature_drop(ordinal: int, resource: str) -> int`

Devuelve el drop de un recurso para un animal NATURE. Retorna 0 si ordinal o recurso no existen.

---

## `combat_optimizer.py`

### `_dominates(a, b) -> bool`

True si `a` domina a `b` en los 4 objetivos (todos a minimizar): `neg_resources`, `total_resource_losses`, `troops_sent_count`, `travel_time_h`.

---

### `_compute_pareto_front(candidates) -> list[dict]`

Devuelve el subconjunto de candidatos no dominados por ningún otro.

---

### `_balance_score(ev, available_map) -> float`

Desviación estándar de `sent_i / available_i` para tipos activos. 0.0 si ≤ 1 tipo activo.

---

### `_compute_n_natural(ev, available_map) -> int | None`

N natural = `min_i floor(available_i / sent_i)` para tipos con `sent_i > 0`. None si no hay inventario. 0 si algún tipo enviado no está en el inventario.

---

### `_optimize_by_sampling(troop_specs, max_quantities, ..., n_min, n_max) -> list[dict]`

Búsqueda por muestreo en tres fases (gruesa + fina + dirigida por rango N). Hard cap: 30.000 combinaciones. Cada combinación se evalúa con `_evaluate_combination` que llama a `simulate_combat`.

---

### `find_optimal_attack(attacker_tribe, troop_types, village_troops, ...) -> OptimizationResult`

Función principal del optimizador. Orquesta pymoo o muestreo, construye frente Pareto, ordena por score ponderado y decora con campos multi-raid.

**Parámetros principales**:

| Parámetro | Tipo | Modo |
|---|---|---|
| `troop_types` | `list[TroopTypeSpec] \| None` | Modo A (sin cantidad) |
| `village_troops` | `list[TroopAvailability] \| None` | Modo B/C (con inventario) |
| `oasis_defenders` | `list[TroopEntry]` | Defensa del oasis (NATURE) |
| `opt_config` | `OptimizationConfig` | Pesos, top_n, scoring_mode, n_min, n_max |

**Retorna**: `OptimizationResult` siempre no vacío. `has_winning_combination=False` si ninguna alternativa gana.

🔖 Última revisión: 2026-06-04
