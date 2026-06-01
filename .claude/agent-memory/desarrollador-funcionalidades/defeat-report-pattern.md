---
name: defeat-report-pattern
description: Patrón para parsear reportes de combate PERDIDO contra oasis (animales con '?'). Cambios en entidad, parser, DDL, router y frontend.
metadata:
  type: project
---

## Patrón: reportes de combate perdido (§17 spec bd-ataques-oasis)

Cuando el atacante pierde contra un oasis, Travian muestra las cantidades de animales como `?`.

### Entidad (`AnimalEntry`)
- `present/killed/survived: int | None` — `None` = desconocido; `0` = oasis vacío de ese tipo.
- Precedente: `AttackerTroopEntry.troop_ordinal: int | None` en el mismo fichero.

### Parser (`_extract_animals` en `attack_report_parser.py`)
- `_DEFEAT_ROW_PATTERN = re.compile(r"^\?[\s\t]*(\?[\s\t]*)*$")` — solo `?` separados.
- `_is_defeat_row(line)` — True si la línea es solo `?`.
- `_is_mixed_row(line)` — True si mezcla `?` y dígitos → `DefeatReportParseError`.
- Los nombres de la cabecera **siempre** se validan contra el índice NATURE, incluso en modo perdido.
- En modo perdido: UNA sola fila de `?` — no buscar segunda fila.

### DDL (`_CREATE_ANIMALS`)
- `present INTEGER, killed INTEGER, survived INTEGER` — sin `NOT NULL DEFAULT 0`.
- Para BDs existentes: borrar `travian_bot.db` o usar el script de recreación de §17.6 del spec.

### Router (`attack_reports.py`)
- Import y manejo de `DefeatReportParseError` en `_parse_or_422()` → HTTP 422 con `"formato inesperado"`.

### Frontend
- `ReportPreview.jsx` → `mapDefenderTroops`: usa `a.present != null ? a.present : null` en lugar de `a.present ?? 0`.
- `TravianReport.jsx` → `NumRow`: si `raw === null || undefined`, muestra `'?'` con color `text-tertiary`.
- `TravianReport.jsx` → `buildFormationSourceTroops`: helper `addOrNull` para preservar `null` al agregar.

### Tests
- 2 fallos preexistentes en la suite (test_login_use_case + test_session_api) — no son regresiones del delta.
- Suite tras delta: 1099 passed, 2 failed, 23 skipped.

**Why:** Travian no expone cantidades del defensor cuando el atacante pierde. `null` representa semánticamente "cantidad desconocida" vs `0` ("oasis vacío de ese tipo").

**How to apply:** Cualquier parser que procese tablas de Travian con filas de `?` debe usar `_is_defeat_row/_is_mixed_row` y preservar `null` en la entidad. [[attack-reports-pattern]]
