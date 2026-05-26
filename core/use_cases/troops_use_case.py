"""
Use case del bloque TROOPS.

Enriquece los DTOs crudos del parser con nombres localizados e iconos
(tropas vía resolve_troop_display; edificios vía translation_port + game_data_port).

Hexagonal: este módulo vive en core/ y NO importa nada de adapters/. Recibe los
datos YA PARSEADOS (el router del adapter llama al parser) y depende de
TranslationPort y GameDataPort, que son PUERTOS del core.

Por qué los métodos son async:
  - resolve_troop_display llama a game_data_port.get_troop_stats(), que es async.
  - get_training llama a game_data_port.get_building_catalog(), que es async.
  La lógica de enriquecimiento de tropas y edificios es parte del use case,
  por lo que el use case hereda la asincronía de los puertos.

RN-10: NO usa VillageMapUseCase — el game_id se extrae de cada fila del HTML.
RN-09: lang governa troop_types[].name, troop_names y buildings[].name.
"""
from __future__ import annotations

from core.dtos.troops_dto import (
    BuildingInfo,
    TroopTypeInfo,
    TroopsHospitalResponse,
    TroopsOwnResponse,
    TroopsSmithyResponse,
    TroopsSupportResponse,
    TroopsTrainingResponse,
)
from core.ports.game_data_port import GameDataPort
from core.ports.translation_port import TranslationPort
from core.use_cases.troop_display import resolve_troop_display


class TroopsUseCase:
    """
    Use case del bloque troops.

    Cada método:
      1. Recibe los datos crudos del parser (DTOs con troop_types: list[str]).
      2. Enriquece troop_types / troop_names / buildings con nombres localizados e iconos.
      3. Devuelve el DTO de respuesta final.

    Todos los métodos son async porque los puertos de datos (game_data_port)
    tienen métodos async (get_troop_stats, get_building_catalog).

    Las excepciones del port (SessionNotActiveError, OverviewPageNotLoadedError,
    OverviewFixtureNotFoundError) se propagan desde el router — este use case no
    las lanza ni las envuelve: solo procesa datos ya parseados.
    """

    @staticmethod
    async def get_own(
        raw: TroopsOwnResponse,
        lang: str,
        translation_port: TranslationPort,
        game_data_port: GameDataPort,
    ) -> TroopsOwnResponse:
        """
        Tropas totales (ejército máximo) por aldea.
        GET /game/troops/{world_id}/own
        """
        troop_types = []
        for unn in raw.troop_types:
            display = await resolve_troop_display(unn, lang, translation_port, game_data_port)
            troop_types.append(
                TroopTypeInfo(
                    unit_class=display["unit_class"],
                    name=display["name"],
                    icon_url=display["icon_url"],
                )
            )
        return TroopsOwnResponse(
            troop_types=troop_types,
            villages=raw.villages,
            totals=raw.totals,
        )

    @staticmethod
    async def get_support(
        raw: TroopsSupportResponse,
        lang: str,
        translation_port: TranslationPort,
        game_data_port: GameDataPort,
    ) -> TroopsSupportResponse:
        """
        Tropas presentes en cada aldea en el momento de la consulta.
        GET /game/troops/{world_id}/support
        """
        all_unns: set[str] = set()
        for v in raw.villages:
            all_unns.update(v.own.keys())
            all_unns.update(v.nature.keys())

        troop_names: dict[str, str] = {}
        for unn in all_unns:
            display = await resolve_troop_display(unn, lang, translation_port, game_data_port)
            troop_names[unn] = display["name"]

        return TroopsSupportResponse(villages=raw.villages, troop_names=troop_names)

    @staticmethod
    async def get_smithy(
        raw: TroopsSmithyResponse,
        lang: str,
        translation_port: TranslationPort,
        game_data_port: GameDataPort,
    ) -> TroopsSmithyResponse:
        """
        Nivel de mejora de tropas en herrería por aldea + investigación activa.
        GET /game/troops/{world_id}/smithy
        """
        troop_types = []
        for unn in raw.troop_types:
            display = await resolve_troop_display(unn, lang, translation_port, game_data_port)
            troop_types.append(
                TroopTypeInfo(
                    unit_class=display["unit_class"],
                    name=display["name"],
                    icon_url=display["icon_url"],
                )
            )
        return TroopsSmithyResponse(troop_types=troop_types, villages=raw.villages)

    @staticmethod
    async def get_hospital(
        raw: TroopsHospitalResponse,
        lang: str,
        translation_port: TranslationPort,
        game_data_port: GameDataPort,
    ) -> TroopsHospitalResponse:
        """
        Heridos por tipo y estado del hospital de cada aldea.
        GET /game/troops/{world_id}/hospital
        """
        troop_types = []
        for unn in raw.troop_types:
            display = await resolve_troop_display(unn, lang, translation_port, game_data_port)
            troop_types.append(
                TroopTypeInfo(
                    unit_class=display["unit_class"],
                    name=display["name"],
                    icon_url=display["icon_url"],
                )
            )
        return TroopsHospitalResponse(
            player_tribe=raw.player_tribe,
            troop_types=troop_types,
            villages=raw.villages,
        )

    @staticmethod
    async def get_training(
        raw: TroopsTrainingResponse,
        lang: str,
        translation_port: TranslationPort,
        game_data_port: GameDataPort,
    ) -> TroopsTrainingResponse:
        """
        Tiempo de cola restante en edificios de entrenamiento por aldea.
        GET /game/troops/{world_id}/training

        Edificios de training: enriquece con name (get_building_name) + icon_url.
        icon_url se obtiene de get_building_catalog(gid).icon_id → /static/icons/{id}.png.
        Hoy building_catalog está vacío → icon_url=None (forward-compatible).
        """
        buildings = []
        for gid in raw.building_gids:
            name = translation_port.get_building_name(gid, lang)
            # Intentar obtener icon_id del catálogo de edificios (puede ser None hoy)
            catalog = await game_data_port.get_building_catalog(gid)
            icon_id = catalog.get("icon_id") if catalog else None
            icon_url = f"/static/icons/{icon_id}.png" if icon_id else None
            buildings.append(BuildingInfo(gid=gid, name=name, icon_url=icon_url))

        return TroopsTrainingResponse(
            buildings=buildings,
            building_gids=raw.building_gids,
            villages=raw.villages,
        )
