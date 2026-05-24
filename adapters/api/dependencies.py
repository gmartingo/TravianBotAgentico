"""
Dependencias compartidas de FastAPI.
Centraliza la validación de Accept-Language para todos los endpoints.
"""
from fastapi import Header, HTTPException, Request, status

from core.i18n.languages import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES
from core.ports.translation_port import TranslationPort


def get_language(
    accept_language: str | None = Header(default=None, alias="Accept-Language")
) -> str:
    """
    Valida y normaliza el header Accept-Language.

    Retorna el código BCP 47 en minúsculas (ej: 'es', 'en').
    Lanza HTTP 400 si la cabecera falta o el idioma no está soportado.
    El idioma por defecto es 'es' cuando Accept-Language vale 'es'.

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
    code = accept_language.strip().lower().split("-")[0]
    if code not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Idioma '{accept_language}' no soportado. "
                f"Valores válidos: {sorted(SUPPORTED_LANGUAGES)}"
            ),
        )
    return code


def get_translation_port(request: Request) -> TranslationPort:
    """
    Devuelve el singleton de TranslationPort almacenado en app.state.
    Se inicializa en el startup de la aplicación.
    """
    return request.app.state.translation_port
