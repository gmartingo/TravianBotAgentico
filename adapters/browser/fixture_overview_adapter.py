"""
Implementación de test de OverviewHtmlSourcePort que devuelve HTML desde ficheros.

Plenamente funcional sin Chrome ni sesión activa. Es la implementación que usan
todos los tests de los cuatro bloques de lectura (overview, resources, culture-points,
troops).

Convención de nombre de fichero: {page.value}.html
Ejemplos: overview.html, resources.html, troops_own.html, culturepoints.html

invalidate_cache es no-op (no hay caché que invalidar).
"""
from __future__ import annotations

from pathlib import Path

from core.exceptions import OverviewFixtureNotFoundError
from core.ports.overview_html_source_port import OverviewHtmlSourcePort, OverviewPage


class FixtureOverviewAdapter(OverviewHtmlSourcePort):
    """
    Implementación de test: devuelve HTML desde ficheros guardados en disco.

    fixtures_dir: Path al directorio con los fixtures HTML.
    Convención de nombre de fichero: {page.value}.html
    Ejemplos: overview.html, resources.html, troops_own.html

    invalidate_cache es no-op (no hay caché).
    """

    def __init__(self, fixtures_dir: Path) -> None:
        self._dir = fixtures_dir

    async def get_page_html(
        self,
        world_id: int,
        page: OverviewPage,
    ) -> str:
        """
        Lee el fichero {page.value}.html del directorio de fixtures.

        Lanza OverviewFixtureNotFoundError si el fichero no existe.
        El world_id se ignora — los fixtures no dependen de ninguna sesión.
        """
        filename = f"{page.value}.html"
        path = self._dir / filename
        if not path.exists():
            raise OverviewFixtureNotFoundError(page)
        return path.read_text(encoding="utf-8")

    def invalidate_cache(self, world_id: int) -> None:
        """No-op: no hay caché en el adaptador de fixtures."""
        pass
