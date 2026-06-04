# Reportes de ataques a oasis — Documento funcional y de negocio

> Audiencias: (1) desarrolladores — sección de código; (2) stakeholders/PO — sección de negocio.
> Para la referencia rápida de funciones ver `documentacion/backend/referencia-funciones/attack-report-temporal-distribution.md` y `referencia-funciones/oasis-spawn-composition.md`.
> Spec de referencia: `docs/specs/bd-ataques-oasis.md` y sus addendums.

---

## Qué resuelve esta feature

El usuario de Travian ataca oasis de animales (guardianes de tipo Nature) y necesita acumular ese historial para responder:

- **¿Qué robé en total?** (y qué perdí en tropas) — rentabilidad de la operación de farmeo.
- **¿Qué animales aparecen en cada oasis y con qué frecuencia?** — para calibrar el equipo de ataque.
- **¿Cuándo atacar?** — distribución temporal según la cadencia de farmeo elegida.

Antes de esta feature el usuario calculaba todo esto a mano, con hoja de cálculo o de memoria. El bot lo automatiza: el usuario pega el texto del reporte de Travian y el sistema lo extrae, persiste y analiza.

---

## Objetivo de negocio

Convertir los reportes de ataque en datos accionables: saber qué oasis merecen el esfuerzo (ratio robado/perdido positivo), qué combinación de tropas necesitar y con qué frecuencia atacar.

---

## Actores

| Actor | Rol |
|---|---|
| Usuario (único) | Pega reportes, consulta historial, aplica filtros, borra reportes. |
| Parser del sistema | Extrae datos del texto crudo del reporte sin que el usuario tenga que rellenar ningún formulario. |
| Extensión Chrome | (Feature pendiente de documentar en `funcionalidades/extension-chrome.md`) Captura reportes automáticamente desde el navegador. |

No hay autenticación ni roles: el sistema es single-tenant (uso local).

---

## Arquitectura del módulo

```
frontend (React)
  └── AttackReportsPage
        ├── IngestTab          — pegar y previsualizar reportes (EP-01 + EP-02)
        ├── HistoryTab         — historial filtrable (EP-03 + EP-04 + EP-05)
        ├── StatsTab           — estadísticas (EP-06..EP-10, EP-SPAWN, EP-balance)
        └── CadenciaTab        — distribución temporal (EP-TD)

backend (FastAPI)
  └── adapters/api/routes/attack_reports.py   — 12 endpoints
  └── adapters/db/attack_report_sqlite_adapter.py  — lógica SQL
  └── core/use_cases/attack_report_parser.py  — parser multilenguaje
  └── core/ports/attack_report_port.py        — contrato hexagonal
```

---

## Módulo de código: parser (`core/use_cases/attack_report_parser.py`)

### `parse_attack_report(raw_text, db_port=None)`

**Qué hace:** recibe el texto crudo pegado por el usuario (texto del reporte de Travian tal como aparece en el juego) y devuelve un objeto `AttackReportPreview` con todos los datos extraídos: timestamp del ataque, coordenadas del oasis, nombre de aldea atacante, tropas enviadas/perdidas/supervivientes, animales presentes/muertos/supervivientes, botín (4 recursos + capacidad), inventario del héroe (opcional), y flags `already_exists`/`existing_id`.

**Por qué existe:** Travian no tiene API. La única forma de extraer datos de los reportes es parsear el texto que el usuario copia de la interfaz web del juego. El parser es un módulo autónomo sin I/O de red ni base de datos (salvo la consulta de unicidad si se pasa `db_port`), lo que facilita testarlo exhaustivamente.

**Impacto en negocio:** Es la puerta de entrada de todos los datos. Sin un parser correcto, no hay estadísticas fiables.

**Multilenguaje sin configuración:** el índice invertido de nombres de animales (`_NATURE_INDEX`) se construye desde `core/i18n/catalog/base/troops.json`, que tiene los 10 animales NATURE en los 25 idiomas soportados (215 entradas, 0 colisiones). El parser detecta automáticamente el idioma del reporte sin que el usuario tenga que especificarlo.

**Modo "reporte perdido" (§17):** cuando el atacante pierde, Travian muestra `?` en lugar de cantidades. El parser detecta este modo y guarda `present/killed/survived = NULL` (semánticamente distinto de `0`, que significa "el oasis estaba vacío de esa especie").

**Excepciones que lanza:**
| Excepción | Situación |
|---|---|
| `MultipleReportsError` | Hay más de un bloque de reporte en el texto pegado |
| `NotNatureOasisError` | El defensor no contiene animales NATURE |
| `UnrecognizedAnimalError` | Un nombre de animal no está en el índice de 25 idiomas |
| `DefeatReportParseError` | Reporte perdido con formato mixto `?`/dígitos (corrupto) |
| `ReportFormatError` | Formato general no reconocible (sin fecha, sin coordenadas) |

### `_get_nature_index()`

**Qué hace:** construye (lazy, una sola vez en memoria) el diccionario `name_lower → ordinal` desde el catálogo multilingüe. Clave: `{rat: 1, ratte: 1, araña: 2, spider: 2, …}`.

**Por qué existe:** el índice global permite detectar el idioma del reporte sin overhead (carga `troops.json` ~30 KB una sola vez).

---

## Módulo de código: router (`adapters/api/routes/attack_reports.py`)

El router declara 12 endpoints. El orden de declaración importa (C6 del spec): las rutas literales deben ir antes de `/{id}` para que FastAPI no capture "stats" como ID.

### Endpoints implementados (verdad del código)

| EP | Método | Ruta | Código éxito | Descripción |
|---|---|---|---|---|
| EP-01 | POST | `/attack-reports/parse` | 200 | Parse sin guardar; comprueba unicidad para el preview |
| EP-02 | POST | `/attack-reports` | 201 | Guarda el reporte (re-parsea el raw_text como fuente de verdad) |
| EP-03 | GET | `/attack-reports` | 200 | Historial paginado (filtros: x+y, from_date, to_date, limit, offset) |
| EP-08 | GET | `/attack-reports/oasis` | 200 | Lista de oasis únicos con resumen |
| EP-07 | GET | `/attack-reports/stats/bounty` | 200 | Botín saqueado (global o por oasis) |
| EP-09 | GET | `/attack-reports/stats/global` | 200 | Estadísticas globales de todos los oasis combinados |
| EP-balance | GET | `/attack-reports/stats/balance` | 200 | Pérdidas (valor tropas muertas) vs robado (botín+héroe), con filtro de fecha |
| EP-10 | GET | `/attack-reports/stats/oasis/comparison` | 200 | Comparativa de tasas de reaparición por oasis |
| EP-SPAWN | GET | `/attack-reports/stats/oasis/spawn-composition` | 200 | Composición típica + peor combinación por oasis (requiere `timer_min`) |
| EP-TD | GET | `/attack-reports/stats/oasis/temporal-distribution` | 200 | Distribución temporal por cadencia (requiere `interval_minutes` y `Accept-Language`) |
| EP-06 | GET | `/attack-reports/stats/oasis` | 200 | Estadísticas completas de un oasis (x+y obligatorios) — incluye balance |
| EP-04 | GET | `/attack-reports/{id}` | 200 | Detalle de un reporte (re-parsea raw_text para enriquecer con iconos y tribu) |
| EP-05 | DELETE | `/attack-reports/{id}` | 204 | Borrar reporte (CASCADE a tropas y animales) |

**Nota sobre EP-TD:** es el único endpoint del router que requiere `Accept-Language` obligatorio (vía dependencia `get_language`), porque devuelve nombres de animales localizados. El resto del router devuelve datos numéricos o texto crudo del propio reporte (no localizado por el backend).

**Nota sobre `attacker_tribe`:** el preview y el detalle incluyen `attacker_tribe` (la tribu del atacante resuelta por el parser). Es un campo añadido tras la implementación inicial (migración M-01). Los reportes pre-migración tienen `attacker_tribe = NULL` y se reparsean retroactivamente.

**Nota sobre `attacker_cost_loss`:** el preview (EP-01) y el detalle (EP-04) calculan el coste en recursos de las tropas perdidas usando los datos de juego (kirilloid). Si la tribu no es resoluble, este campo es `null`. No estaba en el spec original — es una mejora implementada.

### `_preview_to_dict(preview, attacker_cost_loss=None)`

**Qué hace:** serializa un `AttackReportPreview` a dict JSON incluyendo URLs de iconos (`/static/icons/{tribe}_{ordinal}.png` para tropas, `/static/icons/nature_{ordinal}.png` para animales). Garantía C2: `hero_inventory` es campo raíz, nunca anidado dentro de `bounty`.

**Por qué existe:** centraliza la serialización del preview para que EP-01 (parse) y EP-04 (detalle) devuelvan el mismo shape, permitiendo al frontend reutilizar el mismo componente `TravianReport` para ambos casos.

### `_compute_attacker_cost_loss(preview, game_data_port)`

**Qué hace:** para cada tropa perdida con `lost > 0` y `troop_ordinal` resoluble, multiplica las bajas por el coste unitario de entrenamiento (de los datos de kirilloid) y suma. Devuelve `{wood, clay, iron, crop, total}` o `None` si la tribu es desconocida.

**Por qué existe:** el usuario necesita saber si el balance neto fue positivo (robó más de lo que perdió en coste de tropas). Sin este dato, el "neto" de BalanceSection no sería comparable.

---

## Módulo de código: adaptador SQLite (`adapters/db/attack_report_sqlite_adapter.py`)

### Esquema de tablas (3 tablas)

```
attack_reports                   — cabecera (1 fila por reporte)
attack_report_attacker_troops    — tropas atacantes (N filas por reporte)
attack_report_animals            — animales defensores (M filas por reporte)
```

Las tablas hijas tienen `ON DELETE CASCADE`: borrar un reporte borra automáticamente sus tropas y animales.

**Columna `attacked_at`:** almacena la **hora local del servidor de Travian** (ISO 8601 naive, sin zona horaria). **Esta es la fuente de verdad para la hora del ataque.** Ver divergencia DIVERG-01.

**Columna `attacker_tribe`:** añadida por migración M-01. Se rellena re-parseando el `raw_text` de reportes existentes. Permite calcular el coste de bajas del atacante.

### Función de módulo: `_calc_regen_rates(repopulation_gaps)`

**Qué hace:** recibe la lista de gaps con animales regenerados y calcula la tasa media de regeneración por hora (`avg_regen_per_hour`) para cada especie de animal.

**Por qué existe:** la tasa de regeneración es una métrica derivada que mide "cuántos animales por hora se regeneran en este oasis". Se usa en EP-06 (stats de oasis individual) y EP-09 (stats globales).

**Regla de exclusión:** solo cuenta intervalos con `gap_seconds > 0`, `regenerated >= 0` y no `NULL`. El primer ataque a un oasis siempre tiene `regenerated = NULL` (no hay ataque previo), y esos no cuentan.

### Función de módulo: `_parse_utc_offset(s)`

**Qué hace:** convierte el offset UTC normalizado del reporte (p. ej. `"+01:00"`) a `timedelta`. Si el string es inválido, devuelve `timedelta(0)` como defensa (asume UTC).

**Por qué existe:** el cálculo de `hours_since_last_attack` en EP-10 (comparativa) necesita convertir la hora local del servidor a UTC antes de calcular el tiempo transcurrido. Sin este helper, el tiempo transcurrido estaría sesgado por la zona horaria del servidor de Travian.

### Migración `_migrate_add_attacker_tribe(conn)`

**Qué hace:** agrega la columna `attacker_tribe` a `attack_reports` (idempotente: captura `OperationalError` si ya existe) y re-parsea todos los reportes con `attacker_tribe IS NULL` para poblar el campo retroactivamente.

**Por qué existe:** la tribu del atacante fue un campo añadido tras la implementación inicial del módulo. La migración permite poblar este dato en los reportes existentes sin que el usuario tenga que volver a pegarlos.

**Anomalía detectada:** la función `_migrate_add_attacker_tribe` se llama **dos veces** en `ensure_tables()` (líneas 323 y 331 del adaptador). La segunda llamada es redundante (el `WHERE attacker_tribe IS NULL` no encontrará nada la segunda vez porque la primera ya lo rellenó todo), pero no es dañina gracias a la condición `IS NULL`. Ver DIVERG-03.

---

## Módulo de código: frontend

### IngestTab

Contiene el área de texto donde el usuario pega el reporte. Al pulsar "Analizar" (o `⌘↵`) llama a EP-01. Si el parse es exitoso, muestra el componente `TravianReport` (preview) con todos los datos. Si `already_exists=true`, muestra un aviso en dorado con enlace al reporte existente. Si el usuario confirma, llama a EP-02.

### HistoryTab

Tabla paginada de reportes (EP-03). Filtros: coordenadas X+Y y rango de fechas (inputs de texto con validación regex + popover de calendario). Al pulsar la fila o el botón "▶" abre el drawer `ReportDetailDrawer` (EP-04). El botón papelera llama a EP-05.

### StatsTab (pestaña Estadísticas)

Orden de los paneles (v2.3 — verdad del código en `StatsTab.jsx`):
1. `SpawnMechanicsPanel` — panel educativo colapsable (datos estáticos del catálogo)
2. `BalanceSection` — balance Perdido vs Robado (EP-balance)
3. `OasisCombatPlannerPanel` — composición típica + peor combinación (EP-SPAWN)
4. `GlobalOasisStatsPanel` — estadísticas globales (EP-09)
5. `OasisList` — lista de oasis (EP-08), al hacer clic carga `OasisStatsPanel` (EP-06)

### CadenciaTab (pestaña Cadencia de farmeo)

Contiene `AnimalFrequencyPanel` que llama a EP-TD con el `interval_minutes` seleccionado. Agrupa los resultados en 5 pestañas internas por tipo de oasis inferido (Hierro, Barro, Madera, Cereal, Sin clasificar).

### BalanceSection / BalanceGrid

`BalanceGrid` es un componente exportado que reutiliza tanto `BalanceSection` (stats globales) como `OasisStatsPanel` (stats de un oasis). Muestra una tabla de 3 columnas (recurso | Perdido | Robado) + fila de neto con color semántico: verde si neto ≥ 0, rojo si neto < 0.

---

## Reglas de negocio

### Ingesta de reportes

**RN-01:** Solo se aceptan reportes donde el defensor es NATURE (oasis de animales). Rechaza reportes de ataques a aldeas o de defensa.

**RN-02:** El índice de nombres de animales es global (25 idiomas, sin colisiones). El usuario no necesita especificar el idioma.

**RN-05:** Clave de unicidad: `(coord_x_dest, coord_y_dest, attacked_at, origin_village_name)`. Un reporte ya existente devuelve 409 (no se duplica silenciosamente).

**RN-06:** Los supervivientes se calculan: `sent - lost` para tropas y `present - killed` para animales. No se leen del reporte (aunque Travian los muestra).

**RN-08:** La hora del ataque se guarda verbatim como hora local del servidor (sin convertir a UTC). Ver divergencia DIVERG-01.

**RN-09:** Solo un reporte por pegado. Si el usuario pega varios reportes de golpe, el parser rechaza con error descriptivo.

### Balance de operaciones

**RN-B01 — Qué cuenta como "Perdido":** el valor en recursos del coste de entrenamiento de las tropas muertas, calculado a partir de los datos de kirilloid (`cost_wood/clay/iron/crop` por tropa). Si la tribu del atacante no es resoluble (`attacker_tribe = NULL`), las pérdidas no se pueden calcular y el reporte no contribuye al total de perdido.

**RN-B02 — Qué cuenta como "Robado":** `bounty_wood + bounty_clay + bounty_iron + bounty_crop` (el drop de recursos de los animales muertos) + `hero_inventory` (recursos añadidos al inventario del héroe, si los había). Ambas fuentes se suman.

**RN-B03 — Reportes sin tribu:** cuando `reports_without_tribe > 0`, la UI muestra una nota informativa en dorado explicando que esos reportes no contribuyen al total de pérdidas.

**RN-B04 — Neto:** `neto = robado_total - perdido_total`. Puede ser negativo (el oasis costó más de lo que rindió en ese período).

### Estadísticas globales (`get_global_oasis_stats`)

**RN-G01 — Denominador correcto para el % de aparición global:** el porcentaje de aparición de cada animal no se calcula sobre el total de reportes, sino sobre los `eligible_reports`: solo los reportes de oasis donde ese animal **ha aparecido al menos una vez** en algún ataque. Un oasis de hierro nunca tiene lobos; contar sus reportes como denominador de la frecuencia de lobos distorsionaría la métrica. Ver spec `bd-ataques-oasis-global-pct-aparicion.md`.

**RN-G02 — LAG particionado:** el cálculo de regeneración usa `PARTITION BY (coord_x_dest, coord_y_dest, animal_ordinal)`. Los gaps no cruzan entre oasis distintos.

### Distribución temporal (EP-TD)

**RN-TD01 — Ventana temporal:** dado un `interval_minutes`, el endpoint selecciona solo los reportes donde el gap con el ataque anterior al mismo oasis cae en la ventana `[interval_minutes - umbral, interval_minutes + umbral]`. Esto filtra datos representativos de esa cadencia.

**RN-TD02 — Agrupación por tipo de oasis:** los resultados se agrupan en 5 secciones fijas: hierro, barro, madera, cereal, sin_clasificar. El tipo se infiere con Jaccard (ver `oasis-spawn-mechanics.md`).

---

## Divergencias código / spec detectadas

### DIVERG-01 — `attacked_at` NO se guarda en UTC (a pesar de lo que dice el spec)

**Spec (bd-ataques-oasis.md §8 RN-08):** "El timestamp se almacena en UTC derivado restando el offset."

**Código real (`attack_report_sqlite_adapter.py`, DDL comentario línea 53):** "Hora local del servidor de Travian, verbatim, sin zona horaria (ISO 8601 naive)."

**Descripción:** el parser extrae la hora local del servidor tal como la muestra Travian y la almacena sin convertirla a UTC. El campo `utc_offset` se guarda por separado para que la conversión pueda hacerse en tiempo de consulta. Esto es consistente con la memoria `travian-report-hora-verbatim.md` (la conversión a UTC introduce ambigüedad de visualización).

**Impacto:** las consultas que calculan `hours_since_last_attack` (EP-10) sí usan el `utc_offset` para normalizar. Las queries de ordenación cronológica (`ORDER BY attacked_at`) son correctas mientras todos los reportes pertenezcan al mismo servidor con el mismo offset.

**Estado:** comportamiento intencionado confirmado. El spec no fue actualizado.

### DIVERG-02 — EP-balance no estaba en el spec original

**Spec original (bd-ataques-oasis.md):** no define ningún endpoint `/attack-reports/stats/balance`.

**Código real:** el endpoint existe como `GET /attack-reports/stats/balance` y sirve los datos de `BalanceSection`. Fue añadido durante la implementación de la feature `bd-ataques-oasis-balance-perdidos-robados`.

**Estado:** endpoint implementado y funcional. Se documenta aquí como adición al spec.

### DIVERG-03 — `_migrate_add_attacker_tribe` se llama dos veces en `ensure_tables`

**Código real (líneas 323 y 331 de `attack_report_sqlite_adapter.py`):** la función de migración se invoca dos veces consecutivas dentro de `ensure_tables()`.

**Impacto:** la segunda llamada no hace nada (el `WHERE attacker_tribe IS NULL` no encuentra filas porque la primera ya las rellenó), pero añade una query extra al arranque. No es un bug, pero es ruido técnico.

**Estado:** redundancia confirmada. Pendiente de limpieza.

### DIVERG-04 — `attacker_tribe` y `attacker_cost_loss` no estaban en el spec

**Spec original:** el response de EP-01 y EP-04 no incluye `attacker_tribe` ni `attacker_cost_loss`.

**Código real:** ambos campos están presentes en el response y en el componente `ReportPreview`/`TravianReport`.

**Estado:** campos añadidos durante la implementación de la feature de balance. No representan un problema; enriquecen el response.

---

## Deuda técnica conocida

| Referencia | Descripción |
|---|---|
| TR-HIST-01 | La columna `world_id` en `attack_reports` es siempre NULL. Los reportes son globales (sin asociación a cuenta ni mundo). Diseñado para extensión futura. |
| TR-HIST-02 | No hay importación masiva de reportes. El usuario pega uno a uno. La extensión Chrome automatiza esta parte pero está documentada por separado. |
| TR-HIST-03 | `avg_regen_per_hour` sigue presente en EP-09 (stats globales). Pendiente de evaluar si retirar cuando el frontend deje de consumirlo. |

---

## Cómo leer las pantallas

### Pestaña Ingresar (IngestTab)

El usuario pega el texto completo del reporte de Travian en el área de texto y pulsa "Analizar". El sistema muestra el preview con todos los datos interpretados (tropas, animales, botín). Si el reporte ya existe, aparece un aviso en dorado. Si todo está bien, el usuario pulsa "Guardar".

### Pestaña Historial (HistoryTab)

Tabla cronológica (más reciente primero) con todos los reportes guardados. Las columnas son: fecha, oasis (coordenadas), aldea desde la que se atacó, botín total y bajas del atacante (en rojo si hubo). Pulsar en cualquier fila abre el detalle completo.

### Pestaña Estadísticas (StatsTab)

Compuesta por 5 paneles independientes: Mecánica de spawn (educativo), Balance global, Planificador de combate por oasis, Estadísticas globales y Lista de oasis. Los paneles cargan de forma independiente (un error en uno no bloquea los demás).

### Pestaña Cadencia de farmeo (CadenciaTab)

Muestra qué animales esperar según la frecuencia de ataque elegida. Agrupa por tipo de oasis para facilitar la planificación.

---

🔖 Última revisión: 2026-06-04 (creado — feature oasis-reportes-ataques: módulo completo de BD de ataques, 13 endpoints, parser multilenguaje, balance perdido/robado, estadísticas globales, distribución temporal)
