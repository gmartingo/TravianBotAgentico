"""
Tests unitarios de las excepciones del dominio.
Verifican mensajes, atributos y jerarquía de herencia.
"""
import pytest

from core.exceptions import (
    TravianBotError,
    AccountNotFoundError,
    DuplicateAccountError,
    WorldNotFoundError,
    SessionNotActiveError,
    InvalidCredentialsError,
    VillageNotFoundError,
    FarmListNotFoundError,
    LoginError,
    BrowserError,
    DatabaseError,
)


# ---------------------------------------------------------------------------
# AccountNotFoundError
# ---------------------------------------------------------------------------

def test_account_not_found_mensaje_contiene_id():
    err = AccountNotFoundError(42)
    assert "42" in str(err)


def test_account_not_found_tiene_atributo_account_id():
    err = AccountNotFoundError(7)
    assert err.account_id == 7


def test_account_not_found_es_travian_bot_error():
    err = AccountNotFoundError(1)
    assert isinstance(err, TravianBotError)


# ---------------------------------------------------------------------------
# WorldNotFoundError
# ---------------------------------------------------------------------------

def test_world_not_found_mensaje_contiene_id():
    err = WorldNotFoundError(99)
    assert "99" in str(err)


def test_world_not_found_tiene_atributo_world_id():
    err = WorldNotFoundError(55)
    assert err.world_id == 55


def test_world_not_found_es_travian_bot_error():
    err = WorldNotFoundError(1)
    assert isinstance(err, TravianBotError)


# ---------------------------------------------------------------------------
# DuplicateAccountError
# ---------------------------------------------------------------------------

def test_duplicate_account_mensaje_contiene_username():
    err = DuplicateAccountError("player123")
    assert "player123" in str(err)


def test_duplicate_account_tiene_atributo_username():
    err = DuplicateAccountError("player123")
    assert err.username == "player123"


# ---------------------------------------------------------------------------
# Resto de excepciones — jerarquía y existencia
# ---------------------------------------------------------------------------

def test_session_not_active_es_travian_bot_error():
    err = SessionNotActiveError()
    assert isinstance(err, TravianBotError)
    assert "sesión" in str(err).lower() or "activa" in str(err).lower()


def test_invalid_credentials_tiene_atributo_username():
    err = InvalidCredentialsError("user1")
    assert err.username == "user1"
    assert "user1" in str(err)


def test_village_not_found_tiene_atributo_village_id():
    err = VillageNotFoundError(33)
    assert err.village_id == 33
    assert "33" in str(err)


def test_farm_list_not_found_tiene_atributo_farm_list_id():
    err = FarmListNotFoundError(77)
    assert err.farm_list_id == 77
    assert "77" in str(err)


def test_login_error_es_travian_bot_error():
    assert issubclass(LoginError, TravianBotError)


def test_browser_error_es_travian_bot_error():
    assert issubclass(BrowserError, TravianBotError)


def test_database_error_es_travian_bot_error():
    assert issubclass(DatabaseError, TravianBotError)


def test_todas_las_excepciones_heredan_de_exception():
    for exc_cls in [
        TravianBotError, AccountNotFoundError, DuplicateAccountError,
        WorldNotFoundError, SessionNotActiveError, InvalidCredentialsError,
        VillageNotFoundError, FarmListNotFoundError, LoginError,
        BrowserError, DatabaseError,
    ]:
        assert issubclass(exc_cls, Exception), f"{exc_cls} no hereda de Exception"
