---
id: extension-chrome-captura-reportes
titulo: Extensión Chrome MV3 — Captura de reportes de ataques a oasis
estado: implemented
fecha: 2026-06-01
autor: analista
apis_validadas_por_desarrollador_apis: true
---

# Extensión Chrome MV3 — Captura de reportes de ataques a oasis

## 1. Objetivo de negocio

Permitir al usuario capturar reportes de ataques a oasis de Travian con un solo clic desde la propia página del reporte, enviándolos directamente al backend local (`POST /attack-reports`) sin ningún paso intermedio de confirmación. El backend valida el texto y persiste el reporte; la extensión proporciona feedback inmediato (toast + badge) sin alterar la experiencia de navegación en Travian.

La extensión **no forma parte del bot de Travian**. Es una herramienta de captura manual instalada en el Chrome personal del usuario.

---

## 2. Actores y permisos

| Actor | Rol |
|---|---|
| Usuario | Único actor. Navega Travian, hace clic en el botón flotante y recibe feedback |
| Backend TravianBot | Receptor de los reportes. Expone `POST /attack-reports` en `http://localhost:8000` (o IP Raspberry Pi) |

**Restricción crítica de anti-detección:** La extensión se instala **exclusivamente** en el Chrome personal del usuario (el mismo que usa para navegar manualmente). **NUNCA** debe instalarse en los perfiles gestionados por el bot (`profiles/`), ya que eso alteraría el fingerprint del browser automatizado y podría comprometer la indetectabilidad. Esta restricción debe quedar documentada en el `README` de la extensión.

---

## 3. Alcance

### Dentro de alcance

- Botón flotante inyectado en páginas de detalle de reporte de Travian
- Extracción del texto del reporte del DOM
- Envío directo a `POST /attack-reports` (sin preview ni confirmación)
- Feedback: toast en página (verde/rojo) + badge de color en icono de extensión
- Panel de opciones para configurar la URL del backend (persiste en `chrome.storage`)
- Soporte para todos los dominios de Travian (`*.travian.*`)
- Manejo de errores: 201, 409, 422, red caída, URL mal configurada

### Fuera de alcance

- Captura múltiple (batch) desde la lista de reportes
- Panel de previsualización o confirmación antes de guardar
- Configuración de idioma (el parser del backend autodetecta el idioma)
- Notificaciones del sistema (solo toast en página + badge)
- Historial local de reportes capturados
- Autenticación de la extensión con el backend

---

## 4. Reglas de negocio

| ID | Regla |
|---|---|
| RN-01 | Un clic en el botón flotante → extrae texto → `POST /attack-reports` → feedback. Sin pasos intermedios. |
| RN-02 | Si el backend responde 201: toast verde "Reporte guardado" + badge verde en el icono |
| RN-03 | Si el backend responde 409 (duplicado): toast naranja/amarillo "Este reporte ya estaba guardado" + badge amarillo. No se intenta guardar de nuevo. |
| RN-04 | Si el backend responde 422 (texto inválido): toast rojo "Texto no reconocido como reporte válido" + badge rojo |
| RN-05 | Si el backend no está accesible (red caída, timeout): toast rojo "No se pudo contactar con el backend" + badge rojo |
| RN-06 | Si la URL del backend está mal configurada (URL vacía o malformada): toast rojo "URL del backend no configurada o inválida" |
| RN-07 | El `Accept-Language` enviado al backend es siempre `es` (valor fijo). Solo afecta a mensajes de error del middleware; el parseo es independiente del idioma. |
| RN-08 | La URL del backend persiste en `chrome.storage.sync`. Default: `http://localhost:8000`. El usuario la cambia desde el panel de opciones (options page). |
| RN-09 | El botón flotante solo se inyecta en páginas que coincidan con el patrón de URL de un reporte de Travian. Ver §5 para la heurística de detección. |
| RN-10 | La extensión **NUNCA** toca el DOM de Travian más allá de inyectar el botón flotante y el toast. No modifica estilos globales ni interfiere con el comportamiento de la página. |

---

## 5. Flujo principal y flujos alternativos

### Flujo principal (happy path)

```
1. Usuario navega a la página de detalle de un reporte en Travian
2. Content script detecta la URL (pattern: contiene /berichte.php o /reports/ con parámetro de ID)
3. Content script inyecta botón flotante discreto en la página
4. Usuario hace clic en el botón
5. Content script extrae el texto del reporte con la función extractTextWithImageAlts()
   - HALLAZGO (verificado empíricamente 2026-06-01): innerText ignora los <img>,
     pero en Travian T4.6 tropas y animales son iconos <img alt="Phalanx">, etc.
     Sin los nombres el parser devuelve 422. El Ctrl+A/Ctrl+C real sí los incluye.
   - SOLUCIÓN — Enfoque A: clonar el nodo, sustituir cada <img> por un TextNode
     con su alt (o title si no hay alt), insertar el clon renderizado fuera de
     pantalla (position:absolute;left:-99999px — NO display:none, que anula el
     layout que necesita innerText para calcular \t/\n de tablas), leer innerText
     del clon y eliminarlo. Sin permisos extra, sin tocar el portapapeles del usuario.
   - Candidato preferente: div#reportContent (o variantes), fallback: document.body
   - Regla: usar selector estructural, nunca por texto visible
6. Content script envía mensaje al service worker: {action: "saveReport", text: rawText}
7. Service worker lee la URL del backend desde chrome.storage.sync
8. Service worker hace fetch: POST <backend_url>/attack-reports
   - Headers: Content-Type: application/json, Accept-Language: es
   - Body: {"raw_text": rawText}
9. Backend responde 201 con {id, attacked_at, utc_offset, coord_x_dest, coord_y_dest, origin_village_name}
10. Service worker notifica al content script: {status: "success", data: {...}}
11. Content script muestra toast verde "Reporte guardado (ID: N)" durante 3 segundos
12. Service worker actualiza badge del icono a verde "#00C851" con texto "OK"
```

### Flujo alternativo A — Reporte duplicado (409)

```
Paso 9 → Backend responde 409 con {detail: "Reporte ya registrado (id: N, ...)"}
Paso 10 → Service worker notifica: {status: "duplicate", detail: "..."}
Paso 11 → Content script muestra toast amarillo "Este reporte ya estaba guardado" durante 3 segundos
Paso 12 → Badge amarillo "#FFB900" con texto "DUP"
```

### Flujo alternativo B — Texto inválido (422)

```
Paso 9 → Backend responde 422 con {detail: "texto de error"}
Paso 10 → Service worker notifica: {status: "invalid", detail: "..."}
Paso 11 → Content script muestra toast rojo "Texto no reconocido como reporte válido" durante 4 segundos
Paso 12 → Badge rojo "#FF4444" con texto "ERR"
```

### Flujo alternativo C — Backend no accesible

```
Paso 8 → fetch lanza error de red (TypeError: Failed to fetch) o timeout (AbortController 10s)
Paso 10 → Service worker notifica: {status: "network_error"}
Paso 11 → Content script muestra toast rojo "No se pudo contactar con el backend (¿está encendida la Raspberry Pi?)" durante 5 segundos
Paso 12 → Badge rojo "#FF4444" con texto "OFF"
```

### Flujo alternativo D — URL mal configurada

```
Paso 7 → URL no existe en storage o está vacía o malformada
Paso 10 → Service worker notifica: {status: "config_error"}
Paso 11 → Content script muestra toast rojo "URL del backend no configurada. Ve a opciones de la extensión." durante 5 segundos
Paso 12 → Badge rojo "#FF4444" con texto "CFG"
```

### Flujo opciones (configuración)

```
1. Usuario hace clic derecho en icono de extensión → "Opciones"
   o accede desde chrome://extensions → Detalles → Opciones de extensión
2. Options page muestra campo de texto con URL actual del backend
3. Usuario edita la URL y hace clic en "Guardar"
4. Options page valida formato (URL válida, http o https, sin trailing slash)
5. Guarda en chrome.storage.sync
6. Muestra mensaje de confirmación "URL guardada"
```

---

## 6. Edge cases

| ID | Edge case | Tratamiento |
|---|---|---|
| EC-01 | Usuario está en una página de Travian que NO es un reporte | Botón NO se inyecta. El content script evalúa la URL antes de inyectar. |
| EC-02 | Usuario hace doble clic rápido en el botón | El botón se deshabilita al primer clic (disabled=true) y se rehabilita tras recibir respuesta. Evita envíos duplicados. |
| EC-03 | El reporte ya existe en BD (409) | Toast amarillo informativo. No hay opción de "guardar igualmente". El flujo para aquí. |
| EC-04 | El texto extraído es demasiado largo (>50.000 chars) | El service worker trunca o, preferiblemente, el backend rechaza con 422. Documentar en implementación: si el texto supera 50.000 chars, mostrar toast "El reporte es demasiado largo para ser procesado". |
| EC-05 | El texto extraído está vacío o es solo espacios | El service worker detecta rawText.trim() === "" antes de hacer el fetch y muestra toast "No se encontró texto en la página". |
| EC-06 | Backend tarda más de 10 segundos | AbortController con timeout de 10s → flujo alternativo C. |
| EC-07 | Usuario cambia de pestaña mientras se procesa | El toast aparece igualmente cuando el usuario vuelve a la pestaña (el procesamiento sigue en el service worker). |
| EC-08 | Varios dominios de Travian (.com, .es, .de, etc.) | `host_permissions` y `content_scripts.matches` cubren todos. Ver §8 para el patrón MV3 exacto. |
| EC-09 | URL del backend con trailing slash | Options page normaliza: quitar trailing slash antes de guardar. |
| EC-10 | URL del backend es HTTPS (Raspberry Pi con proxy) | Compatible. Solo validar que la URL empieza por http:// o https://. |
| EC-11 | El div#reportContent no existe en la página | Fallback a `document.body.innerText`. El backend rechazará con 422 si el texto no es un reporte válido. |
| EC-12 | El badge no se resetea entre reportes | El service worker resetea el badge a estado neutro (sin texto, sin color) al iniciar un nuevo envío (cuando el usuario hace clic). |
| EC-13 | Extensión instalada en perfil del bot | Restricción documentada en README. La extensión no tiene mecanismos técnicos para detectarlo, pero el README lo prohíbe explícitamente. |

---

## 7. Modelo de datos / cambios de esquema

**Sin cambios en la BD del backend.** El backend ya tiene la tabla `attack_reports` con su esquema completo.

**Datos que persiste la extensión en `chrome.storage.sync`:**

```json
{
  "backendUrl": "http://localhost:8000"
}
```

- Tipo: string
- Scope: sync (disponible en todos los Chrome del usuario si está logueado)
- Default: `"http://localhost:8000"`
- Validación: URL válida que empieza por `http://` o `https://`

---

## 8. Contratos de API / interfaces

### Gate de reutilización: EP-02 ya existe

El endpoint `POST /attack-reports` ya está implementado y validado. **No se crea ni modifica ningún endpoint**. La extensión lo consume tal cual.

**Contrato de EP-02 (validado, sin cambios):**

```
POST /attack-reports
Content-Type: application/json
Accept-Language: es

Body:
{
  "raw_text": string  // min_length=1, max_length=50_000
}

Respuestas:
201 Created:
{
  "id": integer,
  "attacked_at": string,     // formato verbatim del reporte
  "utc_offset": string,      // UTC+N:MM
  "coord_x_dest": integer,
  "coord_y_dest": integer,
  "origin_village_name": string
}

409 Conflict:
{
  "detail": string  // "Reporte ya registrado (id: N, atacado el ... desde '...')."
}

422 Unprocessable Content:
{
  "detail": string  // mensaje de error de parseo
}
```

### Solución CORS — service worker fetch (SIN delta de backend)

**Decisión:** Las peticiones HTTP al backend se hacen desde el **service worker** de la extensión, no desde el content script (que corre en el contexto de la página de Travian).

**Justificación técnica:**
- En MV3, el service worker tiene `host_permissions` globales sobre las URLs declaradas en el manifest
- El navegador NO aplica CORS blocking a peticiones del service worker cuando el origen tiene `host_permissions` sobre la URL destino
- El backend recibe la petición sin cabecera `Origin` problemática (o con `Origin: null`)
- **No es necesario añadir `CORSMiddleware` al backend** — cero delta de backend

**Alternativa descartada:** Añadir `CORSMiddleware` con `allow_origins=["chrome-extension://<id>"]` fue descartada porque el ID de extensión varía entre instalaciones de desarrollo (no empaquetadas), lo que haría que el CORS fallara en desarrollo. Además, añade complejidad innecesaria al backend.

### Patrón host_permissions para dominios Travian

En Manifest V3, el patrón `*://*.travian.*/*` **no es válido** porque el comodín en el TLD no es estándar. El patrón correcto es una lista explícita de los TLDs conocidos de Travian o usar una aproximación que funcione.

**Patrón recomendado para MV3:**

```json
"host_permissions": [
  "*://*.travian.com/*",
  "*://*.travian.es/*",
  "*://*.travian.de/*",
  "*://*.travian.fr/*",
  "*://*.travian.it/*",
  "*://*.travian.ru/*",
  "*://*.travian.net/*",
  "*://*.travian.pl/*",
  "*://*.travian.com.br/*",
  "*://*.travian.pt/*",
  "*://*.travian.nl/*",
  "*://*.travian.tr/*",
  "*://*.travian.ro/*",
  "*://*.travian.cz/*",
  "*://*.travian.sk/*",
  "*://*.travian.hu/*",
  "*://*.travian.ae/*",
  "*://*.travian.us/*",
  "*://*.travian.cn/*"
]
```

Para el backend (URL configurable), se usa `<all_urls>` o una entrada genérica ya que la IP puede variar. Dado que el usuario puede configurar cualquier IP local:

```json
"host_permissions": [
  // ... dominios travian arriba ...
  "http://localhost/*",
  "http://192.168.*.*/*"  // Redes locales habituales
]
```

**Nota de implementación:** Si se quiere mayor flexibilidad para la URL del backend, se puede usar `"<all_urls>"` en `host_permissions`, pero esto triggerea avisos de privacidad en la Chrome Web Store. Para uso interno, es preferible la lista explícita + `http://localhost/*` + `http://192.168.*.*/*`.

### Interfaz de mensajería content script ↔ service worker

```typescript
// Content script → Service worker
interface SaveReportMessage {
  action: "saveReport";
  text: string;  // rawText extraído del DOM
}

// Service worker → Content script (respuesta)
interface SaveReportResponse {
  status: "success" | "duplicate" | "invalid" | "network_error" | "config_error" | "text_empty";
  data?: {  // solo en status: "success"
    id: number;
    attacked_at: string;
    coord_x_dest: number;
    coord_y_dest: number;
    origin_village_name: string;
  };
  detail?: string;  // mensaje de error del backend (409, 422)
}
```

---

## 9. Flujo lógico paso a paso

### Estructura de archivos de la extensión

```
chrome-extension/
├── manifest.json
├── service-worker.js     # background service worker
├── content-script.js     # inyectado en páginas Travian
├── options.html          # página de opciones
├── options.js            # lógica de opciones
├── icons/
│   ├── icon16.png
│   ├── icon48.png
│   └── icon128.png
└── README.md             # IMPORTANTE: restricción anti-detección
```

### manifest.json (estructura)

```json
{
  "manifest_version": 3,
  "name": "TravianBot — Captura de Reportes",
  "version": "1.0.0",
  "description": "Captura reportes de ataques a oasis directamente desde Travian",
  "permissions": [
    "storage",
    "activeTab"
  ],
  "host_permissions": [
    "*://*.travian.com/*",
    "*://*.travian.es/*",
    "*://*.travian.de/*",
    // ... resto de dominios Travian ...
    "http://localhost/*",
    "http://192.168.*.*/*"
  ],
  "background": {
    "service_worker": "service-worker.js"
  },
  "content_scripts": [
    {
      "matches": [
        "*://*.travian.com/*",
        "*://*.travian.es/*",
        "*://*.travian.de/*"
        // ... mismo conjunto que host_permissions de Travian ...
      ],
      "js": ["content-script.js"],
      "run_at": "document_idle"
    }
  ],
  "options_page": "options.html",
  "action": {
    "default_icon": {
      "16": "icons/icon16.png",
      "48": "icons/icon48.png",
      "128": "icons/icon128.png"
    }
  }
}
```

### Pseudocódigo — content-script.js

```javascript
// Heurística para detectar página de reporte
function isReportPage() {
  const url = window.location.href;
  // Travian muestra reportes en URLs con parámetros como ?t=13 o /berichte.php
  // La heurística exacta debe verificarse contra URLs reales de Travian
  // Candidatos conocidos: URL contiene "berichte", "reports", o parámetro de tipo reporte
  return url.includes('berichte') || 
         url.includes('/reports') || 
         (url.includes('?') && url.includes('t=13'));
  // TAREA DE IMPLEMENTACIÓN: inspeccionar URLs reales de reportes en Travian
  // para afinar esta heurística con un selector estructural robusto
}

// Inyección del botón flotante
function injectButton() {
  if (!isReportPage()) return;
  if (document.getElementById('travianbot-capture-btn')) return; // evitar duplicados
  
  const btn = document.createElement('button');
  btn.id = 'travianbot-capture-btn';
  btn.textContent = '📋 Guardar reporte';
  btn.style.cssText = `
    position: fixed;
    bottom: 20px;
    right: 20px;
    z-index: 999999;
    padding: 10px 16px;
    background: #2c5282;
    color: white;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 14px;
    font-family: sans-serif;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
  `;
  
  btn.addEventListener('click', handleCapture);
  document.body.appendChild(btn);
}

async function handleCapture() {
  const btn = document.getElementById('travianbot-capture-btn');
  btn.disabled = true;
  btn.textContent = '⏳ Guardando...';
  
  // Extracción del texto: fallback robusto
  // TAREA DE IMPLEMENTACIÓN: verificar si div#reportContent existe en Travian
  // Si existe, usarlo para acotar la extracción y evitar capturar menús/nav
  const reportContainer = document.querySelector('#reportContent');
  const rawText = reportContainer 
    ? reportContainer.innerText 
    : document.body.innerText;
  
  if (!rawText || rawText.trim() === '') {
    showToast('No se encontró texto en la página', 'error');
    btn.disabled = false;
    btn.textContent = '📋 Guardar reporte';
    return;
  }
  
  // Enviar al service worker (evita CORS — la petición HTTP sale del service worker)
  const response = await chrome.runtime.sendMessage({
    action: 'saveReport',
    text: rawText
  });
  
  handleResponse(response, btn);
}

function handleResponse(response, btn) {
  btn.disabled = false;
  btn.textContent = '📋 Guardar reporte';
  
  switch(response.status) {
    case 'success':
      showToast(`✓ Reporte guardado (ID: ${response.data.id})`, 'success');
      break;
    case 'duplicate':
      showToast('Este reporte ya estaba guardado', 'warning');
      break;
    case 'invalid':
      showToast('Texto no reconocido como reporte válido', 'error');
      break;
    case 'network_error':
      showToast('No se pudo contactar con el backend (¿está encendida la Raspberry Pi?)', 'error');
      break;
    case 'config_error':
      showToast('URL del backend no configurada. Ve a opciones de la extensión.', 'error');
      break;
    case 'text_empty':
      showToast('No se encontró texto en la página', 'error');
      break;
  }
}

function showToast(message, type) {
  // Eliminar toast anterior si existe
  const existing = document.getElementById('travianbot-toast');
  if (existing) existing.remove();
  
  const colors = {
    success: '#00C851',
    warning: '#FFB900',
    error: '#FF4444'
  };
  
  const toast = document.createElement('div');
  toast.id = 'travianbot-toast';
  toast.textContent = message;
  toast.style.cssText = `
    position: fixed;
    bottom: 70px;
    right: 20px;
    z-index: 999999;
    padding: 12px 18px;
    background: ${colors[type]};
    color: white;
    border-radius: 6px;
    font-size: 14px;
    font-family: sans-serif;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    max-width: 320px;
    word-wrap: break-word;
  `;
  
  document.body.appendChild(toast);
  const duration = type === 'error' ? 5000 : 3000;
  setTimeout(() => toast.remove(), duration);
}

// Inicialización
injectButton();
// Re-inyectar si Travian usa SPA (navegación sin recarga completa)
// TAREA DE IMPLEMENTACIÓN: verificar si Travian es SPA
// Si lo es, observar cambios de URL con MutationObserver o popstate
```

### Pseudocódigo — service-worker.js

```javascript
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'saveReport') {
    handleSaveReport(message.text)
      .then(sendResponse)
      .catch(err => sendResponse({ status: 'network_error' }));
    return true; // async response
  }
});

async function handleSaveReport(rawText) {
  // Validación previa
  if (!rawText || rawText.trim() === '') {
    return { status: 'text_empty' };
  }
  
  // Leer URL del backend desde storage
  const config = await chrome.storage.sync.get('backendUrl');
  const backendUrl = config.backendUrl;
  
  if (!backendUrl || !isValidUrl(backendUrl)) {
    await updateBadge('CFG', '#FF4444');
    return { status: 'config_error' };
  }
  
  // Resetear badge al iniciar
  await chrome.action.setBadgeText({ text: '' });
  
  // Fetch con timeout (la petición sale del service worker → sin CORS)
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 10000);
  
  try {
    const response = await fetch(`${backendUrl}/attack-reports`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept-Language': 'es'
      },
      body: JSON.stringify({ raw_text: rawText }),
      signal: controller.signal
    });
    
    clearTimeout(timeoutId);
    
    if (response.status === 201) {
      const data = await response.json();
      await updateBadge('OK', '#00C851');
      return { status: 'success', data };
    }
    
    if (response.status === 409) {
      const data = await response.json();
      await updateBadge('DUP', '#FFB900');
      return { status: 'duplicate', detail: data.detail };
    }
    
    if (response.status === 422) {
      const data = await response.json();
      await updateBadge('ERR', '#FF4444');
      return { status: 'invalid', detail: data.detail };
    }
    
    // Cualquier otro código de error
    await updateBadge('ERR', '#FF4444');
    return { status: 'network_error' };
    
  } catch (err) {
    clearTimeout(timeoutId);
    await updateBadge('OFF', '#FF4444');
    return { status: 'network_error' };
  }
}

async function updateBadge(text, color) {
  await chrome.action.setBadgeText({ text });
  await chrome.action.setBadgeBackgroundColor({ color });
}

function isValidUrl(url) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}
```

### Pseudocódigo — options.js

```javascript
document.addEventListener('DOMContentLoaded', async () => {
  const input = document.getElementById('backend-url');
  const saveBtn = document.getElementById('save-btn');
  const status = document.getElementById('status');
  
  // Cargar valor actual
  const config = await chrome.storage.sync.get('backendUrl');
  input.value = config.backendUrl || 'http://localhost:8000';
  
  saveBtn.addEventListener('click', async () => {
    let url = input.value.trim();
    
    // Normalizar: quitar trailing slash
    if (url.endsWith('/')) url = url.slice(0, -1);
    
    // Validar
    if (!isValidUrl(url)) {
      status.textContent = 'URL inválida. Usa http://... o https://...';
      status.style.color = 'red';
      return;
    }
    
    await chrome.storage.sync.set({ backendUrl: url });
    status.textContent = 'URL guardada correctamente';
    status.style.color = 'green';
    setTimeout(() => status.textContent = '', 3000);
  });
});

function isValidUrl(url) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}
```

---

## 10. Validaciones y reglas

### Validaciones en la extensión (antes de llamar al backend)

| Validación | Dónde | Tratamiento |
|---|---|---|
| rawText vacío o solo espacios | Content script / service worker | Toast "No se encontró texto" — no se llama al backend |
| URL del backend vacía o nula | Service worker | Toast "URL no configurada" — no se llama al backend |
| URL del backend malformada | Service worker | Toast "URL no configurada o inválida" — no se llama al backend |
| rawText > 50.000 chars | Service worker (preventivo) | Toast "El reporte es demasiado largo" — no se llama al backend |
| Botón clickeado mientras hay petición en curso | Content script | Botón deshabilitado durante la petición — ignorado |

### Validaciones en el backend (ya implementadas)

| Validación | Código | Descripción |
|---|---|---|
| raw_text vacío | 422 | `min_length=1` en Pydantic |
| raw_text > 50.000 chars | 422 | `max_length=50_000` en Pydantic |
| Texto no parseable como reporte válido | 422 | Parser del backend |
| Reporte duplicado | 409 | Clave única en BD |

---

## 11. Seguridad, rendimiento y concurrencia

### Anti-detección (restricción crítica)

**La extensión NUNCA debe instalarse en el perfil del bot.** El fingerprint de un Chrome con una extensión de captura instalada difiere del fingerprint de un Chrome "limpio" usado por el bot. Instalar la extensión en `profiles/` comprometería la indetectabilidad del bot ante Travian.

Esta restricción debe documentarse:
1. En el `README.md` de la extensión: "AVISO: Esta extensión es para uso manual únicamente. NO la instales en los perfiles del bot (carpeta `profiles/`)."
2. En `CLAUDE.md` o documentación del proyecto.

### Seguridad

- **No hay autenticación** entre extensión y backend. El backend solo escucha en localhost o red local. Aceptable para uso personal.
- **No se almacenan datos sensibles** en `chrome.storage` (solo la URL del backend, que no es sensible).
- **Permisos mínimos** en el manifest: solo `storage` y `activeTab`. Sin `tabs`, `cookies`, `webRequest`, ni acceso a historial.
- **No se inyecta código externo**: toda la lógica es local (sin CDNs, sin scripts externos).
- El content script **no puede hacer fetch directo** al backend por las restricciones CORS del contexto de la página de Travian — solo puede enviar mensajes al service worker. Esto es por diseño.

### Rendimiento

- El content script es ligero: solo inyecta un botón y un event listener.
- La extracción de `document.body.innerText` puede ser costosa en páginas grandes. Si se identifica el contenedor del reporte (`#reportContent` u otro), acotar la extracción reduce el texto procesado y mejora la experiencia.
- El timeout de 10 segundos al backend es apropiado para conexiones locales (incluso sobre Wi-Fi a la Raspberry Pi).

### Concurrencia

- El botón se deshabilita durante la petición para evitar envíos paralelos (EC-02).
- El service worker de MV3 puede ser terminado por Chrome entre peticiones — esto es normal y esperado. El estado se persiste en `chrome.storage`, no en memoria del service worker.

---

## 12. Plan de pruebas

### Casos felices

| ID | Caso | Resultado esperado |
|---|---|---|
| T-01 | Navegar a página de reporte de oasis en Travian.com | Botón flotante aparece en la esquina inferior derecha |
| T-02 | Clic en el botón con reporte nuevo | Toast verde "Reporte guardado (ID: N)" y badge verde "OK" |
| T-03 | Reporte guardado aparece en `GET /attack-reports` | El reporte está en la BD |
| T-04 | Cambiar URL del backend a IP de Raspberry Pi en opciones | La URL se persiste y se usa en el siguiente clic |
| T-05 | Navegar a página de lista de reportes (no detalle) | Botón NO aparece |
| T-06 | Navegar a Travian.es (dominio diferente) | Botón aparece igualmente |

### Edge cases

| ID | Caso | Resultado esperado |
|---|---|---|
| T-07 | Clic con reporte ya existente en BD (409) | Toast amarillo "Ya estaba guardado", badge "DUP" |
| T-08 | Clic con backend apagado | Toast rojo "No se pudo contactar", badge "OFF" |
| T-09 | Clic con URL del backend no configurada | Toast rojo "URL no configurada", badge "CFG" |
| T-10 | Clic en página con texto inválido (no es reporte) | Toast rojo "Texto no reconocido", badge "ERR" |
| T-11 | Doble clic rápido | Solo un envío (botón deshabilitado durante la petición) |
| T-12 | Backend tarda >10s | Toast rojo "No se pudo contactar" (timeout) |
| T-13 | URL con trailing slash en opciones | Se normaliza automáticamente (la URL guardada no tiene slash final) |
| T-14 | Badge resetea al nuevo clic | Badge vuelve a estado neutro antes de mostrar el nuevo resultado |

### Tests automáticos — extracción de texto con iconos (añadidos 2026-06-01)

**Ficheros:**
- `chrome-extension/tests/fixture-report.html` — HTML que reproduce la estructura de un reporte T4.6 con `<img alt="...">` para tropas y animales
- `chrome-extension/tests/test-extract.js` — 8 tests con `node:test` + `node:assert`, sin dependencias externas

**Comando:**
```
node chrome-extension/tests/test-extract.js
```

**Qué validan:**
- T-UNIT-01: nombres de tropas galas (Phalanx, Swordsman, Pathfinder, Theutates Thunder, Hero)
- T-UNIT-02: nombres de animales de oasis (Rat, Spider, ..., Elephant)
- T-UNIT-03: los números de tropas se conservan junto a los nombres
- T-UNIT-04: fallback a `title` cuando no hay `alt`
- T-UNIT-05: imágenes decorativas sin alt/title no producen texto espurio
- T-UNIT-06: estructura completa de reporte (atacante + defensor)
- T-UNIT-07: árbol sin imágenes funciona igual que antes
- T-UNIT-08: el fixture HTML contiene todos los `alt` esperados

**Limitación conocida:** Los tests validan la lógica de sustitución `<img>` → texto con un mock de DOM puro. No pueden verificar las tabulaciones (`\t`) que produce `innerText` en las celdas de tabla — eso requiere layout de browser real y se verifica con la prueba manual.

**Resultado (2026-06-01):** 8/8 tests pasan.

### Tarea de verificación de implementación

**IMPORTANTE:** El desarrollador debe:
1. Abrir un reporte real de ataque a oasis en Travian
2. Inspeccionar el DOM con DevTools para identificar el contenedor del reporte
3. Verificar si `div#reportContent` existe o cuál es el selector correcto
4. Confirmar que el texto capturado contiene los nombres de tropas (Ctrl+A y comparar)
5. Verificar la heurística de URL de `isReportPage()` con URLs reales de reportes

---

## 13. Riesgos y trade-offs

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| `#reportContent` no existe en Travian → fallback a `body.innerText` captura menú/navbar | Media | Bajo | El backend rechaza el texto inválido con 422; el usuario recibe feedback. Coste: más texto enviado. |
| Travian usa SPA → URL no cambia al navegar entre reportes → botón no se re-inyecta | Media | Medio | Tarea de verificación de implementación: observar si Travian usa navegación SPA. Si lo hace, añadir MutationObserver. |
| Usuario instala la extensión en perfil del bot | Baja | Alto | Documentación explícita en README. No hay mecanismo técnico que lo impida. |
| IP de la Raspberry Pi cambia (DHCP) | Media | Bajo | El usuario actualiza la IP en el panel de opciones. Recomendación: IP estática en el router. |
| Chrome Web Store requiere `<all_urls>` si la lista de host_permissions es insuficiente | Baja | Bajo | Para uso interno, la extensión se instala como "sin empaquetar" (Load unpacked), no a través de la Store. |

### Decisión de trade-off: sin preview

**Decisión:** Un clic → guardar directamente, sin preview ni confirmación.
**Justificación:** El backend valida y rechaza texto inválido con 422. No se persiste basura en la BD. La fricción de un modal de confirmación es innecesaria para el flujo de uso repetitivo (el usuario sabe qué está haciendo).
**Riesgo residual:** Ninguno significativo — el peor caso es un 422 con mensaje claro.

### Decisión de trade-off: CORS via service worker (sin delta de backend)

**Decisión:** Las peticiones HTTP se hacen desde el service worker, no desde el content script.
**Justificación:** Evita añadir `CORSMiddleware` al backend. El ID de extensión varía en desarrollo, haciendo el enfoque CORS con `allow_origins` frágil. El service worker con `host_permissions` es el enfoque canónico en MV3.
**Trade-off:** El content script necesita una capa de IPC (`chrome.runtime.sendMessage`) en vez de hacer el fetch directamente. Complejidad ligeramente mayor, pero más correcta arquitecturalmente.

---

## 14. Pasos de implementación ordenados

1. **Crear la carpeta `chrome-extension/` en la raíz del proyecto** (fuera de `frontend/` y `profiles/`)
2. **Crear `manifest.json`** con los permisos mínimos y la lista de host_permissions para dominios Travian
3. **Crear `service-worker.js`** con la lógica de fetch al backend y actualización de badge
4. **Crear `content-script.js`** con la inyección del botón y el toast
5. **TAREA DE VERIFICACIÓN:** Inspeccionar DOM de un reporte real en Travian para confirmar/refinar el selector de contenedor y la heurística de URL de `isReportPage()`
6. **Actualizar `content-script.js`** con el selector verificado del contenedor del reporte
7. **Crear `options.html` y `options.js`** para la configuración de la URL del backend
8. **Crear los iconos** en `icons/` (16x16, 48x48, 128x128 PNG)
9. **Crear `README.md`** con la advertencia de anti-detección y las instrucciones de instalación
10. **Cargar la extensión en Chrome** ("Cargar sin empaquetar" → carpeta `chrome-extension/`)
11. **Prueba manual** con el backend local arrancado:
    - T-01 a T-06 (casos felices)
    - T-07 a T-14 (edge cases)
12. **Verificar heurística SPA:** Navegar entre reportes en Travian sin recargar la página; confirmar si el botón se inyecta correctamente o si es necesario un MutationObserver

---

## 15. Criterios de aceptación

Lista verificable por el implementador:

- [ ] **CA-01:** El botón flotante aparece en la esquina inferior derecha al navegar a la página de detalle de un reporte en cualquier dominio Travian soportado
- [ ] **CA-02:** El botón NO aparece en páginas de Travian que no son reportes (inicio, aldea, mapa, etc.)
- [ ] **CA-03:** Un clic en el botón con un reporte nuevo resulta en toast verde y badge "OK", y el reporte aparece en `GET /attack-reports`
- [ ] **CA-04:** Un clic con reporte ya existente resulta en toast amarillo "Ya estaba guardado" y badge "DUP"
- [ ] **CA-05:** Un clic con backend apagado resulta en toast rojo y badge "OFF" en menos de 11 segundos
- [ ] **CA-06:** Un clic con texto que no es un reporte válido resulta en toast rojo y badge "ERR"
- [ ] **CA-07:** El doble clic rápido no genera dos peticiones al backend
- [ ] **CA-08:** El panel de opciones permite cambiar la URL del backend y la persiste en `chrome.storage`
- [ ] **CA-09:** La URL del backend se normaliza (sin trailing slash) antes de guardarse
- [ ] **CA-10:** El badge se resetea al estado neutro al inicio de cada nueva petición
- [ ] **CA-11:** La extensión no interfiere con el DOM de Travian más allá del botón y el toast
- [ ] **CA-12:** El manifest declara solo los permisos mínimos: `storage`, `activeTab`, y `host_permissions` para Travian + backend local
- [ ] **CA-13:** El `README.md` de la extensión incluye la advertencia sobre no instalar en perfiles del bot
- [ ] **CA-14:** Las peticiones al backend parten del service worker (verificable en DevTools → Network de la pestaña service worker)
- [ ] **CA-15:** La extensión funciona con backend en `http://localhost:8000` y con backend en `http://192.168.x.x:8000`

---

## 16. Trazabilidad

| Decisión técnica | Requisito / edge case de origen |
|---|---|
| Service worker hace el fetch (no el content script) | CORS: backend sin CORSMiddleware; content script en contexto de página Travian no puede hacer fetch a otro origen. Decidido en análisis técnico, verificado en `main.py` (sin CORSMiddleware). |
| `document.body.innerText` como fallback | Selector `#reportContent` no confirmado. Regla del proyecto: selectores estructurales. EC-11. |
| Botón deshabilitado durante petición | EC-02: doble clic rápido podría enviar dos peticiones. |
| Timeout de 10 segundos | EC-06: backend puede estar en Raspberry Pi sobre Wi-Fi local. |
| Sin `Accept-Language` obligatorio en EP-02 | Decisión del usuario (punto 8): el parser autodetecta el idioma. Verificado en código: el router attack_reports no usa `get_language`. |
| Sin preview ni confirmación | Decisión del usuario (punto 2): el backend valida y el 422 contiene el riesgo. RN-01. |
| Lista explícita de TLDs Travian en host_permissions | Patrón `*://*.travian.*/*` no válido en MV3 (comodín en TLD). Decisión del usuario (punto 6). |
| `chrome.storage.sync` para la URL del backend | Persiste incluso si Chrome se cierra. Sincroniza entre dispositivos del mismo usuario. Decisión del usuario (punto 7). |
| Restricción anti-detección en README | El bot usa perfiles en `profiles/`. Instalar la extensión ahí alteraría el fingerprint. Principio de anti-detección del proyecto. |
| `chrome-extension/` en raíz (fuera de `frontend/`) | La extensión no es parte del frontend React. Es un artefacto independiente. |
| EP-02 REUTILIZADO sin modificaciones | Contrato ya implementado y validado (correcciones C1-C7 incorporadas). Palantir gate: REUTILIZAR. Validación de API: CORRECTO. |
```

---

## Registro de implementación

**Fecha:** 2026-06-01
**Implementador:** desarrollador-funcionalidades

### Ficheros creados

```
chrome-extension/
├── manifest.json         — MV3, permisos mínimos (storage + activeTab + host_permissions)
├── service-worker.js     — fetch al backend, badge, timeout 10s, EC-04/EC-05/EC-06/EC-12
├── content-script.js     — botón flotante, toast, extracción DOM defensiva, soporte SPA
├── options.html          — página de configuración de URL del backend con aviso anti-detección
├── options.js            — lógica de guardado/validación/normalización de URL
├── icons/
│   ├── icon16.png        — 16x16 RGBA, generado con Python stdlib (sin dependencias externas)
│   ├── icon48.png        — 48x48 RGBA
│   └── icon128.png       — 128x128 RGBA
└── README.md             — instrucciones de instalación + AVISO anti-detección (CA-13)
```

### No se modificó ningún fichero del backend ni del frontend.

### Cómo instalar y probar

```
1. Abrir chrome://extensions
2. Activar "Modo de desarrollador"
3. Clic en "Cargar descomprimida"
4. Seleccionar la carpeta chrome-extension/ del repositorio
5. Arrancar el backend: python main.py (desde la raíz del proyecto)
6. Navegar a una página de reporte en Travian
7. Verificar que aparece el botón flotante "Guardar reporte"
8. Hacer clic y verificar toast verde + badge "OK"
```

### Tests automáticos

La validación de sintaxis JS se realizó con `node --check` (todos los archivos pasan).

**Bugfix 2026-06-01 — tests de extracción de iconos añadidos:**
```
node chrome-extension/tests/test-extract.js
→ 8/8 tests pasan (node:test, sin dependencias externas)
```
Ficheros: `chrome-extension/tests/test-extract.js` + `chrome-extension/tests/fixture-report.html`

### Desviaciones respecto al diseño

1. **Selector `report` en URL (isReportPage):** El spec indica que la heurística exacta
   debe verificarse contra URLs reales (§12 Tarea de verificación). Se implementó
   con los 4 patrones conocidos documentados en el spec: `berichte`, `/reports`, `t=13`,
   `type=13`. Adicionalmente se añadió el patrón `report` como cobertura ampliada.
   Desviación trivial, reversible y documentada. El comportamiento defensivo del
   selector de contenedor (con 4 candidatos antes del fallback a `document.body.innerText`)
   cubre el EC-11 del spec sin cambios estructurales.

2. **Candidatos de contenedor adicionales:** Además de `#reportContent` y el fallback
   a `document.body.innerText`, se añaden `#report`, `.report-body` y `.reportContainer`
   como candidatos intermedios. Esto es más defensivo que el spec mínimo (que solo menciona
   `#reportContent` como candidato). No cambia ningún comportamiento observable.

3. **Soporte SPA con MutationObserver:** El spec indica en §13 Riesgo-2 que si Travian
   usa SPA habría que añadir un MutationObserver. Se implementó directamente como medida
   preventiva. El observer es inocuo si Travian no usa SPA (nunca se dispara).

4. **Iconos generados programáticamente:** Los iconos son PNG RGBA generados con Python
   stdlib (sin dependencias externas como Pillow). Son PNG válidos que Chrome acepta.
   Diseño: cuadrado azul (#2c5282) con letra "T" blanca. El spec no especificaba el
   diseño gráfico de los iconos, solo los tamaños (16, 48, 128).

### Desviación adicional — Bugfix 2026-06-01 (extracción de iconos)

5. **extractTextWithImageAlts (causa raíz del 422 en T4.6):** La extracción anterior
   usaba `.innerText` directamente, que ignora los `<img>`. En Travian T4.6 los nombres
   de tropas y animales son iconos `<img alt="Rat">`. Sin los nombres, el parser del
   backend devuelve 422. La función `extractReportText()` se reescribió usando
   `extractTextWithImageAlts()`: clonar el nodo → sustituir cada `<img>` por un
   TextNode con su `alt`/`title` → insertar el clon renderizado fuera de pantalla
   (position:absolute, no display:none) → leer `innerText` → eliminar el clon.
   Reproduce el comportamiento de Ctrl+A/Ctrl+C sin permisos extra ni tocar el
   portapapeles del usuario (Enfoque A del briefing de bugfix).

### Criterios pendientes de verificación manual

- CA-01, CA-02: requieren navegar a Travian real para confirmar que la heurística
  de `isReportPage()` distingue correctamente páginas de reporte vs. otras páginas.
- CA-03 a CA-06: requieren el backend arrancado para probar los flujos 201/409/422/red caída.
  **Con el bugfix de extracción de iconos, CA-03 (201 en reporte real de oasis) debería
  pasar ahora donde antes devolvía 422.**
- CA-11: verificar en DevTools que el botón/toast no altera estilos globales de Travian.
- CA-14: verificar en DevTools → pestaña "Service Worker" que el fetch aparece allí,
  no en la pestaña Network de la página de Travian.
- CA-15: verificar con backend en IP de Raspberry Pi real (192.168.x.x).
- Tarea de verificación del spec §12: inspeccionar DOM del reporte para confirmar/refinar
  el selector del contenedor. Actualizar `extractReportText()` si se encuentra un
  selector más preciso.

