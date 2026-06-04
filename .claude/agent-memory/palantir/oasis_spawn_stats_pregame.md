---
name: oasis-spawn-stats-pregame
description: Gate de entrada para feature mecánica de spawn/estadísticas de oasis (panel educativo, composición típica, peor combinación, cooldown/respawn, reemplazo avg_regen_per_hour). Verificado 2026-06-02.
metadata:
  type: project
---

## Contexto
El usuario quiere añadir 4 nuevas secciones a la pestaña Estadísticas de attack-reports/oasis,
más reemplazar avg_regen_per_hour. Este gate registra los hallazgos del mapa para las 5 piezas.

## Hallazgos clave del mapa

### Catálogo de animales nature (seed existente)
- `seeds/game_data/troop_stats.json` tiene las 10 entradas tribe=nature con ordinal 1–10,
  stats de combate (attack, def_infantry, def_cavalry, carry) e icon_id (nature_1..nature_10).
- `core/i18n/catalog/base/troops.json` tiene NATURE_1..NATURE_10 con nombres en 25 idiomas.
- LO QUE FALTA: no hay spawn_timer_s (rata=300s, araña=360s, …, elefante=840s), ni sets_por_tipo_oasis (hierro/arcilla/madera/cereal), ni carry/botín por animal mapeado al tipo de oasis. Hay que añadirlo como seed estático o como constante en core.

### Tipo de oasis — NO existe en BD
- La tabla attack_reports NO tiene columna oasis_type ni hierro/arcilla/madera/cereal.
- El spec reaparicion-animales-oasis.md §3 lo excluye explícitamente de v1 (RN-01: inferencia empírica).
- Tampoco hay config de usuario con "intervalo entre ataques" (attack_interval o user_timer).
  Los intervalos entre ataques se tienen como gap_seconds en repopulation_gaps, pero no hay un "timer que el usuario configura".

### avg_regen_per_hour — call-sites (todos los que romperían si se elimina)
Backend (Python):
  - adapters/db/attack_report_sqlite_adapter.py líneas 198, 1334, 1341 (_calc_regen_rates devuelve la clave; EP-10 comparison la propaga)
  - adapters/api/routes/attack_reports.py (EP-10 ya devuelve avg_regen_per_hour en species[])
Frontend (JSX):
  - frontend/src/components/attack-reports/RegenRatesSection.jsx línea 190 (renderiza "X,XX /h")
  - frontend/src/components/attack-reports/GlobalOasisStatsPanel.jsx línea 352 (regenSummary)
  - frontend/src/components/attack-reports/OasisStatsPanel.jsx línea 206 (pasa rates a RegenRatesSection)
Tests:
  - tests/test_global_oasis_stats_api.py (múltiples asserts sobre avg_regen_per_hour)
  - tests/test_attack_reports_api.py líneas 1031, 1044, 1047
  - tests/test_oasis_comparison_api.py (via EP-10)

### repopulation_gaps — qué tiene y qué falta para cooldown/respawn
Tiene: gap_seconds (segundos entre ataques consecutivos), attacked_at, prev_attacked_at, regenerated_animals.
Falta para detectar cooldown vs respawn: un umbral de referencia (el timer fijo de cada especie, p.ej. rata=300s). Sin ese umbral no se puede clasificar un gap como "cooldown" o "respawn activo".

### EP-10 comparison — estado actual
- Route declarada y endpoint implementado en adapters/api/routes/attack_reports.py línea 531.
- Método get_all_oasis_regen_comparison() implementado en sqlite_adapter línea 1115.
- Port abstracto NO tiene el método todavía (grep devuelve vacío).
- Componente OasisComparisonPanel NO existe en frontend (grep devuelve vacío).

## Veredictos registrados
Ver respuesta completa del gate en la conversación de 2026-06-02.
Resumen: panel educativo=CREAR (seed timer falta); composición típica=ADAPTAR _calc_regen_rates+CREAR agregación/UI; peor combinación=CREAR (fórmula nueva); cooldown/respawn=ADAPTAR gaps+CREAR clasificador; reemplazo avg_regen_per_hour=MODIFICAR _calc_regen_rates (renombrar campo) con impacto en 5+ call-sites listados.
