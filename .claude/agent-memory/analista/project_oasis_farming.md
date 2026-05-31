---
name: project-oasis-farming
description: Oasis farming automatizado — modelo de roles en FarmScheduler, grupos de oasis, máquina de estados y WIP explícitos (spec v2, modelo corregido)
metadata:
  type: project
---

Spec en `docs/specs/oasis-farming.md` con estado `ready-for-impl`.

**REFACTORIZACIÓN 2026-05-29:** El ciclo global de fases (HARDCORE/MAINTENANCE a nivel WorldAgent, duraciones 4-6h / 45-60min) fue extraído a `docs/specs/human-sessions.md`. Oasis-farming.md ya NO contiene: `OasisPhase` enum, `OasisSchedulerConfig` con campos de duración, arranque en MAINTENANCE, `_oasis_phase`/`_oasis_phase_start_time`/`_oasis_warmup_minutes`. El spec de oasis solo define intervalos de disparo de raids (bimodal HARDCORE, ±20% MAINTENANCE) y la máquina de estados de grupos. La dependencia se documenta en §1b y §RN-O09.

**Prerrequisito de implementación:** `human-sessions.md` primero, luego `oasis-farming.md`.

[[project-oasis-farming]] → nuevo spec hermano en `docs/specs/human-sessions.md`

**CORRECCIÓN FUNDAMENTAL (v2):** El spec anterior modelaba cada oasis como una entidad separada con su propia farm list. Esto era incorrecto. En Travian los oasis son slots dentro de listas (farm list = múltiples slots → múltiples oasis). El modelo correcto es el de ROLES en FarmScheduler.

**Modelo correcto — Roles de farm list:**
Las farm lists se diferencian por su campo `role` en `farm_schedulers`:
- `VILLAGE` → comportamiento actual de vacas (sin cambios)
- `OASIS_HARDCORE` → envío agresivo 340-490 s, equipo 2TT/slot
- `OASIS_MAINTENANCE` → envío cada 25 min ±20%, equipo 4TT/slot
- `OASIS_CLEANUP` → activada manualmente por WorldAgent al detectar pérdidas, equipo 1S+1TT+1H/slot

Las listas HARDCORE + MAINTENANCE + CLEANUP del mismo conjunto de oasis comparten `oasis_group_id` en `farm_schedulers`. Forman un **grupo de oasis**.

**Cambios en BD:**
- `farm_schedulers` recibe 2 columnas: `role TEXT NOT NULL DEFAULT 'VILLAGE'` y `oasis_group_id INTEGER`. DEFAULT garantiza retrocompatibilidad con los 21 endpoints existentes, sin tocar ninguno.
- Nueva tabla `oasis_groups` (estado del grupo: FARMING/ALERT/PAUSED, clean_streak, loss_streak).
- Nueva tabla `oasis_group_raid_history` (TTL 30 días).
- NO hay tabla `oasis` individual (eliminada).
- NO hay entidad `Oasis` individual (eliminada).
- NO hay `OasisDbPort` (eliminado).

**Máquina de estados del grupo (3 estados, no 5):**
```
FARMING → ALERT   : cualquier slot de HARDCORE/MAINTENANCE devuelve withLosses
ALERT   → FARMING : 3 raids CLEANUP limpias (clean_streak >= 3)
ALERT   → PAUSED  : 5 raids CLEANUP con pérdidas (loss_streak >= 5)
PAUSED  → FARMING : reactivación manual
```
No hay COLD_START ni STABILIZING: los oasis ya están configurados en Travian antes de activar el bot.

**Nuevas piezas creadas (coordenadas para el implementador):**
- `core/entities/farm_scheduler.py` → añadir `FarmSchedulerRole` enum + campos `role`/`oasis_group_id` en FarmScheduler
- `core/entities/oasis_group.py` → `OasisGroup`, `OasisGroupRaidRecord`, `OasisGroupState`
- `core/entities/task.py` → añadir `SEND_OASIS_RAID` a TaskType
- `core/utils/travel_time.py` → `calculate_travel_time(distance, troop_speed_fph, server_speed)`
- `core/ports/oasis_group_db_port.py` → `OasisGroupDbPort` (ABC)
- `core/exceptions.py` → `OasisGroupNotFoundError`, `OasisGroupAlreadyExistsError`
- `adapters/db/oasis_group_sqlite_adapter.py` → tablas oasis_groups + oasis_group_raid_history (TTL 30 días)
- `adapters/db/farm_list_sqlite_adapter.py` → migración ALTER TABLE (role, oasis_group_id) + lectura/escritura de nuevos campos
- `core/use_cases/oasis_group.py` → `OasisGroupUseCase`, `ReactivateOasisGroupUseCase`
- `core/scheduling/world_agent.py` → handler SEND_OASIS_RAID, seed_oasis_groups_from_db(), OasisSchedulerConfig, OasisPhase

**Correcciones del guardian incorporadas:**
- C1 (obligatorio): Arrancar SIEMPRE en MAINTENANCE, warmup random.uniform(20,30) min antes de HARDCORE
- C2 (recomendado): Offset incremental i×random.uniform(3,8)s entre grupos en wake-up Banda 1
- C3 (recomendado): Distribución bimodal HARDCORE (60% central 360-440s, 40% completo 340-490s)

**Reglas de negocio clave:**
- priority=2 para SEND_OASIS_RAID (SEND_FARM_LIST_GROUP priority=1).
- CLEANUP no tiene scheduler periódico propio — activación reactiva por el WorldAgent.
- Pérdidas detectadas si CUALQUIER slot del grupo devuelve withLosses.
- Grupos PAUSED no generan tareas; requieren ReactivateOasisGroupUseCase.
- EC-O04: errores de envío no cambian estado del grupo.
- EC-O05: slots con last_raid_state="" se ignoran (no penalizan).
- Wake-up: elapsed<10min→farming normal, 10-90→MAINTENANCE primero, >90min→ALERT+CLEANUP.
- TTL historial grupos: 30 días (vs 7 días de farm lists).

**WIP críticos:**
- Parseo de informe de batalla (necesita BattleReportBrowserPort)
- Bonus plaza de torneos en travel_time
- Notificaciones push en PAUSED
- Modificación dinámica del equipo en DOM de Travian
- UI/Dashboard de oasis
- Persistencia de fase HARDCORE/MAINTENANCE en BD
- CLEANUP por oasis individual (requiere parseo de informes)

[[project-farm-lists]]
