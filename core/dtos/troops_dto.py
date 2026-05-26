"""
DTOs del bloque TROOPS — 5 sub-pestañas de /village/statistics/troops.

Todos los dataclasses son frozen=True.  Los campos que admiten None están
documentados con la semántica:
  None  = no aplica / edificio/dato inexistente
  0     = valor cero (presencia confirmada, sin actividad)

Sección 7 del spec lectura-troops.
"""
from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Tipos auxiliares compartidos
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TroopTypeInfo:
    """
    Información de un tipo de tropa: código estable + nombre localizado + icono.

    unit_class : código CSS global, p.ej. "u21", "u22", ..., "uhero"
    name       : nombre localizado al idioma pedido, p.ej. "Falange" (es)
                 Fallback a unit_class si no hay entrada en el catálogo.
    icon_url   : ruta al PNG del icono, ej. "/static/icons/gauls_1.png".
                 None si no hay datos en game_data_port (BD vacía) o si
                 el unit_class no mapea a ninguna tribu (uhero, desconocidos).
    """

    unit_class: str
    name: str
    icon_url: str | None = None


@dataclass(frozen=True)
class BuildingInfo:
    """
    Información de un edificio de entrenamiento: gid + nombre localizado + icono.

    gid      : identificador del edificio (19=Cuartel, 20=Establo, 21=Taller, 46=Hospital)
    name     : nombre localizado vía translation_port.get_building_name(gid, lang)
               Fallback a "building_{gid}" si el gid no está en el catálogo.
    icon_url : ruta al PNG del icono del edificio, ej. "/static/icons/building_19.png".
               None hoy (building_catalog vacío en BD) — forward-compatible: se rellenará
               cuando se cargue el catálogo de edificios vía kirilloid.
    """

    gid: int
    name: str
    icon_url: str | None = None


# ---------------------------------------------------------------------------
# 7.1  Troops Own
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VillageOwnTroopsDTO:
    """
    Tropas totales (ejército máximo) de una aldea.

    game_id : newdid de la aldea
    counts  : uNN → cantidad (incluye u21-u30 y uhero; 0 si ausente)
              Las columnas presentes son las del thead del fixture.
              Los nombres localizados de cada uNN están en TroopsOwnResponse.troop_types.
    """

    game_id: int
    counts: dict[str, int]


@dataclass(frozen=True)
class TroopsOwnResponse:
    """Respuesta del endpoint GET /game/troops/{world_id}/own."""

    villages: list[VillageOwnTroopsDTO]
    troop_types: list[TroopTypeInfo]  # orden canónico según el thead
    totals: dict[str, int]            # suma global por uNN (de la fila tr.sum)


# ---------------------------------------------------------------------------
# 7.2  Troops Support
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VillageSupportTroopsDTO:
    """
    Tropas presentes en una aldea en el momento de la consulta.

    own             : uNN → cantidad (propias u21-u30 + uhero)
    nature          : uNN → cantidad (naturaleza u31-u40)
    hero            : alias de own.get("uhero", 0) — acceso conveniente
    upkeep_per_hour : consumo de cereal por hora
    offence         : fuerza ofensiva total (None si sin tropas / "-" en HTML)
    def_infantry    : defensa infantería total (None si sin tropas)
    def_cavalry     : defensa caballería total (None si sin tropas)
    """

    game_id: int
    own: dict[str, int]
    nature: dict[str, int]
    hero: int
    upkeep_per_hour: int
    offence: int | None
    def_infantry: int | None
    def_cavalry: int | None


@dataclass(frozen=True)
class TroopsSupportResponse:
    """Respuesta del endpoint GET /game/troops/{world_id}/support."""

    villages: list[VillageSupportTroopsDTO]
    troop_names: dict[str, str]  # uNN → nombre localizado para todos los uNN presentes


# ---------------------------------------------------------------------------
# 7.3  Troops Smithy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VillageSmithyDTO:
    """
    Estado de investigación/mejora de tropas en la herrería de una aldea.

    in_progress : uNN de tropas actualmente investigándose ([] si span.dot)
    levels      : uNN → nivel de mejora (int ≥ 0) o None (tropa no investigable, "-" en HTML)
                  Solo incluye los uNN que aparecen en el thead (u21-u28 en los fixtures).
    """

    game_id: int
    in_progress: list[str]
    levels: dict[str, int | None]


@dataclass(frozen=True)
class TroopsSmithyResponse:
    """Respuesta del endpoint GET /game/troops/{world_id}/smithy."""

    villages: list[VillageSmithyDTO]
    troop_types: list[TroopTypeInfo]  # orden canónico según thead


# ---------------------------------------------------------------------------
# 7.4  Troops Hospital
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VillageHospitalDTO:
    """
    Estado del hospital de una aldea.

    has_hospital : True si el hospital existe (span.dot en inProgress o heridos > 0)
    healing      : True si hay curación activa (contenido distinto de span.dot/span.none)
    wounded      : uNN → heridos (u21-u26; solo si has_hospital=True)
                   Si has_hospital=False, wounded es {} (vacío).
    """

    game_id: int
    has_hospital: bool
    healing: bool
    wounded: dict[str, int]


@dataclass(frozen=True)
class TroopsHospitalResponse:
    """Respuesta del endpoint GET /game/troops/{world_id}/hospital."""

    player_tribe: int                 # extraído de th.villageName > i.tribeN_medium
    villages: list[VillageHospitalDTO]
    troop_types: list[TroopTypeInfo]  # orden canónico según thead


# ---------------------------------------------------------------------------
# 7.5  Troops Training
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BuildingQueueDTO:
    """
    Cola de entrenamiento de un edificio concreto en una aldea.

    gid             : 19=Cuartel, 20=Establo, 21=Taller, 46=Hospital
    building_exists : True si el edificio existe (span.duration o span.dot)
    queue_seconds   : Segundos en cola (0 si span.dot; None si span.none / edificio inexistente)
    """

    gid: int
    building_exists: bool
    queue_seconds: int | None


@dataclass(frozen=True)
class VillageTrainingDTO:
    """Cola de entrenamiento de todos los edificios de una aldea."""

    game_id: int
    queues: list[BuildingQueueDTO]  # uno por columna del thead, en orden del thead


@dataclass(frozen=True)
class TroopsTrainingResponse:
    """Respuesta del endpoint GET /game/troops/{world_id}/training."""

    buildings: list[BuildingInfo]      # orden de columnas según thead
    building_gids: list[int]           # alias de [b.gid for b in buildings]
    villages: list[VillageTrainingDTO]
