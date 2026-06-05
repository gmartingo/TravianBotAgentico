---
name: radar-ataques-entrantes-feature
description: "feature radar de ataques entrantes — spec v3 en docs/specs/radar-ataques-entrantes.md; A/B ready-for-impl, C/D bloqueados por fixture"
metadata: 
  node_type: memory
  type: project
  originSessionId: 9651a264-00ca-4a77-8440-cb70320c1e78
---

Feature "Radar de ataques entrantes" especificada en `docs/specs/radar-ataques-entrantes.md` (spec v3, 2026-06-05). Cuatro componentes:

- **A — Radar cross-cutting del sidebar** (`ready-for-impl`): en CADA interacción post-login se parsea el HTML ya cargado de `#sidebarBoxVillageList` (coste cero, sin petición extra) para detectar qué aldeas propias están bajo ataque. **Discriminador CONFIRMADO = `div.listEntry.village.attack`** (clase `attack` en el listEntry). OJO: `span.incomingTroops > svg.attack` está SIEMPRE presente en las 8 aldeas (señuelo) y `svg.handle` es el mango de arrastre — ninguno discrimina. Confirmado por diff de fixtures con-ataque vs sin-ataque. Hook = punto único de invocación en `WorldAgent` tras tarea de browser; no-op si no hay sidebar (p.ej. login).
- **B — dorf1 con timer** (`ready-for-impl`): parser del bloque `troopMovements` en dorf1.php; `img.att1`=entrante hostil, `img.att2`=saliente, `span.timer[value=N]`=segundos al impacto. Reutiliza el HTML ya cargado (sidebar+timer viven ambos en dorf1.php); `browser.get` solo fallback marcado como deuda [[stats-overview-direct-url-debt]]. Una lectura por detección, NO polling.
- **C — rally point** (`blocked-needs-fixture`): navegar por click humano a `build.php?gid=16&tt=1` para quién/origen/tipo/hora. Falta el HTML real (GAP-02).
- **D — ficha del atacante** (`blocked-needs-fixture`): seguir el hipervínculo de cada aldea atacante (máx 3, `human_delay(4000,9000)`, idempotente) para registrar sus datos. Falta el HTML (GAP-03).

Persistencia: tabla `incoming_attacks` por mundo, FK con `ON DELETE CASCADE`; la alerta "activa" = consulta filtrada por `impact_at > now()`, nunca se borran filas al impactar; separada de `attack_reports` (post-combate). API: `GET /game/incoming-attacks/{world_id}` + `POST .../check`; SIN `Accept-Language` (desviación consciente: no hay texto localizado; coherente con endpoints de sesión); `503` (no 409) para sesión no activa; `limit` máx 100.

Validada por palantir (reutilización), guardian-antideteccion (anti-detección) y desarrollador-apis (contrato) antes de implementar. Pendiente: fixtures C/D, implementación, y el gate humano de prueba manual antes de commit.
