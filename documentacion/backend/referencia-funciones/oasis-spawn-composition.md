# Referencia — mecánica de spawn de oasis (EP-SPAWN)

Cubre todas las funciones introducidas en la feature `oasis-spawn-mechanics-stats` (2026-06-02).

## Ubicación de los artefactos

| Elemento | Ruta |
|---|---|
| Catálogo de spawn (Python) | `core/game_data/oasis_spawn_catalog.py` |
| Catálogo de spawn (JS) | `frontend/src/utils/oasisSpawnCatalog.js` |
| Puerto abstracto | `core/ports/attack_report_port.py` — `AttackReportPort.get_oasis_spawn_composition` |
| Implementación del port | `adapters/db/attack_report_sqlite_adapter.py` — `AttackReportSQLiteAdapter.get_oasis_spawn_composition` |
| Helpers de módulo | `adapters/db/attack_report_sqlite_adapter.py` — funciones sueltas al final del fichero |
| Endpoint HTTP | `adapters/api/routes/attack_reports.py` — `GET /attack-reports/stats/oasis/spawn-composition` |
| Panel educativo | `frontend/src/components/attack-reports/SpawnMechanicsPanel.jsx` |
| Panel planificador | `frontend/src/components/attack-reports/OasisCombatPlannerPanel.jsx` |
| Sección por jugador | `frontend/src/components/attack-reports/PlayerOasisSection.jsx` |
| Sección por aldea | `frontend/src/components/attack-reports/CityOasisSection.jsx` |
| Tests | `tests/test_oasis_spawn_composition_api.py` |
| Spec funcional | `docs/specs/oasis-spawn-mechanics-stats.md` |
| Spec de diseño | `docs/design/oasis-spawn-mechanics.md` |

---

## Catálogo de spawn — `core/game_data/oasis_spawn_catalog.py`

Este módulo no tiene funciones; expone únicamente constantes. Es la **única fuente de verdad** para timers y sets de animales en toda la aplicación (RN-CAT-01).

### `NATURE_ORDINALS: dict[str, int]`

Diccionario nombre-español → ordinal (1–10). No se usa directamente en el backend de producción (los queries trabajan con ordinales enteros), pero sirve como referencia de mapeo y para tests.

**Por qué existe:** los ordinales de Travian son estables entre versiones e idiomas; los nombres en español son solo una clave de lectura humana para los desarrolladores.

### `SPAWN_TIMER_S: dict[int, int]`

Ordinal → segundos de spawn en servidor x1. Rata = 300 s (5 min), Araña = 360 s (6 min), ..., Elefante = 840 s (14 min).

**Por qué existe:** los timers son fijos por mecánica del juego (RN-CAT-01). Centralizar aquí evita que cualquier módulo los hardcodee y permite ajustarlos en un único lugar. La fórmula de peor combinación y la clasificación de estado spawn leen este dict.

**Impacto en negocio:** es la base del cálculo de cuántos animales pueden aparecer entre dos envíos consecutivos al oasis (Pieza 3). Cualquier error aquí se propaga a todos los cálculos ofensivos del usuario.

### `OASIS_TYPE_SETS: dict[str, set[int]]`

Tipo de oasis (`"hierro"` / `"arcilla"` / `"madera"` / `"cereal"`) → set de ordinales del set normal de animales. El set de cereal contiene todos los ordinales (1–10), lo que hace necesaria la métrica de Jaccard para la inferencia de tipo.

**Por qué existe:** cada tipo de oasis tiene una composición de animales característica. Un animal observado fuera del set es una "anomalía" y no se incluye en el cálculo del peor caso.

**Impacto en negocio:** determina qué animales son "normales" en cada oasis y cuáles son raros/anómalos. Afecta al cálculo del peor caso y a las etiquetas visuales del panel.

### `COOLDOWN_THRESHOLD_S: int`

`4 * 3600 = 14 400 segundos` (4 horas). Umbral heurístico a partir del cual se considera que el oasis ha entrado en cooldown. Definido aquí para ser ajustable sin tocar el adaptador.

**Por qué existe:** el umbral exacto de cooldown de Travian no está documentado públicamente. Se usa una heurística conservadora de 4 horas como proxy. Si el conocimiento del juego cambia, solo se modifica esta constante.

---

## Método del port — `get_oasis_spawn_composition`

```python
@abstractmethod
async def get_oasis_spawn_composition(self, timer_min: int) -> dict:
```

### Parámetros

| Parámetro | Tipo | Descripción |
|---|---|---|
| `timer_min` | `int` | Intervalo de envío elegido por el usuario (minutos). Valores válidos: `6 \| 7 \| 10 \| 15`. Validado en el router **antes** de llegar al port; el adapter puede asumir que es válido. |

### Retorno

```json
{
  "computed_at": "2026-06-02T10:00:00.000000+00:00",
  "timer_min": 10,
  "oasis": [
    {
      "coord_x_dest": -70,
      "coord_y_dest": 73,
      "total_attacks": 15,
      "last_attack": "2026-06-01T22:15:00",
      "inferred_type": "cereal",
      "confidence": "medium",
      "spawn_status": "respawning",
      "elapsed_seconds": 43200.0,
      "attackers": [
        {"player": "CrazyMouse", "village": "05 Caesar On Leave"},
        {"player": "GonnaDie",   "village": "05"}
      ],
      "species": [
        {
          "animal_ordinal": 9,
          "icon_url": "/static/icons/nature_9.png",
          "avg_present_per_burst": 4.5,
          "max_present_per_burst": 7,
          "is_anomaly": false,
          "spawn_timer_s": 780,
          "worst_case_count": 5,
          "def_infantry_contribution": 700,
          "def_cavalry_contribution": 1000
        }
      ],
      "worst_case_summary": {
        "def_infantry_total": 2020,
        "def_cavalry_total": 2560
      }
    }
  ]
}
```

**Por qué existe:** reemplaza la métrica `avg_regen_per_hour`, que mezclaba la ráfaga de spawn con el cooldown posterior y producía un número inutilizable para la toma de decisiones tácticas. El nuevo método expone la composición real por ráfaga, el peor caso calculable y el estado del oasis.

**Impacto en negocio:** permite al usuario saber con qué animales se va a encontrar al atacar un oasis, cuántos en el peor caso para un intervalo de tiempo dado, y si el oasis está generando actualmente o en cooldown.

---

## Implementación — `AttackReportSQLiteAdapter.get_oasis_spawn_composition`

La implementación se organiza en 9 pasos claramente comentados en el código. A continuación se describe cada uno con sus decisiones de diseño.

### Paso 1 — Carga de estadísticas de defensa de animales nature

Llama al helper privado `_load_nature_defense_stats()` que lee `seeds/game_data/troop_stats.json` filtrando `tribe == "nature"`. Devuelve `{ordinal: {def_infantry, def_cavalry}}`.

**Por qué importación tardía del catálogo:** `SPAWN_TIMER_S`, `OASIS_TYPE_SETS` y `COOLDOWN_THRESHOLD_S` se importan dentro del método (no a nivel de módulo) para evitar dependencia circular durante el arranque.

### Paso 2 — Query de composición (`comp_sql`)

```sql
SELECT r.coord_x_dest, r.coord_y_dest, a.animal_ordinal,
       AVG(a.present) AS avg_present,
       MAX(a.present) AS max_present,
       COUNT(*) AS burst_count
FROM attack_report_animals a
JOIN attack_reports r ON r.id = a.report_id
WHERE a.present > 0
GROUP BY r.coord_x_dest, r.coord_y_dest, a.animal_ordinal
ORDER BY r.coord_x_dest, r.coord_y_dest, a.animal_ordinal
```

El filtro `WHERE a.present > 0` excluye los registros en los que el animal no estaba en ese spawn concreto (RN-COMP-01). Un oasis con un animal observado en 1 de 5 ataques tiene `burst_count = 1` para ese animal.

### Paso 3 — Query de metadatos (`meta_sql_precise`)

Subconsulta correlacionada para obtener el `utc_offset` del reporte con `MAX(attacked_at)` por oasis. Necesario para calcular `elapsed_seconds` con la hora correcta del servidor.

**Nota de implementación:** el código define también `meta_sql` (versión simplificada que asume un único offset por oasis) pero usa `meta_sql_precise` en producción. La versión simplificada es aceptable para el MVP porque la mayoría de oasis tienen un único offset.

### Paso 3b — Cargas de atribución (anti N+1)

Dos queries ejecutadas una sola vez fuera del bucle de oasis:

1. `SELECT name FROM villages` → `all_village_names: list[str]`
2. `SELECT coord_x_dest, coord_y_dest, GROUP_CONCAT(DISTINCT origin_village_name) AS blobs_raw FROM attack_reports GROUP BY coord_x, coord_y` → `blobs_by_oasis: dict[tuple, list[str]]`

**Por qué no el JOIN farm_slots:** hasta la v2.4, la atribución usaba `farm_slots` (qué aldeas tenían el oasis en su lista). El bug verificado en BD real era que aldea "05" era invisible porque sus oasis aparecían en farm_lists de 00/01/02/03 y la regla "primario gana" los atribuía a ellas. Desde v2.5 la atribución se hace exclusivamente desde los blobs `origin_village_name` de los reportes reales.

**Por qué TODO de `world_id`:** la query de villages no filtra por `world_id` porque `attack_reports.world_id` es NULL en la versión actual del MVP. Cuando se resuelva esa deuda técnica, la query debe filtrar por world.

### Paso 4 — Indexación de composición

Los resultados de `comp_sql` se agrupan en `comp_by_oasis: dict[tuple, list[dict]]` para acceso O(1) por coordenadas en el bucle de oasis.

### Pasos 5–9 — Bucle por oasis

Para cada oasis encontrado en `meta_rows`:

1. Se llama a `_infer_type(observed, comp_list)` — ver función más abajo.
2. Se llama a `_calc_elapsed_seconds(last_attack_str, utc_offset_str, computed_at)`.
3. Se llama a `_spawn_status(elapsed_s, tipo, ...)` — ver función más abajo.
4. Se llama a `_infer_attackers(key, blobs_by_oasis, all_village_names)` — ver función más abajo.
5. Por cada animal de la composición, se llama a `_worst_case_count(...)`.
6. Se construye `species_list` con todos los campos de la respuesta.
7. Se acumula `worst_case_summary` solo para animales no anómalos.
8. Se ordena el resultado: oasis con tipo inferido primero, luego por `last_attack DESC`.

---

## Helpers de módulo

### `_infer_type(observed_ordinales, comp_list) -> tuple[str | None, str | None]`

**Qué hace:** recibe el conjunto de ordinales observados en el oasis y devuelve `(tipo, confidence)`.

**Algoritmo de Jaccard:**
```python
score[tipo] = len(observed & set_base) / len(observed | set_base)
tipo = argmax(score)
```

En caso de empate: gana el tipo con menor cardinal de set (más específico); si persiste el empate, se elige alfabéticamente el primero.

**Por qué Jaccard y no solapamiento bruto (`|intersección|`):** el solapamiento bruto hace que `cereal` (set universal `{1..10}`) iguale o supere el score de cualquier tipo en cuanto el oasis tiene 4+ especies, porque su intersección con cualquier set es máxima. Esto anula la detección de anomalías y clasifica incorrectamente. Jaccard penaliza el set universal dividiendo por la unión: un oasis de hierro `{1,2,4}` obtiene `1.0` en hierro y `0.30` en cereal, aunque ambos tengan intersección `3`.

Tabla de verificación:

| Observados | hierro | arcilla | madera | cereal | Tipo (Jaccard) |
|---|---|---|---|---|---|
| `{1,2,4}` | **1.00** | 0.50 | 0.00 | 0.30 | hierro |
| `{1,2,5}` | 0.50 | **1.00** | 0.20 | 0.30 | arcilla |
| `{5,6,7}` | 0.00 | 0.20 | **1.00** | 0.30 | madera |
| `{1,2,5,8}` (coco en arcilla) | 0.40 | **0.75** | 0.14 | 0.40 | arcilla, anomalía={8} |

**Confianza:** `"medium"` si `sum(burst_count) >= 3`, `"low"` si no. La confianza "high" no existe en v1 (no hay cap de animales para validar completamente la inferencia).

**Caso especial:** si `observed_ordinales` está vacío → `(None, None)`. Si el score máximo es 0 (ninguna intersección, EC-11) → se elige el tipo con menor set, confianza `"low"`.

**Impacto en negocio:** un tipo inferido incorrecto hace que la UI muestre el tipo erróneo y que las anomalías y el peor caso se calculen sobre el set equivocado. La confianza "low" avisa al usuario de que el dato es provisional.

---

### `_calc_elapsed_seconds(last_attack_str, utc_offset_str, computed_at) -> float`

**Qué hace:** convierte `last_attack` (string naive ISO, hora local del servidor) y `utc_offset` (string tipo `"+01:00"`) a UTC y calcula `(computed_at - attack_utc).total_seconds()`.

Reutiliza `_parse_utc_offset` (helper preexistente en el adapter).

**Guarda de EC-09:** si el resultado es negativo (reloj del servidor adelantado), devuelve `0.0`. El oasis queda en estado `"respawning"`.

**Por qué la hora local y el offset por separado:** el campo `attacked_at` en BD es la hora local del servidor de Travian. El offset se guarda también del reporte. Si solo guardásemos la hora local sin el offset, no podríamos calcular el elapsed real en UTC.

---

### `_spawn_status(elapsed_s, tipo, oasis_type_sets, spawn_timer_s, cooldown_threshold_s) -> str`

**Qué hace:** clasifica el oasis en uno de tres estados:

- `"respawning"` (verde): `elapsed_s <= max(timers del set base)`. El animal más lento del set aún no ha completado su primer ciclo — el oasis puede estar generando activamente.
- `"cooldown"` (rojo): `elapsed_s > cooldown_threshold_s` (por defecto 4 horas). El oasis probablemente no está generando.
- `"unknown"` (gris): tipo no inferido, o zona intermedia entre los dos umbrales anteriores.

**Por qué dos umbrales distintos en lugar de uno:** existe una zona intermedia de duración incierta entre "el animal más lento acaba de terminar" y "4 horas desde el último ataque". En esa zona no hay suficiente información para clasificar con certeza. La UI representa esa zona como gris para no confundir al usuario.

**Por qué la detección ocurre en el backend:** para evitar depender del reloj del navegador del usuario, que puede diferir del reloj del servidor de Travian.

**Impacto en negocio:** el usuario usa este estado para decidir si vale la pena atacar el oasis ahora o si es mejor esperar.

---

### `_worst_case_count(animal_ordinal, max_present, tipo, is_anomaly, timer_s, spawn_timer_s) -> int | None`

**Qué hace:** dado un intervalo `timer_s` (segundos), calcula cuántos animales de la especie `animal_ordinal` podría haber en el oasis en el peor caso:

```python
extra_spawns = floor(timer_s / spawn_timer_s[animal_ordinal])
worst_case = max_present + extra_spawns
```

Devuelve `None` si el tipo es `null` o el animal es anómalo.

**Por qué `max_present` como cota superior:** usar el máximo histórico es una cota conservadora (pesimista). El usuario prefiere sobredimensionar su ataque a encontrarse con más animales de los esperados.

**Por qué las anomalías devuelven `None`:** las anomalías son raras y su presencia distorsionaría el umbral defensivo táctico. Se muestran en la UI pero no se planifica contra ellas.

**Impacto en negocio:** este número es la respuesta a la pregunta táctica "¿cuántos animales tendré que matar si envío un ataque cada N minutos?".

---

### `_FROM_VILLAGE_MARKERS: tuple[str, ...]`

Constante de módulo (no es función). Lista de marcadores textuales en múltiples idiomas que preceden al nombre de aldea en el campo `origin_village_name` de los reportes.

Marcador verificado con datos reales del usuario: `"from village"` (inglés). El resto son best-effort extensibles. El servidor del usuario está en inglés.

**Por qué lista en lugar de regex:** simplicidad y rendimiento. El algoritmo hace `find()` sobre el blob en minúsculas, que es O(n). Una regex sería más flexible pero añadiría complejidad innecesaria para el volumen actual.

---

### `_extract_player_village_from_blob(blob, all_village_names) -> list[tuple[str, str]]`

**Qué hace:** extrae todos los pares `(player, village)` de un blob `origin_village_name`. Algoritmo en tres pasos:

**Paso A — Quitar tag de alianza:** si el blob empieza con `[`, se elimina el bloque `[Alianza] ` hasta el primer `]` inclusive.

**Paso B — Buscar marcador:** se busca el primer marcador de `_FROM_VILLAGE_MARKERS` (case-insensitive). Si se encuentra y hay texto no vacío a ambos lados:
- `player` = texto antes del marcador (stripped)
- `village_raw` = texto después del marcador (stripped)

Si no se encuentra: `player = "Desconocido"`, `village_raw = None`.

**Paso C — Canonizar village:** se busca si algún nombre de `all_village_names` es substring de `village_raw` (o del blob completo si `village_raw` es None). El nombre más largo que coincida gana (evita que "Norte" gane sobre "Aldea del Norte"). Si hay empate de longitud, se generan varios pares. Si no hay ningún match, se usa `village_raw` directamente (o `"Desconocido"` si también es None).

**Nunca devuelve lista vacía:** mínimo `[("Desconocido", "Desconocido")]` (RN-ACCT-05).

**Por qué post-hoc en lugar de parsear en el ingesta:** modificar el parser de reportes afectaría la clave UNIQUE de la tabla `attack_reports` (que incluye `origin_village_name`). El enfoque post-hoc no requiere migración de datos ni rompe la unicidad.

**Limitación conocida:** si el servidor está en un idioma sin marcador en `_FROM_VILLAGE_MARKERS`, `player` cae a `"Desconocido"`. La lista es extensible sin tocar la lógica principal.

**Impacto en negocio:** permite al usuario ver qué aldeas (y qué jugadores de su cuenta) han atacado cada oasis, y organizar la vista en el frontend por la jerarquía Jugador → Aldea → Oasis.

---

### `_infer_attackers(key, blobs_by_oasis, all_village_names) -> list[dict[str, str]]`

**Qué hace:** para las coordenadas `key = (coord_x, coord_y)` de un oasis, recopila todos los pares `(player, village)` únicos de todos sus blobs y los devuelve ordenados por player A-Z, luego village A-Z.

```python
blobs = blobs_by_oasis.get(key, [])
found: set[tuple[str, str]] = set()
for blob in blobs:
    found.update(_extract_player_village_from_blob(blob, all_village_names))
```

Devuelve `[{"player": "Desconocido", "village": "Desconocido"}]` si `found` está vacío.

**Por qué conjuntos (set) para la deduplicación:** varios reportes pueden tener el mismo blob de atacante. El set elimina duplicados en O(1) por inserción.

**Impacto en negocio:** si un oasis tiene múltiples atacantes distintos (distintas cuentas o aldeas del usuario), aparece bajo cada uno de ellos en el frontend, con los mismos datos de stats del oasis. No hay filtrado por "cuenta propia del usuario" — eso es responsabilidad visual del frontend.

---

## Endpoint HTTP — `GET /attack-reports/stats/oasis/spawn-composition`

### Firma

```python
@router.get("/attack-reports/stats/oasis/spawn-composition", status_code=200)
async def get_oasis_spawn_composition(
    request: Request,
    timer_min: int = Query(..., description="Intervalo de timer en minutos. Valores válidos: 6, 7, 10, 15."),
) -> dict:
```

### Validación

El endpoint valida `timer_min` antes de llamar al port:

```python
if timer_min not in (6, 7, 10, 15):
    raise HTTPException(status_code=400, detail=f"timer_min debe ser uno de: 6, 7, 10, 15. Recibido: {timer_min}")
```

Si `timer_min` está ausente o no es entero, FastAPI devuelve `422` automáticamente.

### Errores

| Código | Condición |
|---|---|
| `200` | Éxito, incluso con `oasis: []` |
| `400` | `timer_min` fuera de `{6, 7, 10, 15}` |
| `422` | `timer_min` ausente o no entero (FastAPI automático) |
| `500` | Error inesperado de BD (detail genérico, sin stack trace) |

### Posición en el router

Declarado antes de EP-TD y EP-06 (`/stats/oasis`) siguiendo la convención C6 del router: las rutas literales más largas se declaran primero para evitar que FastAPI capture "spawn-composition" como parte de un path param `{id}`.

### Sin Accept-Language

EP-SPAWN no usa `Accept-Language`. Devuelve ordinales enteros y las URLs de iconos; el frontend resuelve los nombres localizados con la clave `NATURE_{ordinal}` de su catálogo i18n. Esta política es coherente con EP-06, EP-09 y EP-10.

---

## Frontend — catálogo JS (`oasisSpawnCatalog.js`)

Espejo JavaScript de `core/game_data/oasis_spawn_catalog.py`. Se usa exclusivamente en el panel educativo `SpawnMechanicsPanel` (datos estáticos, sin llamada a la API).

**Divergencia de representación:** `OASIS_TYPE_SETS` es un `dict[str, set[int]]` en Python y un `dict[str, int[]]` (arrays, no sets) en JavaScript. El comportamiento es equivalente; solo cambia la estructura de datos del lenguaje.

Exporta además `OASIS_TYPE_ORDER = ['hierro', 'arcilla', 'madera', 'cereal']` para controlar el orden de filas en la tabla de sets, y `formatTimerMmSs(seconds)` que convierte segundos a `"MM:SS"`.

**Riesgo de divergencia:** si `oasis_spawn_catalog.py` cambia (nuevos tipos, nuevos timers), hay que actualizar `oasisSpawnCatalog.js` manualmente. No hay mecanismo de sincronización automática en v1.

---

## Frontend — `SpawnMechanicsPanel`

Panel educativo estático. No llama a la API. Usa los datos de `oasisSpawnCatalog.js` directamente.

### Props

| Prop | Tipo | Descripción |
|---|---|---|
| `lang` | `string` | Idioma activo (para `Intl`, aunque actualmente no lo usa directamente). |
| `t` | `function` | Función de traducción i18n. |
| `vacíoBD` | `boolean` | Si `true`, el panel se despliega automáticamente (la BD está vacía y el usuario necesita contexto). |

### Estado de colapso

Se persiste en `localStorage` bajo la clave `'spawn_panel_open'`. Primera visita → abierto (y se marca la clave con `'1'`). Segunda visita → cerrado por defecto. Si `vacíoBD` es `true`, se fuerza abierto independientemente de localStorage.

**Lógica exacta del comportamiento de primera visita:** el estado inicial se calcula en el inicializador de `useState`. Si la clave `LS_KEY` no existe en localStorage, se devuelve `true` Y se escribe `'1'` en localStorage. Esto significa que la lógica de "segunda visita" funciona incluso si el usuario recarga la página en la misma sesión.

### Sub-componentes internos

- `TimersTable` — tabla de 10 filas (rata → elefante) con columnas Animal | Orden | Timer (min). La columna "Orden" usa `className="hidden md:table-cell"` para ocultarse en móvil (P3).
- `SetsTable` — tabla de 4 filas por tipo de oasis; cada celda muestra chips de `NatureIcon` + nombre. El nombre del animal usa `className="hidden md:inline"` en móvil (solo icono).

---

## Frontend — `OasisCombatPlannerPanel`

Panel operativo principal. Consume EP-SPAWN y organiza los datos en la jerarquía Jugador → Aldea → Oasis.

### Props

| Prop | Tipo | Descripción |
|---|---|---|
| `data` | `dict \| null` | Respuesta EP-SPAWN o null si está cargando/error. |
| `loading` | `boolean` | Muestra skeleton. |
| `error` | `string \| null` | Muestra banner de error + reintentar. |
| `onRetry` | `() => void` | Callback para el botón Reintentar. |
| `onGoToIngest` | `() => void` | Callback para el botón "Ir a Ingresar" en estado vacío. |
| `timerMin` | `number` | Intervalo activo (6/7/10/15). Estado gestionado por `StatsTab`. |
| `onTimerChange` | `(n: number) => void` | Callback al cambiar el intervalo. |
| `lang` | `string` | Idioma activo. |
| `t` | `function` | Función de traducción. |

### Construcción del mapa anidado (`buildPlayerMap`)

```javascript
function buildPlayerMap(oasisArray) {
  // playerMap: { playerName → { villageName → [oasis] } }
  for (const oasis of oasisArray) {
    for (const { player, village } of oasis.attackers) {
      playerMap[player][village].push(oasis)
    }
  }
  // Ordena jugadores A-Z con "Desconocido" al final
  // Ordena aldeas A-Z con "Desconocido" al final
}
```

Un oasis atacado por `N` pares `(player, village)` aparece `N` veces en el mapa — una vez bajo cada par. Esto es correcto por diseño (RN-ACCT-06).

**Por qué `sortEntries`:** el backend ya ordena `attackers` por player A-Z, pero `buildPlayerMap` construye el mapa desde el array del backend donde un oasis puede estar en muchos jugadores. El reordenamiento local en el frontend garantiza que la jerarquía del DOM esté siempre ordenada independientemente del orden de llegada de los oasis.

### Sub-componentes internos

| Componente | Descripción |
|---|---|
| `TimerSelector` | 4 botones pill (6/7/10/15 min). Activo: fondo `--accent-subtle`, borde `--accent-subtle-border`, texto `--accent-text`. Deshabilitado en estado vacío. `aria-pressed` y `aria-disabled` implementados. |
| `SpawnStatusDot` | Punto de 7px + texto. Verde (`--success`) = respawning, rojo (`--danger`) = cooldown, gris (`--text-disabled`) = unknown. El color siempre va acompañado del texto (nunca es la única señal). |
| `OasisTypeBadge` | Pill con el tipo localizado + confianza en texto secundario (`·baja confianza` / `·media confianza`). Si `type` es null, muestra "—". |
| `AnimalChip` | Chip compacto: `NatureIcon` + conteo + badge `"anom."` si es anomalía. En la fila Media muestra `max_present_per_burst`; en la fila Peor muestra `worst_case_count` como número plano (sin "×"). El backend calcula y envía también las contribuciones defensivas, pero **no se muestran** en v2.2 por decisión del usuario (el "×N" generaba confusión interpretándose como multiplicador). |
| `OasisBlock` | Bloque de un oasis: cabecera con coords+tipo+estado, cuerpo con filas Media y Peor. Si `inferred_type` es null, muestra solo nota inline. |
| `PlannerSkeleton` | 3 bloques animados con pulso (respeta `prefers-reduced-motion`). |
| `ErrorBanner` | `role="alert"` + mensaje + botón Reintentar. |
| `EmptyState` | Icono + texto + CTA "Ir a Ingresar". |

---

## Divergencias código / spec detectadas

### DIV-SPAWN-01 — `meta_sql` vs `meta_sql_precise`

**Spec §9 paso 3:** describe una subconsulta correlacionada para obtener el `utc_offset` del reporte con `MAX(attacked_at)`.

**Código real:** define dos queries: `meta_sql` (simplificada, no correlacionada) y `meta_sql_precise` (correlacionada). **Solo se usa `meta_sql_precise`** en producción (`async with self._conn.execute(meta_sql_precise)`). `meta_sql` queda definida pero sin usar.

**Impacto:** ninguno en producción. Es código muerto menor. Se recomienda eliminar `meta_sql` en una limpieza futura.

### DIV-SPAWN-02 — Confianza en EC-11 (sin intersección)

**Spec §4.2 EC-11:** "Se devuelve el tipo con mayor score (aunque sea 1 de 3) con `confidence: "low"`".

**Código real:** cuando `max_score == 0.0`, el código toma `candidates = list(OASIS_TYPE_SETS.keys())` y los ordena por cardinal, eligiendo el de menor set. La confianza se calcula a partir del `burst_count` total — si el oasis tiene solo 1 observación, devuelve `"low"`. El spec esperaba `"low"` explícitamente en este caso, que el código produce de forma natural si `total_bursts < 3`.

**Evaluación:** no hay divergencia de comportamiento real. La confianza es siempre `"low"` para un oasis de 1 sola observación (el único caso realista de EC-11).

### DIV-SPAWN-03 — `"from village "` (variante con espacio extra) eliminada del código

**Spec §4.7 RN-CITY-12:** la constante `_FROM_VILLAGE_MARKERS` incluye `"from village "` (con espacio extra al final) como variante defensiva.

**Código real:** `_FROM_VILLAGE_MARKERS` en `adapters/db/attack_report_sqlite_adapter.py` **no incluye** la variante con espacio extra. Solo incluye `"from village"` (sin espacio extra).

**Impacto:** la variante con espacio extra era redundante porque el algoritmo hace `.strip()` sobre `village_candidate` después de aplicar el marcador, por lo que `"from village "` y `"from village"` producen el mismo resultado. Sin impacto funcional.

### DIV-SPAWN-04 — Fuerza defensiva no mostrada en la UI

**Spec original (v2.1):** la tabla fusionada incluiría columnas `Def. inf.` y `Def. cav.` por animal y totales por oasis.

**Código real (v2.2):** `OasisCombatPlannerPanel` **no muestra** estas columnas. El backend sigue calculando y enviando `def_infantry_contribution`, `def_cavalry_contribution` y `worst_case_summary` en la respuesta, pero el frontend los ignora por completo. La decisión fue tomada por el usuario en la iteración v2.2 porque `"×N"` generaba confusión.

**Impacto:** los campos defensivos están disponibles en la API si se necesitan en el futuro. No hay deuda técnica en el backend. El spec de diseño (v2.2) ya documenta esta decisión.

---

🔖 Última revisión: 2026-06-02 (creado — feature oasis-spawn-mechanics-stats)
