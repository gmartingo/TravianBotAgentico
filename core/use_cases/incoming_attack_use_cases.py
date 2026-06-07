"""
Use cases del radar de ataques entrantes.

ListIncomingAttacksUseCase  — lista ataques entrantes para un mundo (EP-RA01).
CheckIncomingAttackUseCase  — dispara la lectura del radar (EP-RA02).

La API consume estos use cases; los handlers NO contienen lógica de negocio.

seconds_remaining se calcula aquí (en el use case), no en el handler:
  - null  si impact_at IS NULL (ataque detectado solo vía sidebar, sin timer aún)
  - max(0, int(delta.total_seconds())) si impact_at no es NULL

Frontera hexagonal:
  - El core NO importa adapters ni librerías de infra.
  - CheckIncomingAttackUseCase recibe el callable 'fetch_dorf1_attacks' inyectado
    desde la capa de adapters (el handler o el lifespan lo construye). El callable
    devuelve list[Dorf1AttackDTO] ya parseados — el parsing ocurre en adapters.

Ver spec docs/specs/radar-ataques-entrantes.md §8 EP-RA01/EP-RA02, §10.
Añadido en la feature radar-ataques-entrantes (2026-06-05).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Callable, Awaitable

from core.exceptions import WorldNotFoundError
from core.dtos.incoming_attack_dto import Dorf1AttackDTO

if TYPE_CHECKING:
    from core.ports.incoming_attack_db_port import IncomingAttackDbPort


def _calc_seconds_remaining(impact_at: str | None) -> int | None:
    """
    Calcula los segundos restantes hasta el impacto.

    - Si impact_at es None → None (sin timer todavía, solo del sidebar)
    - Si impact_at no es None → max(0, int(delta.total_seconds()))

    El resultado nunca es negativo (EC-17, §10).
    """
    if impact_at is None:
        return None
    try:
        # impact_at es ISO-8601 UTC (puede terminar en 'Z' o '+00:00' o sin zona)
        ts = impact_at.replace("Z", "+00:00")
        impact_dt = datetime.fromisoformat(ts)
        if impact_dt.tzinfo is None:
            # Si no tiene zona, asumimos UTC (defensivo)
            impact_dt = impact_dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = (impact_dt - now).total_seconds()
        return max(0, int(delta))
    except (ValueError, TypeError):
        return None


class ListIncomingAttacksUseCase:
    """
    Lista ataques entrantes para un mundo.

    Calcula seconds_remaining en el use case, no en el handler.
    """

    def __init__(self, db_port: "IncomingAttackDbPort") -> None:
        self._db = db_port

    async def execute(
        self,
        world_id: int,
        include_past: bool = False,
        village_game_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
        db_port_for_world_check=None,
    ) -> dict:
        """
        Lista ataques entrantes pendientes para un mundo.

        Lanza WorldNotFoundError si el mundo no existe (404).
        Devuelve: { items, total, limit, offset }
        Cada item incluye seconds_remaining calculado en este use case.
        """
        # Verificar existencia del mundo si se proporciona el puerto de cuentas
        if db_port_for_world_check is not None:
            try:
                await db_port_for_world_check.get_world(world_id)
            except Exception:
                raise WorldNotFoundError(world_id)

        result = await self._db.list_attacks(
            world_id=world_id,
            include_past=include_past,
            village_game_id=village_game_id,
            limit=limit,
            offset=offset,
        )

        # Enriquecer cada item con seconds_remaining (calculado aquí, no en el handler)
        enriched_items = []
        for item in result["items"]:
            impact_at = item.get("impact_at")
            seconds_remaining = _calc_seconds_remaining(impact_at)
            enriched_items.append({
                **item,
                "seconds_remaining": seconds_remaining,
                # Exponer attacker_snapshot (JSON opaco) tal como está en BD
                "attacker_snapshot": item.get("attacker_snapshot_json"),
            })

        return {
            "items": enriched_items,
            "total": result["total"],
            "limit": limit,
            "offset": offset,
        }


class SummaryIncomingAttacksUseCase:
    """
    Devuelve el recuento de ataques pendientes agrupado por mundo (EP-RA03).

    Diseñado para el badge de la lista de Mundos del frontend: una sola petición
    HTTP devuelve todos los mundos, incluso los que tienen 0 ataques, para que el
    frontend pueda inicializar badges sin una segunda petición.

    pending_attacks = filas con impact_at IS NULL (sidebar sin timer) OR
                      impact_at > datetime('now') (ataque todavía en el futuro).
    Postura conservadora (RT-05): los ataques sin timer se cuentan como pendientes.

    Ver spec docs/specs/radar-ataques-entrantes.md §8 EP-RA03.
    """

    def __init__(self, db_port: "IncomingAttackDbPort") -> None:
        self._db = db_port

    async def execute(self) -> list[dict]:
        """
        Devuelve [{world_id: int, pending_attacks: int}] para todos los mundos.

        El orden es por world_id ascendente (estable y predecible para el frontend).
        Si no hay mundos, devuelve lista vacía [].
        No lanza WorldNotFoundError: si no hay mundos la respuesta es [].
        """
        return await self._db.summary_by_world()


class CheckIncomingAttackUseCase:
    """
    Dispara manualmente la lectura del radar de ataques entrantes para un mundo.

    Usado por el endpoint POST /game/incoming-attacks/{world_id}/check.

    Frontera hexagonal: el use case recibe 'fetch_dorf1_attacks', un callable
    inyectado desde adapters/ que devuelve list[Dorf1AttackDTO] ya parseados.
    El use case NO invoca parsers de adapters directamente.
    """

    def __init__(
        self,
        db_port: "IncomingAttackDbPort",
    ) -> None:
        self._db = db_port

    async def execute(
        self,
        world_id: int,
        fetch_dorf1_attacks: Callable[[int], Awaitable[list[Dorf1AttackDTO]]],
        db_port_for_world_check=None,
    ) -> dict:
        """
        Fuerza la comprobación del radar para el mundo indicado.

        Lanza WorldNotFoundError si el mundo no existe (404).
        Lanza SessionNotActiveError si no hay sesión activa para ese mundo (503).
        Devuelve: { world_id, attacks_detected, message }

        fetch_dorf1_attacks: callable inyectado que obtiene y parsea dorf1.
            Firma: async (world_id: int) -> list[Dorf1AttackDTO]
            Lanza SessionNotActiveError si no hay sesión activa.
        """
        from core.ports.incoming_attack_db_port import IncomingAttackRecord  # noqa: PLC0415

        # Verificar existencia del mundo
        if db_port_for_world_check is not None:
            try:
                await db_port_for_world_check.get_world(world_id)
            except Exception:
                raise WorldNotFoundError(world_id)

        # El callable puede lanzar SessionNotActiveError — se propaga directamente
        attacks: list[Dorf1AttackDTO] = await fetch_dorf1_attacks(world_id)

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        count = 0
        for dto in attacks:
            impact_dt = now + timedelta(seconds=dto.seconds_to_impact)
            await self._db.upsert_attack(IncomingAttackRecord(
                world_id=world_id,
                village_game_id=0,      # placeholder — Comp. B no tiene game_id exacto
                attack_count=dto.attack_count,
                impact_at=impact_dt.isoformat(),
                rally_point_href=dto.rally_point_href,
                source="dorf1",
                detected_at=now_iso,
                updated_at=now_iso,
            ))
            count += 1

        return {
            "world_id": world_id,
            "attacks_detected": count,
            "message": "Check completado",
        }
