---
name: project-oasis-spawn-docs
description: oasis-spawn-mechanics-stats documentada 2026-06-02 — rutas, divergencias, claves arquitectónicas de la feature de mecánica de spawn
metadata:
  type: project
---

Feature `oasis-spawn-mechanics-stats` documentada el 2026-06-02.

## Documentos creados / actualizados

- `documentacion/backend/referencia-funciones/oasis-spawn-composition.md` — referencia de funciones de código para desarrolladores
- `documentacion/funcionalidades/oasis-spawn-mechanics.md` — documento de negocio para stakeholders
- `documentacion/manual-usuario/oasis-spawn.html` — manual de usuario (tipo 3) con 11 capturas reales
- `documentacion/README.md` — actualizado con los tres documentos

## Capturas del manual de usuario (oasis-spawn.html)

11 PNG en `documentacion/manual-usuario/assets/spawn-*.png`:
- `spawn-01-vista-general.png` — pestaña Estadísticas con leyenda colapsada
- `spawn-02-leyenda-expandida.png` — panel Leyenda abierto con tabla de timers
- `spawn-03-leyenda-sets.png` — tabla de sets por tipo de oasis + nota de anomalía
- `spawn-04-planificador-selector.png` — planificador con 10 min activo + CrazyMouse y GonnaDie
- `spawn-05-intervalo-6min.png` — selector cambiado a 6 min (Peor diferente)
- `spawn-06-gonnadie-jerarquia.png` — GonnaDie con sus aldeas y oasis (estado Desconocido)
- `spawn-07-media-peor.png` — filas Media y Peor con badge anom. en dorado
- `spawn-08-estado-cooldown.png` — oasis en estado Cooldown (punto rojo)
- `spawn-09-tres-jugadores.png` — GonnaDie + SharpHorseman + nota de anómalos excluidos de Peor
- `spawn-10-modo-oscuro.png` — modo oscuro activo
- `spawn-11-global-stats.png` — panel de estadísticas globales + lista de 138 oasis

## Observaciones del entorno (2026-06-02)

- Estado Repoblando no estaba presente en los datos en el momento de captura (todos cooldown o desconocido).
- `[aria-expanded]` sin filtro selecciona el dropdown de idioma en la topbar antes que el SpawnMechanicsPanel; necesario filtrar por `aria-controls^="spawn-body-"`.
- Script de capturas: `frontend/scripts/uishot-spawn2.mjs` (el corregido; uishot-spawn.mjs tiene el bug del dropdown).

## Artefactos del código documentados

### Backend
- `core/game_data/oasis_spawn_catalog.py` — constantes `SPAWN_TIMER_S`, `OASIS_TYPE_SETS`, `COOLDOWN_THRESHOLD_S`, `NATURE_ORDINALS`
- `core/ports/attack_report_port.py` — `get_oasis_spawn_composition` (método abstracto) y `get_all_oasis_regen_comparison` (regularizado como gap pre-existente)
- `adapters/db/attack_report_sqlite_adapter.py` — `get_oasis_spawn_composition` + helpers: `_infer_type`, `_calc_elapsed_seconds`, `_spawn_status`, `_worst_case_count`, `_FROM_VILLAGE_MARKERS`, `_extract_player_village_from_blob`, `_infer_attackers`
- `adapters/api/routes/attack_reports.py` — `GET /attack-reports/stats/oasis/spawn-composition` (EP-SPAWN)

### Frontend
- `frontend/src/utils/oasisSpawnCatalog.js` — espejo JS del catálogo Python
- `frontend/src/components/attack-reports/SpawnMechanicsPanel.jsx` — panel educativo estático colapsable
- `frontend/src/components/attack-reports/OasisCombatPlannerPanel.jsx` — panel planificador fusionado (v2.6)
- `frontend/src/components/attack-reports/PlayerOasisSection.jsx` — nivel jugador en la jerarquía
- `frontend/src/components/attack-reports/CityOasisSection.jsx` — nivel aldea en la jerarquía

## Divergencias código/spec detectadas

| ID | Descripción | Severidad |
|---|---|---|
| DIV-SPAWN-01 | `meta_sql` definida pero sin usar (código muerto menor) | Baja |
| DIV-SPAWN-02 | EC-11 (sin intersección): confianza "low" producida de forma natural, no explícita | Sin impacto |
| DIV-SPAWN-03 | `"from village "` (con espacio extra) omitida en código vs spec, pero irrelevante por `.strip()` | Sin impacto |
| DIV-SPAWN-04 | Fuerza defensiva (def_infantry/cavalry) enviada por backend pero NO mostrada en UI (decisión usuario v2.2) | Documentada, intencional |

## Claves arquitectónicas a recordar

- **Jaccard, no solapamiento bruto:** `OASIS_TYPE_SETS["cereal"] = {1..10}` (universal) hace que el solapamiento bruto clasifique todo como cereal. Jaccard penaliza el set universal.
- **Atribución solo desde blobs de reportes:** el JOIN farm_slots fue eliminado en v2.5 por bug verificado (aldea "05" invisible).
- **Anti N+1:** solo 4 queries totales (comp_sql, meta_sql_precise, villages_sql, blobs_sql), todas fuera del bucle de oasis.
- **worst_case_count es absoluto, no multiplicador:** esto causó confusión en la UI con "×N". Ahora se muestra como número plano.
- **Backend calcula def_infantry/cavalry pero UI no los muestra** — campos disponibles para uso futuro.
- **TODO crítico:** filtrar villages por world_id cuando attack_reports.world_id deje de ser NULL (TR-11).

**Why:** [[project-doc-structure]]
