/**
 * Content Script — TravianBot Captura de Reportes
 *
 * Se inyecta en todas las páginas de Travian (declarado en manifest.json).
 * Responsabilidades:
 *   1. Detectar si la página actual es un detalle de reporte (heurística de URL)
 *   2. Inyectar el botón flotante discreto en la página (sin interferir con el DOM)
 *   3. Al hacer clic: extraer el texto del reporte y enviarlo al service worker
 *   4. Mostrar el toast con el resultado recibido del service worker
 *
 * REGLA DE PROYECTO: Nunca usar selectores por texto visible — Travian es multi-idioma.
 * Los selectores usados son siempre estructurales (id, clase CSS, patrón de URL).
 *
 * NOTA: El fetch al backend lo hace el service worker, NO este content script.
 * Esto evita el CORS blocking que aplicaría Chrome si el fetch saliera del contexto
 * de la página de Travian (ver service-worker.js y spec §8 — Solución CORS).
 */

// ---------------------------------------------------------------------------
// Heurística de detección de página de reporte
// ---------------------------------------------------------------------------

/**
 * Determina si la página actual es un detalle de reporte de ataque en Travian.
 *
 * TAREA DE VERIFICACIÓN (spec §12): Esta heurística debe verificarse contra URLs
 * reales de Travian. Los patrones conocidos son:
 *   - Versión internacional: URL contiene "berichte" (alemán, histórico)
 *   - Versión moderna: URL contiene "/reports/" o parámetro "t=13"
 *
 * Si Travian usa una URL diferente en el dominio del usuario, actualizar aquí.
 * La regla del proyecto es usar selectores estructurales (parámetros de URL,
 * rutas fijas), nunca texto visible.
 *
 * @returns {boolean}
 */
function isReportPage() {
  const url = window.location.href;
  const pathname = window.location.pathname;
  const search = window.location.search;

  // Patrón 1: ruta contiene "berichte" (reportes en versión clásica, multi-idioma
  //            porque la ruta del servidor no depende del idioma de la UI)
  if (pathname.includes('berichte')) return true;

  // Patrón 2: ruta contiene "/reports" (versión moderna de Travian)
  if (pathname.includes('/reports')) return true;

  // Patrón 3: parámetro t=13 (tipo de reporte de combate en la versión antigua)
  if (search.includes('t=13')) return true;

  // Patrón 4: ruta type=13 o report en URL (algunos servidores)
  if (url.includes('type=13') || url.includes('report')) return true;

  return false;
}

// ---------------------------------------------------------------------------
// Extracción del texto del reporte
// ---------------------------------------------------------------------------

/**
 * Convierte un nodo del DOM en texto plano incluyendo el atributo alt/title
 * de los elementos <img>, que innerText normalmente ignora.
 *
 * PROBLEMA RAÍZ (verificado empíricamente): en Travian T4.6 los nombres de
 * tropas y animales se muestran como <img alt="Phalanx">, <img alt="Rat">, etc.
 * document.body.innerText (y cualquier .innerText) omite esas imágenes, dejando
 * solo los números en las filas de la tabla. El parser del backend identifica
 * tropas/animales por su NOMBRE → al faltar los nombres devuelve 422.
 *
 * SOLUCIÓN — Enfoque A (sin permisos extra, sin tocar el portapapeles del usuario):
 *   1. Clonar el nodo raíz
 *   2. En el clon, reemplazar cada <img> por un nodo de texto con su alt (o title)
 *   3. Insertar el clon en el DOM fuera de pantalla PERO RENDERIZADO
 *      (position:absolute; left:-99999px — NO display:none, porque innerText
 *       requiere layout para calcular los saltos de línea y tabulaciones de tablas)
 *   4. Leer innerText del clon → ahora incluye los nombres y mantiene \t/\n de tablas
 *   5. Eliminar el clon del DOM
 *
 * Esto reproduce fielmente el comportamiento de Ctrl+A / Ctrl+C del navegador,
 * que sí incluye el texto alt de los iconos y produce cabeceras tabuladas:
 *   "Phalanx\tSwordsman\t...\nRat\tSpider\t..."
 *
 * @param {Element} node - Nodo raíz del que extraer el texto
 * @returns {string} Texto con nombres de tropas/animales + tabulaciones de tablas
 */
function extractTextWithImageAlts(node) {
  // Clonar el subárbol completo (deep clone)
  const clone = node.cloneNode(true);

  // Reemplazar cada <img> del clon por un nodo de texto con su alt o title
  const imgs = clone.querySelectorAll('img');
  for (const img of imgs) {
    const label = img.getAttribute('alt') || img.getAttribute('title') || '';
    if (label) {
      img.replaceWith(document.createTextNode(label));
    }
    // Si no hay alt ni title, dejar el img (innerText lo ignorará, que es el
    // comportamiento correcto para iconos decorativos sin texto semántico)
  }

  // Insertar el clon fuera de pantalla pero PLENAMENTE RENDERIZADO. innerText
  // requiere layout para producir las tabulaciones (\t) entre celdas de tabla y
  // los saltos (\n) entre filas. OJO: ni `display:none` NI `visibility:hidden`
  // sirven — ambos hacen que innerText degrade a un volcado tipo textContent que
  // concatena los nombres SIN separadores (PhalanxSwordsman…RatSpider…) y el
  // parser del backend no puede dividir la cabecera → 422. Por eso solo se saca
  // del viewport con position:absolute, manteniéndolo visible y con layout.
  clone.style.cssText = [
    'position: absolute',
    'left: -99999px',
    'top: 0',
    'pointer-events: none'
  ].join('; ');

  document.body.appendChild(clone);

  // Leer el texto ya con los nombres de imágenes sustituidos
  const text = clone.innerText;

  // Limpiar — eliminar el clon del DOM
  clone.remove();

  return text;
}

/**
 * Extrae el texto del reporte del DOM incluyendo los nombres de tropas/animales
 * que aparecen como iconos <img alt="...">.
 *
 * Estrategia defensiva (spec §5, EC-11):
 *   1. Intentar el contenedor específico #reportContent (si existe en Travian)
 *   2. Intentar el contenedor #report (variante conocida)
 *   3. Intentar .report-body / .reportContainer (otras variantes)
 *   4. Fallback robusto: document.body
 *
 * En todos los casos se aplica extractTextWithImageAlts() para que los nombres
 * de tropas y animales queden incluidos en el texto extraído.
 *
 * NUNCA se usa texto visible como selector (Travian es multi-idioma).
 *
 * @returns {string} Texto extraído del DOM con nombres de tropas/animales incluidos
 */
function extractReportText() {
  // Intentar contenedor específico primero (más limpio, evita menú/navbar)
  const candidates = [
    document.querySelector('#reportContent'),
    document.querySelector('#report'),
    document.querySelector('.report-body'),
    document.querySelector('.reportContainer')
  ];

  for (const container of candidates) {
    if (container) {
      const text = extractTextWithImageAlts(container);
      if (text && text.trim().length > 0) {
        return text;
      }
    }
  }

  // Fallback robusto: todo el cuerpo de la página
  return extractTextWithImageAlts(document.body);
}

// ---------------------------------------------------------------------------
// Toast de feedback
// ---------------------------------------------------------------------------

/**
 * Muestra un toast de feedback en la página.
 * El toast se posiciona sobre el botón flotante (bottom: 70px).
 *
 * @param {string} message - Texto a mostrar
 * @param {'success'|'warning'|'error'} type - Tipo de toast (determina el color)
 */
function showToast(message, type) {
  // Eliminar toast anterior si existe
  const existing = document.getElementById('travianbot-toast');
  if (existing) existing.remove();

  const colors = {
    success: '#00C851',
    warning: '#FFB900',
    error:   '#FF4444'
  };

  const toast = document.createElement('div');
  toast.id = 'travianbot-toast';
  toast.textContent = message;

  // Estilos inline para evitar interferencia con CSS de Travian (RN-10)
  toast.style.cssText = [
    'position: fixed',
    'bottom: 72px',
    'right: 20px',
    'z-index: 2147483647',        // máximo z-index posible
    `background: ${colors[type] || colors.error}`,
    'color: #fff',
    'padding: 12px 18px',
    'border-radius: 6px',
    'font-size: 14px',
    'font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    'font-weight: 500',
    'line-height: 1.4',
    'box-shadow: 0 4px 12px rgba(0,0,0,0.35)',
    'max-width: 320px',
    'word-wrap: break-word',
    'pointer-events: none'        // no bloquea clics en la página
  ].join('; ');

  document.body.appendChild(toast);

  // Duración según tipo: warning y success = 3s, error = 5s (spec §5 flujos)
  const duration = type === 'error' ? 5000 : 3000;
  setTimeout(() => {
    if (toast.parentNode) toast.remove();
  }, duration);
}

// ---------------------------------------------------------------------------
// Manejo de la respuesta del service worker
// ---------------------------------------------------------------------------

/**
 * Procesa la respuesta recibida del service worker y actualiza el botón y el toast.
 * @param {object} response - Respuesta del service worker (SaveReportResponse)
 * @param {HTMLButtonElement} btn - Botón flotante
 */
function handleResponse(response, btn) {
  // Rehabilitar el botón (EC-02)
  btn.disabled = false;
  btn.textContent = 'Guardar reporte';

  if (!response) {
    showToast('Error de comunicación con la extensión', 'error');
    return;
  }

  switch (response.status) {
    case 'success':
      showToast(`Reporte guardado (ID: ${response.data.id})`, 'success');
      break;

    case 'duplicate':
      showToast('Este reporte ya estaba guardado', 'warning');
      break;

    case 'invalid':
      showToast('Texto no reconocido como reporte válido', 'error');
      break;

    case 'network_error':
      showToast('No se pudo contactar con el backend (\xbfest\xe1 encendida la Raspberry Pi?)', 'error');
      break;

    case 'config_error':
      showToast('URL del backend no configurada. Ve a opciones de la extensi\xf3n.', 'error');
      break;

    case 'text_empty':
      showToast('No se encontr\xf3 texto en la p\xe1gina', 'error');
      break;

    case 'too_long':
      showToast('El reporte es demasiado largo para ser procesado', 'error');
      break;

    default:
      showToast('Error desconocido al procesar el reporte', 'error');
  }
}

// ---------------------------------------------------------------------------
// Manejador del clic en el botón
// ---------------------------------------------------------------------------

async function handleCapture() {
  const btn = document.getElementById('travianbot-capture-btn');
  if (!btn || btn.disabled) return;

  // EC-02: deshabilitar el botón inmediatamente para evitar doble envío
  btn.disabled = true;
  btn.textContent = 'Guardando…';

  // Extraer el texto del reporte del DOM
  const rawText = extractReportText();

  // EC-05: texto vacío → toast inmediato sin llamar al service worker
  if (!rawText || rawText.trim() === '') {
    showToast('No se encontr\xf3 texto en la p\xe1gina', 'error');
    btn.disabled = false;
    btn.textContent = 'Guardar reporte';
    return;
  }

  // Enviar al service worker (IPC — la petición HTTP la hace el service worker)
  let response;
  try {
    response = await chrome.runtime.sendMessage({
      action: 'saveReport',
      text: rawText
    });
  } catch (err) {
    // Puede ocurrir si el service worker está inactivo durante el envío
    response = { status: 'network_error' };
  }

  handleResponse(response, btn);
}

// ---------------------------------------------------------------------------
// Inyección del botón flotante
// ---------------------------------------------------------------------------

/**
 * Inyecta el botón flotante en la página si es una página de reporte.
 * Evita duplicados comprobando si ya existe el botón (EC-07, SPA sin recarga).
 */
function injectButton() {
  if (!isReportPage()) return;

  // Evitar duplicados
  if (document.getElementById('travianbot-capture-btn')) return;

  const btn = document.createElement('button');
  btn.id = 'travianbot-capture-btn';
  btn.textContent = 'Guardar reporte';

  // Estilos inline para no interferir con CSS de Travian (RN-10)
  btn.style.cssText = [
    'position: fixed',
    'bottom: 20px',
    'right: 20px',
    'z-index: 2147483646',        // justo por debajo del toast
    'padding: 10px 16px',
    'background: #2c5282',
    'color: #fff',
    'border: none',
    'border-radius: 6px',
    'cursor: pointer',
    'font-size: 14px',
    'font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    'font-weight: 600',
    'box-shadow: 0 2px 8px rgba(0,0,0,0.3)',
    'transition: background 0.15s ease'
  ].join('; ');

  btn.addEventListener('mouseenter', () => {
    if (!btn.disabled) btn.style.background = '#2a4a7f';
  });
  btn.addEventListener('mouseleave', () => {
    if (!btn.disabled) btn.style.background = '#2c5282';
  });

  btn.addEventListener('click', handleCapture);
  document.body.appendChild(btn);
}

// ---------------------------------------------------------------------------
// Soporte para SPA (spec §9, §13 Riesgo-2)
// ---------------------------------------------------------------------------

/**
 * Travian puede usar navegación SPA (sin recarga completa de página).
 * Se observan cambios de URL con popstate y pushState interceptado para
 * re-evaluar si hay que inyectar el botón al navegar entre reportes.
 *
 * TAREA DE VERIFICACIÓN (spec §14 paso 12): confirmar si Travian usa SPA.
 * Si no lo usa, este observer es inocuo (nunca se dispara).
 */
let lastHref = window.location.href;

function checkUrlChange() {
  if (window.location.href !== lastHref) {
    lastHref = window.location.href;
    // Eliminar botón anterior si no aplica en la nueva página
    const existing = document.getElementById('travianbot-capture-btn');
    if (existing) existing.remove();
    // Re-evaluar e inyectar si corresponde
    injectButton();
  }
}

// Observar cambios del DOM que indiquen navegación SPA
const _spaObserver = new MutationObserver(checkUrlChange);
_spaObserver.observe(document.body, { childList: true, subtree: false });

// Escuchar también popstate (navegación con botón atrás/adelante)
window.addEventListener('popstate', checkUrlChange);

// ---------------------------------------------------------------------------
// Inicialización
// ---------------------------------------------------------------------------

injectButton();
