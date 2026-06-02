# Spec de diseño — Calendario de rango para el filtro del Historial de reportes

> Agente: `disenador-producto`. Este documento NO es código: define la UI/UX del
> selector de fechas tipo calendario que se añade al filtro del **Historial de
> reportes de ataque**. La implementación la hará `desarrollador-ux-ui` a partir de
> este spec + el layout aprobado del mockup
> `frontend/mockups/calendario-filtro-historial.playground.html`.

---

## 1. Contexto y job-to-be-done

En `frontend/src/components/attack-reports/HistoryFilters.jsx` los campos **"Desde"**
y **"Hasta"** son hoy dos `<input type="text">` donde el usuario teclea a mano el
string `YYYY-MM-DD HH:MM:SS` (componente interno `DateFilterInput`). Es incómodo y
propenso a error de formato (la propia UI ya muestra borde rojo + `role="alert"`
cuando el patrón no encaja).

**Job-to-be-done:** *"Como usuario quiero acotar el historial a un rango de fechas
(con precisión de segundos) sin tener que recordar ni teclear el formato exacto."*

La salida que consume el filtro **no cambia**: sigue siendo el string
`YYYY-MM-DD HH:MM:SS` que `HistoryFilters` ya normaliza a ISO (`toISO()` reemplaza el
espacio por `T`) antes de llamar a `onApply`. El calendario es **un editor visual de
esos mismos dos campos de texto**, no un estado paralelo ni un formato nuevo. No
cambia el backend ni el contrato de `GET /attack-reports` (`from_date` / `to_date`).

---

## 2. Decisión de anatomía — campos editables + trigger de calendario

**Decisión: se MANTIENEN los dos inputs de texto actuales y se añade, dentro de cada
input (o pegado a él), un icono de calendario (`Calendar` de lucide-react) que abre un
ÚNICO popover de rango.** Justificación:

1. **No se pierde la entrada por teclado.** El usuario avanzado que ya sabe el formato
   puede seguir tecleando; el popover es una ayuda, no un reemplazo. Esto respeta el
   dictamen de palantir ("editor visual de los MISMOS campos").
2. **Un solo popover de rango** (no dos calendarios) cubre Desde y Hasta a la vez:
   evita duplicar UI y resuelve de forma natural la relación `from ≤ to`.
3. **Patrón ya conocido en el código:** el trigger + popover flotante es exactamente
   el de `LangPicker.jsx` (botón disparador + panel `absolute`, animación zoom, cierre
   por click-fuera/Escape, `z-index` alto, `max-width` para móvil) y `DeletePopover.jsx`
   (`role="dialog"`, focus trap con `useFocusTrap`).

Se descarta *reemplazar* el input por un único botón "elegir fechas": perdería la
edición manual y el feedback de validación en vivo que ya existe.

### Trigger
- Dentro del grupo "Fechas" del filtro, **un solo botón de calendario** (icono
  `Calendar`, 16px, `--text-secondary`) abre el popover de rango que controla **ambos**
  campos. Se coloca al final del grupo (lado `end`), alineado con los inputs (alto
  32px en desktop, ≥44px de área táctil en móvil vía padding).
- `aria-haspopup="dialog"`, `aria-expanded`, `aria-label` = "Elegir rango de fechas"
  (traducido). Hover → `--surface-2`. Foco → anillo `--accent` (regla §12 DESIGN).
- Los dos inputs de texto **se conservan tal cual** (mismo `DateFilterInput`,
  validación en vivo, borde rojo en error). Editar el calendario **escribe** en esos
  inputs; teclear en los inputs **se refleja** al reabrir el calendario.

---

## 3. Wireframe ASCII

### 3a. El filtro con el nuevo trigger (desktop, md+)

```
┌─ Filtro historial (surface-2, borde hairline) ───────────────────────────────────┐
│  COORDENADAS          FECHAS                                                       │
│  ┌──┐ ┌──┐            ┌ Desde ───────────────┐ ┌ Hasta ───────────────┐ ┌─┐       │
│  │X │ │Y │            │ 2026-05-28 00:00:00  │ │ 2026-06-01 13:39:30  │ │📅│       │
│  └──┘ └──┘            └──────────────────────┘ └──────────────────────┘ └─┘       │
│                                                                  [ Aplicar ] [Limpiar]│
└────────────────────────────────────────────────────────────────────────────────────┘
            (📅 = botón calendario; abre el popover de rango de §3b)
```

> Los inputs "Desde"/"Hasta" son los actuales `DateFilterInput` (mono, 32px, borde rojo
> en error). El botón 📅 es nuevo. "Aplicar" = primario monocromo; "Limpiar" = ghost
> con borde (solo si hay filtro activo) — ambos ya existen, no cambian.

### 3b. Popover recién abierto, SIN selección (las horas NO se muestran todavía)

```
                                          ┌─ Popover (role=dialog, surface, shadow-lg) ──────────┐
                                          │  Rango de fechas                              [ × ]  │
                                          │  ─────────────────────────────────────────────────  │
                                          │  ATAJOS                                               │
                                          │  [ Última hora ] [ Último día ] [ Desde el lunes ]    │  ← ghost
                                          │  ─────────────────────────────────────────────────  │
                                          │       ‹     junio 2026        ›   (navegación mes)    │
                                          │   lu  ma  mi  ju  vi  sá  do      ← Intl, semana=LUN  │
                                          │    1   2   3   4   5   6   7                          │
                                          │    8   9  10  11  12  13  14                          │
                                          │   15  16  17  18  19  20  21                          │
                                          │   22  23  24  25  26  27  28                          │
                                          │   29  30                                              │
                                          │                                                       │
                                          │  ── (sección HORA OCULTA: ningún input HH:MM:SS) ──   │
                                          │             [ Limpiar ]   [ Aplicar rango ]           │
                                          └───────────────────────────────────────────────────────┘
```

> **Estado vacío:** sin día seleccionado **no se muestra la sección "Hora"** — solo
> calendario + atajos + acciones. Esto reduce el ruido visual: los HH:MM:SS solo tienen
> sentido cuando ya hay un día al que aplicarlos.

### 3c. Popover con UN extremo elegido (aparece SOLO la hora de "Desde")

```
                                          │  ...calendario, con [15] marcado como inicio...      │
                                          │   Elige la fecha final           ← hint --text-secondary │
                                          │  ─────────────────────────────────────────────────  │
                                          │  HORA                                                 │
                                          │  Desde  [HH][:][MM][:][SS]       ← solo la fila "Desde" │ ← mono
                                          │  ─────────────────────────────────────────────────  │
                                          │             [ Limpiar ]   [ Aplicar rango ]           │
```

> Al fijar el **primer** extremo aparece, con transición suave (`--dur-fast`/`--dur-base`,
> sin salto brusco de layout), **únicamente la fila de hora "Desde"**. La fila "Hasta"
> sigue oculta hasta que exista el segundo extremo.

### 3d. Popover con RANGO completo (aparecen AMBAS filas de hora)

```
                                          ┌─ Popover (role=dialog, surface, shadow-lg) ──────────┐
                                          │  Rango de fechas                              [ × ]  │
                                          │  ─────────────────────────────────────────────────  │
                                          │  ATAJOS                                               │
                                          │  [ Última hora ] [ Último día ] [ Desde el lunes ]    │  ← ghost
                                          │  ─────────────────────────────────────────────────  │
                                          │       ‹     mayo 2026         ›   (navegación mes)    │
                                          │   lu  ma  mi  ju  vi  sá  do      ← Intl, semana=LUN  │
                                          │              1   2   3   4                            │
                                          │    5   6   7   8   9  10  11                          │
                                          │   12  13  14  15  16  17  18                          │
                                          │   19  20  21  22  23  24  25                          │
                                          │   26  27 [28]▓[29]▓[30]▓[31]      ← rango resaltado    │
                                          │                                                       │
                                          │   junio 2026                                          │
                                          │   lu  ma  mi  ju  vi  sá  do                          │
                                          │  ▓[1]◀ to   2   3   4   5   6   7    ← extremo "to"    │
                                          │  ...                                                  │
                                          │  ─────────────────────────────────────────────────  │
                                          │  HORA                                                 │
                                          │  Desde  [HH][:][MM][:][SS]   Hasta [HH][:][MM][:][SS] │ ← mono
                                          │  ─────────────────────────────────────────────────  │
                                          │             [ Limpiar ]   [ Aplicar rango ]           │
                                          └───────────────────────────────────────────────────────┘
```

> Leyenda: `[28]▓ … [31]▓` = días dentro del rango (fondo `--accent-subtle`).
> `[28]` y `[1]` (los extremos `from`/`to`) llevan fondo más marcado (`--accent`,
> texto `--btn-primary-text`/blanco) para distinguir los bordes del rango.
> Con el segundo extremo fijado (o tras un atajo, que rellena `from`+`to` de golpe)
> aparece también la fila "Hasta". En móvil el popover ocupa casi todo el ancho
> (`max-width: calc(100vw - 32px)`) y un solo mes visible con scroll vertical entre meses.

---

## 4. Mapa de interacción

| Acción | Comportamiento |
|---|---|
| **Abrir** | Clic en 📅 (o `Enter`/`Espacio` con foco en él) → monta el popover con animación zoom (mismo patrón `LangPicker`: doble `rAF` → `scale .95→1`, `opacity 0→1`, 150ms). El mes inicial mostrado es el del `from` actual si hay; si no, el del `to`; si no, el mes actual. El foco va al primer control del popover (atajo "Última hora" o el día seleccionado si existe). **Si no hay nada seleccionado, la sección "Hora" NO se muestra** (solo calendario + atajos + acciones); aparece en cuanto se fija un extremo (ver fila siguiente). |
| **Visibilidad de los HH:MM:SS** | Los inputs de hora están **ocultos por defecto** y se revelan por extremo: la fila "Desde" aparece al fijar `from`; la fila "Hasta" al fijar `to`. Si los inputs de texto del filtro ya traían un rango válido al abrir, las filas correspondientes aparecen ya visibles. La aparición usa una transición suave (`--dur-fast` para opacidad de cada fila, `--dur-base` para la altura de la sección) y **no debe provocar saltos bruscos** de layout. **Accesibilidad:** mientras está oculta, la fila lleva `hidden` + `aria-hidden="true"` (no se anuncia a lectores de pantalla ni entra en el orden de tabulación); al mostrarse, sus inputs vuelven a ser enfocables en orden coherente (Desde antes que Hasta). `prefers-reduced-motion` elimina la transición (aparece/desaparece sin animar). |
| **Cerrar** | Botón `×`, tecla `Escape`, o clic fuera del popover. Al cerrar con Escape/×, el foco vuelve al botón 📅 (trigger). Cerrar **NO aplica** los cambios automáticamente: aplicar es explícito (botón "Aplicar rango" o el "Aplicar" del filtro). Cerrar sin aplicar conserva lo elegido en los inputs de texto (es solo un editor de esos inputs). |
| **Seleccionar rango — primer clic** | Clic en un día → se fija `from` = ese día. El estado pasa a "un extremo elegido / esperando el segundo". Visualmente ese día queda como extremo marcado; aún no hay relleno de rango. **Aparece la fila de hora "Desde"** (HH:MM:SS) con transición suave; la fila "Hasta" sigue oculta. La hora del `from` se conserva (la de su input; si vacío → `00:00:00`). |
| **Seleccionar rango — segundo clic** | Clic en otro día → si es posterior o igual al `from`, se fija `to` = ese día y se resalta el rango entre ambos. **Aparece la fila de hora "Hasta"** (junto a la de "Desde" ya visible). La hora del `to` se conserva (la de su input; si vacío → `23:59:59` cuando es el extremo superior recién creado, ver §6 nota). |
| **Clic invertido (segundo día < primero)** | Si el segundo clic cae **antes** del `from` ya elegido, se reinterpreta: el nuevo día pasa a ser `from` y el anterior `from` pasa a ser `to` (auto-swap), de modo que **nunca** queda `from > to`. Alternativa válida: tratar el segundo clic como reinicio de selección (nuevo `from`). **Decisión: auto-swap** (menos clics, comportamiento esperado en date-range pickers). |
| **Tercer clic (rango ya completo)** | Reinicia: el nuevo clic se convierte en `from`, se borra `to`, vuelve a estado "esperando segundo". |
| **Editar horas** | Tres inputs mono `HH` `MM` `SS` por extremo (NO `<input type="time">` — no llega a segundos fiable). Reutilizan el estilo de `DateFilterInput` (alto 32px, fuente mono, borde rojo en error). Cada campo acepta 2 dígitos; al salir (`blur`) se zero-pad a 2 dígitos y se clampa al rango válido (HH 00–23, MM/SS 00–59). Cambiar la hora **no** mueve el día seleccionado. |
| **Pulsar atajo** | Calcula `from`/`to` (ver §6), pinta el rango en el calendario, rellena los inputs de hora y los dos inputs de texto del filtro. Como rellena ambos extremos a la vez, **aparecen las dos filas de hora** ("Desde" y "Hasta"). NO aplica solo: deja todo listo para que el usuario revise y pulse "Aplicar". |
| **Aplicar rango** (botón dentro del popover) | Escribe `from`/`to` formateados como `YYYY-MM-DD HH:MM:SS` en los dos inputs de texto del filtro, cierra el popover y dispara el mismo `onApply` que el botón "Aplicar" del filtro (que normaliza a ISO). Equivale a "elegir + aplicar" en un gesto. |
| **Limpiar** (botón dentro del popover) | Borra `from` y `to` (deja los dos inputs de texto vacíos = sin filtro de fecha) y vuelve el calendario a estado vacío. **Las filas de hora se vuelven a ocultar** (con transición suave). No cierra el popover (permite re-elegir). El "Limpiar" del filtro general sigue existiendo y limpia todo el filtro. |
| **Navegación entre meses** | Flechas `‹` / `›` (icono chevron lucide, **se espejan en RTL**) cambian el mes mostrado. En desktop se ven 1–2 meses; en móvil 1 mes con scroll. `PageUp`/`PageDown` mes anterior/siguiente con foco en el grid. |
| **Teclado en el grid** | Grid de calendario accesible: flechas mueven el día con foco (←/→ día ±1, ↑/↓ semana ±7), `Home`/`End` a inicio/fin de semana, `Enter`/`Espacio` selecciona el día con foco (mismo flujo de primer/segundo clic). `Tab` sale del grid hacia los inputs de hora. |
| **Teclear directo en los inputs de texto del filtro** | Sigue funcionando como hoy (validación en vivo). Al reabrir el popover, si el texto es un `YYYY-MM-DD HH:MM:SS` válido, el calendario lo refleja (día resaltado + horas) y **muestra la fila de hora del extremo que tenga valor** (si solo hay "Desde" válido → solo su fila; si hay ambos → ambas). Si el texto es inválido o vacío, el popover abre en estado vacío sobre el mes actual con las **filas de hora ocultas** (no intenta parsear basura). |

---

## 5. Estados (todos)

| Estado | Visual |
|---|---|
| **Vacío (sin selección) → horas ocultas** | Ningún día resaltado. **La sección "Hora" NO se muestra** (ni el label "Hora" ni ningún input HH:MM:SS); el popover solo enseña calendario + atajos + acciones. "Aplicar rango" habilitado (aplicar vacío = quitar filtro de fecha). |
| **Un solo extremo elegido (esperando segundo) → su hora visible** | El día `from` marcado (fondo `--accent`, texto invertido). Hint sutil bajo el calendario: "Elige la fecha final" (`--text-secondary`, 12px). **Aparece, con transición suave, SOLO la fila de hora "Desde"** (HH:MM:SS); la fila "Hasta" permanece oculta (`hidden`+`aria-hidden`, fuera de tabulación). Hover sobre días posteriores muestra preview tenue del rango (fondo `--accent-subtle` con opacidad menor). |
| **Rango completo → ambas horas visibles** | `from` y `to` con fondo `--accent` (extremos), días intermedios con fondo `--accent-subtle`. **Ambas filas de hora ("Desde" y "Hasta") visibles** y pobladas. (Un atajo aterriza directamente en este estado porque rellena los dos extremos a la vez.) |
| **Tras "Limpiar" → vuelve a horas ocultas** | Borrar la selección (botón "Limpiar" del popover, o vaciar los inputs de texto) re-oculta la sección "Hora" con transición suave y devuelve el popover al estado vacío. |
| **Rango inválido (`from > to`)** | No debería ocurrir vía calendario (auto-swap lo evita). Solo es alcanzable tecleando en los inputs de texto: en ese caso ambos inputs muestran borde rojo (igual que hoy por formato) **y** un mensaje `role="alert"` "La fecha 'Desde' debe ser anterior o igual a 'Hasta'"; el botón "Aplicar"/"Aplicar rango" queda **deshabilitado** (igual mecánica que el `hasDateError` actual, ampliada a la comprobación de orden). |
| **Mes sin datos** | El calendario no conoce qué meses tienen reportes (eso es del backend). **No** se deshabilitan días por "sin datos": el usuario filtra libremente; un rango sin reportes simplemente devuelve historial vacío (estado vacío de la tabla, fuera de este spec). No se bloquean fechas futuras (el usuario podría querer un `to` futuro). |
| **Foco / hover** | Día con hover: fondo `--surface-2`. Día con foco de teclado: anillo `--accent` (`outline 2px`). Botones atajo hover: borde `--accent`, texto `--accent-text` (ghost → oro al hover, coherente con chips §19.8). |
| **"Aplicar" deshabilitado** | Cuando hay error de formato en algún input de texto **o** `from > to`: botón con `--text-disabled`, `opacity .5`, `cursor not-allowed`, `aria-disabled` (idéntico al patrón actual de `HistoryFilters`). |
| **Móvil vs desktop** | Desktop: popover anclado al trigger (`absolute`, `end-0`), 1–2 meses lado a lado. Móvil: popover casi a ancho completo (`max-width: calc(100vw - 32px)`), 1 mes, días ≥44px, inputs de hora ≥16px (evita auto-zoom iOS, §17.7). |
| **Claro vs oscuro** | Solo tokens. Rango: claro `--accent-subtle` rgba(138,100,24,.14) / oscuro rgba(203,176,121,.16). Extremos: `--accent` (oro antiguo claro / champán oscuro) con texto `--btn-primary-text`. |
| **RTL (ar/he/fa)** | El grid del calendario se espeja (columna lunes a la derecha). Chevrons `‹`/`›` se intercambian. Propiedades lógicas (`inset-inline`, `margin-inline`, `text-align: start/end`). Nombres de día/mes vía `Intl` ya vienen en el script correcto. El popover ancla en `start`/`end` lógico. |

---

## 6. Comportamiento exacto de los 3 atajos

Los tres botones son **exactamente tres, ni más ni menos** (ghost). Todos calculan
**"ahora" en hora LOCAL del navegador** y formatean a `YYYY-MM-DD HH:MM:SS` **sin pasar
por UTC** (ver §8, bug de zona horaria). "Ahora" usa los **segundos reales actuales**
(no se redondea a `:00`).

Sea `now` = instante actual local (con su HH:MM:SS reales):

| Atajo | `from` | `to` |
|---|---|---|
| **"Última hora"** | `now − 1 hora` | `now` |
| **"Último día"** | `now − 24 horas` | `now` |
| **"Desde el lunes"** | Lunes de esta semana a las `00:00:00` (semana empieza en **lunes**) | `now` |

Detalle de cálculo (todo en local, formateado a mano, sin `toISOString()`):

- **Última hora:** `to = fmt(now)`; `from = fmt(now − 3600s)`. Ej.: now = `2026-06-01
  13:39:30` → from `2026-06-01 12:39:30`, to `2026-06-01 13:39:30`.
- **Último día:** `to = fmt(now)`; `from = fmt(now − 86400s)`. Ej.: from
  `2026-05-31 13:39:30`, to `2026-06-01 13:39:30`.
- **Desde el lunes:** localizar el lunes de la semana actual. `dow = getDay()` (0=dom…
  6=sáb); días a restar = `(dow + 6) % 7` (dom→6, lun→0, mar→1…). `lunes = now − díasARestar*86400s`,
  luego forzar `HH:MM:SS = 00:00:00`. `from = fmt(lunes 00:00:00)`; `to = fmt(now)`.
  Ej.: si hoy es lunes 2026-06-01 13:39:30 → from `2026-06-01 00:00:00`, to
  `2026-06-01 13:39:30`. Si fuera miércoles 2026-06-03 → from `2026-06-01 00:00:00`.

> **Redondeo de segundos:** los extremos `to` (y `from` de "última hora"/"último día")
> conservan los segundos reales de `now`; solo el `from` de "Desde el lunes" fuerza
> `00:00:00` por definición del atajo (inicio del día). Nada se trunca a minuto.

Al pulsar un atajo, además del cálculo: se pintan los días en el calendario, se
rellenan los inputs de hora del popover y los dos inputs de texto del filtro. Queda
listo para "Aplicar" (no aplica solo).

---

## 7. Localización y accesibilidad

### Localización
- **Nombres de meses y días con `Intl.DateTimeFormat(lang, …)`** usando el `lang`
  activo (`localStorage` `lang`, default `es`; los 25 idiomas del proyecto).
  - Cabecera de mes: `new Intl.DateTimeFormat(lang, { month: 'long', year: 'numeric' })`.
  - Nombres cortos de día (lu, ma, mi…): `Intl.DateTimeFormat(lang, { weekday: 'short' })`
    sobre 7 fechas de referencia, **ordenadas empezando en LUNES**.
- **La semana empieza en LUNES** siempre (independiente del locale), por decisión del
  usuario. El offset de la primera fila se calcula con `(getDay() + 6) % 7`.
- Números de día con numerales occidentales por defecto (alinean en el grid);
  `tabular-nums` para que no "bailen".
- **Cero texto hardcodeado**: labels ("Desde", "Hasta", "Última hora", "Último día",
  "Desde el lunes", "Aplicar rango", "Limpiar", "Elegir rango de fechas", hint "Elige
  la fecha final", mensaje de orden inválido) vía claves de traducción (`useI18n`).

### Accesibilidad (ARIA del grid)
- Contenedor del calendario: `role="grid"`, `aria-label` = "Calendario, <mes año>"
  (localizado). Cada semana: `role="row"`. Cada día: `role="gridcell"` dentro de un
  `<button>` (o `tabindex` roving).
- `aria-selected="true"` en los días `from`/`to` y en los del rango. `aria-current="date"`
  en el día de hoy.
- `aria-label` de cada día = fecha completa localizada:
  `Intl.DateTimeFormat(lang, { weekday:'long', day:'numeric', month:'long', year:'numeric' })`.
- **Roving tabindex**: solo el día activo tiene `tabindex="0"`, el resto `-1`. Flechas
  navegan (ver §4). `Enter`/`Espacio` selecciona.
- Popover: `role="dialog"`, `aria-modal` no estricto (es popover anclado, no bloquea la
  página) pero con **focus trap** vía `useFocusTrap(ref, open)` de `ui/uiUtils.jsx`
  (mismo patrón que `DeletePopover`). Escape cierra y devuelve foco al trigger.
- `prefers-reduced-motion`: desactiva la animación zoom del popover **y la aparición
  suave de las filas de hora** (aparecen/desaparecen sin animar).
- **Filas de hora reveladas progresivamente:** mientras una fila HH:MM:SS está oculta
  lleva `hidden` + `aria-hidden="true"`, de modo que **no se anuncia a lectores de
  pantalla** y sus inputs **quedan fuera del orden de tabulación**. Al revelarse, los
  tres inputs vuelven a ser enfocables y mantienen un orden de tabulación coherente
  (Desde → Hasta, y dentro de cada extremo HH → MM → SS). La aparición no debe robar el
  foco al usuario (no se hace `focus()` automático sobre los inputs al mostrarlos).
- Targets táctiles ≥44px en móvil; foco visible siempre (anillo `--accent`).

---

## 8. Bug de zona horaria — regla dura

El proyecto trata las fechas como **naive verbatim** (ver
`frontend/src/utils/formatDateVerbatim.js`). En este componente:

- **NUNCA** hacer round-trip con `new Date(isoString)` para reconstruir un valor a
  mostrar/escribir: `new Date("2026-05-31T13:39:30")` se interpreta como UTC y se
  desplaza a la zona local → corrompería la hora.
- Los **atajos** calculan `now` con `new Date()` (instante local real) y extraen
  `getFullYear/getMonth/getDate/getHours/getMinutes/getSeconds` **locales**, que se
  formatean a mano a `YYYY-MM-DD HH:MM:SS` (zero-pad). No se usa `toISOString()` (es
  UTC). Las restas (−1h, −24h, lunes) se hacen sobre el `Date` local y se vuelven a
  leer con los getters locales.
- El **parseo** de un input de texto válido para resaltar el calendario se hace por
  string-split (`"YYYY-MM-DD HH:MM:SS".split(...)`), **no** con `new Date(str)`.
  Construir el `Date` solo para navegar meses se hace con `new Date(y, m-1, d)`
  (constructor por-componentes = local, seguro), nunca desde el string ISO.

---

## 9. Inventario de componentes — nuevos vs reutilizados

| Pieza | Nuevo / Reutiliza | Notas |
|---|---|---|
| Popover flotante (trigger + panel `absolute`, zoom, click-fuera, Escape, z-index, `max-w` móvil) | **Reutiliza patrón** de `ui/LangPicker.jsx` | Mismo doble-`rAF`, `transformOrigin`, `--shadow-lg`. |
| `role="dialog"` + focus trap | **Reutiliza** `useFocusTrap` de `ui/uiUtils.jsx` (+ patrón `DeletePopover.jsx`) | Escape devuelve foco al trigger. |
| Inputs de hora `HH:MM:SS` | **Nuevo** componente pequeño, **estilo reutilizado** de `DateFilterInput` (32px, mono, borde rojo en error) | NO `<input type="time">`. |
| Inputs de texto "Desde"/"Hasta" | **Reutiliza** `DateFilterInput` actual de `HistoryFilters.jsx` | Sin cambios de formato; el calendario los escribe. |
| Botón "Aplicar rango" | **Reutiliza** estilo del "Aplicar" actual (primario monocromo invertido) | |
| Botones de atajo (3) | **Nuevo**, estilo **ghost** (transparente + borde, oro al hover) | NO primarios; el oro no va en botones de relleno (regla §4 DESIGN). |
| Grid de calendario (`role=grid`, navegación teclado, rango) | **Nuevo** (no existe date-picker en el repo) | Único componente realmente nuevo de peso. |
| Tokens visuales | **Reutiliza** `tokens.css` (`--surface`, `--surface-2`, `--border`, `--border-strong`, `--shadow-lg`, `--radius-sm/md`, `--accent`, `--accent-subtle`, `--accent-text`, `--dur-fast`, `--font-mono`, `--text*`) | Cero hex hardcodeado. |
| Iconos | **Reutiliza** lucide-react (`Calendar`, `ChevronLeft`, `ChevronRight`, `X`) | Set único, ya en uso (`LangPicker` usa `Globe`/`Check`). |
| Localización | **Reutiliza** `useI18n` + `Intl.DateTimeFormat` | Semana = lunes. |

> El único componente nuevo de envergadura es el **grid de calendario de rango**. Todo
> lo demás reutiliza patrones y estilos existentes.

---

## 10. Criterios de aceptación de diseño (verificables)

1. El filtro mantiene los dos inputs de texto "Desde"/"Hasta" y añade **un** botón de
   calendario que abre **un único** popover de rango.
2. El popover contiene, en este orden: cabecera con título + `×`, los **3** atajos
   (ghost), el calendario de rango con navegación de mes, la sección de hora con los
   inputs `HH:MM:SS` para Desde y Hasta (revelada progresivamente, ver criterio 12), y
   los botones "Limpiar" + "Aplicar rango".
3. Primer clic fija `from`; segundo clic (≥) fija `to` y resalta el rango; segundo
   clic anterior hace **auto-swap**; tercer clic reinicia. Nunca queda `from > to` vía
   calendario.
4. Días intermedios usan `--accent-subtle`; los extremos `from`/`to` usan `--accent`
   con texto invertido. Hoy lleva `aria-current="date"`.
5. Los 3 atajos producen exactamente los `from`/`to` de §6 (segundos reales; "Desde el
   lunes" = lunes 00:00:00, semana empieza lunes), calculados en hora local **sin**
   round-trip UTC.
6. Aplicar escribe `YYYY-MM-DD HH:MM:SS` en los inputs y dispara el mismo `onApply`
   normalizado a ISO; el contrato del endpoint no cambia.
7. "Aplicar"/"Aplicar rango" se deshabilita si hay error de formato o `from > to`.
8. Meses y días vienen de `Intl.DateTimeFormat(lang,…)`; la primera columna es lunes en
   los 25 idiomas; el grid se espeja en RTL (ar/he/fa) con propiedades lógicas.
9. Navegación completa por teclado (flechas en el grid, Enter/Espacio selecciona,
   Escape cierra y devuelve foco al trigger); `role=grid`/`gridcell`/`aria-selected`/
   `aria-current` presentes; foco visible.
10. Funciona en claro y oscuro solo con tokens (cero hex hardcodeado); popover cabe en
    móvil (`max-width: calc(100vw - 32px)`, días ≥44px, inputs de hora ≥16px).
11. `prefers-reduced-motion` desactiva la animación del popover **y la aparición suave
    de las filas de hora**.
12. **Revelado progresivo de las horas:** al abrir sin selección, la sección "Hora" NO
    se muestra; al fijar el primer extremo aparece SOLO la fila "Desde"; al fijar el
    segundo (o al pulsar un atajo, que rellena ambos) aparece también la fila "Hasta";
    al "Limpiar" se vuelven a ocultar. La aparición/desaparición es suave (`--dur-fast`
    /`--dur-base`) sin saltos bruscos de layout. Mientras está oculta, cada fila lleva
    `hidden`+`aria-hidden` (no anunciada a SR, fuera de tabulación); al mostrarse, sus
    inputs son enfocables en orden coherente (Desde antes que Hasta) y no roban el foco.

---

## 11. Estado del spec

**ready-for-impl** — pendiente del gate humano (mockup
`frontend/mockups/calendario-filtro-historial.playground.html`): el usuario recompone
los bloques, aprueba la composición y exporta el layout antes de que
`desarrollador-ux-ui` implemente. `guardian-antideteccion` NO aplica (cambio puramente
de frontend, no toca `adapters/browser/` ni la interacción con Travian).

🔖 Última revisión: 2026-06-01 (DISEÑO APROBADO con un cambio: las filas de hora
HH:MM:SS arrancan OCULTAS y se revelan progresivamente — "Desde" al fijar el primer
extremo, "Hasta" al fijar el segundo o al pulsar un atajo, y se re-ocultan al limpiar;
aparición suave `--dur-fast`/`--dur-base` sin saltos, `hidden`+`aria-hidden` mientras
están ocultas. Mockup y spec actualizados y verificados con uishot. · Versión inicial:
calendario de rango como editor visual de los inputs de texto Desde/Hasta del filtro del
historial; un popover de rango con 3 atajos ghost, inputs HH:MM:SS, semana=lunes, Intl +
RTL, sin round-trip UTC; reutiliza patrón LangPicker/DeletePopover/useFocusTrap; único
componente nuevo de peso = el grid de calendario).
