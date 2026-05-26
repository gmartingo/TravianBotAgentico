"""
DTOs de respuesta para el endpoint GET /game/overview/{world_id}.

Todos los dataclasses son frozen=True: inmutables una vez construidos,
igual que VillageInfo del tronco. No se modifican después de la serialización.

Semántica de None/0:
  - Listas vacías ([]) significan "ninguna actividad", no "dato desconocido".
  - merchants_free=0, merchants_total=0 significa aldea sin mercado o sin mercaderes libres.
  - name="" en OverviewVillageDTO significa "aldea en parser pero ausente del índice VillageMap"
    (EC-10); es un estado de rotura de consistencia, no un valor normal.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TroopMovementDTO:
    """
    Un movimiento de tropas activo en la aldea (columna td.att de #overview).

    El tipo se determina por la clase CSS del <img> dentro de td.att; nunca por el alt
    (que es idioma-dependiente del servidor Travian). El campo movement_type es un string
    libre, no un enum, porque Travian puede añadir clases nuevas sin previo aviso.

    Clases vistas en el fixture:
      - "def1" — refuerzos llegando (propios o aliados)
      - "att2" — tropas propias en ataque / salidas
    Otras clases ("att1", "def2", "att3"…) se parsean genéricamente cuando aparezcan.
    """
    movement_type: str   # Clase CSS del img: "def1", "att2", etc.
    quantity:      int   # Prefijo numérico del alt: "618x …" → 618


@dataclass(frozen=True)
class BuildingInProgressDTO:
    """
    Un edificio actualmente en construcción (columna td.bui de #overview).

    El `gid` del edificio NO está disponible de forma estructural en la tabla #overview
    (el HTML solo tiene el `alt` del img.bau, que es idioma-dependiente del servidor).

    Política actual (mejor esfuerzo):
    - `building_name` = alt del img.bau tal como viene del servidor (idioma del servidor).
    - `name` = igual que building_name (no hay gid para resolver via get_building_name).
    - `name_source` = "server_lang": el nombre NO está localizado al Accept-Language solicitado,
      sino que viene del servidor de Travian en su idioma de configuración.

    Si en el futuro se implementa un mapa alt_en→gid, `name_source` pasará a "catalog"
    y `name` se resolverá con get_building_name(gid, lang). Fuera del alcance de este spec.
    """
    building_name: str          # Alt crudo del img.bau (idioma del servidor), ej: "Barracks"
    name:          str          # Nombre localizado si gid conocido; alt crudo si no
    name_source:   str          # "catalog" si se usó translation_port; "server_lang" si no


@dataclass(frozen=True)
class TroopPresentDTO:
    """
    Un tipo de tropa con unidades presentes/destacadas en la aldea (columna td.tro de #overview).

    Nota: td.tro muestra tropas ya entrenadas presentes en la aldea, NO la cola de
    entrenamiento. El detalle de entrenamiento está en el bloque troops.

    El tipo se determina SIEMPRE por la clase `uNN` del <img>; nunca por el `alt`
    (que es idioma-dependiente, ej: "Swordsman" vs "Espadachín"). El `name` se resuelve
    vía `unit_class_to_tribe_ordinal` + `translation_port.get_troop_name(tribe, ordinal, lang)`.
    Fallback a `unit_class` si no hay entrada en el catálogo (uhero, u31-u40 NPC, etc. tienen
    entradas; solo códigos completamente desconocidos caen al fallback).

    icon_url: ruta al PNG del icono de la tropa, ej: "/static/icons/gauls_2.png".
    None si no hay datos en game_data_port (BD vacía en test/desarrollo) o si el
    unit_class no mapea a ninguna tribu.
    """
    unit_class: str          # Código estable: clase uNN del img, p.ej. "u22"
    name:       str          # Nombre localizado al idioma pedido, p.ej. "Espadachín" (es)
                             # Fallback a unit_class si no hay entrada en el catálogo
    quantity:   int          # Prefijo numérico del alt: "71x …" → 71
    icon_url:   str | None = None  # "/static/icons/{icon_id}.png" o None si sin datos


@dataclass(frozen=True)
class OverviewVillageDTO:
    """
    Estado de una aldea en la tabla #overview de /village/statistics/overview.

    Campos None/vacío:
      - movements = [] si td.att contiene <span class="none">
      - buildings_under_construction = [] si td.bui contiene <span class="none">
      - troops_present = [] si td.tro contiene <span class="none">
      - merchants_free = 0, merchants_total = 0 si aldea sin mercado o "0/0"
      - name = "" si la aldea está en el parser pero ausente del índice VillageMapUseCase (EC-10)
    """
    game_id:                       int
    name:                          str

    # td.att — movimientos de tropas (lista vacía si span.none)
    movements:                     list[TroopMovementDTO]

    # td.bui — edificios en construcción (lista vacía si span.none)
    buildings_under_construction:  list[BuildingInProgressDTO]

    # td.tro — tropas presentes/destacadas (lista vacía si span.none)
    troops_present:                list[TroopPresentDTO]

    # td.tra — mercaderes libres / totales (0/0 si sin mercado)
    merchants_free:                int
    merchants_total:               int


@dataclass(frozen=True)
class OverviewResponseDTO:
    """
    Respuesta completa del endpoint GET /game/overview/{world_id}.

    villages es lista vacía para cuentas recién creadas sin aldeas (EC-12).
    lang es el código BCP-47 validado del Accept-Language de la request.
    """
    world_id:  int
    lang:      str
    villages:  list[OverviewVillageDTO]
