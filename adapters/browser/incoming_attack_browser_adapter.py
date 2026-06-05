"""
Adaptador de browser para el radar de ataques entrantes — Componente B.

IncomingAttackBrowserAdapter obtiene el HTML de dorf1.php para que
Dorf1IncomingParser pueda extraer los timers de los ataques entrantes.

DEUDA ANTI-DETECCIÓN (RT-08, RN-18):
  get_dorf1_html navega por URL directa (browser.get) siguiendo el mismo patrón
  que LiveOverviewAdapter. Esta es deuda explícita vinculada a
  stats-overview-direct-url-debt. Cuando se implemente el sistema de rutas in-game,
  migrar a navegación con clicks humanos.
  NO copiar este patrón para nuevas features.

Componentes C y D (BLOQUEADOS — requieren fixtures GAP-02 / GAP-03):
  Los métodos click_rally_point_link y click_origin_village_link están presentes
  como stubs documentados. Cuando los fixtures estén disponibles, completar los
  parsers y habilitar estos métodos. Todo click sobre Travian DEBE usar
  human_click(element, tab) — PROHIBIDO tab.evaluate("...click()").

Ver spec docs/specs/radar-ataques-entrantes.md §9.3, §11 anti-detección.
Añadido en la feature radar-ataques-entrantes (2026-06-05).
"""
from __future__ import annotations

import logging
from typing import Callable

from adapters.browser.driver import human_delay
from adapters.browser.url_utils import build_url
from core.exceptions import IncomingAttackPageError, SessionNotActiveError

logger = logging.getLogger(__name__)

# Timeout para esperar que dorf1 cargue completamente
_DORF1_PAGE_TIMEOUT: int = 30

# Selector que indica que dorf1.php cargó completamente
_DORF1_LOADED_SELECTOR = "#content"


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
            await tab.wait_for(_DORF1_LOADED_SELECTOR, timeout=_DORF1_PAGE_TIMEOUT)
            return await tab.get_content()
        except (SessionNotActiveError, IncomingAttackPageError):
            raise
        except Exception as exc:
            raise IncomingAttackPageError(
                f"Error al cargar dorf1.php para world_id={world_id}: {exc}"
            ) from exc

    async def click_rally_point_link(self, tab, rally_point_href: str) -> str:
        """
        [COMP. C — BLOQUEADO hasta fixture GAP-02]

        Localiza el <a> del rally point por substring 'gid=16' (no igualdad exacta —
        el href puede traer parámetros de sesión variables — RN-G9) y hace click humano.

        tab: zd.Tab activo — OBLIGATORIO (RN-09).
        PROHIBIDO: tab.evaluate('...click()') — click sintético detectable (G2).

        Selector estructural: a[href*='gid=16'] (substring).
        """
        # Import diferido — solo se usa en Comp. C (no disponible aún)
        from adapters.browser.driver import human_click  # noqa: PLC0415
        element = await tab.select("a[href*='gid=16']")
        if element is None:
            raise IncomingAttackPageError(
                "No se encontró el enlace estructural a[href*='gid=16']"
            )
        await human_click(element, tab)
        await tab.wait_for(_DORF1_LOADED_SELECTOR, timeout=_DORF1_PAGE_TIMEOUT)
        return await tab.get_content()

    async def click_origin_village_link(self, tab, origin_village_href: str) -> str:
        """
        [COMP. D — BLOQUEADO hasta fixture GAP-03]

        Localiza el hipervínculo de la aldea atacante por href estructural y hace
        click humano.

        tab: zd.Tab activo — OBLIGATORIO (RN-10).
        PROHIBIDO: tab.evaluate('...click()') — click sintético detectable (G2).
        """
        from adapters.browser.driver import human_click  # noqa: PLC0415
        selector = f"a[href*='{origin_village_href}']"
        element = await tab.select(selector)
        if element is None:
            raise IncomingAttackPageError(
                f"No se encontró el enlace a aldea atacante: {origin_village_href}"
            )
        await human_click(element, tab)
        await tab.wait_for(_DORF1_LOADED_SELECTOR, timeout=_DORF1_PAGE_TIMEOUT)
        return await tab.get_content()
