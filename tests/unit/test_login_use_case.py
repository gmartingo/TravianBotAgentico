"""
Tests unitarios de LoginUseCase.
No abren Chrome ni BD. Mockean WorldRuntimePort y DbPort completamente.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from core.entities.tribe import Tribe
from core.entities.world import World
from core.entities.account import Account
from core.exceptions import AccountNotFoundError, WorldNotFoundError
from core.use_cases.login_use_case import LoginUseCase


def _make_world(world_id: int = 1) -> World:
    return World(id=world_id, server="https://ts1.x1.international.travian.com/", tribe=Tribe.ROMANS)


def _make_account(worlds: list[World] | None = None) -> Account:
    return Account(id=1, email="test@example.com", username="testuser", password="testpass", worlds=worlds or [])


def _make_use_case(db_account=None, registry_login_result=True):
    """Fabrica un LoginUseCase con mocks configurables."""
    db = MagicMock()
    db.get_account = AsyncMock(return_value=db_account)

    registry = MagicMock()
    registry.login = AsyncMock(return_value=registry_login_result)

    use_case = LoginUseCase(registry=registry, db=db)
    return use_case, db, registry


# ---------------------------------------------------------------------------
# Caso feliz — login exitoso
# ---------------------------------------------------------------------------

def test_login_success():
    """account existe, world en lista, registry.login devuelve True → execute devuelve True."""
    world = _make_world(1)
    account = _make_account(worlds=[world])
    use_case, db, registry = _make_use_case(db_account=account, registry_login_result=True)

    result = asyncio.run(use_case.execute(account_id=1, world_id=1))

    assert result is True
    db.get_account.assert_called_once_with(1)
    registry.login.assert_called_once_with(account, world)


# ---------------------------------------------------------------------------
# Caso: registry devuelve False
# ---------------------------------------------------------------------------

def test_login_failure_from_registry():
    """registry.login devuelve False → execute devuelve False."""
    world = _make_world(1)
    account = _make_account(worlds=[world])
    use_case, _, _ = _make_use_case(db_account=account, registry_login_result=False)

    result = asyncio.run(use_case.execute(account_id=1, world_id=1))

    assert result is False


# ---------------------------------------------------------------------------
# Caso: cuenta no encontrada
# ---------------------------------------------------------------------------

def test_account_not_found_lanza_excepcion():
    """db.get_account devuelve None → lanza AccountNotFoundError."""
    use_case, _, _ = _make_use_case(db_account=None)

    with pytest.raises(AccountNotFoundError) as exc_info:
        asyncio.run(use_case.execute(account_id=99, world_id=1))

    assert exc_info.value.account_id == 99


def test_account_not_found_no_abre_browser():
    """Cuando la cuenta no existe, registry.login no debe ser llamado."""
    use_case, _, registry = _make_use_case(db_account=None)

    with pytest.raises(AccountNotFoundError):
        asyncio.run(use_case.execute(account_id=99, world_id=1))

    registry.login.assert_not_called()


# ---------------------------------------------------------------------------
# Caso: mundo no pertenece a la cuenta
# ---------------------------------------------------------------------------

def test_world_not_found_lanza_excepcion():
    """world_id no en account.worlds → lanza WorldNotFoundError."""
    world = _make_world(1)
    account = _make_account(worlds=[world])
    use_case, _, _ = _make_use_case(db_account=account)

    with pytest.raises(WorldNotFoundError) as exc_info:
        asyncio.run(use_case.execute(account_id=1, world_id=99))

    assert exc_info.value.world_id == 99


def test_world_not_found_no_abre_browser():
    """Cuando el mundo no existe, registry.login no debe ser llamado."""
    world = _make_world(1)
    account = _make_account(worlds=[world])
    use_case, _, registry = _make_use_case(db_account=account)

    with pytest.raises(WorldNotFoundError):
        asyncio.run(use_case.execute(account_id=1, world_id=99))

    registry.login.assert_not_called()


# ---------------------------------------------------------------------------
# Caso: lista de mundos vacía
# ---------------------------------------------------------------------------

def test_world_list_empty_lanza_world_not_found():
    """account.worlds = [] → lanza WorldNotFoundError."""
    account = _make_account(worlds=[])
    use_case, _, _ = _make_use_case(db_account=account)

    with pytest.raises(WorldNotFoundError):
        asyncio.run(use_case.execute(account_id=1, world_id=1))


# ---------------------------------------------------------------------------
# Caso: múltiples mundos, selección correcta
# ---------------------------------------------------------------------------

def test_login_selecciona_mundo_correcto():
    """Cuando hay múltiples mundos, se selecciona y pasa el correcto a registry."""
    world1 = _make_world(1)
    world2 = World(id=2, server="https://ts2.x3.international.travian.com/", tribe=Tribe.GAULS)
    account = _make_account(worlds=[world1, world2])
    use_case, _, registry = _make_use_case(db_account=account, registry_login_result=True)

    asyncio.run(use_case.execute(account_id=1, world_id=2))

    registry.login.assert_called_once_with(account, world2)
