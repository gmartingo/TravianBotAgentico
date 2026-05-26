---
name: tailwind-v4-reset-must-be-layered
description: "En el frontend React, el reset CSS global debe ir en @layer base o anula todo el espaciado de Tailwind v4"
metadata: 
  node_type: memory
  type: reference
  originSessionId: e82e3551-50d4-4464-85df-1652fc4e450f
---

En `frontend/src/styles/app.css` (Tailwind v4 vía `@import "tailwindcss"`), un reset universal `*, *::before, *::after { margin:0; padding:0 }` colocado **SIN `@layer`** anula TODAS las utilidades de espaciado de Tailwind (`px-`, `py-`, `mb-`, `gap-`, `space-y-`…). Motivo: en CSS las reglas sin capa ganan a cualquier regla dentro de `@layer` (y las utilidades de Tailwind v4 viven en `@layer utilities`). Síntoma: la UI sale "amontonada, sin espacios", botones desbordando, columnas pegadas — pero los colores/tamaños (`bg-[var()]`, `h-`, `w-`) sí funcionan (el reset no los toca).

**Fix:** envolver el reset en `@layer base { ... }`. Verificado el 2026-05-26 con captura headless de Chrome del dev server.

**Cómo verificar UI:** con el dev server en `:5173`, capturar con `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --window-size=1440,900 --user-data-dir=/tmp/xxx --screenshot=out.png --virtual-time-budget=4500 URL` y leer el PNG. Es localhost (no Travian) → no aplica anti-detección. Relacionado: [[registro-cuentas-mundos-feature]].
