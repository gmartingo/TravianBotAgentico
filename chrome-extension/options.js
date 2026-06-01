/**
 * Options Page — TravianBot Captura de Reportes
 *
 * Gestiona la configuración de la URL del backend.
 * La URL se persiste en chrome.storage.sync (disponible en todos los Chrome
 * del usuario si está logueado con la misma cuenta Google).
 *
 * Validaciones (spec §10):
 *   - URL válida que empiece por http:// o https://
 *   - Sin trailing slash (EC-09: se normaliza automáticamente)
 *   - Sin trailing slash antes de guardar
 *
 * Default: http://localhost:8000 (RN-08)
 */

const DEFAULT_BACKEND_URL = 'http://localhost:8000';

// ---------------------------------------------------------------------------
// Validación de URL
// ---------------------------------------------------------------------------

/**
 * Valida que la URL sea válida y comience por http:// o https://.
 * @param {string} url
 * @returns {boolean}
 */
function isValidUrl(url) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Inicialización y lógica de guardado
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', async () => {
  const input   = document.getElementById('backend-url');
  const saveBtn = document.getElementById('save-btn');
  const status  = document.getElementById('status');

  // Cargar valor actual desde storage (o default si no existe)
  try {
    const config = await chrome.storage.sync.get('backendUrl');
    input.value = config.backendUrl || DEFAULT_BACKEND_URL;
  } catch {
    input.value = DEFAULT_BACKEND_URL;
  }

  // Limpiar mensaje de estado al editar
  input.addEventListener('input', () => {
    status.textContent = '';
    status.className = '';
  });

  // Guardar al hacer clic en el botón
  saveBtn.addEventListener('click', async () => {
    let url = input.value.trim();

    // EC-09: normalizar quitando trailing slash
    while (url.endsWith('/')) {
      url = url.slice(0, -1);
    }

    // Actualizar el input con la URL normalizada
    input.value = url;

    // Validar formato (spec §10)
    if (!url) {
      status.textContent = 'La URL no puede estar vac\xeda.';
      status.className = 'err';
      return;
    }

    if (!isValidUrl(url)) {
      status.textContent = 'URL inv\xe1lida. Usa http://… o https://…';
      status.className = 'err';
      return;
    }

    // Guardar en chrome.storage.sync
    try {
      await chrome.storage.sync.set({ backendUrl: url });
      status.textContent = 'URL guardada correctamente.';
      status.className = 'ok';
    } catch {
      status.textContent = 'Error al guardar. Inténtalo de nuevo.';
      status.className = 'err';
    }

    // Limpiar el mensaje después de 3 segundos
    setTimeout(() => {
      status.textContent = '';
      status.className = '';
    }, 3000);
  });

  // Guardar también con Enter en el campo de texto
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') saveBtn.click();
  });
});
