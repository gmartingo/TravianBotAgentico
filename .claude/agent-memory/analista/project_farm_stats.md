---
name: project-farm-stats
description: Gaps de Farm Stats y Metadata de Scheduler (4 gaps cerrados en farm-stats-y-metadata-scheduler.md)
metadata:
  type: project
---

Feature de cierre de 4 gaps sobre `docs/specs/farm-lists.md` (estado `implemented`). Spec en
`docs/specs/farm-stats-y-metadata-scheduler.md`.

**Gap A — `last_send_time` por farm list:**
- `_serialize_farm_list` en `adapters/api/routes/farm.py` ya tenía `"last_send_time": None` hardcodeado.
- Fix: nueva query `MAX(timestamp) GROUP BY farm_list_id` en `FarmListSQLiteAdapter` como método `get_last_send_times_by_world(world_id, farm_list_ids) -> dict[int, datetime | None]`.

**Gap B — Metadata del scheduler desnormalizada en historial:**
- Añadir 4 columnas a `farm_list_send_history`: `scheduler_name`, `scheduler_interval_min_ms`, `scheduler_interval_max_ms`, `scheduler_execution_count`.
- `scheduler_execution_count` = valor ANTES del incremento (número de secuencia del envío).
- Para envíos manuales: NULLs. Para `SchedulerNotFoundError` en carrera: NULLs también (EC-B02).

**Gap C — `total_bounty` calculado, no almacenado:**
- Tabla nueva `slot_bounty_history(id, slot_id, farm_list_id, world_id, timestamp, bounty, raid_report_id)`.
- TTL: 7 días (mismo que `farm_list_send_history`). Purga en cada insert.
- DROP COLUMN `farm_slots.total_bounty` — pérdida de datos aceptada en la migración.
- `FarmSlot.total_bounty` sigue en el dataclass (campo calculado, valor 0 por defecto).
- `_load_slots` ahora hace 2 queries: slots + `_get_bounty_sums(farm_list_id)` como dict.
- `sync_farm_list` necesita `world_id` como nuevo parámetro (firma rota, breaking change mínimo).
- Al reasignar ID de slot (mismo x,y): UPDATE `slot_bounty_history` al nuevo id antes de borrar el viejo.

**Gap D — Endpoint de stats:**
- `GET /farm/worlds/{world_id}/schedulers/{scheduler_id}/stats` → nuevo.
- No requiere sesión de browser (solo BD).
- Métricas: `success_rate`, `active_slots_avg`, `total_bounty`, `bounty_per_hour`, `execution_count`, `last_send_time`, `per_list`.
- `bounty_per_hour` = `total_bounty / MAX(1, horas_en_rango)` para evitar / 0.
- Si `scheduler.world_id != world_id` de la ruta → 404 (EC-D03).

**Gap E — POSPUESTO:**
- Desglose loot (loot_wood/clay/iron/crop) reservado para Agente ROI. Los 4 campos ya existen en BD y entidad; fuera de scope de este spec.

**Patrón de migración SQLite observado:**
- `ALTER TABLE ADD COLUMN` no soporta `IF NOT EXISTS` → usar `PRAGMA table_info` como guard.
- `DROP COLUMN` requiere SQLite >= 3.35 (Python 3.14 incluye sqlite3 >= 3.45, OK).
- Siempre verificar existencia de columna con `PRAGMA table_info` antes del DROP.

**Why:** el usuario cerró las 3 respuestas pendientes del análisis en un solo mensaje y pidió
el spec directamente. No hubo Fase 1 adicional.

**How to apply:** al analizar features de stats/analytics sobre historial con TTL en este proyecto,
recordar el patrón: historial de 7 días, suma por ventana de tiempo, desnormalización de nombres
para que los registros sobrevivan al borrado de la entidad.
