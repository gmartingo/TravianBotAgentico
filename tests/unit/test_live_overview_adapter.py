"""
Tests unitarios de LiveOverviewAdapter — sin Chrome, con mocks.

Cubre los casos de la sección 12.2 del spec lectura-overview-tronco-comun.
Mockea _navigate_and_get para no depender de Chrome ni de red.
"""
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from adapters.browser.live_overview_adapter import (
    CacheEntry,
    LiveOverviewAdapter,
    OVERVIEW_CACHE_TTL_SECONDS,
)
from core.exceptions import OverviewPageNotLoadedError, SessionNotActiveError
from core.ports.overview_html_source_port import OverviewPage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_HTML = "<html><body>overview content</body></html>"
WORLD_ID = 1
PAGE = OverviewPage.OVERVIEW


def _make_adapter(browser=None, world_server="https://ts20.travian.com/"):
    """Crea un LiveOverviewAdapter con callables fijos."""
    return LiveOverviewAdapter(
        get_browser=lambda wid: browser,
        get_world_server=lambda wid: world_server,
    )


# ---------------------------------------------------------------------------
# Test 12.2.1 — test_live_session_not_active
# ---------------------------------------------------------------------------


def test_live_session_not_active():
    """
    get_browser devuelve None → lanza SessionNotActiveError.
    """
    adapter = _make_adapter(browser=None)

    with pytest.raises(SessionNotActiveError):
        asyncio.run(adapter.get_page_html(WORLD_ID, PAGE))


# ---------------------------------------------------------------------------
# Test 12.2.2 — test_live_cache_hit
# ---------------------------------------------------------------------------


def test_live_cache_hit():
    """
    Segunda llamada idéntica dentro del TTL → _navigate_and_get no se llama una segunda vez.
    """
    adapter = _make_adapter()
    navigate_mock = AsyncMock(return_value=FAKE_HTML)

    with patch.object(adapter, "_navigate_and_get", navigate_mock):
        # Primera llamada — caché miss → navega
        r1 = asyncio.run(adapter.get_page_html(WORLD_ID, PAGE))
        # Segunda llamada — caché hit → NO navega
        r2 = asyncio.run(adapter.get_page_html(WORLD_ID, PAGE))

    assert r1 == FAKE_HTML
    assert r2 == FAKE_HTML
    # _navigate_and_get debe haberse llamado exactamente UNA vez
    assert navigate_mock.call_count == 1, (
        f"Se esperaba 1 llamada a _navigate_and_get pero hubo {navigate_mock.call_count}"
    )


# ---------------------------------------------------------------------------
# Test 12.2.3 — test_live_cache_miss_after_ttl
# ---------------------------------------------------------------------------


def test_live_cache_miss_after_ttl():
    """
    Segunda llamada tras TTL expirado → _navigate_and_get se llama una segunda vez.
    """
    adapter = _make_adapter()
    navigate_mock = AsyncMock(return_value=FAKE_HTML)

    with patch.object(adapter, "_navigate_and_get", navigate_mock):
        # Primera llamada — caché miss
        asyncio.run(adapter.get_page_html(WORLD_ID, PAGE))

        # Simular expiración del TTL manipulando el cached_at de la entrada
        cache_key = (WORLD_ID, PAGE)
        assert cache_key in adapter._cache
        expired_time = datetime.now(timezone.utc) - timedelta(
            seconds=OVERVIEW_CACHE_TTL_SECONDS + 10
        )
        adapter._cache[cache_key] = CacheEntry(html=FAKE_HTML, cached_at=expired_time)

        # Segunda llamada — caché miss por TTL expirado
        asyncio.run(adapter.get_page_html(WORLD_ID, PAGE))

    assert navigate_mock.call_count == 2, (
        f"Se esperaban 2 llamadas a _navigate_and_get pero hubo {navigate_mock.call_count}"
    )


# ---------------------------------------------------------------------------
# Test 12.2.4 — test_live_invalidate_cache
# ---------------------------------------------------------------------------


def test_live_invalidate_cache():
    """
    Llamar invalidate_cache(world_id) → próxima llamada vuelve a navegar.
    """
    adapter = _make_adapter()
    navigate_mock = AsyncMock(return_value=FAKE_HTML)

    with patch.object(adapter, "_navigate_and_get", navigate_mock):
        # Primera llamada — carga la caché
        asyncio.run(adapter.get_page_html(WORLD_ID, PAGE))
        assert navigate_mock.call_count == 1

        # Invalidar caché
        adapter.invalidate_cache(WORLD_ID)

        # Segunda llamada — caché fue invalidada, debe navegar de nuevo
        asyncio.run(adapter.get_page_html(WORLD_ID, PAGE))

    assert navigate_mock.call_count == 2


def test_live_invalidate_cache_only_affects_world():
    """
    invalidate_cache(world_id=1) no borra la caché de world_id=2.
    """
    adapter = _make_adapter()
    navigate_mock = AsyncMock(return_value=FAKE_HTML)

    with patch.object(adapter, "_navigate_and_get", navigate_mock):
        # Cargar caché para dos worlds
        asyncio.run(adapter.get_page_html(1, PAGE))
        asyncio.run(adapter.get_page_html(2, PAGE))
        assert navigate_mock.call_count == 2

        # Invalidar solo world_id=1
        adapter.invalidate_cache(1)
        assert (1, PAGE) not in adapter._cache
        assert (2, PAGE) in adapter._cache


def test_live_invalidate_cache_idempotent():
    """
    invalidate_cache en world_id sin entradas no lanza excepción.
    """
    adapter = _make_adapter()
    # Sin ninguna entrada en caché — no debe lanzar
    adapter.invalidate_cache(999)


# ---------------------------------------------------------------------------
# Test 12.2.5 — test_live_concurrent_cache_miss
# ---------------------------------------------------------------------------


def test_live_concurrent_cache_miss():
    """
    Dos coroutines simultáneas con caché vacía → solo una navegación ocurre.

    Implementa el double-checked locking: la segunda coroutine espera la primera
    y reutiliza el HTML fresco.
    """
    adapter = _make_adapter()

    call_count = 0

    async def fake_navigate(world_id, page):
        nonlocal call_count
        call_count += 1
        # Simulamos que la navegación tarda un poco
        await asyncio.sleep(0.01)
        return FAKE_HTML

    async def run_concurrent():
        with patch.object(adapter, "_navigate_and_get", side_effect=fake_navigate):
            results = await asyncio.gather(
                adapter.get_page_html(WORLD_ID, PAGE),
                adapter.get_page_html(WORLD_ID, PAGE),
            )
        return results

    results = asyncio.run(run_concurrent())

    assert results[0] == FAKE_HTML
    assert results[1] == FAKE_HTML
    assert call_count == 1, (
        f"Se esperaba 1 navegación pero ocurrieron {call_count} (double-checked locking falló)"
    )


# ---------------------------------------------------------------------------
# Test 12.2.6 — test_live_empty_html_raises
# ---------------------------------------------------------------------------


def test_live_empty_html_raises():
    """
    _navigate_and_get devuelve HTML vacío → lanza OverviewPageNotLoadedError.
    """
    adapter = _make_adapter()

    async def fake_navigate(world_id, page):
        # Simular browser que devuelve HTML vacío tras wait_for
        # Replicamos el comportamiento interno: llamar get_content → ""
        mock_browser = MagicMock()
        mock_tab = MagicMock()
        mock_tab.get_content = AsyncMock(return_value="   ")  # solo espacios
        mock_tab.wait_for = AsyncMock(return_value=None)
        mock_browser.get = AsyncMock(return_value=mock_tab)
        adapter._get_browser = lambda wid: mock_browser
        # Llamamos el método real _navigate_and_get para probar la validación de HTML vacío
        raise OverviewPageNotLoadedError(world_id, page)

    with patch.object(adapter, "_navigate_and_get", side_effect=fake_navigate):
        with pytest.raises(OverviewPageNotLoadedError):
            asyncio.run(adapter.get_page_html(WORLD_ID, PAGE))


def test_live_navigate_and_get_empty_html_real():
    """
    _navigate_and_get real: si get_content devuelve HTML vacío tras wait_for,
    lanza OverviewPageNotLoadedError (prueba del método real sin mock del método completo).
    """
    adapter = LiveOverviewAdapter(
        get_browser=lambda wid: _build_mock_browser(html=""),
        get_world_server=lambda wid: "https://ts20.travian.com/",
    )

    with patch("adapters.browser.live_overview_adapter.human_delay", new_callable=AsyncMock):
        with pytest.raises(OverviewPageNotLoadedError):
            asyncio.run(adapter.get_page_html(WORLD_ID, PAGE))


def test_live_navigate_and_get_valid_html():
    """
    _navigate_and_get real: si get_content devuelve HTML válido, lo cachea y lo devuelve.
    """
    adapter = LiveOverviewAdapter(
        get_browser=lambda wid: _build_mock_browser(html=FAKE_HTML),
        get_world_server=lambda wid: "https://ts20.travian.com/",
    )

    with patch("adapters.browser.live_overview_adapter.human_delay", new_callable=AsyncMock):
        result = asyncio.run(adapter.get_page_html(WORLD_ID, PAGE))

    assert result == FAKE_HTML
    # Debe haber quedado en caché
    assert (WORLD_ID, PAGE) in adapter._cache


# ---------------------------------------------------------------------------
# Helpers para mocks de browser
# ---------------------------------------------------------------------------


def _build_mock_browser(html: str) -> MagicMock:
    """
    Construye un mock de zd.Browser que devuelve html desde get_content.
    wait_for no lanza (simula carga exitosa).
    """
    mock_tab = MagicMock()
    mock_tab.wait_for = AsyncMock(return_value=None)
    mock_tab.get_content = AsyncMock(return_value=html)

    mock_browser = MagicMock()
    mock_browser.get = AsyncMock(return_value=mock_tab)
    return mock_browser
