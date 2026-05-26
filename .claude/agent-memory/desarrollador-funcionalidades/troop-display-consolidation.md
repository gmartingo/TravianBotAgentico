---
name: troop-display-consolidation
description: Helper resolve_troop_display consolida nombre+icono de tropas; use cases son async; TroopNotFoundError requiere (tribe, ordinal)
metadata:
  type: project
---

`core/use_cases/troop_display.py` contiene `resolve_troop_display(unit_class, lang, translation_port, game_data_port) -> dict` que devuelve `{unit_class, name, icon_url}`.

Reemplaza el `_resolve_troop_name` duplicado que existía en `overview_use_case.py` y `troops_use_case.py`.

**Decisión clave**: vive en `core/use_cases/` (no en `core/utils/`) porque depende de dos puertos del core (TranslationPort y GameDataPort). `core/utils/` solo tiene helpers sin dependencias de puertos.

**Por qué los use cases son async**: `get_troop_stats` y `get_building_catalog` son métodos async del GameDataPort. Los use cases que los llaman heredan la asincronía. Los routers los esperan con `await`.

**TroopNotFoundError** requiere `(tribe: Tribe, ordinal: int | None)` en su `__init__`. En tests, instanciar como `TroopNotFoundError(Tribe.GAULS, 2)` — no como `TroopNotFoundError()`.

**Fallback de uhero**: `unit_class_to_tribe_ordinal("uhero")` devuelve `None` → name=unit_class, icon_url=None, `get_troop_stats` NO se llama.

**Edificios training**: `get_building_catalog(gid)` → `None` hoy (BD vacía) → `icon_url=None`. Forward-compatible: cuando el catálogo se cargue, saldrá solo.

**Edificios overview** (`td.bui`): NO tienen gid disponible en el HTML → no se tocan, siguen con `name_source="server_lang"`.

**Why**: consolidar evita divergencia entre overview y troops; async es correcto porque enriquecer con datos de BD es lógica de aplicación.

**How to apply**: cualquier nuevo use case que necesite nombre+icono de tropa debe importar `resolve_troop_display` de `core.use_cases.troop_display`, NO reimplementar la lógica.

[[troops-block-pattern]]
[[game-data-port-pattern]]
[[async-tests-pattern]]
