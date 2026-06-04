---
name: temporal-distribution-pattern
description: EP-TD v4: 5 secciones por tipo oasis + max_present/avg_bounty/total_animals/oasis_coords; CTE obligatoria para LAG; infer_type pública; deduplicación bounty por report_id.
metadata:
  type: project
---

## Patrón EP-TD v4 — Distribución temporal de animales por tipo de oasis

Implementado en feature `bd-ataques-oasis-temporal-distribution` v4 (2026-06-02).
v3 añade segmentación por tipo de oasis inferido (hierro/arcilla/madera/cereal/sin_clasificar).
v4 añade 4 campos por sección: `max_present` (por animal), `avg_bounty`, `total_animals`, `oasis_coords`.

**Por qué:** los gaps de farmeo se calculan a nivel de oasis completo (PARTITION BY coords), no por animal. La inferencia de tipo reutiliza `infer_type` (elevada desde `_infer_type` en v3) y la misma query de composición que EP-SPAWN.

**How to apply:** para cualquier cálculo que necesite gaps entre ataques consecutivos al mismo oasis, distribuir por tipo de animal y luego agrupar por tipo de oasis inferido.

### GOTCHA CRÍTICO: CTE obligatoria cuando el JOIN con animales precede al LAG

**Problema:** si se hace `JOIN attack_report_animals` ANTES del LAG window, hay múltiples filas por reporte (una por animal). El LAG toma la fila anterior del JOIN (el animal anterior del MISMO reporte) en lugar del REPORTE anterior. Resultado: solo el primer animal (ordinal más bajo) tiene gap correcto; el resto tienen gap=0 o NULL.

**Solución:** CTE que calcula gaps a nivel de reporte, luego JOIN con animals.

```sql
WITH report_gaps AS (
    SELECT r.id AS report_id, r.coord_x_dest, r.coord_y_dest, r.attacked_at,
        CAST((UNIXEPOCH(r.attacked_at) - UNIXEPOCH(LAG(r.attacked_at) OVER w)) AS INTEGER) AS gap_seconds
    FROM attack_reports r
    WINDOW w AS (PARTITION BY r.coord_x_dest, r.coord_y_dest ORDER BY r.attacked_at)
)
SELECT rg.report_id, rg.coord_x_dest, rg.coord_y_dest,
       a.animal_ordinal, a.animal_name, a.present, rg.gap_seconds
FROM report_gaps rg
JOIN attack_report_animals a ON a.report_id = rg.report_id
```

### Inferencia de tipo por oasis (v3)

```python
# infer_type es función PÚBLICA de módulo en attack_report_sqlite_adapter.py
# (elevada desde _infer_type en v3 — RN-TD14)
tipo, confidence = infer_type(observed_ordinales, comp_list)
# oasis_type_map[(cx, cy)] = (tipo, confidence)
```

Misma query de composición que EP-SPAWN (`WHERE present > 0`, `COUNT(*) AS burst_count`).
Un oasis sin ningún `present > 0` → tipo=None → sección "sin_clasificar".

### GOTCHA: Empate Jaccard hierro vs arcilla para observed={1}

`observed = {1}` (solo Rata):
- Jaccard(hierro={1,2,4}, {1}) = 1/3 ≈ 0.33
- Jaccard(arcilla={1,2,5}, {1}) = 1/3 ≈ 0.33  ← EMPATE
- Ambos tienen cardinal 3 → segundo desempate: **alfabético → "arcilla" gana**

Para forzar clasificación como hierro sin empate, usar Murciélago (ord=4) que no pertenece a arcilla:
- Jaccard(hierro={1,2,4}, {4}) = 1/3 ≈ 0.33
- Jaccard(arcilla={1,2,5}, {4}) = 0  ← no hay 4 en arcilla → hierro gana

### 5 secciones fijas siempre presentes

```python
TYPE_ORDER = ["hierro", "arcilla", "madera", "cereal", None]  # None = sin_clasificar
TYPE_LABELS = {"hierro":"Hierro", "arcilla":"Barro", "madera":"Madera", "cereal":"Cereal", None:"Sin clasificar"}
# "arcilla" → "Barro" (terminología del usuario, RN-TD18)
```

### Binning — umbral inferior (Opción B) — sin cambio desde v2

Cada `F` → ventana `[F*60, F_next*60)`. Para 300 → `[18000, ∞)`.
Gaps `< 360s` (< 6 min) se descartan. Gaps `<= 0` o `IS NULL` también.

### Moda con Counter

```python
from collections import Counter
counter = Counter(valids)
max_count = max(counter.values())
mode = sorted(k for k, v in counter.items() if v == max_count)
```

### GOTCHA: Tribe enum en mayúsculas y clave "nombre"

```python
translation_port.get_troop_names_by_tribe(Tribe.NATURE, lang)  # NATURE, no nature
names_by_ordinal = {entry["ordinal"]: entry["nombre"] for entry in name_entries}  # "nombre", no "name"
```

### CRÍTICO v4: Deduplicación de botín por report_id (RN-TD25)

El JOIN con `attack_report_animals` produce N filas por reporte (una por animal).
El botín está en `attack_reports` (nivel de reporte), NO en `attack_report_animals`.
Si se acumula `bounty_wood` por cada fila de animal → se multiplica por el número de animales.

**Solución:** dict `type_bounty[tipo] = {report_id: (w,c,i,cr)}` — solo insertar la primera vez.

```python
if rid not in type_bounty[tipo]:
    type_bounty[tipo][rid] = (row["bounty_wood"], row["bounty_clay"],
                               row["bounty_iron"], row["bounty_crop"])
```

### v4: Regla TODO-O-NADA para total_animals (RN-TD21)

El "total de animales" de un reporte = suma de `present` de todos sus animales.
Si CUALQUIER animal del reporte tiene `present=NULL` → el reporte se excluye de `n_valid`.

```python
type_report_nulls[tipo] = defaultdict(bool)  # {rid: any_null}
type_report_sums[tipo]  = defaultdict(int)   # {rid: sum_present}
if present_val is None:
    type_report_nulls[tipo][rid] = True  # excluir de n_valid
else:
    type_report_sums[tipo][rid] += present_val
```

### v4: avg_bounty — denominador = n_reports_in_section (incluye derrotas)

Las derrotas guardan `bounty=0` (NOT NULL DEFAULT 0 en el DDL). Se incluyen en el denominador.
`avg_bounty.total` = media del `(w+c+i+cr)` por reporte — NO suma de las 4 medias individuales.

### v4: oasis_coords — ordenación (y ASC, x ASC)

```python
sorted(type_oasis_ids[tipo], key=lambda coord: (coord[1], coord[0]))
```

### v4: Modelos Pydantic en attack_reports.py

Prefijo `_TD` para los 7 modelos: `_TDResponse`, `_TDOasisTypeSection`, `_TDAnimalItem`,
`_TDAvgBounty`, `_TDTotalAnimals`, `_TDOasisCoord`, `_TDWindow`.
`response_model=_TDResponse` en el endpoint EP-TD.

### v4: CTE ampliada con bounty

```sql
WITH report_gaps AS (
    SELECT r.id AS report_id, r.coord_x_dest, r.coord_y_dest, r.attacked_at,
           r.bounty_wood, r.bounty_clay, r.bounty_iron, r.bounty_crop,  -- [v4]
           CAST(...) AS gap_seconds
    ...
)
SELECT rg.report_id, rg.coord_x_dest, rg.coord_y_dest,
       rg.bounty_wood, rg.bounty_clay, rg.bounty_iron, rg.bounty_crop,  -- [v4]
       a.animal_ordinal, a.animal_name, a.present, rg.gap_seconds
```

Ver [[attack-reports-pattern]] para el patrón general del router de attack_reports.
