---
name: project-radar-ataques
description: Radar de ataques entrantes (pre-combate): 4 componentes, A y B ready-for-impl pleno, C y D bloqueados. Spec v3 — GAP-01 cerrado.
metadata:
  type: project
---

Feature "Radar de ataques entrantes" especificada en `docs/specs/radar-ataques-entrantes.md`.
Spec v3 revisada el 2026-06-05: cierre de GAP-01 con diff con-ataque vs sin-ataque.

## Estado por componente

- **A (sidebar cross-cutting):** `ready-for-impl` PLENO (GAP-01 cerrado). Discriminador confirmado: `div.listEntry.village.attack`. HALLAZGO CRÍTICO: `svg.attack` en `span.incomingTroops` es SEÑUELO PERMANENTE (presente en todas las entradas con y sin ataque — daría falso positivo en las 8 aldeas). `svg.handle` también irrelevante. El parser ignora ambos y solo lee la clase `attack` del `div.listEntry`.
- **B (dorf1 timer):** `ready-for-impl`. Fixture disponible: `img.att1`, `span.timer[value]`, `span.a1`.
- **C (rally point):** `blocked-needs-fixture` (GAP-02).
- **D (ficha atacante):** `blocked-needs-fixture` (GAP-03). Límite: 3 aldeas, `human_delay(4000, 9000)` entre ellas (rango de lectura humana).

## Correcciones clave de v2 (para no repetir errores en futuros specs)

- **Hook solo post-login:** si `#sidebarBoxVillageList` ausente → no-op silencioso. NUNCA cablear en `login.py`.
- **Firmas de click:** `human_click(element, tab)` — el `tab` (zd.Tab) es SIEMPRE obligatorio. Igual para `human_click_at_rect(rect, tab)`. Propagar el `tab` desde el adapter.
- **PROHIBIDO:** `tab.evaluate("...click()")` — click sintético detectable.
- **Selector rally point:** `a[href*='gid=16']` (substring, no igualdad exacta — el href puede traer params de sesión).
- **Punto de invocación único del hook:** solo `WorldAgent._post_page_hook`. Los adapters individuales NO llaman al hook (evita "radar silencioso" al añadir adapters).
- **`browser.get` directo a dorf1 = deuda RT-08** vinculada a `stats-overview-direct-url-debt`. Documentar como fallback, no como patrón aceptable.
- **`human_delay(4000, 9000)` entre fichas de atacante** (subido de 1500-3000; rango de lectura humana).
- **Idempotencia snapshot:** si `attacker_snapshot_json IS NOT NULL` → no volver a navegar esa ficha.
- **`execute_at = utcnow() + random(3..15 s)`** antes de encolar Comp. B — retraso humano variable.
- **Puerto inyectado como OPCIONAL (default None)** en WorldAgent, patrón `noise_db`. Import diferido de `random` (no añadir `ignore_imports` a `.importlinter`).

## Decisiones de modelo y API

- Tabla `incoming_attacks` separada de `attack_reports` (pre-combate ≠ post-combate).
- `impact_at` es NULLABLE (NULL cuando solo viene del sidebar, sin timer de dorf1).
- `seconds_remaining` = null cuando `impact_at IS NULL`; calculado en use case (no handler).
- FK `world_id` ON DELETE CASCADE.
- `UNIQUE (world_id, village_game_id, impact_at)` + ON CONFLICT DO UPDATE.
- Filtro "alerta activa": `WHERE impact_at IS NULL OR impact_at > NOW()` (conservador).

## APIs (v2 — correcciones A1-A7)

- EP-RA01: `GET /game/incoming-attacks/{world_id}` — SIN Accept-Language (ningún campo localizado; desviación consciente documentada). Wrapper `{items, total, limit, offset}` sin `world_id` en raíz. `limit` máximo 100.
- EP-RA02: `POST /game/incoming-attacks/{world_id}/check` — `503` (no `409`) para sesión no activa.
- Router con `prefix="/game"` (coherente con `game_overview_router`).
- `IncomingAttackPageError`: `error_code = "INCOMING_ATTACK_PAGE_ERROR"`, subclase `TravianBotError`.

## GAPs pendientes (fixtures)

- GAP-01: CERRADO (v3, 2026-06-05). Discriminador confirmado con diff con-ataque vs sin-ataque.
- GAP-02: HTML rally point `build.php?gid=16&tt=1` con ataques listados.
- GAP-03: HTML ficha aldea atacante (desde rally point).

**Why:** Spec cerrado con múltiples gates de revisión. Las correcciones de firmas de click y punto de invocación único son las más críticas para la anti-detección.
**How to apply:** Al diseñar cualquier hook cross-cutting de browser: (1) solo post-login, (2) punto de invocación único en WorldAgent, (3) firmas con tab obligatorio, (4) no `evaluate click`. Pre-combate y post-combate = tablas independientes.

[[project-arch-conventions]]
[[project-overview-tronco]]
[[project-human-click]]
