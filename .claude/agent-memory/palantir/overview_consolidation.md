---
name: overview-consolidation
description: Decisiones de consolidación de los 4 bloques de lectura de overview (overview, resources, culture-points, troops) dictaminadas en gate de cierre.
metadata:
  type: project
---

Decisiones tomadas en el gate de cierre (palantir) de los 4 specs de bloque de lectura de overview. Fechas: 2026-05-26.

**Why:** Cuatro analistas escribieron specs en paralelo. Se detectaron 7 puntos transversales que necesitaban decisión unificada antes de la implementación para evitar duplicación, violaciones hexagonales e inconsistencias de API.

**How to apply:** Antes de implementar cualquiera de los 4 bloques, verificar que el implementador aplica estas decisiones.

---

## Decisiones vinculantes

### 1. Hexagonal — use case NO importa de adapters
Los use cases de `core/` NO importan parsers de `adapters/`. El parseo ocurre en el handler (adapter) antes de invocar el use case. Afecta: `overview_use_case.py` y `culture_points_use_case.py` tal como están en el spec (tienen import incorrecto de `adapters.browser.parsers.*`). El implementador debe corregirlos.

### 2. Mercaderes — coexistencia consciente
`resources` es fuente canónica para decisiones del bot. `overview` mantiene `merchants_free/merchants_total` para la vista de control rápido. Son páginas distintas con TTL de caché independiente; pueden diferir hasta 60 s. Ambos se mantienen sin cambio.

### 3. Tropas overview vs troops — complementarios
`td.tro` (overview) = resumen de tropas presentes. `/troops/support` = detalle con upkeep y fuerza. `/troops/training` = colas con tiempos. Tres cosas distintas, no duplicadas.

### 4. VillageMapUseCase — solo bloque overview
Solo el bloque overview llama a `VillageMapUseCase` (para el merge nombre↔game_id). Los otros 3 bloques extraen `game_id` directamente de sus filas HTML. Patrón correcto tal como está en los specs de resources/culture-points/troops.

### 5. API naming — corregir router culture-points
`adapters/api/routes/game_culture_points.py`: cambiar `router = APIRouter()` a `router = APIRouter(prefix="/game", tags=["game-culture-points"])` y la ruta a `@router.get("/culture-points/{world_id}")`. El spec actual pone el prefijo `/game` hardcodeado en la ruta, inconsistente con el patrón del resto de bloques.

### 6. DTOs frozen=True — todos los bloques
Todos los DTOs de todos los bloques deben ser `frozen=True`. Los specs de overview/resources/culture-points lo especifican. El spec de troops NO lo especifica — el implementador debe añadirlo a todos los dataclasses de `core/dtos/troops_dto.py`. La convención la establece `VillageInfo` del tronco.

### 7. Helpers compartidos — crear _common.py
CREAR `adapters/browser/parsers/_common.py` con:
1. `extract_game_id_from_vil_cell(vil_cell) -> int | None` — patrón `td.vil.fc > a[href*='newdid=']`
2. `extract_game_id_from_village_name_cell(name_cell) -> int | None` — patrón `td.villageName > a[href*='newdid=']` (usado por troops)
3. `parse_merchants_text(raw, context="") -> tuple[int, int]` — parseo "libres/totales" con limpieza bidi
4. `extract_unit_class(img_tag) -> str | None` — extrae clase uNN de img.unit

El patrón `re.search(r"newdid=(\d+)", link["href"])` se repite literalmente 10+ veces sin este helper.

---

## Decisión que NO se tomó
- NO se creó `ParserPort` en `core/ports/` — los parsers son simples y deterministas.
- NO se creó DTO base de aldea compartido — el DRY no justifica el acoplamiento entre bloques independientes.
