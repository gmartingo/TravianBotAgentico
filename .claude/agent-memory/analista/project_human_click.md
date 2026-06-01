---
name: project-human-click
description: human-click spec v2.3: Fitts timing, curvatura 10-25%, human_drift_toward, lock por tab — firmas eliminadas y decisiones clave
metadata:
  type: project
---

El spec `docs/specs/human-click.md` está en estado `partially-implemented`: la base v2.2.1 (Bézier, gaussiana truncada, settle, mousedown/up, scroll-into-view, ElementNotClickableError, cursor persistente) está implementada y probada en login real. Los deltas v2.3 están en `ready-for-impl`.

**Dos firmas eliminadas en v2.3:**
1. Bézier completaba en 50-150 ms → ahora Fitts [200-800 ms] con jitter ±15% por waypoint.
2. Cursor quieto entre clicks → `human_drift_toward` aprovecha tiempos de espera con destino conocido.

**Decisiones clave:**
- Fitts: `T = 100 + 80 × log₂(2d/w)`, capado [200, 800] ms. Constantes calibradas para 250-350 ms en distancias medias.
- Curvatura: `[0.10, 0.25]` (vs 0.05-0.20 en v2.2.1). 10% mínimo evita curvas casi rectas en trayectorias largas.
- `human_drift_toward(target, tab, duration_ms, end_distance_px=20)`: sin click, termina a ≤20 px del borde del target (no exactamente en el borde — sería antinatural).
- `asyncio.Lock` por tab via `_TAB_LOCKS.setdefault(id(tab), asyncio.Lock())` — serializa drift + click concurrentes.
- Coroutine ambient de fondo SIN destino: rechazada explícitamente por el usuario ("los humanos no mueven el ratón sin propósito").
- Bézier cuadrático (un control point) mantenido; cúbico pospuesto a v2.4.
- `min_duration_ms: int | None = None` en `human_click` para que el caller especifique tiempo mínimo.

**Specs dependientes de human_click:** login.md, farm-lists.md, oasis-farming.md, human-sessions.md.

**Why:** Dos firmas detectables remanentes tras v2.2.1 identificadas por el usuario en login real.
**How to apply:** Cuando se diseñen specs que invocan clicks en el browser, recomendar human_drift_toward antes de human_click si hay espera de AJAX/dwell disponible. min_duration_ms útil en esperas conocidas.
