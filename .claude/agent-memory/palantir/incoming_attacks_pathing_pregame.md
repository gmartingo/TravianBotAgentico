---
name: incoming-attacks-pathing-pregame
description: Gate de entrada — integración captura atacante (Comp C+D) con sistema de pathing de rutas. Fixtures GAP-02/GAP-03 ahora disponibles. Mapa completo de reutilización vs creación genuina. Verificado 2026-06-07.
metadata:
  type: project
---

## Contexto
Los Componentes C (rally point) y D (ficha atacante) del radar estaban BLOQUEADOS por falta de fixtures. Los fixtures `troop_details_in_attack.html` y `karte_tile_attacker_dialog.html` ya existen en `tests/fixtures/incoming_attacks/`. La pregunta es cómo integrar la navegación con clicks humanos y el sistema de pathing.

## Sistema de pathing — lo que existe

### Motor de rutas componibles (v2)
- **Entidades**: `RouteTemplate` / `RouteTemplatePath` / `NavigationStep` en `core/entities/noise.py` (líneas 205-280).
- **Resolución de cadena**: `resolve_origin_chain(template_id, db)` → `list[ResolvedStep]` en `core/use_cases/route_template_service.py`.
- **Motor de ejecución producción**: `WorldAgent._execute_noise_action` (línea 1662 de `world_agent.py`) — cuando `path.origin.startswith("ROUTE_TEMPLATE:")` entra en flujo v2: verificación arranque frío + resolución cadena + `human_click_at_rect` por step. CERO `browser.get`.
- **Motor de test**: `execute_path_test_standalone` (línea 163 de `world_agent.py`) y `WorldAgent.execute_path_test` (línea ~2220) — mismo flujo v2.
- **_execute_noise_step** (línea 1536): ejecuta `NavigationStep` con `human_click_at_rect`; soporta CLICK / WAIT_FOR_SELECTOR / SCROLL_TO / HOVER.
- **human_click_at_rect** en `adapters/browser/driver.py` (línea ~689).
- **_browser_lock**: `asyncio.Lock` en `WorldAgent` — serializa todo acceso al tab.

### Orígenes disponibles
- `NavigationOrigin` enum genérico (DORF1, MAP, etc.) — v1 con `browser.get`.
- `"VILLAGE_<data_id>"` — v1 con `browser.get` a `/dorf1.php?newdid=<data_id>`.
- `"ROUTE_TEMPLATE:<id>"` — v2 sin `browser.get`, solo clicks. El punto de integración correcto para C+D.

### Navegación a aldea propia
- Para ir a la aldea bajo ataque: origin `"VILLAGE_<village_game_id>"` → `browser.get("/dorf1.php?newdid=<id>")` (v1, deuda conocida) o, idealmente, una `RouteTemplate` raíz cuya `url_pattern` sea `/dorf1.php` con el `newdid` en el selector del primer step del sidebar.
- `parse_village_switcher(tab, world_id)` en `village_switcher.py` — SOLO LECTURA (JS evaluate, sin clicks), devuelve `list[Village]` con `data_id`. NO navega a ninguna aldea.

## Lo que existe y es REUTILIZABLE en los Componentes C y D

### C — Navegación al rally point y parseo de troop_details
- **click en `a[href*='gid=16']`**: `IncomingAttackBrowserAdapter.click_rally_point_link` (línea 97 de `incoming_attack_browser_adapter.py`) ya implementado como STUB — selector correcto confirmado con fixture, usa `human_click(element, tab)`. LISTO para desbloquear con el fixture.
- **`extract_unit_class(img_tag)`**: `adapters/browser/parsers/_common.py` línea 108 — extrae `uNN`/`uhero` de las clases de un `<img>`. REUTILIZABLE directamente para leer los iconos de tropa de `tbody.units`.
- **Timer `span.timer[value]`**: mismo patrón ya en `Dorf1IncomingParser.parse` (leer `value` o `data-value`). Lógica REUTILIZABLE para leer el timer de `tbody.infos`.
- **`_parse_coord`** en `incoming_attack_sidebar_parser.py` línea 33 — regex `[-−]?\d+`, maneja guion Unicode. REUTILIZABLE para las coords de `th.coords` en `tbody.units`. NOTA: está definida como función LOCAL en ese módulo, no exportada. Si el nuevo parser la necesita, copiarla o moverla a `_common.py`.
- **`IncomingAttackRecord`** en `core/ports/incoming_attack_db_port.py` — ya tiene columnas `attacker_name`, `origin_village_name`, `operation_type`, `origin_village_href` (nullable, `source='rally_point'`). REUTILIZAR sin cambios.
- **`upsert_attack`** en `IncomingAttackSQLiteAdapter` — lógica COALESCE ya implementada para enriquecer progresivamente. REUTILIZAR.

### D — Click al link karte.php y parseo del diálogo tileDetails
- **click en `a[href*='karte.php?d=']`**: `IncomingAttackBrowserAdapter.click_origin_village_link` (línea 120) — STUB, usa `human_click`. Selector a ajustar: el fixture muestra que el href es `karte.php?d=<NNN>`, el stub usa `origin_village_href` directamente. LISTO para desbloquear.
- **`attacker_snapshot_json`**: columna ya en BD (TEXT). Parser devuelve `VillageProfileDTO` → serializar a JSON. Columna REUTILIZAR.
- **Tribu en karte_tile**: en el fixture es texto plano en `<td>` después de `<th>Tribe</th>` (primera fila de `#village_info`). NO es el patrón `i.tribeN_medium` de `troops_parser.py` línea 344 — ese patrón es para `/village/statistics`, NO reutilizable aquí.
- **Coordenadas en karte_tile**: `span.coordinateX` / `span.coordinateY` con texto bidi — MISMO patrón que `_parse_coord` del sidebar parser.

## Lo que NO existe y hay que CREAR (genuinamente nuevo)

1. **`RallyPointParser`** (Comp. C): parser de `table.troop_details.inAttack`:
   - `td.troopHeadline > a[href*='karte.php?d=']` → nombre atacante + aldea origen (ej. "GonnaDie attacks 05") y el href `karte.php?d=49454`.
   - `td.role > a[href*='karte.php?d=']` → href de la aldea defensora.
   - `tbody.units`: iconos `img.unit.uNN` (via `extract_unit_class`) + cantidades en `tbody.units.last > tr > td.unit`.
   - `tbody.infos > tr > td > div.in > span.timer[value]` → timer segundos.
   - `tbody.infos > tr > td > div.at > span` → hora display "at HH:MM:SS".
   - DTOs: `RallyPointAttackDTO` ya definido en `core/dtos/incoming_attack_dto.py` — REUTILIZAR.

2. **`VillageProfileParser`** (Comp. D): parser de `div#tileDetails`:
   - `div#tileDetails.village-N` → clase contiene el tipo de tile (aldea/oasis).
   - `h1.titleInHeader span.coordinateX/Y` → coords del atacante (via `_parse_coord`).
   - `#village_info tr.first td` → texto de tribu (Gauls/Romans/Teutons) — texto en idioma de la cuenta, no enum. Necesita mapeo.
   - `#village_info td.alliance a` → nombre + href alianza.
   - `#village_info td.player a` → nombre + href jugador (ej. `/profile/392`).
   - `#village_info td:last-of-type` (Population row) → número.
   - DTO: `VillageProfileDTO` ya en `core/dtos/incoming_attack_dto.py` — REUTILIZAR.

3. **`TaskType.FETCH_RALLY_POINT_DETAIL` y `TaskType.FETCH_ATTACKER_VILLAGE_PROFILE`** en `core/entities/task.py` — NO existen aún, solo `CHECK_INCOMING_ATTACK_DETAIL`.

4. **Handlers en WorldAgent** para los dos nuevos TaskType — el patrón ya está (`_handle_check_incoming_attack_detail` como referencia).

## Punto de integración con el sistema de pathing — recomendación

El sistema de rutas componibles (`RouteTemplate`) es para ruido de navegación PROGRAMADO. Los Componentes C y D son navegación REACTIVA (event-driven, disparada por un ataque). NO encajan en el catálogo de plantillas.

La integración correcta es:
- `IncomingAttackBrowserAdapter` ya tiene los métodos `click_rally_point_link` y `click_origin_village_link` con `human_click` — el MISMO primitivo que usa `_execute_noise_step`. No hay que pasar por el sistema de plantillas.
- El `_browser_lock` de `WorldAgent` es el punto de integración: los handlers de Comp. C+D deben adquirirlo antes de acceder al tab (igual que `_execute_noise_action` en línea 1720).
- El patrón a seguir es `_handle_check_incoming_attack_detail` → `_handle_fetch_rally_point` → `_handle_fetch_attacker_village_profile`, en WorldAgent, con el lock.

## Duplicaciones a evitar

- `_parse_coord` existe SOLO en `incoming_attack_sidebar_parser.py` (local). Si `RallyPointParser` y `VillageProfileParser` también la necesitan → moverla a `_common.py` y exportarla. No duplicar en cada parser.
- El patrón `extract_unit_class` ya en `_common.py` — importar desde ahí, no copiar.

**Why:** el spec del radar ya tiene los fixtures y los DTOs están definidos. El analista debe desbloquear Comp. C y D directamente con los fixtures disponibles, sin re-diseñar desde cero.
**How to apply:** el analista recibe este mapa ya hecho. Solo necesita diseñar los dos parsers nuevos, los dos TaskType y los dos handlers de WorldAgent. El resto es reutilización directa.
