"""
Use case del bloque overview.

Enriquece los datos parseados de la tabla #overview con:
  - el nombre de cada aldea (del índice VillageMap, por game_id)
  - el nombre localizado y el icon_url de cada tipo de tropa presente
    (vía resolve_troop_display, que combina translation_port + game_data_port)

Hexagonal: este use case vive en core/ y NO importa nada de adapters/. Recibe los
datos YA parseados (el handler llama al parser del adapter) y depende de
TranslationPort y GameDataPort, que son PUERTOS del core.

Por qué execute es async:
  - resolve_troop_display llama a game_data_port.get_troop_stats(), que es async
    (implementación SQLite con aiosqlite). La lógica de enriquecimiento de tropas
    es parte del use case, por lo que el use case hereda la asincronía.
"""
from __future__ import annotations

from core.dtos.overview_dto import (
    BuildingInProgressDTO,
    OverviewResponseDTO,
    OverviewVillageDTO,
    TroopMovementDTO,
    TroopPresentDTO,
)
from core.ports.game_data_port import GameDataPort
from core.ports.translation_port import TranslationPort
from core.use_cases.troop_display import resolve_troop_display


class OverviewUseCase:
    """Construye el OverviewResponseDTO a partir de datos parseados + índice de aldeas + idioma."""

    @staticmethod
    async def execute(
        world_id: int,
        parsed_villages: list[dict],
        village_names: dict[int, str],
        lang: str,
        translation_port: TranslationPort,
        game_data_port: GameDataPort,
    ) -> OverviewResponseDTO:
        """
        Combina los datos del parser de #overview con el índice de nombres de aldea
        (VillageMap) y enriquece las tropas presentes con nombre localizado e icon_url.

        village_names: {game_id: nombre} obtenido de VillageMapUseCase. Si una aldea
        del parser no está en el índice, su `name` queda "" (EC-10 — inconsistencia,
        no se inventa nombre).

        execute es async porque resolve_troop_display llama a game_data_port.get_troop_stats()
        que es un método async del puerto.
        """
        villages: list[OverviewVillageDTO] = []
        for v in parsed_villages:
            game_id = v["game_id"]
            movements = [
                TroopMovementDTO(movement_type=m["movement_type"], quantity=m["quantity"])
                for m in v["movements"]
            ]
            buildings = [
                BuildingInProgressDTO(
                    building_name=b["building_name"],
                    name=b["building_name"],
                    name_source="server_lang",
                )
                for b in v["buildings_under_construction"]
            ]
            troops = []
            for t in v["troops_present"]:
                display = await resolve_troop_display(
                    unit_class=t["unit_class"],
                    lang=lang,
                    translation_port=translation_port,
                    game_data_port=game_data_port,
                )
                troops.append(
                    TroopPresentDTO(
                        unit_class=display["unit_class"],
                        name=display["name"],
                        quantity=t["quantity"],
                        icon_url=display["icon_url"],
                    )
                )
            villages.append(
                OverviewVillageDTO(
                    game_id=game_id,
                    name=village_names.get(game_id, ""),
                    movements=movements,
                    buildings_under_construction=buildings,
                    troops_present=troops,
                    merchants_free=v["merchants_free"],
                    merchants_total=v["merchants_total"],
                )
            )
        return OverviewResponseDTO(world_id=world_id, lang=lang, villages=villages)
