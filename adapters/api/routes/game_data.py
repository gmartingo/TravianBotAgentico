"""
Endpoints de datos de juego — stats de tropas e iconos.

GET /catalog/troops/{tribe}/stats  — stats numéricos de tropas por tribu
GET /catalog/icons                 — metadatos de iconos PNG

Ambos heredan el middleware Cache-Control (rutas bajo /catalog/ → public, max-age=3600).

Política de idioma:
  - /catalog/troops/{tribe}/stats → selección con precedencia ?lang= > Accept-Language > todos:
      ?lang=<código> presente y válido → language con ese idioma (+ fallback 'es');
      Accept-Language presente y válido → language con ese idioma (+ fallback 'es');
      sin ninguno → language con todos los idiomas disponibles (~25 claves);
      valor presente pero no soportado (en cualquiera) → 400.
      La respuesta incluye Vary: Accept-Language.
  - /catalog/icons → Accept-Language OBLIGATORIA. El endpoint no devuelve campo `language`,
      pero mantener la cabecera obligatoria preserva la coherencia del catálogo autenticado
      y reserva la capacidad de filtrar por idioma en el futuro sin romper el contrato.

Los DTOs de este módulo son distintos a los de catalog.py:
  - catalog.py devuelve nombres localizados (TranslationPort)
  - game_data.py devuelve stats numéricos + campo language (GameDataPort + TranslationPort)
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict

from adapters.api.dependencies import get_game_data_port, get_language, resolve_language, get_translation_port
from core.entities.tribe import Tribe
from core.exceptions import TroopNotFoundError
from core.ports.game_data_port import GameDataPort
from core.ports.translation_port import TranslationPort

router = APIRouter(tags=["game_data"])


# ---------------------------------------------------------------------------
# DTOs — creados en este módulo, NO en catalog.py (responsabilidades distintas)
# ---------------------------------------------------------------------------


class TroopStatsItem(BaseModel):
    """
    Stats de una tropa con su nombre localizado.
    Abierto (sin extra='forbid') para extensibilidad futura.
    Stats opcionales (NULL en BD) se serializan como null en JSON.
    """
    ordinal: int
    key: str
    is_playable: bool
    language: dict[str, str]   # {lang_servido: nombre}
    attack: int | None
    def_infantry: int | None
    def_cavalry: int | None
    speed: int | None
    carry: int | None
    cost_wood: int | None
    cost_clay: int | None
    cost_iron: int | None
    cost_crop: int | None
    cost_sum: int | None
    upkeep: int | None
    train_time_s: int | None
    icon_url: str | None       # URL relativa al StaticFiles mount, o null


class TroopStatsCatalogResponse(BaseModel):
    """Wrapper de respuesta de /catalog/troops/{tribe}/stats."""
    model_config = ConfigDict(extra="forbid")

    tribe: str
    server_version: str
    troops: list[TroopStatsItem]


class IconItem(BaseModel):
    """
    Metadatos de un icono PNG.
    Abierto para extensibilidad futura.
    """
    icon_id: str
    icon_type: str             # "troop" | "stat" | "upgrade"
    tribe: str | None
    ordinal: int | None
    stat_name: str | None
    url: str                   # URL relativa al StaticFiles mount
    width_px: int
    height_px: int


class IconListResponse(BaseModel):
    """Wrapper de respuesta de /catalog/icons."""
    model_config = ConfigDict(extra="forbid")

    icons: list[IconItem]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/catalog/troops/{tribe}/stats",
    response_model=TroopStatsCatalogResponse,
    summary="Stats numéricos de tropas por tribu",
    description=(
        "Devuelve los stats base de todas las tropas de una tribu "
        "(ataque, defensa, velocidad, costes, etc.) con el campo language. "
        "Selección de idioma con la siguiente precedencia (explícito gana a implícito): "
        "1) ?lang=<código> — override explícito en query string; "
        "2) Accept-Language (header) — preferencia estándar del cliente; "
        "3) sin ninguno → language con todos los idiomas disponibles (~25 claves). "
        "Devuelve 400 si cualquier valor presente no está entre los 25 idiomas soportados. "
        "Devuelve 404 si la tribu no tiene datos de stats cargados en la BD. "
        "FastAPI valida el path param tribe contra el enum Tribe (422 si es inválido). "
        "La respuesta incluye Vary: Accept-Language."
    ),
)
async def get_troop_stats(
    tribe: Tribe,
    response: Response,
    server_version: str = Query(default="1.45", description="Versión del servidor Travian"),
    lang: str | None = Depends(resolve_language),
    game_data_port: GameDataPort = Depends(get_game_data_port),
    translation_port: TranslationPort = Depends(get_translation_port),
) -> TroopStatsCatalogResponse:
    """
    Handler de GET /catalog/troops/{tribe}/stats.

    Inyecta DOS puertos:
      - game_data_port — stats numéricos desde SQLite
      - translation_port — nombres de cada tropa

    Política de language (resolve_language con precedencia ?lang= > Accept-Language > None):
      - lang is None → se carga todos los idiomas vía get_troop_all_langs_by_tribe
        y se indexan por ordinal para lookup O(1).
      - lang tiene valor → se carga con get_troop_names_by_tribe (un idioma + fallback 'es').

    El 404 incluye server_version en el detail para facilitar el debug.
    """
    response.headers["Vary"] = "Accept-Language"
    all_stats = await game_data_port.get_all_troop_stats(tribe, server_version)

    if not all_stats:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No hay datos de stats para la tribu '{tribe.value}' "
                f"con server_version='{server_version}'"
            ),
        )

    # Pre-cargar traducciones una sola vez para toda la tribu
    if lang is None:
        # Todos los idiomas indexados por ordinal: {ordinal: {lang: nombre}}
        try:
            all_langs_items = translation_port.get_troop_all_langs_by_tribe(tribe)
            lang_index: dict[int, dict[str, str]] = {
                item["ordinal"]: item["language"] for item in all_langs_items
            }
        except TroopNotFoundError:
            lang_index = {}
        except Exception:
            lang_index = {}
    else:
        # Un idioma por tropa, indexado por ordinal: {ordinal: {lang_servido: nombre}}
        try:
            single_lang_items = translation_port.get_troop_names_by_tribe(tribe, lang)
            lang_index = {
                item["ordinal"]: {item["lang_servido"]: item["nombre"]}
                for item in single_lang_items
            }
        except TroopNotFoundError:
            lang_index = {}
        except Exception:
            lang_index = {}

    troops: list[TroopStatsItem] = []
    for row in all_stats:
        ordinal = row["ordinal"]
        key = f"{tribe.value.upper()}_{ordinal}"
        language = lang_index.get(ordinal, {})

        # Construir icon_url si hay icon_id registrado
        icon_id = row.get("icon_id")
        icon_url: str | None = f"/static/icons/{icon_id}.png" if icon_id else None

        troops.append(TroopStatsItem(
            ordinal=ordinal,
            key=key,
            is_playable=row["is_playable"],
            language=language,
            attack=row.get("attack"),
            def_infantry=row.get("def_infantry"),
            def_cavalry=row.get("def_cavalry"),
            speed=row.get("speed"),
            carry=row.get("carry"),
            cost_wood=row.get("cost_wood"),
            cost_clay=row.get("cost_clay"),
            cost_iron=row.get("cost_iron"),
            cost_crop=row.get("cost_crop"),
            cost_sum=row.get("cost_sum"),
            upkeep=row.get("upkeep"),
            train_time_s=row.get("train_time_s"),
            icon_url=icon_url,
        ))

    return TroopStatsCatalogResponse(
        tribe=tribe.value,
        server_version=server_version,
        troops=troops,
    )


@router.get(
    "/catalog/icons",
    response_model=IconListResponse,
    summary="Metadatos de iconos PNG",
    description=(
        "Devuelve la lista de metadatos de iconos disponibles. "
        "Filtros opcionales: icon_type ('troop', 'stat', 'upgrade') y tribe. "
        "Lista vacía (200) si ningún icono cumple los filtros — no es un 404. "
        "Los iconos binarios se sirven directamente desde /static/icons/{icon_id}.png."
    ),
)
async def list_icons(
    icon_type: Literal["troop", "stat", "upgrade"] | None = Query(
        default=None,
        description="Filtra por tipo de icono: troop, stat o upgrade",
    ),
    tribe: Tribe | None = Query(
        default=None,
        description="Filtra por tribu (solo aplica con icon_type=troop)",
    ),
    lang: str = Depends(get_language),
    game_data_port: GameDataPort = Depends(get_game_data_port),
) -> IconListResponse:
    """
    Handler de GET /catalog/icons.

    Lista vacía = 200 (semántica REST correcta para colecciones vacías).
    Los filtros combinados incorrectos (p.ej. icon_type=stat + tribe) devuelven
    200 con lista vacía — no un error.
    """
    tribe_value = tribe.value if tribe is not None else None
    icons_raw = await game_data_port.list_icons(
        icon_type=icon_type,
        tribe=tribe_value,
    )

    icons = [
        IconItem(
            icon_id=row["icon_id"],
            icon_type=row["icon_type"],
            tribe=row.get("tribe"),
            ordinal=row.get("ordinal"),
            stat_name=row.get("stat_name"),
            url=f"/static/icons/{row['icon_id']}.png",
            width_px=row["width_px"],
            height_px=row["height_px"],
        )
        for row in icons_raw
    ]

    return IconListResponse(icons=icons)
