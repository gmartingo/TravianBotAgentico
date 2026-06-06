---
name: project-category-combobox-design
description: CategoryCombobox — desplegable inteligente estilo Notion para categorías de ruta; spec draft + mockup 10 vistas pendiente gate humano
metadata:
  type: project
---

CategoryCombobox reemplaza el <select> hardcodeado de NoiseCategory en RouteTemplatesPage y NoiseDestinationDrawer.

Spec de diseño: `docs/design/route-categories-combobox.md` (estado: draft, pendiente gate humano mockup).
Mockup editable: `frontend/mockups/category-combobox.playground.html` (10 bloques arrastrables).

**Decisiones clave de diseño:**
- Typeahead + crear desde el mismo input (flujo P1 del spec funcional).
- Acciones inline en hover (lápiz, swatch color, papelera) — divulgación progresiva.
- Item `uncategorized` sin papelera (RN-CAT01), con lápiz y color (RN-CAT02/03).
- DeletePopover reutilizado sin modificar.
- Bottom sheet en móvil (< 768px).
- Paleta 12 colores apagados, tokens `--cat-*`: ninguno compite con el oro ni con los semánticos.
- WCAG AA con texto blanco sobre swatch (todos verificados en spec §14).

**Componentes:**
- CREAR: CategoryCombobox, CategoryItem, ColorSwatchPicker, CategoryBadge.
- REUTILIZAR: DeletePopover, Spinner, showToast.
- MODIFICAR: NoiseCategoryBadge → acepta {label, color} en lugar de {category: enum}.

**Paleta de colores (tokens CSS `--cat-*`):**
Acero #2E6DAD · Musgo #3D7A4E · Ámbar #A66521 · Terracota #B5453A · Malva #7A5FAF ·
Teal #2E8B8B · Salmón #C4604E · Pizarra #5C6B7A · Índigo #4A5AC0 · Siena #8B4513 ·
Bosque #2D6A4F · Grafito cálido #6B5B4E.

**Why:** spec funcional `route-categories-dynamic.md` reemplaza el enum NoiseCategory con catálogo dinámico.
**How to apply:** cuando desarrollador-ux-ui implemente el CategoryCombobox, usar el spec de diseño + layout del mockup aprobado por el usuario.

[[project-route-templates-design]]
