"""
DTOs del bloque de lectura de recursos (almacenado, producción, capacidad).

Todas las clases son frozen=True: los datos de lectura son inmutables.

Nomenclatura:
  - Los campos numéricos usan nombres semánticos en inglés (wood, clay, iron, crop),
    idioma-independientes y estables para el bot.
  - Los selectores CSS internos en el parser usan los nombres de Travian (lum, clay, iron, crop).
    El mapping lum→wood se documenta explícitamente en el parser.
  - 'wood' = madera (CSS class: lum / Travian icon: r1)
  - 'clay' = arcilla (CSS class: clay / Travian icon: r2)
  - 'iron' = hierro (CSS class: iron / Travian icon: r3)
  - 'crop' = cereal (CSS class: crop / Travian icon: r4)
"""
from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Sub-DTOs de aldea
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VillageMerchants:
    """Mercaderes libres y totales de una aldea."""

    free:  int  # Disponibles para enviar
    total: int  # Total del mercado de esta aldea


@dataclass(frozen=True)
class VillageStoredResources:
    """Recursos almacenados en una aldea (tabla #ressources — OJO: doble 's' en HTML)."""

    game_id:   int                 # newdid de la aldea (extraído del href)
    name:      str                 # Nombre de la aldea (texto del <a>)
    wood:      int                 # td.lum → madera almacenada
    clay:      int                 # td.clay → arcilla almacenada
    iron:      int                 # td.iron → hierro almacenado
    crop:      int                 # td.crop → cereal almacenado
    merchants: VillageMerchants    # td.tra > <a> → mercaderes libres/totales


@dataclass(frozen=True)
class StoredTotals:
    """Fila tr.sum de la tabla #ressources."""

    wood:      int                 # td.lum
    clay:      int                 # td.clay
    iron:      int                 # td.iron
    crop:      int                 # td.crop
    merchants: VillageMerchants    # td.tra (texto directo, sin <a>)


@dataclass(frozen=True)
class VillageProductionResources:
    """
    Producción BRUTA por hora de una aldea (tabla #production).

    IMPORTANTE: Los valores son producción BRUTA, es decir, NO restan el consumo
    de cereal del ejército. El valor de `crop` puede ser menor que el consumo real
    del ejército — esto es correcto y esperado; el bot no compensa esta diferencia
    en este bloque.

    La producción neta (bruta - consumo del ejército) se calcula combinando este
    bloque con los datos del bloque troops (out of scope para este bloque).
    """

    game_id: int  # newdid de la aldea
    name:    str  # Nombre de la aldea
    wood:    int  # td.lum → producción bruta de madera por hora
    clay:    int  # td.clay → producción bruta de arcilla por hora
    iron:    int  # td.iron → producción bruta de hierro por hora
    crop:    int  # td.crop → producción BRUTA de cereal por hora (no resta consumo ejército)


@dataclass(frozen=True)
class ProductionTotals:
    """Fila tr.sum de la tabla #production."""

    wood:                int        # td.lum → total madera
    clay:                int        # td.clay → total arcilla
    iron:                int        # td.iron → total hierro
    crop:                int        # td.crop → total cereal (bruto)
    total_all_resources: int | None # td.vil > span.total — suma global lum+clay+iron+crop
                                    # None si el elemento span.total no existe en el HTML (EC-07)


@dataclass(frozen=True)
class VillageCapacity:
    """Capacidad de almacén y granero de una aldea (tabla #capacity)."""

    game_id:   int  # newdid de la aldea
    name:      str  # Nombre de la aldea
    warehouse: int  # td.max123 → capacidad del almacén (madera, arcilla, hierro)
    granary:   int  # td.max4   → capacidad del granero (cereal)


@dataclass(frozen=True)
class CapacityTotals:
    """Fila tr.sum de la tabla #capacity."""

    warehouse: int  # td.max123 → capacidad total de almacén
    granary:   int  # td.max4   → capacidad total de granero


# ---------------------------------------------------------------------------
# DTO raíz de respuesta
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResourceNames:
    """
    Nombres localizados de los cuatro recursos de Travian.

    Se resuelven una sola vez al nivel raíz de la respuesta a partir del idioma
    solicitado (Accept-Language), vía translation_port.get_message(code, lang).

    Códigos usados:
      r1 → wood (madera)
      r2 → clay (arcilla)
      r3 → iron (hierro)
      r4 → crop (cereal)
    """

    wood: str  # ej. "Madera" (es), "Wood" (en), "Holz" (de)
    clay: str  # ej. "Arcilla" (es), "Clay" (en), "Lehm" (de)
    iron: str  # ej. "Hierro" (es), "Iron" (en), "Eisen" (de)
    crop: str  # ej. "Cereal" (es), "Crop" (en), "Getreide" (de)


@dataclass(frozen=True)
class ResourcesResponseDTO:
    """
    Respuesta completa del endpoint GET /game/resources/{world_id}.

    Agrega las tres pestañas de /village/statistics/resources en una sola respuesta:
      - stored:      recursos almacenados por aldea + totales
      - production:  producción bruta por hora por aldea + totales
      - capacity:    capacidad de almacén y granero por aldea + totales

    Patrón de localización:
      - Los campos numéricos (wood, clay, iron, crop) usan nombres semánticos en inglés
        (idioma-independientes, estables para el bot).
      - `resource_names` expone el nombre localizado de cada recurso una sola vez al
        nivel raíz. El cliente usa resource_names.wood → "Madera" para etiquetar
        la columna de madera.
      - Los nombres de aldea (name) vienen del HTML de Travian y NO se traducen.
    """

    lang:              str
    resource_names:    ResourceNames
    stored:            list[VillageStoredResources]
    stored_totals:     StoredTotals
    production:        list[VillageProductionResources]
    production_totals: ProductionTotals
    capacity:          list[VillageCapacity]
    capacity_totals:   CapacityTotals
