---
name: project-bd-ataques-oasis
description: BD de ataques a oasis — hallazgos del catálogo, modelo de datos, correcciones C1-C7 APIs, delta reportes perdidos (present/killed/survived nullable)
metadata:
  type: project
---

Feature "BD de ataques a oasis por pegado de reporte" — spec guardado en `docs/specs/bd-ataques-oasis.md`.

**Why:** Acumular reportes de ataques a oasis para estadísticas de aparición, repoblación y regeneración de animales.

**How to apply:** Si vuelve a tocar esta feature o features relacionadas con parseo de reportes Travian, partir de este diseño.

## Hallazgos del catálogo NATURE (confirmados programáticamente)

- El catálogo `core/i18n/catalog/base/troops.json` tiene claves `NATURE_1..10` con 25 idiomas.
- El índice invertido `name_lower → ordinal` tiene **215 entradas únicas** y **0 colisiones cross-language**: ningún nombre de animal mapea a dos ordinales distintos. El parser puede operar globalmente sin conocer el idioma.
- Los nombres de tropas atacantes son **ambiguos cross-tribe**: 70 nombres conflictivos. No se puede resolver la tribu del atacante sin input explícito del usuario. MVP: guardar `troop_name` texto y `troop_ordinal = null`.

## Modelo de datos clave

3 tablas:
- `attack_reports` — cabecera (coords destino, aldea origen, timestamp UTC, botín, capacity, hero_inventory_json opaco, raw_text, world_id nullable)
- `attack_report_attacker_troops` — tropas por reporte (FK CASCADE)
- `attack_report_animals` — animales por reporte (FK CASCADE)

Clave de unicidad: `(coord_x_dest, coord_y_dest, attacked_at, origin_village_name)`.

La **regeneración de animales** es un cálculo derivado con `LAG() OVER WINDOW`, no columna persistida. Requiere SQLite 3.25+ (Python 3.14 usa 3.46+).

## Decisiones arquitectónicas

- El endpoint `parse` comprueba duplicados (campo `already_exists` en preview) pero no guarda.
- El endpoint `save` re-parsea el raw_text (no recibe el preview del cliente).
- `Accept-Language` NO obligatorio en este router (datos numéricos/ISO, no texto localizado).
- `raw_text` almacenado en BD para re-parseo futuro.

## Correcciones de desarrollador-apis (C1-C7) — aplicar en futuros specs similares

Estas correcciones fueron recurrentes y aplican a cualquier spec con endpoints de parse/save de texto y estadísticas:

- **C1**: DTOs de texto libre siempre con `Field(..., min_length=1, max_length=50000)`. Nunca dejar `raw_text` sin validación de tamaño.
- **C2**: Si hay un objeto anidado (ej. `bounty`) Y un campo relacionado pero separado (ej. `hero_inventory`), dejar el campo relacionado como campo RAÍZ del response, NO dentro del objeto anidado. En la entidad del core, `BountyData` no debe incluir `hero_inventory`; `AttackReportPreview` lo tiene como atributo de primer nivel. Inequívoco en el spec: comentar "NO va dentro de bounty".
- **C3**: El response 201 de save debe incluir todos los campos que el frontend puede necesitar para mostrar confirmación, incluyendo `utc_offset`. Documentar idempotencia natural si existe (clave única → 409 natural, sin `Idempotency-Key`).
- **C4**: Documentar TODOS los errores 400 posibles de forma exhaustiva (no solo el primero). Límite máximo de `limit` = 100 por convención del proyecto (no 200).
- **C5**: `cumulative_bounty` o totales acumulados: especificar si son del rango filtrado o del histórico total. El implementador no puede inferirlo.
- **C6**: Parámetros de ruta `{id}` numéricos SIEMPRE tipar como `int = Path(..., ge=1)` en FastAPI para evitar colisión con rutas literales (ej. `/stats/oasis` no debe capturarse como `{id}`). Declarar rutas literales ANTES en el router también ayuda como segundo seguro.
- **C7**: En estadísticas de series temporales, documentar: (a) semántica exacta de `min` (excluye ceros o no), (b) respuesta para el caso sin datos (200 con estructura vacía, no 404), (c) tipos nullable explícitos (integer|null) para campos del primer elemento de la serie.

## Estado

- Spec base: `ready-for-impl` — contrato API validado por desarrollador-apis (correcciones C1-C7 incorporadas, `apis_validadas_por_desarrollador_apis: true`).
- Spec de cambio hora/balance: `docs/specs/bd-ataques-oasis-fix-hora-balance.md` (`ready-for-impl`, EP-07 validado por desarrollador-apis, `apis_validadas_por_desarrollador_apis: true`).
- Spec prueba manual: `docs/specs/bd-ataques-oasis-stats-oasis-nav.md` (`ready-for-impl`, EP-06 modificación + EP-08 creación **pendientes de gate desarrollador-apis**, `apis_validadas_por_desarrollador_apis: false`).
- Spec distribución temporal: `docs/specs/bd-ataques-oasis-temporal-distribution.md` (`ready-for-impl`, EP-TD creación, `apis_validadas_por_desarrollador_apis: false` — Agent no disponible, gate pendiente).

## Fix hora del ataque (lección aprendida — 2026-05-31)

**Gotcha crítico para futuros specs de parseo de reportes Travian:**
El reporte tiene DOS horas distintas: la línea del ataque (`DD.MM.YY, HH:MM:SS`) y el
`Server time: HH:MM:SS (UTC +HH:MM)`. La segunda es la hora a la que el usuario MIRABA
el reporte, no la hora del ataque. En reportes reales pueden diferir varias horas.

- `attacked_at` = verbatim de la línea del ataque, naive, sin restar offset.
- `utc_offset` = metadato del Server time (conservar para correlaciones futuras, NO usar para calcular `attacked_at`).
- El frontend NO debe usar `new Date(isoStr)` + `Intl.DateTimeFormat` para mostrar `attacked_at`; parse manual del string evita la conversión de zona horaria del navegador.
- `UNIXEPOCH` de SQLite sobre strings naive funciona correctamente para diferencias de tiempo (todas las filas en el mismo reloj).

## Balance de recursos (EP-07)

- Endpoint `GET /attack-reports/stats/bounty?x=&y=` (x/y opcionales: omitir = global, ambos = por oasis).
- Response incluye campo `scope: "oasis" | "global"` para que el cliente sepa qué recibió.
- Query: `SUM(bounty_wood/clay/iron/crop)` + `COUNT(*)` sobre `attack_reports`, con WHERE opcional por coords.

## Lecciones de prueba manual (spec stats-oasis-nav — 2026-05-31)

**Gotcha desajuste de nombres de campo frontend/backend:**
- Nombres reales en EP-06: `appearances`, `avg_present`, `max_present`, `min_present`.
- El frontend tenía `count`, `avg`, `max`, `min`. La regla es siempre alinear el frontend a la API (no al revés), porque la API tiene tests.
- `regenerated_animals` es una LISTA, no un dict. El frontend necesita transformar a dict por `animal_name` antes de leer por nombre de columna. Transformar en el render, no en estado.

**ResIcon reutilizable (TravianReport.jsx línea 44):**
- `export function ResIcon({ res, size, label })` — usa `/api/static/icons/stat_{res}.png`.
- Siempre importar desde `'../combat/TravianReport.jsx'` cuando se necesiten iconos de recursos. No duplicar.

**Ratio de regeneración por hora — patrón para futuros specs:**
- Calcular en Python (no SQL) sobre `repopulation_gaps` ya materializado en memoria.
- Excluir intervalos con `gap_seconds <= 0` o `regenerated < 0` (irregularidades).
- Incluir `valid_intervals` en la respuesta (confianza estadística de coste cero).
- Si el animal no tiene intervalos válidos, no incluirlo en la lista (no exponer null).

**lista de oasis navegable (EP-08):**
- `GROUP BY coord_x_dest, coord_y_dest` + `ORDER BY last_attack DESC` sobre `attack_reports`.
- Reutilizar patrón WHERE dinámico de `list_reports`.
- Sin paginación en v1 (pocos oasis distintos en caso de uso real).
- Declarar ANTES de `GET /attack-reports/{id}` en el router.

## Agregado global (EP-09 — 2026-05-31)

Spec en `docs/specs/bd-ataques-oasis-stats-global.md` (`ready-for-impl`).

**Decisiones clave:**
- `_calc_regen_rates` reutilizada SIN modificación: es función pura, acepta cualquier lista de gaps.
- LAG global usa `PARTITION BY coord_x_dest, coord_y_dest` (y también `animal_ordinal` en la query de regen): los intervalos de cada oasis se calculan de forma independiente, nunca se cruzan oasis distintos.
- Panel frontend en `StatsTab` (hermano de `OasisList`, no hijo); carga en paralelo.
- `RegenRatesSection` reutilizada sin modificación.
- Ruta `stats/global` declarada ANTES de `stats/oasis` en el router (orden de declaración: bounty → global → oasis → {id}).
- `apis_validadas_por_desarrollador_apis: false` — la herramienta Agent no estuvo disponible; contrato revisado manualmente por el analista con criterios C1-C7.

**Patrón LAG global (para futuros specs de agregados multi-oasis):**
```sql
WINDOW w AS (
    PARTITION BY r.coord_x_dest, r.coord_y_dest, a.animal_ordinal
    ORDER BY r.attacked_at
)
```
Sin filtro WHERE de coordenadas, el PARTITION garantiza que el LAG no cruce oasis distintos.

## Distribucion temporal de animales por tipo de oasis (EP-TD v4 — 2026-06-02)

Spec en `docs/specs/bd-ataques-oasis-temporal-distribution.md` (`ready-for-impl`, v4).

**Historial:**
- v1 (bucket_hours, matriz): implementado, 33 tests.
- v2 (interval_minutes, lista plana, Opcion B): implementado, 39 tests.
- v3 (agrupado por tipo de oasis inferido): implementado, 41 tests, EP-SPAWN 52/52.
- v4 (max_present + avg_bounty + total_animals + oasis_coords): ready-for-impl, gate desarrollador-apis pendiente.

**Decisiones clave v2-v3 (siguen vigentes en v4):**
- `interval_minutes` en {6,7,10,15,30,60,120,180,240,300}, default 240. Binning umbral inferior.
- Gaps < 360s descartados. present=NULL → n_total (no n_valid).
- Moda en Python con Counter. Media a 2 dec. Accept-Language obligatorio.
- Tribe.NATURE (mayusculas), clave "nombre" en JsonTranslationAdapter.
- infer_type elevada desde _infer_type. 5 secciones fijas. arcilla→"Barro".
- CTE para la query LAG (no JOIN directo — el LAG toma el reporte anterior, no el animal anterior).

**Decisiones clave v4 (nuevas — denominadores críticos):**
- `max_present` por animal: max(valids) — mismo null-handling que avg/mode. null si n_valid=0.
- `avg_bounty` denominador = TODOS los reportes (incl. derrotas con bounty=0). DDL NOT NULL DEFAULT 0.
  No promediar solo sobre "con bounty>0" — eso sesgaría. Consistente con get_bounty_stats.
- `avg_bounty.total` = media de (w+c+i+cr) por reporte — NO suma de medias individuales.
- Botín deduplicado por report_id (JOIN produce N filas de animal por reporte; bounty es del reporte).
- `total_animals` denominador = reportes con TODOS los animales not null ("todo o nada").
  Si CUALQUIER animal del reporte tiene present=NULL → reporte excluido de n_valid del total.
  Justificación: suma parcial de present con ausencias silenciosas es engañosa.
- `oasis_coords`: serializar type_oasis_ids[tipo] → lista [{x, y}] ordenada (y ASC, x ASC). Sin cap.
  Enteros crudos — formateo (-15|23) es del frontend. Palantir detectó 5 copias → centralizar en coordUtils.js (tarea UI v5).
- CTE report_gaps se amplía con bounty_wood/clay/iron/crop (mínimo cambio, sin nueva query).
- `apis_validadas_por_desarrollador_apis: false` — gate pendiente de desarrollador-apis.

**Patrón de generación de buckets (para futuros specs con buckets uniformes + cubo abierto):**
```python
THRESHOLD = 24 * 3600
bucket_secs = bucket_hours * 3600
def assign_bucket(gap_seconds):
    if gap_seconds >= THRESHOLD:
        return (24, None)   # cubo abierto
    lower_h = (gap_seconds // bucket_secs) * bucket_hours
    return (lower_h, lower_h + bucket_hours)
```

## Fix % de aparición global (EP-09 — 2026-06-01)

Spec en `docs/specs/bd-ataques-oasis-global-pct-aparicion.md` (`ready-for-impl`, `apis_validadas_por_desarrollador_apis: false` — Agent no disponible; gate pendiente de desarrollador-apis).

**Problema resuelto:** el denominador correcto para el % de aparición global NO es "todos los reportes de la BD", sino solo los reportes de oasis donde ese animal ha aparecido alguna vez (`present > 0`). Usar todos los reportes diluye artificialmente el % (oasis de madera baja el % de ratas).

**Denominador (`eligible_reports`) — query clave:**
```sql
SELECT a_ever.animal_ordinal, COUNT(DISTINCT r_eligible.id) AS eligible_reports
FROM (
    SELECT DISTINCT r2.coord_x_dest, r2.coord_y_dest, a2.animal_ordinal
    FROM attack_report_animals a2 JOIN attack_reports r2 ON r2.id = a2.report_id
    WHERE a2.present > 0
) a_ever
JOIN attack_reports r_eligible
    ON r_eligible.coord_x_dest = a_ever.coord_x_dest AND r_eligible.coord_y_dest = a_ever.coord_y_dest
GROUP BY a_ever.animal_ordinal
```

**Invariante:** `appearances <= eligible_reports` siempre. Si se viola → bug.

**Patrón para futuros specs de % de aparición multi-oasis:**
- Numerador = conteo de reportes con `present > 0` para ese animal.
- Denominador = todos los reportes de los oasis donde ese animal apareció alguna vez (`ever_present`).
- Oasis donde el animal NUNCA apareció no entran en el denominador.
- `present = NULL` (derrota) no satisface `> 0` → no entra ni en numerador ni en denominador.
- El % es presentacional (se calcula en el frontend con `Math.round`), no se devuelve como campo JSON.
- El campo `eligible_reports` es aditivo → retrocompatible; clientes que no lo lean siguen funcionando.

**Display en frontend:** `"appearances / eligible_reports (NN%)"` ej. `"8/15 (53%)"`.
Guardia defensiva: si `eligible_reports` es null o 0, mostrar solo `appearances`.

## Delta: reportes de combate PERDIDO (2026-06-01)

Spec en `docs/specs/bd-ataques-oasis.md` §17 (`ready-for-impl`).

**Hallazgo clave para futuros parsers de reportes Travian:**
Cuando el atacante pierde contra un oasis, Travian muestra `?` en lugar de
cantidades del defensor. La fila de `?` no supera el test `^[\d\s\t]+$` y el
parser anterior lanzaba `NotNatureOasisError` antes de validar los nombres.

**Decisiones de diseño cerradas:**
- `present/killed/survived = null` (no 0). null = desconocido; 0 = oasis vacío de ese tipo.
- Detección por patrón `_DEFEAT_ROW_PATTERN = r"^\?[\s\t]*(\?[\s\t]*)*$"` (idioma-agnóstico).
- Fila mixta `?`/dígitos → `DefeatReportParseError` (reporte corrupto).
- Validar nombres de la cabecera también en modo perdido (confirma que es oasis Nature).
- En modo perdido, Travian muestra UNA sola fila de `?` (no dos); el parser no busca segunda fila.
- NO añadir `is_defeat: bool` — derivable de `all(a.present is None for a in animals)`.
- Migración BD de desarrollo: borrar `travian_bot.db` (sin Alembic; BD sin datos de producción).
- DDL: columnas `present/killed/survived` pasan de `INTEGER NOT NULL DEFAULT 0` a `INTEGER` puro.
- `hero_inventory` no cambia: es independiente del modo perdido/ganado.
- Contrato de API: sin cambio de ruta/método/código. Solo `present/killed/survived` pasan a `integer | null`.
- `apis_validadas_por_desarrollador_apis: true` (fallback manual; Agent no disponible; FastAPI serializa `None → null` automáticamente; queries de stats toleran NULL por SQL estándar).

**Reporte de referencia para CA-D01:**
Oasis (-59|25), tropas galas Swordsman×2 + Theutates Thunder×2, todas perdidas,
animales desconocidos (todos `?`), bounty 0/0, hero_inventory {wood:240, clay:240, iron:240, crop:240}.
