# Cubre Capa 1 — Configuracion de Chrome / zendriver
"""
Tests estaticos de configuracion de zendriver.
No abren Chrome real. Verifican que el factory de configuracion produce
un objeto Config con todas las capas de anti-deteccion obligatorias.
"""
import os
import ast
import pathlib
import importlib
import unittest.mock as mock

import pytest

# Raiz del repositorio, resuelta de forma relativa a ESTE archivo:
#   tests/antideteccion/test_config_zendriver.py  ->  parents[2] = raiz del repo.
# Antes estaba hardcodeada como "c:/Dev/Travian con Agentes/...", lo que hacia
# fallar los tests al ejecutarlos en otro entorno (macOS, Raspberry Pi, u otra
# ruta en Windows). Ahora es portable en cualquier maquina.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Test 1: El objeto Config resultante contiene los flags obligatorios
# ---------------------------------------------------------------------------

def test_config_zendriver_tiene_flag_antiautomatizacion():
    """
    Cubre Capa 1 — create_browser() debe producir un Config con
    --disable-blink-features=AutomationControlled en browser_args.
    Usa mock de zd.start para no abrir Chrome.
    """
    # Si driver.py aun no tiene create_browser (version pre-spec), el test
    # falla con un mensaje explicativo.
    import adapters.browser.driver as driver_module

    if not hasattr(driver_module, "create_browser"):
        pytest.fail(
            "BLOQUEANTE: adapters/browser/driver.py no tiene la funcion "
            "create_browser(). El spec requiere esta funcion standalone. "
            "Implementar antes de hacer commit."
        )

    captured_config = {}

    async def fake_start(config):
        captured_config["config"] = config
        return mock.MagicMock()

    with mock.patch("zendriver.start", side_effect=fake_start):
        import asyncio
        asyncio.run(driver_module.create_browser("profiles/test_account"))

    config = captured_config.get("config")
    assert config is not None, "create_browser() no llamo a zd.start(config)"

    browser_args = getattr(config, "browser_args", []) or []
    args_str = " ".join(browser_args)

    assert "--disable-blink-features=AutomationControlled" in args_str, (
        "BLOQUEANTE Capa 1: falta --disable-blink-features=AutomationControlled "
        f"en browser_args. Args actuales: {browser_args}"
    )

    assert getattr(config, "no_sandbox", False) is True, (
        "BLOQUEANTE Capa 1: no_sandbox debe ser True (requerido en VirtualBox)"
    )

    assert getattr(config, "disable_webrtc", False) is True, (
        "BLOQUEANTE Capa 6: disable_webrtc debe ser True"
    )

    assert getattr(config, "disable_webgl", False) is True, (
        "BLOQUEANTE Capa 6: disable_webgl debe ser True"
    )

    user_data_dir = getattr(config, "user_data_dir", None)
    assert user_data_dir is not None, (
        "BLOQUEANTE Capa 5: user_data_dir no puede ser None"
    )
    assert os.path.isabs(user_data_dir), (
        f"BLOQUEANTE Capa 5: user_data_dir debe ser ruta absoluta. "
        f"Valor actual: '{user_data_dir}'"
    )


# ---------------------------------------------------------------------------
# Test 2: Prohibicion de headless
# ---------------------------------------------------------------------------

def test_no_existen_flags_headless_en_driver():
    """
    Cubre Capa 1 — Prohibicion de headless=True o --headless.
    Parsea adapters/browser/driver.py con ast y busca patrones prohibidos.
    No abre Chrome.
    """
    driver_path = REPO_ROOT / "adapters" / "browser" / "driver.py"
    source = driver_path.read_text(encoding="utf-8")

    patrones_prohibidos = [
        "headless=True",
        "--headless",
        "--headless=new",
        "headless=1",
    ]

    for patron in patrones_prohibidos:
        assert patron not in source, (
            f"BLOQUEANTE Capa 1: patron prohibido encontrado en driver.py: '{patron}'. "
            "El bot NUNCA debe correr en modo headless."
        )


# ---------------------------------------------------------------------------
# Test 3: Selectores prohibidos en adapters/browser/
# ---------------------------------------------------------------------------

def test_no_existen_selectores_por_texto_en_adapters_browser():
    """
    Cubre Capa 2 — Selectores prohibidos.
    Recorre todos los .py de adapters/browser/ y verifica que no hay
    selectores por texto visible.
    """
    browser_dir = REPO_ROOT / "adapters" / "browser"
    py_files = list(browser_dir.rglob("*.py"))

    assert len(py_files) > 0, (
        "No se encontraron archivos .py en adapters/browser/. "
        "Verificar que el directorio existe."
    )

    patrones_prohibidos = [
        "By.LINK_TEXT",
        "By.PARTIAL_LINK_TEXT",
        "link_text=",
        "partial_link_text=",
        ":has-text(",
        ":contains(",
        "contains(text()",
        'text()="',
        "text()='",
    ]

    violaciones = []
    for py_file in py_files:
        source = py_file.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(source.splitlines(), start=1):
            for patron in patrones_prohibidos:
                if patron in line:
                    violaciones.append(
                        f"{py_file.name}:{lineno} — patron '{patron}' — linea: {line.strip()}"
                    )

    assert not violaciones, (
        "BLOQUEANTE Capa 2: selectores por texto visible encontrados:\n"
        + "\n".join(violaciones)
    )


# ---------------------------------------------------------------------------
# Test 4: Timing — sin time.sleep con valor constante
# ---------------------------------------------------------------------------

def test_no_hay_time_sleep_con_valor_constante_en_adapters_browser():
    """
    Cubre Capa 3 — Timing humano.
    Verifica que time.sleep() en adapters/browser/ y core/ no recibe
    literales numericos directos (timing deterministico).
    Excepcion: lineas con comentario '# anti-deteccion-ok: <razon>'
    """
    import re

    directorios = [
        REPO_ROOT / "adapters" / "browser",
        REPO_ROOT / "core",
    ]

    # Patron: time.sleep( seguido de un literal numerico
    patron_sleep_fijo = re.compile(r'time\.sleep\s*\(\s*\d+\.?\d*\s*\)')

    violaciones = []
    for directorio in directorios:
        if not directorio.exists():
            continue
        for py_file in directorio.rglob("*.py"):
            lines = py_file.read_text(encoding="utf-8", errors="replace").splitlines()
            for lineno, line in enumerate(lines, start=1):
                if patron_sleep_fijo.search(line):
                    # Verificar si la linea anterior tiene la excepcion declarada
                    prev_line = lines[lineno - 2] if lineno >= 2 else ""
                    if "# anti-deteccion-ok:" not in prev_line:
                        violaciones.append(
                            f"{py_file.name}:{lineno} — time.sleep con valor fijo: {line.strip()}"
                        )

    assert not violaciones, (
        "BLOQUEANTE Capa 3: time.sleep() con valor constante encontrado. "
        "Usar random.uniform() o el helper human_delay(). "
        "Si es intencional, anadir comentario '# anti-deteccion-ok: <razon>' en la linea anterior.\n"
        + "\n".join(violaciones)
    )


# ---------------------------------------------------------------------------
# Test 5: Helper human_delay — distribucion estadistica correcta
# ---------------------------------------------------------------------------

def test_helper_human_delay_distribucion_estadistica():
    """
    Cubre Capa 3 — Timing humano.
    Invoca human_delay() 200 veces y verifica que la media cae en 500-900 ms
    y la varianza no es cero.
    """
    import adapters.browser.driver as driver_module

    if not hasattr(driver_module, "human_delay"):
        pytest.fail(
            "BLOQUEANTE: adapters/browser/driver.py no tiene la funcion "
            "human_delay(). El spec requiere esta funcion standalone. "
            "Implementar antes de hacer commit."
        )

    import asyncio
    import time

    tiempos = []

    async def medir():
        for _ in range(200):
            inicio = time.monotonic()
            await driver_module.human_delay()
            fin = time.monotonic()
            tiempos.append((fin - inicio) * 1000)  # en ms

    asyncio.run(medir())

    media = sum(tiempos) / len(tiempos)
    varianza = sum((t - media) ** 2 for t in tiempos) / len(tiempos)

    assert 500 <= media <= 900, (
        f"BLOQUEANTE Capa 3: la media de human_delay() es {media:.1f} ms, "
        f"fuera del rango 500-900 ms esperado."
    )

    assert varianza > 0, (
        "BLOQUEANTE Capa 3: varianza de human_delay() es cero — el timing es deterministico."
    )


# ---------------------------------------------------------------------------
# Test 6: Helper human_type — distribucion de timing por caracter
# ---------------------------------------------------------------------------

def test_helper_human_type_distribucion_por_caracter():
    """
    Cubre Capa 3 — Escritura humana.
    Verifica que human_type() introduce delays en rango 80-220 ms por caracter.
    Mockea el elemento para no necesitar browser real.
    """
    import adapters.browser.driver as driver_module
    import asyncio
    import time

    if not hasattr(driver_module, "human_type"):
        pytest.fail(
            "BLOQUEANTE: adapters/browser/driver.py no tiene la funcion "
            "human_type(). El spec requiere esta funcion standalone. "
            "Implementar antes de hacer commit."
        )

    tiempos_por_char = []
    chars_escritos = []

    class FakeElement:
        async def send_keys(self, char):
            chars_escritos.append(char)

    texto = "hola"
    fake_el = FakeElement()

    async def medir():
        # Medir 50 veces para tener muestra estadistica
        for _ in range(50):
            inicio = time.monotonic()
            await driver_module.human_type(fake_el, texto)
            fin = time.monotonic()
            tiempo_total_ms = (fin - inicio) * 1000
            tiempo_por_char = tiempo_total_ms / len(texto)
            tiempos_por_char.append(tiempo_por_char)

    asyncio.run(medir())

    media = sum(tiempos_por_char) / len(tiempos_por_char)

    # La media del tiempo por caracter debe estar en 80-220 ms
    # Damos margen del 20% para variabilidad del sistema
    assert 60 <= media <= 260, (
        f"BLOQUEANTE Capa 3: la media de tiempo por caracter en human_type() "
        f"es {media:.1f} ms, fuera del rango esperado 80-220 ms (margen +-20%)."
    )

    varianza = sum((t - media) ** 2 for t in tiempos_por_char) / len(tiempos_por_char)
    assert varianza > 0, (
        "BLOQUEANTE Capa 3: varianza de human_type() es cero — escritura deterministica."
    )


# ---------------------------------------------------------------------------
# Test 7: User-Agent — coherencia por plataforma y version no hardcodeada
# ---------------------------------------------------------------------------

def test_user_agent_coherente_por_plataforma_y_no_hardcodeado():
    """
    Cubre Capa 1 — User-Agent dinamico.
    Verifica que _get_user_agent() retorna UA coherente con la plataforma
    y que no contiene versiones hardcodeadas de Chrome.
    Mockea platform.system() y subprocess.run().
    """
    import adapters.browser.driver as driver_module

    if not hasattr(driver_module, "_get_user_agent"):
        pytest.fail("adapters/browser/driver.py no tiene _get_user_agent()")

    # Versiones de Chrome que NO deben aparecer hardcodeadas
    versiones_prohibidas = ["Chrome/124", "Chrome/120", "Chrome/110"]

    plataformas = {
        "Windows": "Windows",
        "Darwin": "Macintosh",
        "Linux": "Linux",
    }

    for sistema, fragmento_esperado in plataformas.items():
        with mock.patch("platform.system", return_value=sistema):
            # Si la funcion tiene _detect_chrome_path/_detect_chrome_major_version,
            # mockearlos para que no ejecuten subprocess
            with mock.patch.object(
                driver_module, "_detect_chrome_path",
                return_value="/fake/chrome", create=True
            ):
                with mock.patch.object(
                    driver_module, "_detect_chrome_major_version",
                    return_value=136, create=True
                ):
                    ua = driver_module._get_user_agent()

        assert ua, f"_get_user_agent() devolvio UA vacio para {sistema}"
        assert fragmento_esperado in ua, (
            f"UA para {sistema} no contiene '{fragmento_esperado}'. UA: '{ua}'"
        )
        for version_prohibida in versiones_prohibidas:
            assert version_prohibida not in ua, (
                f"BLOQUEANTE Capa 1: UA para {sistema} contiene version hardcodeada "
                f"'{version_prohibida}'. UA: '{ua}'"
            )


def test_user_agent_version_chrome_no_es_X_0_0_0():
    """
    Cubre Capa 1 — El UA no debe reportar Chrome/<major>.0.0.0
    ya que ese patron es un indicador conocido de automatizacion.
    ADVERTENCIA: este test falla con la implementacion del spec actual
    que construye chrome_ver = f'{major}.0.0.0'.
    """
    import adapters.browser.driver as driver_module

    if not hasattr(driver_module, "_get_user_agent"):
        pytest.skip("_get_user_agent no existe aun")

    import re

    # _get_user_agent() construye el UA con _detect_chrome_full_version(), que
    # devuelve la version COMPLETA de Chrome (4 segmentos). Mockeamos ESA funcion
    # (la real) con una version realista para que el test sea deterministico en
    # cualquier entorno. Antes se mockeaba _detect_chrome_major_version, que no
    # existe en la implementacion: el mock era un no-op y en macOS el UA caia al
    # fallback "136.0.0.0", haciendo fallar el test.
    with mock.patch("platform.system", return_value="Windows"):
        with mock.patch.object(
            driver_module, "_detect_chrome_path",
            return_value="/fake/chrome", create=True
        ):
            with mock.patch.object(
                driver_module, "_detect_chrome_full_version",
                return_value="136.0.7103.114", create=True
            ):
                ua = driver_module._get_user_agent()

    # Buscar patron Chrome/X.0.0.0 donde X es el major y los tres siguientes son ceros
    patron_ua_automatizacion = re.compile(r'Chrome/(\d+)\.0\.0\.0')
    match = patron_ua_automatizacion.search(ua)

    assert not match, (
        f"BLOQUEANTE Capa 1: El UA contiene el patron 'Chrome/{match.group(1)}.0.0.0' "
        f"que es un indicador conocido de automatizacion. "
        f"El spec debe usar la version completa de Chrome (ej: 136.0.7103.114), "
        f"no solo el numero mayor seguido de tres ceros. "
        f"UA actual: '{ua}'"
    )


# ---------------------------------------------------------------------------
# Test 8: Aislamiento de perfil — dos cuentas obtienen rutas distintas
# ---------------------------------------------------------------------------

def test_aislamiento_de_perfil_por_cuenta_y_mundo():
    """
    Cubre Capa 5 — Perfil y persistencia.
    Verifica que para dos (account_id, world_id) distintos se generan
    rutas de perfil distintas y absolutas.
    """
    import adapters.browser.driver as driver_module

    if not hasattr(driver_module, "create_browser"):
        pytest.skip("create_browser no existe aun — spec no implementado")

    import asyncio

    perfiles_capturados = []

    async def fake_start(config):
        perfiles_capturados.append(getattr(config, "user_data_dir", None))
        return mock.MagicMock()

    with mock.patch("zendriver.start", side_effect=fake_start):
        asyncio.run(driver_module.create_browser("profiles/account_1_world_1"))
        asyncio.run(driver_module.create_browser("profiles/account_1_world_2"))
        asyncio.run(driver_module.create_browser("profiles/account_2_world_1"))

    assert len(perfiles_capturados) == 3

    # Todos deben ser rutas absolutas
    for perfil in perfiles_capturados:
        assert perfil is not None
        assert os.path.isabs(perfil), (
            f"BLOQUEANTE Capa 5: perfil no es ruta absoluta: '{perfil}'"
        )

    # Todos deben ser distintos
    assert len(set(perfiles_capturados)) == 3, (
        f"BLOQUEANTE Capa 5: perfiles distintos produjeron la misma ruta. "
        f"Riesgo de contaminacion cruzada de cookies. "
        f"Perfiles: {perfiles_capturados}"
    )
