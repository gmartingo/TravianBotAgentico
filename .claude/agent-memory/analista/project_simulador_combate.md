---
name: project-simulador-combate
description: Decisiones de diseño del simulador/optimizador de combate Travian — spec en docs/specs/simulador-combate.md, estado draft (pendiente revalidación de API por correcciones breaking 2026-05-29)
metadata:
  type: project
---

Spec en `docs/specs/simulador-combate.md`. Estado actual: **`draft`** — pendiente de revisión v4 de `desarrollador-apis` por dos cambios breaking en el response (2026-05-29). Después de la revisión, volver a `ready-for-impl`.

**Why:** Se aplicaron dos correcciones del usuario (2026-05-29) que cambian contratos del response: (1) `resources_gained_from_animals` pasa de `integer` a objeto `{wood, clay, iron, crop, total}`; (2) default de `attack_type` cambia a `"raid"`. Ambas son breaking en el contrato del response.

**How to apply:** Antes de dar el spec al `desarrollador-funcionalidades`, lanzar `desarrollador-apis` en modo revisión de contrato para v4. Solo cuando dé luz verde, devolver el spec a `ready-for-impl` y `apis_validadas_por_desarrollador_apis: true`.

## Correcciones de la segunda ronda (usuario, 2026-05-28)

1. **`attack_type`** (`"attack"` | `"raid"`) — campo opcional con default `"raid"` (cambiado de `"attack"` en corrección de 2026-05-29). En raid, catapultas y arietes cuentan como tropa normal (sin daño estructural).
2. **Daño estructural activo** — catapultas destruyen niveles de edificios (`floor(hits / (level+1))`); arietes reducen el muro (`floor(rams × ram_attack / (wall_bonus × strong_buildings))`). Campos nuevos en request: `catapult_targets` y `rams`. Campo nuevo en response: `structural_damage` (nullable si raid o sin targets).
3. **Drops de animales por tipo de recurso** — confirmado por el usuario que los drops son por recurso (wood/clay/iron/crop), no un total único. Rata = 40/tipo (único valor exactamente confirmado). Ordinal 2..10 son estimaciones proporcionales pendientes de verificación. Estructura: `{wood, clay, iron, crop, total}` o `null` cuando no hay NATURE muerta. Dict en `core/use_cases/nature_animal_drops.py` con `{ordinal: {"wood": X, "clay": X, "iron": X, "crop": X}}`.
4. **Botín activo** — `potential_loot: null` reemplazado por objeto `loot: {capacity, potential, resources_gained_from_animals}`. Campo `carry` YA EXISTE en BD (verificado). `village_resources` es input opcional en `defenders[]`.
5. **Coste en recursos de bajas** — nuevo objeto `resource_losses: {attacker, defender}` con desglose por tropa. Campos `cost_wood/clay/iron/crop/sum` YA EXISTEN en BD (verificado). El criterio de optimización cambia de "minimizar unidades perdidas" a "minimizar `total_resource_losses`".

## Decisiones clave del diseño (consolidado)

- **Héroe**: dos componentes — `hero_attack_points` (suma a A_base) y `hero_attack_bonus_percent` (multiplicador). Igual para defensor.
- **Múltiples defensores**: lista `DefenderFormation`. D total = suma de todas. Muro aplica una sola vez.
- **Límite tropas defensoras**: 50 tipos totales entre todos los defensores.
- **Artefactos**: declarativos en MVP; solo afectan tiempo de marcha y crop, NO la fórmula A vs D. Excepción: `strong_buildings` afecta daño de arietes (`wall_damage`).
- **Optimizador Modo A vs Modo B**: mutuamente excluyentes.
- **Optimizador multi-objetivo**: frente de Pareto (pymoo NSGA-II). Criterio de optimización 2: `total_resource_losses` (recursos gastados en producir bajas, no conteo de unidades).
- **Bonus de muro**: desde `GameDataPort.get_building_defense_bonus(gid, level)`. Fallback `0.03×nivel` + warning.
- **FA-09 (cálculo inverso de botín)**: fuera del MVP, segunda iteración del optimizador.

## Verificaciones de BD (2026-05-28)

| Campo | Tabla | Resultado |
|---|---|---|
| `carry` | `troop_stats` | EXISTE — no requiere migración |
| `cost_wood/clay/iron/crop/sum` | `troop_stats` | EXISTEN — no requieren migración |
| `drop_wood/clay/iron/crop` | `troop_stats` | NO EXISTEN — decisión del implementador: 4 columnas BD (Opción A) u Opción B (dict estático, preferida) |

## Librería de optimización

Recomendada: **`pymoo`** (NSGA-II). Fallback: búsqueda por muestreo discreto (pasos 10%, N<=5 tipos, O(11^N)).

## Ubicaciones clave

- Spec: `docs/specs/simulador-combate.md`
- Drops de animales: `core/use_cases/nature_animal_drops.py` (dict `NATURE_DROPS`)
- Tabla `WALL_GID_BY_TRIBE`: en `core/use_cases/combat_engine.py` (dict estático)
- Tabla inf/cav/catapultas/arietes por tribu: en `core/use_cases/combat_engine.py` (dict estático)
- `GameDataPort.get_building_defense_bonus(gid, level)` y `get_building_stats(gid, level)`: verificar existencia en `core/ports/game_data_port.py`

[[project-arch-conventions]]
[[project-kirilloid-scraper]]
