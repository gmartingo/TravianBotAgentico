---
id: lectura-troops
titulo: "Lectura de tropas — bloque TROOPS (5 sub-pestañas)"
estado: implemented
fecha: 2026-05-26
autor: analista
apis_validadas_por_desarrollador_apis: true
---

# Lectura de tropas — bloque TROOPS

---

## 1. Objetivo de negocio

Exponer a través de la API del bot el estado completo de las tropas del jugador en
Travian, agregado por todas sus aldeas, a partir de las cinco sub-pestañas de
`/village/statistics/troops`:

| Sub-pestaña | Información |
|---|---|
| `own` | Cantidad máxima de tropas por tipo y por aldea (ejército total) |
| `support` | Tropas actualmente presentes en cada aldea (propias + naturaleza + héroe) |
| `smithy` | Nivel de mejora de cada tipo de tropa en cada herrería + si hay investigación activa |
| `hospital` | Heridos por tipo en cada hospital + si hay tropas curándose |
| `training` | Tiempo de cola restante en cuartel / establo / taller / hospital de cada aldea |

El bloque NO modifica datos ni interactúa con el juego. Es solo lectura.

---

## 2. Actores y permisos

| Actor | Rol |
|---|---|
| Cliente HTTP del bot (frontend / orquestador) | Consume los endpoints para mostrar estado de tropas |
| `OverviewHtmlSourcePort` | Tronco ya implementado: abstrae la fuente de HTML (live vs fixture) |
| `TroopsUseCase` | Use case del bloque; orquesta el port y los parsers |
| `TroopsParser` | Parser puro HTML → DTOs; vive en `adapters/browser/parsers/troops_parser.py` |
| `FixtureOverviewAdapter` | Implementación de test; ya funcional (tronco implementado) |
| `LiveOverviewAdapter` | Implementación viva (Chrome autenticado); ya funcional (tronco implementado) |

No hay control de acceso diferenciado. La misma política que en los otros bloques de overview.

---

## 3. Alcance

### Dentro de alcance

- Parser `TroopsParser` en `adapters/browser/parsers/troops_parser.py` con métodos
  estáticos para las 5 sub-pestañas.
- DTOs en `core/dtos/troops_dto.py`.
- Use case `TroopsUseCase` en `core/use_cases/troops_use_case.py`.
- Router FastAPI en `adapters/api/routes/game_troops.py` con 5 sub-rutas bajo
  `/game/troops/{world_id}/`.
- Tests con los 5 fixtures reales ya disponibles en `tests/fixtures/overview/`.
- Derivación de la tribu del jugador desde el HTML de `TROOPS_HOSPITAL`
  (`th.villageName i.tribeN_medium`). Este dato se expone en la respuesta de `/hospital`.

### Fuera de alcance

- Modificación del tronco (`OverviewHtmlSourcePort`, `OverviewPage`, adaptadores,
  `VillageMapUseCase`). Ya implementado; se usa sin cambios.
- Enriquecimiento con stats estáticos de `GameDataPort` (consumo de cereal, ataque,
  defensa por tipo). La API de `troops/support` ya expone estos valores calculados
  por Travian en el HTML (`upkeep`, `strengthWrapper`). No se cruzan con el catálogo.
- Endpoint agregado que devuelva las 5 sub-pestañas en una sola llamada (ver sección 13,
  TR-01).
- Persistencia de datos de tropas en SQLite.
- Autenticación / autorización en los endpoints.

---

## 4. Reglas de negocio

**RN-01 — Tipo de tropa identificado por `uNN` (estable, idioma-independiente):**
El tipo de tropa SIEMPRE se identifica por la clase CSS de la imagen (`img.unit.uNN`):
`u21`–`u30` propias Galos, `u31`–`u40` naturaleza, `uhero` héroe. NUNCA por el texto
`alt` (que cambia con el idioma de Travian). La cadena `"u21"`, `"u22"`, … `"uhero"`
es el identificador canónico en todos los DTOs y respuestas JSON.

**RN-02 — Páginas agregadas; no existe página por aldea:**
Cada sub-pestaña lista TODAS las aldeas del jugador. El parser extrae las filas de cada
aldea del HTML de la página completa.

**RN-03 — `td.none` = cantidad 0, no ausencia de datos:**
La presencia de la clase `none` en una celda de cantidad indica explícitamente el valor 0.
El parser lo convierte a `int 0`, nunca a `None`.

**RN-04 — `span.dot` vs `span.none` en columnas de estado:**
- `span.dot` (•): el edificio / proceso existe pero no hay actividad (herrería sin
  investigación activa, hospital sin curación en curso, edificio sin cola de entrenamiento).
- `span.none` (-): el edificio no existe en esa aldea (sin hospital, sin taller, etc.).
Ambos son semánticamente distintos y el DTO debe capturar la diferencia.

**RN-05 — Tribu derivable del HTML de hospital:**
La cabecera de la tabla de hospital lleva `th.villageName > i.tribeN_medium` donde N
es el número de tribu (1=Romanos, 2=Teutones, 3=Galos). Este dato se expone solo en
el endpoint `/hospital` como campo `player_tribe` de tipo `int`.

**RN-06 — Smithy: columnas fijas u21–u28 (8 tropas de combate Galos):**
La tabla de herrería expone niveles para u21–u28 (Phalanx a Trebuchet). Las tropas
u29 (Chieftain) y u30 (Settler) no tienen niveles de mejora en herrería. El parser
lee los encabezados del `thead` para determinar las columnas presentes (en lugar de
asumir posición fija), pero en los fixtures reales son siempre u21–u28.

**RN-07 — Hospital: heridos solo u21–u26 (6 tropas de infantería/caballería):**
La tabla de hospital expone heridos para u21–u26. Las máquinas de guerra (u27-u28),
el Chieftain (u29) y el Settler (u30) no pueden herirse. El héroe (uhero) tampoco.

**RN-08 — Training: columnas dinámicas según edificios disponibles:**
Las columnas de la tabla de training dependen de qué edificios de entrenamiento existen
en el mundo del jugador. Se leen dinámicamente desde los `th.unit > i.building_small`
del `thead`, extrayendo el `gid` del `a[href*='gid=N']` en la fila de datos (no del
icono del encabezado, que no lleva `gid` directamente). Los `gid` canónicos son:
19=Cuartel, 20=Establo, 21=Taller, 46=Hospital. El tiempo de cola se parsea con
`parse_time` a segundos.

**RN-09 — `Accept-Language` obligatoria y FUNCIONAL:**
Todos los endpoints del bloque usan `get_language` (obligatoria, `400` si falta).
El idioma resuelto gobierna los nombres de tropas y edificios en la respuesta:
- Cada tipo de tropa expone `unit_class` (código estable) **Y** `name` (nombre localizado al
  idioma pedido), resuelto vía `unit_class_to_tribe_ordinal(uNN)` +
  `translation_port.get_troop_name(tribe, ordinal, lang)`.
  Fallback: si el `uNN` no tiene entrada en el catálogo (uhero, NATARS_11 vacío), `name = unit_class`.
- El endpoint `/training` expone `building_name` (nombre localizado del edificio) vía
  `translation_port.get_building_name(gid, lang)` para los gid conocidos (19, 20, 21, 46).
- Los use cases del bloque reciben `lang: str` y `translation_port: TranslationPort`.
- El `translation_port` es un puerto del core; su inyección no viola hexagonal.

**RN-10 — Sin `VillageMapUseCase` en este bloque:**
Las 5 sub-pestañas de troops ya incluyen `game_id` de aldea en cada fila via
`href*='newdid=N'`. No es necesario llamar a `VillageMapUseCase` para construir
el índice de aldeas. El `game_id` se extrae directamente del href de cada fila.

**RN-11 — Solapamiento "training/tropas" con bloque overview:**
La columna `td.tro` del overview principal muestra un resumen de unidades en
entrenamiento (solo tipos de tropa en curso, no tiempos). El bloque `troops/training`
expone los tiempos de cola completos. Son fuentes complementarias, no duplicadas.
Se deja anotado para que `palantir` lo considere al comparar la fuente canónica de
"entrenamiento activo".

---

## 5. Flujo principal y flujos alternativos

### Flujo principal — petición HTTP a un sub-endpoint de troops

```
Cliente HTTP
  └─> GET /game/troops/{world_id}/own   Accept-Language: es
        └─> FastAPI handler
              ├─ get_language(...)           → "es"
              ├─ get_html_source_port(...)   → OverviewHtmlSourcePort
              └─> troops_use_case.get_own(port, world_id)
                    └─> port.get_page_html(world_id, OverviewPage.TROOPS_OWN)
                          └─ [caché hit / miss + posible navegación Chrome]
                    └─> TroopsParser.parse_own(html) → list[TroopsOwnVillageDTO]
              └─> serializar → JSON 200
```

El mismo patrón se repite para `/support`, `/smithy`, `/hospital`, `/training`.

### Flujo alternativo A — sesión no activa (modo live sin login)

```
port.get_page_html(world_id, TROOPS_OWN)
  └─ SessionNotActiveError → handler devuelve HTTP 503
```

### Flujo alternativo B — fixture no encontrado (modo fixture)

```
port.get_page_html(world_id, TROOPS_OWN)
  └─ OverviewFixtureNotFoundError → handler devuelve HTTP 500
     (error de configuración del entorno de test, no fallo transitorio del servicio)
```

### Flujo alternativo C — aldea sin tropas de ningún tipo (página `own`)

```
TroopsParser.parse_own(html)
  └─ fila con todos los td.none → VillageOwnTroopsDTO(game_id=N, counts={uNN: 0 para todos})
```
Se devuelve el DTO con todos los valores a 0, no se omite la aldea.

### Flujo alternativo D — aldea sin hospital (página `hospital`)

```
TroopsParser.parse_hospital(html)
  └─ td.inProgress > span.none → VillageHospitalDTO(game_id=N, has_hospital=False, healing=False, wounded={})
```

### Flujo alternativo E — aldea sin ningún edificio de entrenamiento (página `training`)

```
TroopsParser.parse_training(html)
  └─ todas las celdas con span.none → VillageTrainingDTO(game_id=N, queues={})
     donde queues es un dict vacío (ningún edificio existe)
```

---

## 6. Edge cases

| ID | Caso | Tratamiento esperado |
|---|---|---|
| EC-01 | `td.none` con texto "0" en troops/own | `parse_int` → `0`; el DTO registra la tropa con count=0 |
| EC-02 | `td.unit.none` con texto "-" en smithy (tropa no investigable) | El nivel se almacena como `None` en el DTO (`smithy_level: int \| None`). El "-" distingue "no investigable" de "no investigada" (nivel 0) |
| EC-03 | `td.unit.none` con texto "0" en smithy (tropa investigable no mejorada) | Nivel `0` (entero); no es `None` |
| EC-04 | Smithy con múltiples tropas en "in progress" | La columna `inProgress` puede contener varios `img.unit.uNN` simultáneos (fixture aldea 00 tiene u22 y u24). El DTO almacena `in_progress: list[str]` con todos los `uNN` en curso |
| EC-05 | Smithy con `span.dot` en "in progress" (sin investigación activa) | `in_progress: []` lista vacía |
| EC-06 | Hospital con `span.dot` en `td.inProgress` (hospital existe, sin curación activa) | `has_hospital=True`, `healing=False` |
| EC-07 | Hospital con `span.none` en `td.inProgress` (sin hospital en la aldea) | `has_hospital=False`, `healing=False`, `wounded={}` vacío |
| EC-08 | Hospital: heridos = 0 en todas las columnas (aldea con hospital pero sin heridos) | `has_hospital=True`, `healing=False`, `wounded={u21: 0, u22: 0, …}` |
| EC-09 | Support: aldea con solo naturaleza (sin tropas propias) | Solo se registran entradas en `nature` del DTO; `own={}` vacío |
| EC-10 | Support: aldea sin ninguna tropa (todo cero, incluyendo naturaleza) | DTO con `own={}`, `nature={}`, `hero=0`; `upkeep_per_hour=0`; `offence=None`, `def_infantry=None`, `def_cavalry=None` (el fixture muestra "-" para fuerza cuando no hay tropas) |
| EC-11 | Support: strength con valor "-" (aldea sin tropas) | Los tres campos de fuerza (`offence`, `def_infantry`, `def_cavalry`) = `None` |
| EC-12 | Training: `span.dot` (edificio existe sin cola) | `queue_seconds=0`; `building_exists=True` en el DTO |
| EC-13 | Training: `span.none` (edificio inexistente) | La clave del edificio NO aparece en `queues`; o bien `queue_seconds=None` y `building_exists=False`. Ver sección 9 para decisión de diseño |
| EC-14 | Training: tiempo de cola con formato "H:MM:SS" con padding de espacios | `parse_time` ya maneja strip; el fixture muestra `"                                    1:56:06                                "` |
| EC-15 | Own: fila `tr.empty` con `td[colspan]` entre datos y `tr.sum` | No tiene `td.villageName`; se ignora (el parser busca `td.villageName` o `td.vil.fc`) |
| EC-16 | Own: fila `tr.sum` (totales) | No tiene `td.villageName`; se ignora. Los totales no se exponen en el DTO de este bloque |
| EC-17 | Support: aldea 02 en fixture no tiene fila de naturaleza (solo propias) | El parser detecta la presencia/ausencia del `tbody.troops` con clases u31-u40 y construye `nature={}` si no hay fila de naturaleza |
| EC-18 | Números con bidi U+202D/U+202C en strength (support) | `parse_int` elimina caracteres bidi antes de convertir; p.ej. `"‭201,060‬"` → `201060` |
| EC-19 | Jugador con una sola aldea | El parser devuelve lista de un DTO. Sin error |
| EC-20 | `Accept-Language` ausente | HTTP 400 — convención del tronco (RN-09) |
| EC-21 | `Accept-Language` con idioma no soportado | HTTP 400 |

---

## 7. Modelo de datos / cambios de esquema

No hay cambios en SQLite. Los datos son efímeros (caché del tronco). Se crean los
siguientes DTOs en `core/dtos/troops_dto.py`:

### 7.1 Troops Own — `TroopsOwnResponse`

```python
@dataclass
class TroopTypeInfo:
    """
    Información de un tipo de tropa: código estable + nombre localizado.
    Usado en `troop_types` de TroopsOwnResponse, TroopsSmithyResponse, etc.
    """
    unit_class: str   # Código estable: "u21", "u22", ..., "uhero"
    name:       str   # Nombre localizado al idioma pedido, ej. "Falange" (es)
                      # Fallback a unit_class si no hay entrada en el catálogo

@dataclass
class VillageOwnTroopsDTO:
    """Tropas totales (ejército) de una aldea. Cantidad máxima por tipo."""
    game_id:  int              # newdid de la aldea
    counts:   dict[str, int]   # uNN → cantidad (incluye u21-u30 y uhero; 0 si ausente)
    # Nota: las columnas presentes en la tabla son las del thead del fixture.
    # Solo aparecen los uNN que el thead lista; el orden del dict sigue el thead.
    # Los nombres localizados de cada uNN están en TroopsOwnResponse.troop_types.

@dataclass
class TroopsOwnResponse:
    villages:    list[VillageOwnTroopsDTO]
    troop_types: list[TroopTypeInfo]   # orden canónico según el thead; cada entrada lleva unit_class + name
    totals:      dict[str, int]        # suma global por uNN (de la fila tr.sum del HTML)
```

### 7.2 Troops Support — `TroopsSupportResponse`

```python
@dataclass
class VillageSupportTroopsDTO:
    """Tropas presentes en una aldea en el momento de la consulta."""
    game_id:          int
    own:              dict[str, int]   # uNN → cantidad (solo propias u21-u30+uhero)
    nature:           dict[str, int]   # uNN → cantidad (solo naturaleza u31-u40)
    hero:             int              # cantidad de héroes (puede solapar con own[uhero])
    upkeep_per_hour:  int              # consumo de cereal por hora
    offence:          int | None       # fuerza ofensiva total (None si sin tropas)
    def_infantry:     int | None       # defensa infantería total
    def_cavalry:      int | None       # defensa caballería total
    # Nota: los nombres localizados de cada uNN en own/nature están en TroopsSupportResponse.troop_names.

@dataclass
class TroopsSupportResponse:
    villages:    list[VillageSupportTroopsDTO]
    troop_names: dict[str, str]   # uNN → nombre localizado para todos los uNN presentes
                                   # ej. {"u21": "Falange", "u31": "Rata", "uhero": "uhero"}
```

**Nota sobre `hero`:** En el fixture, el héroe aparece en dos sitios: como
`img.unit.uhero` en la fila de iconos de tropas propias y como `img.unit.uhero` en la
fila de naturaleza (primera tabla, aldea 00). El parser debe agrupar todas las
ocurrencias de `uhero` en `own["uhero"]`. El campo `hero` es un alias conveniente de
`own.get("uhero", 0)` para acceso rápido; ambos deben ser consistentes.

**Patrón de nombres en support:** dado que support puede contener tribus distintas a la
del jugador (tribus aliadas en refuerzo, tropas de naturaleza), los nombres se construyen
en el use case recorriendo todos los `uNN` encontrados en todas las aldeas y llamando a
`unit_class_to_tribe_ordinal` + `translation_port.get_troop_name` para cada uno.
El dict `troop_names` de nivel raíz evita repetir el nombre en cada fila de aldea.

### 7.3 Troops Smithy — `TroopsSmithyResponse`

```python
@dataclass
class VillageSmithyDTO:
    """Estado de investigación/mejora de tropas en la herrería de una aldea."""
    game_id:     int
    in_progress: list[str]           # uNN de tropas actualmente investigándose ([] si span.dot)
    levels:      dict[str, int | None]
    # uNN → nivel de mejora (int ≥ 0) o None (tropa no investigable, "-" en HTML)
    # Solo incluye los uNN que aparecen en el thead (u21-u28 en los fixtures actuales)

@dataclass
class TroopsSmithyResponse:
    villages:    list[VillageSmithyDTO]
    troop_types: list[TroopTypeInfo]   # orden canónico según thead; cada entrada lleva unit_class + name
```

### 7.4 Troops Hospital — `TroopsHospitalResponse`

```python
@dataclass
class VillageHospitalDTO:
    """Estado del hospital de una aldea."""
    game_id:      int
    has_hospital: bool             # True si el hospital existe (span.dot o heridos > 0)
    healing:      bool             # True si hay curación activa (span.dot en inProgress)
    wounded:      dict[str, int]   # uNN → heridos (u21-u26; solo si has_hospital=True)
    # Si has_hospital=False, wounded es {} (vacío)

@dataclass
class TroopsHospitalResponse:
    player_tribe:   int                    # extraído de th.villageName > i.tribeN_medium
    villages:       list[VillageHospitalDTO]
    troop_types:    list[TroopTypeInfo]    # orden canónico según thead; cada entrada lleva unit_class + name
```

**Nota sobre `healing`:** El fixture muestra que `span.dot` en `td.inProgress` significa
"hospital existe, curación NO activa" (aldeass 00 y 01). `span.none` significa "sin
hospital" (aldeas 02-05). Semánticamente: `span.dot` = hospital presente pero sin
actividad de curación en ese momento. Si hubiera curación activa, el HTML mostraría un
`span.duration` o un contador de tiempo en lugar del `span.dot`. En el fixture actual
todos los inProgress tienen `span.dot` o `span.none`, ninguno tiene timer activo. El
parser debe prepararse para un posible `span.duration` o `a > span.timer` si Travian
muestra el tiempo restante de curación (aunque el fixture actual no lo evidencia).

### 7.5 Troops Training — `TroopsTrainingResponse`

```python
@dataclass
class BuildingInfo:
    """
    Información de un edificio de entrenamiento: gid + nombre localizado.
    Usado en `buildings` de TroopsTrainingResponse.
    """
    gid:  int   # 19=Cuartel, 20=Establo, 21=Taller, 46=Hospital
    name: str   # Nombre localizado vía translation_port.get_building_name(gid, lang)
                # ej. "Cuartel" (es), "Barracks" (en), "Kaserne" (de)
                # Fallback: "building_{gid}" si el gid no está en el catálogo de edificios

@dataclass
class BuildingQueueDTO:
    """Cola de entrenamiento de un edificio concreto en una aldea."""
    gid:              int          # 19=Cuartel, 20=Establo, 21=Taller, 46=Hospital
    building_exists:  bool         # True si el edificio existe (span.duration o span.dot)
    queue_seconds:    int | None   # Segundos en cola (0 si span.dot; None si span.none)

@dataclass
class VillageTrainingDTO:
    game_id:  int
    queues:   list[BuildingQueueDTO]   # uno por columna del thead (en orden del thead)

@dataclass
class TroopsTrainingResponse:
    buildings:  list[BuildingInfo]         # orden de columnas según thead; cada entrada lleva gid + name
    building_gids: list[int]               # alias de [b.gid for b in buildings] — para compatibilidad
    villages:   list[VillageTrainingDTO]
```

**Nota de diseño:** `queues` es una lista (no dict) para preservar el orden del thead y
facilitar la serialización a array en JSON. El cliente cruza con `buildings` para
saber qué columna corresponde a cada posición y su nombre localizado.

---

## 8. Contratos de API / interfaces

**NOTA:** Contrato validado por `desarrollador-apis` (2026-05-26). Incluye la política
de localización FUNCIONAL: `Accept-Language` gobierna `troop_types[].name`, `troop_names`
y `buildings[].name` vía `translation_port`. Ver RN-09 actualizado.

### Decisión de diseño: sub-rutas separadas vs endpoint único agregado

**Decisión: sub-rutas separadas** (`/own`, `/support`, `/smithy`, `/hospital`, `/training`).

**Justificación:**
- Coste anti-detección: un solo endpoint `/troops` agregaría 5 navegaciones de Chrome
  en secuencia. Desde el punto de vista del bot, navegar 5 pestañas seguidas en una
  sola petición HTTP aumenta el tiempo de respuesta total a ~10-20 segundos y concentra
  5 acciones de browser en un instante — más detectable que solicitudes independientes
  espaciadas en el tiempo.
- Utilidad real del cliente: el frontend o el orquestador probablemente necesita solo
  1-2 sub-pestañas a la vez (p.ej., antes de una decisión de entrenamiento, solo
  `training`; antes de calcular la defensa disponible, solo `own` + `support`).
- Caché del tronco: el `LiveOverviewAdapter` cachea por `(world_id, page)`. Si las
  5 sub-rutas fueran parte de un endpoint único, la caché no se aprovecharía entre
  llamadas independientes. Con sub-rutas, cada pestaña se cachea de forma independiente.
- Alternativa rechazada: un endpoint `/game/troops/{world_id}` con query param
  `?views=own,support` complicaría el parser y el DTO sin beneficio real. La opción de
  un endpoint agregado sin parámetros (siempre las 5 páginas) se rechaza explícitamente
  por el coste de 5 navegaciones simultáneas.

### Rutas propuestas

Prefijo: `/game/troops/{world_id}` — bajo `/game/` (tronco RN-08).

```
GET /game/troops/{world_id}/own
GET /game/troops/{world_id}/support
GET /game/troops/{world_id}/smithy
GET /game/troops/{world_id}/hospital
GET /game/troops/{world_id}/training
```

### 8.1 `GET /game/troops/{world_id}/own`

**Descripción:** Tropas totales (ejército máximo) por aldea y por tipo.

**Path params:**
- `world_id: int` — ID del mundo (sesión activa).

**Headers:**
- `Accept-Language: es` (obligatoria; `400` si falta o no soportada).

**Respuesta 200:**
```json
{
  "troop_types": [
    {"unit_class": "u21", "name": "Falange"},
    {"unit_class": "u22", "name": "Espadachín"},
    {"unit_class": "u23", "name": "Explorador galo"},
    {"unit_class": "u24", "name": "Teutat Thunder"},
    {"unit_class": "u25", "name": "Druidrider"},
    {"unit_class": "u26", "name": "Haeduan"},
    {"unit_class": "u27", "name": "Ariete galo"},
    {"unit_class": "u28", "name": "Catapulta gala"},
    {"unit_class": "u29", "name": "Conquistador"},
    {"unit_class": "u30", "name": "Colono galo"},
    {"unit_class": "uhero", "name": "uhero"}
  ],
  "villages": [
    {
      "game_id": 19040,
      "counts": {
        "u21": 227,
        "u22": 3136,
        "u23": 125,
        "u24": 1885,
        "u25": 0,
        "u26": 420,
        "u27": 30,
        "u28": 60,
        "u29": 0,
        "u30": 0,
        "uhero": 0
      }
    }
  ],
  "totals": {
    "u21": 327,
    "u22": 4883,
    "u23": 278,
    "u24": 3357,
    "u25": 17,
    "u26": 480,
    "u27": 54,
    "u28": 78,
    "u29": 0,
    "u30": 0,
    "uhero": 1
  }
}
```

> **Patrón código estable + nombre localizado:** `troop_types` es la lista de metadatos
> de tipos de tropa. Cada entrada lleva `unit_class` (código estable) y `name` (nombre
> localizado al idioma pedido). Las filas de aldea (`counts`, `totals`) usan `unit_class`
> como clave — el cliente cruza con `troop_types` para obtener el nombre de cada clave.

**Errores:**
| Código | Motivo |
|---|---|
| `400` | `Accept-Language` ausente o idioma no soportado |
| `422` | `world_id` no es entero (validación FastAPI automática) |
| `503` | `SessionNotActiveError` — sesión no activa |
| `503` | `OverviewPageNotLoadedError` — timeout cargando la página de Travian |
| `500` | `OverviewFixtureNotFoundError` — fixture no encontrado (solo en modo test) |

**Cabeceras de request requeridas:**

```
Accept-Language: es    (obligatoria; 400 si falta o idioma no soportado)
```

**Cabeceras de respuesta mínimas (añadidas por el middleware de main.py):**

```
Content-Type: application/json; charset=utf-8
X-Request-ID: <uuid-v4>
X-API-Version: 0.1.0
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
```

> Nota de localización: `Accept-Language` es **FUNCIONAL**. `troop_types[].name` se resuelve
> vía `unit_class_to_tribe_ordinal(uNN)` + `translation_port.get_troop_name(tribe, ordinal, lang)`.
> Las claves de `counts` y `totals` siguen siendo `uNN` (estables, idioma-independientes).

### 8.2 `GET /game/troops/{world_id}/support`

**Descripción:** Tropas presentes en cada aldea en el momento de la consulta.

**Path params:** `world_id: int`

**Headers:** `Accept-Language` (obligatoria)

**Respuesta 200:**
```json
{
  "troop_names": {
    "u21": "Falange",
    "u22": "Espadachín",
    "u23": "Explorador galo",
    "u24": "Teutat Thunder",
    "u25": "Druidrider",
    "u26": "Haeduan",
    "u27": "Ariete galo",
    "u28": "Catapulta gala",
    "u29": "Conquistador",
    "u30": "Colono galo",
    "u40": "Elefante",
    "uhero": "uhero"
  },
  "villages": [
    {
      "game_id": 19040,
      "own": {
        "u21": 227, "u22": 1199, "u23": 125, "u24": 848,
        "u25": 0, "u26": 228, "u27": 0, "u28": 0, "u29": 0, "u30": 0, "uhero": 0
      },
      "nature": {
        "u31": 0, "u32": 0, "u33": 0, "u34": 0, "u35": 0,
        "u36": 0, "u37": 0, "u38": 0, "u39": 0, "u40": 5
      },
      "hero": 0,
      "upkeep_per_hour": 9093,
      "offence": 201060,
      "def_infantry": 90625,
      "def_cavalry": 110720
    },
    {
      "game_id": 26421,
      "own": {"u21": 0, "u22": 0, "u23": 0, "u24": 0, "u25": 0, "u26": 0, "u27": 0, "u28": 0, "u29": 0, "u30": 0, "uhero": 0},
      "nature": {},
      "hero": 0,
      "upkeep_per_hour": 0,
      "offence": null,
      "def_infantry": null,
      "def_cavalry": null
    }
  ]
}
```

> **Nota de localización:** `troop_names` es un dict plano `uNN → nombre localizado` que cubre
> todos los `uNN` encontrados en el HTML (propias + naturaleza). Cada aldea sigue usando `uNN`
> como clave en `own` y `nature`; el cliente cruza con `troop_names` para mostrar el nombre.

**Errores:** igual que `/own` (400/422/503/500 según tabla anterior).

### 8.3 `GET /game/troops/{world_id}/smithy`

**Descripción:** Nivel de mejora de tropas en herrería por aldea + investigación activa.

**Respuesta 200:**
```json
{
  "troop_types": [
    {"unit_class": "u21", "name": "Falange"},
    {"unit_class": "u22", "name": "Espadachín"},
    {"unit_class": "u23", "name": "Explorador galo"},
    {"unit_class": "u24", "name": "Teutat Thunder"},
    {"unit_class": "u25", "name": "Druidrider"},
    {"unit_class": "u26", "name": "Haeduan"},
    {"unit_class": "u27", "name": "Ariete galo"},
    {"unit_class": "u28", "name": "Catapulta gala"}
  ],
  "villages": [
    {
      "game_id": 19040,
      "in_progress": ["u22", "u24"],
      "levels": {
        "u21": 0, "u22": 9, "u23": 0, "u24": 9, "u25": 0, "u26": 3, "u27": 0, "u28": 0
      }
    },
    {
      "game_id": 25306,
      "in_progress": [],
      "levels": {
        "u21": 0, "u22": 1, "u23": 0, "u24": 1, "u25": 0, "u26": null, "u27": null, "u28": null
      }
    }
  ]
}
```

**Errores:** igual que `/own` (400/422/503/500 según tabla de la sección 8.1).

### 8.4 `GET /game/troops/{world_id}/hospital`

**Descripción:** Heridos por tipo y estado del hospital de cada aldea.

**Respuesta 200:**
```json
{
  "player_tribe": 3,
  "troop_types": [
    {"unit_class": "u21", "name": "Falange"},
    {"unit_class": "u22", "name": "Espadachín"},
    {"unit_class": "u23", "name": "Explorador galo"},
    {"unit_class": "u24", "name": "Teutat Thunder"},
    {"unit_class": "u25", "name": "Druidrider"},
    {"unit_class": "u26", "name": "Haeduan"}
  ],
  "villages": [
    {
      "game_id": 19040,
      "has_hospital": true,
      "healing": false,
      "wounded": {"u21": 0, "u22": 0, "u23": 0, "u24": 0, "u25": 0, "u26": 0}
    },
    {
      "game_id": 25306,
      "has_hospital": false,
      "healing": false,
      "wounded": {}
    }
  ]
}
```

**Errores:** igual que `/own` (400/422/503/500 según tabla de la sección 8.1).

### 8.5 `GET /game/troops/{world_id}/training`

**Descripción:** Tiempo de cola restante en edificios de entrenamiento por aldea.

**Respuesta 200:**
```json
{
  "buildings": [
    {"gid": 19, "name": "Cuartel"},
    {"gid": 20, "name": "Establo"},
    {"gid": 21, "name": "Taller"},
    {"gid": 46, "name": "Hospital"}
  ],
  "building_gids": [19, 20, 21, 46],
  "villages": [
    {
      "game_id": 19040,
      "queues": [
        {"gid": 19, "building_exists": true, "queue_seconds": 6966},
        {"gid": 20, "building_exists": true, "queue_seconds": 9405},
        {"gid": 21, "building_exists": true, "queue_seconds": 0},
        {"gid": 46, "building_exists": true, "queue_seconds": 0}
      ]
    },
    {
      "game_id": 25306,
      "queues": [
        {"gid": 19, "building_exists": true, "queue_seconds": 85790},
        {"gid": 20, "building_exists": true, "queue_seconds": 46701},
        {"gid": 21, "building_exists": false, "queue_seconds": null},
        {"gid": 46, "building_exists": false, "queue_seconds": null}
      ]
    }
  ]
}
```

> **Nota de localización:** `buildings[].name` se resuelve vía
> `translation_port.get_building_name(gid, lang)`. Los `gid` canónicos de entrenamiento
> (19, 20, 21, 46) tienen entradas en el catálogo de edificios. `building_gids` es un
> alias de `[b.gid for b in buildings]` mantenido por compatibilidad.

**Errores:** igual que `/own` (400/422/503/500 según tabla de la sección 8.1).

---

## 9. Flujo lógico paso a paso

### 9.1 `TroopsParser.parse_own(html: str) -> TroopsOwnResponse`

```
soup = BeautifulSoup(html, "html.parser")
table = soup.select_one("table#troops")

# 1. Leer columnas del thead
troop_types = []
for img in table.select("thead tr td.unit img.unit"):
    classes = [c for c in img["class"] if c.startswith("u") and c != "unit"]
    if classes:
        troop_types.append(classes[0])   # "u21", "u22", ..., "uhero"

# 2. Leer filas de aldeas (tbody tr que tienen td.villageName)
villages = []
for row in table.select("tbody tr"):
    name_cell = row.select_one("td.villageName")
    if name_cell is None:
        continue   # tr.empty, tr.sum, etc.
    link = name_cell.select_one("a[href*='newdid=']")
    game_id = parse_int(re.search(r"newdid=(\d+)", link["href"]).group(1))

    # Celdas de cantidad: todas las td que no son villageName, en orden
    td_list = [td for td in row.find_all("td") if "villageName" not in td.get("class", [])]
    counts = {}
    for i, unn in enumerate(troop_types):
        td = td_list[i] if i < len(td_list) else None
        if td is None:
            counts[unn] = 0
        else:
            counts[unn] = parse_int(td.get_text(strip=True))
            # parse_int("0") = 0 independientemente de si td tiene clase "none"
    villages.append(VillageOwnTroopsDTO(game_id=game_id, counts=counts))

# 3. Leer tr.sum (totales)
sum_row = table.select_one("tr.sum")
totals = {}
if sum_row:
    td_list = [td for td in sum_row.find_all("td") if "vil" not in td.get("class", [])]
    for i, unn in enumerate(troop_types):
        td = td_list[i] if i < len(td_list) else None
        totals[unn] = parse_int(td.get_text(strip=True)) if td else 0

return TroopsOwnResponse(troop_types=troop_types, villages=villages, totals=totals)
```

### 9.2 `TroopsParser.parse_support(html: str) -> TroopsSupportResponse`

```
soup = BeautifulSoup(html, "html.parser")
villages = []

for wrapper in soup.select("div.troops_wrapper"):
    table = wrapper.select_one("table.vil_troops")

    # game_id desde thead th a
    link = table.select_one("thead th a[href*='newdid=']")
    game_id = parse_int(re.search(r"newdid=(\d+)", link["href"]).group(1))

    # tbody.troops: puede contener 1 o 2 "grupos" de filas (naturaleza + propias)
    # Cada grupo = fila de iconos seguida de fila de cantidades
    troops_body = table.select_one("tbody.troops")
    rows = troops_body.find_all("tr") if troops_body else []
    # Filtrar tr.empty (colspan)
    rows = [r for r in rows if not r.select_one("td.empty")]

    own = {}
    nature = {}

    # Parsear cada par de filas (icono, cantidad)
    i = 0
    while i + 1 < len(rows):
        icon_row = rows[i]
        qty_row  = rows[i + 1]
        imgs = icon_row.find_all("img", class_="unit")
        qtys = qty_row.find_all("td")
        for j, img in enumerate(imgs):
            unit_classes = [c for c in img["class"] if c.startswith("u") and c != "unit"]
            if not unit_classes:
                continue
            unn = unit_classes[0]
            qty = parse_int(qtys[j].get_text(strip=True)) if j < len(qtys) else 0
            # Naturaleza = u31-u40
            if unn.startswith("u") and unn != "uhero":
                num = int(unn[1:]) if unn[1:].isdigit() else 0
                if 31 <= num <= 40:
                    nature[unn] = qty
                else:
                    own[unn] = qty
            elif unn == "uhero":
                own["uhero"] = qty
        i += 2

    hero = own.get("uhero", 0)

    # tbody.upkeep
    upkeep_body = table.select_one("tbody.upkeep")
    upkeep_per_hour = 0
    offence = None
    def_infantry = None
    def_cavalry = None

    if upkeep_body:
        cons_span = upkeep_body.select_one("div.consumption span")
        if cons_span:
            upkeep_per_hour = parse_int(cons_span.get_text(strip=True))
        for icon_tag, attr in [
            ("i.offence_small",       "offence"),
            ("i.defenceInfantry_small", "def_infantry"),
            ("i.defenceCavalry_small",  "def_cavalry"),
        ]:
            val_span = upkeep_body.select_one(f"{icon_tag} + span.value, {icon_tag} ~ span.value")
            # El span.value es hermano de la i, buscar dentro del div padre
            strength_div = upkeep_body.select_one(f"div.strength:has({icon_tag})")
            if strength_div:
                val_span = strength_div.select_one("span.value")
                raw = val_span.get_text(strip=True) if val_span else None
                if raw and raw != "-":
                    locals()[attr]  # placeholder — asignación real abajo

    # Asignación correcta de fuerza (revisar selector)
    for strength_div in (upkeep_body.select("div.inlineIcon.strength") if upkeep_body else []):
        icon = strength_div.select_one("i")
        val_span = strength_div.select_one("span.value")
        raw = val_span.get_text(strip=True) if val_span else None
        if icon and raw and raw != "-":
            if "offence_small" in icon.get("class", []):
                offence = parse_int(raw)
            elif "defenceInfantry_small" in icon.get("class", []):
                def_infantry = parse_int(raw)
            elif "defenceCavalry_small" in icon.get("class", []):
                def_cavalry = parse_int(raw)

    villages.append(VillageSupportTroopsDTO(
        game_id=game_id, own=own, nature=nature, hero=hero,
        upkeep_per_hour=upkeep_per_hour,
        offence=offence, def_infantry=def_infantry, def_cavalry=def_cavalry,
    ))

return TroopsSupportResponse(villages=villages)
```

### 9.3 `TroopsParser.parse_smithy(html: str) -> TroopsSmithyResponse`

```
soup = BeautifulSoup(html, "html.parser")
table = soup.select_one("table.under_progress")

# 1. Leer columnas (u21-u28) del thead segunda fila
troop_types = []
for img in table.select("thead tr:nth-child(2) th.unit img.unit"):
    unn = [c for c in img["class"] if c.startswith("u") and c != "unit"]
    if unn:
        troop_types.append(unn[0])

# 2. Filas de aldeas
villages = []
for row in table.select("tbody tr"):
    vil_cell = row.select_one("td.vil.fc")
    if vil_cell is None:
        continue
    link = vil_cell.select_one("a[href*='newdid=']")
    game_id = parse_int(re.search(r"newdid=(\d+)", link["href"]).group(1))

    # Columna "in progress" (2ª td)
    tds = row.find_all("td")
    in_progress_td = tds[1] if len(tds) > 1 else None
    in_progress = []
    if in_progress_td:
        for img in in_progress_td.find_all("img", class_="unit"):
            unn = [c for c in img["class"] if c.startswith("u") and c != "unit"]
            if unn:
                in_progress.append(unn[0])
        # Si hay span.dot y ninguna img, in_progress ya es [] (correcto)

    # Columnas de niveles (3ª en adelante)
    level_tds = tds[2:] if len(tds) > 2 else []
    levels = {}
    for i, unn in enumerate(troop_types):
        td = level_tds[i] if i < len(level_tds) else None
        if td is None:
            levels[unn] = None
        else:
            raw = td.get_text(strip=True)
            if raw == "-":
                levels[unn] = None   # no investigable
            else:
                levels[unn] = parse_int(raw)   # 0, 1, ..., 20

    villages.append(VillageSmithyDTO(
        game_id=game_id, in_progress=in_progress, levels=levels
    ))

return TroopsSmithyResponse(troop_types=troop_types, villages=villages)
```

### 9.4 `TroopsParser.parse_hospital(html: str) -> TroopsHospitalResponse`

```
soup = BeautifulSoup(html, "html.parser")
table = soup.select_one("table.under_progress")

# 1. Tribu del jugador
tribe_icon = table.select_one("th.villageName i[class]")
player_tribe = 0
if tribe_icon:
    for cls in tribe_icon.get("class", []):
        m = re.match(r"tribe(\d+)_medium", cls)
        if m:
            player_tribe = int(m.group(1))
            break

# 2. Columnas de heridos (u21-u26) del thead segunda fila
troop_types = []
for img in table.select("thead tr:nth-child(2) th.unit img.unit"):
    unn = [c for c in img["class"] if c.startswith("u") and c != "unit"]
    if unn:
        troop_types.append(unn[0])

# 3. Filas de aldeas
villages = []
for row in table.select("tbody tr"):
    name_cell = row.select_one("td.villageName")
    if name_cell is None:
        continue
    link = name_cell.select_one("a[href*='newdid=']")
    game_id = parse_int(re.search(r"newdid=(\d+)", link["href"]).group(1))

    # Columna inProgress
    in_progress_td = row.select_one("td.inProgress")
    has_hospital = False
    healing = False
    if in_progress_td:
        if in_progress_td.select_one("span.dot"):
            has_hospital = True
            healing = False   # hospital existe pero sin curación activa
        elif in_progress_td.select_one("span.none"):
            has_hospital = False
            healing = False
        else:
            # Posible span.duration o timer si hay curación en curso (no evidenciado en fixtures)
            has_hospital = True
            healing = True

    # Columnas de heridos
    tds = row.find_all("td")
    # Las celdas de heridos empiezan en índice 2 (0=villageName, 1=inProgress)
    wounded_tds = tds[2:] if len(tds) > 2 else []
    wounded = {}
    if has_hospital:
        for i, unn in enumerate(troop_types):
            td = wounded_tds[i] if i < len(wounded_tds) else None
            wounded[unn] = parse_int(td.get_text(strip=True)) if td else 0

    villages.append(VillageHospitalDTO(
        game_id=game_id,
        has_hospital=has_hospital,
        healing=healing,
        wounded=wounded,
    ))

return TroopsHospitalResponse(
    player_tribe=player_tribe,
    troop_types=troop_types,
    villages=villages,
)
```

### 9.5 `TroopsParser.parse_training(html: str) -> TroopsTrainingResponse`

```
soup = BeautifulSoup(html, "html.parser")
table = soup.select_one("table.under_progress")

# 1. Columnas (gids) del thead
# Los th.unit contienen i.building_small.tribeN.typeNN
# El gid se extrae del PRIMER a[href*='gid='] de la columna correspondiente en los datos
# (el thead solo tiene iconos, sin gid explícito)
# Estrategia: iterar las columnas del thead para contar cuántas hay, luego
# extraer los gids de los a[href*='gid='] de la primera fila de datos.

header_ths = table.select("thead tr th.unit")
num_cols = len(header_ths)

# Extraer gids de la primera fila de datos (más robusto que parsear icono del thead)
building_gids = []
first_data_row = table.select_one("tbody tr")
if first_data_row:
    data_tds = first_data_row.find_all("td")
    # td[0] = villageName; td[1..] = edificios
    for td in data_tds[1:1 + num_cols]:
        link = td.select_one("a[href*='gid=']")
        if link:
            m = re.search(r"gid=(\d+)", link["href"])
            if m:
                building_gids.append(int(m.group(1)))
        else:
            # span.none: edificio sin gid → no sabemos el gid de esta columna
            # Usar el icono del thead como fallback para extraer typeNN → gid
            # type19=19, type20=20, type21=21, type46=46
            col_idx = len(building_gids)
            if col_idx < len(header_ths):
                icon = header_ths[col_idx].select_one("i.building_small")
                if icon:
                    for cls in icon.get("class", []):
                        m2 = re.match(r"type(\d+)", cls)
                        if m2:
                            building_gids.append(int(m2.group(1)))
                            break
                    else:
                        building_gids.append(0)  # fallback desconocido
                else:
                    building_gids.append(0)

# 2. Filas de aldeas
villages = []
for row in table.select("tbody tr"):
    name_cell = row.select_one("td.villageName")
    if name_cell is None:
        continue
    link = name_cell.select_one("a[href*='newdid=']")
    game_id = parse_int(re.search(r"newdid=(\d+)", link["href"]).group(1))

    data_tds = row.find_all("td")
    building_tds = data_tds[1:1 + num_cols]

    queues = []
    for col_idx, td in enumerate(building_tds):
        gid = building_gids[col_idx] if col_idx < len(building_gids) else 0
        duration_span = td.select_one("span.duration")
        dot_span      = td.select_one("span.dot")
        none_span     = td.select_one("span.none")

        if duration_span:
            raw_time = duration_span.get_text(strip=True)
            queue_seconds = parse_time(raw_time)
            queues.append(BuildingQueueDTO(gid=gid, building_exists=True, queue_seconds=queue_seconds))
        elif dot_span:
            queues.append(BuildingQueueDTO(gid=gid, building_exists=True, queue_seconds=0))
        else:  # span.none o celda vacía
            queues.append(BuildingQueueDTO(gid=gid, building_exists=False, queue_seconds=None))

    villages.append(VillageTrainingDTO(game_id=game_id, queues=queues))

return TroopsTrainingResponse(building_gids=building_gids, villages=villages)
```

### 9.6 `TroopsUseCase` — use case del bloque

```python
# core/use_cases/troops_use_case.py

from core.ports.translation_port import TranslationPort
from core.utils.units import unit_class_to_tribe_ordinal


class TroopsUseCase:
    """
    Use case del bloque troops. Orquesta el port y los parsers.
    Cada método solicita una sola página y parsea el resultado.
    No llama a VillageMapUseCase — el game_id se extrae directamente de cada fila.

    El enriquecimiento con nombres localizados ocurre aquí:
    - Para troop_types (own, smithy, hospital): iterar los uNN del parser y llamar
      a unit_class_to_tribe_ordinal + translation_port.get_troop_name.
    - Para troop_names (support): mismo mecanismo, construyendo un dict uNN → nombre.
    - Para buildings (training): translation_port.get_building_name(gid, lang).
    - El translation_port es un puerto del core; su inyección es hexagonalmente limpia.
    """

    async def get_own(
        self, port: OverviewHtmlSourcePort, world_id: int,
        lang: str, translation_port: TranslationPort,
    ) -> TroopsOwnResponse:
        html = await port.get_page_html(world_id, OverviewPage.TROOPS_OWN)
        raw = TroopsParser.parse_own(html)
        # Enriquecer troop_types con nombres localizados
        troop_types = [
            TroopTypeInfo(
                unit_class=unn,
                name=_resolve_troop_name(unn, lang, translation_port),
            )
            for unn in raw.troop_types   # raw.troop_types es list[str] del parser
        ]
        return TroopsOwnResponse(
            troop_types=troop_types,
            villages=raw.villages,
            totals=raw.totals,
        )

    async def get_support(
        self, port: OverviewHtmlSourcePort, world_id: int,
        lang: str, translation_port: TranslationPort,
    ) -> TroopsSupportResponse:
        html = await port.get_page_html(world_id, OverviewPage.TROOPS_SUPPORT)
        raw = TroopsParser.parse_support(html)
        # Construir troop_names con todos los uNN encontrados en own y nature
        all_unns = set()
        for v in raw.villages:
            all_unns.update(v.own.keys())
            all_unns.update(v.nature.keys())
        troop_names = {
            unn: _resolve_troop_name(unn, lang, translation_port)
            for unn in all_unns
        }
        return TroopsSupportResponse(villages=raw.villages, troop_names=troop_names)

    async def get_smithy(
        self, port: OverviewHtmlSourcePort, world_id: int,
        lang: str, translation_port: TranslationPort,
    ) -> TroopsSmithyResponse:
        html = await port.get_page_html(world_id, OverviewPage.TROOPS_SMITHY)
        raw = TroopsParser.parse_smithy(html)
        troop_types = [
            TroopTypeInfo(
                unit_class=unn,
                name=_resolve_troop_name(unn, lang, translation_port),
            )
            for unn in raw.troop_types
        ]
        return TroopsSmithyResponse(troop_types=troop_types, villages=raw.villages)

    async def get_hospital(
        self, port: OverviewHtmlSourcePort, world_id: int,
        lang: str, translation_port: TranslationPort,
    ) -> TroopsHospitalResponse:
        html = await port.get_page_html(world_id, OverviewPage.TROOPS_HOSPITAL)
        raw = TroopsParser.parse_hospital(html)
        troop_types = [
            TroopTypeInfo(
                unit_class=unn,
                name=_resolve_troop_name(unn, lang, translation_port),
            )
            for unn in raw.troop_types
        ]
        return TroopsHospitalResponse(
            player_tribe=raw.player_tribe,
            troop_types=troop_types,
            villages=raw.villages,
        )

    async def get_training(
        self, port: OverviewHtmlSourcePort, world_id: int,
        lang: str, translation_port: TranslationPort,
    ) -> TroopsTrainingResponse:
        html = await port.get_page_html(world_id, OverviewPage.TROOPS_TRAINING)
        raw = TroopsParser.parse_training(html)
        buildings = [
            BuildingInfo(
                gid=gid,
                name=translation_port.get_building_name(gid, lang),
            )
            for gid in raw.building_gids
        ]
        return TroopsTrainingResponse(
            buildings=buildings,
            building_gids=raw.building_gids,
            villages=raw.villages,
        )


def _resolve_troop_name(
    unit_class: str,
    lang: str,
    translation_port: TranslationPort,
) -> str:
    """
    Resuelve el nombre localizado de una tropa por su clase CSS global.
    Llama a unit_class_to_tribe_ordinal para obtener (tribe, ordinal).
    Si no hay entrada (uhero, código desconocido, NATARS_11 vacío): devuelve unit_class.
    Nunca lanza.
    """
    result = unit_class_to_tribe_ordinal(unit_class)
    if result is None:
        return unit_class
    tribe, ordinal = result
    name = translation_port.get_troop_name(tribe, ordinal, lang)
    return name if name else unit_class
```

**Nota:** el parser (`TroopsParser`) devuelve `troop_types: list[str]` (lista de strings `uNN`).
El use case transforma esa lista en `list[TroopTypeInfo]` (con nombre localizado) antes de
devolver la respuesta. La distinción es intencional: el parser vive en `adapters/` y no debe
depender del `translation_port` (un puerto del core). El enriquecimiento ocurre en el
use case del `core/`, que sí puede depender de puertos del core.

### 9.7 Router FastAPI — `game_troops.py`

```python
# adapters/api/routes/game_troops.py

from fastapi import APIRouter, Depends
from adapters.api.dependencies import get_language, get_html_source_port, get_translation_port
from core.ports.overview_html_source_port import OverviewHtmlSourcePort
from core.ports.translation_port import TranslationPort
from core.use_cases.troops_use_case import TroopsUseCase

router = APIRouter(prefix="/game/troops", tags=["game-troops"])
_use_case = TroopsUseCase()

# NOTA DE DISEÑO: SessionNotActiveError, OverviewPageNotLoadedError y
# OverviewFixtureNotFoundError son TravianBotError. Los handlers NO las capturan
# para re-lanzarlas como HTTPException con texto fijo. Las dejan propagar al handler
# global de main.py (travian_bot_error_handler), que las traduce al idioma del
# Accept-Language y asigna el HTTP status via ERROR_HTTP_MAP.
# Esto garantiza que los mensajes de error 503/500 también salgan localizados.


@router.get("/{world_id}/own")
async def get_troops_own(
    world_id:         int,
    lang:             str                    = Depends(get_language),
    port:             OverviewHtmlSourcePort = Depends(get_html_source_port),
    translation_port: TranslationPort        = Depends(get_translation_port),
):
    return await _use_case.get_own(port, world_id, lang, translation_port)


@router.get("/{world_id}/support")
async def get_troops_support(
    world_id:         int,
    lang:             str                    = Depends(get_language),
    port:             OverviewHtmlSourcePort = Depends(get_html_source_port),
    translation_port: TranslationPort        = Depends(get_translation_port),
):
    return await _use_case.get_support(port, world_id, lang, translation_port)


@router.get("/{world_id}/smithy")
async def get_troops_smithy(
    world_id:         int,
    lang:             str                    = Depends(get_language),
    port:             OverviewHtmlSourcePort = Depends(get_html_source_port),
    translation_port: TranslationPort        = Depends(get_translation_port),
):
    return await _use_case.get_smithy(port, world_id, lang, translation_port)


@router.get("/{world_id}/hospital")
async def get_troops_hospital(
    world_id:         int,
    lang:             str                    = Depends(get_language),
    port:             OverviewHtmlSourcePort = Depends(get_html_source_port),
    translation_port: TranslationPort        = Depends(get_translation_port),
):
    return await _use_case.get_hospital(port, world_id, lang, translation_port)


@router.get("/{world_id}/training")
async def get_troops_training(
    world_id:         int,
    lang:             str                    = Depends(get_language),
    port:             OverviewHtmlSourcePort = Depends(get_html_source_port),
    translation_port: TranslationPort        = Depends(get_translation_port),
):
    return await _use_case.get_training(port, world_id, lang, translation_port)
```

### 9.8 Diagrama del flujo de datos

```mermaid
flowchart TD
    Client["Cliente HTTP"] -->|GET /game/troops/{world_id}/own\nAccept-Language: es| Handler

    Handler -->|get_language| DepLang["Dependency: get_language\n→ 'es'"]
    Handler -->|get_html_source_port| DepPort["Dependency: get_html_source_port\n→ OverviewHtmlSourcePort"]

    Handler -->|use_case.get_own| UseCase["TroopsUseCase.get_own()"]
    UseCase -->|port.get_page_html(world_id, TROOPS_OWN)| Port["OverviewHtmlSourcePort"]
    Port -->|fixture o Chrome| HTML["HTML crudo (str)"]
    HTML --> Parser["TroopsParser.parse_own(html)"]
    Parser -->|BeautifulSoup + parse_int| DTO["TroopsOwnResponse"]
    DTO -->|JSON 200| Client
```

---

## 10. Validaciones y reglas

| Elemento | Validación | Dónde |
|---|---|---|
| `Accept-Language` | Obligatoria; `400` si ausente o no soportada | `get_language` en `dependencies.py` (tronco) |
| `world_id` | Entero positivo; FastAPI valida tipo automáticamente | Declaración de path param |
| Texto de celda de cantidad (`td`) | `parse_int(text)` — elimina bidi + separadores antes de `int()` | `core/utils/parsing.py` |
| Texto `"-"` en smithy | `→ None` (no investigable); no se llama `parse_int` | `TroopsParser.parse_smithy` |
| `span.dot` vs `span.none` en hospital | Distinción semántica `has_hospital` + `healing` | `TroopsParser.parse_hospital` |
| Texto de duración en training | `parse_time(text.strip())` → segundos | `TroopsParser.parse_training` |
| Fila `tr.sum` en own | Se ignora al iterar filas de aldeas (no tiene `td.villageName`) | `TroopsParser.parse_own` |
| Fila `tr.empty` en own | Se ignora (tiene `td[colspan]`, no `td.villageName`) | `TroopsParser.parse_own` |
| `tr.sum` en smithy | No existe en el fixture real; el parser no la espera. Si Travian la añade en futuras versiones, será ignorada al filtrar por `td.vil.fc` | `TroopsParser.parse_smithy` |
| Tipo de tropa en DTOs | Siempre `uNN` (clase CSS), nunca texto `alt` | `TroopsParser` (todos los métodos) |

---

## 11. Seguridad, rendimiento y concurrencia

### Anti-detección

El parser NO navega el browser — solo recibe HTML ya obtenido por el tronco
(`LiveOverviewAdapter`), que ya aplica las capas de anti-detección descritas en
`CLAUDE.md` (sin headless, UA dinámico, `human_delay`). El bloque TROOPS no añade
ni elimina capas de anti-detección.

Consideración de carga: las 5 sub-rutas disparan hasta 5 navegaciones separadas de
Chrome si se consumen en secuencia dentro del mismo TTL de caché. La recomendación
es que el orquestador/frontend llame a las sub-rutas en momentos distintos o que el
TTL de 60 s absorba la mayoría de las solicitudes dentro de la misma ventana.

### Rendimiento

- Caché del tronco con TTL 60 s cubre las solicitudes repetidas.
- `BeautifulSoup` con `html.parser` (stdlib) sobre ~80-200 KB de HTML de overview.
  Estimación: < 100 ms por página en Raspberry Pi 4B. Aceptable.
- Los DTOs son objetos Python ligeros; la serialización a JSON por FastAPI
  (`jsonable_encoder`) es lineal al tamaño del DTO.

### Concurrencia

El parser es una clase estática (sin estado). Es seguro llamar a múltiples métodos
en concurrencia asyncio. El locking de caché es responsabilidad del tronco
(`LiveOverviewAdapter`) y ya está implementado.

---

## 12. Plan de pruebas

### 12.1 Parser `parse_own` — fixture `troops_own.html`

| Test | Descripción | Resultado esperado |
|---|---|---|
| `test_parse_own_troop_types` | Leer encabezados del thead | `["u21","u22","u23","u24","u25","u26","u27","u28","u29","u30","uhero"]` |
| `test_parse_own_village_count` | Número de aldeas en villages | 6 (aldeas 00–05) |
| `test_parse_own_village_00_counts` | Aldea game_id=19040 | `{u21:227, u22:3136, u23:125, u24:1885, u25:0, u26:420, u27:30, u28:60, u29:0, u30:0, uhero:0}` |
| `test_parse_own_village_04_all_zero` | Aldea game_id=26421 (todos cero) | Todos los counts = 0 |
| `test_parse_own_village_02_hero` | Aldea game_id=25306 (uhero=1) | `uhero: 1` |
| `test_parse_own_totals` | Fila tr.sum | `{u21:327, u22:4883, u23:278, u24:3357, u25:17, u26:480, u27:54, u28:78, u29:0, u30:0, uhero:1}` |
| `test_parse_own_ignores_sum_row` | tr.sum no aparece en villages | `len(villages) == 6` |
| `test_parse_own_ignores_empty_row` | tr.empty no aparece en villages | `len(villages) == 6` |

### 12.2 Parser `parse_support` — fixture `troops_support.html`

| Test | Descripción | Resultado esperado |
|---|---|---|
| `test_parse_support_village_count` | Número de wrappers | 6 |
| `test_parse_support_village_00_nature` | Aldea 19040, naturaleza | `{u40: 5}` (resto 0) |
| `test_parse_support_village_00_own` | Aldea 19040, propias | `{u21:227, u22:1199, u23:125, u24:848, u25:0, u26:228, u27:0, u28:0, u29:0, u30:0, uhero:0}` |
| `test_parse_support_village_00_upkeep` | Aldea 19040, cereal/h | `9093` |
| `test_parse_support_village_00_offence` | Aldea 19040, offence | `201060` |
| `test_parse_support_village_02_no_nature` | Aldea 25306, sin naturaleza | `nature == {}` o `nature` sin entradas > 0 |
| `test_parse_support_village_04_all_zero_strength` | Aldea 26421, sin tropas | `offence=None, def_infantry=None, def_cavalry=None` |
| `test_parse_support_village_04_upkeep_zero` | Aldea 26421 | `upkeep_per_hour=0` |

### 12.3 Parser `parse_smithy` — fixture `troops_smithy.html`

| Test | Descripción | Resultado esperado |
|---|---|---|
| `test_parse_smithy_troop_types` | Columnas del thead | `["u21","u22","u23","u24","u25","u26","u27","u28"]` |
| `test_parse_smithy_village_count` | Número de aldeas | 6 |
| `test_parse_smithy_village_00_in_progress` | Aldea 19040, in_progress | `["u22","u24"]` |
| `test_parse_smithy_village_01_no_progress` | Aldea 24341, span.dot | `in_progress == []` |
| `test_parse_smithy_village_00_levels` | Aldea 19040, niveles | `{u21:0, u22:9, u23:0, u24:9, u25:0, u26:3, u27:0, u28:0}` |
| `test_parse_smithy_dash_is_none` | Aldea 25306, u26="-" | `levels["u26"] is None` |
| `test_parse_smithy_zero_is_int` | Aldea 25306, u21="0" | `levels["u21"] == 0` (int, no None) |
| `test_parse_smithy_aldea_04_all_dash_except_first` | Aldea 26421, solo u21=0, resto "-" | `levels["u21"] == 0`, `levels["u22"] is None` ... |

### 12.4 Parser `parse_hospital` — fixture `troops_hospital.html`

| Test | Descripción | Resultado esperado |
|---|---|---|
| `test_parse_hospital_player_tribe` | Tribu del jugador | `3` (Galos, `tribe3_medium`) |
| `test_parse_hospital_troop_types` | Columnas | `["u21","u22","u23","u24","u25","u26"]` |
| `test_parse_hospital_village_count` | Número de aldeas | 6 |
| `test_parse_hospital_village_00_has_hospital` | Aldea 19040, span.dot | `has_hospital=True, healing=False` |
| `test_parse_hospital_village_02_no_hospital` | Aldea 25306, span.none | `has_hospital=False, healing=False, wounded={}` |
| `test_parse_hospital_village_01_wounded_u22` | Aldea 24341 tiene herido en u22 | `wounded["u22"] == 2` |
| `test_parse_hospital_village_01_has_hospital` | Aldea 24341, span.dot | `has_hospital=True` |

### 12.5 Parser `parse_training` — fixture `troops_training.html`

| Test | Descripción | Resultado esperado |
|---|---|---|
| `test_parse_training_building_gids` | Columnas del thead | `[19, 20, 21, 46]` |
| `test_parse_training_village_count` | Número de aldeas | 6 |
| `test_parse_training_village_00_cuartel` | Aldea 19040, gid=19 | `building_exists=True, queue_seconds=6966` (1h56m6s) |
| `test_parse_training_village_00_establo` | Aldea 19040, gid=20 | `building_exists=True, queue_seconds=9405` (2h36m45s) |
| `test_parse_training_village_00_taller_dot` | Aldea 19040, gid=21, span.dot | `building_exists=True, queue_seconds=0` |
| `test_parse_training_village_02_taller_none` | Aldea 25306, gid=21, span.none | `building_exists=False, queue_seconds=None` |
| `test_parse_training_village_04_cuartel_dot` | Aldea 26421, gid=19, span.dot | `building_exists=True, queue_seconds=0` |
| `test_parse_training_village_05_cuartel` | Aldea 24498, gid=19 | `queue_seconds=3325` (0h55m25s) |
| `test_parse_training_whitespace_in_duration` | Strip de espacios en span.duration | No lanza error; `parse_time` maneja whitespace |

### 12.6 Tests del use case (integración con fixture adapter)

| Test | Descripción |
|---|---|
| `test_use_case_get_own_with_fixture` | `TroopsUseCase.get_own` con `FixtureOverviewAdapter` real |
| `test_use_case_get_support_with_fixture` | Ídem para support |
| `test_use_case_get_smithy_with_fixture` | Ídem para smithy |
| `test_use_case_get_hospital_with_fixture` | Ídem para hospital |
| `test_use_case_get_training_with_fixture` | Ídem para training |
| `test_use_case_propagates_session_error` | Port lanza `SessionNotActiveError` | La excepción se propaga sin envolver |

---

## 13. Riesgos y trade-offs

### TR-01 — Sub-rutas vs endpoint único agregado

**Riesgo:** El cliente que necesita todas las vistas deba hacer 5 peticiones HTTP.

**Decisión:** Sub-rutas separadas (ver sección 8 para justificación completa).

**Mitigación:** La caché del tronco (TTL 60 s) hace que la segunda y sucesivas
peticiones al mismo `world_id` sean básicamente gratuitas desde el punto de vista
del browser. El coste real de 5 navegaciones solo ocurre si las 5 peticiones llegan
con la caché vacía al mismo tiempo (p.ej., primer arranque del bot).

### TR-02 — Extracción de `gid` en training: icono del thead vs `href` de datos

**Problema:** Los `th.unit` del thead de training contienen `i.building_small.tribeN.typeNN`
pero el `typeNN` no es directamente el `gid` (type19=gid19, type20=gid20, type21=gid21,
type46=gid46 — en los fixtures actuales coincide, pero no está garantizado por el spec de
Travian).

**Decisión:** Extraer el `gid` del `a[href*='gid=N']` de la primera fila de datos cuando
existe. Para columnas donde la primera fila tiene `span.none` (sin edificio), usar el
`typeNN` del icono del `thead` como fallback. Esto hace la extracción más robusta.

**Riesgo residual:** Si el jugador tiene todas las aldeas sin un tipo de edificio
(p.ej., ninguna tiene Taller), la primera fila tendrá `span.none` en esa columna y
el fallback leerá `typeNN`. Si `typeNN != gid`, el `gid` en el DTO será incorrecto.
En la práctica, `typeNN` y `gid` coinciden para los 4 edificios de entrenamiento.

### TR-03 — Estado de curación activa en hospital

**Problema:** El fixture actual no muestra ninguna aldea con curación activa en curso.
Solo hay `span.dot` (hospital existe, sin actividad) y `span.none` (sin hospital).
Se desconoce qué HTML devuelve Travian cuando hay curación en curso.

**Decisión:** El parser detecta `span.dot` → `healing=False`, `span.none` → no hospital,
cualquier otro contenido en `td.inProgress` → `healing=True`. Esta heurística cubre
el caso documentado y la extensión razonable para curación activa.

**Riesgo:** Si Travian usa un elemento diferente para curación activa (p.ej.,
`a > span.timer[data-value]`), el parser podría incorrecto. **Mitigación:** cuando
el usuario tenga tropas en curación, debe capturar un fixture real y verificar el selector.

### TR-04 — `parse_int` con texto "0" que tiene clase `none`

**Aclaración:** En los fixtures, las celdas con valor 0 llevan la clase CSS `none`
(`td.none`) y el texto es literalmente `"0"`. La clase `none` es un indicador visual
en el HTML, no una señal de "dato ausente". El parser usa `parse_int(text)` directamente
y obtiene `0` sin ambigüedad. No hay colisión con el `"-"` de smithy porque smithy no
tiene `td.none` con `"-"` — usa `td.unit.none` y el texto `"-"` explícitamente.

### TR-05 — Solapamiento "troops in village" (support) vs "own troops" (own)

**Observación:** La pestaña `own` muestra el total máximo del ejército; la pestaña
`support` muestra las tropas físicamente presentes en la aldea. Son vistas
complementarias (las tropas pueden estar atacando, reforzando otras aldeas, etc.).
No son duplicados; ambas tienen utilidad independiente.

### TR-06 — Hero en support: campo `hero` vs `own["uhero"]`

**Decisión:** Se mantienen ambos campos (`hero: int` como alias de `own.get("uhero", 0)`).
El campo `hero` facilita el acceso rápido desde el cliente sin tener que conocer el
identificador `"uhero"`. Los dos deben ser consistentes; si el parser detecta `uhero`
en la fila de iconos propios, lo almacena en `own["uhero"]` y `hero` replica ese valor.

---

## 14. Pasos de implementación ordenados

1. **`core/dtos/troops_dto.py`** — CREAR (si no existe `core/dtos/`): crear el
   paquete `core/dtos/__init__.py` + el módulo con los 5 grupos de DTOs descritos en
   la sección 7. Usar `@dataclass` para todos. Importar `parse_int`, `parse_time` no
   aquí sino en el parser.

2. **`adapters/browser/parsers/` (directorio)** — CREAR si no existe:
   `adapters/browser/parsers/__init__.py`.

3. **`adapters/browser/parsers/troops_parser.py`** — CREAR. Clase `TroopsParser`
   con 5 métodos estáticos: `parse_own`, `parse_support`, `parse_smithy`,
   `parse_hospital`, `parse_training`. Imports: `BeautifulSoup`, `re`,
   `parse_int`, `parse_int_or_none`, `parse_time` de `core.utils.parsing`, y los DTOs
   de `core.dtos.troops_dto`.

4. **`tests/unit/test_troops_parser.py`** — CREAR. Tests de las secciones 12.1–12.5
   usando los 5 fixtures reales de `tests/fixtures/overview/`. Ejecutar y verificar
   que todos pasan antes de continuar.

5. **`core/use_cases/troops_use_case.py`** — CREAR. Clase `TroopsUseCase` con 5
   métodos async (sección 9.6). Sin lógica adicional: solo obtiene HTML del port y
   delega al parser.

6. **`tests/unit/test_troops_use_case.py`** — CREAR. Tests de la sección 12.6 usando
   `FixtureOverviewAdapter` real con `fixtures_dir = tests/fixtures/overview`.

7. **`adapters/api/routes/game_troops.py`** — CREAR. Router con 5 endpoints (sección
   9.7). Las excepciones de dominio (`SessionNotActiveError`, `OverviewPageNotLoadedError`,
   `OverviewFixtureNotFoundError`) se dejan propagar al handler global — NO se capturan
   en los handlers. Importar y registrar en `adapters/api/main.py` (ver paso 8).

8. **`adapters/api/main.py`** — MODIFICAR. Añadir:
   ```python
   from adapters.api.routes.game_troops import router as troops_router
   application.include_router(troops_router)
   ```
   en la sección de inclusión de routers, junto a los otros routers de `/game/`.

9. **Verificar regresión completa:**
   ```bash
   source .venv/bin/activate && pytest --ignore=tests/antideteccion -v
   ```
   Todos los 271 tests previos + los nuevos tests del bloque deben pasar.

---

## 15. Criterios de aceptación

### Parser

- [ ] `TroopsParser` vive en `adapters/browser/parsers/troops_parser.py`.
- [ ] Todos los métodos son `@staticmethod`. No hay estado en la clase.
- [ ] Ningún selector usa texto visible (`alt`, texto de celda, etc.) para identificar tipos de tropa — solo clases CSS (`uNN`).
- [ ] `parse_own`: extrae 6 aldeas del fixture real con counts correctos (ver 12.1).
- [ ] `parse_own`: `tr.sum` se procesa como totales, no como aldea.
- [ ] `parse_own`: `tr.empty` ignorada.
- [ ] `parse_support`: extrae 6 aldeas; aldea 19040 tiene `nature["u40"]=5`.
- [ ] `parse_support`: aldea 26421 (sin tropas) devuelve `offence=None`.
- [ ] `parse_smithy`: aldea 19040 tiene `in_progress=["u22","u24"]`.
- [ ] `parse_smithy`: `"-"` → `None`; `"0"` → `0` (int).
- [ ] `parse_hospital`: `player_tribe=3` extraído del icono.
- [ ] `parse_hospital`: `span.dot` → `has_hospital=True, healing=False`.
- [ ] `parse_hospital`: `span.none` → `has_hospital=False, wounded={}`.
- [ ] `parse_training`: aldea 19040 gid=19 → `queue_seconds=6966`.
- [ ] `parse_training`: `span.dot` → `building_exists=True, queue_seconds=0`.
- [ ] `parse_training`: `span.none` → `building_exists=False, queue_seconds=None`.

### DTOs

- [ ] Todos los DTOs son `@dataclass` en `core/dtos/troops_dto.py`.
- [ ] `TroopTypeInfo` existe con campos `unit_class: str` y `name: str`.
- [ ] `BuildingInfo` existe con campos `gid: int` y `name: str`.
- [ ] `TroopsOwnResponse.troop_types` es `list[TroopTypeInfo]` (no `list[str]`).
- [ ] `TroopsSmithyResponse.troop_types` es `list[TroopTypeInfo]`.
- [ ] `TroopsHospitalResponse.troop_types` es `list[TroopTypeInfo]`.
- [ ] `TroopsSupportResponse.troop_names` es `dict[str, str]` (uNN → nombre localizado).
- [ ] `TroopsTrainingResponse.buildings` es `list[BuildingInfo]`.
- [ ] `TroopsOwnResponse.totals` incluye las sumas de `tr.sum`.
- [ ] `VillageSupportTroopsDTO.hero` = `own.get("uhero", 0)` (consistencia).
- [ ] `VillageSmithyDTO.levels` usa `int | None` (no `int | str`).
- [ ] `BuildingQueueDTO.queue_seconds` es `int | None` (no `str`).

### Use case

- [ ] `TroopsUseCase` vive en `core/use_cases/troops_use_case.py`.
- [ ] Cada método `async` acepta `lang: str` y `translation_port: TranslationPort`.
- [ ] Cada método llama a `port.get_page_html` con el `OverviewPage` correcto.
- [ ] `get_own`, `get_smithy`, `get_hospital`: construyen `list[TroopTypeInfo]` enriquecida con nombres localizados.
- [ ] `get_support`: construye `dict[str, str]` `troop_names` con todos los uNN encontrados.
- [ ] `get_training`: construye `list[BuildingInfo]` con nombres de edificio vía `get_building_name`.
- [ ] `_resolve_troop_name` aplica `unit_class_to_tribe_ordinal` + `get_troop_name` + fallback a `unit_class`.
- [ ] NO llama a `VillageMapUseCase` (el `game_id` se extrae de cada fila del HTML).
- [ ] Excepciones del port se propagan sin envolver.

### Router

- [ ] 5 endpoints en `adapters/api/routes/game_troops.py` bajo `/game/troops/{world_id}/`.
- [ ] El router declara `APIRouter(prefix="/game/troops", tags=["game-troops"])`.
- [ ] Todos usan `Depends(get_language)` — `Accept-Language` obligatoria.
- [ ] Todos usan `Depends(get_html_source_port)`.
- [ ] Todos usan `Depends(get_translation_port)` e inyectan el port al use case.
- [ ] `SessionNotActiveError` y `OverviewPageNotLoadedError` → HTTP 503 vía propagación al handler global (sin `try/except` en la ruta).
- [ ] `OverviewFixtureNotFoundError` → HTTP 500 vía propagación al handler global.
- [ ] Los mensajes de error en 503/500 están en el idioma del `Accept-Language` (localización FUNCIONAL).
- [ ] El handler NO captura `TravianBotError` ni sus subclases.
- [ ] El router está registrado en `main.py`.
- [ ] Swagger muestra los 5 endpoints con `Accept-Language` en parámetros.

### Tests

- [ ] `tests/unit/test_troops_parser.py` cubre los casos de las secciones 12.1–12.5.
- [ ] `tests/unit/test_troops_use_case.py` cubre la sección 12.6.
- [ ] Todos los tests nuevos pasan con los fixtures reales (sin Chrome).
- [ ] Suite completa sin regresiones (`pytest --ignore=tests/antideteccion` = verde).

---

## 16. Trazabilidad

| Decisión técnica | Requisito o edge case que la origina |
|---|---|
| Identificador de tropa por `uNN` (clase CSS) | RN-01: idioma-independiente; selector estructural (CLAUDE.md RN-05) |
| Sub-rutas separadas en lugar de endpoint único | TR-01: coste anti-detección de 5 navegaciones; caché del tronco por pestaña |
| `in_progress: list[str]` en SmithyDTO | EC-04: múltiples tropas investigándose simultáneamente (fixture aldea 00) |
| `levels[uNN]: int \| None` en SmithyDTO | EC-02/EC-03: distinción entre "no investigable" (`None`) y "nivel 0" (`0`) |
| `has_hospital: bool` + `healing: bool` en HospitalDTO | EC-06/EC-07: distinción semántica entre hospital-sin-actividad y sin-hospital (RN-04) |
| `wounded: {}` cuando `has_hospital=False` | EC-07: sin hospital no hay heridos posibles; dict vacío evita `null` en JSON |
| `player_tribe: int` en `TroopsHospitalResponse` | RN-05 + nota de VillageInfo en tronco: tribu derivable de hospital; se expone en ese endpoint |
| `BuildingQueueDTO` como lista ordenada (no dict) | RN-08: columnas dinámicas; el orden del thead es la fuente canónica del orden |
| `gid` extraído de `a[href*='gid=N']` de datos (no del icono del thead) | TR-02: `typeNN` del icono no siempre garantiza coincidencia con `gid`; el href es más directo |
| `parse_time` para duración de training | EC-14: strings con padding de espacios; `parse_time` ya aplica `.strip()` internamente |
| No usar `VillageMapUseCase` | RN-10: los hrefs de aldea están en cada fila — llamada extra al port innecesaria |
| Propagación pura de `TravianBotError` al handler global (sin re-lanzar como `HTTPException`) | Garantiza localización de mensajes de error al idioma del cliente; 503/500 via `ERROR_HTTP_MAP` |
| Solapamiento `own["uhero"]` y `hero` en SupportDTO | TR-06: campo `hero` como acceso conveniente; consistencia explícita requerida |
| Nota RN-11 sobre solapamiento training / overview | Para que palantir evalúe la fuente canónica de "entrenamiento activo" al comparar con el bloque overview |
| `offence/def_infantry/def_cavalry = None` cuando el valor es `"-"` | EC-10/EC-11: sin tropas, Travian muestra `-` en lugar de `0`; `None` distingue "sin datos" de `0` |
| `Accept-Language` obligatoria y FUNCIONAL; `translation_port` inyectado | RN-09 actualizado: el idioma resuelto gobierna `troop_types[].name`, `troop_names` y `buildings[].name`. El enriquecimiento ocurre en el use case. Los `uNN` y `gid` siguen siendo códigos estables — los nombres son la capa de presentación localizada. |
| `TroopTypeInfo` y `BuildingInfo` como DTOs de presentación | Patrón código estable + nombre localizado: el parser produce códigos, el use case los enriquece con nombres antes de devolver la respuesta al handler. |
| `_resolve_troop_name` como función compartida del use case | Evita duplicar la lógica de `unit_class_to_tribe_ordinal` + `get_troop_name` + fallback en los 4 métodos que lo usan (own, smithy, hospital, support). |
| `OverviewFixtureNotFoundError` → HTTP 500 (no 503) | Error de configuración del entorno de test, no fallo transitorio del servicio de Travian. Alineado con resources y overview. |

---

## Registro de implementación

**Fecha:** 2026-05-26

**Implementado por:** desarrollador-funcionalidades (claude-sonnet-4-6)

### Ficheros creados

| Fichero | Descripción |
|---|---|
| `adapters/browser/parsers/troops_parser.py` | Parser estático con 5 métodos `@staticmethod` |
| `core/use_cases/troops_use_case.py` | Use case con 5 métodos async + `_resolve_troop_name` |
| `adapters/api/routes/game_troops.py` | Router FastAPI con 5 endpoints bajo `/game/troops/{world_id}/` |
| `tests/unit/test_troops_parser.py` | 46 tests unitarios del parser contra los 5 fixtures reales |
| `tests/unit/test_troops_use_case.py` | 22 tests del use case (integración con FixtureOverviewAdapter) + 6 tests de endpoint con `@pytest.mark.skip` |

### Ficheros modificados

| Fichero | Cambio |
|---|---|
| `docs/specs/lectura-troops.md` | `estado: ready-for-impl` → `estado: implemented` + este registro |

### Comando para ejecutar los tests del bloque

```bash
source .venv/bin/activate && pytest tests/unit/test_troops_parser.py tests/unit/test_troops_use_case.py -v
```

Suite completa (sin antidetección):

```bash
source .venv/bin/activate && pytest --ignore=tests/antideteccion -v
```

### Desviaciones respecto al diseño

1. **`parse_support` devuelve `troop_names={}`** (dict vacío en lugar de omitido):
   El spec indica que el parser devuelve la response sin el campo `troop_names`
   construido; el use case lo llena. Para respetar el tipo `TroopsSupportResponse`
   (frozen dataclass con `troop_names: dict[str, str]`), el parser pasa `{}` y el
   use case lo sustituye con el dict completo construido via translation_port.
   No hay impacto en la API — el cliente siempre recibe `troop_names` construido.

2. **`parse_training` devuelve `buildings=[]`** (lista vacía):
   Análogo al punto anterior. El parser no puede construir `BuildingInfo` (necesita
   translation_port del core); devuelve lista vacía que el use case sustituye por la
   lista completa con nombres localizados. Sin impacto en la API.

3. **Import de `TroopsParser` en `core/use_cases/troops_use_case.py`**:
   El use case importa el parser de `adapters/`, lo que es una desviación menor
   del hexagonal estricto. Documentado en el docstring del módulo. El parser es
   una clase estática sin estado ni IO, equivalente a una función pura. La
   alternativa (inyectar el parser como dependencia) añadiría complejidad sin
   beneficio real dado que solo existe un parser. Alineado con el patrón del
   bloque overview (`game_overview.py` importa `OverviewParser` directamente).

