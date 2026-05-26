"""
Implementación viva de OverviewHtmlSourcePort: navega Travian con Chrome autenticado.

Incluye:
  - Caché in-memory con TTL configurable (clave: world_id x page).
  - Double-checked locking via asyncio.Lock por clave para evitar navegaciones
    duplicadas cuando dos coroutines piden la misma página simultáneamente.
  - Inyección del browser como callable para desacoplar del SessionRegistry
    (que todavía no existe).

Mientras no exista SessionRegistry, instanciar con:
    adapter = LiveOverviewAdapter(
        get_browser=lambda wid: None,
        get_world_server=lambda wid: "",
    )
El adaptador lanzará SessionNotActiveError de forma controlada en cada petición.

URLs de cada OverviewPage (relativas a {world_server}/):
  OVERVIEW              → village/statistics/overview
  RESOURCES             → village/statistics/resources
  RESOURCES_PRODUCTION  → village/statistics/resources/production
  RESOURCES_CAPACITY    → village/statistics/resources/capacity
  CULTURE_POINTS        → village/statistics/culturepoints
  TROOPS_OWN            → village/statistics/troops/own
  TROOPS_SUPPORT        → village/statistics/troops/support
  TROOPS_SMITHY         → village/statistics/troops/smithy
  TROOPS_HOSPITAL       → village/statistics/troops/hospital
  TROOPS_TRAINING       → village/statistics/troops/training
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from adapters.browser.driver import human_delay
from core.exceptions import OverviewPageNotLoadedError, SessionNotActiveError
from core.ports.overview_html_source_port import OverviewHtmlSourcePort, OverviewPage

# ---------------------------------------------------------------------------
# Constantes configurables por variable de entorno
# ---------------------------------------------------------------------------

# TTL de caché — default 60 s
OVERVIEW_CACHE_TTL_SECONDS: int = int(
    os.environ.get("OVERVIEW_CACHE_TTL_SECONDS", "60")
)

# Timeout para esperar que la página cargue — default 30 s
OVERVIEW_PAGE_TIMEOUT: int = int(
    os.environ.get("OVERVIEW_PAGE_TIMEOUT_SECONDS", "30")
)

# Selector estable que indica que la página de statistics cargó completamente.
# #content está presente en todas las pestañas de /village/statistics.
OVERVIEW_LOADED_SELECTOR = "#content"

# Mapeo OverviewPage → ruta relativa al world_server (sin barra inicial)
_PAGE_PATHS: dict[OverviewPage, str] = {
    OverviewPage.OVERVIEW:             "village/statistics/overview",
    OverviewPage.RESOURCES:            "village/statistics/resources",
    OverviewPage.RESOURCES_PRODUCTION: "village/statistics/resources/production",
    OverviewPage.RESOURCES_CAPACITY:   "village/statistics/resources/capacity",
    OverviewPage.CULTURE_POINTS:       "village/statistics/culturepoints",
    OverviewPage.TROOPS_OWN:           "village/statistics/troops/own",
    OverviewPage.TROOPS_SUPPORT:       "village/statistics/troops/support",
    OverviewPage.TROOPS_SMITHY:        "village/statistics/troops/smithy",
    OverviewPage.TROOPS_HOSPITAL:      "village/statistics/troops/hospital",
    OverviewPage.TROOPS_TRAINING:      "village/statistics/troops/training",
}


# ---------------------------------------------------------------------------
# Estructura interna de la caché (privado al adaptador)
# ---------------------------------------------------------------------------


@dataclass
class CacheEntry:
    """Entrada de caché: HTML de la página + timestamp de cuándo fue cacheado."""
    html:      str
    cached_at: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_url(world_server: str, page: OverviewPage) -> str:
    """
    Construye la URL completa de la pestaña solicitada.

    world_server debe terminar en '/' o no tenerla — se normaliza aquí.
    """
    base = world_server.rstrip("/")
    return f"{base}/{_PAGE_PATHS[page]}"


# ---------------------------------------------------------------------------
# Adaptador
# ---------------------------------------------------------------------------


class LiveOverviewAdapter(OverviewHtmlSourcePort):
    """
    Implementación viva del port: navega Travian con Chrome autenticado.

    El browser (zd.Browser) se obtiene a través de callables inyectados:
        get_browser:       Callable[[int], zd.Browser | None]  — dado world_id
        get_world_server:  Callable[[int], str]                 — dado world_id

    Mientras no exista SessionRegistry, ambos callables pueden ser lambdas que
    devuelven None / "": el adaptador lanzará SessionNotActiveError de forma
    controlada. Esto permite registrar el adaptador en el lifespan hoy sin
    bloquear el desarrollo de los cuatro bloques.

    Caché:
      - Clave: (world_id, page)
      - Valor: CacheEntry(html, cached_at)
      - TTL: OVERVIEW_CACHE_TTL_SECONDS (configurable por variable de entorno)
      - Invalidación: invalidate_cache(world_id) borra todas las entradas del mundo
      - Concurrencia: un asyncio.Lock por clave evita navegaciones duplicadas
        cuando dos coroutines piden la misma página simultáneamente (double-checked
        locking, patrón estándar en asyncio).
    """

    def __init__(
        self,
        get_browser: Callable,
        get_world_server: Callable,
    ) -> None:
        """
        Parámetros:
          get_browser:      Callable[[int], zd.Browser | None]
            Función que dado world_id devuelve el zd.Browser activo, o None si
            no hay sesión. Cuando exista SessionRegistry, sustituir por
            session_registry.get_browser.

          get_world_server: Callable[[int], str]
            Función que dado world_id devuelve la URL base del servidor Travian
            (ej: "https://ts20.x2.america.travian.com/"). Cuando exista
            SessionRegistry, sustituir por session_registry.get_world_server.
        """
        self._get_browser = get_browser
        self._get_world_server = get_world_server
        self._cache: dict[tuple, CacheEntry] = {}
        self._locks: dict[tuple, asyncio.Lock] = {}

    async def get_page_html(
        self,
        world_id: int,
        page: OverviewPage,
    ) -> str:
        """
        Devuelve el HTML de la pestaña solicitada.

        Caché hit → devuelve HTML cacheado sin navegar.
        Caché miss → adquiere lock, re-verifica (double-checked), navega, cachea.

        Lanza:
          SessionNotActiveError      — si get_browser devuelve None.
          OverviewPageNotLoadedError — si la página no carga o devuelve HTML vacío.
        """
        cache_key = (world_id, page)

        # --- Caché hit (sin lock — lectura rápida) ---
        entry = self._cache.get(cache_key)
        if entry is not None:
            age = (datetime.now(timezone.utc) - entry.cached_at).total_seconds()
            if age < OVERVIEW_CACHE_TTL_SECONDS:
                return entry.html

        # --- Caché miss — adquirir lock por clave ---
        if cache_key not in self._locks:
            self._locks[cache_key] = asyncio.Lock()
        async with self._locks[cache_key]:
            # Double-check: otro coroutine pudo haber llenado la caché mientras
            # esperábamos el lock.
            entry = self._cache.get(cache_key)
            if entry is not None:
                age = (datetime.now(timezone.utc) - entry.cached_at).total_seconds()
                if age < OVERVIEW_CACHE_TTL_SECONDS:
                    return entry.html

            html = await self._navigate_and_get(world_id, page)
            self._cache[cache_key] = CacheEntry(
                html=html,
                cached_at=datetime.now(timezone.utc),
            )
            return html

    async def _navigate_and_get(
        self,
        world_id: int,
        page: OverviewPage,
    ) -> str:
        """
        Navega a la pestaña solicitada y devuelve el HTML.

        Lanza SessionNotActiveError si get_browser devuelve None.
        Lanza OverviewPageNotLoadedError si #content no aparece en el timeout
        o el HTML devuelto está vacío.
        """
        browser = self._get_browser(world_id)
        if browser is None:
            raise SessionNotActiveError()

        world_server = self._get_world_server(world_id)
        url = _build_url(world_server, page)

        tab = await browser.get(url)

        # Delay humano post-navegación — anti-detección obligatorio (CLAUDE.md)
        # Simula el tiempo de render perception de un humano real.
        await human_delay(500, 900)

        # Esperar a que la página cargue (#content presente en todas las pestañas
        # de /village/statistics).
        try:
            await tab.wait_for(OVERVIEW_LOADED_SELECTOR, timeout=OVERVIEW_PAGE_TIMEOUT)
        except Exception:
            raise OverviewPageNotLoadedError(world_id, page)

        html = await tab.get_content()

        # Verificar que el HTML no está vacío (EC-04)
        if not html or not html.strip():
            raise OverviewPageNotLoadedError(world_id, page)

        return html

    def invalidate_cache(self, world_id: int) -> None:
        """
        Invalida todas las entradas de caché para world_id.

        Seguro de llamar aunque no haya entradas (idempotente).
        Se llama desde LoginUseCase (o quien gestione el login) cuando re-autentica.
        """
        keys_to_delete = [k for k in self._cache if k[0] == world_id]
        for k in keys_to_delete:
            del self._cache[k]
            self._locks.pop(k, None)

    def set_callables(self, get_browser, get_world_server) -> None:
        """
        Permite sustituir los callables get_browser y get_world_server post-construcción.

        Se usa en main.py lifespan para cablear SessionRegistry con LiveOverviewAdapter
        después de que ambos objetos han sido construidos (evita dependencia circular
        en los constructores).

        El constructor sigue aceptando los callables en __init__ (retrocompatibilidad
        con tests existentes que instancian con lambdas).
        """
        self._get_browser = get_browser
        self._get_world_server = get_world_server
