"""
Use case: cálculo del coste en recursos de tropas atacantes muertas.

Extraído del router `adapters/api/routes/attack_reports.py` al core para
respetar la arquitectura hexagonal (lógica de negocio fuera de los adaptadores).

El router mantiene `_compute_attacker_cost_loss` como wrapper que delega aquí
para no romper EP-01 (backward compatible).

Ver spec docs/specs/bd-ataques-oasis-balance-perdidos-robados.md §9.2.
Añadido en la feature bd-ataques-oasis-balance-perdidos-robados (2026-06-01).
"""
from __future__ import annotations

from core.entities.tribe import Tribe


async def compute_attacker_cost_loss(
    troops: list,
    tribe_str: str | None,
    game_data_port,  # GameDataPort | None
) -> dict:
    """
    Calcula el coste en recursos de tropas atacantes perdidas.

    Para cada tropa con `lost > 0` y `troop_ordinal` conocido, multiplica su
    coste unitario de entrenamiento (cost_wood/clay/iron/crop del catálogo
    kirilloid) por las bajas.

    Requiere:
      - tribe_str: tribu del atacante como string (p.ej. 'gauls').
      - game_data_port: puerto con `get_all_troop_stats(tribe)`.
      - troops: lista de AttackerTroopEntry o cualquier objeto con atributos
        `lost`, `troop_ordinal` (o dicts con las mismas claves).

    Devuelve {wood, clay, iron, crop, total} con todo 0 si:
      - tribe_str es None o vacío.
      - game_data_port es None.
      - No hay tropas con lost > 0 y ordinal conocido.
      - La tribu no es un valor Tribe válido.
    """
    if not tribe_str or game_data_port is None:
        return {"wood": 0, "clay": 0, "iron": 0, "crop": 0, "total": 0}

    try:
        tribe = Tribe(tribe_str)
    except ValueError:
        return {"wood": 0, "clay": 0, "iron": 0, "crop": 0, "total": 0}

    stats = await game_data_port.get_all_troop_stats(tribe)
    cost_by_ordinal = {s["ordinal"]: s for s in stats}

    wood = clay = iron = crop = 0
    for t in troops:
        # Soporte tanto para objetos (AttackerTroopEntry) como dicts
        if hasattr(t, "lost"):
            lost = t.lost
            ordinal = t.troop_ordinal
        else:
            lost = t.get("lost", 0)
            ordinal = t.get("troop_ordinal")

        if not lost or ordinal is None:
            continue

        s = cost_by_ordinal.get(ordinal)
        if not s:
            continue

        wood += lost * (s.get("cost_wood") or 0)
        clay += lost * (s.get("cost_clay") or 0)
        iron += lost * (s.get("cost_iron") or 0)
        crop += lost * (s.get("cost_crop") or 0)

    total = wood + clay + iron + crop
    return {"wood": wood, "clay": clay, "iron": iron, "crop": crop, "total": total}
