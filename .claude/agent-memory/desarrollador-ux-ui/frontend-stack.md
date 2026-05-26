---
name: frontend-stack
description: Stack, estructura y comandos del frontend React del proyecto TravianBot
metadata:
  type: project
---

React 18 + Vite 6 + Tailwind CSS v4 (plugin @tailwindcss/vite). Carpeta `frontend/`.

Comandos:
- `cd frontend && npm install` — instalar dependencias
- `npm run dev` — desarrollo en http://localhost:5173 (proxy /api → :8000)
- `npm run build` — build de producción en dist/

Estructura src/:
- `main.jsx` — entry point: BrowserRouter > I18nProvider > App
- `App.jsx` — router: ManagementShell (rutas /cuentas, /cuentas/:id) + WorldSpacePage (/mundos/:worldId)
- `styles/tokens.css` — CSS vars duales claro/oscuro
- `styles/app.css` — @import tailwindcss + @theme inline + reset
- `i18n/` — sistema i18n (ver [[i18n-system]])
- `hooks/useTheme.js` — tema claro/oscuro con localStorage
- `hooks/useWindowSize.js` — breakpoints reactivos
- `components/layout/` — ManagementShell, Topbar, Sidebar
- `components/ui/` — ThemeToggle, LangPicker
- `pages/` — placeholders etapa 1
- `api/client.js` — cliente HTTP con Accept-Language obligatorio

Proxy Vite: `/api/*` → `http://localhost:8000/*` (retira `/api`).
Accept-Language: tomado de `localStorage['lang'] || 'es'` en cada petición.
Tema: `localStorage['theme']` + `data-theme` en `<html>`.
