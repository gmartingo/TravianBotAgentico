---
name: project-oasis-reportes-docs
description: Documentación completa del tema OASIS (3 features) realizada 2026-06-04: rutas, capturas reales, divergencias detectadas y gaps cerrados
metadata:
  type: project
---

Documentación del tema OASIS completada el 2026-06-04. Tres features documentadas:

## 1. Mecánica de spawn de oasis (actualización)
- `documentacion/funcionalidades/oasis-spawn-mechanics.md` — ACTUALIZADO (añadidas referencias cruzadas y divergencias adicionales)
- Docs de referencia ya existentes: `referencia-funciones/oasis-spawn-composition.md`

## 2. Reportes de ataques a oasis (nuevo)
- `documentacion/funcionalidades/oasis-reportes-ataques.md` — NUEVO (funcional + negocio)
- `documentacion/backend/referencia-funciones/attack-report-adapter.md` — NUEVO (referencia de funciones)
- `documentacion/manual-usuario/oasis-reportes.html` — NUEVO (manual de usuario HTML)

### Capturas reales (10 capturas, 2026-06-04, datos de prueba reales — 2124 reportes en BD)
- `documentacion/manual-usuario/assets/ar-01-vista-historial.png` — página principal, pestaña Ingresar
- `documentacion/manual-usuario/assets/ar-02-tabla-historial.png` — historial con 2124 reportes
- `documentacion/manual-usuario/assets/ar-03-detalle-reporte.png` — drawer de detalle (reporte #2136)
- `documentacion/manual-usuario/assets/ar-04-filtros-historial.png` — filtros del historial
- `documentacion/manual-usuario/assets/ar-05-balance-stats.png` — balance Perdido/Robado, neto +3.114.628
- `documentacion/manual-usuario/assets/ar-06-global-stats.png` — stats globales + lista de 152 oasis
- `documentacion/manual-usuario/assets/ar-07-lista-oasis.png` — lista de oasis navegable
- `documentacion/manual-usuario/assets/ar-08-stats-oasis.png` — stats de un oasis individual
- `documentacion/manual-usuario/assets/ar-09-ingest-vacio.png` — formulario Ingresar vacío
- `documentacion/manual-usuario/assets/ar-10-cadencia.png` — pestaña Cadencia de farmeo (EP-TD)

### Divergencias detectadas en attack-reports:
- DIVERG-01: `attacked_at` se guarda como hora LOCAL del servidor (no UTC como dice el spec RN-08). Intencionado.
- DIVERG-02: EP-balance (`/stats/balance`) no estaba en el spec original. Implementado y funcional.
- DIVERG-03: `_migrate_add_attacker_tribe` se llama dos veces en `ensure_tables()`. Redundante pero inofensivo.
- DIVERG-04: `attacker_tribe` y `attacker_cost_loss` añadidos en el response (no estaban en el spec original).

## 3. Oasis Farming (nuevo — módulo no implementado aún)
- `documentacion/funcionalidades/oasis-farming.md` — NUEVO (spec ready-for-impl, documenta diseño)
- Estado: spec completo en `docs/specs/oasis-farming.md`, implementación pendiente

## Gaps pendientes (cerrados con esta sesión)
- `backend/attack-reports.md` — cubierto por `funcionalidades/oasis-reportes-ataques.md` + `referencia-funciones/attack-report-adapter.md`
- `funcionalidades/attack-reports.md` — cubierto por `funcionalidades/oasis-reportes-ataques.md`
- Extensión Chrome — sigue pendiente (`funcionalidades/extension-chrome.md`), ver gaps en README.md
- Task Order Randomization — sigue pendiente

## Notas para próxima sesión
- `documentacion/README.md` necesita añadir las entradas de los nuevos documentos (ver fragmentos al pie del informe del agente)
- `documentacion/manual-usuario/index.html` necesita enlazar `oasis-reportes.html`
- La pestaña Estadísticas tiene las pestañas en orden: Ingresar, Historial, Estadísticas, Cadencia de farmeo (NO Historial como pestaña por defecto — la UI abre en "Ingresar" por defecto)

**Why:** sesión de documentación integral del tema oasis (junio 2026).
**How to apply:** al documentar en futuras sesiones, consultar estas rutas para no duplicar ni contradecir lo ya escrito.
