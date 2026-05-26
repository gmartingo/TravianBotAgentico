---
name: design-tokens
description: Tokens CSS duales y cómo están cablerads en Tailwind v4
metadata:
  type: project
---

Fuente: `frontend/DESIGN.md §15`.

Ficheros:
- `src/styles/tokens.css` — define `:root` (claro) + `@media dark :root:not([data-theme=light])` + `:root[data-theme=dark]` + `:root[data-theme=light]`
- `src/styles/app.css` — `@import "tailwindcss"` + `@import "./tokens.css"` + `@theme inline { --color-bg: var(--bg); ... }`

Convención de Tailwind: `bg-bg`, `bg-surface`, `text-text-secondary`, `border-border-strong`, etc.
Tokens de radio: `rounded-[var(--radius-sm)]` (Tailwind no los expone por nombre en v4 sin configuración adicional).

Tema en runtime:
- Sin `data-theme` → sigue `prefers-color-scheme`
- `data-theme="light"` → fuerza claro
- `data-theme="dark"` → fuerza oscuro
- Toggle: `localStorage['theme']` + `document.documentElement.dataset.theme`
- Script anti-FOUC en `index.html` aplica tema ANTES del primer render React.
