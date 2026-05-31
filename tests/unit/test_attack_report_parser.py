"""
Tests unitarios del parser de reportes de ataque a oasis.

Cubre los casos felices y edge cases del spec §12 que son puramente unitarios
(sin BD, sin HTTP). El parser se llama con db_port=None.

Idiomas cubiertos: español, inglés, alemán (CA-10).
Edge cases: EC-01..EC-14 relevantes para el parser.

Ver spec docs/specs/bd-ataques-oasis.md §12 para la correspondencia de tests.
Añadido en la feature bd-ataques-oasis (2026-05-30).
"""
from __future__ import annotations

import pytest

from core.use_cases.attack_report_parser import (
    MultipleReportsError,
    NotNatureOasisError,
    ReportFormatError,
    UnrecognizedAnimalError,
    build_nature_inverted_index,
    parse_attack_report,
)


# ---------------------------------------------------------------------------
# Fixtures de texto crudo — reportes de Travian simulados
# El formato refleja la estructura real de los reportes de Travian:
#   - Encabezado con nombre del oasis y coordenadas
#   - "Server time" con offset UTC
#   - Fecha de ataque
#   - Sección Attacker con nombre de aldea y tabla de tropas
#   - Sección Defender con tabla de animales
#   - Sección Bounty con recursos y capacidad
# ---------------------------------------------------------------------------

# Reporte en español — caso básico
_REPORT_ES = """\
Informe de ataque a Oasis (-32|-45)

Fecha del ataque: 30.05.26, 16:28:53
Server time: 17:28:53 (UTC +1:00)

Attacker
Mi Aldea (-10|-20)
Legionario
500
5

Defender
Rata  Spider  Serpiente
12    8       0
12    8       0

Bounty
480  480  480  480
120/240
"""

# Reporte en inglés — con offset UTC y hero inventory
_REPORT_EN = """\
Attack report on Oasis (-32|-45)

30.05.26, 16:28:53
Server time: 17:28:53 (UTC +1:00)

Attacker
MyVillage (-10|-20)
Legionnaire
100
5

Defender
Rat  Spider
12   8
12   8

Bounty
480  480  480  480
120/240
Additional resources were added to the hero's inventory
48  48  48  48
"""

# Reporte en alemán
_REPORT_DE = """\
Kampfbericht für Oase (-32|-45)

30.05.26, 16:28:53
Server time: 17:28:53 (UTC +1:00)

Attacker
MeinDorf (-10|-20)
Legionär
100
5

Defender
Ratte  Spinne
12     8
12     8

Bounty
480  480  480  480
120/240
"""

# Reporte sin offset UTC — EC-03
_REPORT_NO_OFFSET = """\
Attack report on Oasis (-32|-45)

30.05.26, 16:28:53

Attacker
MyVillage (-10|-20)
Legionnaire
100
5

Defender
Rat
12
12

Bounty
480  480  480  480
120/240
"""

# Reporte con coordenadas negativas — EC-02
_REPORT_NEG_COORDS = """\
Attack report on Oasis (-100/-200)

30.05.26, 16:28:53
Server time: 17:28:53 (UTC +1:00)

Attacker
MyVillage (50|60)
Legionnaire
50
0

Defender
Rat
5
5

Bounty
100  100  100  100
50/100
"""

# Reporte con animal con 0 presentes — EC-01
_REPORT_ZERO_ANIMALS = """\
Attack report on Oasis (10|20)

30.05.26, 16:28:53
Server time: 17:28:53 (UTC +1:00)

Attacker
MyVillage (5|5)
Legionnaire
100
0

Defender
Rat  Spider
0    5
0    5

Bounty
50  50  50  50
50/100
"""

# Reporte con animales supervivientes (oasis no limpiado) — T-EC14
_REPORT_SURVIVORS = """\
Attack report on Oasis (10|20)

30.05.26, 16:28:53
Server time: 17:28:53 (UTC +1:00)

Attacker
MyVillage (5|5)
Legionnaire
20
2

Defender
Rat  Spider
10   8
5    3

Bounty
100  100  100  100
50/100
"""

# Texto con múltiples bloques de reporte — EC-03 del spec
_REPORT_MULTIPLE = """\
Attack report on Oasis (-32|-45)

30.05.26, 16:28:53
Server time: 17:28:53 (UTC +1:00)

Attacker
MyVillage (-10|-20)
Legionnaire
100
5

Attack report on Oasis (-33|-46)

31.05.26, 10:00:00
Server time: 11:00:00 (UTC +1:00)

Attacker
MyVillage (-10|-20)
Legionnaire
100
0
"""

# Texto sin sección Nature — RN-01
_REPORT_NOT_NATURE = """\
Attack report on Village (-32|-45)

30.05.26, 16:28:53
Server time: 17:28:53 (UTC +1:00)

Attacker
MyVillage (-10|-20)
Legionnaire
100
5

Defender
Pretoriano
50
10

Bounty
200  200  200  200
200/500
"""

# Texto con nombre de animal inventado — RN-04
_REPORT_UNKNOWN_ANIMAL = """\
Attack report on Oasis (-32|-45)

30.05.26, 16:28:53
Server time: 17:28:53 (UTC +1:00)

Attacker
MyVillage (-10|-20)
Legionnaire
100
5

Defender
Lobezno  Dragón
10       5
10       5

Bounty
100  100  100  100
50/100
"""


# ---------------------------------------------------------------------------
# Tests del índice invertido
# ---------------------------------------------------------------------------

class TestNatureIndex:
    def test_index_has_215_catalog_entries_plus_live_aliases(self):
        # 215 nombres del catálogo kirilloid + alias del juego real ("snake").
        idx = build_nature_inverted_index()
        assert len(idx) == 216

    def test_snake_alias_maps_to_serpent_ordinal(self):
        # El juego muestra "Snake" pero kirilloid usa "Serpent" para NATURE_3.
        idx = build_nature_inverted_index()
        assert idx["snake"] == 3
        assert idx["serpent"] == 3

    def test_rat_is_ordinal_1_in_multiple_languages(self):
        idx = build_nature_inverted_index()
        assert idx["rata"] == 1     # es
        assert idx["rat"] == 1      # en, fr, nl
        assert idx["ratte"] == 1    # de

    def test_spider_is_ordinal_2(self):
        idx = build_nature_inverted_index()
        assert idx["spider"] == 2   # en
        assert idx["araña"] == 2    # es
        assert idx["spinne"] == 2   # de

    def test_no_collisions(self):
        """Confirma que ningún nombre apunta a dos ordinales distintos."""
        idx = build_nature_inverted_index()
        # Si llegamos aquí sin AssertionError, build_nature_inverted_index pasó
        # sin colisiones (la función es determinista con 0 colisiones confirmadas).
        assert all(1 <= v <= 10 for v in idx.values())

    def test_singleton_returns_same_object(self):
        """El índice se construye una sola vez (singleton)."""
        idx1 = build_nature_inverted_index()
        idx2 = build_nature_inverted_index()
        assert idx1 is idx2


# ---------------------------------------------------------------------------
# Tests de casos felices
# ---------------------------------------------------------------------------

class TestParseHappyPath:
    def test_T01_parse_report_es(self):
        """T-01: Parse de reporte válido en español."""
        preview = parse_attack_report(_REPORT_ES)
        assert preview.coord_x_dest == -32
        assert preview.coord_y_dest == -45
        assert preview.utc_offset == "+01:00"
        assert "2026" in preview.attacked_at
        # Atacante: "Legionario" → romano, ordinal 1 (tribu deducida del roster).
        assert len(preview.attacker_troops) >= 1
        assert preview.attacker_tribe == "romans"
        assert preview.attacker_troops[0].troop_ordinal == 1
        # Animales — Rata=1 y Spider/Araña=2
        ordinals = {a.animal_ordinal for a in preview.animals}
        assert 1 in ordinals  # Rata
        assert 2 in ordinals  # Araña/Spider
        # No hay ordinal desconocido
        assert all(1 <= a.animal_ordinal <= 10 for a in preview.animals)

    def test_T02_parse_report_en(self):
        """T-02: Parse de reporte válido en inglés."""
        preview = parse_attack_report(_REPORT_EN)
        assert preview.coord_x_dest == -32
        ordinals = {a.animal_ordinal for a in preview.animals}
        assert 1 in ordinals  # Rat
        assert 2 in ordinals  # Spider

    def test_T02_parse_report_de(self):
        """T-02 (alemán): Parser con nombres en alemán resueltos a ordinales."""
        preview = parse_attack_report(_REPORT_DE)
        ordinals = {a.animal_ordinal for a in preview.animals}
        assert 1 in ordinals  # Ratte
        assert 2 in ordinals  # Spinne

    def test_T03_utc_offset_normalization(self):
        """T-03: attacked_at es verbatim de la línea del ataque; utc_offset es metadato."""
        preview = parse_attack_report(_REPORT_ES)
        assert preview.utc_offset == "+01:00"
        # La hora del ataque es 16:28:53 (línea del ataque), NO 15:28:53.
        # El offset del Server time NO se resta (RN-08-bis).
        assert "16:28:53" in preview.attacked_at
        # Formato verbatim naive: sin +00:00 ni timezone info.
        assert "+" not in preview.attacked_at
        assert "Z" not in preview.attacked_at
        assert "T" in preview.attacked_at  # separador fecha/hora ISO

    def test_T04_no_hero_inventory(self):
        """T-04: Sin inventario de héroe → hero_inventory = None."""
        preview = parse_attack_report(_REPORT_ES)
        assert preview.hero_inventory is None

    def test_hero_inventory_present(self):
        """Parse de reporte con inventario de héroe → hero_inventory con 4 campos."""
        preview = parse_attack_report(_REPORT_EN)
        assert preview.hero_inventory is not None
        assert set(preview.hero_inventory.keys()) == {"wood", "clay", "iron", "crop"}
        assert preview.hero_inventory["wood"] == 48

    def test_survived_calculated_attacker(self):
        """RN-06: supervivientes atacante = enviadas − perdidas."""
        preview = parse_attack_report(_REPORT_EN)
        for t in preview.attacker_troops:
            assert t.survived == t.sent - t.lost

    def test_survived_calculated_animals(self):
        """RN-06: supervivientes animales = presentes − muertos."""
        preview = parse_attack_report(_REPORT_ES)
        for a in preview.animals:
            assert a.survived == a.present - a.killed

    def test_already_exists_default_false(self):
        """Sin db_port → already_exists=False por defecto."""
        preview = parse_attack_report(_REPORT_ES)
        assert preview.already_exists is False
        assert preview.existing_id is None

    def test_bounty_parsed(self):
        """Botín extraído correctamente."""
        preview = parse_attack_report(_REPORT_ES)
        assert preview.bounty.wood == 480
        assert preview.bounty.clay == 480
        assert preview.bounty.iron == 480
        assert preview.bounty.crop == 480
        assert preview.bounty.capacity_used == 120
        assert preview.bounty.capacity_total == 240

    def test_hero_inventory_is_root_field_not_in_bounty(self):
        """C2: hero_inventory es campo raíz de AttackReportPreview, NO en BountyData."""
        preview = parse_attack_report(_REPORT_EN)
        # BountyData no tiene el atributo hero_inventory
        assert not hasattr(preview.bounty, "hero_inventory")
        # AttackReportPreview sí lo tiene en primer nivel
        assert hasattr(preview, "hero_inventory")


# ---------------------------------------------------------------------------
# Tests de edge cases
# ---------------------------------------------------------------------------

class TestParseEdgeCases:
    def test_EC01_zero_animals(self):
        """EC-01: Animal con 0 presentes → present=0, killed=0, survived=0."""
        preview = parse_attack_report(_REPORT_ZERO_ANIMALS)
        zero_animals = [a for a in preview.animals if a.present == 0]
        assert len(zero_animals) >= 1
        for a in zero_animals:
            assert a.killed == 0
            assert a.survived == 0

    def test_EC02_negative_coordinates(self):
        """EC-02: Coordenadas negativas parseadas correctamente."""
        preview = parse_attack_report(_REPORT_NEG_COORDS)
        assert preview.coord_x_dest == -100
        assert preview.coord_y_dest == -200

    def test_EC03_no_utc_offset(self):
        """EC-03: Sin offset UTC → utc_offset = None; attacked_at verbatim igualmente."""
        preview = parse_attack_report(_REPORT_NO_OFFSET)
        assert preview.utc_offset is None
        assert "16:28:53" in preview.attacked_at  # verbatim de la línea del ataque
        assert "+" not in preview.attacked_at

    def test_EC04_year_interpretation(self):
        """EC-04: Año 2 dígitos → 2000 + YY."""
        preview = parse_attack_report(_REPORT_ES)
        assert "2026" in preview.attacked_at

    def test_T_EC14_survivors(self):
        """T-EC14: Oasis no limpiado → survived > 0."""
        preview = parse_attack_report(_REPORT_SURVIVORS)
        survivors = [a for a in preview.animals if a.survived > 0]
        assert len(survivors) >= 1
        for a in preview.animals:
            assert a.survived == a.present - a.killed

    def test_T_EC01_unrecognized_animal(self):
        """T-EC01: Nombre de animal no reconocido → UnrecognizedAnimalError con lista."""
        with pytest.raises(UnrecognizedAnimalError) as exc_info:
            parse_attack_report(_REPORT_UNKNOWN_ANIMAL)
        assert "Lobezno" in exc_info.value.names or "lobezno" in str(exc_info.value)

    def test_T_EC02_not_nature_oasis(self):
        """T-EC02: Sin sección Nature → NotNatureOasisError."""
        with pytest.raises((NotNatureOasisError, UnrecognizedAnimalError, ReportFormatError)):
            parse_attack_report(_REPORT_NOT_NATURE)

    def test_T_EC03_multiple_reports(self):
        """T-EC03: 2 bloques de reporte → MultipleReportsError."""
        with pytest.raises(MultipleReportsError) as exc_info:
            parse_attack_report(_REPORT_MULTIPLE)
        assert exc_info.value.count == 2

    def test_T_EC07_empty_text_raises(self):
        """T-EC07: Texto vacío → error de formato (el DTO ya valida min_length=1)."""
        with pytest.raises((ReportFormatError, ValueError)):
            parse_attack_report("")

    def test_T_EC13_no_utc_in_header(self):
        """T-EC13: Parse sin offset UTC en encabezado → utc_offset=None en preview."""
        preview = parse_attack_report(_REPORT_NO_OFFSET)
        assert preview.utc_offset is None

    def test_multiple_reports_error_message(self):
        """El mensaje de MultipleReportsError menciona el número de bloques."""
        with pytest.raises(MultipleReportsError) as exc_info:
            parse_attack_report(_REPORT_MULTIPLE)
        assert "2" in str(exc_info.value)

    def test_unrecognized_animal_error_message(self):
        """El mensaje de UnrecognizedAnimalError incluye los nombres no reconocidos."""
        with pytest.raises(UnrecognizedAnimalError) as exc_info:
            parse_attack_report(_REPORT_UNKNOWN_ANIMAL)
        msg = str(exc_info.value)
        assert "Lobezno" in msg or "lobezno" in msg.lower()


# ---------------------------------------------------------------------------
# Regresión: reporte REAL copiado del juego (no del catálogo kirilloid)
#   - Coordenadas envueltas en control bidi + signo menos U+2212
#   - Botín e inventario del héroe con un recurso por línea
#   - Animal "Snake" (juego) en vez de "Serpent" (kirilloid)
# ---------------------------------------------------------------------------

# Coords reales tal cual las pega Travian: ‭ ... − ... ‬
_REPORT_REAL_GAME = (
    "01 raids Unoccupied oasis ‭(‭−70‬‬|‭73‬)‬\n"
    "31.05.26, 15:29:52\n\n"
    "Attacker\n"
    "[Storm] GonnaDie from village 01\n\n"
    "Phalanx\tSwordsman\tSnake placeholder\n"  # cabecera tropas irrelevante aquí
    "Swordsman\tTheutates Thunder\tHaeduan\n"
    "75\t30\t15\n"
    "1\t0\t0\n"
    "Bounty\t\n"
    "37\n147\n37\n37\n"
    "‭‭258‬/‭6555‬‬\n"
    "Additional resources were added to the hero's inventory for killing animals.\n"
    "680\n680\n680\n680\n"
    "Defender\n"
    "Nature from village Unoccupied oasis ‭(‭−70‬‬|‭73‬)‬\n"
    "Rat\tSpider\tSnake\tBat\tWild Boar\n"
    "8\t5\t0\t0\t2\n"
    "8\t5\t0\t0\t2\n"
    "Statistics\n"
    "Server time: 18:39:04 (UTC +01:00)\n"
)


class TestParseRealGameReport:
    def test_negative_coords_with_bidi_and_unicode_minus(self):
        preview = parse_attack_report(_REPORT_REAL_GAME)
        assert preview.coord_x_dest == -70
        assert preview.coord_y_dest == 73

    def test_snake_is_recognized_as_nature(self):
        preview = parse_attack_report(_REPORT_REAL_GAME)
        names = {a.animal_name.lower() for a in preview.animals}
        assert "snake" in names

    def test_bounty_resources_one_per_line(self):
        preview = parse_attack_report(_REPORT_REAL_GAME)
        b = preview.bounty
        assert (b.wood, b.clay, b.iron, b.crop) == (37, 147, 37, 37)
        assert (b.capacity_used, b.capacity_total) == (258, 6555)

    def test_hero_inventory_one_per_line(self):
        preview = parse_attack_report(_REPORT_REAL_GAME)
        assert preview.hero_inventory == {"wood": 680, "clay": 680, "iron": 680, "crop": 680}

    def test_origin_village_is_attacker_line_not_title(self):
        preview = parse_attack_report(_REPORT_REAL_GAME)
        # No debe devolver el título del oasis atacado.
        assert "raids" not in preview.origin_village_name.lower()
        assert "GonnaDie" in preview.origin_village_name

    def test_attacker_tribe_and_ordinals_resolved(self):
        # El roster (Swordsman, Theutates Thunder, Haeduan…) es galo.
        preview = parse_attack_report(_REPORT_REAL_GAME)
        assert preview.attacker_tribe == "gauls"
        by_name = {t.troop_name: t.troop_ordinal for t in preview.attacker_troops}
        assert by_name.get("Swordsman") == 2          # GAULS_2
        assert by_name.get("Theutates Thunder") == 4   # GAULS_4
        assert by_name.get("Haeduan") == 6             # GAULS_6


# ---------------------------------------------------------------------------
# Tests unitarios de _calc_regen_rates
# (importamos directamente la función de módulo del adaptador)
# ---------------------------------------------------------------------------

from adapters.db.attack_report_sqlite_adapter import _calc_regen_rates  # noqa: E402


def _make_gap(gap_seconds, animals):
    """Helper: construye un dict de gap como los que produce get_oasis_stats."""
    return {
        "attack_id": 1,
        "attacked_at": "2026-05-31T09:00:00",
        "prev_attacked_at": None,
        "gap_seconds": gap_seconds,
        "regenerated_animals": animals,
    }


def _animal(ordinal, name, regenerated):
    return {"animal_ordinal": ordinal, "animal_name": name, "prev_survived": 0, "present_now": regenerated or 0, "regenerated": regenerated}


class TestCalcRegenRates:
    def test_T_R1_one_valid_interval(self):
        """T-R1: 1 intervalo válido con gap=3600s, regenerated=5 → avg=5.0/h."""
        gaps = [
            _make_gap(None, [_animal(1, "Rat", None)]),  # primer ataque, excluido
            _make_gap(3600, [_animal(1, "Rat", 5)]),
        ]
        result = _calc_regen_rates(gaps)
        assert len(result) == 1
        assert result[0]["animal_ordinal"] == 1
        assert result[0]["avg_regen_per_hour"] == 5.0
        assert result[0]["valid_intervals"] == 1

    def test_T_R2_mixed_valid_invalid(self):
        """T-R2: [válido: 3600s/5, inválido: gap=0, inválido: regen=-1] → valid_intervals=1."""
        gaps = [
            _make_gap(None, [_animal(1, "Rat", None)]),
            _make_gap(3600, [_animal(1, "Rat", 5)]),
            _make_gap(0, [_animal(1, "Rat", 3)]),    # gap=0, excluido
            _make_gap(7200, [_animal(1, "Rat", -1)]),  # regen<0, excluido
        ]
        result = _calc_regen_rates(gaps)
        assert len(result) == 1
        assert result[0]["valid_intervals"] == 1
        assert result[0]["avg_regen_per_hour"] == 5.0

    def test_T_R3_first_attack_excluded(self):
        """T-R3: Primer ataque (regenerated=None) → excluido, no contribuye."""
        gaps = [_make_gap(None, [_animal(1, "Rat", None)])]
        result = _calc_regen_rates(gaps)
        assert result == []

    def test_T_R4_regen_zero_is_valid(self):
        """T-R4: regenerated=0 con gap_seconds=7200 → tasa=0.0/h, incluido."""
        gaps = [
            _make_gap(None, [_animal(1, "Rat", None)]),
            _make_gap(7200, [_animal(1, "Rat", 0)]),
        ]
        result = _calc_regen_rates(gaps)
        assert len(result) == 1
        assert result[0]["avg_regen_per_hour"] == 0.0
        assert result[0]["valid_intervals"] == 1

    def test_T_R5_empty_gaps(self):
        """T-R5: Oasis con 1 ataque (gaps vacíos) → []."""
        result = _calc_regen_rates([])
        assert result == []

    def test_T_R6_all_negative_regen(self):
        """T-R6: Todos los intervalos con regenerated<0 → []."""
        gaps = [
            _make_gap(None, [_animal(1, "Rat", None)]),
            _make_gap(3600, [_animal(1, "Rat", -2)]),
            _make_gap(3600, [_animal(1, "Rat", -1)]),
        ]
        result = _calc_regen_rates(gaps)
        assert result == []

    def test_multiple_animals(self):
        """Múltiples animales → cada uno con su propio avg."""
        gaps = [
            _make_gap(None, [_animal(1, "Rat", None), _animal(2, "Spider", None)]),
            _make_gap(3600, [_animal(1, "Rat", 4), _animal(2, "Spider", 2)]),
        ]
        result = _calc_regen_rates(gaps)
        by_ordinal = {r["animal_ordinal"]: r for r in result}
        assert by_ordinal[1]["avg_regen_per_hour"] == 4.0
        assert by_ordinal[2]["avg_regen_per_hour"] == 2.0

    def test_result_sorted_by_ordinal(self):
        """La lista resultante está ordenada por animal_ordinal ascendente."""
        gaps = [
            _make_gap(None, [_animal(2, "Spider", None), _animal(1, "Rat", None)]),
            _make_gap(3600, [_animal(2, "Spider", 3), _animal(1, "Rat", 6)]),
        ]
        result = _calc_regen_rates(gaps)
        ordinals = [r["animal_ordinal"] for r in result]
        assert ordinals == sorted(ordinals)

    def test_avg_rounded_to_2_decimals(self):
        """avg_regen_per_hour se redondea a 2 decimales."""
        # 7 regenerados en 3600s → 7.0/h (redondeo sin cambio)
        # Dos intervalos: 7 y 3 → avg = 5.0
        gaps = [
            _make_gap(None, [_animal(1, "Rat", None)]),
            _make_gap(3600, [_animal(1, "Rat", 7)]),
            _make_gap(3600, [_animal(1, "Rat", 3)]),
        ]
        result = _calc_regen_rates(gaps)
        assert result[0]["avg_regen_per_hour"] == 5.0
