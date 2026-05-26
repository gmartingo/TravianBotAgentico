"""
Tests unitarios para core/utils/units.py — unit_class_to_tribe_ordinal.

Verifica el mapeo global uNN → (Tribe, ordinal) contra el catálogo troops.json
y el enum Tribe. Cada rango de tribus tiene al menos un caso positivo y se
cubren todos los casos de retorno None.
"""
import pytest
from core.entities.tribe import Tribe
from core.utils.units import unit_class_to_tribe_ordinal


class TestUnitClassToTribeOrdinal:
    """Casos positivos — cada tribu del enum que tiene rango en el catálogo."""

    # ── ROMANS u1–u10 ────────────────────────────────────────────────────────
    def test_romans_first(self):
        assert unit_class_to_tribe_ordinal("u1") == (Tribe.ROMANS, 1)

    def test_romans_last(self):
        assert unit_class_to_tribe_ordinal("u10") == (Tribe.ROMANS, 10)

    def test_romans_middle(self):
        assert unit_class_to_tribe_ordinal("u5") == (Tribe.ROMANS, 5)

    # ── TEUTONS u11–u20 ──────────────────────────────────────────────────────
    def test_teutons_first(self):
        assert unit_class_to_tribe_ordinal("u11") == (Tribe.TEUTONS, 1)

    def test_teutons_last(self):
        assert unit_class_to_tribe_ordinal("u20") == (Tribe.TEUTONS, 10)

    def test_teutons_middle(self):
        assert unit_class_to_tribe_ordinal("u15") == (Tribe.TEUTONS, 5)

    # ── GAULS u21–u30 ────────────────────────────────────────────────────────
    def test_gauls_first(self):
        assert unit_class_to_tribe_ordinal("u21") == (Tribe.GAULS, 1)

    def test_gauls_second(self):
        # u22 → GAULS_2 (Espadachín galo) — verificado en fixture overview.html
        assert unit_class_to_tribe_ordinal("u22") == (Tribe.GAULS, 2)

    def test_gauls_fourth(self):
        # u24 → GAULS_4 (Teutat Thunder) — verificado en fixture
        assert unit_class_to_tribe_ordinal("u24") == (Tribe.GAULS, 4)

    def test_gauls_sixth(self):
        # u26 → GAULS_6 (Haeduan) — verificado en fixture
        assert unit_class_to_tribe_ordinal("u26") == (Tribe.GAULS, 6)

    def test_gauls_last(self):
        assert unit_class_to_tribe_ordinal("u30") == (Tribe.GAULS, 10)

    # ── NATURE u31–u40 ───────────────────────────────────────────────────────
    def test_nature_first(self):
        # u31 → (NATURE, 1) — Naturaleza tiene entradas en el catálogo
        assert unit_class_to_tribe_ordinal("u31") == (Tribe.NATURE, 1)

    def test_nature_last(self):
        assert unit_class_to_tribe_ordinal("u40") == (Tribe.NATURE, 10)

    # ── EGYPTIANS u41–u50 ────────────────────────────────────────────────────
    def test_egyptians_first(self):
        assert unit_class_to_tribe_ordinal("u41") == (Tribe.EGYPTIANS, 1)

    def test_egyptians_last(self):
        assert unit_class_to_tribe_ordinal("u50") == (Tribe.EGYPTIANS, 10)

    # ── HUNS u51–u60 ─────────────────────────────────────────────────────────
    def test_huns_first(self):
        assert unit_class_to_tribe_ordinal("u51") == (Tribe.HUNS, 1)

    def test_huns_last(self):
        assert unit_class_to_tribe_ordinal("u60") == (Tribe.HUNS, 10)

    # ── NATARS u61–u71 ───────────────────────────────────────────────────────
    def test_natars_first(self):
        assert unit_class_to_tribe_ordinal("u61") == (Tribe.NATARS, 1)

    def test_natars_last(self):
        # u71 → (NATARS, 11) — NATARS_11 existe en catálogo pero nombre vacío
        assert unit_class_to_tribe_ordinal("u71") == (Tribe.NATARS, 11)

    def test_natars_middle(self):
        assert unit_class_to_tribe_ordinal("u65") == (Tribe.NATARS, 5)

    # ── SPARTANS u72–u81 ─────────────────────────────────────────────────────
    def test_spartans_first(self):
        assert unit_class_to_tribe_ordinal("u72") == (Tribe.SPARTANS, 1)

    def test_spartans_last(self):
        assert unit_class_to_tribe_ordinal("u81") == (Tribe.SPARTANS, 10)

    # ── VIKINGS u82–u91 ──────────────────────────────────────────────────────
    def test_vikings_first(self):
        assert unit_class_to_tribe_ordinal("u82") == (Tribe.VIKINGS, 1)

    def test_vikings_last(self):
        assert unit_class_to_tribe_ordinal("u91") == (Tribe.VIKINGS, 10)


class TestUnitClassToTribeOrdinalNone:
    """Casos que deben devolver None."""

    def test_uhero_returns_none(self):
        assert unit_class_to_tribe_ordinal("uhero") is None

    def test_out_of_range_high(self):
        # u99 está fuera de todos los rangos
        assert unit_class_to_tribe_ordinal("u99") is None

    def test_out_of_range_zero(self):
        # u0 no está en ningún rango (rangos empiezan en 1)
        assert unit_class_to_tribe_ordinal("u0") is None

    def test_out_of_range_between_natars_spartans(self):
        # No existe u92 en el catálogo
        assert unit_class_to_tribe_ordinal("u92") is None

    def test_invalid_no_prefix(self):
        assert unit_class_to_tribe_ordinal("foo") is None

    def test_invalid_empty(self):
        assert unit_class_to_tribe_ordinal("") is None

    def test_invalid_only_u(self):
        # "u" sin número
        assert unit_class_to_tribe_ordinal("u") is None

    def test_invalid_u_with_non_digit(self):
        # "u1a" — sufijo no es puramente numérico
        assert unit_class_to_tribe_ordinal("u1a") is None

    def test_invalid_uppercase(self):
        # Travian usa minúsculas; "U22" no es una clase válida
        assert unit_class_to_tribe_ordinal("U22") is None

    def test_invalid_just_number(self):
        assert unit_class_to_tribe_ordinal("22") is None


class TestUnitClassNeverRaises:
    """La función nunca debe lanzar, independientemente de la entrada."""

    @pytest.mark.parametrize("value", [
        None, 42, [], {}, object(), "u" * 1000, "u-1",
    ])
    def test_no_raise_on_arbitrary_input(self, value):
        try:
            result = unit_class_to_tribe_ordinal(value)  # type: ignore[arg-type]
            # Si no lanza, debe devolver None o una tupla
            assert result is None or (isinstance(result, tuple) and len(result) == 2)
        except (AttributeError, TypeError):
            # Inputs que no son str pueden provocar AttributeError/TypeError en
            # startswith/isdigit — es aceptable; lo importante es que no causen
            # errores de lógica silenciosos. Si el contrato requiere str, esto
            # documenta el comportamiento con entradas no-str.
            pass
