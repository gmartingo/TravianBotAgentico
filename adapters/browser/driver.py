"""
Adaptador de navegador basado en zendriver.
Implementa BrowserPort con todas las capas de anti-detección obligatorias.
"""
import os
import platform
import random
import asyncio
from typing import Optional

import zendriver as zd

from core.ports.browser_port import BrowserPort


def _get_user_agent() -> str:
    """Devuelve un User-Agent coherente con el OS real del host."""
    system = platform.system()
    if system == "Windows":
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    if system == "Darwin":
        return (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    return (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )


class ZendriverAdapter(BrowserPort):
    """
    Implementación de BrowserPort usando zendriver (CDP directo, sin ChromeDriver).

    Capas de anti-detección activas:
    - Sin ChromeDriver -> navigator.webdriver=false
    - --disable-blink-features=AutomationControlled
    - Perfil Chrome persistente por cuenta (cookies/historial reales)
    - User-Agent dinámico por OS
    - Sin modo headless
    - Delays humanos: 500-900 ms entre acciones
    - Escritura humana: 80-220 ms por carácter
    - no_sandbox=True (requerido en VirtualBox)
    """

    def __init__(self, profile_dir: str = "profiles/default") -> None:
        self._profile_dir = os.path.abspath(profile_dir)
        self._browser: Optional[zd.Browser] = None
        self._tab = None

    async def start(self) -> None:
        config = zd.Config(
            user_data_dir=self._profile_dir,
            browser_args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-infobars",
                f"--user-agent={_get_user_agent()}",
            ],
            disable_webrtc=True,
            disable_webgl=True,
            no_sandbox=True,
        )
        self._browser = await zd.start(config)
        self._tab = await self._browser.get("about:blank")

    async def stop(self) -> None:
        if self._browser:
            await self._browser.stop()
            self._browser = None
            self._tab = None

    async def navigate(self, url: str) -> None:
        await self._tab.get(url)
        await self._human_delay()

    async def find_element(self, selector: str) -> object:
        return await self._tab.find(selector)

    async def type_text(self, selector: str, text: str) -> None:
        """Escribe carácter a carácter con delay de 80-220 ms (simula typing humano)."""
        element = await self.find_element(selector)
        for char in text:
            await element.send_keys(char)
            await asyncio.sleep(random.uniform(0.08, 0.22))

    async def click(self, selector: str) -> None:
        element = await self.find_element(selector)
        await element.click()
        await self._human_delay()

    async def _human_delay(self) -> None:
        """Pausa de 500-900 ms para simular tiempo de reacción humano."""
        await asyncio.sleep(random.uniform(0.5, 0.9))
