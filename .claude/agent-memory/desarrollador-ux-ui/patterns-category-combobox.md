---
name: patterns-category-combobox
description: CategoryCombobox: desplegable CRUD de categorías dinámicas, badge dinámico NoiseCategoryBadge, ColorSwatchPicker, integración en RouteTemplatesPage
metadata:
  type: project
---

## CategoryCombobox (src/components/ui/CategoryCombobox.jsx)

Componente combobox completo con CRUD inline para categorías de ruta.
Spec: docs/design/route-categories-combobox.md (estado: implemented 2026-06-06).

### Exportaciones
- `CategoryCombobox` — combobox principal (props: `value`, `onChange`, `readOnly`, `id`)
- `CategoryBadge` — badge dinámico readonly que acepta `{label, color}` (text blanco sobre color, neutro si color=null)
- `PALETTE` — array de 12 entradas `{name, var: '--cat-*'}` con los colores del spec §14

### Subcomponentes internos
- `CategoryItem` — fila de la lista con acciones hover: lápiz/renombrar, paleta/color, papelera/borrar
- `ColorSwatchPicker` — grid 6×2 de swatches + "Sin color"; `role="dialog"`, focus trap con Tab
- `ColorSwatchPicker` se posiciona `position:absolute` dentro del CategoryItem

### Patrón de estado clave
```jsx
// Por item: renamingSlug, swatchOpenSlug, deleteOpenSlug (un slug activo a la vez)
// Por tipo de loading: renameLoading (bool), swatchLoading (slug|null), deleteLoading (bool), creatingLoading (bool)
// Optimistic UI: patchCategory(slug, {color}) → actualiza localmente antes → revierte si falla
```

### NoiseCategoryBadge actualizado (NoiseDestinationsTable.jsx)
Ahora acepta DOS contratos de props:
1. `<NoiseCategoryBadge category="MAP" />` — modo legacy (enum hardcodeado + i18n)
2. `<NoiseCategoryBadge label="Mi cat" color="var(--cat-steel)" />` — modo dinámico (servidor)

### Integración en RouteTemplatesPage
- Carga `api.listCategories()` independiente de `api.listRouteTemplates()` al montar
- Helper `getCatMeta(tpl)` cruza `tpl.category_slug` con el catálogo cargado → `{label, color}`
- La columna Categoría en la tabla usa `<NoiseCategoryBadge label={catLabel} color={catColor} />`
- Filtro de tabla: `CategoryCombobox` en lugar del `<select>` hardcodeado
- `NewTemplateModal`: campo categoría ahora es `CategoryCombobox` (CRUD completo desde la creación)

### Responsive
- `isMobile = window.innerWidth < 768` con resize listener
- Desktop: panel flotante `position:absolute` bajo el trigger
- Móvil: overlay `rgba(0,0,0,0.4)` + bottom sheet `position:fixed; bottom:0; insetInline:0; borderRadius top`
- Input búsqueda: `fontSize: isMobile ? '16px' : '13px'` (evitar auto-zoom iOS)
- Trigger altura: `isMobile ? '44px' : '32px'`

### Accesibilidad
- trigger: `role="combobox"`, `aria-haspopup="listbox"`, `aria-expanded`, `aria-controls={listboxId}`
- panel: `role="listbox"`, `id={listboxId}` (generado con `useId()`)
- items: `role="option"`, `aria-selected`
- input: `role="searchbox"`, `aria-autocomplete="list"`, `aria-controls={listboxId}`
- ColorSwatchPicker: `role="dialog"`, `aria-modal`, focus trap Tab + Escape
- DeletePopover: componente existente ya tiene focus trap

### Tokens de color de categorías
Definidos en `tokens.css` (sección `--cat-*`):
`--cat-steel, --cat-moss, --cat-amber, --cat-terracot, --cat-mauve, --cat-teal,`
`--cat-salmon, --cat-slate, --cat-indigo, --cat-sienna, --cat-forest, --cat-warmgra`
Todos WCAG AA (≥4.5:1 texto blanco). Mismos hex en claro y oscuro (mid-tones neutros).

### Deuda conocida
- AC-D14: animación fade+collapse al borrar no implementada (solo unmount instantáneo de React)
- AC-D20: botones de acción inline en CategoryItem son 24×24px (< 28px mínimo desktop del spec); están contenidos en un área de 36px+ pero el target clickeable es 24px

### uishot para verificar
```bash
cd frontend && node scripts/uishot.mjs /tmp/combobox.png \
  '[{"goto":"http://localhost:5173/rutas"},{"wait":2000},{"click":"button[role=combobox]"},{"wait":500}]'
```
