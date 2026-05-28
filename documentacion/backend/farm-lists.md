# Farm Lists — Documentación técnica de código

Cubre todos los módulos que implementan la funcionalidad de "listas de vacas" (farm lists):
entidades de dominio, puerto de BD, adaptador SQLite, casos de uso y router FastAPI.

---

## Módulos documentados

| Fichero | Responsabilidad |
|---|---|
| `core/entities/farm_list.py` | Entidades de dominio: FarmSlot, FarmList, BotSlotStatus, SlotEvent, SlotBountyRecord |
| `core/entities/farm_list_send_event.py` | Entidad FarmListSendEvent (historial de envíos) |
| `core/entities/farm_scheduler.py` | Entidades FarmScheduler, SchedulerListStats, SchedulerStats |
| `core/ports/farm_list_db_port.py` | Puerto abstracto FarmListDbPort |
| `core/use_cases/farm_lists.py` | Casos de uso (toda la lógica de negocio) |
| `adapters/db/farm_list_sqlite_adapter.py` | Implementación concreta de FarmListDbPort sobre SQLite |
| `adapters/api/routes/farm.py` | Router FastAPI — endpoints bajo el prefijo `/farm` |

---

## 1. Entidades de dominio (`core/entities/`)

### 1.1 `FarmSlot`

**Qué hace.** Representa una aldea objetivo individual (coloquialmente "vaca") dentro de una farm list. Almacena tanto los datos que provienen del DOM de Travian (posición, nombre, tropas asignadas, resultado del último raid) como el estado que el bot gestiona de forma autónoma (flags de desactivación, cooldown, historial de reportes).

**Campos clave:**

| Campo | Tipo | Origen | Descripción |
|---|---|---|---|
| `id` / `farm_list_id` | int | DOM | PK compuesta en BD: un slot puede repetirse en distintas listas |
| `is_active` | bool | DOM | El usuario activó/desactivó la vaca en Travian |
| `disabled_by_bot` | bool | Bot | El bot la desactivó (pérdidas detectadas) — distinto de `is_active` |
| `last_raid_state` | str | DOM | Resultado del último raid: `"withoutLosses"`, `"withLosses"`, `"lost"`, etc. |
| `last_raid_report_id` | str | DOM | ID del informe de combate. Cambio de este ID = raid nuevo registrado |
| `last_raid_bounty` | int | DOM | Botín del último raid (recursos totales) |
| `average_raid_bounty` | int | DOM | Promedio calculado por Travian |
| `total_bounty` | int | BD calculado | Suma de `slot_bounty_history.bounty` (últimos 7 días). **No se persiste en `farm_slots`** — es un campo calculado en memoria al cargar el slot. Ver Gap C |
| `disabled_at` | datetime | Bot | Cuándo el bot desactivó la vaca (para calcular el cooldown) |
| `cooldown_seconds` | int | Bot | Duración del cooldown actual. Empieza en 3600 y se duplica con cada sonda fallida |
| `report_id_at_disable` | str | Bot | `last_raid_report_id` en el momento de la desactivación. Permite detectar si llegó un raid nuevo |

**Por qué existe `disabled_by_bot` separado de `is_active`.** Un slot desactivado manualmente por el usuario (`is_active=False`, `disabled_by_bot=False`) no debe ser tocado por el bot. Si el bot lo desactivara, sería incapaz de distinguirlo de los slots que él mismo ha gestionado. Los dos flags permiten una máquina de estados clara con cuatro combinaciones posibles.

**Impacto en negocio.** Es la unidad atómica del sistema de farmeo automático. Sin ella no hay modo de rastrear el estado individual de cada objetivo ni aplicar la lógica de cooldown y sondas.

---

### 1.2 `FarmList`

**Qué hace.** Agrupa un conjunto de `FarmSlot` bajo el mismo nombre y aldea propietaria. Refleja exactamente el concepto de "Farm list" de Travian: el jugador crea listas en Travian, el bot las lee y las gestiona.

**Campos transitorios (no persisten en BD):**
`village_name`, `village_data_id`, `village_x`, `village_y` — se populan en memoria al cargar la lista para evitar JOINs adicionales en los serializadores.

**Relación con `FarmScheduler`.** Una farm list puede estar asignada a cero o un scheduler (`scheduler_id`). Si está asignada, el scheduler la incluirá en sus ciclos de envío periódico. Si el scheduler se borra, `scheduler_id` queda en NULL (la lista sobrevive pero deja de enviarse automáticamente).

---

### 1.3 `BotSlotStatus`

**Qué hace.** Vista reducida de un `FarmSlot` orientada a monitoreo. Solo contiene los campos relevantes para el dashboard: si el bot la tiene desactivada, cuánto falta para el cooldown, y el resultado del último raid.

**Por qué existe separado de `FarmSlot`.** Cuando el dashboard necesita pintar el estado de todos los slots de un mundo, no necesita el JSON de tropas ni el botín acumulado. Una entidad de proyección reduce el volumen de datos y deja claro qué consulta es para monitoreo y cuál es para operación.

---

### 1.4 `SlotEvent`

**Qué hace.** Registro de un cambio de estado significativo de un slot. Los tipos de evento son:

| Valor | Significado |
|---|---|
| `LOSSES_DETECTED` | El bot detectó pérdidas y desactivó la vaca |
| `PROBE_SENT` | El bot envió una sonda (cooldown expirado, sin informe nuevo) |
| `REACTIVATED` | El bot reactivó la vaca (informe nuevo limpio) |
| `PROBE_CANCELLED` | El usuario canceló una sonda pendiente |

**Campos denormalizados.** `slot_name`, `farm_list_name` y `world_id` se guardan aunque el slot o la lista se hayan borrado después. La regla del proyecto es que el historial debe ser legible sin joins a entidades que pueden desaparecer.

---

### 1.5 `SlotBountyRecord`

**Qué hace.** Registro atómico de botín para un slot en un raid concreto. Se inserta en `slot_bounty_history` cada vez que `last_raid_report_id` cambia y `last_raid_bounty > 0`. La suma de todos los registros de un slot en los últimos 7 días es su `total_bounty`.

**Por qué existe en lugar de un campo acumulado.** El campo `farm_slots.total_bounty` era propenso a inconsistencias cuando Travian reasignaba IDs de slot (el contador quedaba huérfano). Al usar una tabla de historial con claves bien definidas, `total_bounty` pasa a ser siempre derivado y verificable. La contrapartida es que los datos acumulados anteriores al primer deploy con esta tabla se pierden (EC-C05, pérdida aceptada).

**TTL.** Los registros con más de 7 días se purgan automáticamente en cada inserción, para el mismo `world_id`. Esto limita el total a una ventana deslizante de una semana, coherente con el TTL del historial de envíos.

---

### 1.6 `FarmListSendEvent` (`core/entities/farm_list_send_event.py`)

**Qué hace.** Registro histórico de un envío de farm list. Captura el momento del envío, su resultado, cuántas tropas estaban raideando y qué slots desactivó el bot en ese ciclo.

**Campos de metadata de scheduler (Gap B).** Los campos `scheduler_name`, `scheduler_interval_min_ms`, `scheduler_interval_max_ms` y `scheduler_execution_count` se rellenan en el momento del envío con los valores actuales del scheduler. Si el scheduler se modifica o borra después, el historial conserva la configuración que ordenó ese envío. Son NULL si el envío fue manual.

**`scheduler_execution_count` = valor ANTES del incremento.** Esto es intencional: actúa como número de secuencia del envío (0 = primer disparo del scheduler, 1 = segundo, etc.), que es más legible que el contador posterior.

**Campos reservados (`loot_*`).** `loot_wood`, `loot_clay`, `loot_iron`, `loot_crop` existen en la entidad y en la BD pero siempre valen 0 por ahora. Están reservados para el futuro Agente ROI que calculará el desglose de recursos (Gap E, pospuesto).

---

### 1.7 `FarmScheduler`, `SchedulerListStats`, `SchedulerStats` (`core/entities/farm_scheduler.py`)

**`FarmScheduler`.** Define cuándo y con qué frecuencia se envía un grupo de farm lists. El intervalo es aleatorio en `[interval_min_ms, interval_max_ms]` para evitar patrones de tiempo detectables por Travian (regla de anti-detección RN-02). `farm_list_ids` es la lista de listas asignadas — cuando está vacía, el scheduler no hace nada al dispararse.

**`SchedulerListStats` / `SchedulerStats`.** Proyecciones de métricas calculadas en BD para el dashboard. No tienen ciclo de vida propio ni se persisten: solo existen como respuesta al endpoint de stats. Ver detalles de cálculo en la sección del adaptador SQLite.

---

## 2. Puerto de BD (`core/ports/farm_list_db_port.py`)

**Qué hace.** Define el contrato abstracto que debe cumplir cualquier implementación de persistencia de farm lists. Sigue el patrón Port & Adapter del proyecto: el `core/` solo habla con esta interfaz; nunca importa SQLite directamente.

**Por qué no extiende `DbPort`.** Decisión explícita del proyecto: `FarmListDbPort` es un puerto especializado con su propio contrato. Extender `DbPort` sería acoplamiento innecesario entre dos contratos que evolucionan a ritmos distintos.

**Grupos de métodos:**

| Grupo | Métodos clave | Propósito |
|---|---|---|
| Farm lists | `sync_farm_lists`, `sync_farm_list`, `get_farm_lists_by_*`, `get_farm_list_by_id` | Sincronización desde DOM y consultas |
| Slots | `get_slot_by_id`, `update_slot_flags`, `update_slot_cooldown_state`, `get_bot_status_slots` | Gestión del estado bot de cada vaca |
| Eventos de slot | `add_slot_event`, `get_slot_events` | Trazabilidad de cambios de estado |
| Schedulers | `create/get/update/delete_scheduler`, `get_schedulers_by_world`, `assign_farm_lists_to_scheduler`, `update_scheduler_run_state` | CRUD de schedulers |
| Historial de envíos | `add_farm_list_send_event`, `get_farm_list_send_history` | Registro de cada envío |
| Bounty por slot | `add_slot_bounty_record` | Gap C: historial de botín atómico |
| Consultas auxiliares | `get_last_send_times_by_world` | Gap A: último envío por lista |
| Stats | `get_scheduler_stats` | Gap D: métricas agregadas |

**`sync_farm_list` recibe `world_id`.** Este parámetro fue añadido en el Gap C: la lógica de inserción en `slot_bounty_history` necesita saber el `world_id` para filtrar la purga de TTL.

---

## 3. Adaptador SQLite (`adapters/db/farm_list_sqlite_adapter.py`)

### 3.1 Esquema de tablas

| Tabla | PK | Notas |
|---|---|---|
| `farm_schedulers` | `id` AUTOINCREMENT | FK a `worlds(id)` |
| `farm_lists` | `id` (del DOM) | FK a `villages(id)`, FK opcional a `farm_schedulers(id) ON DELETE SET NULL` |
| `farm_slots` | `(id, farm_list_id)` compuesta | FK a `farm_lists(id) ON DELETE CASCADE`. La PK compuesta refleja que Travian puede reusar IDs de slot entre listas distintas |
| `farm_list_send_history` | `id` AUTOINCREMENT | Sin FK (denormalizado). TTL 7 días |
| `slot_events` | `id` AUTOINCREMENT | Sin FK (denormalizado) |
| `slot_bounty_history` | `id` AUTOINCREMENT | Sin FK intencional (ver Gap C). TTL 7 días |

**Decisión de diseño: fechas como VARCHAR(30) ISO.** Las columnas de fecha en `farm_schedulers` (`last_run`, `next_run`) se almacenan como texto ISO, coherente con el bot de referencia. Los helpers `_dt_to_str` / `_str_to_dt` gestionan la conversión.

---

### 3.2 `ensure_tables()`

**Qué hace.** Crea las tablas e índices si no existen, y aplica las migraciones de esquema de forma idempotente. Se llama desde el `lifespan` de la aplicación FastAPI al arrancar.

**Migraciones incluidas:**
- Crea `slot_bounty_history` con sus índices (Gap C).
- Añade las 4 columnas de metadata de scheduler a `farm_list_send_history` con guard `PRAGMA table_info` (SQLite no soporta `IF NOT EXISTS` en `ALTER TABLE ADD COLUMN`).
- Elimina `farm_slots.total_bounty` si existe (requiere SQLite ≥ 3.35, disponible en Python 3.14).

**Impacto en negocio.** Una migración mal ejecutada podría perder datos. El guard de `PRAGMA table_info` garantiza que el `ALTER TABLE` solo se ejecuta si la columna no existe, haciendo el `ensure_tables` seguro en reinicios.

---

### 3.3 `sync_farm_lists` / `sync_farm_list` / `_sync_slots`

**`sync_farm_lists(village_id, farm_lists, world_id)`.** Sincroniza el snapshot completo de una aldea: borra las listas que ya no están en Travian, inserta/actualiza las que sí. Delega en `_sync_one_farm_list` para cada lista.

**`sync_farm_list(farm_list, world_id)`.** Sincroniza una sola lista leyendo su estado fresco del DOM. Delega en `_sync_slots`.

**`_sync_slots(farm_list, world_id)`.** El método más complejo del adaptador. Por cada slot entrante:

1. **Matching por coordenadas (x, y)** en lugar de por ID. Travian puede reasignar IDs cuando el usuario reordena sus listas; las coordenadas son invariantes.
2. **Preservación del estado bot.** Si el slot existía antes, conserva `disabled_by_bot`, `disabled_at`, `cooldown_seconds` y `report_id_at_disable`.
3. **EC-06.** Si el DOM devuelve `is_active=True` para un slot que el bot había desactivado (`disabled_by_bot=True`), el bot lo acepta: el usuario lo reactivó manualmente en Travian. Se resetea el estado bot.
4. **Gap C — inserción de bounty.** Si `last_raid_report_id` cambió respecto al valor en BD y `last_raid_bounty > 0`, inserta una fila en `slot_bounty_history` (con su purga TTL) dentro del mismo commit.
5. **EC-C03 — reasignación de IDs.** Si un slot con las mismas coordenadas tiene un ID nuevo (Travian lo reasignó), actualiza `slot_bounty_history` para apuntar al nuevo ID antes de borrar el slot antiguo.

**Enriquecimiento de `total_bounty`.** Tras el commit, llama a `_get_bounty_sums` para calcular la suma de bounty de cada slot y asignarla en memoria al `FarmSlot` retornado.

---

### 3.4 `_load_slots` / `_get_bounty_sums`

**`_load_slots(farm_list_id)`.** Carga todos los slots de una lista en dos queries: una para los slots y otra para las sumas de bounty agrupadas por `slot_id`. Esta separación es deliberada (EC-C04): un JOIN con GROUP BY en una sola query complica el helper `_to_slot` sin beneficio apreciable dado el tamaño de las listas.

**`_get_bounty_sums(farm_list_id)`.** Devuelve `{slot_id: SUM(bounty)}` desde `slot_bounty_history`. Una sola query de agregación para toda la lista.

---

### 3.5 `get_scheduler_stats(scheduler_id, world_id)`

**Qué hace.** Calcula métricas del scheduler a partir de tres queries:
1. Historial de envíos de los últimos 7 días del scheduler.
2. Bounty total por farm list desde `slot_bounty_history`.
3. Nombres de las farm lists del scheduler.

**Fórmulas de negocio:**

| Métrica | Fórmula |
|---|---|
| `success_rate` | `envíos_con_status='success' / total_envíos` (últimos 7 días) |
| `active_slots_avg` | Media de `being_raided_total` en el historial (excluyendo NULLs) |
| `total_bounty` | Suma de `slot_bounty_history.bounty` para todas las listas del scheduler |
| `bounty_per_hour` | `total_bounty / MAX(1, horas_desde_primer_envío)` |
| `execution_count` | Directo de `farm_schedulers.execution_count` — no se recalcula |

**EC-D03.** Si el `world_id` de la ruta no coincide con el `world_id` del scheduler en BD, lanza `SchedulerNotFoundError`. Esto evita que un cliente consulte recursos de otro mundo con un `scheduler_id` válido pero ajeno.

---

### 3.6 `add_farm_list_send_event`

**Qué hace.** Persiste un evento de envío y ejecuta la purga de TTL (7 días) para el mismo `world_id` en la misma transacción. La purga es `DELETE WHERE world_id = ? AND timestamp < <cutoff>`, usando el índice `idx_farm_history_world`.

**Por qué la purga está en el insert.** No hay un proceso de limpieza periódico separado. Hacer la purga en el momento de la escritura garantiza que la tabla no crece indefinidamente aunque el WorldAgent corra durante días.

---

## 4. Casos de uso (`core/use_cases/farm_lists.py`)

Toda la lógica de negocio de farm lists vive en este fichero. Los casos de uso no acceden directamente a SQLite ni al browser: solo hablan con los puertos.

### Constantes de negocio

```python
_GROUP_GAP_MIN_SECONDS = 2.0    # pausa mínima entre envíos del mismo scheduler
_GROUP_GAP_MAX_SECONDS = 5.0    # pausa máxima entre envíos del mismo scheduler
_BASE_COOLDOWN_SECONDS = 3600   # cooldown inicial al detectar pérdidas (1 hora)
_MAX_COOLDOWN_SECONDS  = 86_400 # cooldown máximo de sonda (24 horas)
```

Estas constantes definen el comportamiento de anti-detección y cooldown. **No deben estar en la capa de API ni en la BD.**

---

### 4.1 Helpers de evaluación de estado

| Función | Qué evalúa |
|---|---|
| `_won_without_losses(state)` | `"withoutLosses" in state` |
| `_had_losses(state)` | `"withLosses" in state` OR `"lost" in state` |
| `_has_new_raid(slot)` | `report_id_at_disable` presente y distinto de `last_raid_report_id` |
| `_cooldown_expired(slot)` | `disabled_at` presente y `elapsed >= cooldown_seconds` |

Estos helpers encapsulan las condiciones del string `last_raid_state` en un único lugar. Si Travian cambia los valores del DOM, solo hay que actualizar aquí.

---

### 4.2 `ReadFarmListsUseCase`

**Qué hace.** Orquesta la lectura desde Travian: navega a la plaza de reuniones, lee el DOM, empareja las listas con las aldeas de la BD por nombre, y sincroniza cada grupo.

**EC-01.** Si una aldea del DOM tiene `data_id > 0` pero no existe en BD, la crea automáticamente con `upsert_village`. Si `data_id == 0` (DOM incompleto), la omite con un warning.

**Impacto en negocio.** Es el punto de entrada para mantener la BD sincronizada con el estado real de Travian. Sin esta operación, el bot trabaja con datos obsoletos.

---

### 4.3 `ProcessFarmListUseCase`

**Qué hace.** El caso de uso más complejo: implementa el ciclo inteligente de envío de UNA farm list con detección de pérdidas, cooldown y sondas. Flujo:

1. Lee la lista fresca del DOM y sincroniza en BD.
2. Para cada slot, aplica la máquina de estados:

| Condición | Acción |
|---|---|
| `is_active=False`, `disabled_by_bot=False` | Slot desactivado manualmente — el bot no lo toca (RN-04) |
| `_had_losses` + no `disabled_by_bot` + no ya visto | Desactivar en Travian + iniciar cooldown BASE (RN-05) + evento LOSSES_DETECTED |
| `disabled_by_bot` + raid nuevo limpio | Reactivar en Travian + limpiar cooldown (RN-06) + evento REACTIVATED |
| `disabled_by_bot` + raid nuevo con pérdidas | Actualizar `report_id_at_disable` sin reactivar (RN-07) |
| `disabled_by_bot` + cooldown expirado + sin raid nuevo | Activar sonda: activar temporalmente en Travian (RN-08) |

3. Obtiene metadata del scheduler (Gap B) antes de crear el evento de envío.
4. Envía la farm list.
5. Desactiva las sondas y duplica su cooldown (`min(cooldown * 2, 86400s)`).

**Guard `losses_already_seen`.** Evita que el bot reaccione al mismo informe de pérdidas dos veces (si el ciclo se ejecuta antes de que llegue un nuevo informe).

---

### 4.4 `SendSchedulerGroupUseCase`

**Qué hace.** Procesa todas las farm lists de un scheduler en orden, con una pausa aleatoria de 2–5 segundos entre cada una (anti-detección, RN-03). El fallo de una lista individual (excepción) no detiene las demás.

---

### 4.5 `SendFarmListUseCase`

**Qué hace.** Envío manual de una farm list. A diferencia de `ProcessFarmListUseCase`, no ejecuta el ciclo de pérdidas/sondas: solo pulsa Start y registra el evento con `triggered_by="manual"`.

**Por qué existe separado.** El usuario puede querer enviar una lista puntualmente sin activar la lógica automática. Son dos operaciones semánticamente distintas.

---

### 4.6 `CancelProbeUseCase`

**Qué hace.** Cancela la sonda pendiente de un slot con dos modos distintos:

| Modo | Efecto |
|---|---|
| `deactivate` (default) | La vaca queda apagada indefinidamente como si el usuario la hubiera desactivado (`disabled_by_bot=False`). El bot no la gestionará más. Registra PROBE_CANCELLED |
| `send_now` | Expira el cooldown artificialmente para que el próximo ciclo del bot envíe la sonda. No registra evento |

**EC-16.** El endpoint valida que `disabled_by_bot=True` antes de llamar al use case. Si no hay sonda activa, devuelve 400.

---

### 4.7 Otros casos de uso

| Caso de uso | Qué hace |
|---|---|
| `GetFarmListsUseCase` | Lee las listas de BD y enriquece `village_name/x/y` para la UI |
| `ActivateSlotInTravianUseCase` | Activa en Travian + limpia `disabled_by_bot` + registra REACTIVATED si procedía |
| `DeactivateSlotInTravianUseCase` | Desactiva en Travian. No toca `disabled_by_bot` (desactivación manual) |
| `DisableSlotByBotUseCase` | Desactiva en Travian + pone `disabled_by_bot=True` (toggle Bot→excluir) |
| `EnableSlotByBotUseCase` | Activa en Travian + limpia `disabled_by_bot` (toggle Bot→incluir) |
| `GetSchedulerStatsUseCase` | Delega enteramente en el puerto de BD — no necesita browser (RN-D07) |

---

## 5. Router FastAPI (`adapters/api/routes/farm.py`)

### 5.1 Convenciones del router

- Prefijo `/farm` (sin `/api`; el proxy Vite retira ese prefijo).
- Sin `Accept-Language`: los datos de farm lists son datos de juego, no catálogo i18n.
- `world_id` siempre en la ruta para todos los recursos de mundo.
- Errores con `{"detail": "<mensaje legible>"}`.
- Paginación: `page` / `page_size` (máx 100) con envelope `{items, page, page_size, total}`.

### 5.2 Helpers de acceso a `app.state`

`_get_farm_db(request)` — devuelve el `FarmListSQLiteAdapter` singleton o 503.
`_get_farm_browser(request, world_id)` — crea o recupera el `LiveFarmListAdapter` para el mundo. El adaptador se crea bajo demanda si hay sesión activa (no requiere `/agent/start` previo).
`_get_world_agent(request, world_id)` — devuelve el `WorldAgent` del mundo o `None`.

### 5.3 Serialización

Los helpers `_serialize_*` convierten entidades de dominio a dicts serializables. Puntos de interés:

**`_serialize_farm_list`** recibe `last_send_time` como parámetro externo (no lo calcula él). El llamador (`list_farm_lists` / `read_farm_lists`) consulta `get_last_send_times_by_world` en una sola query de agregación y pasa el resultado a cada serialización (Gap A).

**`_serialize_send_event`** incluye los 4 campos de metadata de scheduler (`scheduler_name`, etc.), que son NULL para envíos manuales (Gap B).

**`_serialize_scheduler_stats`** serializa el `SchedulerStats` incluyendo el array `per_list` con métricas individuales por farm list (Gap D).

### 5.4 Tabla de endpoints

| Método | Ruta | Código | Descripción |
|---|---|---|---|
| GET | `/farm/worlds/{wid}/schedulers` | 200 | Lista schedulers del mundo |
| POST | `/farm/worlds/{wid}/schedulers` | 201 | Crea scheduler |
| PUT | `/farm/worlds/{wid}/schedulers/{sid}` | 200 | Actualiza scheduler |
| DELETE | `/farm/worlds/{wid}/schedulers/{sid}` | 204 | Borra scheduler (listas quedan con scheduler_id=NULL) |
| PUT | `/farm/worlds/{wid}/schedulers/{sid}/farm-lists` | 200 | Asigna farm lists al scheduler |
| POST | `/farm/worlds/{wid}/schedulers/{sid}/toggle` | 200 | Alterna `is_enabled` |
| GET | `/farm/worlds/{wid}/schedulers/{sid}/stats` | 200 | Métricas del scheduler (Gap D) |
| GET | `/farm/worlds/{wid}/farm-lists` | 200 | Lista farm lists con slots y `last_send_time` |
| POST | `/farm/worlds/{wid}/farm-lists/read` | 200 | Sincroniza desde el DOM de Travian |
| POST | `/farm/slots/{slot_id}/activate` | 200 | Activa slot en Travian |
| POST | `/farm/slots/{slot_id}/deactivate` | 200 | Desactiva slot en Travian |
| POST | `/farm/slots/{slot_id}/bot-disable` | 200 | Toggle bot→excluir |
| POST | `/farm/slots/{slot_id}/bot-enable` | 200 | Toggle bot→incluir |
| POST | `/farm/slots/{slot_id}/cancel-probe` | 200 | Cancela sonda (modos: deactivate, send_now) |
| POST | `/farm/farm-lists/{flid}/send` | 200 | Envío manual de una farm list |
| GET | `/farm/worlds/{wid}/history` | 200 | Historial paginado de envíos |
| GET | `/farm/worlds/{wid}/slot-events` | 200 | Historial paginado de eventos de slots |
| POST | `/farm/worlds/{wid}/agent/start` | 200 | Arranca el WorldAgent |
| POST | `/farm/worlds/{wid}/agent/stop` | 200 | Solicita parada limpia |
| GET | `/farm/worlds/{wid}/agent/status` | 200 | Estado del WorldAgent (nunca 404) |
| POST | `/farm/worlds/{wid}/schedulers/{sid}/run-now` | 200 | Adelanta el próximo disparo del scheduler |

### 5.5 Códigos de error relevantes

| Código | Condición habitual |
|---|---|
| 400 | Intentar cancelar una sonda en un slot sin `disabled_by_bot=True` |
| 404 | Scheduler o farm list no encontrado; `world_id` de la ruta no coincide con el del scheduler en stats |
| 409 | WorldAgent ya corriendo (start) o no corriendo (run-now) |
| 422 | `interval_min_ms > interval_max_ms`; paginación fuera de rango |
| 503 | No hay sesión activa para el mundo; port no disponible |
| 502 | Error al leer o enviar en el DOM de Travian |

---

## 6. Relación entre componentes

```
FarmListBrowserPort         FarmListDbPort
(adapters/browser/)    <──  FarmListSQLiteAdapter
        │                         │
        └─────────┬───────────────┘
                  │
           Use Cases (core/)
                  │
            FastAPI Router
           (adapters/api/)
```

El `core/` solo conoce los puertos. Los adaptadores concretos (SQLite, browser) se inyectan en el `lifespan` de la app o se crean on-demand por los helpers del router.

---

## 7. Divergencias código / spec

Ninguna divergencia relevante detectada. La implementación sigue los specs `docs/specs/farm-lists.md` y `docs/specs/farm-stats-y-metadata-scheduler.md`. La única desviación documentada en el propio spec es el test `test_scheduler_deleted_race_condition` (EC-B02), corregido por restricciones de FK en la BD de test; el comportamiento de producción es el correcto.

Hay warnings de `datetime.utcnow()` deprecado en Python 3.12+ (pre-existentes en el proyecto, fuera del alcance de esta feature).

---

🔖 Última revisión: 2026-05-28 (documentación inicial de la feature farm lists + farm stats)
