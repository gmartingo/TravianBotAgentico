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
import os
import platform
import random
import re
import subprocess
from typing import Optional

import zendriver as zd

from core.exceptions import BrowserError
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
        await element.click()
        await self._human_delay()

    async def _human_delay(self) -> None:
        """Pausa de 500-900 ms para simular tiempo de reacción humano."""
        await asyncio.sleep(random.uniform(0.5, 0.9))
