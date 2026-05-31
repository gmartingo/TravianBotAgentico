---
name: patterns-attack-reports
description: S12 AttackReportsPage: TabBar, IngestTab, HistoryTab, OasisList expand-in-place, OasisStatsPanel+RegenRates, formatDateVerbatim, NatureIcon, client.js endpoints
metadata:
  type: project
---

## Feature: BD ataques a oasis (S12) — actualizada 2026-05-31

### Ruta y componentes clave

- Ruta: `/reportes-oasis` → `AttackReportsPage.jsx`
- `frontend/src/pages/AttackReportsPage.jsx` — orquesta TabBar + 3 tabs + ReportDetailDrawer
- `frontend/src/components/attack-reports/` — todos los componentes de la feature
- `frontend/src/components/ui/TabBar.jsx` — strip reutilizable, ARIA completo, navegación flecha
- `frontend/src/components/ui/DeletePopover.jsx` — popover inline con focus trap y Escape

### Tab activo persistido en localStorage

Clave `ar_active_tab`. Patrón para todas las páginas con tabs que necesiten persistencia.

### Flujo IngestTab

POST `/attack-reports/parse` → `{ already_exists, existing_id, attacker_troops[], animals[], bounty, hero_inventory, ... }` → `ReportPreview` mapea props → POST `/attack-reports` para guardar.

El mapeo de props `animals[i].present → quantity_initial, killed → quantity_lost, survived → quantity_survived` está en `ReportPreview.jsx`, no en TravianReport (que no se modifica).

### Endpoints en client.js

- `api.parseAttackReport(raw_text)` → POST `/attack-reports/parse`
- `api.saveAttackReport(data)` → POST `/attack-reports`
- `api.getAttackReports(params)` → GET `/attack-reports?...`
- `api.getAttackReport(id)` → GET `/attack-reports/{id}`
- `api.deleteAttackReport(id)` → DELETE `/attack-reports/{id}`
- `api.getOasisStats(x, y)` → GET `/attack-reports/stats/oasis?x=&y=` (EP-06 — ahora incluye animal_regen_rates)
- `api.listOasisSummaries()` → GET `/attack-reports/oasis` (EP-08 — nueva)

### formatDateVerbatim (CRÍTICO)

`new Date("2026-05-31T13:39:30")` interpreta naive como UTC y añade el offset del PC (España verano = +2h → 15:39 en vez de 13:39). Solución en `frontend/src/utils/formatDateVerbatim.js`. SOLO para `attacked_at`. `created_at` sigue con new Date()+Intl.

### OasisList — patrón expand-in-place

- Una sola fila expandida a la vez (`selectedKey = "x,y"`)
- Cache de detalles en `detailData` = `{ "x,y": {loading, error, data} }` — no recarga si ya tiene data
- Accesibilidad: `aria-expanded`, `aria-controls="oasis-detail-{x}-{y}"`, `role="region"`, navegación teclado
- Mobile: tarjetas apiladas con panel inline

### OasisStatsPanel — estructura actualizada

Orden de secciones: `RegenRatesSection` (KPI) → `AnimalsTable` → `RepopTable` (solo si total_attacks >= 2).

BUG1 corregido (2026-05-31): nombres de campo correctos: `appearances/avg_present/max_present/min_present`. RepopTable: `regenerated_animals[]` (lista) → dict por nombre inline en render.

### NatureIcon

Icono `/api/static/icons/nature_{ordinal}.png` con fallback a badge de texto. Análogo a ResIcon. Props: `ordinal`, `name`, `size`.

### HeroInventory en ReportDetailDrawer

BUG2 corregido (2026-05-31): usa `ResIcon` de `../combat/TravianReport.jsx` en lugar de emojis del OS.

### StatsTab — nueva interfaz

Ahora requiere `onGoToIngest` además de `lang`:
```jsx
<StatsTab lang={lang} onGoToIngest={() => handleTabChange('ingest')} />
```

### Claves i18n (ar.*)

Todas definidas en `src/i18n/catalog/es.js` (base) y `en.js`. Los 23 idiomas restantes tienen el bloque en inglés como fallback funcional. Nuevas claves: `ar.stats.list.*`, `ar.stats.detail.*`, `ar.stats.regen.*`.

### Huecos pendientes

- EP-08 `GET /attack-reports/oasis` y `animal_regen_rates` en EP-06 los implementa `desarrollador-funcionalidades`. Sin backend actualizado, OasisList muestra error de carga.
- Campos `bounty_total`/`attacker_losses_count` en listado GET: la UI los intenta leer pero muestra "—" si no están.
