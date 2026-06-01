---
name: patterns-stats-historial-cierre
description: Patrones del sprint de cierre: acordeón con useState+max-height, inputs fecha texto con validación en vivo, tabla sin tarjetas sticky, BalanceSection KPI
metadata:
  type: project
---

## Acordeón colapsable (GlobalOasisStatsPanel)

Patrón acordeón implementado en `GlobalOasisStatsPanel.jsx` — componente local `Accordion`:
- Estado: `useState(false)` por acordeón, arranca cerrado
- Cuerpo: `max-height: open ? '2000px' : '0'` + `transition: max-height var(--dur-base) var(--ease)`
- Accesibilidad: `role="button"`, `aria-expanded`, `aria-controls`, `tabIndex=0`, Enter/Space activan
- Chevron: rotación CSS 180° con `transform: open ? 'rotate(180deg)' : 'rotate(0deg)'`
- `prefers-reduced-motion`: style tag `@media (prefers-reduced-motion: reduce) { #${bodyId} { transition: none !important; } }`
- IMPORTANTE: NO modifica RegenRatesSection internamente; lo envuelve desde el padre

## Inputs fecha texto con validación en vivo (HistoryFilters, BalanceSection)

Regex: `/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/`
- Vacío = válido (sin filtro)
- Error: borde `var(--danger)`, mensaje `role="alert"`, input `aria-invalid`, `aria-describedby`
- Botón Aplicar: `disabled` + `aria-disabled` + `opacity:0.5` + `cursor:not-allowed` si hay error
- Normalización al aplicar: `valor.trim().replace(' ', 'T')` → ISO 8601 para el backend
- `HistoryTab.handleApplyFilters(normalizedFilters)` recibe las fechas ya normalizadas del hijo

## Tabla sin tarjetas (HistoryTable)

Eliminada la variante tarjeta móvil (`ReportCard` + bloque `md:hidden`).
La tabla es la única representación en todos los breakpoints:
- Contenedor: `overflow-x: auto`, `role="region"`, `tabIndex=0`
- Primera columna th+td: `position: sticky; left: 0; background: var(--surface[-2]); z-index: 1`
- Columnas P2 (Desde, Bajas): siguen con `className="hidden md:table-cell"`

## BalanceSection

Nuevo componente `frontend/src/components/attack-reports/BalanceSection.jsx`:
- Estado propio: `fromDate/toDate` (texto para UI), `appliedFrom/appliedTo` (ISO 8601 para API)
- Consume `api.getBalanceStats({ from_date, to_date })` → `GET /attack-reports/stats/balance`
- Grid Perdido/Robado: 3 columnas (Perdido | divisor | Robado), colapsa a 1 en móvil
- Robado total = `stolen.bounty + stolen.hero_inventory` por recurso
- Neto: 22px fontWeight 700 `--font-mono`, color `--success`/`--danger`/`--text`
- Nota tribes: solo si `reports_without_tribe > 0`, icono ⓘ en `--accent-text`
- Endpoint EP-BALANCE aún pendiente de implementación en backend

## Hueco conocido: doble ≈ en RegenRatesSection

`RegenRatesSection.jsx` hardcodea `≈` antes de `intervalLabel(n)`, y la clave i18n
`ar.stats.regen.interval.pl` ya incluye `≈`. Resultado: "≈ ≈ N intervalos".
NO se toca porque el spec prohíbe modificar `RegenRatesSection` internamente.

## Claves i18n añadidas (S-cierre)

Prefijos: `ar.balance.*`, `ar.stats.global.regen.header/summary`,
`ar.stats.global.appearances.header/summary`, `ar.history.filter.date.placeholder/invalid`
Añadidas en `es.js` y `en.js`. Los 23 idiomas restantes usan fallback automático a `es`.

## Precaución con Write de archivos ya tocados por linter

Si el linter modifica un archivo entre Read y Write, el Write falla con "File has been modified
since read". En ese caso: releer el archivo y usar Edit quirúrgico en lugar de Write completo.
