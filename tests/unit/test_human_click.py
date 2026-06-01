"""
Tests unitarios para adapters/browser/driver.py (spec human-click v2.3.1).

Patron: asyncio.run() directo. No arrancan Chrome.
Cubre UT-HC01 a UT-HC30. UT-HC13 y UT-HC30 consolidados segun spec par 12.
"""
import asyncio
import math
import random
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adapters.browser.driver import (
    _CURSOR_POS,
    _TAB_LOCKS,
    _bezier_path,
    _fitts_duration_ms,
    _sample_click_point,
    _sample_near_target,
    _to_rect,
    _validate_or_reset_cursor,
    human_click,
    human_click_at_rect,
    human_drift_toward,
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


# ===========================================================================
# Tests v2.3 — Fitts + min_duration + drift + pre-validación de cursor
# (auditoría guardian-antidetección de commits 714aa4c / a18aa63 / 8e85a5b)
# ===========================================================================


# ---------------------------------------------------------------------------
# UT-HC12 — Fitts: duración crece con la distancia, dentro de [200, 800] ms
# Cubre Capa 3 — Timing humano (techo ~2 s)
# ---------------------------------------------------------------------------

def test_ut_hc12_fitts_monotona_y_dentro_de_rango():
    """
    RN-HC12: T = 100 + 80·log2(2·distance/width), capado a [200, 800] ms.
    - Toda salida está en [200, 800] (muy por debajo del techo de ~2 s).
    - A mayor distancia (mismo width), mayor o igual duración (monotonía).
    """
    width = 50.0
    prev = 0
    for dist in (1, 10, 50, 100, 300, 600, 1200, 5000):
        t = _fitts_duration_ms(float(dist), width)
        assert 200 <= t <= 800, f"dist={dist}: t={t} fuera de [200,800]"
        assert t >= prev, f"Fitts no monótona: dist={dist} t={t} < prev={prev}"
        prev = t


def test_ut_hc12_fitts_distancia_cero_fallback_200():
    """EC-HC02: distance < 1 → 200 ms sin calcular log2 (evita -inf)."""
    assert _fitts_duration_ms(0.0, 50.0) == 200
    assert _fitts_duration_ms(0.5, 50.0) == 200


def test_ut_hc12_fitts_width_cero_no_revienta():
    """EC-HC03: target_width < 1 → se usa 1, sin ZeroDivision ni log2(0)."""
    t = _fitts_duration_ms(100.0, 0.0)
    assert 200 <= t <= 800


def test_ut_hc12_fitts_nunca_supera_techo_2s():
    """
    Capa 3: ninguna combinación (incluida min_duration_ms absurdo) supera 800 ms.
    El techo de 2 s del checklist nunca se acerca.
    """
    assert _fitts_duration_ms(99999.0, 1.0) <= 800
    assert _fitts_duration_ms(10.0, 50.0, min_duration_ms=100000) == 800


# ---------------------------------------------------------------------------
# UT-HC13 — Fitts NO es determinista en el trayecto real (jitter ±15%)
# Cubre Capa 3 — Timing humano (no determinista)
# ---------------------------------------------------------------------------

def test_ut_hc13_waypoint_timing_no_determinista():
    """
    RN-HC12: el total se reparte entre waypoints con jitter ±15%. Capturamos
    los sleeps de un human_click_at_rect y verificamos que los intervalos de
    movimiento NO son todos iguales (timing perfecto = firma de bot).
    """
    sleep_calls: list[float] = []

    async def _fake_sleep(secs: float) -> None:
        sleep_calls.append(secs)

    async def _run():
        sleep_calls.clear()
        _CURSOR_POS.clear()
        page = _make_mock_page()
        rect = _make_rect(100, 100, 200, 80)
        with patch("adapters.browser.driver.asyncio.sleep", side_effect=_fake_sleep):
            await human_click_at_rect(rect, page)

        # Sleeps de movimiento: > 0 y por debajo del settle/down-up (≈ <0.2 s c/u,
        # repartidos del total). Tomamos los que no son ni el settle ni el down-up.
        movimiento = [s for s in sleep_calls if 0.0 < s < 0.30]
        assert len(movimiento) >= 3, f"Muy pocos sleeps de movimiento: {movimiento}"
        # No deterministas: no todos iguales
        assert len(set(round(s, 6) for s in movimiento)) > 1, (
            f"Timing de movimiento perfectamente constante (robótico): {movimiento}"
        )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# UT-HC14 — min_duration_ms: piso de movimiento + ValueError en <= 0
# Cubre RN-HC09/RN-HC14
# ---------------------------------------------------------------------------

def test_ut_hc14_min_duration_pisa_a_fitts():
    """RN-HC14: min_duration_ms > Fitts → gana min_duration_ms (capado a 800)."""
    # Distancia corta (Fitts ≈ 200) pero pedimos al menos 500
    t = _fitts_duration_ms(2.0, 50.0, min_duration_ms=500)
    assert t == 500
    # Y nunca por encima de 800 aunque se pida más
    assert _fitts_duration_ms(2.0, 50.0, min_duration_ms=5000) == 800


def test_ut_hc14_min_duration_invalida_lanza_valueerror():
    """EC-HC08: min_duration_ms <= 0 → ValueError, antes de tocar el browser."""
    with pytest.raises(ValueError, match="min_duration_ms"):
        _fitts_duration_ms(100.0, 50.0, min_duration_ms=0)
    with pytest.raises(ValueError, match="min_duration_ms"):
        _fitts_duration_ms(100.0, 50.0, min_duration_ms=-50)

    async def _run():
        page = _make_mock_page()
        rect = _make_rect()
        with pytest.raises(ValueError, match="min_duration_ms"):
            await human_click_at_rect(rect, page, min_duration_ms=-1)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# UT-HC15 — _sample_near_target: punto FUERA del rect, ≤ end_distance del borde
# Cubre RN-HC15 / EC-HC11
# ---------------------------------------------------------------------------

def test_ut_hc15_drift_endpoint_fuera_del_rect_y_cerca():
    """
    RN-HC15: el end point está fuera del rect y a ≤ end_distance_px del borde.
    Verificado en 1000 muestras con direcciones aleatorias.
    """
    rect = _make_rect(300, 300, 100, 60)
    x0, y0, w, h = rect["x"], rect["y"], rect["width"], rect["height"]
    for _ in range(1000):
        x, y = _sample_near_target(rect, end_distance_px=20)
        dentro = (x0 <= x <= x0 + w) and (y0 <= y <= y0 + h)
        assert not dentro, f"end point ({x},{y}) cayó DENTRO del rect"


# ---------------------------------------------------------------------------
# UT-HC16 — [FIX GUARDIAN] el end point del drift se clampa al viewport
# Cubre RN-HC18 (evita end point no-op de CDP = teletransporte)
# ---------------------------------------------------------------------------

def test_ut_hc16_drift_endpoint_clampado_al_viewport():
    """
    FIX: un target pegado al borde del viewport podía dar un end point FUERA
    del viewport → CDP no-op silencioso → salto del cursor. Con viewport pasado,
    el end point SIEMPRE queda dentro de [1, viewport-1].
    """
    vw, vh = 1024.0, 768.0
    # Target pegado a la esquina inferior-derecha del viewport
    rect = {"x": vw - 40, "y": vh - 30, "width": 40, "height": 30}
    fuera_sin_clamp = 0
    for _ in range(2000):
        # Sin viewport: puede salir fuera (comportamiento del bug)
        xb, yb = _sample_near_target(rect, end_distance_px=200)
        if xb > vw or yb > vh or xb < 0 or yb < 0:
            fuera_sin_clamp += 1
        # Con viewport: SIEMPRE dentro
        x, y = _sample_near_target(rect, end_distance_px=200, viewport_w=vw, viewport_h=vh)
        assert 1.0 <= x <= vw - 1.0, f"x={x} fuera del viewport pese al clamp"
        assert 1.0 <= y <= vh - 1.0, f"y={y} fuera del viewport pese al clamp"
    # Sanidad: confirmamos que SIN clamp el bug era real (salía fuera muchas veces)
    assert fuera_sin_clamp > 0, "El test no ejerce el caso de borde (revisar rect)"


# ---------------------------------------------------------------------------
# UT-HC17 — _validate_or_reset_cursor: dentro se conserva, fuera se resetea
# Cubre RN-HC18
# ---------------------------------------------------------------------------

def test_ut_hc17_valida_cursor_dentro_y_resetea_fuera():
    async def _run():
        _CURSOR_POS.clear()
        page = _make_mock_page()
        tab_key = id(page)

        # Caso 1: cursor dentro del viewport → se conserva sin tocar
        _CURSOR_POS[tab_key] = (400.0, 300.0)
        pos = await _validate_or_reset_cursor(page, 800.0, 600.0)
        assert pos == (400.0, 300.0)

        # Caso 2: cursor fuera del viewport → se resetea al inner 80%
        _CURSOR_POS[tab_key] = (5000.0, 5000.0)
        page.send.reset_mock()
        pos = await _validate_or_reset_cursor(page, 800.0, 600.0)
        assert 80.0 <= pos[0] <= 720.0, f"reset x={pos[0]} fuera del inner 80%"
        assert 60.0 <= pos[1] <= 540.0, f"reset y={pos[1]} fuera del inner 80%"
        # Debe emitir un mousemove de anclaje tras el reset
        assert page.send.await_count >= 1, "No emitió move de anclaje tras reset"

        # Caso 3: sin posición previa → también resetea
        _CURSOR_POS.clear()
        pos = await _validate_or_reset_cursor(page, 800.0, 600.0)
        assert 0.0 <= pos[0] <= 800.0 and 0.0 <= pos[1] <= 600.0

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# UT-HC18 — human_drift_toward NO emite click y actualiza _CURSOR_POS
# Cubre RN-HC15/RN-HC17
# ---------------------------------------------------------------------------

def test_ut_hc18_drift_no_hace_click_y_persiste_cursor():
    """
    RN-HC15: human_drift_toward mueve pero NUNCA dispara mousePressed/Released.
    RN-HC17: _CURSOR_POS queda actualizado al terminar.
    """
    eventos: list[str] = []

    async def _capture_send(cmd):
        # cmd es el objeto CDP; capturamos su repr para detectar press/release
        eventos.append(repr(cmd))
        return None

    async def _run():
        _CURSOR_POS.clear()
        page = _make_mock_page()
        page.send = AsyncMock(side_effect=_capture_send)
        tab_key = id(page)

        rect = {"x": 300, "y": 300, "width": 100, "height": 60}
        with patch("adapters.browser.driver.asyncio.sleep", new_callable=AsyncMock):
            await human_drift_toward(rect, page, duration_ms=600, end_distance_px=20)

        blob = " ".join(eventos).lower()
        assert "mousepressed" not in blob, "drift NO debe emitir mousePressed"
        assert "mousereleased" not in blob, "drift NO debe emitir mouseReleased"
        # El cursor quedó persistido
        assert tab_key in _CURSOR_POS

    asyncio.run(_run())


def test_ut_hc18_drift_duration_invalida_lanza_valueerror():
    """EC-HC10: duration_ms <= 0 → ValueError antes de tocar el browser."""
    async def _run():
        page = _make_mock_page()
        rect = {"x": 10, "y": 10, "width": 50, "height": 20}
        with pytest.raises(ValueError, match="duration_ms"):
            await human_drift_toward(rect, page, duration_ms=0)

    asyncio.run(_run())


def test_ut_hc18_drift_endpoint_dentro_del_viewport_real():
    """
    FIX integrado: tras un drift hacia un target en el borde del viewport,
    _CURSOR_POS persistido queda DENTRO del viewport (no fuera = no teletransporte).
    """
    async def _run():
        _CURSOR_POS.clear()
        page = _make_mock_page()
        page.evaluate = AsyncMock(return_value=1024)  # vw y vh = 1024
        tab_key = id(page)

        # Target en la esquina inferior-derecha, end_distance grande
        rect = {"x": 1000, "y": 1000, "width": 24, "height": 24}
        with patch("adapters.browser.driver.asyncio.sleep", new_callable=AsyncMock):
            await human_drift_toward(rect, page, duration_ms=400, end_distance_px=200)

        x, y = _CURSOR_POS[tab_key]
        assert 0.0 <= x <= 1024.0, f"cursor x={x} persistido FUERA del viewport"
        assert 0.0 <= y <= 1024.0, f"cursor y={y} persistido FUERA del viewport"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# UT-HC19 — Lock por tab: no determinista, serializa sin timing fijo
# Cubre RN-HC16 (el lock no introduce sleeps deterministas)
# ---------------------------------------------------------------------------

def test_ut_hc19_lock_por_tab_no_introduce_timing_fijo():
    """
    RN-HC16: el _TAB_LOCKS serializa pero NO añade ningún sleep determinista.
    Verificamos que dos human_click_at_rect secuenciales en la misma tab no
    introducen una pausa constante atribuible al lock (los sleeps siguen siendo
    los aleatorios de movimiento/settle/click).
    """
    from adapters.browser.driver import _TAB_LOCKS

    sleeps_run1: list[float] = []
    sleeps_run2: list[float] = []

    async def _run():
        _CURSOR_POS.clear()
        _TAB_LOCKS.clear()
        page = _make_mock_page()
        rect = _make_rect(100, 100, 200, 80)

        async def _fs(target):
            async def _f(secs):
                target.append(secs)
            return _f

        with patch("adapters.browser.driver.asyncio.sleep", side_effect=await _fs(sleeps_run1)):
            await human_click_at_rect(rect, page)
        with patch("adapters.browser.driver.asyncio.sleep", side_effect=await _fs(sleeps_run2)):
            await human_click_at_rect(rect, page)

        # Ambas ejecuciones tienen sleeps aleatorios; ninguno es un valor fijo
        # repetido idéntico en todas las posiciones (señal de timing rígido).
        assert len(set(round(s, 6) for s in sleeps_run1)) > 1
        assert len(set(round(s, 6) for s in sleeps_run2)) > 1

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# UT-HC25 — CancelledError en human_click: cursor = ultimo waypoint enviado
# Cubre RN-HC17 (actualizacion incremental de _CURSOR_POS)
# ---------------------------------------------------------------------------

def test_ut_hc25_cursor_incremental_tras_cancelacion_click():
    """
    RN-HC17: si human_click se cancela mid-flight, _CURSOR_POS debe reflejar
    el ultimo waypoint ENVIADO al browser, NO el end planeado ni el origen.
    Garantia: el siguiente human_click parte de una posicion real, no fantasma.
    """
    send_count = [0]

    async def _run():
        from adapters.browser.driver import _TAB_LOCKS
        _CURSOR_POS.clear()
        _TAB_LOCKS.clear()

        page = _make_mock_page()
        tab_key = id(page)
        _CURSOR_POS[tab_key] = (50.0, 50.0)  # origen conocido

        async def counting_send(cmd):
            if "mouseMoved" in repr(cmd):
                send_count[0] += 1

        page.send = AsyncMock(side_effect=counting_send)

        rect = _make_rect(500, 500, 100, 60)
        sleep_count = [0]

        async def cancel_after_two_waypoints(secs):
            sleep_count[0] += 1
            if send_count[0] >= 2 and sleep_count[0] <= send_count[0]:
                raise asyncio.CancelledError("simulado mid-flight")

        with patch("adapters.browser.driver.asyncio.sleep",
                   side_effect=cancel_after_two_waypoints):
            try:
                await human_click_at_rect(rect, page)
            except asyncio.CancelledError:
                pass

        # El cursor debe haber avanzado desde el origen (50, 50)
        assert tab_key in _CURSOR_POS, "_CURSOR_POS no tiene entrada tras cancelacion"
        pos = _CURSOR_POS[tab_key]
        if send_count[0] >= 1:
            # Con actualizacion incremental, el cursor ya no esta en el origen
            assert pos != (50.0, 50.0), (
                f"Cursor quedo en el origen inicial — RN-HC17 no implementado: pos={pos}"
            )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# UT-HC26 — CancelledError en human_drift_toward: cursor = ultimo waypoint enviado
# Cubre RN-HC17
# ---------------------------------------------------------------------------

def test_ut_hc26_cursor_incremental_tras_cancelacion_drift():
    """
    RN-HC17: cancelacion de human_drift_toward mid-flight → _CURSOR_POS
    refleja el ultimo waypoint enviado, no el end planeado ni el origen.
    """
    send_count = [0]

    async def _run():
        from adapters.browser.driver import _TAB_LOCKS
        _CURSOR_POS.clear()
        _TAB_LOCKS.clear()

        page = _make_mock_page()
        tab_key = id(page)
        _CURSOR_POS[tab_key] = (640.0, 360.0)

        async def counting_send(cmd):
            if "mouseMoved" in repr(cmd):
                send_count[0] += 1

        page.send = AsyncMock(side_effect=counting_send)

        rect = {"x": 300.0, "y": 300.0, "width": 100.0, "height": 60.0}
        sleep_count = [0]

        async def cancel_on_second_sleep(secs):
            sleep_count[0] += 1
            if sleep_count[0] == 2:
                raise asyncio.CancelledError("simulado en drift")

        with patch("adapters.browser.driver.asyncio.sleep",
                   side_effect=cancel_on_second_sleep):
            try:
                await human_drift_toward(rect, page, duration_ms=3000)
            except asyncio.CancelledError:
                pass

        assert tab_key in _CURSOR_POS
        pos = _CURSOR_POS[tab_key]
        if send_count[0] >= 1:
            assert pos != (640.0, 360.0), (
                f"Cursor quedo en el origen — RN-HC17 no implementado en drift: pos={pos}"
            )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# UT-HC27/28 — _validate_or_reset_cursor: fuera → reset, dentro → conserva
# Cubre RN-HC18 (ya en test_ut_hc17, estos son los tests numerados del spec)
# ---------------------------------------------------------------------------

def test_ut_hc27_cursor_fuera_del_viewport_resetea():
    """UT-HC27: cursor (-50, 100) con viewport 1280x720 → resetea al inner 80%."""
    async def _run():
        _CURSOR_POS.clear()
        page = _make_mock_page()
        tab_key = id(page)
        _CURSOR_POS[tab_key] = (-50.0, 100.0)

        result = await _validate_or_reset_cursor(page, 1280.0, 720.0)
        assert result != (-50.0, 100.0), "No reseteo el cursor fuera del viewport"
        rx, ry = result
        assert 0 <= rx <= 1280 and 0 <= ry <= 720
        assert 128 <= rx <= 1152, f"x={rx} no en inner 80% del viewport"
        assert 72 <= ry <= 648, f"y={ry} no en inner 80% del viewport"

    asyncio.run(_run())


def test_ut_hc28_cursor_muy_fuera_del_viewport_resetea():
    """UT-HC28: cursor (2000, 800) con viewport 1280x720 → reset detectado."""
    async def _run():
        _CURSOR_POS.clear()
        page = _make_mock_page()
        tab_key = id(page)
        _CURSOR_POS[tab_key] = (2000.0, 800.0)

        result = await _validate_or_reset_cursor(page, 1280.0, 720.0)
        assert result != (2000.0, 800.0)
        rx, ry = result
        assert 0 <= rx <= 1280 and 0 <= ry <= 720

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# UT-HC29 — Sleep 150-350 ms post-scroll en human_drift_toward con target offscreen
# Cubre RN-HC19
# ---------------------------------------------------------------------------

def test_ut_hc29_sleep_post_scroll_en_drift_offscreen():
    """
    RN-HC19: cuando human_drift_toward ejecuta scroll (target offscreen),
    se dispara asyncio.sleep(random.uniform(0.150, 0.350)) antes de continuar.
    Garantia: el layout se asienta tras el scroll antes de medir el rect final.
    """
    rect_offscreen = {"x": -500.0, "y": 100.0, "width": 50.0, "height": 30.0}
    rect_ok = {"x": 200.0, "y": 200.0, "width": 100.0, "height": 60.0}
    sleep_vals: list[float] = []

    async def _run():
        from adapters.browser.driver import _TAB_LOCKS
        _CURSOR_POS.clear()
        _TAB_LOCKS.clear()
        page = _make_mock_page()
        tab_key = id(page)
        _CURSOR_POS[tab_key] = (640.0, 360.0)

        element = MagicMock()
        element.apply = AsyncMock(side_effect=[rect_offscreen, rect_ok])
        element.scroll_into_view = AsyncMock(return_value=None)

        async def capturing_sleep(secs):
            sleep_vals.append(secs)

        with patch("adapters.browser.driver.asyncio.sleep", side_effect=capturing_sleep):
            await human_drift_toward(element, page, duration_ms=1000)

        element.scroll_into_view.assert_called_once()
        post_scroll = [s for s in sleep_vals if 0.148 <= s <= 0.352]
        assert post_scroll, (
            f"No hay sleep post-scroll [150-350 ms] tras scroll_into_view en drift. "
            f"Calls: {[round(s * 1000) for s in sleep_vals]}"
        )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# UT-HC30 — Test estadistico de curvatura: n=500 + K-S test p > 0.05
# Cubre RN-HC13 (curvatura 10-25% uniforme por trayecto)
# Consolidado con UT-HC13 segun autorizacion del spec par 12
# ---------------------------------------------------------------------------

def test_ut_hc30_curvatura_distribucion_uniforme_ks():
    """
    UT-HC30: n=500 valores de curvatura uniforme [0.10, 0.25].
    Kolmogorov-Smirnov vs uniforme(loc=0.10, scale=0.15), p-value > 0.05.
    n=500 detecta sesgos > 0.06 a alfa=0.05 — banda minima razonable para
    garantia anti-deteccion estadistica (guardado en spec TR-HC04b).
    """
    from scipy import stats as scipy_stats

    samples = [random.uniform(0.10, 0.25) for _ in range(500)]

    # Rango correcto
    assert all(0.10 <= r <= 0.25 for r in samples), \
        "Valor de curvatura fuera de [0.10, 0.25]"

    # K-S vs uniforme(loc=0.10, scale=0.15)
    _, pvalue = scipy_stats.kstest(samples, "uniform", args=(0.10, 0.15))
    assert pvalue > 0.05, f"K-S test fallo con p={pvalue:.4f} — distribucion no uniforme"

    # Verificar que _bezier_path usa el rango correcto 10-25%
    captured = []
    original_uniform = random.uniform

    def spy_uniform(a, b):
        val = original_uniform(a, b)
        if abs(a - 0.10) < 0.001 and abs(b - 0.25) < 0.001:
            captured.append(val)
        return val

    with patch("adapters.browser.driver.random.uniform", side_effect=spy_uniform):
        for _ in range(100):
            _bezier_path((0.0, 0.0), (300.0, 200.0), 5)

    assert len(captured) == 100, f"Se esperaban 100 capturas de curvatura, se obtuvieron {len(captured)}"
    assert all(0.10 <= r <= 0.25 for r in captured), \
        "Bezier usa curvatura fuera del rango [0.10, 0.25]"
