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

from adapters.browser.driver import human_click_at_rect, human_delay
from adapters.browser.farm_lists import (
    ensure_farm_list_loaded,
    _js_is_expanded,
    _js_get_expand_rect,
)
from core.entities.farm_list_send_result import FarmListSendResult
from core.exceptions import FarmListSendError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JS expressions (IIFE) para envío y lectura de estado
# ---------------------------------------------------------------------------

# Localiza el header por data-list y devuelve el bounding rect de button.startFarmList.
# El JS NO hace click (RN-HC02): solo localiza el botón, Python hace el click vía CDP.
# El id es un entero → interpolación segura (no hay riesgo de inyección JS).
_JS_GET_START_BUTTON_RECT = """
(() => {{
    const dragEl = document.querySelector('[data-list="{farm_list_id}"]');
    if (!dragEl) return null;
    const header = dragEl.closest('.farmListHeader');
    if (!header) return null;
    const btn = header.querySelector('button.startFarmList');
    if (!btn) return null;
    const r = btn.getBoundingClientRect();
    return {{ x: r.left, y: r.top, width: r.width, height: r.height, _found: true }};
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

    # Obtener rect del botón Start via JS (el JS solo localiza, Python hace el click — RN-HC02)
    js_rect = _JS_GET_START_BUTTON_RECT.format(farm_list_id=int(farm_list_id))
    start_rect = await page.evaluate(js_rect)

    if start_rect is None:
        # El JS devuelve null cuando no puede localizar el botón: distinguimos el motivo
        # intentando evaluar las condiciones previas en orden. Si no, error genérico.
        check_el = await page.evaluate(
            f"!!document.querySelector('[data-list=\"{int(farm_list_id)}\"]')"
        )
        if not check_el:
            reason = "no se encontró el elemento [data-list] en el DOM"
        else:
            check_hdr = await page.evaluate(
                f"!!document.querySelector('[data-list=\"{int(farm_list_id)}\"]')"
                f"?.closest('.farmListHeader')"
            )
            if not check_hdr:
                reason = "se encontró el data-list pero no el .farmListHeader padre"
            else:
                reason = "no se encontró button.startFarmList — ¿todas las vacas desactivadas?"
        raise FarmListSendError(farm_list_id, reason)

    await human_click_at_rect(start_rect, page)

    # Asegurarse de que la lista esté expandida para leer .farmListStatus
    # (en ProcessFarmListUseCase ya está expandida; en SendFarmListUseCase puede no estarlo)
    is_expanded = await page.evaluate(_js_is_expanded(farm_list_id))
    if not is_expanded:
        rect = await page.evaluate(_js_get_expand_rect(farm_list_id))
        if rect:
            await human_click_at_rect(rect, page)
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
