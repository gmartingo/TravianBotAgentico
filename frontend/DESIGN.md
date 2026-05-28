# DESIGN.md — Sistema de diseño del dashboard

Fuente de verdad visual del frontend. Todo componente, pantalla o ajuste de UI
debe respetar estas reglas. Si una pantalla necesita algo que no está aquí, se
añade aquí primero (y se bumpea la marca de agua), no se improvisa en el componente.

> El lenguaje visual es **minimalista estilo Apple / macOS**: superficies neutras
> en gris plata (claro) o grafito (oscuro), tipografía del sistema, jerarquía por
> espacio y peso —no por color—, y un **único acento: oro champán apagado**, usado
> con cuentagotas. La densidad manda sobre la decoración: esto es una herramienta
> interna, no una landing.

---

## 1. Filosofía

1. **Neutro primero, color al final.** El 95% de la interfaz es gris. El oro solo
   aparece en lo accionable (botón primario, enlace, foco, estado "activo").
2. **El espacio y el peso crean jerarquía**, no las cajas de colores ni las sombras
   fuertes. Una hairline de 1px hace más que una sombra.
3. **Restraint.** Si dudas entre añadir o quitar, quita. Nada de adornos.
4. **Densidad informativa.** Tablas compactas, números alineados, lectura rápida.
5. **Coherencia con el SO.** Fuente del sistema, radios moderados, movimiento sutil:
   la app debe sentirse "nativa" en un Mac y correcta en Windows/Linux.

---

## 2. Modo claro + oscuro (no negociable)

La app **siempre** soporta los dos modos con un toggle. Todos los colores se
declaran como **tokens duales** (variables CSS); ningún componente hardcodea un hex.

- **Por defecto:** sigue la preferencia del sistema (`prefers-color-scheme`).
- **Override manual:** el toggle fija `data-theme="light" | "dark"` en `<html>` y se
  **persiste en `localStorage`** (mismo patrón que la preferencia de idioma `lang`
  descrita en `CLAUDE.md`).
- **Regla de oro del modo oscuro:** la elevación se consigue **subiendo el tono de la
  superficie**, no agrandando la sombra. Las sombras casi no se ven sobre grafito.

---

## 3. Paleta — neutros (el cuerpo de la UI)

### Modo claro — "plata"

| Token | Hex | Uso |
|---|---|---|
| `--bg` | `#F5F5F7` | Fondo de la app (gris plata, apple.com) |
| `--surface` | `#FFFFFF` | Tarjetas, paneles, filas |
| `--surface-2` | `#EFEFF2` | Relieve sutil: cabecera de tabla, hover, input fill |
| `--border` | `#D2D2D7` | Hairline 1px (divisores, bordes de tarjeta) |
| `--border-strong` | `#C7C7CC` | Borde de input, separadores marcados |
| `--text` | `#1D1D1F` | Texto principal (casi negro, **nunca `#000`**) |
| `--text-secondary` | `#6E6E73` | Texto secundario, labels |
| `--text-tertiary` | `#8E8E93` | Placeholders, metadatos |
| `--text-disabled` | `#AEAEB2` | Estado deshabilitado |

### Modo oscuro — "grafito"

| Token | Hex | Uso |
|---|---|---|
| `--bg` | `#1D1D1F` | Fondo de la app (grafito, **nunca negro puro**) |
| `--surface` | `#2C2C2E` | Tarjetas, paneles, filas |
| `--surface-2` | `#3A3A3C` | Relieve / elevación (sube tono, no sombra) |
| `--border` | `#3A3A3C` | Hairline 1px |
| `--border-strong` | `#48484A` | Borde de input, separadores marcados |
| `--text` | `#F5F5F7` | Texto principal (plata claro) |
| `--text-secondary` | `#AEAEB2` | Texto secundario, labels |
| `--text-tertiary` | `#8E8E93` | Placeholders, metadatos |
| `--text-disabled` | `#636366` | Estado deshabilitado |

---

## 4. Acento — oro champán apagado (único color de marca)

El oro **solo** se usa en: **enlaces / texto accionable**, **estado "activo /
trabajando"**, anillo de foco e indicador de selección. **NO se usa en botones** —
los botones son monocromos (ver §12) para que el oro no pierda su valor de señal.
Nunca como decoración, nunca dos acentos compitiendo.

> ⚠️ **Contraste:** el oro tiene poco contraste sobre fondo claro. Por eso en modo
> claro usamos un **oro antiguo más profundo** (el oro vivo más alto posible que aún
> cumple AA sobre plata) y reservamos el champán brillante para modo oscuro, donde
> brilla sin problema. Valores **verificados WCAG AA (≥ 4.5:1)** en texto normal.

### Modo claro

| Token | Hex | Contraste | Uso |
|---|---|---|---|
| `--accent-text` | `#8A6418` | 4.9:1 sobre plata · 5.4:1 sobre blanco | Enlaces y texto accionable |
| `--accent` | `#8A6418` | — | Iconos accionables, barras de progreso, indicador "activo" |
| `--accent-hover` | `#6F5012` | — | Hover / pressed de enlaces |
| `--accent-subtle` | `rgba(138,100,24,0.14)` | — | Fila seleccionada, fondo de chip "activo" |

### Modo oscuro

| Token | Hex | Contraste | Uso |
|---|---|---|---|
| `--accent-text` | `#CBB079` | 8.0:1 sobre grafito | Enlaces y texto accionable (brilla) |
| `--accent` | `#CBB079` | — | Iconos accionables, barras de progreso, indicador "activo" |
| `--accent-hover` | `#D8C089` | — | Hover / pressed de enlaces (más claro) |
| `--accent-subtle` | `rgba(203,176,121,0.16)` | — | Fila seleccionada, fondo de chip "activo" |

### Acción primaria (botones) — monocromo, NO oro

El botón primario es el **neutro de máximo contraste**, invertido por modo. Así la
acción principal destaca sin robarle protagonismo al oro.

| Token | Claro | Oscuro | Uso |
|---|---|---|---|
| `--btn-primary-bg` | `#1D1D1F` | `#F5F5F7` | Relleno del botón primario |
| `--btn-primary-text` | `#FFFFFF` | `#1D1D1F` | Texto sobre el botón primario |
| `--btn-primary-hover` | `#3A3A3C` | `#E2E2E6` | Hover / pressed |

---

## 5. Estados semánticos (solo para estado, nunca decorativos)

Colores reservados para señalizar **estado del bot / del dato**. Se usan con icono
**además** del color (el color nunca es la única señal — ver Accesibilidad). Se
mantienen sobrios para no competir con el oro.

| Estado | Claro | Oscuro | Uso |
|---|---|---|---|
| Éxito / corriendo | `#248A3D` | `#34C759` | Bot activo, tarea OK |
| Error / detenido | `#C9352C` | `#FF453A` | Fallo, sesión caída |
| Información | `#0A6FCC` | `#0A84FF` | Aviso neutro, tooltip informativo |
| Neutro / inactivo | `--text-tertiary` | `--text-tertiary` | Pausado, idle, sin datos |

> **No hay "warning naranja".** El naranja choca con el oro. Para "en progreso /
> requiere atención" usamos el **propio acento oro** + icono, no un naranja aparte.

---

## 6. Tipografía

**Fuente del sistema** (cero web fonts: más rápido y más "nativo"):

```css
--font-sans: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI",
             Roboto, Helvetica, Arial, sans-serif;
--font-mono: ui-monospace, "SF Mono", Menlo, Consolas, "Roboto Mono", monospace;
```

- Mac → SF Pro (look Apple real). Windows → Segoe UI. Linux/Pi → Roboto.
- **`--font-mono` para todo dato numérico** que se alinea en columnas (recursos,
  tasas, timers, coordenadas) **junto con `font-variant-numeric: tabular-nums`** para
  que las cifras no "bailen" al actualizarse.
- `-webkit-font-smoothing: antialiased;` en `body`.

### Escala tipográfica (herramienta densa)

| Rol | Tamaño | Peso | Tracking | Uso |
|---|---|---|---|---|
| Display / H1 | 28px | 600 | -0.02em | Título de página |
| H2 | 22px | 600 | -0.015em | Sección |
| H3 | 17px | 600 | -0.01em | Subsección, cabecera de tarjeta |
| Body | 14px | 400 | 0 | Texto general (densidad) |
| Body-strong | 14px | 500 | 0 | Énfasis, valores |
| Caption | 12px | 400 | 0 | Labels, metadatos, secundario |
| Mono / dato | 13px | 400/500 | 0 | Números, timers, IDs (tabular-nums) |

- Interlineado: ~1.4 en cuerpo, ~1.2 en títulos.
- **Sin gradient text.** **Sin texto en mayúsculas decorativo** (salvo micro-labels
  de cabecera de tabla, 11px, `letter-spacing: 0.04em`, opcional).

---

## 7. Espaciado y grid

Base de **4px**. Usa solo estos pasos (no inventes valores intermedios):

```
4 · 8 · 12 · 16 · 20 · 24 · 32 · 40 · 48 · 64
```

- Padding interno de tarjeta: 16–24px. Gap entre tarjetas: 16–24px.
- Padding de página: 24–32px.
- El espacio en blanco generoso es parte del estilo Apple — no lo rellenes "porque sí".

---

## 8. Radios de borde

Moderados (macOS), nunca exagerados (eso es iOS marketing):

| Token | Valor | Uso |
|---|---|---|
| `--radius-sm` | 6px | Botones, inputs, chips |
| `--radius-md` | 10px | Tarjetas, paneles |
| `--radius-lg` | 14px | Modales, superficies grandes |
| `--radius-full` | 9999px | Pills, avatares, badges de estado |

---

## 9. Elevación, sombras y hairlines

La **hairline de 1px hace el trabajo pesado.** Las sombras son sutiles y suaves.

### Modo claro

```css
--shadow-sm: 0 1px 2px rgba(0,0,0,.04), 0 1px 3px rgba(0,0,0,.06);
--shadow-md: 0 2px 8px rgba(0,0,0,.06), 0 1px 3px rgba(0,0,0,.04);
--shadow-lg: 0 8px 30px rgba(0,0,0,.12);   /* solo modales / popovers */
```

En claro, **prefiere borde a sombra** en tarjetas estáticas. La sombra se reserva
para elementos que "flotan" (menús, modales, tooltips).

### Modo oscuro

```css
--shadow-sm: 0 1px 2px rgba(0,0,0,.4);
--shadow-md: 0 4px 12px rgba(0,0,0,.5);
--shadow-lg: 0 12px 32px rgba(0,0,0,.6);
```

En oscuro la sombra casi no se percibe: **eleva con `--surface-2`**, no con sombra.

---

## 10. Movimiento

Sutil, rápido, ease-out. Estilo Apple = se nota poco, nunca distrae.

```css
--ease: cubic-bezier(0.4, 0.0, 0.2, 1);
--dur-fast: 150ms;   /* hover, foco, micro */
--dur-base: 220ms;   /* paneles, transiciones de estado */
--dur-slow: 300ms;   /* modales, cambios de página */
```

- **Nada de rebotes ni animaciones juguetonas.**
- Respeta `@media (prefers-reduced-motion: reduce)`: desactiva todo movimiento no
  esencial.

---

## 11. Iconografía

- Un **único set de iconos de línea fina**, estilo SF Symbols.
  **Recomendado: [Lucide](https://lucide.dev)** (fino, consistente, MIT; SF Symbols
  no tiene licencia para web).
- Tamaño base 16–18px, grosor de trazo coherente (1.5–2px).
- Color: hereda `--text-secondary` por defecto; `--accent` solo cuando es accionable.
- Nada de mezclar estilos de icono (relleno + línea) en la misma vista.

---

## 12. Convenciones de componentes

> El diseño de **pantallas concretas y su navegación** lo produce el agente
> `disenador-producto` en `docs/design/`. Aquí solo viven las **reglas base** de
> cómo se ven los componentes transversales.

### Botones
- **Primario (monocromo, NO oro):** relleno `--btn-primary-bg`, texto
  `--btn-primary-text`, `--radius-sm`, altura 32px (denso) / 36px. Hover →
  `--btn-primary-hover`. Es grafito en claro y plata en oscuro (se invierte).
- **Secundario:** fondo `--surface`, borde `--border-strong` 1px, texto `--text`.
- **Terciario / ghost:** solo texto en `--accent-text` (oro), sin fondo ni borde.
- **Destructivo:** usa el rojo semántico, no el oro.

### Inputs
- Fondo `--surface` (o `--surface-2`), borde `--border-strong` 1px, `--radius-sm`.
- **Foco:** anillo de 2px en `--accent` + cambio de borde a `--accent`. Sin "glow".
- Placeholder en `--text-tertiary`.

### Foco (accesibilidad — obligatorio)
- **Nunca** `outline: none` sin reemplazo. Todo elemento interactivo muestra un
  anillo de foco visible: `outline: 2px solid var(--accent); outline-offset: 2px;`.

### Tablas (el caballo de batalla — herramienta densa)
- Filas compactas (36–40px), **divisores hairline** entre filas (`--border`), **sin
  zebra striping** (las tablas Apple son limpias). Hover de fila muy sutil
  (`--surface-2`).
- Cabecera en `--surface-2`, texto `--text-secondary`, micro-label opcional en
  mayúsculas 11px.
- **Números siempre `--font-mono` + `tabular-nums`**, alineados a la derecha.
- Fila seleccionada: fondo `--accent-subtle`.

### Tarjetas / paneles
- Fondo `--surface`, `--radius-md`, borde `--border` 1px (claro) / elevación por
  `--surface-2` (oscuro). Padding 16–24px.

### Estados de vista (obligatorio en toda vista con datos)
Cada vista que muestra datos define explícitamente: **vacío**, **cargando**,
**error** y **sin permiso**. El detalle visual de cada uno por pantalla lo fija
`disenador-producto`; aquí solo se exige que existan.

---

## 13. Accesibilidad (mínimos no negociables)

- **Contraste:** texto normal ≥ 4.5:1, texto grande / iconos ≥ 3:1 (WCAG AA). Los
  valores de acento de §4 ya están verificados.
- **El color nunca es la única señal:** los estados (corriendo / detenido / error)
  llevan **icono o texto además del color**.
- **Foco visible siempre** (ver §12).
- **`prefers-reduced-motion`** respetado (ver §10).
- Targets táctiles/click ≥ 28px de alto en controles densos, 32px+ donde haya sitio.

---

## 14. Lista de prohibiciones (los "no" del estilo)

- ❌ **Glassmorphism** / blur decorativo. Superficies planas y limpias.
- ❌ **Gradient text** y rellenos en degradado decorativos.
- ❌ **Negro puro `#000`** o blanco crudo como fondo de app. Usa `#1D1D1F` / `#F5F5F7`.
- ❌ **Colores neón / saturados** de marca. El oro apagado es el único acento.
- ❌ **Dos acentos compitiendo.**
- ❌ **Sombras oscuras/pesadas.** Sutiles o nada.
- ❌ **Animaciones con rebote** / skeuomorfismo.
- ❌ **Mezclar sets de iconos.**
- ❌ **Decoración por encima de densidad.** Es una herramienta interna.

---

## 15. Implementación — tokens (Tailwind v4 + toggle)

Bloque de referencia listo para copiar cuando se haga el scaffold del frontend.
Stack: **React + Vite + Tailwind v4**.

### 15.1 Variables CSS (tema en runtime)

```css
/* src/styles/tokens.css */

:root {
  /* ---- neutros: claro ---- */
  --bg: #F5F5F7;
  --surface: #FFFFFF;
  --surface-2: #EFEFF2;
  --border: #D2D2D7;
  --border-strong: #C7C7CC;
  --text: #1D1D1F;
  --text-secondary: #6E6E73;
  --text-tertiary: #8E8E93;
  --text-disabled: #AEAEB2;

  /* ---- acento oro: claro (oro antiguo, AA) ---- */
  --accent: #8A6418;
  --accent-text: #8A6418;
  --accent-hover: #6F5012;
  --accent-subtle: rgba(138,100,24,.14);

  /* ---- botón primario: monocromo invertido (claro) ---- */
  --btn-primary-bg: #1D1D1F;
  --btn-primary-text: #FFFFFF;
  --btn-primary-hover: #3A3A3C;

  /* ---- semánticos: claro ---- */
  --success: #248A3D;
  --danger: #C9352C;
  --info: #0A6FCC;

  /* ---- sombras: claro ---- */
  --shadow-sm: 0 1px 2px rgba(0,0,0,.04), 0 1px 3px rgba(0,0,0,.06);
  --shadow-md: 0 2px 8px rgba(0,0,0,.06), 0 1px 3px rgba(0,0,0,.04);
  --shadow-lg: 0 8px 30px rgba(0,0,0,.12);

  /* ---- radios, fuentes, motion (no cambian por tema) ---- */
  --radius-sm: 6px;  --radius-md: 10px;  --radius-lg: 14px;  --radius-full: 9999px;
  --font-sans: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI",
               Roboto, Helvetica, Arial, sans-serif;
  --font-mono: ui-monospace, "SF Mono", Menlo, Consolas, "Roboto Mono", monospace;
  --ease: cubic-bezier(0.4, 0.0, 0.2, 1);
  --dur-fast: 150ms; --dur-base: 220ms; --dur-slow: 300ms;
}

/* tokens oscuros: reutilizados por (a) sistema en dark salvo override claro,
   y (b) override manual data-theme="dark" */
@mixin-dark {
  --bg: #1D1D1F;
  --surface: #2C2C2E;
  --surface-2: #3A3A3C;
  --border: #3A3A3C;
  --border-strong: #48484A;
  --text: #F5F5F7;
  --text-secondary: #AEAEB2;
  --text-tertiary: #8E8E93;
  --text-disabled: #636366;

  --accent: #CBB079;
  --accent-text: #CBB079;
  --accent-hover: #D8C089;
  --accent-subtle: rgba(203,176,121,.16);

  --btn-primary-bg: #F5F5F7;
  --btn-primary-text: #1D1D1F;
  --btn-primary-hover: #E2E2E6;

  --success: #34C759;
  --danger: #FF453A;
  --info: #0A84FF;

  --shadow-sm: 0 1px 2px rgba(0,0,0,.4);
  --shadow-md: 0 4px 12px rgba(0,0,0,.5);
  --shadow-lg: 0 12px 32px rgba(0,0,0,.6);
}

/* CSS real (sin @mixin): repetir el bloque oscuro en los dos selectores */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { /* …pegar aquí los tokens oscuros… */ }
}
:root[data-theme="dark"] { /* …pegar aquí los tokens oscuros… */ }
```

> Comportamiento resultante del toggle:
> - **Sin `data-theme`** → sigue el sistema (`prefers-color-scheme`).
> - **`data-theme="light"`** → fuerza claro aunque el sistema esté en oscuro.
> - **`data-theme="dark"`** → fuerza oscuro.
>
> El `@mixin-dark` de arriba es solo para no duplicar la lista en el documento; en
> el CSS real se pega el mismo bloque en los dos selectores indicados.

### 15.2 Mapeo a Tailwind v4

`@theme inline` hace que las utilidades generadas **referencien la variable**
(`var(--bg)`) en vez de copiar su valor → el cambio de tema en runtime funciona solo:

```css
/* src/styles/app.css */
@import "tailwindcss";
@import "./tokens.css";

@theme inline {
  --color-bg: var(--bg);
  --color-surface: var(--surface);
  --color-surface-2: var(--surface-2);
  --color-border: var(--border);
  --color-border-strong: var(--border-strong);
  --color-text: var(--text);
  --color-text-secondary: var(--text-secondary);
  --color-text-tertiary: var(--text-tertiary);
  --color-accent: var(--accent);
  --color-accent-text: var(--accent-text);
  --color-accent-hover: var(--accent-hover);
  --color-btn-primary: var(--btn-primary-bg);
  --color-btn-primary-text: var(--btn-primary-text);
  --color-btn-primary-hover: var(--btn-primary-hover);
  --color-success: var(--success);
  --color-danger: var(--danger);
  --color-info: var(--info);

  --radius-sm: var(--radius-sm);
  --radius-md: var(--radius-md);
  --radius-lg: var(--radius-lg);

  --font-sans: var(--font-sans);
  --font-mono: var(--font-mono);
}
```

Uso en componentes: `bg-bg`, `bg-surface`, `text-text-secondary`, `border-border`,
`bg-accent text-accent-contrast`, `rounded-md`, `font-mono`, etc.

### 15.3 Toggle (patrón)

```js
// lee preferencia: localStorage > sistema
const stored = localStorage.getItem("theme");        // "light" | "dark" | null
if (stored) document.documentElement.dataset.theme = stored;
// al alternar:
function setTheme(t) {
  document.documentElement.dataset.theme = t;        // "light" | "dark"
  localStorage.setItem("theme", t);
}
```

> Coherente con la preferencia `lang` en `localStorage` que ya usa el cliente HTTP
> (ver `CLAUDE.md` → "Cliente HTTP — cabecera de idioma obligatoria").

---

## 16. Internacionalización — multi-idioma (25 idiomas + RTL)

Restricción **global** del diseño, al mismo nivel que el modo claro/oscuro: la app
sirve los **25 idiomas** soportados por el backend (`ar, bg, cs, da, de, el, en, es,
fa, fr, he, hu, it, ja, lt, lv, nl, pl, pt, rs, ru, sl, sv, tr, uk` — ver `CLAUDE.md`
→ gobernanza de idioma). El idioma activo se guarda en `localStorage` (`lang`,
default `es`) y se envía como `Accept-Language` en cada petición. **El diseño debe
aguantar los 25 sin romperse.**

### 16.1 Selector de idioma
- Control visible (header o ajustes) que lista los 25 idiomas **por su endónimo**
  (nombre en su propia lengua: "Deutsch", "日本語", "العربية"), no traducidos.
- Con **buscador/filtro** — 25 es demasiado para un dropdown plano.
- Al cambiar: fija `dir`, fija `lang` en `<html>`, persiste en `localStorage` y
  recarga los textos.

### 16.2 Dirección de texto — RTL
- **3 idiomas RTL:** árabe (`ar`), hebreo (`he`), persa (`fa`). Cuando el idioma
  activo es RTL → `document.documentElement.dir = "rtl"`.
- **Usar SIEMPRE propiedades lógicas CSS**, nunca físicas: `margin-inline-start` (no
  `margin-left`), `padding-inline`, `inset-inline`, `text-align: start/end` (no
  `left`/`right`). En Tailwind v4: `ms-*`, `me-*`, `ps-*`, `pe-*`, `start-*`,
  `end-*`, `text-start`/`text-end`.
- **Iconos direccionales** (flechas atrás/siguiente, chevrons, progreso) se
  **espejan** en RTL; los no direccionales (logo, ajustes) no.
- El layout completo se espeja (sidebar, orden de columnas accionables). El toggle de
  tema y el selector de idioma deben seguir alcanzables en ambas direcciones.

### 16.3 Expansión de texto
- El mismo string cambia mucho de longitud: **alemán (`de`) puede crecer ~+35%** vs
  inglés/español; ruso y griego también expanden.
- **Nunca anchos fijos atados al texto.** Botones, chips, labels y cabeceras de tabla
  **crecen con su contenido** (`min-width`, no `width`).
- Revisar cada pantalla con el idioma **más largo** (alemán) y el **más corto** para
  confirmar que nada se corta ni desborda.
- Truncar solo texto **no crítico**, con `ellipsis` + tooltip con el texto completo.
  Nunca truncar acciones ni datos clave.

### 16.4 Tipografía multi-script
- La **fuente del sistema cubre los 25 scripts** (latino + diacríticos, cirílico,
  griego, árabe, hebreo, japonés) en Mac y Windows sin cargar nada → otra razón para
  el stack del sistema (§6).
- En Linux/Pi (base Roboto) el sistema hace fallback por script; verificar que
  árabe/hebreo/japonés rendericen (instalar **Noto** si falta en el entorno de
  despliegue).
- **Interlineado ≥ 1.4 y sin recortes verticales:** los diacríticos (checo `cs`,
  polaco `pl`, húngaro `hu`, turco `tr`), el griego y el cirílico tienen
  ascendentes/descendentes que se cortan con line-heights apretados.
- **CJK (japonés `ja`)** no usa espacios entre palabras: el corte de línea es por
  carácter; no asumir wrapping por espacios y dar un punto más de line-height.

### 16.5 Números, fechas y unidades
- Formatear con **`Intl.NumberFormat` / `Intl.DateTimeFormat`** según el locale activo
  (separadores de miles, formato de fecha/hora).
- Mantener **`tabular-nums`** para que las columnas numéricas sigan alineadas (§6).
- Dígitos: por defecto numerales occidentales (alinean mejor en tablas densas);
  respetar dígitos locales solo si el locale los impone vía `Intl` y no rompe la
  alineación.

### 16.6 Reglas para el código de UI
- **Cero texto hardcodeado** en componentes: todo string vía claves de traducción.
- **No concatenar fragmentos** para formar frases (el orden de palabras cambia por
  idioma): usar plantillas/ICU con interpolación y plurales.
- Los estados/acento usan **icono + texto**, nunca solo color (ya en §13) — el icono
  también ayuda cuando el texto es muy largo o va en RTL.

---

## 17. Responsive y adaptativo (muchos dispositivos)

Restricción **global**, al nivel de modo claro/oscuro e i18n. El dashboard se consulta
desde móvil, tablet, laptop y monitores grandes, y debe adaptarse a cada pantalla.

### 17.1 Filosofía
- **Mobile-first:** los estilos base son los del móvil; `md:`/`lg:`… **añaden**, no al
  revés.
- La app **no encoge la versión desktop**: **reordena prioridades**. En pantalla
  pequeña se muestra lo esencial (monitorizar el bot + acciones clave: estado,
  alertas, arrancar/parar) y la **gestión densa/avanzada vive en pantallas grandes**.
- Minimalismo bajo presión de espacio: **ocultar lo secundario/decorativo y colapsar
  lo importante tras un gesto explícito** (menú, "más", expandir fila). **Nunca se
  elimina el acceso a un dato o acción crítica — solo se reubica.**

### 17.2 Breakpoints (Tailwind v4)

| Breakpoint | min-width | Dispositivo | Layout |
|---|---|---|---|
| base | 0 | móvil | 1 columna · nav en drawer/bottom · tablas → tarjetas |
| `sm` | 640px | móvil grande | 1 columna, más aire |
| `md` | 768px | tablet | 2 columnas · sidebar colapsable |
| `lg` | 1024px | laptop | sidebar fija · tablas completas |
| `xl` | 1280px | desktop | densidad plena |
| `2xl` | 1536px | monitor grande | cap de ancho de contenido legible |

### 17.3 Jerarquía de prioridad — qué se oculta o colapsa
Cada elemento se clasifica y el comportamiento al estrechar es:

- **P1 — siempre visible:** identidad de la vista, dato/acción principal, **estado del
  bot, alertas críticas** y acceso a las secciones (aunque la nav vaya colapsada).
- **P2 — colapsa tras disclosure en pantallas pequeñas:** filtros, columnas
  secundarias de tabla, paneles de detalle → van a un drawer/acordeón ("Filtros",
  "Detalles", "Más").
- **P3 — se oculta en móvil:** metadatos decorativos, columnas de baja prioridad,
  captions redundantes, breadcrumbs, ayudas largas.

> Regla: **ocultar P3 · colapsar P2 · nunca tocar P1.**

### 17.4 Navegación
- **≥ `lg`:** sidebar fija.
- **`md`:** sidebar colapsable (icon-only / toggle).
- **< `md`:** drawer (hamburguesa) o bottom-tab con las 3–5 secciones P1. El **toggle
  de tema y el selector de idioma** deben quedar accesibles desde ahí.

### 17.5 Tablas densas en pantalla pequeña (el caso difícil)
- Cada columna declara **prioridad**: al estrecharse **se ocultan primero las de menor
  prioridad** (no scroll infinito de columnas).
- Por debajo de `md`: la tabla se transforma en **lista de tarjetas apiladas** — cada
  fila = una tarjeta con 2–3 campos P1 y el resto tras "expandir".
- Si se conserva formato tabla: **scroll horizontal contenido** (solo la tabla, no la
  página) con **primera columna sticky** (identidad de la fila).
- Las acciones de fila se agrupan en un menú "⋯" en móvil. Números siguen
  `tabular-nums`.

### 17.6 Táctil vs puntero
- Táctil (`@media (pointer: coarse)`): **targets ≥ 44px** (mínimo Apple) y más
  espaciado. Con ratón en desktop, la densidad de 28–32px de §13.
- El hover no es fiable en táctil: toda info en hover (tooltips de truncado) debe tener
  equivalente por **tap/foco**.

### 17.7 Tipografía y espaciado fluidos
- Body 14px en desktop; **inputs ≥ 16px en móvil** para evitar el auto-zoom de iOS.
- Los títulos bajan un escalón en móvil (H1 28→24, H2 22→19…).
- Padding de página y gaps menores en móvil (16) y mayores en desktop (24–32), dentro
  de la escala de §7.
- **Cap de ancho de contenido legible** en monitores enormes (no estirar texto/tarjetas
  a 2560px; las tablas sí pueden usar el ancho disponible).

### 17.8 Reglas duras
- **Sin scroll horizontal de la página** — solo contenedores con scroll intencional.
- Responsive **compone con** dark mode, RTL e i18n: columnas ocultas + espejado RTL +
  texto expandido deben funcionar a la vez.
- Probar en anchos de referencia: **390 (móvil) · 768 (tablet) · 1280 (laptop) · 1920
  (desktop)**.

---

## 18. Workflow mockup-first (regla de proceso, no negociable)

**Ninguna vista/app se implementa en código sin pasar antes por su mockup editable.**
El usuario tiene que poder *coger cada componente y arrastrarlo donde quiera* (botones,
sliders, pestañas, campos… todo) y aprobar la composición antes de escribir el
componente real.

### 18.1 El artefacto
- Por cada vista nueva se crea **`frontend/mockups/<vista>.playground.html`**: un HTML
  **autocontenido** (cero dependencias del backend ni build) que:
  - Usa los **tokens de §15** (mismo aspecto que la app real).
  - Tiene **modo Editar** con drag & drop libre e **imán de 8px** sobre una rejilla.
  - Incluye **toggle de tema** y **selector de idioma** para revisar claro/oscuro,
    el oro y RTL mientras se compone.
  - Permite **Guardar** (localStorage), **Restablecer** y **Exportar layout** (JSON
    con posiciones de cada bloque).
- Convención: vive en `frontend/mockups/`, **fuera de `src/`** (no es producción).
  Referencia viva: `frontend/mockups/login.playground.html`.

### 18.2 El gate humano
1. El agente entrega el `*.playground.html`.
2. El usuario entra en **Editar**, recoloca los bloques y **aprueba** la composición.
3. **Exporta el layout** y se lo pasa al agente (JSON).
4. Solo entonces `desarrollador-ux-ui` implementa la vista real.

### 18.3 Del layout al código
- El layout exportado expresa **composición e intención** (orden, agrupación,
  jerarquía, qué va junto a qué), **no** coordenadas pixel-perfect definitivas.
- La implementación **reaplica el responsive (§17)**: las posiciones absolutas del
  playground se traducen a un layout fluido con la jerarquía P1/P2/P3, breakpoints y
  reglas de tabla. El mockup decide el *qué y el dónde relativo*; el código decide el
  *cómo se adapta*.

### 18.4 Alcance del editor
- **v1 = reposición** (mover lo que ya hay). Suficiente para decidir composición.
- Si una vista necesita **añadir/quitar/duplicar** componentes desde una paleta o
  **redimensionar**, se puede escalar a un editor más potente (p. ej. GrapesJS o
  Gridstack) — se decide por vista, manteniendo siempre los tokens de este documento.

---

## 19. Patrones de layout y componentes implementados

Patrones extraídos del código real y verificados visualmente. Referencia obligatoria para crear nuevos mockups y componentes. Los tokens de layout viven en `tokens.css`.

### 19.1 Las dos shells — Management vs WorldSpace

Existen **dos shells completamente distintas** según el contexto:

#### Shell Management (`/cuentas`, `/cuentas/:id`)

```
┌── Topbar (52px) ─────────────────────────────────────────────────┐
│  [TB ■  TravianBot]                       [🌙 toggle][🌐 lang]   │
├── Sidebar (200px) ──┬── Contenido (padding: 24–32px) ────────────┤
│  ▶ Cuentas          │  H1 + acciones                             │
│                     │  tabla o contenido de página               │
│  ────────────────   │                                            │
│  v0.1.0 (mono 11px) │                                            │
└─────────────────────┴────────────────────────────────────────────┘
```

- Topbar: `[TB ■]` + `"TravianBot"` como wordmark fijo (no es botón de back)
- Sidebar: 200px, `background: var(--surface)`, `border-inline-end: 1px solid var(--border)`
- Footer sidebar: `border-top: 1px solid var(--border)`, `padding: 12px 16px`, versión en `var(--font-mono)` / `var(--text-tertiary)` / 11px

#### Shell WorldSpace (`/mundos/:id`)

```
┌── Topbar (52px) ─────────────────────────────────────────────────────────────┐
│  [TB ■ ←]   email(oro) · ● Activo(verde) · server · tribe (centrado)  [🌙][🌐]│
├── Sidebar (180px) ──┬── Contenido principal (padding: 24px 24px 72px) ────────┤
│  Dashboard          │  section heading + sección activa                       │
│  ▶ Agentes          │                                                         │
│  Listas de vacas    │  (72px de padding inferior = clearance del bottom bar)  │
│  Calculadora PRONTO │                                                         │
├─────────────────────┴──────────────────────────────────────────────────────────┤
│  [● Bot activo]  │  [pill: "nombre  00:00:00"]  ···  (carrusel horizontal)     │
│  AgentBottomBar (position:fixed, inset-inline:0, bottom:0, height:48px)        │
└─────────────────────────────────────────────────────────────────────────────────┘
```

- Topbar: `[TB ■]` solo (es `<button>` que hace `navigate(-1)`); info del mundo CENTRADA
- Sidebar: 180px (`--sidebar-w`); nav items en lugar de pestañas — no hay tabs
- AgentBottomBar: `position: fixed; z-index: 200; background: var(--surface); border-top: 1px solid var(--border)`

### 19.2 Topbar — el bloque TB ■

Compartido entre las dos shells, pero con comportamiento diferente:

```css
/* El cuadrado TB */
width: 28px; height: 28px; border-radius: 7px;
background: var(--btn-primary-bg); color: var(--btn-primary-text);
font-weight: 700; font-size: 12px;
display: grid; place-items: center;
```

- **Management Shell**: envuelto en `<button>` junto al texto "TravianBot" (15px/600), navega a `/`. Hover: `opacity: 0.75`.
- **WorldSpace Shell**: solo el cuadrado, sin texto, actúa como botón ← (navigate(-1)).

**Centro del topbar en WorldSpace** — una sola fila `flex`, overflow hidden:
- Email: `var(--accent-text)` / `var(--font-mono)` / fontWeight 500 / `max-width: 220px` / truncado
- `·` separador: `var(--text-disabled)`
- `● Activo`: punto 6px + texto, ambos en `var(--success)`
- `·` separador + server: `var(--font-mono)` / `var(--text-secondary)`
- `·` separador + tribu: `var(--text-secondary)`

### 19.3 Sidebar nav item

```css
/* Contenedor */
padding: 8px 10px; border-radius: var(--radius-sm);
display: flex; align-items: center; gap: 10px;
font-size: 14px; width: 100%; border: none; cursor: pointer;
position: relative;
transition: background var(--dur-fast) var(--ease);

/* ACTIVO */
background: var(--accent-subtle);
color: var(--accent-text); font-weight: 500;

/* Barra de acento izquierda (solo activo) */
position: absolute; inset-block: 4px; inset-inline-start: 0;
width: 3px; border-radius: var(--radius-full); background: var(--accent);

/* HOVER (inactivo) */
background: var(--surface-2);

/* DISABLED — ej. "Calculadora PRONTO" */
color: var(--text-disabled); cursor: not-allowed;
/* etiqueta "PRONTO": font-mono, 10px, uppercase, letterSpacing .04em, text-disabled, al final del item */
```

Icono: 16px, `aria-hidden="true"`. Label del item: flex:1. Sidebar no es colapsable en la implementación actual.

### 19.4 AgentBottomBar (barra inferior + carrusel)

```css
/* Sección izquierda = --sidebar-w = 180px */
/* [● dot] [label "Bot activo" / "Bot parado"] — clic = toggle ON/OFF */
dot: 7px × 7px, border-radius 50%
  running → background: var(--success)
  stopped → background: var(--danger)
label: font-size 13px, font-weight 500, color = mismo que el dot

/* Divisor vertical */
width: 1px; height: 20px; background: var(--border); align-self: center;
margin-inline-end: 14px;

/* Carrusel de pills — scrollable horizontal sin scrollbar visible */
flex: 1; display: flex; align-items: center; gap: 6px;
overflow-x: auto; scrollbar-width: none;
```

Cuando el agente está parado: texto "Bot parado — sin tareas programadas" en `var(--text-disabled)` / 12px.

### 19.5 Task pill (carrusel del AgentBottomBar)

```css
flex-shrink: 0; width: 168px; height: 28px; padding: 0 10px;
border-radius: var(--radius-full);
border: 1px solid var(--border); background: var(--surface-2);
display: flex; align-items: center; gap: 6px;
```

Nombre: 12px / fontWeight 500. Countdown: `var(--font-mono)` / 12px / fontWeight 600.

**Variante `isNext` (primera en la cola):**
```css
border-color: var(--accent); background: var(--accent-subtle);
/* countdown color: var(--accent-text) */
```

### 19.6 Scheduler card

Componente central de la pestaña Agentes. Una tarjeta por scheduler:

```css
/* Contenedor */
background: var(--surface); border: 1px solid var(--border);
border-radius: var(--radius-md); padding: 16px 20px;
transition: box-shadow var(--dur-fast);
/* Hover */
box-shadow: var(--shadow-sm);
/* Disabled (is_enabled=false) */
opacity: 0.6;
```

**Fila de cabecera** (`display:flex; align-items:center; gap:12px; margin-bottom:10px`):
- Nombre: 15px / fontWeight 500 / flex:1
- Badge "INACTIVO" si `!is_enabled`: text-disabled / font-mono / 11px
- Botón "Enviar ahora": secundario, icono ✈ (13px) + texto
- Botón "Asignar listas": secundario
- Botón `⋮` (RowMenu): ghost 28×28px, `var(--text-tertiary)`, abre dropdown con Editar / Ejecutar ahora / Eliminar
- **ToggleSwitch** (ver §19.7)

**Sub-info** (`font-size: 12px; color: var(--text-secondary)`):
`"N listas · intervalo X–Y min · N envíos"`

**Fila inferior** (`border-top: 1px solid var(--border); padding-top: 10px; display:flex; gap:12px`):
- Chips de listas (ver §19.8) — lado izquierdo, `flex:1`
- Countdown área — lado derecho, `flex-shrink:0`:
  - Label "Próximo:": 12px / text-secondary
  - Countdown: `var(--font-mono)` / **18px** / fontWeight 600 / `var(--text)` (o text-disabled si sin próxima ejecución)
  - `·` + hora exacta: font-mono / 12px / text-secondary / tabular-nums

### 19.7 ToggleSwitch

```css
/* Track */
width: 36px; height: 20px; border-radius: var(--radius-full);
cursor: pointer; position: relative; flex-shrink: 0;
transition: background var(--dur-base), border-color var(--dur-base);

/* ON */
background: var(--success); border: 1px solid var(--success);
/* OFF */
background: var(--surface-2); border: 1px solid var(--border-strong);

/* Thumb (span absoluto) */
width: 14px; height: 14px; border-radius: 50%; background: #fff;
top: 2px;
inset-inline-start: 18px;  /* ON */
inset-inline-start: 2px;   /* OFF */
transition: inset-inline-start var(--dur-base);
```

Semántica: `role="switch"` + `aria-checked` + `aria-label`.

### 19.8 Farm list assignment chips (dentro del scheduler card)

Chips clicables que navegan a la farm list correspondiente:

```css
display: inline-flex; align-items: center;
background: var(--surface-2); border: 1px solid var(--border);
border-radius: var(--radius-full); padding: 2px 10px;
font-size: 11px; color: var(--text-secondary);
white-space: nowrap; max-width: 180px;
overflow: hidden; text-overflow: ellipsis;
cursor: pointer;
transition: background var(--dur-fast), color var(--dur-fast);

/* Hover → oro */
background: var(--accent-subtle);
color: var(--accent-text);
border-color: var(--accent);
```

### 19.9 Village group y tabla de farm lists

**Cabecera de grupo** (aldea):
```css
font-size: 13px; font-weight: 500; color: var(--text-secondary);
margin-bottom: 8px; padding-bottom: 6px;
border-bottom: 1px solid var(--border);
display: flex; align-items: baseline; gap: 6px;
/* coordenadas: font-mono / 12px / text-tertiary → "(x,y)" */
```

**Tabla** (dentro del grupo):
```css
width: 100%; border-collapse: collapse;
background: var(--surface); border: 1px solid var(--border);
border-radius: var(--radius-md); overflow: hidden;
/* thead: background: var(--surface-2), micro-caps 11px/500, text-secondary */
/* filas: cursor pointer, hover implicit via el td highlight */
/* flecha de detalle: › (›) al final de cada fila, text-tertiary */
```

**Columna SLOTS — color según actividad:**
```css
/* 0/N (ninguno activo) → peligro */
color: var(--danger);
/* X/N (alguno activo, X > 0) → éxito */
color: var(--success);
/* font: var(--font-mono); font-variant-numeric: tabular-nums */
```

### 19.10 Badge / chip de estado inline

```css
display: inline-flex; align-items: center; gap: 4px;
border-radius: var(--radius-full); padding: 1px 7px;
font-size: 11px; font-weight: 500;
```

| Variante | Background | Color | Uso |
|---|---|---|---|
| Aviso / sonda | `var(--accent-subtle)` | `var(--accent-text)` | Slots en cooldown por bot |
| Neutral | `var(--surface-2)` | `var(--text-secondary)` | Estado manual |
| Dot de estado | (inline, sin bg) | `var(--success)`/`var(--danger)` | Acompañado de texto |

Icono opcional: 9–10px, `currentColor`, antes del texto.

### 19.11 Drawer lateral

Panel que desliza desde el extremo `end` (RTL-safe):

```css
position: fixed; inset-block: 0; inset-inline-end: 0;
width: 480px;   /* ≥ lg; móvil → 100vw */
background: var(--surface);
border-inline-start: 1px solid var(--border);
box-shadow: var(--shadow-lg); z-index: 300; overflow-y: auto;
transform: translateX(100%);   /* cerrado */
transition: transform var(--dur-base) var(--ease);
/* abierto: translateX(0) */
```

Cabecera sticky: `height: 52px; padding: 0 16px; border-bottom: 1px solid var(--border); background: var(--surface); position: sticky; top: 0`. Botón cierre ghost 28×28px con `×`.

### 19.12 Toast

```css
position: fixed; inset-inline: 0; bottom: 24px; margin: auto;
width: max-content; max-width: 90vw;
background: var(--btn-primary-bg); color: var(--btn-primary-text);
padding: 10px 16px; border-radius: var(--radius-sm);
box-shadow: var(--shadow-lg); font-size: 13px; pointer-events: none;
opacity: 0; transform: translateY(8px);
transition: opacity var(--dur-base) var(--ease), transform var(--dur-base) var(--ease);
/* visible: opacity:1; transform:translateY(0) — auto-dismiss 3s */
```

### 19.13 ErrorBoundary overlay

```css
/* Fondo */
position: fixed; inset: 0; z-index: 310;
display: flex; align-items: center; justify-content: center;
background: rgba(0, 0, 0, 0.4);
/* Panel */
background: var(--surface); border-radius: var(--radius-lg);
box-shadow: var(--shadow-lg); padding: 28px 32px; max-width: 400px; text-align: center;
```

Jerarquía: título 15px/600, detalle 12px/`var(--text-secondary)`/`var(--font-mono)`, botón primario.

### 19.14 Row highlight (nav scheduler → farm list)

```css
tr[data-highlight="1"] td {
  background: var(--accent-subtle) !important;
  transition: background 2s ease-out;
}
```

La fila recibe `data-highlight="1"` durante ~2s; la transición disuelve el fondo suavemente.

### 19.15 Active link en tabla (URL de servidor activo)

Cuando un mundo tiene sesión activa, su URL se convierte en botón:

```css
color: var(--accent-text); font-family: var(--font-mono); font-size: 12px;
text-decoration: underline; text-underline-offset: 2px;
background: transparent; border: none; padding: 0; cursor: pointer;
overflow: hidden; text-overflow: ellipsis; max-width: 200px; display: block;
```

### 19.16 Token de mockup — bloque a copiar

Todo `*.playground.html` nuevo debe copiar este bloque (fuente de verdad: `frontend/src/styles/tokens.css`):

```css
:root {
  --bg:#F5F5F7; --surface:#fff; --surface-2:#EFEFF2;
  --border:#D2D2D7; --border-strong:#C7C7CC;
  --text:#1D1D1F; --text-secondary:#6E6E73; --text-tertiary:#8E8E93; --text-disabled:#AEAEB2;
  --accent:#8A6418; --accent-text:#8A6418; --accent-hover:#6F5012; --accent-subtle:rgba(138,100,24,.14);
  --btn-primary-bg:#1D1D1F; --btn-primary-text:#fff; --btn-primary-hover:#3A3A3C;
  --success:#248A3D; --danger:#C9352C; --info:#0A6FCC;
  --shadow-sm:0 1px 2px rgba(0,0,0,.04),0 1px 3px rgba(0,0,0,.06);
  --shadow-md:0 2px 8px rgba(0,0,0,.06),0 1px 3px rgba(0,0,0,.04);
  --shadow-lg:0 8px 30px rgba(0,0,0,.12);
  --radius-sm:6px; --radius-md:10px; --radius-lg:14px; --radius-full:9999px;
  --font-sans:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --font-mono:ui-monospace,"SF Mono",Menlo,Consolas,"Roboto Mono",monospace;
  --ease:cubic-bezier(.4,0,.2,1); --dur-fast:150ms; --dur-base:220ms; --dur-slow:300ms;
  --topbar-h:52px; --sidebar-w:180px; --bottombar-h:48px;
}
[data-theme="dark"] {
  --bg:#1D1D1F; --surface:#2C2C2E; --surface-2:#3A3A3C;
  --border:#3A3A3C; --border-strong:#48484A;
  --text:#F5F5F7; --text-secondary:#AEAEB2; --text-tertiary:#8E8E93; --text-disabled:#636366;
  --accent:#CBB079; --accent-text:#CBB079; --accent-hover:#D8C089; --accent-subtle:rgba(203,176,121,.16);
  --btn-primary-bg:#F5F5F7; --btn-primary-text:#1D1D1F; --btn-primary-hover:#E2E2E6;
  --success:#34C759; --danger:#FF453A; --info:#0A84FF;
  --shadow-sm:0 1px 2px rgba(0,0,0,.4); --shadow-md:0 4px 12px rgba(0,0,0,.5); --shadow-lg:0 12px 32px rgba(0,0,0,.6);
}
```

---

🔖 Última revisión: 2026-05-27 (sistema de diseño: minimalismo estilo Apple, plata +
grafito con modo claro/oscuro y toggle; acento único oro antiguo `#8A6418` claro /
champán `#CBB079` oscuro reservado a enlaces + estados activos; botones primarios
monocromos invertidos; tokens duales Tailwind v4; internacionalización para 25
idiomas con RTL, expansión de texto y multi-script; responsive mobile-first con
jerarquía de prioridad P1/P2/P3 y tablas adaptativas; workflow mockup-first
obligatorio antes de implementar cualquier UI; §19 añadido con patrones verificados
visualmente: 2 shells (Management vs WorldSpace), nav lateral con barra de acento,
AgentBottomBar con carrusel, scheduler card con toggle switch, farm list chips,
group headers con slots coloreados, drawer lateral, toast, tokens de layout)
