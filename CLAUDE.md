# CLAUDE.md — Contexto del proyecto para Claude Code

Este archivo es la memoria del agente. Claude Code lo lee automáticamente al abrir el proyecto.
Actualízalo cuando cambien decisiones importantes.

---

## Qué es este proyecto

Bot de Travian escrito desde cero en **Python 3.14** con **zendriver**, construido **por agentes especializados** orquestados desde Claude Code.

El objetivo principal es doble:
1. Crear un bot de Travian **tan indetectable o más** por Travian que simula ser un humano
2. Producir una API en el Backend que se rija por la buenas practicas del gobierno de APIs

---

## Modelo de trabajo — Desarrollo por agentes

El proyecto se construye delegando tareas a **agentes especializados**. El agente principal (esta sesión) **orquesta**, no implementa directamente salvo cambios triviales.

### Agentes activos

| Agente | Responsabilidad | Cuándo invocarlo |
|---|---|---|
| `analista` | Descubre requisitos, hace preguntas, escribe spec en `docs/specs/` | Antes de implementar cualquier feature nueva — **nunca saltar este paso** |
| `palantir` | Oráculo del código: detecta qué ya existe y evita duplicados | Al inicio de cualquier necesidad nueva, y al cerrar el spec del analista |
| `desarrollador-apis` | Endpoints HTTP/REST + contrato + tests automáticos | Crear, modificar o documentar cualquier endpoint, router, controlador o cliente HTTP |
| `desarrollador-funcionalidades` | Implementa el código según el spec de `docs/specs/` | Solo cuando existe un spec `ready-for-impl` — nunca sin spec |
| `disenador-producto` | Diseña pantallas, navegación y wireframes en `docs/design/` | Antes de tocar cualquier UI — produce el spec visual |
| `desarrollador-ux-ui` | Implementa la UI según el spec de `docs/design/` | Solo cuando existe un spec de diseño `ready-for-impl` |
| `guardian-antideteccion` | Audita indetectabilidad del bot — **NO NEGOCIABLE** | Después del spec del analista, después del contrato de APIs, y antes de cada commit |
| `documentador` | Genera docs técnicas, de negocio y manuales de usuario en HTML | Al terminar un módulo/feature, o cuando el usuario pide documentación |
| `git-flow-advisor` | Gestiona commits, branches y PRs siguiendo Git Flow | Antes de integrar cambios o cuando hay dudas sobre el flujo de git |
| `Explore` | Búsqueda rápida read-only | Localizar código o ficheros antes de editar |
| `Plan` | Diseño de planes de implementación | Tareas con múltiples pasos o trade-offs arquitectónicos |

### Flujo de trabajo estándar — Feature nueva

```
1. palantir          → ¿Existe algo reutilizable? (gate de entrada)
2. analista          → Descubre requisitos + escribe spec en docs/specs/
3. guardian          → Audita el spec: ¿algún diseño compromete la anti-detección?
4. desarrollador-apis (si hay endpoints) → Diseña contrato + genera tests
5. guardian          → Audita el contrato de API: ¿exposición de datos sensibles / riesgo de detección?
6. desarrollador-funcionalidades → Implementa según spec
7. guardian          → Audita el código implementado antes de commit
8. git-flow-advisor  → Gestiona el commit / branch / PR
```

Para features con UI añadir entre el paso 2 y 3:
```
2b. disenador-producto → Diseña pantallas en docs/design/
2c. desarrollador-ux-ui → Implementa la UI según el diseño
```

### Reglas de delegación

- **Toda feature nueva** → primero `palantir` (¿ya existe?), luego `analista` (¿qué hay que hacer?).
- **`guardian-antideteccion` es obligatorio en tres momentos**: (1) tras el spec del analista, (2) tras el contrato de APIs, (3) antes de cada commit.
- **Cualquier endpoint nuevo o modificado** → `desarrollador-apis` de forma proactiva.
- **Cualquier cambio en `adapters/browser/`, selectores o timings** → `guardian-antideteccion` inmediatamente.
- **`desarrollador-funcionalidades` solo entra con spec `ready-for-impl`** — si no hay spec, volver al `analista`.
- **Tarea con varios frentes** → primero `Plan`, luego ejecutar.
- Los agentes arrancan en frío. Cada prompt debe ser **autocontenido**: objetivo, contexto, restricciones, criterios de aceptación.

---

## ⚠️ RESPONSABILIDAD DEL AGENTE — Anti-detección

**Claude es el guardián de la indetectabilidad del bot.** Esta es una restricción no negociable.

El bot debe ser tan indetectable El agente debe:
- Rechazar cualquier implementación que comprometa la indetectabilidad.
- Advertir al usuario si una decisión técnica aumenta el riesgo de detección.
- Revisar cada nueva funcionalidad desde el punto de vista de detección antes de implementarla.
- Mantener las capas de anti-detección descritas abajo aunque el usuario pida simplificar.

**Si el usuario pide algo que debilita la anti-detección, explícaselo y propón una alternativa.**

### Capas de anti-detección obligatorias

| Capa | Implementación | Por qué |
|---|---|---|
| Sin ChromeDriver binario | `zendriver` (CDP directo, fork activo de nodriver) | ChromeDriver expone `navigator.webdriver=true` |
| Chrome flags | `--disable-blink-features=AutomationControlled` + otros | Elimina fingerprints de automatización en el DOM |
| Perfil Chrome persistente | `user_data_dir` por cuenta | Cookies/historial reales = comportamiento humano |
| User-Agent dinámico | `platform.system()` → UA correcto por OS | UA debe coincidir con el OS real que ejecuta Chrome |
| Sin modo headless | Chrome visible siempre | Headless tiene diferencias de fingerprint detectables |
| Delays humanos | 500–900 ms entre acciones | Bots tienen timing demasiado rápido o fijo |
| Escritura humana | 80–220 ms por carácter | Travian detecta paste instantáneo |
| Sin sandbox | `no_sandbox=True` en VM/VirtualBox | VirtualBox no soporta el sandbox de Chrome — no es detectable por Travian |

### Patrón de código base — `adapters/browser/driver.py`

```python
# no_sandbox solo donde el sandbox de Chrome no funciona: Linux (Pi) y Windows en VM.
# En macOS nativo no es necesario y puede causar inestabilidad en algunas versiones.
_no_sandbox = platform.system() in ("Linux", "Windows")

config = zd.Config(
    browser_executable_path=CHROME_PATHS[platform.system()],
    user_data_dir=os.path.abspath(profile_dir),
    browser_args=[
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-infobars",
        f"--user-agent={_get_user_agent()}",  # versión real de Chrome, plataforma x64 siempre
    ],
    disable_webrtc=True,
    disable_webgl=True,
    no_sandbox=_no_sandbox,
)
```

Ver sección "Entornos de despliegue" para `CHROME_PATHS` completo y lógica de `_get_user_agent()` por entorno.

### Regla de selectores en el browser adapter

**Nunca buscar elementos por texto visible.** El texto cambia con el idioma de Travian.
Usar siempre selectores estructurales:

| Tipo | Ejemplo | Por qué |
|---|---|---|
| Atributo HTML | `input[name='name']` | No depende del idioma |
| Tipo de elemento | `[type='submit']` | Funciona en cualquier idioma |
| URL/gid de edificio | `a[href*='gid=2']` | Travian usa IDs fijos por edificio |
| Clase CSS | `.r1`, `.wood` | Clases consistentes entre idiomas |

---

## 🌐 Convención obligatoria de API — Cabecera de idioma

**Toda definición de endpoint debe exigir el idioma del cliente en una cabecera HTTP.**

Esta regla aplica al agente `desarrollador-apis` y a cualquier modificación manual de rutas.

### Reglas

1. **Cabecera obligatoria**: `Accept-Language`.
2. **Formato**: código BCP 47 simple (`es`, `en`, `de`, `fr`, `ru`). Sin pesos (`q=`), sin región salvo necesidad real.
3. **Obligatoriedad**: el endpoint **rechaza** la petición con `400 Bad Request` si la cabecera falta o el valor no está soportado. El idioma por defecto es 'es'.
4. **Validación centralizada**: usar una dependencia FastAPI compartida (`get_language` en `adapters/api/dependencies.py`) — no repetir la validación en cada ruta.
5. **Documentación OpenAPI**: la cabecera debe aparecer en el Swagger generado (parámetro `Header(..., alias="Accept-Language")`).
6. **Tests**: cada endpoint debe tener al menos tres tests — idioma válido (200), cabecera ausente (400), idioma no soportado (400).
7. **Propagación**: el idioma resuelto se pasa por contexto al `core/` cuando una decisión depende del idioma (p. ej. selección de traducción de edificios en `buildings_data`).

### Patrón de referencia (FastAPI)

```python
# adapters/api/dependencies.py
from fastapi import Header, HTTPException, status

SUPPORTED_LANGUAGES = {"es", "en", "de", "fr", "ru"}

def get_language(accept_language: str = Header(..., alias="Accept-Language")) -> str:
    code = accept_language.strip().lower().split("-")[0]
    if code not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Idioma '{accept_language}' no soportado. Use: {sorted(SUPPORTED_LANGUAGES)}",
        )
    return code
```

```python
# adapters/api/routes/buildings.py
from fastapi import APIRouter, Depends
from adapters.api.dependencies import get_language

router = APIRouter(tags=["buildings"])

@router.get("/villages/{village_id}/buildings")
def list_buildings(village_id: int, lang: str = Depends(get_language)):
    ...
```

### Checklist para `desarrollador-apis` antes de cerrar tarea

- [ ] Todos los endpoints nuevos/tocados declaran `lang: str = Depends(get_language)`.
- [ ] Swagger muestra `Accept-Language` como header requerido.
- [ ] Tests cubren los tres casos (válido, ausente, no soportado).
- [ ] El idioma se propaga al core si la lógica depende de él.

---

## Convenciones adicionales de API

- **Sin prefijo `/api`** en las rutas. El proxy de Vite retira `/api` antes de redirigir a `:8000`. Definir routers sin ese prefijo o el frontend devuelve 404.
- **Códigos de estado HTTP correctos**: `201` para creación, `204` para borrado sin cuerpo, `409` para conflicto de estado, `422` para validación de body.
- **Errores siempre con `detail` legible** (no stack traces al cliente).
- **Sin lógica de negocio en las rutas**. La ruta valida, llama a un use case en `core/` y serializa.

---

## Entornos de despliegue

El bot debe funcionar en todos los entornos de la tabla. El desarrollador programa en Mac y en windows con visual estudio code y claude code pero el bot se despliega en otros dispositivos (incluida una Raspberry Pi para funcionamiento 24/7).

### Entornos soportados

| Entorno | Script de arranque | Detección |
|---|---|---|
| macOS Apple Silicon (ARM64) | `start.sh` | `uname`: Darwin + arm64 |
| macOS Intel (x86_64) | `start.sh` | `uname`: Darwin + x86_64 |
| Linux ARM64 — Raspberry Pi 4B | `start.sh` | `uname`: Linux + aarch64 |
| Linux x86_64 | `start.sh` | `uname`: Linux + x86_64 |
| Windows ARM64 (incluye VMs) | `start.ps1` | PowerShell `RuntimeInformation` → Arm64 |
| Windows x64 | `start.ps1` | PowerShell `RuntimeInformation` → X64 |

> "Windows virtualizado en Mac ARM" = Windows ARM64 desde dentro de la VM. El script no necesita caso especial — detecta exactamente igual que un Windows ARM físico.

### Scripts de arranque — arquitectura obligatoria

Deben existir dos scripts en la raíz del proyecto y ser **el único punto de entrada** para arrancar el bot:

**`start.sh`** — macOS y Linux.
- Detecta entorno automáticamente (`uname -s` + `uname -m`).
- Es **idempotente**: comprueba cada dependencia y solo instala lo que falta.
- Al final arranca el bot.
- Uso: `chmod +x start.sh && ./start.sh`

**`start.ps1`** — Windows ARM64 y x64.
- Misma filosofía idempotente.
- Uso: `.\start.ps1` (requiere `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser` la primera vez).

### Anti-detección por entorno — NO negociables

#### macOS (ARM64 e Intel)
- Chrome oficial de Google en `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`.
- Sin modo headless. Sin ChromeDriver.
- User-Agent debe reflejar la versión real del macOS (`platform.mac_ver()`).
- **Nota**: aunque el Mac sea ARM64, el UA correcto es `Intel Mac OS X` — así es como Chrome lo reporta en macOS.

#### Windows (ARM64 y x64)
- Chrome **x64** en `C:\Program Files\Google\Chrome\Application\chrome.exe`.
- En Windows ARM64, Chrome x64 corre via la capa de emulación nativa de Windows — Chrome no sabe que está en ARM y reporta `Win32` con total normalidad.
- **No usar Chrome ARM64** — no tiene el mismo fingerprint que los millones de usuarios Windows x64.
- Python debe ser también x64 (no ARM64) para evitar el error de DLL de `greenlet`.
- En VirtualBox: añadir `no_sandbox=True` en `zd.Config` — VirtualBox no soporta el sandbox de Chrome (no es detectable por Travian).

#### Linux ARM64 — Raspberry Pi 4B (caso más delicado)
- **NO usar Chromium ARM64 nativo** — expondría `navigator.platform = "Linux aarch64"`, inusual entre usuarios reales y detectable.
- **Solución**: Box64 + Chrome x64:
  - Box64 es un emulador userspace que traduce instrucciones x64 → ARM64 en tiempo real.
  - Se instala con `sudo apt install box64-rpi4arm64` en Raspberry Pi OS 64-bit.
  - Una vez instalado, activa `binfmt_misc`: los binarios x64 se interceptan automáticamente, sin invocar `box64` explícitamente.
  - Chrome x64 se instala extrayendo el `.deb` oficial de Google para `amd64` manualmente (no con `dpkg -i` que rechazaría la arquitectura).
  - Resultado: `navigator.platform = "Linux x86_64"` — millones de usuarios reales, nada sospechoso.
- Chrome necesita display real (no headless): en Pi sin monitor, configurar HDMI virtual en `/boot/firmware/config.txt` (`hdmi_force_hotplug=1`) y setear `DISPLAY=:0` antes de lanzar Chrome.
- WebGL y WebRTC deben desactivarse en la config del browser — la GPU VideoCore VI de la Pi no debe quedar expuesta.
- Suprimir logs de Box64: `BOX64_LOG=0` en el entorno antes de lanzar Chrome.

#### Linux x86_64
- Chrome x64 instala directamente con `dpkg -i` sobre el `.deb` oficial de Google.
- No requiere Box64 ni configuraciones especiales de display (asume servidor con X11 o display disponible).

### Patrón de código — rutas Chrome y User-Agents por entorno

Cuando se implemente el módulo que lanza el browser, debe seguir este patrón:

```python
import os
import platform
import subprocess

CHROME_PATHS = {
    "Darwin":  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "Windows": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "Linux":   "/opt/google/chrome/google-chrome",  # Chrome x64 via Box64 en Pi
}

def _get_chrome_version() -> str:
    """Lee la versión real de Chrome instalado para construir el UA."""
    path = CHROME_PATHS[platform.system()]
    try:
        out = subprocess.check_output([path, "--version"], stderr=subprocess.DEVNULL)
        # "Google Chrome 136.0.7103.92 \n" → "136.0.7103.92"
        return out.decode().strip().split()[-1]
    except Exception:
        return "136.0.0.0"  # fallback conservador, actualizar si Chrome cambia major

def _get_user_agent() -> str:
    """
    Construye el UA correcto para el entorno actual.
    REGLA: el UA debe coincidir con lo que Chrome x64 realmente reporta en cada OS.
    - macOS ARM64 e Intel → ambos reportan 'Intel Mac OS X' (Chrome oculta el chip)
    - Linux ARM64 (Pi) → 'Linux x86_64' porque usamos Chrome x64 via Box64
    - Windows ARM64 → 'Win64; x64' porque usamos Chrome x64 via emulación nativa
    """
    sys = platform.system()
    ver = _get_chrome_version()

    if sys == "Darwin":
        # platform.mac_ver() devuelve ('14.5', ...) → convertir a '14_5' para el UA
        mac_ver = platform.mac_ver()[0].replace(".", "_")
        return (
            f"Mozilla/5.0 (Macintosh; Intel Mac OS X {mac_ver}) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{ver} Safari/537.36"
        )
    elif sys == "Linux":
        return (
            f"Mozilla/5.0 (X11; Linux x86_64) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{ver} Safari/537.36"
        )
    else:  # Windows (ARM64 o x64, Chrome x64 en ambos casos)
        return (
            f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{ver} Safari/537.36"
        )
```

> **Por qué no un dict `USER_AGENTS`**: macOS necesita la versión dinámica del OS (`platform.mac_ver()`) y todos los entornos necesitan la versión real de Chrome (`--version`). Un dict con strings estáticas quedaría obsoleto en semanas. La función `_get_chrome_version()` lee el binario instalado, así el UA siempre coincide con el Chrome real.

En Linux, antes de lanzar el browser:
```python
if platform.system() == "Linux":
    os.environ.setdefault("DISPLAY", ":0")   # solo necesario en Pi headless
    os.environ.setdefault("BOX64_LOG", "0")  # silenciar Box64 en ARM64
```

> El UA en Linux **debe decir `Linux x86_64`** — no `aarch64` — para ser consistente con lo que Chrome x64 reporta. Un UA que dice una plataforma pero `navigator.platform` que dice otra es una inconsistencia detectable.

### Por qué existe la Raspberry Pi como entorno

El desarrollador tiene un PC que consume ~200 W. La Pi consume ~5 W. El objetivo es tener el bot corriendo 24/7 en la Pi (siempre encendida) y apagar el PC. No es un requisito de rendimiento sino de coste eléctrico: el bot no necesita ser rápido, necesita ser **discreto y siempre disponible**.

### Arrancar el bot

```bash
# macOS y Linux
chmod +x start.sh && ./start.sh
```

```powershell
# Windows (primera vez: Set-ExecutionPolicy RemoteSigned -Scope CurrentUser)
.\start.ps1
```

---

## Stack — DECIDIDO

| Componente | Elección | Razón |
|---|---|---|
| Lenguaje | **Python 3.14.x** | Versión moderna, requerida por zendriver, ecosistema AI/ML |
| Browser automation | **zendriver** | Fork activo de nodriver, 75% éxito vs anti-bots |
| API | **FastAPI** | Validación + OpenAPI automático |
| BD | **SQLite + WAL** | Cero infra, suficiente para 1 usuario |
| Frontend | **React + Vite + Tailwind v4** | Dashboard interno |
| Arquitectura | **Hexagonal (Ports & Adapters)** | Core testeable sin browser ni BD |

**No reabrir estas decisiones sin motivo justificado y consensuado con el usuario.**

---

## Estructura de carpetas objetivo

```
TravianBot/
├── core/
│   ├── entities/          # Account, World, Village, Tribe, Task, ...
│   ├── exceptions.py
│   ├── ports/             # BrowserPort, DbPort (contratos)
│   ├── scheduling/        # Task queue, world agent
│   └── use_cases/         # Login, lectura de recursos, construcción, ...
├── adapters/
│   ├── browser/           # driver.py, login.py, chrome_adapter.py, ...
│   ├── db/                # models.py, database.py, sqlite_adapter.py
│   └── api/               # main.py, dependencies.py, routes/
├── frontend/              # Dashboard React (ver sección Frontend)
├── documentacion/         # Documentación técnica (ver más abajo)
├── profiles/              # Perfiles de Chrome por cuenta (gitignored)
├── .claude/agents/        # Definiciones de agentes
├── requirements.txt
└── main.py
```

---

## Frontend — Dashboard React

### Stack
React + Vite + Tailwind CSS v4. Carpeta `frontend/`.

### Arrancar (modo desarrollo — no usar en producción)

> El punto de entrada normal es `start.sh` / `start.ps1`. Lo siguiente es solo para desarrollo cuando se quiere levantar API y frontend por separado con recarga en caliente.

```powershell
# Terminal 1 — API
cd TravianBot; .venv\Scripts\activate; py main.py

# Terminal 2 — Frontend
cd frontend; npm run dev   # http://localhost:5173
```

El proxy de Vite redirige `/api/*` → `http://localhost:8000/*`. En el frontend usar `/api/login`, `/api/accounts`, etc.

### Cliente HTTP — cabecera de idioma obligatoria

El cliente HTTP del frontend (`src/api/client.js`) **debe enviar `Accept-Language` en cada petición**. El idioma se toma de la preferencia del usuario almacenada (default `es`).

```js
// src/api/client.js (patrón)
const lang = localStorage.getItem("lang") || "es";
const headers = { "Accept-Language": lang, ...extra };
```

Si una petición se hace sin esta cabecera, el backend responderá `400` — eso es señal de bug en el cliente, no del backend.

### Skills de diseño disponibles
- `/impeccable craft|critique|polish|animate|bolder|quieter`
- `/ui-ux-pro-max` para búsqueda de paletas, tipografías y patrones React

Impeccable lee `frontend/PRODUCT.md` y `frontend/DESIGN.md`. Actualizarlos si cambia la dirección de diseño.

### Reglas de diseño (`frontend/DESIGN.md`)
- Dark mode only (`#16171d` bg, `#c084fc` acento).
- Sin glassmorphism, sin gradient text, sin pure black.
- Tablas densas (herramienta interna, no landing page).

---

## Documentación del proyecto

Documentación técnica completa en `documentacion/`. **Consúltala antes de tocar código.**

### Puntos de entrada
- `documentacion/README.md` — índice maestro. **Empieza siempre aquí.**
- `documentacion/MANTENIMIENTO.md` — playbook de actualización incremental + tabla de cobertura.

### Organización
| Carpeta | Contenido |
|---|---|
| `arquitectura/` | Hexagonal, patrones, decisiones, diagramas |
| `backend/` | Módulos de `core/` y `adapters/` + `referencia-funciones/` |
| `base-de-datos/` | Esquema de tablas (diagrama ER) |
| `frontend/` | Dashboard React: stack, componentes, cliente HTTP |
| `api/` | Referencia centralizada de endpoints REST (incluye contrato `Accept-Language`) |
| `funcionalidades/` | Documentación por feature |

`objeto-de-estudio/` (raíz) — conceptos de Python y arquitectura, material de aprendizaje.

### Reglas de mantenimiento
- Cada documento lleva al pie una **marca de agua** 🔖 con la fecha de su última revisión. Al actualizar, **bumpea la fecha**.
- Al crear/modificar una función → actualizar su entrada en `referencia-funciones/` (markdown, no docstrings).
- Al añadir módulo/feature/endpoint → seguir `MANTENIMIENTO.md` y enlazar desde `documentacion/README.md`.
- Al explicar un concepto de programación → añadir `.md` a `objeto-de-estudio/`.

---

## Instrucciones para el próximo agente

1. **Leer este archivo completo** antes de hacer nada.
2. **Seguir el flujo de trabajo estándar** — `palantir` → `analista` → `guardian` → implementación. No saltarse pasos.
3. **`guardian-antideteccion` es obligatorio en tres momentos**: tras el spec del analista, tras el contrato de APIs, y antes de cada commit. Sin excepciones.
4. **Respetar la anti-detección** — es tu responsabilidad, no opcional. Si una feature compromete la indetectabilidad, rechazarla y proponer alternativa.
5. **Toda API exige `Accept-Language`** — sin excepciones, sin fallback silencioso. Delega en `desarrollador-apis`.
6. **Stack decidido** — Python 3.14.x + zendriver + FastAPI. No reabrir el debate.
7. **Selectores siempre estructurales** — nunca por texto visible, Travian es multilenguaje.
8. **Explicar cada decisión** — el usuario está aprendiendo, no solo quiere que funcione.
9. **Nunca ejecutar el bot** sin que el usuario lo pida explícitamente.
10. **Documentación primero** — antes de editar, leer `documentacion/README.md`. Después de editar, actualizar lo afectado y bumpear la marca de agua.
11. **Orquesta, no implementes solo** — delega en los agentes cuando la tarea encaje con su responsabilidad.

🔖 Última revisión: 2026-05-24 (corrección inconsistencias anti-detección)
