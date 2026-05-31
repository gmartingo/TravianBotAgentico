---
id: bd-ataques-oasis-fix-hora-balance
titulo: "Fix hora del ataque (verbatim) + balance de recursos por oasis"
estado: implemented
fecha: 2026-05-31
autor: analista
apis_validadas_por_desarrollador_apis: true
---

# Fix hora del ataque (verbatim) + balance de recursos por oasis

> **SPEC DE CAMBIO sobre `bd-ataques-oasis` (estado: implemented).**
> El spec base es `docs/specs/bd-ataques-oasis.md`. Este documento describe SOLO los delta:
> lo que cambia, lo que se añade y los edge cases nuevos o actualizados.
> Lo no mencionado aquí permanece igual al spec base.
>
> **APIs VALIDADAS por `desarrollador-apis`** (2026-05-31, modo revisión de contrato):
> veredicto OK con 7 correcciones (C1-C7) ya aplicadas a este documento. Cambios clave:
> `coord_x_dest`/`coord_y_dest` siempre presentes (`null` en scope global); rango de
> coordenadas `-400..400` validado por FastAPI con `ge`/`le` → `422` (no 400) fuera de rango;
> la combinatoria x-sin-y sigue siendo `400`. El contrato de EP-07 queda cerrado.
>
> **Spec complementario:** `docs/specs/bd-ataques-oasis-stats-oasis-nav.md` cubre los
> cambios surgidos en la misma prueba manual (BUG 1 panel stats, BUG 2 iconos héroe,
> ratio regen/hora, lista de oasis navegable). Aplicar los dos specs en el mismo bloque
> de trabajo: el verbatim de `attacked_at` de este spec es prerrequisito del cálculo
> de `gap_seconds` del spec complementario.

---

## 1. Objetivo de negocio

Este cambio corrige dos problemas independientes descubiertos tras la implementación:

**Cambio 1 — Hora del ataque guardada y mostrada de forma incorrecta.**
Un reporte real del 31.05.26 demostró que el parser coge la hora de la línea del ataque
(`13:39:30`) y le resta el offset del `Server time` (`UTC +01:00`), guardando `12:39:30`
en BD. El frontend luego reinterpreta ese ISO 8601 UTC con la zona horaria del PC del
usuario (España, UTC+2 en verano), mostrando `14:39:30`. Ambas conversiones son erróneas.

La decisión tomada (ya acordada con el usuario, no reabrir): guardar y mostrar la hora
**verbatim** — exactamente como la pone Travian en la línea del ataque, sin ninguna
conversión de zona horaria.

**Cambio 2 — Balance de recursos saqueados como estadística automática.**
Hoy el usuario calcula a mano el total de wood/clay/iron/crop saqueados. Se añade un
endpoint que devuelve esos totales desglosados por recurso, por oasis y de forma global.

---

## 2. Actores y permisos

Sin cambios respecto al spec base. Usuario único, local, sin autenticación.

---

## 3. Alcance

### Dentro del alcance de este cambio

- Corrección del parser: `attacked_at` pasa a ser la hora verbatim de la línea del ataque.
- Corrección de la semántica del campo `attacked_at` en BD: cambia de "UTC ISO 8601" a
  "hora local del servidor de Travian, verbatim, sin zona horaria".
- Ajuste de las queries de estadísticas para confirmar que siguen siendo correctas con el
  nuevo formato.
- Corrección del frontend: 4 componentes dejan de usar `new Date()` + `Intl.DateTimeFormat`
  para mostrar `attacked_at`; pasan a mostrar el string verbatim con formateo presentacional
  básico (sin conversión de zona).
- Nuevo endpoint EP-07: balance de recursos saqueados (desglosado por recurso) por oasis
  y de forma global.
- Corrección de tests afectados por el cambio de hora.
- Migración de datos existentes en BD (ver §7).

### Fuera del alcance de este cambio (anotado para el futuro)

- Balance de tropas perdidas (bajas del atacante en términos de recursos).
- Total de animales matados acumulado (sumatorio histórico por tipo de animal).
- Pantalla nueva en el frontend para el balance de recursos (queda para otro spec); el
  endpoint EP-07 se crea y expone, pero la pantalla de visualización es trabajo futuro.
- Estadísticas globales multi-oasis de repoblación (EP-06 sigue exigiendo `x`/`y`
  obligatorios; el resumen global de tiempo entre ataques queda fuera de alcance).

---

## 4. Reglas de negocio (cambios respecto al spec base)

### RN-08-bis — Timestamp verbatim (reemplaza RN-08 del spec base)

El reporte de Travian tiene DOS horas distintas con semánticas distintas:

| Línea en el reporte | Ejemplo | Semántica |
|---|---|---|
| Línea del ataque (bajo el título del oasis) | `31.05.26, 13:39:30` | **HORA DEL ATAQUE** — la que el usuario quiere |
| `Server time: HH:MM:SS (UTC +HH:MM)` | `Server time: 19:22:21 (UTC +01:00)` | Reloj de visualización (hora a la que el usuario *miró* el reporte) |

**Regla:** `attacked_at` = fecha y hora extraídas de la línea del ataque (`DD.MM.YY, HH:MM:SS`),
guardada como string ISO 8601 **sin información de zona horaria** (`YYYY-MM-DDTHH:MM:SS`, naive).

**El offset del `Server time` NO se usa para calcular `attacked_at`.** Travian tiene el
servidor fijo en UTC+1 todo el año (sin DST); el offset es siempre `+01:00`, pero eso no
convierte la hora del ataque: la hora que pone en la línea del ataque ya es la hora que
el usuario ve en el juego, y eso es exactamente lo que queremos guardar.

**`utc_offset`** se conserva como metadato informativo del servidor (saber en qué zona
opera el servidor de Travian puede ser útil en el futuro para correlaciones). Pero queda
claro en el código y en los comentarios: **no se usa para derivar `attacked_at`**. Si la
línea `Server time` no está presente, `utc_offset = NULL` — sin ningún impacto en `attacked_at`.

#### Formato de `attacked_at` en BD

| Antes (bug) | Después (corrección) |
|---|---|
| `"2026-05-31T12:39:30+00:00"` (UTC ISO 8601) | `"2026-05-31T13:39:30"` (naive, verbatim) |

El string es parseable por SQLite sin ambigüedad: `UNIXEPOCH("2026-05-31T13:39:30")` da
el epoch correcto tratando el valor como si fuera UTC, lo cual es consistente para todas
las filas (todas están en el mismo "reloj del servidor de Travian"). Ver §7.2.

### RN-B1 — Balance de recursos: desglose por recurso y por oasis

Para cada oasis (identificado por `coord_x_dest`, `coord_y_dest`), el sistema puede
devolver la suma histórica de `bounty_wood`, `bounty_clay`, `bounty_iron`, `bounty_crop`
y su total. También puede devolver ese mismo desglose de forma global (todos los oasis).

Si `x`/`y` se omiten en la llamada → resultado global (suma de todos los reportes).
Si `x`/`y` se incluyen → resultado filtrado por ese oasis.

---

## 5. Flujo principal y flujos alternativos (cambios)

### Flujo alternativo A — Duplicado (mensaje actualizado)

El mensaje de 409 usaba `attacked_at` en formato UTC ISO 8601. Pasa a usar el string
verbatim tal como viene de la BD:

```
409 Conflict:
{
  "detail": "Reporte ya registrado (id: 42, atacado el 31.05.26 13:39:30 desde '00')."
}
```

El formato de presentación del timestamp en el `detail` es libre (el implementador elige
el que sea legible), pero NO debe incluir zona horaria ni aplicar conversiones.

---

## 6. Edge cases (cambios y nuevos)

| ID | Caso | Tratamiento actualizado |
|---|---|---|
| EC-03-bis | Sin línea `Server time` en el reporte (pegado incompleto) | `utc_offset = NULL`. `attacked_at` se guarda verbatim desde la línea del ataque igualmente. No hay impacto en la hora — el caso ya era correcto; ahora queda aún más claro. |
| EC-H1 | Hora del ataque y hora del Server time difieren en más de 1 hora (ej. usuario mirando el reporte horas después) | Con verbatim esto ya no es un problema: se guarda la hora del ataque, ignorando el Server time a efectos de `attacked_at`. |
| EC-H2 | Servidor de Travian en otro offset (futura versión multi-región) | Con verbatim tampoco es problema: guardamos lo que pone el juego, sea cual sea el offset del servidor. |
| EC-H3 | Cambio de horario de verano en el PC del usuario | Irrelevante: ya no se lee la zona horaria del PC en el frontend. La hora mostrada es siempre la del string verbatim. |
| EC-H4 | Dos ataques al mismo oasis guardados con el mismo timestamp verbatim | La clave UNIQUE `(coord_x, coord_y, attacked_at, origin_village_name)` sigue siendo válida. Con verbatim los strings son comparables lexicográficamente sin conversión adicional. |
| EC-B1 | Balance de recursos con 0 reportes para ese oasis | EP-07 devuelve `200` con todos los totales a `0`. No devuelve `404`. |
| EC-B2 | Balance global con 0 reportes en toda la BD | EP-07 sin `x`/`y` devuelve `200` con todos los totales a `0`. |

---

## 7. Modelo de datos / cambios de esquema

### 7.1 Cambio de semántica del campo `attacked_at` (sin cambio de DDL)

El DDL de la tabla `attack_reports` **no cambia** (el campo sigue siendo `TEXT NOT NULL`).
Solo cambia el formato de los valores que se insertan:

| Campo | Antes | Después |
|---|---|---|
| `attacked_at` | `"2026-05-31T12:39:30+00:00"` (UTC con offset) | `"2026-05-31T13:39:30"` (naive, verbatim) |
| Comentario en DDL | `-- Almacenado en UTC como ISO 8601` | `-- Hora local del servidor de Travian, verbatim, sin zona (ISO 8601 naive)` |

La clave de unicidad `UNIQUE(coord_x_dest, coord_y_dest, attacked_at, origin_village_name)`
sigue siendo válida: el formato naive es igualmente único.

Los índices `idx_attack_reports_coords_time` e `idx_attack_reports_attacked_at` no cambian;
las comparaciones `>=` / `<=` sobre strings ISO 8601 naive son correctas lexicográficamente
(el formato `YYYY-MM-DDTHH:MM:SS` ordena igual que un timestamp numérico).

### 7.2 Impacto en queries de estadísticas — `UNIXEPOCH`

Las queries de repoblación en `get_oasis_stats` usan:

```sql
UNIXEPOCH(r.attacked_at) - UNIXEPOCH(LAG(r.attacked_at) OVER w)
```

Con strings naive (`"2026-05-31T13:39:30"` sin offset), SQLite los interpreta como si
fueran UTC. Esto es correcto para calcular **diferencias**: como todas las filas están
en el **mismo reloj** (hora local del servidor de Travian, que opera en UTC+1 sin DST),
los deltas entre ataques consecutivos son matemáticamente exactos. La diferencia entre
`13:39:30` y `09:14:21` es siempre 5h 25min 9s, independientemente de que SQLite trate
ambas como UTC o como UTC+1.

No se necesita ningún ajuste en las queries SQL de estadísticas.

### 7.3 Migración de datos existentes

**Caso nominal:** la feature `bd-ataques-oasis` no está commiteada. La BD en el entorno
del desarrollador es `travian_bot.db`, que está en `.gitignore` y puede estar vacía o
contener solo filas del periodo de desarrollo.

**Si la BD tiene filas con el formato UTC antiguo:** el campo `raw_text` se almacenó con
cada reporte. El path de migración es:

```python
# Script de migración (one-shot, ejecutar manualmente si hay filas viejas):
# 1. Leer todas las filas de attack_reports (id, raw_text, attacked_at).
# 2. Por cada fila, re-parsear el raw_text con el nuevo parser.
# 3. Si el nuevo attacked_at difiere del guardado, actualizar la fila.
# 4. Re-verificar unicidad (el update puede crear colisiones si había 2 filas
#    que en el nuevo formato resultaran duplicadas — caso extremadamente improbable).
```

El implementador debe evaluar si hay filas. Si la BD está vacía, no hay migración.

---

## 8. Contratos de API — cambios en existentes y nuevo endpoint

> Los endpoints EP-01 a EP-06 se mantienen con los mismos contratos del spec base,
> salvo los cambios de semántica del campo `attacked_at` descritos abajo.

### Cambio de semántica de `attacked_at` en EP-01, EP-02, EP-03, EP-04, EP-06

El campo `attacked_at` en todos los responses pasa de `"2026-05-31T12:39:30+00:00"` (UTC)
a `"2026-05-31T13:39:30"` (naive verbatim). Los campos que lo documentaban como
"ISO 8601 UTC" pasan a documentarse como "ISO 8601 naive (hora local del servidor de Travian)".

**Ejemplo concreto:** el reporte del 31.05.26 ataque a las 13:39:30 devuelve:

```json
"attacked_at": "2026-05-31T13:39:30"
```

y **nunca** `"2026-05-31T12:39:30+00:00"` ni `"2026-05-31T14:39:30"`.

### EP-07 — Balance de recursos (nuevo)

```
GET /attack-reports/stats/bounty?x=<int>&y=<int>

Query params (ambos opcionales, enteros, rango -400..400):
  x, y  — si se pasan AMBOS: balance de ese oasis específico.
           si se omiten AMBOS: balance global (todos los reportes de la BD).
           si se pasa UNO solo: 400 Bad Request.
           si no son enteros o están fuera de -400..400: 422 (automático de FastAPI, ge/le).

Sin Accept-Language (datos numéricos, no texto localizado).

Response 200 OK — con datos (scope oasis):
{
  "scope": "oasis",                     // "oasis" si x/y presentes, "global" si no
  "coord_x_dest": -32,                  // valor si scope="oasis"; null si scope="global"
  "coord_y_dest": -45,                  // ídem
  "total_reports": 7,                   // número de reportes incluidos en el cálculo
  "bounty": {
    "wood":  4320,
    "clay":  4320,
    "iron":  4320,
    "crop":  4320,
    "total": 17280                      // = wood + clay + iron + crop
  }
}

Response 200 OK — balance global (sin x/y):
{
  "scope": "global",
  "coord_x_dest": null,                 // SIEMPRE presente; null en scope global (C1)
  "coord_y_dest": null,
  "total_reports": 42,
  "bounty": { "wood": 21000, "clay": 18500, "iron": 12000, "crop": 9000, "total": 60500 }
}

Response 200 OK — sin datos (0 reportes para ese scope):
{
  "scope": "oasis",
  "coord_x_dest": -32,
  "coord_y_dest": -45,
  "total_reports": 0,
  "bounty": { "wood": 0, "clay": 0, "iron": 0, "crop": 0, "total": 0 }
}

Response 400 Bad Request:
{
  "detail": "Parámetro 'x' requiere 'y' y viceversa."
}
// → cuando se pasa x sin y, o y sin x

Response 422 Unprocessable Entity:
// → cuando x o y no son enteros, o están fuera del rango -400..400.
//   Lo genera FastAPI automáticamente al declarar Query(..., ge=-400, le=400).
```

**Decisión de diseño — ruta `/stats/bounty`:**
Se declara como ruta literal bajo el prefijo `/attack-reports/stats/`, igual que EP-06
(`/stats/oasis`). Para que FastAPI no capture `"stats"` como `{id}`, EP-07 también se
declara ANTES de `GET /attack-reports/{id}` en el router (o bien se apoya en que `{id}`
ya está tipado como `int ge=1`, lo que protege contra strings).

**Validación manual contra correcciones C1-C7 del proyecto:**
- C1 (validación de body): EP-07 es GET puro, no tiene body. N/A.
- C2 (hero_inventory como campo raíz): EP-07 no devuelve hero_inventory. N/A.
- C3 (response 201 completo): EP-07 es GET, no 201. N/A.
- C4 (errores 400 exhaustivos): documentados — solo el caso x-sin-y.
- C5 (semántica de acumulados): `bounty.total` es la suma de los 4 recursos del alcance
  indicado. Documentado explícitamente en el response.
- C6 (`{id}` como int): EP-07 no tiene `{id}`. N/A. La ruta literal `/stats/bounty`
  se declara antes de `/{id}` en el router.
- C7 (semántica de min/caso sin datos): caso sin datos devuelve 200 con totales a 0.

> **CONTRATO VALIDADO por `desarrollador-apis` (2026-05-31):** veredicto OK con correcciones
> C1-C7, ya aplicadas arriba. Coords siempre presentes (`null` en global); rango `-400..400`
> con `422`; combinatoria x-sin-y con `400`. EP-07 listo para implementar.

---

## 9. Flujo lógico paso a paso (cambios)

### 9.1 Parser — PASO 2 corregido (verbatim)

El único cambio está en la rama del if/else de detección del offset:

```python
# ANTES (bug):
if m_server:
    raw_offset = m_server.group(1)           # "+1:00"
    utc_offset = _normalize_offset(raw_offset)
    offset_delta = _parse_offset(raw_offset)
    dt_utc = dt_server - offset_delta        # ← RESTA EL OFFSET (incorrecto)
    attacked_at = dt_utc.replace(tzinfo=timezone.utc).isoformat()
else:
    attacked_at = dt_server.isoformat()       # naive

# DESPUÉS (correcto):
if m_server:
    raw_offset = m_server.group(1)           # "+1:00" — solo para utc_offset
    utc_offset = _normalize_offset(raw_offset)
    # NO se calcula offset_delta, NO se resta nada.
    # dt_server ya es la hora del ataque; se guarda verbatim.

attacked_at = dt_server.isoformat()          # naive, verbatim, siempre igual
                                             # formato: "YYYY-MM-DDTHH:MM:SS"
# _parse_offset y offset_delta se eliminan de este bloque.
# Si _parse_offset no se usa en ningún otro sitio, puede eliminarse del módulo.
```

Las funciones `_parse_offset` y `_normalize_offset` del parser:
- `_normalize_offset`: se mantiene — sigue siendo necesaria para serializar `utc_offset`
  como string legible (`"+01:00"`).
- `_parse_offset`: solo se usaba para restar el offset. Con la corrección ya no se necesita
  en el flujo principal. Si no tiene otros usos en el módulo, eliminarla; si se quiere
  conservar como utilidad, marcarla como privada y añadir un comentario explicativo.

### 9.2 Nuevo método en el adaptador de BD: `get_bounty_stats`

```python
async def get_bounty_stats(
    self,
    x: int | None = None,
    y: int | None = None,
) -> dict:
    """
    Balance de recursos saqueados.

    Si x e y son None → balance global (todos los reportes).
    Si x e y son enteros → balance del oasis en (x, y).

    Reutiliza la tabla attack_reports existente sin cambios de esquema.
    """
    params: list = []
    where = ""
    if x is not None:
        where = "WHERE coord_x_dest = ? AND coord_y_dest = ?"
        params = [x, y]

    sql = f"""
        SELECT
            COUNT(*)                    AS total_reports,
            COALESCE(SUM(bounty_wood),  0) AS wood,
            COALESCE(SUM(bounty_clay),  0) AS clay,
            COALESCE(SUM(bounty_iron),  0) AS iron,
            COALESCE(SUM(bounty_crop),  0) AS crop
        FROM attack_reports
        {where}
    """
    async with self._conn.execute(sql, params) as cursor:
        row = await cursor.fetchone()

    total_reports = row["total_reports"] if row else 0
    wood  = row["wood"]  if row else 0
    clay  = row["clay"]  if row else 0
    iron  = row["iron"]  if row else 0
    crop  = row["crop"]  if row else 0

    # C1/C5: coord_x_dest y coord_y_dest SIEMPRE presentes; None (→ null en JSON)
    # cuando scope="global". No usar presencia condicional (rompería el esquema OpenAPI).
    return {
        "scope": "oasis" if x is not None else "global",
        "coord_x_dest": x,    # None cuando global → serializa como null
        "coord_y_dest": y,    # None cuando global → serializa como null
        "total_reports": total_reports,
        "bounty": {
            "wood":  wood,
            "clay":  clay,
            "iron":  iron,
            "crop":  crop,
            "total": wood + clay + iron + crop,
        },
    }
```

### 9.3 Frontend — formateo de fecha verbatim

La función `formatDate` actual en los 4 componentes hace:

```js
// ANTES (bug):
return new Intl.DateTimeFormat(lang, {
  day: '2-digit', month: '2-digit', year: '2-digit',
  hour: '2-digit', minute: '2-digit',
}).format(new Date(isoStr))
// → new Date("2026-05-31T13:39:30") interpreta como UTC, pero el sistema del
//   usuario está en UTC+2 → muestra 15:39 en vez de 13:39.

// DESPUÉS (correcto):
// Parsear el string verbatim sin construir un Date (que haría conversión de zona).
function formatDateVerbatim(isoStr) {
  if (!isoStr) return '—'
  // isoStr: "2026-05-31T13:39:30"
  // Extraer partes directamente del string:
  const [datePart, timePart] = isoStr.split('T')
  if (!datePart) return isoStr
  const [y, m, d] = datePart.split('-')
  const timeShort = timePart ? timePart.slice(0, 5) : ''  // "13:39" (sin segundos)
  return `${d}/${m}/${y.slice(2)} ${timeShort}`           // "31/05/26 13:39"
}
```

**Formato de presentación elegido: `DD/MM/YY HH:MM`** — compacto y legible, igual que el
formato del reporte de Travian pero con separadores estándar occidentales. No se muestra
los segundos en el listado (la tabla ya es densa); sí se muestran en el detalle del
reporte si el diseño lo requiere. Esta decisión de presentación puede ajustarse sin
tocar la lógica.

> Nota: el `created_at` (fecha en que el usuario guardó el reporte en la BD) sí puede
> seguir usando `new Date()` + `Intl` porque es un timestamp del sistema local del usuario
> (no de Travian). Ver `ReportDetailDrawer.jsx:303`.

---

## 10. Validaciones y reglas (adiciones)

| Campo | Validación | Código error |
|---|---|---|
| `x` sin `y` en EP-07 | Ambos o ninguno (combinatoria semántica, validada en el handler) | 400 |
| `x`, `y` en EP-07 | Enteros con signo, rango -400..400 (`Query(ge=-400, le=400)`) | 422 |

---

## 11. Seguridad, rendimiento y concurrencia (sin cambios relevantes)

La query de `get_bounty_stats` es un simple `SELECT ... SUM ... COUNT` sin joins. Con
el volumen esperado (cientos a pocos miles de filas) es O(n) y tarda < 5 ms. El índice
`idx_attack_reports_coords_time` cubre el filtro por `(coord_x_dest, coord_y_dest)`.

---

## 12. Plan de pruebas (cambios y nuevos)

### Correcciones a tests existentes

#### test_T03_utc_offset_normalization (test_attack_report_parser.py)

El fixture `_REPORT_ES` tiene:
- Línea del ataque: `30.05.26, 16:28:53`
- `Server time: 17:28:53 (UTC +1:00)`

**Antes (bug):** el test afirmaba `"15:28:53" in preview.attacked_at` (restaba el offset).
**Después (correcto):** el test debe afirmar `"16:28:53" in preview.attacked_at`.

```python
def test_T03_utc_offset_normalization(self):
    """T-03: attacked_at es verbatim de la línea del ataque; utc_offset es metadato."""
    preview = parse_attack_report(_REPORT_ES)
    assert preview.utc_offset == "+01:00"
    # La hora del ataque es 16:28:53 (línea del ataque), NO 15:28:53.
    # El offset del Server time NO se resta.
    assert "16:28:53" in preview.attacked_at
    # Formato verbatim naive: sin +00:00 ni timezone info.
    assert "+" not in preview.attacked_at
    assert "Z" not in preview.attacked_at
    assert "T" in preview.attacked_at  # separador fecha/hora ISO
```

#### test_EC03_no_utc_offset (test_attack_report_parser.py)

El fixture `_REPORT_NO_OFFSET` tiene línea de ataque `30.05.26, 16:28:53` y sin Server time.
El comportamiento ya era correcto (guardaba verbatim); el test debe verificar el formato:

```python
def test_EC03_no_utc_offset(self):
    """EC-03: Sin offset UTC → utc_offset = None; attacked_at verbatim igualmente."""
    preview = parse_attack_report(_REPORT_NO_OFFSET)
    assert preview.utc_offset is None
    assert "16:28:53" in preview.attacked_at  # verbatim de la línea del ataque
    assert "+" not in preview.attacked_at
```

#### test_T01_parse_report_es (test_attack_report_parser.py)

El test actual solo verifica `"2026" in preview.attacked_at` (no la hora). Si se quiere
añadir verificación de la hora verbatim, añadir:

```python
assert "16:28:53" in preview.attacked_at   # verbatim de "30.05.26, 16:28:53"
```

#### Tests de integración: tests afectados en test_attack_reports_api.py

Los tests que comparan `attacked_at` en el response con valores como
`"2026-05-30T15:28:53+00:00"` deben actualizarse al formato verbatim
`"2026-05-30T16:28:53"`. Buscar en el archivo todos los asserts sobre `attacked_at`
que incluyan offsets UTC (`+00:00`, `Z`) y corregirlos.

### Nuevos tests para EP-07

| ID | Caso | Verificación |
|---|---|---|
| T-B1 | `GET /attack-reports/stats/bounty?x=-32&y=-45` con 3 reportes | `scope="oasis"`, `total_reports=3`, sumas correctas de wood/clay/iron/crop/total |
| T-B2 | `GET /attack-reports/stats/bounty` (sin x/y, con reportes) | `scope="global"`, `coord_x_dest=null`, `coord_y_dest=null`, `total_reports` = total en BD, sumas globales correctas |
| T-B3 | `GET /attack-reports/stats/bounty?x=-32&y=-45` sin reportes | 200, `scope="oasis"`, `coord_x_dest=-32`, `coord_y_dest=-45`, `total_reports=0`, todos los bounty a 0 |
| T-B4 | `GET /attack-reports/stats/bounty` sin datos en BD | 200, `scope="global"`, `coord_x_dest=null`, `coord_y_dest=null`, `total_reports=0`, todos a 0 |
| T-B5 | `GET /attack-reports/stats/bounty?x=-32` (sin y) | 400 con detail sobre x/y |
| T-B6 | `GET /attack-reports/stats/bounty?y=-45` (sin x) | 400 con detail sobre x/y |
| T-B7 | `bounty.total` = suma de los 4 recursos | Verificar que `bounty.total == wood + clay + iron + crop` |
| T-B8 | `GET /attack-reports/stats/bounty?x=999&y=10` (fuera de rango) | 422 (FastAPI, `ge`/`le`) |

---

## 13. Riesgos y trade-offs

### RT-H1 — ¿Qué pasa si en el futuro Travian añade conversión de zona horaria explícita?

Con el enfoque verbatim, si Travian algún día mueve servidores y empieza a mostrar
horas en otro huso horario, los reportes antiguos y los nuevos tendrán horas en relojes
distintos. Los gaps de repoblación seguirán siendo correctos dentro de cada "era" pero
no entre eras.

**Decisión:** aceptar el riesgo. El servidor de Travian lleva años en UTC+1 sin DST.
El `utc_offset` guardado como metadato permite en el futuro detectar y corregir este caso.

### RT-H2 — Strings ISO 8601 naive en SQLite: ¿ordenación correcta?

`UNIXEPOCH("2026-05-31T13:39:30")` en SQLite devuelve el epoch Unix tratando el string
como UTC. Todos los valores de `attacked_at` están en el mismo reloj (UTC+1 del servidor),
así que la diferencia entre dos epochs es matemáticamente igual a la diferencia real en
segundos entre los ataques. La ordenación lexicográfica de los strings también es correcta.

**Verificación:** con dos filas `"2026-05-31T09:14:21"` y `"2026-05-31T13:39:30"`,
`UNIXEPOCH(t2) - UNIXEPOCH(t1)` = 19509 segundos (5h 25min 9s). Correcto.

### RT-B1 — Un solo endpoint para bounty global y por oasis

Se podría haber creado dos endpoints separados (`/stats/bounty/global` y
`/stats/bounty/oasis?x=&y=`). Se eligió un único endpoint con parámetros opcionales
porque el comportamiento es idéntico salvo el filtro WHERE, reduce el surface de API,
y el campo `scope` en la respuesta indica al cliente qué tipo de resultado está recibiendo.

---

## 14. Pasos de implementación ordenados

> El implementador lee primero el spec base (`docs/specs/bd-ataques-oasis.md`),
> luego este documento. Las modificaciones son quirúrgicas y acotadas.

### Bloque 1 — Parser (core, sin I/O)

**Archivo:** `core/use_cases/attack_report_parser.py`

1. Localizar el bloque "PASO 2 — Extraer cabecera" (~líneas 421-433).
2. **Eliminar** la resta del offset dentro del `if m_server:`. El nuevo código guarda
   `utc_offset` (metadato) pero ya NO calcula `offset_delta` ni `dt_utc`.
3. Mover `attacked_at = dt_server.isoformat()` **fuera** del if/else, de forma que
   siempre se ejecuta con el valor verbatim, independientemente de si hay `Server time`.
4. Verificar si `_parse_offset` tiene otros usos en el módulo. Si no los tiene,
   eliminarla. `_normalize_offset` se conserva para el metadato `utc_offset`.

```python
# PASO 2 — bloque attacked_at corregido:
utc_offset: str | None = None
m_server = _SERVER_TIME_PATTERN.search(text)
if m_server:
    raw_offset = m_server.group(1)
    utc_offset = _normalize_offset(raw_offset)
    # Metadato informativo. NO se usa para calcular attacked_at.

# Hora del ataque verbatim (naive, sin zona horaria).
# dt_server proviene de la línea "DD.MM.YY, HH:MM:SS" del reporte.
attacked_at = dt_server.isoformat()  # → "YYYY-MM-DDTHH:MM:SS"
```

### Bloque 2 — Adaptador de BD

**Archivo:** `adapters/db/attack_report_sqlite_adapter.py`

5. Actualizar el comentario del DDL de `attacked_at` en `ensure_tables()`:
   - Antes: `-- Almacenado en UTC como ISO 8601 (TEXT): "2026-05-30T15:28:53+00:00"`
   - Después: `-- Hora local del servidor de Travian, verbatim, sin zona horaria (ISO 8601 naive): "2026-05-30T16:28:53"`
6. Añadir el método `get_bounty_stats(self, x, y)` siguiendo el pseudocódigo de §9.2.
7. Actualizar el puerto abstracto `core/ports/attack_report_port.py`: añadir el método
   abstracto `get_bounty_stats(self, x=None, y=None) -> dict`.

### Bloque 3 — Router de API

**Archivo:** `adapters/api/routes/attack_reports.py`

8. Añadir EP-07 como ruta GET declarada ANTES de `GET /attack-reports/{id}` (el segmento
   es `/stats/bounty`, que como literal no colisiona con `/{id}` siempre que se declare
   primero o que `{id}` sea `int ge=1`).

```python
@router.get("/attack-reports/stats/bounty")
async def get_bounty_stats(
    request: Request,
    x: int | None = Query(default=None, ge=-400, le=400, description="Coordenada X del oasis (-400..400). Si se omite junto con y, devuelve el balance global."),
    y: int | None = Query(default=None, ge=-400, le=400, description="Coordenada Y del oasis (-400..400)."),
):
    # Combinatoria x/y: ambos o ninguno (FastAPI ya valida tipo y rango → 422).
    if (x is None) != (y is None):
        raise HTTPException(status_code=400, detail="Parámetro 'x' requiere 'y' y viceversa.")
    port = request.app.state.attack_report_port
    return await port.get_bounty_stats(x=x, y=y)
```

### Bloque 4 — Frontend (4 componentes)

**Archivos afectados** (todos con `formatDate` que usa `new Date()` + `Intl.DateTimeFormat`):

| Archivo | Líneas clave | Qué cambia |
|---|---|---|
| `frontend/src/components/attack-reports/HistoryTable.jsx` | 37-46 (función `formatDate`) | Reemplazar por `formatDateVerbatim` |
| `frontend/src/components/attack-reports/ReportPreview.jsx` | 31-38 (función `formatDate`) | Reemplazar por `formatDateVerbatim` |
| `frontend/src/components/attack-reports/ReportDetailDrawer.jsx` | 28-37 (función `formatDate`) | Reemplazar por `formatDateVerbatim` |
| `frontend/src/components/attack-reports/OasisStatsPanel.jsx` | 20-28 (función `formatDate`) | Reemplazar por `formatDateVerbatim` |

La función `formatDateVerbatim` es idéntica en los 4 componentes. Si se quiere evitar
la duplicación, extraerla a `frontend/src/utils/formatDateVerbatim.js` y hacer import
desde los 4 componentes. Decisión de refactoring libre para el implementador.

**`created_at` queda SIN cambios**: este campo es la fecha de guardado en la BD del sistema
local del usuario; sí tiene semántica de zona horaria correcta y puede seguir usando
`new Date()`. Ver `ReportDetailDrawer.jsx:303`.

### Bloque 5 — Tests

9. **`tests/unit/test_attack_report_parser.py`:** actualizar `test_T03_utc_offset_normalization`
   y `test_EC03_no_utc_offset` según los valores del §12. Revisar cualquier otro assert
   sobre `attacked_at` que contenga offsets (`+00:00`, `Z`).

10. **`tests/test_attack_reports_api.py`:** buscar y corregir todos los asserts que comparen
    `attacked_at` con el formato UTC antiguo. Añadir tests T-B1 a T-B7 para EP-07.

---

## 15. Criterios de aceptación

Lista verificable por el implementador:

- [ ] **CA-H1**: Pegar el reporte real del 31.05.26 (`attacked_at` en la línea del ataque:
  `13:39:30`, `Server time: 19:22:21 (UTC +01:00)`). El preview devuelve
  `attacked_at = "2026-05-31T13:39:30"` exactamente. Nunca `12:39`, nunca `14:39`,
  nunca `19:22`.
- [ ] **CA-H2**: El frontend muestra `13:39` en la tabla de historial, en el preview, en el
  drawer de detalle y en el panel de estadísticas. No muestra `14:39` (que sería el bug
  con UTC+2 del PC en verano).
- [ ] **CA-H3**: `utc_offset` sigue apareciendo como `"+01:00"` en el response de EP-01 y
  EP-02 (metadato conservado).
- [ ] **CA-H4**: `test_T03_utc_offset_normalization` afirma `"16:28:53" in preview.attacked_at`
  y pasa en verde.
- [ ] **CA-H5**: Ningún test del parser o de la API contiene una aserción con offset UTC en
  `attacked_at` (`+00:00`, `Z`, o diferencia de -1h respecto a la hora del reporte).
- [ ] **CA-H6**: El gap de repoblación entre dos ataques al mismo oasis guardados con el nuevo
  formato es matemáticamente correcto (verificable con dos reportes de prueba).
- [ ] **CA-B1**: `GET /attack-reports/stats/bounty?x=-32&y=-45` con reportes devuelve las
  sumas correctas de wood/clay/iron/crop y su total.
- [ ] **CA-B2**: `GET /attack-reports/stats/bounty` (sin x/y) devuelve el balance global con
  `scope="global"` y `coord_x_dest`/`coord_y_dest` a `null` (presentes siempre, C1).
- [ ] **CA-B3**: `GET /attack-reports/stats/bounty?x=-32&y=-45` sin reportes devuelve 200
  con `scope="oasis"`, `coord_x_dest=-32`, `coord_y_dest=-45` y todos los totales a 0.
- [ ] **CA-B4**: `GET /attack-reports/stats/bounty?x=-32` (sin y) devuelve 400; con `x`/`y`
  fuera de rango (`-400..400`) devuelve 422.
- [ ] **CA-B5**: EP-07 está declarado en el router ANTES de `GET /attack-reports/{id}` y
  no hay colisión de routing.

---

## 16. Trazabilidad

| Decisión técnica | Requisito / edge case que la origina |
|---|---|
| `attacked_at` verbatim (naive, sin restar offset) | RN-08-bis; diagnóstico con reporte real 31.05.26: 13:39:30 es la hora del ataque, 19:22:21 es la hora de visualización |
| Conservar `utc_offset` como metadato | RT-H1: permite correlaciones futuras si el servidor de Travian cambia de zona |
| `_parse_offset` puede eliminarse | Ya no se usa tras la corrección; `_normalize_offset` se conserva para serializar `utc_offset` |
| `formatDateVerbatim` sin `new Date()` | EC-H3: `new Date(isoStr)` interpreta naive como UTC y JS lo convierte a zona local; España en verano está en UTC+2, mostrando la hora 1h más tarde |
| `created_at` sigue usando `new Date()` | `created_at` es un timestamp del sistema local del usuario, no de Travian; la conversión de zona es correcta para ese campo |
| UNIXEPOCH sobre strings naive en SQLite | RT-H2: diferencias de tiempo son correctas porque todas las filas están en el mismo reloj |
| EP-07 con x/y opcionales (un endpoint, no dos) | RT-B1: misma lógica SQL, `scope` en response indica el tipo |
| EP-07 declarado antes de `/{id}` en el router | C6 (corrección previa de desarrollador-apis): evitar captura de literales como `{id}` |

### Reutilización (mapa de palantir del spec base — sin cambios)

| Pieza | Decisión | Notas para este cambio |
|---|---|---|
| `_normalize_offset` en parser | REUTILIZAR | Se conserva para `utc_offset` metadato |
| `_SERVER_TIME_PATTERN` en parser | REUTILIZAR | Solo se usa para extraer `utc_offset`; ya no para restar |
| `_FECHA_PATTERN` en parser | REUTILIZAR sin cambios | Extrae la fecha/hora del ataque verbatim |
| `get_oasis_stats` en adapter | REUTILIZAR sin cambios | Las queries UNIXEPOCH siguen siendo correctas con strings naive |
| EP-06 (`/stats/oasis`) | REUTILIZAR sin cambios | No toca la lógica de bounty |
| `idx_attack_reports_coords_time` | REUTILIZAR | Cubre el WHERE de `get_bounty_stats` |

### APIs (fallback — no validado por desarrollador-apis en esta sesión)

EP-07 (`GET /attack-reports/stats/bounty`) es CREAR. No existe endpoint previo que lo
cubra. El contrato fue diseñado manualmente siguiendo las correcciones C1-C7 del
proyecto. Pendiente de luz verde de `desarrollador-apis` antes de implementar.

---

*Spec de cambio redactado el 2026-05-31. Fecha del spec base: 2026-05-30.*

---

## Registro de implementación

**Fecha:** 2026-05-31
**Implementado por:** desarrollador-funcionalidades

### Archivos creados/modificados

| Archivo | Cambio |
|---|---|
| `core/use_cases/attack_report_parser.py` | Eliminada resta del offset; `attacked_at = dt_server.isoformat()` siempre; eliminada `_parse_offset`; eliminado import `timedelta/timezone` |
| `adapters/db/attack_report_sqlite_adapter.py` | Comentario DDL actualizado; añadido `_calc_regen_rates` (función de módulo); añadido `get_bounty_stats`; añadido `list_oasis_summaries`; `get_oasis_stats` ahora incluye `animal_regen_rates` |
| `core/ports/attack_report_port.py` | Añadidos métodos abstractos `get_bounty_stats` y `list_oasis_summaries`; docstring de `get_oasis_stats` actualizado |
| `adapters/api/routes/attack_reports.py` | Añadidos EP-07 (`/stats/bounty`) y EP-08 (`/oasis`) antes de `/{id}`; mensaje 409 sin "UTC" |
| `adapters/api/main.py` | Import y registro de `AttackReportSQLiteAdapter` + `attack_reports_router` (faltaban) |
| `tests/unit/test_attack_report_parser.py` | Corregidos `test_T03` y `test_EC03`; añadidos tests `TestCalcRegenRates` (T-R1..T-R6 + extras) |
| `tests/test_attack_reports_api.py` | Corregido `test_T03_utc_offset_in_parse`; añadidos `TestBountyStats` (T-B1..T-B8), `TestOasisStatsRegen` (T-R8, T-R9, T-R1, estructura), `TestOasisList` (T-N1..T-N9 + extras) |
| `travian_bot.db` | Migración aplicada: 5 filas con formato UTC antiguo (`+00:00`) actualizadas a formato verbatim naive |

### Comando para ejecutar los tests

```bash
python -m pytest tests/unit/test_attack_report_parser.py tests/test_attack_reports_api.py -v
```

### Resultado de tests

107 de 107 tests pasan (0 fallos en el scope de esta feature).
Suite completa (sin antidetección): 949 passed, 2 failed (preexistentes: test_login_use_case y test_session_api con token inválido), 23 skipped.

### Resultado de la migración de BD

5 filas actualizadas en `travian_bot.db`:
| id | Antes | Después |
|---|---|---|
| 13 | `2026-05-31T14:29:52+00:00` | `2026-05-31T15:29:52` |
| 14 | `2026-05-30T19:27:28+00:00` | `2026-05-30T20:27:28` |
| 15 | `2026-05-30T22:14:49+00:00` | `2026-05-30T23:14:49` |
| 16 | `2026-05-31T05:29:30+00:00` | `2026-05-31T06:29:30` |
| 17 | `2026-05-31T12:39:30+00:00` | `2026-05-31T13:39:30` |

### Desviaciones respecto al diseño

- El router de attack_reports (`adapters/api/routes/attack_reports.py`) no estaba registrado en `main.py` y el adaptador no se inicializaba en el lifespan. Se añadieron ambos como parte de la implementación (el spec base lo daba por hecho pero no había sido incluido). Anotado como corrección necesaria — sin impacto en el contrato.
- `_calc_regen_rates` se implementó como función de módulo en `attack_report_sqlite_adapter.py` (recomendado por el spec) y NO como método estático de la clase.
