---
name: reaparicion-animales-oasis-feature
description: "feature EP-10 comparativa de reaparición de animales por oasis; backend hecho+verificado, UI pendiente de mockup; blocker de arranque attacker_tribe"
metadata: 
  node_type: memory
  type: project
  originSessionId: 4fd7bbf0-45e0-4285-b081-d451c9646a42
---

Feature de análisis sobre la base de [[bd-ataques-oasis-feature]]: tasa de reaparición de animales/hora por oasis + proyección de acumulados desde el último ataque, segmentada por las especies que REALMENTE reaparecen en cada oasis (no todas; los de madera no traen ratas, etc.). Decidido con el usuario: comparar+predecir, tipo de oasis INFERIDO empíricamente (no se persiste, no se hardcodean reglas Travian), métrica solo tasa bruta (sin population cap).

Spec: `docs/specs/reaparicion-animales-oasis.md`. Diseño UI + mockup: `docs/design/oasis-comparison.md` + `frontend/mockups/oasis-comparison.playground.html`.

Endpoint nuevo **EP-10 `GET /attack-reports/stats/oasis/comparison`** (sin Accept-Language, igual que EP-06/EP-09). Método `get_all_oasis_regen_comparison()` en `attack_report_sqlite_adapter.py`, reutiliza `_calc_regen_rates` + helper nuevo `_parse_utc_offset`.

**Estado:** backend implementado, 23/23 tests, VERIFICADO en vivo contra BD real (vía adaptador, no HTTP). UI pendiente del gate humano del mockup (mockup-first). NADA commiteado.

**Bug encontrado y corregido en verificación:** el parser escribe filas para las 10 especies en cada reporte (present=0 para ausentes), así que la 1ª versión mostraba las 10 especies con 0.0/h en todos los oasis. Fix: filtrar por `MAX(present)>0` por oasis (como `animal_appearances` de EP-06). Distinguir "ausente" (omitir) de "presente con tasa 0" (mostrar). Lección: los fixtures de test deben reproducir filas present=0 de especies ausentes.

**Blocker no obvio (de otra tanda):** la API NO arranca en el working tree actual — `ensure_tables()` hace CREATE INDEX sobre `attacker_tribe`, columna que `travian_bot.db` no tiene (CREATE TABLE IF NOT EXISTS no la añade). Es de la feature §17/tribu en vuelo, no de EP-10. Para probar EP-10 por HTTP hace falta migrar esa columna. `DB_PATH` está hardcodeado en `adapters/db/database.py` (no configurable por env). Ver [[fernet-key-must-be-persisted]] (la key sí estaba en ~/.zshrc, solo faltaba en el shell no-interactivo).

**EP-09 tiene el mismo defecto latente** (especies nunca presentes con tasa 0.0) — pendiente de tarea/spec aparte.

**Higiene de rama:** `feature/bd-ataques-oasis` mezcla esta feature + human-click (driver.py +277, anti-detección) + frontend de otras tandas, todo sin commitear. Separar antes de commitear. Ver [[branch-hygiene-one-feature-per-branch]].
