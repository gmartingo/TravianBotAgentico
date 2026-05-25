"""
Dependencias compartidas de FastAPI.
Centraliza la validación de Accept-Language para todos los endpoints,
y provee los singletons de puertos inicializados en el lifespan.

Variantes de validación de idioma:
  - get_language          → obligatoria: 400 si falta O si el idioma no está soportado.
  - get_language_optional → opcional: None si falta (devuelve todos los idiomas),
                            código validado si presente y soportado,
                            400 si presente pero NO soportado.

Helper de resolución con precedencia explícita > implícita:
  - resolve_language(lang_query, accept_language) → str | None
      Prioridad: ?lang= (query) > Accept-Language (header) > None (todos los idiomas).
      None significa "el handler debe devolver todos los idiomas".
      Lanza HTTP 400 si cualquiera de los dos tiene un valor presente pero inválido.
"""
from fastapi import Header, HTTPException, Query, Request, status

from core.i18n.languages import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES
from core.ports.game_data_port import GameDataPort
from core.ports.translation_port import TranslationPort


def _validate_lang_code(raw: str, source: str) -> str:
    """
    Normaliza y valida un código de idioma (strip + lower + quitar región).
    Lanza HTTP 400 si el código no está en SUPPORTED_LANGUAGES.
    source: nombre descriptivo del origen ('Accept-Language' o '?lang') para el mensaje.
    """
    code = raw.strip().lower().split("-")[0]
    if code not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Idioma '{raw}' no soportado en {source}. "
                f"Valores válidos: {sorted(SUPPORTED_LANGUAGES)}"
            ),
        )
    return code


def get_language(
    accept_language: str | None = Header(default=None, alias="Accept-Language")
) -> str:
    """
    Valida y normaliza el header Accept-Language (versión obligatoria).

    Retorna el código en minúsculas (ej: 'es', 'en').
    Lanza HTTP 400 si la cabecera falta o el idioma no está soportado.

    Se declara como opcional (default=None) para que FastAPI no devuelva 422
    cuando el header falta — en ese caso lanzamos nosotros el 400 explícito.
    """
    if accept_language is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Cabecera 'Accept-Language' obligatoria. "
                f"Valores válidos: {sorted(SUPPORTED_LANGUAGES)}"
            ),
        )
    return _validate_lang_code(accept_language, "Accept-Language")


def get_language_optional(
    accept_language: str | None = Header(default=None, alias="Accept-Language")
) -> str | None:
    """
    Valida y normaliza el header Accept-Language (versión opcional).

    Retorna:
      - None         si la cabecera no se envía   → el handler devuelve todos los idiomas.
      - str (código) si la cabecera es válida      → el handler devuelve solo ese idioma.
    Lanza HTTP 400 si la cabecera está presente pero el idioma no está soportado.

    La diferencia con get_language es que la ausencia de cabecera NO es error;
    se usa en endpoints de catálogo que quieren devolver todos los idiomas cuando
    el cliente no especifica ninguno.
    """
    if accept_language is None:
        return None
    return _validate_lang_code(accept_language, "Accept-Language")


def resolve_language(
    lang: str | None = Query(
        default=None,
        description=(
            "Código de idioma explícito (p. ej. 'es', 'en', 'it'). "
            "Tiene precedencia sobre la cabecera Accept-Language. "
            "Si se omite, se usa Accept-Language; si tampoco hay cabecera, "
            "se devuelven todos los idiomas disponibles (~25). "
            f"Valores válidos: {sorted(SUPPORTED_LANGUAGES)}"
        ),
    ),
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
) -> str | None:
    """
    Resuelve el idioma con la siguiente precedencia (explícito gana a implícito):
      1. ?lang=<código>          — override explícito en query string.
      2. Accept-Language header  — preferencia declarada del cliente.
      3. None                    — sin preferencia → el handler devuelve todos los idiomas.

    Lanza HTTP 400 si cualquiera de los dos tiene un valor presente pero inválido.
    Retorna None cuando no hay ninguna preferencia de idioma → todos los idiomas.
    """
    if lang is not None:
        return _validate_lang_code(lang, "?lang")
    if accept_language is not None:
        return _validate_lang_code(accept_language, "Accept-Language")
    return None


def get_translation_port(request: Request) -> TranslationPort:
    """
    Devuelve el singleton de TranslationPort almacenado en app.state.
    Se inicializa en el lifespan de la aplicación.
    """
    return request.app.state.translation_port


def get_game_data_port(request: Request) -> GameDataPort:
    """
    Devuelve el singleton de GameDataPort almacenado en app.state.
    Se inicializa en el lifespan de la aplicación junto al translation_port.
    """
    return request.app.state.game_data_port
