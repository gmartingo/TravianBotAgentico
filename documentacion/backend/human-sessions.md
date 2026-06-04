# Documentación de código — Human Sessions v2.1

Módulos documentados:
- `core/entities/session.py` — entidades de dominio + funciones puras de cálculo de modo
- `core/scheduling/world_agent.py` — integración del timeline en el WorldAgent (bucle principal, transiciones, modos)
- `adapters/api/routes/session.py` — endpoints HTTP de timeline, override y config PASIVO

Spec de referencia: [`docs/specs/human-sessions.md`](../../docs/specs/human-sessions.md) (v2.1 — implementado)
Referencia de API: [`documentacion/api/human-sessions.md`](../api/human-sessions.md)
Documento de negocio: [`funcionalidades/human-sessions.md`](../funcionalidades/human-sessions.md)

---

## Contexto de negocio

El bot fue baneado por Travian (primera ofensa: downgrade del 33% de edificios). Causa raíz identificada: el bot operaba 24/7 al mismo ritmo y recorría las colecciones siempre en el mismo orden — ningún humano juega sin dormir ni sin variación diaria.

Human Sessions introduce un calendario semanal configurable con tres modos de actividad: **HARDCORE** (operación completa), **PASIVO** (actividad reducida con Chrome abierto) y **DISCONNECTED** (parada total, Chrome cerrado). Los bordes de los bloques tienen jitter aleatorio de ±N minutos para evitar que el bot cambie de modo siempre a la hora exacta.

---

## `core/entities/session.py` — Entidades y lógica pura

Este módulo contiene solo entidades dataclass y funciones puras (sin IO, sin BD). Todas las funciones de cálculo de modo son testables sin browser ni base de datos.

### Enum `SessionMode`

```python
class SessionMode(str, Enum):
    HARDCORE     = "HARDCORE"
    PASIVO       = "PASIVO"
    DISCONNECTED = "DISCONNECTED"
```

Los tres modos de actividad del bot. `str, Enum` permite serialización directa a JSON.

**Por qué PASIVO (no IDLE, no REST):** el spec v1 usaba `HARDCORE_SESSION` / `REST_SESSION`. v2 renombró REST → IDLE. v2.1 renombra definitivamente IDLE → PASIVO para describir con más precisión el comportamiento: el humano que deja el juego "en segundo plano" no duerme (REST) ni está inactivo (IDLE) — está jugando pasivamente.

### Dataclasses de dominio

| Clase | Campos clave | Propósito |
|---|---|---|
| `SessionBlock` | `start_hour, start_minute, end_hour, end_minute, mode` | Un bloque horario (p.ej. 08:00-23:00 HARDCORE) |
| `SessionTimeline` | `world_id, weekday, blocks, jitter_minutes=15, is_default=False` | Timeline completo de un día de la semana para un mundo |
| `SessionOverride` | `world_id, mode, expires_at` | Override manual activo (dura hasta el próximo borde de bloque) |
| `SessionConfig` | `world_id, passive_interval_factor=2.0, passive_send_probability=0.05` | Parámetros configurables del modo PASIVO |

### `_make_default_blocks(is_weekend) → list[SessionBlock]`

**Qué hace:** Devuelve los bloques del timeline por defecto.
- Lun-Vie: `00:00-08:00 DISCONNECTED`, `08:00-23:00 HARDCORE`, `23:00-24:00 DISCONNECTED`
- Sáb-Dom: `00:00-09:00 DISCONNECTED`, `09:00-24:00 HARDCORE`

**Por qué existe:** El usuario que no configura nada recibe un comportamiento razonable sin necesidad de escribir en BD (RN-HS11). El timeline por defecto no se persiste: si el usuario nunca configura ese día, el endpoint `GET timeline` lo devuelve con `is_default: true`.

### `get_default_timeline(world_id, weekday) → SessionTimeline`

**Qué hace:** Construye y devuelve el `SessionTimeline` por defecto para un (world_id, weekday). `is_default=True`.

### `_find_active_block(blocks, now) → SessionBlock`

**Qué hace:** Dado el instante `now`, recorre `blocks` buscando el que contiene la hora actual. Soporta bloques que cruzan medianoche (end_m < start_m) aunque el PUT de timeline los prohíbe en persistencia.

**Impacto anti-detección:** garantiza que el bot opere exactamente en el modo configurado para el instante actual, sin desviaciones por redondeo de hora.

**Errores:** `RuntimeError` si ningún bloque cubre `now` (invariante roto — el timeline siempre debe cubrir 24h).

### `_block_end_as_datetime(block, now) → datetime`

**Qué hace:** Convierte el fin nominal de un bloque a un `datetime` relativo al día de `now`. `end_hour=24` → medianoche del día siguiente (= primer segundo del día siguiente).

### `current_mode(now, timeline, override) → tuple[SessionMode, datetime]`

**Qué hace:** Función pura principal. Dado el instante actual, el timeline del día y un posible override, devuelve el `SessionMode` activo y el instante `jitter_fin` (cuando expira el bloque con jitter aplicado).

**Lógica:**
1. Si hay override activo (no expirado) → devuelve el modo del override y su `expires_at`.
2. Encuentra el bloque activo en el timeline.
3. Calcula el fin nominal del bloque como `datetime`.
4. Aplica jitter aleatorio: `fin_nominal ± random.uniform(-jitter_minutes×60, +jitter_minutes×60)`.
5. Garantía EC-HS03: `jitter_fin >= now + 1 min` (bloquea cortocircuitos por jitter grande en bloques muy cortos).

**Por qué es pura:** el WorldAgent la llama en cada iteración del bucle. Al no tener IO, es instantánea y testable con `datetime` mock.

**Manejo de timezone:** si `override.expires_at` es offset-aware y `now` es naive (o viceversa), la función normaliza ambos a UTC naive para la comparación.

### `calculate_jitter_fin_for_now(now, timeline) → datetime`

**Qué hace:** Calcula el `jitter_fin` del bloque activo en `now` sin considerar overrides. Se usa en `PUT /session/mode` para calcular el `expires_at` del override que se va a crear.

---

## `core/scheduling/world_agent.py` — Integración en el WorldAgent

El WorldAgent es el bucle principal del bot para un mundo. Human Sessions se integra en tres puntos:

### Arranque (`WorldAgent.run()`)

```python
# Al arrancar:
timeline = await session_timeline_db.get_timeline(world_id, weekday) or get_default_timeline(...)
override = await session_timeline_db.get_override(world_id)
self._active_mode, self._jitter_fin = compute_current_mode(now, timeline, override)

# Si DISCONNECTED → no abre Chrome
# Si HARDCORE → seed_oasis_groups_from_db()
# Si HARDCORE o PASIVO → seed noise loop
# Si no hay sesión activa y modo != DISCONNECTED → relogin
```

**Por qué no hay modo de arranque hardcodeado:** en v1 el arranque forzaba HARDCORE. Con timeline, arrancar en el modo incorrecto es una firma: un humano que enciende el PC a las 03:00 no empieza a jugar en modo agresivo.

### `_check_mode_transition(now)`

**Qué hace:** Al inicio de cada iteración del bucle:
1. Si hay override activo y no ha expirado → usa el modo del override.
2. Si hay override y ha expirado → lo descarta, recalcula modo del calendario.
3. Si no hay override y `now >= self._jitter_fin` → nuevo bloque, recalcula modo y nuevo `jitter_fin`.
4. Si el modo cambió → ejecuta efectos secundarios:
   - Nuevo modo == DISCONNECTED → `SessionRegistry.close_session(world_id)` (cierra Chrome).
   - Modo previo == DISCONNECTED y nuevo != DISCONNECTED → `_relogin_with_backoff()`.
   - Nuevo modo == HARDCORE (y era PASIVO/DISCONNECTED) → `_safe_seed_oasis()`.
   - Nuevo modo ∈ {HARDCORE, PASIVO} → `_safe_seed_noise_loop()`.

### Bucle principal por modo

| Modo activo | Qué ejecuta el WorldAgent |
|---|---|
| `HARDCORE` | Tareas normales: SEND_FARM_LIST_GROUP, SEND_OASIS_RAID, edificios, tropas |
| `PASIVO` | Solo `_handle_pasivo_farm_list(task)` para SEND_FARM_LIST_GROUP; no encola oasis ni edificios ni tropas |
| `DISCONNECTED` | No ejecuta tareas productivas; espera `DEFAULT_IDLE_SECONDS` antes de comprobar transición |

### `_handle_pasivo_farm_list(task)` — Lógica PASIVO

**Qué hace:** Cuando el modo es PASIVO y llega una tarea `SEND_FARM_LIST_GROUP`:
1. Genera un número aleatorio `r ∈ [0, 1)`.
2. Si `r >= passive_send_probability` → **salta** la ejecución. La tarea se considera consumida y se reencola con el intervalo multiplicado. Se loguea como "skipped (PASIVO)".
3. Si `r < passive_send_probability` → **ejecuta** normalmente.
4. Al reencolar (tanto si ejecutó como si saltó), los intervalos `interval_min_ms` e `interval_max_ms` del `FarmScheduler` se multiplican por `passive_interval_factor`.

**Por qué existe:** Simula al humano que tiene el juego en segundo plano: rara vez manda raids (5% por defecto), y cuando lo hace, los espacía más (2× el intervalo normal).

### `_relogin_with_backoff()`

**Qué hace:** Ejecuta el flujo de relogin automático al salir de DISCONNECTED. Backoff exponencial: 10 → 20 → 40 → 60 min (máximo).

**Casos especiales:**
- Fallo por `FernetDecryptionError` (credencial no descifrable) → estado `DISCONNECTED-error` sin backoff. Log CRITICAL. El usuario debe corregir la `TRAVIAN_BOT_SECRET_KEY` y reiniciar.
- Si el calendario vuelve a DISCONNECTED durante el backoff → se aborta el relogin y el WorldAgent vuelve a DISCONNECTED sin haber abierto Chrome.

---

## Esquema de BD — tablas de Human Sessions

Las tablas se crean automáticamente al primer uso (migraciones lazy).

### `world_session_timeline`

Una fila por `(world_id, weekday, block_index)`. El timeline de un día es una lista de filas.

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | INTEGER PK | |
| `world_id` | INTEGER FK → worlds | |
| `weekday` | INTEGER 0-6 | 0=lunes…6=domingo |
| `block_index` | INTEGER | Orden del bloque en el día (0-based) |
| `start_hour` / `start_minute` | INTEGER | Inicio del bloque |
| `end_hour` / `end_minute` | INTEGER | Fin del bloque (end_hour puede ser 24) |
| `mode` | TEXT | `HARDCORE` / `PASIVO` / `DISCONNECTED` |
| `jitter_minutes` | INTEGER DEFAULT 15 | Jitter en minutos por borde |

**Decisión de shape:** fila por bloque (no JSON blob) para poder validar campos con CHECK constraints de SQLite y agregar/eliminar bloques individuales sin reescribir todo el día.

### `world_session_override`

Una fila por `world_id` (máximo un override activo por mundo).

| Columna | Tipo | Descripción |
|---|---|---|
| `world_id` | INTEGER PK FK | |
| `mode` | TEXT | Modo del override |
| `expires_at` | TEXT | ISO-8601 UTC |

### `world_session_config`

Una fila por `world_id`. Se crea lazy: al primer `PUT /session/config`.

| Columna | Tipo | Descripción |
|---|---|---|
| `world_id` | INTEGER PK FK | |
| `passive_interval_factor` | REAL DEFAULT 2.0 | Rango [1.5, 5.0] |
| `passive_send_probability` | REAL DEFAULT 0.05 | Rango [0.01, 0.50] |

---

## Puerto `SessionTimelineDbPort`

Definido en `core/ports/session_timeline_db_port.py`. Métodos principales:

| Método | Descripción |
|---|---|
| `get_timeline(world_id, weekday) → SessionTimeline \| None` | Devuelve el timeline del día. `None` si no existe (el caller usa el default). |
| `upsert_timeline(timeline) → SessionTimeline` | Reemplaza los bloques del día. Rellena huecos con DISCONNECTED. Valida no-solapes. |
| `get_override(world_id) → SessionOverride \| None` | Override activo, o None si no existe o ya expiró (lo borra si expiró). |
| `set_override(override)` | Escribe o reemplaza el override activo. |
| `clear_override(world_id)` | Borra el override activo. |
| `get_session_config(world_id) → SessionConfig` | Config PASIVO del mundo. Devuelve defaults si no existe fila. |
| `upsert_session_config(config) → SessionConfig` | Crea o actualiza la config. Valida rangos antes de escribir. |

---

## Frontend — Componentes de UI implementados

La pestaña "Sesión" vive en `WorldSpacePage.jsx` como una de las pestañas del sidebar del mundo (ruta `/mundos/:worldId`). Los componentes implementados son:

| Componente | Fichero | Descripción |
|---|---|---|
| `SessionTab` | `frontend/src/components/session/SessionTab.jsx` | Contenedor raíz. Orquesta polling de estado (15 s), carga de timelines, override y guardado de bloques. Gestiona también el flujo de "copiar día a otros días". |
| `SessionStatusPanel` | `frontend/src/components/session/SessionStatusPanel.jsx` | Panel P1 siempre visible. Badge de modo, bloque activo (HH:MM–HH:MM), jitter ±N min, countdown `Countdown.jsx` al `next_block_ends_at`. Si hay override activo, muestra `OverrideRow` con countdown al `expires_at` y botón "Cancelar override" (llama a `DELETE /session/override`). |
| `ModeBadge` | Exportado desde `SessionStatusPanel.jsx` | Pill colorado por modo: verde (HARDCORE), azul (Pasivo), gris (Descanso total). Reutilizable por otros componentes. |
| `SessionOverridePanel` | `frontend/src/components/session/SessionOverridePanel.jsx` | Tres botones de override: HARDCORE / Pasivo / Descanso total. El botón del modo efectivo tiene borde+fondo del token de modo. Gestiona estado de carga individual por botón. |
| `WeekdaySelector` | `frontend/src/components/session/WeekdaySelector.jsx` | Fila de 7 botones de día (`role="tablist"`). Nombres localizados con `Intl`. Dot de color del primer modo. Etiqueta "DEFAULT" si `is_default: true`. Borde dorado en día seleccionado; borde `--text-tertiary` en el día real hoy. |
| `TimelineBar` | `frontend/src/components/session/TimelineBar.jsx` | Barra proporcional de 24h con segmentos coloreados por modo. Si hay huecos, los muestra en rojo con `mode='error'`. Incluye etiquetas de horas (00:00, 06:00, 12:00, 18:00, 24:00) y leyenda de modos únicos. Exporta también `TimelineCoverageIndicator` y `validateCoverage`. |
| `BlockEditor` | `frontend/src/components/session/BlockEditor.jsx` | Tabla editable de bloques (Desde/Hasta/Modo). El `start` de cada bloque es de solo lectura y se encadena automáticamente al `end` del bloque anterior. La validación de cobertura (`validateCoverage`) se ejecuta en `onChange`, actualizando la barra en tiempo real. Botón `+ Añadir bloque`. Presets de copia "Toda la semana / Entre semana / Fin de semana". |

### Funcionalidades de UI no contempladas en el spec de diseño original

**Funcionalidad real presente en el código:**

- **Presets de copia "Copiar este día a:"** — `BlockEditor` incluye tres botones: "Toda la semana", "Entre semana" y "Fin de semana". Al hacer clic, aplica los bloques del día actualmente editado a ese conjunto de días, realizando PUT secuencial por cada día destino (secuencial, no paralelo, para evitar solapamiento de transacciones SQLite). No estaba en el spec de diseño `human-sessions-ui.md` v2026-05-31.

- **Cancelación de override vía `DELETE /session/override`** — El botón "Cancelar override" de `OverrideRow` llama a `api.deleteWorldOverride(worldId)` (endpoint `DELETE /worlds/{id}/session/override`, v2.2). El spec de diseño mencionaba este botón pero su implementación vía DELETE es más limpia que la alternativa PUT al modo del bloque.

- **Normalización de modos en minúsculas/mayúsculas** — La UI mantiene los modos en minúsculas internamente (`hardcore`, `pasivo`, `disconnected`) y serializa a MAYÚSCULAS (`HARDCORE`, `PASIVO`, `DISCONNECTED`) solo al hacer el PUT. El backend (enum `SessionMode`) exige mayúsculas. Esto es un detalle de implementación no documentado en el spec.

- **`24:00` como valor especial en `input[type="time"]`** — El input nativo de hora no acepta `24:00` (valor no válido en HTML5). El `BlockEditor` muestra `23:59` como proxy visual cuando el estado interno es `24:00`. Si el usuario introduce `23:59` en el último bloque, lo normaliza a `24:00`.

---

## Divergencias código/spec conocidas

**DIV-HS01 — Spec de diseño dice "IDLE", código usa "PASIVO"**

El spec de diseño `human-sessions-ui.md` (fecha 2026-05-31) usa `IDLE` como nombre del segundo modo en varios lugares: tokens CSS (`--mode-idle`, `--mode-idle-subtle`), textos microcopy (`session.status.mode.idle = "IDLE"`), y el wireframe (`OP[Botones de override: HARDCORE / IDLE / DISCONNECTED]`).

El spec funcional `human-sessions.md` renombró definitivamente `IDLE` → `PASIVO` en v2.1 (2026-05-31). El código implementa `PASIVO`. La UI real muestra "Pasivo" (con CSS token `--mode-pasivo`, no `--mode-idle`).

**Impacto:** los tokens CSS definidos en el spec de diseño como `--mode-idle` no coinciden con los tokens reales del código (`--mode-pasivo`). El spec de diseño está desactualizado respecto al spec funcional.

**DIV-HS02 — Presets de copia no estaban en el spec de diseño**

El `BlockEditor.jsx` implementa tres botones "Copiar este día a: Toda la semana / Entre semana / Fin de semana" que no aparecen en `human-sessions-ui.md`. Son una mejora de UX añadida durante la implementación.

**DIV-HS03 — El spec menciona `_current_mode(now)` como método del WorldAgent**

La implementación extrae la lógica a la función pura `current_mode(now, timeline, override)` en `core/entities/session.py` (importada en el WorldAgent como `compute_current_mode`). Mejora de diseño — hace la lógica testable sin instanciar el WorldAgent. No es una divergencia funcional.

🔖 Última revisión: 2026-06-04 (ampliado: sección Frontend con los 6 componentes implementados, funcionalidades UI adicionales detectadas en el código, y 3 divergencias código/spec documentadas)
