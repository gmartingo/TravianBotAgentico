"""
Use case e infraestructura para extraer el índice de aldeas del jugador.

Contenido:
  - VillageInfo — DTO inmutable con game_id, name, x, y de una aldea
  - VillageMapUseCase — extrae la lista de aldeas desde /village/statistics/overview
  - VillageOverviewParser — parser puro (HTML str → list[VillageInfo])

Este índice es compartido por los cuatro bloques de lectura (overview, resources,
culture-points, troops). No se re-extrae por bloque; se recomienda cachearlo en
el caller por world_id.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from core.ports.overview_html_source_port import OverviewHtmlSourcePort, OverviewPage


@dataclass(frozen=True)
class VillageInfo:
    """
    Información mínima de una aldea extraída del overview.

    Inmutable (frozen=True): el índice no se modifica una vez construido.

    Campos:
      game_id — ID en Travian (aparece en URLs como newdid=N o village=N)
      name    — Nombre de la aldea tal como aparece en el overview
      x       — Coordenada X en el mapa (placeholder 0 — no disponible en la tabla #overview)
      y       — Coordenada Y en el mapa (placeholder 0 — no disponible en la tabla #overview)

    Nota: las coordenadas son responsabilidad de un use case posterior (World Map),
    fuera del alcance del tronco. Se usan 0 como placeholder documentado.
    """
    game_id: int
    name:    str
    x:       int
    y:       int


class VillageMapUseCase:
    """
    Extrae la lista de aldeas del jugador desde la página de overview principal.

    Esta lista es el índice compartido de los cuatro bloques.
    Se recomienda cachearlo en el caller (p.ej. por world_id) y no llamarlo
    en cada request individual.
    """

    async def execute(
        self,
        port: OverviewHtmlSourcePort,
        world_id: int,
    ) -> list[VillageInfo]:
        """
        Devuelve la lista de aldeas del jugador desde /village/statistics/overview.

        Lanza las mismas excepciones que port.get_page_html:
          - SessionNotActiveError        (Live sin sesión activa)
          - OverviewPageNotLoadedError   (Live, timeout o HTML vacío)
          - OverviewFixtureNotFoundError (Fixture, fichero no encontrado)
        """
        html = await port.get_page_html(
            world_id=world_id,
            page=OverviewPage.OVERVIEW,
        )
        return VillageOverviewParser.extract_villages(html)


class VillageOverviewParser:
    """
    Parser puro: dado el HTML de /village/statistics/overview, extrae la lista
    de aldeas.

    Selectores verificados con fixture overview.html (T4.x, Galos,
    ts20.x2.america.travian.com):
      - Filas de aldea: table#overview > tbody > tr que tengan td.vil.fc
      - game_id: href del enlace en td.vil.fc > a → parámetro newdid=N → int(N)
      - name: texto del mismo <a> (strip)
      - Ignorar tr.sum (fila de totales — no tiene td.vil.fc)
      - Coordenadas: NO están en la tabla #overview → x=0, y=0 placeholder

    Todos los selectores son estructurales — nunca por texto visible (RN-05).
    """

    @staticmethod
    def extract_villages(html: str) -> list[VillageInfo]:
        """
        Parsea el HTML de /village/statistics/overview y devuelve la lista de aldeas.

        Pasos:
          1. soup.select('table#overview > tbody > tr')
          2. Filtrar filas que tengan td.vil.fc
          3. Por cada fila: extraer href del <a> dentro de td.vil.fc, parsear newdid=N
          4. Extraer texto del mismo <a> como nombre de aldea
          5. Devolver VillageInfo(game_id=N, name=..., x=0, y=0)

        Devuelve lista vacía si no hay filas (cuenta recién creada sin aldeas).
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        villages: list[VillageInfo] = []

        for row in soup.select("table#overview > tbody > tr"):
            vil_cell = row.select_one("td.vil.fc")
            if vil_cell is None:
                continue  # tr.sum u otra fila sin aldea
            link = vil_cell.select_one("a[href*='newdid=']")
            if link is None:
                continue
            m = re.search(r"newdid=(\d+)", link["href"])
            if m is None:
                continue
            game_id = int(m.group(1))
            name = link.get_text(strip=True)
            if not name:
                continue  # omitir si el nombre viene vacío (validación 10)
            villages.append(VillageInfo(game_id=game_id, name=name, x=0, y=0))

        return villages
