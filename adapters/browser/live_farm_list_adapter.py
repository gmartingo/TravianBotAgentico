"""
Implementación viva de FarmListBrowserPort: navega Travian con Chrome autenticado.

El adaptador se instancia por mundo: `world_id` se fija en el constructor
(igual que WorldAgent, que también es uno por mundo). Esto es consistente con
el contrato del puerto, cuyos métodos no reciben `world_id` — el adaptador
ya sabe qué mundo gestiona.

Sigue el mismo patrón de inyección de callables que LiveOverviewAdapter:
  - get_browser:      Callable[[int], zd.Browser | None]   — dado world_id
  - get_world_server: Callable[[int], str]                  — dado world_id

Cuando no haya sesión activa (get_browser devuelve None), lanza SessionNotActiveError.

set_callables() permite cablear SessionRegistry después de construir el adaptador
(igual que LiveOverviewAdapter), evitando dependencias circulares en el lifespan.
"""
from __future__ import annotations

import logging
from typing import Callable

from adapters.browser.farm_list_sender import send_farm_list
from adapters.browser.farm_lists import (
    activate_slot_in_travian,
    deactivate_slot_in_travian,
    read_farm_list,
    read_farm_lists,
)
from core.entities.farm_list import FarmList
from core.entities.farm_list_send_result import FarmListSendResult
from core.exceptions import SessionNotActiveError
from core.ports.farm_list_browser_port import FarmListBrowserPort

logger = logging.getLogger(__name__)


class LiveFarmListAdapter(FarmListBrowserPort):
    """
    Implementación viva del FarmListBrowserPort.

    Se instancia una vez por mundo (world_id fijo). El WorldAgent lo recibe
    inyectado; los use cases llaman los métodos del puerto sin pasar world_id
    porque el adaptador ya lo conoce.

    Parámetros:
      world_id:         ID del mundo que gestiona este adaptador.
      get_browser:      Callable[[int], zd.Browser | None]
        Función que dado world_id devuelve el zd.Browser activo, o None si no hay
        sesión. Cuando exista SessionRegistry, sustituir por
        session_registry.get_browser.
      get_world_server: Callable[[int], str]
        Función que dado world_id devuelve la URL base del servidor Travian
        (ej: "https://ts20.x2.america.travian.com/").
    """

    def __init__(
        self,
        world_id: int,
        get_browser: Callable,
        get_world_server: Callable,
    ) -> None:
        self._world_id = world_id
        self._get_browser = get_browser
        self._get_world_server = get_world_server

    def set_callables(self, get_browser: Callable, get_world_server: Callable) -> None:
        """
        Permite sustituir los callables get_browser y get_world_server post-construcción.

        Se usa en main.py lifespan para cablear SessionRegistry con LiveFarmListAdapter
        después de que ambos objetos han sido construidos (evita dependencia circular
        en los constructores).
        """
        self._get_browser = get_browser
        self._get_world_server = get_world_server

    def _resolve(self):
        """Resuelve browser y server_url, lanzando SessionNotActiveError si no hay sesión."""
        browser = self._get_browser(self._world_id)
        if browser is None:
            raise SessionNotActiveError()
        server_url = self._get_world_server(self._world_id)
        return browser, server_url

    async def read_farm_lists(self) -> list[FarmList]:
        """
        Navega a la plaza de reuniones y lee todas las farm lists del DOM.

        Lanza:
          SessionNotActiveError — si no hay sesión activa.
          FarmListPageError     — si no se encuentran listas (Gold Club no activo).
        """
        browser, server_url = self._resolve()
        return await read_farm_lists(browser, server_url)

    async def read_farm_list(self, farm_list_id: int) -> FarmList:
        """
        Lee el estado actual de una sola farm list del DOM.

        Lanza:
          SessionNotActiveError — si no hay sesión activa.
          FarmListPageError     — si la lista no aparece en el DOM.
        """
        browser, server_url = self._resolve()
        return await read_farm_list(browser, server_url, farm_list_id)

    async def send_farm_list(self, farm_list_id: int) -> FarmListSendResult:
        """
        Envía los ataques de una lista pulsando el botón Start vía JS.

        Lanza:
          SessionNotActiveError — si no hay sesión activa.
          FarmListSendError     — si el botón no está disponible en el DOM.
        """
        browser, server_url = self._resolve()
        return await send_farm_list(browser, server_url, farm_list_id)

    async def activate_slot_in_travian(
        self, slot_id: int, farm_list_id: int
    ) -> None:
        """
        Activa un slot en Travian vía el menú contextual.

        Lanza:
          SessionNotActiveError — si no hay sesión activa.
          FarmListSendError     — si el slot no aparece en el DOM o el menú falla.
        """
        browser, server_url = self._resolve()
        await activate_slot_in_travian(browser, server_url, farm_list_id, slot_id)

    async def deactivate_slot_in_travian(
        self, slot_id: int, farm_list_id: int
    ) -> None:
        """
        Desactiva un slot en Travian vía el menú contextual.

        Lanza:
          SessionNotActiveError — si no hay sesión activa.
          FarmListSendError     — si el slot no aparece en el DOM o el menú falla.
        """
        browser, server_url = self._resolve()
        await deactivate_slot_in_travian(browser, server_url, farm_list_id, slot_id)
