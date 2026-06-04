---
name: project-antideteccion-docs
description: Features de anti-detección documentadas 2026-06-04: human-click v2.3.1, human-sessions v2.1 (incl. UI + manual HTML con 6 capturas reales), noise EP-N01..N14; 7 divergencias detectadas
metadata:
  type: project
---

## Auditoría de cobertura 2026-06-04

### Documentos creados en esta sesión

| Fichero | Contenido | Tipo |
|---|---|---|
| `documentacion/backend/human-click.md` | Motor de click anti-detección: `human_click`, `human_click_at_rect`, `human_drift_toward`, estado global `_CURSOR_POS`/`_TAB_LOCKS`, Bézier, Fitts, divs código/spec | Técnico |
| `documentacion/backend/human-sessions.md` | Human Sessions v2.1: entidades `SessionBlock/Timeline/Override/Config`, `current_mode` pura, integración en WorldAgent (transiciones, HARDCORE/PASIVO/DISCONNECTED, relogin), tablas BD | Técnico |
| `documentacion/backend/noise.md` | Noise navigation: entidades, bucle en WorldAgent, EP-N01..N14, gaps EP-N15 y frequency-weight | Técnico |
| `documentacion/backend/referencia-funciones/human-click.md` | Referencia rápida de firmas y estado global de human-click | Técnico |
| `documentacion/funcionalidades/anti-deteccion-click.md` | Negocio: por qué existe el click humano, qué hace, reglas, limitaciones | Negocio |
| `documentacion/funcionalidades/human-sessions.md` | Negocio: tres modos, calendario semanal, jitter, override, relogin automático, parámetros | Negocio |
| `documentacion/funcionalidades/noise.md` | Negocio: por qué existe el ruido, destinos/rutas/pasos, wizard, ciclo, pendientes | Negocio |

### Documentos actualizados

- `documentacion/README.md`: añadidas entradas para los 7 documentos nuevos + sección de gaps pendientes

### Divergencias código/spec detectadas

| ID | Feature | Spec dice | Código hace | Impacto |
|---|---|---|---|---|
| DIV-HC01 | human-click | `human_drift_toward` usa `randint(3,8)` waypoints | Usa `randint(4,8)` — mínimo 4 en lugar de 3 | Mínimo |
| DIV-HC02 | human-click | `_to_rect` acepta elements vía `.get_bounding_rect()` | En `human_drift_toward` los elements se resuelven con `target.apply(getBoundingClientRect)` directamente | Sin impacto funcional |
| DIV-HS01 | human-sessions | Spec de diseño `human-sessions-ui.md` usa `IDLE` (tokens `--mode-idle`, microcopy `session.status.mode.idle`) | Código implementa `PASIVO` (tokens `--mode-pasivo`). Spec funcional v2.1 ya dice PASIVO. El spec de diseño está desactualizado. | Spec de diseño obsoleto; código correcto |
| DIV-HS02 | human-sessions | Spec de diseño no menciona presets de copia "Toda la semana / Entre semana / Fin de semana" | `BlockEditor.jsx` implementa `COPY_PRESETS` con 3 botones de copia secuencial vía PUT por día | Funcionalidad extra no documentada en diseño |
| DIV-HS03 | human-sessions | Spec menciona `_current_mode(now)` como método del WorldAgent | Implementado como función pura `current_mode()` en `core/entities/session.py` importada como `compute_current_mode` | Mejora de diseño; sin impacto funcional |
| DIV-N01 | noise | EP-N15 "navigate-to-origin" en `ready-for-impl` | No implementado | Botón "Ir al inicio" del wizard no operativo |
| DIV-N02 | noise | Frecuencia como MM:SS + peso controlable | `NoiseConfig` usa `req_per_hour_min/max`; `frequency_weight` en BD pero no expuesto en UI | Frecuencia no configurable como MM:SS desde UI |

### Gaps pendientes detectados (sin documentar todavía)

- **Attack Reports (BD ataques)**: CERRADO en 2026-06-04. Ver `project-oasis-reportes-docs.md`. Docs: `funcionalidades/oasis-reportes-ataques.md` + `referencia-funciones/attack-report-adapter.md` + `manual-usuario/oasis-reportes.html`.
- **Extensión Chrome**: sigue pendiente `funcionalidades/extension-chrome.md`. La extensión vive en `extension/`.
- **Task Order Randomization**: spec en `docs/specs/task-order-randomization.md`, sin doc en `documentacion/`.

**Why:** el alcance solicitado era "gap completo"; estos gaps se detectaron y se anotaron en `documentacion/README.md` §"Gaps pendientes" pero no se documentaron por alcance de tiempo. Abordar en la próxima sesión de documentación.

**How to apply:** en la próxima sesión de documentador, leer la sección "Gaps pendientes" del README antes de crear nuevos docs — esos son los gaps de mayor prioridad.
