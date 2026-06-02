"""
Entidades de dominio para el test en vivo de rutas de navegación (EP-N14).

Estas dataclasses representan el resultado de ejecutar una ruta de ruido en
modo diagnóstico (no-destructivo): no modifican BD ni contadores, solo informan.

Spec: noise-path-wizard.md §16.7
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PathTestStepResult:
    """Resultado de un paso individual en el test de la ruta."""

    step_order: int
    """Índice del paso (igual que NavigationStep.step_order)."""

    action: str
    """Valor del NoiseAction ejecutado: "CLICK", "WAIT_FOR_SELECTOR", "SCROLL_TO", "HOVER", "TIMEOUT"."""

    selector: str
    """Selector CSS del paso (o "(timeout global)" en el pseudo-paso de timeout)."""

    status: str
    """"ok" si el paso completó sin error; "error" si falló."""

    reason: str | None = None
    """None si status=="ok"; motivo legible del fallo si status=="error"."""

    current_url: str | None = None
    """URL del tab TRAS ejecutar el paso; None si no se pudo leer o no aplica."""


@dataclass
class PathTestReport:
    """Reporte completo de una ejecución de test de ruta (EP-N14).

    Construido por WorldAgent.execute_path_test y serializado por el handler HTTP.
    El reporte es puramente informativo: no modifica ningún estado persistente.
    """

    overall: str
    """"ok" si todos los pasos completaron sin error; "error" en cualquier otro caso."""

    steps: list[PathTestStepResult] = field(default_factory=list)
    """Resultados de cada paso ejecutado, en orden. Los pasos no ejecutados (tras
    un abort) no aparecen en la lista."""

    aborted_at_step: int | None = None
    """step_order del paso donde abortó el test; None si overall=="ok"."""

    anchor_navigated_to: str | None = None
    """URL completa a la que se navegó antes del primer paso (el ancla de origen).
    None si origin=="ANY" (no se navegó) o si no se pudo construir la URL."""
