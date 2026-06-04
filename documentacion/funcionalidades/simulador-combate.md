# Funcionalidad: Simulador de combate

Spec: `docs/specs/simulador-combate.md` (estado: `implemented`, 2026-05-29)
Diseño UI: `docs/design/simulador-combate-ui.md`
Doc de código: `documentacion/backend/simulador-combate.md`

---

## 1. Qué problema resuelve

En Travian, atacar un oasis o una aldea enemiga sin información supone perder tropas de forma inesperada. El usuario no puede ver de antemano el resultado del combate, así que tiende a sobre-enviar tropas por precaución (desperdicio) o bajo-enviar y perder la batalla.

El simulador de combate resuelve exactamente ese problema: permite al usuario introducir su ejército y la defensa del objetivo y calcular el resultado exacto — quién gana, cuántas tropas pierde cada bando y cuántos recursos obtiene — **antes de lanzar el ataque real**.

---

## 2. Actores

| Actor | Rol |
|---|---|
| Jugador | Opera la calculadora desde el dashboard para planificar ataques antes de ejecutarlos |
| API `/combat/simulate` | Calcula el resultado de combate en el backend usando la fórmula real de Travian T4.5 |
| Base de datos de juego | Fuente de stats de tropas (`troop_stats`, `troop_upgrades`, `buildings`) poblada por el scraper de kirilloid |

---

## 3. Reglas de negocio clave

### Modo de combate: saqueo vs ataque normal

El campo `attack_type` cambia radicalmente el comportamiento de las bajas:

- **Saqueo (`"raid"`)** — ambos bandos sobreviven proporcionalmente. El ganador pierde `x / (1+x)` de sus tropas. Catapultas y arietes cuentan como tropa normal (sin daño estructural). Es el modo por defecto porque el caso de uso principal es farmear oasis.
- **Ataque normal (`"attack"`)** — el perdedor es aniquilado al 100%. Las catapultas destruyen niveles de edificios y los arietes reducen el muro. Este modo es para asedios PvP o destrucción de infraestructura.

### Modificadores aplicados a la fuerza atacante

1. Nivel de smithy por tropa (tabla `troop_upgrades` en BD).
2. Puntos de ataque y bonus porcentual del héroe.
3. Bonus de alianza (0–5%).
4. Moral (solo en servidores speed, rango 30–100).

### Modificadores aplicados a la defensa

1. Nivel de smithy por tropa defensora.
2. Muro de la tribu defensora (`GameDataPort.get_building_defense_bonus(wall_gid, wall_level)`). Si no se especifica tribu de muro, usa la aproximación `nivel × 3%` con aviso.
3. Stonemason (`+5% por nivel`).
4. Héroe defensor: puntos + bonus porcentual.
5. Cuando hay múltiples formaciones defensoras, el bonus de héroe es el promedio y el muro aplica una sola vez sobre el total.

### Drops de animales

Al matar animales NATURE, el héroe recibe recursos directamente (no van al almacén). El reparto es igual por los cuatro tipos de recurso (madera, arcilla, hierro, trigo) para cada animal. Los valores confirmados con reportes reales son:

| Animales (ordinal 1-4) | 40 por recurso / animal |
| Animales (5-6) | 80 por recurso / animal |
| Animales (7-8) | 120 por recurso / animal |
| Tigre (9) y Elefante (10) | 240 y 300 — **pendiente confirmar con datos reales** |

Ver `core/use_cases/nature_animal_drops.py` para la tabla completa.

### Resultado neto

La UI presenta tres filas en la tabla de recursos: botín de animales (en verde), coste de tropas perdidas (en rojo) y neto (verde si positivo, rojo si negativo). Esto permite al usuario saber en un vistazo si el ataque fue rentable en recursos.

---

## 4. Valor para el negocio

- Reduce las pérdidas inesperadas de tropas, que son el recurso más escaso del juego (se tarda horas en producirlas).
- Permite calcular cuántas veces puede repetir el mismo ataque antes de quedarse sin tropas.
- Informa sobre la rentabilidad real de cada oasis: algunos generan recursos de animales negativos respecto al coste de las bajas.

---

## 5. Qué decide el usuario con este simulador

- Si enviar ese ejército o reforzarlo antes del ataque.
- Qué modo elegir (saqueo para farmear, ataque para destruir murallas).
- Si incluir al héroe merece la pena dado el riesgo.
- Con cuántas tropas puede cubrir el oasis sin desperdiciar excedente.

---

## 6. Casos límite y comportamientos no obvios

| Situación | Comportamiento |
|---|---|
| Defensor sin tropas (oasis vacío) | Victoria inmediata, ratio = null, badge "Victoria sin combate" |
| Ratio exactamente = 1 | El atacante gana (el código usa `ratio >= 1.0`) |
| Moral < 30 | Clampeado a 30 con aviso; Travian no permite moral menor |
| Smithy nivel > máximo en BD | Clampeado al máximo disponible con aviso |
| Tropa de ataque = 0 (explorador) | Contribuye 0 a la fuerza pero sobrevive si el ejército gana |
| Múltiples defensores (refuerzos) | Se suman; el muro aplica solo una vez sobre el total |
| Sin `wall_tribe` | Fallback a `nivel × 3%` con aviso en `warnings[]` |

---

## 7. Divergencias código / spec detectadas (2026-06-04)

| Referencia | Spec dice | Código real |
|---|---|---|
| `loot.potential` | Calculado cuando `defender.village_resources` es proporcionado | El código solo lo calcula si `attacker_wins AND defenders[0].village_resources is not None`. Si el atacante pierde, `loot_potential = None` aunque se haya dado `village_resources`. Comportamiento razonable (no hay botín si se pierde) pero no está explicitado en el spec. |
| Drops Tigre (ord 9) y Elefante (ord 10) | Tabla spec: 120 y 200 respectivamente | Código real (`nature_animal_drops.py`): 240 y 300. Los valores del spec son estimaciones; el código fue actualizado con valores corregidos pero la tabla del spec no se actualizó. **Valores del código son los válidos.** |
| `attack_type` default | Spec menciona que se corrigió de `"attack"` a `"raid"` (corrección post-v3) | Código real: `attack_type: Literal["attack", "raid"] = "raid"` — correcto. |
| Gids de muro para Huns, Spartans, Vikings | Spec §RN-03 lista solo Romans, Teutons, Gauls, Egyptians | `WALL_GID_BY_TRIBE` en `combat_engine.py` también tiene solo esas 4 tribus. Huns/Spartans/Vikings usan fallback con warning. |

🔖 Última revisión: 2026-06-04
