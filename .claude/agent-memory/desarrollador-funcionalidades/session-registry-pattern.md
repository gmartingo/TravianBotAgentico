---
name: session-registry-pattern
description: SessionRegistry implementa WorldRuntimePort; patrón de tests de API con app.state override; 9 fallos preexistentes en la suite
metadata:
  type: project
---

SessionRegistry vive en `adapters/browser/session_registry.py` como singleton en `app.state.world_runtime_port`, instanciado en el lifespan de main.py DESPUÉS de `html_source_port` (dependencia de orden: necesita la referencia al adaptador).

**Patrón de cableado en lifespan (main.py):**
1. Crear `html_source_port` (Live o Fixture)
2. Crear `session_registry = SessionRegistry()`
3. `app.state.world_runtime_port = session_registry`
4. Si `live`: `html_source_port.set_callables(registry.get_browser, registry.get_world_server)` + `registry.set_live_adapter(html_source_port)`

**Patrón de tests de API con app.state (sin lifespan manual):**
Usar `_StateOverride` context manager que sobreescribe `app.state.xxx` y lo restaura en `__exit__`. Fixture `scope="module"` con `with TestClient(app) as c:` activa el lifespan una sola vez. Ver `tests/unit/test_session_api.py`.

**9 fallos preexistentes en la suite (no regresiones):**
- 2 tests CA-20 en `tests/antideteccion/test_ca20_catalogo_no_en_browser.py`
- 7 tests en `tests/unit/test_kirilloid_scraper.py::test_parse_upgrade_table_*` (usan MagicMock donde se necesita AsyncMock para query_selector)

**Why:** SessionRegistry no introduce ningun delay propio (anti-detección); delega completamente en `login.py` que tiene los delays humanos.

**How to apply:** Al añadir nuevas features que necesiten acceso al browser, usar `get_world_runtime_port` de `dependencies.py` como dependencia de FastAPI (lanza 503 si no disponible).
