---
name: code-health-audit-2026-06-05
description: Resultados de la auditoría completa de duplicaciones y salud arquitectónica, 2026-06-05. Hallazgos consolidados para calibrar futuros gates.
metadata:
  type: project
---

Auditoría completa del árbol fuente ejecutada el 2026-06-05. Hallazgos que NO son derivables releyendo el código, relevantes para calibrar futuros gates:

**Decisión de diseño: _compute_attacker_cost_loss vive dos veces deliberadamente (por ahora)**
- `core/use_cases/attack_report_balance.py` tiene la versión canónica (2026-06-01).
- `adapters/api/routes/attack_reports.py:136` mantiene un wrapper local que NO delega al core — la función está copiada, no extraída.
- El docstring del core dice "el router mantiene _compute_attacker_cost_loss como wrapper que delega aquí", pero en la realidad no delega. Es una duplicación real pendiente de cerrar.

**Decisión deliberada: _NEWDID_RE aparece 3 veces**
- `_common.py` es el canónico para overview/resources/troops — OK.
- `culture_points_parser.py` y `village_map.py` tienen sus propias copias inline. No usan `_common`.
- La razón probable: `village_map.py` vive en `core/` y no puede importar de `adapters/browser/parsers/`. Eso es correcto arquitectónicamente. El problema es que village_map.py importa `bs4` directamente (BeautifulSoup), lo que viola la pureza del core.
- `culture_points_parser.py` debería usar `_common.extract_game_id_from_vil_cell`.

**Decisión deliberada: world_agent.py importa de adapters con imports diferidos**
- Líneas 946, 1077, 1380, 1446, 1447: imports de `adapters.browser.*` dentro de métodos con `# noqa: PLC0415`.
- Son imports diferidos deliberados para "no crear dependencia circular", pero el hecho de que sean necesarios indica que WorldAgent mezcla responsabilidades del core (scheduling, lógica de ruido) con comportamientos del browser adapter.
- Impacto real: el core NO es testeable sin browser en esas rutas. Es la violación arquitectónica más significativa del proyecto.

**Patrón de acceso a app.state inconsistente**
- `dependencies.py` centraliza `get_db_port`, `get_translation_port`, `get_html_source_port`, `get_world_runtime_port`, `get_fernet`.
- Pero `attack_reports.py`, `farm.py`, `noise.py`, `session.py`, `accounts.py` hacen `getattr(request.app.state, ...)` directamente para `attack_report_port`, `noise_db_port`, `session_db_port`, `farm_db_port`, `game_data_port`.
- La mitad de los puertos están centralizados y la otra mitad no.

**session.py importa funciones privadas del adapter**
- `from adapters.db.session_sqlite_adapter import _fill_gaps_with_disconnected, _validate_no_overlaps`
- `from core.entities.session import _block_end_as_datetime, _find_active_block`
- Acceso a internos privados de adapters y entidades del core desde una ruta de API. Debería estar encapsulado en un use case.

**accounts.py accede a SQL directamente**
- `adapters/api/routes/accounts.py:131-132`: `cursor = await db._conn.execute("SELECT created_at FROM worlds WHERE id = ?", ...)`
- Una ruta FastAPI ejecuta SQL directamente sobre la conexión interna del adapter (bypasea el port).

**Campos deprecated req_per_hour en BD**
- 4 columnas `*_req_per_hour_*` en la tabla `noise_config` de SQLite marcadas como deprecated.
- Permanecen por compatibilidad. Pendiente: migración + limpieza documentada en spec `noise-frequency-and-destination-weight.md §7.1`.

**TODO world_id NULL pendiente**
- `attack_reports.world_id` es siempre NULL en MVP (línea 384 del adapter, TODO TR-11 en línea 1604).
- No es duplicación pero sí deuda técnica explícita.

**Spec desactualizado: lectura-overview.md**
- `estado: ready-for-impl` pero el bloque ya está implementado. Los otros 3 (resources, troops, culture-points) dicen `implemented`. El spec del overview principal quedó sin actualizar.

**Mockup orphan: frontend/mockups/login.html**
- Existe `login.html` (459 líneas) Y `login.playground.html` (359 líneas). El primero es un prototipo de diseño anterior al workflow playground. No hay login en la UI React (el login lo gestiona la API). El `login.html` es probablemente huérfano.

**Why:** Los hallazgos sobre world_agent/adapter imports y _compute_attacker_cost_loss son los más críticos para futuras features que toquen scheduling o cálculo de costes.
**How to apply:** En próximos gates, verificar siempre que world_agent.py no está recibiendo nueva lógica que llame a adapters directamente. Para cálculo de costes de tropas, redirigir a `core/use_cases/attack_report_balance.py`.
