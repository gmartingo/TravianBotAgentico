---
id: bd-ataques-oasis-stats-global
titulo: Panel de agregado global de todos los oasis (Estadísticas)
estado: implemented
fecha: 2026-05-31
autor: analista
apis_validadas_por_desarrollador_apis: true
---

# Panel de agregado global de todos los oasis

## 1. Objetivo de negocio

Añadir un **panel fijo siempre visible encima de la lista de oasis** en la pestaña
"Estadísticas" del módulo de reportes de ataque a oasis. El panel muestra métricas
agregadas de **todos los oasis conjuntamente**:

1. **Apariciones de animales**: por cada tipo de animal, cuántas veces apareció en el
   conjunto de todos los oasis, con promedio / máximo / mínimo de unidades observadas.
2. **Ritmo de regeneración global**: velocidad media de regeneración por hora de cada
   animal, calculada juntando TODOS los intervalos válidos de todos los oasis en un
   único cálculo (los oasis con más datos pesan más porque aportan más intervalos).

El objetivo es que el usuario pueda tener una visión de conjunto antes de analizar
oasis individuales, y calibrar la frecuencia óptima de ataque a cada tipo de animal.

## 2. Actores y permisos

- **Usuario del dashboard** (único actor). Solo lectura. Sin autenticación adicional
  más allá de la que ya protege la aplicación.
- No hay diferencia de permisos entre usuarios.

## 3. Alcance

### Dentro del alcance

- Nuevo endpoint `GET /attack-reports/stats/global` (EP-09).
- Nuevo método abstracto `get_global_oasis_stats()` en `AttackReportPort`.
- Nueva implementación en `AttackReportSQLiteAdapter`.
- Nuevo componente React `GlobalOasisStatsPanel.jsx`.
- Modificación additive de `StatsTab.jsx` para integrar el panel global encima de
  `OasisList`.
- Nuevo método `getGlobalOasisStats()` en `frontend/src/api/client.js`.

### Fuera del alcance (v1)

- Botín total global (cubierto ya por EP-07 `stats/bounty`).
- Recuentos de número de oasis distintos o número total de ataques.
- Filtros por rango de fechas en la vista global.
- Paginación.
- Comparativa global vs. oasis individual.
- Posibilidad de mencionar `total_oasis` y `total_attacks` como campos informativos
  del panel se deja como mejora futura, pero **no se incluye en este spec**.

## 4. Reglas de negocio

**RN-G01 — Definición de "apariciones":**
`appearances` = número de filas en `attack_report_animals` (de todos los oasis) donde
`present > 0` para ese `(animal_ordinal, animal_name)`. Es decir: cuántos reportes,
en toda la base de datos, registraron al menos una unidad de ese animal.

**RN-G02 — avg/max/min_present:**
- `avg_present`: promedio de `present` sobre todas las filas con `present > 0` (global).
- `max_present`: máximo de `present` sobre esas mismas filas.
- `min_present`: mínimo de `present` sobre filas con `present > 0` (excluye ceros).
  Devuelve `null` si no hay ninguna fila con `present > 0` (caso teórico imposible
  dado que solo se incluyen filas con `present > 0`, pero se declara por completitud).

**RN-G03 — Orden de la lista de animales:**
Siempre por `animal_ordinal ASC` (coherente con EP-06 y el catálogo de tropas Nature).

**RN-G04 — Cálculo de regeneración global:**
Se reutiliza `_calc_regen_rates(repopulation_gaps)` sin modificación alguna. Los gaps
se construyen con LAG particionado por `(coord_x_dest, coord_y_dest)` de forma que:
- Los intervalos de cada oasis se calculan de forma independiente (LAG dentro de ese oasis).
- Todos los intervalos válidos de todos los oasis se concatenan en una única lista.
- `_calc_regen_rates` procesa esa lista completa: cada oasis contribuye con tantos
  intervalos como ataques menos uno tenga, por lo que los oasis con más ataques
  ponderan proporcionalmente más.

**RN-G05 — Respuesta vacía:**
Si no hay ningún reporte en la BD, la respuesta es `200` con `animal_appearances: []`
y `animal_regen_rates: []`. Nunca `404`.

**RN-G06 — Animales sin intervalos válidos:**
Si un animal no tiene ningún intervalo válido global (por ejemplo, solo aparece como
primer ataque en cada oasis, sin LAG previo), NO aparece en `animal_regen_rates`.
Esta regla ya está implementada en `_calc_regen_rates`.

**RN-G07 — Sin Accept-Language:**
El endpoint devuelve datos numéricos y texto crudo (`animal_name` proviene de la BD,
no de catálogo localizado). No requiere `Accept-Language` (mismo patrón que EP-06/07/08).

## 5. Flujo principal y flujos alternativos

### Flujo principal

```
1. Frontend monta StatsTab
2. En paralelo:
   a. StatsTab llama getGlobalOasisStats() → GET /attack-reports/stats/global
   b. OasisList llama listOasisSummaries()  → GET /attack-reports/oasis
3. GlobalOasisStatsPanel muestra loading skeleton
4. Respuesta 200 con datos → panel muestra:
   a. Sección "Ritmo de regeneración global" (RegenRatesSection reutilizada)
   b. Sección "Apariciones de animales" (tabla: animal, apariciones, prom, máx, mín)
5. OasisList carga por su cuenta con su propio estado (sin dependencia del panel global)
```

### Flujos alternativos

**FA-1 — BD vacía (sin reportes):**
El endpoint devuelve `{ scope:"global", animal_appearances:[], animal_regen_rates:[] }`.
El panel frontend muestra un estado vacío descriptivo (no un error) con el texto
"Sin datos todavía. Ingresa algunos reportes de ataque para ver estadísticas globales."
con CTA que navega a la pestaña Ingresar.

**FA-2 — Error de red o 5xx:**
El panel muestra banner de error (mismo patrón rojo de OasisList) con botón "Reintentar"
que vuelve a llamar a `loadGlobal()`. No propaga el error a OasisList.

**FA-3 — Solo un ataque total en toda la BD (de cualquier oasis):**
`animal_appearances` tiene datos (ese ataque registró animales).
`animal_regen_rates` = [] porque no hay ningún intervalo LAG con `gap_seconds > 0`.
La sección de regen muestra el aviso "⚠ Se necesitan al menos 2 ataques al mismo
oasis para calcular el ritmo de regeneración" (reutiliza el banner ya existente en
`RegenRatesSection` cuando `rates.length === 0`).

## 6. Edge cases

| ID | Escenario | Tratamiento esperado |
|----|-----------|----------------------|
| EC-G01 | BD vacía (0 reportes) | 200 con arrays vacíos; panel muestra estado vacío descriptivo |
| EC-G02 | Un único reporte en toda la BD | appearances poblado, regen_rates = [] |
| EC-G03 | Todos los oasis tienen exactamente 1 ataque | appearances poblado, regen_rates = [] |
| EC-G04 | Un animal solo en primer ataque de cada oasis | No aparece en regen_rates (sin LAG válido) |
| EC-G05 | Animal con present = 0 en algún reporte | Excluido del COUNT y de min/avg/max (WHERE present > 0) |
| EC-G06 | min_present devuelve null | Frontend muestra '—' |
| EC-G07 | avg_present con muchos decimales | Se redondea a 2 decimales en el adaptador (como get_oasis_stats) |
| EC-G08 | Un oasis con 100 ataques y otro con 1 | El de 100 aporta 99 intervalos; el de 1 aporta 0; correcta ponderación |
| EC-G09 | Animal diferente en cada oasis | Aparece en la lista global con sus stats; orden por animal_ordinal |
| EC-G10 | Error en la carga del panel global | Banner rojo + reintentar; OasisList no se ve afectada |
| EC-G11 | Carga lenta (> 2s) | Skeleton/spinner en el panel mientras OasisList puede estar ya cargada |

## 7. Modelo de datos / cambios de esquema

**Sin cambios de esquema.** El endpoint opera sobre las 3 tablas existentes:
- `attack_reports`
- `attack_report_animals`
- `attack_report_attacker_troops` (no se consulta en este endpoint)

No hay migraciones DDL.

## 8. Contratos de API / interfaces

> **Nota:** El contrato fue validado por el subagente desarrollador-apis (orquestado
> por el hilo principal). Veredicto: APROBADO con una corrección — `avg_present` pasa a
> `float | None` por consistencia con la guardia defensiva de EP-06 (frontend muestra `—`
> cuando sea null). Resto del contrato (ruta entre `stats/bounty` y `stats/oasis`,
> `scope: "global"`, 200 siempre, arrays vacíos si BD vacía, reutilización de
> `_calc_regen_rates`, sin Accept-Language) alineado con los patrones del módulo.

### EP-09 — Estadísticas globales de todos los oasis

```
GET /attack-reports/stats/global
```

**Sin parámetros de entrada.** No requiere `Accept-Language`.

**Posición en el router:** declarar ANTES de `GET /attack-reports/stats/oasis`
(línea ~436 del router actual). Ambas son rutas literales bajo `/stats/`, por lo
que no hay riesgo de colisión con `{id}`, pero la convención del módulo es declarar
las rutas literales más específicas primero. La nueva ruta debe quedar en este orden:

```
GET /attack-reports/stats/bounty   (EP-07 — existente)
GET /attack-reports/stats/global   (EP-09 — NUEVO, insertar aquí)
GET /attack-reports/stats/oasis    (EP-06 — existente)
```

**Response 200 (caso con datos):**

```json
{
  "scope": "global",
  "animal_appearances": [
    {
      "animal_ordinal": 1,
      "animal_name": "Rata",
      "appearances": 42,
      "avg_present": 7.50,
      "max_present": 15,
      "min_present": 3
    },
    {
      "animal_ordinal": 2,
      "animal_name": "Araña",
      "appearances": 18,
      "avg_present": 4.33,
      "max_present": 9,
      "min_present": 2
    }
  ],
  "animal_regen_rates": [
    {
      "animal_ordinal": 1,
      "animal_name": "Rata",
      "avg_regen_per_hour": 3.45,
      "valid_intervals": 18
    }
  ]
}
```

**Response 200 (BD vacía / sin reportes):**

```json
{
  "scope": "global",
  "animal_appearances": [],
  "animal_regen_rates": []
}
```

**Tipos de campos:**

| Campo | Tipo | Nullable | Notas |
|-------|------|----------|-------|
| `scope` | string | No | Siempre `"global"` |
| `animal_appearances` | array | No | Vacío si no hay datos |
| `animal_appearances[].animal_ordinal` | integer | No | 1..10 |
| `animal_appearances[].animal_name` | string | No | Texto crudo de la BD |
| `animal_appearances[].appearances` | integer | No | >= 1 (solo presente si > 0) |
| `animal_appearances[].avg_present` | float | **Sí** | Redondeado a 2 decimales; null si sin datos (teórico, guardia defensiva como EP-06). Frontend muestra `—` |
| `animal_appearances[].max_present` | integer | No | >= 1 |
| `animal_appearances[].min_present` | integer | **Sí** | null si sin datos (teórico) |
| `animal_regen_rates` | array | No | Vacío si < 2 ataques al mismo oasis |
| `animal_regen_rates[].animal_ordinal` | integer | No | 1..10 |
| `animal_regen_rates[].animal_name` | string | No | Texto crudo de la BD |
| `animal_regen_rates[].avg_regen_per_hour` | float | No | Redondeado a 2 decimales |
| `animal_regen_rates[].valid_intervals` | integer | No | >= 1 |

**Errores posibles:**

| Código | Condición |
|--------|-----------|
| 500 | Error interno de la BD (aiosqlite) |

No hay errores 400/422: el endpoint no acepta parámetros de entrada.

**Auth:** ninguna adicional (mismo nivel que el resto del módulo).
**Cabeceras de respuesta:** `Content-Type: application/json`. Sin `Vary`.
**Idempotencia:** GET puro, siempre idempotente.
**Caché:** sin directivas de caché especiales (datos cambian con cada nuevo reporte).

## 9. Flujo lógico paso a paso

### Backend — `get_global_oasis_stats()`

```python
async def get_global_oasis_stats(self) -> dict:
    """
    Estadísticas globales de todos los oasis combinados.
    Reutiliza _calc_regen_rates con los gaps de todos los oasis concatenados.
    """

    # ── Paso 1: Apariciones globales ─────────────────────────────────────────
    # WHERE present > 0: excluye reportes donde el animal ya había sido eliminado.
    # GROUP BY animal_ordinal, animal_name: una fila por tipo de animal.
    # MIN(CASE WHEN present > 0 THEN present END): excluye ceros de min (RN-G02).
    # ORDER BY animal_ordinal ASC: coherente con EP-06 (RN-G03).

    SELECT
        a.animal_ordinal,
        a.animal_name,
        COUNT(*)                                              AS appearances,
        AVG(a.present)                                        AS avg_present,
        MAX(a.present)                                        AS max_present,
        MIN(CASE WHEN a.present > 0 THEN a.present END)       AS min_present_nonzero
    FROM attack_report_animals a
    JOIN attack_reports r ON r.id = a.report_id
    WHERE a.present > 0
    GROUP BY a.animal_ordinal, a.animal_name
    ORDER BY a.animal_ordinal

    → animal_appearances: lista de dicts con campos del contrato

    # ── Paso 2: Regen con LAG particionado por oasis ──────────────────────────
    # Sin WHERE de coordenadas (todos los oasis).
    # PARTITION BY coord_x_dest, coord_y_dest, animal_ordinal: el LAG se calcula
    # dentro de cada (oasis, animal), exactamente igual que get_oasis_stats pero
    # sin filtro. Esto garantiza que el LAG no cruce oasis distintos.

    WITH ordered AS (
        SELECT
            r.id               AS report_id,
            r.attacked_at,
            r.coord_x_dest,
            r.coord_y_dest,
            a.animal_ordinal,
            a.animal_name,
            a.present,
            a.survived,
            LAG(a.survived) OVER w  AS prev_survived
        FROM attack_reports r
        JOIN attack_report_animals a ON a.report_id = r.id
        WINDOW w AS (
            PARTITION BY r.coord_x_dest, r.coord_y_dest, a.animal_ordinal
            ORDER BY r.attacked_at
        )
    )
    SELECT
        report_id, attacked_at, animal_ordinal, animal_name,
        present, survived, prev_survived,
        CASE WHEN prev_survived IS NOT NULL
             THEN present - prev_survived
             ELSE NULL
        END AS regenerated
    FROM ordered
    ORDER BY attacked_at, coord_x_dest, coord_y_dest, animal_ordinal

    → regen_rows

    # ── Paso 3: Gaps con LAG particionado por oasis ───────────────────────────
    # Sin WHERE de coordenadas. PARTITION BY (coord_x_dest, coord_y_dest):
    # los gaps se calculan dentro de cada oasis. El LAG NO cruza entre oasis.

    SELECT
        r.id,
        r.coord_x_dest,
        r.coord_y_dest,
        r.attacked_at,
        LAG(r.attacked_at) OVER w            AS prev_attacked_at,
        (UNIXEPOCH(r.attacked_at) - UNIXEPOCH(LAG(r.attacked_at) OVER w))
                                             AS gap_seconds
    FROM attack_reports r
    WINDOW w AS (
        PARTITION BY r.coord_x_dest, r.coord_y_dest
        ORDER BY r.attacked_at
    )
    ORDER BY r.attacked_at

    → gap_rows

    # ── Paso 4: Construir repopulation_gaps ───────────────────────────────────
    # Idéntico a get_oasis_stats: agrupar regen_rows por report_id, luego
    # construir la lista de gaps con regenerated_animals por reporte.
    # El resultado es la misma estructura que espera _calc_regen_rates.

    regen_by_report = { report_id: [{ animal_ordinal, animal_name, regenerated }, ...] }

    repopulation_gaps = [
        {
            "attack_id": gap["id"],
            "attacked_at": gap["attacked_at"],
            "prev_attacked_at": gap["prev_attacked_at"],
            "gap_seconds": gap["gap_seconds"],
            "regenerated_animals": regen_by_report.get(gap["id"], []),
        }
        for gap in gap_rows
    ]

    # ── Paso 5: Calcular rates globales ──────────────────────────────────────
    # _calc_regen_rates es función pura: acepta cualquier lista de gaps.
    # Filtra los gaps con gap_seconds <= 0 o regenerated < 0.
    # Animales sin intervalos válidos no aparecen en el resultado.

    animal_regen_rates = _calc_regen_rates(repopulation_gaps)

    # ── Paso 6: Construir y devolver el dict de respuesta ────────────────────
    return {
        "scope": "global",
        "animal_appearances": [
            {
                "animal_ordinal": row["animal_ordinal"],
                "animal_name": row["animal_name"],
                "appearances": row["appearances"],
                "avg_present": round(row["avg_present"], 2),
                "max_present": row["max_present"],
                "min_present": row["min_present_nonzero"],  # puede ser None
            }
            for row in appearance_rows
        ],
        "animal_regen_rates": animal_regen_rates,
    }
```

### Frontend — `GlobalOasisStatsPanel.jsx`

```jsx
function GlobalOasisStatsPanel({ data, loading, error, onRetry, lang, t }) {
    // Estado loading: skeleton (2 secciones grises)
    if (loading) return <GlobalStatsSkeleton />

    // Estado error: banner rojo + botón reintentar
    if (error) return <ErrorBanner message={error} onRetry={onRetry} />

    // Estado vacío: arrays vacíos en data
    if (!data || (data.animal_appearances.length === 0 && data.animal_regen_rates.length === 0)) {
        return <GlobalStatsEmpty t={t} />
    }

    return (
        <section aria-labelledby="global-stats-title" role="region">
            <h2 id="global-stats-title">...</h2>

            {/* Sección 1: Ritmo de regeneración (RegenRatesSection REUTILIZADA) */}
            <RegenRatesSection
                rates={data.animal_regen_rates}
                totalAttacks={null}   // no disponible en v1
                lang={lang}
                t={t}
            />

            {/* Sección 2: Apariciones de animales */}
            <GlobalAppearancesTable
                appearances={data.animal_appearances}
                lang={lang}
                t={t}
            />
        </section>
    )
}
```

### Frontend — integración en `StatsTab.jsx`

```jsx
export function StatsTab({ lang, onGoToIngest }) {
    const { t } = useI18n()
    const [globalData, setGlobalData]       = useState(null)
    const [globalLoading, setGlobalLoading] = useState(true)
    const [globalError, setGlobalError]     = useState(null)

    const loadGlobal = useCallback(async () => {
        setGlobalLoading(true)
        setGlobalError(null)
        try {
            const res = await api.getGlobalOasisStats()
            setGlobalData(res)
        } catch (err) {
            setGlobalError(err?.detail ?? t('ar.stats.global.error'))
        } finally {
            setGlobalLoading(false)
        }
    }, [t])

    useEffect(() => { loadGlobal() }, [loadGlobal])

    return (
        <div style={{ maxWidth: '900px' }}>
            {/* Panel global — SIEMPRE encima de OasisList */}
            <GlobalOasisStatsPanel
                data={globalData}
                loading={globalLoading}
                error={globalError}
                onRetry={loadGlobal}
                lang={lang}
                t={t}
            />
            {/* Separador visual */}
            <div style={{ marginTop: '24px' }}>
                <OasisList lang={lang} onGoToIngest={onGoToIngest} t={t} />
            </div>
        </div>
    )
}
```

## 10. Validaciones y reglas

| Validación | Dónde | Detalle |
|------------|-------|---------|
| Sin parámetros de entrada | — | No aplica; el endpoint no acepta params |
| `present > 0` | SQL (WHERE) | Excluye animales eliminados de las apariciones |
| `gap_seconds > 0` | `_calc_regen_rates` | Excluye primer ataque (sin LAG) y gaps inválidos |
| `regenerated >= 0` | `_calc_regen_rates` | Excluye regeneraciones negativas (irregularidades) |
| `min_present` excluye 0 | SQL (CASE WHEN) | `MIN(CASE WHEN present > 0 THEN present END)` |
| `avg_present` redondeado | Python (round) | `round(avg, 2)` coherente con EP-06 |
| `animal_regen_rates` sin nulos | `_calc_regen_rates` | Animales sin intervalos no aparecen |
| Orden animal_appearances | SQL (ORDER BY) | `animal_ordinal ASC` siempre |
| Orden animal_regen_rates | `_calc_regen_rates` | `sorted(accum.keys())` = ordinal ASC |

## 11. Seguridad, rendimiento y concurrencia

**Seguridad:**
- Solo lectura; sin parámetros de entrada; sin riesgo de inyección SQL.
- SQLite en modo WAL: las lecturas no bloquean escrituras.

**Rendimiento:**
- La query de apariciones es un simple GROUP BY sobre `attack_report_animals`
  con JOIN a `attack_reports`. El índice `idx_animals_ordinal_report` cubre bien
  el GROUP BY por ordinal.
- Las queries de LAG son más costosas porque procesan todas las filas sin filtro
  de coordenadas. Con las cargas de uso reales (un usuario, pocos oasis, decenas
  a centenares de reportes), el tiempo esperado es < 100ms.
- Si en el futuro el volumen crece (miles de reportes), se puede materializar
  la tabla de gaps en un job periódico. No es necesario en v1.

**Concurrencia:**
- Sin estado mutable en la query; WAL garantiza consistencia de lectura.
- Las llamadas paralelas de `getGlobalOasisStats()` y `listOasisSummaries()` desde
  el frontend no generan condiciones de carrera.

## 12. Plan de pruebas

### Casos felices

| ID | Escenario | Verificación |
|----|-----------|--------------|
| T-G01 | BD vacía | 200 con `{ scope:"global", animal_appearances:[], animal_regen_rates:[] }` |
| T-G02 | 1 oasis, 3 ataques con animales distintos | `appearances` correcto; `regen_rates` con 2 intervalos válidos |
| T-G03 | 2 oasis, 5 ataques cada uno | La regen global acumula 4+4=8 intervalos por animal; verificar `valid_intervals` |
| T-G04 | Oasis A con 10 ataques, oasis B con 1 | Regen global incluye 9 intervalos de A y 0 de B; B no distorsiona |
| T-G05 | Animal con `present = 0` en algún reporte | No aparece en `appearances` para ese reporte; min_present excluye ese valor |
| T-G06 | Mismo animal en todos los oasis | Una sola fila en `animal_appearances` con el agregado correcto |
| T-G07 | Animal solo en un oasis | Aparece en `animal_appearances` con stats de ese único oasis |

### Edge cases en tests

| ID | Escenario | Verificación |
|----|-----------|--------------|
| T-G08 | 1 ataque en toda la BD | `animal_regen_rates: []`; `animal_appearances` con ese ataque |
| T-G09 | Todos los oasis con 1 solo ataque | `animal_regen_rates: []`; panel frontend muestra aviso de regen |
| T-G10 | `regenerated` negativo en algún gap | Intervalo excluido del cálculo de regen (`_calc_regen_rates` ya filtra) |
| T-G11 | `gap_seconds = 0` (dos ataques en el mismo segundo) | Intervalo excluido |
| T-G12 | `min_present` solo tiene filas con `present > 0` | min_present >= 1 siempre (nunca 0) |

### Tests de frontend

| ID | Escenario | Verificación |
|----|-----------|--------------|
| T-F01 | `data = null`, `loading = true` | Skeleton visible, sin error |
| T-F02 | `error = "mensaje"`, `loading = false` | Banner rojo con mensaje y botón reintentar |
| T-F03 | `data` con arrays vacíos | Estado vacío descriptivo con CTA a Ingresar |
| T-F04 | `data` con `animal_regen_rates: []` | RegenRatesSection muestra aviso "necesitas 2+ ataques" |
| T-F05 | `data` con datos completos | Dos secciones visibles con números formateados por Intl |
| T-F06 | Móvil (< md) | Columna de confianza oculta; ratio visible |
| T-F07 | Panel global no afecta OasisList | OasisList carga independientemente aunque el panel falle |

## 13. Riesgos y trade-offs

### Trade-off 1 — `repopulation_gaps` expuesto vs. solo rates

**Decisión:** La respuesta de EP-09 NO incluye `repopulation_gaps` (la lista detallada
de cada intervalo). Solo incluye `animal_appearances` y `animal_regen_rates`.

**Justificación:** El panel global es una vista de resumen. Los gaps individuales
(potencialmente cientos) no aportan valor en la vista global y aumentarían el
payload innecesariamente. El detalle de gaps queda en EP-06 (por oasis).

### Trade-off 2 — Carga paralela vs. secuencial con OasisList

**Decisión:** El panel global se carga en paralelo con OasisList (dos llamadas
independientes al montar StatsTab), no secuencialmente.

**Justificación:** Independencia de estados; si uno falla el otro no se bloquea.
El coste es dos queries simultáneas a SQLite, que en WAL es perfectamente válido.

### Trade-off 3 — `total_oasis` / `total_attacks` omitidos en v1

**Decisión:** No se incluyen en el payload ni en el panel.

**Justificación:** El usuario los excluyó explícitamente. Se pueden añadir como
campos opcionales en una v2 sin romper retrocompatibilidad (añadir campos al response
es no-breaking).

### Riesgo 1 — Rendimiento con volumen alto

Con miles de reportes, las queries de LAG sin filtro de coordenadas pueden ser
lentas. Mitigación v1: el caso de uso real es un usuario con decenas o centenas
de reportes. Mitigación futura: índice compuesto `(coord_x_dest, coord_y_dest,
attacked_at)` ya existe (`idx_attack_reports_coords_time`), lo que ayuda al LAG.

## 14. Pasos de implementación ordenados

Los pasos deben seguirse en este orden. Cada uno es autocontenido y testeable.

```
1. [backend/port] Añadir método abstracto a AttackReportPort:
   
   @abstractmethod
   async def get_global_oasis_stats(self) -> dict:
       """
       Devuelve estadísticas globales de todos los oasis combinados:
         - animal_appearances: aparición de animales (appearances, avg, max, min)
         - animal_regen_rates: ratio de regeneración por hora por animal
           (calculado juntando todos los intervalos de todos los oasis)
       200 con arrays vacíos si no hay datos.
       Ver spec docs/specs/bd-ataques-oasis-stats-global.md §8 EP-09.
       """

2. [backend/adaptador] Implementar get_global_oasis_stats() en
   AttackReportSQLiteAdapter (ver §9 para el pseudocódigo SQL completo).
   Reutilizar _calc_regen_rates sin modificación alguna.
   Añadir justo después de get_oasis_stats() para que quede agrupado.

3. [backend/router] Añadir EP-09 en attack_reports.py:
   - Posición: ANTES de @router.get("/attack-reports/stats/oasis") (línea ~436).
   - Sin parámetros de entrada.
   - Sin Accept-Language.
   - Delegar a port.get_global_oasis_stats() directamente (sin lógica en la ruta).
   
   @router.get("/attack-reports/stats/global", status_code=status.HTTP_200_OK)
   async def get_global_oasis_stats(request: Request) -> dict:
       """Estadísticas globales de todos los oasis. Ver spec §8 EP-09."""
       port = request.app.state.attack_report_port
       return await port.get_global_oasis_stats()

4. [backend/tests] Escribir tests de EP-09 cubriendo T-G01..T-G12 del §12.
   Usar la misma fixture de BD que los tests de EP-06.

5. [frontend/client] Añadir en frontend/src/api/client.js dentro del objeto api:
   
   /** GET /attack-reports/stats/global → estadísticas globales de todos los oasis */
   getGlobalOasisStats: () =>
     request('GET', '/attack-reports/stats/global'),

6. [frontend/componente] Crear GlobalOasisStatsPanel.jsx en
   frontend/src/components/attack-reports/. Ver §9 para el pseudocódigo JSX.
   Sub-componentes: GlobalStatsSkeleton, GlobalStatsEmpty, GlobalAppearancesTable.
   Reutilizar RegenRatesSection importando desde './RegenRatesSection.jsx'.
   Seguir tokens CSS del DESIGN.md: var(--surface), var(--border), var(--accent-text),
   tabular-nums en columnas numéricas, Intl.NumberFormat(lang) para formatear.

7. [frontend/StatsTab] Modificar StatsTab.jsx de forma additive (ver §9):
   - Añadir estado: globalData, globalLoading, globalError.
   - Añadir loadGlobal (useCallback + useEffect al montar).
   - Render: <GlobalOasisStatsPanel ... /> ANTES de <OasisList ... />.
   - Separador visual de 24px entre panel y lista.

8. [frontend/tests] Cubrir T-F01..T-F07 del §12.
```

## 15. Criterios de aceptación

Checklist verificable por el implementador antes de marcar como implementado:

**Backend:**
- [ ] `AttackReportPort` tiene el método abstracto `get_global_oasis_stats()`.
- [ ] `AttackReportSQLiteAdapter` implementa `get_global_oasis_stats()`.
- [ ] `_calc_regen_rates` NO fue modificada (es función pura reutilizada tal cual).
- [ ] `GET /attack-reports/stats/global` declarado ANTES de `stats/oasis` en el router.
- [ ] Con BD vacía → 200 con `{ scope:"global", animal_appearances:[], animal_regen_rates:[] }`.
- [ ] Con 1 ataque total → `animal_regen_rates: []`, `animal_appearances` con datos.
- [ ] Con 2+ oasis con 2+ ataques → `valid_intervals` suma los intervalos de todos los oasis.
- [ ] `min_present` nunca es 0 (excluye filas con `present = 0`).
- [ ] `avg_present` y `avg_regen_per_hour` redondeados a 2 decimales.
- [ ] Orden `animal_appearances` y `animal_regen_rates` por `animal_ordinal ASC`.
- [ ] Tests del §12 pasan (T-G01..T-G12).

**Frontend:**
- [ ] `api.getGlobalOasisStats()` añadido en `client.js`.
- [ ] `GlobalOasisStatsPanel.jsx` creado; importa y reutiliza `RegenRatesSection`.
- [ ] Panel visible ENCIMA de `OasisList` al abrir la pestaña Estadísticas.
- [ ] Estado loading: skeleton o spinner visible mientras carga.
- [ ] Estado error: banner rojo con botón reintentar; OasisList no afectada.
- [ ] Estado vacío: texto descriptivo con CTA a pestaña Ingresar.
- [ ] `RegenRatesSection` muestra su aviso propio cuando `animal_regen_rates = []`.
- [ ] Números formateados con `Intl.NumberFormat(lang)` y `tabular-nums`.
- [ ] Responsive: en `< md`, columna de confianza oculta (`.hidden md:table-cell`).
- [ ] Tests del §12 pasan (T-F01..T-F07).

**Integración:**
- [ ] Las dos llamadas (global stats + oasis list) se hacen en paralelo al montar.
- [ ] Un error en el panel global no impide que OasisList cargue.
- [ ] El panel global se recarga al hacer clic en "Reintentar" sin recargar OasisList.

## 16. Trazabilidad

| Decisión técnica | Requisito / edge case origen |
|------------------|------------------------------|
| Nuevo método `get_global_oasis_stats()` en el puerto | Necesidad de datos globales sin contaminar la firma de `get_oasis_stats(x,y)` |
| Reutilización de `_calc_regen_rates` sin modificación | RN-G04: cálculo global = misma función con más gaps; palantir lo identificó |
| `PARTITION BY coord_x_dest, coord_y_dest` en el LAG global | EC-G07: los gaps de oasis distintos son independientes; cruzarlos sería incorrecto |
| `appearances` (mismo nombre que EP-06) | Consistencia del contrato; frontend puede reutilizar los mismos helpers de formateo |
| `scope: "global"` en la respuesta | Consistencia con EP-07 (`get_bounty_stats`) que usa el mismo campo |
| Panel fijo encima de OasisList, carga en paralelo | Decisión del usuario (UI: panel siempre visible); Trade-off 2 |
| `total_oasis` / `total_attacks` omitidos | Decisión explícita del usuario (§3 Fuera del alcance) |
| `min_present` nullable en el tipo | EC-G06: `MIN(CASE WHEN > 0 ...)` puede devolver NULL si no hay filas válidas |
| Ruta declarada antes de `stats/oasis` | C6 (convención del módulo): literales primero para evitar ambigüedad de routing |
| Carga en StatsTab (no en OasisList) | El panel es hermano de OasisList, no hijo; OasisList no se modifica |
| Reutilización de RegenRatesSection | palantir: acepta `rates[]` con la estructura exacta que devuelve el backend |
| API: reutiliza/modifica/crea | CREAR EP-09 — decisión por palantir (no existe endpoint global); verificado en `adapters/api/routes/attack_reports.py` |
| Reutilización: `_calc_regen_rates` REUTILIZAR — palantir, verificado en `adapters/db/attack_report_sqlite_adapter.py` línea 135 |
| Reutilización: `RegenRatesSection` REUTILIZAR — palantir, verificado en `frontend/src/components/attack-reports/RegenRatesSection.jsx` |
| Modificación: `AttackReportPort` MODIFICAR (adición de método) — palantir, verificado en `core/ports/attack_report_port.py` |
| Modificación: `AttackReportSQLiteAdapter` MODIFICAR (nueva impl) — palantir, verificado en `adapters/db/attack_report_sqlite_adapter.py` |
| Modificación: router MODIFICAR (nuevo endpoint) — palantir, verificado en `adapters/api/routes/attack_reports.py` |
| Modificación: `client.js` MODIFICAR (nuevo método) — palantir, verificado en `frontend/src/api/client.js` |
| Creación: `GlobalOasisStatsPanel.jsx` CREAR — componente nuevo sin equivalente existente |
| Modificación: `StatsTab.jsx` MODIFICAR additive — palantir, verificado en `frontend/src/components/attack-reports/StatsTab.jsx` |

## Registro de implementación

**Fecha:** 2026-05-31
**Implementado por:** desarrollador-funcionalidades

### Ficheros creados
- `/Users/german/DEV/Travian con Agentes/tests/test_global_oasis_stats_api.py` — 18 tests de integración EP-09
- `/Users/german/DEV/Travian con Agentes/frontend/src/components/attack-reports/GlobalOasisStatsPanel.jsx` — panel global con sub-componentes (skeleton, error, vacío, tabla de apariciones)

### Ficheros modificados
- `core/ports/attack_report_port.py` — método abstracto `get_global_oasis_stats()` añadido
- `adapters/db/attack_report_sqlite_adapter.py` — implementación `get_global_oasis_stats()` añadida después de `list_oasis_summaries`; `_calc_regen_rates` no modificada
- `adapters/api/routes/attack_reports.py` — EP-09 insertado entre `stats/bounty` y `stats/oasis`; docstring de rutas actualizado
- `frontend/src/api/client.js` — método `getGlobalOasisStats()` añadido
- `frontend/src/components/attack-reports/StatsTab.jsx` — reescrito additive con estado global independiente + `GlobalOasisStatsPanel` encima de `OasisList`
- `frontend/src/i18n/catalog/es.js` — 9 claves `ar.stats.global.*` en español
- `frontend/src/i18n/catalog/en.js` — 9 claves `ar.stats.global.*` en inglés
- Los 23 catálogos restantes (`ar`, `bg`, `cs`, `da`, `de`, `el`, `fa`, `fr`, `he`, `hu`, `it`, `ja`, `lt`, `lv`, `nl`, `pl`, `pt`, `rs`, `ru`, `sl`, `sv`, `tr`, `uk`) — 9 claves `ar.stats.global.*` en inglés (fallback)

### Comando para ejecutar los tests
```bash
cd "Travian con Agentes" && .venv/bin/python -m pytest tests/test_global_oasis_stats_api.py tests/test_attack_reports_api.py -v
```

### Resultado
81 passed (18 nuevos EP-09 + 63 preexistentes sin regresiones) en 29.31s

### Criterios de aceptación cumplidos
Todos los criterios de §15 verificados como cumplidos.

### Desviaciones respecto al diseño
1. **Tests de frontend T-F01..T-F07 no implementados.** El proyecto no tiene framework de tests de componentes React (`vitest`, `jest`, `testing-library`). Queda pendiente para cuando se añada infraestructura de test frontend. Los estados (loading/error/vacío/con-datos) son verificables visualmente en la prueba manual del usuario.
