"""
Lector DOM de farm lists de la plaza de reuniones (Rallypoint, gid=16, tt=99).

Funciones públicas:
  read_farm_lists(browser, server_url)  → list[FarmList]   (lectura completa)
  read_farm_list(browser, server_url, farm_list_id) → FarmList  (una sola lista)
  ensure_farm_list_loaded(page, server_url, farm_list_id, *, expand)  → bool

Funciones de slots (activate / deactivate) via menú contextual:
  activate_slot_in_travian(browser, server_url, farm_list_id, slot_id)
  deactivate_slot_in_travian(browser, server_url, farm_list_id, slot_id)

Anti-detección:
  - Todos los waits usan human_delay (nunca asyncio.sleep fijo).
  - Selectores siempre estructurales (data-list, input[data-slot-id], etc.),
    nunca texto visible — Travian es multiidioma.
  - Navegación inteligente: no recarga la página si la lista ya está en el DOM.
"""
from __future__ import annotations

import asyncio
import logging
import re

import zendriver as zd

from adapters.browser.driver import human_delay
from adapters.browser.url_utils import build_url
from core.entities.farm_list import FarmList, FarmSlot
from core.exceptions import FarmListPageError, FarmListResponseError, FarmListSendError

logger = logging.getLogger(__name__)

_FARM_LIST_PATH = "/build.php?gid=16&tt=99"


# ---------------------------------------------------------------------------
# Parsers DOM → entidades de dominio
# ---------------------------------------------------------------------------


def _parse_slot(raw: dict, farm_list_id: int) -> FarmSlot:
    return FarmSlot(
        id=raw["id"],
        farm_list_id=farm_list_id,
        target_name=raw.get("targetName", ""),
        x=raw.get("x", 0),
        y=raw.get("y", 0),
        population=raw.get("population", 0),
        troops=raw.get("troops", {}),
        is_active=raw.get("isActive", True),
        disabled_by_bot=False,
        last_raid_state=raw.get("lastRaidState", ""),
        last_raid_time=raw.get("lastRaidTime", ""),
        last_raid_report_id=raw.get("lastRaidReportId", ""),
        last_raid_bounty=raw.get("lastRaidBounty", 0),
        average_raid_bounty=raw.get("averageRaidBounty", 0),
        distance=raw.get("distance", 0),
    )


def _parse_farm_list(raw: dict, index: int) -> FarmList:
    if not raw.get("id") or not raw.get("name"):
        raise FarmListResponseError(index, "faltan campos 'id' o 'name' en el DOM")
    slots = [_parse_slot(s, raw["id"]) for s in raw.get("slots", [])]
    return FarmList(
        id=raw["id"],
        name=raw["name"],
        owner_village_id=0,   # se rellena en sync con el village_id real de BD
        village_name=raw.get("villageName", ""),
        village_data_id=raw.get("villageDid", 0),
        slots=slots,
    )


# ---------------------------------------------------------------------------
# Navegación a la pestaña de farm lists (anti-detección: skip si ya estamos)
# ---------------------------------------------------------------------------


async def _navigate_to_farm_list(page: zd.Tab, server_url: str) -> None:
    """
    Navega hasta la pestaña de farm lists de la plaza de reuniones,
    saltando los pasos que ya estén completados según la URL actual.
    Un humano no volvería a entrar en una página donde ya está.

    Flujo:
      1. Si ya estamos en tt=99 → nada.
      2. Si estamos en gid=16 (otra pestaña) → solo cambiar tab.
      3. Resto → dorf2.php → click gid=16 → click tt=99
           (fallback directo si no se encuentra el selector de la plaza).
    """
    current_url: str = await page.evaluate("location.href")

    # Ya estamos en la pestaña de farm list
    if "tt=99" in current_url:
        return

    # Estamos en la plaza pero en otra pestaña
    if "gid=16" in current_url:
        tab_href = await page.evaluate(
            "document.querySelector(\"a[href*='tt=99']\")?.getAttribute('href')"
        )
        if tab_href:
            tab_url = build_url(server_url, tab_href) if tab_href.startswith("/") else tab_href
            await page.get(tab_url)
            await human_delay(1000, 1800)
        return

    # Navegación completa desde dorf2
    await page.get(build_url(server_url, "dorf2.php"))
    await human_delay(1000, 1800)

    plaza_href = await page.evaluate(
        "document.querySelector(\"a[href*='gid=16']\")?.getAttribute('href')"
    )
    if plaza_href:
        plaza_url = build_url(server_url, plaza_href) if plaza_href.startswith("/") else plaza_href
        await page.get(plaza_url)
        await human_delay(1000, 1800)
    else:
        # Fallback directo si no encontramos el enlace a la plaza
        await page.get(build_url(server_url, _FARM_LIST_PATH))
        await human_delay(1000, 1800)
        return

    tab_href = await page.evaluate(
        "document.querySelector(\"a[href*='tt=99']\")?.getAttribute('href')"
    )
    if tab_href:
        tab_url = build_url(server_url, tab_href) if tab_href.startswith("/") else tab_href
        await page.get(tab_url)
        await human_delay(1000, 1800)


# ---------------------------------------------------------------------------
# JS expressions (IIFE) para lectura y manipulación del DOM
# ---------------------------------------------------------------------------

# Devuelve [{id, villageName, villageDid}] para cada lista encontrada en el DOM.
# villageDid es el data-did del nav sidebar (= data_id en la BD de aldeas).
# Si el nav no tiene la aldea por nombre, villageDid queda 0.
_JS_GET_FARM_LIST_ENTRIES = """
(() => {
    const nameToDidMap = {};
    document.querySelectorAll('span.name[data-did]').forEach(s => {
        const did = parseInt(s.getAttribute('data-did'));
        const name = s.textContent?.trim();
        if (did && name) nameToDidMap[name] = did;
    });
    const wrappers = document.querySelectorAll('.villageWrapper');
    const result = [];
    for (const vw of wrappers) {
        const villageName = vw.querySelector('.villageHeader .villageName')?.textContent?.trim() ?? '';
        const villageDid = nameToDidMap[villageName] ?? 0;
        const els = vw.querySelectorAll('.farmListHeader [data-list]');
        for (const el of els) {
            const id = parseInt(el.getAttribute('data-list'));
            if (!isNaN(id)) result.push({ id, villageName, villageDid });
        }
    }
    return result;
})()
"""


def _js_is_expanded(list_id: int) -> str:
    return f"""
(() => {{
    const el = document.querySelector('[data-list="{list_id}"]');
    const wrapper = el?.closest('.farmListWrapper');
    return wrapper?.classList.contains('expanded') ?? false;
}})()
"""


def _js_click_expand(list_id: int) -> str:
    return f"""
(() => {{
    const el = document.querySelector('[data-list="{list_id}"]');
    const wrapper = el?.closest('.farmListWrapper');
    const btn = wrapper?.querySelector('.farmListHeader a.expandCollapse');
    if (!btn) return false;
    btn.click();
    return true;
}})()
"""


def _js_read_list(list_id: int) -> str:
    return f"""
(() => {{
    const el = document.querySelector('[data-list="{list_id}"]');
    const farmWrapper = el?.closest('.farmListWrapper');
    if (!farmWrapper) return null;

    const villageWrapper = farmWrapper.closest('.villageWrapper');
    const villageName = villageWrapper?.querySelector('.villageHeader .villageName')?.textContent?.trim() ?? '';

    const nameEl = farmWrapper.querySelector('.farmListName .name');
    const name = nameEl?.textContent?.trim() ?? '';

    const slots = Array.from(farmWrapper.querySelectorAll('tr.slot')).map(row => {{
        const input = row.querySelector('input[data-slot-id]');
        const id = parseInt(input?.getAttribute('data-slot-id') ?? '0') || 0;

        const targetLink = row.querySelector('td.target a');
        const targetName = targetLink?.querySelector('span')?.textContent?.trim() ?? '';
        const href = targetLink?.getAttribute('href') ?? '';
        const qmark = href.indexOf('?');
        const params = new URLSearchParams(qmark >= 0 ? href.slice(qmark + 1) : '');
        const x = parseInt(params.get('x') ?? '0') || 0;
        const y = parseInt(params.get('y') ?? '0') || 0;

        const population = parseInt(
            row.querySelector('td.population span')?.textContent?.replace(/[^0-9]/g, '') ?? '0'
        ) || 0;

        const isActive = !row.classList.contains('disabled');

        // Tropas: {{ t2: 2, t4: 1, ... }}
        const troops = {{}};
        row.querySelectorAll('td.troops div span').forEach(span => {{
            const icon = span.querySelector('i');
            const valueEl = span.querySelector('.value');
            if (!icon || !valueEl) return;
            const tClass = Array.from(icon.classList).find(c => /^t\\d+$/.test(c));
            if (tClass) troops[tClass] = parseInt(valueEl.textContent.trim()) || 0;
        }});

        // Último ataque
        const reportLink = row.querySelector('a.lastRaidReport');
        const reportHref = reportLink?.getAttribute('href') ?? '';
        const lastRaidReportId = reportHref.includes('id=') ? reportHref.split('id=')[1] : '';
        const lastRaidState = Array.from(
            reportLink?.querySelector('i.lastRaidState')?.classList ?? []
        ).filter(c => c !== 'lastRaidState').join(' ');
        const lastRaidTime = reportLink?.querySelector('.value')?.textContent?.trim() ?? '';
        const lastRaidBounty = parseInt(
            row.querySelector('.lastRaidBounty .value')?.textContent?.replace(/[^0-9]/g, '') ?? '0'
        ) || 0;
        const averageRaidBounty = parseInt(
            row.querySelector('.averageRaidBounty .value')?.textContent?.replace(/[^0-9]/g, '') ?? '0'
        ) || 0;

        const distText = row.querySelector('td.distance span')?.textContent
            ?? row.querySelector('td.distance')?.textContent ?? '0';
        const distance = parseFloat(distText.trim()) || 0;

        return {{
            id, targetName, x, y, population, isActive, troops,
            lastRaidState, lastRaidTime, lastRaidReportId, lastRaidBounty, averageRaidBounty, distance
        }};
    }}).filter(s => s.id > 0);

    return {{ id: {list_id}, name, villageName, slots }};
}})()
"""

# JS que devuelve los game_ids de todas las aldeas del jugador (para navegar entre aldeas)
_JS_GET_VILLAGE_IDS = """
(() => {
    const spans = document.querySelectorAll('span.name[data-did]');
    const seen = new Set();
    const ids = [];
    for (const s of spans) {
        const id = parseInt(s.getAttribute('data-did'));
        if (id && !seen.has(id)) { seen.add(id); ids.push(id); }
    }
    return ids;
})()
"""


# ---------------------------------------------------------------------------
# JS expressions (IIFE) para activate / deactivate de slots via context menu
# ---------------------------------------------------------------------------


def _js_is_disabled(slot_id: int) -> str:
    """
    Devuelve True si el slot está desactivado, False si activo, null si no existe.
    Una vaca desactivada tiene la clase 'disabled' en su <tr class="slot disabled">.
    """
    return f"""
    (() => {{
        const input = document.querySelector('input[data-slot-id="{int(slot_id)}"]');
        if (!input) return null;
        const row = input.closest('tr.slot');
        if (!row) return null;
        return row.classList.contains('disabled');
    }})()
    """


def _js_open_context_menu(slot_id: int) -> str:
    """
    Pulsa el icono de menú contextual del slot. Travian inserta el menú dentro
    del mismo <td class="openContextMenu"> tras el click.
    Devuelve 'ok' / 'no_row' / 'no_trigger'.
    """
    return f"""
    (() => {{
        const input = document.querySelector('input[data-slot-id="{int(slot_id)}"]');
        if (!input) return 'no_row';
        const row = input.closest('tr.slot');
        if (!row) return 'no_row';
        const trigger = row.querySelector('td.openContextMenu > a');
        if (!trigger) return 'no_trigger';
        trigger.click();
        return 'ok';
    }})()
    """


def _js_click_menu_entry(slot_id: int, entry: str) -> str:
    """
    Pulsa una entrada del menú contextual. `entry` = 'deactivate' | 'activate'.
    Devuelve 'ok' / 'no_row' / 'no_menu' / 'no_entry'.
    """
    return f"""
    (() => {{
        const input = document.querySelector('input[data-slot-id="{int(slot_id)}"]');
        if (!input) return 'no_row';
        const row = input.closest('tr.slot');
        if (!row) return 'no_row';
        const menu = row.querySelector('td.openContextMenu .contextMenu');
        if (!menu) return 'no_menu';
        const btn = menu.querySelector('button.entry.{entry}');
        if (!btn) return 'no_entry';
        btn.click();
        return 'ok';
    }})()
    """


# ---------------------------------------------------------------------------
# ensure_farm_list_loaded
# ---------------------------------------------------------------------------


async def ensure_farm_list_loaded(
    page: zd.Tab, server_url: str, farm_list_id: int, *, expand: bool = True
) -> bool:
    """
    Garantiza que la farm list `farm_list_id` está disponible en la página actual.

    Si Chrome no la tiene cargada (está en dorf1/dorf2/otra página), navega a la
    plaza de reuniones. Si `expand=True`, además despliega la lista — necesario para
    leer o manipular sus slots, ya que las filas `tr.slot` solo están en el DOM
    con la lista expandida.

    No navega si la lista ya está presente → las acciones consecutivas sobre la
    misma lista no recargan la página (anti-detección: evita navegaciones innecesarias).

    Devuelve True si la lista quedó disponible en el DOM.
    """
    present_js = f"!!document.querySelector('[data-list=\"{int(farm_list_id)}\"]')"

    on_page = await page.evaluate(present_js)
    if not on_page:
        await _navigate_to_farm_list(page, server_url)
        for _ in range(20):
            on_page = await page.evaluate(present_js)
            if on_page:
                break
            await asyncio.sleep(0.5)
        if not on_page:
            return False

    if expand:
        is_expanded = await page.evaluate(_js_is_expanded(farm_list_id))
        if not is_expanded:
            await page.evaluate(_js_click_expand(farm_list_id))
            await human_delay(800, 1200)

    return True


# ---------------------------------------------------------------------------
# read_farm_lists — lectura completa de todas las listas del mundo
# ---------------------------------------------------------------------------


async def read_farm_lists(browser: zd.Browser, server_url: str) -> list[FarmList]:
    """
    Navega a la plaza de reuniones, lee todas las farm lists del DOM y las devuelve.

    Lanza:
      FarmListPageError si no se encuentran listas en el DOM (Gold Club no activo
      o el usuario no ha creado listas).
    """
    page = browser.main_tab

    await _navigate_to_farm_list(page, server_url)

    entries: list[dict] = []
    for _ in range(60):
        entries = await page.evaluate(_JS_GET_FARM_LIST_ENTRIES)
        if entries:
            break
        await asyncio.sleep(0.5)

    if not entries:
        raise FarmListPageError(
            "no se encontraron listas (.farmListHeader [data-list]) — "
            "verifica que el Gold Club esté activo y que haya listas de vacas creadas"
        )

    logger.info("Listas de vacas encontradas: %d", len(entries))

    farm_lists: list[FarmList] = []

    for i, entry in enumerate(entries):
        list_id = entry["id"]
        logger.info(
            "Leyendo lista %d/%d (id=%d, aldea='%s')",
            i + 1, len(entries), list_id, entry.get("villageName", ""),
        )

        is_expanded = await page.evaluate(_js_is_expanded(list_id))
        if not is_expanded:
            await page.evaluate(_js_click_expand(list_id))
            await human_delay(800, 1200)

        raw = await page.evaluate(_js_read_list(list_id))

        if not raw:
            logger.warning(
                "Lista %d/%d (id=%d): sin datos en el DOM — se omite",
                i + 1, len(entries), list_id,
            )
            continue

        # villageDid no lo devuelve _js_read_list — lo propagamos desde el entry
        raw["villageDid"] = entry.get("villageDid", 0)

        try:
            fl = _parse_farm_list(raw, index=i)
            farm_lists.append(fl)
            logger.info(
                "Lista '%s' (aldea='%s') leída: %d vacas",
                fl.name, fl.village_name, len(fl.slots),
            )
        except FarmListResponseError as e:
            logger.warning("Lista %d/%d (id=%d): %s", i + 1, len(entries), list_id, e)

        if i < len(entries) - 1:
            await human_delay(400, 700)

    if not farm_lists:
        raise FarmListPageError(
            f"se encontraron {len(entries)} listas pero ninguna devolvió datos del DOM"
        )

    return farm_lists


# ---------------------------------------------------------------------------
# read_farm_list — lectura de una sola lista
# ---------------------------------------------------------------------------


def _parse_current_village_id(url: str) -> int | None:
    m = re.search(r"[?&]newdid=(\d+)", url)
    return int(m.group(1)) if m else None


async def _read_village_game_ids(page: zd.Tab) -> list[int]:
    result = await page.evaluate(_JS_GET_VILLAGE_IDS)
    return result if isinstance(result, list) else []


async def read_farm_list(
    browser: zd.Browser, server_url: str, farm_list_id: int
) -> FarmList:
    """
    Lee una sola farm list (estado actual de sus slots) navegando a la plaza.

    Estrategia de retry EC-12:
      1. Intenta con la aldea actual.
      2. Si no tiene datos, navega a otra aldea y reintenta una vez.
      3. Si falla → FarmListPageError.
    """
    page = browser.main_tab

    if await ensure_farm_list_loaded(page, server_url, farm_list_id, expand=True):
        raw = await page.evaluate(_js_read_list(farm_list_id))
        if raw:
            return _parse_farm_list(raw, index=0)

    # Retry: navegar desde otra aldea para forzar recarga completa
    game_ids = await _read_village_game_ids(page)
    if len(game_ids) < 2:
        raise FarmListPageError(
            f"la lista {farm_list_id} no devolvió datos del DOM"
        )

    current_id = _parse_current_village_id(await page.evaluate("location.href"))
    alternatives = [gid for gid in game_ids if gid != current_id]
    if not alternatives:
        raise FarmListPageError(
            f"la lista {farm_list_id} no devolvió datos del DOM"
        )

    other_game_id = alternatives[0]
    logger.warning(
        "Lista %d: sin datos — reintentando desde aldea game_id=%d",
        farm_list_id, other_game_id,
    )
    await page.get(build_url(server_url, f"dorf2.php?newdid={other_game_id}"))
    await human_delay(1000, 1800)

    if not await ensure_farm_list_loaded(page, server_url, farm_list_id, expand=True):
        raise FarmListPageError(
            f"la lista {farm_list_id} no devolvió datos del DOM "
            f"(reintento desde aldea {other_game_id} también falló)"
        )

    raw = await page.evaluate(_js_read_list(farm_list_id))
    if not raw:
        raise FarmListPageError(
            f"la lista {farm_list_id} no devolvió datos del DOM "
            f"(reintento desde aldea {other_game_id} también falló)"
        )

    return _parse_farm_list(raw, index=0)


# ---------------------------------------------------------------------------
# Activar / desactivar slots via menú contextual
# ---------------------------------------------------------------------------


async def _ensure_slot_visible(
    page: zd.Tab, server_url: str, farm_list_id: int, slot_id: int
) -> bool | None:
    """
    Garantiza que el slot está en el DOM y devuelve si está desactivado.
    Devuelve True (desactivado), False (activo) o None (no encontrado en DOM).
    """
    is_disabled = await page.evaluate(_js_is_disabled(slot_id))
    if is_disabled is not None:
        return is_disabled

    loaded = await ensure_farm_list_loaded(page, server_url, farm_list_id, expand=True)
    if not loaded:
        return None
    return await page.evaluate(_js_is_disabled(slot_id))


async def _toggle_slot(
    browser: zd.Browser,
    server_url: str,
    farm_list_id: int,
    slot_id: int,
    *,
    action: str,
    entry_class: str,
) -> None:
    """
    Activa o desactiva un slot via su menú contextual.

    Pasos:
      1. Asegura que el slot es visible en el DOM.
      2. Si ya está en el estado deseado → idempotente, sale sin hacer nada.
      3. Pulsa el icono del menú contextual.
      4. Pausa humana (400-800 ms).
      5. Pulsa la entrada del menú (activate | deactivate).

    Lanza FarmListSendError si el slot no aparece o el menú no responde.
    (FarmListSendError es la excepción de error de interacción con el browser
    más apropiada disponible en el dominio; `FarmSlotContextMenuError` no está
    en el spec de este proyecto — registrado como desviación mínima.)
    """
    page = browser.main_tab

    is_disabled = await _ensure_slot_visible(page, server_url, farm_list_id, slot_id)
    if is_disabled is None:
        logger.warning("Slot %d no encontrado en el DOM", slot_id)
        raise FarmListSendError(
            farm_list_id,
            f"slot {slot_id} no encontrado en el DOM al intentar '{action}'"
        )

    # Idempotente: si ya está en el estado deseado, nada que hacer
    already_in_target = (is_disabled if action == "deactivate" else not is_disabled)
    if already_in_target:
        logger.info("Slot %d ya está '%s' en Travian, nada que hacer", slot_id, action)
        return

    # Abrir menú contextual
    opened = await page.evaluate(_js_open_context_menu(slot_id))
    if opened != "ok":
        raise FarmListSendError(
            farm_list_id,
            f"no se pudo abrir el context menu del slot {slot_id}: {opened}"
        )

    # Pausa humana: el menú aparece y un humano tarda en llevar el cursor a la entrada
    await human_delay(400, 800)

    # Pulsar la entrada del menú
    clicked = await page.evaluate(_js_click_menu_entry(slot_id, entry_class))
    if clicked != "ok":
        raise FarmListSendError(
            farm_list_id,
            f"no se pudo pulsar '{entry_class}' en el slot {slot_id}: {clicked}"
        )

    await human_delay(500, 900)
    logger.info("Slot %d: '%s' aplicado en Travian", slot_id, action)


async def activate_slot_in_travian(
    browser: zd.Browser, server_url: str, farm_list_id: int, slot_id: int
) -> None:
    """Activa un slot vía su menú contextual en Travian."""
    await _toggle_slot(
        browser, server_url, farm_list_id, slot_id,
        action="activate", entry_class="activate",
    )


async def deactivate_slot_in_travian(
    browser: zd.Browser, server_url: str, farm_list_id: int, slot_id: int
) -> None:
    """Desactiva un slot vía su menú contextual en Travian."""
    await _toggle_slot(
        browser, server_url, farm_list_id, slot_id,
        action="deactivate", entry_class="deactivate",
    )
