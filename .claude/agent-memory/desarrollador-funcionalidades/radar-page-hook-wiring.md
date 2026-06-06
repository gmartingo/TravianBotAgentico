---
name: radar-page-hook-wiring
description: Patrón de cableado del page_html_provider para invocar _post_page_hook sin romper la frontera hexagonal en WorldAgent
metadata:
  type: project
---

## Patrón: inyectar `page_html_provider` en WorldAgent para el radar de ataques (RT-06)

El hook `_post_page_hook(html, world_id)` de WorldAgent recibe el HTML de la página actualmente cargada mediante un callable inyectado desde el composition root (`adapters/api/routes/farm.py`), sin que `world_agent.py` (core/) importe nada de `adapters.browser.*`.

### Firma del callable

```python
# En WorldAgent.__init__
page_html_provider: Callable[[], Awaitable[str | None]] | None = None
```

Sin parámetros explícitos — el `world_id` queda capturado en la closure construida en `farm.py`.

### Implementación en farm.py (composition root)

```python
async def _page_html_provider(
    _wid: int = world_id,
    _registry=session_registry,
) -> str | None:
    browser_inst = _registry.get_browser(_wid)
    if browser_inst is None:
        return None
    tab = browser_inst.main_tab
    if tab is None:
        return None
    return await tab.get_content()
```

`tab.get_content()` es una lectura CDP del DOM — sin petición HTTP extra (RN-01/G7).

### Punto de invocación en `_execute`

- `await self._maybe_run_page_hook()` DESPUÉS de `SEND_FARM_LIST_GROUP` y `NOISE_NAVIGATION`.
- NO después de `CHECK_INCOMING_ATTACK_DETAIL` — previene re-entrada del radar.

### Helper `_maybe_run_page_hook`

Captura excepciones del provider sin propagar (EC-15). No-op si provider es None.

**Why:** La frontera hexagonal impide que core/ importe adapters.browser.*. El callable se inyecta desde la capa de adapters (composition root) siguiendo el mismo patrón que `sidebar_attack_hook` y `dorf1_attack_reader`.

**How to apply:** En cualquier feature futura que necesite que el WorldAgent lea la página actualmente cargada sin añadir peticiones extra, usar este patrón de provider inyectado.

Ver también: [[noise-navigation-pattern]], [[noise-execution-wiring]]
