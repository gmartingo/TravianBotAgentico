"""
Dependencias compartidas de FastAPI.
Centraliza la validación de Accept-Language para todos los endpoints.
"""
from fastapi import Header, HTTPException, status

SUPPORTED_LANGUAGES = {"es", "en", "de", "fr", "ru"}


def get_language(
    accept_language: str = Header(..., alias="Accept-Language")
) -> str:
    """
    Valida y normaliza el header Accept-Language.

    Retorna el código BCP 47 en minúsculas (ej: 'es', 'en').
    Lanza HTTP 400 si la cabecera falta o el idioma no está soportado.
    El idioma por defecto es 'es' cuando Accept-Language vale 'es'.
    """
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
