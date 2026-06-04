---
name: oasis-spawn-mechanics-stats-feature
description: "feature stats de aparición de animales en oasis — backend hecho+testeado, UI pendiente del gate de mockup; inferencia de tipo usa Jaccard"
metadata: 
  node_type: memory
  type: project
  originSessionId: dcfb5865-50fa-4889-a5ee-56222ba99f21
---

Feature para que el usuario ENTIENDA el ritmo de aparición de animales en oasis (motivada por el Excel "Oasis farming from a nerd"). Spec: `docs/specs/oasis-spawn-mechanics-stats.md`. Reemplaza la métrica engañosa `avg_regen_per_hour` (mezclaba ráfaga de spawn + cooldown) por 4 piezas: panel educativo estático (timers fijos rata 5:00…elefante 14:00 + sets por tipo), composición típica por oasis (avg/max present), peor combinación a batir por intervalo elegido (6/7/10/15 min), y estado cooldown/respawn.

Decisiones del usuario: tipo de oasis se INFIERE de los animales vistos (no se guarda a mano); intervalo lo ELIGE el usuario; servidor x1 fijo.

Estado (2026-06-02) — IMPLEMENTADO end-to-end, 274 tests passed, PENDIENTE prueba manual del usuario + commit:
- **Backend**: catálogo `core/game_data/oasis_spawn_catalog.py` (SPAWN_TIMER_S, OASIS_TYPE_SETS, COOLDOWN_THRESHOLD_S=4h), endpoint `GET /attack-reports/stats/oasis/spawn-composition?timer_min=N` en `adapters/api/routes/attack_reports.py`, lógica en `adapters/db/attack_report_sqlite_adapter.py::get_oasis_spawn_composition`. Devuelve por oasis: inferred_type/confidence/spawn_status + species[] (avg/max present, worst_case_count, def_*) + **origin_villages[]** (v2.3, ciudades atacantes, GROUP_CONCAT DISTINCT). Tests `tests/test_oasis_spawn_composition_api.py`.
- **Frontend** (en `frontend/src/components/attack-reports/`): `SpawnMechanicsPanel.jsx` (leyenda estática), `OasisCombatPlannerPanel.jsx` (dos filas compactas Media/Peor icono+número SIN "×" ni fuerza defensiva). v2.6: anidado **Jugador→Aldea→Oasis** = `PlayerOasisSection.jsx` (nivel jugador, colapsable) → `CityOasisSection.jsx` (nivel aldea) → oasis. Selector intervalo único arriba. Orden StatsTab: leyenda → balance → combinaciones → globales → lista. i18n `stats.planner.*` en 25 catálogos.
- **`avg_regen_per_hour`**: el frontend ya NO lo muestra. Decisión: se DEJA como deuda interna del backend (EP-09 lo conserva; EP-10 lo usa para projected_now y no tiene consumidor) — purgarlo de EP-06/EP-10 era alto coste/bajo valor. El objetivo (que el usuario no vea "animales/hora") está cumplido.
- Diseño: `docs/design/oasis-spawn-mechanics.md` (v2.3). Mockup: `frontend/mockups/oasis-spawn-mechanics.playground.html`.

Corrección clave (v2): la inferencia de tipo usa **similitud de Jaccard** `|∩|/|∪|`, NO solapamiento bruto. Con solapamiento bruto y `cereal={1..10}` (universal), cereal ganaba siempre y anulaba la detección de anomalías. Jaccard penaliza el set universal (un cocodrilo en arcilla → arcilla con coco como anomalía). Si alguien vuelve a tocar `_infer_type`, NO volver a `|∩|`.

Corrección clave (v2.5 — agrupación por ciudad ATACANTE, por reportes): `origin_villages` por oasis NO se saca del `origin_village_name` guardado tal cual (el parser, si la línea del atacante no trae coords `[Ali] Jugador from village <Aldea>`, guarda la LÍNEA ENTERA como blob — bug attack_report_parser.py:588-592; y ese campo está en la clave UNIQUE, NO re-parsear). Inferencia POST-HOC en `get_oasis_spawn_composition` (helpers `_infer_origin_villages` + `_infer_origin_village_from_blob` + constante `_FROM_VILLAGE_MARKERS`). **Atribución POR REPORTES** (quien ataca de verdad, NO el dueño de la farm list — la v2.4 usaba farm-list-owner y ocultaba aldeas que atacan sin lista como la 05; DEROGADA). v2.6: el contrato pasó de `origin_villages: string[]` a **`attackers: [{player, village}]`** por oasis — se extrae también el JUGADOR del blob (`[Tag] Player from village Village`): tras quitar `[tag]`, lo de antes del marcador = player, lo de después = village (canonizado vía villages substring → si no, crudo). Helpers `_extract_player_village_from_blob` + `_infer_attackers` en el adapter. El frontend anida Jugador→Aldea→Oasis (no juzga qué cuenta es "tuya"; cada player su sección). Verificado en BD real: GonnaDie (tuya, 5 aldeas, 138 oasis) separada de cuentas ajenas CrazyMouse/SharpHorseman (metidas por error). world_id NULL en MVP → sin scoping (TODO). NO volver a atribución por farm-list ni a origin_villages.

Honra [[feedback-confirm-metric-before-stats-change]]: se confirmó métrica/pantalla con el usuario antes de implementar.
