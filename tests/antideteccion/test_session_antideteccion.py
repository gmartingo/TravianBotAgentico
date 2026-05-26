# Cubre Capa 1 — Config Chrome | Capa 2 — Selectores | Capa 3 — Timing humano | Capa 5 — Perfil/persistencia
"""
Tests anti-deteccion de la feature "login-sesion API".

La feature cablea el login REAL en Travian mediante 3 endpoints HTTP y un
SessionRegistry (adapters/browser/session_registry.py) que mantiene los browsers
activos por world_id. Todas las capas de anti-deteccion (escritura humana, perfil
Chrome, UA por entorno, sin headless, no_sandbox, _kill_orphan_chrome) viven en
adapters/browser/login.py y adapters/browser/driver.py — ficheros que esta feature
NO debe tocar (spec login-sesion-api.md, §11 + Nota anti-deteccion).

Estos tests fijan las invariantes para que un cambio futuro no las erosione en
silencio:

  - Capa 1/3/5: login.py y driver.py permanecen byte-a-byte iguales a la version
    commiteada en HEAD (las capas viven ahi; tocarlas requiere pasar de nuevo por
    el guardian). Se compara el working tree contra el blob de git.
  - Capa 3: SessionRegistry NO importa time / asyncio.sleep ni introduce delays
    propios. El timing humano es exclusivo de login.py.
  - Capa 4: logout() y login() solo cierran el browser via browser.stop(); nunca
    navegan URLs (browser.get / page.get / *.navigate) — cerrar Chrome local no
    debe disparar una peticion de logout a Travian (seria rastreable).
  - Capa 2: ningun fichero nuevo de la feature usa seleccion por texto visible.
  - No-leak: el response de sesion expone solo {active, world_id, account_id};
    nunca world.server, perfil Chrome ni credenciales. LOGIN_FAILED -> 401 sin
    distinguir la causa (anti-enumeracion).

Ninguno abre Chrome real: son estaticos (git/ast/regex) o usan mocks asincronos.
"""
import ast
import asyncio
import pathlib
import re
import subprocess
import unittest.mock as mock

import pytest

# tests/antideteccion/<este>.py -> parents[2] = raiz del repo (portable).
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
LOGIN_PATH = REPO_ROOT / "adapters" / "browser" / "login.py"
DRIVER_PATH = REPO_ROOT / "adapters" / "browser" / "driver.py"
REGISTRY_PATH = REPO_ROOT / "adapters" / "browser" / "session_registry.py"
ACCOUNTS_ROUTE_PATH = REPO_ROOT / "adapters" / "api" / "routes" / "accounts.py"
LOGIN_USE_CASE_PATH = REPO_ROOT / "core" / "use_cases" / "login_use_case.py"


# ---------------------------------------------------------------------------
# Capa 1/3/5 — login.py y driver.py INTACTOS respecto a HEAD
# Las capas anti-deteccion viven ahi. El spec exige NO tocarlos en esta feature.
# ---------------------------------------------------------------------------

def _git_blob_at_head(rel_path: str) -> bytes | None:
    """Contenido del fichero tal como esta commiteado en HEAD, o None si no se
    pudo leer (p.ej. fuera de un repo git)."""
    try:
        return subprocess.check_output(
            ["git", "show", f"HEAD:{rel_path}"],
            cwd=REPO_ROOT,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return None


@pytest.mark.parametrize(
    "rel_path",
    ["adapters/browser/login.py", "adapters/browser/driver.py"],
)
def test_login_y_driver_no_modificados_respecto_a_head(rel_path):
    """
    Cubre Capa 1/3/5 — las capas anti-deteccion centrales viven en login.py y
    driver.py. La feature login-sesion NO debe tocarlas. Comparamos el working
    tree contra el blob commiteado en HEAD: si alguien las edita junto con la
    feature, este test lo detecta antes del commit.
    """
    head_bytes = _git_blob_at_head(rel_path)
    if head_bytes is None:
        pytest.skip("No se pudo leer el blob de HEAD (¿entorno sin git?).")

    disk_bytes = (REPO_ROOT / rel_path).read_bytes()
    assert disk_bytes == head_bytes, (
        f"BLOQUEANTE Capa 1/3/5: {rel_path} difiere de la version en HEAD. "
        "Las capas anti-deteccion (escritura humana, perfil, UA, sin headless, "
        "no_sandbox) viven aqui. Modificarlas exige pasar de nuevo por el guardian."
    )


# ---------------------------------------------------------------------------
# Capa 3 — SessionRegistry NO introduce timing propio
# ---------------------------------------------------------------------------

def test_session_registry_no_importa_time_ni_sleep():
    """
    Cubre Capa 3 — Timing humano.
    SessionRegistry orquesta browsers; el timing humano debe vivir SOLO en
    login.py. El registry no puede importar time / asyncio para dormir, ni
    contener sleeps: cualquier delay propio competiria o se desincronizaria con
    los delays humanos de login.py.
    """
    tree = ast.parse(REGISTRY_PATH.read_text(encoding="utf-8"))

    imports_prohibidos = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in ("time",) or alias.name.split(".")[0] == "time":
                    imports_prohibidos.append(f"import {alias.name}")
        if isinstance(node, ast.ImportFrom) and node.module == "time":
            imports_prohibidos.append(f"from time import ...")

    assert not imports_prohibidos, (
        "BLOQUEANTE Capa 3: session_registry.py importa 'time'. El timing humano "
        f"debe vivir solo en login.py. Imports: {imports_prohibidos}"
    )


def test_session_registry_no_tiene_sleeps():
    """
    Cubre Capa 3 — Timing humano.
    Ni time.sleep ni asyncio.sleep (con cualquier valor) en el registry: no debe
    introducir pausas; el ritmo humano lo marca login.py.
    Excepcion declarada con comentario '# anti-deteccion-ok: <razon>' encima.
    """
    lines = REGISTRY_PATH.read_text(encoding="utf-8").splitlines()
    patron_sleep = re.compile(r'\b(time|asyncio)\.sleep\s*\(')

    violaciones = []
    for lineno, line in enumerate(lines, start=1):
        if patron_sleep.search(line):
            prev = lines[lineno - 2] if lineno >= 2 else ""
            if "# anti-deteccion-ok:" not in prev:
                violaciones.append(f"session_registry.py:{lineno} — {line.strip()}")

    assert not violaciones, (
        "BLOQUEANTE Capa 3: session_registry.py contiene sleep(). "
        "El timing humano vive en login.py.\n" + "\n".join(violaciones)
    )


# ---------------------------------------------------------------------------
# Capa 4 — logout/login NO navegan URLs: solo browser.stop()
# Cerrar Chrome local no debe disparar peticion de logout a Travian (rastreable).
# ---------------------------------------------------------------------------

def test_session_registry_no_navega_urls():
    """
    Cubre Capa 4 — Comportamiento DOM.
    El registry no debe llamar a browser.get / page.get / *.navigate / *.open:
    logout() cierra el Chrome local (browser.stop) sin pedir la URL de logout de
    Travian. Una navegacion de cierre dejaria una peticion identificable en el
    servidor en cada cierre de sesion del bot.
    """
    tree = ast.parse(REGISTRY_PATH.read_text(encoding="utf-8"))

    metodos_navegacion = {"get", "navigate", "open", "reload", "goto"}
    violaciones = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            # dict.get() es legitimo: solo marcamos navegacion sobre browser/page/tab.
            if attr in metodos_navegacion and attr != "get":
                violaciones.append(f"session_registry.py — .{attr}(...)")
            if attr == "get":
                # Permitir self._sessions.get(...) (acceso a dict), prohibir
                # browser.get / page.get / tab.get (navegacion).
                recv = node.func.value
                recv_name = getattr(recv, "id", None) or getattr(
                    getattr(recv, "attr", None), "__str__", lambda: None
                )()
                # Solo es navegacion si el receptor se llama browser/page/tab.
                recv_id = recv.id if isinstance(recv, ast.Name) else getattr(recv, "attr", "")
                if recv_id in ("browser", "page", "tab", "old_browser"):
                    violaciones.append(f"session_registry.py — {recv_id}.get(...)")

    assert not violaciones, (
        "BLOQUEANTE Capa 4: session_registry.py navega una URL. logout()/login() "
        "solo deben usar browser.stop(); NO navegar la URL de logout de Travian.\n"
        + "\n".join(violaciones)
    )


def test_logout_solo_llama_browser_stop_y_no_mata_todos_los_chrome():
    """
    Cubre Capa 4 — gestion de procesos / aislamiento.
    logout(world_id) debe cerrar SOLO el browser de ese world_id (browser.stop)
    y nunca tocar otros browsers ni invocar _kill_orphan_chrome (que mata Chrome
    por perfil de forma global). Mock asincrono — sin Chrome real.
    """
    from adapters.browser.session_registry import SessionRegistry

    class _FakeBrowser:
        def __init__(self, name):
            self.name = name
            self.stopped = False

        async def stop(self):
            self.stopped = True

    class _World:
        def __init__(self, wid, server):
            self.id = wid
            self.server = server

    reg = SessionRegistry()
    b1 = _FakeBrowser("w1")
    b2 = _FakeBrowser("w2")
    reg._sessions[1] = (b1, _World(1, "https://a.travian.com/"))
    reg._sessions[2] = (b2, _World(2, "https://b.travian.com/"))

    asyncio.run(reg.logout(1))

    assert b1.stopped is True, "logout(1) debio cerrar el browser del world 1."
    assert b2.stopped is False, (
        "BLOQUEANTE Capa 4: logout(1) cerro tambien el browser del world 2. "
        "Cada logout debe afectar SOLO a su world_id."
    )
    assert 1 not in reg._sessions and 2 in reg._sessions, (
        "logout(1) debe eliminar solo la entrada del world 1 del registry."
    )


def test_logout_es_idempotente_sin_sesion():
    """
    Cubre Capa 4 — robustez. logout() sobre un world sin sesion no debe lanzar ni
    intentar cerrar nada (no deja procesos huerfanos ni errores).
    """
    from adapters.browser.session_registry import SessionRegistry

    reg = SessionRegistry()
    # No debe lanzar.
    asyncio.run(reg.logout(999))
    assert reg.is_active(999) is False


def test_relogin_cierra_solo_el_browser_previo_del_mismo_world():
    """
    Cubre Capa 4 — aislamiento de procesos en relogin (RN-06).
    Un login() sobre un world con sesion previa debe cerrar SOLO ese browser
    previo (browser.stop) antes de abrir el nuevo, sin tocar otros worlds.
    """
    from adapters.browser import session_registry as mod
    from adapters.browser.session_registry import SessionRegistry

    class _FakeBrowser:
        def __init__(self, name):
            self.name = name
            self.stopped = False

        async def stop(self):
            self.stopped = True

    class _World:
        def __init__(self, wid, server):
            self.id = wid
            self.server = server

    reg = SessionRegistry()
    prev_w1 = _FakeBrowser("prev_w1")
    other_w2 = _FakeBrowser("other_w2")
    reg._sessions[1] = (prev_w1, _World(1, "https://a/"))
    reg._sessions[2] = (other_w2, _World(2, "https://b/"))

    nuevo_browser = _FakeBrowser("nuevo_w1")

    async def fake_login(account, world):
        # Simula login.py: devuelve (True, browser) sin tocar Chrome real.
        return True, nuevo_browser

    class _Account:
        worlds = []

    with mock.patch.object(mod.login_module, "login", side_effect=fake_login):
        ok = asyncio.run(reg.login(_Account(), _World(1, "https://a/")))

    assert ok is True
    assert prev_w1.stopped is True, "El browser previo del world 1 debio cerrarse."
    assert other_w2.stopped is False, (
        "BLOQUEANTE Capa 4: el relogin del world 1 cerro el browser del world 2."
    )
    assert reg.get_browser(1) is nuevo_browser, (
        "Tras el relogin, get_browser(1) debe devolver el browser nuevo."
    )


# ---------------------------------------------------------------------------
# Capa 2 — ningun fichero nuevo de la feature usa seleccion por texto visible
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "path",
    [REGISTRY_PATH, ACCOUNTS_ROUTE_PATH, LOGIN_USE_CASE_PATH],
)
def test_ficheros_feature_sin_selectores_por_texto(path):
    """
    Cubre Capa 2 — Selectores.
    Los ficheros tocados/creados por la feature no deben introducir seleccion por
    texto visible (Travian es multilenguaje). Aqui no deberia haber selectores,
    pero el test bloquea que se cuelen en el futuro.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    patrones_prohibidos = [
        ":has-text(",
        ":contains(",
        "contains(text()",
        "text()=",
        "find_element_by_link_text",
        "find_element_by_partial_link_text",
        "By.LINK_TEXT",
        "By.PARTIAL_LINK_TEXT",
        "link_text=",
        "partial_link_text=",
    ]
    patron_text_compare = re.compile(
        r'\.text\s*(==|!=|\.startswith|\.endswith)'
    )

    violaciones = []
    for lineno, line in enumerate(lines, start=1):
        # Ignorar comentarios/docstrings que mencionan los patrones como prosa
        # (este fichero los lista en su docstring, p.ej.).
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for patron in patrones_prohibidos:
            if patron in line:
                violaciones.append(f"{path.name}:{lineno} — '{patron}' — {stripped}")
        if patron_text_compare.search(line):
            violaciones.append(
                f"{path.name}:{lineno} — comparacion por texto — {stripped}"
            )

    assert not violaciones, (
        "BLOQUEANTE Capa 2: seleccion/filtrado por texto visible en un fichero de "
        "la feature. Usar selectores estructurales.\n" + "\n".join(violaciones)
    )


# ---------------------------------------------------------------------------
# No-leak — el response de sesion no expone server, perfil ni credenciales
# ---------------------------------------------------------------------------

def test_session_status_response_solo_expone_campos_seguros():
    """
    Cubre no-leak (anti-deteccion / privacidad de sesion).
    SessionStatusResponse debe contener EXACTAMENTE {active, world_id, account_id}.
    Exponer world.server, la ruta del perfil Chrome o credenciales daria pistas
    sobre la infraestructura del bot.
    """
    import importlib

    accounts_mod = importlib.import_module("adapters.api.routes.accounts")
    schema = accounts_mod.SessionStatusResponse
    campos = set(schema.model_fields.keys())

    assert campos == {"active", "world_id", "account_id"}, (
        f"BLOQUEANTE no-leak: SessionStatusResponse expone {campos}. "
        "Debe ser exactamente {active, world_id, account_id} — sin server, "
        "perfil Chrome ni credenciales."
    )


def test_session_registry_no_loguea_credenciales():
    """
    Cubre no-leak — el registry no debe pasar password/username/server a logger.
    Verificacion estatica: ninguna llamada a logger.* recibe como argumento un
    acceso a .password / .username / .server.
    """
    tree = ast.parse(REGISTRY_PATH.read_text(encoding="utf-8"))

    atributos_sensibles = {"password", "username", "server"}
    violaciones = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "logger"
        ):
            for arg in ast.walk(node):
                if isinstance(arg, ast.Attribute) and arg.attr in atributos_sensibles:
                    violaciones.append(
                        f"session_registry.py — logger.{node.func.attr}(... .{arg.attr} ...)"
                    )

    assert not violaciones, (
        "BLOQUEANTE no-leak: el registry loguea un atributo sensible "
        "(password/username/server).\n" + "\n".join(violaciones)
    )


def test_login_failed_mapea_a_401_sin_distinguir_causa():
    """
    Cubre anti-enumeracion (RN-13).
    LOGIN_FAILED debe mapear a 401 y su mensaje NO debe distinguir entre
    'credenciales incorrectas' y 'error de red' (eso permitiria enumerar cuentas
    validas). Verificamos el mapeo HTTP y que el mensaje base es ambiguo.
    """
    import importlib
    import json

    error_codes = importlib.import_module("adapters.api.error_codes")
    assert error_codes.ERROR_HTTP_MAP.get("LOGIN_FAILED") == 401, (
        "BLOQUEANTE: LOGIN_FAILED debe mapear a 401."
    )

    catalog = json.loads(
        (REPO_ROOT / "core" / "i18n" / "catalog" / "base" / "messages.json").read_text(
            encoding="utf-8"
        )
    )
    msg_es = catalog["LOGIN_FAILED"]["es"].lower()
    # El mensaje debe ofrecer AMBAS causas como posibles (o/y), no afirmar una.
    assert "o el estado del servidor" in msg_es or "o el servidor" in msg_es, (
        "BLOQUEANTE anti-enumeracion: el mensaje LOGIN_FAILED afirma una causa "
        "concreta. Debe ser ambiguo (credenciales O estado del servidor)."
    )
