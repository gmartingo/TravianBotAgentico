---
name: incoming-attacks-radar-closure
description: Gate de cierre del spec radar-ataques-entrantes.md — veredictos de reutilización, ajustes y conflictos detectados. Verificado 2026-06-05.
metadata:
  type: project
---

Feature: Radar de ataques entrantes (spec radar-ataques-entrantes.md).

## Infraestructura REUTILIZABLE confirmada

- `SessionNotActiveError` / `WorldNotFoundError` — `core/exceptions.py` — ya existen, usar directamente.
- `build_url(base, path)` — `adapters/browser/url_utils.py` — spec ya lo nombra explícitamente.
- `human_delay(min, max)` — `adapters/browser/driver.py` — spec ya lo nombra explícitamente.
- `human_click` / `human_click_at_rect` — `adapters/browser/driver.py` — para Componentes C y D.
- Patrón LiveOverviewAdapter (callables inyectados `get_browser`+`get_world_server`, `browser.get` + `human_delay` + `tab.wait_for`) — reutilizar para `IncomingAttackBrowserAdapter.get_dorf1_html`.
- Patrón ABC port + ensure_tables + SQLite adapter — `attack_report_sqlite_adapter.py` como referencia directa de estructura.
- Patrón DataClass frozen DTO — igual que DTOs de `core/dtos/`.
- Patrón de parsers estáticos — `IncomingAttackSidebarParser` y `Dorf1IncomingParser` son isomorfos a `OverviewParser`, `ResourcesParser`, etc. en `adapters/browser/parsers/`.
- `adapters/browser/parsers/_common.py` — helpers `_parse_coord` NO debe duplicar; sin embargo, la función específica del spec `_parse_coord` es diferente (parsea "(-68" y "73|)") — NO hay solapamiento directo con `parse_merchants_text` ni `extract_game_id_from_vil_cell`.
- `get_language` — `adapters/api/dependencies.py` — ya correcto para EP-RA01.
- Patrón lifespan `ensure_tables` — main.py ya tiene el patrón, nuevo adaptador se añade con el mismo estilo.

## Conflictos / aclaraciones detectadas

- `IncomingAttackPageError` (mencionado en el spec §5 Flujo B1): NO existe en `core/exceptions.py`. Se debe CREAR como subclase de `TravianBotError`.
- `TaskType.CHECK_INCOMING_ATTACK_DETAIL` y `FETCH_RALLY_POINT_DETAIL` y `FETCH_ATTACKER_VILLAGE_PROFILE`: NO existen en `core/entities/task.py` (solo `SEND_FARM_LIST_GROUP` y `NOISE_NAVIGATION`). Se deben añadir.
- Hook transversal: ver sección específica en el informe — WorldAgent necesita `_post_page_hook` pero actualmente NO lo llama ningún adapter de browser. El spec propone cablear el hook en TODOS los adapters de browser, lo que implica modificar `live_overview_adapter.py`, `live_farm_list_adapter.py` y `login.py`. Cambio transversal que hay que analizar cuidadosamente.

## Tablas NO solapadas (confirmado)

- `incoming_attacks` (pre-combate, FK world_id) vs `attack_reports` (post-combate, FK world_id=NULL en MVP): distintas en propósito, ciclo de vida y schema. No se solapan.

**Why:** El spec fue revisado en gate de cierre 2026-06-05.
**How to apply:** Al implementar, referenciar este mapa para no duplicar y verificar los tres conflictos listados antes de escribir código.
