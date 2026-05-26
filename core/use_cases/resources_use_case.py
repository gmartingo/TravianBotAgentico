"""
Use case del bloque resources.

Enriquece los datos ya parseados de las tres páginas de /village/statistics/resources:
  - RESOURCES            → villages_stored, stored_totals
  - RESOURCES_PRODUCTION → villages_production, production_totals
  - RESOURCES_CAPACITY   → villages_capacity, capacity_totals

Aplica los nombres localizados de los cuatro recursos (wood, clay, iron, crop)
vía translation_port.get_message(code, lang):
  r1 → wood  (madera)
  r2 → clay  (arcilla)
  r3 → iron  (hierro)
  r4 → crop  (cereal)

Hexagonal: este use case vive en core/ y NO importa nada de adapters/. Recibe
los datos YA PARSEADOS (el router del adapter llama al parser) y depende de
TranslationPort, que es un PUERTO del core.

Las excepciones del port (SessionNotActiveError, OverviewPageNotLoadedError,
OverviewFixtureNotFoundError) se propagan desde el router — este use case no las
lanza ni las envuelve: solo procesa datos ya limpios.
"""
from __future__ import annotations

from core.dtos.resources_dto import (
    ResourceNames,
    ResourcesResponseDTO,
)
from core.ports.translation_port import TranslationPort


class ResourcesUseCase:
    """
    Construye el ResourcesResponseDTO a partir de datos parseados + idioma.

    Sin estado — todos los datos vienen de los parsers (invocados por el router).
    """

    @staticmethod
    def execute(
        villages_stored: list,
        stored_totals,
        villages_production: list,
        production_totals,
        villages_capacity: list,
        capacity_totals,
        lang: str,
        translation_port: TranslationPort,
    ) -> ResourcesResponseDTO:
        """
        Combina las tres estructuras parseadas, resuelve los nombres de recurso
        localizados y devuelve el ResourcesResponseDTO completo.

        Parámetros:
          villages_stored / stored_totals     — resultado de ResourcesParser.parse_stored
          villages_production / production_totals — resultado de ResourcesParser.parse_production
          villages_capacity / capacity_totals — resultado de ResourcesParser.parse_capacity
          lang                                — código BCP-47 del idioma del cliente
          translation_port                    — puerto de traducción del core

        Pasos:
          1. Resolver nombres de recurso con translation_port.get_message(code, lang)
          2. Construir y devolver ResourcesResponseDTO
        """
        # --- Paso 1: nombres de recurso localizados ---
        # Códigos internos de Travian: r1=madera, r2=arcilla, r3=hierro, r4=cereal
        resource_names = ResourceNames(
            wood=translation_port.get_message("r1", lang),
            clay=translation_port.get_message("r2", lang),
            iron=translation_port.get_message("r3", lang),
            crop=translation_port.get_message("r4", lang),
        )

        # --- Paso 2: construir y devolver DTO ---
        return ResourcesResponseDTO(
            lang=lang,
            resource_names=resource_names,
            stored=villages_stored,
            stored_totals=stored_totals,
            production=villages_production,
            production_totals=production_totals,
            capacity=villages_capacity,
            capacity_totals=capacity_totals,
        )
