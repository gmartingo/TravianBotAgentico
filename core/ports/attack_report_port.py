"""
Puerto de persistencia para reportes de ataque a oasis.

Define el contrato abstracto que debe implementar cualquier adaptador de BD.
La implementación concreta está en adapters/db/attack_report_sqlite_adapter.py.

Ver spec docs/specs/bd-ataques-oasis.md §14 bloque 1 para la firma del puerto.
Añadido en la feature bd-ataques-oasis (2026-05-30).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.entities.attack_report import AttackReportPreview


class AttackReportPort(ABC):
    """Puerto de persistencia para reportes de ataque a oasis (Nature)."""

    @abstractmethod
    async def ensure_tables(self) -> None:
        """Crea las tablas y los índices si no existen (DDL idempotente)."""

    @abstractmethod
    async def save_report(self, preview: AttackReportPreview, raw_text: str) -> int:
        """
        Persiste un reporte completo (cabecera + tropas + animales).

        Devuelve el id (AUTOINCREMENT) del reporte recién creado.
        Lanza DuplicateReportError si la clave única ya existe.
        """

    @abstractmethod
    async def report_exists(
        self,
        coord_x: int,
        coord_y: int,
        attacked_at: str,
        origin: str,
    ) -> int | None:
        """
        Verifica si existe un reporte con la clave de unicidad indicada.

        Devuelve el id del reporte existente, o None si no existe.
        """

    @abstractmethod
    async def get_report(self, report_id: int) -> dict | None:
        """
        Devuelve el reporte completo (cabecera + tropas + animales) como dict,
        o None si no existe.
        """

    @abstractmethod
    async def list_reports(
        self,
        x: int | None = None,
        y: int | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """
        Devuelve un dict con:
          - total: int — número total de reportes que coinciden con los filtros
          - items: list[dict] — reportes paginados (cabecera + animales summary)
          - cumulative_bounty: int — suma de bounty_total del rango filtrado actual
        """

    @abstractmethod
    async def delete_report(self, report_id: int) -> bool:
        """
        Borra el reporte y sus filas hijas (CASCADE).

        Devuelve True si se borró, False si no existía.
        """

    @abstractmethod
    async def get_oasis_stats(self, x: int, y: int) -> dict:
        """
        Devuelve las estadísticas de un oasis:
          - total_attacks, first_attack, last_attack
          - animal_appearances: aparición de animales (avg, max, min_present_nonzero)
          - repopulation_gaps: diferencia temporal entre ataques consecutivos + regeneración
          - animal_regen_rates: ratio promedio de regeneración por hora por animal
            (campo nuevo — spec bd-ataques-oasis-stats-oasis-nav §8 MEJORA 1)

        Si no hay reportes para esas coords, devuelve el body de "cero ataques"
        (con animal_regen_rates: []).
        """

    @abstractmethod
    async def get_bounty_stats(
        self,
        x: int | None = None,
        y: int | None = None,
    ) -> dict:
        """
        Balance de recursos saqueados (EP-07).

        Si x e y son None → balance global (todos los reportes).
        Si x e y son enteros → balance del oasis en (x, y).

        Devuelve: { scope, coord_x_dest, coord_y_dest, total_reports, bounty: {wood,clay,iron,crop,total} }

        Ver spec docs/specs/bd-ataques-oasis-fix-hora-balance.md §8 EP-07.
        """

    @abstractmethod
    async def list_oasis_summaries(
        self,
        x: int | None = None,
        y: int | None = None,
    ) -> dict:
        """
        Lista de oasis únicos con reportes, con resumen estadístico básico (EP-08).

        Ordenación: last_attack DESC.
        Filtro opcional: x+y (ambos o ninguno).

        Devuelve: { total, items: [{ coord_x_dest, coord_y_dest, attack_count, last_attack, total_bounty }] }

        Ver spec docs/specs/bd-ataques-oasis-stats-oasis-nav.md §8 EP-08.
        """

    @abstractmethod
    async def get_global_oasis_stats(self) -> dict:
        """
        Devuelve estadísticas globales de todos los oasis combinados:
          - animal_appearances: aparición de animales (appearances, avg, max, min)
          - animal_regen_rates: ratio de regeneración por hora por animal
            (calculado juntando todos los intervalos de todos los oasis)
        200 con arrays vacíos si no hay datos.
        Ver spec docs/specs/bd-ataques-oasis-stats-global.md §8 EP-09.
        """


class DuplicateReportError(Exception):
    """Se intenta guardar un reporte que ya existe en BD (clave única violada)."""

    def __init__(self, existing_id: int) -> None:
        self.existing_id = existing_id
        super().__init__(f"Reporte duplicado (id existente: {existing_id})")
