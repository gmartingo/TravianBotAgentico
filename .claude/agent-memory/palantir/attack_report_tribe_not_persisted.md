---
name: attack-report-tribe-not-persisted
description: attacker_tribe se resuelve en tiempo de parse pero NO se guarda en la BD; para el cómputo PERDIDO hay que re-parsear el raw_text o hacer JOIN con los datos de juego en runtime
metadata:
  type: project
---

`attacker_tribe` existe en `AttackReportPreview` (resuelto por `_resolve_attacker_tribe` en `core/use_cases/attack_report_parser.py`), pero el método `save_report` en `adapters/db/attack_report_sqlite_adapter.py` NO la inserta en la tabla `attack_reports` (no hay columna `attacker_tribe` en el esquema DDL).

**Consecuencia para el cómputo PERDIDO (recursos = tropas perdidas × coste):**
- Para un reporte individual (EP-01 parse, EP-04 detail): el endpoint re-parsea el `raw_text` almacenado y llama a `_compute_attacker_cost_loss`, que resuelve la tribu del preview y cruza con `game_data_port.get_all_troop_stats(tribe)`. Esto ya funciona.
- Para un SUMATORIO GLOBAL sobre todos los reportes: no hay forma de hacer la suma en SQL puro, porque la tribu no está en la BD. El analista debe elegir entre:
  a. Añadir columna `attacker_tribe TEXT` al esquema + migración y persistirla en `save_report`.
  b. Re-parsear todos los `raw_text` de la BD en Python (lento si hay muchos reportes, pero viable en MVP).
  c. Aprovisionar la columna opcionalmente a partir del `raw_text` (lazy migration).

La opción (a) es la más limpia pero requiere alterar el esquema. La opción (b) es la más rápida de implementar.

**Why:** El esquema MVP no incluyó `attacker_tribe` como columna porque la tribu se deduce del nombre de las tropas en el parser — no era un campo de entrada del usuario. Se priorizó la simplicidad del esquema.

**How to apply:** Cuando el analista diseñe el cómputo PERDIDO global, señalar esta limitación y que necesita una decisión de migración de esquema o estrategia de re-parseo.

[[attack-report-pregame]]
