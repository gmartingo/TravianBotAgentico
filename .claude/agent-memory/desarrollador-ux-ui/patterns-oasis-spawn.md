---
name: patterns-oasis-spawn
description: S-SPAWN OasisCombatPlannerPanel (v2.3, agrupación por ciudad atacante): CityOasisSection colapsable, buildCityMap, claves city_*, mock correcto para capturas headless
metadata:
  type: project
---

## Feature: mecánica de spawn de oasis (última versión: v2.3, 2026-06-02)

### ESTADO ACTUAL (v2.3 — implementada)

**StatsTab orden:** SpawnMechanicsPanel → BalanceSection → OasisCombatPlannerPanel → GlobalOasisStatsPanel → OasisList.

### Componentes en frontend/src/components/attack-reports/

- `SpawnMechanicsPanel.jsx` — educativo/estático, colapsable. useId() para bodyId, localStorage key `spawn_panel_open`. grid-template-rows para colapso CSS.
- `CityOasisSection.jsx` (v2.3 NUEVO) — sección colapsable por ciudad atacante. Props: cityName, rawName, oasisList, t, children. Chevron SVG inline, aria-expanded, aria-labelledby en section. Expandida por defecto.
- `OasisCombatPlannerPanel.jsx` — panel fusionado v2.3. `buildCityMap(oasisArray)` construye `{ciudad→[oasis...]}` con reduce; un oasis con N ciudades aparece en todas. Orden: alfabético, "Desconocido" raw siempre al final. Selector intervalo único + dos filas compactas de chips por oasis:
  - Fila **Media**: NatureIcon + `max_present_per_burst`. Anomalías aparecen con badge "anom." en acento oro.
  - Fila **Peor**: NatureIcon + `worst_case_count` como número plano (SIN "×"). Solo animales no anómalos.
  - Sin fuerza defensiva (backend la devuelve, UI la ignora).
  - Si `inferred_type=null`: nota inline, sin fila Peor.
- ~~OasisCompositionPanel.jsx~~ — ELIMINADO (v2.2)
- ~~WorstCasePlannerPanel.jsx~~ — ELIMINADO (v2.2)

### Por qué worst_case_count sin "×"
Es un conteo absoluto de animales (no un multiplicador). El "×N" confundía: el usuario interpretaba "×5" como 12 ratas × 5 = 60, cuando en realidad es "habrá 5 ratas en el peor caso". Mostrar como número plano (ej. "5") elimina la ambigüedad.

### Catálogo JS en frontend/src/utils/oasisSpawnCatalog.js
Espejo JS de `core/game_data/oasis_spawn_catalog.py`. SPAWN_TIMER_S, OASIS_TYPE_SETS, NATURE_ORDINALS, formatTimerMmSs.

### Patrón EP-SPAWN en StatsTab.jsx
`OasisCombatPlannerPanel` recibe `data/loading/error/onRetry/timerMin/onTimerChange` desde StatsTab. Cuando cambia timerMin, StatsTab re-lanza loadSpawn(timerMin).

### Claves i18n
- NATURE_1..10: nombres de animales
- `stats.spawn.*`, `stats.composition.*`, `stats.worst.*` (v2 — mantenidas, no eliminar)
- `stats.planner.*` (v2.2): panel_title, interval_label, row_media, row_worst, no_type_note, anomaly_note, empty_title, empty_body, empty_cta, error, retry
- `stats.planner.city_*` (v2.3 NUEVAS): city_unknown, city_oasis_count_one, city_oasis_count_pl (`{n} oasis`)
- "Desconocido" raw viene del backend en español; se mapea a `stats.planner.city_unknown` para localizarlo.
- Los 25 catálogos tienen todas las claves; ES/EN con calidad, resto EN como fallback.

### Mock correcto para capturas headless de StatsTab
GlobalOasisStatsPanel espera `animal_appearances: []` y `animal_regen_rates: []` (NO `by_type/by_animal`).
OasisList espera `res.items` (no `res.oasis`). Si se pasan datos incorrectos, React crashea con `Cannot read properties of undefined (reading 'length')` y el `#root` queda vacío.

### Capturas headless (uishot-city-groups.mjs)
- Usar el **preview server** (`vite preview`, puerto 5190) en lugar del dev server (los módulos ESM de Vite dev interfieren con `setRequestInterception`).
- Activar interceptación ANTES de `page.goto()`, no después de `networkidle2`.
- Clic en el tab "Estadísticas": usar `page.evaluate()` con `find(t => t.textContent.trim() === 'Estadísticas').click()` (NO `page.click()` ni `tabs[2].click()` nativo de Puppeteer, que puede causar comportamientos raros).
- Colapsar SpawnMechanicsPanel antes del screenshot para que el planificador sea visible en el viewport.

### Retirada avg_regen_per_hour (deuda técnica pendiente)
GlobalOasisStatsPanel y RegenRatesSection usan "—" en lugar del campo retirado. Pendiente eliminación backend (EP-06, RN-RET-01).

### Ruta AttackReportsPage
`/reportes-oasis` (no `/attack-reports`). Las capturas headless usan esta ruta.
