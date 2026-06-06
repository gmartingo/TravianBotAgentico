"""
Tests unitarios para entidades RouteTemplate y RouteTemplatePath (v1 + v2).

Cubre los casos del spec §12 (v1) y §v2.12 unitarios (TU-V2-01..TU-V2-07).

Spec route-templates-developer-portal.md §12, §v2.12.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from core.entities.noise import (
    NavigationStep,
    NoiseAction,
    NoiseCategory,
    RouteTemplate,
    RouteTemplatePath,
)
from core.use_cases.route_template_service import (
    CyclicOriginError,
    ResolvedStep,
    TemplateNotFoundError,
    resolve_origin_chain,
    validate_chain_integrity,
    validate_no_cycle,
    validate_selector_is_structural,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_template(
    template_id: int | None,
    slug: str,
    origin_template_id: int | None = None,
    with_step: bool = False,
) -> RouteTemplate:
    """Construye una RouteTemplate mínima válida."""
    paths: list[RouteTemplatePath] = []
    if with_step:
        step = NavigationStep(
            id=1 if template_id else None,
            path_id=template_id,
            step_order=0,
            action=NoiseAction.CLICK,
            selector=f"a[href*='{slug}']",
            delay_min_ms=417,
            delay_max_ms=823,
        )
        path = RouteTemplatePath(
            id=1 if template_id else None,
            template_id=template_id,
            origin="ANY",
            label=f"Path de {slug}",
            steps=[step],
        )
        paths = [path]
    return RouteTemplate(
        id=template_id,
        slug=slug,
        label=slug.replace("-", " ").title(),
        category=NoiseCategory.OTHER,
        url_pattern=f"/{slug}",
        origin_template_id=origin_template_id,
        paths=paths,
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
        category=NoiseCategory.BUILDING_VIEW,
        url_pattern="/build.php?gid=13",
    )
    assert tpl.slug == "rally-point-view"


def test_valid_slug_with_numbers():
    """Slug con números también es válido."""
    tpl = RouteTemplate(
        id=None,
        slug="map-v2",
        label="Mapa v2",
        category=NoiseCategory.MAP,
        url_pattern="/karte.php",
    )
    assert tpl.slug == "map-v2"


# ---------------------------------------------------------------------------
# TU-RT02 — slug inválido → ValueError (CA-RT01)
# ---------------------------------------------------------------------------

def test_TU_RT02_invalid_slug_spaces():
    """Slug con espacio lanza ValueError."""
    with pytest.raises(ValueError, match="kebab-case"):
        RouteTemplate(
            id=None,
            slug="Rally Point",
            label="Rally Point",
            category=NoiseCategory.BUILDING_VIEW,
            url_pattern="/build.php?gid=13",
        )


def test_invalid_slug_uppercase():
    with pytest.raises(ValueError, match="kebab-case"):
        RouteTemplate(
            id=None,
            slug="Rally-Point",
            label="RP",
            category=NoiseCategory.BUILDING_VIEW,
            url_pattern="/build.php?gid=13",
        )


def test_invalid_slug_exclamation():
    """CA-RT01: Slug con caracteres especiales lanza ValueError."""
    with pytest.raises(ValueError, match="kebab-case"):
        RouteTemplate(
            id=None,
            slug="bad slug!",
            label="Bad",
            category=NoiseCategory.OTHER,
            url_pattern="/karte.php",
        )


def test_invalid_slug_empty():
    with pytest.raises(ValueError):
        RouteTemplate(
            id=None,
            slug="",
            label="Bad",
            category=NoiseCategory.OTHER,
            url_pattern="/karte.php",
        )


# ---------------------------------------------------------------------------
# TU-RT03 — navigation_weight NO existe en la entidad (CA-RT02 — v2 rev.2)
# ---------------------------------------------------------------------------

def test_TU_RT03_navigation_weight_not_accepted():
    """
    CA-RT02: RouteTemplate NO acepta navigation_weight como parámetro.
    En v2 rev.2 el peso fue eliminado de la entidad.
    Spec §v2-PESO, §v2.2.3.
    """
    with pytest.raises(TypeError):
        RouteTemplate(  # type: ignore[call-arg]
            id=None,
            slug="test-template",
            label="Test",
            category=NoiseCategory.MAP,
            url_pattern="/karte.php",
            navigation_weight=5.01,  # campo eliminado → TypeError
        )


def test_navigation_weight_not_in_fields():
    """navigation_weight no aparece en los campos del dataclass."""
    tpl = RouteTemplate(
        id=None,
        slug="test-template",
        label="Test",
        category=NoiseCategory.MAP,
        url_pattern="/karte.php",
    )
    assert not hasattr(tpl, "navigation_weight"), (
        "navigation_weight fue eliminado de RouteTemplate en v2 rev.2"
    )


# ---------------------------------------------------------------------------
# TU-RT04 — origin_template_id en la entidad (v2)
# ---------------------------------------------------------------------------

def test_origin_template_id_default_none():
    """origin_template_id por defecto es None (ruta raíz)."""
    tpl = RouteTemplate(
        id=None,
        slug="statistics",
        label="Estadísticas",
        category=NoiseCategory.OTHER,
        url_pattern="/statistics",
    )
    assert tpl.origin_template_id is None


def test_origin_template_id_can_be_set():
    """origin_template_id puede ser un entero (ruta hija)."""
    tpl = RouteTemplate(
        id=None,
        slug="top10-alianzas",
        label="Top 10 Alianzas",
        category=NoiseCategory.OTHER,
        url_pattern="/statistics/alliances",
        origin_template_id=5,
    )
    assert tpl.origin_template_id == 5


# ---------------------------------------------------------------------------
# TU-RT05 — url_pattern vacío → ValueError
# ---------------------------------------------------------------------------

def test_TU_RT05_empty_url_pattern():
    with pytest.raises(ValueError, match="url_pattern"):
        RouteTemplate(
            id=None,
            slug="test-template",
            label="Test",
            category=NoiseCategory.MAP,
            url_pattern="",
        )


def test_empty_label_raises():
    with pytest.raises(ValueError, match="label"):
        RouteTemplate(
            id=None,
            slug="test-template",
            label="",
            category=NoiseCategory.MAP,
            url_pattern="/karte.php",
        )


# ---------------------------------------------------------------------------
# TU-RT06 — NavigationStep con delay_min_ms < 200 → ValueError (anti-detección)
# ---------------------------------------------------------------------------

def test_TU_RT06_step_delay_below_floor():
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
    with pytest.raises(ValueError, match="label"):
        RouteTemplatePath(
            id=None,
            template_id=None,
            origin="DORF2",
            label="",
        )


def test_template_path_valid():
    path = RouteTemplatePath(
        id=None,
        template_id=None,
        origin="DORF2",
        label="Desde aldea - edificios",
    )
    assert path.origin == "DORF2"
    assert path.is_active is True
    assert path.steps == []


def test_template_zero_paths_valid():
    """EC-RT05: Plantilla sin paths es válida."""
    tpl = RouteTemplate(
        id=None,
        slug="player-own-profile",
        label="Perfil propio",
        category=NoiseCategory.PLAYER_PROFILE,
        url_pattern="/profile",
        paths=[],
    )
    assert tpl.paths == []


# ===========================================================================
# Tests v2 — core/use_cases/route_template_service.py
# ===========================================================================

# ---------------------------------------------------------------------------
# TU-V2-01 — validate_no_cycle: auto-ciclo A → A (EC-V2-01)
# ---------------------------------------------------------------------------

def test_TU_V2_01_auto_cycle():
    """
    validate_no_cycle(A, origin=A) detecta el auto-ciclo en la primera iteración.
    EC-V2-01: current_id == new_template_id en el primer paso.
    """
    # A intenta apuntarse a sí misma como origen
    db_mock = AsyncMock()
    # get_template nunca debería llamarse (detecta el ciclo antes)

    with pytest.raises(CyclicOriginError) as exc_info:
        asyncio.run(validate_no_cycle(
            new_template_id=5,
            proposed_origin_id=5,  # auto-referencia
            db=db_mock,
        ))
    assert 5 in exc_info.value.cycle_path


# ---------------------------------------------------------------------------
# TU-V2-02 — validate_no_cycle: ciclo indirecto C → B → A → C
# ---------------------------------------------------------------------------

def test_TU_V2_02_indirect_cycle():
    """
    EC-V2-02: ciclo indirecto C → B → A → C al editar A para poner origin=C.
    Escenario: ya existe la cadena C(3).origin=B(2), B(2).origin=A(1).
    Ahora A(1) intenta poner origin=C(3).
    validate_no_cycle(new=A=1, proposed=C=3):
      - sube por 3 → origin=2 → 2 → origin=1 → 1 == new_template_id → ciclo.
    """
    # Cadena existente en BD: C(3)→B(2)→A(1)→None
    # A(1): origin=None (raíz)
    # B(2): origin=A(1)
    # C(3): origin=B(2)
    tpl_a = _make_template(1, "statistics", origin_template_id=None)
    tpl_b = _make_template(2, "top10-alianzas", origin_template_id=1)
    tpl_c = _make_template(3, "top10-alianza-rivales", origin_template_id=2)

    # Ahora A(1) quiere poner origin=C(3):
    # validate_no_cycle(new=1, proposed=3)
    # current=3, 3 != 1, not in visited → visit 3; ancestor(3).origin=2 → next=2
    # current=2, 2 != 1, not in visited → visit 2; ancestor(2).origin=1 → next=1
    # current=1 == new_template_id → CyclicOriginError

    tpl_map = {1: tpl_a, 2: tpl_b, 3: tpl_c}

    async def mock_get(tid):
        return tpl_map.get(tid)

    db_mock = AsyncMock()
    db_mock.get_template = AsyncMock(side_effect=mock_get)

    with pytest.raises(CyclicOriginError) as exc_info:
        asyncio.run(validate_no_cycle(
            new_template_id=1,    # A está siendo editada
            proposed_origin_id=3, # A quiere apuntar a C (que ya está en la cadena de A)
            db=db_mock,
        ))
    assert 1 in exc_info.value.cycle_path


# ---------------------------------------------------------------------------
# TU-V2-03 — validate_no_cycle: sin ciclo para D
# ---------------------------------------------------------------------------

def test_TU_V2_03_no_cycle():
    """
    validate_no_cycle(D=4, origin=A=1) donde A→B→C (sin D).
    No lanza excepción.
    """
    tpl_a = _make_template(1, "statistics", origin_template_id=None)
    tpl_b = _make_template(2, "top10-alianzas", origin_template_id=1)
    tpl_c = _make_template(3, "top10-alianza-rivales", origin_template_id=2)

    tpl_map = {1: tpl_a, 2: tpl_b, 3: tpl_c}

    async def mock_get(tid):
        return tpl_map.get(tid)

    db_mock = AsyncMock()
    db_mock.get_template = AsyncMock(side_effect=mock_get)

    # No debe lanzar excepción
    asyncio.run(validate_no_cycle(
        new_template_id=4,
        proposed_origin_id=3,
        db=db_mock,
    ))


# ---------------------------------------------------------------------------
# TU-V2-04 — validate_no_cycle: cadena de 21 niveles → CyclicOriginError
# ---------------------------------------------------------------------------

def test_TU_V2_04_depth_exceeded():
    """
    EC-V2-04: cadena de 21 niveles supera max_depth=20 → CyclicOriginError.
    """
    # Crear 21 plantillas encadenadas: 21 → 20 → ... → 1 (sin ciclo real)
    tpl_map = {}
    for i in range(1, 23):
        origin = i - 1 if i > 1 else None
        tpl_map[i] = _make_template(i, f"ruta-{i}", origin_template_id=origin)

    async def mock_get(tid):
        return tpl_map.get(tid)

    db_mock = AsyncMock()
    db_mock.get_template = AsyncMock(side_effect=mock_get)

    with pytest.raises(CyclicOriginError):
        asyncio.run(validate_no_cycle(
            new_template_id=99,   # ID que no existe en la cadena
            proposed_origin_id=21,
            db=db_mock,
            max_depth=20,
        ))


# ---------------------------------------------------------------------------
# TU-V2-05 — resolve_origin_chain: plantilla raíz (sin origen)
# ---------------------------------------------------------------------------

def test_TU_V2_05_resolve_root():
    """
    resolve_origin_chain(raíz) devuelve [ResolvedStep de la raíz].
    La raíz tiene origin_template_id=None y 1 path con 1 step.
    """
    tpl_root = _make_template(1, "statistics", origin_template_id=None, with_step=True)
    db_mock = AsyncMock()
    db_mock.get_template = AsyncMock(return_value=tpl_root)

    result: list[ResolvedStep] = asyncio.run(resolve_origin_chain(1, db_mock))

    assert len(result) == 1
    assert result[0].template_id == 1
    assert result[0].template_slug == "statistics"


# ---------------------------------------------------------------------------
# TU-V2-06 — resolve_origin_chain: cadena de 3 niveles
# ---------------------------------------------------------------------------

def test_TU_V2_06_resolve_chain_3_levels():
    """
    Cadena statistics(1) → top10-alianzas(2) → top10-alianza-rivales(3).
    resolve_origin_chain(3) devuelve [paso_raíz(1), paso_medio(2), paso_hoja(3)].
    """
    tpl_1 = _make_template(1, "statistics", origin_template_id=None, with_step=True)
    tpl_2 = _make_template(2, "top10-alianzas", origin_template_id=1, with_step=True)
    tpl_3 = _make_template(3, "top10-alianza-rivales", origin_template_id=2, with_step=True)

    tpl_map = {1: tpl_1, 2: tpl_2, 3: tpl_3}

    async def mock_get(tid):
        return tpl_map.get(tid)

    db_mock = AsyncMock()
    db_mock.get_template = AsyncMock(side_effect=mock_get)

    result: list[ResolvedStep] = asyncio.run(resolve_origin_chain(3, db_mock))

    assert len(result) == 3
    assert result[0].template_id == 1  # raíz primero
    assert result[1].template_id == 2
    assert result[2].template_id == 3  # hoja al final


# ---------------------------------------------------------------------------
# TU-V2-07 — resolve_origin_chain: nodo intermedio sin steps → se salta
# ---------------------------------------------------------------------------

def test_TU_V2_07_resolve_skips_empty_node():
    """
    EC-V2-07: nodo intermedio sin path/step no aporta clic.
    resolve_origin_chain(3) devuelve solo los nodos con step definido.
    """
    tpl_1 = _make_template(1, "statistics", origin_template_id=None, with_step=True)
    # tpl_2 sin steps
    tpl_2 = _make_template(2, "top10-alianzas", origin_template_id=1, with_step=False)
    tpl_3 = _make_template(3, "top10-alianza-rivales", origin_template_id=2, with_step=True)

    tpl_map = {1: tpl_1, 2: tpl_2, 3: tpl_3}

    async def mock_get(tid):
        return tpl_map.get(tid)

    db_mock = AsyncMock()
    db_mock.get_template = AsyncMock(side_effect=mock_get)

    result: list[ResolvedStep] = asyncio.run(resolve_origin_chain(3, db_mock))

    # El nodo 2 (sin steps) se salta
    assert len(result) == 2
    template_ids = [r.template_id for r in result]
    assert 1 in template_ids
    assert 3 in template_ids
    assert 2 not in template_ids


# ---------------------------------------------------------------------------
# TU-V2 extra — resolve_origin_chain: origen borrado corta la cadena (EC-V2-03)
# ---------------------------------------------------------------------------

def test_resolve_origin_deleted_cuts_chain():
    """
    Si origen está borrado (ON DELETE SET NULL → origin_template_id=None),
    la plantilla queda como raíz. resolve_origin_chain devuelve solo su propio step.
    """
    # tpl_orphan tiene origin_template_id=None porque el origen fue borrado
    tpl_orphan = _make_template(7, "orphan-route", origin_template_id=None, with_step=True)
    db_mock = AsyncMock()
    db_mock.get_template = AsyncMock(return_value=tpl_orphan)

    result = asyncio.run(resolve_origin_chain(7, db_mock))
    assert len(result) == 1
    assert result[0].template_id == 7


# ---------------------------------------------------------------------------
# Tests de validate_selector_is_structural (GAP-4, §v2-REGLA-SELECTORES)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_selector", [
    "a:has-text(\"Estadísticas\")",
    "li:contains(\"Mensajes\")",
    "//a[text()=\"Mapa\"]",
    "//span[contains(text(),\"Rally\")]",
])
def test_selector_forbidden_patterns_raise(bad_selector: str):
    """
    CA-V2-18 (GAP-4): selectores con texto visible lanzan ValueError.
    Patrones: :has-text(, :contains(, text()=, contains(text(),.
    """
    with pytest.raises(ValueError, match="texto visible"):
        validate_selector_is_structural(bad_selector)


@pytest.mark.parametrize("good_selector", [
    "a[href*='gid=13']",
    "a[href*='/statistics']",
    "#map",
    ".build-title",
    "[type='submit']",
    "a.alliance-name:nth-child(2)",
    "input[name='username']",
])
def test_selector_structural_ok(good_selector: str):
    """
    CA-V2-18 (GAP-4): selectores estructurales no lanzan excepción.
    """
    # No debe lanzar
    validate_selector_is_structural(good_selector)


# ---------------------------------------------------------------------------
# Tests de validate_chain_integrity (creación)
# ---------------------------------------------------------------------------

def test_validate_chain_integrity_no_cycle():
    """
    validate_chain_integrity no lanza si la cadena del origen propuesto es válida.
    """
    tpl_root = _make_template(1, "statistics", origin_template_id=None)
    db_mock = AsyncMock()
    db_mock.get_template = AsyncMock(return_value=tpl_root)

    # No debe lanzar
    asyncio.run(validate_chain_integrity(proposed_origin_id=1, db=db_mock))


def test_validate_chain_integrity_missing_origin_ok():
    """
    Si el origen no existe en BD (rompe la cadena), validate_chain_integrity
    no lanza CyclicOriginError (es responsabilidad del handler lanzar 404).
    """
    db_mock = AsyncMock()
    db_mock.get_template = AsyncMock(return_value=None)  # origen no existe

    # No debe lanzar CyclicOriginError (el 404 lo hace el handler)
    asyncio.run(validate_chain_integrity(proposed_origin_id=999, db=db_mock))
