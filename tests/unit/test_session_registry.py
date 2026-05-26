"""
Tests unitarios de SessionRegistry — sección 12.1 del spec login-sesion-api.

Estrategia:
  - Ningún test abre Chrome real.
  - login_module.login se mockea con unittest.mock.patch/AsyncMock.
  - browser se mockea con AsyncMock (tiene .stop() async).
  - live_adapter se mockea con Mock para verificar invalidate_cache.
  - Se usan asyncio.run() directo (NO @pytest.mark.asyncio — modo STRICT del proyecto).

15 tests cubriendo:
  - login exitoso / fallido
  - re-login con sesión previa
  - invalidación de caché en login/logout
  - logout con/sin sesión
  - is_active / get_browser / get_world_server
  - ausencia de live_adapter (no-crash)
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from adapters.browser.session_registry import SessionRegistry
from core.entities.account import Account
from core.entities.tribe import Tribe
from core.entities.world import World


# ---------------------------------------------------------------------------
# Fixtures helpers
# ---------------------------------------------------------------------------

def _make_account(username: str = "testtravian13@gmail.com") -> Account:
    return Account(
        id=1,
        email="testtravian13@gmail.com",
        username=username,
        password="secret",
    )


def _make_world(world_id: int = 1, server: str = "https://ts20.x2.america.travian.com/") -> World:
    return World(id=world_id, server=server, tribe=Tribe.ROMANS)


def _make_browser() -> AsyncMock:
    """Browser simulado: stop() es una coroutine."""
    browser = AsyncMock()
    browser.stop = AsyncMock()
    return browser


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_login_success():
    """login_module.login → (True, browser): sessions poblado, devuelve True."""
    registry = SessionRegistry()
    account = _make_account()
    world = _make_world(world_id=1)
    mock_browser = _make_browser()

    with patch(
        "adapters.browser.session_registry.login_module.login",
        new=AsyncMock(return_value=(True, mock_browser)),
    ):
        result = asyncio.run(registry.login(account, world))

    assert result is True
    assert 1 in registry._sessions
    assert registry._sessions[1][0] is mock_browser


def test_login_failure():
    """login_module.login → (False, None): sessions vacío, devuelve False."""
    registry = SessionRegistry()
    account = _make_account()
    world = _make_world(world_id=1)

    with patch(
        "adapters.browser.session_registry.login_module.login",
        new=AsyncMock(return_value=(False, None)),
    ):
        result = asyncio.run(registry.login(account, world))

    assert result is False
    assert 1 not in registry._sessions


def test_login_replaces_existing_session():
    """Sesión previa existe: old_browser.stop() llamado; sessions tiene new_browser."""
    registry = SessionRegistry()
    account = _make_account()
    world = _make_world(world_id=1)

    old_browser = _make_browser()
    new_browser = _make_browser()

    # Sembrar sesión previa directamente en el dict interno
    registry._sessions[1] = (old_browser, world)

    with patch(
        "adapters.browser.session_registry.login_module.login",
        new=AsyncMock(return_value=(True, new_browser)),
    ):
        asyncio.run(registry.login(account, world))

    old_browser.stop.assert_called_once()
    assert registry._sessions[1][0] is new_browser


def test_login_invalidates_cache_on_success():
    """Login exitoso con live_adapter inyectado: invalidate_cache(world_id) llamado."""
    registry = SessionRegistry()
    live_adapter = Mock()
    registry.set_live_adapter(live_adapter)

    account = _make_account()
    world = _make_world(world_id=1)
    mock_browser = _make_browser()

    with patch(
        "adapters.browser.session_registry.login_module.login",
        new=AsyncMock(return_value=(True, mock_browser)),
    ):
        asyncio.run(registry.login(account, world))

    live_adapter.invalidate_cache.assert_called_with(1)


def test_login_invalidates_cache_on_relogin():
    """Re-login: invalidate_cache llamado 2 veces (cierre previo + nueva sesión)."""
    registry = SessionRegistry()
    live_adapter = Mock()
    registry.set_live_adapter(live_adapter)

    account = _make_account()
    world = _make_world(world_id=1)
    old_browser = _make_browser()
    new_browser = _make_browser()

    # Sembrar sesión previa
    registry._sessions[1] = (old_browser, world)

    with patch(
        "adapters.browser.session_registry.login_module.login",
        new=AsyncMock(return_value=(True, new_browser)),
    ):
        asyncio.run(registry.login(account, world))

    # Debe haberse llamado exactamente 2 veces: al cerrar la anterior y al abrir la nueva
    assert live_adapter.invalidate_cache.call_count == 2
    live_adapter.invalidate_cache.assert_called_with(1)


def test_logout_with_active_session():
    """Sesión activa: browser.stop() llamado, sessions vacío."""
    registry = SessionRegistry()
    world = _make_world(world_id=1)
    mock_browser = _make_browser()
    registry._sessions[1] = (mock_browser, world)

    asyncio.run(registry.logout(1))

    mock_browser.stop.assert_called_once()
    assert 1 not in registry._sessions


def test_logout_without_session():
    """Sin sesión activa: no-op, no lanza excepción."""
    registry = SessionRegistry()
    # No debe lanzar ninguna excepción
    asyncio.run(registry.logout(1))
    assert 1 not in registry._sessions


def test_logout_invalidates_cache():
    """Logout con live_adapter inyectado: invalidate_cache(world_id) llamado."""
    registry = SessionRegistry()
    live_adapter = Mock()
    registry.set_live_adapter(live_adapter)

    world = _make_world(world_id=1)
    mock_browser = _make_browser()
    registry._sessions[1] = (mock_browser, world)

    asyncio.run(registry.logout(1))

    live_adapter.invalidate_cache.assert_called_once_with(1)


def test_is_active_true():
    """Sesión activa para world_id=1: is_active(1) → True."""
    registry = SessionRegistry()
    world = _make_world(world_id=1)
    mock_browser = _make_browser()
    registry._sessions[1] = (mock_browser, world)

    assert registry.is_active(1) is True


def test_is_active_false():
    """Sin sesión: is_active(1) → False."""
    registry = SessionRegistry()
    assert registry.is_active(1) is False


def test_get_browser_returns_browser():
    """Sesión activa: get_browser(world_id) devuelve el browser."""
    registry = SessionRegistry()
    world = _make_world(world_id=1)
    mock_browser = _make_browser()
    registry._sessions[1] = (mock_browser, world)

    result = registry.get_browser(1)
    assert result is mock_browser


def test_get_browser_returns_none():
    """Sin sesión: get_browser(world_id) → None."""
    registry = SessionRegistry()
    assert registry.get_browser(1) is None


def test_get_world_server_returns_server():
    """Sesión activa con world.server: get_world_server devuelve la URL del servidor."""
    registry = SessionRegistry()
    server_url = "https://ts20.x2.america.travian.com/"
    world = _make_world(world_id=1, server=server_url)
    mock_browser = _make_browser()
    registry._sessions[1] = (mock_browser, world)

    result = registry.get_world_server(1)
    # World.__post_init__ normaliza a trailing slash
    assert result == server_url


def test_get_world_server_returns_empty():
    """Sin sesión: get_world_server(world_id) → ''."""
    registry = SessionRegistry()
    assert registry.get_world_server(1) == ""


def test_no_live_adapter_no_crash():
    """Sin set_live_adapter: login exitoso no lanza excepción al intentar invalidar."""
    registry = SessionRegistry()
    # _live_adapter es None por defecto — no se llama set_live_adapter

    account = _make_account()
    world = _make_world(world_id=1)
    mock_browser = _make_browser()

    with patch(
        "adapters.browser.session_registry.login_module.login",
        new=AsyncMock(return_value=(True, mock_browser)),
    ):
        # No debe lanzar AttributeError ni ninguna excepción
        result = asyncio.run(registry.login(account, world))

    assert result is True
