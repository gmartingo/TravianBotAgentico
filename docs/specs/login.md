---
id: login
titulo: Login de cuenta en un mundo de Travian
estado: implemented
fecha: 2026-05-24
fecha_impl: 2026-05-24
autor: analista
apis_validadas_por_desarrollador_apis: n-a
---

# Login de cuenta en un mundo de Travian

## 1. Objetivo de negocio

Permitir que el bot abra una sesión autenticada en un mundo concreto de Travian para una cuenta registrada, obteniendo un objeto `Browser` vivo que los use cases subsiguientes (lectura de recursos, construcción, raiding, etc.) reutilizarán durante la sesión. La sesión es statefull: se mantiene en un registro en memoria (`WorldRuntimePort`) identificada por `world_id`.

El login debe ser indistinguible del comportamiento de un humano real: navegación, pausas, escritura carácter a carácter, y perfil de Chrome persistente con cookies e historial reales.

Esta feature NO expone ningún endpoint HTTP — es lógica de core orquestada por `LoginUseCase`. La exposición vía API (endpoint `/bot/login`) es responsabilidad de una feature posterior.

---

## 2. Actores y permisos

| Actor | Rol |
|---|---|
| `LoginUseCase` | Orquestador — recupera cuenta y mundo de la BD, delega en `WorldRuntimePort.login()` |
| `adapters/browser/login.py::login()` | Implementación concreta — abre Chrome, navega, rellena formulario, verifica URL de éxito |
| `SessionRegistry` (futuro adaptador de `WorldRuntimePort`) | Registro stateful en memoria de browsers activos por `world_id` |
| `DbPort` | Fuente de verdad para recuperar `Account` (con sus `World`) |

No hay autenticación humana en esta feature — el bot actúa de forma autónoma.

---

## 3. Alcance

### Dentro del alcance

- Crear entidades de dominio: `Tribe`, `Village`, `World`, actualizar `Account`.
- Crear el puerto `WorldRuntimePort`.
- Reemplazar `adapters/browser/driver.py` con la versión completa del proyecto viejo.
- Crear `adapters/browser/login.py`.
- Ampliar `core/exceptions.py` con todas las excepciones del dominio.
- Crear `core/use_cases/login_use_case.py` con `LoginUseCase` y `LogoutUseCase`.
- Actualizar `core/ports/db_port.py` para que `get_account` devuelva `Account` con sus `worlds` cargados (o elevar excepción — ver sección 6).

### Fuera del alcance

- Endpoint HTTP `/bot/login` o `/bot/logout` (feature separada).
- Implementación concreta de `SessionRegistry` (el adaptador de `WorldRuntimePort`) — la implementación concreta se define en la feature de orquestación del bot.
- Persistencia de mundos/aldeas en la BD (la BD CRUD de mundos es una feature separada).
- Lógica post-login: lectura de recursos, construcción, raiding.
- Tests de integración con Chrome real (los tests de esta feature son unitarios con mocks).

---

## 4. Reglas de negocio

| ID | Regla |
|---|---|
| RN-01 | Una `Account` tiene una lista de `World`. El login siempre es para una cuenta + un mundo específico. |
| RN-02 | El `world_id` debe pertenecer a la lista `account.worlds`; si no, se lanza `WorldNotFoundError`. |
| RN-03 | Cada sesión de browser usa un perfil Chrome dedicado: `profiles/account_{account_id}_world_{world_id}/`. Esto mantiene cookies e historial reales por cuenta/mundo. |
| RN-04 | El bot considera el login exitoso si y solo si la URL de la página tras el submit contiene `"dorf"` o `"village"` (indicador nativo de Travian de estar en la vista de aldea). |
| RN-05 | Si el login falla (credenciales incorrectas, error de red, excepción), `login()` devuelve `(False, None)` y el browser se cierra para no dejar procesos Chrome huérfanos. |
| RN-06 | El User-Agent debe coincidir con la versión real de Chrome instalada en el host (obtenida leyendo el binario, no hardcodeada). Actualmente Chrome 136 es la versión mínima esperada; Chrome/124 es obsoleto y aumenta el riesgo de detección. |
| RN-07 | En macOS, el User-Agent debe incluir la versión real del OS obtenida con `platform.mac_ver()`, no un valor fijo como `10_15_7`. |
| RN-08 | En Linux, antes de arrancar Chrome se deben setear las variables de entorno `DISPLAY=:0`, `BOX64_LOG=0` y `BOX64_DYNAREC_LOG=0` (necesario para Raspberry Pi 4B con Box64 + Chrome x64). |
| RN-09 | Si hay procesos Chrome bloqueando el directorio del perfil al arrancar, deben matarse silenciosamente antes de crear el `zd.Config`. |
| RN-10 | `LogoutUseCase` cierra el browser activo para `world_id` en el `WorldRuntimePort`. Si no hay sesión activa, no lanza excepción — opera de forma idempotente. |
| RN-11 | Los selectores de formulario usan atributos HTML estructurales (`input[name='name']`, `input[name='password']`, `[type='submit']`), nunca texto visible (Travian es multilenguaje). |
| RN-12 | `Account` solo contiene credenciales (`id`, `username`, `password`) y su lista de `World`. Los campos `server_url` y `active` se eliminan — no son atributos de la entidad de dominio. |

---

## 5. Flujo principal y flujos alternativos

### Flujo principal — login exitoso

```
caller
  └─> LoginUseCase.execute(account_id, world_id)
        ├─ db.get_account(account_id)          → Account (con worlds cargados)
        ├─ _find_world(account, world_id)       → World
        └─ registry.login(account, world)
              └─> login(account, world)  [adapters/browser/login.py]
                    ├─ _kill_orphan_chrome(profile_dir)
                    ├─ create_browser(profile_dir)         → zd.Browser
                    ├─ browser.get(world.server)            → page
                    ├─ human_delay(1000, 2000)
                    ├─ page.find("input[name='name']")      → username_field
                    ├─ human_delay()
                    ├─ human_type(username_field, account.username)
                    ├─ page.find("input[name='password']")  → password_field
                    ├─ human_delay()
                    ├─ human_type(password_field, account.password)
                    ├─ human_delay()
                    ├─ page.find("[type='submit']")         → submit_btn
                    ├─ submit_btn.click()
                    ├─ human_delay(3000, 5000)
                    ├─ check: "dorf" in page.url OR "village" in page.url
                    └─ return (True, browser)
              └─ registry stores browser for world_id
        └─ return True
```

### Flujo alternativo A — cuenta no encontrada

```
LoginUseCase.execute(account_id=99, world_id=1)
  └─ db.get_account(99) → None
  └─ raise AccountNotFoundError(99)
```

### Flujo alternativo B — mundo no pertenece a la cuenta

```
LoginUseCase.execute(account_id=1, world_id=99)
  └─ db.get_account(1) → Account(worlds=[World(id=1), World(id=2)])
  └─ _find_world(account, 99) → raise WorldNotFoundError(99)
```

### Flujo alternativo C — credenciales incorrectas

```
login(account, world)
  └─ ... navega, rellena form, hace submit ...
  └─ human_delay(3000, 5000)
  └─ "dorf" not in page.url AND "village" not in page.url
  └─ logger.warning("Login fallido...")
  └─ await browser.stop()
  └─ return (False, None)
```

### Flujo alternativo D — excepción durante el login

```
login(account, world)
  └─ ... cualquier excepción de zendriver/red ...
  └─ except Exception: logger.exception(...)
  └─ (browser no se cierra aquí — browser puede no existir aún)
  └─ return (False, None)
```

NOTA: En el flujo D, si el browser ya fue creado antes de la excepción, puede quedar sin cerrar. Ver edge case EC-04.

### Flujo alternativo E — logout

```
LogoutUseCase.execute(world_id)
  └─ registry.logout(world_id)
        └─ if world_id in sessions:
              await sessions[world_id].stop()
              del sessions[world_id]
        └─ (si no existe, no hace nada — idempotente)
```

---

## 6. Edge cases

| ID | Caso | Tratamiento esperado |
|---|---|---|
| EC-01 | `db.get_account` devuelve `None` (cuenta no existe) | `LoginUseCase` lanza `AccountNotFoundError(account_id)`. El browser nunca se abre. |
| EC-02 | `world_id` no está en `account.worlds` | `LoginUseCase._find_world` lanza `WorldNotFoundError(world_id)`. El browser nunca se abre. |
| EC-03 | Proceso Chrome bloqueando el perfil al arrancar | `_kill_orphan_chrome(profile_dir)` mata silenciosamente cualquier proceso Chrome que tenga ese directorio como `--user-data-dir` antes de llamar a `zd.start()`. |
| EC-04 | Excepción después de que el browser ya fue creado | El bloque `except` en `login()` debe intentar `await browser.stop()` si `browser` no es `None` antes de retornar `(False, None)`. El código de referencia tiene un bug aquí — el spec lo corrige. |
| EC-05 | `world.server` sin trailing slash o con doble slash | `World.__post_init__` normaliza: `self.server = self.server.strip().rstrip("/") + "/"`. Garantizado antes de que `login.py` llame a `browser.get(world.server)`. |
| EC-06 | Login ya activo para el mismo `world_id` | `WorldRuntimePort.login()` debe verificar si ya existe una sesión activa para ese `world_id`. Si existe, la cierra antes de abrir una nueva (evita browsers huérfanos). |
| EC-07 | Chrome no instalado en la ruta esperada | `create_browser()` intenta las rutas de `_CHROME_PATHS[platform.system()]` en orden. Si ninguna existe, lanza `BrowserError("Chrome no encontrado en ninguna ruta conocida")`. |
| EC-08 | `account.worlds` es lista vacía | `_find_world` itera la lista vacía y llega al `raise WorldNotFoundError(world_id)` — mismo tratamiento que EC-02. No requiere caso especial. |
| EC-09 | URL de Travian sin `.xN.` en el servidor (velocidad no parseable) | `World.server_speed` devuelve `1.0` como fallback. No bloquea el login. |
| EC-10 | Login en Linux sin variable `DISPLAY` | `create_browser()` setea `os.environ["DISPLAY"] = ":0"` condicionalmente si `platform.system() == "Linux"` y `DISPLAY` no está ya definida. |

---

## 7. Modelo de datos / cambios de esquema

Esta feature NO introduce cambios en la BD SQLite (no hay migraciones). Las entidades son solo clases Python en memoria para esta fase.

### Entidades a crear / reemplazar

#### `core/entities/tribe.py` (CREAR)

```python
from enum import Enum

class Tribe(Enum):
    ROMANS = "romans"
    TEUTONS = "teutons"
    GAULS = "gauls"
    EGYPTIANS = "egyptians"
    HUNS = "huns"
```

#### `core/entities/village.py` (CREAR)

```python
from dataclasses import dataclass

@dataclass
class Village:
    id: int
    world_id: int
    game_id: int   # ID interno de Travian (usado en URLs: gid=N)
    name: str
    x: int         # Coordenada X en el mapa
    y: int         # Coordenada Y en el mapa
```

#### `core/entities/world.py` (CREAR)

```python
import re
from dataclasses import dataclass, field
from core.entities.tribe import Tribe
from core.entities.village import Village

_SERVER_SPEED_RE = re.compile(r'\.x(\d+)\.', re.IGNORECASE)

@dataclass
class World:
    id: int
    server: str      # URL base del servidor, ej: "https://ts1.x1.international.travian.com/"
    tribe: Tribe
    villages: list[Village] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.server = self.server.strip().rstrip("/") + "/"

    @property
    def server_speed(self) -> float:
        """Extrae la velocidad del servidor del dominio (x1, x3, x5...). Default 1.0."""
        m = _SERVER_SPEED_RE.search(self.server or "")
        return float(m.group(1)) if m else 1.0
```

#### `core/entities/account.py` (REEMPLAZAR)

Eliminar `server_url` y `active`. Añadir `worlds`. Eliminar `__post_init__` (las validaciones de `server_url` ya no aplican).

```python
from dataclasses import dataclass, field
from typing import Optional
from core.entities.world import World

@dataclass
class Account:
    id: Optional[int]
    username: str
    password: str
    worlds: list[World] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.username:
            raise ValueError("El nombre de usuario no puede estar vacío.")
```

**Nota para el implementador:** `DbPort.get_account()` actualmente devuelve `Optional[Account]`. El `LoginUseCase` espera que la cuenta ya tenga sus `worlds` cargados. Como la BD aún no persiste mundos (fuera de alcance), en los tests los mundos se inyectan directamente en la entidad. Cuando la BD soporte mundos, `get_account` deberá hacer JOIN y poblar `account.worlds`. Esto es intencionado y no es un bug.

### Cambios en `core/ports/db_port.py` (MODIFICAR — cambio mínimo)

El contrato de `get_account` no cambia de firma. El único cambio es que la importación de `Account` es compatible con la nueva entidad (sin `server_url`). No hay cambio de firma.

---

## 8. Contratos de API / interfaces

No aplica. Esta feature no expone ni consume endpoints HTTP.

`apis_validadas_por_desarrollador_apis: n-a`

---

## 9. Flujo lógico paso a paso

### 9.1 `adapters/browser/driver.py` — funciones standalone a añadir

El archivo actual (`ZendriverAdapter`) se conserva intacto. Se añaden al mismo módulo las siguientes funciones standalone que `login.py` usará:

```python
import subprocess
import sys

# Rutas de Chrome por OS
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
    Lee la versión COMPLETA de Chrome (4 segmentos) ejecutando --version.
    Devuelve "136.0.0.0" como fallback si falla.

    IMPORTANTE: usar la versión completa (ej: "136.0.7103.114"), no solo el major.
    El patrón "Chrome/136.0.0.0" (con tres ceros) es un indicador conocido de
    automatización (Puppeteer, nodriver mal configurado) y puede ser detectado.
    """
    try:
        result = subprocess.run(
            [chrome_path, "--version"],
            capture_output=True, text=True, timeout=5
        )
        # Salida: "Google Chrome 136.0.7103.114 ..." → capturar "136.0.7103.114"
        match = re.search(r'(\d+\.\d+\.\d+\.\d+)', result.stdout)
        if match:
            return match.group(1)
    except Exception:
        pass
    return "136.0.0.0"  # Fallback solo si chrome --version falla

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

async def create_browser(profile_dir: str) -> zd.Browser:
    """
    Crea y arranca un browser zendriver con todas las capas de anti-detección.
    En Linux configura DISPLAY y variables Box64 si es necesario.
    """
    if platform.system() == "Linux":
        os.environ.setdefault("DISPLAY", ":0")
        os.environ.setdefault("BOX64_LOG", "0")
        os.environ.setdefault("BOX64_DYNAREC_LOG", "0")

    config = zd.Config(
        user_data_dir=os.path.abspath(profile_dir),
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
    return await zd.start(config)

async def human_delay(min_ms: int = 500, max_ms: int = 900) -> None:
    """Pausa aleatoria entre min_ms y max_ms milisegundos."""
    await asyncio.sleep(random.uniform(min_ms / 1000, max_ms / 1000))

async def human_type(element: object, text: str) -> None:
    """Escribe texto carácter a carácter con delay 80-220 ms por carácter."""
    for char in text:
        await element.send_keys(char)
        await asyncio.sleep(random.uniform(0.08, 0.22))
```

La clase `ZendriverAdapter` existente NO se modifica. La función `_get_user_agent()` que ya existe en el módulo se reemplaza por la nueva versión dinámica. El implementador debe eliminar la función `_get_user_agent()` original y los imports que ya no sean necesarios, y añadir los imports de `subprocess` y `re` que la nueva versión requiere.

### 9.2 `adapters/browser/login.py` — función `login()`

```python
import logging
import zendriver as zd
from adapters.browser.driver import create_browser, human_delay, human_type, _kill_orphan_chrome
from core.entities.account import Account
from core.entities.world import World

logger = logging.getLogger(__name__)

async def login(account: Account, world: World) -> tuple[bool, zd.Browser | None]:
    profile_dir = os.path.abspath(f"profiles/account_{account.id}_world_{world.id}")
    _kill_orphan_chrome(profile_dir)
    browser: zd.Browser | None = None
    try:
        browser = await create_browser(profile_dir=profile_dir)
        page = await browser.get(world.server)
        await human_delay(1000, 2000)

        username_field = await page.find("input[name='name']")
        await human_delay()
        await human_type(username_field, account.username)

        password_field = await page.find("input[name='password']")
        await human_delay()
        await human_type(password_field, account.password)

        await human_delay()
        submit_button = await page.find("[type='submit']")
        await human_delay(200, 500)  # pausa visual antes del click, como haría un humano
        await submit_button.click()
        await human_delay(3000, 5000)

        success = "dorf" in page.url or "village" in page.url
        if success:
            return True, browser

        logger.warning(
            "Login fallido para %s en %s — URL: %s",
            account.username, world.server, page.url
        )
        await browser.stop()
        return False, None

    except Exception:
        logger.exception(
            "Excepción durante el login de %s en %s",
            account.username, world.server
        )
        if browser is not None:
            try:
                await browser.stop()
            except Exception:
                pass
        return False, None
```

**Diferencia respecto al código de referencia:** el bloque `except` ahora cierra el browser si fue creado antes de la excepción (corrección del EC-04).

### 9.3 `core/ports/world_runtime_port.py` — puerto formal

```python
from abc import ABC, abstractmethod
from core.entities.account import Account
from core.entities.world import World

class WorldRuntimePort(ABC):
    """
    Puerto para el registro de sesiones activas del bot.
    Abstrae el ciclo de vida de los browsers por mundo.
    """

    @abstractmethod
    async def login(self, account: Account, world: World) -> bool:
        """
        Abre una sesión autenticada para account en world.
        Devuelve True si el login fue exitoso, False en caso contrario.
        Si ya existe una sesión para world.id, la cierra antes de abrir una nueva.
        """

    @abstractmethod
    async def logout(self, world_id: int) -> None:
        """
        Cierra la sesión activa para world_id.
        Idempotente: no lanza excepción si no hay sesión activa.
        """

    @abstractmethod
    def is_active(self, world_id: int) -> bool:
        """
        Devuelve True si hay una sesión activa para world_id.
        """
```

### 9.4 `core/use_cases/login_use_case.py`

```python
from dataclasses import dataclass
from core.ports.db_port import DbPort
from core.ports.world_runtime_port import WorldRuntimePort
from core.entities.account import Account
from core.entities.world import World
from core.exceptions import AccountNotFoundError, WorldNotFoundError

@dataclass
class LoginUseCase:
    registry: WorldRuntimePort
    db: DbPort

    async def execute(self, account_id: int, world_id: int) -> bool:
        account = await self.db.get_account(account_id)
        if account is None:
            raise AccountNotFoundError(account_id)
        world = self._find_world(account, world_id)
        return await self.registry.login(account, world)

    def _find_world(self, account: Account, world_id: int) -> World:
        for world in account.worlds:
            if world.id == world_id:
                return world
        raise WorldNotFoundError(world_id)


@dataclass
class LogoutUseCase:
    registry: WorldRuntimePort

    async def execute(self, world_id: int) -> None:
        await self.registry.logout(world_id)
```

### 9.5 `core/exceptions.py` — versión completa (REEMPLAZAR)

```python
class TravianBotError(Exception):
    """Base de todas las excepciones del dominio."""

class AccountNotFoundError(TravianBotError):
    def __init__(self, account_id: int) -> None:
        super().__init__(f"Cuenta {account_id} no encontrada")
        self.account_id = account_id

class DuplicateAccountError(TravianBotError):
    def __init__(self, username: str) -> None:
        super().__init__(f"Ya existe una cuenta con el username '{username}'")
        self.username = username

class WorldNotFoundError(TravianBotError):
    def __init__(self, world_id: int) -> None:
        super().__init__(f"Mundo {world_id} no encontrado")
        self.world_id = world_id

class SessionNotActiveError(TravianBotError):
    def __init__(self) -> None:
        super().__init__("No hay sesión activa — ejecuta login primero")

class InvalidCredentialsError(TravianBotError):
    def __init__(self, username: str) -> None:
        super().__init__(f"Credenciales incorrectas para '{username}'")
        self.username = username

class VillageNotFoundError(TravianBotError):
    def __init__(self, village_id: int) -> None:
        super().__init__(f"Aldea {village_id} no encontrada")
        self.village_id = village_id

class FarmListNotFoundError(TravianBotError):
    def __init__(self, farm_list_id: int) -> None:
        super().__init__(f"Lista de vacas {farm_list_id} no encontrada")
        self.farm_list_id = farm_list_id

# Las siguientes se incluyen para completitud del dominio; se usarán en features posteriores:
class LoginError(TravianBotError):
    """Error genérico durante el proceso de login en Travian."""

class BrowserError(TravianBotError):
    """Error en la capa de automatización del navegador."""

class DatabaseError(TravianBotError):
    """Error al acceder a la base de datos local."""
```

---

## 10. Validaciones y reglas

| Campo | Validación | Dónde |
|---|---|---|
| `account.username` | No puede ser vacío o None | `Account.__post_init__` |
| `account.id` | Debe ser no-None para construir `profile_dir` | `login()` asume que la cuenta viene de la BD con ID asignado |
| `world.server` | Se normaliza con trailing slash en `World.__post_init__` | `World.__post_init__` |
| `world_id` | Debe existir en `account.worlds` | `LoginUseCase._find_world` |
| `account_id` | Debe existir en la BD | `LoginUseCase.execute` |
| `profile_dir` | Ruta absoluta siempre | `create_browser` llama a `os.path.abspath()` |
| Versión de Chrome | No hardcodeada; leída del binario | `_detect_chrome_major_version()` |
| Selectores de formulario | Solo estructurales (`input[name='...']`, `[type='submit']`) | `login.py` — regla absoluta, nunca texto visible |

---

## 11. Seguridad, rendimiento y concurrencia

### Anti-detección (restricción no negociable)

| Capa | Implementación en esta feature |
|---|---|
| Sin ChromeDriver | `zendriver` vía `zd.start()` — CDP directo |
| Perfil persistente | `profiles/account_{id}_world_{id}/` con `user_data_dir` absoluto |
| User-Agent dinámico | `_get_user_agent()` lee versión real de Chrome + version real de macOS |
| Sin headless | `zd.Config` no activa headless (comportamiento por defecto de zendriver) |
| Delays humanos | `human_delay(500, 900)` entre acciones; `human_delay(1000, 2000)` tras navegación; `human_delay(3000, 5000)` tras submit |
| Escritura humana | `human_type()`: 80-220 ms por carácter, nunca paste masivo |
| Sin AutomationControlled | `--disable-blink-features=AutomationControlled` en browser args |
| Sin WebRTC leak | `disable_webrtc=True` |
| Sin WebGL fingerprint | `disable_webgl=True` |
| Sin sandbox (VM) | `no_sandbox=True` — requerido en VirtualBox; no afecta fingerprint de Travian |
| Variables Box64 (Pi) | `BOX64_LOG=0`, `BOX64_DYNAREC_LOG=0` — evitan ruido en stderr que podría interferir con el proceso |

### Rendimiento

- El login es intrínsecamente lento (~8-15 segundos) por diseño: los delays humanos son la feature, no el problema.
- Un browser Chrome consume ~200-400 MB RAM. El `SessionRegistry` debe limitar sesiones concurrentes (definido en la feature de orquestación, fuera de alcance aquí).
- `_kill_orphan_chrome()` usa `taskkill /F /IM chrome.exe` en Windows — mata TODOS los Chrome, no solo el del perfil. Esto es aceptable en el entorno de test (VM dedicada). En producción con múltiples cuentas simultáneas, se deberá refinar para matar solo el proceso con el `--user-data-dir` correcto.

### Concurrencia

- `LoginUseCase` es stateless. El estado (browser vivo) vive en `WorldRuntimePort`.
- El `WorldRuntimePort` es el punto de concurrencia: si dos llamadas simultáneas intentan login para el mismo `world_id`, la implementación del adaptador debe serializar o rechazar la segunda (definido en la feature de SessionRegistry).
- Los locks de asyncio son responsabilidad del adaptador concreto de `WorldRuntimePort`, no del use case.

### Seguridad de credenciales

- Las credenciales (`account.password`) se pasan en memoria como string Python — no se loguean ni se persisten en texto plano.
- El logger en `login.py` usa `account.username` en warnings, nunca `account.password`.
- El perfil de Chrome cifra la sesión a nivel de OS (DPAPI en Windows, Keychain en macOS).

---

## 12. Plan de pruebas

### Tests unitarios (sin Chrome real)

Todos los tests mockean `WorldRuntimePort` y `DbPort`. No arrancan Chrome.

#### 12.1 `LoginUseCase` — casos de uso

| Test | Descripción | Resultado esperado |
|---|---|---|
| `test_login_success` | account existe, world en lista, registry.login devuelve True | `execute` devuelve True |
| `test_login_failure_from_registry` | registry.login devuelve False | `execute` devuelve False |
| `test_account_not_found` | db.get_account devuelve None | lanza `AccountNotFoundError` |
| `test_world_not_found` | world_id no en account.worlds | lanza `WorldNotFoundError` |
| `test_world_list_empty` | account.worlds = [] | lanza `WorldNotFoundError` |

#### 12.2 `LogoutUseCase`

| Test | Descripción | Resultado esperado |
|---|---|---|
| `test_logout_calls_registry` | registry.logout llamado con world_id correcto | registry.logout invocado una vez |
| `test_logout_idempotent` | registry.logout no lanza si no hay sesión | no lanza excepción |

#### 12.3 Entidades de dominio

| Test | Descripción | Resultado esperado |
|---|---|---|
| `test_world_trailing_slash` | server sin slash → normalizado con slash | `world.server` termina en `/` |
| `test_world_double_slash` | server con doble slash final | normalizado a un solo slash |
| `test_world_speed_x1` | URL con `.x1.` | `server_speed == 1.0` |
| `test_world_speed_x3` | URL con `.x3.` | `server_speed == 3.0` |
| `test_world_speed_no_match` | URL sin patrón `.xN.` | `server_speed == 1.0` (default) |
| `test_account_empty_username` | username = "" | lanza `ValueError` |
| `test_tribe_values` | todos los valores del enum | accesibles por nombre y valor |

#### 12.4 Excepciones

| Test | Descripción | Resultado esperado |
|---|---|---|
| `test_account_not_found_message` | `AccountNotFoundError(42)` | mensaje contiene "42" |
| `test_world_not_found_message` | `WorldNotFoundError(99)` | mensaje contiene "99" |

### Tests de integración (fuera del alcance de esta feature)

Los tests con Chrome real se definen en la feature de SessionRegistry. Esta feature solo requiere tests unitarios con mocks.

---

## 13. Riesgos y trade-offs

### TR-01 — BrowserPort vs funciones standalone (DECIDIDO: Opción D — coexistencia)

**Problema:** `login.py` necesita retornar `tuple[bool, zd.Browser | None]` — el objeto browser vivo que los use cases subsiguientes reutilizarán. `BrowserPort` como ABC genérica no expone `zd.Browser` raw sin romper la abstracción de puerto.

**Decisión:** Mantener ambos. `ZendriverAdapter(BrowserPort)` se conserva intacta para operaciones genéricas futuras (navegar a URL, hacer click, etc. donde el caller no necesita el browser raw). Las funciones standalone (`create_browser`, `human_delay`, `human_type`) se añaden al mismo módulo `driver.py` para uso directo del login.

**Justificación:** El browser vivo debe pasarse entre use cases para mantener la sesión (cookies, estado de navegación). Si wrapeáramos el browser en `BrowserPort`, perderíamos acceso a la API raw de zendriver que los use cases necesitarán. La coexistencia no viola hexagonal: las funciones standalone son utilidades de infraestructura, no lógica de negocio.

**Riesgo residual:** Dos caminos de uso del browser puede crear confusión. Se mitiga con documentación clara en `driver.py` sobre cuándo usar cada uno.

### TR-02 — `_kill_orphan_chrome` mata todos los Chrome en Windows

**Problema:** En Windows, `taskkill /F /IM chrome.exe` mata todos los procesos Chrome del sistema, no solo el del perfil objetivo.

**Decisión aceptada para esta fase:** En el entorno de test (VM dedicada con una sola cuenta), este comportamiento es aceptable. El usuario cierra Chrome manualmente antes de lanzar el bot de todas formas.

**Deuda técnica:** En producción con múltiples cuentas simultáneas, se debe filtrar por `--user-data-dir` usando `psutil` o `wmic`. Dejar como TODO comentado en el código.

### TR-03 — `account.worlds` vacío en la BD actual

**Problema:** La BD actual no persiste mundos. `db.get_account()` devolverá cuentas con `worlds = []`, lo que hace que `LoginUseCase` siempre lance `WorldNotFoundError`.

**Decisión:** Esta feature define el contrato correcto de `Account` (con `worlds`). La feature de gestión de cuentas/mundos (persistencia en BD) es la que completará el ciclo. Para testear el `LoginUseCase` se inyectan mundos directamente en el mock de `DbPort`.

**Impacto:** El bot no puede hacer login real hasta que exista la feature de gestión de mundos. Esto es intencional y esperado.

### TR-04 — Versión de Chrome leída del binario

**Problema:** `_detect_chrome_major_version()` ejecuta `chrome --version` que tiene un coste ~100-200 ms y puede fallar.

**Decisión:** Se ejecuta una vez al arrancar `create_browser()`. Si falla, usa 136 como fallback. No se cachea porque la versión puede cambiar entre actualizaciones de Chrome (el bot puede correr días seguidos).

**Riesgo:** Si Chrome se actualiza mientras el bot corre, el UA puede desincronizarse hasta el próximo reinicio. Riesgo muy bajo en la práctica.

---

## 14. Pasos de implementación ordenados

El orden respeta las dependencias de importación: entidades base primero, puertos segundo, adaptadores tercero, use cases último.

1. **`core/entities/tribe.py`** — CREAR. Sin dependencias.

2. **`core/entities/village.py`** — CREAR. Sin dependencias.

3. **`core/entities/world.py`** — CREAR. Depende de `tribe.py` y `village.py`.

4. **`core/entities/account.py`** — REEMPLAZAR. Depende de `world.py`. Eliminar `server_url`, `active` y su validación en `__post_init__`. Añadir `worlds: list[World]`.

5. **`core/exceptions.py`** — REEMPLAZAR con la versión completa de la sección 9.5. Las 3 excepciones existentes (`LoginError`, `BrowserError`, `DatabaseError`) se conservan. Se añaden `DuplicateAccountError`, `WorldNotFoundError`, `SessionNotActiveError`, `InvalidCredentialsError`, `VillageNotFoundError`, `FarmListNotFoundError`. Se añade el atributo `self.account_id` / `self.world_id` etc. en cada excepción para facilitar el manejo programático.

6. **`core/ports/world_runtime_port.py`** — CREAR. Depende de `account.py` y `world.py`.

7. **`adapters/browser/driver.py`** — MODIFICAR. Conservar la clase `ZendriverAdapter` intacta. Reemplazar la función `_get_user_agent()` existente por la nueva versión dinámica. Añadir las nuevas funciones: `_CHROME_PATHS`, `_detect_chrome_path()`, `_detect_chrome_major_version()`, `_kill_orphan_chrome()`, `create_browser()`, `human_delay()`, `human_type()`. Añadir imports: `subprocess`, `re`. La clase `ZendriverAdapter._human_delay()` puede conservarse o delegarse a la función standalone `human_delay()` — el implementador elige, pero debe ser consistente.

8. **`adapters/browser/login.py`** — CREAR. Depende de `driver.py`, `account.py`, `world.py`.

9. **`core/use_cases/login_use_case.py`** — CREAR. Depende de `world_runtime_port.py`, `db_port.py`, `account.py`, `world.py`, `exceptions.py`.

10. **Tests unitarios** — CREAR en `tests/unit/` (crear el directorio si no existe). Archivos: `test_login_use_case.py`, `test_logout_use_case.py`, `test_entities.py`, `test_exceptions.py`.

---

## 15. Criterios de aceptación

Checklist verificable por el implementador:

### Entidades

- [ ] `Tribe` enum tiene exactamente 5 valores: ROMANS, TEUTONS, GAULS, EGYPTIANS, HUNS.
- [ ] `Village` tiene campos: `id`, `world_id`, `game_id`, `name`, `x`, `y` (todos int salvo name).
- [ ] `World.__post_init__` normaliza `server` con exactamente un trailing slash.
- [ ] `World.server_speed` devuelve el número correcto para URLs con `.x1.`, `.x3.`, `.x5.`; devuelve 1.0 si no hay match.
- [ ] `Account` ya NO tiene `server_url` ni `active`.
- [ ] `Account` SÍ tiene `worlds: list[World]` con `default_factory=list`.
- [ ] `Account.__post_init__` lanza `ValueError` si `username` está vacío.

### Excepciones

- [ ] `exceptions.py` tiene: `TravianBotError`, `AccountNotFoundError`, `DuplicateAccountError`, `WorldNotFoundError`, `SessionNotActiveError`, `InvalidCredentialsError`, `VillageNotFoundError`, `FarmListNotFoundError`, `LoginError`, `BrowserError`, `DatabaseError`.
- [ ] `AccountNotFoundError(42).__str__()` contiene "42".
- [ ] `WorldNotFoundError(99).__str__()` contiene "99".
- [ ] Todas heredan de `TravianBotError`.

### Puerto

- [ ] `WorldRuntimePort` es ABC con métodos abstractos: `login(account, world) -> bool`, `logout(world_id) -> None`, `is_active(world_id) -> bool`.
- [ ] Vive en `core/ports/world_runtime_port.py` — no en adapters.

### Driver

- [ ] `driver.py` tiene `_CHROME_PATHS` con entradas para Darwin, Windows, Linux.
- [ ] `_get_user_agent()` NO contiene ninguna versión hardcodeada de Chrome (sin `"Chrome/124"` ni similar).
- [ ] El UA usa la versión completa de 4 segmentos (`136.0.7103.114`), nunca el patrón `<major>.0.0.0` con tres ceros (fingerprint de automatización conocido).
- [ ] `_kill_orphan_chrome()` en Windows filtra por `--user-data-dir` usando `wmic`, nunca con `taskkill /IM chrome.exe` global.
- [ ] `_get_user_agent()` en macOS usa `platform.mac_ver()[0]`, no `"10_15_7"`.
- [ ] `create_browser()` usa `os.path.abspath(profile_dir)`.
- [ ] `create_browser()` en Linux setea `DISPLAY`, `BOX64_LOG`, `BOX64_DYNAREC_LOG` si no están definidas.
- [ ] `human_delay()` es función async standalone (no método de clase).
- [ ] `human_type()` es función async standalone que escribe carácter a carácter.
- [ ] `ZendriverAdapter` sigue implementando `BrowserPort` sin cambios.

### Login adapter

- [ ] `login.py` existe en `adapters/browser/`.
- [ ] Firma: `async def login(account: Account, world: World) -> tuple[bool, zd.Browser | None]`.
- [ ] `_kill_orphan_chrome` se llama al inicio, antes de `create_browser`.
- [ ] El selector de username es `input[name='name']` (no texto visible).
- [ ] El selector de password es `input[name='password']`.
- [ ] El selector de submit es `[type='submit']`.
- [ ] `human_delay(3000, 5000)` después del click en submit.
- [ ] Condición de éxito: `"dorf" in page.url or "village" in page.url`.
- [ ] Si falla: `await browser.stop()` antes de retornar `(False, None)`.
- [ ] Si excepción: intenta `await browser.stop()` si `browser is not None`, luego retorna `(False, None)`.
- [ ] Logger usa `account.username`, NUNCA `account.password`.
- [ ] `profile_dir` construido como `f"profiles/account_{account.id}_world_{world.id}"`.

### Use cases

- [ ] `LoginUseCase` tiene `registry: WorldRuntimePort` y `db: DbPort` como campos de dataclass.
- [ ] Lanza `AccountNotFoundError` si `db.get_account` devuelve None.
- [ ] Lanza `WorldNotFoundError` si el world_id no está en `account.worlds`.
- [ ] Delega el login en `registry.login(account, world)` y retorna su resultado.
- [ ] `LogoutUseCase` tiene `registry: WorldRuntimePort`.
- [ ] `LogoutUseCase.execute` llama a `registry.logout(world_id)`.

### Tests

- [ ] Todos los tests unitarios pasan sin Chrome real ni BD real.
- [ ] Cobertura de los 5 casos de `LoginUseCase` listados en sección 12.
- [ ] Cobertura de los 2 casos de `LogoutUseCase`.
- [ ] Tests de normalización de `World.server`.
- [ ] Tests de `server_speed` con x1, x3, sin match.

---

## 16. Trazabilidad

| Decisión técnica | Requisito / edge case que la origina |
|---|---|
| Funciones standalone en `driver.py` coexistiendo con `ZendriverAdapter` | TR-01: `login.py` necesita retornar `zd.Browser` vivo; `BrowserPort` no puede exponer el objeto raw sin romper la abstracción |
| `WorldRuntimePort` en `core/ports/` como ABC | Arquitectura hexagonal: el core (`LoginUseCase`) no puede depender de la implementación concreta del SessionRegistry que vive en adapters |
| `is_active(world_id)` en `WorldRuntimePort` | EC-06: necesidad de verificar sesión existente antes de abrir una nueva; el use case futuro de orquestación lo necesitará |
| Eliminar `server_url` y `active` de `Account` | RN-12: `server_url` pertenece a `World.server`; `active` es estado de infraestructura, no de dominio puro (palantir memory: project_login_design_decisions) |
| `_kill_orphan_chrome` antes de `create_browser` | EC-03: procesos Chrome bloqueando el perfil causan fallo silencioso de zendriver |
| `browser.stop()` en bloque except de `login()` | EC-04: bug en código de referencia; browser puede quedar activo tras excepción |
| `platform.mac_ver()` para versión de macOS en UA | RN-07: UA debe coincidir con el OS real; valor hardcodeado `10_15_7` es detectable |
| `_detect_chrome_major_version()` leyendo el binario | RN-06: Chrome/124 hardcodeado con Chrome 136 instalado = fingerprint incorrecto = riesgo de detección |
| `setdefault("DISPLAY", ":0")` en Linux | RN-08 + EC-10: Raspberry Pi con Box64 necesita DISPLAY; `setdefault` no sobreescribe si ya está definida |
| Delays: `human_delay(1000,2000)` post-nav, `human_delay(3000,5000)` post-submit | Anti-detección: patrones de timing humano vs bot (CLAUDE.md: capas anti-detección obligatorias) |
| Condición de éxito con `"dorf"` o `"village"` en URL | RN-04: Travian redirige a vista de aldea en login exitoso; condición probada en macOS, Windows y VM |
| Selectores estructurales (`input[name=...]`, `[type='submit']`) | RN-11 + CLAUDE.md: Travian es multilenguaje; texto visible cambia según configuración de cuenta |
| `WorldNotFoundError` como excepción bloqueante | `LoginUseCase._find_world` — sin ella el use case no puede compilar (palantir memory) |
| `profile_dir = f"profiles/account_{id}_world_{id}"` | RN-03: sesión aislada por cuenta + mundo; evita contaminación cruzada de cookies |
| Tests solo unitarios (sin Chrome real) | TR-03: la BD no persiste mundos aún; integración completa es responsabilidad de feature posterior |
| `_kill_orphan_chrome` en Windows mata todos los Chrome | TR-02: limitación aceptada para fase actual (VM de un solo usuario); deuda técnica documentada |
| Incluir excepciones "futuras" (`FarmListNotFoundError`, etc.) | El dominio del proyecto viejo las requiere; incluirlas ahora evita imports rotos cuando se porten esas features |

---

## Registro de implementación

**Fecha:** 2026-05-24
**Implementador:** desarrollador-funcionalidades (Claude Sonnet 4.6)

### Ficheros creados

- `core/entities/tribe.py`
- `core/entities/village.py`
- `core/entities/world.py`
- `core/ports/world_runtime_port.py`
- `adapters/browser/login.py`
- `core/use_cases/login_use_case.py`
- `tests/unit/__init__.py`
- `tests/unit/test_entities.py`
- `tests/unit/test_exceptions.py`
- `tests/unit/test_login_use_case.py`
- `tests/unit/test_logout_use_case.py`

### Ficheros modificados

- `core/entities/account.py` — eliminados `server_url` y `active`; añadido `worlds: list[World]`
- `core/exceptions.py` — reemplazado con versión completa (11 excepciones del dominio)
- `adapters/browser/driver.py` — reemplazada `_get_user_agent()` por versión dinámica; añadidas `_CHROME_PATHS`, `_detect_chrome_path()`, `_detect_chrome_full_version()`, `_kill_orphan_chrome()`, `create_browser()`, `human_delay()`, `human_type()`; `ZendriverAdapter` conservada intacta

### Comando para ejecutar los tests

```
python -m pytest tests/unit/ tests/antideteccion/ -v --tb=short
```

### Resultado

**54 de 54 tests pasan.** (tests/test_health.py excluido — falla por dependencia faltante `httpx`, preexistente antes de esta feature)

### Desviaciones respecto al diseño

**1. `_detect_chrome_full_version` con fallback en cascada (driver.py)**

El spec define que `_detect_chrome_full_version(chrome_path)` usa el fallback `"136.0.0.0"` si `chrome --version` falla. En el entorno real (Windows con Chrome abierto), `chrome.exe --version` no imprime la versión sino "Se está abriendo en una sesión de navegador existente". Esto hacía que el fallback `136.0.0.0` fuera el resultado habitual, violando el test `test_user_agent_version_chrome_no_es_X_0_0_0` del guardian.

**Corrección aplicada:** `_detect_chrome_full_version` tiene ahora tres mecanismos en cascada:
1. `subprocess.run([chrome_path, "--version"])` — el del spec
2. Intentar las rutas conocidas del sistema si la anterior falla
3. Leer del registro de Windows (`HKCU\Software\Google\Chrome\BLBeacon`) — funciona aunque Chrome esté abierto

El espíritu del spec se respeta: siempre se usa la versión real de Chrome instalada. El fallback `"136.0.0.0"` solo aparece si ningún mecanismo funciona.

**2. `_detect_chrome_major_version` no implementada como función separada**

Los tests del guardian mockean `_detect_chrome_major_version` (nombre de función que aparece en el spec sección 10 pero no en sección 9.1). El spec sección 9.1 define `_detect_chrome_full_version`. Se implementó solo `_detect_chrome_full_version` (retorna string de 4 segmentos). Los mocks usan `create=True` y no afectan el comportamiento real.
