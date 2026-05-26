"""
Tests unitarios de core/utils/parsing.py

Cubre los casos de la sección 12.4 del spec lectura-overview-tronco-comun.
Incluye casos de caracteres bidi U+202D y U+202C que Travian inyecta alrededor
de los números en las páginas de statistics.
"""
import pytest

from core.utils.parsing import parse_int, parse_int_or_none, parse_time


# ---------------------------------------------------------------------------
# Tests — parse_int
# ---------------------------------------------------------------------------


def test_parse_int_dot_separator():
    """'1.200' → 1200 (separador de miles con punto)."""
    assert parse_int("1.200") == 1200


def test_parse_int_comma_separator():
    """'1,200' → 1200 (separador de miles con coma)."""
    assert parse_int("1,200") == 1200


def test_parse_int_no_separator():
    """'400' → 400 (sin separador)."""
    assert parse_int("400") == 400


def test_parse_int_large_dot():
    """'100.000' → 100000."""
    assert parse_int("100.000") == 100000


def test_parse_int_small():
    """'40' → 40."""
    assert parse_int("40") == 40


def test_parse_int_invalid():
    """'abc' → ValueError."""
    with pytest.raises(ValueError):
        parse_int("abc")


def test_parse_int_bidi_lro():
    """U+202D + '8' + U+202C → 8 (solo bidi, sin separador)."""
    # Construimos el string con los codepoints bidi
    text = "‭8‬"
    assert parse_int(text) == 8


def test_parse_int_bidi_with_comma():
    """U+202D + '8,786' + U+202C → 8786 (bidi + separador de miles)."""
    text = "‭8,786‬"
    assert parse_int(text) == 8786


def test_parse_int_bidi_nested():
    """
    '‭‭14‬/‭14‬‬' (anidado) — parse_int solo maneja una parte sin '/'.
    Para la primera parte '‭14‬' debe devolver 14.
    """
    # Tomamos solo la primera parte (antes del '/')
    raw = "‭‭14‬/‭14‬‬"
    first_part = raw.split("/")[0]
    assert parse_int(first_part) == 14


def test_parse_int_whitespace_stripped():
    """'  1200  ' → 1200 (whitespace ignorado)."""
    assert parse_int("  1200  ") == 1200


# ---------------------------------------------------------------------------
# Tests — parse_int_or_none
# ---------------------------------------------------------------------------


def test_parse_int_or_none_dash():
    """'—' (guión largo) → None."""
    assert parse_int_or_none("—") is None


def test_parse_int_or_none_empty():
    """'' (vacío) → None."""
    assert parse_int_or_none("") is None


def test_parse_int_or_none_hyphen():
    """'-' (guión corto) → None."""
    assert parse_int_or_none("-") is None


def test_parse_int_or_none_valid():
    """'120' → 120."""
    assert parse_int_or_none("120") == 120


def test_parse_int_or_none_with_separator():
    """'2.500' → 2500."""
    assert parse_int_or_none("2.500") == 2500


def test_parse_int_or_none_bidi():
    """'‭120‬' (con bidi) → 120."""
    text = "‭120‬"
    assert parse_int_or_none(text) == 120


def test_parse_int_or_none_bidi_dash():
    """'‭—‬' (bidi alrededor de guión largo) → None."""
    text = "‭—‬"  # U+2014 = em dash "—"
    # Tras quitar bidi queda "—"
    assert parse_int_or_none(text) is None


def test_parse_int_or_none_non_numeric():
    """'abc' → None (no numérico, devuelve None sin lanzar)."""
    assert parse_int_or_none("abc") is None


# ---------------------------------------------------------------------------
# Tests — parse_time
# ---------------------------------------------------------------------------


def test_parse_time_hmmss():
    """'1:30:00' → 5400 segundos."""
    assert parse_time("1:30:00") == 5400


def test_parse_time_zero():
    """'0:00:00' → 0 segundos."""
    assert parse_time("0:00:00") == 0


def test_parse_time_bare_int():
    """'0' (entero pelado) → 0 segundos."""
    assert parse_time("0") == 0


def test_parse_time_bare_int_nonzero():
    """'5' (entero pelado) → 5 segundos."""
    assert parse_time("5") == 5


def test_parse_time_with_suffix():
    """'0:30:00 / 2880 / jornada' → 1800 (solo primera parte)."""
    assert parse_time("0:30:00 / 2880 / jornada") == 1800


def test_parse_time_invalid():
    """'abc' → ValueError."""
    with pytest.raises(ValueError):
        parse_time("abc")


def test_parse_time_only_two_parts():
    """'12:34' (solo 2 partes) → ValueError."""
    with pytest.raises(ValueError):
        parse_time("12:34")


def test_parse_time_leading_zero():
    """'0:05:30' → 330 segundos."""
    assert parse_time("0:05:30") == 330


def test_parse_time_large_hours():
    """'2:30:00' → 9000 segundos."""
    assert parse_time("2:30:00") == 9000


def test_parse_time_valid_complex():
    """'1:23:45' → 5025 segundos."""
    assert parse_time("1:23:45") == 5025
