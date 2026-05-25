"""
Endpoints de datos de juego — stats de tropas, stats de edificios e iconos.

GET /catalog/troops/{tribe}/stats      — stats numéricos de tropas por tribu
GET /catalog/buildings/{gid}/stats     — stats numéricos de un edificio por gid (todos los niveles)
GET /catalog/icons                     — metadatos de iconos PNG

Todos heredan el middleware Cache-Control (rutas bajo /catalog/ → public, max-age=3600).

Política de idioma para /catalog/troops/{tribe}/stats y /catalog/buildings/{gid}/stats:
  Selección con precedencia ?lang= > Accept-Language > todos:
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
        "Filtros opcionales: icon_type ('troop', 'stat', 'upgrade', 'building') y tribe. "
        "Lista vacía (200) si ningún icono cumple los filtros — no es un 404. "
        "Los iconos binarios se sirven directamente desde /static/icons/{icon_id}.png."
    ),
)
async def list_icons(
    icon_type: Literal["troop", "stat", "upgrade", "building"] | None = Query(
        default=None,
        description="Filtra por tipo de icono: troop, stat, upgrade o building",
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


# ---------------------------------------------------------------------------
# DTOs — edificios (stats por nivel)
# ---------------------------------------------------------------------------


class BuildingLevel(BaseModel):
    """Un nivel de edificio con sus costes y efectos."""

    level: int
    cost_wood: int | None = None
    cost_clay: int | None = None
    cost_iron: int | None = None
    cost_crop: int | None = None
    cost_sum: int | None = None
    upkeep: int | None = None
    culture_points: int | None = None
    build_time_s: int | None = None
    effect_value: int | None = None
    effect_label: str | None = None


class BuildingStatsCatalogResponse(BaseModel):
    """Respuesta de GET /catalog/buildings/{gid}/stats."""

    model_config = ConfigDict(extra="forbid")

    gid: int
    server_version: str
    alias: str
    category: str | None
    description: str | None
    language: dict[str, str]
    icon_url: str | None
    levels: list[BuildingLevel]


# ---------------------------------------------------------------------------
# Endpoint — stats de un edificio por gid
# ---------------------------------------------------------------------------


@router.get(
    "/catalog/buildings/{gid}/stats",
    response_model=BuildingStatsCatalogResponse,
    summary="Stats de niveles de un edificio",
    description=(
        "Devuelve los costes y efectos de todos los niveles de un edificio "
        "identificado por su gid (entero positivo). "
        "Selección de idioma con la siguiente precedencia (explícito gana a implícito): "
        "1) ?lang=<código> — override explícito en query string; "
        "2) Accept-Language (header) — preferencia estándar del cliente; "
        "3) sin ninguno → language con todos los idiomas disponibles (~25 claves). "
        "Devuelve 400 si cualquier valor presente no está entre los 25 idiomas soportados. "
        "Devuelve 404 si el gid no tiene datos de stats cargados en la BD. "
        "FastAPI valida el path param gid como entero (422 si es inválido). "
        "La respuesta incluye Vary: Accept-Language."
    ),
)
async def get_building_stats(
    gid: int,
    response: Response,
    server_version: str = Query(default="1.45", description="Versión del servidor Travian"),
    lang: str | None = Depends(resolve_language),
    game_data_port: GameDataPort = Depends(get_game_data_port),
    translation_port: TranslationPort = Depends(get_translation_port),
) -> BuildingStatsCatalogResponse:
    """
    Handler de GET /catalog/buildings/{gid}/stats.

    Inyecta DOS puertos:
      - game_data_port   — stats numéricos y metadatos desde SQLite
      - translation_port — nombre del edificio

    Política de language (resolve_language con precedencia ?lang= > Accept-Language > None):
      - lang is None → se devuelven todos los idiomas vía get_building_all_langs.
      - lang tiene valor → se devuelve solo ese idioma con fallback 'es'.

    El 404 incluye server_version en el detail para facilitar el debug.
    """
    response.headers["Vary"] = "Accept-Language"

    levels = await game_data_port.get_building_stats(gid, server_version)
    catalog_meta = await game_data_port.get_building_catalog(gid, server_version)

    if not levels and catalog_meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No hay datos de stats para el edificio gid={gid} "
                f"con server_version='{server_version}'"
            ),
        )

    # Nombre localizado
    if lang is None:
        language = translation_port.get_building_all_langs(gid)
    else:
        nombre = translation_port.get_building_name(gid, lang)
        language = {lang: nombre}

    icon_id = catalog_meta.get("icon_id") if catalog_meta else None
    icon_url = f"/static/icons/{icon_id}.png" if icon_id else None

    return BuildingStatsCatalogResponse(
        gid=gid,
        server_version=server_version,
        alias=catalog_meta.get("alias", "") if catalog_meta else "",
        category=catalog_meta.get("category") if catalog_meta else None,
        description=catalog_meta.get("description") if catalog_meta else None,
        language=language,
        icon_url=icon_url,
        levels=[BuildingLevel(**row) for row in levels],
    )


# ---------------------------------------------------------------------------
# DTOs — mejoras de herrería por tropa
# ---------------------------------------------------------------------------


class TroopUpgradeLevel(BaseModel):
    """
    Un nivel de mejora de herrería para una tropa.

    stats: solo contiene los stat_names que aplican a esa unidad
           (p.ej. Legionario romano solo tendrá "attack" y "def_cavalry").
    """

    level: int
    cost_wood: int | None = None
    cost_clay: int | None = None
    cost_iron: int | None = None
    cost_crop: int | None = None
    cost_sum: int | None = None
    upgrade_time_s: int | None = None
    stats: dict[str, float]        # {stat_name: stat_value} — solo los visibles


class TroopUpgradesResponse(BaseModel):
    """Respuesta de GET /catalog/troops/{tribe}/{ordinal}/upgrades."""

    model_config = ConfigDict(extra="forbid")

    tribe: str
    ordinal: int
    server_version: str
    levels: list[TroopUpgradeLevel]


# ---------------------------------------------------------------------------
# Endpoint — mejoras de herrería de una tropa
# ---------------------------------------------------------------------------


@router.get(
    "/catalog/troops/{tribe}/{ordinal}/upgrades",
    response_model=TroopUpgradesResponse,
    summary="Mejoras de herrería de una tropa",
    description=(
        "Devuelve la tabla de mejoras de herrería de una tropa identificada "
        "por su tribu y ordinal (posición dentro de la tribu, empieza en 1). "
        "Los niveles se devuelven agrupados: cada nivel tiene sus costes y el mapa "
        "de stats con los valores de ese nivel. Solo aparecen los stats que aplican "
        "a la unidad (las columnas con display:none en kirilloid se omiten). "
        "Devuelve 404 si no hay datos de mejora para esa tropa/tribu/versión. "
        "FastAPI valida tribe contra el enum Tribe (422 si es inválido). "
        "Accept-Language es OPCIONAL en este endpoint: la respuesta no contiene "
        "texto localizado. Si se envía y el idioma no está soportado → 400. "
        "Si no se envía → 200 igualmente (no hay campo 'language' en la respuesta)."
    ),
)
async def get_troop_upgrades(
    tribe: Tribe,
    ordinal: int,
    server_version: str = Query(default="1.45", description="Versión del servidor Travian"),
    lang: str | None = Depends(resolve_language),
    game_data_port: GameDataPort = Depends(get_game_data_port),
) -> TroopUpgradesResponse:
    """
    Handler de GET /catalog/troops/{tribe}/{ordinal}/upgrades.

    Política de Accept-Language:
      - La respuesta es puramente numérica (niveles, costes, valores de mejora).
      - No hay texto localizado → Accept-Language no modifica la respuesta.
      - Se acepta igualmente via resolve_language para coherencia futura y para
        validar que los valores enviados sean idiomas del catálogo soportado (400
        si viene un idioma no soportado, evitando que el cliente asuma que funciona
        cuando en realidad el idioma no existe en ningún endpoint del proyecto).
      - Si no se envía → 200 sin campo language.
    """
    raw_rows = await game_data_port.get_troop_upgrades(tribe, ordinal, server_version)

    if not raw_rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No hay datos de mejora para la tropa ordinal={ordinal} "
                f"de la tribu '{tribe.value}' con server_version='{server_version}'"
            ),
        )

    # Agrupar por nivel: {level: {cost_*, upgrade_time_s, stats: {}}}
    levels_by_num: dict[int, dict] = {}
    for row in raw_rows:
        lvl = row["level"]
        if lvl not in levels_by_num:
            levels_by_num[lvl] = {
                "level":          lvl,
                "cost_wood":      row.get("cost_wood"),
                "cost_clay":      row.get("cost_clay"),
                "cost_iron":      row.get("cost_iron"),
                "cost_crop":      row.get("cost_crop"),
                "cost_sum":       row.get("cost_sum"),
                "upgrade_time_s": row.get("upgrade_time_s"),
                "stats":          {},
            }
        # stat_value puede ser None si la BD lo tiene NULL; float si tiene valor
        stat_val = row.get("stat_value")
        if stat_val is not None:
            levels_by_num[lvl]["stats"][row["stat_name"]] = stat_val

    levels = [
        TroopUpgradeLevel(**data)
        for data in sorted(levels_by_num.values(), key=lambda d: d["level"])
    ]

    return TroopUpgradesResponse(
        tribe=tribe.value,
        ordinal=ordinal,
        server_version=server_version,
        levels=levels,
    )
