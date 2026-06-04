---
id: bd-ataques-oasis-global-pct-aparicion
titulo: Corrección del % de aparición de animales en la vista global de estadísticas de oasis (EP-09)
estado: implemented
fecha: 2026-06-01
autor: analista
apis_validadas_por_desarrollador_apis: true
---

# Corrección del % de aparición de animales en la vista global de oasis

## 1. Objetivo de negocio

La vista global de estadísticas de oasis (EP-09 `GET /attack-reports/stats/global`) devuelve
actualmente por animal solo el campo `appearances` (conteo crudo de reportes donde `present > 0`).
El frontend lo muestra como número sin denominador, lo que impide calcular ni mostrar un porcentaje
de aparición útil.

El problema de usar "todos los reportes de la BD" como denominador es que diluye artificialmente
el porcentaje: un oasis de madera (que nunca tiene ratas) suma reportes al total y baja el % de
las ratas aunque ese oasis sea irrelevante para ellas.

**Objetivo:** añadir al campo por animal un denominador semánticamente correcto
(`eligible_reports`) que permita calcular y mostrar un porcentaje de aparición justo, y actualizar
la celda de apariciones en `GlobalAppearancesTable` para mostrarlo como `appearances / eligible_reports (NN%)`.

**Ejemplo numérico de referencia** (incluido en los criterios de aceptación):
- Rata aparece en 6 de 10 reportes del oasis A y en 2 de 5 reportes del oasis B.
- El oasis C (de madera) tiene 20 reportes, ninguno con ratas.
- `appearances = 8` (6 + 2); `eligible_reports = 15` (10 + 5; oasis C excluido).
- `% aparición = 8 / 15 = 53 %` — NO `8 / 35 = 23 %` (que sería usar todos los reportes).

## 2. Actores y permisos

- **Usuario del dashboard** (único actor). Solo lectura. Sin autenticación adicional.
- No hay diferencia de permisos entre usuarios.

## 3. Alcance

### Dentro del alcance

- Añadir campo `eligible_reports` (integer) a cada item de `animal_appearances[]` en la
  respuesta de EP-09 (`GET /attack-reports/stats/global`).
- Nueva query SQL en `get_global_oasis_stats` del `AttackReportSQLiteAdapter` para calcular
  el denominador por `animal_ordinal`.
- Actualizar la celda "apariciones" en `GlobalAppearancesTable` (dentro de `GlobalOasisStatsPanel.jsx`)
  para mostrar `appearances / eligible_reports (NN%)`.
- Documentar EP-09 en `docs/api/openapi.yaml` con su path y schema (incluyendo `eligible_reports`).
- Añadir/actualizar tests de backend en `tests/test_global_oasis_stats_api.py` para verificar
  `eligible_reports` e invariante `appearances ≤ eligible_reports`.

### Fuera del alcance

- **EP-06 `GET /attack-reports/stats/oasis` no cambia.** Sigue mostrando `appearances/total_attacks`
  del oasis individual. Su celda de apariciones permanece sin modificar.
- **EP-10 `GET /attack-reports/stats/oasis/comparison` no cambia.**
- Ningún cambio de esquema de BD (sin migraciones DDL).
- No se añade columna de porcentaje como campo JSON independiente; el % es presentacional
  (se calcula en el frontend a partir de `appearances` y `eligible_reports`).
- No se añade filtro por rango de fechas al denominador.

## 4. Reglas de negocio

**RN-P01 — Definición de `eligible_reports` (denominador por animal):**
Para un animal dado (identificado por `animal_ordinal`), el denominador es el número de reportes
que pertenecen a oasis donde ESE animal ha aparecido al menos una vez (`present > 0` en algún
reporte de ese oasis). Incluye TODOS los reportes de esos oasis, también aquellos donde el animal
estaba a 0 o ausente en esa visita concreta.

Los oasis que NUNCA tuvieron ese animal (ningún reporte con `present > 0`) NO entran en el
denominador.

**RN-P02 — Numerador invariante:**
`appearances` (reportes con `present > 0` para ese animal) ya existe y no cambia. Es siempre
`≤ eligible_reports`. Esta es una invariante verificable: si se viola, hay un bug.

**RN-P03 — Porcentaje:**
`% aparición = appearances / eligible_reports × 100`. Dado RN-P02, el valor está en [0, 100].

**RN-P04 — El % es presentacional:**
No se devuelve como campo JSON. El frontend lo calcula como `Math.round(appearances / eligible_reports * 100)`.

**RN-P05 — `eligible_reports = 0` es imposible en la práctica:**
Si un animal aparece en `animal_appearances[]`, significa que tiene `appearances >= 1`, lo que
implica que existe al menos un oasis donde apareció, lo que implica que `eligible_reports >= 1`.
El frontend debe igualmente protegerse defensivamente contra `eligible_reports == null` o `== 0`
(backward-compat con clientes o BDs antiguas antes de este fix).

**RN-P06 — Animales con `present = NULL` (reportes de derrota) no cuentan:**
Las filas de `attack_report_animals` con `present = NULL` corresponden a reportes de derrota
donde Travian ocultó las cantidades. No cuentan ni en numerador (`appearances`) ni en denominador
(`eligible_reports`): la subquery del denominador filtra `WHERE a2.present > 0`, por lo que
`present = NULL` no satisface la condición y no entra en el conjunto `ever_present`.

**RN-P07 — EP-06 y EP-10 no cambian:**
Las vistas de oasis individual y de comparativa no se ven afectadas. Sus semánticas son distintas
(EP-06 usa `total_attacks` del oasis como denominador implícito, que es el comportamiento correcto
para un oasis individual).

## 5. Flujo principal y flujos alternativos

### Flujo principal (sin cambios observables externamente en el contrato de error)

```
1. Frontend monta StatsTab
2. StatsTab llama getGlobalOasisStats() → GET /attack-reports/stats/global
3. GlobalOasisStatsPanel muestra loading skeleton
4. Respuesta 200 con datos:
   - Cada item de animal_appearances ahora tiene: appearances, eligible_reports, avg/max/min_present
5. GlobalAppearancesTable renderiza la celda de apariciones como:
   "appearances / eligible_reports (NN%)"
   ej. "8/15 (53%)"
6. Usuario interpreta el % como: "de los reportes de oasis donde esta especie puede aparecer,
   en el NN% de ellos efectivamente estaba presente"
```

### Flujos alternativos

**FA-1 — BD vacía:** sin cambio; `animal_appearances: []` no tiene items que renderizar.

**FA-2 — Error de red o 5xx:** sin cambio; mismo banner rojo existente.

**FA-3 — `eligible_reports` ausente o `0` (cliente antiguo / BD sin datos):**
El frontend muestra solo `appearances` sin denominador ni porcentaje:
`"appearances"` (ej. `"8"`), sin barra ni paréntesis.

## 6. Edge cases

| ID | Escenario | Tratamiento esperado |
|----|-----------|----------------------|
| EC-P01 | Animal solo en un oasis con N reportes | `eligible_reports = N`; `appearances <= N`; `% <= 100%` |
| EC-P02 | Mismo animal en varios oasis | `eligible_reports` = suma de reportes de todos esos oasis |
| EC-P03 | Oasis C nunca tuvo ratas (`present = 0` en todos sus reportes) | Oasis C no entra en `eligible_reports` para rata. El denominador no lo incluye |
| EC-P04 | Animal con `present = 0` en algún reporte del oasis A, pero sí con `present > 0` en otros reportes del mismo oasis A | El oasis A SÍ entra en `eligible_reports` (basta con que haya aparecido alguna vez). Ese reporte con `present = 0` forma parte del denominador pero no del numerador |
| EC-P05 | BD vacía | `animal_appearances: []`; no hay items; no hay denominador que calcular |
| EC-P06 | Animal con `present = NULL` (reporte de derrota) | `NULL` no satisface `present > 0`; ese reporte ni cuenta en `appearances` ni en `eligible_reports`. Ver RN-P06 |
| EC-P07 | Un solo oasis con un solo reporte con `present > 0` | `appearances = 1`, `eligible_reports = 1`, `% = 100%`. Correcto: el animal apareció en el 100% de los reportes del único oasis donde puede aparecer |
| EC-P08 | Oasis con 3 reportes: first `present = 5`, second `present = 0`, third `present = 3` | `appearances = 2` (reportes 1 y 3); `eligible_reports = 3` (todos los reportes de ese oasis, porque el oasis sí tiene `ever_present`); `% = 67%` |
| EC-P09 | `appearances / eligible_reports` produce fracción | `Math.round(appearances / eligible_reports * 100)` en el frontend. Entero sin decimales |
| EC-P10 | `eligible_reports` es `null` en la respuesta (client antiguo) | Frontend muestra solo `appearances` sin denominador ni % (guardia defensiva) |
| EC-P11 | Invariante rota: `appearances > eligible_reports` | Imposible por diseño SQL, pero si ocurre: el frontend puede mostrar `> 100%`, que es señal visible de bug. No crashea |

## 7. Modelo de datos / cambios de esquema

**Sin cambios de esquema.** El campo `eligible_reports` se calcula on-the-fly con una query SQL.
No se añade ninguna columna ni tabla. No hay migraciones DDL.

Las tablas consultadas son las mismas tres existentes:
- `attack_reports`
- `attack_report_animals`
- `attack_report_attacker_troops` (no consultada en EP-09)

## 8. Contratos de API / interfaces

> **NOTA:** EP-09 no tiene path documentado en `docs/api/openapi.yaml` a fecha de este spec.
> El contrato a continuación incluye el campo nuevo `eligible_reports` y debe ser validado y
> documentado por el agente `desarrollador-apis` antes de implementar.
> `apis_validadas_por_desarrollador_apis` permanece `false` hasta recibir luz verde.

### EP-09 — Estadísticas globales de todos los oasis (modificación del shape)

```
GET /attack-reports/stats/global
```

**Sin parámetros de entrada. Sin Accept-Language.**

**Response 200 — con datos (shape modificado):**

```json
{
  "scope": "global",
  "animal_appearances": [
    {
      "animal_ordinal": 1,
      "animal_name": "Rat",
      "appearances": 8,
      "eligible_reports": 15,
      "avg_present": 7.50,
      "max_present": 15,
      "min_present": 3
    },
    {
      "animal_ordinal": 2,
      "animal_name": "Spider",
      "appearances": 4,
      "eligible_reports": 4,
      "avg_present": 4.33,
      "max_present": 9,
      "min_present": 2
    }
  ],
  "animal_regen_rates": [
    {
      "animal_ordinal": 1,
      "animal_name": "Rat",
      "avg_regen_per_hour": 3.45,
      "valid_intervals": 18
    }
  ]
}
```

**Response 200 — BD vacía / sin reportes (sin cambio):**

```json
{
  "scope": "global",
  "animal_appearances": [],
  "animal_regen_rates": []
}
```

**Tipos de campos — tabla completa con el nuevo campo:**

| Campo | Tipo | Nullable | Notas |
|-------|------|----------|-------|
| `scope` | string | No | Siempre `"global"` |
| `animal_appearances` | array | No | Vacío si no hay datos |
| `animal_appearances[].animal_ordinal` | integer | No | 1..10 |
| `animal_appearances[].animal_name` | string | No | Texto crudo de la BD |
| `animal_appearances[].appearances` | integer | No | >= 1 |
| `animal_appearances[].eligible_reports` | integer | No | >= appearances (invariante); nunca 0 si appearances >= 1 |
| `animal_appearances[].avg_present` | float | Sí | Redondeado a 2 decimales; null si sin datos (guardia defensiva) |
| `animal_appearances[].max_present` | integer | No | >= 1 |
| `animal_appearances[].min_present` | integer | Sí | null si sin datos (teórico) |
| `animal_regen_rates` | array | No | Sin cambio respecto al spec original |
| `animal_regen_rates[].animal_ordinal` | integer | No | |
| `animal_regen_rates[].animal_name` | string | No | |
| `animal_regen_rates[].avg_regen_per_hour` | float | No | Redondeado a 2 decimales |
| `animal_regen_rates[].valid_intervals` | integer | No | >= 1 |

**Compatibilidad:** el campo `eligible_reports` es aditivo. Clientes que no lo lean seguirán
funcionando correctamente (solo no mostrarán el denominador ni el %).

**Errores posibles (sin cambio):**

| Código | Condición |
|--------|-----------|
| 500 | Error interno de la BD (aiosqlite) |

No hay errores 400/422. Sin parámetros de entrada.

**Auth:** ninguna adicional. **Cabeceras:** `Content-Type: application/json`. Sin `Vary`.
**Idempotencia:** GET puro.

### Pendiente de validación por desarrollador-apis

El agente `desarrollador-apis` debe:
1. Decidir si REUTILIZAR/MODIFICAR EP-09 existente (ruta ya existe, solo se añade campo) o
   si el campo `eligible_reports` requiere versionado. El criterio: añadir un campo aditivo
   a un endpoint existente es un cambio retrocompatible y no requiere nueva versión.
2. Verificar que `eligible_reports` como `integer, not null` es el tipo correcto.
3. Documentar EP-09 con su path y schema en `docs/api/openapi.yaml`.
4. Dar luz verde explícita para actualizar `apis_validadas_por_desarrollador_apis: true`.

## 9. Flujo lógico paso a paso

### Backend — modificación de `get_global_oasis_stats()` en `AttackReportSQLiteAdapter`

El único cambio en el backend es añadir el **Paso 1b** (nueva query del denominador) e
incluir `eligible_reports` en el dict de cada item de `animal_appearances`.

```python
async def get_global_oasis_stats(self) -> dict:
    """
    Estadísticas globales de todos los oasis combinados.
    MODIFICADO: añade eligible_reports (denominador del % de aparición) por animal.

    Ver spec docs/specs/bd-ataques-oasis-global-pct-aparicion.md
    """

    # ── Paso 1a: Apariciones globales (SIN CAMBIO) ────────────────────────────
    async with self._conn.execute("""
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
    """) as cursor:
        appearance_rows = await cursor.fetchall()

    # ── Paso 1b: Denominador por animal (NUEVO) ───────────────────────────────
    # Para cada animal_ordinal:
    #   1. Identificar los oasis donde ese animal ha aparecido alguna vez (ever_present):
    #      subconsulta DISTINCT sobre (coord_x_dest, coord_y_dest, animal_ordinal)
    #      WHERE present > 0.
    #   2. Contar TODOS los reportes de esos oasis (sin filtro de present).
    #      Incluye los reportes donde el animal estaba a 0 ese día, porque en ese
    #      oasis sí puede aparecer.
    #   3. COUNT(DISTINCT r_eligible.id) evita contar el mismo reporte dos veces
    #      si el animal aparece en varios oasis con el mismo report_id (imposible por
    #      el esquema, pero la cláusula es una garantía formal).
    async with self._conn.execute("""
        SELECT
            a_ever.animal_ordinal,
            COUNT(DISTINCT r_eligible.id) AS eligible_reports
        FROM (
            SELECT DISTINCT
                r2.coord_x_dest,
                r2.coord_y_dest,
                a2.animal_ordinal
            FROM attack_report_animals a2
            JOIN attack_reports r2 ON r2.id = a2.report_id
            WHERE a2.present > 0
        ) a_ever
        JOIN attack_reports r_eligible
            ON  r_eligible.coord_x_dest = a_ever.coord_x_dest
            AND r_eligible.coord_y_dest = a_ever.coord_y_dest
        GROUP BY a_ever.animal_ordinal
    """) as cursor:
        eligible_rows = await cursor.fetchall()

    # Construir dict ordinal → eligible_reports para join O(1)
    eligible_by_ordinal: dict[int, int] = {
        row["animal_ordinal"]: row["eligible_reports"]
        for row in eligible_rows
    }

    # ── Pasos 2-5: LAG, gaps, _calc_regen_rates (SIN CAMBIO) ─────────────────
    # ... [código existente, sin modificación] ...

    # ── Paso 6: Construir y devolver el dict de respuesta ─────────────────────
    # MODIFICADO: añadir eligible_reports a cada item de animal_appearances
    return {
        "scope": "global",
        "animal_appearances": [
            {
                "animal_ordinal": row["animal_ordinal"],
                "animal_name":    row["animal_name"],
                "appearances":    row["appearances"],
                "eligible_reports": eligible_by_ordinal.get(row["animal_ordinal"]),
                # Si el ordinal no está en eligible_by_ordinal (caso teórico imposible
                # porque si hay appearances >= 1 hay ever_present), devuelve None.
                # El frontend maneja None como "sin denominador" (EC-P10).
                "avg_present":    round(row["avg_present"], 2) if row["avg_present"] is not None else None,
                "max_present":    row["max_present"],
                "min_present":    row["min_present_nonzero"],
            }
            for row in appearance_rows
        ],
        "animal_regen_rates": animal_regen_rates,
    }
```

### SQL del denominador — explicación detallada

```sql
-- Paso A: oasis donde el animal ha aparecido alguna vez (ever_present)
-- Resultado: filas únicas (coord_x_dest, coord_y_dest, animal_ordinal) donde present > 0
SELECT DISTINCT
    r2.coord_x_dest,
    r2.coord_y_dest,
    a2.animal_ordinal
FROM attack_report_animals a2
JOIN attack_reports r2 ON r2.id = a2.report_id
WHERE a2.present > 0
-- Alias: a_ever

-- Paso B: todos los reportes de esos oasis (sin filtro de present)
-- JOIN entre a_ever y attack_reports por coordenadas → incluye los reportes
-- donde ese día el animal estaba a 0 (pero el oasis sí puede tenerlo)
SELECT
    a_ever.animal_ordinal,
    COUNT(DISTINCT r_eligible.id) AS eligible_reports
FROM a_ever
JOIN attack_reports r_eligible
    ON  r_eligible.coord_x_dest = a_ever.coord_x_dest
    AND r_eligible.coord_y_dest = a_ever.coord_y_dest
GROUP BY a_ever.animal_ordinal
```

**Por qué `COUNT(DISTINCT r_eligible.id)`:**
El JOIN entre `a_ever` y `attack_reports` puede generar múltiples filas para el mismo
`report_id` si el animal `ever_present` aparece en la subquery con varias entradas de
coords distintas pero el mismo reporte_id (imposible en este schema: cada reporte tiene
unas coordenadas únicas). El `DISTINCT` es una guardia formal de correctitud.

**Invariante demostrada:** Para cada animal_ordinal en appearance_rows:
- `appearances` = COUNT(*) WHERE present > 0 para ese ordinal → todos esos reportes
  pertenecen a oasis donde el animal apareció al menos una vez.
- `eligible_reports` = COUNT de todos los reportes de esos oasis → incluye los
  `appearances` reportes más los reportes donde ese día estaba a 0.
- Por lo tanto: `appearances ≤ eligible_reports`. QED.

### Frontend — modificación de `GlobalAppearancesTable`

Solo cambia la celda que actualmente muestra `{new Intl.NumberFormat(lang).format(row.appearances)}`.

```jsx
// Antes (celda actual en GlobalOasisStatsPanel.jsx ~línea 211-222):
<td style={{ ... }}>
  {new Intl.NumberFormat(lang).format(row.appearances)}
</td>

// Después (misma celda, mismo estilo):
<td style={{ ... }}>
  {row.eligible_reports != null && row.eligible_reports > 0
    ? (() => {
        const pct = Math.round(row.appearances / row.eligible_reports * 100)
        return (
          <span>
            <span style={{ fontVariantNumeric: 'tabular-nums', fontFamily: 'var(--font-mono)' }}>
              {new Intl.NumberFormat(lang).format(row.appearances)}
              {'/'}
              {new Intl.NumberFormat(lang).format(row.eligible_reports)}
            </span>
            {' '}
            <span style={{ color: 'var(--text-tertiary)', fontSize: '11px' }}>
              ({pct}%)
            </span>
          </span>
        )
      })()
    : new Intl.NumberFormat(lang).format(row.appearances)
  }
</td>
```

**Reglas de formateo del %:**
- `Math.round(appearances / eligible_reports * 100)` — entero, sin decimales.
  Razón: un porcentaje con decimales (53.3%) añade falsa precisión para el usuario;
  el dato de origen (ataques a oasis) no tiene esa resolución.
- `Intl.NumberFormat(lang)` para `appearances` y `eligible_reports` — garantiza separadores
  de miles correctos para cada locale.
- El `%` se muestra como texto literal, sin pasar por `Intl.NumberFormat` (es un símbolo, no
  un número formateado).
- Estilo: `color: var(--text-tertiary)` para el paréntesis con %, `font-size: 11px` para que
  no compita visualmente con los números principales. Consistente con `DESIGN.md`.
- `tabular-nums` en los números — ya presente en el estilo de la celda; se mantiene.

**Encabezado de columna:** no cambia. La clave de i18n `ar.stats.global.col.appearances`
puede mantenerse con el texto actual (ej. "Apariciones") o actualizarse a "Apariciones / % "
según criterio del implementador. El spec no lo fuerza: es una decisión menor de UX.

**Guardia defensiva:**
- `row.eligible_reports != null && row.eligible_reports > 0` cubre:
  - Servidor antiguo que no devuelva el campo (backward-compat).
  - Caso teórico de `eligible_reports = 0` (imposible, pero no crashea).
  - En esos casos: muestra solo `appearances` sin denominador, igual que antes del fix.

## 10. Validaciones y reglas

| Validación | Dónde | Detalle |
|------------|-------|---------|
| `present > 0` en subquery ever_present | SQL | Solo oasis donde el animal apareció alguna vez |
| `eligible_reports >= appearances` | Invariante | Demostrada matemáticamente en §9; verificada por tests T-P03 y T-P04 |
| `eligible_reports` no nulo en la respuesta | Python (Paso 1b) | Si `appearances >= 1` siempre habrá entradas en `eligible_by_ordinal` para ese ordinal |
| `eligible_reports > 0` antes de dividir | Frontend | Guardia defensiva en JSX |
| `Math.round` para el % | Frontend | Entero sin decimales |
| `Intl.NumberFormat(lang)` para números | Frontend | Separadores de miles correctos por locale |
| Pasos 2-5 del backend sin modificación | Backend | `_calc_regen_rates` no se toca |
| EP-06 no modificada | Backend/Frontend | Semánticas distintas, fuera del alcance de este fix |

## 11. Seguridad, rendimiento y concurrencia

**Seguridad:** sin cambio respecto al spec original. GET puro, sin params, sin riesgo de inyección.

**Rendimiento del Paso 1b:**
La nueva query usa una subconsulta con `DISTINCT` sobre `attack_report_animals JOIN attack_reports`
seguida de un `JOIN` con `attack_reports`. Los índices existentes cubren esta query:
- `idx_animals_ordinal_report ON attack_report_animals (animal_ordinal, report_id)` — cubre
  el WHERE + DISTINCT de la subconsulta interna.
- `idx_attack_reports_coords_time ON attack_reports (coord_x_dest, coord_y_dest, attacked_at)` —
  cubre el JOIN externo por coordenadas.

Con el volumen típico (un usuario, decenas a centenares de reportes), el tiempo total de
EP-09 permanece < 200 ms. La query del Paso 1b se ejecuta de forma independiente y no
bloquea las queries del Paso 1a ni del LAG.

**Concurrencia:** SQLite WAL. Sin cambio respecto al spec original.

## 12. Plan de pruebas

### Tests de backend a añadir/actualizar en `tests/test_global_oasis_stats_api.py`

Los tests existentes T-G01..T-G12 no verifican el shape del item de `animal_appearances[]`
con strictness (no comprueban keys exactas), por lo que no se rompen con el campo nuevo.
Se añaden tests específicos del denominador.

| ID | Escenario | Verificación |
|----|-----------|--------------|
| T-P01 | Un solo oasis, N reportes, M con present > 0 | `appearances = M`, `eligible_reports = N`, `M <= N` |
| T-P02 | Dos oasis A (10 rep, rata siempre) y B (5 rep, rata siempre); oasis C (20 rep, sin rata) | `appearances = 15`, `eligible_reports = 15`, oasis C excluido |
| T-P03 | Invariante: `appearances <= eligible_reports` para todos los animales | Verificar para todos los items de `animal_appearances[]` |
| T-P04 | `eligible_reports` presente en cada item de `animal_appearances[]` | `row["eligible_reports"]` es un entero >= 1 cuando `appearances >= 1` |
| T-P05 | EC-P08: oasis con 3 reportes (present=5, present=0, present=3) | `appearances = 2`, `eligible_reports = 3` |
| T-P06 | Ejemplo numérico de referencia (§1): A(10 rep, 6 con rata), B(5 rep, 2 con rata), C(20 rep, sin rata) | `appearances = 8`, `eligible_reports = 15`, no `35` |
| T-P07 | BD vacía | `animal_appearances = []`; no hay items que verificar |
| T-P08 | EC-P07: un oasis con un reporte con present > 0 | `appearances = 1`, `eligible_reports = 1` |

### Tests de frontend (sin framework de test React activo — verificación visual)

Dado que el proyecto no tiene framework de tests de componentes React (anotado en el spec
`bd-ataques-oasis-stats-global.md` §Desviaciones), la verificación del frontend se realiza
visualmente durante la prueba manual del usuario. El implementador debe verificar:

- Celda muestra `"8/15 (53%)"` con el ejemplo numérico de referencia.
- Con `eligible_reports = null` (simulando servidor antiguo): muestra solo `"8"`.
- Con `eligible_reports = 1`, `appearances = 1`: muestra `"1/1 (100%)"`.
- % redondeado a entero (sin decimales).
- Locale respetado: separadores de miles correctos para el idioma activo.

## 13. Riesgos y trade-offs

### Trade-off 1 — % entero vs. con decimales

**Decisión:** `Math.round(...)` — porcentaje como entero.

**Justificación:** Los datos de origen son conteos de ataques, que oscilan entre decenas y
centenares de reportes como máximo. Un decimal no añade información útil para el usuario
y "53.3%" suena más preciso de lo que es. El comportamiento de `Math.round` al 50% es
"redondeo bancario impuro" (JS usa round-half-up), aceptable.

### Trade-off 2 — % en el backend vs. en el frontend

**Decisión:** `eligible_reports` en el backend, cálculo del % en el frontend.

**Justificación:** El backend entrega datos, no presentación. Devolver el denominador
permite que el frontend formatee el % con `Math.round` vs `toFixed(1)` según preferencia
sin necesitar un nuevo endpoint. También permite mostrar el denominador absoluto junto al %
(ej. `"8/15 (53%)"` en lugar de solo `"53%"`), que es más informativo.

### Trade-off 3 — Añadir campo al response vs. endpoint separado

**Decisión:** campo aditivo `eligible_reports` en el response existente de EP-09.

**Justificación:** No cambia la ruta ni la versión. Es retrocompatible (clientes que no lo
lean seguirán funcionando). No requiere una llamada HTTP extra desde el frontend. El único
riesgo (campo ignora el contrato OpenAPI anterior) es mitigado documentándolo en este spec y
validándolo con desarrollador-apis.

### Riesgo 1 — Rendimiento de la query del Paso 1b

Con volúmenes muy grandes (miles de oasis, decenas de miles de reportes), la subconsulta
con DISTINCT puede ser lenta. Mitigación v1: el volumen real es de un usuario con centenares
de reportes. Si en el futuro el volumen crece, la subconsulta se puede materializar o cachear.

### Riesgo 2 — Invariante `appearances <= eligible_reports` rota por bug

Si hay un bug en la query del Paso 1b que produzca `eligible_reports < appearances`, el
frontend mostraría un porcentaje > 100%, que es claramente incorrecto y visible. Los tests
T-P03 verifican la invariante explícitamente. El bug sería detectado inmediatamente.

## 14. Pasos de implementación ordenados

Los pasos deben seguirse en este orden. Cada uno es autocontenido y verificable.

```
1. [backend/adaptador] Modificar get_global_oasis_stats() en
   adapters/db/attack_report_sqlite_adapter.py (~línea 884):
   - Añadir el Paso 1b: query SQL del denominador (ver §9 para el SQL completo).
   - Construir eligible_by_ordinal dict (ordinal → eligible_reports).
   - En el Paso 6 (construcción del dict de respuesta), añadir el campo
     "eligible_reports": eligible_by_ordinal.get(row["animal_ordinal"])
     a cada item de animal_appearances.
   - Los Pasos 2-5 (LAG, gaps, _calc_regen_rates) NO se modifican.
   - Nota: el puerto (core/ports/attack_report_port.py) NO cambia; la firma
     get_global_oasis_stats() -> dict ya es válida.

2. [backend/tests] Añadir tests T-P01..T-P08 en
   tests/test_global_oasis_stats_api.py (ver §12).
   - Reutilizar el fixture client y el helper _build_report existentes.
   - Verificar especialmente T-P06 con el ejemplo numérico de referencia (§1).
   - Verificar T-P03 (invariante appearances <= eligible_reports) para todos los
     items de animal_appearances.
   - Ejecutar la suite completa para confirmar 0 regresiones en T-G01..T-G12.

3. [frontend/componente] Modificar GlobalAppearancesTable en
   frontend/src/components/attack-reports/GlobalOasisStatsPanel.jsx (~línea 211-222):
   - Reemplazar la celda de appearances por la versión con denominador y % (ver §9).
   - Guardia defensiva: mostrar solo appearances si eligible_reports es null o 0.
   - Mantener tabular-nums y font-mono en los números.
   - Mantener todos los demás estilos existentes de la celda.

4. [docs/api/openapi.yaml] Documentar EP-09 con desarrollador-apis (gate §8):
   - Añadir path /attack-reports/stats/global con operationId get_global_oasis_stats.
   - Definir schema GlobalOasisStatsResponse con los dos arrays.
   - Definir schema GlobalAnimalAppearance (incluye eligible_reports: integer, not null).
   - Definir schema GlobalAnimalRegenRate (ya existe parcialmente como AnimalRegenRate).
   - Insertar entre /attack-reports/stats/bounty y /attack-reports/stats/oasis
     (convención: literales más específicas primero, ya establecida en el router).
   NOTA: Este paso lo ejecuta el agente desarrollador-apis, no desarrollador-funcionalidades.
```

## 15. Criterios de aceptación

Checklist verificable por el implementador antes de marcar como implementado:

**Backend:**
- [ ] `get_global_oasis_stats()` ejecuta el Paso 1b (query del denominador) sin error.
- [ ] Cada item de `animal_appearances[]` contiene el campo `eligible_reports` (integer >= 1
      cuando `appearances >= 1`).
- [ ] Con el ejemplo numérico de referencia (A:10 rep/6 rata, B:5 rep/2 rata, C:20 rep/sin rata):
      `appearances = 8`, `eligible_reports = 15` (NO 35).
- [ ] `_calc_regen_rates` no fue modificada.
- [ ] `get_oasis_stats()` (EP-06) no fue modificada.
- [ ] Invariante: para todos los items de la respuesta, `appearances <= eligible_reports`.
- [ ] Tests T-P01..T-P08 pasan; T-G01..T-G12 sin regresiones.

**Frontend:**
- [ ] Celda de apariciones muestra `appearances / eligible_reports (NN%)` cuando
      `eligible_reports` está disponible y > 0.
- [ ] % es un entero (sin decimales), calculado con `Math.round`.
- [ ] Con `eligible_reports = null` o `0`: muestra solo `appearances` (sin /, sin %).
- [ ] Los números siguen usando `tabular-nums` y `Intl.NumberFormat(lang)`.
- [ ] Verificación visual del ejemplo numérico: `"8/15 (53%)"`.
- [ ] El % `(100%)` se muestra correctamente cuando `appearances == eligible_reports`.
- [ ] Ningún otro componente del módulo fue modificado (EP-06 y EP-10 no tienen cambios).

**API:**
- [ ] EP-09 documentado en `docs/api/openapi.yaml` con el campo `eligible_reports`.
- [ ] `apis_validadas_por_desarrollador_apis: true` en el frontmatter.

## 16. Trazabilidad

| Decisión técnica | Requisito / edge case origen |
|-----------------|------------------------------|
| Denominador = reportes de oasis con ever_present | Decisión cerrada DC-1: evitar dilución por oasis sin ese animal |
| Numerador = `appearances` existente (sin cambio) | Decisión cerrada DC-2: reutilizar lógica existente |
| `eligible_reports` como campo aditivo (no endpoint nuevo) | Trade-off 3: retrocompatibilidad + sin llamada HTTP extra |
| % calculado en frontend con `Math.round` | Trade-off 2: backend entrega datos, no presentación; Trade-off 1: entero sin decimales |
| Guardia defensiva `eligible_reports != null && > 0` | EC-P10: backward-compat con clientes o versiones antiguas |
| `COUNT(DISTINCT r_eligible.id)` en Paso 1b | EC-P02: evitar doble conteo formal aunque el schema lo hace imposible |
| `WHERE a2.present > 0` en subquery ever_present | RN-P06: excluir reportes de derrota (present = NULL no satisface > 0) |
| EP-06 y EP-10 no cambian | Decisión cerrada DC-4 / RN-P07 |
| Celda: `appearances / eligible_reports (NN%)` | Decisión cerrada DC-5 sobre display en frontend |
| % entero con Math.round | Trade-off 1: falsa precisión no deseable |
| Reutilización: `get_global_oasis_stats` MODIFICAR — palantir, verificado en `adapters/db/attack_report_sqlite_adapter.py` línea ~884 |
| Reutilización: `GlobalAppearancesTable` MODIFICAR — palantir, verificado en `frontend/src/components/attack-reports/GlobalOasisStatsPanel.jsx` línea ~135 |
| Sin cambio en el puerto `AttackReportPort` — firma `get_global_oasis_stats() -> dict` es válida para el shape ampliado |
| API: MODIFICAR EP-09 (campo aditivo) — decidido por analista, pendiente verificación de desarrollador-apis |
| Documentación EP-09 en openapi.yaml: CREAR path nuevo — EP-09 no está documentado actualmente |

## Registro de implementación

**Fecha:** 2026-06-01
**Implementado por:** desarrollador-funcionalidades

### Ficheros modificados (BACKEND solamente — frontend pendiente de implementación separada)

| Fichero | Tipo | Descripción |
|---------|------|-------------|
| `adapters/db/attack_report_sqlite_adapter.py` | Modificado | Añadido Paso 1b (query SQL del denominador) en `get_global_oasis_stats()`; `eligible_reports` añadido a cada item de `animal_appearances`; comentario del docstring actualizado |
| `tests/test_global_oasis_stats_api.py` | Modificado | Añadida clase `TestGlobalOasisStatsEligibleReports` con tests T-P01..T-P08 |
| `docs/specs/bd-ataques-oasis-global-pct-aparicion.md` | Modificado | `estado` cambiado a `implemented`; añadido este Registro de implementación |

### Comando para ejecutar los tests

```bash
# Solo los tests del módulo EP-09:
.venv/bin/python -m pytest tests/test_global_oasis_stats_api.py -v

# Tests de no regresión EP-06/balance:
.venv/bin/python -m pytest tests/test_attack_reports_api.py -v
```

### Resultado

- `tests/test_global_oasis_stats_api.py`: **26 passed** (18 existentes T-G01..T-G12 + 8 nuevos T-P01..T-P08)
- `tests/test_attack_reports_api.py`: **114 passed** (0 regresiones)

### Desviaciones respecto al diseño

Ninguna. La implementación sigue fielmente el spec §9 y §14 sin ningún cambio de criterio.

**Nota sobre el alcance:** este registro cubre únicamente el backend (Pasos 1 y 2 de §14). El frontend (Paso 3 de §14 — modificación de `GlobalAppearancesTable` en `GlobalOasisStatsPanel.jsx`) está fuera del alcance de esta tarea según instrucción explícita del orquestador y quedó pendiente para implementación separada.
