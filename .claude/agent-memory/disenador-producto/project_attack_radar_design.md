---
name: project-attack-radar-design
description: Diseño de aviso de ataques en dos niveles (badge S4 + panel S9). Spec listo. Mockup generado. Gate humano pendiente.
metadata:
  type: project
---

Spec anterior `docs/design/aviso-ataque-entrante.md` marcado como SUPERSEDED.
El usuario descartó el banner global fijo. El nuevo diseño vive en
`docs/design/aviso-ataque-mundos.md`. Estado: ready-for-impl.
Mockup: `frontend/mockups/aviso-ataque-mundos.playground.html` (12 vistas). Gate humano: pendiente aprobación.

**Dos niveles:**

**Nivel 1 — AttackBadge en AccountDetailPage (S4):**
- Badge compacto `ShieldAlert` (12px) + número, token `--danger`.
- Aparece en la celda de Sesión junto al `SessionStatusBadge` existente.
- En tarjeta móvil: línea secundaria junto al SessionStatusBadge.
- P1: nunca oculto en móvil. Solo visible con sesión activa.
- Fallo silencioso: si el fetch falla, la fila queda sin badge, sin degradar la UI.
- Backend: endpoint `GET /game/incoming-attacks/summary` → `[{world_id, attack_count}]` (PA-2 CERRADA).

**Nivel 2 — IncomingAttacksPanel en WorldSpacePage (S9):**
- Panel con polling propio 20 s (no contexto global; worldId ya disponible en S9).
- Ubicación: PESTAÑA "Ataques" nueva en el sidebar, patrón igual a Agentes/Farm Lists/Sesión/Ruido (PA-1 CERRADA).
- El nav item lleva badge numérico rojo (`var(--danger)`) cuando count ≥ 1.
- Agrupa ataques por aldea propia atacada en `VillageAttackCard`.
- Por cada ataque: `AttackRow` con countdown (Countdown.jsx reutilizado), hora exacta (ExactTime reutilizado), datos del atacante.
- `attacker_tribe` llega como clave (`gauls`/`romans`/…); el frontend localiza con `t("tribe.<key>")` (PA-3 CERRADA).
- Estado "Detectado · sin detalle" (badge gris) cuando `attacker_name: null`. Sin filas vacías.
- Estado mixto: ataques con y sin detalle en la misma tarjeta (coexisten).
- `aria-live="polite"` en el panel (Nivel 2 = usuario eligió entrar al mundo; no assertive).

**Decisiones cerradas:**
- PA-1 CERRADA: pestaña "Ataques" en el sidebar (no colapsable bajo topbar).
- PA-2 CERRADA: endpoint summary `GET /game/incoming-attacks/summary`.
- PA-3 CERRADA: tribe como clave; `t("tribe.<key>")` en AttackRow.

**Componentes nuevos:**
- `AttackBadge` — badge presentacional para S4.
- `IncomingAttacksPanel` — panel con polling para S9.
- `VillageAttackCard` — tarjeta por aldea propia atacada.
- `AttackRow` — fila por ataque individual.
- `TroopChip` — chip de tipo de tropa + cantidad.

**Reutilizados:** Countdown, ExactTime, ShieldAlert (Lucide), useI18n, api.getIncomingAttacks(worldId), token --danger.

**Why:** usuario descartó el banner global. El nuevo enfoque es contextual: señal pasiva en la lista, detalle dentro del mundo.
**How to apply:** si el desarrollador-ux-ui pregunta sobre el diseño de ataques, referir al spec aviso-ataque-mundos.md. El spec anterior está supersedido. El gate humano (aprobación del mockup) debe completarse antes de implementar.
