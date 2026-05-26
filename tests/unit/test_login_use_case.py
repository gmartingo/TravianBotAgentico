"""
Tests unitarios de LoginUseCase y LogoutUseCase.
No abren Chrome ni BD. Mockean WorldRuntimePort y DbPort completamente.

Incluye:
  - Tests del spec original (login exitoso, fallos de cuenta/mundo, etc.)
  - Tests del Amendment A1: descifrado con Fernet real, InvalidToken → LoginFailedError,
    cipher None → LoginFailedError.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.fernet import Fernet, InvalidToken

from core.crypto import encrypt_password
from core.entities.account import Account
from core.entities.tribe import Tribe
from core.entities.world import World
from core.exceptions import AccountNotFoundError, LoginFailedError, WorldNotFoundError
from core.use_cases.login_use_case import LoginUseCase, LogoutUseCase

# ---------------------------------------------------------------------------
# Constantes de test — Fernet real (no mock)
# ---------------------------------------------------------------------------

TEST_FERNET = Fernet(Fernet.generate_key())
TEST_PASSWORD = "mi_password_real"
TEST_CIPHER = encrypt_password(TEST_FERNET, TEST_PASSWORD)


# ---------------------------------------------------------------------------
# Helpers de construcción
# ---------------------------------------------------------------------------

def _make_world(world_id: int = 1) -> World:
    return World(id=world_id, server="https://ts1.x1.international.travian.com/", tribe=Tribe.ROMANS)


def _make_account(worlds: list[World] | None = None) -> Account:
    return Account(
        id=1,
        email="test@example.com",
        username="testuser",
        password="",  # placeholder; get_account() devuelve "" — el use case descifra
        worlds=worlds or [],
    )


def _make_use_case(
    db_account=None,
    db_cipher=TEST_CIPHER,
    registry_login_result=True,
    fernet=TEST_FERNET,
):
    """
    Fabrica un LoginUseCase con mocks configurables.
    Por defecto: cuenta existe, cipher real, registry.login → True, Fernet real.
    """
    db = MagicMock()
    db.get_account = AsyncMock(return_value=db_account)
    db.get_account_password_cipher = AsyncMock(return_value=db_cipher)

    registry = MagicMock()
    registry.login = AsyncMock(return_value=registry_login_result)

    use_case = LoginUseCase(registry=registry, db=db, fernet=fernet)
    return use_case, db, registry


# ---------------------------------------------------------------------------
# Amendment A1.9.2 — Tests con Fernet real
# ---------------------------------------------------------------------------

def test_execute_success_decrypts_password():
    """
    A1: Caso feliz — el use case descifra correctamente y pasa la contraseña real
    a registry.login.
    registry.login debe recibir account con account.password == TEST_PASSWORD.
    """
    world = _make_world(1)
    account = _make_account(worlds=[world])
    use_case, db, registry = _make_use_case(
        db_account=account,
        db_cipher=TEST_CIPHER,
        registry_login_result=True,
        fernet=TEST_FERNET,
    )

    result = asyncio.run(use_case.execute(account_id=1, world_id=1))

    assert result is True
    # El account pasado a registry.login debe tener la contraseña descifrada
    call_args = registry.login.call_args
    passed_account = call_args[0][0]
    assert passed_account.password == TEST_PASSWORD


def test_execute_invalid_token_raises_login_failed():
    """
    A1 EC-A2: Token cifrado con una clave Fernet diferente → InvalidToken →
    debe lanzar LoginFailedError (nunca InvalidToken cruda, nunca 500).
    """
    world = _make_world(1)
    account = _make_account(worlds=[world])

    # Cifrar con una clave DIFERENTE a la inyectada en el use case
    other_fernet = Fernet(Fernet.generate_key())
    wrong_cipher = encrypt_password(other_fernet, "otra_password")

    use_case, db, registry = _make_use_case(
        db_account=account,
        db_cipher=wrong_cipher,
        fernet=TEST_FERNET,  # clave distinta a la usada para cifrar
    )

    with pytest.raises(LoginFailedError):
        asyncio.run(use_case.execute(account_id=1, world_id=1))

    # Confirmar que registry.login nunca se llamó (fallo antes)
    registry.login.assert_not_called()


def test_execute_cipher_none_raises_login_failed():
    """
    A1 EC-A1: get_account_password_cipher devuelve None →
    debe lanzar LoginFailedError (situación de corrupción de BD, 401 nunca 500).
    """
    world = _make_world(1)
    account = _make_account(worlds=[world])

    use_case, db, registry = _make_use_case(
        db_account=account,
        db_cipher=None,  # simula BD corrupta
    )

    with pytest.raises(LoginFailedError):
        asyncio.run(use_case.execute(account_id=1, world_id=1))

    registry.login.assert_not_called()


# ---------------------------------------------------------------------------
# Tests del spec original — adaptados para incluir fernet
# ---------------------------------------------------------------------------

def test_login_success():
    """account existe, world en lista, registry.login devuelve True → execute devuelve True."""
    world = _make_world(1)
    account = _make_account(worlds=[world])
    use_case, db, registry = _make_use_case(db_account=account, registry_login_result=True)

    result = asyncio.run(use_case.execute(account_id=1, world_id=1))

    assert result is True
    db.get_account.assert_called_once_with(1)
    db.get_account_password_cipher.assert_called_once_with(1)
    # registry.login es llamado con el account (con contraseña descifrada) y el world correcto
    registry.login.assert_called_once()
    call_args = registry.login.call_args[0]
    assert call_args[1] == world


def test_login_failure_from_registry():
    """registry.login devuelve False → execute devuelve False."""
    world = _make_world(1)
    account = _make_account(worlds=[world])
    use_case, _, _ = _make_use_case(db_account=account, registry_login_result=False)

    result = asyncio.run(use_case.execute(account_id=1, world_id=1))

    assert result is False


def test_execute_login_returns_false():
    """Todo correcto pero registry.login devuelve False → execute devuelve False (el handler lo convierte en LoginFailedError)."""
    world = _make_world(1)
    account = _make_account(worlds=[world])
    use_case, _, registry = _make_use_case(db_account=account, registry_login_result=False)

    result = asyncio.run(use_case.execute(account_id=1, world_id=1))

    assert result is False
    # El use case devuelve False; es el handler quien lanza LoginFailedError
    registry.login.assert_called_once()


def test_execute_account_not_found():
    """db.get_account devuelve None → lanza AccountNotFoundError."""
    use_case, _, registry = _make_use_case(db_account=None)

    with pytest.raises(AccountNotFoundError) as exc_info:
        asyncio.run(use_case.execute(account_id=99, world_id=1))

    assert exc_info.value.account_id == 99
    registry.login.assert_not_called()


def test_execute_world_not_found():
    """world_id no en account.worlds → lanza WorldNotFoundError."""
    world = _make_world(2)
    account = _make_account(worlds=[world])
    use_case, _, registry = _make_use_case(db_account=account)

    with pytest.raises(WorldNotFoundError) as exc_info:
        asyncio.run(use_case.execute(account_id=1, world_id=99))

    assert exc_info.value.world_id == 99
    registry.login.assert_not_called()


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


def test_world_list_empty_lanza_world_not_found():
    """account.worlds = [] → lanza WorldNotFoundError."""
    account = _make_account(worlds=[])
    use_case, _, _ = _make_use_case(db_account=account)

    with pytest.raises(WorldNotFoundError):
        asyncio.run(use_case.execute(account_id=1, world_id=1))


def test_login_selecciona_mundo_correcto():
    """Cuando hay múltiples mundos, se selecciona y pasa el correcto a registry."""
    world1 = _make_world(1)
    world2 = World(id=2, server="https://ts2.x3.international.travian.com/", tribe=Tribe.GAULS)
    account = _make_account(worlds=[world1, world2])
    use_case, _, registry = _make_use_case(db_account=account, registry_login_result=True)

    asyncio.run(use_case.execute(account_id=1, world_id=2))

    call_args = registry.login.call_args[0]
    assert call_args[1] == world2


# ---------------------------------------------------------------------------
# LogoutUseCase — no debe tener campo fernet, no ha cambiado
# ---------------------------------------------------------------------------

def test_logout_use_case_unchanged():
    """
    A1: LogoutUseCase no tiene campo fernet y registry.logout es llamado correctamente.
    """
    registry = MagicMock()
    registry.logout = AsyncMock()

    use_case = LogoutUseCase(registry=registry)

    # Confirmar que no tiene campo fernet
    assert not hasattr(use_case, "fernet"), "LogoutUseCase no debe tener campo 'fernet'"

    asyncio.run(use_case.execute(world_id=1))
    registry.logout.assert_called_once_with(1)
