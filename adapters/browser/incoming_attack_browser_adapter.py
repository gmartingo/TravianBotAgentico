"""
Adaptador de browser para el radar de ataques entrantes — Componentes B, C y D.

IncomingAttackBrowserAdapter gestiona toda la navegación del radar:

  Componente B — get_dorf1_html:
    Navega a dorf1.php y devuelve el HTML para parsear ataques con timer.

  Componente C — navigate_to_village_dorf1 + click_rally_point_link:
    Navega a la aldea atacada (preferentemente click en sidebar, fallback URL directa)
    y hace click humano en el rally point para obtener el HTML de tropas.

  Componente D — click_origin_village_link + get_active_tab:
    Hace click humano en el href de la aldea atacante para obtener el diálogo #tileDetails.

DEUDA ANTI-DETECCIÓN (RT-08, RN-18):
  get_dorf1_html y el fallback de navigate_to_village_dorf1 navegan por URL directa
  (browser.get). Esta es deuda explícita vinculada a stats-overview-direct-url-debt.
  Cuando se implemente el sistema de rutas in-game, migrar a navegación con clicks humanos.
  NO copiar este patrón para nuevas features.

REGLAS ANTI-DETECCIÓN:
  - Todo click sobre Travian DEBE usar human_click(element, tab) — OBLIGATORIO.
  - PROHIBIDO tab.evaluate("...click()") — click sintético detectable.
  - navigate_to_village_dorf1 intenta click en sidebar ANTES de URL directa (RN-24).
  - click_rally_point_link espera table.troop_details.inAttack (RT-14).
  - click_origin_village_link espera div#tileDetails (RN-29).

Ver spec docs/specs/radar-ataques-entrantes.md §9.3, §9.10, §11 anti-detección.
Actualizado en radar-ataques-entrantes v4 (2026-06-07): Componentes C y D desbloqueados.
"""
from __future__ import annotations

import logging
import re
from typing import Callable

from adapters.browser.driver import human_delay
from adapters.browser.url_utils import build_url
from core.exceptions import IncomingAttackPageError, SessionNotActiveError

logger = logging.getLogger(__name__)

# Timeout para esperar que las páginas carguen
_PAGE_TIMEOUT: int = 30

# Selector que indica que dorf1.php cargó completamente
_DORF1_LOADED_SELECTOR = "#content"

# Selector del rally point en el bloque de movimientos de dorf1
_RALLY_POINT_SELECTOR = "a[href*='gid=16'][href*='tt=1']"

# Selectores de espera para C y D (más específicos que #content — RT-14, RN-29)
_RALLY_POINT_TABLE_SELECTOR = "table.troop_details.inAttack"
_TILE_DETAILS_SELECTOR = "div#tileDetails"

# JS para localizar el bounding rect del link del sidebar de una aldea (RN-24)
# Devuelve {left, top, width, height} o null si no se encuentra.
_JS_FIND_SIDEBAR_LINK = """
(function(did) {{
    var span = document.querySelector('span.name[data-did="' + did + '"]');
    if (!span) return null;
    var a = span.closest('a') || (span.parentElement && span.parentElement.closest('a'));
    if (!a) return null;
    var rect = a.getBoundingClientRect();
    return {{left: rect.left, top: rect.top, width: rect.width, height: rect.height}};
}})('{village_game_id}')
"""


class IncomingAttackBrowserAdapter:
    """
    Adaptador de browser para el radar de ataques entrantes.

    Parámetros inyectados:
      get_browser:       Callable[[int], zd.Browser | None]  — dado world_id
      get_world_server:  Callable[[int], str]                 — dado world_id

    Patrón de inyección idéntico al de LiveOverviewAdapter (RT-07).
    """

    def __init__(
        self,
        get_browser: Callable,
        get_world_server: Callable,
    ) -> None:
        self._get_browser      = get_browser
        self._get_world_server = get_world_server

    # -----------------------------------------------------------------------
    # Componente B — dorf1.php con timer
    # -----------------------------------------------------------------------

    async def get_dorf1_html(self, world_id: int) -> str:
        """
        Navega a dorf1.php y devuelve el HTML.

        SIN caché (dorf1 cambia en tiempo real — RN-04). Lectura PUNTUAL, no en polling.
        Reutiliza el patrón de LiveOverviewAdapter:
          browser.get(url) + human_delay(500, 900) + wait DOM.

        NOTA DE DEUDA (RT-08 / RN-18): el uso de browser.get directo es deuda
        vinculada a stats-overview-direct-url-debt. El patrón correcto sería
        navegar a dorf1 via clicks desde la página actual. Cuando se implemente
        el sistema de rutas in-game, migrar a navegación con clicks humanos.
        NO copiar este patrón para nuevas features.

        Lanza:
          SessionNotActiveError — si no hay browser activo para ese world_id.
          IncomingAttackPageError — si la página no carga en el timeout.
        """
        browser = self._get_browser(world_id)
        if browser is None:
            raise SessionNotActiveError()

        server = self._get_world_server(world_id)
        url = build_url(server, "dorf1.php")

        try:
            tab = await browser.get(url)
            await human_delay(500, 900)
            await tab.wait_for(_DORF1_LOADED_SELECTOR, timeout=_PAGE_TIMEOUT)
            return await tab.get_content()
        except (SessionNotActiveError, IncomingAttackPageError):
            raise
        except Exception as exc:
            raise IncomingAttackPageError(
                f"Error al cargar dorf1.php para world_id={world_id}: {exc}"
            ) from exc

    # -----------------------------------------------------------------------
    # Componente C — Navegación a la aldea atacada + click rally point
    # -----------------------------------------------------------------------

    async def navigate_to_village_dorf1(
        self, world_id: int, village_game_id: int
    ) -> object:
        """
        Navega al dorf1 de la aldea con village_game_id. Devuelve el tab activo.

        Estrategia preferida (RN-24): click humano en el <a> padre de
        span.name[data-did=N] del sidebar (ZERO petición HTTP directa).
        Fallback: browser.get(dorf1.php?newdid=N) con WARNING de deuda RT-08.

        tab: zd.Tab — se devuelve ya posicionado en dorf1 de la aldea correcta.

        Lanza:
          SessionNotActiveError — si no hay browser activo.
          IncomingAttackPageError — si la navegación falla.
        """
        from adapters.browser.driver import human_click_at_rect  # noqa: PLC0415

        browser = self._get_browser(world_id)
        if browser is None:
            raise SessionNotActiveError()

        tab = browser.main_tab

        # Verificar si ya estamos en dorf1 de esa aldea (tab.url es sincrónico en zendriver)
        try:
            current_url: str = tab.url
            if "dorf1" in current_url and f"newdid={village_game_id}" in current_url:
                return tab  # ya estamos aquí — no navegar de nuevo
        except Exception:
            pass  # si no se puede leer la URL, continuar con la navegación

        # Estrategia preferida: localizar el link del sidebar via JS (lectura pura, no click)
        js = _JS_FIND_SIDEBAR_LINK.format(village_game_id=village_game_id)
        rect = None
        try:
            rect = await tab.evaluate(js)
        except Exception:
            rect = None

        if rect:
            # Click humano en el bounding rect del sidebar (anti-detección RN-24)
            await human_click_at_rect(rect, tab)
            await tab.wait_for(_DORF1_LOADED_SELECTOR, timeout=_PAGE_TIMEOUT)
            await human_delay(500, 900)
            return tab

        # Fallback — URL directa (deuda RT-08 — ya documentada)
        logger.warning(
            "Comp.C: navigate_to_village_dorf1: sidebar link no encontrado "
            "para did=%d — fallback URL directa (RT-08 deuda anti-detección)",
            village_game_id,
        )
        server = self._get_world_server(world_id)
        url = build_url(server, f"dorf1.php?newdid={village_game_id}")
        try:
            tab = await browser.get(url)
            await human_delay(500, 900)
            await tab.wait_for(_DORF1_LOADED_SELECTOR, timeout=_PAGE_TIMEOUT)
            return tab
        except Exception as exc:
            raise IncomingAttackPageError(
                f"Comp.C: error al navegar a dorf1 de la aldea {village_game_id}: {exc}"
            ) from exc

    async def click_rally_point_link(self, tab) -> str:
        """
        Comp. C — DESBLOQUEADO (GAP-02 cerrado v4).

        Localiza a[href*='gid=16'][href*='tt=1'] (selector doble de substring — RN-25,
        G9: el href puede traer parámetros de sesión variables) y hace click humano.

        Espera 'table.troop_details.inAttack' (RT-14 — más específico que #content,
        evita falsos positivos si el rally point está vacío durante la carga).

        tab: zd.Tab activo — OBLIGATORIO (RN-09).
        PROHIBIDO: tab.evaluate('...click()') — click sintético detectable (G2).

        Devuelve: HTML completo de la página del rally point.
        Lanza: IncomingAttackPageError si el enlace no se encuentra o la tabla no carga.
        """
        from adapters.browser.driver import human_click  # noqa: PLC0415

        element = await tab.select(_RALLY_POINT_SELECTOR)
        if element is None:
            raise IncomingAttackPageError(
                f"Comp.C: no se encontró {_RALLY_POINT_SELECTOR!r} en el DOM actual"
            )
        await human_click(element, tab)
        try:
            await tab.wait_for(_RALLY_POINT_TABLE_SELECTOR, timeout=_PAGE_TIMEOUT)
        except Exception as exc:
            # RT-14: si la tabla no carga (ataque ya impactó), tratar como EC-11
            raise IncomingAttackPageError(
                f"Comp.C: tabla {_RALLY_POINT_TABLE_SELECTOR!r} no apareció "
                f"(¿ataque ya impactó?): {exc}"
            ) from exc
        return await tab.get_content()

    async def click_origin_village_link(self, tab, origin_village_href: str) -> str:
        """
        Comp. D — DESBLOQUEADO (GAP-03 cerrado v4).

        Localiza a[href*='d=NNN'] donde NNN es el parámetro d= del origin_village_href
        (RN-29). El elemento debe estar visible en el DOM del rally point (cargado en C).

        Espera 'div#tileDetails' (el diálogo del mapa — más específico que #content).

        tab: zd.Tab activo — OBLIGATORIO (RN-10).
        PROHIBIDO: tab.evaluate('...click()') — click sintético detectable (G2).

        Devuelve: HTML completo de la página (con div#tileDetails).
        Lanza: IncomingAttackPageError si el href es inválido, el elemento no se
               encuentra, o el diálogo no carga.
        """
        from adapters.browser.driver import human_click  # noqa: PLC0415

        m = re.search(r"d=(\d+)", origin_village_href)
        if not m:
            raise IncomingAttackPageError(
                f"Comp.D: origin_village_href sin parámetro d=: {origin_village_href!r}"
            )
        d_value = m.group(1)
        selector = f"a[href*='d={d_value}']"

        element = await tab.select(selector)
        if element is None:
            raise IncomingAttackPageError(
                f"Comp.D: no se encontró {selector!r} en el DOM actual (rally point)"
            )
        await human_click(element, tab)
        try:
            await tab.wait_for(_TILE_DETAILS_SELECTOR, timeout=_PAGE_TIMEOUT)
        except Exception as exc:
            raise IncomingAttackPageError(
                f"Comp.D: {_TILE_DETAILS_SELECTOR!r} no apareció: {exc}"
            ) from exc
        return await tab.get_content()

    def get_active_tab(self, world_id: int) -> object:
        """
        Devuelve el main_tab del browser activo para world_id.

        Usado por el handler de Comp. D para obtener el tab donde está
        cargada la página del rally point (resultado de Comp. C).

        Lanza: SessionNotActiveError si no hay sesión activa.
        """
        browser = self._get_browser(world_id)
        if browser is None:
            raise SessionNotActiveError()
        return browser.main_tab
