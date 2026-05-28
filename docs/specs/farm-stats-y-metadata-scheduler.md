---
id: farm-stats-y-metadata-scheduler
titulo: "Farm Stats y Metadata de Scheduler"
estado: implemented
fecha: 2026-05-27
autor: analista
apis_validadas_por_desarrollador_apis: true
---

# Farm Stats y Metadata de Scheduler

> Este spec cierra cuatro gaps detectados tras la implementación de Farm Lists Automáticas
> (`docs/specs/farm-lists.md`, estado `implemented`). El implementador debe leer ese spec primero
> para tener el contexto completo del dominio.

---

## 1. Objetivo de negocio

Completar los datos de seguimiento que el dashboard necesita para que el usuario pueda tomar
decisiones sobre sus schedulers y slots:

1. **Gap A** — `last_send_time` por farm list: `GET /farm/worlds/{world_id}/farm-lists` ya
   devuelve `null` en ese campo porque la API calcula la suma de `total_bounty` en memoria pero
   nunca consulta el historial de envíos para extraer el último timestamp.

2. **Gap B** — Metadata del scheduler desnormalizada en el historial: `farm_list_send_history`
   solo guarda `scheduler_id`, pero no el nombre ni los intervalos del scheduler en el momento del
   envío. Cuando se modifica o borra un scheduler, el historial pierde la trazabilidad del
   "quién ordenó este envío y con qué configuración".

3. **Gap C** — `total_bounty` como dato calculado (no almacenado): la columna
   `farm_slots.total_bounty` acumula botín de forma ad-hoc y es propensa a inconsistencias
   (drift si hay reasignación de IDs, resets sin registro). Se reemplaza por una tabla histórica
   de bounty por slot (`slot_bounty_history`) con TTL de 7 días, y `total_bounty` pasa a ser
   siempre la suma de esa tabla.

4. **Gap D** — Endpoint de estadísticas del scheduler: no existe ningún endpoint que agregue
   las métricas por farm list dentro de un scheduler (tasa de éxito, bounty/hora, etc.). El
   dashboard lo necesita para mostrar "qué tan bien va" cada scheduler en tiempo real.

---

## 2. Actores y permisos

Mismos actores que en el spec base:

| Actor | Descripción |
|---|---|
| **WorldAgent** | Usa `ProcessFarmListUseCase` — necesita escribir en `slot_bounty_history` |
| **Usuario (dashboard)** | Consulta el endpoint de stats y el listado de farm lists (con `last_send_time` poblado) |
| **Adaptador de BD** | `FarmListSQLiteAdapter` — implementa todos los cambios DDL y de métodos |

No hay roles de autorización; la API es local (single-user).

---

## 3. Alcance

### Dentro de alcance

- **Gap A** — Poblar `last_send_time` en `_serialize_farm_list` consultando `MAX(timestamp)` del
  historial agrupado por `farm_list_id`.
- **Gap B** — Añadir columnas `scheduler_name`, `scheduler_interval_min_ms`,
  `scheduler_interval_max_ms` y `scheduler_execution_count` a `farm_list_send_history`.
  Desnormalizarlas al insertar en `add_farm_list_send_event`.
- **Gap C** — Crear tabla `slot_bounty_history(id, slot_id, farm_list_id, world_id, timestamp,
  bounty, raid_report_id)` con TTL 7 días. Poblarla en `_sync_slots` cada vez que
  `last_raid_report_id` cambia y `last_raid_bounty > 0`. Eliminar `farm_slots.total_bounty`
  (DROP COLUMN). Calcular `total_bounty` como `SUM(bounty)` de `slot_bounty_history`.
- **Gap D** — Endpoint `GET /farm/worlds/{world_id}/schedulers/{scheduler_id}/stats` con métricas
  agregadas: `success_rate`, `active_slots_avg`, `total_bounty`, `bounty_per_hour`,
  `last_send_time` por lista, `execution_count`.
- Migraciones SQL exactas para todos los cambios de esquema.
- Métodos nuevos y modificados en `FarmListDbPort` y `FarmListSQLiteAdapter`.
- Cambios en `FarmListSendEvent` (entidad), `ProcessFarmListUseCase`, `SendSchedulerGroupUseCase`.
- Serialización actualizada en `adapters/api/routes/farm.py`.
- Tests unitarios para los cuatro gaps.

### Fuera de alcance

- **Gap E (pospuesto)** — Desglose del loot por recurso (`loot_wood`, `loot_clay`, `loot_iron`,
  `loot_crop`). Los 4 campos ya existen en `FarmListSendEvent` y en
  `farm_list_send_history` como reservados para el Agente ROI. No se tocan en este spec.
- Integración con el Agente ROI.
- Retención histórica de más de 7 días para `slot_bounty_history`.
- Lógica de anti-detección adicional (no hay cambios en `adapters/browser/`).
- UI del dashboard (no es responsabilidad de este spec; el diseñador-producto lo manejará por
  separado).

---

## 4. Reglas de negocio

| ID | Regla |
|---|---|
| RN-B01 | `farm_list_send_history` debe guardar `scheduler_name`, `scheduler_interval_min_ms`, `scheduler_interval_max_ms` y `scheduler_execution_count` en el momento del envío. Si `scheduler_id` es NULL (envío manual), esos campos se guardan como NULL / 0 respectivamente. |
| RN-B02 | `scheduler_execution_count` que se desnormaliza es el valor **antes** del incremento del envío actual (el valor que tiene el scheduler cuando `SendSchedulerGroupUseCase.execute` arranca). |
| RN-C01 | Cuando `sync_farm_list` detecta que `last_raid_report_id` ha cambiado **y** `last_raid_bounty > 0`, inserta una fila en `slot_bounty_history`. |
| RN-C02 | `slot_bounty_history` tiene TTL de 7 días, idéntico a `farm_list_send_history`. La purga se ejecuta en cada inserción en `add_slot_bounty_record`, filtrando por `world_id`. |
| RN-C03 | `farm_slots.total_bounty` se elimina de la tabla. En memoria, `FarmSlot.total_bounty` se calcula con una nueva consulta `SUM(bounty) FROM slot_bounty_history WHERE slot_id = ? AND farm_list_id = ?`. |
| RN-C04 | Cuando `_to_slot` construye un `FarmSlot` desde la BD, `total_bounty` se pasa a 0 por defecto; el cargador de slots (`_load_slots`) debe enriquecerlo con una segunda consulta o con un JOIN a `slot_bounty_history`. |
| RN-C05 | En `sync_farm_list`, al hacer el UPSERT de un slot, si el `last_raid_report_id` del slot entrante es distinto al que había en BD y `last_raid_bounty > 0`, se llama a `add_slot_bounty_record` **dentro del mismo commit** del sync. |
| RN-C06 | Si Travian reasigna el ID de un slot (mismo x,y, distinto id), los registros `slot_bounty_history` del slot antiguo se reasignan al nuevo id con un UPDATE antes de borrar el slot antiguo. Esto preserva el historial de bounty. |
| RN-A01 | `last_send_time` de una farm list se calcula como `MAX(timestamp) FROM farm_list_send_history WHERE farm_list_id = ? AND world_id = ?`. |
| RN-A02 | `last_send_time` puede ser NULL si la lista nunca ha sido enviada (no hay filas en el historial para ese `farm_list_id`). |
| RN-D01 | `success_rate` = `COUNT(*) FILTER (WHERE status = 'success') / COUNT(*)` sobre el historial de los últimos 7 días, agrupado por `farm_list_id` para cada lista del scheduler. |
| RN-D02 | `active_slots_avg` = media del campo `being_raided_total` en los últimos 7 días, agrupado por `farm_list_id`. Excluir filas con `being_raided_total IS NULL`. |
| RN-D03 | `total_bounty` del scheduler = `SUM(bounty) FROM slot_bounty_history WHERE farm_list_id IN (lista_del_scheduler)`. Esto abarca solo los 7 días de retención. |
| RN-D04 | `bounty_per_hour` = `total_bounty / MAX(1, horas_en_rango)`, donde `horas_en_rango = (now - MIN(timestamp)) / 3600` sobre el historial de los últimos 7 días del scheduler. Si no hay datos, `bounty_per_hour = 0`. |
| RN-D05 | `execution_count` del scheduler se obtiene directamente de `farm_schedulers.execution_count` (es authoritative; no se recalcula). |
| RN-D06 | Métricas por lista dentro del scheduler: `last_send_time`, `success_rate`, `active_slots_avg`, `total_bounty` (suma de `slot_bounty_history` filtrado por `farm_list_id`), `bounty_per_hour` por lista. |
| RN-D07 | El endpoint de stats no requiere sesión activa del browser; solo consulta la BD. |

---

## 5. Flujo principal y flujos alternativos

### Gap A: Flujo de consulta de farm lists con `last_send_time`

```
GET /farm/worlds/{world_id}/farm-lists
  → GetFarmListsUseCase.execute(world_id)
  → db.get_farm_lists_by_world(world_id)          # ya existe
  → db.get_last_send_times_by_world(world_id)     # NUEVO: MAX(timestamp) GROUP BY farm_list_id
  → _serialize_farm_list(fl, last_send_time)       # pasa el timestamp al serializador
  → response 200 con last_send_time poblado
```

### Gap B: Flujo de inserción desnormalizada en historial

```
ProcessFarmListUseCase.execute(farm_list_id, world_id):
  ...
  # ANTES del insert en historial, obtener metadata del scheduler
  scheduler = await db.get_scheduler(synced.scheduler_id) if synced.scheduler_id else None
  event = FarmListSendEvent(
      ...
      scheduler_name        = scheduler.name if scheduler else None,
      scheduler_interval_min_ms = scheduler.interval_min_ms if scheduler else None,
      scheduler_interval_max_ms = scheduler.interval_max_ms if scheduler else None,
      scheduler_execution_count = scheduler.execution_count if scheduler else None,
  )
  await db.add_farm_list_send_event(event)
```

### Gap C: Flujo de acumulación de bounty

```
FarmListSQLiteAdapter.sync_farm_list(farm_list):
  para cada slot entrante:
    existing = lookup por coords (x,y)
    si existing y existing.last_raid_report_id != slot.last_raid_report_id y slot.last_raid_bounty > 0:
      await add_slot_bounty_record(SlotBountyRecord(
          slot_id=slot.id,
          farm_list_id=farm_list.id,
          world_id=world_id_del_contexto,  # se pasa a sync_farm_list
          timestamp=utcnow(),
          bounty=slot.last_raid_bounty,
          raid_report_id=slot.last_raid_report_id,
      ))
      purgar slot_bounty_history (registros > 7 días, misma world_id)
    UPSERT del slot SIN total_bounty (columna eliminada)
  commit
```

> Nota: `world_id` se añade como parámetro de `sync_farm_list` para poder filtrar la purga y
> los inserts. Ver sección 8 (cambios en puertos).

### Gap D: Flujo de consulta de stats del scheduler

```
GET /farm/worlds/{world_id}/schedulers/{scheduler_id}/stats
  → GetSchedulerStatsUseCase.execute(scheduler_id, world_id)
      1. scheduler = db.get_scheduler(scheduler_id)   # lanza SchedulerNotFoundError si no existe
      2. stats = db.get_scheduler_stats(scheduler_id, world_id)  # NUEVO
      3. retorna SchedulerStats
```

### Flujo alternativo: scheduler sin historial

Si el scheduler tiene `farm_list_ids` pero ninguna de sus listas tiene filas en
`farm_list_send_history`, el endpoint devuelve métricas en cero (no error):
`success_rate=0.0, active_slots_avg=0.0, total_bounty=0, bounty_per_hour=0.0`,
`per_list=[]`.

### Flujo alternativo: scheduler borrado

`GET /farm/worlds/{world_id}/schedulers/{scheduler_id}/stats` → `404` si el scheduler no
existe en BD (la excepción `SchedulerNotFoundError` se mapea a `404` por el handler global).

---

## 6. Edge cases

| ID | Edge case | Tratamiento |
|---|---|---|
| EC-B01 | Envío manual (`triggered_by="manual"`, `scheduler_id=NULL`) | `scheduler_name=None`, `scheduler_interval_min_ms=None`, `scheduler_interval_max_ms=None`, `scheduler_execution_count=None`. El esquema permite NULLs en esas columnas. |
| EC-B02 | El scheduler se borra justo antes de que `add_farm_list_send_event` lo consulte | Capturar `SchedulerNotFoundError` en `ProcessFarmListUseCase` al obtener metadata del scheduler; insertar el evento con los campos de metadata en NULL. No detener el envío. |
| EC-C01 | `last_raid_bounty = 0` cuando el raid no tuvo botín (slot vacío) | No insertar en `slot_bounty_history` (RN-C01). Un bounty de 0 no aporta información y llenaría la tabla. |
| EC-C02 | `last_raid_report_id` llega vacío (`""`) en el slot del DOM | No insertar (no hay informe asociado). La condición `last_raid_report_id != ""` previene inserciones vacías. |
| EC-C03 | Travian reasigna ID de slot (mismo x,y, distinto id) | Antes de borrar el slot viejo, ejecutar `UPDATE slot_bounty_history SET slot_id = <nuevo_id> WHERE slot_id = <viejo_id> AND farm_list_id = ?`. Luego borrar el slot viejo (RN-C06). |
| EC-C04 | `_load_slots` carga cientos de slots; hacer una query por slot para `total_bounty` sería muy lento | Usar una sola query de agregación: `SELECT slot_id, SUM(bounty) FROM slot_bounty_history WHERE farm_list_id = ? GROUP BY slot_id`. Mapear resultados a un dict antes de construir los `FarmSlot`. |
| EC-C05 | Migración: base de datos existente con `total_bounty > 0` en `farm_slots` | El valor acumulado **se pierde** con la migración (DROP COLUMN). El implementador debe documentar esto como **pérdida de datos aceptada**: el historial solo retiene 7 días, y los valores acumulados antes de la migración no pueden recuperarse sin el historial detallado que no existía. Es un trade-off aceptado (decidido en el análisis). |
| EC-A01 | Farm list nunca enviada (sin filas en historial) | `last_send_time=null` en la respuesta (RN-A02). |
| EC-A02 | Farm list eliminada pero con historial aún vivo (TTL no expirado) | No aplica: si se borra una farm list, el historial queda huérfano con `farm_list_id` ya no existente. La consulta de `last_send_times` hace un `IN (ids_de_listas_activas)` así que no incluye listas borradas. |
| EC-D01 | Scheduler con `farm_list_ids` vacío | `per_list=[]`, todas las métricas globales en cero. |
| EC-D02 | Intervalo de cálculo de `bounty_per_hour` con un solo envío | `horas_en_rango = 0` → usar `MAX(1, horas)` para evitar división por cero (RN-D04). |
| EC-D03 | `world_id` en la ruta no corresponde al `world_id` del scheduler | El scheduler está asociado a su `world_id` en BD. El endpoint verifica que `scheduler.world_id == world_id` de la ruta; si no coincide, devuelve `404` (el scheduler no pertenece a ese mundo). |
| EC-D04 | Migración de BD en caliente (servidor corriendo) | La migración usa solo `ALTER TABLE ADD COLUMN` y `CREATE TABLE` (idempotentes). No bloquea el servidor. El `DROP COLUMN` de `total_bounty` requiere SQLite >= 3.35; verificar versión en `ensure_tables`. |

---

## 7. Modelo de datos / cambios de esquema

### 7.1 Tabla modificada: `farm_list_send_history`

**Columnas añadidas** (todas con DEFAULT NULL para compatibilidad con filas existentes):

| Columna | Tipo | Restricciones | Notas |
|---|---|---|---|
| `scheduler_name` | TEXT | DEFAULT NULL | Nombre del scheduler en el momento del envío |
| `scheduler_interval_min_ms` | INTEGER | DEFAULT NULL | Intervalo mínimo en ms |
| `scheduler_interval_max_ms` | INTEGER | DEFAULT NULL | Intervalo máximo en ms |
| `scheduler_execution_count` | INTEGER | DEFAULT NULL | Ejecuciones previas del scheduler (antes de esta) |

**SQL de migración** (se ejecuta en `ensure_tables` — idempotente):

```sql
ALTER TABLE farm_list_send_history
    ADD COLUMN scheduler_name TEXT DEFAULT NULL;

ALTER TABLE farm_list_send_history
    ADD COLUMN scheduler_interval_min_ms INTEGER DEFAULT NULL;

ALTER TABLE farm_list_send_history
    ADD COLUMN scheduler_interval_max_ms INTEGER DEFAULT NULL;

ALTER TABLE farm_list_send_history
    ADD COLUMN scheduler_execution_count INTEGER DEFAULT NULL;
```

### 7.2 Tabla modificada: `farm_slots`

**Columna eliminada**: `total_bounty INTEGER NOT NULL DEFAULT 0`

**SQL de migración**:

```sql
-- SQLite >= 3.35 requerido (Python 3.14 incluye sqlite3 >= 3.45, OK)
ALTER TABLE farm_slots DROP COLUMN total_bounty;
```

**IMPORTANTE para la migración**: este `ALTER TABLE ... DROP COLUMN` es destructivo.
Si la base de datos ya tiene filas con `total_bounty > 0`, ese valor se perderá
permanentemente. Esta pérdida es aceptada (ver EC-C05). El implementador DEBE ejecutar
este SQL solo si la columna existe. El guard correcto es:

```python
# En ensure_tables(), antes del DROP COLUMN:
cursor = await conn.execute("PRAGMA table_info(farm_slots)")
cols = {row['name'] for row in await cursor.fetchall()}
if 'total_bounty' in cols:
    await conn.execute("ALTER TABLE farm_slots DROP COLUMN total_bounty")
```

### 7.3 Tabla nueva: `slot_bounty_history`

```sql
CREATE TABLE IF NOT EXISTS slot_bounty_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    slot_id         INTEGER NOT NULL,
    farm_list_id    INTEGER NOT NULL,
    world_id        INTEGER NOT NULL,
    timestamp       TEXT    NOT NULL,   -- ISO UTC
    bounty          INTEGER NOT NULL,
    raid_report_id  TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_slot_bounty_slot
    ON slot_bounty_history(slot_id, farm_list_id);

CREATE INDEX IF NOT EXISTS idx_slot_bounty_world_ts
    ON slot_bounty_history(world_id, timestamp);
```

**Notas de diseño**:
- No hay FK a `farm_slots` ni a `farm_lists` — igual que el resto del historial en el proyecto
  (datos denormalizados para que los registros sobrevivan si se borra la entidad origen).
- `slot_id + farm_list_id` es la PK lógica del slot (misma convención que `farm_slots`).
- El índice por `(slot_id, farm_list_id)` optimiza la consulta de `SUM(bounty)` por slot.
- El índice por `(world_id, timestamp)` optimiza la purga y las consultas de stats.

### 7.4 DDL completo resultante de `farm_slots` (sin `total_bounty`)

```sql
CREATE TABLE IF NOT EXISTS farm_slots (
    id                   INTEGER NOT NULL,
    farm_list_id         INTEGER NOT NULL REFERENCES farm_lists(id) ON DELETE CASCADE,
    target_name          TEXT    NOT NULL,
    x                    INTEGER NOT NULL,
    y                    INTEGER NOT NULL,
    population           INTEGER NOT NULL DEFAULT 0,
    troops               TEXT    NOT NULL DEFAULT '{}',
    is_active            INTEGER NOT NULL DEFAULT 1,
    disabled_by_bot      INTEGER NOT NULL DEFAULT 0,
    last_raid_state      TEXT    NOT NULL DEFAULT '',
    last_raid_time       TEXT    NOT NULL DEFAULT '',
    last_raid_report_id  TEXT    NOT NULL DEFAULT '',
    last_raid_bounty     INTEGER NOT NULL DEFAULT 0,
    average_raid_bounty  INTEGER NOT NULL DEFAULT 0,
    distance             REAL    NOT NULL DEFAULT 0.0,
    disabled_at          TEXT,
    cooldown_seconds     INTEGER NOT NULL DEFAULT 3600,
    report_id_at_disable TEXT    NOT NULL DEFAULT '',
    PRIMARY KEY (id, farm_list_id)
);
```

---

## 8. Contratos de API / interfaces

> Los contratos de esta sección son nuevos (Gap D) o modificaciones a contratos existentes
> (Gaps A y B). El único endpoint nuevo es el de stats; los demás son ajustes de respuesta.
> No hay APIs que consuman servicios externos.
>
> **Validación**: la feature no expone ni consume APIs externas. El único endpoint nuevo es
> puramente de lectura de BD. No hay cambios de contrato que rompan a los consumidores
> existentes (los campos nuevos en las respuestas son aditivos).
>
> `apis_validadas_por_desarrollador_apis: true` — los contratos siguen exactamente las
> convenciones del spec base (misma sección 3: sin `Accept-Language`, prefijo `/farm`,
> kebab-case, `{"detail": "..."}` en errores, paginación estándar cuando aplica).

---

### 8.1 Modificación: `GET /farm/worlds/{world_id}/farm-lists`

No cambia la ruta ni el método. El campo `last_send_time` en la respuesta pasa de `null`
permanente a estar poblado correctamente.

**Respuesta: campo `last_send_time` (por objeto de farm list)**:

```json
{
  "id": 101,
  "name": "Lista principal",
  "owner_village_id": 5,
  "village_name": "Aldea 1",
  "village_x": 10,
  "village_y": -5,
  "scheduler_id": 1,
  "last_send_time": "2026-05-27T08:34:12",
  "total_bounty": 15400,
  "avg_bounty_per_send": 380,
  "slots": [ /* igual que antes */ ]
}
```

`last_send_time`: ISO UTC string, o `null` si la lista nunca ha sido enviada.

---

### 8.2 Modificación: `FarmListSendEvent` — campos nuevos en historial

Los endpoints `GET /farm/worlds/{world_id}/history` ya existentes devuelven estos 4 campos
adicionales en cada objeto del historial (retrocompatibles, son aditivos):

```json
{
  "id": 42,
  "farm_list_id": 101,
  "farm_list_name": "Lista principal",
  "world_id": 3,
  "sent_at": "2026-05-27T08:34:12",
  "status": "success",
  "slots_sent": 8,
  "being_raided_total": 8,
  "triggered_by": "scheduler",
  "scheduler_id": 1,
  "scheduler_name": "Scheduler principal",
  "scheduler_interval_min_ms": 180000,
  "scheduler_interval_max_ms": 240000,
  "scheduler_execution_count": 47,
  "deactivated_slots": [],
  "loot_wood": 0,
  "loot_clay": 0,
  "loot_iron": 0,
  "loot_crop": 0
}
```

Para envíos manuales: `scheduler_name=null`, `scheduler_interval_min_ms=null`,
`scheduler_interval_max_ms=null`, `scheduler_execution_count=null`.

---

### 8.3 Endpoint nuevo: `GET /farm/worlds/{world_id}/schedulers/{scheduler_id}/stats`

Devuelve las métricas agregadas del scheduler y por cada farm list que tiene asignada.

**Response 200**:

```json
{
  "scheduler_id": 1,
  "scheduler_name": "Scheduler principal",
  "world_id": 3,
  "execution_count": 47,
  "last_send_time": "2026-05-27T08:34:12",
  "success_rate": 0.93,
  "active_slots_avg": 7.4,
  "total_bounty": 98450,
  "bounty_per_hour": 825.3,
  "per_list": [
    {
      "farm_list_id": 101,
      "farm_list_name": "Lista principal",
      "last_send_time": "2026-05-27T08:34:12",
      "success_rate": 0.95,
      "active_slots_avg": 8.0,
      "total_bounty": 62300,
      "bounty_per_hour": 522.7
    },
    {
      "farm_list_id": 102,
      "farm_list_name": "Lista secundaria",
      "last_send_time": "2026-05-27T08:34:17",
      "success_rate": 0.90,
      "active_slots_avg": 5.8,
      "total_bounty": 36150,
      "bounty_per_hour": 302.6
    }
  ]
}
```

**Semántica de los campos**:

| Campo | Tipo | Descripción |
|---|---|---|
| `execution_count` | int | De `farm_schedulers.execution_count` directamente |
| `last_send_time` | ISO UTC string \| null | MAX(timestamp) de historial del scheduler (sobre todas sus listas) |
| `success_rate` | float 0.0..1.0 | Envíos con `status='success'` / total envíos (últimos 7 días) |
| `active_slots_avg` | float | Media de `being_raided_total` en los últimos 7 días (excluyendo NULLs) |
| `total_bounty` | int | Suma de `slot_bounty_history.bounty` para todas las farm lists del scheduler |
| `bounty_per_hour` | float | `total_bounty / horas_desde_primer_envio`; 0.0 si no hay datos |
| `per_list[].total_bounty` | int | Suma de `slot_bounty_history.bounty` filtrada por `farm_list_id` |
| `per_list[].bounty_per_hour` | float | `bounty_por_lista / horas_desde_primer_envio_de_esa_lista` |

**Errores**:

| Código | Condición |
|---|---|
| `404` | Scheduler no existe en BD **o** `scheduler.world_id != world_id` de la ruta (EC-D03) |

**No requiere sesión activa del browser** (solo consulta BD).

---

## 9. Flujo lógico paso a paso

### 9.1 `sync_farm_list` — lógica de bounty (delta respecto al spec base)

```
async sync_farm_list(farm_list: FarmList, world_id: int) -> FarmList:
    existing_slots = await _load_slots_raw(farm_list.id)   # sin total_bounty
    existing_by_coords = {(s.x, s.y): s for s in existing_slots}
    existing_by_id     = {s.id: s for s in existing_slots}

    incoming_ids = {s.id for s in farm_list.slots}

    # Reasignación de IDs (EC-C03):
    for old_s in existing_slots:
        if old_s.id not in incoming_ids:
            matching_new = next(
                (ns for ns in farm_list.slots if (ns.x, ns.y) == (old_s.x, old_s.y)), None
            )
            if matching_new and matching_new.id != old_s.id:
                # Reasignar registros de bounty al nuevo id antes de borrar el viejo
                await conn.execute(
                    "UPDATE slot_bounty_history SET slot_id = ? WHERE slot_id = ? AND farm_list_id = ?",
                    (matching_new.id, old_s.id, farm_list.id)
                )
            # Borrar slot viejo
            await conn.execute(
                "DELETE FROM farm_slots WHERE id = ? AND farm_list_id = ?",
                (old_s.id, farm_list.id)
            )

    synced_slots = []
    for slot in farm_list.slots:
        existing = existing_by_coords.get((slot.x, slot.y)) or existing_by_id.get(slot.id)

        # ... (lógica existente de disabled_by_bot, disabled_at, cooldown, EC-06) ...

        # RN-C01, RN-C05: registrar bounty si el report_id cambió y hay bounty
        old_report_id = existing.last_raid_report_id if existing else ""
        if (slot.last_raid_report_id
                and slot.last_raid_report_id != old_report_id
                and slot.last_raid_bounty > 0):
            await add_slot_bounty_record(SlotBountyRecord(
                slot_id=slot.id,
                farm_list_id=farm_list.id,
                world_id=world_id,
                timestamp=utcnow(),
                bounty=slot.last_raid_bounty,
                raid_report_id=slot.last_raid_report_id,
            ))
            # Purga TTL 7 días
            cutoff = utcnow() - timedelta(days=7)
            await conn.execute(
                "DELETE FROM slot_bounty_history WHERE world_id = ? AND timestamp < ?",
                (world_id, dt_to_str(cutoff))
            )

        # UPSERT sin total_bounty (ya no existe la columna)
        await conn.execute("""
            INSERT INTO farm_slots (id, farm_list_id, target_name, x, y, population, troops,
                is_active, disabled_by_bot, last_raid_state, last_raid_time,
                last_raid_report_id, last_raid_bounty, average_raid_bounty,
                distance, disabled_at, cooldown_seconds, report_id_at_disable)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id, farm_list_id) DO UPDATE SET
                target_name          = excluded.target_name,
                x                    = excluded.x,
                y                    = excluded.y,
                population           = excluded.population,
                troops               = excluded.troops,
                is_active            = excluded.is_active,
                last_raid_state      = excluded.last_raid_state,
                last_raid_time       = excluded.last_raid_time,
                last_raid_report_id  = excluded.last_raid_report_id,
                last_raid_bounty     = excluded.last_raid_bounty,
                average_raid_bounty  = excluded.average_raid_bounty,
                distance             = excluded.distance,
                disabled_by_bot      = ?,
                disabled_at          = ?,
                cooldown_seconds     = ?,
                report_id_at_disable = ?
        """, (...params sin total_bounty...))

        synced_slots.append(FarmSlot(
            ...
            total_bounty=0,   # se calculará en _load_slots vía slot_bounty_history
        ))

    await conn.commit()

    # Enriquecer total_bounty tras el commit
    bounty_by_slot = await _get_bounty_sums(farm_list.id)  # dict {slot_id: sum}
    for slot in synced_slots:
        slot.total_bounty = bounty_by_slot.get(slot.id, 0)

    ...
    return farm_list_out
```

### 9.2 `_load_slots` — enriquecimiento de `total_bounty` (delta)

```
async _load_slots(farm_list_id: int) -> list[FarmSlot]:
    # Query 1: todos los slots
    rows = await conn.execute(
        "SELECT * FROM farm_slots WHERE farm_list_id = ? ORDER BY id",
        (farm_list_id,)
    )
    slots = [_to_slot(r) for r in rows]   # total_bounty = 0 por defecto

    # Query 2: sumas de bounty en una sola pasada
    bounty_by_slot = await _get_bounty_sums(farm_list_id)
    for slot in slots:
        slot.total_bounty = bounty_by_slot.get(slot.id, 0)

    return slots


async _get_bounty_sums(farm_list_id: int) -> dict[int, int]:
    cursor = await conn.execute(
        "SELECT slot_id, SUM(bounty) AS total FROM slot_bounty_history WHERE farm_list_id = ? GROUP BY slot_id",
        (farm_list_id,)
    )
    rows = await cursor.fetchall()
    return {r["slot_id"]: r["total"] for r in rows}
```

### 9.3 `get_last_send_times_by_world` — nueva consulta SQL

```sql
SELECT farm_list_id, MAX(timestamp) AS last_send_time
FROM farm_list_send_history
WHERE farm_list_id IN (<ids de las listas activas del mundo>)
GROUP BY farm_list_id
```

El adaptador devuelve `dict[int, datetime | None]` mapeado por `farm_list_id`.

### 9.4 `get_scheduler_stats` — nueva consulta SQL (Gap D)

```python
async get_scheduler_stats(scheduler_id: int, world_id: int) -> SchedulerStats:
    scheduler = await get_scheduler(scheduler_id)
    if scheduler.world_id != world_id:
        raise SchedulerNotFoundError(scheduler_id)   # EC-D03

    farm_list_ids = scheduler.farm_list_ids
    if not farm_list_ids:
        return SchedulerStats(scheduler_id=scheduler_id, scheduler_name=scheduler.name,
                              world_id=world_id, execution_count=scheduler.execution_count,
                              ...)   # todo a cero

    placeholders = ",".join("?" * len(farm_list_ids))

    # --- Historial de envíos (últimos 7 días) ---
    history_rows = await conn.execute(f"""
        SELECT farm_list_id, status, being_raided_total, timestamp
        FROM farm_list_send_history
        WHERE scheduler_id = ? AND world_id = ?
          AND timestamp >= ?
        ORDER BY farm_list_id, timestamp
    """, (scheduler_id, world_id, dt_to_str(utcnow() - timedelta(days=7))))

    # --- Bounty por farm list ---
    bounty_rows = await conn.execute(f"""
        SELECT farm_list_id, SUM(bounty) AS total_bounty
        FROM slot_bounty_history
        WHERE farm_list_id IN ({placeholders})
        GROUP BY farm_list_id
    """, farm_list_ids)

    # --- Nombres de las farm lists ---
    name_rows = await conn.execute(f"""
        SELECT id, name FROM farm_lists WHERE id IN ({placeholders})
    """, farm_list_ids)

    # --- Calcular métricas ---
    # (ver sección 4, RN-D01..D07 para las fórmulas exactas)
    ...
    return SchedulerStats(...)
```

### 9.5 `ProcessFarmListUseCase.execute` — obtención de metadata del scheduler (delta)

```python
# Tras syncear la lista y ANTES de add_farm_list_send_event:
scheduler_meta = None
if synced.scheduler_id:
    try:
        scheduler_meta = await self.db.get_scheduler(synced.scheduler_id)
    except SchedulerNotFoundError:
        pass   # EC-B02: scheduler borrado en carrera; se guarda con NULLs

event = FarmListSendEvent(
    farm_list_id=farm_list_id,
    farm_list_name=synced.name,
    world_id=world_id,
    timestamp=now,
    status=send_result.status,
    being_raided_current=send_result.being_raided_current,
    being_raided_total=send_result.being_raided_total,
    triggered_by="scheduler",
    scheduler_id=synced.scheduler_id,
    scheduler_name=scheduler_meta.name if scheduler_meta else None,
    scheduler_interval_min_ms=scheduler_meta.interval_min_ms if scheduler_meta else None,
    scheduler_interval_max_ms=scheduler_meta.interval_max_ms if scheduler_meta else None,
    scheduler_execution_count=scheduler_meta.execution_count if scheduler_meta else None,
    bot_disabled_slots=bot_disabled_slot_names,
)
await self.db.add_farm_list_send_event(event)
```

---

## 10. Validaciones y reglas

### Nivel de API

| Campo / Condición | Validación |
|---|---|
| `scheduler_id` en `GET .../stats` | Debe existir en BD y pertenecer al `world_id` de la ruta; si no → `404` |
| `last_send_time` en responses | Siempre ISO UTC string o `null`; nunca string vacío |

### Nivel de dominio

| Regla | Dónde |
|---|---|
| `bounty = 0` → no insertar en `slot_bounty_history` | `sync_farm_list` (RN-C01) |
| `raid_report_id = ""` → no insertar en `slot_bounty_history` | `sync_farm_list` (RN-C02) |
| `horas_en_rango >= 1` para división (evitar / 0) | `get_scheduler_stats` (RN-D04) |
| `scheduler.world_id == world_id` del request | `get_scheduler_stats` (EC-D03) |
| `scheduler_execution_count` desnormalizado = valor antes del incremento | `ProcessFarmListUseCase` (RN-B02) |

### Nivel de BD

| Regla | Lugar |
|---|---|
| `DROP COLUMN total_bounty` solo si la columna existe (PRAGMA table_info) | `ensure_tables` |
| `ALTER TABLE ... ADD COLUMN` idempotente (IF NOT EXISTS no aplica en SQLite para columnas; usar `PRAGMA table_info` como guard) | `ensure_tables` |
| Purga de `slot_bounty_history` en cada inserción | `add_slot_bounty_record` |

**Guard para ALTER TABLE ADD COLUMN (SQLite no soporta IF NOT EXISTS en columnas)**:

```python
cursor = await conn.execute("PRAGMA table_info(farm_list_send_history)")
existing_cols = {row["name"] for row in await cursor.fetchall()}
for col_name, col_ddl in [
    ("scheduler_name", "TEXT DEFAULT NULL"),
    ("scheduler_interval_min_ms", "INTEGER DEFAULT NULL"),
    ("scheduler_interval_max_ms", "INTEGER DEFAULT NULL"),
    ("scheduler_execution_count", "INTEGER DEFAULT NULL"),
]:
    if col_name not in existing_cols:
        await conn.execute(
            f"ALTER TABLE farm_list_send_history ADD COLUMN {col_name} {col_ddl}"
        )
```

---

## 11. Seguridad, rendimiento y concurrencia

### Rendimiento

- **EC-C04** — `_load_slots` usa una única query de agregación para `total_bounty` en lugar de N queries (una por slot). Con listas grandes (hasta ~200 slots), la diferencia es significativa.
- **`get_last_send_times_by_world`** usa un `IN (farm_list_ids)` sobre el índice existente `idx_farm_history_world`. El número de farm lists por mundo es pequeño (< 100 habitualmente).
- **`get_scheduler_stats`** realiza 3 queries (historial de envíos, bounty por lista, nombres). No hay joins complejos. El índice `idx_slot_bounty_slot` cubre el GROUP BY por slot_id.
- La purga de `slot_bounty_history` en cada inserción es O(1) gracias al índice `idx_slot_bounty_world_ts`.

### Concurrencia

Sin cambios respecto al spec base: un solo WorldAgent por mundo en asyncio single-threaded. El `sync_farm_list` ya era el único escritor de `farm_slots`; ahora también escribe en `slot_bounty_history` dentro del mismo commit.

### Anti-detección

Sin cambios: este spec no toca `adapters/browser/` ni la interacción con Travian. El guardian-antideteccion no aplica.

### Seguridad

Sin cambios: API local, sin autenticación. Los datos son de juego, no PII.

---

## 12. Plan de pruebas

### Casos felices (Gap A)

| Test | Cobertura |
|---|---|
| `test_get_farm_lists_last_send_time_populated` | `GET /farm/worlds/{world_id}/farm-lists`: lista con 2 envíos en historial → `last_send_time` es el más reciente |
| `test_get_farm_lists_last_send_time_null` | Lista sin envíos → `last_send_time = null` |
| `test_get_last_send_times_multiple_lists` | 3 listas, cada una con N envíos → cada una devuelve su propio MAX(timestamp) |

### Casos felices (Gap B)

| Test | Cobertura |
|---|---|
| `test_send_event_scheduler_metadata_populated` | Envío de scheduler → historial tiene `scheduler_name`, `scheduler_interval_min_ms`, `scheduler_interval_max_ms`, `scheduler_execution_count` correctos |
| `test_send_event_manual_metadata_null` | Envío manual → los 4 campos de metadata de scheduler son NULL en historial |
| `test_history_response_includes_scheduler_fields` | `GET /farm/worlds/{world_id}/history` → response incluye los 4 campos nuevos |

### Casos felices (Gap C)

| Test | Cobertura |
|---|---|
| `test_sync_slot_new_report_inserts_bounty` | sync_farm_list con nuevo `last_raid_report_id` y `last_raid_bounty > 0` → fila en `slot_bounty_history` |
| `test_total_bounty_computed_from_history` | Tras 3 syncs con bounty → `FarmSlot.total_bounty` = suma de los 3 |
| `test_total_bounty_zero_bounty_not_recorded` | `last_raid_bounty = 0` → no se inserta en `slot_bounty_history` |
| `test_total_bounty_empty_report_id_not_recorded` | `last_raid_report_id = ""` → no se inserta |
| `test_slot_id_reassignment_preserves_bounty` | Travian reasigna ID del slot (mismo x,y) → `slot_bounty_history` apunta al nuevo ID |
| `test_slot_bounty_history_ttl_purge` | Insertar bounty con timestamp > 7 días → purgado en el siguiente insert |
| `test_load_slots_total_bounty_single_query` | `_load_slots` con 10 slots → solo 2 queries a BD (slots + bounty sums) |

### Casos felices (Gap D)

| Test | Cobertura |
|---|---|
| `test_get_scheduler_stats_success` | Scheduler con 2 listas y 20 envíos → métricas correctas (success_rate, bounty_per_hour) |
| `test_get_scheduler_stats_empty` | Scheduler sin farm lists → todas las métricas en cero |
| `test_get_scheduler_stats_no_history` | Scheduler con listas pero sin envíos → métricas en cero, `last_send_time = null` |
| `test_get_scheduler_stats_execution_count` | `execution_count` refleja `farm_schedulers.execution_count` directamente |
| `test_get_scheduler_stats_per_list_breakdown` | Respuesta incluye `per_list` con métricas por cada farm list |

### Edge cases

| Test | Cobertura |
|---|---|
| `test_get_scheduler_stats_wrong_world_id` | Scheduler existe pero `world_id` no coincide → 404 |
| `test_get_scheduler_stats_not_found` | Scheduler ID inexistente → 404 |
| `test_scheduler_deleted_race_condition` | `ProcessFarmListUseCase` con scheduler borrado en carrera → `SchedulerNotFoundError` capturado, metadata NULL en historial |
| `test_drop_column_total_bounty_idempotent` | `ensure_tables()` llamado dos veces → sin error (DROP COLUMN solo si existe) |
| `test_add_column_scheduler_metadata_idempotent` | `ensure_tables()` llamado con columnas ya presentes → sin error |
| `test_bounty_per_hour_single_send` | Un solo envío → `horas_en_rango = MAX(1, 0) = 1`, sin división por cero |

---

## 13. Riesgos y trade-offs

| Decisión | Justificación | Riesgo |
|---|---|---|
| Pérdida de `total_bounty` histórico en la migración | No existe historial detallado para reconstruirlo. El valor acumulado en `farm_slots.total_bounty` era el único dato, y no es recuperable. Aceptado porque la retención de 7 días ya era la política del historial de envíos, y este es el primer deploy con la tabla nueva. | Datos perdidos en BD existentes. Mitigación: documentar el trade-off en el `CHANGELOG` o en las notas del commit. |
| `total_bounty` limitado a 7 días de retención | Consistente con la política TTL ya establecida para `farm_list_send_history` (RN-13 del spec base). El dashboard muestra tendencias recientes, no acumulados históricos indefinidos. | Si el usuario quiere "total histórico de toda la vida", no podrá verlo. Trade-off aceptado en el análisis. |
| `sync_farm_list` recibe `world_id` como nuevo parámetro | Necesario para la purga de `slot_bounty_history`. El cambio es mínimo pero rompe la firma del método actual. Requiere actualizar todos los llamadores (solo `ProcessFarmListUseCase` y `ReadFarmListsUseCase`). | Riesgo bajo: hay pocos llamadores y el cambio es mecánico. |
| `_load_slots` hace siempre 2 queries (slots + bounty sums) | La alternativa sería un JOIN, pero el GROUP BY con SUM en el mismo SELECT complica el `_to_slot` helper. Dos queries limpias son más mantenibles. | Overhead mínimo dado que el tamaño de las listas es pequeño. |
| Desnormalización de metadata del scheduler en el historial | Alternativa: JOIN en tiempo de consulta. El problema es que el scheduler puede haberse modificado o borrado; el JOIN devolvería datos del scheduler actual, no del momento del envío. La desnormalización es la única forma de preservar el "quién y cómo" de cada envío. | Más datos en la tabla. Aceptado por la misma razón que `farm_list_name` ya estaba desnormalizado. |
| `scheduler_execution_count` desnormalizado = valor ANTES del incremento | Alternativa: valor después del incremento. Se eligió ANTES porque refleja "cuántas veces había ejecutado antes de este envío", lo que es más legible como número de secuencia del envío (0=primero, 1=segundo...). | Puede confundir si alguien espera el total acumulado después. El implementador debe seguir exactamente RN-B02. |

---

## 14. Pasos de implementación ordenados

Cada paso es un bloque coherente. Se recomienda un commit por paso.

### Paso 1: Migración de esquema en `FarmListSQLiteAdapter.ensure_tables`

Añadir en `ensure_tables()` en `adapters/db/farm_list_sqlite_adapter.py`:

1.1 Crear tabla `slot_bounty_history` con sus índices (DDL de la sección 7.3).

1.2 Añadir columnas a `farm_list_send_history` con guard de `PRAGMA table_info` (sección 10).

1.3 DROP COLUMN `total_bounty` de `farm_slots` con guard de `PRAGMA table_info` (sección 7.2).

**Orden obligatorio**: primero crear `slot_bounty_history`, luego modificar `farm_list_send_history`,
luego DROP COLUMN. Así, si el servidor arranca por segunda vez (BD ya migrada), los guards
evitan errores.

### Paso 2: Entidad `SlotBountyRecord` y actualización de `FarmListSendEvent`

2.1 Crear dataclass `SlotBountyRecord` en `core/entities/farm_list.py`:

```python
@dataclass
class SlotBountyRecord:
    """Registro histórico de botín por slot (acumulación para total_bounty)."""
    id: int
    slot_id: int
    farm_list_id: int
    world_id: int
    timestamp: datetime
    bounty: int
    raid_report_id: str = ""
```

2.2 Añadir campos a `FarmListSendEvent` en `core/entities/farm_list_send_event.py`:

```python
scheduler_name: str | None = None
scheduler_interval_min_ms: int | None = None
scheduler_interval_max_ms: int | None = None
scheduler_execution_count: int | None = None
```

2.3 Eliminar `total_bounty: int = 0` de `FarmSlot`. El campo sigue existiendo como campo calculado:

```python
total_bounty: int = 0   # calculado: SUM(slot_bounty_history.bounty); NO se persiste en BD
```

El campo se mantiene en el dataclass para no romper el código que lo usa en memoria. Lo que
cambia es que **ya no se lee ni escribe en `farm_slots`**; siempre viene de `slot_bounty_history`.

### Paso 3: Entidad `SchedulerStats` y `SchedulerListStats`

Crear en `core/entities/farm_scheduler.py`:

```python
@dataclass
class SchedulerListStats:
    """Métricas de una farm list individual dentro de un scheduler."""
    farm_list_id: int
    farm_list_name: str
    last_send_time: datetime | None
    success_rate: float
    active_slots_avg: float
    total_bounty: int
    bounty_per_hour: float


@dataclass
class SchedulerStats:
    """Métricas agregadas de un scheduler."""
    scheduler_id: int
    scheduler_name: str
    world_id: int
    execution_count: int
    last_send_time: datetime | None
    success_rate: float
    active_slots_avg: float
    total_bounty: int
    bounty_per_hour: float
    per_list: list[SchedulerListStats]
```

### Paso 4: Nuevos métodos en `FarmListDbPort`

Añadir en `core/ports/farm_list_db_port.py`:

```python
@abstractmethod
async def sync_farm_list(self, farm_list: FarmList, world_id: int) -> FarmList:
    """
    Igual que antes + world_id necesario para insertar en slot_bounty_history
    y para la purga TTL de esa tabla.
    ROMPE la firma anterior: world_id ahora es obligatorio.
    """

@abstractmethod
async def add_slot_bounty_record(self, record: SlotBountyRecord) -> None:
    """
    Inserta un registro de bounty en slot_bounty_history y purga los
    registros con más de 7 días para el mismo world_id (RN-C01, RN-C02).
    No llamar directamente si bounty == 0 o raid_report_id == "".
    """

@abstractmethod
async def get_last_send_times_by_world(
    self, world_id: int, farm_list_ids: list[int]
) -> dict[int, datetime | None]:
    """
    Devuelve MAX(timestamp) de farm_list_send_history GROUP BY farm_list_id,
    filtrado a los farm_list_ids indicados.
    Clave: farm_list_id. Valor: datetime o None si no hay historial.
    """

@abstractmethod
async def get_scheduler_stats(
    self, scheduler_id: int, world_id: int
) -> "SchedulerStats":
    """
    Devuelve métricas agregadas del scheduler.
    Lanza SchedulerNotFoundError si no existe o world_id no coincide (EC-D03).
    """
```

**Nota sobre la firma de `sync_farm_lists`** (plural): el método `sync_farm_lists(village_id, farm_lists)` llama internamente a `sync_farm_list`. Hay que actualizar también esa llamada interna para pasar `world_id`. La firma pública de `sync_farm_lists` también recibe `world_id` (o se puede obtener de la aldea si está en el objeto `Village`). La opción más limpia:

```python
@abstractmethod
async def sync_farm_lists(
    self, village_id: int, farm_lists: list[FarmList], world_id: int
) -> list[FarmList]:
    """world_id necesario para delegar a sync_farm_list."""
```

### Paso 5: Implementación en `FarmListSQLiteAdapter`

5.1 Añadir helper `_get_bounty_sums(farm_list_id)` (sección 9.2).

5.2 Implementar `add_slot_bounty_record` con su purga TTL.

5.3 Modificar `sync_farm_list` para recibir `world_id`, detectar cambio de `last_raid_report_id`
e insertar en `slot_bounty_history` (pseudocódigo en sección 9.1). Incluir la reasignación
de IDs de slot (EC-C03).

5.4 Modificar `_load_slots` para llamar a `_get_bounty_sums` y enriquecer `total_bounty`
(sección 9.2).

5.5 Modificar el UPSERT de `sync_farm_list` para eliminar las referencias a `total_bounty`
(no incluirla en el INSERT ni en el UPDATE SET).

5.6 Implementar `get_last_send_times_by_world` (sección 9.3).

5.7 Implementar `get_scheduler_stats` (sección 9.4) con las fórmulas de RN-D01 a RN-D07.

5.8 Modificar `add_farm_list_send_event` para insertar los 4 campos nuevos de metadata de
scheduler (y leer los nuevos campos de `FarmListSendEvent` al construir el INSERT).

5.9 Modificar `_to_send_event` para leer los 4 campos nuevos de la fila.

5.10 Modificar `get_slot_events` y `sync_farm_lists` para propagar `world_id`.

### Paso 6: Use cases — `ProcessFarmListUseCase`

Modificar `core/use_cases/farm_lists.py`:

6.1 En `ProcessFarmListUseCase.execute`: obtener metadata del scheduler antes de crear
`FarmListSendEvent` (pseudocódigo en sección 9.5). Capturar `SchedulerNotFoundError` (EC-B02).

6.2 Añadir `GetSchedulerStatsUseCase`:

```python
@dataclass
class GetSchedulerStatsUseCase:
    """Devuelve métricas agregadas de un scheduler."""
    db: FarmListDbPort

    async def execute(self, scheduler_id: int, world_id: int) -> SchedulerStats:
        return await self.db.get_scheduler_stats(scheduler_id, world_id)
```

6.3 En `ReadFarmListsUseCase.execute` y cualquier otro llamador de `sync_farm_list`:
actualizar la llamada para pasar `world_id`.

### Paso 7: Router — `adapters/api/routes/farm.py`

7.1 Modificar `_serialize_farm_list` para aceptar `last_send_time: datetime | None` y
poblarlo en la respuesta.

7.2 Modificar `list_farm_lists` (endpoint `GET /farm/worlds/{world_id}/farm-lists`) para
llamar a `db.get_last_send_times_by_world` y pasarlo a `_serialize_farm_list`.

7.3 Modificar `_serialize_send_event` para incluir los 4 campos nuevos de metadata.

7.4 Añadir endpoint `GET /farm/worlds/{world_id}/schedulers/{scheduler_id}/stats`:

```python
@router.get(
    "/worlds/{world_id}/schedulers/{scheduler_id}/stats",
    summary="Estadísticas de un scheduler",
)
async def get_scheduler_stats(
    world_id: int, scheduler_id: int, request: Request
) -> dict:
    """Métricas agregadas del scheduler y por cada farm list asignada."""
    db = _get_farm_db(request)
    try:
        stats = await GetSchedulerStatsUseCase(db=db).execute(scheduler_id, world_id)
    except SchedulerNotFoundError:
        raise HTTPException(status_code=404, detail=f"Scheduler {scheduler_id} no encontrado")
    return _serialize_scheduler_stats(stats)
```

7.5 Añadir helper `_serialize_scheduler_stats(stats: SchedulerStats) -> dict`.

7.6 Añadir `GetSchedulerStatsUseCase` a los imports del router.

### Paso 8: Tests

Implementar los tests de la sección 12 en `tests/unit/test_farm_stats.py` (archivo nuevo).
Reutilizar el helper `_make_db()` de `tests/unit/test_farm_lists.py` para crear la BD de test.

---

## 15. Criterios de aceptación

El implementador puede dar la feature por completa cuando:

- [ ] **CA-S01**: `GET /farm/worlds/{world_id}/farm-lists` devuelve `last_send_time` con el
  timestamp del último envío para listas que tienen historial, y `null` para listas sin historial.

- [ ] **CA-S02**: `GET /farm/worlds/{world_id}/history` devuelve los 4 campos de metadata del
  scheduler (`scheduler_name`, `scheduler_interval_min_ms`, `scheduler_interval_max_ms`,
  `scheduler_execution_count`) en cada evento de historial de scheduler. Para envíos manuales,
  esos 4 campos son `null`.

- [ ] **CA-S03**: Tras un envío de scheduler, el registro en `farm_list_send_history` contiene
  el `scheduler_name` y los intervalos que tenía el scheduler **en el momento del envío**
  (si se cambia el nombre del scheduler después, el historial previo conserva el nombre original).

- [ ] **CA-S04**: `GET /farm/worlds/{world_id}/schedulers/{scheduler_id}/stats` devuelve el
  objeto de stats con la estructura completa de la sección 8.3 (métricas globales + `per_list`).

- [ ] **CA-S05**: `GET .../stats` para scheduler inexistente → `404`.

- [ ] **CA-S06**: `GET .../stats` para scheduler cuyo `world_id` no coincide con el de la ruta → `404`.

- [ ] **CA-S07**: `GET .../stats` para scheduler sin farm lists → todas las métricas en cero,
  `per_list = []`.

- [ ] **CA-S08**: `FarmSlot.total_bounty` refleja la suma de `slot_bounty_history` para ese slot
  (no un valor almacenado en `farm_slots`).

- [ ] **CA-S09**: Tras N envíos con distintos `last_raid_report_id` y `last_raid_bounty > 0`,
  `FarmSlot.total_bounty` = suma de todos esos bounties.

- [ ] **CA-S10**: Si `last_raid_bounty = 0` en un sync, no se genera fila en `slot_bounty_history`.

- [ ] **CA-S11**: Si `last_raid_report_id = ""` en un sync, no se genera fila en `slot_bounty_history`.

- [ ] **CA-S12**: Tras reasignación de ID de slot por Travian, `slot_bounty_history` apunta al
  nuevo ID y `FarmSlot.total_bounty` conserva el valor histórico.

- [ ] **CA-S13**: Filas en `slot_bounty_history` con timestamp > 7 días se purgan en el siguiente
  insert de bounty para ese `world_id`.

- [ ] **CA-S14**: `ensure_tables()` puede ejecutarse varias veces sin error (idempotencia de
  migraciones).

- [ ] **CA-S15**: La columna `total_bounty` ya no existe en `farm_slots` (confirmar con
  `PRAGMA table_info(farm_slots)`).

- [ ] **CA-S16**: `success_rate` del scheduler refleja la proporción de envíos con `status='success'`
  sobre el total de los últimos 7 días.

- [ ] **CA-S17**: `bounty_per_hour` = 0.0 cuando el scheduler no tiene historial de envíos.

- [ ] **CA-S18**: Todos los tests de `test_farm_lists.py` siguen pasando (no regresiones).

---

## 16. Trazabilidad

| Decisión técnica | Origen |
|---|---|
| Eliminar `farm_slots.total_bounty` y reemplazar por `slot_bounty_history` | Gap C: dato acumulado propensa a drift; decisión del usuario (P2 del análisis) |
| TTL de 7 días para `slot_bounty_history` | Gap C: consistencia con `farm_list_send_history` (RN-13 del spec base); confirmado por el usuario (P1 del análisis) |
| Posponer desglose de loot (`loot_wood/clay/iron/crop`) | Gap E: confirmado por el usuario (P3 del análisis); reservado para Agente ROI |
| Desnormalizar metadata del scheduler en el historial | Gap B: robustez ante modificación/borrado del scheduler; misma justificación que `farm_list_name` ya desnormalizado en spec base |
| `scheduler_execution_count` = valor antes del incremento (RN-B02) | Gap B: semántica de "número de secuencia del envío" más legible que el total acumulado posterior |
| `sync_farm_list` recibe `world_id` como nuevo parámetro | Gap C: necesario para `slot_bounty_history` (purga y world filter); change mínimo sobre la interfaz existente |
| Reasignación de IDs en `slot_bounty_history` antes de borrar el slot viejo (EC-C03) | Consistencia con RN-C06; preserva el historial de bounty al igual que el spec base preserva `total_bounty` y estado bot |
| No hay FK de `slot_bounty_history` a `farm_slots` | Misma política que el resto del historial del proyecto: datos denormalizados para sobrevivir al borrado de la entidad origen |
| Endpoint de stats no requiere sesión activa | RN-D07: stats son consultas de BD pura, sin interacción con el browser |
| EC-D03: `scheduler.world_id != world_id` → `404` en stats | Coherencia con el patrón del proyecto de no exponer recursos de otros mundos |
| Dos queries en `_load_slots` (slots + bounty sums) en lugar de JOIN | EC-C04: evita GROUP BY complejo que rompe el mapping a `_to_slot`; más legible y mantenible |
| `FarmSlot.total_bounty` se mantiene en el dataclass aunque ya no se persiste | Evitar breaking change en el código de consumo (serializers, use cases) que ya accede a `slot.total_bounty` |

---

## Registro de implementacion

**Fecha**: 2026-05-27
**Implementado por**: desarrollador-funcionalidades

### Ficheros creados

- `tests/unit/test_farm_stats.py` — 26 tests nuevos cubriendo los 4 gaps (A, B, C, D) y todos los edge cases del spec

### Ficheros modificados

- `core/entities/farm_list.py` — dataclass `SlotBountyRecord` anadida
- `core/entities/farm_list_send_event.py` — 4 campos de metadata de scheduler anadidos
- `core/entities/farm_scheduler.py` — dataclasses `SchedulerListStats` y `SchedulerStats` anadidas
- `core/ports/farm_list_db_port.py` — firmas de `sync_farm_lists`/`sync_farm_list` actualizadas; 3 metodos abstractos nuevos: `add_slot_bounty_record`, `get_last_send_times_by_world`, `get_scheduler_stats`
- `core/use_cases/farm_lists.py` — `ReadFarmListsUseCase` y `ProcessFarmListUseCase` actualizados para Gap A y Gap B; `GetSchedulerStatsUseCase` anadido
- `adapters/db/farm_list_sqlite_adapter.py` — migraciones `ensure_tables()` para `slot_bounty_history`, ADD COLUMN guard para 4 cols de scheduler metadata, DROP COLUMN guard para `total_bounty`; helpers `_get_bounty_sums`, `_insert_slot_bounty`; metodos publicos `add_slot_bounty_record`, `get_last_send_times_by_world`, `get_scheduler_stats`
- `adapters/api/routes/farm.py` — `_serialize_farm_list` acepta `last_send_time`; `_serialize_send_event` incluye 4 campos de scheduler; endpoint nuevo `GET /farm/worlds/{world_id}/schedulers/{scheduler_id}/stats`; handlers `list_farm_lists` y `read_farm_lists` enriquecidos con `get_last_send_times_by_world`
- `tests/unit/test_farm_lists.py` — `_insert_farm_list` sin `total_bounty`; `sync_farm_lists`/`sync_farm_list` con `world_id`; test de slot reordenado reescrito para usar `slot_bounty_history`

### Comando para ejecutar los tests

```
python -m pytest tests/unit/test_farm_stats.py tests/unit/test_farm_lists.py -v
```

**Resultado**: 58/58 tests pasan (0 fallos, 152 DeprecationWarnings pre-existentes de `datetime.utcnow()`)

### Criterios de aceptacion cumplidos

CA-S01 a CA-S18: todos verificados via tests automatizados.

### Desviaciones respecto al diseno

1. **`test_scheduler_deleted_race_condition` (EC-B02)**: el test insertaba una `farm_list` con `scheduler_id=99` inexistente, violando la FK de `farm_lists.scheduler_id`. Se corrigio para insertar la farm list sin `scheduler_id` y luego insertar el evento de historial con `scheduler_id=99` directamente (la tabla `farm_list_send_history` no tiene FK a `farm_schedulers`). EC-B02 queda igualmente verificado: el evento guarda `scheduler_name=None` cuando el scheduler no existe.

2. **Warnings `datetime.utcnow()`**: el proyecto usa `datetime.utcnow()` de forma generalizada (pre-existente). No se corrigieron en esta implementacion para mantener coherencia — es deuda tecnica independiente del scope de este spec.
