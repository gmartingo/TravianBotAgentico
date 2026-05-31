---
name: combat-simulator-pattern
description: Patrón de implementación del simulador/optimizador de combate Travian T4.5; clasificación inf/cav por tribu; get_building_defense_bonus; pymoo NSGA-II
metadata:
  type: project
---

## Motor de combate (combat_engine.py)

- Tablas estáticas en `_CAVALRY_ORDINALS`, `_RAM_ORDINALS`, `_CATAPULT_ORDINALS`, `WALL_GID_BY_TRIBE` por `Tribe`.
- ordinal 7 = ariet, ordinal 8 = catapulta para todas las tribus jugables T4.5 (verificado en kirilloid).
- `apply_smithy` es async porque llama a `GameDataPort.get_troop_upgrades`; devuelve `stat_value` del nivel efectivo.
- `simulate_combat` es la función pública async; retorna `CombatResult` dataclass.
- Cuando `D_efectiva == 0` → ratio = None (EC-01 del spec); cuando ratio >= 1.0 → atacante gana (EC-03 incluido).

## get_building_defense_bonus

Añadido a `GameDataPort` y `GameDataSQLiteAdapter` en 2026-05-29.
Lee `building_stats.effect_value` (entero porcentual de kirilloid, ej: 30 = 30%) y lo devuelve como float /100 (fracción decimal).
El llamador hace `D × (1 + bonus)` directamente.

## NATURE_DROPS

Dict estático en `core/use_cases/nature_animal_drops.py` (Opción B spec §RN-08).
Ordinal 1 (Rata) = 40/tipo confirmado; ordinales 2-10 son estimaciones pendientes verificación.

## Optimizador (combat_optimizer.py)

- pymoo instalado (versión 0.6.1.6). Para N<=5 tipos se usa muestreo (pasos 10%); para N>5 se activa NSGA-II.
- `_FALLBACK_MAX_N = 5` controla el umbral de cambio de estrategia.
- Cuando `has_winning_combination = False`, `defender_troops` debe mostrar los animales intactos (quantity_survived = quantity_initial). El optimizador inicializa la lista "intacta" y no la sobreescribe cuando no hay ganadoras.

## Router (combat.py)

- `morale` se valida con `ge=30` en Pydantic → valores < 30 dan 422 (no se clampean silenciosamente en la API).
- El clamping con warning sí existe en el motor para llamadas directas al use case.
- Los DTOs Pydantic de request/response usan `model_config = ConfigDict(extra="forbid")`.

## Tests

- `tests/unit/test_combat_engine.py`: 34 tests (todos unitarios con mocks de ports); `asyncio.run()` para ejecutar corutinas.
- `tests/test_combat_api.py`: 24 tests de integración con `TestClient(app)` y lifespan (BD real con seed).
- Resultado 2026-05-29: 58 passed (nuevos) + 850 passed suite completa (0 regresiones).
