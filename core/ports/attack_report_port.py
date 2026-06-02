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

    @abstractmethod
    async def get_balance_stats(
        self,
        x: int | None = None,
        y: int | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        game_data_port=None,
    ) -> dict:
        """
        Cómputo global PERDIDOS (valor en recursos de tropas atacantes muertas)
        vs ROBADOS (botín + inventario del héroe), con filtros opcionales por
        oasis (x, y) y por rango de fecha (from_date, to_date, ISO 8601).

        Devuelve {range, total_reports, reports_without_tribe, lost, stolen, net}.
        El cálculo de PERDIDO requiere game_data_port (costes de tropas por tribu).
        Ver spec docs/specs/bd-ataques-oasis-balance-perdidos-robados.md.
        """

    @abstractmethod
    async def get_all_oasis_regen_comparison(self) -> dict:
        """
        Comparativa de tasas de reaparición y proyección de animales para todos los oasis.

        Sin parámetros. 200 siempre, incluso con BD vacía (oasis:[], species_columns:[]).
        Ver spec docs/specs/reaparicion-animales-oasis.md §8 EP-10 y §9.

        Gap pre-existente regularizado en oasis-spawn-mechanics-stats §14 paso 0.
        El adaptador ya implementaba este método (línea 1115); el port no lo declaraba.
        """

    @abstractmethod
    async def get_oasis_spawn_composition(self, timer_min: int) -> dict:
        """
        Devuelve composición típica, inferencia de tipo, peor combinación a batir
        (dado timer_min en minutos) y estado cooldown/respawn para todos los oasis.

        timer_min: 6|7|10|15 (validado en el router antes de llamar al port).
        200 siempre, incluso con oasis: [].
        Ver spec docs/specs/oasis-spawn-mechanics-stats.md §8 EP-SPAWN y §9.
        """

    @abstractmethod
    async def get_animal_temporal_distribution(
        self,
        interval_minutes: int,
        lang: str,
        translation_port,
    ) -> dict:
        """
        Distribución empírica de animales por tipo de oasis para una cadencia de farmeo dada (v3).

        interval_minutes: frecuencia en minutos. Valores válidos: 6|7|10|15|30|60|120|180|240|300.
        lang: código de idioma validado (25 soportados).
        translation_port: puerto de traducción para resolver nombres de animales.

        Devuelve { interval_minutes, interval_label, window, n_reports_in_window, types }.
        types: lista de 5 secciones fijas (hierro, arcilla, madera, cereal, sin_clasificar).
        Cada sección contiene: oasis_type, oasis_type_label, n_oasis, n_oasis_low_confidence,
        n_reports_in_section, animals[] (mismos campos que la lista plana de v2).
        200 siempre. Ver spec docs/specs/bd-ataques-oasis-temporal-distribution.md §8 EP-TD (v3).
        """


class DuplicateReportError(Exception):
    """Se intenta guardar un reporte que ya existe en BD (clave única violada)."""

    def __init__(self, existing_id: int) -> None:
        self.existing_id = existing_id
        super().__init__(f"Reporte duplicado (id existente: {existing_id})")
