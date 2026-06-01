---
name: chrome-extension-mv3-pattern
description: Patrón MV3 para extensiones Chrome en este proyecto; CORS via service worker; iconos PNG con Python stdlib; extracción de texto con alt de <img>; tests con node:test sin deps
metadata:
  type: project
---

## Extensión Chrome MV3 — chrome-extension/

La extensión vive en `chrome-extension/` en la raíz del repo (fuera de `frontend/` y de `profiles/`).
No tiene tests automáticos (las extensiones Chrome MV3 no tienen framework de tests estándar).
Validación de sintaxis JS con `node --check`.

## Patrón CORS via service worker

El content script NO hace fetch al backend directamente (correría bajo el contexto del dominio Travian
y Chrome aplicaría CORS blocking). La arquitectura correcta:
1. Content script extrae el texto del DOM y envía `chrome.runtime.sendMessage({action, text})`
2. Service worker recibe el mensaje, hace el fetch (tiene `host_permissions` → sin CORS), y responde
3. Content script recibe la respuesta y muestra el toast

El backend NO necesita CORSMiddleware para esto. El ID de extensión varía entre instalaciones
de desarrollo, por lo que `allow_origins=["chrome-extension://<id>"]` sería frágil.

## Iconos PNG sin dependencias externas

Se generan con Python stdlib (zlib + struct) en un script one-shot. Sin Pillow ni otras deps.
Ver el script en el registro de implementación del spec.

## host_permissions en MV3

El patrón `*://*.travian.*/*` NO es válido en MV3 (comodín en TLD no está soportado).
Hay que listar explícitamente cada TLD:
`*.travian.com, *.travian.es, *.travian.de, ...` + `http://localhost/*` + `http://192.168.*.*/*`

## Restricción anti-detección crítica

La extensión NUNCA debe instalarse en los perfiles del bot (`profiles/`). Documentado en README.
No hay mecanismo técnico que lo impida; solo la documentación lo advierte.

**Why:** Instalar la extensión en un perfil del bot alteraría su fingerprint ante Travian.
**How to apply:** Siempre incluir el AVISO en README.md de cualquier herramienta que no sea el bot.

## Heurística de isReportPage()

La URL de los reportes en Travian no está documentada de forma canónica. Implementar con
4 patrones conocidos: `berichte`, `/reports`, `t=13`, `type=13`. Marcar como "requiere
verificación manual" en el spec. El fallback de `document.body.innerText` hace que el
backend rechace con 422 si no es un reporte válido, haciendo el error detectable.

## Bug verificado: innerText ignora <img> en Travian T4.6

**Causa raíz del 422 en reportes de oasis:** Travian T4.6 muestra tropas y animales como
iconos `<img alt="Phalanx">`, `<img alt="Rat">`. `document.body.innerText` ignora las
imágenes → el texto extraído solo contiene números → el parser del backend no puede
identificar las tropas → devuelve 422. El Ctrl+A/Ctrl+C real del browser SÍ incluye los alt.

**Solución (Enfoque A, sin permisos extra):** `extractTextWithImageAlts(node)`:
1. `clone = node.cloneNode(true)`
2. `clone.querySelectorAll('img')` → `img.replaceWith(document.createTextNode(img.alt || img.title))`
3. Insertar clon con `position:absolute; left:-99999px; visibility:hidden` (NO `display:none`,
   que hace que `innerText` devuelva `''` porque anula el layout)
4. `text = clone.innerText` (ahora incluye los nombres y los \t de celdas de tabla)
5. `clone.remove()`

**Tests sin deps externas:** `node:test` + `node:assert` + mock de DOM puro en JS.
Ficheros: `chrome-extension/tests/test-extract.js` + `chrome-extension/tests/fixture-report.html`
Comando: `node chrome-extension/tests/test-extract.js`

**Limitación de los tests sin browser:** Los `\t` de celda de tabla los produce `innerText`
con layout real; sin browser no se pueden testear. La lógica de sustitución img→texto sí se
puede testear con un mock de DOM (querySelectorAll, replaceWith, textContent).
