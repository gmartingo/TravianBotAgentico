# Referencia — `get_animal_temporal_distribution`

## Ubicación

| Elemento | Ruta |
|---|---|
| Puerto abstracto | `core/ports/attack_report_port.py` — clase `AttackReportPort` |
| Implementación | `adapters/db/attack_report_sqlite_adapter.py` — clase `AttackReportSQLiteAdapter` |
| Endpoint HTTP | `adapters/api/routes/attack_reports.py` — `GET /attack-reports/stats/oasis/temporal-distribution` |
| Cliente JS | `frontend/src/api/client.js` — `api.getAnimalTemporalDistribution(intervalMinutes)` |
| Tests | `tests/test_animal_temporal_distribution_api.py` (54 tests: T-TD01..T-TD35 v3 + T-TD36..T-TD48 v4 + criterios CA) |
| Spec | `docs/specs/bd-ataques-oasis-temporal-distribution.md` (v4) |
| Helper reutilizado | `infer_type(observed_ordinales, comp_list)` — función pública de módulo en `attack_report_sqlite_adapter.py` (elevada desde `_infer_type` en v3) |
| Modelos Pydantic | `_TDResponse`, `_TDOasisTypeSection`, `_TDAnimalItem`, `_TDAvgBounty`, `_TDTotalAnimals`, `_TDOasisCoord`, `_TDWindow` en `attack_reports.py` (v4) |

---

## Firma del método (port)

```python
@abstractmethod
async def get_animal_temporal_distribution(
    self,
    interval_minutes: int,
    lang: str,
    translation_port,
) -> dict:
    ...
```

### Parámetros

| Parámetro | Tipo | Descripción |
|---|---|---|
| `interval_minutes` | `int` | Cadencia de farmeo en minutos. Valores válidos: `6\|7\|10\|15\|30\|60\|120\|180\|240\|300`. Validado en el router antes de llegar al adapter. |
| `lang` | `str` | Código de idioma validado (`es`, `en`, etc.). Los 25 soportados en `SUPPORTED_LANGUAGES`. |
| `translation_port` | `TranslationPort` | Puerto de traducción para resolver nombres de animales localizados. |

### Retorno (v4)

```python
{
    "interval_minutes": 240,        # eco del parámetro recibido
    "interval_label": "4h",         # etiqueta legible: "6 min","7 min",..."5h+"
    "window": {
        "lower_min": 240,           # límite inferior en minutos (inclusive)
        "upper_min": 300,           # límite superior en minutos (exclusive); null para bin 300
        "is_open": False,           # True solo para interval_minutes=300
    },
    "n_reports_in_window": 42,      # suma de n_reports_in_section de las 5 secciones
    "types": [                      # siempre 5 secciones en orden fijo
        {
            "oasis_type": "hierro",          # clave canónica
            "oasis_type_label": "Hierro",    # etiqueta de presentación fija
            "n_oasis": 3,                    # oasis distintos de este tipo con gaps en ventana
            "n_oasis_low_confidence": 1,     # oasis con confidence="low" (<3 bursts)
            "n_reports_in_section": 18,      # report_ids distintos de este tipo en ventana
            # [v4] Coordenadas de los oasis de este tipo con gap en la ventana
            "oasis_coords": [                # [] si sección vacía (RN-TD24)
                {"x": -15, "y": 23},         # enteros crudos, sin formateo
                {"x": -12, "y": 28},         # ordenados (y ASC, x ASC)
            ],
            # [v4] Botín medio por reporte — denominador=n_reports_in_section (incluye derrotas) (RN-TD22/23)
            "avg_bounty": {                  # todos a 0 si sección vacía
                "wood": 45, "clay": 12, "iron": 318, "crop": 22,
                "total": 397,               # media del (w+c+i+cr) por reporte, NO suma de medias
            },
            # [v4] Total de animales por reporte — regla TODO-O-NADA (RN-TD21)
            "total_animals": {              # avg/mode/max null/[]/null si n_valid=0
                "avg": 12.50,              # None si n_valid=0
                "mode": [10, 12],          # [] si n_valid=0
                "max": 24,                 # None si n_valid=0
                "n_valid": 15,             # reportes sin ningún present=NULL
                "n_total": 18,             # = n_reports_in_section (invariante)
            },
            "animals": [                     # vacío si n_reports_in_section=0
                {
                    "animal_ordinal": 1,
                    "animal_name": "Rata",
                    "icon_url": "/static/icons/nature_1.png",
                    "avg_present": 2.50,     # None si n_valid=0
                    "mode_present": [2],     # [] si n_valid=0; lista si empate en moda
                    "max_present": 6,        # [v4] None si n_valid=0 (RN-TD20)
                    "n_total": 18,           # gaps de este tipo con este animal (incluye derrotas)
                    "n_valid": 15,           # gaps con present IS NOT NULL
                }
            ]
        },
        # ... arcilla, madera, cereal, sin_clasificar (siempre presentes aunque vacías)
        # Sección vacía example: { ..., "n_reports_in_section": 0,
        #   "oasis_coords": [], "avg_bounty": {wood:0,...,total:0},
        #   "total_animals": {avg:null,mode:[],max:null,n_valid:0,n_total:0}, "animals": [] }
    ]
}
```

**Orden fijo de las 5 secciones:** `hierro` → `arcilla` → `madera` → `cereal` → `sin_clasificar`.

**Etiquetas de presentación:**

| `oasis_type` (clave) | `oasis_type_label` |
|---|---|
| `hierro` | `"Hierro"` |
| `arcilla` | `"Barro"` ← OJO: la etiqueta es "Barro", no "Arcilla" |
| `madera` | `"Madera"` |
| `cereal` | `"Cereal"` |
| `sin_clasificar` | `"Sin clasificar"` |

---

## Binning por umbral inferior (Opción B) — sin cambio desde v2

Dado `interval_minutes = F`, la ventana es `[F * 60, F_next * 60)` en segundos, donde `F_next` es el siguiente valor del conjunto en orden ascendente. Para `F = 300` la ventana es `[18000, ∞)` (abierta).

| `interval_minutes` | Ventana (segundos) | `interval_label` |
|--------------------|---------------------|------------------|
| 6   | [360, 420)    | "6 min" |
| 7   | [420, 600)    | "7 min" |
| 10  | [600, 900)    | "10 min" |
| 15  | [900, 1800)   | "15 min" |
| 30  | [1800, 3600)  | "30 min" |
| 60  | [3600, 7200)  | "1h" |
| 120 | [7200, 10800) | "2h" |
| 180 | [10800, 14400)| "3h" |
| 240 | [14400, 18000)| "4h" |
| 300 | [18000, ∞)    | "5h+" |

Gaps `< 360s` (< 6 min) se descartan silenciosamente (ningún bin los recoge).

---

## Algoritmo de implementación v4 (adapter)

### Paso 1 (v3) — Inferencia de tipo por oasis

```sql
-- Misma query que usa EP-SPAWN para la composición (consistencia garantizada)
SELECT r.coord_x_dest, r.coord_y_dest, a.animal_ordinal, COUNT(*) AS burst_count
FROM attack_report_animals a
JOIN attack_reports r ON r.id = a.report_id
WHERE a.present > 0
GROUP BY r.coord_x_dest, r.coord_y_dest, a.animal_ordinal
```

Resultado agrupado por oasis → llamada a `infer_type(observed_ordinales, comp_list)`:
- Devuelve `(tipo, confidence)` donde `tipo ∈ {"hierro","arcilla","madera","cereal",None}`.
- `confidence = "medium"` si `sum(burst_count) >= 3`, `"low"` si `< 3`.
- `tipo = None` si `observed_ordinales` está vacío (solo derrotas) → va a `sin_clasificar`.

### Paso 2 (v4) — Query LAG con CTE (ampliada con bounty)

```sql
-- CTE que calcula gaps a nivel de REPORTE (una fila por ataque al oasis).
-- v4: incluye bounty_wood/clay/iron/crop del reporte para avg_bounty.
-- El botín aparece repetido en cada fila de animal del JOIN posterior, pero
-- se deduplica en Python con type_bounty[tipo] = {rid: (w,c,i,cr)}.
WITH report_gaps AS (
    SELECT
        r.id AS report_id,
        r.coord_x_dest, r.coord_y_dest,
        r.attacked_at,
        r.bounty_wood, r.bounty_clay, r.bounty_iron, r.bounty_crop,  -- [v4]
        CAST(
            (UNIXEPOCH(r.attacked_at) -
             UNIXEPOCH(LAG(r.attacked_at) OVER w)) AS INTEGER
        ) AS gap_seconds
    FROM attack_reports r
    WINDOW w AS (
        PARTITION BY r.coord_x_dest, r.coord_y_dest
        ORDER BY r.attacked_at
    )
)
SELECT rg.report_id, rg.coord_x_dest, rg.coord_y_dest,
       rg.bounty_wood, rg.bounty_clay, rg.bounty_iron, rg.bounty_crop,  -- [v4]
       a.animal_ordinal, a.animal_name, a.present, rg.gap_seconds
FROM report_gaps rg
JOIN attack_report_animals a ON a.report_id = rg.report_id
ORDER BY a.animal_ordinal, rg.coord_x_dest, rg.coord_y_dest, rg.attacked_at
```

> **Por qué la CTE:** si el JOIN con `attack_report_animals` se hace ANTES del LAG, el window
> tiene múltiples filas por reporte (una por animal). El LAG entonces toma la fila anterior del
> MISMO reporte (el animal anterior) en lugar del REPORTE anterior. La CTE calcula primero los
> gaps a nivel de reporte (una fila por ataque al oasis) y luego explota por animal.

### Paso 3 — Filtrado

- `gap_seconds IS NULL` (primer ataque por oasis) → descartado (RN-TD02).
- `gap_seconds <= 0` (relojes inconsistentes) → descartado (EC-TD07).
- `gap_seconds < 360` (< 6 min) → descartado (RN-TD04).

### Paso 4 — Filtro de ventana

```python
if is_open:
    window_rows = [r for r in valid_rows if r["gap_seconds"] >= lower_sec]
else:
    window_rows = [r for r in valid_rows if lower_sec <= r["gap_seconds"] < upper_sec]
```

### Paso 5 (v3) — Etiquetado; Paso 6 (v3+v4) — Agrupación y estructuras auxiliares

```python
# Etiquetar cada gap con el tipo de su oasis (del mapa del Paso 1)
# Si el oasis no está en el mapa (sin present>0) → tipo=None → sin_clasificar
tipo, confidence = oasis_type_map.get((cx, cy), (None, None))
rid = row["report_id"]
present_val = row["present"]

# v3: acumular por (tipo, animal_ordinal)
type_oasis_ids[tipo].add((cx, cy))
if confidence == "low":
    type_oasis_low[tipo].add((cx, cy))
type_report_ids[tipo].add(rid)
type_groups[tipo][ordinal]["n_total"] += 1
if present_val is not None:
    type_groups[tipo][ordinal]["valids"].append(present_val)

# [v4] botín: deduplicar por report_id (RN-TD25 — el botín NO se acumula por fila de animal)
if rid not in type_bounty[tipo]:
    type_bounty[tipo][rid] = (row["bounty_wood"], row["bounty_clay"],
                               row["bounty_iron"], row["bounty_crop"])

# [v4] total_animals: regla TODO-O-NADA (RN-TD21)
if rid not in type_report_nulls[tipo]:
    type_report_nulls[tipo][rid] = False
    type_report_sums[tipo][rid] = 0
if present_val is None:
    type_report_nulls[tipo][rid] = True   # este reporte queda excluido de n_valid
else:
    type_report_sums[tipo][rid] += present_val
```

### Paso 6bis — Estadísticas por (tipo, animal)

- **Media** (RN-TD06): `round(sum(valids) / len(valids), 2)` si `len > 0`, else `None`.
- **Moda** (RN-TD07): `Counter(valids)`, empates como lista ASC. `[]` si vacío.
- **[v4] Máximo** (RN-TD20): `max(valids)` si `len > 0`, else `None`.

### Paso 7 — Localización

```python
name_entries = translation_port.get_troop_names_by_tribe(Tribe.NATURE, lang)
names_by_ordinal = {entry["ordinal"]: entry["nombre"] for entry in name_entries}
# Fallback: animal_name de la BD si el ordinal no está en el catálogo
localized_name = names_by_ordinal.get(ordinal, data["name_raw"])
```

**Importante:** el enum se accede como `Tribe.NATURE` (mayúsculas) y la clave del dict devuelto por `JsonTranslationAdapter` es `"nombre"` (no `"name"`).

### Paso 8 (v3+v4) — Construcción del array types

```python
TYPE_ORDER = ["hierro", "arcilla", "madera", "cereal", None]
TYPE_LABELS = {"hierro":"Hierro","arcilla":"Barro","madera":"Madera","cereal":"Cereal",None:"Sin clasificar"}

# [v4] Helpers:
# _build_avg_bounty(tipo): media botín — denominador=n_reports_in_section, incluye derrotas (RN-TD22/23)
#   Si sección vacía → {wood:0, clay:0, iron:0, crop:0, total:0}
# _build_total_animals(tipo): distribución del total de animales (RN-TD21)
#   Regla TODO-O-NADA: excluye de n_valid los reportes con cualquier present=NULL
#   Si sección vacía → {avg:null, mode:[], max:null, n_valid:0, n_total:0}
# _build_oasis_coords(tipo): oasis distintos con gap en ventana, (y ASC, x ASC) (RN-TD24)
#   Si sección vacía → []

types = []
for tipo in TYPE_ORDER:
    oasis_type_key = tipo if tipo is not None else "sin_clasificar"
    types.append({
        "oasis_type":             oasis_type_key,
        "oasis_type_label":       TYPE_LABELS[tipo],
        "n_oasis":                len(type_oasis_ids[tipo]),
        "n_oasis_low_confidence": len(type_oasis_low[tipo]),
        "n_reports_in_section":   len(type_report_ids[tipo]),
        "oasis_coords":           _build_oasis_coords(tipo),    # [v4]
        "avg_bounty":             _build_avg_bounty(tipo),       # [v4]
        "total_animals":          _build_total_animals(tipo),    # [v4]
        "animals":                _build_animals(tipo),          # v4: cada animal incluye max_present
    })
n_reports_in_window = sum(len(type_report_ids[t]) for t in TYPE_ORDER)
```

---

## Endpoint HTTP

**Ruta:** `GET /attack-reports/stats/oasis/temporal-distribution`

**Query params:**

| Parámetro | Tipo | Default | Validación |
|---|---|---|---|
| `interval_minutes` | `integer` | `240` | `{6,7,10,15,30,60,120,180,240,300}`; otro entero → 400 con detail que lista los 10 valores; no entero → 422 |

**Headers:**

| Header | Obligatorio | Descripción |
|---|---|---|
| `Accept-Language` | Sí | Ausente o código no soportado → 400 |

**Errores:**

| Código | Condición |
|---|---|
| 400 | `interval_minutes` fuera de `{6,7,10,15,30,60,120,180,240,300}` |
| 400 | `Accept-Language` ausente o idioma no soportado |
| 422 | `interval_minutes` no es entero (FastAPI automático) |
| 500 | Error inesperado de BD (detail genérico sin stack trace) |

---

## Posición en el router

EP-TD está declarado **después de EP-SPAWN y antes de EP-06** (`/stats/oasis`) para que FastAPI resuelva la ruta literal sin colisión con `/{id}`.

---

## Cliente JS

```js
// frontend/src/api/client.js
api.getAnimalTemporalDistribution(intervalMinutes = 240)
// → GET /attack-reports/stats/oasis/temporal-distribution?interval_minutes=<im>
// Accept-Language inyectado automáticamente por buildHeaders() desde localStorage
// Schema v4: respuesta incluye types[5] (hierro/arcilla/madera/cereal/sin_clasificar).
// Cada sección: oasis_coords, avg_bounty, total_animals (v4) + animals[].
// animals[].max_present: int|null — máximo present observado (v4).
// El campo animals[] de v2 ya no existe en el nivel raíz.
```

---

## Función helper reutilizada: `infer_type`

```python
# adapters/db/attack_report_sqlite_adapter.py (función pública de módulo, v3)
def infer_type(
    observed_ordinales: set[int],
    comp_list: list[dict],
) -> tuple[str | None, str | None]:
    """
    Infiere el tipo de oasis por Jaccard |∩|/|∪| contra OASIS_TYPE_SETS.
    Usada por EP-SPAWN (get_oasis_spawn_composition) y EP-TD.
    Elevada desde _infer_type en v3 para evitar duplicar Jaccard (RN-TD14).
    """
```

Ambos endpoints (EP-SPAWN y EP-TD) llaman a `infer_type`. Un oasis que EP-SPAWN clasifica como "hierro" también aparecerá en la sección "hierro" de EP-TD.

---

🔖 Última revisión: 2026-06-02 (v4 — max_present por animal; avg_bounty por sección (denominador=n_reports, incluye derrotas); total_animals por sección (regla TODO-O-NADA); oasis_coords por sección (y ASC, x ASC); CTE ampliada con bounty; deduplicación de botín por report_id (RN-TD25); modelos Pydantic v4; 54 tests)
