---
name: project-human-sessions-design
description: Diseño de la pestaña Sesión (Human Sessions): timeline semanal de modos HARDCORE/IDLE/DISCONNECTED, spec ready-for-impl
metadata:
  type: project
---

Feature de anti-detección: pestaña "Sesión" (5.ª) en WorldSpacePage. Diseñada 2026-05-31.

**Spec**: `docs/design/human-sessions-ui.md` (estado: ready-for-impl)
**Mockup**: `frontend/mockups/human-sessions.playground.html`
**Spec funcional**: `docs/specs/human-sessions.md`

## Decisiones de diseño clave

- Encaje en WorldSpacePage como 5.º ítem del sidebar (navItems), no pantalla aparte.
- 3 tokens de modo reutilizando semánticos existentes: HARDCORE=`--success` (verde), IDLE=`--info` (azul), DISCONNECTED=`--text-tertiary` (gris neutro). El oro sigue reservado a acento.
- La barra de timeline de 24h es proporcional a los minutos de cada bloque. Segmentos coloreados por modo.
- Editor de bloques: inline (no modal), expande al seleccionar el día. Validación en vivo en el cliente (replica `_validate_timeline()` del backend en JS).
- Start del primer bloque = 00:00 fijo; end del último bloque = 24:00 siempre.
- Override: 3 pills horizontales. El del modo activo tiene borde `--accent` + fondo `--accent-subtle`.
- Countdown: reutiliza `Countdown.jsx` existente. `font-mono`, `tabular-nums`.
- Microcopy anti-detección: una sola línea en caption `--text-tertiary` (no banner).
- Nombre "Descanso total" para DISCONNECTED en la UI (más humano); el enum sigue siendo `DISCONNECTED` en la API.
- `is_default: true`: hint en el editor, etiqueta "DEFAULT" en el día del selector.

## Componentes a crear de cero
SessionTab, SessionStatusPanel, SessionOverridePanel, WeekdaySelector, TimelineBar, BlockEditor, BlockRow, TimelineCoverageIndicator

## Componentes reutilizados
Countdown.jsx, showToast/ErrorBoundary/Spinner (uiUtils.jsx), useI18n

**Why:** feature motivada por el baneo real del bot por operar 24/7. La UI debe comunicar sin alarmar por qué configurar descansos es importante.
**How to apply:** al diseñar features relacionadas con modos/estados del bot, reutilizar los mismos tokens de color de modo (no inventar nuevos colores).
