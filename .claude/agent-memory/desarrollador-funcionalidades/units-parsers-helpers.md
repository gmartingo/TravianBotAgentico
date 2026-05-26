---
name: units-parsers-helpers
description: Helpers compartidos para los 4 bloques de overview: units.py (uNN→tribu) y parsers/_common.py (game_id, merchants, unit_class)
metadata:
  type: project
---

## core/utils/units.py — mapeo global uNN → (Tribe, ordinal)

Rangos verificados contra troops.json y Tribe enum:
- u1-u10   → ROMANS (ordinal 1-10)
- u11-u20  → TEUTONS (ordinal 1-10)
- u21-u30  → GAULS (ordinal 1-10)
- u31-u40  → NATURE (ordinal 1-10) — NPC; sí tiene entradas en catálogo
- u41-u50  → EGYPTIANS (ordinal 1-10)
- u51-u60  → HUNS (ordinal 1-10)
- u61-u71  → NATARS (ordinal 1-11) — 11 unidades; NATARS_11 nombre vacío → fallback unit_class
- u72-u81  → SPARTANS (ordinal 1-10)
- u82-u91  → VIKINGS (ordinal 1-10)
- uhero, fuera de rango → None

Función: `unit_class_to_tribe_ordinal(unit_class: str) -> tuple[Tribe, int] | None`
Nunca lanza. Tests en `tests/unit/test_units.py` (78 tests total incluyendo _common).

## adapters/browser/parsers/_common.py — helpers de parseo compartidos

Paquete: `adapters/browser/parsers/` con `__init__.py`.

Funciones:
- `extract_game_id_from_vil_cell(vil_cell)` — td.vil.fc > a[href*='newdid='] → int|None
- `extract_game_id_from_village_name_cell(name_cell)` — td.villageName > a[href*='newdid='] → int|None
- `parse_merchants_text(raw, context="")` — 'libres/totales' con bidi → (free, total); (0,0) si inválido
- `extract_unit_class(img_tag)` — primer 'uNN' o 'uhero' de clases img → str|None

Usa BeautifulSoup Tags como argumentos. parse_merchants_text delega limpieza bidi a parse_int.
Tests en `tests/unit/test_parsers_common.py`.

**Why:** palantir dictaminó crear helpers compartidos para los 4 bloques de parsing de overview.
**How to apply:** los parsers overview_parser.py, resources_parser.py, etc. importan desde este paquete en lugar de duplicar lógica.
