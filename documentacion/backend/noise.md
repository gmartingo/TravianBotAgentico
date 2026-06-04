# Documentación de código — Sistema de Ruido (Noise Navigation)

Módulos documentados:
- `core/entities/noise.py` — entidades de dominio: `NoiseCategory`, `NavigationOrigin`, `NoiseDestination`, `NavigationStep`, `NavigationPath`, `NoiseConfig`
- `core/entities/noise_test.py` — entidades del reporte de prueba de ruta
- `core/scheduling/world_agent.py` — bucle de ruido y funciones relacionadas (extracto)
- `adapters/db/noise_sqlite_adapter.py` — adaptador SQLite del puerto de ruido
- `adapters/api/routes/noise.py` — endpoints EP-N01..EP-N14

Specs de referencia:
- `docs/specs/human-sessions.md` §17 (sistema base de ruido — implementado)
- `docs/specs/noise-path-wizard.md` (anclas semilla, wizard, EP-N11..N14 — implementado)
- `docs/specs/noise-navigate-to-origin.md` (EP-N15 "Ir al inicio" — **pendiente de implementación**)
- `docs/specs/noise-frequency-and-destination-weight.md` (frecuencia MM:SS y peso — **ready-for-impl, pendiente de gates**)

Documento de negocio: [`funcionalidades/noise.md`](../funcionalidades/noise.md)

---

## Contexto de negocio

Travian detecta bots que solo realizan acciones productivas (raids, construcción) sin navegar por el resto del juego. Un jugador real visita periódicamente páginas como el mapa, el ranking, los mensajes o las estadísticas, sin un propósito productivo concreto. El sistema de ruido reproduce ese comportamiento: el WorldAgent ejecuta periódicamente una "acción de ruido" que consiste en navegar por una ruta configurada hacia un destino, con delays humanizados entre pasos.

---

## `core/entities/noise.py` — Entidades

### `NoiseCategory`

```python
class NoiseCategory(str, Enum):
    NAVIGATION = "NAVIGATION"
    HOVER      = "HOVER"
```

Categoría de un destino de ruido. `NAVIGATION` es la usada por defecto (navegar a una URL). `HOVER` está definida pero no produce un comportamiento diferenciado en la implementación actual (pendiente).

### `NavigationOrigin`

Enum con los orígenes (anclas semilla) disponibles para empezar una ruta de ruido:

| Valor | URL relativa | Descripción |
|---|---|---|
| `DORF1` | `/dorf1.php` | Vista de recursos de la aldea activa |
| `DORF2` | `/dorf2.php` | Vista de edificios de la aldea activa |
| `MAP` | `/karte.php` | Mapa del mundo |
| `STATISTICS` | `/statistics` | Estadísticas del servidor |
| `REPORTS` | `/report` | Reportes de combate |
| `MESSAGES` | `/messages` | Mensajes |
| `VILLAGE_STATISTICS` | `/village/statistics` | Estadísticas de aldea |
| `OASIS_VIEW` | `/karte.php` | Vista de oasis (misma URL que MAP — variante semántica) |
| `ANY` | `""` | Sin ancla específica; el WorldAgent parte de donde esté |

Además de estos valores fijos, el sistema acepta orígenes dinámicos con el patrón `VILLAGE_<data_id>` (uno por cada aldea propia del jugador). Estos orígenes dinámicos se validan contra la tabla `villages` de BD.

`ORIGIN_PATHS` es un dict que mapea cada `NavigationOrigin` a su path relativo (sin el dominio de Travian).

### `NoiseDestination`

Destino de navegación de ruido. Un mundo puede tener múltiples destinos.

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | int \| None | ID BD (None antes de persistir) |
| `world_id` | int | Mundo al que pertenece |
| `url_pattern` | str | Patrón de URL (p.ej. `/karte.php`) |
| `label` | str | Etiqueta legible |
| `category` | NoiseCategory | Tipo de acción |
| `frequency_weight` | float > 0 | Peso para el sorteo proporcional de destino |
| `is_safe` | bool = True | Si False, el WorldAgent no ejecuta rutas hacia este destino |
| `is_dead` | bool = False | Marcado si falla repetidamente |
| `consecutive_failures_count` | int | Contador de fallos consecutivos |

`url_pattern` y `category` son inmutables tras la creación (el endpoint PUT no los permite cambiar).

### `NavigationStep`

Un paso dentro de una ruta de navegación.

| Campo | Tipo | Descripción |
|---|---|---|
| `step_order` | int | 0-based, único dentro del path |
| `action` | NoiseAction | `CLICK`, `HOVER` o `WAIT_FOR_SELECTOR` |
| `selector` | str | Selector CSS estructural (nunca texto visible) |
| `value` | str | Para WAIT_FOR_SELECTOR: timeout en ms como string |
| `delay_min_ms` | int = 500 | Delay mínimo tras este paso |
| `delay_max_ms` | int = 900 | Delay máximo tras este paso |
| `expected_url_after_click` | str \| None | URL esperada tras un CLICK (None = sin verificación) |

**Anti-detección (no negociable):** `delay_min_ms` tiene un piso de 200 ms hardcodeado en `__post_init__`. El techo es 5000 ms. Esto blinda que ningún paso se encadene sin el tiempo de reacción humano mínimo — incluso si el usuario envía `delay_min_ms=0` vía API, `__post_init__` lanza `ValueError`.

`expected_url_after_click` fue añadido en `noise-path-wizard.md` §7.4. Si está presente en un paso CLICK, el WorldAgent comprueba la URL del tab tras el click. Si no coincide, incrementa `consecutive_failures_count` del path.

### `NavigationPath`

Ruta de navegación hacia un destino. Contiene una lista de pasos ordenados por `step_order`.

| Campo | Tipo | Descripción |
|---|---|---|
| `origin` | str | Ancla de inicio. Admite `NavigationOrigin.value` y `"VILLAGE_<data_id>"` |
| `label` | str | Etiqueta legible |
| `is_active` | bool = True | Si False, el WorldAgent no ejecuta esta ruta |
| `is_dead` | bool = False | True si `consecutive_failures_count >= THRESHOLD` (RN-NP07) |
| `consecutive_failures_count` | int | Fallos consecutivos de verificación de URL |

**Nota de tipo:** `origin` es `str` (no `NavigationOrigin`) para admitir los valores dinámicos `VILLAGE_<data_id>`. La validación se hace en el adapter de BD y en el endpoint.

### `NoiseConfig`

Configuración de ruido por mundo (frecuencia y dwell).

| Campo | Tipo | Descripción |
|---|---|---|
| `noise_enabled` | bool = True | Master switch del sistema de ruido |
| `hardcore_total_req_per_hour_min/max` | int | Rango de peticiones/hora en HARDCORE (default 80-150) |
| `passive_total_req_per_hour_min/max` | int | Rango de peticiones/hora en PASIVO (default 15-40) |
| `dwell_min_seconds` | float = 2.0 | Tiempo mínimo de "permanencia" en el destino tras la ruta |
| `dwell_max_seconds` | float = 30.0 | Tiempo máximo de permanencia |

**Nota:** el spec `noise-frequency-and-destination-weight.md` (estado `ready-for-impl`) reemplazará `req_per_hour_min/max` por un intervalo en MM:SS más intuitivo. Esta refactorización está pendiente de gate guardian y gate desarrollador-apis.

---

## `core/scheduling/world_agent.py` — Funciones del sistema de ruido

### Estado de ruido en el WorldAgent

```python
self._noise_db: NoiseDbPort | None           # Puerto de BD de noise (inyectado)
self._noise_in_burst: bool                   # Si está en burst de múltiples páginas
self._noise_burst_remaining: int             # Clicks restantes en el burst actual
self._noise_recent_count: int                # Navegaciones en las últimas 30 min
self._noise_window_start: datetime           # Inicio de la ventana de 30 min
self._browser_lock: asyncio.Lock             # Serializa noise, path test y refresh villages
```

### `seed_noise_loop_on_session_start()`

**Qué hace:** Encola la primera tarea `NOISE_NAVIGATION` con un gap inicial calculado. Se llama al arranque del WorldAgent en modo HARDCORE o PASIVO, y al salir de DISCONNECTED tras un relogin exitoso.

**Por qué existe:** El sistema de ruido no arranca por sí solo — necesita ser "sembrado" con la primera tarea. Después, `_handle_noise_navigation` reencola la siguiente tarea al terminar cada navegación.

### `_calculate_next_noise_gap(mode, config, now) → int` (segundos)

**Qué hace:** Calcula el gap en segundos hasta la próxima acción de ruido, basándose en `config.req_per_hour_min/max` para el modo activo. Convierte req/hora a segundos por request e introduce variabilidad con `random.uniform`. En PASIVO usa `passive_total_req_per_hour_min/max`.

**Impacto anti-detección:** el gap nunca es fijo — siempre tiene variabilidad aleatoria. Un intervalo exacto y repetible sería firma de bot.

### `_select_noise_action() → tuple[NoiseDestination, NavigationPath] | None`

**Qué hace:** Selecciona un destino y una ruta para ejecutar. Proceso:
1. Lee todos los destinos activos y no muertos del mundo desde BD.
2. Usa `random.choices` con pesos `frequency_weight` para el sorteo proporcional.
3. Para el destino seleccionado, elige una ruta aleatoria entre las activas.
4. Si no hay destinos/rutas disponibles, devuelve `None` (el WorldAgent omite la navegación y reencola con el gap normal).

### `_execute_noise_step(tab, step)`

**Qué hace:** Ejecuta un único paso de navegación:
- `CLICK`: llama a `human_click_at_rect` con el rect del selector (via `getBoundingClientRect` en JS).
- `HOVER`: emite `Input.dispatchMouseEvent` con `type: mouseMoved` al centro del elemento.
- `WAIT_FOR_SELECTOR`: espera hasta que el selector esté presente en el DOM (con timeout).

Si el paso tiene `expected_url_after_click`, tras el click verifica que la URL del tab coincide (usando `_extract_url_path`). Si no coincide, incrementa `consecutive_failures_count` del path.

**Anti-detección:** todos los clicks pasan por `human_click_at_rect`, no por `element.click()` directo.

### `_execute_noise_action(dest, path, config)`

**Qué hace:** Ejecuta una ruta completa: para cada paso en orden, ejecuta `_execute_noise_step` + `human_delay(step.delay_min_ms, step.delay_max_ms)`. Al final, `human_delay` de dwell aleatorio (`config.dwell_min_seconds`, `config.dwell_max_seconds`).

Adquiere `self._browser_lock` antes de comenzar para serializar con `execute_path_test` y `refresh_villages`.

### `_handle_noise_navigation()`

**Qué hace:** Orquesta una acción de ruido completa: selecciona destino/ruta, la ejecuta, maneja errores, actualiza `last_used_at` y `consecutive_failures_count` en BD, y reencola la próxima tarea `NOISE_NAVIGATION` con el siguiente gap.

**Marcado `is_dead`:** si `path.consecutive_failures_count >= DEAD_PATH_THRESHOLD` (definido en `world_agent.py`), el path se marca como `is_dead=True` y se excluye de futuros sorteos.

### `refresh_villages() → list`

**Qué hace:** Parsea el village-switcher del sidebar de Travian (presente en cualquier página autenticada), extrae `newdid` y nombre de cada aldea propia, y los persiste en la tabla `villages`. Devuelve la lista de aldeas actualizadas.

Adquiere `self._browser_lock` para no interleave con `_execute_noise_action` ni `execute_path_test`.

**Por qué existe:** Los orígenes dinámicos `VILLAGE_<data_id>` de las rutas de ruido requieren que la tabla `villages` esté actualizada. `refresh_villages` se llama al arrancar la sesión y puede llamarse vía EP-N13.

### `execute_path_test(path) → PathTestReport`

**Qué hace:** Ejecuta una ruta en vivo con el Chrome real del bot, con propósito de verificación. Produce un `PathTestReport` con el resultado de cada paso (`ok`, `fail`, `aborted_at`).

Timeout configurable (`PATH_TEST_TIMEOUT_SECONDS`): si no consigue el `_browser_lock` en ese tiempo, lanza `BrowserBusyError`. Si lo consigue, el timeout también aplica al tiempo total de ejecución de la ruta.

**Anti-detección:** usa los mismos `_execute_noise_step` que producción — el comportamiento de click, hover y timing es idéntico al real.

---

## Endpoints EP-N01..EP-N14

Los endpoints de ruido viven en `adapters/api/routes/noise.py`. Resumen:

| EP | Método | Ruta | Función |
|---|---|---|---|
| EP-N01 | GET | `/worlds/{id}/noise/config` | Leer NoiseConfig del mundo |
| EP-N02 | PUT | `/worlds/{id}/noise/config` | Actualizar NoiseConfig |
| EP-N03 | GET | `/worlds/{id}/noise/destinations` | Listar destinos |
| EP-N04 | POST | `/worlds/{id}/noise/destinations` | Crear destino |
| EP-N05 | PUT | `/worlds/{id}/noise/destinations/{dest_id}` | Actualizar destino (label, weight, is_safe) |
| EP-N06 | DELETE | `/worlds/{id}/noise/destinations/{dest_id}` | Borrar destino |
| EP-N07 | GET | `/worlds/{id}/noise/destinations/{dest_id}/paths` | Listar rutas de un destino |
| EP-N08 | POST | `/worlds/{id}/noise/destinations/{dest_id}/paths` | Crear ruta |
| EP-N09 | PUT | `/worlds/{id}/noise/paths/{path_id}` | Actualizar ruta (label, origin, steps) |
| EP-N10 | DELETE | `/worlds/{id}/noise/paths/{path_id}` | Borrar ruta |
| EP-N11 | POST | `/worlds/{id}/noise/derive-selector` | Derivar selector CSS desde outerHTML (wizard) |
| EP-N12 | GET | `/worlds/{id}/noise/origins` | Listar anclas semilla disponibles |
| EP-N13 | POST | `/worlds/{id}/noise/refresh-villages` | Refrescar aldeas del village-switcher |
| EP-N14 | POST | `/worlds/{id}/noise/paths/{path_id}/test` | Probar ruta en vivo |

**EP-N15 (POST `/worlds/{id}/noise/navigate-to-origin`) — NO IMPLEMENTADO.** El spec `noise-navigate-to-origin.md` está en estado `ready-for-impl`. El botón "Ir al inicio" del wizard lleva el Chrome del bot a la URL del ancla seleccionada. Está pendiente de implementación.

---

## `adapters/db/noise_sqlite_adapter.py` — Adaptador SQLite

### Migraciones lazy

El adaptador ejecuta migraciones al conectar:
- `_migrate_noise_paths_add_is_dead_and_failures`: añade `is_dead` y `consecutive_failures_count` a `noise_navigation_paths` si no existen.
- `_migrate_noise_steps_add_expected_url`: añade `expected_url_after_click` a `noise_navigation_steps` si no existe.
- `_repair_noise_steps_broken_fk`: repara steps huérfanos si existen.

### Validaciones inline

- `_validate_origin(origin, village_data_ids)`: acepta los 9 valores del enum `NavigationOrigin` y `VILLAGE_<data_id>` donde `data_id` esté en la lista de aldeas del mundo.
- `_validate_url_pattern(url_pattern, world_server)`: verifica que el patrón de URL pertenezca al mismo dominio del servidor de Travian.

### `NoiseSQLiteAdapter`

Implementa `NoiseDbPort`. Métodos principales por entidad:

| Método | Descripción |
|---|---|
| `get_or_create_noise_config(world_id)` | Config de ruido; crea fila con defaults si no existe |
| `upsert_noise_config(config)` | Actualiza la config de ruido |
| `list_destinations(world_id)` | Todos los destinos del mundo |
| `create_destination(dest)` / `update_destination(dest)` / `delete_destination(id)` | CRUD de destinos |
| `list_paths(destination_id)` | Rutas de un destino con sus steps |
| `create_path(path)` / `update_path(path)` / `delete_path(id)` | CRUD de rutas |
| `mark_path_dead(path_id)` | Marca is_dead=True y resetea contador |
| `increment_path_failures(path_id)` | Incrementa consecutive_failures_count |
| `reset_path_failures(path_id)` | Resetea consecutive_failures_count y is_dead=False |
| `get_villages_for_world(world_id)` | Lista aldeas del mundo (para validar orígenes VILLAGE_) |
| `upsert_village(village)` | Crea o actualiza una aldea |

---

## Divergencias código/spec conocidas

| ID | Spec dice | Código hace | Impacto |
|---|---|---|---|
| DIV-N01 | `noise-navigate-to-origin.md` (EP-N15) en estado `ready-for-impl` | **No implementado**. El método `navigate_to_origin` y el endpoint EP-N15 no existen en el código. | El botón "Ir al inicio" del wizard no está operativo. El spec es completo y válido; falta el paso de implementación. |
| DIV-N02 | `noise-frequency-and-destination-weight.md`: frecuencia como MM:SS + peso controlable | No implementado. `NoiseConfig` usa `req_per_hour_min/max`. El campo `frequency_weight` de `NoiseDestination` existe en BD pero no expuesto en la UI. | La frecuencia de ruido no es configurable desde la UI como MM:SS. Pendiente de gate guardian + gate desarrollador-apis. |

🔖 Última revisión: 2026-06-04 (documento creado — sistema noise EP-N01..N14 documentado; EP-N15 y noise-frequency no implementados)
