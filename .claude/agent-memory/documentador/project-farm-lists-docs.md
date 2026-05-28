---
name: project-farm-lists-docs
description: documentación completa de farm lists y farm stats generada 2026-05-28 — ubicación de archivos, capturas reales, sin divergencias código/spec
metadata:
  type: project
---

Feature farm lists + farm stats (4 Gaps) completamente documentada el 2026-05-28.

## Archivos creados

| Tipo | Ruta |
|---|---|
| Tipo 1 — código | `documentacion/backend/farm-lists.md` |
| Tipo 2 — negocio | `documentacion/funcionalidades/farm-lists.md` |
| Tipo 3 — manual HTML | `documentacion/manual-usuario/farm-lists.html` |
| README actualizado | `documentacion/README.md` (marca de agua 2026-05-28) |

## Capturas reales incluidas en el manual (7 PNG)

Todas en `documentacion/manual-usuario/assets/`:

- `farm-01-vista-principal.png` — pantalla de cuentas
- `farm-02-mundo-pestanyas.png` — espacio mundo, sección Agentes con scheduler
- `farm-03-listas-vacas.png` — tabla de listas de vacas agrupadas por aldea
- `farm-04-drawer-slots.png` — drawer pestaña Slots ("00 Vacas 7x7", 82/82 activas)
- `farm-05-drawer-stats.png` — drawer pestaña Stats con ranking top 5
- `farm-06-scheduler.png` — sección Agentes con scheduler configurado
- `farm-07-drawer-historial.png` — drawer pestaña Historial de "01 Madera"

Las capturas se obtuvieron el 2026-05-28 con `frontend/scripts/uishot.mjs`
(puppeteer-core + Chrome sistema), app corriendo en `http://localhost:5173`,
world_id=1.

## Divergencias código/spec

Ninguna detectada. El código implementado coincide con el spec
`docs/specs/farm-stats-y-metadata-scheduler.md` (estado: `implemented`, 58/58 tests).

## Claves arquitectónicas documentadas

- `FarmSlot`: dos flags separados — `is_active` (usuario/Travian) y `disabled_by_bot` (bot). El usuario tiene prioridad absoluta (RN-04).
- Matching de slots por coordenadas (x,y), no por ID interno de Travian (RN-15, EC-C03).
- `ensure_tables()` del adaptador SQLite maneja migraciones idempotentes (PRAGMA table_info, DROP COLUMN requiere SQLite ≥3.35).
- Stats: patrón 2 queries (sin JOIN) para `_load_slots()` + `_get_bounty_sums()`.
- TTL 7 días en farm_list_send_history y slot_bounty_history (no FK: slot_bounty_history.farm_slot_id es referencia suave).
- `execution_count` en el evento de envío = valor ANTES del incremento (actúa como número de secuencia).

**Why:** La feature es compleja (21 endpoints, 10 use cases, 6 tablas). Guardar contexto para no re-leer todo en futuras sesiones.

**How to apply:** Si el usuario pide actualizar la documentación de farm lists o añadir una sub-feature, leer esta memoria para saber qué ya existe y solo editar/ampliar — no recrear desde cero. Ver [[project-doc-structure]] para convenciones de formato.
