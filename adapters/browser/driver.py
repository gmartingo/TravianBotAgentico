"""
Adaptador de navegador basado en zendriver.
Implementa BrowserPort con todas las capas de anti-detección obligatorias.

Contiene también funciones standalone usadas por login.py:
  - create_browser()  — arranca Chrome con todas las capas anti-detección
  - human_delay()     — pausa aleatoria entre acciones (timing humano)
  - human_type()      — escritura carácter a carácter (anti-paste masivo)
  - _kill_orphan_chrome() — mata solo el Chrome del perfil indicado

Cuándo usar ZendriverAdapter vs funciones standalone:
  - ZendriverAdapter: operaciones genéricas futuras donde el caller no necesita
    el objeto browser raw (navegar, hacer click, etc.).
  - create_browser + funciones standalone: cuando el caller necesita retener
    el objeto zd.Browser vivo entre use cases (login, sesión larga).
"""
import asyncio
import math
import os
import platform
import random
import re
import subprocess
from typing import Optional

import zendriver as zd

from core.exceptions import BrowserError, ElementNotClickableError
from core.ports.browser_port import BrowserPort

# ---------------------------------------------------------------------------
# Rutas de Chrome por OS — orden de preferencia
# ---------------------------------------------------------------------------

_CHROME_PATHS = {
    "Darwin": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ],
    "Windows": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ],
    "Linux": [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ],
}


# ---------------------------------------------------------------------------
# Detección de Chrome
# ---------------------------------------------------------------------------

def _detect_chrome_path() -> str:
    """Devuelve la primera ruta válida de Chrome para el OS actual.
    Lanza BrowserError si no se encuentra ninguna."""
    system = platform.system()
    for path in _CHROME_PATHS.get(system, []):
        if os.path.exists(path):
            return path
    raise BrowserError(f"Chrome no encontrado en ninguna ruta conocida para {system}")


def _detect_chrome_full_version(chrome_path: str) -> str:
    """
    Lee la versión COMPLETA de Chrome (4 segmentos, ej: "136.0.7103.114").

    CRÍTICO — Windows: NUNCA llamar a chrome.exe --version.
    En Windows ese comando abre una ventana de Chrome real (o activa la instancia
    existente), causando que se lancen dos Chrome por ejecución del bot.

    Estrategia por OS:
      - Windows: PowerShell lee VersionInfo.FileVersion del binario (sin lanzar Chrome),
                 con fallback al registro HKCU\\Software\\Google\\Chrome\\BLBeacon.
      - macOS / Linux: chrome --version imprime en stdout sin abrir ventana.
    """
    system = platform.system()

    if system == "Windows":
        # Leer versión del binario vía PowerShell — no abre Chrome
        try:
            result = subprocess.run(
                [
                    "powershell", "-NoProfile", "-Command",
                    f"(Get-Item '{chrome_path}').VersionInfo.FileVersion",
                ],
                capture_output=True, text=True, timeout=5,
            )
            ver = result.stdout.strip()
            if re.match(r'\d+\.\d+\.\d+\.\d+', ver):
                return ver
        except Exception:
            pass
        # Fallback: registro de Windows
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Google\Chrome\BLBeacon",
            )
            ver_reg, _ = winreg.QueryValueEx(key, "version")
            if ver_reg and re.match(r'\d+\.\d+\.\d+\.\d+', str(ver_reg)):
                return str(ver_reg)
        except Exception:
            pass

    else:
        # macOS y Linux: --version escribe en stdout sin abrir ventana
        try:
            result = subprocess.run(
                [chrome_path, "--version"],
                capture_output=True, text=True, timeout=5,
            )
            match = re.search(r'(\d+\.\d+\.\d+\.\d+)', result.stdout)
            if match:
                return match.group(1)
        except Exception:
            pass

    return "136.0.0.0"  # Fallback solo si todos los mecanismos fallan


def _get_user_agent() -> str:
    """
    Construye un UA coherente con el OS real y la versión de Chrome instalada.
    Nunca hardcodea la versión de Chrome. Usa la versión completa de 4 segmentos.
    """
    system = platform.system()
    try:
        chrome_path = _detect_chrome_path()
        chrome_ver = _detect_chrome_full_version(chrome_path)
    except Exception:
        chrome_ver = "136.0.0.0"

    if system == "Windows":
        return (
            f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{chrome_ver} Safari/537.36"
        )
    if system == "Darwin":
        mac_ver = platform.mac_ver()[0].replace(".", "_") or "14_0_0"
        return (
            f"Mozilla/5.0 (Macintosh; Intel Mac OS X {mac_ver}) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{chrome_ver} Safari/537.36"
        )
    # Linux (incluyendo Raspberry Pi con Box64)
    return (
        f"Mozilla/5.0 (X11; Linux x86_64) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{chrome_ver} Safari/537.36"
    )


# ---------------------------------------------------------------------------
# Matar proceso Chrome huérfano del perfil indicado
# ---------------------------------------------------------------------------

def _kill_orphan_chrome(profile_dir: str) -> None:
    """
    Mata SOLO el proceso Chrome que tenga profile_dir como --user-data-dir.
    Silencioso — no lanza excepciones.

    IMPORTANTE: NO usar 'taskkill /F /IM chrome.exe' en Windows — mataría
    todos los Chrome del sistema, incluyendo sesiones activas de otras cuentas.
    Se filtra por --user-data-dir usando wmic para matar solo el proceso correcto.
    """
    abs_profile = os.path.abspath(profile_dir)
    try:
        if platform.system() == "Windows":
            # Buscar PIDs de Chrome que tengan este perfil en su CommandLine
            result = subprocess.run(
                [
                    "wmic", "process", "where",
                    f"CommandLine like '%{abs_profile}%'",
                    "get", "ProcessId", "/format:csv",
                ],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                parts = line.strip().split(",")
                if len(parts) >= 2 and parts[-1].isdigit():
                    pid = int(parts[-1])
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(pid)],
                        capture_output=True,
                    )
        else:
            # macOS y Linux: pgrep filtra por el argumento del proceso
            result = subprocess.run(
                ["pgrep", "-f", abs_profile],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                if line.strip().isdigit():
                    subprocess.run(
                        ["kill", "-9", line.strip()],
                        capture_output=True,
                    )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Funciones standalone para login y sesiones activas
# ---------------------------------------------------------------------------

async def create_browser(profile_dir: str) -> zd.Browser:
    """
    Crea y arranca un browser zendriver con todas las capas de anti-detección.
    En Linux configura DISPLAY y variables Box64 si es necesario.
    """
    if platform.system() == "Linux":
        os.environ.setdefault("DISPLAY", ":0")
        os.environ.setdefault("BOX64_LOG", "0")
        os.environ.setdefault("BOX64_DYNAREC_LOG", "0")

    chrome_path = _detect_chrome_path()

    config = zd.Config(
        browser_executable_path=chrome_path,
        user_data_dir=os.path.abspath(profile_dir),
        browser_args=[
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-infobars",
            "--profile-directory=Default",  # evita el selector de perfiles en primer arranque
            "--disable-sync",               # sin popup de login a cuenta Google
            "--disable-extensions",         # sin extensiones en el perfil del bot
            f"--user-agent={_get_user_agent()}",
        ],
        disable_webrtc=True,
        disable_webgl=True,
        no_sandbox=True,
    )
    return await zd.start(config)


async def human_delay(min_ms: int = 500, max_ms: int = 900) -> None:
    """Pausa aleatoria entre min_ms y max_ms milisegundos."""
    await asyncio.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


async def human_type(element: object, text: str) -> None:
    """Escribe texto carácter a carácter con delay 80-220 ms por carácter."""
    for char in text:
        await element.send_keys(char)
        await asyncio.sleep(random.uniform(0.08, 0.22))


# ---------------------------------------------------------------------------
# Human click — posición gaussiana + Bézier path + mousedown/up separados
# RN-HC01..RN-HC11 (spec human-click v2.2.1, guardian OK 2026-06-01)
# ---------------------------------------------------------------------------

# Última posición conocida del cursor por tab, keyed por id(tab).
# Permite que el siguiente click parta del punto donde quedó el anterior
# en vez de teletransportarse siempre desde el mismo origen (RN-HC05).
_CURSOR_POS: dict[int, tuple[float, float]] = {}


def _bezier_path(
    origin: tuple[float, float],
    target: tuple[float, float],
    n_points: int,
) -> list[tuple[float, float]]:
    """
    Genera n_points waypoints siguiendo una Bézier cuadrática con un punto
    de control perpendicular a la recta origen-target desplazado por ruido
    gaussiano (RN-HC04, spec §7).

    El primer punto es ligeramente distinto al origen (la curva arranca
    ya desplazada). El último punto es el target exacto para que el click
    aterrice en las coordenadas calculadas.
    """
    ox, oy = origin
    tx, ty = target
    mx, my = (ox + tx) / 2, (oy + ty) / 2
    dx, dy = tx - ox, ty - oy
    length = math.hypot(dx, dy) or 1.0
    # Vector perpendicular normalizado
    px_, py_ = -dy / length, dx / length
    # Desviación entre 5-20% de la longitud, con signo aleatorio
    offset = random.uniform(0.05, 0.20) * length * random.choice([-1, 1])
    cx, cy = mx + px_ * offset, my + py_ * offset
    points: list[tuple[float, float]] = []
    for i in range(1, n_points + 1):
        t = i / n_points
        u = 1 - t
        # Bézier cuadrática B(t) = (1-t)²·P0 + 2(1-t)t·C + t²·P1
        x = u * u * ox + 2 * u * t * cx + t * t * tx
        y = u * u * oy + 2 * u * t * cy + t * t * ty
        # Micro-ruido de tembleque humano (±0.5 px)
        x += random.gauss(0, 0.5)
        y += random.gauss(0, 0.5)
        points.append((x, y))
    # Forzar último waypoint al target exacto
    points[-1] = (tx, ty)
    return points


def _sample_click_point(
    rect: dict,
    jitter: float,
) -> tuple[float, float]:
    """
    Calcula el punto de click con distribución gaussiana truncada al inner
    80% del rect (margen 10% por lado). Rejection sampling con cap en 20
    intentos; fallback al centro geométrico si todos son rechazados (RN-HC03).

    Función pura (sin IO) para facilitar el testing unitario.
    """
    x = rect["x"]
    y = rect["y"]
    w = rect["width"]
    h = rect["height"]
    cx = x + w / 2
    cy = y + h / 2
    sigma_x = jitter * w
    sigma_y = jitter * h
    clip_x_lo = x + 0.1 * w
    clip_x_hi = x + 0.9 * w
    clip_y_lo = y + 0.1 * h
    clip_y_hi = y + 0.9 * h
    px, py = cx, cy  # fallback si todos los intentos son rechazados
    for _ in range(20):
        px = random.gauss(cx, sigma_x)
        py = random.gauss(cy, sigma_y)
        if clip_x_lo <= px <= clip_x_hi and clip_y_lo <= py <= clip_y_hi:
            break
    else:
        px, py = cx, cy
    return px, py


async def _dispatch_mouse_move(tab: zd.Tab, x: float, y: float) -> None:
    """Emite un único evento mouseMoved al punto (x, y) via CDP."""
    await tab.send(
        zd.cdp.input_.dispatch_mouse_event("mouseMoved", x=x, y=y)
    )


async def _dispatch_mouse_down(tab: zd.Tab, x: float, y: float) -> None:
    """Emite mousePressed (botón izquierdo) en (x, y) via CDP."""
    await tab.send(
        zd.cdp.input_.dispatch_mouse_event(
            "mousePressed",
            x=x,
            y=y,
            button=zd.cdp.input_.MouseButton("left"),
            buttons=1,
            click_count=1,
        )
    )


async def _dispatch_mouse_up(tab: zd.Tab, x: float, y: float) -> None:
    """Emite mouseReleased (botón izquierdo) en (x, y) via CDP."""
    await tab.send(
        zd.cdp.input_.dispatch_mouse_event(
            "mouseReleased",
            x=x,
            y=y,
            button=zd.cdp.input_.MouseButton("left"),
            buttons=0,
            click_count=1,
        )
    )


async def _perform_human_click(
    tab: zd.Tab,
    rect: dict,
    jitter: float,
    settle_ms: tuple[int, int],
) -> None:
    """
    Núcleo compartido de human_click y human_click_at_rect.
    El rect ya ha sido validado antes de llegar aquí.
    Ejecuta: muestreo gaussiano → Bézier path → settle → mousedown/up.
    """
    px, py = _sample_click_point(rect, jitter)

    # Obtener última posición del cursor para este tab (RN-HC05)
    tab_key = id(tab)
    if tab_key in _CURSOR_POS:
        origin = _CURSOR_POS[tab_key]
    else:
        # Primera llamada: arrancar del centro del viewport (no de (0,0))
        vw = await tab.evaluate("window.innerWidth")
        vh = await tab.evaluate("window.innerHeight")
        vw = vw if isinstance(vw, (int, float)) else 800
        vh = vh if isinstance(vh, (int, float)) else 600
        origin = (float(vw) / 2, float(vh) / 2)

    # Generar y recorrer waypoints Bézier (RN-HC04)
    n_waypoints = random.randint(3, 8)
    waypoints = _bezier_path(origin, (px, py), n_waypoints)
    for wx, wy in waypoints:
        await _dispatch_mouse_move(tab, round(wx), round(wy))
        await asyncio.sleep(random.uniform(0.008, 0.025))

    # Actualizar posición persistida del cursor (RN-HC05)
    _CURSOR_POS[tab_key] = (px, py)

    # Settle: tiempo de reacción motor humano antes del press (RN-HC06)
    await asyncio.sleep(random.uniform(settle_ms[0] / 1000, settle_ms[1] / 1000))

    # Click: mousedown + pausa real + mouseup (RN-HC07)
    await _dispatch_mouse_down(tab, round(px), round(py))
    await asyncio.sleep(random.uniform(0.035, 0.110))
    await _dispatch_mouse_up(tab, round(px), round(py))


def _validate_jitter_settle(jitter: float, settle_ms: tuple[int, int]) -> None:
    """Valida los parámetros jitter y settle_ms (EC-HC07, EC-HC08)."""
    if not (0.10 <= jitter <= 0.45):
        raise ValueError(f"jitter must be in [0.10, 0.45], got {jitter}")
    if len(settle_ms) != 2 or not (0 < settle_ms[0] <= settle_ms[1]):
        raise ValueError(
            f"settle_ms must be a tuple (min_ms, max_ms) with 0 < min_ms <= max_ms, got {settle_ms}"
        )


def _is_offscreen(rect: dict) -> bool:
    """
    Devuelve True si el rect está completamente fuera del viewport.
    Detecta: todo el elemento a la izquierda, arriba, derecha o abajo del viewport.
    Se considera offscreen si el borde "de salida" del elemento no supera el cero:
      x + width < 0  → completamente a la izquierda
      y + height < 0 → completamente arriba
    No se comprueba el límite derecho/inferior porque no se conoce el viewport
    sin una llamada async; esos casos se detectarán en _perform_human_click
    cuando el punto gaussiano caiga fuera.
    """
    return (rect["x"] + rect["width"] < 0) or (rect["y"] + rect["height"] < 0)


async def human_click(
    element: zd.Element,
    page: zd.Tab,
    jitter: float = 0.25,
    settle_ms: tuple[int, int] = (80, 180),
) -> None:
    """
    Click anti-detección: posición gaussiana truncada dentro del inner 80%
    del elemento, precedido de movimiento con waypoints Bézier y micro-pausa,
    con mousedown y mouseup separados por 35-110 ms.

    API de zendriver usada:
      - element.apply() para obtener getBoundingClientRect() en coordenadas CSS
      - tab.send(cdp.input_.dispatch_mouse_event(...)) para move/down/up
      - element.scroll_into_view() para scrollear antes de fallar (RN-HC10)

    DPR: zendriver opera en CSS pixels (los eventos CDP reciben coords CSS).
    No se multiplica por devicePixelRatio.

    Raises:
        ElementNotClickableError: si el rect es inválido (width/height 0)
            o el elemento sigue offscreen tras intentar scroll.
        ValueError: si jitter o settle_ms están fuera de rango.
    """
    _validate_jitter_settle(jitter, settle_ms)

    # Obtener bounding rect via element.apply() — CSS pixels, coords de viewport
    rect: dict = await element.apply(
        "(el) => { const r = el.getBoundingClientRect(); "
        "return {x: r.left, y: r.top, width: r.width, height: r.height}; }"
    )

    tag: str = await element.apply("(el) => el.tagName") or "UNKNOWN"

    # Rect inválido: width o height es 0 (display:none, no en DOM) — EC-HC01
    if not rect or rect.get("width", 0) == 0 or rect.get("height", 0) == 0:
        raise ElementNotClickableError(tag, "rect width/height is 0")

    # Elemento offscreen: intentar scroll antes de fallar (RN-HC10, EC-HC09)
    if _is_offscreen(rect):
        await element.scroll_into_view()
        await human_delay(150, 350)
        rect = await element.apply(
            "(el) => { const r = el.getBoundingClientRect(); "
            "return {x: r.left, y: r.top, width: r.width, height: r.height}; }"
        )
        if _is_offscreen(rect):
            raise ElementNotClickableError(
                tag, f"element offscreen after scroll attempt: rect={rect}"
            )

    await _perform_human_click(page, rect, jitter, settle_ms)


async def human_click_at_rect(
    rect: dict,
    page: zd.Tab,
    jitter: float = 0.25,
    settle_ms: tuple[int, int] = (80, 180),
) -> None:
    """
    Variante de human_click para cuando el rect ya viene de JS evaluate().
    No necesita element — toma las coordenadas del rect directamente.
    rect debe ser {"x": float, "y": float, "width": float, "height": float}.

    Misma lógica gaussiana, mismas validaciones de jitter/settle_ms.
    No realiza scroll automático (el caller es responsable de que el rect
    sea válido al pasarlo — si viene de JS, debería estarlo).

    Raises:
        ElementNotClickableError: si el rect tiene width/height 0 o es offscreen.
        ValueError: si jitter o settle_ms están fuera de rango.
    """
    _validate_jitter_settle(jitter, settle_ms)

    if not rect or rect.get("width", 0) == 0 or rect.get("height", 0) == 0:
        raise ElementNotClickableError("js-rect", "rect width/height is 0")

    if _is_offscreen(rect):
        raise ElementNotClickableError("js-rect", f"element offscreen: rect={rect}")

    await _perform_human_click(page, rect, jitter, settle_ms)


# ---------------------------------------------------------------------------
# ZendriverAdapter — implementación de BrowserPort (operaciones genéricas)
# ---------------------------------------------------------------------------

class ZendriverAdapter(BrowserPort):
    """
    Implementación de BrowserPort usando zendriver (CDP directo, sin ChromeDriver).

    Capas de anti-detección activas:
    - Sin ChromeDriver -> navigator.webdriver=false
    - --disable-blink-features=AutomationControlled
    - Perfil Chrome persistente por cuenta (cookies/historial reales)
    - User-Agent dinámico por OS
    - Sin modo headless
    - Delays humanos: 500-900 ms entre acciones
    - Escritura humana: 80-220 ms por carácter
    - no_sandbox=True (requerido en VirtualBox)
    """

    def __init__(self, profile_dir: str = "profiles/default") -> None:
        self._profile_dir = os.path.abspath(profile_dir)
        self._browser: Optional[zd.Browser] = None
        self._tab = None

    async def start(self) -> None:
        config = zd.Config(
            user_data_dir=self._profile_dir,
            browser_args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-infobars",
                f"--user-agent={_get_user_agent()}",
            ],
            disable_webrtc=True,
            disable_webgl=True,
            no_sandbox=True,
        )
        self._browser = await zd.start(config)
        self._tab = await self._browser.get("about:blank")

    async def stop(self) -> None:
        if self._browser:
            await self._browser.stop()
            self._browser = None
            self._tab = None

    async def navigate(self, url: str) -> None:
        await self._tab.get(url)
        await self._human_delay()

    async def find_element(self, selector: str) -> object:
        return await self._tab.find(selector)

    async def type_text(self, selector: str, text: str) -> None:
        """Escribe carácter a carácter con delay de 80-220 ms (simula typing humano)."""
        element = await self.find_element(selector)
        for char in text:
            await element.send_keys(char)
            await asyncio.sleep(random.uniform(0.08, 0.22))

    async def click(self, selector: str) -> None:
        element = await self.find_element(selector)
        await human_click(element, self._tab)
        await self._human_delay()

    async def _human_delay(self) -> None:
        """Pausa de 500-900 ms para simular tiempo de reacción humano."""
        await asyncio.sleep(random.uniform(0.5, 0.9))
