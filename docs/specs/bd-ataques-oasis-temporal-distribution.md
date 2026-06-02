---
id: bd-ataques-oasis-temporal-distribution
titulo: "Distribución empírica de animales por frecuencia de farmeo (Animal Temporal Distribution)"
estado: ready-for-impl
fecha: 2026-06-02
autor: analista
apis_validadas_por_desarrollador_apis: false
# HISTORIAL:
# v1 (2026-06-02): estado=implemented. Gate desarrollador-apis ejecutado (CORRECTO).
#   Contratos validados: bucket_hours en {1,2,4,8,12,24}, matriz animal x franja, Accept-Language oblig.
#   Implementacion completada: 33/33 tests, sin regresiones en suite completa (166 tests).
# v2 (2026-06-02): redesign funcional. interval_minutes sustituye a bucket_hours.
#   Binning umbral inferior (Opcion B). Respuesta de una sola frecuencia (no matriz).
#   39 tests en verde. UI rediseno separado (disenador-producto + mockup). Gate desarrollador-apis pendiente.
# v3 (2026-06-02): segmentacion por tipo de oasis inferido.
#   Response agrupado en 5 secciones fijas (hierro/arcilla/madera/cereal/sin_clasificar).
#   Reutiliza _infer_type y OASIS_TYPE_SETS (elevada a funcion de modulo en el adapter).
#   UI rediseno separado (disenador-producto). Gate desarrollador-apis pendiente.
---

# Distribución empírica de animales por frecuencia de farmeo

---

## REVISIÓN v3 — Segmentación por tipo de oasis inferido

> Esta sección documenta el nuevo diseño sobre v2 ya implementado (39 tests en verde).
> El resto del spec (secciones 1-16) ha sido actualizado para reflejar v3.
> El §"Qué cambia respecto a v2" al final del spec lista los cambios concretos para cada agente.

### Motivación

El usuario quiere entender cómo varía la composición de animales según el **tipo de oasis**
(Hierro, Arcilla, Madera, Cereal) a una cadencia dada. Un oasis de madera respawna lobos y osos;
uno de hierro respawna ratas y murciélagos. Mezclarlos en una sola lista oculta esa señal.

### Principio de diseño: inferencia por oasis, reutilización total de lógica existente

El tipo de oasis **no está almacenado** en la BD. Se **infiere** en tiempo de consulta a partir
de los animales observados, reutilizando sin duplicar la lógica ya implementada en EP-SPAWN:

- **`_infer_type(observed_ordinales, comp_list)`** — función en
  `adapters/db/attack_report_sqlite_adapter.py` (~línea 1953). Usa similitud de Jaccard
  contra `OASIS_TYPE_SETS`. Devuelve `(tipo: str|None, confidence: "low"|"medium"|None)`.
  Confianza "medium" si `sum(burst_count) >= 3`, "low" si < 3.
- **`OASIS_TYPE_SETS`** — en `core/game_data/oasis_spawn_catalog.py` (~línea 54):
  - `"hierro":  {1, 2, 4}`   — rata, araña, murciélago
  - `"arcilla": {1, 2, 5}`   — rata, araña, jabalí
  - `"madera":  {5, 6, 7}`   — jabalí, lobo, oso
  - `"cereal":  {1..10}`     — todos (set universal)

**Regla de elevación:** `_infer_type` es actualmente privada (prefijo `_`). Para que EP-TD
pueda llamarla, el implementador debe **renombrarla a `infer_type` (sin guión bajo)** o
extraerla a un módulo compartido (p.ej. `adapters/db/_oasis_type_utils.py`). Lo que NO debe
hacer es reimplementar el cálculo de Jaccard: un tercer Jaccard divergente sería un bug
esperando explotar. La decisión de elevación (renombrar vs. módulo) se deja al implementador,
pero debe documentarse en el Registro de implementación v3.

### Clasificación de cada oasis: una vez, sobre el agregado

La inferencia se hace **una vez por oasis** sobre el conjunto de todos sus animales observados
con `present > 0`, no por reporte individual. Cada gap de ese oasis hereda el tipo inferido
de su oasis.

El proceso exacto de obtención de `observed_ordinales` y `comp_list` por oasis es el mismo
que ya hace EP-SPAWN en `get_oasis_spawn_composition` (~línea 1539-1651):

```sql
-- Composicion por (oasis, animal) — solo present > 0
SELECT
    r.coord_x_dest,
    r.coord_y_dest,
    a.animal_ordinal,
    COUNT(*) AS burst_count
FROM attack_report_animals a
JOIN attack_reports r ON r.id = a.report_id
WHERE a.present > 0
GROUP BY r.coord_x_dest, r.coord_y_dest, a.animal_ordinal
```

De este resultado se construye por oasis:
- `observed_ordinales: set[int]` — set de ordinales con `present > 0`
- `comp_list: list[dict]` — lista con `{"animal_ordinal": int, "burst_count": int, ...}`

Y se llama `tipo, confidence = infer_type(observed_ordinales, comp_list)`.

**Resultado:** cada par `(coord_x_dest, coord_y_dest)` queda etiquetado con su `tipo` e `confidence`.
Este mapa `{(cx, cy): (tipo, confidence)}` se usa luego en el paso de agrupación de gaps.

### Gestión de baja confianza y oasis no clasificables

| Situación | Tratamiento |
|-----------|-------------|
| `confidence = "medium"` (>=3 bursts con present>0) | Oasis incluido en su sección de tipo con plena confianza. |
| `confidence = "low"` (<3 bursts con present>0) | Oasis incluido en su sección de tipo **con marca de baja confianza** (el n_oasis de esa sección cuenta los de low también). La sección expone `n_oasis_low_confidence` para que el front pueda mostrar un disclaimer. |
| `tipo = None` (sin ningún animal observado con present>0, p.ej. solo derrotas) | Oasis y todos sus gaps van a la sección `"sin_clasificar"`. |
| Oasis con todos los gaps descartados (< 6 min, o < 2 reportes) | No genera gaps en la ventana — no aparece en ninguna sección. No es necesario clasificarlo. |

**Justificación de incluir low-confidence en su sección:** excluirlos crearía la ilusión de
que ciertos tipos de oasis están "vacíos" cuando en realidad hay datos, aunque pocos. Es más
honesto mostrar el dato con su señal de confianza que ocultarlo. El front puede elegir añadir
un icono o nota "pocos datos" junto a la cifra.

### Problema del cereal y cómo lo resuelve Jaccard

El set de cereal es `{1..10}` (universal). Si usáramos solapamiento bruto, cualquier oasis
clasificaría como cereal con alta puntuación. Jaccard penaliza el set universal porque
`|∩| / |∪|` crece más lentamente cuando el denominador es grande:

- Oasis con animales `{1,2,4}` (hierro): Jaccard(hierro)=1.0, Jaccard(cereal)=3/10=0.30 → **hierro gana**.
- Oasis con animales `{5,6,7}` (madera): Jaccard(madera)=1.0, Jaccard(cereal)=3/10=0.30 → **madera gana**.
- Oasis con animales `{1,2,4,5,6,7,8,9,10}` (9 tipos muy variados): Jaccard(cereal)=9/10=0.90 → **cereal** — correcto, es un oasis cereal.

**Limitación del cereal que el frontend debe comunicar:** un oasis con animales muy diversos
puede clasificarse como cereal correctamente, pero la etiqueta "Cereal" cubre el 100% de los
tipos de animal. El frontend debe añadir una nota junto a la sección "Cereal" del estilo
"Oasis con composición variada — incluye todos los tipos de animal". Esto no es un bug; es
la naturaleza del oasis cereal en Travian.

### Response schema v3: agrupado por tipo

La respuesta añade el campo `types` (lista de secciones) en lugar del campo `animals` (plano).
El campo `animals` v2 **desaparece** del nivel raíz y queda dentro de cada sección de tipo.

**Schema completo v3:**

```json
{
  "interval_minutes": 240,
  "interval_label": "4h",
  "window": {
    "lower_min": 240,
    "upper_min": 300,
    "is_open": false
  },
  "n_reports_in_window": 42,
  "types": [
    {
      "oasis_type": "hierro",
      "oasis_type_label": "Hierro",
      "n_oasis": 3,
      "n_oasis_low_confidence": 1,
      "n_reports_in_section": 18,
      "animals": [
        {
          "animal_ordinal": 1,
          "animal_name": "Rata",
          "icon_url": "/static/icons/nature_1.png",
          "avg_present": 2.50,
          "mode_present": [2],
          "n_total": 18,
          "n_valid": 15
        }
      ]
    },
    {
      "oasis_type": "arcilla",
      "oasis_type_label": "Barro",
      "n_oasis": 2,
      "n_oasis_low_confidence": 0,
      "n_reports_in_section": 14,
      "animals": [...]
    },
    {
      "oasis_type": "madera",
      "oasis_type_label": "Madera",
      "n_oasis": 4,
      "n_oasis_low_confidence": 2,
      "n_reports_in_section": 7,
      "animals": [...]
    },
    {
      "oasis_type": "cereal",
      "oasis_type_label": "Cereal",
      "n_oasis": 1,
      "n_oasis_low_confidence": 0,
      "n_reports_in_section": 3,
      "animals": [...]
    },
    {
      "oasis_type": "sin_clasificar",
      "oasis_type_label": "Sin clasificar",
      "n_oasis": 1,
      "n_oasis_low_confidence": 0,
      "n_reports_in_section": 0,
      "animals": []
    }
  ]
}
```

**Descripción de los campos nuevos y modificados:**

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `n_reports_in_window` | `integer` | Total de gaps en la ventana (suma de `n_reports_in_section` de todas las secciones). Campo raiz, igual que en v2. |
| `types` | `array[5]` | Siempre exactamente 5 elementos (uno por tipo). Ver orden abajo. |
| `types[].oasis_type` | `string` | Clave canonica interna: `"hierro"`, `"arcilla"`, `"madera"`, `"cereal"`, `"sin_clasificar"`. |
| `types[].oasis_type_label` | `string` | Etiqueta de presentacion (fija, no localizada): `"Hierro"`, `"Barro"`, `"Madera"`, `"Cereal"`, `"Sin clasificar"`. OJO: la clave interna sigue siendo `"arcilla"` (del catalogo) pero el label es `"Barro"` (el usuario usa ese nombre). |
| `types[].n_oasis` | `integer` | Numero de oasis distintos de este tipo que tienen al menos un gap en la ventana. |
| `types[].n_oasis_low_confidence` | `integer` | Cuantos de esos oasis tienen `confidence = "low"`. `0` si ninguno. |
| `types[].n_reports_in_section` | `integer` | Numero de gaps (report_ids distintos) de oasis de este tipo en la ventana. `0` si no hay datos. |
| `types[].animals` | `array` | Lista de animales con estadisticas (mismos campos que en v2: `animal_ordinal`, `animal_name`, `icon_url`, `avg_present`, `mode_present`, `n_total`, `n_valid`). `[]` si `n_reports_in_section=0`. Orden: `animal_ordinal ASC`. |

**Nota importante sobre `n_total` dentro de animals en v3:** `n_total` de un animal dentro
de una seccion de tipo es el numero de gaps de oasis de ESE tipo en la ventana donde aparece
ese animal (incluye derrotas). No es el total global. La suma de `n_total` de todos los
animales de una seccion puede ser mayor que `n_reports_in_section` porque un mismo ataque
puede tener varios tipos de animal.

**Orden de las secciones (fijo):** `hierro`, `arcilla`, `madera`, `cereal`, `sin_clasificar`.
Este orden coincide con la progresion de los sets de especificidad (de mas especificos a mas
generales) y es predecible para el frontend.

**Las 5 secciones se devuelven siempre**, aunque esten vacias (`n_reports_in_section=0`,
`animals=[]`). Justificacion: el frontend necesita estructuras predecibles para renderizar
"Sin datos para este tipo a esta cadencia" sin hacer comprobaciones de presencia de clave.
Una seccion vacia es semanticamente diferente de una clave ausente.

**Sin parametro de filtro por tipo:** el endpoint siempre devuelve las 5 secciones. No se
anade un param `oasis_type` opcional porque el usuario eligio "todos los tipos a la vez"
y la complejidad adicional no aportaria valor.

---

## REVISIÓN v2 — Frecuencias en minutos + lista simple + binning umbral-inferior

> Esta seccion documenta el rediseno completo respecto a la implementacion v1.
> El resto del spec ha sido actualizado para reflejar v3 (que incluye v2).
> El apartado "Que cambia respecto a v2" al final del spec lista los cambios concretos para cada agente.

### Nuevo parámetro: `interval_minutes`

Sustituye a `bucket_hours`. El usuario elige UNA frecuencia discreta en minutos entre las
siguientes (conjunto cerrado, sin excepciones):

| Valor | Etiqueta | Significado |
|-------|----------|-------------|
| `6`   | `"6 min"` | Cadencia ultrarrápida |
| `7`   | `"7 min"` | Cadencia rápida |
| `10`  | `"10 min"` | |
| `15`  | `"15 min"` | |
| `30`  | `"30 min"` | Media hora |
| `60`  | `"1h"` | Hora |
| `120` | `"2h"` | |
| `180` | `"3h"` | |
| `240` | `"4h"` | Default (ventana de sueño del usuario) |
| `300` | `"5h"` | |

- Valor fuera del conjunto (p.ej. `interval_minutes=45`) → `400` con detail legible.
- Valor no entero o formato inválido → `422` (FastAPI validation automática).
- `interval_minutes` ausente → `200` con default `240` (4 horas).

### Binning por umbral inferior (Opción B)

Cada valor `F` del conjunto corresponde a una ventana `[F, F_next)` donde `F_next` es el
siguiente valor del conjunto en orden ascendente. La ventana de `300` (el último) es abierta
por arriba: `[300, ∞)`.

**Tabla de bins completa:**

| `interval_minutes` | Ventana | `lower_min` | `upper_min` | `is_open` |
|--------------------|---------|-------------|-------------|-----------|
| `6`   | `[6, 7)`    | 6   | 7   | false |
| `7`   | `[7, 10)`   | 7   | 10  | false |
| `10`  | `[10, 15)`  | 10  | 15  | false |
| `15`  | `[15, 30)`  | 15  | 30  | false |
| `30`  | `[30, 60)`  | 30  | 60  | false |
| `60`  | `[60, 120)` | 60  | 120 | false |
| `120` | `[120, 180)`| 120 | 180 | false |
| `180` | `[180, 240)`| 180 | 240 | false |
| `240` | `[240, 300)`| 240 | 300 | false |
| `300` | `[300, ∞)`  | 300 | null| true  |

**Frontera: inclusiva por abajo, exclusiva por arriba `[F, F_next)`.**

Un gap de exactamente `F` minutos pertenece al bin `F`, no al bin anterior.
Un gap de `F_next - ε` minutos pertenece al bin `F`, no al bin `F_next`.

**Justificación de Opción B vs. vecino-más-cercano:**

La asignación por umbral inferior es monótona y robusta al ruido de lag: un timer configurado
a 7 min que por latencia o imprecisión del reloj tarda 9 min sigue contando como cadencia de
7 min (cae en `[7, 10)`), sin saltar al bin de 10 min. El vecino-más-cercano rompería esa
propiedad: un gap de 8.5 min estaría a 1.5 min del umbral 7 y a 1.5 min del umbral 10, y la
decisión de asignación dependería del ruido, no de la intención del usuario. La Opción B
elimina esa ambigüedad: el bin es el umbral inferior de la ventana en que cae el gap, sin
excepción.

### Gaps fuera de rango (< 6 min)

Gaps con `gap_seconds < 360` (< 6 minutos) quedan **fuera de todos los bins** del conjunto.
Se **descartan silenciosamente** (no se cuentan en ninguna ventana).

Justificación: no existe ninguna frecuencia inferior a 6 min en el conjunto de valores
permitidos. Incluirlos en el bin de 6 min distorsionaría las estadísticas de esa cadencia
(mezclaría gaps genuinamente rápidos con anomalías de reloj o duplicados). Se anota en el
log de diagnóstico pero no se devuelve al cliente.

Adicionalmente, los gaps nulos (primer ataque por oasis) y los gaps ≤ 0 (relojes
inconsistentes) siguen descartándose como en v1 (RN-TD02 y EC-TD07).

### Response schema de UNA frecuencia (v2)

La respuesta ya no es una matriz por franja: el cliente elige UNA frecuencia y recibe la
estadística de la ventana correspondiente. Schema definitivo:

```json
{
  "interval_minutes": 240,
  "interval_label": "4h",
  "window": {
    "lower_min": 240,
    "upper_min": 300,
    "is_open": false
  },
  "n_reports_in_window": 18,
  "animals": [
    {
      "animal_ordinal": 6,
      "animal_name": "Lobo",
      "icon_url": "/static/icons/nature_6.png",
      "avg_present": 3.40,
      "mode_present": [3],
      "n_total": 18,
      "n_valid": 15
    }
  ]
}
```

**Descripción de campos:**

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `interval_minutes` | `integer` | Frecuencia solicitada (echo del parámetro). |
| `interval_label` | `string` | Etiqueta legible: `"6 min"`, `"7 min"`, `"10 min"`, `"15 min"`, `"30 min"`, `"1h"`, `"2h"`, `"3h"`, `"4h"`, `"5h+"`. El bin `300` lleva `"5h+"` para indicar que es abierto. |
| `window.lower_min` | `integer` | Límite inferior de la ventana en minutos (inclusive). |
| `window.upper_min` | `integer\|null` | Límite superior en minutos (exclusive). `null` para `interval_minutes=300`. |
| `window.is_open` | `boolean` | `true` solo para `interval_minutes=300`. |
| `n_reports_in_window` | `integer` | Número de gaps (ataques) que caen en la ventana. Incluye reportes con `present=null`. `0` si la ventana está vacía. |
| `animals` | `array` | Lista de animales con observaciones en la ventana. Orden: `animal_ordinal ASC`. `[]` si `n_reports_in_window=0`. |
| `animals[].animal_ordinal` | `integer` | Ordinal del animal (1-10, catálogo NATURE). |
| `animals[].animal_name` | `string` | Nombre localizado del animal. |
| `animals[].icon_url` | `string` | `/static/icons/nature_{ordinal}.png` |
| `animals[].avg_present` | `number\|null` | Media de `present` redondeada a 2 decimales. `null` si `n_valid=0`. |
| `animals[].mode_present` | `array[integer]` | Moda(s) de `present`. `[]` si `n_valid=0`. Empates: todos ASC. |
| `animals[].n_total` | `integer` | Reportes en la ventana para este animal (incluye derrotas con `present=null`). |
| `animals[].n_valid` | `integer` | Reportes con `present IS NOT NULL` en la ventana. |

**Estado "frecuencia sin datos":** si `n_reports_in_window = 0`, se devuelve
`200` con `animals: []`. El frontend mostrará el empty state: *"Aún no tienes suficientes
ataques con esta cadencia"*. Nunca `404`.

**Nota sobre `n_total` a nivel de `animals[]`:** cada animal puede tener un `n_total`
distinto porque no todos los animales aparecen en todos los reportes. La suma de
`animals[i].n_total` para todos los animales no tiene por qué ser igual a
`n_reports_in_window` (que cuenta reportes/gaps, no apariciones).

---

## 1. Objetivo de negocio

El usuario ataca oasis repetidamente y necesita saber **cuántos animales suelen aparecer**
en función de la cadencia de farmeo que utiliza. Con esa información puede calibrar la
frecuencia de sus ataques a cada oasis para maximizar el botín y evitar ataques en vacío.

El endpoint calcula, para una cadencia concreta elegida por el usuario (p.ej. "cada 4h"),
cuántas veces apareció cada tipo de animal en reportes cuyo gap con el ataque anterior cae
en la ventana correspondiente a esa cadencia, junto con la media y la moda del número de
unidades observadas. Esto permite responder preguntas como: "si farmeo cada 4h,
¿cuántos lobos suelen aparecer?"

## 2. Actores y permisos

- **Usuario del dashboard** (único actor). Solo lectura. Sin autenticación adicional más allá
  de la que ya protege la aplicación.

## 3. Alcance

### Dentro del alcance

- Modificar el endpoint `GET /attack-reports/stats/oasis/temporal-distribution` (EP-TD):
  cambiar el schema de respuesta de lista plana (`animals[]`) a lista agrupada por tipo
  (`types[]` con 5 secciones fijas: hierro, arcilla, madera, cereal, sin_clasificar).
- Elevar `_infer_type` a funcion publica/modulo en `adapters/db/attack_report_sqlite_adapter.py`
  (renombrar a `infer_type` o extraer a modulo compartido) para que EP-TD pueda reutilizarla
  sin duplicar el calculo de Jaccard.
- Modificar el metodo abstracto en `AttackReportPort`:
  `get_animal_temporal_distribution(interval_minutes, lang)` — la firma no cambia pero el
  tipo de retorno incluye `types` en lugar de `animals`.
- Modificar la implementacion en `AttackReportSQLiteAdapter`: nueva query de composicion por
  oasis, mapa de tipo por oasis con `infer_type`, agrupacion de gaps por tipo, calculo de
  estadisticas por (tipo x animal).
- **La UI** (componente `AnimalFrequencyPanel.jsx`) requiere **rediseno completo** por el
  agente `disenador-producto` (la vista pasa de lista plana a secciones por tipo de oasis)
  + **nuevo mockup editable aprobado** por el usuario **antes de implementarse**.
  Este spec cubre unicamente el backend + contrato de API.

### Fuera del alcance (v3)

- Consulta simultanea de multiples frecuencias (el cliente pide una por request).
- Filtro por oasis especifico (solo global).
- Filtro por rango de fechas.
- Filtro por tipo de oasis como parametro de query (el endpoint devuelve siempre las 5 secciones).
- Agrupacion individual por oasis dentro de una seccion.
- Paginacion.
- Comparativa entre oasis.
- Percentiles o histogramas de distribucion de unidades (solo media y moda).
- Exposicion de gaps descartados (< 6 min) al cliente.
- Localizacion de `oasis_type_label` (etiqueta fija en castellano: "Hierro", "Barro", "Madera", "Cereal", "Sin clasificar").

## 4. Reglas de negocio

**RN-TD01 — Base temporal: gap empírico entre ataques consecutivos.**
El gap de un reporte se calcula como la diferencia en segundos entre `attacked_at` del reporte
actual y `attacked_at` del reporte inmediatamente anterior al mismo oasis
(`PARTITION BY coord_x_dest, coord_y_dest ORDER BY attacked_at`), usando `LAG()`.
`attacked_at` se trata como naive (sin zona horaria) — todos los timestamps están en el mismo
reloj de servidor, por lo que las diferencias son correctas sin conversión.

**RN-TD02 — Primer ataque a cada oasis: descartado.**
El primer reporte de un oasis no tiene ataque previo → su gap es `NULL` → se descarta.
No contribuye a ninguna ventana.

**RN-TD03 — Binning por umbral inferior (Opción B).**
Dado `interval_minutes = F`, la ventana es `[F * 60, F_next * 60)` en segundos, donde
`F_next` es el siguiente valor del conjunto `{6,7,10,15,30,60,120,180,240,300}` en orden
ascendente. Para `F = 300` la ventana es `[18000, ∞)` (abierta por arriba).

La asignación es determinista y monótona: un gap `g` en segundos pertenece a la ventana `F`
si y solo si `F * 60 <= g < F_next * 60` (o `g >= 18000` para el bin `300`).

El cálculo del bin es en Python (no en SQL). SQL devuelve los gaps en segundos y Python
determina si caen en la ventana de la frecuencia solicitada.

**RN-TD04 — Gaps fuera de rango (< 6 min) descartados.**
Gaps con `gap_seconds < 360` no pertenecen a ningún bin del conjunto (no existe bin menor que
6 min). Se descartan silenciosamente. No se devuelven al cliente ni se cuentan en
`n_reports_in_window`.

**RN-TD05 — NULL en present (derrota): se excluye de media y moda, se cuenta en n_total.**
Cuando el resultado del combate fue derrota, `present = NULL` (desconocido). Para un animal:
- Se cuenta en `n_total` (el reporte ocurrió, tiene gap en la ventana → pertenece).
- No se cuenta en `n_valid` (no hay dato de cuántos animales había).
- No contribuye a `avg_present` ni a `mode_present`.

**RN-TD06 — Media: redondeada a 2 decimales.**
`avg_present = round(mean(present) for present not null, 2)`. Si `n_valid = 0` →
`avg_present = null`.

**RN-TD07 — Moda: calculada en Python, empates como lista.**
SQLite no tiene `MODE()`. La moda se calcula en Python con `collections.Counter` sobre los
valores de `present` no nulos. Si hay un único valor máximo → `mode_present = [valor]`.
Si hay empate → `mode_present` contiene todos los valores empatados, ordenados ASC.
Si `n_valid = 0` → `mode_present = []`.

**RN-TD08 — n_reports_in_window y n_total/n_valid por animal.**
- `n_reports_in_window` (nivel raíz): número de gaps (ataques al mismo oasis) que caen en
  la ventana. Incluye reportes con `present=null`. Es el denominador de "cuántos ataques
  tienes en esta cadencia".
- `animals[].n_total`: reportes en la ventana para ese animal (incluye derrotas).
- `animals[].n_valid`: reportes con `present IS NOT NULL`.
La suma de `animals[i].n_total` puede ser distinta de `n_reports_in_window` porque no todos
los animales aparecen en todos los reportes.

**RN-TD09 — Orden de resultados.**
Animales: por `animal_ordinal ASC` (coherente con el catálogo Nature).

**RN-TD10 — Nombres de animal localizados por Accept-Language.**
`Accept-Language` es obligatorio. Se resuelve con la dependencia `get_language` de
`adapters/api/dependencies.py`. El nombre localizado se obtiene de
`translation_port.get_troop_names_by_tribe(Tribe.nature, lang)` y se indexa por ordinal.
Fallback: si el ordinal no tiene nombre en el catálogo para ese idioma, se usa el nombre
guardado en `animal_name` de la BD (texto crudo).

**RN-TD11 — Scope: solo global.**
El cálculo agrega todos los oasis. Usa el mismo patrón LAG de EP-09: `PARTITION BY
coord_x_dest, coord_y_dest` garantiza que los gaps no cruzan oasis distintos.

**RN-TD12 — Estado vacío: 200 con n_reports_in_window=0 y animals=[].**
Si ningún gap cae en la ventana solicitada (BD vacía, sin datos suficientes, o frecuencia
sin observaciones) → `200` con `n_reports_in_window: 0` y `animals: []`.
Nunca `404`.

**RN-TD13 — Valores válidos de interval_minutes.**
`interval_minutes` ∈ `{6, 7, 10, 15, 30, 60, 120, 180, 240, 300}`.
Cualquier otro valor entero → `400` con detail legible que enumera los valores aceptados.
Valor no entero → `422` (FastAPI validation automática).
Ausente → `200` con default `240` (4 horas).

**RN-TD14 — Inferencia de tipo por oasis (v3).**
El tipo de cada oasis se infiere UNA sola vez sobre el agregado de todos sus animales observados
con `present > 0`, usando `infer_type(observed_ordinales, comp_list)` (funcion elevada desde
`_infer_type` del adapter). La inferencia usa Jaccard contra `OASIS_TYPE_SETS`. Devuelve
`(tipo, confidence)` donde `tipo` es `"hierro"|"arcilla"|"madera"|"cereal"|None` y
`confidence` es `"medium"` (>= 3 bursts) o `"low"` (< 3 bursts) o `None` (sin datos).
Cada gap de ese oasis hereda ese `tipo`. Este calculo precede a la agrupacion de gaps.

**RN-TD15 — Oasis sin tipo inferido van a "sin_clasificar" (v3).**
Un oasis con `tipo = None` (sin ningun animal observado con `present > 0`, p.ej. solo
reportes de derrota) no puede clasificarse. Todos sus gaps se agrupan bajo `"sin_clasificar"`.

**RN-TD16 — Oasis de baja confianza se incluyen en su seccion de tipo (v3).**
Un oasis con `confidence = "low"` (< 3 bursts con `present > 0`) se incluye en la seccion
correspondiente a su tipo inferido, no en `"sin_clasificar"`. El campo
`n_oasis_low_confidence` de la seccion informa cuantos oasis tienen baja confianza, para
que el frontend pueda mostrar un disclaimer. Excluir oasis de baja confianza ocultaria datos
reales; incluirlos con marca de confianza es mas honesto.

**RN-TD17 — Cinco secciones fijas, siempre presentes (v3).**
La respuesta siempre contiene exactamente 5 secciones en orden fijo:
`hierro`, `arcilla`, `madera`, `cereal`, `sin_clasificar`.
Una seccion sin datos se devuelve con `n_oasis=0`, `n_oasis_low_confidence=0`,
`n_reports_in_section=0`, `animals=[]`. Nunca se omite una seccion del array.

**RN-TD18 — Etiqueta "Barro" para la clave canonica "arcilla" (v3).**
La clave interna del catalogo es `"arcilla"` (de `OASIS_TYPE_SETS`). La etiqueta de
presentacion es `"Barro"` (terminologia del usuario). Nunca se cambia la clave interna;
solo el `oasis_type_label`. Esto se resuelve con un dict de labels en el adapter:
`{"hierro": "Hierro", "arcilla": "Barro", "madera": "Madera", "cereal": "Cereal", None: "Sin clasificar"}`.

**RN-TD19 — n_reports_in_window es la suma de todas las secciones (v3).**
`n_reports_in_window` (campo raiz) = suma de `n_reports_in_section` de las 5 secciones.
Mantiene el mismo significado semantico de v2 (numero total de gaps en la ventana).

## 5. Flujo principal y flujos alternativos

### Flujo principal (v3)
1. Cliente envía `GET /attack-reports/stats/oasis/temporal-distribution?interval_minutes=240`
   con cabecera `Accept-Language: es`.
2. FastAPI valida `interval_minutes` (entero, tipo). Si ausente → usa default `240`.
3. El router valida manualmente que `interval_minutes` ∈ `{6,7,10,15,30,60,120,180,240,300}`
   → `400` si no está.
4. El router resuelve `lang` con `get_language`.
5. El router llama a `port.get_animal_temporal_distribution(interval_minutes=240, lang="es")`.
6. **[NUEVO v3]** El adapter ejecuta la query de composicion por oasis (`present > 0`) para
   construir el mapa de tipos: `{(cx, cy): (tipo, confidence)}` usando `infer_type`.
7. El adapter ejecuta la query LAG en SQLite para obtener todos los gaps validos con sus
   datos de animal y las coordenadas del oasis.
8. El adapter filtra en Python: descarta `gap_seconds IS NULL`, `gap_seconds <= 0` y
   `gap_seconds < 360` (< 6 min).
9. El adapter filtra los gaps que caen en la ventana `[240*60, 300*60)` (en segundos).
10. **[NUEVO v3]** El adapter etiqueta cada gap con el tipo de su oasis usando el mapa del paso 6.
    Gaps de oasis sin tipo en el mapa (sin ningun `present > 0`) → tipo `None` → "sin_clasificar".
11. **[NUEVO v3]** El adapter agrupa los gaps por tipo, luego por animal_ordinal dentro de cada
    tipo, y calcula `n_oasis`, `n_oasis_low_confidence`, `n_reports_in_section`, `n_total`,
    `n_valid`, `avg_present`, `mode_present` por (tipo, animal).
12. El adapter resuelve nombres localizados via `translation_port`.
13. **[NUEVO v3]** El adapter construye el array `types` con las 5 secciones fijas en orden
    `hierro → arcilla → madera → cereal → sin_clasificar`. Secciones vacias incluidas.
14. El adapter construye la respuesta raiz con `n_reports_in_window` (suma de secciones) y `types`.
15. El router serializa y responde `200`.

### Flujos alternativos
- **`interval_minutes` fuera del set permitido** → `400` antes de llegar al adapter.
- **`interval_minutes` ausente** → `200` con default `240`.
- **`Accept-Language` ausente o idioma no soportado** → `400` (comportamiento estandar de
  `get_language`).
- **Ningún gap en la ventana solicitada** → adapter devuelve respuesta con `n_reports_in_window: 0`
  y las 5 secciones vacias (`n_reports_in_section: 0`, `animals: []`) → router responde `200`.
- **BD vacia o todos los oasis sin `present > 0`** → mapa de tipos vacio → todos los gaps
  van a "sin_clasificar" o no hay gaps → las 5 secciones estan vacias → `200`.
- **Error inesperado de BD** → capturado en el router, responde `500` con detail generico
  (sin stack trace).

## 6. Edge cases

| # | Edge case | Tratamiento |
|---|-----------|-------------|
| EC-TD01 | Primer ataque a un oasis (sin previo) | Gap = NULL → descartado |
| EC-TD02 | `present = NULL` (derrota) | Cuenta en `n_total` del animal, excluido de `n_valid`, `avg_present`, `mode_present` |
| EC-TD03 | Todos los reportes de la ventana para un animal son derrotas (`n_valid = 0`) | `avg_present = null`, `mode_present = []`, `n_total > 0` |
| EC-TD04 | Empate en la moda (ej. present=[2,2,3,3]) | `mode_present = [2, 3]` (todos los empatados, ASC) |
| EC-TD05 | Animal sin ningún reporte en la ventana solicitada | El animal no aparece en `animals[]` |
| EC-TD06 | Ningún animal tiene reportes en la ventana | `n_reports_in_window=0`, `animals=[]` |
| EC-TD07 | Gap negativo o cero (relojes inconsistentes en la BD) | `gap_seconds <= 0` → descartado silenciosamente |
| EC-TD08 | Gap < 6 min (< 360s), p.ej. 300s | Descartado silenciosamente; no pertenece a ningún bin |
| EC-TD09 | Gap exactamente en el límite inferior del bin (ej. gap=7*60=420s con `interval_minutes=7`) | Pertenece al bin 7 `[420, 600)` — frontera inclusiva |
| EC-TD10 | Gap de 9 min (540s) con `interval_minutes=7` — ruido de lag | Cae en `[420, 600)` → bin 7. No salta al bin 10. Esto es la robustez de Opción B |
| EC-TD11 | Gap de exactamente 10 min (600s) | Cae en bin 10 `[600, 900)`, no en bin 7. La frontera superior es exclusiva |
| EC-TD12 | Gap de 5 min (300s, exactamente < 6 min) | Descartado. No entra en ningún bin |
| EC-TD13 | Gap de 86400s (24h) con `interval_minutes=240` | `86400 = 1440*60`. La ventana 240 es `[14400, 18000)`. `86400 >= 18000` → no cae en 240. Cae en la ventana 300 `[18000, ∞)`. |
| EC-TD14 | Gap de 86400s con `interval_minutes=300` | `86400 >= 18000` → pertenece al bin 300 abierto. Se cuenta |
| EC-TD15 | BD vacía | `200` con `n_reports_in_window=0`, `animals: []` |
| EC-TD16 | Idioma sin nombre para un ordinal en el catálogo | Fallback a `animal_name` de la BD |
| EC-TD17 | Oasis con un solo reporte (no puede generar gap) | El reporte se descarta; el oasis no aporta datos |
| EC-TD18 | `interval_minutes` ausente | `200` con default `240` |
| EC-TD19 | `interval_minutes=45` (valor entero pero fuera del set) | `400` con detail que lista los valores válidos |
| EC-TD20 | Oasis con solo reportes de derrota (`present=NULL` en todos sus reportes) | `tipo=None` → gap va a "sin_clasificar". No tiene `present>0` → `infer_type` recibe `observed=set()` → devuelve `(None, None)` |
| EC-TD21 | Oasis con 1 o 2 bursts observados (`burst_count` total < 3) | Tipo inferido con `confidence="low"`. Va a su seccion de tipo. Se cuenta en `n_oasis_low_confidence` de esa seccion |
| EC-TD22 | Todos los oasis de la BD son del mismo tipo (p.ej. todos hierro) | Las 4 secciones restantes devuelven `n_oasis=0`, `n_reports_in_section=0`, `animals=[]`. No se omiten del array `types` |
| EC-TD23 | BD con oasis de 3 tipos distintos; usuario pide `interval_minutes=6` y ninguno tiene gaps en esa ventana | `n_reports_in_window=0`, las 5 secciones vacias. `200` |
| EC-TD24 | Oasis con animales muy variados (ej. `{1,2,4,5,6,7}`) que Jaccard clasifica como cereal | Va a la seccion "cereal". La limitacion esta documentada (set universal). No es un bug |
| EC-TD25 | Dos oasis con tipo inferido "arcilla"; ambos tienen gaps en la ventana pero distintos animales observados | La seccion "arcilla" agrega los gaps de AMBOS oasis. `n_oasis=2`. Los animales se calculan sobre el conjunto unido de gaps de esos 2 oasis |
| EC-TD26 | Oasis con `presente>0` en la query de composicion pero ninguno de sus gaps cae en la ventana solicitada | El oasis tiene tipo inferido, pero como no aporta gaps a la ventana, no incrementa `n_oasis` ni `n_reports_in_section` de ninguna seccion |
| EC-TD27 | Empate de Jaccard entre dos tipos (mismo score) | `infer_type` resuelve por menor cardinal de set y luego alfabetico (comportamiento ya implementado). Determinista |

## 7. Modelo de datos / cambios de esquema

**No hay cambios de esquema.** Se reutilizan las tablas existentes:

```sql
-- Tablas reutilizadas (sin modificacion)
attack_reports          -- cabecera: coord_x_dest, coord_y_dest, attacked_at, id
attack_report_animals   -- filas de animal: report_id → animal_ordinal, animal_name, present
```

El calculo es 100% derivado en tiempo de consulta. En v3 se usan DOS queries sobre las mismas
tablas:

1. **Query de composicion por oasis** (para inferir tipos): `GROUP BY coord_x_dest, coord_y_dest,
   animal_ordinal WHERE present > 0` — misma que usa EP-SPAWN. Devuelve `animal_ordinal` y
   `burst_count` por oasis. A partir de esta se construye el mapa de tipos con `infer_type`.

2. **Query de gaps LAG** (para calcular estadisticas en la ventana): la misma query de v2,
   ampliada para devolver tambien `coord_x_dest` y `coord_y_dest` (necesarios para cruzar
   con el mapa de tipos del paso anterior).

No se necesita columna nueva ni indice adicional para v3.

## 8. Contratos de API / interfaces

<!-- PENDIENTE VALIDACION POR desarrollador-apis (v3) -->
<!-- La v1 fue validada y declarada CORRECTA. Este contrato sustituye el de v2. -->
<!-- Requiere gate de desarrollador-apis antes de implementar cliente HTTP (v3). -->

### EP-TD — GET /attack-reports/stats/oasis/temporal-distribution

> **DECISIÓN DE REUTILIZACIÓN:** Endpoint existente (implementado en v1). Se MODIFICA
> para sustituir `bucket_hours` por `interval_minutes` y cambiar el schema de respuesta.
> No se crea un endpoint nuevo.

**Método y ruta:** `GET /attack-reports/stats/oasis/temporal-distribution`

**Query parameters:**

| Parámetro | Tipo | Obligatorio | Default | Validación |
|-----------|------|-------------|---------|-----------|
| `interval_minutes` | `integer` | No | `240` | Valores exactos: `6\|7\|10\|15\|30\|60\|120\|180\|240\|300`. Otro entero → `400`. No entero → `422`. Ausente → `200` con default `240`. |

**Headers de request:**

| Header | Obligatorio | Descripción |
|--------|-------------|-------------|
| `Accept-Language` | Sí | Código de idioma (25 soportados en `SUPPORTED_LANGUAGES`). Ausente o código no soportado → `400`. |

**Response 200 — exito (v3):**

```json
{
  "interval_minutes": 240,
  "interval_label": "4h",
  "window": {
    "lower_min": 240,
    "upper_min": 300,
    "is_open": false
  },
  "n_reports_in_window": 42,
  "types": [
    {
      "oasis_type": "hierro",
      "oasis_type_label": "Hierro",
      "n_oasis": 3,
      "n_oasis_low_confidence": 1,
      "n_reports_in_section": 18,
      "animals": [
        {
          "animal_ordinal": 1,
          "animal_name": "Rata",
          "icon_url": "/static/icons/nature_1.png",
          "avg_present": 2.50,
          "mode_present": [2],
          "n_total": 18,
          "n_valid": 15
        },
        {
          "animal_ordinal": 4,
          "animal_name": "Murcielago",
          "icon_url": "/static/icons/nature_4.png",
          "avg_present": 1.20,
          "mode_present": [1],
          "n_total": 12,
          "n_valid": 10
        }
      ]
    },
    {
      "oasis_type": "arcilla",
      "oasis_type_label": "Barro",
      "n_oasis": 2,
      "n_oasis_low_confidence": 0,
      "n_reports_in_section": 14,
      "animals": [...]
    },
    {
      "oasis_type": "madera",
      "oasis_type_label": "Madera",
      "n_oasis": 4,
      "n_oasis_low_confidence": 2,
      "n_reports_in_section": 7,
      "animals": [...]
    },
    {
      "oasis_type": "cereal",
      "oasis_type_label": "Cereal",
      "n_oasis": 1,
      "n_oasis_low_confidence": 0,
      "n_reports_in_section": 3,
      "animals": [...]
    },
    {
      "oasis_type": "sin_clasificar",
      "oasis_type_label": "Sin clasificar",
      "n_oasis": 1,
      "n_oasis_low_confidence": 0,
      "n_reports_in_section": 0,
      "animals": []
    }
  ]
}
```

**Ejemplo — ventana vacia (frecuencia sin datos):**

```json
{
  "interval_minutes": 6,
  "interval_label": "6 min",
  "window": {
    "lower_min": 6,
    "upper_min": 7,
    "is_open": false
  },
  "n_reports_in_window": 0,
  "types": [
    {"oasis_type": "hierro",       "oasis_type_label": "Hierro",          "n_oasis": 0, "n_oasis_low_confidence": 0, "n_reports_in_section": 0, "animals": []},
    {"oasis_type": "arcilla",      "oasis_type_label": "Barro",           "n_oasis": 0, "n_oasis_low_confidence": 0, "n_reports_in_section": 0, "animals": []},
    {"oasis_type": "madera",       "oasis_type_label": "Madera",          "n_oasis": 0, "n_oasis_low_confidence": 0, "n_reports_in_section": 0, "animals": []},
    {"oasis_type": "cereal",       "oasis_type_label": "Cereal",          "n_oasis": 0, "n_oasis_low_confidence": 0, "n_reports_in_section": 0, "animals": []},
    {"oasis_type": "sin_clasificar","oasis_type_label": "Sin clasificar", "n_oasis": 0, "n_oasis_low_confidence": 0, "n_reports_in_section": 0, "animals": []}
  ]
}
```

**Ejemplo — bin abierto (`interval_minutes=300`):**

```json
{
  "interval_minutes": 300,
  "interval_label": "5h+",
  "window": {
    "lower_min": 300,
    "upper_min": null,
    "is_open": true
  },
  "n_reports_in_window": 5,
  "types": [...]
}
```

**Campos del response (v3):**

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `interval_minutes` | `integer` | Frecuencia solicitada (echo del parametro; `240` si se uso el default). |
| `interval_label` | `string` | Etiqueta legible. Valores: `"6 min"`, `"7 min"`, `"10 min"`, `"15 min"`, `"30 min"`, `"1h"`, `"2h"`, `"3h"`, `"4h"`, `"5h+"`. El bin `300` lleva `"5h+"`. |
| `window.lower_min` | `integer` | Limite inferior de la ventana en minutos (inclusive). |
| `window.upper_min` | `integer\|null` | Limite superior en minutos (exclusive). `null` para `interval_minutes=300`. |
| `window.is_open` | `boolean` | `true` solo para `interval_minutes=300`. |
| `n_reports_in_window` | `integer` | Numero total de gaps en la ventana. Suma de `n_reports_in_section` de las 5 secciones. `0` si ninguna seccion tiene datos. |
| `types` | `array[5]` | Siempre exactamente 5 elementos. Orden fijo: hierro, arcilla, madera, cereal, sin_clasificar. |
| `types[].oasis_type` | `string` | Clave canonica: `"hierro"`, `"arcilla"`, `"madera"`, `"cereal"`, `"sin_clasificar"`. |
| `types[].oasis_type_label` | `string` | Etiqueta de presentacion fija: `"Hierro"`, `"Barro"`, `"Madera"`, `"Cereal"`, `"Sin clasificar"`. |
| `types[].n_oasis` | `integer` | Numero de oasis distintos de este tipo con al menos un gap en la ventana. `0` si seccion vacia. |
| `types[].n_oasis_low_confidence` | `integer` | Cuantos de esos oasis tienen `confidence="low"`. `0` si ninguno o seccion vacia. |
| `types[].n_reports_in_section` | `integer` | Numero de gaps (report_ids distintos) de oasis de este tipo en la ventana. `0` si seccion vacia. |
| `types[].animals` | `array` | Lista de animales observados en esta seccion. `[]` si `n_reports_in_section=0`. Orden: `animal_ordinal ASC`. |
| `types[].animals[].animal_ordinal` | `integer` | Ordinal del animal (1-10, catalogo NATURE). |
| `types[].animals[].animal_name` | `string` | Nombre localizado del animal (via `Accept-Language`). |
| `types[].animals[].icon_url` | `string` | `/static/icons/nature_{ordinal}.png` |
| `types[].animals[].avg_present` | `number\|null` | Media de `present` redondeada a 2 decimales. `null` si `n_valid=0`. |
| `types[].animals[].mode_present` | `array[integer]` | Moda(s) de `present`. `[]` si `n_valid=0`. Empates: todos ASC. |
| `types[].animals[].n_total` | `integer` | Gaps de este tipo donde aparece este animal (incluye derrotas con `present=null`). |
| `types[].animals[].n_valid` | `integer` | Gaps con `present IS NOT NULL` en esta seccion para este animal. |

**Tabla de etiquetas por valor de `interval_minutes`:**

| `interval_minutes` | `interval_label` | `window.lower_min` | `window.upper_min` | `window.is_open` |
|--------------------|------------------|--------------------|--------------------|------------------|
| `6`   | `"6 min"` | 6   | 7   | false |
| `7`   | `"7 min"` | 7   | 10  | false |
| `10`  | `"10 min"`| 10  | 15  | false |
| `15`  | `"15 min"`| 15  | 30  | false |
| `30`  | `"30 min"`| 30  | 60  | false |
| `60`  | `"1h"`    | 60  | 120 | false |
| `120` | `"2h"`    | 120 | 180 | false |
| `180` | `"3h"`    | 180 | 240 | false |
| `240` | `"4h"`    | 240 | 300 | false |
| `300` | `"5h+"`   | 300 | null| true  |

**Errores:**

| Código | Condición |
|--------|-----------|
| `400` | `interval_minutes` no está en `{6,7,10,15,30,60,120,180,240,300}`. Detail: `"interval_minutes debe ser uno de: 6, 7, 10, 15, 30, 60, 120, 180, 240, 300. Recibido: <valor>"`. |
| `400` | `Accept-Language` ausente. Detail estándar de `get_language`. |
| `400` | `Accept-Language` con código no soportado (ej. `zh`). |
| `422` | `interval_minutes` no es entero (FastAPI validation automática). |
| `500` | Error inesperado de BD. Detail genérico: `"Error interno al calcular la distribución temporal de animales."` |

**Posición en el router (orden de declaración):**

El endpoint debe declararse ANTES de `EP-06` (`/stats/oasis` sin subruta) para que FastAPI
lo resuelva como literal. Posición relativa con `comparison` y `spawn-composition`: sin
colisión (paths distintos). Orden recomendado para legibilidad:
`comparison` → `spawn-composition` → `temporal-distribution` → EP-06.

**Relación con otros endpoints:**
- Reutiliza el mismo patrón LAG de EP-09 (`get_global_oasis_stats`) con
  `PARTITION BY coord_x_dest, coord_y_dest`.
- Añade `Accept-Language` + `translation_port`, a diferencia de EP-09 que no los usa.
- No hay solapamiento funcional con EP-09, EP-10 ni EP-SPAWN.

## 9. Flujo lógico paso a paso

```
# Constantes de modulo (sin cambio desde v2)
VALID_INTERVALS = [6, 7, 10, 15, 30, 60, 120, 180, 240, 300]

WINDOWS = {
    6: (6, 7), 7: (7, 10), 10: (10, 15), 15: (15, 30), 30: (30, 60),
    60: (60, 120), 120: (120, 180), 180: (180, 240), 240: (240, 300), 300: (300, None),
}

LABELS = {
    6: "6 min", 7: "7 min", 10: "10 min", 15: "15 min", 30: "30 min",
    60: "1h", 120: "2h", 180: "3h", 240: "4h", 300: "5h+",
}

# Labels de presentacion para cada tipo (v3)
TYPE_LABELS = {
    "hierro": "Hierro", "arcilla": "Barro", "madera": "Madera",
    "cereal": "Cereal", None: "Sin clasificar",
}

# Orden fijo de secciones (v3): None = sin_clasificar al final
TYPE_ORDER = ["hierro", "arcilla", "madera", "cereal", None]

FUNCION get_animal_temporal_distribution(interval_minutes: int, lang: str) -> dict:

    lower_min, upper_min = WINDOWS[interval_minutes]
    lower_sec = lower_min * 60
    upper_sec = upper_min * 60 if upper_min is not None else None
    is_open = (upper_sec is None)

    # ─── Paso 1 (NUEVO v3): Inferir tipo por oasis ────────────────────────────
    # Misma query que usa EP-SPAWN para la composicion (solo present > 0).
    comp_sql = """
        SELECT r.coord_x_dest, r.coord_y_dest, a.animal_ordinal, COUNT(*) AS burst_count
        FROM attack_report_animals a
        JOIN attack_reports r ON r.id = a.report_id
        WHERE a.present > 0
        GROUP BY r.coord_x_dest, r.coord_y_dest, a.animal_ordinal
    """
    # Construir comp_by_oasis: {(cx, cy): [{"animal_ordinal": int, "burst_count": int}]}
    comp_by_oasis = defaultdict(list)
    for row in comp_rows:  # comp_rows = resultado de comp_sql
        comp_by_oasis[(row["coord_x_dest"], row["coord_y_dest"])].append({
            "animal_ordinal": row["animal_ordinal"],
            "burst_count":    row["burst_count"],
        })

    # Mapa de tipo e confidence por oasis: {(cx, cy): (tipo, confidence)}
    # infer_type = _infer_type elevada a funcion publica (RN-TD14)
    oasis_type_map = {}
    for (cx, cy), comp_list in comp_by_oasis.items():
        observed = {c["animal_ordinal"] for c in comp_list}
        tipo, confidence = infer_type(observed, comp_list)
        oasis_type_map[(cx, cy)] = (tipo, confidence)
    # Oasis con present=0 en todos sus reportes (solo derrotas) no aparecen en comp_by_oasis
    # → no estan en oasis_type_map → tipo sera None cuando se cruce con los gaps (EC-TD20).

    # ─── Paso 2: Calcular gaps con LAG (igual que v2, ampliado con coords) ────
    gap_sql = """
        SELECT
            r.id            AS report_id,
            r.coord_x_dest,
            r.coord_y_dest,
            a.animal_ordinal,
            a.animal_name,
            a.present,
            CAST(
                (UNIXEPOCH(r.attacked_at) -
                 UNIXEPOCH(LAG(r.attacked_at) OVER w)) AS INTEGER
            ) AS gap_seconds
        FROM attack_report_animals a
        JOIN attack_reports r ON r.id = a.report_id
        WINDOW w AS (
            PARTITION BY r.coord_x_dest, r.coord_y_dest
            ORDER BY r.attacked_at
        )
        ORDER BY a.animal_ordinal, r.attacked_at
    """

    # ─── Paso 3: Filtrar gaps invalidos (igual que v2) ────────────────────────
    valid_rows = [
        row for row in raw_rows
        if row["gap_seconds"] is not None
        and row["gap_seconds"] > 0
        and row["gap_seconds"] >= 360
    ]

    # ─── Paso 4: Filtrar por ventana (igual que v2) ───────────────────────────
    if is_open:
        window_rows = [r for r in valid_rows if r["gap_seconds"] >= lower_sec]
    else:
        window_rows = [r for r in valid_rows if lower_sec <= r["gap_seconds"] < upper_sec]

    # ─── Paso 5 (NUEVO v3): Etiquetar cada gap con el tipo de su oasis ────────
    # Si el oasis no esta en oasis_type_map → tipo=None → "sin_clasificar".
    def get_tipo(row):
        return oasis_type_map.get((row["coord_x_dest"], row["coord_y_dest"]), (None, None))[0]

    def get_confidence(row):
        return oasis_type_map.get((row["coord_x_dest"], row["coord_y_dest"]), (None, None))[1]

    # ─── Paso 6 (NUEVO v3): Agrupar por (tipo, animal_ordinal) ───────────────
    # Estructuras auxiliares:
    # - type_oasis_ids[tipo]: set de (cx,cy) con al menos un gap en la ventana
    # - type_oasis_low[tipo]: set de (cx,cy) con confidence="low"
    # - type_groups[tipo][ordinal]: {"n_total", "valids", "name_raw"}
    # - type_report_ids[tipo]: set de report_ids distintos en la seccion
    type_oasis_ids    = defaultdict(set)
    type_oasis_low    = defaultdict(set)
    type_groups       = defaultdict(lambda: defaultdict(lambda: {"n_total": 0, "valids": [], "name_raw": ""}))
    type_report_ids   = defaultdict(set)

    for row in window_rows:
        tipo = get_tipo(row)
        cx, cy = row["coord_x_dest"], row["coord_y_dest"]
        confidence = get_confidence(row)
        type_oasis_ids[tipo].add((cx, cy))
        if confidence == "low":
            type_oasis_low[tipo].add((cx, cy))
        type_report_ids[tipo].add(row["report_id"])
        ordinal = row["animal_ordinal"]
        type_groups[tipo][ordinal]["n_total"] += 1
        if row["present"] is not None:
            type_groups[tipo][ordinal]["valids"].append(row["present"])
        if not type_groups[tipo][ordinal]["name_raw"]:
            type_groups[tipo][ordinal]["name_raw"] = row["animal_name"]

    # ─── Paso 7: Resolver nombres localizados (igual que v2) ──────────────────
    names_by_ordinal = {
        entry["ordinal"]: entry["nombre"]
        for entry in translation_port.get_troop_names_by_tribe(Tribe.NATURE, lang)
    }

    # ─── Paso 8: Helper para construir la lista de animales de una seccion ────
    def build_animals(tipo):
        result = []
        for ordinal in sorted(type_groups[tipo].keys()):
            data = type_groups[tipo][ordinal]
            n_valid = len(data["valids"])
            avg_present = round(sum(data["valids"]) / n_valid, 2) if n_valid > 0 else None
            if n_valid > 0:
                counter = Counter(data["valids"])
                max_count = max(counter.values())
                mode_present = sorted(k for k, v in counter.items() if v == max_count)
            else:
                mode_present = []
            result.append({
                "animal_ordinal": ordinal,
                "animal_name":    names_by_ordinal.get(ordinal, data["name_raw"]),
                "icon_url":       f"/static/icons/nature_{ordinal}.png",
                "avg_present":    avg_present,
                "mode_present":   mode_present,
                "n_total":        data["n_total"],
                "n_valid":        n_valid,
            })
        return result

    # ─── Paso 9 (NUEVO v3): Construir array types con las 5 secciones ─────────
    types = []
    for tipo in TYPE_ORDER:  # hierro, arcilla, madera, cereal, None
        oasis_type_key = tipo if tipo is not None else "sin_clasificar"
        types.append({
            "oasis_type":              oasis_type_key,
            "oasis_type_label":        TYPE_LABELS[tipo],
            "n_oasis":                 len(type_oasis_ids[tipo]),
            "n_oasis_low_confidence":  len(type_oasis_low[tipo]),
            "n_reports_in_section":    len(type_report_ids[tipo]),
            "animals":                 build_animals(tipo),
        })

    # ─── Paso 10: Construir respuesta raiz ────────────────────────────────────
    n_reports_in_window = sum(len(type_report_ids[t]) for t in TYPE_ORDER)

    return {
        "interval_minutes": interval_minutes,
        "interval_label":   LABELS[interval_minutes],
        "window": {
            "lower_min": lower_min,
            "upper_min": upper_min,
            "is_open":   is_open,
        },
        "n_reports_in_window": n_reports_in_window,
        "types": types,
    }
```

**Nota sobre las dos queries en paralelo:** la query de composicion (Paso 1) y la query LAG
(Paso 2) pueden ejecutarse de forma secuencial o con `asyncio.gather` si el conector SQLite
lo permite. Para el volumen esperado (<10.000 reportes), la diferencia es negligible. Lo que
no debe hacerse es ejecutar la query de composicion dentro del loop de gaps (N+1).

**Nota sobre `None` como clave de dict:** Python permite `None` como clave de dict. El
`defaultdict` con clave `None` funciona correctamente para agrupar oasis sin tipo inferido.
El implementador puede usar `None` o la string `"sin_clasificar"` como clave interna; lo
importante es que en el output final `oasis_type` sea `"sin_clasificar"` (string).

## 10. Validaciones y reglas

| Capa | Validación | Respuesta ante fallo |
|------|-----------|----------------------|
| Router (FastAPI) | `interval_minutes` es `integer` (tipo) | `422` automático |
| Router (manual) | `interval_minutes` ∈ `{6,7,10,15,30,60,120,180,240,300}` | `400` con detail legible que lista los valores válidos |
| Router (manual) | `interval_minutes` ausente → usar default `240` | `200` con `interval_minutes: 240` |
| Router (`get_language`) | `Accept-Language` presente y código soportado | `400` |
| Adapter (Python) | `gap_seconds IS NULL` (primer ataque) | Filtrado silencioso |
| Adapter (Python) | `gap_seconds <= 0` (relojes inconsistentes) | Filtrado silencioso |
| Adapter (Python) | `gap_seconds < 360` (< 6 min) | Filtrado silencioso |
| Adapter (Python) | Gap fuera de la ventana `[lower_sec, upper_sec)` | No se incluye en `window_rows` |
| Adapter (Python) | `present IS NULL` (derrota) | Cuenta en `n_total`, excluido de calculos de `avg`/`mode` |
| Adapter (Python) | Catalogo sin nombre para un ordinal | Fallback a `animal_name` de BD |
| Adapter (Python v3) | Oasis no en `oasis_type_map` (sin `present>0` nunca) | Tipo `None` → seccion "sin_clasificar" |
| Adapter (Python v3) | `confidence="low"` (< 3 bursts) | Incluido en su seccion de tipo; incrementa `n_oasis_low_confidence` |
| Adapter (Python v3) | Oasis con gaps en la ventana pero ausente del mapa de tipos | Se trata como tipo `None` (EC-TD20). No lanza excepcion |

## 11. Seguridad, rendimiento y concurrencia

**Seguridad:**
- `interval_minutes` validado contra whitelist estricta (no arithmetic injection).
- `lang` validado por `get_language` contra `SUPPORTED_LANGUAGES` (sin interpolacion SQL).
- Las queries no aceptan parametros de coordenadas ni de tipo → sin inyeccion SQL.
- No se expone `raw_text` ni datos personales.

**Rendimiento (v3):**
- En v3 se ejecutan DOS queries en vez de una: la query de composicion (Paso 1) y la query
  LAG (Paso 2). Para el volumen esperado (<10.000 reportes y pocos oasis distintos), el
  coste adicional es negligible.
- La inferencia de tipo se hace en Python en O(|oasis| x |tipos|) = O(n x 4) — despreciable.
- El agrupamiento por (tipo, animal) es O(|window_rows|) en Python — adecuado.
- Si en el futuro la tabla crece (>100.000 filas), considerar un indice parcial en
  `(coord_x_dest, coord_y_dest, attacked_at)` sobre `attack_reports`. No es necesario en v3.
- Los nombres localizados se cargan en memoria una sola vez por request (lista de 10 animales).

**Concurrencia:**
- SQLite en modo WAL: la query de lectura es compatible con escrituras concurrentes.
- Sin estado mutable en el adapter para este endpoint.

## 12. Plan de pruebas

### Casos felices (v3)

| ID | Caso | Verificacion |
|----|------|-------------|
| T-TD01 | `interval_minutes=240` (default), lang=`es`, BD con reportes de oasis hierro con gaps en `[14400, 18000)` | 200, `n_reports_in_window>0`, `types` tiene 5 elementos, seccion "hierro" tiene `n_reports_in_section>0` y `animals` con rat/spider/murciélago ordenados por `animal_ordinal ASC` |
| T-TD02 | `interval_minutes=60`, lang=`en` | 200, `interval_label="1h"`, `window={lower_min:60, upper_min:120}` |
| T-TD03 | `interval_minutes=300` | 200, `interval_label="5h+"`, `window.is_open=true`, `window.upper_min=null` |
| T-TD04 | BD con reportes de derrota (`present=null`) en la ventana para un oasis | `n_total > n_valid` para el animal en su seccion, `avg_present=null` si todos son derrota, `mode_present=[]` |
| T-TD05 | Empate en moda (ej. present=[2,2,3,3]) para un animal en una seccion | `mode_present=[2,3]` |
| T-TD06 | Animal con un unico valor de `present` | `mode_present=[valor]` |
| T-TD07 | BD vacia | 200, `n_reports_in_window=0`, `types` con 5 secciones todas con `n_reports_in_section=0` y `animals=[]` |
| T-TD08 | BD con exactamente 1 reporte por oasis (sin gaps) | 200, `n_reports_in_window=0`, 5 secciones vacias |
| T-TD09 | lang=`it` (idioma italiano) | Nombres en italiano dentro de `types[].animals[].animal_name` |
| T-TD10 | Ordinal sin nombre en catalogo para el idioma | `animal_name` = valor de la BD |
| T-TD11 | `interval_minutes` ausente | 200 con `interval_minutes=240` (default) |
| T-TD28 | BD con oasis de tipo "hierro" (animales {1,2,4}) y "madera" (animales {5,6,7}); gaps de ambos en ventana | `types` tiene 5 elementos; seccion "hierro" y "madera" con datos; secciones "arcilla", "cereal", "sin_clasificar" vacias (`n_reports_in_section=0`) |
| T-TD29 | Oasis con solo reportes de derrota (todos `present=NULL`) y con gap en ventana | Ese oasis no esta en `oasis_type_map` → su gap va a seccion "sin_clasificar". `types[4].n_reports_in_section >= 1` |
| T-TD30 | Oasis con 1 burst observable (`burst_count_total=1`, confidence="low") y gap en ventana | Oasis incluido en su seccion de tipo. `n_oasis_low_confidence=1` en esa seccion |
| T-TD31 | Oasis con 3 o mas bursts (`confidence="medium"`) | `n_oasis_low_confidence=0` para ese oasis en su seccion |
| T-TD32 | Dos oasis del mismo tipo con gaps en la ventana | `n_oasis=2` en esa seccion; `animals` agrega los gaps de ambos |
| T-TD33 | `n_reports_in_window` == suma de `n_reports_in_section` de las 5 secciones | Invariante de integridad |
| T-TD34 | Secciones en orden fijo: hierro[0], arcilla[1], madera[2], cereal[3], sin_clasificar[4] | `types[0].oasis_type="hierro"`, `types[1].oasis_type="arcilla"`, ..., `types[4].oasis_type="sin_clasificar"` |
| T-TD35 | `oasis_type_label` de arcilla es "Barro" (no "Arcilla") | `types[1].oasis_type_label=="Barro"` |

### Edge cases — binning de frontera (críticos para Opción B)

| ID | Caso | Verificación |
|----|------|-------------|
| T-TD12 | Gap exactamente `7*60=420s` con `interval_minutes=7` | Cae en bin 7 `[420,600)` — frontera inclusiva inferior. `n_reports_in_window>=1` |
| T-TD13 | Gap de `9*60=540s` con `interval_minutes=7` | Cae en bin 7 `[420,600)`. No salta al bin 10. `n_reports_in_window>=1` |
| T-TD14 | Gap de `10*60=600s` con `interval_minutes=7` | Cae en bin 10 `[600,900)`. NO en bin 7. Frontera superior exclusiva |
| T-TD15 | Gap de `5*60=300s` (< 6 min) | Descartado. Con `interval_minutes=6` → `n_reports_in_window=0` |
| T-TD16 | Gap de `86400s` (24h) con `interval_minutes=240` | `86400 >= 18000` → no cae en ventana 240. Con `interval_minutes=300` sí cuenta |
| T-TD17 | Gap de `86400s` con `interval_minutes=300` | `86400 >= 18000` → `n_reports_in_window>=1` |
| T-TD18 | Gap exactamente en límite superior: `upper_min * 60` exacto | No pertenece al bin. Pertenece al bin siguiente |
| T-TD19 | Gap de `0s` (relojes iguales) | Descartado. No aparece en ninguna ventana |

### Edge cases y errores de validación

| ID | Caso | Verificación |
|----|------|-------------|
| T-TD20 | `interval_minutes=45` (entero pero fuera del set) | 400, detail menciona los 10 valores válidos |
| T-TD21 | `interval_minutes=0` | 400 |
| T-TD22 | `interval_minutes=301` | 400 |
| T-TD23 | `interval_minutes` no entero (ej. `"cuatro"`) | 422 (FastAPI) |
| T-TD24 | `Accept-Language` ausente | 400 |
| T-TD25 | `Accept-Language: zh` (no soportado) | 400 |
| T-TD26 | Dos oasis con el mismo animal; gaps de oasis A no cruzan a oasis B | Verificar que el LAG usa PARTITION BY coords correctamente |
| T-TD27 | Ventana solicitada sin datos (frecuencia inusual, ej. `interval_minutes=6` con BD típica) | 200, `n_reports_in_window=0`, `animals=[]` |

## 13. Riesgos y trade-offs

**Trade-off: Opción B (umbral inferior) vs. vecino-más-cercano.**
Se eligió **umbral inferior** (Opción B) porque:
- Es monótono: un gap `g` pertenece al bin `F` si y solo si `F ≤ g/60 < F_next`. No hay
  ambigüedad ni zonas de incertidumbre.
- Es robusto al ruido de lag: un timer configurado a 7 min que tarda 9 min por latencia
  sigue en el bin 7 (`[7, 10)`), no salta al 10.
- El vecino-más-cercano crea zonas de empate exactas (p.ej. gap de 8.5 min, equidistante
  de 7 y 10) que exigen desempate arbitrario.
*Contra:* el usuario debe saber que "bin 7 min" incluye gaps de hasta justo antes de 10 min.
*Mitigación:* la etiqueta en la UI puede mostrar el rango real `"7–10 min"` para claridad.

**Trade-off: conjunto discreto vs. rango continuo.**
El usuario elige una frecuencia discreta del conjunto `{6,7,10,15,30,60,120,180,240,300}`,
que son las cadencias reales del juego (respawn intervals habituales). Esto hace la UI más
intuitiva (selector de opciones, no slider) y evita ventanas huecas con cero datos.

**Trade-off: respuesta de una frecuencia vs. matriz completa.**
En v1 se devolvía la matriz completa de todas las franjas. En v2 se devuelve solo la
frecuencia solicitada. Esto reduce el payload, simplifica el frontend y permite al usuario
explorar interactivamente las frecuencias sin cargar datos que no va a usar.
*Contra:* si el frontend necesita mostrar comparativa entre frecuencias, necesita múltiples
requests. *Mitigación v2:* si se necesita en el futuro, añadir endpoint de resumen
multi-frecuencia o query param `include_all=true`.

**Trade-off: gaps < 6 min descartados vs. incluidos en bin 6.**
Se descartan porque mezclarlos con el bin de 6 min distorsionaría la estadística de esa
cadencia (incluiría anomalías de reloj, duplicados accidentales o datos corruptos).
El bin de 6 min debe representar ataques deliberadamente rápidos, no ruido de sistema.

**Trade-off: solo global vs. por oasis.**
Se eligió **solo global** porque el número de oasis distintos suele ser pequeño y los datos
por oasis son insuficientes para una distribución significativa. El patrón LAG con
`PARTITION BY` es extensible a filtro por coordenadas si se necesita en v3.

**Trade-off: moda en Python vs. en SQL.**
SQLite no tiene `MODE()`. Se eligió **Python** con `Counter`: más legible, maneja empates
elegantemente y tiene rendimiento suficiente para el volumen esperado (<10.000 reportes).

**Riesgo: `attacked_at` como string naive.**
Los timestamps se almacenan como strings ISO 8601 naive. `UNIXEPOCH()` de SQLite sobre
strings naive funciona correctamente siempre que todos estén en el mismo reloj de servidor
(confirmado en specs anteriores). Si en el futuro se mezclan timestamps de distintos
servidores con offsets diferentes, el LAG produciría gaps erróneos. No es un problema porque
el bot solo ataca a un servidor a la vez.

**Riesgo: velocidad de servidor NO se ajusta.**
Los gaps se miden en tiempo real de servidor, no ajustados por la velocidad de servidor
(x1..x10). El endpoint trabaja siempre con tiempo real. Si el usuario juega en un servidor
x3 y ataca cada 2h, su cadencia de farmeo "efectiva" en terminos de juego seria 2h/3=40min,
pero el endpoint la registra como 2h. Esto es correcto: el usuario configura sus timers en
tiempo real, no en tiempo de juego. No hay ajuste que implementar.

**Trade-off v3: incluir oasis de baja confianza en su seccion vs. excluirlos o moverlos a "sin_clasificar".**
Se eligio **incluir con marca** porque ocultar datos con pocos bursts crearia la ilusion de
que ciertos tipos de oasis estan vacios cuando en realidad hay datos (solo insuficientes).
El campo `n_oasis_low_confidence` permite al frontend mostrar un disclaimer sin complicar
la logica del backend.
*Contra:* un oasis con 2 bursts clasificado incorrectamente puede contaminar su seccion.
*Mitigacion:* Jaccard es robusto incluso con pocos datos si los animales observados son
caracteristicos del tipo. La marca de baja confianza es la senal al usuario para tomar
el dato con reservas.

**Trade-off v3: cereal como tipo "borroso" — documentar la limitacion en la UI.**
El set cereal ({1..10}) es universal. Jaccard evita que anule a los demas tipos (ver §REVISION v3),
pero un oasis con composicion verdaderamente variada (muchos tipos de animal) sera clasificado
como cereal correctamente. El frontend debe mostrar junto a la seccion "Cereal" la nota:
"Oasis de cereal — puede contener todos los tipos de animal". No requiere cambio en el backend.

**Trade-off v3: no exponer `confidence` por oasis en el response de EP-TD.**
Se podria exponer la confidence individual de cada oasis dentro de la seccion (p.ej.
`oasis_details: [{cx, cy, confidence}]`). Se descarta por complejidad de UI innecesaria:
`n_oasis_low_confidence` es suficiente para mostrar un disclaimer agregado. Si se necesita
en v4 (p.ej. para un tooltip "3 de los 5 oasis tienen pocos datos"), se anade ese campo.

**Trade-off v3: elevar `_infer_type` vs. duplicar Jaccard.**
Se eleva la funcion porque duplicar el calculo de Jaccard crearia dos implementaciones que
podrian divergir silenciosamente (un bug en una no se detectaria con los tests de la otra).
El costo de la elevacion es minimo (renombrar o mover un metodo). Ver RN-TD14.

## 14. Pasos de implementación ordenados

> **Prerrequisito:** La UI (`AnimalFrequencyPanel.jsx`) NO se implementa aqui.
> La UI pasa de lista plana a secciones por tipo de oasis → requiere **rediseno completo** por
> `disenador-producto` + **nuevo mockup editable** aprobado por el usuario.
> Solo implementar backend + API.
>
> **Gate de APIs:** antes de implementar el cliente HTTP del frontend, `desarrollador-apis`
> debe revisar el contrato v3 de §8 y emitir luz verde. El estado del spec es
> `ready-for-impl` para backend. El cliente JS puede actualizarse en paralelo pero
> no desplegarse sin esa validacion.

**Paso 1 — Elevar `_infer_type` a funcion de modulo**
(`adapters/db/attack_report_sqlite_adapter.py`)

Renombrar `_infer_type` (actualmente privada, ~linea 1953) a `infer_type` (sin guion bajo),
O extraerla a un modulo compartido `adapters/db/_oasis_type_utils.py` e importarla tanto
en el metodo EP-SPAWN como en el metodo EP-TD.

**CRITICO:** NO reimplementar el calculo de Jaccard. Solo mover/renombrar la funcion existente.
Actualizar la llamada interna de EP-SPAWN (`get_oasis_spawn_composition`) para que use el
nuevo nombre/ubicacion. Verificar que los tests de EP-SPAWN siguen pasando tras el cambio.

**Paso 2 — Actualizar el port abstracto**
(`core/ports/attack_report_port.py`)

La firma del metodo `get_animal_temporal_distribution` no cambia externamente, pero actualizar
el docstring para reflejar que el retorno incluye `types` en lugar de `animals`:

```python
@abstractmethod
async def get_animal_temporal_distribution(
    self,
    interval_minutes: int,
    lang: str,
    translation_port,
) -> dict:
    """
    Distribucion empirica de animales por tipo de oasis para una cadencia de farmeo dada (v3).

    interval_minutes: frecuencia en minutos. Valores validos: 6|7|10|15|30|60|120|180|240|300.
    lang: codigo de idioma validado (25 soportados).
    translation_port: puerto de traduccion para resolver nombres de animales.

    Devuelve { interval_minutes, interval_label, window, n_reports_in_window, types }.
    types: lista de 5 secciones fijas (hierro, arcilla, madera, cereal, sin_clasificar).
    200 siempre. Ver spec docs/specs/bd-ataques-oasis-temporal-distribution.md §8 EP-TD (v3).
    """
```

**Paso 3 — Reescribir la implementacion en el adapter**
(`adapters/db/attack_report_sqlite_adapter.py`)

Sustituir el metodo `get_animal_temporal_distribution` siguiendo el pseudocodigo del §9:

1. Anadir constantes de modulo `TYPE_LABELS` y `TYPE_ORDER` (las existentes `_WINDOWS`/`_LABELS`
   no cambian).
2. Ejecutar la query de composicion por oasis (Paso 1 del §9) y construir `oasis_type_map`
   llamando a `infer_type` (elevada en Paso 1 de esta seccion).
3. Ampliar la query LAG (Paso 2 del §9) para devolver tambien `coord_x_dest` y `coord_y_dest`.
4. Mantener los filtros de v2 (NULL, <=0, <360, ventana).
5. Agrupar por `(tipo, animal_ordinal)` usando el `oasis_type_map` (Pasos 5-6 del §9).
6. Construir el array `types` con las 5 secciones fijas (Paso 9 del §9).
7. Devolver el nuevo schema con `types` en lugar de `animals`.

Importante: el bug de v2 ya corregido (`Tribe.NATURE` en mayusculas, clave `"nombre"` del
JsonTranslationAdapter) sigue vigente — no regresar a `Tribe.nature` ni `entry["name"]`.

**Paso 4 — Actualizar el endpoint en el router**
(`adapters/api/routes/attack_reports.py`)

El router no cambia su firma ni validaciones (ya usa `interval_minutes` y la whitelist
de v2). Solo actualizar el comentario de cabecera del endpoint para referenciar v3.
La respuesta es el dict del adapter — sin cambio de logica en el router.

**Paso 5 — Actualizar el metodo cliente en frontend**
(`frontend/src/api/client.js`)

La firma de `getAnimalTemporalDistribution(intervalMinutes=240)` no cambia. Solo cambia el
schema del objeto que devuelve (ahora tiene `types` en lugar de `animals`). Anadir un comentario
en el metodo indicando que la respuesta v3 tiene `types[]` con 5 secciones:

```js
export async function getAnimalTemporalDistribution(intervalMinutes = 240) {
  // v3: response incluye types[5] (hierro/arcilla/madera/cereal/sin_clasificar)
  const params = new URLSearchParams({ interval_minutes: intervalMinutes });
  const res = await fetch(
    `/api/attack-reports/stats/oasis/temporal-distribution?${params}`,
    { headers: buildHeaders() }
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
```

El componente `AnimalFrequencyPanel.jsx` NO se actualiza aqui (solo tiene un stub).
Su implementacion queda bloqueada hasta el rediseno del `disenador-producto` (v3).

**Paso 6 — Actualizar el stub en StatsTab**
(`frontend/src/components/attack-reports/StatsTab.jsx`)

Actualizar el comentario del placeholder `<AnimalFrequencyPanel />`:
`{/* TODO: redisenar UI tras spec de disenador-producto (v3: secciones por tipo de oasis) */}`

**Paso 7 — Reescribir los tests**
(`tests/test_animal_temporal_distribution_api.py`)

Eliminar los 39 tests v2 y escribir los nuevos tests v3 cubriendo los casos del §12:
- Mantener todos los casos de binning de frontera (T-TD12..T-TD18) sin cambio.
- Mantener los casos de validacion de interval_minutes y Accept-Language (T-TD20..T-TD27) sin cambio.
- Sustituir T-TD01..T-TD11 para verificar la estructura `types[5]` en lugar de `animals`.
- Anadir T-TD28..T-TD35 (casos v3 de clasificacion por tipo, confidence, secciones vacias, orden).
- Usar fixtures SQLite en memoria. Cada fixture debe crear oasis con tipos diferenciados
  (p.ej. oasis A con animals {1,2,4} para hierro; oasis B con animals {5,6,7} para madera).

## 15. Criterios de aceptacion

Checklist verificable por el implementador:

**Contrato y parametros (sin cambio desde v2):**
- [ ] `GET /attack-reports/stats/oasis/temporal-distribution?interval_minutes=240` con `Accept-Language: es` responde `200` con `interval_minutes: 240`, `interval_label: "4h"`, `window: {lower_min:240, upper_min:300, is_open:false}`.
- [ ] `interval_minutes` ausente → `200` con `interval_minutes: 240` (default).
- [ ] Frontera inclusiva inferior: gap `7*60=420s` con `interval_minutes=7` → cuenta.
- [ ] Frontera exclusiva superior: gap `10*60=600s` con `interval_minutes=7` → NO cuenta.
- [ ] Robustez al ruido: gap `9*60=540s` con `interval_minutes=7` → cuenta en ventana 7.
- [ ] Gaps < 6 min descartados: gap `5*60=300s` no aparece en ninguna ventana.
- [ ] Gap 86400s con `interval_minutes=300` → cuenta (ventana abierta).
- [ ] Gap 86400s con `interval_minutes=240` → NO cuenta.
- [ ] Gap 0s o negativo → descartado.
- [ ] Primer ataque a oasis → no genera gap.
- [ ] `interval_minutes=45` (fuera del set) → `400` con detail que lista los 10 valores validos.
- [ ] `interval_minutes` no entero → `422`.
- [ ] `Accept-Language` ausente → `400`.
- [ ] `Accept-Language: zh` → `400`.
- [ ] `interval_minutes=300` → `interval_label: "5h+"`, `window.upper_min: null`, `window.is_open: true`.
- [ ] El endpoint esta declarado ANTES de EP-06 (`/stats/oasis`) en el router.

**Estructura v3 — agrupacion por tipo:**
- [ ] La respuesta tiene campo `types` (NO `animals` en el nivel raiz).
- [ ] `types` contiene exactamente 5 elementos.
- [ ] Orden fijo: `types[0].oasis_type="hierro"`, `types[1].oasis_type="arcilla"`, `types[2].oasis_type="madera"`, `types[3].oasis_type="cereal"`, `types[4].oasis_type="sin_clasificar"`.
- [ ] `types[1].oasis_type_label="Barro"` (no "Arcilla").
- [ ] `n_reports_in_window` == suma de `n_reports_in_section` de las 5 secciones.
- [ ] Secciones sin datos: `n_oasis=0`, `n_oasis_low_confidence=0`, `n_reports_in_section=0`, `animals=[]`. No se omiten del array.
- [ ] BD vacia o ventana sin datos → `200` con `n_reports_in_window: 0`, 5 secciones vacias.

**Clasificacion por tipo:**
- [ ] Oasis con animales `{1,2,4}` (rata, arana, murcielago) → clasificado como "hierro".
- [ ] Oasis con animales `{5,6,7}` (jabali, lobo, oso) → clasificado como "madera".
- [ ] Oasis con solo reportes de derrota (todos `present=NULL`) → sus gaps van a "sin_clasificar".
- [ ] Oasis con 1-2 bursts observados (`confidence="low"`) → incluido en su seccion de tipo, no en "sin_clasificar"; `n_oasis_low_confidence` de esa seccion = 1.
- [ ] Oasis con >= 3 bursts (`confidence="medium"`) → `n_oasis_low_confidence` no se incrementa para ese oasis.

**Estadisticas dentro de cada seccion:**
- [ ] `animals` dentro de cada seccion ordenados por `animal_ordinal ASC`.
- [ ] `n_total` incluye gaps con `present=null` (derrotas). `n_valid` los excluye.
- [ ] Si `n_valid=0` para un animal en una seccion → `avg_present: null`, `mode_present: []`.
- [ ] Empate en moda dentro de una seccion → `mode_present` con todos los valores empatados ASC.

**Reutilizacion de logica:**
- [ ] `_infer_type` ha sido elevada a `infer_type` (o equivalente en modulo compartido).
- [ ] EP-SPAWN sigue funcionando tras la elevacion (sus tests existentes en verde).
- [ ] NO hay un tercer calculo de Jaccard en el adapter (no duplicacion).

**Port y cliente:**
- [ ] Metodo abstracto `get_animal_temporal_distribution` tiene docstring actualizado con v3.
- [ ] `getAnimalTemporalDistribution(intervalMinutes=240)` en `frontend/src/api/client.js` tiene comentario indicando la estructura v3 con `types[]`.
- [ ] El componente `AnimalFrequencyPanel.jsx` NO esta implementado (solo stub); su implementacion queda bloqueada hasta el rediseno del `disenador-producto` (v3).

## 16. Trazabilidad

| Decisión técnica | Requisito / edge case que la origina |
|-----------------|--------------------------------------|
| Base temporal = LAG sobre `attacked_at` | Decisión del usuario: gap empírico entre ataques consecutivos al mismo oasis |
| Scope = solo global | Decisión del usuario: alcance = solo global |
| Tipos de animal = todos por separado | Decisión del usuario |
| Reutilizar `attack_reports` + `attack_report_animals` | Datos ya existen; no hay cambio de esquema |
| Patrón LAG con `PARTITION BY coords` | RN-TD11: gaps no deben cruzar oasis distintos — patrón confirmado en EP-09 |
| `interval_minutes` ∈ `{6,7,10,15,30,60,120,180,240,300}`, default `240` | Decisión del usuario (v2): frecuencias discretas reales del juego; 240 = ventana de sueño |
| Binning Opción B (umbral inferior) | Decisión del usuario (v2): monotonicidad y robustez al ruido de lag (§13) |
| Gaps < 6 min descartados | RN-TD04: no existe bin menor que 6 min; incluirlos distorsionaría el bin de 6 min |
| Respuesta de una sola frecuencia (no matriz) | Decisión del usuario (v2): UX más simple, payload menor, exploración interactiva |
| `n_reports_in_window` a nivel raíz | RN-TD08: denominador de "cuántos ataques tienes en esta cadencia" — señal de confianza |
| `present = NULL` → cuenta en `n_total`, excluido de cálculos | EC-TD02: derrotas son válidas como observaciones de timing pero no de cantidad |
| `n_total` y `n_valid` por animal | EC-TD02, EC-TD03: señal de confianza a nivel de especie |
| Moda en Python con `Counter` | RN-TD07: SQLite no tiene `MODE()`; empates como lista |
| Media redondeada a 2 decimales | RN-TD06: precisión suficiente para unidades de animales |
| `Accept-Language` obligatorio via `get_language` | RN-TD10: nombres de animal localizados — consistente con convención del proyecto |
| Nombres via `translation_port.get_troop_names_by_tribe(Tribe.nature, lang)` | RN-TD10: catálogo NATURE_1..10 en 25 idiomas verificado |
| `icon_url = /static/icons/nature_{ordinal}.png` | Patrón existente de EP-06 y otros endpoints de animales |
| `400` para `interval_minutes` semánticamente inválido | RN-TD13: valor fuera del conjunto es error de negocio, no de tipo; `422` es para errores de tipo/formato |
| `200` con `n_reports_in_window=0`, `animals=[]` si ventana vacía | RN-TD12: consistente con todos los endpoints de stats del proyecto; nunca `404` |
| UI bloqueada hasta rediseño del `disenador-producto` | Regla "mockup-first" del proyecto (CLAUDE.md): la vista pasa de matriz a lista simple |
| Endpoint declarado antes de EP-06 | Evitar colisión de routing con ruta literal vs. ruta dinámica |
| **Reutilizacion (v2):** modificar endpoint existente, no crear nuevo | El endpoint EP-TD fue creado en v1; v2 es una modificacion del mismo |
| **APIs (v2/v3):** contrato pendiente de gate de `desarrollador-apis` | `apis_validadas_por_desarrollador_apis: false` — v3 cambia schema radicalmente; gate necesario antes de implementar cliente HTTP |
| Velocidad de servidor no se ajusta | Decision acordada: el endpoint trabaja con tiempo real; el usuario configura timers en tiempo real |
| **v3: segmentacion por tipo de oasis** | Feedback del usuario: necesita distinguir la composicion por tipo de oasis (hierro/arcilla/madera/cereal) a una cadencia dada |
| **v3: inferencia por oasis (no por reporte)** | Una vez por oasis sobre el agregado de `present>0` — mas robusta que por reporte individual; un animal "sorpresa" en un reporte no cambia el tipo inferido del oasis |
| **v3: reutilizacion de `_infer_type` elevada** | RN-TD14: un segundo Jaccard divergente seria un bug silencioso. Decision: elevar a `infer_type` publica — confirmada por palantir (aviso de duplicacion en el analisis del gate) |
| **v3: oasis de baja confianza incluidos en su seccion** | RN-TD16: excluirlos ocultaria datos reales. La marca `n_oasis_low_confidence` es suficiente para que el front informe al usuario |
| **v3: 5 secciones fijas siempre presentes** | RN-TD17: el frontend necesita estructuras predecibles para renderizar el empty state sin comprobar si la clave existe |
| **v3: `oasis_type_label` "Barro" para clave "arcilla"** | RN-TD18: la terminologia del usuario es "Barro"; la clave interna del catalogo es "arcilla". Se desacoplan para no cambiar el catalogo |
| **v3: sin parametro de filtro por tipo** | Decision acordada: el endpoint devuelve siempre las 5 secciones; el filtrado es responsabilidad del frontend |
| **v3: cereal borroso — limitacion documentada** | El set cereal es universal {1..10}; Jaccard lo penaliza pero oasis muy variados se clasifican correctamente como cereal. La nota en la UI es obligatoria (§13 trade-offs) |
| **v3: UI rediseno separado** | Regla "mockup-first" del proyecto: la vista pasa de lista plana a secciones por tipo — requiere nuevo spec de disenador-producto y mockup aprobado por el usuario |

## Registro de implementación v1 (histórico)

**Fecha:** 2026-06-02
**Implementado por:** desarrollador-funcionalidades

### Ficheros creados
- `tests/test_animal_temporal_distribution_api.py` — 33 tests (T-TD01..T-TD20 + criterios de aceptación)

### Ficheros modificados
- `core/ports/attack_report_port.py` — método abstracto `get_animal_temporal_distribution` añadido (~línea 180, tras `get_oasis_spawn_composition`)
- `adapters/db/attack_report_sqlite_adapter.py` — método `get_animal_temporal_distribution` implementado en `AttackReportSQLiteAdapter`; añadido `Counter` a los imports de `collections`
- `adapters/api/routes/attack_reports.py` — endpoint EP-TD declarado antes de EP-06; imports de `get_language`, `get_translation_port` y `Depends` añadidos; comentario de cabecera actualizado
- `frontend/src/api/client.js` — método `getAnimalTemporalDistribution(bucketHours=2)` añadido
- `frontend/src/components/attack-reports/StatsTab.jsx` — comentario stub de `AnimalFrequencyPanel` añadido (bloqueado hasta spec de diseño)

### Resultado v1
**33 de 33 tests pasan.**
Suite completa del módulo: 166/166 tests en `test_attack_reports_api.py` + `test_oasis_spawn_composition_api.py` sin regresiones.

### Desviaciones de diseño registradas en v1
- **Cálculo de bucket en test_TD20 corregido**: el spec describe que un gap de 10h con `bucket_hours=2` cae en `[10h, 12h)` (`lower_h=10`), no en `[8h, 10h)` como el test inicial asumía. El cálculo `floor(36000 / 7200) * 2 = 10` es correcto conforme a la fórmula del §9. El test fue corregido para reflejar la expectativa correcta — no hay desviación en la implementación, sino en el test.
- **getAnimalTemporalDistribution en client.js usa buildHeaders()**: la función `buildHeaders()` del cliente ya inyecta `Accept-Language` automáticamente desde `localStorage.getItem('lang')`, por lo que no es necesario pasar el header explícitamente como en el pseudocódigo del §14. El comportamiento es idéntico al contrato acordado.

---

## Qué cambia respecto a la implementación v1 (guía para el implementador)

> Esta sección es la hoja de ruta de migración v1 → v2. El implementador debe seguir
> esta lista en orden. Los ficheros afectados son exactamente los mismos que en v1.

### Para `desarrollador-apis` (revalidar contrato)

1. **Parámetro renombrado:** `bucket_hours` → `interval_minutes`.
2. **Conjunto de valores:** `{1,2,4,8,12,24}` (horas) → `{6,7,10,15,30,60,120,180,240,300}` (minutos).
3. **Default:** `2` (horas) → `240` (minutos).
4. **Semántica de `400`:** el detail debe listar los 10 nuevos valores válidos.
5. **Schema de response completamente nuevo:** de `{bucket_hours, animals[{..., buckets[...]}]}` (matriz) a `{interval_minutes, interval_label, window, n_reports_in_window, animals[{..., avg, mode, n_total, n_valid}]}` (lista plana de una frecuencia). Ver §8 para el schema completo y la tabla de etiquetas.
6. **Campo `interval_label`** como string semántico (ej. `"4h"`, `"5h+"`, `"7 min"`).
7. **Campo `window`** con `lower_min`, `upper_min` (en minutos, no horas), `is_open`.
8. **Campo `n_reports_in_window`** a nivel raíz.
9. **El bin 300 es abierto:** `upper_min: null`, `is_open: true`, `interval_label: "5h+"`.
10. El contrato v1 en `openapi.yaml`, `API.md` y `AGENTS.md` debe actualizarse para reflejar el nuevo schema.

### Para `desarrollador-funcionalidades` (cambios de implementación)

#### `core/ports/attack_report_port.py`
- Cambiar la firma del método abstracto: `bucket_hours: int` → `interval_minutes: int`.
- Actualizar el docstring para reflejar los nuevos valores válidos y el nuevo schema de retorno.

#### `adapters/db/attack_report_sqlite_adapter.py`
- Reescribir el método `get_animal_temporal_distribution` completamente (ver pseudocódigo §9):
  - Añadir constantes `VALID_INTERVALS`, `WINDOWS`, `LABELS` (o importarlas de un módulo compartido).
  - Calcular `lower_sec` / `upper_sec` desde `WINDOWS[interval_minutes]`.
  - **Nuevo filtro:** descartar `gap_seconds < 360` (< 6 min) — no existía en v1.
  - **Nuevo filtro de ventana:** seleccionar solo gaps en `[lower_sec, upper_sec)`.
  - **Eliminar el agrupamiento por bucket:** ahora se agrupa solo por `animal_ordinal`.
  - **Calcular `n_reports_in_window`** a nivel raíz (count de `report_id` distintos).
  - **Devolver el nuevo schema** (sin campo `buckets` dentro de cada animal; los campos `avg_present`, `mode_present`, `n_total`, `n_valid` suben al nivel del animal directamente).

#### `adapters/api/routes/attack_reports.py`
- Cambiar `bucket_hours: int = Query(default=2)` → `interval_minutes: int = Query(default=240)`.
- Cambiar la whitelist de `{1,2,4,8,12,24}` → `{6,7,10,15,30,60,120,180,240,300}`.
- Actualizar el detail del `400`.
- Actualizar la llamada al adapter.

#### `frontend/src/api/client.js`
- Renombrar la función o el parámetro: `bucketHours=2` → `intervalMinutes=240`.
- Cambiar el nombre del query param de `bucket_hours` a `interval_minutes`.

#### `tests/test_animal_temporal_distribution_api.py`
- **Eliminar los 33 tests v1** (basados en `bucket_hours` y la matriz).
- **Escribir los 27 tests v2** (T-TD01..T-TD27 del §12), incluyendo obligatoriamente los casos
  de binning de frontera T-TD12..T-TD18.
- Los tests de frontera son los más críticos para verificar la Opción B:
  - T-TD12: gap exactamente en límite inferior → cuenta.
  - T-TD13: gap con ruido dentro del bin → cuenta en el bin correcto, no salta.
  - T-TD14: gap exactamente en límite superior → cae en el bin siguiente, no en el actual.
  - T-TD15: gap < 6 min → descartado.

### Nota sobre la UI
El componente `AnimalFrequencyPanel.jsx` y su stub en `StatsTab.jsx` no se tocan en esta
iteración, salvo actualizar el comentario del stub para indicar que es una vista de lista
simple (no matriz). El rediseño completo de la UI es responsabilidad del `disenador-producto`
en una iteración separada.

---

## Registro de implementación v2

**Fecha:** 2026-06-02
**Implementado por:** desarrollador-funcionalidades

### Ficheros modificados
- `core/ports/attack_report_port.py` — firma del método abstracto `get_animal_temporal_distribution`: `bucket_hours` → `interval_minutes`; docstring actualizado con los 10 valores válidos y el nuevo schema de retorno.
- `adapters/db/attack_report_sqlite_adapter.py` — reescritura completa del método `get_animal_temporal_distribution`: constantes `_WINDOWS`/`_LABELS` locales, binning umbral inferior, filtro `gap_seconds < 360`, ventana `[lower_sec, upper_sec)` o `[lower_sec, ∞)`, `n_reports_in_window` por report_ids distintos, schema plano de una sola frecuencia sin `buckets`. Bug fixes: `Tribe.NATURE` (mayúsculas) y clave `"nombre"` del JsonTranslationAdapter.
- `adapters/api/routes/attack_reports.py` — `bucket_hours: int = Query(default=2)` → `interval_minutes: int = Query(default=240)`; whitelist `{1,2,4,8,12,24}` → `{6,7,10,15,30,60,120,180,240,300}`; detail del 400 actualizado con los 10 valores; llamada al adapter actualizada.
- `frontend/src/api/client.js` — `getAnimalTemporalDistribution(bucketHours=2)` → `getAnimalTemporalDistribution(intervalMinutes=240)`; query param `bucket_hours` → `interval_minutes`.
- `tests/test_animal_temporal_distribution_api.py` — 33 tests v1 eliminados; 39 tests v2 escritos (T-TD01..T-TD27 + CA).
- `documentacion/backend/referencia-funciones/attack-report-temporal-distribution.md` — actualizado a v2 con nueva firma, tabla de bins, algoritmo y cliente JS.

### Comando para ejecutar los tests
```bash
source .venv/bin/activate && pytest tests/test_animal_temporal_distribution_api.py -v
```
Suite completa (sin regresiones):
```bash
source .venv/bin/activate && pytest tests/ --ignore=tests/unit --ignore=tests/antideteccion -q
```

### Resultado
**39 de 39 tests del módulo pasan.**
Suite completa: 541 passed, 11 skipped (resources_api — dependencia de browser, no aplica), 0 failed.

### Desviaciones de diseño registradas en v2
- `Tribe.NATURE` en mayusculas: el pseudocodigo del §9 usa `Tribe.nature` pero el enum Python usa `Tribe.NATURE`. La v1 fallaba silenciosamente al resolver nombres (los capturaba el `except Exception`); en v2 se corrige y se cubre con T-TD09.
- Clave `"nombre"` en el dict del translation_port: el pseudocodigo del §9 usa `entry["name"]` pero `JsonTranslationAdapter.get_troop_names_by_tribe` devuelve `entry["nombre"]`. Corregido en la implementacion v2.
- 39 tests en lugar de 27: el §12 describe 27 tests (T-TD01..T-TD27) pero la implementacion anade 12 tests CA adicionales (criterios de aceptacion §15 y validaciones de metadatos de ventana). Los 27 del spec estan todos presentes y en verde.

---

## Que cambia respecto a la implementacion v2 (guia para el implementador v3)

> Esta seccion es la hoja de ruta de migracion v2 → v3.
> Los ficheros de la implementacion v2 son exactamente los que hay que modificar.

### Para `desarrollador-apis` (revalidar contrato v3)

1. **El campo raiz `animals` desaparece.** Se sustituye por `types` (array de 5 secciones).
2. **Campo `types` nuevo:** array con 5 elementos fijos (hierro, arcilla, madera, cereal, sin_clasificar).
3. **Cada seccion tiene:** `oasis_type`, `oasis_type_label`, `n_oasis`, `n_oasis_low_confidence`,
   `n_reports_in_section`, `animals[]` (mismo schema que el array plano de v2).
4. **`oasis_type_label` de "arcilla" es "Barro"** — no "Arcilla".
5. **`n_reports_in_window` en el raiz** sigue presente; ahora es la suma de `n_reports_in_section`.
6. **Secciones vacias siempre presentes** — nunca ausentes del array.
7. **Sin nuevo query param.** El endpoint no anade `oasis_type` como parametro de filtro.
8. El contrato v2 en `openapi.yaml`, `API.md` y `AGENTS.md` debe actualizarse para reflejar el schema v3.

### Para `desarrollador-funcionalidades` (cambios de implementacion v2 → v3)

#### `adapters/db/attack_report_sqlite_adapter.py` (cambio principal)

Pasos 1-7 del §14:
- **Elevar `_infer_type` a `infer_type`** (Paso 1 del §14) — no reimplementar Jaccard.
- **Anadir query de composicion** (misma que EP-SPAWN, Paso 1 del §9 pseudocodigo).
- **Ampliar query LAG** para devolver `coord_x_dest` y `coord_y_dest` (Paso 2 del §9).
- **Sustituir agrupamiento por `animal_ordinal`** por agrupamiento por `(tipo, animal_ordinal)`.
- **Construir array `types` con 5 secciones** (Paso 9 del §9).
- **Eliminar el campo `animals` del retorno raiz** — ahora va dentro de cada seccion.
- **Anadir constantes `TYPE_LABELS` y `TYPE_ORDER`** al modulo.

Bugs de v2 que siguen vigentes (NO regresar): `Tribe.NATURE` (mayusculas), clave `"nombre"`.

#### `core/ports/attack_report_port.py`
- Actualizar el docstring del metodo abstracto: el retorno tiene `types` (no `animals`).
- La firma `(interval_minutes, lang, translation_port)` no cambia.

#### `adapters/api/routes/attack_reports.py`
- Sin cambios funcionales. Solo actualizar el comentario de cabecera a v3.

#### `frontend/src/api/client.js`
- Sin cambios funcionales en la firma. Anadir comentario sobre el schema v3 con `types[]`.

#### `tests/test_animal_temporal_distribution_api.py`
- **Eliminar los 39 tests v2** (verifican `animals` en el raiz).
- **Escribir los tests v3** cubriendo T-TD01..T-TD35 del §12.
- Mantener todos los casos de binning de frontera (T-TD12..T-TD18) sin modificacion.
- Anadir fixtures con oasis de tipos diferenciados para los casos T-TD28..T-TD35.

### Nota sobre la UI
El componente `AnimalFrequencyPanel.jsx` y su stub en `StatsTab.jsx` no se tocan en v3,
salvo actualizar el comentario del stub a "(v3: secciones por tipo de oasis)".
El rediseno completo de la UI (secciones por tipo, etiquetas, disclaimer de cereal,
indicador de baja confianza) es responsabilidad del `disenador-producto` + nuevo mockup
editable aprobado por el usuario. No implementar la UI sin ese gate.

---

## Registro de implementacion v3

**Fecha:** pendiente
**Implementado por:** desarrollador-funcionalidades

### Ficheros a modificar
- `adapters/db/attack_report_sqlite_adapter.py` — elevar `_infer_type` + reescribir `get_animal_temporal_distribution` con inferencia de tipo, agrupacion por (tipo x animal), array `types` v3.
- `core/ports/attack_report_port.py` — actualizar docstring del metodo abstracto.
- `adapters/api/routes/attack_reports.py` — actualizar comentario de cabecera.
- `frontend/src/api/client.js` — anadir comentario sobre schema v3.
- `frontend/src/components/attack-reports/StatsTab.jsx` — actualizar comentario stub.
- `tests/test_animal_temporal_distribution_api.py` — reescribir tests v2 → v3.
- `documentacion/backend/referencia-funciones/attack-report-temporal-distribution.md` — actualizar a v3.

### Resultado
*Pendiente de implementacion.*

### Desviaciones de diseno registradas en v3
*(A rellenar por el implementador.)*
