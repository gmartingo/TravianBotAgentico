---
name: patterns-combat-calculator
description: S11 CombatCalculator: estructura de componentes, estado, contrato API, huecos conocidos
metadata:
  type: project
---

# Calculadora de combate (S11)

Implementada en `frontend/src/components/combat/`. Pestaña "Calculadora" habilitada en `WorldSpacePage.jsx`.

## Estructura de componentes

```
CombatCalculator.jsx   — raíz, estado global, llama a api.combat.simulate
  ArmyPanel.jsx        — reutilizable (role: attacker | defender | reinforcement)
    TribeBar.jsx       — avatares circulares (44px táctil), role=radiogroup
    TroopGrid.jsx      — 3 filas: icono 24px + input qty (52px) + input smithy
  CombatResult.jsx     — tabla de resultado, botín, pérdidas, warnings
```

## Estado del CombatCalculator

- `atkTribe`, `atkTroopValues`, `atkType`, `atkAllianceBonus`, `atkArtifact`, `atkHeroPoints`, `atkHeroBonusPct`
- `defState` — objeto { tribe, troopValues, wallLevel, stonemasonLevel, allianceBonus, heroDefPoints, heroDefBonusPct }
- `reinforcements` — array de defState con id único adicional
- Caché de tropas por tribu: `troopsCache` (variable de módulo en CombatCalculator.jsx) + hook `useTribesTroops`

## Carga de iconos de tropas

Usa `api.getCatalogIcons({ icon_type: 'troop', tribe })` — ya existía en client.js.
Patrón idéntico al de FarmListDrawer.jsx (línea 926).
Las URLs se preprocesan: si no empiezan por 'http' se preprende `/api`.

## Contrato API de combate

```js
api.combat.simulate(body)  // POST /combat/simulate
api.combat.optimize(body)  // POST /combat/optimize
```

Body de simulate: `{ attacker: AttackerInput, defenders: DefenderInput[] }`
`AttackerInput`: tribe, attack_type, troops[{ordinal,quantity,smithy_level}], hero_attack_points, hero_attack_bonus_percent, alliance_bonus, fast_troops_multiplier, morale
`DefenderInput`: tribe, troops[{tribe,ordinal,quantity,smithy_level}], hero_defense_points, hero_defense_bonus_percent, wall_level, stonemason_level, alliance_bonus

Respuesta esperada: { winner: 'attacker'|'defender', combat_ratio, attacker: { troops, resource_losses }, defenders: [...], loot: { capacity, potential, animals }, warnings: [] }

## Huecos conocidos (API no implementada aún)

- `POST /combat/simulate` y `POST /combat/optimize` no existen en el backend todavía.
  El frontend llama a estos endpoints y muestra `showToast` con el error si fallan.
  El resultado anterior (si lo hubiera) permanece visible en pantalla.
  Pendiente: `desarrollador-apis` debe implementar ambos endpoints.

## i18n

Claves añadidas bajo prefijo `calc.*` en ES y EN (catálogos es.js y en.js).
Resto de idiomas hacen fallback automático al español.

## Decisiones de diseño

- NATURE como tribu defensor por defecto (oasis animals como primer caso de uso)
- TribeBar usa iniciales 2 letras (no flag ni imagen de tribu, que no existen aún)
- TroopGrid hace scroll horizontal en móvil (`overflow-x: auto`) sin romper el layout
- Tropas con qty=0 tienen opacity 0.45 — activación visual al escribir
- `troopsCache` es variable de módulo para no recargar entre renders
