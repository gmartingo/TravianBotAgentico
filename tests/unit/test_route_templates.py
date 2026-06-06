"""
Tests unitarios para entidades RouteTemplate y RouteTemplatePath.

Cubre los casos TU-RT01 a TU-RT06 del spec §12 y los CA-RT01/CA-RT02.

Spec route-templates-developer-portal.md §12.
"""
from __future__ import annotations

import pytest

from core.entities.noise import (
    NavigationStep,
    NoiseAction,
    RouteTemplate,
    RouteTemplatePath,
)


# ---------------------------------------------------------------------------
# TU-RT01 — slug válido kebab-case
# ---------------------------------------------------------------------------

def test_TU_RT01_valid_slug():
    """RouteTemplate con slug válido kebab-case no lanza."""
    tpl = RouteTemplate(
        id=None,
        slug="rally-point-view",
        label="Rally Point",
        category_slug="building-view",
        url_pattern="/build.php?gid=13",
    )
    assert tpl.slug == "rally-point-view"


def test_valid_slug_with_numbers():
    """Slug con números también es válido."""
    tpl = RouteTemplate(
        id=None,
        slug="map-v2",
        label="Mapa v2",
        category_slug="map",
        url_pattern="/karte.php",
    )
    assert tpl.slug == "map-v2"


# ---------------------------------------------------------------------------
# TU-RT02 — slug inválido (no kebab-case) → ValueError (CA-RT01)
# ---------------------------------------------------------------------------

def test_TU_RT02_invalid_slug_spaces():
    """Slug con espacio o mayúsculas lanza ValueError."""
    with pytest.raises(ValueError, match="kebab-case"):
        RouteTemplate(
            id=None,
            slug="Rally Point",
            label="Rally Point",
            category_slug="building-view",
            url_pattern="/build.php?gid=13",
        )


def test_invalid_slug_uppercase():
    with pytest.raises(ValueError, match="kebab-case"):
        RouteTemplate(
            id=None,
            slug="Rally-Point",
            label="RP",
            category_slug="building-view",
            url_pattern="/build.php?gid=13",
        )


def test_invalid_slug_exclamation():
    """Slug con caracteres especiales lanza ValueError (CA-RT01)."""
    with pytest.raises(ValueError, match="kebab-case"):
        RouteTemplate(
            id=None,
            slug="bad slug!",
            label="Bad",
            category_slug="other",
            url_pattern="/karte.php",
        )


def test_invalid_slug_empty():
    with pytest.raises(ValueError):
        RouteTemplate(
            id=None,
            slug="",
            label="Bad",
            category_slug="other",
            url_pattern="/karte.php",
        )


# ---------------------------------------------------------------------------
# TU-RT03 — navigation_weight > 5.0 → ValueError (CA-RT02)
# ---------------------------------------------------------------------------

def test_TU_RT03_weight_too_high():
    """navigation_weight=5.01 lanza ValueError (CA-RT02)."""
    with pytest.raises(ValueError, match="navigation_weight"):
        RouteTemplate(
            id=None,
            slug="test-template",
            label="Test",
            category_slug="map",
            url_pattern="/karte.php",
            navigation_weight=5.01,
        )


# ---------------------------------------------------------------------------
# TU-RT04 — navigation_weight < 0.1 → ValueError
# ---------------------------------------------------------------------------

def test_TU_RT04_weight_too_low():
    """navigation_weight=0.09 lanza ValueError."""
    with pytest.raises(ValueError, match="navigation_weight"):
        RouteTemplate(
            id=None,
            slug="test-template",
            label="Test",
            category_slug="map",
            url_pattern="/karte.php",
            navigation_weight=0.09,
        )


def test_weight_boundary_valid_low():
    """navigation_weight=0.1 es válido."""
    tpl = RouteTemplate(
        id=None,
        slug="test-template",
        label="Test",
        category_slug="map",
        url_pattern="/karte.php",
        navigation_weight=0.1,
    )
    assert tpl.navigation_weight == 0.1


def test_weight_boundary_valid_high():
    """navigation_weight=5.0 es válido."""
    tpl = RouteTemplate(
        id=None,
        slug="test-template",
        label="Test",
        category_slug="map",
        url_pattern="/karte.php",
        navigation_weight=5.0,
    )
    assert tpl.navigation_weight == 5.0


# ---------------------------------------------------------------------------
# TU-RT05 — url_pattern vacío → ValueError
# ---------------------------------------------------------------------------

def test_TU_RT05_empty_url_pattern():
    """url_pattern vacío lanza ValueError."""
    with pytest.raises(ValueError, match="url_pattern"):
        RouteTemplate(
            id=None,
            slug="test-template",
            label="Test",
            category_slug="map",
            url_pattern="",
        )


def test_empty_label_raises():
    """label vacío lanza ValueError."""
    with pytest.raises(ValueError, match="label"):
        RouteTemplate(
            id=None,
            slug="test-template",
            label="",
            category_slug="map",
            url_pattern="/karte.php",
        )


# ---------------------------------------------------------------------------
# TU-RT06 — NavigationStep con delay_min_ms < 200 → ValueError (anti-detección)
# ---------------------------------------------------------------------------

def test_TU_RT06_step_delay_below_floor():
    """NavigationStep con delay_min_ms=199 en path de plantilla lanza ValueError."""
    with pytest.raises(ValueError, match="200"):
        NavigationStep(
            id=None,
            path_id=None,
            step_order=0,
            action=NoiseAction.CLICK,
            selector="a[href*='gid=13']",
            delay_min_ms=199,
            delay_max_ms=900,
        )


def test_step_delay_at_floor_ok():
    """NavigationStep con delay_min_ms=200 es válido."""
    step = NavigationStep(
        id=None,
        path_id=None,
        step_order=0,
        action=NoiseAction.CLICK,
        selector="a[href*='gid=13']",
        delay_min_ms=200,
        delay_max_ms=900,
    )
    assert step.delay_min_ms == 200


# ---------------------------------------------------------------------------
# RouteTemplatePath — validación de label
# ---------------------------------------------------------------------------

def test_template_path_empty_label_raises():
    """RouteTemplatePath con label vacío lanza ValueError."""
    with pytest.raises(ValueError, match="label"):
        RouteTemplatePath(
            id=None,
            template_id=None,
            origin="DORF2",
            label="",
        )


def test_template_path_valid():
    """RouteTemplatePath válido no lanza."""
    path = RouteTemplatePath(
        id=None,
        template_id=None,
        origin="DORF2",
        label="Desde aldea - edificios",
    )
    assert path.origin == "DORF2"
    assert path.is_active is True
    assert path.steps == []


# ---------------------------------------------------------------------------
# RouteTemplate con paths anidados
# ---------------------------------------------------------------------------

def test_template_with_paths_and_steps():
    """RouteTemplate puede tener paths con steps válidos."""
    step = NavigationStep(
        id=None,
        path_id=None,
        step_order=0,
        action=NoiseAction.CLICK,
        selector="a[href*='gid=13']",
        delay_min_ms=500,
        delay_max_ms=900,
    )
    path = RouteTemplatePath(
        id=None,
        template_id=None,
        origin="DORF2",
        label="Desde aldea",
        steps=[step],
    )
    tpl = RouteTemplate(
        id=None,
        slug="rally-point-view",
        label="Rally Point",
        category_slug="building-view",
        url_pattern="/build.php?gid=13",
        paths=[path],
    )
    assert len(tpl.paths) == 1
    assert len(tpl.paths[0].steps) == 1


def test_template_zero_paths_valid():
    """Plantilla sin paths es válida (EC-RT05)."""
    tpl = RouteTemplate(
        id=None,
        slug="player-own-profile",
        label="Perfil propio",
        category_slug="player-profile",
        url_pattern="/profile",
        paths=[],
    )
    assert tpl.paths == []
