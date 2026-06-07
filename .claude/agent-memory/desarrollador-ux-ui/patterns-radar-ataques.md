---
name: patterns-radar-ataques
description: Radar de ataques entrantes — AttackBadge (Nivel 1) en AccountDetailPage + IncomingAttacksPanel (Nivel 2) pestaña Ataques en WorldSpacePage
metadata:
  type: project
---

## Radar de ataques entrantes (spec aviso-ataque-mundos.md — implemented 2026-06-07)

### Nivel 1 — AttackBadge en AccountDetailPage

- Componente: `frontend/src/components/world/AttackBadge.jsx`
- Se monta junto al `SessionStatusBadge` en la celda Sesión (desktop) y línea secundaria (móvil).
- Solo aparece cuando `state === 'active'` Y `attackCounts[world.id] > 0`.
- `attackCounts` se puebla con `api.getIncomingAttacksSummary()` al montar AccountDetailPage. Si falla → `{}` → sin badges (fallo silencioso).
- Estilos: `color-mix(in srgb, var(--danger) 10%, transparent)` para el fondo, borde 25%, texto `var(--danger)`, font-mono 11px.
- Aria: `role="status"`, `aria-label` dinámico con `t('radar.badge.aria_one')` / `t('radar.badge.aria_other', { count })`.

### Nivel 2 — IncomingAttacksPanel en WorldSpacePage

- Componente: `frontend/src/components/world/IncomingAttacksPanel.jsx`
- Sub-componentes inline: `TroopChip`, `AttackRow`, `VillageAttackCard`, `SkeletonCard`.
- Pestaña "Ataques" añadida en WorldSpacePage entre Dashboard/Agentes y Sesión.
- Nav-badge: fondo `var(--danger)`, texto blanco 10px, mínimo 18px alto. Se pasa como `item.badge` en el array `navItems`.
- Polling: `setInterval(fetchAttacks, 20_000)` dentro de `IncomingAttacksPanel` (no compartido con el contexto global).
- `onCountChange` callback → `setAttackCount` en WorldSpacePage para el nav-badge.
- Estados cubiertos: loading (SkeletonCard×2), error-initial (botón Reintentar), no-session (IconLock), ok-vacío (ShieldCheck), ok-con-ataques.
- Error de polling: aviso inline bajo cabecera, contenido previo permanece.
- Animación pulso: CSS inyectado en `<head>` con id `radar-pulse-css` (una vez). Clase `.radar-imminent` en countdown ≤60s. Respeta `prefers-reduced-motion`.
- RTL: `marginInlineStart`/`insetInlineStart` en todos los márgenes; coordenadas con `direction: ltr; unicodeBidi: isolate`.
- Distancia (`distance`): muestra "Dist. X,XX campos" (toFixed(2).replace('.', ',')). Si `null` → no aparece. P2 en móvil (oculto < md).
- Campos P2 (coords origen, alianza, pob, distancia): `className="md:block hidden"` / `className="md:inline hidden"`.

### API client

- `api.getIncomingAttacksSummary()` → GET `/game/incoming-attacks/summary` → `[{world_id, attack_count}]`
- `api.getIncomingAttacks(worldId)` → GET `/game/incoming-attacks/:worldId` → `{ items: VillageAttacks[] }`

### I18n

- Namespace `radar.*` completo en `es.js` y `en.js` (29 claves).
- `worldnav.attacks` traducida en los 25 idiomas.
- Las 28 claves restantes de `radar.*` usan fallback a `es` en los 23 idiomas no redactados.
- Sistema de fallback del proyecto (`translate()` en i18n/index.jsx) lo maneja automáticamente.

### Deuda conocida

- ESLint v9 no configurado en el proyecto (no hay `eslint.config.js`). `npm run lint` falla.
- `sessionActive = true` hardcodeado en WorldSpacePage: WorldSpacePage solo se monta con sesión activa. Si la sesión puede caerse en runtime, propagar el estado real.
