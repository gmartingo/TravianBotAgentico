"""
Tests unitarios de las entidades de dominio: World, Village, Account, Tribe.
No abren Chrome ni BD. Verifican invariantes y normalización.
"""
import pytest

from core.entities.tribe import Tribe, PLAYABLE_TRIBES
from core.entities.village import Village
from core.entities.world import World
from core.entities.account import Account


# ---------------------------------------------------------------------------
# World — normalización de server URL
# ---------------------------------------------------------------------------

def test_world_trailing_slash_se_anade():
    """Un server sin trailing slash debe normalizarse añadiendo /."""
    world = World(id=1, server="https://ts1.x1.international.travian.com", tribe=Tribe.ROMANS)
    assert world.server.endswith("/"), f"server debe terminar en '/': {world.server!r}"


def test_world_trailing_slash_ya_presente_no_duplica():
    """Un server que ya termina en / no debe acabar con doble slash."""
    world = World(id=1, server="https://ts1.x1.international.travian.com/", tribe=Tribe.ROMANS)
    assert world.server == "https://ts1.x1.international.travian.com/"
    assert not world.server.endswith("//"), f"doble slash detectado: {world.server!r}"


def test_world_double_slash_se_normaliza():
    """Un server con doble slash al final debe quedar con uno solo."""
    world = World(id=1, server="https://ts1.x1.international.travian.com//", tribe=Tribe.ROMANS)
    assert world.server == "https://ts1.x1.international.travian.com/"


def test_world_server_con_espacios_se_limpia():
    """Espacios alrededor del server se eliminan y se añade trailing slash."""
    world = World(id=1, server="  https://ts1.x1.international.travian.com  ", tribe=Tribe.ROMANS)
    assert world.server == "https://ts1.x1.international.travian.com/"


# ---------------------------------------------------------------------------
# World — server_speed
# ---------------------------------------------------------------------------

def test_world_speed_x1():
    world = World(id=1, server="https://ts1.x1.international.travian.com/", tribe=Tribe.ROMANS)
    assert world.server_speed == 1.0


def test_world_speed_x3():
    world = World(id=1, server="https://ts2.x3.international.travian.com/", tribe=Tribe.ROMANS)
    assert world.server_speed == 3.0


def test_world_speed_x5():
    world = World(id=1, server="https://ts5.x5.international.travian.com/", tribe=Tribe.ROMANS)
    assert world.server_speed == 5.0


def test_world_speed_no_match_devuelve_1():
    """URL sin patrón .xN. devuelve 1.0 como default."""
    world = World(id=1, server="https://ts1.international.travian.com/", tribe=Tribe.ROMANS)
    assert world.server_speed == 1.0


# ---------------------------------------------------------------------------
# Account — validaciones (campo email añadido en registro-cuentas-mundos)
# ---------------------------------------------------------------------------

def test_account_username_vacio_lanza_value_error():
    with pytest.raises(ValueError, match="vacío"):
        Account(id=1, email="a@b.com", username="", password="pass123")


def test_account_username_none_lanza_value_error():
    with pytest.raises(ValueError):
        Account(id=1, email="a@b.com", username=None, password="pass123")  # type: ignore[arg-type]


def test_account_sin_worlds_tiene_lista_vacia():
    account = Account(id=1, email="user@example.com", username="travian_user", password="secret")
    assert account.worlds == []


def test_account_no_tiene_server_url():
    """account.py ya no debe tener el atributo server_url."""
    account = Account(id=1, email="user@example.com", username="travian_user", password="secret")
    assert not hasattr(account, "server_url"), "server_url fue eliminado del modelo"


def test_account_no_tiene_active():
    """account.py ya no debe tener el atributo active."""
    account = Account(id=1, email="user@example.com", username="travian_user", password="secret")
    assert not hasattr(account, "active"), "active fue eliminado del modelo"


def test_account_con_worlds_se_asigna():
    world = World(id=10, server="https://ts1.x1.international.travian.com/", tribe=Tribe.GAULS)
    account = Account(id=1, email="user@example.com", username="travian_user", password="secret", worlds=[world])
    assert len(account.worlds) == 1
    assert account.worlds[0].id == 10


def test_account_email_se_normaliza_lower_strip():
    """El email se normaliza a minúsculas y sin espacios."""
    account = Account(id=1, email="  User@Example.COM  ", username="u", password="p")
    assert account.email == "user@example.com"


def test_account_email_vacio_lanza_value_error():
    with pytest.raises(ValueError, match="email"):
        Account(id=1, email="", username="u", password="p")


def test_account_email_solo_espacios_lanza_value_error():
    """Un email de solo espacios se normaliza a vacío → ValueError."""
    with pytest.raises(ValueError, match="email"):
        Account(id=1, email="   ", username="u", password="p")


# ---------------------------------------------------------------------------
# Tribe — enum completo
# ---------------------------------------------------------------------------

def test_tribe_valores_correctos():
    assert Tribe.ROMANS.value == "romans"
    assert Tribe.TEUTONS.value == "teutons"
    assert Tribe.GAULS.value == "gauls"
    assert Tribe.EGYPTIANS.value == "egyptians"
    assert Tribe.HUNS.value == "huns"


def test_tribe_tiene_nueve_valores():
    """
    Tribe tiene 9 valores: los 5 originales + 4 añadidos en la feature kirilloid-tropas-scraper
    (NATURE, NATARS, SPARTANS, VIKINGS).
    """
    assert len(Tribe) == 9


def test_tribe_acceso_por_nombre():
    assert Tribe["ROMANS"] is Tribe.ROMANS
    assert Tribe["HUNS"] is Tribe.HUNS


# ---------------------------------------------------------------------------
# Tribe — is_playable (UT-16, UT-17)
# ---------------------------------------------------------------------------

def test_tribe_is_playable_jugables():
    """Las 7 tribus jugables deben tener is_playable=True."""
    jugables = [Tribe.ROMANS, Tribe.TEUTONS, Tribe.GAULS, Tribe.EGYPTIANS,
                Tribe.HUNS, Tribe.SPARTANS, Tribe.VIKINGS]
    for t in jugables:
        assert t.is_playable, f"{t} debería ser jugable"


def test_tribe_is_playable_npc():
    """NATURE y NATARS son NPC: is_playable=False."""
    assert not Tribe.NATURE.is_playable
    assert not Tribe.NATARS.is_playable


def test_playable_tribes_tiene_siete_elementos():
    assert len(PLAYABLE_TRIBES) == 7


def test_playable_tribes_no_incluye_npc():
    assert Tribe.NATURE not in PLAYABLE_TRIBES
    assert Tribe.NATARS not in PLAYABLE_TRIBES


# ---------------------------------------------------------------------------
# Village — estructura básica
# ---------------------------------------------------------------------------

def test_village_campos():
    v = Village(id=1, world_id=10, data_id=3, name="Mi Aldea", x=100, y=-50)
    assert v.id == 1
    assert v.world_id == 10
    assert v.data_id == 3
    assert v.name == "Mi Aldea"
    assert v.x == 100
    assert v.y == -50
