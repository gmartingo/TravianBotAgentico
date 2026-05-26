"""
Tests unitarios del JsonTranslationAdapter (sección 12.1 del spec i18n-backend).

Usa catálogos temporales en disco para probar carga, fallback, override y error handling.
"""
import json
import pytest
from pathlib import Path

from adapters.translations.json_translation_adapter import JsonTranslationAdapter
from core.entities.tribe import Tribe
from core.exceptions import TroopNotFoundError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BUILDINGS_BASE = {
    "1": {"alias": "woodcutter",  "es": "Leñador",         "en": "Woodcutter", "de": "", "fr": "", "ru": ""},
    "2": {"alias": "clay_pit",    "es": "Hoyo de arcilla", "en": "Clay Pit",   "de": "Tongrube", "fr": "", "ru": ""},
    "3": {"alias": "iron_mine",   "es": "Mina de hierro",  "en": "Iron Mine",  "de": "", "fr": "", "ru": ""},
}

TROOPS_BASE = {
    "ROMANS_1":  {"es": "Legionario",  "en": "Legionnaire", "de": "", "fr": "", "ru": ""},
    "ROMANS_2":  {"es": "Pretoriano",  "en": "Praetorian",  "de": "", "fr": "", "ru": ""},
    "GAULS_1":   {"es": "Falanx",      "en": "Phalanx",     "de": "Phalanx DE", "fr": "", "ru": ""},
}

MESSAGES_BASE = {
    "ACCOUNT_NOT_FOUND": {
        "es": "Cuenta {account_id} no encontrada",
        "en": "Account {account_id} not found",
        "de": "Konto {account_id} nicht gefunden",
        "fr": "", "ru": "",
    },
}


@pytest.fixture
def catalog_dirs(tmp_path: Path):
    """
    Crea directorios base y override con los catálogos mínimos de prueba.
    Override vacío por defecto; los tests que necesitan override lo rellenan.
    """
    base_dir = tmp_path / "base"
    override_dir = tmp_path / "override"
    base_dir.mkdir()
    override_dir.mkdir()

    (base_dir / "buildings.json").write_text(json.dumps(BUILDINGS_BASE), encoding="utf-8")
    (base_dir / "troops.json").write_text(json.dumps(TROOPS_BASE), encoding="utf-8")
    (base_dir / "messages.json").write_text(json.dumps(MESSAGES_BASE), encoding="utf-8")

    (override_dir / "buildings.json").write_text("{}", encoding="utf-8")
    (override_dir / "troops.json").write_text("{}", encoding="utf-8")
    (override_dir / "messages.json").write_text("{}", encoding="utf-8")

    return base_dir, override_dir


@pytest.fixture
def adapter(catalog_dirs):
    base_dir, override_dir = catalog_dirs
    return JsonTranslationAdapter(base_dir=base_dir, override_dir=override_dir)


# ---------------------------------------------------------------------------
# 12.1 — get_building_name
# ---------------------------------------------------------------------------

def test_get_building_name_idioma_existente(adapter):
    assert adapter.get_building_name(1, "en") == "Woodcutter"


def test_get_building_name_fallback_a_es(adapter):
    # gid=1 no tiene traducción en "de" (vacío) → fallback a "es"
    assert adapter.get_building_name(1, "de") == "Leñador"


def test_get_building_name_gid_inexistente(adapter):
    # Nunca lanza excepción; devuelve string de fallback
    result = adapter.get_building_name(999, "en")
    assert result == "building_999"


# ---------------------------------------------------------------------------
# 12.1 — get_all_buildings
# ---------------------------------------------------------------------------

def test_get_all_buildings_lang_servido_correcto(adapter):
    items = adapter.get_all_buildings("en")
    for item in items:
        assert item["lang_servido"] == "en"
        assert item["nombre"]  # no vacío


def test_get_all_buildings_fallback_lang_servido_es(adapter):
    # gid=1 no tiene "de" → lang_servido="es"
    items = adapter.get_all_buildings("de")
    item_gid1 = next(i for i in items if i["gid"] == 1)
    assert item_gid1["lang_servido"] == "es"
    assert item_gid1["nombre"] == "Leñador"


def test_get_all_buildings_fallback_mixto(adapter):
    # gid=2 SÍ tiene "de" ("Tongrube"); gid=1 NO tiene "de" → fallback "es"
    items = adapter.get_all_buildings("de")
    item_gid1 = next(i for i in items if i["gid"] == 1)
    item_gid2 = next(i for i in items if i["gid"] == 2)
    assert item_gid1["lang_servido"] == "es"
    assert item_gid2["lang_servido"] == "de"
    assert item_gid2["nombre"] == "Tongrube"


# ---------------------------------------------------------------------------
# 12.1 — get_troop_name
# ---------------------------------------------------------------------------

def test_get_troop_name_idioma_existente(adapter):
    assert adapter.get_troop_name(Tribe.ROMANS, 1, "en") == "Legionnaire"


def test_get_troop_name_fallback_a_es(adapter):
    # Romanos no tienen "de" → fallback a "es"
    assert adapter.get_troop_name(Tribe.ROMANS, 1, "de") == "Legionario"


def test_get_troop_name_ordinal_inexistente(adapter):
    with pytest.raises(TroopNotFoundError):
        adapter.get_troop_name(Tribe.ROMANS, 15, "en")


# ---------------------------------------------------------------------------
# 12.1 — get_troop_names_by_tribe
# ---------------------------------------------------------------------------

def test_get_troop_names_by_tribe_lang_servido_correcto(adapter):
    items = adapter.get_troop_names_by_tribe(Tribe.ROMANS, "es")
    assert len(items) == 2  # solo ROMANS_1 y ROMANS_2 en catálogo de prueba
    for item in items:
        assert item["lang_servido"] == "es"


def test_get_troop_names_by_tribe_fallback_lang_servido_es(adapter):
    # ROMANS no tienen "de" → todos lang_servido="es"
    items = adapter.get_troop_names_by_tribe(Tribe.ROMANS, "de")
    for item in items:
        assert item["lang_servido"] == "es"


def test_get_troop_names_by_tribe_sin_tropas(adapter):
    # Teutons no está en el catálogo de prueba → TroopNotFoundError
    with pytest.raises(TroopNotFoundError):
        adapter.get_troop_names_by_tribe(Tribe.TEUTONS, "es")


# ---------------------------------------------------------------------------
# 12.1 — get_message
# ---------------------------------------------------------------------------

def test_get_message_con_params(adapter):
    msg = adapter.get_message("ACCOUNT_NOT_FOUND", "en", account_id=42)
    assert msg == "Account 42 not found"


def test_get_message_fallback_a_es(adapter):
    # "fr" vacío en catálogo de prueba → fallback a "es"
    msg = adapter.get_message("ACCOUNT_NOT_FOUND", "fr", account_id=7)
    assert msg == "Cuenta 7 no encontrada"


def test_get_message_code_desconocido(adapter):
    result = adapter.get_message("UNKNOWN_CODE", "en", foo="bar")
    assert "UNKNOWN_CODE" in result


# ---------------------------------------------------------------------------
# 12.1 — Override gana sobre base
# ---------------------------------------------------------------------------

def test_override_gana_sobre_base(tmp_path):
    base_dir = tmp_path / "base"
    override_dir = tmp_path / "override"
    base_dir.mkdir()
    override_dir.mkdir()

    base = {"1": {"alias": "woodcutter", "es": "Leñador Base", "en": "Woodcutter Base", "de": "", "fr": "", "ru": ""}}
    override = {"1": {"alias": "woodcutter", "es": "Leñador Override", "en": "Woodcutter Override", "de": "", "fr": "", "ru": ""}}

    (base_dir / "buildings.json").write_text(json.dumps(base), encoding="utf-8")
    (base_dir / "troops.json").write_text("{}", encoding="utf-8")
    (base_dir / "messages.json").write_text("{}", encoding="utf-8")

    (override_dir / "buildings.json").write_text(json.dumps(override), encoding="utf-8")
    (override_dir / "troops.json").write_text("{}", encoding="utf-8")
    (override_dir / "messages.json").write_text("{}", encoding="utf-8")

    adapter = JsonTranslationAdapter(base_dir=base_dir, override_dir=override_dir)
    assert adapter.get_building_name(1, "es") == "Leñador Override"
    assert adapter.get_building_name(1, "en") == "Woodcutter Override"


# ---------------------------------------------------------------------------
# 12.1 — Startup errors
# ---------------------------------------------------------------------------

def test_startup_con_base_ausente_lanza_error(tmp_path):
    base_dir = tmp_path / "base"
    override_dir = tmp_path / "override"
    base_dir.mkdir()
    override_dir.mkdir()
    # No creamos buildings.json en base_dir
    with pytest.raises(RuntimeError, match="buildings.json"):
        JsonTranslationAdapter(base_dir=base_dir, override_dir=override_dir)


def test_startup_con_json_corrupto_lanza_error(tmp_path):
    base_dir = tmp_path / "base"
    override_dir = tmp_path / "override"
    base_dir.mkdir()
    override_dir.mkdir()

    (base_dir / "buildings.json").write_text("NOT VALID JSON", encoding="utf-8")
    (base_dir / "troops.json").write_text("{}", encoding="utf-8")
    (base_dir / "messages.json").write_text("{}", encoding="utf-8")

    with pytest.raises(RuntimeError):
        JsonTranslationAdapter(base_dir=base_dir, override_dir=override_dir)


def test_startup_con_override_ausente_ok(tmp_path):
    base_dir = tmp_path / "base"
    override_dir = tmp_path / "override"
    base_dir.mkdir()
    override_dir.mkdir()

    (base_dir / "buildings.json").write_text(json.dumps(BUILDINGS_BASE), encoding="utf-8")
    (base_dir / "troops.json").write_text(json.dumps(TROOPS_BASE), encoding="utf-8")
    (base_dir / "messages.json").write_text(json.dumps(MESSAGES_BASE), encoding="utf-8")
    # override_dir existe pero sin archivos → deben ignorarse silenciosamente

    adapter = JsonTranslationAdapter(base_dir=base_dir, override_dir=override_dir)
    assert adapter.get_building_name(1, "es") == "Leñador"


# ---------------------------------------------------------------------------
# 12.1 — Idioma es-ES truncado a es
# ---------------------------------------------------------------------------

def test_idioma_es_ES_truncado_a_es(adapter):
    """
    get_language ya normaliza "es-ES" → "es" antes de llamar al adaptador.
    Este test verifica que el adaptador funciona igual con lang="es" (ya normalizado).
    """
    result_es = adapter.get_building_name(1, "es")
    # Simular que el adaptador recibe "es" (ya truncado por get_language)
    assert result_es == "Leñador"
