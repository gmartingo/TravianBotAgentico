"""
Puerto de browser para farm lists (FarmListBrowserPort).

Contrato abstracto que separa el core del adaptador de browser concreto.
La implementación viva es LiveFarmListAdapter (adapters/browser/live_farm_list_adapter.py).

NO extiende BrowserPort: convención explícita del proyecto de no extender los puertos
genéricos (ver CLAUDE.md y spec farm-lists sección 13).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.entities.farm_list import FarmList
from core.entities.farm_list_send_result import FarmListSendResult


class FarmListBrowserPort(ABC):
    """
    Puerto de browser para operaciones de farm lists.

    Cada método opera sobre el browser del mundo correspondiente
    (el world_id se resuelve en la capa de adaptador a través del callable
    get_browser inyectado desde SessionRegistry).
    """

    @abstractmethod
    async def read_farm_lists(self) -> list[FarmList]:
        """
        Navega a la plaza de reuniones (gid=16, tt=99) y lee todas las
        farm lists del DOM, expandiendo cada lista para capturar los slots.

        Devuelve lista de FarmList con village_name relleno (transitorio)
        para que ReadFarmListsUseCase pueda hacer matching con aldeas en BD.

        Lanza:
          FarmListPageError — si la página no carga o no hay listas en el DOM.
        """

    @abstractmethod
    async def read_farm_list(self, farm_list_id: int) -> FarmList:
        """
        Lee una sola farm list (estado actual de sus slots) navegando
        si es necesario a la plaza de reuniones.

        Lanza:
          FarmListPageError — si la lista no aparece en el DOM tras reintentar.
        """

    @abstractmethod
    async def send_farm_list(self, farm_list_id: int) -> FarmListSendResult:
        """
        Pulsa el botón Start de la farm list indicada (vía JS IIFE, sin
        movimiento de ratón — RN-11) y devuelve el resultado leído del DOM.

        Lanza:
          FarmListSendError — si el botón Start no se encuentra o el DOM
                              devuelve un estado inesperado.
          FarmListPageError — si la lista no se puede cargar en la plaza.
        """

    @abstractmethod
    async def activate_slot_in_travian(self, slot_id: int, farm_list_id: int) -> None:
        """
        Activa el slot (marca su checkbox) en la interfaz de Travian via JS.
        Usado por el ciclo de sondas: activa momentáneamente antes del send.
        """

    @abstractmethod
    async def deactivate_slot_in_travian(self, slot_id: int, farm_list_id: int) -> None:
        """
        Desactiva el slot (desmarca su checkbox) en la interfaz de Travian via JS.
        Usado cuando se detectan pérdidas y cuando se completa el envío de una sonda.
        """
