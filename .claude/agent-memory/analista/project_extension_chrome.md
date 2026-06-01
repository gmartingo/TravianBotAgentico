---
name: project-extension-chrome
description: Extensión Chrome MV3 de captura de reportes Travian — decisiones de arquitectura, CORS, host_permissions y restricción anti-detección
metadata:
  type: project
---

Feature "Extensión Chrome MV3 — Captura de reportes de ataques a oasis" — spec guardado en `docs/specs/extension-chrome-captura-reportes.md`.

**Why:** Capturar reportes de ataques a oasis desde Travian con un solo clic, enviándolos a `POST /attack-reports` sin preview ni confirmación.

**How to apply:** Si se toca esta extensión o se diseña otra extensión Chrome para el proyecto, partir de estas decisiones.

## Decisiones arquitectónicas clave

### CORS — service worker fetch (sin delta de backend)
- Las peticiones HTTP al backend se hacen desde el **service worker**, no desde el content script
- En MV3, el service worker con `host_permissions` sobre la URL destino evita el preflight CORS
- El backend NO necesita CORSMiddleware — delta de backend CERO
- Alternativa descartada: `CORSMiddleware` con `allow_origins=["chrome-extension://<id>"]` porque el ID varía entre instalaciones de desarrollo

### host_permissions — lista explícita de TLDs Travian
- El patrón `*://*.travian.*/*` NO es válido en MV3 (comodín en TLD no permitido)
- Solución: lista explícita de TLDs conocidos de Travian (com, es, de, fr, it, ru, net, pl, etc.)
- Para el backend (IP configurable): `"http://localhost/*"` + `"http://192.168.*.*/*"`

### Permisos mínimos del manifest
- Solo `storage` y `activeTab`
- Sin `tabs`, `cookies`, `webRequest`, ni acceso a historial
- Instalación: "Load unpacked" (sin Chrome Web Store)

## Restricción anti-detección crítica
- La extensión NUNCA debe instalarse en los perfiles del bot (`profiles/`)
- Un Chrome con extensión tiene fingerprint diferente al Chrome "limpio" del bot
- Documentar explícitamente en README de la extensión

## EP-02 reutilizado sin modificaciones
- `POST /attack-reports` ya existe y está validado (C1-C7 incorporadas)
- Body: `{"raw_text": str, min_length=1, max_length=50_000}`
- Sin `Accept-Language` obligatorio en este router (datos numéricos/ISO)
- El parser del backend autodetecta el idioma del reporte

## Tarea de verificación pendiente (para el implementador)
- Inspeccionar DOM real de Travian para confirmar el selector del contenedor del reporte
- Candidato: `div#reportContent` — NO confirmado al momento del spec
- Fallback robusto: `document.body.innerText`
- Verificar si Travian usa SPA (navegación sin recarga) para decidir si añadir MutationObserver

## Estructura de la extensión
- Carpeta: `chrome-extension/` en raíz del proyecto (fuera de `frontend/` y `profiles/`)
- Archivos: `manifest.json`, `service-worker.js`, `content-script.js`, `options.html`, `options.js`, `icons/`, `README.md`

## IPC content script ↔ service worker
- Mensajes: `{action: "saveReport", text: rawText}`
- Respuestas: `{status: "success"|"duplicate"|"invalid"|"network_error"|"config_error"|"text_empty", data?, detail?}`

## Estado
- Spec: `ready-for-impl` — contrato API validado manualmente (herramienta Agent no disponible), criterios C1-C7 aplicados, luz verde.
- `apis_validadas_por_desarrollador_apis: true` — validación manual por el analista con criterios del proyecto.
