"""
SessionRegistry — implementación de WorldRuntimePort.

Mantiene en memoria un dict {world_id → (Browser, World)} con los browsers
activos del bot. Es un singleton instanciado en el lifespan de la app FastAPI
y almacenado en app.state.world_runtime_port.

Adicionalmente expone get_browser y get_world_server para que LiveOverviewAdapter
pueda inyectarlos como callables. Estos métodos NO forman parte de WorldRuntimePort
(no son abstractos): son la interfaz de integración entre SessionRegistry y
LiveOverviewAdapter, conocida solo en la capa de adapters (main.py).

Restricciones anti-detección (obligatorias — guardian-antideteccion):
  - No loguear account.password, account.username ni world.server en INFO/DEBUG.
    Solo se logua world_id y resultado booleano.
  - logout() solo llama browser.stop(). NUNCA navega URLs de logout de Travian.
  - El timing humano vive exclusivamente en adapters/browser/login.py.
    SessionRegistry no introduce ningún delay propio.
  - get_browser/get_world_server son referencias directas a métodos del registry
    (sin wrappers que registren/transformen/midan tiempos).
"""
from __future__ import annotations

import logging

import zendriver as zd

from adapters.browser import login as login_module
from core.entities.account import Account
from core.entities.world import World
from core.ports.world_runtime_port import WorldRuntimePort

logger = logging.getLogger(__name__)


class SessionRegistry(WorldRuntimePort):
    """
    Implementa WorldRuntimePort. Mantiene en memoria un dict de browsers activos
    keyed por world_id.

    Adicionalmente expone get_browser y get_world_server para que LiveOverviewAdapter
    pueda inyectarlos como callables. Estos métodos NO forman parte de WorldRuntimePort
    (no son abstractos): son la interfaz de integración entre SessionRegistry y
    LiveOverviewAdapter, conocida solo en la capa de adapters (main.py).
    """

    def __init__(self) -> None:
        # dict[world_id, tuple[zd.Browser, World]]
        self._sessions: dict[int, tuple[zd.Browser, World]] = {}
        # Referencia opcional a LiveOverviewAdapter para invalidar caché en login/logout.
        # Se inyecta desde main.py tras construir ambos adaptadores.
        self._live_adapter = None  # tipo: LiveOverviewAdapter | None

    def set_live_adapter(self, adapter) -> None:
        """
        Inyecta la referencia a LiveOverviewAdapter para invalidar caché.
        Llamar desde main.py lifespan después de instanciar ambos objetos.
        Solo aplicable si OVERVIEW_SOURCE == 'live'.
        """
        self._live_adapter = adapter

    # ------------------------------------------------------------------
    # WorldRuntimePort — métodos abstractos implementados
    # ------------------------------------------------------------------

    async def login(self, account: Account, world: World) -> bool:
        """
        Abre una sesión autenticada para account en world.

        Comportamiento ante sesión previa:
          Si ya existe una sesión para world.id, la cierra con browser.stop()
          e invalida la caché de LiveOverviewAdapter antes de abrir la nueva.

        Devuelve True si el login fue exitoso, False en caso contrario.
        En caso de fallo, el browser ya fue cerrado por login_module.login().

        Anti-detección: no loguea credenciales; solo world_id y resultado.
        """
        world_id = world.id

        # Cerrar sesión previa si existe (RN-06, EC-04)
        if world_id in self._sessions:
            old_browser, _ = self._sessions.pop(world_id)
            try:
                await old_browser.stop()
            except Exception:
                logger.warning(
                    "Error cerrando browser previo para world_id=%s", world_id
                )
            self._invalidate_cache(world_id)

        success, browser = await login_module.login(account, world)

        if success and browser is not None:
            self._sessions[world_id] = (browser, world)
            self._invalidate_cache(world_id)  # RN-12: nueva sesión = caché obsoleta
            logger.info("Login exitoso para world_id=%s", world_id)
            return True

        # login fallido: browser ya cerrado por login_module.login()
        logger.info("Login fallido para world_id=%s", world_id)
        return False

    async def logout(self, world_id: int) -> None:
        """
        Cierra la sesión activa para world_id.
        Idempotente: no lanza excepción si no hay sesión activa (RN-08, EC-05).

        Anti-detección: solo llama browser.stop(). NO navega URLs de logout de Travian.
        """
        if world_id not in self._sessions:
            return  # idempotente

        browser, _ = self._sessions.pop(world_id)
        try:
            await browser.stop()
        except Exception:
            logger.warning(
                "Error cerrando browser en logout para world_id=%s", world_id
            )
        self._invalidate_cache(world_id)
        logger.info("Logout completado para world_id=%s", world_id)

    def is_active(self, world_id: int) -> bool:
        """Devuelve True si hay una sesión activa para world_id."""
        return world_id in self._sessions

    # ------------------------------------------------------------------
    # Métodos adicionales para LiveOverviewAdapter (NO en WorldRuntimePort)
    # ------------------------------------------------------------------

    def get_browser(self, world_id: int) -> zd.Browser | None:
        """
        Devuelve el zd.Browser activo para world_id, o None si no hay sesión.
        Se pasa como callable a LiveOverviewAdapter:
            get_browser=session_registry.get_browser
        """
        entry = self._sessions.get(world_id)
        return entry[0] if entry is not None else None

    def get_world_server(self, world_id: int) -> str:
        """
        Devuelve la URL base del servidor Travian para world_id, o "" si no hay sesión.
        Se pasa como callable a LiveOverviewAdapter:
            get_world_server=session_registry.get_world_server
        """
        entry = self._sessions.get(world_id)
        return entry[1].server if entry is not None else ""

    # ------------------------------------------------------------------
    # Helper interno
    # ------------------------------------------------------------------

    def _invalidate_cache(self, world_id: int) -> None:
        """
        Invalida la caché de LiveOverviewAdapter para world_id si está inyectado.
        No-op si no hay live_adapter configurado (modo fixture o tests).
        """
        if self._live_adapter is not None:
            self._live_adapter.invalidate_cache(world_id)
