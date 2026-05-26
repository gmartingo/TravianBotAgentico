---
name: ui-testing-puppeteer-core
description: "Cómo testear/verificar la UI del frontend yo mismo (render E interacciones) con capturas, antes de enseñársela al usuario"
metadata: 
  node_type: memory
  type: reference
  originSessionId: e82e3551-50d4-4464-85df-1652fc4e450f
---

Para verificar el frontend React (no solo el render, también **interacciones**: clics, abrir menús ⋯, completar el wizard, rellenar formularios) hay una herramienta propia:

**`frontend/scripts/uishot.mjs`** — usa `puppeteer-core` + el **Chrome del sistema** (sin descargar navegador; ya instalado como devDependency de frontend).

Uso:
```
cd frontend && node scripts/uishot.mjs <out.png> '<stepsJSON>'
```
`steps` = array ejecutado en orden, captura al final. Acciones: `{"goto":"http://localhost:5173/..."}`, `{"waitFor":".sel"}`, `{"click":".sel"}`, `{"fill":["#email","x@y.com"]}`, `{"press":"Enter"}`, `{"wait":400}`. Luego hacer `Read` del PNG para verlo.
- Requiere el dev server arriba: `cd frontend && npm run dev` (`:5173`).
- Viewport por env `W`/`H` (default 1440x900, deviceScaleFactor 1). Chrome por env `CHROME_PATH` (default ruta macOS).
- También vale Chrome headless directo para captura simple sin interacción: ver [[tailwind-v4-reset-must-be-layered]].

⚠️ **Solo para el dashboard LOCAL (localhost). NUNCA apuntar a Travian** — es una herramienta de dev del front, no el bot; no toca la capa anti-detección.

**Hábito pedido por el usuario (2026-05-26):** tener autonomía para testear yo las interacciones y **verificar cada pantalla/interacción con captura ANTES de enseñársela** — nunca mostrarle cáscaras/placeholders ni decir "míralo" sin haberlo comprobado. **Why:** ya pasó que se le enseñaron placeholders y UI rota y generó frustración. **How to apply:** tras implementar/cambiar una vista, scriptear el flujo con uishot.mjs, leer el PNG, y solo entonces reportar.
