"""
Helper compartido de enriquecimiento de tropas para los use cases del core.

Consolida la lógica duplicada que antes vivía en overview_use_case.py y
troops_use_case.py (_resolve_troop_name). Añade además la resolución del
icono (icon_url) vía GameDataPort.

Por qué vive en core/use_cases/ y no en core/utils/:
  - Depende de dos puertos del core (TranslationPort, GameDataPort).
  - Es lógica de aplicación (enriquecimiento de DTO), no utilidad de parseo/string.
  - core/utils/ solo contiene helpers que no dependen de puertos (parsing.py, units.py).
  - Colocarlo aquí mantiene la dependencia dentro de la capa de use cases,
    sin cruzar fronteras hacia adapters ni hacia utils.
"""
from __future__ import annotations

from core.exceptions import TroopNotFoundError
from core.ports.game_data_port import GameDataPort
from core.ports.translation_port import TranslationPort
from core.utils.units import unit_class_to_tribe_ordinal


async def resolve_troop_display(
    unit_class: str,
    lang: str,
    translation_port: TranslationPort,
    game_data_port: GameDataPort,
) -> dict:
    """
    Resuelve nombre localizado e icon_url de una tropa a partir de su clase CSS uNN.

    Flujo:
      1. unit_class_to_tribe_ordinal(uNN) → (Tribe, ordinal) o None.
         Si None (uhero, código desconocido): name=unit_class, icon_url=None.
      2. translation_port.get_troop_name(tribe, ordinal, lang)
         Si lanza TroopNotFoundError → name=unit_class (fallback).
      3. game_data_port.get_troop_stats(tribe, ordinal) → dict o None.
         icon_id = stats.get("icon_id") if stats else None.
         icon_url = f"/static/icons/{icon_id}.png" if icon_id else None.

    Devuelve:
      {
        "unit_class": uNN,
        "name": <nombre localizado o unit_class como fallback>,
        "icon_url": <"/static/icons/{icon_id}.png" o None>,
      }

    Nunca lanza — todos los fallos producen fallback.
    """
    mapped = unit_class_to_tribe_ordinal(unit_class)
    if mapped is None:
        return {"unit_class": unit_class, "name": unit_class, "icon_url": None}

    tribe, ordinal = mapped

    # Resolver nombre localizado
    try:
        name = translation_port.get_troop_name(tribe, ordinal, lang)
        name = name if name else unit_class
    except TroopNotFoundError:
        name = unit_class

    # Resolver icon_url
    stats = await game_data_port.get_troop_stats(tribe, ordinal)
    icon_id = stats.get("icon_id") if stats else None
    icon_url = f"/static/icons/{icon_id}.png" if icon_id else None

    return {"unit_class": unit_class, "name": name, "icon_url": icon_url}
