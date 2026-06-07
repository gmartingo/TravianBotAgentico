"""
Hook transversal del radar de ataques entrantes — Componente A.

check_sidebar_attacks es el ÚNICO punto de invocación del radar del sidebar.
Se llama desde WorldAgent._post_page_hook con el HTML ya cargado.

REGLAS (no negociables):
  - NO hace ningún browser.get ni petición HTTP adicional (RN-01, RN-19).
  - NO se cablea desde login.py ni desde adapters individuales (RN-21).
  - Si #sidebarBoxVillageList no está en el HTML → no-op silencioso,
    sin loggear nada (RN-19, EC-01).
  - Nunca propaga excepciones — loggea WARNING y retorna lista vacía (EC-15).
  - El WorldAgent encola CHECK_INCOMING_ATTACK_DETAIL con retraso variable
    de 3-15 s al detectar ataques (RN-22) — esa lógica vive en el WorldAgent,
    no aquí.

Ver spec docs/specs/radar-ataques-entrantes.md §9.1, §4 RN-01/RN-19/RN-21.
Añadido en la feature radar-ataques-entrantes (2026-06-05).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from adapters.browser.parsers.incoming_attack_sidebar_parser import (
    IncomingAttackSidebarParser,
)
from core.dtos.incoming_attack_dto import VillageUnderAttackDTO
from core.ports.incoming_attack_db_port import IncomingAttackDbPort, IncomingAttackRecord

logger = logging.getLogger(__name__)


async def check_sidebar_attacks(
    page_html: str,
    world_id: int,
    db_port: IncomingAttackDbPort,
) -> list[VillageUnderAttackDTO]:
    """
    Hook transversal. Llamado desde WorldAgent._post_page_hook con el HTML ya cargado.

    NO hace ninguna petición HTTP adicional — usa el HTML que ya tiene el caller.
    NO se llama desde login.py ni desde adapters individuales (RN-19, RN-21).
    Nunca propaga excepciones; loggea WARNING y retorna lista vacía ante cualquier error.

    Si #sidebarBoxVillageList no está en el HTML → retorna [] sin loggear
    (no-op silencioso — RN-19).

    Devuelve la lista de VillageUnderAttackDTO detectadas (puede ser vacía).
    """
    try:
        attacks = IncomingAttackSidebarParser.parse(page_html)
        if attacks:
            await _persist_attacks(attacks, world_id, db_port)
        return attacks
    except Exception as exc:
        logger.warning("Radar sidebar falló: %s", exc)
        return []


async def _persist_attacks(
    attacks: list[VillageUnderAttackDTO],
    world_id: int,
    db_port: IncomingAttackDbPort,
) -> None:
    """
    Persiste cada aldea bajo ataque en BD con source='sidebar'.

    impact_at es None porque el sidebar no proporciona timer (se completará en Comp. B).
    attack_count es 1 como mínimo conservador (el sidebar no da la cantidad exacta).
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    for dto in attacks:
        await db_port.upsert_attack(IncomingAttackRecord(
            world_id=world_id,
            village_game_id=dto.village_game_id,
            village_name=dto.village_name,
            village_coord_x=dto.coord_x,
            village_coord_y=dto.coord_y,
            attack_count=1,          # sidebar no conoce la cantidad exacta
            impact_at=None,          # tampoco tiene timer; se completará en Comp. B
            source="sidebar",
            detected_at=now_iso,
            updated_at=now_iso,
        ))
