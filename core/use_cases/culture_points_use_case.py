"""
Use case del bloque culture-points.

Recibe el CulturePointsSummary ya parseado y lo devuelve sin modificación.

La responsabilidad de este use case es mínima (solo consistencia arquitectónica
con los otros 3 bloques); el parseo real ocurre en el router (adapter→adapter).

Este bloque NO usa translation_port: los datos de culture-points son exclusivamente
numéricos; no hay nombres de tropa, edificio ni recurso que localizar (TR-03, RN-07).

Hexagonal: este módulo vive en core/ y NO importa nada de adapters/.
"""
from __future__ import annotations

from core.dtos.culture_points_dto import CulturePointsSummary


class CulturePointsUseCase:
    """
    Use case del bloque culture-points.

    Recibe el CulturePointsSummary ya parseado por el router y lo devuelve.
    Sin estado propio — instanciación sin coste, concurrentemente seguro.
    """

    @staticmethod
    def execute(
        summary: CulturePointsSummary,
    ) -> CulturePointsSummary:
        """
        Retorna el resumen de culture points de todas las aldeas del jugador.

        Parámetros:
          summary — CulturePointsSummary ya construido por CulturePointsParser
                    en el router (adapter→adapter).

        No lanza excepciones propias; las excepciones del port se propagan
        desde el router antes de llegar a este método.
        """
        return summary
