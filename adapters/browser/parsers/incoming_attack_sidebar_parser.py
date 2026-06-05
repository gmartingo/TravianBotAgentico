"""
Parser del sidebar de Travian para detectar aldeas propias bajo ataque.

Componente A del radar de ataques entrantes.

Función pura: recibe HTML como string, devuelve lista de VillageUnderAttackDTO.
SIN navegación adicional — parsea el HTML ya cargado por el WorldAgent.
NO hace ningún browser.get ni petición HTTP.

Discriminador CONFIRMADO (GAP-01 cerrado — diff con-ataque vs sin-ataque):
  El ÚNICO indicador de "aldea bajo ataque" es la clase CSS 'attack'
  en el div.listEntry.village. Selector: div.listEntry.village.attack

SEÑUELOS A IGNORAR (presentes en TODAS las entradas, con o sin ataque):
  - svg.attack dentro de span.incomingTroops → señuelo permanente, NO discrimina
  - svg.handle en div.dragAndDrop → drag-handle, NO discrimina

Ver spec docs/specs/radar-ataques-entrantes.md §4 RN-02, §9.2.
Añadido en la feature radar-ataques-entrantes (2026-06-05).
"""
from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from core.dtos.incoming_attack_dto import VillageUnderAttackDTO

logger = logging.getLogger(__name__)


def _parse_coord(el) -> int:
    """
    Extrae el entero de un span de coordenada.

    El texto puede incluir paréntesis, barras y el guion Unicode menos (−):
      "(−68"  → -68
      "(10"   → 10
      "73)"   → 73

    Usa regex r'[-−]?\\d+' (guion ASCII + guion Unicode menos U+2212).
    Devuelve 0 si no hay match o el elemento es None.
    """
    if el is None:
        return 0
    text = el.get_text(strip=True)
    m = re.search(r"[-−]?\d+", text)
    if not m:
        return 0
    # Reemplazar el guion Unicode menos por el guion ASCII antes de int()
    return int(m.group().replace("−", "-"))


class IncomingAttackSidebarParser:
    """
    Parser estático del sidebar de Travian.

    Detecta aldeas propias bajo ataque a partir del HTML ya cargado.
    No instancia estado — todos los métodos son estáticos.
    """

    @staticmethod
    def parse(html: str) -> list[VillageUnderAttackDTO]:
        """
        Parsea el HTML del sidebar y devuelve las aldeas bajo ataque.

        Si #sidebarBoxVillageList no existe en el HTML → retorna lista vacía
        sin loggear (no-op silencioso — RN-19, EC-01).

        Si una entrada div.listEntry.village.attack no tiene data-did →
        loggea WARNING y la omite (EC-03).

        Nunca propaga excepciones: los errores de parseo individuales
        no deben romper el flujo principal del WorldAgent.
        """
        soup = BeautifulSoup(html, "html.parser")
        sidebar = soup.select_one("#sidebarBoxVillageList")
        if not sidebar:
            # No-op silencioso: página pre-login o sidebar no cargado (RN-19)
            return []

        results: list[VillageUnderAttackDTO] = []

        # DISCRIMINADOR CONFIRMADO (GAP-01 cerrado):
        # El ÚNICO indicador de "aldea bajo ataque" es la clase 'attack'
        # en el div.listEntry. Selector: div.listEntry.village.attack
        #
        # SEÑUELOS A IGNORAR (están en TODAS las entradas, no discriminan):
        #   - span.incomingTroops > svg.attack  →  señuelo permanente
        #   - div.dragAndDrop > svg.handle      →  drag-handle
        # Cualquier lógica basada en svg.attack daría falso positivo en TODAS las aldeas.
        attacked_entries = sidebar.select("div.listEntry.village.attack")

        for entry in attacked_entries:
            did = entry.get("data-did")
            if not did:
                logger.warning(
                    "div.listEntry.village.attack sin data-did — ignorando entrada"
                )
                continue

            name_el  = entry.select_one("span.name")
            x_el     = entry.select_one("span.coordinateX")
            y_el     = entry.select_one("span.coordinateY")

            results.append(VillageUnderAttackDTO(
                village_game_id=int(did),
                village_name=name_el.get_text(strip=True) if name_el else "",
                coord_x=_parse_coord(x_el),
                coord_y=_parse_coord(y_el),
            ))

        return results
