"""
Endpoints del simulador y optimizador de combate.

POST /combat/simulate  — Simula un combate según la fórmula Travian T4.5.
POST /combat/optimize  — Optimizador multi-objetivo de ataque a oasis (frente de Pareto).

Política de idioma: resolve_language (precedencia ?lang= > Accept-Language > None).
Si resolve_language devuelve None → 400 explícito (idioma obligatorio en ambos endpoints).

Ver spec §8 para los contratos de API completos.
Ver spec §RN-01..RN-13 para las reglas de negocio.
Añadido en la feature simulador-combate (2026-05-29).
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from adapters.api.dependencies import (
    get_game_data_port,
    get_translation_port,
    resolve_language,
)
from core.entities.combat import (
    AttackerArtifacts,
    AttackerFormation,
    CatapultTarget,
    CombatConfig,
    DefenderArtifacts,
    DefenderFormation,
    OptimizationConfig,
    OptimizationWeights,
    RamSpec,
    TroopAvailability,
    TroopEntry,
    TroopTypeSpec,
    WallConfig,
)
from core.entities.tribe import Tribe
from core.i18n.languages import SUPPORTED_LANGUAGES
from core.ports.game_data_port import GameDataPort
from core.ports.translation_port import TranslationPort
from core.use_cases.combat_engine import simulate_combat
from core.use_cases.combat_optimizer import find_optimal_attack

router = APIRouter(tags=["combat"])


# ---------------------------------------------------------------------------
# DTOs de REQUEST — simulate
# ---------------------------------------------------------------------------


class TroopEntryRequest(BaseModel):
    """Tropa con cantidad para simulador."""
    model_config = ConfigDict(extra="forbid")

    tribe: Tribe | None = None       # si None, hereda la tribu del bloque padre
    ordinal: int = Field(..., ge=1, le=30)
    quantity: int = Field(..., ge=1, le=1_000_000)
    smithy_level: int = Field(default=0, ge=0, le=20)


class ArtifactsAttackerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fast_troops: float = Field(default=1.0, ge=0.01, le=10.0)
    diet: float = Field(default=1.0, ge=0.01, le=10.0)


class ArtifactsDefenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strong_buildings: float = Field(default=1.0, ge=0.01, le=10.0)
    great_cranny: float = Field(default=1.0, ge=0.01, le=10.0)


class CatapultTargetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    building_gid: int = Field(..., gt=0)
    current_level: int = Field(..., ge=0, le=20)


class RamSpecRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: int = Field(..., ge=0, le=1_000_000)
    smithy_level: int = Field(default=0, ge=0, le=20)


class AttackerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tribe: Tribe
    attack_type: Literal["attack", "raid"] = "raid"
    troops: list[TroopEntryRequest] = Field(..., min_length=1)
    hero_attack_points: float = Field(default=0.0, ge=0.0, le=20_000.0)
    hero_attack_bonus_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    alliance_bonus: float = Field(default=0.0, ge=0.0, le=5.0)
    morale: float = Field(default=100.0, ge=30.0, le=100.0)
    artifacts: ArtifactsAttackerRequest = Field(
        default_factory=ArtifactsAttackerRequest
    )
    catapult_targets: list[CatapultTargetRequest] = Field(default_factory=list)
    rams: RamSpecRequest | None = None

    @model_validator(mode="after")
    def check_troops_not_all_zero(self) -> "AttackerRequest":
        if all(t.quantity == 0 for t in self.troops):
            raise ValueError("El ejército atacante no tiene tropas activas.")
        return self


class DefenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tribe: Tribe | None = None
    troops: list[TroopEntryRequest] = Field(default_factory=list)
    hero_defense_points: float = Field(default=0.0, ge=0.0, le=20_000.0)
    hero_defense_bonus_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    village_resources: int | None = Field(default=None, ge=0)
    artifacts: ArtifactsDefenderRequest = Field(
        default_factory=ArtifactsDefenderRequest
    )


class WallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wall_level: int = Field(default=0, ge=0, le=20)
    stonemason_level: int = Field(default=0, ge=0, le=5)
    wall_tribe: Tribe | None = None


class CombatConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exponent: float = Field(default=0.5, ge=0.4, le=0.6)
    server_speed: float = Field(default=1.0, ge=1.0, le=10.0)
    distance_fields: float | None = Field(default=None, gt=0)


class SimulateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attacker: AttackerRequest
    defenders: list[DefenderRequest] = Field(..., min_length=1, max_length=20)
    wall: WallRequest = Field(default_factory=WallRequest)
    config: CombatConfigRequest = Field(default_factory=CombatConfigRequest)

    @model_validator(mode="after")
    def check_total_defender_troops(self) -> "SimulateRequest":
        total = sum(len(d.troops) for d in self.defenders)
        if total > 50:
            raise ValueError(
                f"Total de tipos de tropas entre defensores ({total}) "
                f"supera el máximo de 50 (RN-11)."
            )
        return self


# ---------------------------------------------------------------------------
# DTOs de REQUEST — optimize
# ---------------------------------------------------------------------------


class TroopTypeSpecRequest(BaseModel):
    """Tipo de tropa sin cantidad — Modo A del optimizador."""
    model_config = ConfigDict(extra="forbid")

    ordinal: int = Field(..., ge=1, le=30)
    smithy_level: int = Field(default=0, ge=0, le=20)


class TroopAvailabilityRequest(BaseModel):
    """Tropa disponible con cantidad máxima — Modo B del optimizador."""
    model_config = ConfigDict(extra="forbid")

    ordinal: int = Field(..., ge=1, le=30)
    quantity_available: int = Field(..., ge=0, le=1_000_000)
    smithy_level: int = Field(default=0, ge=0, le=20)


class AttackerOptimizeRequest(BaseModel):
    """Atacante para el optimizador — Modo A (troop_types) o Modo B (village_troops)."""
    model_config = ConfigDict(extra="forbid")

    tribe: Tribe
    troop_types: list[TroopTypeSpecRequest] | None = None
    village_troops: list[TroopAvailabilityRequest] | None = None
    hero_attack_points: float = Field(default=0.0, ge=0.0, le=20_000.0)
    hero_attack_bonus_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    alliance_bonus: float = Field(default=0.0, ge=0.0, le=5.0)
    artifacts: ArtifactsAttackerRequest = Field(
        default_factory=ArtifactsAttackerRequest
    )

    @model_validator(mode="after")
    def check_mode_exclusivity(self) -> "AttackerOptimizeRequest":
        has_types = self.troop_types is not None
        has_village = self.village_troops is not None
        if has_types and has_village:
            raise ValueError(
                "Los campos troop_types y village_troops son mutuamente excluyentes."
            )
        if not has_types and not has_village:
            raise ValueError(
                "Se debe proporcionar troop_types (Modo A) o village_troops (Modo B)."
            )
        if has_village:
            all_zero = all(t.quantity_available == 0 for t in (self.village_troops or []))
            if all_zero:
                raise ValueError(
                    "El ejército atacante no tiene tropas activas "
                    "(todos los quantity_available son 0)."
                )
        return self


class OasisDefenseTroopRequest(BaseModel):
    """Tropa de naturaleza en el oasis — sin tribu (siempre NATURE) y sin smithy."""
    model_config = ConfigDict(extra="forbid")

    ordinal: int = Field(..., ge=1, le=30)
    quantity: int = Field(..., ge=1, le=1_000_000)


class OasisDefenseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    troops: list[OasisDefenseTroopRequest] = Field(..., min_length=1)


class OptimizationWeightsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resources_gained: float = Field(default=1.0, ge=0.0)
    total_losses: float = Field(default=1.0, ge=0.0)
    troops_sent: float = Field(default=0.5, ge=0.0)
    travel_time: float = Field(default=0.0, ge=0.0)


class OptimizationConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exponent: float = Field(default=0.5, ge=0.4, le=0.6)
    server_speed: float = Field(default=1.0, ge=1.0, le=10.0)
    distance_fields: float | None = Field(default=None, gt=0)
    top_n: int = Field(default=3, ge=1, le=10)
    optimization_weights: OptimizationWeightsRequest = Field(
        default_factory=OptimizationWeightsRequest
    )


class OptimizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attacker: AttackerOptimizeRequest
    oasis_defense: OasisDefenseRequest
    config: OptimizationConfigRequest = Field(
        default_factory=OptimizationConfigRequest
    )


# ---------------------------------------------------------------------------
# DTOs de RESPONSE — comunes
# ---------------------------------------------------------------------------


class TroopResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tribe: str
    ordinal: int
    name: str
    icon_url: str | None
    quantity_initial: int
    quantity_survived: int
    quantity_lost: int


class AnimalResourceDropResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wood: int
    clay: int
    iron: int
    crop: int
    total: int


class LootResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capacity: int
    potential: int | None
    resources_gained_from_animals: AnimalResourceDropResponse | None


class TroopResourceLossResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tribe: str
    ordinal: int
    name: str
    quantity_lost: int
    cost_per_unit: dict
    total_cost: dict


class ResourceLossesBandResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_resources: int
    breakdown: list[TroopResourceLossResponse]


class ResourceLossesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attacker: ResourceLossesBandResponse
    defender: ResourceLossesBandResponse


class CatapultResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    building_gid: int
    level_before: int
    level_after: int
    hits: int


class StructuralDamageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    catapult_results: list[CatapultResultResponse]
    wall_before: int
    wall_after: int


# ---------------------------------------------------------------------------
# DTOs de RESPONSE — simulate
# ---------------------------------------------------------------------------


class SimulateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attacker_wins: bool
    ratio: float | None
    attacker_power: float
    defender_power: float
    attacker_troops: list[TroopResultResponse]
    defender_troops: list[TroopResultResponse]
    loot: LootResponse
    resource_losses: ResourceLossesResponse
    structural_damage: StructuralDamageResponse | None
    crop_consumption: int | None
    warnings: list[str]


# ---------------------------------------------------------------------------
# DTOs de RESPONSE — optimize
# ---------------------------------------------------------------------------


class OptimizationAlternativeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    is_winning: bool
    troops_sent: list[TroopResultResponse]
    total_losses: int
    total_resource_losses: int
    troops_sent_count: int
    attacker_power: float
    defender_power: float
    ratio: float
    resources_gained: AnimalResourceDropResponse | None
    loot: LootResponse | None
    travel_time_h: float | None


class OptimizeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    has_winning_combination: bool
    alternatives: list[OptimizationAlternativeResponse]
    defender_troops: list[TroopResultResponse]
    warnings: list[str]
    message: str | None


# ---------------------------------------------------------------------------
# Helpers de conversión entidades → DTOs de response
# ---------------------------------------------------------------------------


def _troop_result_to_response(tr) -> TroopResultResponse:
    return TroopResultResponse(
        tribe=tr.tribe.value if hasattr(tr.tribe, "value") else str(tr.tribe),
        ordinal=tr.ordinal,
        name=tr.name,
        icon_url=tr.icon_url,
        quantity_initial=tr.quantity_initial,
        quantity_survived=tr.quantity_survived,
        quantity_lost=tr.quantity_lost,
    )


def _animal_drop_to_response(ad) -> AnimalResourceDropResponse | None:
    if ad is None:
        return None
    return AnimalResourceDropResponse(
        wood=ad.wood,
        clay=ad.clay,
        iron=ad.iron,
        crop=ad.crop,
        total=ad.total,
    )


def _loot_to_response(loot) -> LootResponse:
    return LootResponse(
        capacity=loot.capacity,
        potential=loot.potential,
        resources_gained_from_animals=_animal_drop_to_response(
            loot.resources_gained_from_animals
        ),
    )


def _resource_losses_band_to_response(band) -> ResourceLossesBandResponse:
    return ResourceLossesBandResponse(
        total_resources=band.total_resources,
        breakdown=[
            TroopResourceLossResponse(
                tribe=item.tribe.value if hasattr(item.tribe, "value") else str(item.tribe),
                ordinal=item.ordinal,
                name=item.name,
                quantity_lost=item.quantity_lost,
                cost_per_unit=item.cost_per_unit,
                total_cost=item.total_cost,
            )
            for item in band.breakdown
        ],
    )


# ---------------------------------------------------------------------------
# Helpers de conversión request → entidades de dominio
# ---------------------------------------------------------------------------


def _build_attacker_formation(req: AttackerRequest) -> AttackerFormation:
    """Convierte AttackerRequest → AttackerFormation."""
    troops = [
        TroopEntry(
            tribe=t.tribe if t.tribe is not None else req.tribe,
            ordinal=t.ordinal,
            quantity=t.quantity,
            smithy_level=t.smithy_level,
        )
        for t in req.troops
    ]
    catapult_targets = [
        CatapultTarget(
            building_gid=ct.building_gid,
            current_level=ct.current_level,
        )
        for ct in req.catapult_targets
    ]
    rams = (
        RamSpec(quantity=req.rams.quantity, smithy_level=req.rams.smithy_level)
        if req.rams is not None
        else None
    )
    return AttackerFormation(
        tribe=req.tribe,
        troops=troops,
        attack_type=req.attack_type,
        hero_attack_points=req.hero_attack_points,
        hero_attack_bonus_percent=req.hero_attack_bonus_percent,
        alliance_bonus=req.alliance_bonus,
        morale=req.morale,
        artifacts=AttackerArtifacts(
            fast_troops=req.artifacts.fast_troops,
            diet=req.artifacts.diet,
        ),
        catapult_targets=catapult_targets,
        rams=rams,
    )


def _build_defender_formations(
    defenders: list[DefenderRequest],
) -> list[DefenderFormation]:
    """Convierte lista de DefenderRequest → lista de DefenderFormation."""
    result = []
    for d in defenders:
        troops = [
            TroopEntry(
                tribe=t.tribe if t.tribe is not None else (d.tribe or Tribe.NATURE),
                ordinal=t.ordinal,
                quantity=t.quantity,
                smithy_level=t.smithy_level,
            )
            for t in d.troops
        ]
        result.append(DefenderFormation(
            tribe=d.tribe,
            troops=troops,
            hero_defense_points=d.hero_defense_points,
            hero_defense_bonus_percent=d.hero_defense_bonus_percent,
            artifacts=DefenderArtifacts(
                strong_buildings=d.artifacts.strong_buildings,
                great_cranny=d.artifacts.great_cranny,
            ),
            village_resources=d.village_resources,
        ))
    return result


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/combat/simulate",
    response_model=SimulateResponse,
    summary="Simular combate Travian T4.5",
    description=(
        "Simula un combate dado un ejército atacante y uno o más ejércitos defensores. "
        "Calcula supervivientes, bajas, botín, recursos de animales muertos, "
        "coste en recursos de bajas, daño estructural (catapultas/arietes) y crop consumption. "
        "Idioma obligatorio: Accept-Language o ?lang= (400 si falta o no soportado). "
        "Cache-Control: no-store."
    ),
)
async def post_combat_simulate(
    body: SimulateRequest,
    response: Response,
    lang: str | None = Depends(resolve_language),
    game_data_port: GameDataPort = Depends(get_game_data_port),
    translation_port: TranslationPort = Depends(get_translation_port),
) -> SimulateResponse:
    """Handler de POST /combat/simulate."""
    response.headers["Cache-Control"] = "no-store"

    if lang is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Cabecera 'Accept-Language' u opción '?lang=' obligatoria. "
                f"Valores válidos: {sorted(SUPPORTED_LANGUAGES)}"
            ),
        )

    attacker = _build_attacker_formation(body.attacker)
    defenders = _build_defender_formations(body.defenders)
    wall = WallConfig(
        wall_level=body.wall.wall_level,
        stonemason_level=body.wall.stonemason_level,
        wall_tribe=body.wall.wall_tribe,
    )
    config = CombatConfig(
        exponent=body.config.exponent,
        server_speed=body.config.server_speed,
        distance_fields=body.config.distance_fields,
    )

    try:
        result = await simulate_combat(
            attacker=attacker,
            defenders=defenders,
            wall=wall,
            config=config,
            lang=lang,
            game_data_port=game_data_port,
            translation_port=translation_port,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    return SimulateResponse(
        attacker_wins=result.attacker_wins,
        ratio=result.ratio,
        attacker_power=result.attacker_power,
        defender_power=result.defender_power,
        attacker_troops=[_troop_result_to_response(t) for t in result.attacker_troops],
        defender_troops=[_troop_result_to_response(t) for t in result.defender_troops],
        loot=_loot_to_response(result.loot),
        resource_losses=ResourceLossesResponse(
            attacker=_resource_losses_band_to_response(result.resource_losses.attacker),
            defender=_resource_losses_band_to_response(result.resource_losses.defender),
        ),
        structural_damage=(
            StructuralDamageResponse(
                catapult_results=[
                    CatapultResultResponse(
                        building_gid=cr.building_gid,
                        level_before=cr.level_before,
                        level_after=cr.level_after,
                        hits=cr.hits,
                    )
                    for cr in result.structural_damage.catapult_results
                ],
                wall_before=result.structural_damage.wall_before,
                wall_after=result.structural_damage.wall_after,
            )
            if result.structural_damage is not None
            else None
        ),
        crop_consumption=result.crop_consumption,
        warnings=result.warnings,
    )


@router.post(
    "/combat/optimize",
    response_model=OptimizeResponse,
    summary="Optimizador de ataque a oasis (frente de Pareto multi-objetivo)",
    description=(
        "Dado un conjunto de tipos de tropas (Modo A: sin límite, Modo B: con cantidades "
        "máximas) y la defensa de un oasis, encuentra las mejores combinaciones según "
        "criterio multi-objetivo (recursos de animales, pérdidas en recursos, tropas enviadas, "
        "tiempo de marcha). Siempre devuelve alternativas (ganadoras si existen, no-ganadoras si no). "
        "Idioma obligatorio: Accept-Language o ?lang= (400 si falta o no soportado). "
        "Cache-Control: no-store."
    ),
)
async def post_combat_optimize(
    body: OptimizeRequest,
    response: Response,
    lang: str | None = Depends(resolve_language),
    game_data_port: GameDataPort = Depends(get_game_data_port),
    translation_port: TranslationPort = Depends(get_translation_port),
) -> OptimizeResponse:
    """Handler de POST /combat/optimize."""
    response.headers["Cache-Control"] = "no-store"

    if lang is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Cabecera 'Accept-Language' u opción '?lang=' obligatoria. "
                f"Valores válidos: {sorted(SUPPORTED_LANGUAGES)}"
            ),
        )

    # Construir troop_types o village_troops
    troop_types_domain = None
    village_troops_domain = None

    if body.attacker.troop_types is not None:
        troop_types_domain = [
            TroopTypeSpec(
                tribe=body.attacker.tribe,
                ordinal=t.ordinal,
                smithy_level=t.smithy_level,
            )
            for t in body.attacker.troop_types
        ]
    else:
        village_troops_domain = [
            TroopAvailability(
                tribe=body.attacker.tribe,
                ordinal=t.ordinal,
                quantity_available=t.quantity_available,
                smithy_level=t.smithy_level,
            )
            for t in (body.attacker.village_troops or [])
        ]

    oasis_defenders = [
        TroopEntry(
            tribe=Tribe.NATURE,
            ordinal=t.ordinal,
            quantity=t.quantity,
            smithy_level=0,
        )
        for t in body.oasis_defense.troops
    ]

    opt_config = OptimizationConfig(
        exponent=body.config.exponent,
        server_speed=body.config.server_speed,
        distance_fields=body.config.distance_fields,
        top_n=body.config.top_n,
        optimization_weights=OptimizationWeights(
            resources_gained=body.config.optimization_weights.resources_gained,
            total_losses=body.config.optimization_weights.total_losses,
            troops_sent=body.config.optimization_weights.troops_sent,
            travel_time=body.config.optimization_weights.travel_time,
        ),
    )

    artifacts = AttackerArtifacts(
        fast_troops=body.attacker.artifacts.fast_troops,
        diet=body.attacker.artifacts.diet,
    )

    try:
        result = await find_optimal_attack(
            attacker_tribe=body.attacker.tribe,
            troop_types=troop_types_domain,
            village_troops=village_troops_domain,
            hero_attack_points=body.attacker.hero_attack_points,
            hero_attack_bonus_percent=body.attacker.hero_attack_bonus_percent,
            alliance_bonus=body.attacker.alliance_bonus,
            artifacts=artifacts,
            oasis_defenders=oasis_defenders,
            opt_config=opt_config,
            lang=lang,
            game_data_port=game_data_port,
            translation_port=translation_port,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    return OptimizeResponse(
        has_winning_combination=result.has_winning_combination,
        alternatives=[
            OptimizationAlternativeResponse(
                rank=alt.rank,
                is_winning=alt.is_winning,
                troops_sent=[_troop_result_to_response(t) for t in alt.troops_sent],
                total_losses=alt.total_losses,
                total_resource_losses=alt.total_resource_losses,
                troops_sent_count=alt.troops_sent_count,
                attacker_power=alt.attacker_power,
                defender_power=alt.defender_power,
                ratio=alt.ratio,
                resources_gained=_animal_drop_to_response(alt.resources_gained),
                loot=(
                    _loot_to_response(alt.loot) if alt.loot is not None else None
                ),
                travel_time_h=alt.travel_time_h,
            )
            for alt in result.alternatives
        ],
        defender_troops=[
            _troop_result_to_response(t) for t in result.defender_troops
        ],
        warnings=result.warnings,
        message=result.message,
    )
