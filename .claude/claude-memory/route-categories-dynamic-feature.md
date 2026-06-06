---
name: route-categories-dynamic-feature
description: "categorías de ruta pasan de enum fijo a catálogo dinámico CRUD con color (estilo Notion); IMPLEMENTADO en rama feature/route-templates-portal, pendiente prueba manual + commit"
metadata: 
  node_type: memory
  type: project
  originSessionId: ad55dfdd-15e0-4477-9638-b1c42abeb276
---

El enum cerrado `NoiseCategory` (7 valores, antes inmutable) se sustituyó por un **catálogo dinámico de categorías de ruta** gestionable por el usuario, estilo Notion: crear/renombrar/borrar/recolorear desde un desplegable inteligente (`CategoryCombobox`) en el portal de route templates.

Decisiones de producto (del usuario): categoría de ruta ahora **editable** tras crear; borrar categoría en uso **reasigna sus rutas a `uncategorized`** (default protegido, no borrable); catálogo arranca **en blanco** salvo `uncategorized`; **color por categoría** (paleta de 12 swatches WCAG AA, ninguno usa el oro de acento); alcance **unificado** (aplica a `route_templates` Y `noise_destinations`, para que clone-to-world siga funcionando).

Backend: entidad `core/entities/route_category.py`, tabla `route_categories`, `RouteCategoryDbPort`+adapter (con `reassign_category` atómico y centinela `UNSET` para PATCH de color), router `EP-CAT01..05` en `adapters/api/routes/route_categories.py`. Campo renombrado `category` → **`category_slug`** en entidades, BD, body y response de route_templates/noise (breaking change consumido por el front). Migración M-CAT03/04 recrea tablas sin el CHECK y mapea datos viejos a `uncategorized` (idempotente). `NoiseCategory` queda marcado DEPRECATED en `noise.py` (no borrado físicamente). lint-imports 2 kept/0 broken; pytest 1768 passed (2 fallos preexistentes de token Fernet ajenos).

Specs: [[route-templates-developer-portal-feature]] · `docs/specs/route-categories-dynamic.md` + `docs/design/route-categories-combobox.md` (ambos `implemented`). Pendiente: prueba manual del usuario (gate humano) y commit vía git-flow-advisor con OK explícito.
