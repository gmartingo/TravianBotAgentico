"""
Puerto de persistencia para el sistema de Human Sessions.

Define el contrato abstracto que deben implementar los adaptadores de BD
para las operaciones de timeline, override y configuración de sesión.

Spec §7.9 — SessionTimelineDbPort.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.entities.session import SessionConfig, SessionMode, SessionOverride, SessionTimeline


class SessionTimelineDbPort(ABC):

    @abstractmethod
    async def get_timeline(self, world_id: int, weekday: int) -> SessionTimeline | None:
        """
        Devuelve el timeline del día para el mundo dado.
        Devuelve None si no hay configuración explícita (el caller usa el default).
        """

    @abstractmethod
    async def upsert_timeline(self, timeline: SessionTimeline) -> SessionTimeline:
        """
        Reemplaza todos los bloques del (world_id, weekday) con los del timeline dado.

        Antes de escribir:
          1. Valida que no haya solapes (_validate_no_overlaps).
          2. Rellena huecos con DISCONNECTED (_fill_gaps_with_disconnected).
          3. Persiste los bloques resultantes (reemplaza los anteriores).

        Devuelve el timeline completo ya con los huecos rellenados.
        Lanza ValueError si hay solapes.
        """

    @abstractmethod
    async def get_override(self, world_id: int) -> SessionOverride | None:
        """
        Devuelve el override activo para el mundo.
        Si no existe o ya expiró (expires_at <= now), lo borra de BD y devuelve None.
        """

    @abstractmethod
    async def set_override(self, override: SessionOverride) -> None:
        """
        Escribe o reemplaza el override activo para el mundo.
        Hay máximo un override por mundo (PRIMARY KEY = world_id).
        """

    @abstractmethod
    async def clear_override(self, world_id: int) -> None:
        """Borra el override activo si existe. Idempotente."""

    @abstractmethod
    async def get_session_config(self, world_id: int) -> SessionConfig:
        """
        Devuelve la config PASIVO del mundo.
        Si no existe fila en world_session_config, devuelve los defaults
        (passive_interval_factor=2.0, passive_send_probability=0.05).
        No devuelve None: los defaults siempre son válidos.
        """

    @abstractmethod
    async def upsert_session_config(self, config: SessionConfig) -> SessionConfig:
        """
        Crea o actualiza la config PASIVO del mundo.
        Solo escribe los campos proporcionados (PATCH parcial semántico):
        si un campo viene con el valor actual, simplemente lo reescribe.
        El adaptador aplica un UPSERT idempotente.
        Devuelve el estado completo tras la escritura.
        """
