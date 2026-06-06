"""
Entidades del dominio de Ruido Humano de Navegación.

Define los tipos de datos para el sistema de navegación de ruido:
destinos de navegación, rutas con pasos, y configuración de ruido por mundo.

Spec human-sessions.md §7 (sección v2.2 — Ruido Humano de Navegación).
Spec noise-path-wizard.md §7 (ampliación — anclas semilla, wizard, derive-selector).
Spec route-templates-developer-portal.md §7 (RouteTemplate + RouteTemplatePath).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class NoiseCategory(str, Enum):
    """
    Categoría de destino de navegación de ruido.

    DEPRECATED: reemplazado por RouteCategory (catálogo dinámico).
    Spec route-categories-dynamic.md §2 (Paso 14 de implementación).
    Se mantiene temporalmente para compatibilidad durante la migración.
    Una vez que todos los tests y adaptadores usen category_slug: str,
    este enum se eliminará del codebase.
    """
    MAP             = "MAP"
    OASIS_INFO      = "OASIS_INFO"
    PLAYER_PROFILE  = "PLAYER_PROFILE"
    MESSAGES        = "MESSAGES"
    REPORTS         = "REPORTS"
    BUILDING_VIEW   = "BUILDING_VIEW"
    OTHER           = "OTHER"


class NavigationOrigin(str, Enum):
    """
    Origen desde el que se puede iniciar una ruta de navegación.

    Estos 9 valores son los orígenes genéricos fijos del sistema. Los orígenes
    por-aldea (VILLAGE_<data_id>) NO son valores de este enum: son cadenas
    dinámicas almacenadas como texto en BD y validadas en la capa de aplicación.

    Spec noise-path-wizard.md §7.1 / RN-NP01.
    """
    DORF1              = "DORF1"               # /dorf1.php (aldea activa - recursos)
    DORF2              = "DORF2"               # /dorf2.php (aldea activa - edificios)
    MAP                = "MAP"                 # /karte.php
    STATISTICS         = "STATISTICS"          # /statistics
    REPORTS            = "REPORTS"             # /report
    MESSAGES           = "MESSAGES"            # /messages
    VILLAGE_STATISTICS = "VILLAGE_STATISTICS"  # /village/statistics
    OASIS_VIEW         = "OASIS_VIEW"          # /karte.php (hash gestionado por el primer paso)
    ANY                = "ANY"                 # sin ancla fija


# Rutas relativas asociadas a cada origen genérico.
# OASIS_VIEW: la parte de hash (#type=oasis) la gestiona el primer paso de la ruta.
# ANY: sin navegación previa (cadena vacía).
ORIGIN_PATHS: dict[NavigationOrigin, str] = {
    NavigationOrigin.DORF1:              "/dorf1.php",
    NavigationOrigin.DORF2:              "/dorf2.php",
    NavigationOrigin.MAP:                "/karte.php",
    NavigationOrigin.STATISTICS:         "/statistics",
    NavigationOrigin.REPORTS:            "/report",
    NavigationOrigin.MESSAGES:           "/messages",
    NavigationOrigin.VILLAGE_STATISTICS: "/village/statistics",
    NavigationOrigin.OASIS_VIEW:         "/karte.php",
    NavigationOrigin.ANY:                "",
}


class NoiseAction(str, Enum):
    """Tipo de acción en un paso de navegación."""
    CLICK              = "CLICK"
    WAIT_FOR_SELECTOR  = "WAIT_FOR_SELECTOR"
    SCROLL_TO          = "SCROLL_TO"
    HOVER              = "HOVER"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class NoiseDestination:
    """
    Destino de navegación de ruido.

    url_pattern es inmutable tras la creación.
    category_slug es editable (spec route-categories-dynamic.md §4 RN-CAT11).

    template_id (nullable): FK a route_templates.id cuando este destino fue
    creado clonando una plantilla maestra (M-RT01). None si fue creado a mano.
    Spec route-templates-developer-portal.md §7.3.
    """
    id: int | None
    world_id: int
    url_pattern: str
    label: str
    category_slug: str                        # slug de RouteCategory (antes: NoiseCategory enum)
    frequency_weight: float                   # > 0
    is_safe: bool = True
    is_dead: bool = False
    consecutive_failures_count: int = 0
    created_at: datetime | None = None
    last_used_at: datetime | None = None
    template_id: int | None = None            # M-RT01: NULL si creado a mano

    def __post_init__(self) -> None:
        # RN-FW07 (GUARDIAN — NO NEGOCIABLE): rango cerrado [0.1, 5.0].
        # Un peso fuera de este rango convierte el pathing en predecible y detectable.
        if not (0.1 <= self.frequency_weight <= 5.0):
            raise ValueError(
                "navigation_weight debe estar entre 0.1 y 5.0 "
                "(anti-detección: pesos extremos hacen el ruido predecible)"
            )
        if not self.url_pattern.strip():
            raise ValueError("url_pattern no puede estar vacío")
        if not self.label.strip():
            raise ValueError("label no puede estar vacío")


@dataclass
class NavigationStep:
    """
    Un paso dentro de una ruta de navegación.
    delay_min_ms/delay_max_ms controlan el wait humanizado entre pasos.

    Spec noise-path-wizard.md §7.4: añade expected_url_after_click.
    """
    id: int | None
    path_id: int | None
    step_order: int                           # 0-based, UNIQUE dentro del path
    action: NoiseAction
    selector: str                             # selector CSS estructural
    value: str = ""                           # para WAIT_FOR_SELECTOR: timeout en ms como str
    delay_min_ms: int = 500
    delay_max_ms: int = 900
    expected_url_after_click: str | None = None  # URL esperada tras CLICK (None = sin verificación)

    # ANTI-DETECCION (Capa 3 — timing humano, NO negociable):
    # El ruido es interacción DIRECTA con Travian. Encadenar pasos (click/hover)
    # con delay 0 o instantáneo es una firma robótica trivial. La invariante no
    # puede depender de que el usuario "no ponga 0": se blinda en la entidad, que
    # es la fuente de verdad del core. Piso 200 ms (umbral de reacción humana —
    # por debajo no es humanamente reactivo) y techo 5000 ms (un delay mayor sería
    # "lento por miedo", no humano). Los defaults reales (500-900) quedan holgados.
    NOISE_STEP_DELAY_FLOOR_MS = 200
    NOISE_STEP_DELAY_CEILING_MS = 5000

    def __post_init__(self) -> None:
        if self.delay_min_ms < 0:
            raise ValueError("delay_min_ms debe ser >= 0")
        if self.delay_max_ms < self.delay_min_ms:
            raise ValueError("delay_max_ms debe ser >= delay_min_ms")
        # Capa 3 anti-detección: no permitir encadenamiento sin delay humano.
        if self.delay_min_ms < self.NOISE_STEP_DELAY_FLOOR_MS:
            raise ValueError(
                f"delay_min_ms debe ser >= {self.NOISE_STEP_DELAY_FLOOR_MS} ms "
                "(anti-detección: clicks/hover sobre Travian no pueden encadenarse "
                "sin un delay humano mínimo)"
            )
        if self.delay_max_ms > self.NOISE_STEP_DELAY_CEILING_MS:
            raise ValueError(
                f"delay_max_ms debe ser <= {self.NOISE_STEP_DELAY_CEILING_MS} ms "
                "(anti-detección: un delay mayor es 'lento por miedo', no humano)"
            )
        if not self.selector.strip():
            raise ValueError("selector no puede estar vacío")


@dataclass
class NavigationPath:
    """
    Ruta de navegación hacia un destino de ruido.
    Contiene pasos ordenados por step_order ASC.

    Spec noise-path-wizard.md §7.5:
    - origin es str (no NavigationOrigin): admite "VILLAGE_<data_id>" dinámicos.
    - consecutive_failures_count: contador de fallos consecutivos de expected_url_after_click.
    """
    id: int | None
    destination_id: int
    origin: str                                      # str — admite NavigationOrigin.value + "VILLAGE_<n>"
    label: str
    is_active: bool = True
    is_dead: bool = False                            # True si consecutive_failures >= THRESHOLD (RN-NP07)
    consecutive_failures_count: int = 0              # fallos consecutivos de URL-check (RN-NP07)
    steps: list[NavigationStep] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("label no puede estar vacío")


@dataclass
class RouteTemplatePath:
    """
    Ruta dentro de una plantilla global de ruido.

    Sin destination_id — la plantilla no es por-mundo.
    Sin is_dead / consecutive_failures_count — campos operacionales por-mundo.

    Spec route-templates-developer-portal.md §7.1.
    """
    id: int | None
    template_id: int | None
    origin: str                  # str — admite NavigationOrigin.value + "VILLAGE_<n>"
    label: str
    is_active: bool = True
    steps: list[NavigationStep] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("label no puede estar vacío")


@dataclass
class RouteTemplate:
    """
    Plantilla global de ruta de navegación de ruido.

    Sin world_id — es global a la instalación del bot.
    Slug único globalmente (RN-RT02).
    Los steps siguen las mismas restricciones anti-detección que NavigationStep.

    Spec route-templates-developer-portal.md §7.1.
    """
    id: int | None
    slug: str                              # kebab-case, UNIQUE global
    label: str
    category_slug: str                     # slug de RouteCategory (antes: NoiseCategory enum)
    url_pattern: str
    navigation_weight: float = 1.0         # peso inicial sugerido al clonar (0.1–5.0)
    is_safe: bool = True
    paths: list[RouteTemplatePath] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not (0.1 <= self.navigation_weight <= 5.0):
            raise ValueError(
                "navigation_weight debe estar entre 0.1 y 5.0 "
                "(anti-detección: pesos extremos hacen el ruido predecible)"
            )
        if not self.slug.strip():
            raise ValueError("slug no puede estar vacío")
        if not re.match(r'^[a-z0-9]+(?:-[a-z0-9]+)*$', self.slug):
            raise ValueError(
                "slug debe ser kebab-case: solo letras minúsculas, dígitos y guiones"
            )
        if not self.label.strip():
            raise ValueError("label no puede estar vacío")
        if not self.url_pattern.strip():
            raise ValueError("url_pattern no puede estar vacío")


@dataclass
class NoiseConfig:
    """
    Configuración de ruido por mundo.

    Valores por defecto (v2 — intervalo directo en segundos):
      - noise_enabled = True
      - HARDCORE: intervalo 30–90 s entre navegaciones
      - PASIVO:   intervalo 180–1200 s entre navegaciones
      - dwell:    2–30 s

    Spec noise-frequency-and-destination-weight.md §7.1 (reemplaza req_per_hour).
    """
    world_id: int
    noise_enabled: bool = True
    hardcore_interval_min_seconds: int = 30       # antes: hardcore_total_req_per_hour_min=80
    hardcore_interval_max_seconds: int = 90       # antes: hardcore_total_req_per_hour_max=150
    passive_interval_min_seconds: int = 180       # antes: passive_total_req_per_hour_min=15
    passive_interval_max_seconds: int = 1200      # antes: passive_total_req_per_hour_max=40
    dwell_min_seconds: float = 2.0
    dwell_max_seconds: float = 30.0

    def __post_init__(self) -> None:
        # RN-FW02 (GUARDIAN — NO NEGOCIABLE): mínimo 30 s para cualquier intervalo.
        # Piso blindado en la entidad (fuente de verdad del core), no solo en la API.
        _MIN_INTERVAL = 30
        for attr, val in [
            ("hardcore_interval_min_seconds", self.hardcore_interval_min_seconds),
            ("hardcore_interval_max_seconds", self.hardcore_interval_max_seconds),
            ("passive_interval_min_seconds",  self.passive_interval_min_seconds),
            ("passive_interval_max_seconds",  self.passive_interval_max_seconds),
        ]:
            if val < _MIN_INTERVAL:
                raise ValueError(
                    f"El intervalo mínimo es 30 segundos (00:30) — anti-detección "
                    f"({attr} recibido: {val})"
                )
        if self.hardcore_interval_max_seconds < self.hardcore_interval_min_seconds:
            raise ValueError(
                "hardcore_interval_max_seconds debe ser >= hardcore_interval_min_seconds"
            )
        if self.passive_interval_max_seconds < self.passive_interval_min_seconds:
            raise ValueError(
                "passive_interval_max_seconds debe ser >= passive_interval_min_seconds"
            )
        if self.dwell_min_seconds < 0:
            raise ValueError("dwell_min_seconds debe ser >= 0")
        if self.dwell_max_seconds < self.dwell_min_seconds:
            raise ValueError("dwell_max_seconds debe ser >= dwell_min_seconds")
