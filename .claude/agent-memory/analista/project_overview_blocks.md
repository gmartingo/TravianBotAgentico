---
name: project-overview-blocks
description: Decisiones de diseño de los cuatro bloques de lectura de overview (overview, resources, culture-points, troops) construidos sobre el tronco común
metadata:
  type: project
---

## Bloque overview (spec: docs/specs/lectura-overview.md)

- Endpoint: `GET /game/overview/{world_id}` + `Accept-Language` obligatoria
- Fuente: `OverviewPage.OVERVIEW` (fixture `overview.html`)
- Parser: `adapters/browser/parsers/overview_parser.py` → `OverviewParser.extract_overview_data(html)`
- DTOs: `core/dtos/overview_dto.py` (TroopMovementDTO, BuildingInProgressDTO, TroopPresentDTO, OverviewVillageDTO, OverviewResponseDTO)
- Use case: `core/use_cases/overview_use_case.py` → orquesta VillageMapUseCase + OverviewParser
- Router: `adapters/api/routes/game_overview.py`

### Hallazgos clave del fixture overview.html

- Tabla `#overview`, 6 aldeas reales (tribu Galos, ts20.x2.america.travian.com T4.x)
- **NO hay `tr.sum`** en esta tabla (a diferencia de `#ressources` que sí lo tiene)
- `td.att`: movimientos via `img` con clase CSS como tipo (`def1`, `att2`), cantidad en prefijo del `alt` ("618x ...")
  - Verificados: `def1` = refuerzos llegando, `att2` = tropas propias en ataque
  - NO verificados (a confirmar con HTML real): ataques enemigos entrantes, atracos, etc.
- `td.bui`: `img.bau`, nombre del edificio en `alt` (idioma-dependiente del servidor)
- `td.tro`: `img.unit.uNN`, NO es cola de entrenamiento — son tropas presentes/destacadas
  - El usuario describió como "entrenando" pero el fixture muestra tropas ya entrenadas
  - El entrenamiento real está en `TROOPS_TRAINING` (bloque troops)
- `td.tra`: texto `"‭‭14‬/‭14‬‬"` (bidi U+202D/U+202C), puede ser `<a>` (con mercado) o `<span>` (sin mercado/0/0)
- Aldea `game_id=26421`: caso base vacío → span.none en att/bui/tro, "0/0" en tra

### Decisiones de diseño

- `movement_type` es string libre (no enum): no se conocen todas las clases posibles
- `building_name` del `alt` es idioma-dependiente del servidor (no de Accept-Language)
- Dos llamadas al port en OverviewUseCase: coste irrelevante por caché hit
- Mercaderes solapan con bloque resources: RI-01 pendiente de resolución por coordinador

**Why:** Los cuatro bloques se desarrollan en paralelo sin coordinar entre sí; cada uno tiene su propio spec.
**How to apply:** Al diseñar otros bloques, verificar que no rediseñan piezas ya resueltas aquí.

---

## Bloque resources (spec: docs/specs/lectura-resources.md)

- Endpoint: `GET /game/resources/{world_id}` + `Accept-Language` obligatoria
- Tres páginas: `RESOURCES`, `RESOURCES_PRODUCTION`, `RESOURCES_CAPACITY`
- Parser: `adapters/browser/parsers/resources_parser.py` → `ResourcesParser` (3 métodos estáticos)
- DTOs: `core/dtos/resources_dto.py` (VillageMerchants, VillageStoredResources, StoredTotals, VillageProductionResources, ProductionTotals, VillageCapacity, CapacityTotals, ResourcesResponseDTO)
- Use case: `core/use_cases/resources_use_case.py`
- Router: `adapters/api/routes/game_resources.py`

### Hallazgos clave de los tres fixtures

**resources.html — `table#ressources` (OJO: doble 's', trampa frecuente)**
- 6 aldeas (newdid: 19040, 24341, 25306, 25875, 26421, 24498)
- Separador visual: `tr > td.empty colspan="6"` entre aldeas y `tr.sum`
- Mercaderes en aldeas: `td.tra.lc > a[href*="gid=17"]` — texto "‭‭14‬/‭14‬‬" (bidi + separadores)
- Mercaderes en `tr.sum`: `td.tra` sin `<a>` — texto directo "‭‭37‬/‭40‬‬"
- El parser `_parse_merchants` debe manejar AMBOS casos (con y sin `<a>`)

**resources_production.html — `table#production`**
- Misma estructura de aldeas; solo 4 columnas de recursos (sin mercaderes)
- `tr.sum` tiene `td.vil > span.total` con la suma global de todos los recursos (98896)
  Este span puede no existir → devolver `total_all_resources=None` (no fallar)
- Producción es BRUTA — no resta consumo de cereal del ejército

**resources_capacity.html — `table#capacity`**
- Solo 2 columnas de datos: `td.max123` (almacén) y `td.max4` (granero)
- `tr.sum` con `td.max123` y `td.max4` (sin `span.total`)

### Decisiones de diseño clave

- Endpoint único (no sub-rutas) — anti-detección: 1 petición HTTP del cliente vs 3 en ráfaga
- Selector `table#ressources` con doble 's' — crítico, si se usa `#resources` el selector falla
- Nomenclatura: `wood` (no `lum`) en DTOs para semántica; `lum` es CSS de Travian
- Mercaderes solapan con bloque overview: RI-01 pendiente de resolución por palantir
- Producción de cereal puede parecer negativa respecto al consumo del ejército: es correcto, es bruta

---

## Bloque troops (spec: docs/specs/lectura-troops.md)

- 5 sub-rutas: `GET /game/troops/{world_id}/{own|support|smithy|hospital|training}`
- Parser: `adapters/browser/parsers/troops_parser.py` → `TroopsParser` (5 métodos estáticos)
- DTOs: `core/dtos/troops_dto.py`
- Use case: `core/use_cases/troops_use_case.py`
- Router: `adapters/api/routes/game_troops.py`

### Hallazgos críticos de los 5 fixtures

**troops_own.html — `table#troops`**
- Encabezados en `thead > tr > td.unit img.unit.uNN` (NO `th`)
- Celdas de aldea: `td.villageName a[href*='newdid=']` (no `td.vil.fc` como en overview)
- `td.none` = valor 0 (clase CSS); texto es "0"; `parse_int("0")` = 0
- Fila separadora: `tr > td.empty[colspan]` — ignorar (no tiene `td.villageName`)
- `tr.sum` tiene `td.vil` (no `td.vil.fc`) — ignorar al iterar aldeas

**troops_support.html — `div.troops_wrapper > table.vil_troops`**
- Una tabla por aldea; `game_id` en `thead th a[href*='newdid=']`
- `tbody.troops`: PARES de filas (icono + cantidad); puede haber 1 o 2 grupos
  - 2 grupos: naturaleza (u31-u40) + propias (u21-u30+uhero)
  - 1 grupo: solo propias (si no hay naturaleza en esa aldea — aldea 25306)
- `tbody.upkeep`: `div.consumption span` = cereal/h; `div.inlineIcon.strength` × 3 para fuerza
  - Fuerza con valor `"-"` (sin tropas) → `None` en DTO; con bidi "‭201,060‬" → 201060
- Hero: `img.unit.uhero` aparece en la fila de propias; almacenar en `own["uhero"]` y `hero`

**troops_smithy.html — `table.under_progress`**
- Columnas en `thead tr:nth-child(2) th.unit img.unit.uNN` (segunda fila del thead)
- Aldea en `td.vil.fc a[href*='newdid=']` (aquí sí usa `vil fc`)
- `td.inProgress`: puede tener múltiples `img.unit.uNN` (aldea 00: u22+u24) o `span.dot`
- Niveles: `td.unit.none` con `"0"` = nivel 0 (investigable no mejorado); `"−"` = `None` (no investigable)

**troops_hospital.html — `table.under_progress`**
- Tribu: `th.villageName > i.tribeN_medium` (tribe3=Galos) — SOLO en el thead
- Columnas: `thead tr:nth-child(2) th.unit img.unit.uNN` (u21-u26, solo infantería+caballería)
- Aldea en `td.villageName a[href*='newdid=']` (sin `vil fc`)
- `td.inProgress span.dot` = hospital sin curación activa (`has_hospital=True, healing=False`)
- `td.inProgress span.none` = sin hospital (`has_hospital=False`)
- Heridos: `td.none` = 0 (con clase none); td sin clase = cantidad > 0 (p.ej. aldea 01, u22=2)

**troops_training.html — `table.under_progress`**
- Columnas dinámicas: `thead th.unit > i.building_small.tribeN.typeNN`
- `gid` extraído de `a[href*='gid=N']` en los datos (más robusto que parsear typeNN)
  - Fallback: typeNN cuando la primera fila tiene span.none en esa columna
- `span.duration` (con whitespace) → `parse_time(text.strip())` → segundos
- `span.dot` → `building_exists=True, queue_seconds=0`
- `span.none` → `building_exists=False, queue_seconds=None`
- Aldea en `td.villageName a[href*='newdid=']`

### Gotchas de parseo troops

- `td.unit.none` con texto `"0"` en smithy es nivel 0 (int); `td.unit.none` con `"-"` es no investigable (None)
- `span.duration` en training tiene mucho whitespace — siempre `.strip()` antes de `parse_time`
- `tbody.troops` en support NO siempre tiene dos grupos; detectar por clase de la primera img (u31+ = naturaleza)
- La tabla de support usa `thead th a` para el game_id (no una celda de fila como las demás tablas)

**Why:** Bloque troops diseñado en paralelo con overview/resources/culture-points; fixtures reales ya disponibles.
**How to apply:** Usar estos hallazgos al revisar o extender el bloque troops. No rediseñar los selectores sin verificar contra los fixtures.
