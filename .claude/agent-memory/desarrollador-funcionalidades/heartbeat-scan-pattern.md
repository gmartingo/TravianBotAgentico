---
name: heartbeat-scan-pattern
description: Patrón HEARTBEAT_SCAN en WorldAgent: latido de vigilancia híbrida; TaskQueue.__iter__; _enqueue_heartbeat con jitter amplio; fallos preexistentes de route-templates y Fernet
metadata:
  type: project
---

El Bloque 6 del radar (vigilancia híbrida v5) añade `TaskType.HEARTBEAT_SCAN` al scheduler del WorldAgent.

## Patrón de implementación

- `_enqueue_heartbeat()`: `uniform(intervalo*0.5, intervalo*1.5)`, `priority=2`, `recurring=False`. Solo encola si `_should_reenqueue_noise()` (HARDCORE/PASIVO) e `incoming_db is not None`.
- `_handle_heartbeat_scan()`: (a) check sesión, (b) check piggyback reciente (`< intervalo*0.5`), (c) `get_dorf1_html` → actualiza `_last_sidebar_scan` → llama a `_post_page_hook`, (d) reencola siempre al final.
- `_maybe_run_page_hook()`: actualiza `_last_sidebar_scan = datetime.now()` ANTES de `_post_page_hook` (VH-04).
- `seed_noise_loop_on_session_start()`: encola primer HEARTBEAT_SCAN si `incoming_db is not None`.

## Gotcha: TaskQueue no era iterable

`TaskQueue` no tenía `__iter__`. El código de producción usaba `for t in self._queue` en `_has_pending_radar_task` y `_count_pending_profile_tasks`, pero esas ramas no eran alcanzadas en tests. Al añadir tests del heartbeat que inspeccionan la cola se descubrió el bug. Se añadió `__iter__` que itera sobre `list(self._tasks)` (snapshot seguro). Ver `core/scheduling/task_queue.py`.

## Fallos preexistentes conocidos en la suite

- `test_execute_invalid_token_raises_login_failed` — Fernet key de entorno (preexistente)
- `test_post_session_invalid_token` — idem
- `test_CAT_AD01_crear_template_con_categoria_libre` — route-templates adapter con `category` kw arg (preexistente)

**Why:** no son regresiones del heartbeat; existían antes del Bloque 6.
**How to apply:** ignorarlos al ejecutar la suite completa; para el radar, ejecutar solo los ficheros específicos del spec.

## Comando de tests del radar (Bloque 6 incluido)

```bash
cd /Users/german/DEV/travian-radar && \
  "/Users/german/DEV/Travian con Agentes/.venv/bin/python" \
  -m pytest tests/unit/test_incoming_attack_parsers.py tests/test_incoming_attacks_api.py \
            tests/unit/test_rally_village_parsers.py tests/unit/test_heartbeat_scan.py -q
# → 113 passed
```
