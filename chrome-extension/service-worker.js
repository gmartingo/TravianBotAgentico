/**
 * Service Worker — TravianBot Captura de Reportes
 *
 * Recibe mensajes del content script, hace el fetch al backend (evitando CORS
 * porque la petición sale del service worker con host_permissions) y actualiza
 * el badge del icono de la extensión.
 *
 * Arquitectura MV3: el content script NO puede hacer fetch directo al backend
 * porque correría bajo el contexto de la página de Travian y Chrome aplicaría
 * CORS blocking. El service worker tiene host_permissions globales sobre las URLs
 * declaradas en el manifest, por lo que el navegador no aplica CORS.
 */

// ---------------------------------------------------------------------------
// Listener de mensajes desde el content script
// ---------------------------------------------------------------------------

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'saveReport') {
    handleSaveReport(message.text)
      .then(sendResponse)
      .catch(() => sendResponse({ status: 'network_error' }));
    return true; // mantener canal abierto para respuesta asíncrona
  }
});

// ---------------------------------------------------------------------------
// Lógica principal: guardar reporte en el backend
// ---------------------------------------------------------------------------

async function handleSaveReport(rawText) {
  // EC-12: resetear badge al iniciar cada nueva petición
  await chrome.action.setBadgeText({ text: '' });

  // EC-05: validar que el texto no esté vacío antes de llamar al backend
  if (!rawText || rawText.trim() === '') {
    return { status: 'text_empty' };
  }

  // EC-04: validar longitud máxima (coincide con max_length=50_000 de Pydantic)
  if (rawText.length > 50000) {
    await updateBadge('ERR', '#FF4444');
    return { status: 'too_long' };
  }

  // Leer URL del backend desde chrome.storage.sync (RN-08)
  let backendUrl;
  try {
    const config = await chrome.storage.sync.get('backendUrl');
    backendUrl = config.backendUrl || null;
  } catch {
    backendUrl = null;
  }

  // RN-06: URL no configurada o malformada
  if (!backendUrl || !isValidUrl(backendUrl)) {
    await updateBadge('CFG', '#FF4444');
    return { status: 'config_error' };
  }

  // EC-06: timeout de 10 segundos (Raspberry Pi sobre Wi-Fi local)
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 10000);

  try {
    // La petición sale del service worker → sin CORS blocking (CA-14)
    const response = await fetch(`${backendUrl}/attack-reports`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept-Language': 'es'   // RN-07: valor fijo, el parser autodetecta el idioma
      },
      body: JSON.stringify({ raw_text: rawText }),
      signal: controller.signal
    });

    clearTimeout(timeoutId);

    // RN-02: 201 → éxito
    if (response.status === 201) {
      const data = await response.json();
      await updateBadge('OK', '#00C851');
      return {
        status: 'success',
        data: {
          id: data.id,
          attacked_at: data.attacked_at,
          coord_x_dest: data.coord_x_dest,
          coord_y_dest: data.coord_y_dest,
          origin_village_name: data.origin_village_name
        }
      };
    }

    // RN-03: 409 → duplicado
    if (response.status === 409) {
      const data = await response.json();
      await updateBadge('DUP', '#FFB900');
      return { status: 'duplicate', detail: data.detail };
    }

    // RN-04: 422 → texto inválido (parser no lo reconoce)
    if (response.status === 422) {
      let detail = 'Texto no reconocido como reporte válido';
      try {
        const data = await response.json();
        detail = data.detail || detail;
      } catch {
        // respuesta no JSON → usar mensaje por defecto
      }
      await updateBadge('ERR', '#FF4444');
      return { status: 'invalid', detail };
    }

    // Cualquier otro código HTTP inesperado
    await updateBadge('ERR', '#FF4444');
    return { status: 'network_error' };

  } catch (err) {
    clearTimeout(timeoutId);
    // RN-05: red caída, timeout, backend apagado
    await updateBadge('OFF', '#FF4444');
    return { status: 'network_error' };
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Actualiza el badge del icono de la extensión.
 * @param {string} text  - Texto corto del badge (max 4 chars recomendado)
 * @param {string} color - Color hexadecimal del badge
 */
async function updateBadge(text, color) {
  await chrome.action.setBadgeText({ text });
  await chrome.action.setBadgeBackgroundColor({ color });
}

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
