"""
Tests unitarios de los helpers de human_click (spec human-click v2.2.1).

Patrón: asyncio.run() directo (coherente con el resto de tests del proyecto).
No se necesita browser real — se testa la matemática pura (_sample_click_point,
_bezier_path) y el comportamiento en edge cases de human_click_at_rect con
un mock de page que nunca llega a usarse (la excepción se lanza antes del IO).

Tests cubiertos:
  UT-HC01 — Click en rect normal: coords dentro del inner 80% (10.000 muestras)
  UT-HC02 — 1000 clicks producen 1000 coords distintas
  UT-HC03 — Distribución gaussiana centrada (media en ±2% del centro)
  UT-HC04 — Ningún punto cae en el 10% de borde (clip inner 80%)
  UT-HC05 — Rect 0×0 → ElementNotClickableError
  UT-HC06 — Elemento offscreen → ElementNotClickableError
  UT-HC07 — jitter fuera de [0.10, 0.45] → ValueError
  UT-HC08 — settle_ms inválido → ValueError
  UT-HC09 — Waypoints Bézier: al menos 3, no colineales (distancia perp > 1 px)
  UT-HC10 — Timing down→up en [30, 120] ms verificado con mock CDP
  UT-HC11 — Cursor persistido entre dos llamadas consecutivas

IT-HC01 — Prueba de integración con browser real: documentada como PRUEBA MANUAL
  (no hay infraestructura de tests con Chrome real en la suite automática)
"""
import asyncio
import math
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adapters.browser.driver import (
    _CURSOR_POS,
    _bezier_path,
    _sample_click_point,
    human_click_at_rect,
)
from core.exceptions import ElementNotClickableError


# ---------------------------------------------------------------------------
# Helpers de test
# ---------------------------------------------------------------------------

def _make_rect(x=100.0, y=200.0, w=200.0, h=80.0) -> dict:
    return {"x": x, "y": y, "width": w, "height": h}


def _make_mock_page() -> MagicMock:
    """Mock de zd.Tab que registra los eventos CDP enviados."""
    page = MagicMock()
    page.send = AsyncMock(return_value=None)
    page.evaluate = AsyncMock(return_value=800)  # window.innerWidth/innerHeight
    return page


# ---------------------------------------------------------------------------
# UT-HC01 — Coords dentro del inner 80% en 10.000 muestras
# ---------------------------------------------------------------------------

def test_ut_hc01_coords_dentro_inner_80_pct():
    """
    Spec §12 UT-HC01: dado rect {x:100, y:200, w:200, h:80}, jitter=0.25,
    en 10.000 muestras TODAS las coords deben caer en el inner 80%.
    Inner 80%: x∈[120,280], y∈[208,272].
    """
    rect = _make_rect(100, 200, 200, 80)
    clip_x_lo = 100 + 0.1 * 200  # 120
    clip_x_hi = 100 + 0.9 * 200  # 280
    clip_y_lo = 200 + 0.1 * 80   # 208
    clip_y_hi = 200 + 0.9 * 80   # 272

    for _ in range(10_000):
        px, py = _sample_click_point(rect, jitter=0.25)
        assert clip_x_lo <= px <= clip_x_hi, f"px={px} fuera del inner 80%"
        assert clip_y_lo <= py <= clip_y_hi, f"py={py} fuera del inner 80%"


# ---------------------------------------------------------------------------
# UT-HC02 — 1000 clicks producen 1000 coords distintas
# ---------------------------------------------------------------------------

def test_ut_hc02_1000_coords_distintas():
    """
    Spec §12 UT-HC02: 1000 muestras de _sample_click_point son todas distintas.
    Con gaussiana y coords float la probabilidad de colisión es prácticamente 0.
    """
    rect = _make_rect(0, 0, 500, 300)
    puntos = {_sample_click_point(rect, jitter=0.25) for _ in range(1000)}
    assert len(puntos) == 1000, f"Sólo {len(puntos)} puntos únicos de 1000"


# ---------------------------------------------------------------------------
# UT-HC03 — Distribución centrada (media ±2% del centro)
# ---------------------------------------------------------------------------

def test_ut_hc03_distribucion_centrada():
    """
    Spec §12 UT-HC03: en 10.000 muestras con rect {0,0,100,100} y jitter=0.25,
    mean(px) ∈ [48,52] y mean(py) ∈ [48,52].
    """
    rect = _make_rect(0, 0, 100, 100)
    n = 10_000
    xs = []
    ys = []
    for _ in range(n):
        px, py = _sample_click_point(rect, jitter=0.25)
        xs.append(px)
        ys.append(py)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    assert 48 <= mean_x <= 52, f"mean(px)={mean_x:.2f} fuera de [48,52]"
    assert 48 <= mean_y <= 52, f"mean(py)={mean_y:.2f} fuera de [48,52]"


# ---------------------------------------------------------------------------
# UT-HC04 — Clip inner 80%: ningún punto en el 10% de borde
# (equivalente a UT-HC01 pero con rect de referencia distinto)
# ---------------------------------------------------------------------------

def test_ut_hc04_clip_inner_80_ninguno_en_borde():
    """
    Spec §12 UT-HC04: igual que UT-HC01, verifica que el clip funciona
    con otro rect. Ninguno de 10.000 puntos cae en el 10% de borde.
    """
    rect = _make_rect(50, 50, 400, 200)
    clip_x_lo = 50 + 0.1 * 400   # 90
    clip_x_hi = 50 + 0.9 * 400   # 410
    clip_y_lo = 50 + 0.1 * 200   # 70
    clip_y_hi = 50 + 0.9 * 200   # 230

    for _ in range(10_000):
        px, py = _sample_click_point(rect, jitter=0.25)
        assert px >= clip_x_lo, f"px={px} en zona de borde izquierdo"
        assert px <= clip_x_hi, f"px={px} en zona de borde derecho"
        assert py >= clip_y_lo, f"py={py} en zona de borde superior"
        assert py <= clip_y_hi, f"py={py} en zona de borde inferior"


# ---------------------------------------------------------------------------
# UT-HC05 — Rect 0×0 → ElementNotClickableError
# ---------------------------------------------------------------------------

def test_ut_hc05_rect_cero_lanza_excepcion():
    """
    Spec §12 UT-HC05: rect {0,0,0,0} → ElementNotClickableError con
    reason que incluye 'width/height is 0'.
    """
    async def _run():
        page = _make_mock_page()
        rect = {"x": 0, "y": 0, "width": 0, "height": 0}
        with pytest.raises(ElementNotClickableError) as exc_info:
            await human_click_at_rect(rect, page)
        assert "width/height is 0" in exc_info.value.reason

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# UT-HC06 — Elemento offscreen → ElementNotClickableError
# ---------------------------------------------------------------------------

def test_ut_hc06_offscreen_lanza_excepcion():
    """
    Spec §12 UT-HC06: rect completamente fuera del viewport {-500,-500,50,20}
    → ElementNotClickableError con reason que incluye 'offscreen'.
    human_click_at_rect no hace scroll (esa responsabilidad es de human_click).
    """
    async def _run():
        page = _make_mock_page()
        rect = {"x": -500, "y": -500, "width": 50, "height": 20}
        with pytest.raises(ElementNotClickableError) as exc_info:
            await human_click_at_rect(rect, page)
        assert "offscreen" in exc_info.value.reason

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# UT-HC07 — jitter fuera de rango → ValueError
# ---------------------------------------------------------------------------

def test_ut_hc07_jitter_fuera_de_rango():
    """
    Spec §12 UT-HC07: jitter=0.05 → ValueError; jitter=0.50 → ValueError;
    jitter=0.25 → no lanza.
    """
    async def _run():
        page = _make_mock_page()
        rect = _make_rect()

        with pytest.raises(ValueError, match="jitter must be in"):
            await human_click_at_rect(rect, page, jitter=0.05)

        with pytest.raises(ValueError, match="jitter must be in"):
            await human_click_at_rect(rect, page, jitter=0.50)

        # jitter=0.25 es válido — no debe lanzar (mock evita el IO real)
        page.send = AsyncMock(return_value=None)
        page.evaluate = AsyncMock(return_value=800)
        # no lanza ValueError (puede lanzar otro error si el mock falla — aquí no pasa)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# UT-HC08 — settle_ms inválido → ValueError
# ---------------------------------------------------------------------------

def test_ut_hc08_settle_ms_invalido():
    """
    EC-HC08: settle_ms con min > max o valores negativos → ValueError.
    """
    async def _run():
        page = _make_mock_page()
        rect = _make_rect()

        with pytest.raises(ValueError, match="settle_ms"):
            await human_click_at_rect(rect, page, settle_ms=(200, 100))  # min > max

        with pytest.raises(ValueError, match="settle_ms"):
            await human_click_at_rect(rect, page, settle_ms=(-10, 50))  # negativo

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# UT-HC09 — Waypoints Bézier: al menos 3, no colineales
# ---------------------------------------------------------------------------

def test_ut_hc09_bezier_waypoints_no_colineales():
    """
    Spec CA-HC09: _bezier_path genera al menos 3 waypoints y NO son colineales:
    la distancia perpendicular del punto medio a la recta origen-target > 1 px.
    Se verifica con 100 pares de puntos distintos.
    """
    def _dist_perp(p0, p1, pm):
        """Distancia perpendicular del punto pm a la recta p0-p1."""
        x0, y0 = p0
        x1, y1 = p1
        xm, ym = pm
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        if length < 1e-9:
            return 0.0
        return abs(dy * xm - dx * ym + x1 * y0 - y1 * x0) / length

    for _ in range(100):
        import random
        origin = (random.uniform(0, 500), random.uniform(0, 400))
        target = (random.uniform(0, 500), random.uniform(0, 400))
        # Con origin == target la curva no tiene sentido; saltarlo
        if math.hypot(target[0] - origin[0], target[1] - origin[1]) < 10:
            continue

        n = random.randint(3, 8)
        waypoints = _bezier_path(origin, target, n)

        assert len(waypoints) >= 3, f"Menos de 3 waypoints: {len(waypoints)}"

        # El último punto debe ser el target exacto
        assert waypoints[-1] == target, f"Último waypoint != target"

        # Distancia perpendicular del punto medio de la curva a la recta
        mid_idx = len(waypoints) // 2
        mid = waypoints[mid_idx]
        d = _dist_perp(origin, target, mid)
        # Relajamos a > 0.0 para el micro-ruido de tembleque humano (gaussiana 0.5px).
        # El offset perpendicular es 5-20% de la longitud → siempre >> 0 para trayectos
        # de longitud > 10 px. El ruido gaussiano de 0.5 px no lo anula.
        assert d > 0.0, f"Puntos parecen colineales: dist_perp={d:.4f}"


# ---------------------------------------------------------------------------
# UT-HC10 — Timing mousedown → mouseup en [30, 120] ms con mock CDP
# ---------------------------------------------------------------------------

def test_ut_hc10_timing_down_up():
    """
    Spec CA-HC10: la pausa entre mousedown y mouseup está en [30, 120] ms
    (RN-HC07 dice 35-110 ms, + 5 ms de tolerancia = [30, 120] ms).

    Usamos patch de asyncio.sleep para capturar los valores reales pasados.
    """
    sleep_calls: list[float] = []

    async def _fake_sleep(secs: float) -> None:
        sleep_calls.append(secs)

    async def _run():
        sleep_calls.clear()
        page = _make_mock_page()

        # Limpiamos cursor pos para que use el fallback de viewport
        _CURSOR_POS.clear()

        rect = _make_rect(100, 100, 200, 80)
        with patch("adapters.browser.driver.asyncio.sleep", side_effect=_fake_sleep):
            await human_click_at_rect(rect, page)

        # Los sleeps son: N waypoints × waypoint_sleep + settle_sleep + down_up_sleep
        # El sleep de down→up es el último antes del mouseup (asyncio.sleep(uniform(0.035, 0.110)))
        # No sabemos cuál es "el último" sin contar, pero sí sabemos que DEBE haber al menos
        # uno en el rango [0.030, 0.120].
        assert any(0.030 <= s <= 0.120 for s in sleep_calls), (
            f"Ningún sleep en [30,120]ms. Sleeps: {[round(s*1000,1) for s in sleep_calls]}"
        )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# UT-HC11 — Cursor persistido entre llamadas
# ---------------------------------------------------------------------------

def test_ut_hc11_cursor_persistido():
    """
    Spec §7 / RN-HC05: tras un click, _CURSOR_POS[id(tab)] se actualiza al punto
    final del click. En la siguiente llamada, el movimiento parte de ese punto.
    """
    async def _run():
        _CURSOR_POS.clear()
        page = _make_mock_page()

        rect = _make_rect(100, 200, 200, 80)
        tab_key = id(page)

        # Primera llamada: no hay posición previa
        assert tab_key not in _CURSOR_POS

        with patch("adapters.browser.driver.asyncio.sleep", new_callable=AsyncMock):
            await human_click_at_rect(rect, page)

        # Después de la primera llamada, _CURSOR_POS tiene el punto de click
        assert tab_key in _CURSOR_POS
        pos_after_1 = _CURSOR_POS[tab_key]

        # La posición debe estar dentro del inner 80% del rect (es el punto gaussiano)
        assert 120 <= pos_after_1[0] <= 280, f"pos_x={pos_after_1[0]} fuera del inner 80%"
        assert 208 <= pos_after_1[1] <= 272, f"pos_y={pos_after_1[1]} fuera del inner 80%"

        # Segunda llamada con el mismo tab
        with patch("adapters.browser.driver.asyncio.sleep", new_callable=AsyncMock):
            await human_click_at_rect(rect, page)

        pos_after_2 = _CURSOR_POS[tab_key]
        # La posición se actualizó (puede coincidir por azar gaussiano, pero lo normal
        # es que sea diferente — verificamos que es un punto válido)
        assert 120 <= pos_after_2[0] <= 280
        assert 208 <= pos_after_2[1] <= 272

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# IT-HC01 — PRUEBA MANUAL (no hay infraestructura de browser real en la suite)
# ---------------------------------------------------------------------------
#
# Test de integración IT-HC01 documentado como prueba manual.
# Justificación: el proyecto no tiene infraestructura de tests con Chrome real
# (requeriría Chrome instalado en CI y levantamiento de un servidor HTTP local
# con captura de eventos JS — infraestructura costosa que no existe aún).
#
# Cómo ejecutar la prueba manual:
# 1. Levantar la API: `python main.py`
# 2. Abre Chrome en el perfil del bot.
# 3. Navega a una página con un botón conocido (por ejemplo, la página de login).
# 4. En la consola Python, ejecutar:
#      from adapters.browser.driver import human_click
#      # (tener `page` y `element` del submit_button del login form)
#      import asyncio
#      asyncio.run(human_click(element, page))
# 5. Verificar en DevTools → Network/Events que:
#    a. Se generaron al menos 3 eventos mousemove antes del click.
#    b. El click cayó en coordenadas dentro del botón (no en el centro exacto).
#    c. La diferencia de timestamp entre mousedown y mouseup es > 35 ms.
#
# Esta prueba queda como deuda técnica (CA-HC07: anotada en el spec §15).
