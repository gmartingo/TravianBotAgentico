---
id: lectura-overview
titulo: "Lectura de overview Travian — bloque overview"
estado: implemented
fecha: 2026-05-26
autor: analista
apis_validadas_por_desarrollador_apis: true
revisado_localizacion_por_desarrollador_apis: 2026-05-26
---

# Lectura de overview Travian — bloque overview

---

## 1. Objetivo de negocio

Exponer via API REST el estado resumido de todas las aldeas del jugador tal como aparece
en la pestaña Overview de Travian (`/village/statistics/overview`): movimientos de tropas
activos (refuerzos, ataques propios), edificios en construcción, tropas presentes
destacadas y mercaderes libres/totales.

Este es un **resumen de estado** por aldea, no un detalle exhaustivo. El detalle de
entrenamiento real, tropas completas, recursos y puntos de cultura los cubren los
otros tres bloques (troops, resources, culture-points). El bloque overview es la
"vista de control" rápida que el bot consulta para saber qué está pasando en cada aldea
sin tener que visitar cuatro pestañas.

---

## 2. Actores y permisos

| Actor | Rol |
|---|---|
| Bot (use cases futuros de automatización) | Consumidor principal: lee el estado agregado para decidir acciones |
| Dashboard React (frontend) | Consumidor secundario: muestra el estado de aldeas en la UI |
| `OverviewHtmlSourcePort` | Abstracción que provee el HTML (implementada por el tronco) |
| `FixtureOverviewAdapter` | Implementación de test; usada en todos los tests de este bloque |
| `LiveOverviewAdapter` | Implementación de producción; navega Travian con Chrome autenticado |
| FastAPI / `get_html_source_port` | Inyecta el port al handler via dependency del tronco |

No hay control de acceso diferenciado en esta fase. La autenticación/autorización de
quién puede consultar qué cuenta es responsabilidad de una capa superior futura.

---

## 3. Alcance

### Dentro de alcance

- Parser `OverviewParser` en `adapters/browser/parsers/overview_parser.py` que extrae,
  de la tabla `#overview`, los datos de las cuatro columnas: movimientos (`td.att`),
  construcción (`td.bui`), tropas presentes (`td.tro`) y mercaderes (`td.tra`).
- DTO `OverviewVillageDTO` y contenedor `OverviewResponseDTO` en `core/dtos/overview_dto.py`.
- Use case `OverviewUseCase` en `core/use_cases/overview_use_case.py` que orquesta:
  `VillageMapUseCase` para el índice de aldeas + `OverviewParser` para los datos de
  cada aldea.
- Endpoint `GET /game/overview/{world_id}` en `adapters/api/routes/game_overview.py`.
- Tests contra `overview.html` (sin Chrome) via `FixtureOverviewAdapter`.

### Fuera de alcance

- Detalle de entrenamiento de tropas (lo cubre el bloque troops).
- Producción de recursos ni almacenamiento (lo cubre el bloque resources).
- Puntos de cultura ni fiestas activas (lo cubre el bloque culture-points).
- Coordenadas de aldea (placeholder `x=0, y=0` — lo cubre el bloque World Map).
- Definición de la fuente canónica de mercaderes entre overview y resources: este bloque
  los expone tal como los muestra la tabla `#overview`; la decisión de fuente canónica
  queda pendiente para palantir/coordinador (ver sección 13 — RI-01).
- Autenticación / autorización de endpoints.
- Implementación de `SessionRegistry` / browser vivo (diferido, ya cubierto por tronco TR-01).

---

## 4. Reglas de negocio

**RN-01 — Fuente única: `OverviewPage.OVERVIEW`:**
Todo el contenido de este bloque proviene de una sola página agregada
(`/village/statistics/overview`, fixture `overview.html`). No se navegan páginas
adicionales para construir la respuesta.

**RN-02 — El índice de aldeas lo provee `VillageMapUseCase`:**
La lista de aldeas (game_id, nombre) se obtiene del `VillageMapUseCase` del tronco.
El parser de este bloque no re-extrae aldeas: mapea los datos de las columnas
al `game_id` extraído por el índice. Esto garantiza consistencia entre bloques.

**RN-03 — Movimientos genéricos por clase de imagen:**
El tipo de movimiento va en la clase CSS del `<img>` dentro de `td.att`
(`def1`, `att2`, etc.). La cantidad va en el prefijo del atributo `alt` (ej: `"618x ..."`).
El parser captura genéricamente TODOS los `img` dentro de `td.att`: nunca hardcodea
solo `def1` y `att2`. Clases nuevas (ej. ataque enemigo entrante) se parsean
automáticamente aunque no estén en el fixture actual.

**RN-04 — Ausencia de movimientos/construcción/tropas vía `span.none`:**
Si una columna está vacía el HTML contiene `<span class="none">-</span>` en vez de
imágenes. El parser reconoce este patrón y devuelve lista vacía (no null, no error).

**RN-05 — Construcción: número de edificios, no el nombre:**
El usuario pide cuántos edificios hay en obra, no el nombre (que está en `alt` y es
idioma-dependiente). El conteo de `img.bau` es el dato canónico. El `alt` se expone
opcionalmente como `building_name` para facilitar el debugging, pero no es fiable
entre idiomas y no es el campo principal.

**RN-06 — Tropas: imagen `img.unit.uNN`, tipo siempre por clase:**
El tipo de tropa SIEMPRE se determina por la clase `uNN` del `<img>`. NUNCA por el
`alt` (que es idioma-dependiente, ej: "Swordsman" vs "Espadachín"). La cantidad va en
el prefijo numérico del `alt` (ej: `"71x Swordsman"` → 71).

**RN-07 — Mercaderes: parseo con `parse_int` limpiando bidi:**
El texto de `td.tra` es `"‭‭14‬/‭14‬‬"` (con caracteres de control bidi U+202D/U+202C).
`parse_int` del tronco (`core/utils/parsing.py`) los elimina antes de convertir.
Formato: `"libres/totales"`. Si la celda no tiene enlace (`<a>`) sino `<span>` directamente
(aldea sin mercado, ej: `game_id=26421` → `"‭‭0‬/‭0‬‬"`), el parser también lo lee correctamente.

**RN-08 — `Accept-Language` obligatoria y FUNCIONAL:**
El endpoint usa `get_language` (no `get_language_optional`). Si falta la cabecera → `400`.
El idioma resuelto GOBIERNA la respuesta:
- Cada tropa presente (`TroopPresentDTO`) lleva `unit_class` (código estable, p.ej. `"u22"`)
  **Y** `name` (nombre localizado al idioma pedido, p.ej. `"Espadachín"` para `es`).
- Cada edificio en construcción (`BuildingInProgressDTO`) lleva `gid` (cuando disponible)
  **Y** `name` (nombre localizado vía `get_building_name(gid, lang)`). Si el `gid` no
  está disponible (overview solo tiene el `alt` del servidor), `gid` es `null` y `name`
  es el `alt` crudo del servidor marcado como `"server_lang"` en el campo `name_source`.
- El idioma se propaga al use case como parámetro `lang` y al `translation_port` para
  resolver los nombres. El `translation_port` es un puerto del core; su inyección no
  viola hexagonal.

**RN-09 — La tabla `#overview` no tiene `tr.sum`:**
Verificado en el fixture: la tabla overview no incluye fila de totales (`tr.sum`).
Solo tiene filas de aldea con `td.vil.fc`. El parser no necesita ignorar `tr.sum`.
(Contrasta con la tabla `#ressources` que sí tiene `tr.sum`.)

**RN-10 — Aldea del fixture `game_id=26421` es el caso base vacío:**
Esta aldea del fixture tiene `span.none` en las tres columnas (att, bui, tro) y
`"0/0"` en mercaderes. Es el caso de una aldea sin actividad. El parser debe producir
listas vacías y `merchants_free=0, merchants_total=0`.

---

## 5. Flujo principal y flujos alternativos

### Flujo principal

```
Cliente HTTP
  └─> GET /game/overview/{world_id}   Accept-Language: es
        └─> FastAPI handler (game_overview.py)
              ├─ get_language(...)             → "es"
              ├─ get_html_source_port(...)     → OverviewHtmlSourcePort
              └─> OverviewUseCase.execute(port, world_id, lang, translation_port)
                    ├─> VillageMapUseCase.execute(port, world_id)
                    │     └─> port.get_page_html(world_id, OverviewPage.OVERVIEW)
                    │           └─ [caché hit/miss] → HTML de /village/statistics/overview
                    │     └─ VillageOverviewParser.extract_villages(html) → list[VillageInfo]
                    ├─> port.get_page_html(world_id, OverviewPage.OVERVIEW)
                    │     └─ [caché hit] → mismo HTML (TTL no expirado)
                    └─> OverviewParser.extract_overview_data(html) → list[OverviewVillageRaw]
                    └─> merge VillageInfo + OverviewVillageRaw por game_id
                    └─> devuelve OverviewResponseDTO
              └─> serializar JSON 200
```

**Nota de optimización:** El use case llama a `port.get_page_html` dos veces (una para
`VillageMapUseCase` y otra para `OverviewParser`). Como ambas usan `OverviewPage.OVERVIEW`
con el mismo `world_id`, la caché del `LiveOverviewAdapter` garantiza que la segunda
llamada es un hit inmediato. Sin coste adicional de navegación. El diseño mantendrá
la separación de responsabilidades aunque esto implique dos llamadas al port.

**Alternativa evaluada:** pasar el HTML ya obtenido directamente al `VillageMapUseCase`
y al parser. Rechazada porque acoplaría el use case de overview a la lógica interna del
port. La caché hace que el coste sea irrelevante.

### Flujo alternativo A — sesión no activa

```
OverviewUseCase.execute(...)
  └─> port.get_page_html(...) → SessionNotActiveError (se propaga)
        └─ handler global TravianBotError: 503, detail en el idioma del Accept-Language
```

### Flujo alternativo B — fixture no encontrado (modo fixture)

```
OverviewUseCase.execute(...)
  └─> port.get_page_html(...) → OverviewFixtureNotFoundError (se propaga)
        └─ handler global TravianBotError: 500, detail en el idioma del Accept-Language
```

### Flujo alternativo C — aldea sin actividad

```
OverviewParser.extract_overview_data(html)
  └─ fila con span.none en td.att → movements = []
  └─ fila con span.none en td.bui → buildings_under_construction = []
  └─ fila con span.none en td.tro → troops_present = []
  └─ td.tra con "0/0" → merchants_free=0, merchants_total=0
```

---

## 6. Edge cases

| ID | Caso | Tratamiento esperado |
|---|---|---|
| EC-01 | `td.att` contiene `span.none` | `movements = []` |
| EC-02 | `td.bui` contiene `span.none` | `buildings_under_construction = []` |
| EC-03 | `td.tro` contiene `span.none` | `troops_present = []` |
| EC-04 | `td.tra` texto `"0/0"` (sin enlace, con `<span>`) | `merchants_free=0, merchants_total=0` |
| EC-05 | `td.att` contiene clases `img` no vistas en el fixture (`att1`, `def2`, etc.) | Parsear genéricamente: clase → tipo, prefijo numérico del `alt` → cantidad. NO ignorar. Documentar en este spec las clases vistas y marcar otras como "a confirmar" |
| EC-06 | `alt` de `img.att`/`img.def` con prefijo `"Nx ..."` pero N=0 | Incluir el movimiento con cantidad 0 (caso real si Travian lo emite) |
| EC-07 | `alt` de `img.unit.uNN` sin prefijo numérico reconocible | `parse_int_or_none(prefijo)` → None; loggear warning; omitir esa tropa de la lista |
| EC-08 | `td.tra` sin `<a>` ni `<span>` (celda vacía inesperada) | `merchants_free=0, merchants_total=0`; loggear warning |
| EC-09 | Número de mercaderes con bidi: `"‭‭14‬/‭14‬‬"` | `parse_int` elimina U+202D/U+202C antes de convertir — ya cubre el tronco |
| EC-10 | `game_id` presente en parser de datos pero ausente en índice `VillageMapUseCase` | Incluirlo con `name=""` y loggear warning (rotura de consistencia, no error fatal) |
| EC-11 | `game_id` presente en índice pero sin fila en parser | Devolver la aldea con todos los campos vacíos / 0; no omitirla |
| EC-12 | HTML con 0 filas de aldea (cuenta nueva) | `OverviewResponseDTO.villages = []`; respuesta `200` con lista vacía |
| EC-13 | Múltiples `img.bau` en `td.bui` | `buildings_under_construction` es lista con un elemento por `img.bau`; longitud = N edificios en obra |
| EC-14 | `td.tra` con enlace `<a>` (aldea con mercado, texto bidi) | Leer el texto del `<a>`, limpiar bidi, dividir por `/` |
| EC-15 | Texto de mercaderes con más de un `/` (ej: `"1/2/3"`) | Usar solo el primero y el último token: `free = tokens[0]`, `total = tokens[-1]`; loggear warning |
| EC-16 | `SessionNotActiveError` propagada desde el port | Se propaga al handler global → `503`, detail en el idioma del cliente |
| EC-17 | `OverviewFixtureNotFoundError` propagada desde el port | Se propaga al handler global → `500`, detail en el idioma del cliente |

### Tipos de movimiento observados en el fixture (`td.att img`)

| Clase CSS | `alt` (idioma servidor) | Interpretación | Estado |
|---|---|---|---|
| `def1` | `"Nx Arriving reinforcing troops"` | Refuerzos llegando (propios o aliados) | Verificado en fixture |
| `att2` | `"Nx Own attacking troops"` | Tropas propias en ataque / salidas | Verificado en fixture |
| `att1` | — | Ataque enemigo entrante (hipótesis) | **A confirmar con HTML real** |
| `def2` | — | Refuerzos saliendo (hipótesis) | **A confirmar con HTML real** |
| `att3`, `def3`, etc. | — | Posibles variantes (intercepción, exploración…) | **A confirmar con HTML real** |

El parser debe capturar genéricamente TODOS los `img` dentro de `td.att` sin filtrar por
clase conocida. Cuando se capture HTML real con ataques/atracos entrantes, actualizar
esta tabla.

---

## 7. Modelo de datos / cambios de esquema

No se modifica ninguna tabla SQLite. Los datos son efímeros (parseados del HTML cacheado en memoria).

### 7.1 DTOs de respuesta

```python
# core/dtos/overview_dto.py

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TroopMovementDTO:
    """
    Un movimiento de tropas activo en la aldea.
    La clase CSS del img determina el tipo; la cantidad viene del prefijo del alt.
    """
    movement_type: str   # Clase CSS del img: "def1", "att2", etc.
    quantity:      int   # Prefijo numérico del alt: "618x …" → 618


@dataclass(frozen=True)
class BuildingInProgressDTO:
    """
    Un edificio actualmente en construcción.

    El `gid` no está disponible de forma estructural en td.bui de overview
    (el HTML solo tiene el `alt` del img.bau, que es idioma-dependiente del servidor).
    Se expone `building_name` como el alt crudo del servidor (para debugging) y,
    cuando un mapeo alt→gid se implemente en el futuro, también `gid`.

    Política actual (pragmática):
    - `building_name` = alt del img.bau, tal como viene del servidor (idioma del servidor).
    - `name` = si existe un gid conocido → nombre localizado vía get_building_name(gid, lang).
               si no hay gid → igual que building_name (mejor esfuerzo).
    - `name_source` = "catalog" | "server_lang" para que el cliente sepa el origen del nombre.

    No se expone el tiempo restante (no aparece en td.bui de overview).
    """
    building_name: str          # Alt crudo del img.bau (idioma del servidor), ej: "Barracks"
    name:          str          # Nombre localizado si gid conocido; alt crudo si no
    name_source:   str          # "catalog" si se usó translation_port; "server_lang" si no


@dataclass(frozen=True)
class TroopPresentDTO:
    """
    Un tipo de tropa con unidades presentes/destacadas en la aldea.
    El tipo se determina por la clase uNN del img; la cantidad por el prefijo del alt.
    """
    unit_class: str          # Código estable: clase uNN del img, p.ej. "u22"
    name:       str          # Nombre localizado al idioma pedido, p.ej. "Espadachín" (es)
                             # Fallback a unit_class si no hay entrada en el catálogo
    quantity:   int          # Prefijo numérico del alt: "71x …" → 71


@dataclass(frozen=True)
class OverviewVillageDTO:
    """
    Estado de una aldea en la tabla #overview.
    """
    game_id:                       int
    name:                          str

    # td.att — movimientos de tropas (lista vacía si span.none)
    movements:                     list[TroopMovementDTO]

    # td.bui — edificios en construcción (lista vacía si span.none)
    buildings_under_construction:  list[BuildingInProgressDTO]

    # td.tro — tropas presentes/destacadas (lista vacía si span.none)
    troops_present:                list[TroopPresentDTO]

    # td.tra — mercaderes libres / totales (0/0 si sin mercado)
    merchants_free:                int
    merchants_total:               int


@dataclass(frozen=True)
class OverviewResponseDTO:
    """
    Respuesta completa del endpoint GET /game/overview/{world_id}.
    """
    world_id:  int
    lang:      str
    villages:  list[OverviewVillageDTO]
```

---

## 8. Contratos de API / interfaces

> Nota: este contrato es propuesto por el analista. Debe ser validado por
> `desarrollador-apis` antes de la implementación (ver sección 3 del flujo de trabajo).
> `apis_validadas_por_desarrollador_apis: false` hasta recibir luz verde.

### `GET /game/overview/{world_id}`

**Descripción:** Devuelve el estado resumido de todas las aldeas del jugador para el
mundo indicado, parseado desde `/village/statistics/overview`.

**Parámetros:**

| Nombre | In | Tipo | Requerido | Descripción |
|---|---|---|---|---|
| `world_id` | path | integer | sí | ID del mundo (sesión de juego) |
| `Accept-Language` | header | string (BCP 47) | sí | Idioma (`es`, `en`, `de`, `fr`, `ru`). `400` si falta o no soportado. |

**Respuesta exitosa — `200 OK`:**

```json
{
  "world_id": 1,
  "lang": "es",
  "villages": [
    {
      "game_id": 19040,
      "name": "00",
      "movements": [
        { "movement_type": "def1", "quantity": 618 },
        { "movement_type": "att2", "quantity": 381 }
      ],
      "buildings_under_construction": [
        {
          "building_name": "Barracks",
          "name": "Cuartel",
          "name_source": "catalog"
        },
        {
          "building_name": "Barracks",
          "name": "Cuartel",
          "name_source": "catalog"
        }
      ],
      "troops_present": [
        { "unit_class": "u22", "name": "Espadachín galo",  "quantity": 71 },
        { "unit_class": "u24", "name": "Teutat Thunder",   "quantity": 22 },
        { "unit_class": "u26", "name": "Haeduan",          "quantity": 30 }
      ],
      "merchants_free": 14,
      "merchants_total": 14
    },
    {
      "game_id": 26421,
      "name": "04",
      "movements": [],
      "buildings_under_construction": [],
      "troops_present": [],
      "merchants_free": 0,
      "merchants_total": 0
    }
  ]
}
```

> **Nota de localización:** `Accept-Language` es FUNCIONAL en este endpoint.
> - `troops_present[].name` se resuelve con `unit_class_to_tribe_ordinal(unit_class)` →
>   `translation_port.get_troop_name(tribe, ordinal, lang)`. Fallback: si el `uNN` no
>   tiene entrada en el catálogo (naturaleza u31-u40, uhero, Natars, etc.), `name` = el
>   propio `unit_class` (el código es autoexplicativo para el bot; nunca falla).
> - `buildings_under_construction[].name` se resuelve con el alt del servidor como
>   mejor esfuerzo (ver RN-08). En la versión actual, el campo `name` = `building_name`
>   y `name_source` = `"server_lang"` porque overview no expone el gid del edificio.
> - `movements` no tiene `name` localizado porque `movement_type` es una clase CSS
>   interna de Travian, no un nombre humano.
```

**Errores:**

| Código HTTP | Condición | `detail` |
|---|---|---|
| `400` | `Accept-Language` ausente | mensaje fijo de `get_language` (texto en inglés; ver nota sobre get_language al pie) |
| `400` | Idioma no soportado (ej. `it`) | mensaje fijo de `get_language` |
| `422` | `world_id` no es entero | Validación automática de FastAPI |
| `503` | No hay sesión activa para `world_id` | Traducido al idioma del `Accept-Language` por el handler global (`SESSION_NOT_ACTIVE`) |
| `503` | Página de Travian no cargó en el timeout | Traducido al idioma del `Accept-Language` por el handler global (`OVERVIEW_PAGE_NOT_LOADED`) |
| `500` | Fixture no encontrado (modo fixture) | Traducido al idioma del `Accept-Language` por el handler global (`OVERVIEW_FIXTURE_NOT_FOUND`) |

> **Nota de propagación:** `SessionNotActiveError`, `OverviewPageNotLoadedError` y
> `OverviewFixtureNotFoundError` son `TravianBotError`. El handler NO las captura para
> re-lanzarlas como `HTTPException` con texto fijo. Las deja propagar al handler global
> de `main.py` (`travian_bot_error_handler`), que las traduce al idioma del cliente
> y mapea el HTTP status via `ERROR_HTTP_MAP`.
>
> **Nota sobre `get_language` (400):** `get_language` lanza `HTTPException(400)` con
> texto fijo en español/inglés (no pasa por el handler global). Es comportamiento
> preexistente del tronco, global a todos los endpoints. Está fuera del alcance de
> este bloque corregirlo; queda documentado como deuda técnica.

**Cabeceras de request requeridas:**

```
Accept-Language: es          (obligatoria; 400 si falta o idioma no soportado)
```

**Cabeceras de respuesta mínimas (añadidas por el middleware de main.py):**

```
Content-Type: application/json; charset=utf-8
X-Request-ID: <uuid-v4>       (se reutiliza el de la request si llega; se genera si no)
X-API-Version: 0.1.0
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
```

No se añade `Cache-Control` (datos vivos; el middleware de catálogo no aplica a `/game/`).

**Auth:** No aplica en esta fase.

> Nota de localización: `Accept-Language` es FUNCIONAL y OBLIGATORIA. El idioma resuelto
> se propaga al `OverviewUseCase.execute(port, world_id, lang, translation_port)` y desde
> allí al enriquecimiento de los DTOs de tropas y edificios. Ver RN-08 para detalle
> campo a campo.

---

## 9. Flujo lógico paso a paso

### 9.1 `OverviewParser` — parseo de la tabla `#overview`

```python
# adapters/browser/parsers/overview_parser.py

from bs4 import BeautifulSoup
from core.utils.parsing import parse_int, parse_int_or_none
import re
import logging

logger = logging.getLogger(__name__)


class OverviewParser:
    """
    Parser estático para la tabla #overview de /village/statistics/overview.
    Todos los métodos reciben html: str y devuelven datos Python puros.
    Selectores estructurales — nunca por texto visible.
    """

    @staticmethod
    def extract_overview_data(html: str) -> list[dict]:
        """
        Extrae los datos de todas las aldeas de la tabla #overview.

        Devuelve lista de dicts con claves:
          game_id, movements, buildings_under_construction,
          troops_present, merchants_free, merchants_total

        game_id: int — extraído del href newdid=N de td.vil.fc
        movements: list[dict] — [{movement_type: str, quantity: int}]
        buildings_under_construction: list[dict] — [{building_name: str}]
        troops_present: list[dict] — [{unit_class: str, quantity: int}]
        merchants_free: int
        merchants_total: int
        """
        soup = BeautifulSoup(html, "html.parser")
        result = []

        for row in soup.select("table#overview > tbody > tr"):
            # Extraer game_id de td.vil.fc
            vil_cell = row.select_one("td.vil.fc")
            if vil_cell is None:
                continue  # tr sin aldea (no debería haber tr.sum en overview)
            link = vil_cell.select_one("a[href*='newdid=']")
            if link is None:
                continue
            m = re.search(r"newdid=(\d+)", link["href"])
            if m is None:
                continue
            game_id = int(m.group(1))

            # ── td.att — movimientos ──────────────────────────────────────
            movements = []
            att_cell = row.select_one("td.att")
            if att_cell and not att_cell.select_one("span.none"):
                for img in att_cell.find_all("img"):
                    classes = img.get("class", [])
                    movement_type = next(
                        (c for c in classes if c not in ("img",)), None
                    )
                    if movement_type is None:
                        continue
                    alt = img.get("alt", "")
                    qty = _parse_quantity_from_alt(alt)
                    if qty is not None:
                        movements.append({
                            "movement_type": movement_type,
                            "quantity": qty,
                        })

            # ── td.bui — edificios en construcción ────────────────────────
            buildings = []
            bui_cell = row.select_one("td.bui")
            if bui_cell and not bui_cell.select_one("span.none"):
                for img in bui_cell.select("img.bau"):
                    building_name = img.get("alt", "")
                    buildings.append({"building_name": building_name})

            # ── td.tro — tropas presentes ─────────────────────────────────
            troops = []
            tro_cell = row.select_one("td.tro")
            if tro_cell and not tro_cell.select_one("span.none"):
                for img in tro_cell.select("img.unit"):
                    classes = img.get("class", [])
                    unit_class = next(
                        (c for c in classes if c.startswith("u") and c != "unit"), None
                    )
                    if unit_class is None:
                        continue
                    alt = img.get("alt", "")
                    qty = _parse_quantity_from_alt(alt)
                    if qty is None:
                        logger.warning(
                            "overview: no se pudo parsear cantidad de tropa en aldea "
                            "%s, alt='%s'", game_id, alt
                        )
                        continue
                    troops.append({"unit_class": unit_class, "quantity": qty})

            # ── td.tra — mercaderes libres/totales ────────────────────────
            merchants_free = 0
            merchants_total = 0
            tra_cell = row.select_one("td.tra")
            if tra_cell:
                # Puede ser <a> (aldea con mercado) o <span> (aldea sin mercado)
                text_node = tra_cell.select_one("a") or tra_cell.select_one("span")
                if text_node:
                    raw = text_node.get_text(strip=True)
                    merchants_free, merchants_total = _parse_merchants(raw, game_id)

            result.append({
                "game_id":                      game_id,
                "movements":                    movements,
                "buildings_under_construction": buildings,
                "troops_present":               troops,
                "merchants_free":               merchants_free,
                "merchants_total":              merchants_total,
            })

        return result


def _parse_quantity_from_alt(alt: str) -> int | None:
    """
    Extrae el número del prefijo "Nx ..." del atributo alt.
    Ej: "618x Arriving reinforcing troops" → 618
    Ej: "71x Swordsman" → 71
    Devuelve None si no hay prefijo numérico reconocible.
    """
    m = re.match(r"^(\d+)x\s", alt)
    if m:
        return int(m.group(1))
    return None


def _parse_merchants(raw: str, game_id: int) -> tuple[int, int]:
    """
    Parsea "libres/totales" del texto de td.tra, limpiando bidi U+202D/U+202C.
    Ej: "‭‭14‬/‭14‬‬" → (14, 14)
    Ej: "0/0" → (0, 0)
    En caso de formato inesperado, devuelve (0, 0) y loggea warning.
    """
    from core.utils.parsing import parse_int
    import logging
    log = logging.getLogger(__name__)

    clean = raw.replace("‭", "").replace("‬", "").strip()
    tokens = clean.split("/")
    if len(tokens) < 2:
        log.warning("overview: formato mercaderes inesperado en aldea %s: '%s'", game_id, raw)
        return 0, 0
    if len(tokens) > 2:
        log.warning("overview: más de un '/' en mercaderes aldea %s: '%s'", game_id, raw)
    try:
        free  = parse_int(tokens[0].strip())
        total = parse_int(tokens[-1].strip())
        return free, total
    except ValueError:
        log.warning("overview: no se pudo parsear mercaderes aldea %s: '%s'", game_id, raw)
        return 0, 0
```

### 9.2 `OverviewUseCase`

```python
# core/use_cases/overview_use_case.py

from core.ports.overview_html_source_port import OverviewHtmlSourcePort, OverviewPage
from core.ports.translation_port import TranslationPort
from core.use_cases.village_map import VillageMapUseCase
from core.dtos.overview_dto import (
    OverviewResponseDTO, OverviewVillageDTO,
    TroopMovementDTO, BuildingInProgressDTO, TroopPresentDTO,
)
from core.utils.units import unit_class_to_tribe_ordinal
from adapters.browser.parsers.overview_parser import OverviewParser


class OverviewUseCase:
    """
    Orquesta la lectura del estado resumido de todas las aldeas.

    1. VillageMapUseCase.execute(port, world_id) → list[VillageInfo]  (índice de aldeas)
    2. port.get_page_html(world_id, OverviewPage.OVERVIEW) → HTML     (caché hit)
    3. OverviewParser.extract_overview_data(html) → list[dict]        (parseo de columnas)
    4. merge por game_id + enriquecimiento con nombres localizados → list[OverviewVillageDTO]
    5. devuelve OverviewResponseDTO

    El enriquecimiento con nombres localizados ocurre en este use case:
    - Tropas presentes: unit_class_to_tribe_ordinal(uNN) → translation_port.get_troop_name(tribe, ordinal, lang)
    - Edificios en construcción: en overview no hay gid estructural; se usa el alt del
      servidor como mejor esfuerzo (name_source="server_lang").
    """

    async def execute(
        self,
        port:             OverviewHtmlSourcePort,
        world_id:         int,
        lang:             str,
        translation_port: TranslationPort,
    ) -> OverviewResponseDTO:
        # Paso 1 — índice de aldeas (nombre por game_id)
        village_map_uc = VillageMapUseCase()
        village_list   = await village_map_uc.execute(port, world_id)
        name_by_id     = {v.game_id: v.name for v in village_list}

        # Paso 2 — HTML (caché hit: mismo page que VillageMapUseCase ya cargó)
        html = await port.get_page_html(world_id, OverviewPage.OVERVIEW)

        # Paso 3 — parseo de columnas
        raw_data = OverviewParser.extract_overview_data(html)
        data_by_id = {r["game_id"]: r for r in raw_data}

        # Paso 4 — merge: todas las aldeas del índice + fallback para aldeas sin fila
        villages = []
        seen_ids = set()
        for village_info in village_list:
            gid  = village_info.game_id
            name = village_info.name
            seen_ids.add(gid)
            raw  = data_by_id.get(gid)

            if raw is None:
                # EC-11: aldea en índice pero sin fila en parser
                villages.append(OverviewVillageDTO(
                    game_id=gid, name=name,
                    movements=[], buildings_under_construction=[],
                    troops_present=[], merchants_free=0, merchants_total=0,
                ))
                continue

            villages.append(OverviewVillageDTO(
                game_id=gid,
                name=name,
                movements=[
                    TroopMovementDTO(movement_type=m["movement_type"], quantity=m["quantity"])
                    for m in raw["movements"]
                ],
                buildings_under_construction=[
                    BuildingInProgressDTO(
                        building_name=b["building_name"],
                        name=b["building_name"],      # mejor esfuerzo: alt del servidor
                        name_source="server_lang",    # overview no expone gid
                    )
                    for b in raw["buildings_under_construction"]
                ],
                troops_present=[
                    _enrich_troop(t["unit_class"], t["quantity"], lang, translation_port)
                    for t in raw["troops_present"]
                ],
                merchants_free=raw["merchants_free"],
                merchants_total=raw["merchants_total"],
            ))

        # EC-10: aldeas en parser pero ausentes del índice
        for gid, raw in data_by_id.items():
            if gid not in seen_ids:
                import logging
                logging.getLogger(__name__).warning(
                    "overview: game_id=%s en parser pero ausente del índice VillageMap", gid
                )
                villages.append(OverviewVillageDTO(
                    game_id=gid, name="",
                    movements=[
                        TroopMovementDTO(**m) for m in raw["movements"]
                    ],
                    buildings_under_construction=[
                        BuildingInProgressDTO(
                            building_name=b["building_name"],
                            name=b["building_name"],
                            name_source="server_lang",
                        )
                        for b in raw["buildings_under_construction"]
                    ],
                    troops_present=[
                        _enrich_troop(t["unit_class"], t["quantity"], lang, translation_port)
                        for t in raw["troops_present"]
                    ],
                    merchants_free=raw["merchants_free"],
                    merchants_total=raw["merchants_total"],
                ))

        return OverviewResponseDTO(world_id=world_id, lang=lang, villages=villages)


def _enrich_troop(
    unit_class: str,
    quantity: int,
    lang: str,
    translation_port: TranslationPort,
) -> TroopPresentDTO:
    """
    Construye un TroopPresentDTO con nombre localizado.

    Llama a unit_class_to_tribe_ordinal(unit_class) para obtener (tribe, ordinal).
    Si hay entrada en el catálogo → translation_port.get_troop_name(tribe, ordinal, lang).
    Si no hay entrada (uhero, NATARS_11 vacío, código desconocido) → name = unit_class.
    Nunca lanza; siempre devuelve un DTO válido.
    """
    result = unit_class_to_tribe_ordinal(unit_class)
    if result is not None:
        tribe, ordinal = result
        name = translation_port.get_troop_name(tribe, ordinal, lang)
        # get_troop_name tiene fallback a 'es'; si el nombre resultante es vacío, caer al código
        if not name:
            name = unit_class
    else:
        name = unit_class   # uhero, código no reconocido
    return TroopPresentDTO(unit_class=unit_class, name=name, quantity=quantity)
```

### 9.3 Handler FastAPI

```python
# adapters/api/routes/game_overview.py

from fastapi import APIRouter, Depends
from adapters.api.dependencies import get_language, get_html_source_port, get_translation_port
from core.ports.overview_html_source_port import OverviewHtmlSourcePort
from core.ports.translation_port import TranslationPort
from core.use_cases.overview_use_case import OverviewUseCase

router = APIRouter(prefix="/game", tags=["game-overview"])


@router.get("/overview/{world_id}")
async def get_overview(
    world_id:         int,
    lang:             str                    = Depends(get_language),
    port:             OverviewHtmlSourcePort = Depends(get_html_source_port),
    translation_port: TranslationPort        = Depends(get_translation_port),
):
    """
    Estado resumido de todas las aldeas del jugador:
    movimientos, construcción, tropas presentes y mercaderes.
    Los nombres de tropas se localizan al idioma de Accept-Language.

    SessionNotActiveError, OverviewPageNotLoadedError y OverviewFixtureNotFoundError
    se dejan PROPAGAR al handler global de main.py (travian_bot_error_handler),
    que las traduce al idioma del cliente y asigna el HTTP status correcto.
    No se capturan ni re-lanzan como HTTPException con texto fijo.
    """
    use_case = OverviewUseCase()
    result = await use_case.execute(
        port=port,
        world_id=world_id,
        lang=lang,
        translation_port=translation_port,
    )
    return result
```

### 9.4 Registro del router en `main.py`

```python
# adapters/api/main.py — añadir tras el registro de otros routers

from adapters.api.routes.game_overview import router as overview_router
application.include_router(overview_router)
```

---

## 10. Validaciones y reglas

| Elemento | Validación | Dónde |
|---|---|---|
| `Accept-Language` | Obligatoria; `400` si falta o idioma no soportado | `get_language` (dependency del tronco) |
| `world_id` | Entero positivo — validación automática FastAPI | Path parameter |
| `td.att img` — clase de movimiento | Genérica: cualquier clase CSS presente | `OverviewParser.extract_overview_data` |
| `td.att img` — cantidad | Prefijo `"Nx "` del `alt`; si no matchea → omitir + warning | `_parse_quantity_from_alt` |
| `img.unit.uNN` — unit_class | Clase que empieza por `"u"` y no es `"unit"` | `OverviewParser.extract_overview_data` |
| `img.unit.uNN` — cantidad | Prefijo `"Nx "` del `alt`; si no matchea → omitir + warning | `_parse_quantity_from_alt` |
| `td.tra` texto | Limpiar bidi U+202D/U+202C; dividir por `/`; `parse_int` | `_parse_merchants` |
| `span.none` | Detectar antes de buscar imgs; producir lista vacía | `OverviewParser.extract_overview_data` |
| Aldea en índice sin fila en parser | Incluirla con campos vacíos; no error | `OverviewUseCase.execute` |
| Aldea en parser sin fila en índice | Incluirla con `name=""`; loggear warning | `OverviewUseCase.execute` |

---

## 11. Seguridad, rendimiento y concurrencia

### Anti-detección

El bloque overview no navega el browser directamente. Toda la navegación ocurre en
`LiveOverviewAdapter` (del tronco), que ya aplica `human_delay(500, 900)` y mantiene
todas las capas de anti-detección del `CLAUDE.md`. Este bloque no modifica esas capas.

### Rendimiento

- La caché del `LiveOverviewAdapter` (TTL 60 s, configurado en el tronco) garantiza que
  las dos llamadas al port en `OverviewUseCase.execute` (VillageMapUseCase + OverviewParser)
  solo generan una navegación real.
- El parseo con `BeautifulSoup` sobre un HTML de ~5-10 KB es < 10 ms. No es un cuello de botella.
- No se necesita caché adicional en este bloque.

### Concurrencia

- El double-checked locking del `LiveOverviewAdapter` garantiza que peticiones concurrentes
  al mismo `(world_id, OverviewPage.OVERVIEW)` no generan navegaciones duplicadas.
- El `OverviewUseCase` es stateless; puede instanciarse por petición sin riesgo de estado compartido.

### Seguridad

- El HTML parseado es solo para uso interno del bot. No se reenvía al cliente.
- Los `building_name` del `alt` son strings del servidor de Travian, no del usuario: no hay
  riesgo de inyección vía esos campos.

---

## 12. Plan de pruebas

Todos los tests se ejecutan sin Chrome usando `FixtureOverviewAdapter` con `overview.html`.

### 12.1 Tests del parser `OverviewParser`

| ID | Test | Descripción | Resultado esperado |
|---|---|---|---|
| T-01 | `test_extract_movements_present` | Aldea `game_id=19040` del fixture | `movements = [TroopMovement(def1, 618), TroopMovement(att2, 381)]` |
| T-02 | `test_extract_movements_none` | Aldea `game_id=26421` (span.none) | `movements = []` |
| T-03 | `test_extract_buildings_two` | Aldea `game_id=19040` (2× img.bau "Barracks") | `len(buildings_under_construction) == 2` |
| T-04 | `test_extract_buildings_one` | Aldea `game_id=25306` (1× img.bau "Academy") | `len(buildings_under_construction) == 1` |
| T-05 | `test_extract_buildings_none` | Aldea `game_id=26421` (span.none) | `buildings_under_construction = []` |
| T-06 | `test_extract_troops_three_types` | Aldea `game_id=19040` (u22×71, u24×22, u26×30) | `troops_present = [TroopPresent(u22,71), TroopPresent(u24,22), TroopPresent(u26,30)]` |
| T-07 | `test_extract_troops_none` | Aldea `game_id=26421` (span.none) | `troops_present = []` |
| T-08 | `test_extract_merchants_with_link` | Aldea `game_id=19040` → `"‭‭14‬/‭14‬‬"` | `merchants_free=14, merchants_total=14` |
| T-09 | `test_extract_merchants_partial` | Aldea `game_id=24341` → `"‭‭9‬/‭12‬‬"` | `merchants_free=9, merchants_total=12` |
| T-10 | `test_extract_merchants_zero_span` | Aldea `game_id=26421` → `"‭‭0‬/‭0‬‬"` (span sin href) | `merchants_free=0, merchants_total=0` |
| T-11 | `test_extract_all_villages_count` | Fixture completo | Parser devuelve exactamente 6 aldeas (una por `td.vil.fc`) |
| T-12 | `test_no_tr_sum_in_overview` | Fixture completo | Ninguna fila devuelta tiene game_id=0 ni procede de `tr.sum` |
| T-13 | `test_unknown_movement_class` | HTML sintético con `img.classX` en `td.att` | Incluido en `movements` con `movement_type="classX"` (genérico) |

### 12.2 Tests del `OverviewUseCase`

| ID | Test | Descripción | Resultado esperado |
|---|---|---|---|
| T-14 | `test_use_case_full_fixture` | `FixtureOverviewAdapter` + `overview.html` | `OverviewResponseDTO` con 6 aldeas; nombres y game_ids correctos |
| T-15 | `test_use_case_village_map_merged` | Fixture real | `game_id` de cada DTO coincide con el del índice de VillageMapUseCase |
| T-16 | `test_use_case_session_not_active` | Port que lanza `SessionNotActiveError` | `SessionNotActiveError` se propaga sin envolver |
| T-17 | `test_use_case_missing_in_parser` | HTML sintético: índice tiene aldea X, parser no la devuelve | DTO incluye aldea X con campos vacíos |
| T-18 | `test_use_case_extra_in_parser` | HTML sintético: parser devuelve aldea Y no en índice | DTO incluye aldea Y con `name=""` |

### 12.3 Tests del handler FastAPI

| ID | Test | Descripción | Resultado esperado |
|---|---|---|---|
| T-19 | `test_endpoint_200_with_fixture` | `GET /game/overview/1` + `Accept-Language: es` + `OVERVIEW_SOURCE=fixture` | `200`, JSON con 6 aldeas |
| T-20 | `test_endpoint_400_no_language` | `GET /game/overview/1` sin cabecera | `400` |
| T-21 | `test_endpoint_400_unsupported_language` | `GET /game/overview/1` + `Accept-Language: it` | `400` |
| T-22 | `test_endpoint_503_session_not_active` | Port mockeado que lanza `SessionNotActiveError` | `503`, `detail` en idioma del `Accept-Language` |
| T-23 | `test_endpoint_422_invalid_world_id` | `GET /game/overview/abc` | `422` |

---

## 13. Riesgos y trade-offs

### TR-01 — Ambigüedad: `td.tro` muestra tropas presentes, no en entrenamiento

**Descripción:** El usuario describió la columna Troops del overview como "tropas que estoy
entrenando". Sin embargo, el fixture muestra `img.unit.uNN` con cantidades que corresponden a
tropas presentes/destacadas (no tropas en cola de entrenamiento).

**Evidencia del fixture:** La aldea `game_id=19040` tiene `u22×71, u24×22, u26×30`.
Estos números son tropas presentes en la aldea. El detalle de entrenamiento (cola, tiempos)
está en la pestaña `TROOPS_TRAINING` y lo cubre el bloque troops.

**Decisión:** Interpretar `td.tro` como "tropas presentes destacadas" y documentarlo
explícitamente en el DTO y en el endpoint. El bloque overview es un resumen; el detalle
de entrenamiento es responsabilidad del bloque troops.

**Lo que el usuario quería decir probablemente:** el overview muestra qué tropas están
"activas" en cada aldea en ese momento, que incluye las que ya están entrenadas y presentes.
No la cola de entrenamiento. La confusión terminológica es natural.

**Acción recomendada:** Al presentar la respuesta al usuario, aclarar que `troops_present`
son las tropas ya entrenadas que están en la aldea, y que para ver la cola de entrenamiento
hay que consultar el endpoint del bloque troops.

### TR-02 — Tipos de movimiento no cubiertos en el fixture

**Descripción:** El fixture solo muestra `def1` (refuerzos llegando) y `att2` (propias
atacando). No hay ataques enemigos entrantes, atracos, exploraciones, etc.

**Decisión:** Parser genérico (ver RN-03). El campo `movement_type` es el string de la
clase CSS, no un enum. Cuando el usuario capture HTML con ataques entrantes, la tabla
de la sección 6 se actualiza y el parser ya los manejará sin cambios de código.

**Riesgo residual:** Si Travian usa un `<div>` u otra estructura para ciertos movimientos
en vez de `<img>` dentro de `td.att`, el parser los perdería. Bajo hasta que se confirme
con HTML real.

### RI-01 — Solape con bloque resources en campo mercaderes

**Descripción:** La tabla `#overview` expone mercaderes `"libres/totales"` en `td.tra`.
La tabla `#ressources` (bloque resources) también expone mercaderes. Son la misma
fuente de verdad (mismo servidor), pero dos parseos desde dos páginas distintas.

**Decisión para este spec:** Exponer los mercaderes en overview tal como aparecen.
La decisión de cuál es la fuente canónica (overview vs resources) queda pendiente
para palantir y el coordinador.

**Impacto:** Ninguno en la implementación de este bloque. El campo existe y se expone.
Si en el futuro se decide que resources es canónico, el campo `merchants_*` de overview
puede marcarse como `deprecated` o eliminarse.

### TR-03 — `building_name` es idioma-dependiente del servidor; `name_source` documenta el origen

**Descripción:** El `alt` del `img.bau` es el nombre del edificio tal como Travian lo
muestra en el idioma del servidor (no el idioma solicitado via `Accept-Language`). Un
servidor en inglés mostrará "Barracks"; uno en español mostrará "Cuartel". La tabla de
overview no expone el `gid` del edificio de forma estructural, por lo que no es posible
resolver el nombre localizado vía `get_building_name(gid, lang)`.

**Decisión (mejor esfuerzo):** El campo `building_name` almacena el `alt` crudo del
servidor. El campo `name` replica ese mismo valor. El campo `name_source = "server_lang"`
advierte al cliente que el nombre NO está localizado al idioma solicitado, sino que viene
del servidor de Travian en su idioma de configuración. Esta distinción (código estable vs
nombre localizado) se aplica igual que en tropas; simplemente en buildings la fuente es
distinta.

**Limitación:** si el servidor Travian está en inglés y el jugador pide `Accept-Language: es`,
recibirá `"Barracks"` en `building_name` y `name`, no `"Cuartel"`. El bot puede trabajar con
`building_name` sin problema; el dashboard debe mostrar el `name` con la advertencia de que
puede no coincidir con el idioma solicitado.

**Si se necesita localización completa en el futuro:** implementar un mapa
`alt_en → gid` (nombre en inglés → gid del edificio) y usar `get_building_name(gid, lang)`.
Fuera del alcance de este spec.

---

## 14. Pasos de implementación ordenados

El implementador debe verificar antes de empezar que el tronco (`lectura-overview-tronco-comun`)
ya está implementado (estado `implemented`). Si alguno de los componentes del tronco falta,
implementarlo primero.

0. **`core/utils/units.py`** — CREAR (o verificar que existe): helper `unit_class_to_tribe_ordinal`.
   Este helper es compartido por los bloques overview, troops y cualquier otro que mapee `uNN`.
   Ver contrato completo en la sección "Helper compartido" al final de este paso de implementación.

1. **`core/dtos/`** — VERIFICAR que el directorio existe; si no, CREAR `core/dtos/__init__.py`.

2. **`core/dtos/overview_dto.py`** — CREAR con los cuatro dataclasses: `TroopMovementDTO`,
   `BuildingInProgressDTO`, `TroopPresentDTO`, `OverviewVillageDTO`, `OverviewResponseDTO`
   (sección 7.1).

3. **`adapters/browser/parsers/`** — VERIFICAR que el directorio existe; si no,
   CREAR `adapters/browser/parsers/__init__.py`.

4. **`adapters/browser/parsers/overview_parser.py`** — CREAR con `OverviewParser`,
   `_parse_quantity_from_alt` y `_parse_merchants` (sección 9.1).

5. **`tests/unit/test_overview_parser.py`** — CREAR con los tests T-01 a T-13.
   Usar `overview.html` (fixture real) + HTML sintético para los casos de borde.
   Ejecutar y verificar que todos pasan.

6. **`core/use_cases/overview_use_case.py`** — CREAR con `OverviewUseCase.execute`
   (sección 9.2).

7. **`tests/unit/test_overview_use_case.py`** — CREAR con los tests T-14 a T-18.
   Ejecutar y verificar que todos pasan.

8. **`adapters/api/routes/game_overview.py`** — CREAR con el handler `get_overview`
   (sección 9.3). Dependencias `get_language` y `get_html_source_port` ya existen en
   `adapters/api/dependencies.py` (del tronco).

9. **`adapters/api/main.py`** — MODIFICAR: importar `overview_router` y registrarlo
   con `application.include_router(overview_router)` (sección 9.4).

10. **`tests/test_overview_api.py`** (o `tests/unit/test_overview_api.py`) — CREAR con
    los tests T-19 a T-23. Usar `TestClient` de FastAPI con `OVERVIEW_SOURCE=fixture`.
    Ejecutar y verificar que todos pasan.

11. **Smoke test final:**
    ```bash
    source .venv/bin/activate && pytest tests/unit/test_overview_parser.py \
        tests/unit/test_overview_use_case.py tests/test_overview_api.py -v
    ```
    Todos los tests deben pasar. Verificar también que los tests del tronco siguen pasando:
    ```bash
    pytest --ignore=tests/antideteccion -v
    ```

### Helper compartido — `core/utils/units.py`

```python
# core/utils/units.py
"""
Mapeado global uNN → (Tribe, ordinal) para resolución de nombres localizados.

Travian usa numeración GLOBAL de unidades en las clases CSS de imágenes:
  u1–u10   → Romanos  (ordinal 1–10)
  u11–u20  → Teutones (ordinal 1–10)
  u21–u30  → Galos    (ordinal 1–10)
  u31–u40  → Naturaleza (ordinal 1–10)
  u41–u50  → Egipcios (ordinal 1–10)
  u51–u60  → Hunos    (ordinal 1–10)
  u61–u71  → Natars   (ordinal 1–11)   — NATARS_11 tiene nombre vacío en el catálogo
  u72–u81  → Espartanos (ordinal 1–10)
  u82–u91  → Vikingos  (ordinal 1–10)
  uhero    → None (sin entrada en el catálogo)

NOTA: las tribus están verificadas contra troops.json.
Naturaleza (u31-u40) tiene entradas completas en el catálogo (Rata, Araña, … Elefante).
NATARS_11 (u71) tiene nombres vacíos en el catálogo → el llamador debe usar fallback = unit_class.
"""
from core.entities.tribe import Tribe

_RANGES: list[tuple[int, int, Tribe]] = [
    (1,  10, Tribe.ROMANS),
    (11, 20, Tribe.TEUTONS),
    (21, 30, Tribe.GAULS),
    (31, 40, Tribe.NATURE),
    (41, 50, Tribe.EGYPTIANS),
    (51, 60, Tribe.HUNS),
    (61, 71, Tribe.NATARS),
    (72, 81, Tribe.SPARTANS),
    (82, 91, Tribe.VIKINGS),
]


def unit_class_to_tribe_ordinal(unit_class: str) -> tuple[Tribe, int] | None:
    """
    Convierte la clase CSS global de una unidad Travian a (Tribe, ordinal).

    El ordinal es 1-based dentro de la tribu:
      "u22" → (Tribe.GAULS, 2)   porque u21=GAULS_1, u22=GAULS_2, ...
      "u31" → (Tribe.NATURE, 1)
      "u61" → (Tribe.NATARS, 1)
      "uhero" → None
      código desconocido → None

    El llamador debe manejar el retorno None devolviendo un fallback razonable
    (p.ej. name = unit_class). Esta función nunca lanza.
    """
    if unit_class == "uhero" or not unit_class.startswith("u"):
        return None
    suffix = unit_class[1:]
    if not suffix.isdigit():
        return None
    n = int(suffix)
    for start, end, tribe in _RANGES:
        if start <= n <= end:
            ordinal = n - start + 1
            return tribe, ordinal
    return None
```

**Invariantes verificados contra `troops.json`:**
- `unit_class_to_tribe_ordinal("u1")` → `(ROMANS, 1)` ✓
- `unit_class_to_tribe_ordinal("u21")` → `(GAULS, 1)` ✓
- `unit_class_to_tribe_ordinal("u31")` → `(NATURE, 1)` ✓  (hay catálogo para Naturaleza)
- `unit_class_to_tribe_ordinal("u71")` → `(NATARS, 11)` ✓ (NATARS_11 en catálogo, nombre vacío → fallback)
- `unit_class_to_tribe_ordinal("uhero")` → `None` ✓
- `unit_class_to_tribe_ordinal("u99")` → `None` ✓ (fuera de rango)

---

## 15. Criterios de aceptación

Checklist verificable por el implementador:

### DTOs

- [ ] `core/dtos/overview_dto.py` existe con los cinco dataclasses: `TroopMovementDTO`, `BuildingInProgressDTO`, `TroopPresentDTO`, `OverviewVillageDTO`, `OverviewResponseDTO`.
- [ ] Todos los dataclasses son `frozen=True`.
- [ ] `OverviewVillageDTO` tiene campos: `game_id`, `name`, `movements`, `buildings_under_construction`, `troops_present`, `merchants_free`, `merchants_total`.

### Parser

- [ ] `adapters/browser/parsers/overview_parser.py` existe con clase `OverviewParser`.
- [ ] `OverviewParser.extract_overview_data` es método estático que recibe `html: str`.
- [ ] El parser captura genéricamente TODOS los `img` dentro de `td.att` (no solo `def1`/`att2`).
- [ ] `span.none` en cualquier columna produce lista vacía (no error, no None).
- [ ] El tipo de tropa en `td.tro` se extrae de la clase `uNN` del `img`, nunca del `alt`.
- [ ] `td.tra` se parsea con `parse_int` (limpieza bidi incluida).
- [ ] Texto de mercaderes con `<span>` (sin `<a>`) también se parsea correctamente.
- [ ] Tests T-01 a T-13 pasan.

### Use case

- [ ] `core/use_cases/overview_use_case.py` existe con clase `OverviewUseCase`.
- [ ] `OverviewUseCase.execute` acepta `lang: str` y `translation_port: TranslationPort`.
- [ ] `OverviewUseCase.execute` llama a `VillageMapUseCase` y a `OverviewParser`.
- [ ] `_enrich_troop` resuelve nombre localizado vía `unit_class_to_tribe_ordinal` + `translation_port.get_troop_name`.
- [ ] `_enrich_troop` devuelve `name = unit_class` para `uhero` y códigos sin entrada en catálogo. Nunca lanza.
- [ ] `BuildingInProgressDTO` siempre lleva `name_source="server_lang"` (no hay gid en overview).
- [ ] Aldeas presentes en el índice pero sin fila en parser → incluidas con campos vacíos.
- [ ] Aldeas en parser pero ausentes del índice → incluidas con `name=""` + warning.
- [ ] Tests T-14 a T-18 pasan.

### Endpoint

- [ ] `adapters/api/routes/game_overview.py` existe con router `prefix="/game"`.
- [ ] `GET /game/overview/{world_id}` está registrado y accesible.
- [ ] El handler inyecta `translation_port: TranslationPort = Depends(get_translation_port)`.
- [ ] El handler pasa `translation_port` al `OverviewUseCase.execute`.
- [ ] Swagger muestra `Accept-Language` como parámetro requerido del endpoint.
- [ ] Sin cabecera `Accept-Language` → `400`.
- [ ] `Accept-Language: it` → `400`.
- [ ] `Accept-Language: es` → `200` con JSON correcto.
- [ ] `SessionNotActiveError` → `503` vía propagación al handler global (sin `try/except` en la ruta).
- [ ] `OverviewPageNotLoadedError` → `503` vía propagación al handler global.
- [ ] `OverviewFixtureNotFoundError` → `500` vía propagación al handler global.
- [ ] Los mensajes de error en 503/500 están en el idioma del `Accept-Language` (localización FUNCIONAL).
- [ ] Tests T-19 a T-23 pasan.

### Integración con tronco

- [ ] `application.include_router(overview_router)` está en `adapters/api/main.py`.
- [ ] La API arranca sin error con `OVERVIEW_SOURCE=fixture`.
- [ ] Todos los tests previos del tronco siguen pasando (no regresiones).

### Comportamiento con fixture real

- [ ] `GET /game/overview/1` con `Accept-Language: es` devuelve 6 aldeas correspondientes
  a los 6 `td.vil.fc` del fichero `overview.html`.
- [ ] La aldea `game_id=26421` tiene `movements=[]`, `buildings_under_construction=[]`,
  `troops_present=[]`, `merchants_free=0`, `merchants_total=0`.
- [ ] La aldea `game_id=19040` tiene `merchants_free=14`, `merchants_total=14`.

---

## 16. Trazabilidad

| Decisión técnica | Requisito o edge case que la origina |
|---|---|
| Parser genérico de `img` en `td.att` (no filtrar por clase) | TR-02: tipos de movimiento no cubiertos en fixture; RN-03: robustez ante HTML futuro |
| `movement_type` como string libre (no enum) | TR-02: no se conocen todos los valores posibles; un enum rompería con clases nuevas |
| `building_name` del `alt` de `img.bau` | RN-05: el usuario quiere el conteo; el nombre es secundario y está en `alt` idioma-dependiente |
| Tipo de tropa por clase `uNN`, nunca por `alt` | RN-06 + convención del tronco (README fixtures): `alt` es idioma-dependiente |
| `parse_int` para mercaderes (con limpieza bidi) | EC-09: texto `td.tra` tiene U+202D/U+202C; RN-07 |
| Dos llamadas al port en `OverviewUseCase` (VillageMap + Parser) | RN-02: separación de responsabilidades; coste irrelevante por caché hit (sección 5 flujo principal) |
| Fallback `name=""` para aldeas sin índice | EC-10: consistencia de datos; no error fatal |
| Fallback campos vacíos para aldeas en índice sin fila | EC-11: índice es la fuente autoritativa de qué aldeas existen |
| `OverviewVillageDTO` `frozen=True` | Inmutabilidad de DTOs de respuesta; patrón del tronco (`VillageInfo` también frozen) |
| Handler captura `SessionNotActiveError` → `503` | EC-16: error operacional, no error de cliente |
| Handler captura `OverviewFixtureNotFoundError` → `500` | EC-17: error de configuración del entorno de test |
| Prefijo `/game/` en el router | RN-08 del tronco: el middleware `/catalog/` cachea 1h; datos vivos deben ir bajo `/game/` |
| `get_language` obligatoria (no optional) | RN-09 del tronco: Accept-Language obligatoria en todos los endpoints de overview |
| `RI-01` mercaderes anotados pero no resueltos | Decisión de fuente canónica delegada a palantir/coordinador; no bloquea este spec |
| `TR-01` `td.tro` como "tropas presentes" | Verificado en fixture: los números corresponden a tropas ya entrenadas, no cola de entrenamiento |
