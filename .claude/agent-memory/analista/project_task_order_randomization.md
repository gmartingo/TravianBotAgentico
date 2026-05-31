---
name: project-task-order-randomization
description: Spec task-order-randomization — helper puro ordered() para aleatorizar el orden de recorrido de colecciones; motivado por el mismo baneo que human-sessions v2
metadata:
  type: project
---

Spec en `docs/specs/task-order-randomization.md` con estado `ready-for-impl` (2026-05-30).

**Contexto:** el bot siempre recorría las farm lists en el mismo orden determinista. El
baneo de Travian (primera ofensa: -33% edificios) identificó esto como firma detectable.

**Qué hace:** Helper puro transversal en `core/utils/traversal.py` que aleatoriza el orden
de cualquier colección antes de iterarla. Aplicación inmediata: loop de farm_list_ids en
`core/use_cases/farm_lists.py:363`.

**Tres estrategias:**
- `DEFAULT`: mismo orden que viene (top→down).
- `REVERSED`: orden inverso (bottom→top).
- `SHUFFLE`: permutación aleatoria (`random.sample`, no in-place).

**Distribución:** 33/33/33 por defecto. Configurable globalmente (no por-tarea). Justificación:
overhead de UX sin beneficio real; la equiprobabilidad maximiza entropía del patrón observado.

**Piezas nuevas:**
- `core/utils/traversal.py` → `TraversalOrder` (enum), `TraversalConfig` (dataclass con
  validación suma ±0.01), `apply_order()`, `choose_order()`, `ordered()`.
- `core/ports/bot_config_db_port.py` → `BotConfigDbPort` genérico (get_config/set_config JSON).
- Tabla `bot_config` (clave-valor JSON genérico, reutilizable para otras configs globales).
- Endpoints: GET /bot/config/traversal, PUT /bot/config/traversal.
- `SendSchedulerGroupUseCase` añade campo `traversal_config: TraversalConfig`.

**Decisión clave: NO port propio para el helper.**
El helper es una función pura sin IO. Un port sería over-engineering claro.

**Puntos de aplicación FUTUROS:** entrenamiento tropas en N aldeas, construcción en N aldeas,
raids puntuales a N aldeas, sondeo de N slots, seed de oasis groups, seed de schedulers.
Todos documentados en §11.2 del spec para que implementadores futuros los encuentren.

**Tests:** UT-TOR01…UT-TOR14, IT-TOR01…IT-TOR05

**Relacionado:** [[project-human-sessions]] (mismo baneo, specs gemelos anti-detección)
