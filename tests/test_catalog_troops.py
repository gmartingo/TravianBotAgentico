"""
Tests del endpoint GET /catalog/troops/{tribe}.

Convención de Accept-Language para este endpoint (OPCIONAL):
  - Sin cabecera      → 200, language con todos los idiomas del catálogo (~25 claves).
  - Idioma soportado  → 200, language con una sola clave (+ fallback a 'es').
  - Idioma no soportado → 400.
"""
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from adapters.api.main import app
from core.entities.tribe import Tribe
from core.exceptions import TroopNotFoundError


@pytest.fixture(scope="module")
def client():
    """Cliente de test con lifespan activado (dispara startup)."""
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# 12.3 — Casos base
# ---------------------------------------------------------------------------

def test_troops_tribu_valida_idioma_valido(client):
    response = client.get(
        "/catalog/troops/romans",
        headers={"Accept-Language": "es"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["tribe"] == "romans"
    troops = body["troops"]
    assert len(troops) == 10  # romanos tienen 10 tropas en el catálogo base
    for item in troops:
        lang_key = list(item["language"].keys())[0]
        assert lang_key == "es"
        assert item["language"][lang_key]


def test_troops_estructura_respuesta_con_idioma(client):
    """Con Accept-Language soportado, cada item tiene exactamente una clave en language."""
    response = client.get(
        "/catalog/troops/gauls",
        headers={"Accept-Language": "es"},
    )
    assert response.status_code == 200
    troops = response.json()["troops"]
    for item in troops:
        assert isinstance(item["ordinal"], int)
        assert isinstance(item["key"], str)
        assert isinstance(item["language"], dict)
        assert len(item["language"]) == 1


def test_troops_no_contiene_campo_name(client):
    """Los items NO deben tener campo `name` plano."""
    response = client.get(
        "/catalog/troops/romans",
        headers={"Accept-Language": "es"},
    )
    assert response.status_code == 200
    troops = response.json()["troops"]
    for item in troops:
        assert "name" not in item


def test_troops_no_contiene_campo_lang_wrapper(client):
    """El wrapper de la respuesta NO debe tener campo `lang`."""
    response = client.get(
        "/catalog/troops/romans",
        headers={"Accept-Language": "es"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "lang" not in body


def test_troops_sin_header_devuelve_200_todos_idiomas(client):
    """Sin Accept-Language → 200 con todos los idiomas del catálogo en cada tropa."""
    response = client.get("/catalog/troops/romans")
    assert response.status_code == 200
    body = response.json()
    assert body["tribe"] == "romans"
    troops = body["troops"]
    assert len(troops) == 10
    for item in troops:
        # Debe tener más de un idioma (al menos es y en están presentes en el catálogo base)
        assert len(item["language"]) > 1, (
            f"Se esperaban múltiples idiomas en la tropa {item['key']}, "
            f"pero solo hay {len(item['language'])}"
        )
        # Claves conocidas del catálogo base deben estar presentes
        assert "es" in item["language"]
        assert "en" in item["language"]


def test_troops_sin_header_estructura_language_es_dict_completo(client):
    """Sin cabecera, language es un dict con ~25 claves no vacías."""
    response = client.get("/catalog/troops/romans")
    assert response.status_code == 200
    first_troop = response.json()["troops"][0]
    language = first_troop["language"]
    assert isinstance(language, dict)
    # El catálogo base tiene 25 idiomas; todos deben aparecer con valor no vacío
    assert len(language) >= 10, "Se esperan al menos 10 idiomas en el catálogo base"
    for lang_code, name in language.items():
        assert isinstance(lang_code, str) and lang_code
        assert isinstance(name, str) and name.strip(), (
            f"Nombre vacío para idioma '{lang_code}' en tropa {first_troop['key']}"
        )


def test_troops_idioma_no_soportado(client):
    """Código fuera de los 25 (p.ej. 'zh') → 400."""
    response = client.get(
        "/catalog/troops/romans",
        headers={"Accept-Language": "zh"},
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Tests nuevos — 25 idiomas + ?lang= + precedencia + Vary
# ---------------------------------------------------------------------------

def test_troops_idioma_it_ahora_valido(client):
    """'it' ahora es uno de los 25 soportados → 200 (antes era 400 con SUPPORTED=5)."""
    response = client.get(
        "/catalog/troops/romans",
        headers={"Accept-Language": "it"},
    )
    assert response.status_code == 200
    troops = response.json()["troops"]
    for item in troops:
        assert len(item["language"]) == 1
        lang_key = list(item["language"].keys())[0]
        assert lang_key in ("it", "es")  # 'es' si no hay traducción en 'it'


def test_troops_idioma_ja_ahora_valido(client):
    """'ja' ahora es uno de los 25 soportados → 200."""
    response = client.get(
        "/catalog/troops/romans",
        headers={"Accept-Language": "ja"},
    )
    assert response.status_code == 200


def test_troops_lang_query_valido_devuelve_un_idioma(client):
    """?lang=en → 200 con language de una sola clave 'en' (o fallback 'es')."""
    response = client.get("/catalog/troops/romans?lang=en")
    assert response.status_code == 200
    troops = response.json()["troops"]
    assert len(troops) > 0
    for item in troops:
        assert len(item["language"]) == 1
        lang_key = list(item["language"].keys())[0]
        assert lang_key in ("en", "es")


def test_troops_lang_query_it_valido(client):
    """?lang=it → 200 (it es uno de los 25)."""
    response = client.get("/catalog/troops/gauls?lang=it")
    assert response.status_code == 200
    assert len(response.json()["troops"]) > 0


def test_troops_lang_query_invalido_devuelve_400(client):
    """?lang=xx (no existe en los 25) → 400."""
    response = client.get("/catalog/troops/romans?lang=xx")
    assert response.status_code == 400


def test_troops_lang_query_zz_invalido_devuelve_400(client):
    """?lang=zz (no existe en los 25) → 400."""
    response = client.get("/catalog/troops/romans?lang=zz")
    assert response.status_code == 400


def test_troops_precedencia_lang_query_sobre_header(client):
    """?lang=en + Accept-Language: es → gana ?lang= → devuelve idioma 'en' (o fallback 'es')."""
    response = client.get(
        "/catalog/troops/romans?lang=en",
        headers={"Accept-Language": "es"},
    )
    assert response.status_code == 200
    troops = response.json()["troops"]
    # Con ?lang=en, el idioma resuelto es 'en'; lang_servido puede ser 'en' o 'es' (fallback)
    for item in troops:
        assert len(item["language"]) == 1
        lang_key = list(item["language"].keys())[0]
        assert lang_key in ("en", "es"), f"Se esperaba 'en' o fallback 'es', se obtuvo '{lang_key}'"


def test_troops_precedencia_lang_query_gana_a_header_idioma_distinto(client):
    """
    Verifica que la clave de language NO sea la del header cuando ?lang= está presente.
    Usa mock para controlar exactamente qué devuelve el adaptador.
    """
    from unittest.mock import MagicMock
    mock_port = MagicMock()
    mock_port.get_troop_names_by_tribe.return_value = [
        {"ordinal": 1, "key": "ROMANS_1", "lang_servido": "en", "nombre": "Legionary"},
    ]
    original_port = app.state.translation_port
    app.state.translation_port = mock_port
    try:
        response = client.get(
            "/catalog/troops/romans?lang=en",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        # get_troop_names_by_tribe debe haberse llamado con 'en' (no con 'es')
        call_args = mock_port.get_troop_names_by_tribe.call_args
        assert call_args is not None
        # El segundo argumento (lang) debe ser 'en'
        lang_arg = call_args[0][1] if call_args[0] else call_args[1].get("lang")
        assert lang_arg == "en", f"Se esperaba llamada con 'en' pero fue con '{lang_arg}'"
    finally:
        app.state.translation_port = original_port


def test_troops_sin_lang_query_ni_header_devuelve_todos(client):
    """Sin ?lang= ni Accept-Language → todos los idiomas (>1 clave)."""
    response = client.get("/catalog/troops/romans")
    assert response.status_code == 200
    troops = response.json()["troops"]
    assert len(troops) > 0
    for item in troops:
        assert len(item["language"]) > 1


def test_troops_header_it_devuelve_200(client):
    """Accept-Language: it → 200 (it está en los 25)."""
    response = client.get(
        "/catalog/troops/romans",
        headers={"Accept-Language": "it"},
    )
    assert response.status_code == 200


def test_troops_vary_header_presente(client):
    """La respuesta incluye Vary: Accept-Language."""
    response = client.get(
        "/catalog/troops/romans",
        headers={"Accept-Language": "es"},
    )
    assert response.status_code == 200
    vary = response.headers.get("vary", "")
    assert "Accept-Language" in vary, f"Vary esperado 'Accept-Language', obtenido: '{vary}'"


def test_troops_vary_header_sin_accept_language(client):
    """La respuesta incluye Vary: Accept-Language incluso sin cabecera."""
    response = client.get("/catalog/troops/romans")
    assert response.status_code == 200
    vary = response.headers.get("vary", "")
    assert "Accept-Language" in vary


def test_troops_tribu_invalida(client):
    """Tribu no válida en el enum → FastAPI devuelve 422 automáticamente."""
    response = client.get(
        "/catalog/troops/persians",
        headers={"Accept-Language": "es"},
    )
    assert response.status_code == 422


def test_troops_cache_control_header(client):
    response = client.get(
        "/catalog/troops/romans",
        headers={"Accept-Language": "es"},
    )
    assert response.status_code == 200
    assert response.headers.get("cache-control") == "public, max-age=3600"


def test_troops_todas_las_tribus(client):
    """Verificar que las 5 tribus devuelven 200."""
    for tribe in ["romans", "teutons", "gauls", "egyptians", "huns"]:
        response = client.get(
            f"/catalog/troops/{tribe}",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200, f"Tribu {tribe} falló con {response.status_code}"
        assert response.json()["tribe"] == tribe


def test_troops_fallback_de_idioma_servido_es(client):
    """
    Con Accept-Language: de y NINGUNA tropa con traducción en 'de',
    el campo language lleva clave 'es' (fallback granular a español).

    El mock inyecta datos controlados: tres tropas sin clave 'de',
    independientemente de lo que tenga el fichero troops.json en disco.
    """
    mock_port = MagicMock()
    # Datos controlados: tres tropas romanas, NINGUNA con 'de' → todas deben hacer fallback
    mock_port.get_troop_names_by_tribe.return_value = [
        {"ordinal": 1, "key": "ROMANS_1", "lang_servido": "es", "nombre": "Legionario"},
        {"ordinal": 2, "key": "ROMANS_2", "lang_servido": "es", "nombre": "Pretoriano"},
        {"ordinal": 3, "key": "ROMANS_3", "lang_servido": "es", "nombre": "Imperiano"},
    ]

    original_port = app.state.translation_port
    app.state.translation_port = mock_port
    try:
        response = client.get(
            "/catalog/troops/romans",
            headers={"Accept-Language": "de"},
        )
        assert response.status_code == 200
        troops = response.json()["troops"]
        assert len(troops) == 3
        for item in troops:
            assert len(item["language"]) == 1
            lang_key = list(item["language"].keys())[0]
            # El adaptador decidió que no había 'de' y devolvió lang_servido='es'
            assert lang_key == "es", (
                f"Se esperaba fallback a 'es' pero se obtuvo '{lang_key}' "
                f"en la tropa {item['key']}"
            )
            assert item["language"][lang_key], "El nombre no debe estar vacío"
    finally:
        app.state.translation_port = original_port


def test_troops_fallback_de_idioma_servido_mixto(client):
    """
    Con Accept-Language: de, items CON traducción en 'de' tienen clave 'de'
    e items SIN ella tienen clave 'es'. Exactamente una clave por item.

    El mock inyecta datos controlados: una tropa con 'de' y otra sin ella,
    independientemente de lo que tenga el fichero troops.json en disco.
    """
    mock_port = MagicMock()
    # Datos controlados: primera tropa con 'de' disponible, segunda hace fallback a 'es'
    mock_port.get_troop_names_by_tribe.return_value = [
        {"ordinal": 1, "key": "ROMANS_1", "lang_servido": "de", "nombre": "Legionär"},
        {"ordinal": 2, "key": "ROMANS_2", "lang_servido": "es", "nombre": "Pretoriano"},
    ]

    original_port = app.state.translation_port
    app.state.translation_port = mock_port
    try:
        response = client.get(
            "/catalog/troops/romans",
            headers={"Accept-Language": "de"},
        )
        assert response.status_code == 200
        troops = response.json()["troops"]
        assert len(troops) == 2

        # Tropa 1: tenía 'de' → se sirve 'de'
        item_de = troops[0]
        assert len(item_de["language"]) == 1
        assert list(item_de["language"].keys())[0] == "de"
        assert item_de["language"]["de"] == "Legionär"

        # Tropa 2: no tenía 'de' → fallback a 'es'
        item_es = troops[1]
        assert len(item_es["language"]) == 1
        assert list(item_es["language"].keys())[0] == "es"
        assert item_es["language"]["es"] == "Pretoriano"
    finally:
        app.state.translation_port = original_port


def test_troops_tribu_valida_sin_tropas_devuelve_404(client):
    """
    Tribu válida en enum pero sin entradas en catálogo → 404 con idioma explícito.
    Mockea el adaptador para lanzar TroopNotFoundError.
    """
    mock_port = MagicMock()
    mock_port.get_troop_names_by_tribe.side_effect = TroopNotFoundError(
        tribe=Tribe.ROMANS, ordinal=None
    )

    original_port = app.state.translation_port
    app.state.translation_port = mock_port
    try:
        response = client.get(
            "/catalog/troops/romans",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 404
        assert "romans" in response.json()["detail"].lower()
    finally:
        app.state.translation_port = original_port


def test_troops_tribu_valida_sin_tropas_sin_header_devuelve_404(client):
    """
    Tribu válida en enum pero sin entradas en catálogo y sin Accept-Language → 404.
    La ruta sin cabecera usa get_troop_all_langs_by_tribe, que también lanza TroopNotFoundError.
    """
    mock_port = MagicMock()
    mock_port.get_troop_all_langs_by_tribe.side_effect = TroopNotFoundError(
        tribe=Tribe.ROMANS, ordinal=None
    )

    original_port = app.state.translation_port
    app.state.translation_port = mock_port
    try:
        response = client.get("/catalog/troops/romans")
        assert response.status_code == 404
        assert "romans" in response.json()["detail"].lower()
    finally:
        app.state.translation_port = original_port


def test_troops_cabeceras_minimas(client):
    """Verificar presencia de las cabeceras mínimas de seguridad."""
    response = client.get(
        "/catalog/troops/romans",
        headers={"Accept-Language": "es"},
    )
    assert response.status_code == 200
    headers = response.headers
    assert "application/json" in headers.get("content-type", "")
    assert "utf-8" in headers.get("content-type", "").lower()
    assert headers.get("x-request-id")
    assert headers.get("x-api-version") == "0.1.0"
    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("x-frame-options") == "DENY"


def test_troops_x_request_id_eco(client):
    """Si el cliente envía X-Request-ID, debe volver idéntico en la respuesta."""
    known_id = "troop-test-request-id-99"
    response = client.get(
        "/catalog/troops/romans",
        headers={"Accept-Language": "es", "X-Request-ID": known_id},
    )
    assert response.status_code == 200
    assert response.headers.get("x-request-id") == known_id


def test_troops_sin_header_cabeceras_minimas(client):
    """Sin Accept-Language, las cabeceras mínimas de seguridad siguen presentes."""
    response = client.get("/catalog/troops/romans")
    assert response.status_code == 200
    headers = response.headers
    assert "application/json" in headers.get("content-type", "")
    assert headers.get("x-request-id")
    assert headers.get("x-api-version") == "0.1.0"
    assert headers.get("x-content-type-options") == "nosniff"


def test_troops_todas_tribus_sin_header(client):
    """Todas las tribus devuelven 200 sin Accept-Language."""
    for tribe in ["romans", "teutons", "gauls", "egyptians", "huns"]:
        response = client.get(f"/catalog/troops/{tribe}")
        assert response.status_code == 200, (
            f"Tribu {tribe} falló sin header con {response.status_code}"
        )
        assert response.json()["tribe"] == tribe
