"""
Puerto de persistencia para el radar de ataques entrantes.

Define el contrato abstracto que debe implementar cualquier adaptador de BD.
La implementación concreta está en adapters/db/incoming_attack_sqlite_adapter.py.

Métodos mínimos: ensure_tables, upsert_attack, list_attacks.

Ver spec docs/specs/radar-ataques-entrantes.md §7 para el DDL completo y §8 para
los contratos de API.
Añadido en la feature radar-ataques-entrantes (2026-06-05).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class IncomingAttackRecord:
    """
    Registro de un ataque entrante para persistir / actualizar en BD.

    Campos obligatorios mínimos: world_id, village_game_id, source, detected_at, updated_at.
    El resto pueden ser None cuando el dato no está disponible aún (sidebar sin timer, etc.).
    """
    world_id:               int
    village_game_id:        int
    source:                 str         # 'sidebar' | 'dorf1' | 'rally_point'
    detected_at:            str         # ISO-8601 UTC
    updated_at:             str         # ISO-8601 UTC

    # Datos de la aldea propia (defensora)
    village_name:           str | None = None
    village_coord_x:        int | None = None
    village_coord_y:        int | None = None

    # Datos del ataque (Componente B)
    attack_count:           int = 1
    impact_at:              str | None = None       # ISO-8601 UTC; NULL si solo viene de sidebar
    rally_point_href:       str | None = None

    # Datos del atacante (Componentes C+D — None hasta que estén disponibles)
    attacker_name:          str | None = None
    origin_village_name:    str | None = None
    origin_village_coord_x: int | None = None
    origin_village_coord_y: int | None = None
    operation_type:         str | None = None
    origin_village_href:    str | None = None

    # Snapshot de la aldea atacante (Componente D — None hasta que esté disponible)
    attacker_snapshot_json: str | None = None


class IncomingAttackDbPort(ABC):
    """Puerto de persistencia para el radar de ataques entrantes."""

    @abstractmethod
    async def ensure_tables(self) -> None:
        """Crea la tabla incoming_attacks y sus índices si no existen (DDL idempotente)."""

    @abstractmethod
    async def upsert_attack(self, record: IncomingAttackRecord) -> int:
        """
        Inserta o actualiza un ataque entrante.

        Unicidad: (world_id, village_game_id, impact_at).
        ON CONFLICT DO UPDATE: actualiza los campos mutables
        (attack_count, attacker_name, origin_village_name, operation_type, updated_at).

        Devuelve el id (AUTOINCREMENT) del registro insertado o actualizado.
        """

    @abstractmethod
    async def list_attacks(
        self,
        world_id: int,
        include_past: bool = False,
        village_game_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """
        Lista ataques entrantes para un mundo.

        include_past=False (default): solo ataques con impact_at > NOW() o impact_at IS NULL
            (los sin timer se muestran como "pendientes" — postura conservadora RT-05).
        include_past=True: todos los registros sin filtro de impacto.

        village_game_id: filtro opcional por aldea concreta.
        limit/offset: paginación.

        Devuelve: { total: int, items: list[dict] }
        Cada item incluye todos los campos de incoming_attacks.
        """

    @abstractmethod
    async def get_attack_by_id(self, attack_id: int) -> dict | None:
        """
        Obtiene un ataque por su id primario.

        Devuelve dict con todos los campos del registro, o None si no existe.
        Necesario para verificar idempotencia del snapshot antes de encolar Comp. D (RN-20).
        Ver spec §9.11.
        """

    @abstractmethod
    async def update_snapshot(
        self,
        attack_id: int,
        snapshot_json: str,
        updated_at: str,
    ) -> None:
        """
        Actualiza attacker_snapshot_json y updated_at para un ataque existente.

        Si attack_id no existe → no-op silencioso (loggea WARNING).
        Llamado desde el handler de Comp. D tras parsear VillageProfileDTO.
        Ver spec §9.11.
        """

    @abstractmethod
    async def summary_by_world(self) -> list[dict]:
        """
        Devuelve [{world_id, pending_attacks}] para todos los mundos conocidos.

        pending_attacks = COUNT de filas con:
          impact_at IS NULL (sidebar sin timer, postura conservadora RT-05)
          OR impact_at > datetime('now') (ataque todavía en el futuro).

        Se incluyen todos los mundos (incluso con 0 ataques) para que el frontend
        pueda inicializar badges sin una segunda petición.

        Ver spec §8 EP-RA03, §9.11.
        """
