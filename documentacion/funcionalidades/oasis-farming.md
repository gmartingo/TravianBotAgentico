# Oasis Farming Automatizado — Documento funcional y de negocio

> Audiencias: (1) desarrolladores — sección de código; (2) stakeholders/PO — sección de negocio.
> Spec de referencia: `docs/specs/oasis-farming.md`.
> Estado del spec: `ready-for-impl` — **el módulo NO está implementado aún** (2026-06-04).

---

## Estado de implementación

**Este módulo está especificado pero no implementado.** Esta documentación describe lo que el spec define y lo que el código real contiene en el momento de la revisión (2026-06-04). Se marcan explícitamente las piezas implementadas vs. pendientes.

### Qué SÍ existe hoy en el código

| Componente | Estado | Ubicación |
|---|---|---|
| Enum `TaskType.SEND_OASIS_RAID` | Implementado | `core/entities/task.py` |
| Campo `role` en `FarmScheduler` | Pendiente de verificar | `core/entities/farm_scheduler.py` |
| Tabla `oasis_groups` | Pendiente de verificar | — |
| `OasisGroupUseCase` | Pendiente de verificar | — |
| `OasisGroupDbPort` | Pendiente de verificar | — |
| Integración en `WorldAgent` | Pendiente de verificar | `core/scheduling/world_agent.py` |

> **Nota al desarrollador:** antes de implementar este módulo, ejecuta `palantir` para confirmar qué entidades ya existen en el código. El spec fue escrito antes de la implementación; puede que algunos campos ya se añadieran en commits intermedios.

---

## Qué resuelve esta feature

El usuario quiere atacar oasis 24/7 de forma completamente automática e indetectable. El problema es que los animales respawnean en ventanas de tiempo fijas y cortas (5-14 minutos según la especie). Si el bot espera demasiado entre ataques, el oasis acumula animales que pueden derrotar las tropas enviadas. Si el bot ataca demasiado seguido, las tropas no llegan a tiempo.

Esta feature automatiza ese ciclo usando las farm lists existentes (ya configuradas por el usuario en Travian) y añade una capa de inteligencia para detectar pérdidas y escalar la respuesta.

---

## Objetivo de negocio

Maximizar el botín de recursos de oasis mientras el bot permanece activo 24/7, con riesgo mínimo de pérdidas, todo de forma indetectable para los servidores de Travian.

Complementa el farming de vacas (farm lists de aldeas): las mismas farm lists organizadas con el campo `role` correcto activan este comportamiento sin cambiar la UI existente.

---

## Actores

| Actor | Rol |
|---|---|
| Bot (WorldAgent) | Ejecuta el ciclo de oasis de forma autónoma. Gestiona la máquina de estados por grupo. |
| Usuario | Configura las farm lists en Travian con las tropas correctas. Asigna el campo `role` y `oasis_group_id` en cada scheduler. Interviene manualmente para sacar un grupo de PAUSED. |
| Sistema (BD SQLite) | Persiste el estado de cada grupo (`oasis_groups`), historial de raids (`oasis_group_raid_history`). |

---

## Conceptos clave

### Rol de farm list (`FarmSchedulerRole`)

Cada `FarmScheduler` tiene un campo `role` que define el comportamiento:

| Rol | Frecuencia | Equipo por slot | Propósito |
|---|---|---|---|
| `VILLAGE` | Existente (sin cambio) | — | Farm lists de vacas (aldeas). Comportamiento anterior. |
| `OASIS_HARDCORE` | Cada 340–490 s (~6 min) | 2 TT (Galos) | Ataque agresivo calibrado para el peor caso de oasis Iron/Clay |
| `OASIS_MAINTENANCE` | Cada ~25 min ±20% | 4 TT | Ataque moderado para oasis que no requieren limpieza frecuente |
| `OASIS_CLEANUP` | Solo cuando hay pérdidas | 1 Espada + 1 TT + 1 Haeduan | Liquidar oasis que acumularon animales peligrosos |

### Grupos de oasis (`oasis_group_id`)

Las listas HARDCORE + MAINTENANCE + CLEANUP que cubren los mismos oasis comparten un `oasis_group_id`. El bot gestiona la máquina de estados a nivel de **grupo**, no de lista individual. Si cualquier slot de la lista HARDCORE detecta pérdidas, se activa la CLEANUP de todo el grupo.

### Máquina de estados del grupo

```
FARMING → ALERT   : cualquier slot HARDCORE o MAINTENANCE devuelve withLosses
ALERT   → FARMING : 3 raids CLEANUP sin pérdidas (clean_streak >= 3)
ALERT   → PAUSED  : 5 raids CLEANUP con pérdidas (loss_streak >= 5)
PAUSED  → FARMING : intervención manual del usuario
```

No hay estado COLD_START ni STABILIZING: los grupos arrancan directamente en FARMING porque los oasis ya están en producción (el usuario los configuró previamente en Travian).

---

## Reglas de negocio

### Timing

**RN-O02:** Los intervalos de HARDCORE (340–490 s) están calibrados para el peor caso de oasis Iron/Clay (araña a 6 min, murciélago a 8 min) con equipo de 2 TT de Galos. El bot no adapta este intervalo al tipo de oasis automáticamente.

**RN-O11:** Las tareas `SEND_OASIS_RAID` tienen prioridad 2. Las farm lists de vacas (`SEND_FARM_LIST_GROUP`) tienen prioridad 1. Las vacas tienen preferencia en caso de colisión.

**RN-O12:** Entre listas de oasis consecutivas el bot aplica una pausa aleatoria de 2–5 segundos (mismo patrón anti-detección que las farm lists).

### Máquina de estados

**RN-O05:** El estado vive en `oasis_groups`, no en las farm lists. Un mismo grupo puede tener múltiples listas (HARDCORE + MAINTENANCE + CLEANUP) pero solo un estado.

**RN-O08:** Un solo slot con `withLosses` activa el protocolo de limpieza de todo el grupo. Es conservador pero seguro.

**RN-O14:** Un grupo en PAUSED no genera ninguna tarea. Requiere `ReactivateOasisGroupUseCase` para salir.

### Dependencia de human-sessions

**RN-O09:** El WorldAgent solo encola tareas `SEND_OASIS_RAID` cuando el modo activo es `HARDCORE` (según `human-sessions.md` v2). Durante `IDLE` o `DISCONNECTED`, ninguna tarea de oasis se encola. Al reactivarse, `seed_oasis_groups_from_db()` reconstruye la cola con wake-up inteligente por bandas de tiempo transcurrido.

### Tipos de oasis soportados

**RN-O01:** Solo oasis Iron, Iron+crop, Clay, Clay+crop, Wood, Wood+clay. Los oasis Crop están excluidos hasta que exista parseo completo de informes (el equipo de 2 TT no es suficiente para ciertos oasis Crop).

---

## Modelo de datos (según spec — pendiente de verificar implementación)

### Cambios en `farm_schedulers`

```sql
ALTER TABLE farm_schedulers ADD COLUMN role TEXT NOT NULL DEFAULT 'VILLAGE';
ALTER TABLE farm_schedulers ADD COLUMN oasis_group_id INTEGER;
```

Retrocompatible: los schedulers existentes conservan `role = 'VILLAGE'` y `oasis_group_id = NULL`.

### Tabla nueva: `oasis_groups`

Columnas clave: `id`, `world_id`, `name`, `state` (FARMING/ALERT/PAUSED), `clean_streak`, `loss_streak`, `last_raid_time`, `last_raid_role`, `paused_reason`.

### Tabla nueva: `oasis_group_raid_history`

Historial de raids por grupo. TTL: 30 días (vs 7 días de farm lists, porque los patrones de oasis necesitan historial más largo).

---

## Wake-up inteligente al reactivar el bot

Al entrar en modo HARDCORE, `seed_oasis_groups_from_db()` lee todos los grupos activos y los encola según cuánto tiempo lleva sin atacarse:

| Banda | Tiempo transcurrido | Acción |
|---|---|---|
| Banda 1 | < 10 min | Retomar directamente (delay corto 30–90 s) |
| Banda 2 | 10–90 min | Arrancar con MAINTENANCE primero (acumulación moderada) |
| Banda 3 | > 90 min o grupo nuevo | Forzar ALERT y activar CLEANUP antes de retomar HARDCORE |

Entre grupos se aplica un offset incremental de 3–8 s (anti-detección: evita burst de envíos simultáneos, RN-C2 del guardian).

---

## Integración con farm lists existentes

Esta feature **no modifica** los 21 endpoints de farm lists. El campo `role` y `oasis_group_id` son transparentes para el frontend de farm lists: aparecen como campos opacos pero no cambian la UI de gestión de listas.

La reutilización de `FarmListBrowserPort.send_farm_list(farm_list_id)` sin modificación fue una decisión explícita del spec: el bot ya sabe enviar farm lists y leer resultados. Oasis farming reutiliza esa infraestructura.

---

## Lo que esta feature NO hace (fuera de alcance)

- No tiene UI propia (un dashboard de oasis es una feature futura independiente).
- No detecta automáticamente el tipo de oasis; el usuario configura el rol manualmente.
- No soporta oasis Crop.
- No incluye bonus de plaza de torneos en el cálculo de `travel_time`.
- No envía notificaciones al usuario cuando un grupo pasa a PAUSED.
- No modifica el equipo dinámicamente; el usuario lo configura en las farm lists de Travian.

---

## Relaciones con otras features

- **Human Sessions (`docs/specs/human-sessions.md`):** prerequisito. El WorldAgent solo encola raids en modo HARDCORE.
- **Farm Lists:** reutiliza el puerto `FarmListBrowserPort` sin cambios.
- **Reportes de ataques:** los datos de esta feature son distintos a los reportes del módulo anterior. Los reportes de ataques son el historial de lo que ya pasó; oasis-farming es la automatización de lo que pasará.

---

🔖 Última revisión: 2026-06-04 (creado — feature oasis-farming: spec ready-for-impl, módulo no implementado; documenta diseño completo para referencia del desarrollador)
