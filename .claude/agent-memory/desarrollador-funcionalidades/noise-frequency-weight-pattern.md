---
name: noise-frequency-weight-pattern
description: Patrón de implementación de frecuencia de ruido por intervalo (v2) y peso de destino (navigation_weight) — reemplaza req_per_hour
metadata:
  type: project
---

## Migración req_per_hour → interval_seconds

`NoiseConfig` ya no tiene `*_req_per_hour_*`: los 4 campos son `hardcore_interval_min/max_seconds` y `passive_interval_min/max_seconds`. Piso guardian **30 s** blindado en `__post_init__`.

La tabla `world_noise_config` conserva los campos viejos como deprecated (compatibilidad BD). Las 4 nuevas columnas se añadieron con `DEFAULT NULL` en M-FW01 (`_migrate_noise_config_add_interval_fields`). M-FW04 endurece el CHECK de `frequency_weight` en `noise_destinations` a `>= 0.1 AND <= 5.0`.

**Migración lazy en `get_or_create_noise_config`:** si los campos interval son NULL (BD antigua), los inicializa con defaults y los persiste (EC-FW01, §9.1).

## NoiseDestination: cap de peso [0.1, 5.0]

`frequency_weight` del rango `> 0` pasó a `0.1 ≤ weight ≤ 5.0` (guardian RN-FW07). La entidad lo valida en `__post_init__` con mensaje "navigation_weight debe estar entre 0.1 y 5.0". El adaptador también lo valida. El CHECK de BD también.

## Alias navigation_weight → frequency_weight en la API

Los Pydantic models de EP-N03/N04/N05 usan `navigation_weight` (no `frequency_weight`). El handler mapea `body.navigation_weight → frequency_weight` al llamar al adaptador. La entidad interna y la columna de BD no cambian.

## _calculate_next_noise_gap (v2)

Firma: `(self, mode, config)` — sin `recent_productive_traffic` (eliminado RN-FW04).
Jitter gaussiano SIEMPRE: `min(1.15, max(0.85, random.gauss(1.0, 0.08)))` sobre `raw_base`.
`silence_floor = max(30, iv_min) * random.uniform(1.0, 1.15)` — aleatorizado para evitar repeticiones.
Cap silence: `[max(30, iv_min)×jitter_floor, min(7200, iv_max×4)]`.

## pick_random_safe_destination: clamp 60%

Con 2+ destinos, aplica clamp iterativo: si alguna prob > 0.60, la fija a 0.60 y redistribuye el exceso proporcionalmente. Con 1 destino → retorna directo (no hay sorteo, no es firma).

## Fallos preexistentes en suite (3)

- `test_login_y_driver_no_modificados_respecto_a_head[adapters/browser/driver.py]` — guardian de commits
- `test_execute_invalid_token_raises_login_failed` — sesiones
- `test_post_session_invalid_token` — sesiones
