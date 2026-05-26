"""
Tests unitarios de account_use_cases y world_use_cases.
No abren Chrome ni BD. Mockean DbPort y WorldRuntimePort completamente.
UT-01 a UT-13 + UT-16 a UT-19 del Plan de pruebas.
"""
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.crypto import decrypt_password, encrypt_password, load_fernet_key
from core.entities.account import Account
from core.entities.tribe import PLAYABLE_TRIBES, Tribe
from core.entities.world import World
from core.exceptions import (
    AccountNotFoundError,
    ActiveSessionConflictError,
    DuplicateAccountError,
    DuplicateWorldError,
    WorldNotFoundError,
)
from core.use_cases.account_use_cases import (
    CreateAccountUseCase,
    DeleteAccountUseCase,
    UpdateAccountUseCase,
)
from core.use_cases.world_use_cases import AddWorldUseCase, DeleteWorldUseCase


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fernet(monkeypatch):
    """Fernet con clave de test — NO usar en producción."""
    from cryptography.fernet import Fernet as _Fernet
    key = _Fernet.generate_key().decode()
    monkeypatch.setenv("TRAVIAN_BOT_SECRET_KEY", key)
    return load_fernet_key()


def _make_account(account_id=1, email="test@example.com", worlds=None):
    return Account(id=account_id, email=email, username="testuser", password="pass", worlds=worlds or [])


def _make_world(world_id=10, server="https://ts1.x1.international.travian.com/"):
    return World(id=world_id, server=server, tribe=Tribe.ROMANS)


def _mock_db(
    get_account=None,
    get_account_by_email=None,
    list_worlds=None,
    save_account=None,
    update_account=None,
    delete_account=None,
    get_world=None,
    get_world_by_account_and_server=None,
    save_world=None,
    delete_world=None,
):
    db = MagicMock()
    db.get_account = AsyncMock(return_value=get_account)
    db.get_account_by_email = AsyncMock(return_value=get_account_by_email)
    db.list_worlds = AsyncMock(return_value=list_worlds or [])
    db.save_account = AsyncMock(side_effect=save_account)
    db.update_account = AsyncMock(return_value=update_account)
    db.delete_account = AsyncMock()
    db.get_world = AsyncMock(return_value=get_world)
    db.get_world_by_account_and_server = AsyncMock(return_value=get_world_by_account_and_server)
    db.save_world = AsyncMock(side_effect=save_world)
    db.delete_world = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# UT-14, UT-15: crypto
# ---------------------------------------------------------------------------

def test_encrypt_decrypt_roundtrip(fernet):
    """UT-14: encrypt + decrypt devuelve el plaintext original."""
    plain = "mi_contraseña_secreta"
    token = encrypt_password(fernet, plain)
    assert isinstance(token, bytes)
    recovered = decrypt_password(fernet, token)
    assert recovered == plain


def test_encrypt_no_determinista(fernet):
    """Cada cifrado produce un token diferente (IV aleatorio)."""
    plain = "misma_password"
    t1 = encrypt_password(fernet, plain)
    t2 = encrypt_password(fernet, plain)
    assert t1 != t2


def test_load_fernet_key_sin_variable_de_entorno(monkeypatch):
    """UT-15: load_fernet_key sin variable → RuntimeError."""
    monkeypatch.delenv("TRAVIAN_BOT_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="TRAVIAN_BOT_SECRET_KEY"):
        load_fernet_key()


# ---------------------------------------------------------------------------
# UT-01 a UT-03: CreateAccountUseCase
# ---------------------------------------------------------------------------

def test_create_account_nuevo(fernet):
    """UT-01: email nuevo → Account con id asignado."""
    saved_account = _make_account(account_id=5)

    async def _save_side(account, pw_bytes):
        assert isinstance(pw_bytes, bytes)
        return saved_account

    db = _mock_db(get_account_by_email=None, save_account=_save_side)
    uc = CreateAccountUseCase(db=db, fernet=fernet)
    result = asyncio.run(uc.execute("NEW@EXAMPLE.COM", "testuser", "secret"))
    assert result.id == 5
    db.get_account_by_email.assert_called_once_with("new@example.com")
    db.save_account.assert_called_once()


def test_create_account_email_duplicado(fernet):
    """UT-02: email ya existe → DuplicateAccountError."""
    existing = _make_account()
    db = _mock_db(get_account_by_email=existing)
    uc = CreateAccountUseCase(db=db, fernet=fernet)
    with pytest.raises(DuplicateAccountError):
        asyncio.run(uc.execute("test@example.com", "u", "p"))


def test_create_account_email_normaliza_mayusculas(fernet):
    """UT-03: email con mayúsculas se normaliza antes de buscar y persistir."""
    saved = _make_account(email="user@example.com")

    async def _save_side(account, pw_bytes):
        assert account.email == "user@example.com"
        return saved

    db = _mock_db(get_account_by_email=None, save_account=_save_side)
    uc = CreateAccountUseCase(db=db, fernet=fernet)
    asyncio.run(uc.execute("USER@EXAMPLE.COM", "u", "p"))
    db.get_account_by_email.assert_called_once_with("user@example.com")


# ---------------------------------------------------------------------------
# UT-04 a UT-06: UpdateAccountUseCase
# ---------------------------------------------------------------------------

def test_update_account_cambia_email_libre(fernet):
    """UT-04: email nuevo libre → persiste el nuevo email."""
    existing = _make_account(email="old@example.com")
    updated = _make_account(email="new@example.com")

    db = _mock_db(get_account=existing, get_account_by_email=None, update_account=updated)
    uc = UpdateAccountUseCase(db=db, fernet=fernet)
    result = asyncio.run(uc.execute(1, "new@example.com", "u"))
    assert result.email == "new@example.com"


def test_update_account_email_duplicado_en_otra_cuenta(fernet):
    """UT-05: nuevo email ya pertenece a otra cuenta → DuplicateAccountError."""
    existing = _make_account(account_id=1, email="me@example.com")
    other = _make_account(account_id=2, email="other@example.com")

    db = _mock_db(get_account=existing, get_account_by_email=other)
    uc = UpdateAccountUseCase(db=db, fernet=fernet)
    with pytest.raises(DuplicateAccountError):
        asyncio.run(uc.execute(1, "other@example.com", "u"))


def test_update_account_sin_password_no_cambia(fernet):
    """UT-06: password=None → update_account llamado con password_cifrada=None."""
    existing = _make_account()
    updated = _make_account()
    db = _mock_db(get_account=existing, get_account_by_email=None, update_account=updated)
    uc = UpdateAccountUseCase(db=db, fernet=fernet)
    asyncio.run(uc.execute(1, "test@example.com", "u", password_plain=None))
    # El cuarto arg de update_account debe ser None
    call_args = db.update_account.call_args
    assert call_args[0][3] is None  # password_cifrada=None


# ---------------------------------------------------------------------------
# UT-07, UT-08: DeleteAccountUseCase
# ---------------------------------------------------------------------------

def test_delete_account_con_sesion_activa(fernet):
    """UT-07: WorldRuntimePort.is_active=True → ActiveSessionConflictError."""
    world = _make_world(world_id=3)
    account = _make_account(worlds=[world])
    db = _mock_db(get_account=account, list_worlds=[world])

    runtime = MagicMock()
    runtime.is_active = MagicMock(return_value=True)

    uc = DeleteAccountUseCase(db=db, runtime_port=runtime)
    with pytest.raises(ActiveSessionConflictError) as exc_info:
        asyncio.run(uc.execute(1))
    assert exc_info.value.world_id == 3


def test_delete_account_sin_runtime_port_permite_borrado(caplog):
    """UT-08: runtime_port=None → borrado permitido + WARNING en log."""
    world = _make_world()
    account = _make_account(worlds=[world])
    db = _mock_db(get_account=account, list_worlds=[world])

    uc = DeleteAccountUseCase(db=db, runtime_port=None)
    with caplog.at_level("WARNING"):
        asyncio.run(uc.execute(1))

    db.delete_account.assert_called_once_with(1)
    assert any("WorldRuntimePort" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# UT-09 a UT-13: AddWorldUseCase / DeleteWorldUseCase
# ---------------------------------------------------------------------------

def test_add_world_tribu_jugable():
    """UT-09: tribu jugable → World persistido."""
    account = _make_account()
    saved_world = _make_world(world_id=5)

    async def _save_world_side(account_id, world):
        return saved_world

    db = _mock_db(
        get_account=account,
        get_world_by_account_and_server=None,
        save_world=_save_world_side,
    )
    uc = AddWorldUseCase(db=db)
    result = asyncio.run(uc.execute(1, "https://ts1.x1.international.travian.com/", Tribe.ROMANS))
    assert result.id == 5


def test_add_world_tribu_npc_lanza_value_error():
    """UT-10: tribu NPC → ValueError (defensa en profundidad del use case)."""
    account = _make_account()
    db = _mock_db(get_account=account, get_world_by_account_and_server=None)
    uc = AddWorldUseCase(db=db)
    with pytest.raises(ValueError, match="jugable"):
        asyncio.run(uc.execute(1, "https://ts1.x1.international.travian.com/", Tribe.NATURE))


def test_add_world_duplicado():
    """UT-11: (account_id, server) duplicado → DuplicateWorldError."""
    account = _make_account()
    existing_world = _make_world()
    db = _mock_db(get_account=account, get_world_by_account_and_server=existing_world)
    uc = AddWorldUseCase(db=db)
    with pytest.raises(DuplicateWorldError):
        asyncio.run(uc.execute(1, "https://ts1.x1.international.travian.com/", Tribe.ROMANS))


def test_delete_world_con_sesion_activa():
    """UT-12: sesión activa → ActiveSessionConflictError."""
    account = _make_account()
    world = _make_world(world_id=7)
    db = _mock_db(get_account=account, get_world=world, list_worlds=[world])

    runtime = MagicMock()
    runtime.is_active = MagicMock(return_value=True)

    uc = DeleteWorldUseCase(db=db, runtime_port=runtime)
    with pytest.raises(ActiveSessionConflictError) as exc_info:
        asyncio.run(uc.execute(account_id=1, world_id=7))
    assert exc_info.value.world_id == 7


def test_delete_world_no_pertenece_a_cuenta():
    """UT-13: world no pertenece a la cuenta → WorldNotFoundError."""
    account = _make_account()
    # El mundo existe globalmente pero no en los mundos de esta cuenta
    world = _make_world(world_id=99)
    # list_worlds devuelve lista vacía (mundo 99 no pertenece a cuenta 1)
    db = _mock_db(get_account=account, get_world=world, list_worlds=[])

    uc = DeleteWorldUseCase(db=db, runtime_port=None)
    with pytest.raises(WorldNotFoundError):
        asyncio.run(uc.execute(account_id=1, world_id=99))


# ---------------------------------------------------------------------------
# UT-16, UT-17: Tribe.is_playable (también en test_entities.py, aquí redundante)
# ---------------------------------------------------------------------------

def test_tribe_is_playable_todas_las_jugables():
    """UT-16: las 7 jugables devuelven True."""
    for t in PLAYABLE_TRIBES:
        assert t.is_playable


def test_tribe_is_playable_npc_false():
    """UT-17: NATURE y NATARS → False."""
    assert not Tribe.NATURE.is_playable
    assert not Tribe.NATARS.is_playable


# ---------------------------------------------------------------------------
# UT-18: Account.__post_init__ con email vacío
# ---------------------------------------------------------------------------

def test_account_post_init_email_vacio_lanza_value_error():
    """UT-18: email vacío → ValueError."""
    with pytest.raises(ValueError, match="email"):
        Account(id=None, email="", username="u", password="p")


# ---------------------------------------------------------------------------
# UT-19: World.__post_init__ normaliza trailing slash
# ---------------------------------------------------------------------------

def test_world_post_init_trailing_slash():
    """UT-19: server sin trailing slash → se añade '/'."""
    world = World(id=0, server="https://ts1.x1.international.travian.com", tribe=Tribe.ROMANS)
    assert world.server.endswith("/")
    assert world.server == "https://ts1.x1.international.travian.com/"
