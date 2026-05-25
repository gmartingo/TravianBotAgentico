"""
Endpoints del catálogo de Travian: edificios y tropas con traducciones.

GET /catalog/buildings        — todos los edificios con nombre localizado
GET /catalog/troops/{tribe}   — tropas de una tribu con nombre localizado

/catalog/buildings exige Accept-Language y devuelve Cache-Control: public, max-age=3600.
/catalog/troops/{tribe} acepta idioma mediante dos mecanismos con esta precedencia:
  1. ?lang=<código> (query string) — override explícito; tiene precedencia sobre el header.
  2. Accept-Language (header)      — preferencia estándar del cliente.
  3. Ninguno de los dos            — devuelve todos los idiomas del catálogo (~25 claves).
  Error 400 si cualquier valor presente no está entre los 25 soportados.
  La respuesta incluye siempre Vary: Accept-Language.
El campo `language` de cada item tiene como clave(s) el/los idiomas realmente servidos.
"""
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict

from adapters.api.dependencies import get_language, resolve_language, get_translation_port
from core.entities.tribe import Tribe
from core.exceptions import TroopNotFoundError
from core.ports.translation_port import TranslationPort

router = APIRouter(tags=["catalog"])

# ---------------------------------------------------------------------------
# DTOs — diseñados para extensibilidad (sección 7 del spec i18n-backend)
# ---------------------------------------------------------------------------


class BuildingItem(BaseModel):
    """
    Item de edificio en la respuesta del catálogo.
    Abierto (sin extra="forbid") para recibir futuros campos de datos de juego
    (levels, cost, build_time_s) sin romper el contrato actual.

    Campos reservados para la feature "datos de juego" (fuera de alcance ahora):
    # levels: list[BuildingLevel] | None = None
    # cost: ResourceCost | None = None
    # build_time_s: int | None = None
    """

    gid: int
    alias: str
    language: dict[str, str]  # {lang_servido: nombre}


class BuildingsCatalogResponse(BaseModel):
    """Wrapper de la respuesta de /catalog/buildings. Cerrado (extra="forbid")."""

    model_config = ConfigDict(extra="forbid")

    buildings: list[BuildingItem]


class TroopItem(BaseModel):
    """
    Item de tropa en la respuesta del catálogo.
    Abierto (sin extra="forbid") para recibir futuros campos de datos de juego
    (attack, defense, speed, carry) sin romper el contrato actual.

    Campos reservados para la feature "datos de juego":
    # attack: int | None = None
    # defense: int | None = None
    # speed: int | None = None
    # carry: int | None = None
    """

    ordinal: int
    key: str
    language: dict[str, str]  # {lang_servido: nombre}


class TroopsCatalogResponse(BaseModel):
    """Wrapper de la respuesta de /catalog/troops/{tribe}. Cerrado (extra="forbid")."""

    model_config = ConfigDict(extra="forbid")

    tribe: str  # valor del enum Tribe en minúsculas (ej. "romans")
    troops: list[TroopItem]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/catalog/buildings",
    response_model=BuildingsCatalogResponse,
    summary="Catálogo de edificios de Travian",
    description=(
        "Devuelve todos los edificios con su nombre en el idioma solicitado. "
        "Si falta la traducción para un item concreto, el campo `language` lleva "
        "la clave 'es' (fallback granular — visible item a item)."
    ),
)
def get_buildings_catalog(
    lang: str = Depends(get_language),
    translation_port: TranslationPort = Depends(get_translation_port),
) -> BuildingsCatalogResponse:
    items_raw = translation_port.get_all_buildings(lang)
    buildings = [
        BuildingItem(
            gid=item["gid"],
            alias=item["alias"],
            language={item["lang_servido"]: item["nombre"]},
        )
        for item in items_raw
    ]
    return BuildingsCatalogResponse(buildings=buildings)


@router.get(
    "/catalog/troops/{tribe}",
    response_model=TroopsCatalogResponse,
    summary="Catálogo de tropas por tribu",
    description=(
        "Devuelve las tropas de una tribu con su nombre localizado. "
        "Selección de idioma con la siguiente precedencia (explícito gana a implícito): "
        "1) ?lang=<código> — override explícito en query string; "
        "2) Accept-Language (header) — preferencia estándar del cliente; "
        "3) sin ninguno → language contiene todos los idiomas disponibles (~25 claves). "
        "Devuelve 400 si cualquier valor presente no está entre los 25 idiomas soportados. "
        "FastAPI valida el path param contra el enum Tribe (422 si es inválido). "
        "Si la tribu no tiene tropas en el catálogo, devuelve 404. "
        "La respuesta incluye Vary: Accept-Language."
    ),
)
def get_troops_catalog(
    tribe: Tribe,
    response: Response,
    lang: str | None = Depends(resolve_language),
    translation_port: TranslationPort = Depends(get_translation_port),
) -> TroopsCatalogResponse:
    from fastapi import HTTPException
    response.headers["Vary"] = "Accept-Language"
    if lang is None:
        # Sin ninguna preferencia de idioma → devolver todos los idiomas disponibles
        try:
            items_raw = translation_port.get_troop_all_langs_by_tribe(tribe)
        except TroopNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"No hay tropas definidas para la tribu '{tribe.value}' en el catálogo",
            )
        troops = [
            TroopItem(
                ordinal=item["ordinal"],
                key=item["key"],
                language=item["language"],
            )
            for item in items_raw
        ]
    else:
        # Idioma resuelto (vía ?lang= o Accept-Language) → un solo idioma con fallback a 'es'
        try:
            items_raw = translation_port.get_troop_names_by_tribe(tribe, lang)
        except TroopNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"No hay tropas definidas para la tribu '{tribe.value}' en el catálogo",
            )
        troops = [
            TroopItem(
                ordinal=item["ordinal"],
                key=item["key"],
                language={item["lang_servido"]: item["nombre"]},
            )
            for item in items_raw
        ]
    return TroopsCatalogResponse(tribe=tribe.value, troops=troops)
