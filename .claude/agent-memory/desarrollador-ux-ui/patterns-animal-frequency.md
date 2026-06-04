---
name: patterns-animal-frequency
description: AnimalFrequencyPanel v5 implementado: normalización backend array→objeto, coordUtils, ResIcon para botín, NatureIcon para animales, tablist ARIA con flechas.
metadata:
  type: project
---

## AnimalFrequencyPanel (EP-TD) — patrón completo

### Normalización del contrato del backend
El endpoint `GET /attack-reports/stats/oasis/temporal-distribution` devuelve:
- `types` como **array** (no objeto), campo `oasis_type` como clave
- Usa `arcilla` para Barro (el spec de diseño llama a esto `barro`)
- Animales con campo `animal_ordinal` (no `ordinal`) para NatureIcon

La función `normalizeResponse(raw)` en `AnimalFrequencyPanel.jsx` transforma:
- Array → objeto indexado por tipo de diseño
- `arcilla → barro` mediante `TYPE_KEY_MAP`
- `animal_ordinal → ordinal` para que NatureIcon funcione
- Infiere `is_empty_db` (no viene del backend) cuando todos tienen 0 reportes y 0 oasis

### Iconos
- Animales: `NatureIcon` con prop `ordinal` (después de normalizar `animal_ordinal`)
- Recursos del botín: `ResIcon` de `TravianReport.jsx` — usa imágenes reales del juego (`stat_wood.png`, etc.), NO Lucide. Siempre verificar si BalanceSection ya usa `ResIcon` antes de elegir iconos alternativos.

### coordUtils.js
Creado en `frontend/src/utils/coordUtils.js`:
- `formatCoord(x, y)` → `"(−70|73)"` con U+2212 para negativos
- `formatCoordSingle(n)` → solo un número formateado
- Reutilizado en: OasisList, HistoryTable, ReportPreview, OasisStatsPanel, OasisCombatPlannerPanel, AnimalFrequencyPanel

### Tablist ARIA (patrón)
```jsx
<div role="tablist" aria-label={t('...')}>
  <button role="tab" aria-selected={isActive} aria-controls={`panel-${key}`}
    id={`tab-${key}`} tabIndex={isActive ? 0 : -1}
    onKeyDown={handleArrowKeys}
  >...</button>
</div>
<div role="tabpanel" id={`panel-${key}`} aria-labelledby={`tab-${key}`}>...</div>
```
Navegación: flechas izquierda/derecha entre tabs; tabIndex en -1 para inactivos; foco gestionado vía `tabRefs.current[next]?.focus()`.

### Claves i18n
Prefijo `ar.freq.*` — añadidas en `es.js` y `en.js`. Los 23 idiomas restantes caen a español via fallback.

### Posición en StatsTab
Posición 4: entre `<OasisCombatPlannerPanel>` y el `<hr>` separador. Estado independiente: `[freqData, freqLoading, freqError, freqIntervalMin]` con `loadFreq(interval)`.

**Why:** [[patterns-oasis-spawn]] — patrón de carga independiente igual que EP-SPAWN.
