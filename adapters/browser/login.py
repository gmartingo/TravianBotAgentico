"""
Adaptador de login para Travian.
Abre Chrome con el perfil de la cuenta/mundo, navega al servidor, rellena
el formulario y verifica la URL de éxito.
"""
import logging
import os

import zendriver as zd

from adapters.browser.driver import (
    create_browser,
    human_click,
    human_delay,
    human_type,
    _kill_orphan_chrome,
)
from core.entities.account import Account
from core.entities.world import World

logger = logging.getLogger(__name__)


async def login(account: Account, world: World) -> tuple[bool, zd.Browser | None]:
    """
    Abre una sesión autenticada en Travian para la cuenta y mundo indicados.

    Retorna (True, browser) si el login fue exitoso.
    Retorna (False, None) si las credenciales son incorrectas o si ocurre
    cualquier excepción, cerrando el browser para no dejar procesos huérfanos.

    Selectores usados (estructurales, no dependen del idioma de Travian):
      - input[name='name']     — campo de usuario
      - input[name='password'] — campo de contraseña
      - [type='submit']        — botón de envío
    """
    profile_dir = os.path.abspath(f"profiles/account_{account.id}_world_{world.id}")
    _kill_orphan_chrome(profile_dir)
    browser: zd.Browser | None = None
    try:
        browser = await create_browser(profile_dir=profile_dir)
        page = await browser.get(world.server)
        await human_delay(1000, 2000)

        username_field = await page.find("input[name='name']")
        await human_delay()
        await human_type(username_field, account.username)

        password_field = await page.find("input[name='password']")
        await human_delay()
        await human_type(password_field, account.password)

        await human_delay()
        submit_button = await page.find("[type='submit']")
        await human_delay(200, 500)  # pausa visual antes del click, como haría un humano
        await human_click(submit_button, page)
        await human_delay(3000, 5000)

        success = "dorf" in page.url or "village" in page.url
        if success:
            return True, browser

        logger.warning(
            "Login fallido para %s en %s — URL: %s",
            account.username, world.server, page.url
        )
        await browser.stop()
        return False, None

    except Exception:
        logger.exception(
            "Excepción durante el login de %s en %s",
            account.username, world.server
        )
        if browser is not None:
            try:
                await browser.stop()
            except Exception:
                pass
        return False, None
