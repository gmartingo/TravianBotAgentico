"""
Puerto (contrato) para la capa de automatización del navegador.
El core solo conoce esta interfaz; nunca importa zendriver directamente.
"""
from abc import ABC, abstractmethod


class BrowserPort(ABC):
    """Interfaz que debe implementar cualquier adaptador de navegador."""

    @abstractmethod
    async def start(self) -> None:
        """Inicia el navegador."""

    @abstractmethod
    async def stop(self) -> None:
        """Cierra el navegador y libera recursos."""

    @abstractmethod
    async def navigate(self, url: str) -> None:
        """Navega a la URL indicada."""

    @abstractmethod
    async def find_element(self, selector: str) -> object:
        """Localiza un elemento por selector CSS."""

    @abstractmethod
    async def type_text(self, selector: str, text: str) -> None:
        """Escribe texto en un campo con delays humanos."""

    @abstractmethod
    async def click(self, selector: str) -> None:
        """Hace clic en un elemento con delay humano."""
