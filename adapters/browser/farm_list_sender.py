"""
Envío de farm lists vía JS evaluate() (IIFE).

Anti-detección (spec sección 11):
  - El click sobre `button.startFarmList` se hace con JS btn.click(), no con
    movimiento de ratón. El bot C# de producción usó este enfoque sin levantar
    alertas anti-bot; se mantiene aquí por consistencia.
  - zendriver.evaluate() NO acepta argumentos para la función JS (a diferencia de
    Playwright). Los IDs se interpolan directamente en el expression y se usan
    IIFEs para que el código se ejecute de verdad.
  - human_delay(1500, 2000) tras el click para que el AJAX de Travian actualice
    el farmListStatus antes de leerlo (EC-11).
"""
from __future__ import annotations

import logging

import zendriver as zd

from adapters.browser.driver import human_delay
from adapters.browser.farm_lists import (
    ensure_farm_list_loaded,
    _js_is_expanded,
    _js_click_expand,
)
from core.entities.farm_list_send_result import FarmListSendResult
from core.exceptions import FarmListSendError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JS expressions (IIFE) para envío y lectura de estado
# ---------------------------------------------------------------------------

# Localiza el header por data-list y hace click en button.startFarmList vía JS.
# El id es un entero → interpolación segura (no hay riesgo de inyección JS).
_JS_START_FARM_LIST = """
(() => {{
    const dragEl = document.querySelector('[data-list="{farm_list_id}"]');
    if (!dragEl) return 'not_found';
    const header = dragEl.closest('.farmListHeader');
    if (!header) return 'no_header';
    const btn = header.querySelector('button.startFarmList');
    if (!btn) return 'no_button';
    btn.click();
    return 'ok';
}})()
"""

# Leído tras el click (AJAX de Travian actualiza el DOM en ~1 s).
# El estado real está en el ratio del span "X/Y being raided" (RN-12):
#   current == active → todas las activas enviadas → success
#   0 < current < active → tropas insuficientes para algunas → partial
#   current == 0         → sin tropas → error
# El span puede contener caracteres Unicode invisibles (bidi marks) que se
# eliminan con replace(/[^0-9/]/g, '') antes de parsear.
#
# NOTA: [data-list] es el drag-handle del header — .farmListStatus NO es hijo
# suyo sino primo dentro de .farmListWrapper. Hay que subir al wrapper.
_JS_READ_STATUS = """
(() => {{
    const el = document.querySelector('[data-list="{farm_list_id}"]');
    const wrapper = el?.closest('.farmListWrapper');
    if (!wrapper) return {{ current: 0, total: 0, active: 0 }};
    const container = wrapper.querySelector('.farmListStatus');
    if (!container) return {{ current: 0, total: 0, active: 0 }};
    const txt = container.querySelector('span')?.textContent || '';
    const nums = txt.replace(/[^0-9/]/g, '').split('/');
    const current = parseInt(nums[0] || '0', 10);
    const total   = parseInt(nums[1] || '0', 10);
    // Slots activos = filas sin clase 'disabled' (requiere lista expandida).
    const active = wrapper.querySelectorAll('tr.slot:not(.disabled)').length;
    return {{ current, total, active }};
}})()
"""


# ---------------------------------------------------------------------------
# send_farm_list
# ---------------------------------------------------------------------------


async def send_farm_list(
    browser: zd.Browser, server_url: str, farm_list_id: int
) -> FarmListSendResult:
    """
    Envía los ataques de una lista de vacas pulsando el botón Start y lee el
    resultado que Travian muestra en .farmListStatus.

    El botón Start vive en .farmListHeader, presente aunque la lista esté
    colapsada → se usa expand=False para no expandir innecesariamente (spec 11).
    Si el botón no está disponible → FarmListSendError (EC-04).

    Lógica de estado del envío (RN-12):
      current >= active → success
      0 < current < active → partial
      current == 0 → error
      active == 0 → unknown (todas las vacas desactivadas, EC-10)
    """
    page = browser.main_tab

    # Asegurar que la lista está en el DOM (sin expandir — el header ya basta para enviar)
    loaded = await ensure_farm_list_loaded(page, server_url, farm_list_id, expand=False)
    if not loaded:
        raise FarmListSendError(
            farm_list_id, "farm list not found in DOM after navigation"
        )

    # Click JS en el botón Start (IIFE — zendriver no acepta argumentos externos)
    js_click = _JS_START_FARM_LIST.format(farm_list_id=int(farm_list_id))
    result = await page.evaluate(js_click)

    if result != "ok":
        reason_map = {
            "not_found": "no se encontró el elemento [data-list] en el DOM",
            "no_header": "se encontró el data-list pero no el .farmListHeader padre",
            "no_button": "no se encontró button.startFarmList — ¿todas las vacas desactivadas?",
        }
        reason = reason_map.get(result, f"resultado inesperado del DOM: {result}")
        raise FarmListSendError(farm_list_id, reason)

    # Asegurarse de que la lista esté expandida para leer .farmListStatus
    # (en ProcessFarmListUseCase ya está expandida; en SendFarmListUseCase puede no estarlo)
    is_expanded = await page.evaluate(_js_is_expanded(farm_list_id))
    if not is_expanded:
        await page.evaluate(_js_click_expand(farm_list_id))
        await human_delay(400, 600)

    # Esperar a que el AJAX de Travian actualice farmListStatus (EC-11)
    await human_delay(1500, 2000)

    js_status = _JS_READ_STATUS.format(farm_list_id=int(farm_list_id))
    status_data: dict = await page.evaluate(js_status)

    current = status_data.get("current", 0)
    total   = status_data.get("total", 0)
    active  = status_data.get("active", 0)

    # Comparar current contra active (slots activos), no contra total (RN-12).
    # total incluye vacas desactivadas; current == active es éxito completo.
    # Si active no se pudo leer, caer en total como fallback.
    compare_to = active if active > 0 else total
    if compare_to > 0:
        if current >= compare_to:
            status = "success"
        elif current > 0:
            status = "partial"
        else:
            status = "error"
    else:
        status = "unknown"

    send_result = FarmListSendResult(
        farm_list_id=farm_list_id,
        status=status,
        being_raided_current=current,
        being_raided_total=active if active > 0 else total,
    )
    logger.info(
        "Farm list %d: ataques enviados — estado=%s raideando=%d/%d",
        farm_list_id,
        send_result.status,
        send_result.being_raided_current,
        send_result.being_raided_total,
    )
    return send_result
