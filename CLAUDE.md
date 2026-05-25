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
| `guardian-antideteccion` | Audita indetectabilidad del bot — **NO NEGOCIABLE cuando aplica** | **Solo cuando hay funciones o lógica que impactan el browser o la interacción con la web de Travian** (`adapters/browser/`, selectores, timings, escritura humana, navegación, peticiones a Travian) |
| `documentador` | Genera docs técnicas, de negocio y manuales de usuario en HTML | Al terminar un módulo/feature, o cuando el usuario pide documentación |
| `git-flow-advisor` | Gestiona commits, branches y PRs siguiendo Git Flow | Antes de integrar cambios o cuando hay dudas sobre el flujo de git |
| `Explore` | Búsqueda rápida read-only | Localizar código o ficheros antes de editar |
| `Plan` | Diseño de planes de implementación | Tareas con múltiples pasos o trade-offs arquitectónicos |

### Flujo de trabajo estándar — Feature nueva

```
1. palantir          → ¿Existe algo reutilizable? (gate de entrada)
2. analista          → Descubre requisitos + escribe spec en docs/specs/
3. guardian          → SOLO si el spec toca el browser o la interacción con Travian: ¿algún diseño compromete la anti-detección?
4. desarrollador-apis (si hay endpoints) → Diseña contrato + genera tests
5. guardian          → SOLO si la API expone datos del browser / sesión de Travian o influye en la interacción: ¿riesgo de detección?
6. desarrollador-funcionalidades → Implementa según spec
7. guardian          → SOLO si el código implementado toca el browser o la interacción con Travian: audita antes de commit
8. *** PRUEBA MANUAL DEL USUARIO *** → El usuario prueba en el entorno real (Chrome real, Travian real)
9. git-flow-advisor  → Gestiona el commit / branch / PR — SOLO si el usuario da el OK
```

> Los pasos 3, 5 y 7 son **condicionales**: el `guardian-antideteccion` solo entra cuando el trabajo incluye funciones o lógica que impactan el browser o la interacción con la web de Travian. Para cambios puramente de backend/API/BD/frontend que no tocan esa interacción, se omiten.

**El paso 8 es un gate humano no salteable.** Ningún agente puede darlo por aprobado.
El usuario debe confirmar explícitamente "OK, funciona" antes de que git-flow-advisor haga cualquier commit.

Para features con UI añadir entre el paso 2 y 3:
```
2b. disenador-producto → Diseña pantallas en docs/design/
2c. desarrollador-ux-ui → Implementa la UI según el diseño
```

### Reglas de delegación

- **Toda feature nueva** → primero `palantir` (¿ya existe?), luego `analista` (¿qué hay que hacer?).
- **`guardian-antideteccion` entra solo cuando hay funciones o lógica que impactan el browser o la interacción con la web de Travian** (`adapters/browser/`, selectores, timings, escritura humana, navegación, peticiones a Travian). Cuando aplica, es obligatorio en los momentos relevantes del flujo (tras el spec, tras el contrato de APIs si expone esa interacción, y antes del commit). Para cambios puramente de backend/API/BD/frontend que no tocan esa interacción, **no se invoca**.
- **Cualquier endpoint nuevo o modificado** → `desarrollador-apis` de forma proactiva.
- **Cualquier cambio en `adapters/browser/`, selectores o timings** → `guardian-antideteccion` inmediatamente (esto sí es siempre).
- **`desarrollador-funcionalidades` solo entra con spec `ready-for-impl`** — si no hay spec, volver al `analista`.
- **`git-flow-advisor` solo entra con OK explícito del usuario** — nunca commitear sin confirmación manual.
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

## 🌐 Convención de API — Selección de idioma

`Accept-Language` y/o el parámetro de query `?lang=` controlan la localización en todos los endpoints que devuelven texto localizado. Esta regla aplica al agente `desarrollador-apis` y a cualquier modificación manual de rutas.

### Idiomas soportados — única fuente de verdad

**`SUPPORTED_LANGUAGES`** vive en `core/i18n/languages.py` y son exactamente los **25 códigos** que existen como claves en `core/i18n/catalog/base/troops.json` (generado por kirilloid):

`ar, bg, cs, da, de, el, en, es, fa, fr, he, hu, it, ja, lt, lv, nl, pl, pt, rs, ru, sl, sv, tr, uk`

Son códigos de kirilloid, NO BCP-47 estricto (p.ej. `rs` = serbio). Se mantienen tal cual para que todo código soportado resuelva directamente a datos en el catálogo. Cualquier código fuera de este conjunto → `400`.

### Tres dependencias de idioma disponibles

| Dependencia | Comportamiento | Cuándo usar |
|---|---|---|
| `get_language` | **Obligatoria**: `400` si `Accept-Language` falta O el idioma no está en los 25 | Endpoints que SIEMPRE devuelven un solo idioma (p.ej. `/catalog/buildings`) |
| `get_language_optional` | **Opcional solo por header**: `None` si falta → todos los idiomas; código validado si soportado; `400` si presente y no soportado | Uso interno / endpoints legacy sin `?lang=` |
| `resolve_language` | **Override + fallback**: prioridad `?lang=` > `Accept-Language` > `None` (todos). `400` si cualquier valor presente es inválido | Endpoints de catálogo con campo `language` que además ofrecen `?lang=` como override |

Todas viven en `adapters/api/dependencies.py`.

### Precedencia en endpoints que usan `resolve_language`

**Explícito gana a implícito**: `?lang=<código>` > `Accept-Language` > (ninguno → todos los idiomas).

Los endpoints `GET /catalog/troops/{tribe}` y `GET /catalog/troops/{tribe}/stats` usan `resolve_language`:

| Entrada | Respuesta |
|---|---|
| `?lang=en` (válido) | `200` — `language` contiene solo ese idioma (con fallback granular a `es`) |
| `?lang=xx` (inválido) | `400` — código no soportado |
| `Accept-Language: it` + sin `?lang=` | `200` — `language` contiene `it` (ahora válido en los 25) |
| `Accept-Language: zh` + sin `?lang=` | `400` — código no soportado |
| `?lang=en` + `Accept-Language: es` | `200` — gana `?lang=en`, language con `en` |
| Nada (sin header, sin `?lang=`) | `200` — `language` con todos los 25 idiomas del catálogo |

### Caché: `Vary: Accept-Language`

Los endpoints con `resolve_language` añaden `Vary: Accept-Language` en la respuesta, para que proxies/CDN cacheen correctamente por variante de idioma. Con `?lang=` la variación ya queda en la URL y `Vary` es redundante pero inofensivo.

### Reglas comunes

1. **Formato**: código simple en minúsculas (`es`, `it`, `ja`). Strip + lower + quitar región (`en-US` → `en`).
2. **`SUPPORTED_LANGUAGES` = los 25 de `core/i18n/languages.py`.** Un idioma fuera → `400`. No hardcodear otro conjunto en ningún router ni test.
3. **Validación centralizada**: siempre usar las dependencias de `adapters/api/dependencies.py`, nunca replicar la lógica en handlers.
4. **Documentación OpenAPI**: tanto `Accept-Language` (header) como `lang` (query) deben aparecer en Swagger.
5. **Propagación**: el idioma resuelto (o `None`) se pasa al `core/` cuando la lógica depende de él.

### Patrón de referencia (FastAPI)

```python
# adapters/api/dependencies.py  (ya implementado)

def get_language(accept_language: str | None = Header(default=None, alias="Accept-Language")) -> str:
    """Obligatoria por header: 400 si falta o idioma no soportado."""
    ...

def resolve_language(
    lang: str | None = Query(default=None, description="Override explícito; gana al header."),
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
) -> str | None:
    """Precedencia: ?lang= > Accept-Language > None (todos). 400 si presente e inválido."""
    ...
```

```python
# Endpoint con idioma obligatorio (p.ej. /catalog/buildings)
@router.get("/catalog/buildings")
def get_buildings(lang: str = Depends(get_language), ...):
    ...

# Endpoint con ?lang= override + Accept-Language (p.ej. /catalog/troops/{tribe})
@router.get("/catalog/troops/{tribe}")
def get_troops(tribe: Tribe, response: Response, lang: str | None = Depends(resolve_language), ...):
    response.headers["Vary"] = "Accept-Language"
    if lang is None:
        items = translation_port.get_troop_all_langs_by_tribe(tribe)   # todos los idiomas
    else:
        items = translation_port.get_troop_names_by_tribe(tribe, lang) # un idioma + fallback 'es'
    ...
```

### Checklist para `desarrollador-apis` antes de cerrar tarea

- [ ] Endpoints que devuelven texto localizado con override de query usan `resolve_language`; los que solo usan header obligatorio usan `get_language`.
- [ ] Swagger muestra tanto `Accept-Language` (header) como `lang` (query, si aplica).
- [ ] Tests de catálogo con `resolve_language` cubren: `?lang=` válido; `?lang=` inválido → `400`; solo header válido; header inválido → `400`; precedencia `?lang=` gana al header; sin nada → todos los idiomas; `Vary: Accept-Language` presente.
- [ ] Tests de `get_language` obligatoria: header ausente → `400`; no soportado → `400`; válido → `200`.
- [ ] `SUPPORTED_LANGUAGES` NO está hardcodeado en los tests: usar un código como `zh` o `xx` que definitivamente no está en los 25, no `it` o `ja` (que ahora son válidos).
- [ ] El idioma resuelto (o `None`) se propaga al core si la lógica depende de él.

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

## Comunicación obligatoria al lanzar agentes

El usuario usa la extensión de VSCode (no el CLI). Los outputs de Bash/PowerShell no son visibles.

**Antes de lanzar cualquier agente** con la herramienta `Agent`, escribir en el texto de respuesta:
```
**`>> NOMBRE-AGENTE`** — descripción de la tarea que se le delega
```

**Al recibir el resultado**, escribir:
```
**`OK NOMBRE-AGENTE`** — resumen del resultado en una línea
```

**Si el agente se bloquea o devuelve un gap**:
```
**`!! NOMBRE-AGENTE`** — motivo del bloqueo
```

Esto es la única forma de que el usuario sepa qué agente está activo en cada momento.

---

## Instrucciones para el próximo agente

1. **Leer este archivo completo** antes de hacer nada.
2. **Seguir el flujo de trabajo estándar** — `palantir` → `analista` → (`guardian` si aplica) → implementación. No saltarse pasos.
3. **`guardian-antideteccion` entra solo cuando el trabajo incluye funciones o lógica que impactan el browser o la interacción con la web de Travian** (`adapters/browser/`, selectores, timings, escritura humana, navegación, peticiones a Travian). Cuando aplica, es obligatorio en los momentos relevantes (tras el spec, tras el contrato de APIs si expone esa interacción, antes del commit) y no es negociable. Para cambios puramente de backend/API/BD/frontend que no tocan esa interacción, **no se invoca**.
4. **Prueba manual del usuario antes de commitear** — el usuario prueba en entorno real y da OK explícito. Ningún agente puede sustituir esta validación.
5. **Respetar la anti-detección** — es tu responsabilidad, no opcional. Si una feature compromete la indetectabilidad, rechazarla y proponer alternativa.
6. **Toda API exige `Accept-Language`** — sin excepciones, sin fallback silencioso. Delega en `desarrollador-apis`.
7. **Stack decidido** — Python 3.14.x + zendriver + FastAPI. No reabrir el debate.
8. **Selectores siempre estructurales** — nunca por texto visible, Travian es multilenguaje.
9. **Explicar cada decisión** — el usuario está aprendiendo, no solo quiere que funcione.
10. **Nunca ejecutar el bot** sin que el usuario lo pida explícitamente.
11. **Documentación primero** — antes de editar, leer `documentacion/README.md`. Después de editar, actualizar lo afectado y bumpear la marca de agua.
12. **Orquesta, no implementes solo** — delega en los agentes cuando la tarea encaje con su responsabilidad.

🔖 Última revisión: 2026-05-25 (gobernanza de idioma: SUPPORTED_LANGUAGES amplía a 25; resolve_language con precedencia ?lang= > Accept-Language > todos; Vary: Accept-Language en endpoints de catálogo de tropas)
