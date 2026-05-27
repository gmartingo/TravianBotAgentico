---
name: project-farm-lists
description: Decisiones cerradas de la feature farm lists automáticas: entidades, puertos, use cases, scheduling, browser adapter, BD
metadata:
  type: project
---

Feature farm lists automáticas especificada en `docs/specs/farm-lists.md` (estado: ready-for-impl, apis_validadas_por_desarrollador_apis: false).

## Entidades de dominio

- `FarmSlot`, `FarmList`, `BotSlotStatus`, `SlotEvent` — en `core/entities/farm_list.py`
- `FarmScheduler` — en `core/entities/farm_scheduler.py`
- `FarmListSendEvent` — en `core/entities/farm_list_send_event.py`
- `FarmListSendResult` — en `core/entities/farm_list_send_result.py`
- `Task`, `TaskType` (con `SEND_FARM_LIST_GROUP`) — en `core/entities/task.py`

## Puertos nuevos

- `FarmListBrowserPort` — métodos: `read_farm_lists`, `read_farm_list`, `send_farm_list`, `activate_slot_in_travian`, `deactivate_slot_in_travian`
- `FarmListDbPort` — todos los métodos de acceso a BD de farm lists, schedulers, slots, eventos e historial

**NO extender BrowserPort ni DbPort** — convención del proyecto.

## Excepciones nuevas (a añadir en `core/exceptions.py`)

- `SchedulerNotFoundError(scheduler_id: int)` — `SCHEDULER_NOT_FOUND`
- `FarmSlotNotFoundError(slot_id: int)` — `FARM_SLOT_NOT_FOUND`
- `FarmListSendError(farm_list_id: int, reason: str)` — `FARM_LIST_SEND_ERROR`
- `FarmListPageError(message: str)` — `FARM_LIST_PAGE_ERROR`
- `FarmListResponseError(index: int, message: str)` — `FARM_LIST_RESPONSE_ERROR`
- `FarmListNotFoundError` — ya existe en `core/exceptions.py`

## Reglas clave

- Click JS en `button.startFarmList` sin movimiento de ratón (RN-11).
- Comparar `current` vs `active` (slots sin clase `disabled`), no vs `total` (RN-12).
- Matching de slots por coordenadas (x,y), no por ID (RN-15).
- Cooldown base 3600s, máximo 86400s con duplicación exponencial (RN-08).
- `losses_already_seen` guard: si `report_id_at_disable == last_raid_report_id` → no doble desactivación (RN-09).
- Pausa entre listas del grupo: `random.uniform(2.0, 5.0)` segundos (RN-03).
- `Accept-Language` NO requerido: estos endpoints no devuelven texto localizado.

## Scheduling

- `TaskQueue` en `core/scheduling/task_queue.py` — lista ordenada por `(priority ASC, execute_at ASC)`.
- `WorldAgent` en `core/scheduling/world_agent.py` — bucle único por mundo, prioridad 1 para farm lists.
- `run_now(scheduler_id)` es síncrono; lanza `_notify_event.set()` para despertar el bucle.

## Browser adapter

- Selectores JS siempre estructurales; JS inyectado como IIFE (zendriver no acepta argumentos).
- `_navigate_to_farm_list`: navega solo si no estamos ya en `tt=99`; si estamos en `gid=16` solo cambia pestaña.
- `ensure_farm_list_loaded`: si la lista no aparece en DOM, reintenta desde otra aldea (`dorf2.php?newdid=`).
- `human_delay`: 400-700ms entre listas; 800-1200ms al expandir; 1500-2000ms tras click de envío (AJAX de Travian).

## BD

- Fechas en `FarmSchedulerModel` como VARCHAR(30) ISO (consistencia con `last_raid_time`).
- PK compuesta en `farm_slots`: (id, farm_list_id).
- Al borrar scheduler: farm lists quedan con `scheduler_id=NULL` (no cascade delete).
- Historial: TTL 7 días, purga automática en cada inserción.
- Campos `loot_*` en `farm_list_send_history` reservados para Agente ROI.

## Código de referencia

`C:\Dev\Travian\TravianBotS0\` — implementación completa consultada para este spec.

**Why:** Spec derivado directamente del código de referencia S0; comportamiento exacto ya validado en producción.
**How to apply:** Al diseñar cambios futuros sobre farm lists, verificar siempre contra el código de referencia S0.
