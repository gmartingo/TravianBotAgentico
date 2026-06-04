# Referencia — `AttackReportSQLiteAdapter` y funciones de módulo

## Ubicación

| Elemento | Ruta |
|---|---|
| Puerto abstracto | `core/ports/attack_report_port.py` — `AttackReportPort` |
| Implementación | `adapters/db/attack_report_sqlite_adapter.py` — `AttackReportSQLiteAdapter` |
| Router | `adapters/api/routes/attack_reports.py` |
| Parser | `core/use_cases/attack_report_parser.py` |
| Spec | `docs/specs/bd-ataques-oasis.md` y addendums |

---

## Funciones de módulo (nivel de fichero)

### `_calc_regen_rates(repopulation_gaps)`

```python
def _calc_regen_rates(repopulation_gaps: list[dict]) -> list[dict]:
```

**Qué hace:** recibe la lista de gaps con animales regenerados (output de las queries LAG) y calcula la tasa media de regeneración por hora (`avg_regen_per_hour`) para cada especie de animal.

**Por qué existe:** la tasa de regeneración es una métrica derivada reutilizada por `get_oasis_stats` (EP-06) y `get_global_oasis_stats` (EP-09). Está extraída como función de módulo para evitar duplicar la lógica.

**Reglas de exclusión (casos borde):**
- `gap_seconds = None` o `<= 0` → se ignora ese gap (primer ataque o dato corrupto).
- `regenerated = None` o `< 0` → se ignora ese animal en ese gap.
- Un animal sin ningún intervalo válido no aparece en el resultado (no se incluye con tasa 0.0).

**Retorna:** lista de `{animal_ordinal, animal_name, avg_regen_per_hour, valid_intervals}`, ordenada por ordinal. Lista vacía si no hay gaps válidos.

---

### `_parse_utc_offset(s)`

```python
def _parse_utc_offset(s: str) -> timedelta:
```

**Qué hace:** convierte el offset UTC normalizado del reporte (p. ej. `"+01:00"`, `"-05:30"`) a `timedelta`. Si el string es inválido, devuelve `timedelta(0)` (comportamiento defensivo — asume UTC).

**Por qué existe:** el campo `attacked_at` se almacena como hora local del servidor. Para calcular el tiempo transcurrido desde el último ataque en el comparador EP-10, es necesario normalizar a UTC. Sin este helper, `hours_since_last_attack` estaría sesgado por la zona horaria del servidor de Travian.

---

### `_migrate_add_attacker_tribe(conn)`

```python
async def _migrate_add_attacker_tribe(conn: aiosqlite.Connection) -> None:
```

**Qué hace:**
1. `ALTER TABLE attack_reports ADD COLUMN attacker_tribe TEXT` (idempotente: captura `OperationalError` si ya existe).
2. Recupera todos los reportes con `attacker_tribe IS NULL`.
3. Para cada uno: `parse_attack_report(raw_text)` → extrae `attacker_tribe` → `UPDATE`.
4. Si el parse falla: loguea warning y deja `NULL` (no aborta).

**Por qué existe:** la tribu del atacante fue añadida tras la implementación inicial. La migración rellena este dato retroactivamente para los reportes ya guardados.

**Anomalía conocida:** se llama dos veces en `ensure_tables()` (líneas 323 y 331). La segunda llamada es redundante (el `WHERE IS NULL` no encuentra nada) pero inofensiva. Pendiente de limpieza (DIVERG-03 en `funcionalidades/oasis-reportes-ataques.md`).

---

## Métodos del adaptador

### `ensure_tables()`

**Qué hace:** crea las tres tablas (`attack_reports`, `attack_report_attacker_troops`, `attack_report_animals`) con sus índices si no existen (DDL idempotente). Ejecuta `_migrate_add_attacker_tribe`. Añade el índice `idx_attack_reports_tribe_attacked_at`.

**Por qué existe:** patrón de todo el proyecto — el adaptador es responsable de su propio DDL, sin Alembic ni migraciones externas.

---

### `save_report(preview, raw_text)`

```python
async def save_report(self, preview: AttackReportPreview, raw_text: str) -> int:
```

**Qué hace:** inserta el reporte en las 3 tablas en una transacción. Devuelve el `id` asignado. Si viola la restricción `UNIQUE`, lanza `DuplicateReportError` con el id del reporte existente.

**Flujo:**
1. INSERT en `attack_reports` con todos los campos de cabecera.
2. INSERT en `attack_report_attacker_troops` (una fila por tropa).
3. INSERT en `attack_report_animals` (una fila por animal).
4. COMMIT.

**Parámetros:**
- `preview` — objeto `AttackReportPreview` con todos los datos parseados.
- `raw_text` — el texto crudo original, para re-parseo futuro si el algoritmo mejora.

---

### `report_exists(coord_x, coord_y, attacked_at, origin)`

```python
async def report_exists(self, coord_x: int, coord_y: int, attacked_at: str, origin: str) -> int | None:
```

**Qué hace:** consulta si ya existe un reporte con la clave de unicidad `(coord_x, coord_y, attacked_at, origin_village_name)`. Devuelve el `id` si existe, `None` si no.

**Por qué existe:** se usa en EP-01 (parse) para que el preview ya avise si el reporte es duplicado, antes de que el usuario confirme el guardado.

---

### `get_report(report_id)`

```python
async def get_report(self, report_id: int) -> dict | None:
```

**Qué hace:** devuelve el reporte completo (cabecera + tropas + animales) o `None` si no existe. Incluye el campo `raw_text` para que EP-04 (detalle) pueda re-parsear y enriquecer con iconos y tribu.

---

### `list_reports(...)`

```python
async def list_reports(self, x, y, from_date, to_date, limit, offset) -> dict:
```

**Qué hace:** historial paginado con filtros opcionales. Devuelve `{total, items, cumulative_bounty}`. El `cumulative_bounty` es la suma del botín de **todos** los reportes del rango filtrado actual (no una running sum).

**Por qué `cumulative_bounty` no es una running sum:** el spec original definía una running sum con window function. La implementación lo simplificó a la suma total del rango filtrado, que es lo que consume `BalanceSection`. Es una desviación del spec que no afecta a la funcionalidad.

---

### `delete_report(report_id)`

```python
async def delete_report(self, report_id: int) -> bool:
```

**Qué hace:** borra el reporte por id. El `ON DELETE CASCADE` de las tablas hijas se encarga de borrar tropas y animales asociados. Devuelve `True` si existía, `False` si no.

---

### `get_oasis_stats(x, y)`

```python
async def get_oasis_stats(self, x: int, y: int) -> dict:
```

**Qué hace:** estadísticas de un oasis concreto: total de ataques, rango temporal, aparición de animales (`animal_appearances`), gaps de repoblación (`repopulation_gaps`) y tasas de regeneración (`animal_regen_rates`).

**Caso sin reportes (C7):** si no hay ningún reporte para esas coordenadas, devuelve 200 con `total_attacks: 0` y arrays vacíos. No devuelve 404.

**Queries SQL usadas:**
- `COUNT + MIN/MAX` para metadatos del oasis.
- `WHERE present > 0 GROUP BY animal_ordinal` para apariciones.
- CTE con `LAG(survived) OVER (PARTITION BY animal_ordinal ORDER BY attacked_at)` para regeneración.
- `LAG(attacked_at) OVER (ORDER BY attacked_at)` + `UNIXEPOCH` para gaps temporales.

---

### `get_bounty_stats(x, y)`

```python
async def get_bounty_stats(self, x=None, y=None) -> dict:
```

**Qué hace:** suma de botín (wood, clay, iron, crop, total) y conteo de reportes. Sin coordenadas: global. Con coordenadas: específico del oasis.

**Nota:** no calcula "perdido", solo "robado" (el botín de animales). El cálculo de pérdidas está en `get_balance_stats`.

---

### `get_global_oasis_stats()`

**Qué hace:** estadísticas de todos los oasis combinados. Incluye `eligible_reports` por animal para el cálculo correcto del % de aparición (ver RN-G01 en `funcionalidades/oasis-reportes-ataques.md`). El LAG de regeneración está particionado por `(coord_x, coord_y, animal_ordinal)` para que los gaps no crucen entre oasis distintos.

---

### `list_oasis_summaries(x, y)`

**Qué hace:** lista de oasis únicos con resumen básico (número de ataques, último ataque, botín total). Ordenados por `last_attack DESC`. Filtro opcional por coordenadas exactas.

---

### `get_all_oasis_regen_comparison()`

**Qué hace:** comparativa de tasas de reaparición por oasis para EP-10. Calcula `_calc_regen_rates` por oasis usando queries particionadas (sin N llamadas a `get_oasis_stats`). Incluye `hours_since_last_attack` usando `_parse_utc_offset` para normalizar la hora del último ataque a UTC antes de restar.

**Comportamiento especial:** solo incluye las especies que han tenido `present > 0` en ese oasis en algún momento. Las especies nunca presentes no aparecen ni con tasa 0.0.

---

## Funciones del router

### `_preview_to_dict(preview, attacker_cost_loss=None)`

**Qué hace:** serializa `AttackReportPreview` a dict JSON incluyendo URLs de iconos de tropas y animales. Garantiza que `hero_inventory` es campo raíz (no anidado en `bounty`). Incluye `attacker_tribe` y `attacker_cost_loss`.

**Usada por:** EP-01 (parse) y EP-04 (detalle), para que ambos devuelvan el mismo shape.

### `_compute_attacker_cost_loss(preview, game_data_port)`

**Qué hace:** multiplica tropas perdidas × coste unitario de entrenamiento (datos de kirilloid) por tribu. Devuelve `{wood, clay, iron, crop, total}` o `None` si la tribu es desconocida.

### `_parse_or_422(raw_text)`

**Qué hace:** wrapper de `parse_attack_report` que convierte las excepciones del parser en `HTTPException` 422 con mensajes legibles. Centraliza el manejo de errores de EP-01 y EP-02.

---

🔖 Última revisión: 2026-06-04 (creado — referencia de funciones del módulo attack-reports: adaptador SQLite, funciones de módulo y helpers del router)
