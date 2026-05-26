# Frontend — Dashboard React de gestión de cuentas y mundos

Módulo documentado: `frontend/`
Diseño de referencia: [`docs/design/gestion-cuentas-mundos.md`](../../docs/design/gestion-cuentas-mundos.md)
Spec de diseño visual: [`frontend/DESIGN.md`](../../frontend/DESIGN.md)
Documento de negocio: [`../funcionalidades/cuentas-mundos.md`](../funcionalidades/cuentas-mundos.md)
API consumida: [`../api/cuentas-mundos.md`](../api/cuentas-mundos.md), [`../api/sesion.md`](../api/sesion.md)

---

## Stack y scaffolding

| Componente | Elección | Razón |
|---|---|---|
| Bundler | Vite | HMR rápido, proxy nativo para `/api` |
| Framework UI | React 18 | Ecosistema maduro, compatible con la arquitectura del proyecto |
| Estilos | Tailwind CSS v4 | Clases utilitarias + tokens CSS propios (sin conflicto) |
| Router | React Router v6 | Rutas declarativas con `Routes`/`Route` |
| Iconos | Lucide React (sidebar) + SVG inline (páginas) | Sin bundle extra en páginas; Lucide para iconos del shell |
| i18n | Sistema propio (Context + catálogo JS) | 25 idiomas, sin dependencia externa, RTL nativo |
| HTTP | Módulo propio `src/api/client.js` | `Accept-Language` obligatorio en cada petición |

El punto de entrada de desarrollo es `npm run dev` en `frontend/`. El proxy de Vite redirige `/api/*` → `http://localhost:8000/*` (sin el prefijo `/api`). Para producción el frontend se sirve estáticamente junto a la API FastAPI.

---

## Estructura de carpetas relevante

```
frontend/
├── src/
│   ├── App.jsx                         — raíz, árbol de rutas
│   ├── main.jsx                        — punto de entrada React
│   ├── styles/
│   │   ├── tokens.css                  — tokens de diseño (colores, radios, fuentes, motion)
│   │   └── app.css                     — reset global, utilidades base
│   ├── api/
│   │   └── client.js                   — cliente HTTP (Accept-Language, ApiError)
│   ├── i18n/
│   │   ├── index.jsx                   — I18nProvider, useI18n, translate()
│   │   ├── languages.js                — lista de 25 idiomas con código, nombre y RTL
│   │   └── catalog/
│   │       ├── index.js                — importa y exporta los 25 catálogos
│   │       ├── es.js                   — 163 claves, idioma base (revisado a mano)
│   │       ├── en.js                   — revisado a mano
│   │       └── [ar bg cs da de el fa fr he hu it ja lt lv nl pl pt rs ru sl sv tr uk].js
│   ├── components/
│   │   ├── layout/
│   │   │   ├── ManagementShell.jsx     — contenedor modo Gestión (Topbar + Sidebar + Outlet)
│   │   │   ├── Topbar.jsx              — wordmark + ThemeToggle + LangPicker
│   │   │   └── Sidebar.jsx             — navegación vertical (solo "Cuentas" activo)
│   │   └── ui/
│   │       ├── ThemeToggle.jsx         — toggle claro/oscuro (localStorage + data-theme)
│   │       ├── LangPicker.jsx          — selector de idioma por endónimo (searchable dropdown)
│   │       ├── WizardModal.jsx         — S3: wizard alta de cuenta (2 pasos)
│   │       ├── EditAccountModal.jsx    — S5: editar cuenta (email, username, password opcional)
│   │       ├── AddWorldModal.jsx       — S6: añadir mundo (server URL + tribu)
│   │       ├── ConfirmDeleteModal.jsx  — S7/S8: confirmación destructiva genérica
│   │       └── uiUtils.jsx             — parseServerUrl, BadgeSpinner, showToast
│   └── pages/
│       ├── AccountsListPage.jsx        — S2: lista de cuentas
│       ├── NewAccountPage.jsx          — S3: renderiza AccountsListPage + WizardModal superpuesto
│       ├── AccountDetailPage.jsx       — S4: detalle de cuenta + mundos + sesión
│       └── WorldSpacePage.jsx          — S9: espacio del mundo (topbar mínima; contenido Etapa 2)
```

---

## Sistema de tokens de diseño (`src/styles/tokens.css`)

Todos los colores, radios, tipografías y duraciones del sistema están definidos como variables CSS en `tokens.css`. Ningún componente hardcodea valores hexadecimales.

### Tokens principales

| Variable | Modo claro | Modo oscuro | Uso |
|---|---|---|---|
| `--bg` | `#F5F5F7` | `#1D1D1F` | Fondo de página |
| `--surface` | `#FFFFFF` | `#2C2C2E` | Tarjetas, modales, sidebar |
| `--surface-2` | `#EFEFF2` | `#3A3A3C` | Cabeceras de tabla, hover de filas |
| `--accent` / `--accent-text` | `#8A6418` | `#CBB079` | Enlace activo, item de sidebar, vista previa de URL parsada |
| `--btn-primary-bg` | `#1D1D1F` | `#F5F5F7` | Botón primario (monocromo invertido) |
| `--success` | `#248A3D` | (mismo) | Estado sesión activa |
| `--danger` | `#C9352C` | (mismo) | Estado error, borrado destructivo |
| `--text-disabled` | `#AEAEB2` | `#636366` | Ítems deshabilitados del sidebar |

El modo oscuro se activa por `prefers-color-scheme: dark` (sigue el sistema) o por `data-theme="dark"` en `<html>` (toggle manual). El valor del toggle se persiste en `localStorage['theme']`.

---

## Internacionalización — 25 idiomas y RTL

### Arquitectura i18n

El sistema i18n es completamente propio: no usa `react-i18next` ni ninguna biblioteca externa.

**`src/i18n/index.jsx`** expone:
- `I18nProvider`: contexto que mantiene el idioma activo, lee/escribe `localStorage['lang']` y aplica `lang` y `dir` al elemento `<html>`.
- `useI18n()`: hook que devuelve `{ t, lang, setLang }`.
- `translate(catalog, lang, key, vars)`: función pura, útil fuera de React.

**`t(key, vars)`** — reglas de resolución:
1. Busca la clave en el catálogo del idioma activo.
2. Si no la encuentra, cae al catálogo `es` (siempre completo).
3. Si tampoco existe en `es`, devuelve la propia clave (nunca `undefined`).
4. Para plurales: si `vars.n !== 1` y existe `key + '.pl'`, usa esa variante.
5. Interpola `{variable}` con `vars`.

### Los 25 idiomas

Los mismos 25 códigos que el backend (`core/i18n/languages.py`):
`ar, bg, cs, da, de, el, en, es, fa, fr, he, hu, it, ja, lt, lv, nl, pl, pt, rs, ru, sl, sv, tr, uk`

Los catálogos `es` y `en` están redactados a mano. Los 23 restantes se marcan como `[AUTO]` en los archivos — fueron generados automáticamente y pueden tener imprecisiones en frases contextuales.

### RTL — árabe, hebreo y persa

Al seleccionar `ar`, `he` o `fa`, el sistema aplica:
- `document.documentElement.dir = 'rtl'`
- `document.documentElement.lang = '<código>'`

El CSS del proyecto usa propiedades lógicas (`padding-inline-start`, `border-inline-start`, etc.) en lugar de las físicas (`padding-left`, `border-left`), por lo que los layouts se espejean automáticamente. El botón "← Mundos" en S9 tiene el texto con la flecha embebida en la clave de traducción, que en idiomas RTL puede espejarse como "→ Mundos" si el catálogo lo define así.

### Catálogo de claves (`es.js`)

163 claves organizadas en secciones:

| Prefijo de clave | Sección |
|---|---|
| `app.*` | Nombre de la app, versión |
| `nav.*` | Sidebar (Cuentas, Recursos, Tropas, Construcción, Próximamente) |
| `topbar.*` | Controles de topbar (tema, idioma, volver a mundos) |
| `page.accounts.*` | S2 — Lista de cuentas |
| `wizard.*` | S3 — Wizard de alta (2 pasos) |
| `page.account.*` | S4 — Detalle de cuenta |
| `modal.edit.*` | S5 — Modal editar cuenta |
| `modal.addWorld.*` | S6 — Modal añadir mundo |
| `modal.deleteAccount.*` | S7 — Modal borrar cuenta |
| `modal.deleteWorld.*` | S8 — Modal borrar mundo |
| `world.*` | S9 — Espacio del mundo y sesión (§4b) |
| `tribe.*` | Nombres de las 7 tribus |
| `error.*` | Errores globales (red, retry) |

---

## Cliente HTTP (`src/api/client.js`)

El cliente envía **`Accept-Language`** en cada petición, tomando el idioma de `localStorage['lang']` (default `es`). Esto cumple el requisito del backend (un `400` en respuesta a cualquier petición sin este header para los endpoints que lo exigen).

### `ApiError`

Clase de error con campos `message`, `status` (código HTTP) y `detail` (el campo `detail` del body de error de FastAPI). Los componentes usan `err.status` para distinguir `404`, `409`, `401`, etc. y adaptar la UI al estado apropiado.

### Funciones del API

| Función | Método + ruta | Resultado |
|---|---|---|
| `api.getAccounts()` | `GET /accounts` | Array de cuentas (desempaqueta `{accounts:[...]}`) |
| `api.getAccount(id)` | `GET /accounts/:id` | Objeto `AccountResponse` |
| `api.createAccount(data)` | `POST /accounts` | `AccountResponse` (`201`) |
| `api.updateAccount(id, data)` | `PUT /accounts/:id` | `AccountResponse` actualizado |
| `api.deleteAccount(id)` | `DELETE /accounts/:id` | `null` (`204`) |
| `api.getWorlds(accountId)` | `GET /accounts/:id/worlds` | Array de mundos |
| `api.createWorld(accountId, data)` | `POST /accounts/:id/worlds` | `WorldResponse` (`201`) |
| `api.deleteWorld(accountId, worldId)` | `DELETE /accounts/:id/worlds/:worldId` | `null` (`204`) |
| `api.getSession(accountId, worldId)` | `GET .../session` | `{active, world_id, account_id}` |
| `api.startSession(accountId, worldId)` | `POST .../session` | `{active: true, ...}` o `ApiError 401` |
| `api.stopSession(accountId, worldId)` | `DELETE .../session` | `null` (`204`) |

Los errores de red (fetch rechazado) producen `ApiError` con `status = 0` y `message = 'error.network'`, que los componentes traducen con `t('error.network')`.

---

## Árbol de rutas (`src/App.jsx`)

```
/                    → redirect a /cuentas
/cuentas             → ManagementShell > AccountsListPage        (S2)
/cuentas/nueva       → ManagementShell > NewAccountPage           (S3 wizard sobre S2)
/cuentas/:id         → ManagementShell > AccountDetailPage        (S4)
/mundos/:worldId     → WorldSpacePage                             (S9, sin shell de gestión)
*                    → NotFound
```

**Orden de rutas importante**: `/cuentas/nueva` debe declararse antes de `/cuentas/:id` para que React Router v6 no interprete `"nueva"` como un `account_id`. Si se invierte el orden, el wizard nunca se muestra.

**Dos shells distintos**: el `ManagementShell` (topbar + sidebar de gestión) envuelve las rutas S2–S4. La ruta S9 (`/mundos/:worldId`) usa `WorldSpacePage` directamente, sin `ManagementShell`, por lo que el sidebar nunca aparece en el espacio del mundo.

---

## Modo Gestión — shell y sidebar

### `ManagementShell`

Contenedor de las pantallas S1–S8. Renderiza `Topbar` + `Sidebar` + `<Outlet />` (contenido de la ruta activa). El sidebar tiene ancho fijo de 200px en desktop (`≥lg`), colapsa a 48px (solo iconos) en tablet (`md`). En móvil el sidebar no se muestra en Etapa 1.

### `Sidebar`

Solo incluye la sección "Cuentas" como ítem activo. Las secciones "Recursos", "Tropas" y "Construcción" están declaradas en el diseño pero no están en `NAV_ITEMS` del sidebar: esas secciones pertenecen al Espacio del mundo (S9), no al shell de gestión. La única sección del sidebar de Gestión es "Cuentas".

**Por qué no hay ítems disabled en el sidebar en el código real**: el diseño original contemplaba cuatro secciones (incluyendo Recursos, Tropas y Construcción como disabled). En la implementación se decidió omitirlos del sidebar de Gestión porque conceptualmente pertenecen al Espacio del mundo. Esto es una **divergencia código/diseño** menor (ver más abajo).

---

## Páginas

### `AccountsListPage` (S2)

Cuatro estados: `loading` (skeleton de 3 filas), `empty` (panel con icono + CTA), `data` (tabla desktop / tarjetas móvil) y `error` (banner inline + reintentar).

La fila entera de la tabla es clickable (navega a S4). El botón `⋯` (menú contextual) está en la columna Acciones y abre la opción "Borrar cuenta" sin navegar.

En móvil (`< md`), la tabla se sustituye por tarjetas apiladas (`AccountCard`). La columna "Creada" se oculta en `< lg` (P3 según DESIGN.md §17).

### `NewAccountPage` (S3)

Renderiza `AccountsListPage` como fondo (atenuado por el backdrop del modal) y superpone `WizardModal`. El wizard tiene dos pasos:

1. **Datos de la cuenta**: Email, Username, Contraseña (con toggle de visibilidad). Validación inline al perder el foco.
2. **Primer mundo**: URL del servidor (con vista previa parseada en tiempo real) + Tribu.

Al completar el wizard, la secuencia de API es: `POST /accounts` → si `201`, `POST /accounts/:id/worlds`. Si el primer paso falla con `409` (email duplicado), el wizard retrocede al paso 1 con error inline.

### `AccountDetailPage` (S4)

La pantalla más compleja. Implementa:

- **Cabecera** con breadcrumb "← Cuentas / username", datos de la cuenta y botones Editar/Borrar.
- **Tabla de mundos** (desktop) / tarjetas (móvil) con columnas: URL, vista parsada, tribu, sesión, acciones.
- **Máquina de estados de sesión** por mundo (§4b del diseño):

| Estado | Badge | Botón de acción |
|---|---|---|
| `idle` | `○ Inactivo` (gris) | `[Arrancar]` |
| `connecting` | `⟳ Conectando…` (oro + spinner) | `[Cancelar]` (deshabilitado) |
| `active` | `● Activo` (verde) | `[Parar]` + `[Entrar]` |
| `error` | `⚠ Error de conexión` (rojo) | `[Reintentar]` |
| `stopping` | `⟳ Parando…` (gris + spinner) | ninguno |

Al montar S4, la página consulta `GET .../session` por cada mundo para inicializar el estado (silencioso: `404`/`501` → `idle`, no rompe la UI).

Al pulsar **Arrancar**: el mundo pasa a `connecting`, se llama `POST .../session` (síncrono, hasta ~30 s; el cliente no tiene timeout menor al valor real). Si la respuesta es `200`, el mundo pasa a `active` y la app navega automáticamente a `/mundos/:worldId`. Si es `401`, el mundo pasa a `error` y la UI permanece en S4.

Al pulsar **Parar**: se llama `DELETE .../session`. El mundo pasa a `idle`.

Al pulsar **Entrar** (mundo ya activo): navega directamente a `/mundos/:worldId` sin re-login.

**Restricciones de UI derivadas del estado de sesión**:
- Un mundo en `active` o `connecting` no puede borrarse (el botón `⋯ → Borrar mundo` se deshabilita con tooltip explicativo).
- El botón "Borrar cuenta" se deshabilita si algún mundo está `active` o `connecting`.

### `WorldSpacePage` (S9 — Etapa 1)

Pantalla completa sin sidebar de gestión. Implementada en **Etapa 1** con la topbar mínima (botón "← Mundos" + wordmark + ThemeToggle + LangPicker) y el área de contenido vacía. El contenido real (configuración del mundo, recursos, tropas, etc.) se implementará en Etapa 2 como features independientes.

El botón "← Mundos" llama a `navigate(-1)` (vuelve a la pantalla anterior en el historial, que normalmente es S4).

---

## Componentes de UI reutilizables

### `uiUtils.jsx`

| Utilidad | Descripción |
|---|---|
| `parseServerUrl(url)` | Extrae `{subdomain, speed, domain}` de una URL de servidor Travian. Devuelve `null` si la URL no es parseable. Produce la vista "ts1 · x1 · international" visible en S3, S4 y S6. |
| `BadgeSpinner` | Spinner SVG animado (16px), alineado inline, para los estados `connecting` y `stopping`. |
| `showToast(message, type?)` | Muestra un toast temporal (3 s) en la esquina inferior derecha. Sin estado global: append al DOM directamente. |

### `ThemeToggle`

Botón que alterna entre `data-theme="light"` y `data-theme="dark"` en `<html>`, persistiendo la preferencia en `localStorage['theme']`. El icono cambia entre ☀ (claro) y 🌙 (oscuro).

### `LangPicker`

Dropdown con campo de búsqueda que lista los 25 idiomas por su endónimo (nombre en la propia lengua, no en español). Al seleccionar un idioma llama a `setLang(code)` del contexto i18n, que actualiza `localStorage['lang']`, cambia el `dir` y `lang` del documento, y re-renderiza los textos.

---

## Convenciones de CSS

- Todo color mediante token CSS: `var(--accent)`, `var(--danger)`, etc. Nunca hex hardcodeado en componentes.
- Propiedades lógicas para RTL: `padding-inline-start` en lugar de `padding-left`; `border-inline-start` en lugar de `border-left`.
- Tamaño mínimo de target táctil: 44px en elementos interactivos (botones, filas de tabla clickables).
- `focus-visible:outline` en lugar de `focus:outline` para que el foco sea visible por teclado pero no en clics.
- Tablas densas (40px por fila, hairline borders, sin zebra striping), coherente con DESIGN.md "Densidad sobre decoración".

---

## Divergencias código/diseño

| Divergencia | Descripción | Estado |
|---|---|---|
| Sidebar sin secciones disabled | El diseño `docs/design/gestion-cuentas-mundos.md` §6 S1 muestra Recursos, Tropas y Construcción como ítems disabled en el sidebar de Gestión. El código (`Sidebar.jsx`) solo tiene "Cuentas" y no incluye esos ítems. La decisión de implementación fue que esas secciones pertenecen al Espacio del mundo (S9), no al shell de Gestión. | Divergencia aceptada; documentada aquí. |
| `WorldSpacePage` sin contenido de Etapa 2 | El diseño describe el panel de estado, las tareas del bot y los intervalos en S9. El código solo tiene la topbar mínima y el área de contenido vacía. | Pendiente Etapa 2. |
| Nota "backend pendiente" en el diseño | El spec de diseño indica "backend de sesión no existe aún" (§4b). En realidad el backend de sesión está completamente implementado. | Discrepancia en el spec de diseño (no actualizado). Documentada en [`funcionalidades/cuentas-mundos.md`](../funcionalidades/cuentas-mundos.md). |

---

## Manual de usuario (pendiente)

El manual de usuario en HTML con capturas reales (tipo 3 según la metodología del documentador) está pendiente. Requiere:

1. La app corriendo en local (`npm run dev` en `frontend/` + `python main.py`).
2. Playwright disponible (`npx playwright install chromium`).
3. Credenciales de prueba para poblar la BD con datos de ejemplo (no datos reales).

Cuando estén disponibles estos prerrequisitos, el manual se generará en `docs/manual/` con capturas de las pantallas S2–S9 y el flujo de alta de cuenta.

---

🔖 Última revisión: 2026-05-26
