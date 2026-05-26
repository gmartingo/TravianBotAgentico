---
id: lectura-overview-tronco-comun
titulo: "Lectura de overview Travian — fundación compartida (tronco común)"
estado: implemented
fecha: 2026-05-26
autor: analista
apis_validadas_por_desarrollador_apis: n-a
---

# Lectura de overview Travian — fundación compartida (tronco común)

---

## 1. Objetivo de negocio

Crear la infraestructura compartida (tronco) sobre la que cuatro equipos independientes
construirán, en paralelo, los endpoints de lectura del estado dinámico del jugador en
Travian. Los cuatro bloques son:

| Bloque | Contenido |
|---|---|
| `overview` | Aldeas + movimientos entrantes + construcción activa + entrenamiento + mercaderes |
| `resources` | Recursos almacenados / suma / mercaderes + producción + capacidades |
| `culture-points` | CP por aldea + fiestas activas |
| `troops` | Tropas propias, en aldea, herrería, hospital, en entrenamiento |

Este spec NO especifica ninguno de esos cuatro bloques. Solo especifica los cimientos:
el puerto de HTML, los adaptadores que lo implementan, el use case de mapeo de aldeas,
las utilidades de parseo compartidas, el wiring en FastAPI y las convenciones que deben
respetar los cuatro equipos.

**Criterio de éxito del tronco:** los cuatro bloques pueden desarrollarse en paralelo
sin coordinar entre sí, sin depender de una sesión Chrome viva, y con parsers que se
testean exclusivamente con fixtures HTML.

---

## 2. Actores y permisos

| Actor | Rol |
|---|---|
| Agentes del bot (futuros use cases) | Consumen el tronco a través del port para leer el estado del juego |
| `OverviewHtmlSourcePort` | Contrato que abstrae la fuente de HTML (viva o fixture) |
| `LiveOverviewAdapter` | Implementación que navega Travian con Chrome autenticado |
| `FixtureOverviewAdapter` | Implementación de test que devuelve HTML desde fichero |
| FastAPI + `get_html_source_port` | Expone el port a los handlers de los cuatro bloques |
| Desarrollador / equipo del bot | Añade fixtures HTML para testear parsers sin Chrome |

No hay control de acceso diferenciado en esta capa. La autorización (quién puede pedir
el estado de qué cuenta) es responsabilidad de los bloques superiores y está fuera del
alcance de este spec.

---

## 3. Alcance

### Dentro de alcance

- Interfaz `OverviewHtmlSourcePort` con sus métodos, parámetros, tipos y errores.
- `LiveOverviewAdapter`: implementación del port que navega Travian con browser autenticado.
  Incluye caché TTL configurable (clave, invalidación, concurrencia básica).
  El browser se recibe por inyección; el adaptador queda "pendiente de cableado" hasta que
  exista el `SessionRegistry` (ver sección 13 — riesgo TR-01).
- `FixtureOverviewAdapter`: implementación que devuelve HTML desde fichero. Plenamente
  funcional hoy; base de todos los tests de los cuatro bloques.
- `VillageMapUseCase` (o función equivalente): extrae la lista de aldeas del jugador con
  su `game_id` y nombre desde la página de overview principal. Define el índice compartido.
- Refactor de utilidades de parseo: mover `_parse_int`, `_parse_int_or_none`, `_parse_time`
  a un módulo compartido para evitar duplicación entre el scraper de kirilloid y los parsers
  de overview.
- Dependency FastAPI `get_html_source_port` y registro en el `lifespan`.
- Convenciones que heredarán los cuatro bloques: prefijo de rutas, estructura de carpetas,
  naming de DTOs, naming de fixtures, uso de `Accept-Language`.
- Lista explícita de HTML que el usuario debe capturar para fijar selectores.

### Fuera de alcance

- Los cuatro bloques de endpoints de lectura (overview, resources, culture-points, troops).
- Implementación de `SessionRegistry` / `WorldRuntimePort` (diferido, ver login.md).
- Endpoint HTTP para disparar login o gestionar sesiones.
- Parsers de cada bloque (HTML → datos estructurados). Solo se especifica la
  interfaz del port y las convenciones; los parsers son responsabilidad de cada bloque.
- Lógica de reintentos o reconexión automática si el browser muere.
- Endpoint de invalidación de caché vía HTTP.
- Autenticación / autorización en los endpoints de overview.

---

## 4. Reglas de negocio

**RN-01 — Páginas de `/village/statistics/<tab>` como fuente agregada:**
Las páginas de overview son agregadas: cada pestaña (`/village/statistics/<tab>`) lista
TODAS las aldeas del jugador (una fila por aldea + fila `tr.sum` de totales). No existen
páginas por aldea. El índice de aldeas se extrae de la pestaña `OVERVIEW`
(`/village/statistics/overview`) y es compartido por los cuatro bloques; no se re-extrae
por bloque.

**RN-02 — Identificación de aldeas por `game_id` (parámetro `newdid` en URLs Travian):**
La entidad `Village` ya tiene `game_id: int` (campo en `core/entities/village.py`).
Es el identificador que aparece en los `href` de aldea dentro de las páginas de statistics
(`/dorf1.php?newdid=N` → N). El tronco nunca usa IDs de BD para referirse a aldeas en
las páginas de Travian.

**RN-03 — Datos leídos en vivo con caché TTL corto:**
Las páginas de overview devuelven el estado actual del jugador. Se cachean para evitar
cargar Travian en cada petición HTTP al bot, pero el TTL debe ser corto para que el
estado no quede desactualizado. El TTL por defecto es 60 segundos, configurable por
`OVERVIEW_CACHE_TTL_SECONDS` (variable de entorno o constante en el adaptador).

**RN-04 — Parsers desacoplados y testables con fixtures:**
Los parsers HTML no dependen de sesión viva. Reciben HTML crudo (str) y devuelven datos.
Los tests cargan un fichero HTML guardado previamente y llaman al parser directamente.
Un parser que necesite el browser para funcionar es una violación del diseño.

**RN-05 — Selectores siempre estructurales:**
Travian es multilenguaje. Ningún selector en parsers de overview puede depender de texto
visible. Solo: atributos HTML, clases CSS, IDs, posición estructural (`nth-child`), o
el `gid` de edificio en URLs. Misma regla que en `adapters/browser/login.py`.

**RN-06 — El port no conoce la implementación del browser:**
`OverviewHtmlSourcePort` recibe y devuelve solo tipos básicos de Python (str, int, enum).
No importa `zendriver` ni ninguna clase de browser. El aislamiento permite sustituir el
adaptador sin tocar el core.

**RN-07 — `OverviewPage` como enumeración estable de las páginas a leer:**
Cada bloque necesita páginas concretas. El port define una enumeración `OverviewPage`
para nombrarlas de forma estable y evitar strings mágicos dispersos por el código.
Añadir una nueva página = añadir un valor al enum; no cambia la firma del port.

**RN-08 — Prefijo `/game/` para endpoints de datos vivos:**
Los endpoints de los cuatro bloques van bajo `/game/` (no bajo `/catalog/`). El
middleware `add_catalog_cache_control` de `main.py` cachea durante 1 hora todo lo que
empieza por `/catalog/`. Los datos de overview son vivos; ese cache de 1 hora los
corrompería. El prefijo `/game/` evita que el middleware los afecte.

**RN-09 — `Accept-Language` obligatoria en endpoints de overview:**
Los endpoints de overview devuelven nombres localizados de aldeas, tropas y edificios.
La dependencia a usar es `get_language` (obligatoria, `400` si falta). No `optional`.

**RN-10 — Un solo adaptador activo por entorno:**
El `lifespan` registra exactamente una implementación de `OverviewHtmlSourcePort` en
`app.state.html_source_port`. La selección entre Live y Fixture se hace en el lifespan
(p.ej. con una variable de entorno `OVERVIEW_SOURCE=live|fixture`). Los handlers no
conocen qué implementación está activa.

**RN-11 — Fallo rápido si el browser no está disponible:**
Si `LiveOverviewAdapter` intenta navegar sin browser (porque el `SessionRegistry` aún
no existe o el login no se ha ejecutado), debe lanzar `SessionNotActiveError` (ya
existe en `core/exceptions.py`). No lanza `AttributeError` ni falla silenciosamente.

---

## 5. Flujo principal y flujos alternativos

### Flujo principal — handler de un bloque recibe petición HTTP

```
Cliente HTTP
  └─> GET /game/<bloque>/<params>   Accept-Language: es
        └─> FastAPI handler
              ├─ get_language(...)         → "es"
              ├─ get_html_source_port(...) → OverviewHtmlSourcePort
              └─> bloque_use_case.execute(port, world_id, lang)
                    ├─> port.get_page_html(world_id, OverviewPage.RESOURCES)
                    │     ├─ [caché hit]  → devuelve HTML cacheado
                    │     └─ [caché miss] → LiveOverviewAdapter navega Travian → HTML → cachea → devuelve
                    └─> parser_del_bloque(html) → datos estructurados (todas las aldeas)
              └─> serializar DTO → JSON 200
```

Nota: las páginas de statistics son agregadas; no hay `village_game_id` en la petición
al port. El parser extrae las filas de cada aldea del HTML devuelto.

### Flujo principal — tests de un bloque (sin Chrome)

```
pytest test_bloque.py
  └─> bloque_use_case.execute(fixture_port, world_id, lang)
        └─> fixture_port.get_page_html(world_id, OverviewPage.RESOURCES)
              └─ abre fichero fixtures/overview/resources.html → devuelve HTML
        └─> parser_del_bloque(html) → datos estructurados (todas las aldeas)
        └─> assert datos == esperados
```

### Flujo alternativo A — caché hit

```
port.get_page_html(world_id, page)
  └─ cache_key = (world_id, page)
  └─ cache[cache_key].timestamp + TTL > now → devuelve cache[cache_key].html
```

### Flujo alternativo B — sesión no activa (Login no ejecutado)

```
LiveOverviewAdapter.get_page_html(...)
  └─ self._get_browser(world_id) → None (SessionRegistry no existe o no hay login)
  └─ raise SessionNotActiveError()
```

### Flujo alternativo C — timeout de carga de página

```
LiveOverviewAdapter._navigate_and_get(...)
  └─ await page.wait_for_element("#content", timeout=OVERVIEW_PAGE_TIMEOUT)
  └─ TimeoutError → raise OverviewPageNotLoadedError(world_id, page)
```

### Flujo alternativo D — fixture no encontrado

```
FixtureOverviewAdapter.get_page_html(world_id, page)
  └─ ruta = fixtures_dir / f"{page.value}.html"
  └─ NOT ruta.exists() → raise OverviewFixtureNotFoundError(page)
```

### Flujo de `VillageMapUseCase`

```
VillageMapUseCase.execute(port, world_id)
  └─> port.get_page_html(world_id, OverviewPage.OVERVIEW)
        └─ devuelve HTML de /village/statistics/overview (todas las aldeas)
  └─> VillageOverviewParser.extract_villages(html)
        └─ filas: table#overview > tbody > tr con td.vil.fc
        └─ game_id: href del td.vil.fc > a → newdid=N → N
        └─ name: texto del mismo <a> (strip)
        └─ ignora tr.sum
        └─ devuelve list[VillageInfo]
```

---

## 6. Edge cases

| ID | Caso | Tratamiento esperado |
|---|---|---|
| EC-01 | Browser no disponible (`LiveOverviewAdapter` sin `SessionRegistry`) | Lanzar `SessionNotActiveError` — no `AttributeError` ni fallo silencioso |
| EC-02 | Timeout al cargar la página de overview | Lanzar `OverviewPageNotLoadedError(world_id, page)` |
| EC-03 | Fixture no encontrado | Lanzar `OverviewFixtureNotFoundError(page)` — el nombre de fichero es `{page.value}.html` |
| EC-04 | Caché corrupto (HTML vacío guardado por error) | El adaptador verifica `len(html.strip()) > 0`; si falla, marca la entrada como inválida y re-navega. Si la re-navegación también devuelve HTML vacío, lanzar `OverviewPageNotLoadedError` |
| EC-05 | Dos peticiones simultáneas con la misma clave de caché (caché miss) | El bloqueo asyncio garantiza que solo una navegación ocurre; la segunda espera y reutiliza el resultado (ver sección 11 — concurrencia) |
| EC-06 | Jugador con una sola aldea | `VillageMapUseCase` devuelve lista de un elemento — no es error |
| EC-07 | Página de overview vacía (cuenta recién creada sin aldeas) | Parser devuelve lista vacía. El use case superior decide si eso es un error de negocio |
| EC-08 | Fixture incorrecto para la pestaña solicitada | El fixture `{page.value}.html` debe corresponder a la pestaña correcta. El adaptador no valida el contenido — es responsabilidad del autor del test |
| EC-09 | `world_id` no encontrado en el registro de browsers | Igual que EC-01 — `SessionNotActiveError` |
| EC-10 | Invalidación de caché por cambio de sesión (nuevo login) | `LiveOverviewAdapter.invalidate_cache(world_id)` borra todas las entradas del world_id. Se llama desde el `LoginUseCase` (o quien gestione el login) cuando re-autentica |
| EC-11 | `OverviewPage` solicitada no tiene fixture guardado | Igual que EC-03 — `OverviewFixtureNotFoundError` con el nombre de la página que falta |
| EC-12 | `_parse_time` recibe formato inesperado (no `H:MM:SS`) | La función ya maneja enteros pelados (ver scraper kirilloid). Si el formato es genuinamente inválido, propaga `ValueError`; el parser del bloque lo captura y devuelve `None` para ese campo |
| EC-13 | TTL expirado durante una petición en curso | Cuando la caché expira, la siguiente petición lo detecta y navega de nuevo. La petición en vuelo al expirar el TTL recibe el HTML fresco, no el expirado |

---

## 7. Modelo de datos / cambios de esquema

Este tronco NO modifica ninguna tabla SQLite existente y NO añade tablas nuevas.
Los datos de overview son efímeros (caché en memoria); solo los parsers del bloque
persisten lo que el negocio requiere.

### 7.1 `OverviewPage` — enum de páginas

```python
# core/ports/overview_html_source_port.py (junto al port)

from enum import Enum

class OverviewPage(Enum):
    """
    Identifica la pestaña de /village/statistics de Travian que se quiere leer.
    Cada valor mapea a una URL agregada (todas las aldeas en una sola página).

    La URL concreta la construye el LiveOverviewAdapter — el port no la expone.
    """
    OVERVIEW             = "overview"              # /village/statistics/overview
    RESOURCES            = "resources"             # /village/statistics/resources
    RESOURCES_PRODUCTION = "resources_production"  # /village/statistics/resources/production
    RESOURCES_CAPACITY   = "resources_capacity"    # /village/statistics/resources/capacity
    CULTURE_POINTS       = "culturepoints"         # /village/statistics/culturepoints
    TROOPS_OWN           = "troops_own"            # /village/statistics/troops/own
    TROOPS_SUPPORT       = "troops_support"        # /village/statistics/troops/support
    TROOPS_SMITHY        = "troops_smithy"         # /village/statistics/troops/smithy
    TROOPS_HOSPITAL      = "troops_hospital"       # /village/statistics/troops/hospital
    TROOPS_TRAINING      = "troops_training"       # /village/statistics/troops/training
```

Cuando los cuatro bloques necesiten pestañas adicionales, añaden valores al enum.
La firma del port (`get_page_html`) no cambia.

### 7.2 `VillageInfo` — DTO del índice de aldeas

```python
# core/use_cases/village_map.py (junto al use case)

from dataclasses import dataclass

@dataclass(frozen=True)
class VillageInfo:
    """
    Información mínima de una aldea extraída del overview.
    Inmutable: el índice no se modifica una vez construido.
    """
    game_id: int     # ID en Travian (aparece en URLs como gid=N o village=N)
    name:    str     # Nombre de la aldea tal como aparece en el overview
    x:       int     # Coordenada X en el mapa (extraída del overview si está disponible)
    y:       int     # Coordenada Y en el mapa (extraída del overview si está disponible)
```

Nota sobre `x` e `y`: la tabla `#overview` no expone las coordenadas de aldea de forma
estructural (no hay columna de coordenadas). Los campos se rellenan con `x=0, y=0` como
placeholder documentado. Las coordenadas son responsabilidad de un use case posterior
(mapa del mundo / World Map), fuera del alcance del tronco.

Nota sobre la tribu del jugador: opcionalmente derivable desde la página `TROOPS_HOSPITAL`
(`th.villageName > i.tribeN_medium` → N) o `TROOPS_TRAINING`
(`i.building_small.tribeN.typeNN` → N). Sin embargo, la tribu NO es responsabilidad del
`VillageMapUseCase`; pertenece a un use case del bloque troops. Solo se deja esta nota
para que ese bloque la aproveche al parsear sus páginas.

### 7.3 `CacheEntry` — estructura interna de la caché (privado al adaptador)

```python
# adapters/browser/live_overview_adapter.py  (uso interno, no expuesto por el port)

from dataclasses import dataclass
from datetime import datetime

@dataclass
class CacheEntry:
    html:      str
    cached_at: datetime
```

La caché vive en un dict `dict[tuple, CacheEntry]` en la instancia del adaptador.
No se persiste a disco ni a SQLite. Al reiniciar la API la caché arranca vacía.

---

## 8. Contratos de API / interfaces

No aplica directamente a este tronco. El tronco no expone endpoints HTTP propios.
Los endpoints los definen los cuatro bloques. Las convenciones de API que deben
respetar esos bloques se especifican en la sección 7 de Convenciones.

El tronco solo añade la dependency `get_html_source_port` a `dependencies.py`.

`apis_validadas_por_desarrollador_apis: n-a`

---

## 9. Flujo lógico paso a paso

### 9.1 `OverviewHtmlSourcePort` — interfaz del port

```python
# core/ports/overview_html_source_port.py

from abc import ABC, abstractmethod
from core.ports.overview_html_source_port import OverviewPage   # mismo fichero


class OverviewHtmlSourcePort(ABC):
    """
    Puerto que abstrae la fuente de HTML de las páginas de overview de Travian.

    Permite testear parsers con ficheros HTML (FixtureOverviewAdapter) y
    navegar Travian en producción (LiveOverviewAdapter) sin cambiar el código
    de los parsers ni de los use cases.

    Contrato:
      - get_page_html devuelve siempre HTML como str no vacío.
      - Si no puede obtener el HTML, lanza una excepción del dominio
        (nunca devuelve None ni str vacío).
      - Es seguro llamarlo concurrentemente para el mismo world_id
        (los adaptadores son responsables del locking si lo necesitan).
    """

    @abstractmethod
    async def get_page_html(
        self,
        world_id: int,
        page:     OverviewPage,
    ) -> str:
        """
        Devuelve el HTML crudo de la pestaña de statistics solicitada.

        Las páginas son agregadas: cada pestaña contiene TODAS las aldeas del jugador.
        No existe el concepto de "página por aldea" — el parser extrae las filas
        de cada aldea del HTML devuelto.

        Parámetros:
          world_id — ID del mundo (de la entidad World) que identifica la sesión.
          page     — Qué pestaña de /village/statistics se quiere (enum OverviewPage).

        Devuelve:
          str — HTML completo de la página. Nunca vacío, nunca None.

        Lanza:
          SessionNotActiveError        — si no hay browser/sesión activa (Live).
          OverviewPageNotLoadedError   — si la página no cargó en el timeout (Live).
          OverviewFixtureNotFoundError — si el fichero fixture no existe (Fixture).
        """

    @abstractmethod
    def invalidate_cache(self, world_id: int) -> None:
        """
        Invalida todas las entradas de caché para world_id.

        Seguro de llamar aunque no haya entradas (idempotente).
        En FixtureOverviewAdapter es no-op (no hay caché).
        """
```

### 9.2 `LiveOverviewAdapter` — caché + navegación

```python
# adapters/browser/live_overview_adapter.py

import asyncio
import os
from datetime import datetime, timezone, timedelta
from core.ports.overview_html_source_port import OverviewHtmlSourcePort, OverviewPage
from core.exceptions import SessionNotActiveError, OverviewPageNotLoadedError
from adapters.browser.driver import human_delay

# TTL configurable — default 60 s
OVERVIEW_CACHE_TTL_SECONDS = int(os.environ.get("OVERVIEW_CACHE_TTL_SECONDS", "60"))

# Timeout para esperar que la página cargue — default 30 s
OVERVIEW_PAGE_TIMEOUT = int(os.environ.get("OVERVIEW_PAGE_TIMEOUT_SECONDS", "30"))

# Selector estable que indica que la página de statistics cargó completamente.
# #content está presente en todas las pestañas de /village/statistics.
OVERVIEW_LOADED_SELECTOR = "#content"


class LiveOverviewAdapter(OverviewHtmlSourcePort):
    """
    Implementación viva del port: navega Travian con Chrome autenticado.

    El browser (zd.Browser) se obtiene a través de un callable inyectado:
        get_browser: Callable[[int], zd.Browser | None]
    donde el int es world_id.

    Mientras no exista SessionRegistry, get_browser puede ser None o una función
    que siempre devuelve None — el adaptador lanzará SessionNotActiveError
    de forma controlada. Esto permite registrar el adaptador en el lifespan
    hoy sin bloquear el desarrollo de los cuatro bloques.

    Caché:
      - Clave: (world_id, page)
      - Valor: CacheEntry(html, cached_at)
      - TTL: OVERVIEW_CACHE_TTL_SECONDS (configurable)
      - Invalidación: invalidate_cache(world_id) borra todas las entradas del mundo
      - Concurrencia: un asyncio.Lock por clave de caché evita navegaciones duplicadas
        cuando dos corrutinas piden la misma pestaña simultáneamente (cache miss)
    """

    def __init__(self, get_browser):
        """
        get_browser: Callable[[int], zd.Browser | None]
          Función (o método de SessionRegistry) que dado world_id devuelve
          el zd.Browser activo, o None si no hay sesión.

        Ejemplo de uso en el lifespan, ANTES de que exista SessionRegistry:
          adapter = LiveOverviewAdapter(get_browser=lambda wid: None)

        Ejemplo de uso CUANDO exista SessionRegistry:
          adapter = LiveOverviewAdapter(get_browser=session_registry.get_browser)
        """
        self._get_browser = get_browser
        self._cache: dict[tuple, CacheEntry] = {}
        self._locks: dict[tuple, asyncio.Lock] = {}

    async def get_page_html(
        self,
        world_id: int,
        page: OverviewPage,
    ) -> str:
        cache_key = (world_id, page)

        # --- Caché hit ---
        entry = self._cache.get(cache_key)
        if entry is not None:
            age = (datetime.now(timezone.utc) - entry.cached_at).total_seconds()
            if age < OVERVIEW_CACHE_TTL_SECONDS:
                return entry.html

        # --- Caché miss — adquirir lock por clave para evitar navegaciones duplicadas ---
        if cache_key not in self._locks:
            self._locks[cache_key] = asyncio.Lock()
        async with self._locks[cache_key]:
            # Re-verificar caché tras adquirir el lock (otro coroutine pudo haber llenado)
            entry = self._cache.get(cache_key)
            if entry is not None:
                age = (datetime.now(timezone.utc) - entry.cached_at).total_seconds()
                if age < OVERVIEW_CACHE_TTL_SECONDS:
                    return entry.html

            html = await self._navigate_and_get(world_id, page)
            self._cache[cache_key] = CacheEntry(html=html, cached_at=datetime.now(timezone.utc))
            return html

    async def _navigate_and_get(
        self,
        world_id: int,
        page: OverviewPage,
    ) -> str:
        browser = self._get_browser(world_id)
        if browser is None:
            raise SessionNotActiveError()

        url = _build_url(world_id, page)
        tab = await browser.get(url)
        await human_delay(500, 900)

        # Esperar #content — presente en todas las pestañas de /village/statistics
        try:
            await tab.wait_for(OVERVIEW_LOADED_SELECTOR, timeout=OVERVIEW_PAGE_TIMEOUT)
        except Exception:
            raise OverviewPageNotLoadedError(world_id, page)

        html = await tab.get_content()
        if not html or not html.strip():
            raise OverviewPageNotLoadedError(world_id, page)
        return html

    def invalidate_cache(self, world_id: int) -> None:
        keys_to_delete = [k for k in self._cache if k[0] == world_id]
        for k in keys_to_delete:
            del self._cache[k]
            self._locks.pop(k, None)
```

**Nota de implementación — construcción de URL:**
`_build_url(world_id, page)` necesita el `world.server` (URL base del servidor).
El `LiveOverviewAdapter` recibirá un segundo callable `get_world_server: Callable[[int], str]`
que devuelve la URL base dado el `world_id`. La implementación concreta se cableará junto
al `SessionRegistry`. Mientras no exista, puede ser `lambda wid: ""` — el adaptador lanzará
`SessionNotActiveError` antes de llegar a construir la URL porque el browser también será `None`.

Las URLs de cada `OverviewPage` (relativas a `{world.server}/`):

| OverviewPage | URL relativa al `world.server` |
|---|---|
| `OVERVIEW` | `village/statistics/overview` |
| `RESOURCES` | `village/statistics/resources` |
| `RESOURCES_PRODUCTION` | `village/statistics/resources/production` |
| `RESOURCES_CAPACITY` | `village/statistics/resources/capacity` |
| `CULTURE_POINTS` | `village/statistics/culturepoints` |
| `TROOPS_OWN` | `village/statistics/troops/own` |
| `TROOPS_SUPPORT` | `village/statistics/troops/support` |
| `TROOPS_SMITHY` | `village/statistics/troops/smithy` |
| `TROOPS_HOSPITAL` | `village/statistics/troops/hospital` |
| `TROOPS_TRAINING` | `village/statistics/troops/training` |

URLs verificadas con fixtures reales capturados desde `ts20.x2.america.travian.com` (T4.x).

### 9.3 `FixtureOverviewAdapter` — adaptador de test

```python
# adapters/browser/fixture_overview_adapter.py

from pathlib import Path
from core.ports.overview_html_source_port import OverviewHtmlSourcePort, OverviewPage
from core.exceptions import OverviewFixtureNotFoundError


class FixtureOverviewAdapter(OverviewHtmlSourcePort):
    """
    Implementación de test: devuelve HTML desde ficheros guardados en disco.

    fixtures_dir: Path al directorio con los fixtures HTML.
    Convención de nombre de fichero: {page.value}.html
    Ejemplos: overview.html, resources.html, troops_own.html

    invalidate_cache es no-op (no hay caché).
    """

    def __init__(self, fixtures_dir: Path):
        self._dir = fixtures_dir

    async def get_page_html(
        self,
        world_id: int,
        page: OverviewPage,
    ) -> str:
        filename = f"{page.value}.html"
        path = self._dir / filename
        if not path.exists():
            raise OverviewFixtureNotFoundError(page)
        return path.read_text(encoding="utf-8")

    def invalidate_cache(self, world_id: int) -> None:
        pass  # no-op
```

### 9.4 `VillageMapUseCase` — índice de aldeas

```python
# core/use_cases/village_map.py

from core.ports.overview_html_source_port import OverviewHtmlSourcePort, OverviewPage
from core.use_cases.village_map import VillageInfo   # mismo fichero


class VillageMapUseCase:
    """
    Extrae la lista de aldeas del jugador desde la página de overview principal.

    Esta lista es el índice compartido de los cuatro bloques.
    Se recomienda cachearlo en el caller (p.ej. por world_id) y no llamarlo
    en cada request individual.
    """

    async def execute(
        self,
        port: OverviewHtmlSourcePort,
        world_id: int,
    ) -> list[VillageInfo]:
        """
        Devuelve la lista de aldeas del jugador desde /village/statistics/overview.
        Lanza las mismas excepciones que port.get_page_html.
        """
        html = await port.get_page_html(
            world_id=world_id,
            page=OverviewPage.OVERVIEW,
        )
        return VillageOverviewParser.extract_villages(html)


class VillageOverviewParser:
    """
    Parser puro: dado el HTML de /village/statistics/overview, extrae la lista de aldeas.

    Selectores (verificados con fixture overview.html, T4.x Galos):
      - Filas de aldea: table#overview > tbody > tr que tengan td.vil.fc
      - game_id: href del enlace en td.vil.fc > a → parámetro newdid=N → int(N)
      - name: texto del mismo <a> (strip)
      - Ignorar tr.sum (fila de totales — no tiene td.vil.fc)
      - Coordenadas: NO están en la tabla overview → x=0, y=0 placeholder documentado

    Todos los selectores son estructurales — nunca por texto visible.
    """

    @staticmethod
    def extract_villages(html: str) -> list[VillageInfo]:
        """
        Parsea el HTML de /village/statistics/overview y devuelve la lista de aldeas.

        El implementador debe usar BeautifulSoup con 'html.parser' (stdlib Python,
        ya en requirements). Pasos:
          1. soup.select('table#overview > tbody > tr')
          2. Filtrar filas que tengan td.vil.fc
          3. Por cada fila: extraer href del a dentro de td.vil.fc, parsear newdid=N
          4. Extraer texto del mismo <a> como nombre de aldea
          5. Devolver VillageInfo(game_id=N, name=..., x=0, y=0)

        Devuelve lista vacía si no hay filas (cuenta recién creada sin aldeas).
        """
        from bs4 import BeautifulSoup
        import re

        soup = BeautifulSoup(html, "html.parser")
        villages = []
        for row in soup.select("table#overview > tbody > tr"):
            vil_cell = row.select_one("td.vil.fc")
            if vil_cell is None:
                continue  # tr.sum u otra fila sin aldea
            link = vil_cell.select_one("a[href*='newdid=']")
            if link is None:
                continue
            m = re.search(r"newdid=(\d+)", link["href"])
            if m is None:
                continue
            game_id = int(m.group(1))
            name = link.get_text(strip=True)
            villages.append(VillageInfo(game_id=game_id, name=name, x=0, y=0))
        return villages
```

### 9.5 Módulo de utilidades de parseo compartidas

```python
# core/utils/parsing.py  (NUEVO)
#
# Contiene las funciones de parseo puro extraídas de adapters/scraper/kirilloid_scraper.py.
# Son funciones sin dependencias externas — testables de forma aislada.

def parse_time(text: str) -> int:
    """Convierte "H:MM:SS" a segundos enteros. Ver kirilloid_scraper._parse_time."""
    ...  # misma implementación que _parse_time en kirilloid_scraper.py

def parse_int(text: str) -> int:
    """
    Convierte entero con separadores de miles a int.

    Elimina separadores de miles (. o ,) y caracteres de control bidi U+202D y U+202C
    que Travian inyecta alrededor de los números (ej: ‭8,786‬).
    Lanza ValueError si el texto no es convertible a int tras la limpieza.
    """
    ...

def parse_int_or_none(text: str) -> int | None:
    """
    Como parse_int pero devuelve None para "—", vacío o no numérico.
    También elimina caracteres bidi U+202D y U+202C antes de intentar la conversión.
    """
    ...
```

**Renaming:** las funciones pasan de nombres privados con guion bajo (`_parse_int`) a
nombres públicos sin guion bajo (`parse_int`). La razón: son utilidades de biblioteca,
no internos de un módulo; el guion bajo daría falsa sensación de privacidad.

**Impacto en kirilloid_scraper.py:**
- Las tres funciones originales se eliminan del módulo.
- Se añade al inicio del fichero: `from core.utils.parsing import parse_int, parse_int_or_none, parse_time`
- Las llamadas internas cambian de `_parse_int(...)` a `parse_int(...)`, etc.
- No hay cambio de comportamiento; todos los tests existentes siguen pasando.

**Tests de `core/utils/parsing.py`:**
- Mover los tests existentes de las tres funciones (que ya existen en
  `tests/unit/test_kirilloid_scraper.py` o similar) a `tests/unit/test_parsing_utils.py`.
- Añadir al menos los casos: separador punto, separador coma, "—", vacío,
  formato `H:MM:SS`, entero pelado sin ":", formato inválido.
- Añadir casos específicos con caracteres bidi U+202D (‭) y U+202C (‬) sueltos
  y combinados con separadores de miles (ej: `"‭8,786‬"` → `8786`).

### 9.6 `get_html_source_port` — dependency FastAPI

```python
# adapters/api/dependencies.py  (AÑADIR al fichero existente)

from core.ports.overview_html_source_port import OverviewHtmlSourcePort

def get_html_source_port(request: Request) -> OverviewHtmlSourcePort:
    """
    Devuelve el singleton de OverviewHtmlSourcePort almacenado en app.state.
    Se inicializa en el lifespan de la aplicación.
    """
    return request.app.state.html_source_port
```

### 9.7 Registro en `lifespan` de `main.py`

```python
# adapters/api/main.py — bloque lifespan (MODIFICAR — añadir tras game_data_adapter)

import os
from adapters.browser.live_overview_adapter import LiveOverviewAdapter
from adapters.browser.fixture_overview_adapter import FixtureOverviewAdapter

# Dentro del lifespan, tras inicializar game_data_port:

OVERVIEW_SOURCE = os.environ.get("OVERVIEW_SOURCE", "fixture").lower()

if OVERVIEW_SOURCE == "live":
    # get_browser y get_world_server se cablearán cuando exista SessionRegistry.
    # Por ahora, lambda que devuelve None → SessionNotActiveError controlado.
    html_source_port = LiveOverviewAdapter(
        get_browser=lambda wid: None,
        get_world_server=lambda wid: "",
    )
else:
    # "fixture" — default; usa HTML capturado manualmente en tests/fixtures/overview/
    fixtures_dir = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "overview"
    html_source_port = FixtureOverviewAdapter(fixtures_dir=fixtures_dir)

application.state.html_source_port = html_source_port
```

---

## 10. Validaciones y reglas

| Elemento | Validación | Dónde |
|---|---|---|
| `OverviewPage` | Solo valores del enum — FastAPI/Python valida automáticamente | `OverviewHtmlSourcePort.get_page_html` recibe el enum, no un string |
| HTML devuelto por `LiveOverviewAdapter` | No vacío ni solo whitespace | `_navigate_and_get` verifica `html.strip()` antes de cachear |
| `VillageInfo.game_id` | Entero positivo — extraído del atributo `newdid=N` del href; nunca del texto | `VillageOverviewParser.extract_villages` |
| `VillageInfo.name` | String no vacío — si el parser no encuentra nombre, omitir la aldea con warning | `VillageOverviewParser.extract_villages` |
| Fixture HTML | Fichero UTF-8 existente con nombre `{page.value}.html` | `FixtureOverviewAdapter.get_page_html` verifica `path.exists()` |
| Caracteres bidi en números | `parse_int` y `parse_int_or_none` deben eliminar U+202D y U+202C antes de convertir | `core/utils/parsing.py` |
| `Accept-Language` en endpoints de los bloques | Obligatoria — `get_language` (no `optional`) | Los handlers de los cuatro bloques heredan esta regla por convención |

---

## 11. Seguridad, rendimiento y concurrencia

### Anti-detección

El `LiveOverviewAdapter` navega Travian usando el browser ya configurado con todas las
capas de anti-detección descritas en `CLAUDE.md` (sin headless, UA dinámico, perfil
persistente, delays humanos). El adaptador NO modifica esas capas.

Regla específica: tras `browser.get(url)` en `_navigate_and_get`, se llama a
`human_delay(500, 900)` antes de esperar el selector. Esto imita el tiempo de
render perception de un humano real — no omitir aunque parezca innecesario.

### Rendimiento

- La caché in-memory con TTL de 60 s amortiza el coste de navegación (~2-4 s) en
  peticiones repetidas dentro del mismo intervalo.
- El TTL es configurable (`OVERVIEW_CACHE_TTL_SECONDS`) sin reiniciar el adaptador.
- La caché no tiene límite de entradas. Con N aldeas × M páginas × P worlds, el consumo
  de RAM es proporcional. Para un bot de una sola cuenta con ~10 aldeas y 5 tipos de
  página, el máximo teórico son ~50 entradas de HTML (~50 KB/entrada = < 3 MB). Aceptable.

### Concurrencia

- Un `asyncio.Lock` por clave de caché garantiza que si dos coroutines piden la misma
  página simultáneamente (cache miss), solo una navega; la segunda espera y reutiliza
  el HTML fresco (double-checked locking, patrón estándar en asyncio).
- `invalidate_cache` se llama desde un contexto de control (login); no necesita lock
  propio porque en Python GIL garantiza atomicidad de `del dict[key]`.
- La caché no es thread-safe para uso multithreading. Este proyecto usa asyncio puro;
  no hay threads. Si en el futuro se introducen threads, revisar esta sección.

### Seguridad

- El HTML que devuelve el port se usa solo para parsear datos propios del bot. No se
  reenvía al cliente externo. No hay riesgo de XSS desde el HTML de Travian.
- Las URLs de Travian construidas en `_build_url` no deben loguear credenciales ni
  tokens de sesión si los hubiera en los parámetros. Usar logger con nivel DEBUG y
  enmascarar cualquier campo sensible con `_mask_frame_locals` de `main.py`.

---

## 12. Plan de pruebas

### Tests del tronco (sin Chrome)

#### 12.1 `FixtureOverviewAdapter`

| Test | Descripción | Resultado esperado |
|---|---|---|
| `test_fixture_returns_html` | Fixture existe, llamar `get_page_html(world_id, OverviewPage.OVERVIEW)` | Devuelve el contenido de `overview.html` |
| `test_fixture_not_found` | Fichero `{page.value}.html` no existe | Lanza `OverviewFixtureNotFoundError` |
| `test_fixture_invalidate_noop` | Llamar `invalidate_cache` | No lanza, no falla |
| `test_fixture_all_pages` | Llamar con cada uno de los 10 valores del enum con fixture presente | Devuelve HTML del fichero correspondiente |

#### 12.2 `LiveOverviewAdapter` (sin Chrome — mocks)

| Test | Descripción | Resultado esperado |
|---|---|---|
| `test_live_session_not_active` | `get_browser` devuelve None | Lanza `SessionNotActiveError` |
| `test_live_cache_hit` | Segunda llamada idéntica dentro del TTL | No llama a `_navigate_and_get` (mock verifica 0 llamadas) |
| `test_live_cache_miss_after_ttl` | Segunda llamada tras TTL expirado | Llama a `_navigate_and_get` una segunda vez |
| `test_live_invalidate_cache` | Llamar `invalidate_cache(world_id)` | Próxima llamada vuelve a navegar |
| `test_live_concurrent_cache_miss` | Dos coroutines simultáneas, caché vacía | Solo una navegación ocurre (mock verifica 1 llamada) |
| `test_live_empty_html_raises` | `_navigate_and_get` devuelve HTML vacío | Lanza `OverviewPageNotLoadedError` |

#### 12.3 `VillageMapUseCase`

Fixture disponible: `tests/fixtures/overview/overview.html` (servidor T4.x, tribu Galos).

| Test | Descripción | Resultado esperado |
|---|---|---|
| `test_village_map_from_fixture` | Usar `overview.html` real | Lista de `VillageInfo` con `game_id` y `name` correctos para cada aldea del jugador; `x=0, y=0` en todos |
| `test_village_map_single_village` | HTML sintético con 1 fila tr con td.vil.fc | Lista de 1 `VillageInfo` con `game_id` correcto |
| `test_village_map_multiple_villages` | HTML sintético con N filas tr con td.vil.fc | Lista de N `VillageInfo`; tr.sum ignorada |
| `test_village_map_empty_page` | HTML sin filas td.vil.fc (cuenta nueva) | Lista vacía, sin excepción |
| `test_village_map_port_error_propagates` | Port lanza `SessionNotActiveError` | La excepción se propaga sin envolver |

#### 12.4 `core/utils/parsing.py`

| Test | Descripción | Resultado esperado |
|---|---|---|
| `test_parse_int_dot_separator` | `"1.200"` | `1200` |
| `test_parse_int_comma_separator` | `"1,200"` | `1200` |
| `test_parse_int_no_separator` | `"400"` | `400` |
| `test_parse_int_invalid` | `"abc"` | Lanza `ValueError` |
| `test_parse_int_bidi_lro` | `"‭8‬"` (solo bidi) | `8` |
| `test_parse_int_bidi_with_comma` | `"‭8,786‬"` (bidi + separador) | `8786` |
| `test_parse_int_bidi_nested` | `"‭‭14‬/‭14‬‬"` (nested) | primera parte = `14` (o normalizar el texto completo antes de dividir) |
| `test_parse_int_or_none_dash` | `"—"` | `None` |
| `test_parse_int_or_none_empty` | `""` | `None` |
| `test_parse_int_or_none_valid` | `"120"` | `120` |
| `test_parse_int_or_none_bidi` | `"‭120‬"` | `120` |
| `test_parse_time_hmmss` | `"1:30:00"` | `5400` |
| `test_parse_time_zero` | `"0:00:00"` | `0` |
| `test_parse_time_bare_int` | `"0"` | `0` |
| `test_parse_time_with_suffix` | `"0:30:00 / 2880 / jornada"` | `1800` |
| `test_parse_time_invalid` | `"abc"` | Lanza `ValueError` |

**Nota sobre fiestas:** los `span.timer[data-value]` en la página `culturepoints` exponen
los segundos restantes ya calculados como atributo (`data-value="N"`). Preferir leer ese
atributo entero directamente antes que parsear el texto `H:MM:SS`.

#### 12.5 Regresión kirilloid — verificar que el refactor no rompe nada

```bash
python -m pytest tests/unit/test_kirilloid_scraper.py tests/unit/test_parsing_utils.py -v
```

Todos los tests del scraper deben seguir pasando tras mover las funciones.

---

## 13. Riesgos y trade-offs

### TR-01 — Browser no disponible hasta que exista `SessionRegistry` (riesgo principal)

**Problema:** `LiveOverviewAdapter` necesita un `zd.Browser` vivo para navegar Travian.
El `SessionRegistry` (implementación concreta de `WorldRuntimePort`) está diferido y
no existe todavía. Sin él, el adaptador no puede navegar.

**Decisión:** Inyectar el browser como callable (`get_browser: Callable[[int], Browser | None]`).
Hoy se inyecta un lambda que siempre devuelve `None`. El adaptador lanza `SessionNotActiveError`
de forma controlada. El `lifespan` registra el adaptador con esta lambda temporal.
Cuando exista el `SessionRegistry`, el lambda se reemplaza por `session_registry.get_browser`
sin cambiar ni el port ni los handlers.

**Alternativa rechazada:** No registrar `LiveOverviewAdapter` en el lifespan hasta que
exista el `SessionRegistry`. Se rechaza porque bloquea el desarrollo de los cuatro bloques
y el testing de integración parcial.

**Riesgo residual:** Un endpoint de bloque en producción (con `OVERVIEW_SOURCE=live`)
siempre devolverá `503 Session Not Active` hasta que se cablee el `SessionRegistry`.
El equipo debe documentar esto como comportamiento esperado hasta esa feature.

### TR-02 — `BeautifulSoup` vs parseo con `lxml` directo

**Problema:** Los parsers de overview necesitan parsear HTML. ¿`BeautifulSoup` o `lxml`?

**Decisión:** `BeautifulSoup` con `html.parser` (stdlib Python, sin dependencias C).
Razones: ya está en el proyecto (verificar `requirements.txt`); API más legible para
selectores CSS; suficientemente rápido para HTML de una página de Travian (~50 KB).

**Alternativa:** `lxml` es más rápido (~3-5x) pero requiere compilación nativa en ARM64.
En Raspberry Pi 4B esto añade complejidad en el `start.sh`. No se justifica para
operaciones sobre páginas individuales.

**Si `BeautifulSoup` no está en `requirements.txt`:** añadir `beautifulsoup4>=4.12`.

### TR-03 — Selectores de `VillageOverviewParser` fijados con HTML real

**Problema original:** Sin HTML real no se podían fijar selectores. Ya resuelto.

**Decisión:** Los selectores se derivan del fixture `overview.html` (T4.x, Galos,
`ts20.x2.america.travian.com`). Selector de fila: `table#overview > tbody > tr` con
`td.vil.fc`. `game_id` vía `newdid=N` del href. Nombre vía texto del `<a>`. Coordenadas
no disponibles en esta tabla → `x=0, y=0` placeholder.

**Riesgo residual bajo:** Si Travian cambia el ID `#overview` o la clase `vil.fc` en una
actualización de servidor, el selector rompe. Mitigación: los selectores son estructurales
(no dependen de texto visible), y los fixtures de test detectarán la rotura antes de llegar
a producción.

### TR-04 — Caché in-memory vs caché SQLite

**Decisión:** In-memory (dict en la instancia del adaptador).
Razones: el TTL de 60 s hace que la persistencia sea irrelevante; al reiniciar la API
el bot vuelve a navegar naturalmente; SQLite añadiría serialización/deserialización de
HTML sin beneficio visible.

**Riesgo:** Si la API se reinicia frecuentemente (deploys), los primeros segundos serán
más lentos por cache miss. Aceptable: el bot se usa continuamente, no en rafagas.

### TR-05 — Nombre del módulo: `core/utils/parsing.py` vs mantenerlo en `adapters/`

**Decisión:** Mover a `core/utils/parsing.py`.
Razones: las funciones son puras (sin IO, sin dependencias externas); vivir en `adapters/`
sugeriría que tienen efectos de infraestructura. Moverlas al `core/` respeta la
arquitectura hexagonal — el core puede tener utilidades puras.

**Impacto:** El import en `kirilloid_scraper.py` cambia. Un test de regresión confirma
que nada se rompe.

---

## 14. Pasos de implementación ordenados

El orden respeta dependencias de importación: core primero, adapters después, wiring al final.

1. **`core/utils/parsing.py`** — CREAR. Copiar las tres funciones desde
   `adapters/scraper/kirilloid_scraper.py`, renombrar a nombres públicos, añadir docstrings.

2. **`adapters/scraper/kirilloid_scraper.py`** — MODIFICAR. Eliminar las tres funciones
   duplicadas, añadir import desde `core.utils.parsing`. Cambiar todas las llamadas
   `_parse_int` → `parse_int`, etc.

3. **`tests/unit/test_parsing_utils.py`** — CREAR. Tests de las tres funciones utilitarias
   (casos de la sección 12.4). Ejecutar y verificar que pasan.

4. **Verificar regresión kirilloid:**
   ```bash
   python -m pytest tests/unit/test_kirilloid_scraper.py -v
   ```
   Todos los tests existentes deben seguir pasando.

5. **`core/exceptions.py`** — MODIFICAR. Añadir tres nuevas excepciones:
   ```python
   class OverviewPageNotLoadedError(TravianBotError): ...
   class OverviewFixtureNotFoundError(TravianBotError): ...
   ```
   Ver contratos en sección 9.1.

6. **`core/ports/overview_html_source_port.py`** — CREAR. Contiene el enum `OverviewPage`
   y la clase abstracta `OverviewHtmlSourcePort` (sección 9.1).

7. **`core/use_cases/village_map.py`** — CREAR. Contiene `VillageInfo`, `VillageMapUseCase`
   y `VillageOverviewParser` con `NotImplementedError` hasta tener el fixture.

8. **`adapters/browser/fixture_overview_adapter.py`** — CREAR. Implementación de test
   (sección 9.3). Plenamente funcional, no depende de Chrome.

9. **`tests/unit/test_fixture_overview_adapter.py`** — CREAR. Tests de la sección 12.1.
   Crear fixtures de prueba en `tests/fixtures/overview/` para hacer pasar los tests.

10. **`adapters/browser/live_overview_adapter.py`** — CREAR. Implementación viva con caché
    (sección 9.2). `get_browser` recibe lambda que devuelve None (temporal).

11. **`tests/unit/test_live_overview_adapter.py`** — CREAR. Tests de la sección 12.2.
    Mockear `_navigate_and_get` para no depender de Chrome.

12. **`adapters/api/dependencies.py`** — MODIFICAR. Añadir `get_html_source_port`
    (sección 9.6).

13. **`adapters/api/main.py`** — MODIFICAR. Añadir al `lifespan` la inicialización de
    `html_source_port` (sección 9.7). Añadir imports necesarios.

14. **`tests/fixtures/overview/`** — Ya existe con los 10 fixtures reales (ver sección 17).
    Verificar que los 10 ficheros están presentes antes de ejecutar los tests.

15. **`VillageOverviewParser.extract_villages`** — IMPLEMENTAR con los selectores de la
    sección 9.4. Crear tests en `tests/unit/test_village_map.py` usando `overview.html`
    (fixture real) y HTML sintético para los casos de edge (aldea única, lista vacía).

---

## 15. Criterios de aceptación

Checklist verificable por el implementador:

### Utilidades de parseo

- [ ] `core/utils/parsing.py` existe con tres funciones: `parse_int`, `parse_int_or_none`, `parse_time`.
- [ ] `parse_int` y `parse_int_or_none` eliminan U+202D y U+202C antes de convertir.
- [ ] Las tres funciones tienen comportamiento idéntico a sus contrapartes en `kirilloid_scraper.py` (más el nuevo manejo bidi).
- [ ] `kirilloid_scraper.py` ya no define las tres funciones; importa desde `core.utils.parsing`.
- [ ] Todos los tests de kirilloid siguen pasando tras el refactor.
- [ ] `tests/unit/test_parsing_utils.py` existe con los casos de la sección 12.4 (incluidos los casos bidi).

### Port y enum

- [ ] `OverviewPage` tiene exactamente los 10 valores especificados en la sección 7.1.
- [ ] `OverviewHtmlSourcePort` es ABC con métodos `get_page_html` e `invalidate_cache`.
- [ ] `get_page_html` tiene firma: `(world_id: int, page: OverviewPage) -> str` (sin `village_game_id`).
- [ ] `invalidate_cache` tiene firma: `(world_id: int) -> None`.

### Excepciones nuevas

- [ ] `OverviewPageNotLoadedError` existe en `core/exceptions.py`, hereda de `TravianBotError`.
- [ ] `OverviewFixtureNotFoundError` existe en `core/exceptions.py`, hereda de `TravianBotError`.

### `FixtureOverviewAdapter`

- [ ] Existe en `adapters/browser/fixture_overview_adapter.py`.
- [ ] Implementa `OverviewHtmlSourcePort`.
- [ ] Lanza `OverviewFixtureNotFoundError` si el fichero no existe.
- [ ] Convención de nombre de fichero: `{page.value}.html` (ej: `overview.html`, `troops_own.html`).
- [ ] `invalidate_cache` es no-op (no lanza).
- [ ] 4 tests de la sección 12.1 pasan.

### `LiveOverviewAdapter`

- [ ] Existe en `adapters/browser/live_overview_adapter.py`.
- [ ] Implementa `OverviewHtmlSourcePort`.
- [ ] Recibe `get_browser` como callable inyectado en `__init__`.
- [ ] Lanza `SessionNotActiveError` si `get_browser(world_id)` devuelve `None`.
- [ ] Caché: hit dentro de TTL no llama a `_navigate_and_get`.
- [ ] Caché: miss tras TTL sí llama a `_navigate_and_get`.
- [ ] `invalidate_cache(world_id)` elimina todas las entradas del mundo y sus locks.
- [ ] Double-checked locking: peticiones concurrentes al mismo cache miss generan 1 sola navegación.
- [ ] `human_delay(500, 900)` se llama tras `browser.get(url)`.
- [ ] 6 tests de la sección 12.2 pasan.

### `VillageMapUseCase`

- [ ] `VillageInfo` es dataclass frozen con campos: `game_id: int`, `name: str`, `x: int`, `y: int`.
- [ ] `VillageMapUseCase.execute` llama a `port.get_page_html` con `page=OverviewPage.OVERVIEW`.
- [ ] `VillageOverviewParser.extract_villages` implementado con los selectores de la sección 9.4.
- [ ] Devuelve `x=0, y=0` para todas las aldeas (placeholder documentado).
- [ ] 5 tests de la sección 12.3 pasan (incluido `test_village_map_from_fixture` con `overview.html` real).

### Wiring FastAPI

- [ ] `get_html_source_port` existe en `adapters/api/dependencies.py`.
- [ ] `app.state.html_source_port` se inicializa en el `lifespan`.
- [ ] Variable de entorno `OVERVIEW_SOURCE=live` activa `LiveOverviewAdapter`.
- [ ] Variable de entorno `OVERVIEW_SOURCE=fixture` (o ausente) activa `FixtureOverviewAdapter`.
- [ ] El `lifespan` no falla al arrancar con `OVERVIEW_SOURCE=live` (el lambda temporal es válido).

### Fixtures

- [ ] `tests/fixtures/overview/` existe en el repo con los 10 ficheros de la sección 17.
- [ ] Los 10 ficheros son legibles por `FixtureOverviewAdapter` con sus respectivos `OverviewPage`.

### Lo que NO debe ocurrir (regresión)

- [ ] Los tests existentes de kirilloid y del scraper siguen pasando.
- [ ] Ningún import del proyecto queda roto por el movimiento de las funciones de parseo.
- [ ] `main.py` arranca sin error con `OVERVIEW_SOURCE=fixture` (modo de test).

---

## 16. Convenciones para los cuatro bloques

Esta sección es el contrato que los equipos de overview, resources, culture-points y
troops DEBEN respetar al construir sus bloques sobre este tronco.

### Prefijo de rutas

Todos los endpoints de datos vivos usan el prefijo **`/game/`**:

```
GET /game/overview/{world_id}
GET /game/resources/{world_id}
GET /game/culture-points/{world_id}
GET /game/troops/{world_id}
```

Las respuestas son agregadas (todas las aldeas del mundo). El `world_id` identifica la sesión.
Los bloques pueden añadir sub-rutas por pestaña (ej: `/game/resources/{world_id}/production`)
siguiendo el mismo patrón.

**Por qué no `/catalog/`:** el middleware `add_catalog_cache_control` en `main.py`
cachea durante 1 hora todo lo que empieza por `/catalog/`. Los datos de overview son
vivos con TTL de 60 s; el cache de 1 h los corrompería.

### Accept-Language

Todos los endpoints de overview usan la dependencia **`get_language`** (obligatoria).
No `get_language_optional`. Si el handler necesita texto localizado, el idioma es
requerido siempre.

### Estructura de carpetas de parsers y DTOs

```
adapters/browser/parsers/
    overview_parser.py       # Parsers del bloque overview
    resources_parser.py      # Parsers del bloque resources
    culture_points_parser.py
    troops_parser.py

adapters/api/routes/
    game_overview.py         # Router del bloque overview
    game_resources.py
    game_culture_points.py
    game_troops.py

core/use_cases/
    overview_use_case.py     # Use case del bloque overview
    resources_use_case.py
    # etc.

core/dtos/                   # (CREAR si no existe)
    overview_dto.py          # DTOs de respuesta del bloque overview
    resources_dto.py
    # etc.
```

Los parsers viven en `adapters/browser/parsers/` (no en `core/`) porque dependen de
la estructura HTML de Travian — son infraestructura, no lógica de dominio puro.

### Naming de fixtures de test

Los fixtures son páginas agregadas (todas las aldeas). Convención: `{OverviewPage.value}.html`.

```
tests/fixtures/overview/
    overview.html              # OverviewPage.OVERVIEW
    resources.html             # OverviewPage.RESOURCES
    resources_production.html  # OverviewPage.RESOURCES_PRODUCTION
    resources_capacity.html    # OverviewPage.RESOURCES_CAPACITY
    culturepoints.html         # OverviewPage.CULTURE_POINTS
    troops_own.html            # OverviewPage.TROOPS_OWN
    troops_support.html        # OverviewPage.TROOPS_SUPPORT
    troops_smithy.html         # OverviewPage.TROOPS_SMITHY
    troops_hospital.html       # OverviewPage.TROOPS_HOSPITAL
    troops_training.html       # OverviewPage.TROOPS_TRAINING
```

Los 10 fixtures reales ya están presentes en `tests/fixtures/overview/`
(ver `tests/fixtures/overview/README.md`).

### Patrón de un parser de bloque

```python
# adapters/browser/parsers/overview_parser.py

from bs4 import BeautifulSoup
from core.utils.parsing import parse_int, parse_int_or_none, parse_time


class OverviewParser:
    """
    Parsers HTML para el bloque overview.
    Todos los métodos son estáticos — no dependen de estado.
    Todos reciben html: str y devuelven datos Python puros.
    """

    @staticmethod
    def extract_incoming_movements(html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        # ... selectores estructurales ...
```

### Patrón de un handler de bloque

```python
# adapters/api/routes/game_overview.py

from fastapi import APIRouter, Depends
from adapters.api.dependencies import get_language, get_html_source_port
from core.ports.overview_html_source_port import OverviewHtmlSourcePort

router = APIRouter(prefix="/game", tags=["game-overview"])

@router.get("/overview/{world_id}")
async def get_overview(
    world_id: int,
    lang: str = Depends(get_language),
    port: OverviewHtmlSourcePort = Depends(get_html_source_port),
):
    # Las páginas son agregadas: port.get_page_html devuelve todas las aldeas.
    # El use case/parser extrae la fila de cada aldea del HTML resultante.
    # ... use case ...
```

---

## 17. Fixtures disponibles

Los 10 fixtures HTML reales ya están capturados en `tests/fixtures/overview/`.
Servidor fuente: `ts20.x2.america.travian.com` (T4.x, tribu Galos / `tribe3`).
Consultar `tests/fixtures/overview/README.md` para selectores detallados por pestaña.

| Fixture | `OverviewPage` | URL origen |
|---|---|---|
| `overview.html` | `OVERVIEW` | `village/statistics/overview` |
| `resources.html` | `RESOURCES` | `village/statistics/resources` |
| `resources_production.html` | `RESOURCES_PRODUCTION` | `village/statistics/resources/production` |
| `resources_capacity.html` | `RESOURCES_CAPACITY` | `village/statistics/resources/capacity` |
| `culturepoints.html` | `CULTURE_POINTS` | `village/statistics/culturepoints` |
| `troops_own.html` | `TROOPS_OWN` | `village/statistics/troops/own` |
| `troops_support.html` | `TROOPS_SUPPORT` | `village/statistics/troops/support` |
| `troops_smithy.html` | `TROOPS_SMITHY` | `village/statistics/troops/smithy` |
| `troops_hospital.html` | `TROOPS_HOSPITAL` | `village/statistics/troops/hospital` |
| `troops_training.html` | `TROOPS_TRAINING` | `village/statistics/troops/training` |

El implementador debe usar estos ficheros directamente — no necesita capturar HTML adicional
para implementar el tronco ni el `VillageOverviewParser`.

---

## 18. Trazabilidad

| Decisión técnica | Requisito o edge case que la origina |
|---|---|
| `OverviewHtmlSourcePort` como puerto abstracto | RN-04: parsers testables sin Chrome; RN-06: el core no debe conocer zendriver |
| `OverviewPage` como enum (no string) | RN-07: evitar strings mágicos; seguridad de tipos en tiempo de compilación |
| Inyección del browser como callable | TR-01: `SessionRegistry` diferido; permite registrar el adaptador hoy sin bloquearse |
| Double-checked locking en caché | EC-05: dos peticiones simultáneas con cache miss no deben generar dos navegaciones |
| TTL configurable via variable de entorno | RN-03: el TTL debe ser ajustable sin desplegar código |
| `FixtureOverviewAdapter` como implementación primaria de tests | RN-04: los cuatro bloques deben poder testearse sin Chrome real desde el día 1 |
| Selectores de `VillageOverviewParser`: `table#overview > tbody > tr` con `td.vil.fc`, `newdid=N` del href | RN-05: selectores estructurales; TR-03 resuelto con fixture `overview.html` real |
| `x=0, y=0` placeholder en `VillageInfo` | La tabla `#overview` no expone coordenadas estructuralmente; coordenadas son responsabilidad del bloque World Map |
| Mover utils de parseo a `core/utils/parsing.py` | TR-05: funciones puras pertenecen al core; evita duplicación entre kirilloid y parsers de overview |
| Prefijo `/game/` en lugar de `/catalog/` | RN-08: el middleware de caché de catálogo (1h) corrompería datos vivos |
| `get_language` obligatoria (no optional) en endpoints de overview | RN-09: los datos de overview incluyen texto localizado; el idioma siempre es necesario |
| `OVERVIEW_SOURCE` variable de entorno | RN-10: un solo adaptador activo por entorno; selección sin cambiar código |
| `human_delay(500, 900)` tras `browser.get(url)` | Anti-detección no negociable (CLAUDE.md): simular tiempo de render perception humano |
| `invalidate_cache(world_id)` en el port (no solo en el adaptador) | EC-10: el `LoginUseCase` necesita invalidar la caché sin conocer la implementación concreta del adaptador |
| `VillageInfo` como `frozen=True` dataclass | El índice de aldeas es de solo lectura; la inmutabilidad previene modificaciones accidentales por los bloques |
| Tests de `VillageMapUseCase` con fixture real `overview.html` | TR-03 resuelto: fixture disponible, tests desbloqueados |
| Eliminación de `village_game_id` de la firma del port | RN-01 corregido: las páginas son agregadas; no existe el concepto de página por aldea |
| Clave de caché `(world_id, page)` sin `village_game_id` | Consecuencia directa del modelo agregado — EC-05 sigue cubierto con la clave reducida |
| `OVERVIEW_LOADED_SELECTOR = "#content"` | Selector verificado con fixtures reales: `#content` presente en todas las pestañas de `/village/statistics` |
| `parse_int` / `parse_int_or_none` eliminan U+202D y U+202C | EC (nuevo): Travian envuelve números con caracteres bidi; sin limpieza, `int()` lanza `ValueError` |

---

## Registro de implementación

**Fecha:** 2026-05-26
**Implementado por:** desarrollador-funcionalidades

### Ficheros creados

| Fichero | Descripción |
|---|---|
| `core/utils/__init__.py` | Paquete utils del core |
| `core/utils/parsing.py` | `parse_int`, `parse_int_or_none`, `parse_time` con limpieza bidi U+202D/U+202C |
| `core/ports/overview_html_source_port.py` | `OverviewPage` (10 valores) + `OverviewHtmlSourcePort` (ABC) |
| `core/use_cases/village_map.py` | `VillageInfo`, `VillageMapUseCase`, `VillageOverviewParser` |
| `adapters/browser/fixture_overview_adapter.py` | Adaptador de test que lee HTML desde disco |
| `adapters/browser/live_overview_adapter.py` | Adaptador vivo con caché TTL + double-checked locking |
| `tests/unit/test_parsing_utils.py` | 30 tests de las tres funciones (incluidos casos bidi) |
| `tests/unit/test_fixture_overview_adapter.py` | 8 tests del adaptador de fixtures |
| `tests/unit/test_live_overview_adapter.py` | 10 tests del adaptador vivo (sin Chrome, con mocks) |
| `tests/unit/test_village_map.py` | 11 tests del use case y parser (con fixture real overview.html) |

### Ficheros modificados

| Fichero | Cambio |
|---|---|
| `adapters/scraper/kirilloid_scraper.py` | Eliminadas las tres funciones privadas de parseo; añadido import desde `core.utils.parsing`; renombradas todas las llamadas internas |
| `tests/unit/test_kirilloid_scraper.py` | Import de `_parse_int`/`_parse_int_or_none`/`_parse_time` redirigido a `core.utils.parsing` (alias para no cambiar los tests) |
| `core/exceptions.py` | Añadidas `OverviewPageNotLoadedError` y `OverviewFixtureNotFoundError` |
| `adapters/api/dependencies.py` | Añadida `get_html_source_port` |
| `adapters/api/main.py` | Imports de adaptadores + wiring en lifespan con `OVERVIEW_SOURCE` |
| `requirements.txt` | Añadida `beautifulsoup4>=4.12` (no estaba instalada — TR-02) |

### Comando para ejecutar los tests

```bash
source .venv/bin/activate && pytest tests/unit/test_parsing_utils.py tests/unit/test_kirilloid_scraper.py tests/unit/test_fixture_overview_adapter.py tests/unit/test_live_overview_adapter.py tests/unit/test_village_map.py -v
```

Suite completa (sin tests que requieren Chrome):

```bash
source .venv/bin/activate && pytest --ignore=tests/antideteccion -v
```

### Resultado

271/271 tests pasan. 0 regresiones en los tests preexistentes.

### Desviaciones respecto al diseño

1. **`beautifulsoup4` no estaba en `requirements.txt`**: detectado durante la implementación. Añadida la dependencia tal como indica el spec (TR-02: "Si `BeautifulSoup` no está en `requirements.txt`: añadir `beautifulsoup4>=4.12`"). Desviación menor esperada y autorizada por el spec.

2. **Helper `_make_overview_html` en los tests**: el HTML sintético de la `tr.sum` inicialmente incluía `td.vil.fc` por error del test, no del parser. Corregido el helper para generar correctamente una `tr.sum` sin esa clase (como en el HTML real de Travian). El parser es correcto; el defecto era del helper de test.

3. **Import en `test_kirilloid_scraper.py`**: se usan alias (`parse_int as _parse_int`) para mantener los tests existentes sin tocarlos, cumpliendo el requisito de regresión de la sección 12.5. Es la mínima desviación posible para respetar el contrato de regresión.
