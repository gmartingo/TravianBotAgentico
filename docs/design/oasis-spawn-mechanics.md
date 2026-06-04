---
id: oasis-spawn-mechanics
titulo: "Mecánica de spawn de oasis: SpawnMechanicsPanel, OasisCombatPlannerPanel (tabla fusionada), reorden StatsTab"
estado: implemented
fecha: 2026-06-02
autor: disenador-producto
spec_funcional_relacionado: docs/specs/oasis-spawn-mechanics-stats.md
spec_diseno_padre: docs/design/bd-ataques-oasis-stats-oasis-nav-ui.md
mockup_editable: frontend/mockups/oasis-spawn-mechanics.playground.html
mockup_aprobado_por_usuario: sí
---

# Mecánica de spawn de oasis — Stats panel v2 + v2.1 (tabla fusionada + reorden)

> **Alcance v2 (implementada 2026-06-02):** tres paneles nuevos en la pestaña Estadísticas:
> `SpawnMechanicsPanel`, `OasisCompositionPanel`, `WorstCasePlannerPanel`.
>
> **Alcance v2.1 (iteración — esta sección):** dos cambios sobre la v2 implementada:
> 1. **Tabla fusionada** — `OasisCompositionPanel` y `WorstCasePlannerPanel` se fusionan
>    en un único panel `OasisCombatPlannerPanel` (una fila por animal, por oasis, con
>    datos de composición típica Y peor combo, bajo un selector de intervalo único).
> 2. **Reorden de la pestaña Estadísticas** al orden pedido por el usuario.
>
> Las pestañas Ingresar e Historial no cambian. El spec padre es la referencia para
> el shell, tokens y patrones transversales.

---

## v2.1 — ITERACIÓN: tabla fusionada + reorden StatsTab

> Esta sección documenta los cambios de la iteración v2.1. Las secciones del spec
> original (§1-§14) se actualizan a continuación para reflejar el estado tras la
> iteración. Lo que no cambia se mantiene igual.

### v2.1.1 — Nuevo orden de la pestaña Estadísticas

**Orden pedido por el usuario (de arriba a abajo):**

```
1. SpawnMechanicsPanel      ← leyenda / educativo / colapsable
2. BalanceSection           ← pérdidas/ganancias del mundo (panel existente)
3. OasisCombatPlannerPanel  ← tabla fusionada (composición típica + peor combo)
4. GlobalOasisStatsPanel    ← apariciones globales (panel existente — arrastrable)
5. OasisList                ← lista navegable de oasis (panel existente — arrastrable)
```

Los paneles 4 y 5 se conservan. En el mockup se marcan como arrastrables para que el
usuario decida si los conserva, mueve o quita. No se rediseñan.

**Cambio respecto a v2:** `BalanceSection` sube al puesto 2 (antes estaba detrás de los
tres paneles nuevos). Los paneles de composición y peor caso se fusionan en uno solo
(puesto 3). `GlobalOasisStatsPanel` y `OasisList` pasan al final.

### v2.1.2 — Panel fusionado: OasisCombatPlannerPanel

**Nombre propuesto:** `OasisCombatPlannerPanel`

Razón del nombre: unifica la visión operativa ("cuántos animales típicos") y la
táctica ("cuánta defensa tengo que superar en el peor caso"), que son las dos
preguntas que el jugador hace antes de un ataque. "Combat Planner" captura esa
intención sin solapamiento con el nombre del panel educativo.

#### Estructura del panel

```
┌──────────────────────────────────────────────────────────────────────┐
│  Planificador de combate por oasis                                    │
│  ─────────────────────────────────────────────────────────────────   │
│                                                                      │
│  Intervalo de envío:  [ 6 min ]  [ 7 min ]  [● 10 min]  [ 15 min ]  │
│                                              (activo = oro)          │
│                                                                      │
│  ┌── Oasis (−70|73)  [🌾 Cereal] ·med  ● Repoblando ─────────────┐  │
│  │                                                                 │  │
│  │ ┌──────────┬──────────────┬──────────────────┬──────┬────────┐ │  │
│  │ │  Animal  │  Típica      │  Peor combo       │ Def.inf│Def.cav│ │  │
│  │ │          │  avg · máx   │  worst_count      │      │       │ │  │
│  │ ├──────────┼──────────────┼──────────────────┼──────┼────────┤ │  │
│  │ │🐯 Tigre  │   4.5 · 7   │        ×5         │  800 │ 1 000  │ │  │
│  │ │🐘 Elef.  │   2.0 · 3   │        ×3         │ 1 020│ 1 260  │ │  │
│  │ │🐻 Oso    │   1.0 · 1   │  [anom.] —        │  —   │  —     │ │  │
│  │ ├──────────┴──────────────┴──────────────────┴──────┴────────┤ │  │
│  │ │                        Def. total:  inf 1 820  cav 2 260   │ │  │
│  │ └─────────────────────────────────────────────────────────────┘ │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌── Oasis (−12|50)  [🧱 Arcilla] ·low  ● Cooldown ─────────────┐  │
│  │ … (misma tabla por animal) …                                   │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌── Oasis ( 12|−45)  [—]  ⬤ Desconocido ───────────────────────┐  │
│  │  Sin tipo inferido — añade más reportes para ver el peor caso  │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  [ⓘ] Los animales anómalos no se incluyen en el peor caso.          │
└──────────────────────────────────────────────────────────────────────┘
```

#### Columnas de la tabla por animal

| Columna | Contenido | Prioridad | Tipografía |
|---|---|---|---|
| **Animal** | `NatureIcon` (ordinal, size 15) + nombre localizado | P1 siempre | body 13px |
| **Típica (avg · máx)** | `avg_present_per_burst` · `max_present_per_burst` (p.ej. `4.5 · 7`) | P1 siempre | `--font-mono` + `tabular-nums` |
| **Peor combo** | `worst_case_count` (p.ej. `×5`). Si `is_anomaly=true`: badge "anom." + "—" | P1 siempre | `--font-mono` chip |
| **Def. inf.** | `def_infantry_contribution` por animal (entero) | P2 colapsa en `<md` | `--font-mono` + `tabular-nums`, `text-end` |
| **Def. cav.** | `def_cavalry_contribution` por animal (entero) | P2 colapsa en `<md` | `--font-mono` + `tabular-nums`, `text-end` |

#### Cabecera de grupo (por oasis)

```
[coords mono]  [OasisTypeBadge: tipo + confianza]  [SpawnStatusDot: color + texto]
```

- Fondo `--surface-2`, `border-bottom: 1px solid var(--border)`, `padding: 8px 12px`.
- Coordenadas: `--font-mono` / 12px / `--text`.
- Badge de tipo: igual que v2 (`badge-accent` si hay tipo, "—" en `--text-tertiary` si null).
- Confianza: texto secundario `·low` / `·med` en `--text-tertiary` / 10px.
- SpawnStatusDot: punto 7px + texto 12px (verde/rojo/gris). Siempre texto + color.

#### Fila de totales (pie de grupo)

```
│                   Def. total:   inf  X XXX   cav  X XXX   │
```

- `background: var(--surface-2)`, `border-top: 1px solid var(--border)`.
- Label "Def. total:" en `--text-secondary` / 12px.
- Valores en `--font-mono` / 13px / `font-weight: 600` / `tabular-nums`.
- Si el oasis no tiene tipo inferido: la fila de totales no se muestra (no hay datos que sumar).
- Los animales con `is_anomaly = true` (sus `def_*_contribution` son `null`) no se suman.
  El total solo suma las filas con valor numérico real.

#### Estados especiales de fila de animal

| Situación | Visualización |
|---|---|
| `is_anomaly = true` | Badge "anom." en acento oro en col Animal; col "Peor combo" muestra "—" en `--text-disabled`; cols Def. muestran "—" en `--text-disabled`; no suma en totales |
| Animal nunca observado | No aparece como fila (igual que v2, RN-COMP-02) |
| `worst_case_count = null` (oasis sin tipo) | Toda la fila del oasis muestra nota inline, sin tabla de animales |

#### Oasis con tipo desconocido (inferred_type = null)

La cabecera del grupo se muestra igual (coords + "—" + gris "Desconocido"). En lugar de la
tabla de animales, se muestra un único mensaje inline:

```
┌── Oasis ( 12|−45)  [—]  ⬤ Desconocido ───────────────────────────┐
│  [ⓘ] Sin tipo inferido — añade más reportes para ver el peor caso  │
└───────────────────────────────────────────────────────────────────┘
```

Si el oasis tiene datos de composición (avg/max de animales) pero no de peor combo:
mostrar la tabla con las columnas "Típica" rellenas y "Peor combo" / "Def.*" con "—".
Esto ocurre cuando hay `species[]` con `avg_present_per_burst` pero `worst_case_count = null`
(porque `inferred_type = null` impide calcular el peor caso).

#### Estados del panel completo

| Estado | Descripción | Trigger |
|---|---|---|
| Loading | Selector deshabilitado + skeleton de grupos | Carga inicial o cambio de intervalo |
| Error | Banner rojo + Reintentar (bajo el selector) | Error HTTP |
| Vacío | Selector deshabilitado + empty state con CTA "Ir a Ingresar" | `oasis: []` |
| Normal | Selector activo + grupos por oasis | `oasis.length > 0` |
| Tipo desconocido (fila de oasis) | Cabecera + nota inline sin tabla | `inferred_type: null` en un oasis |

#### Responsive móvil (jerarquía P1/P2/P3)

| Breakpoint | Comportamiento |
|---|---|
| `< md` | La tabla por animal colapsa: columnas Def. inf. y Def. cav. se ocultan (P2). La fila de totales se contrae a una sola línea `Def: inf X XXX / cav X XXX`. El `TimerSelector` siempre visible (P1). Cada grupo de oasis mantiene su cabecera visible (P1). |
| `< sm` | Formato tarjeta por animal: Animal (P1) + Típica (P1) + Peor combo (P1). Totales al pie de tarjeta (P2). Def. por animal se oculta (P3). |
| `≥ md` | Tabla completa, 5 columnas, totales al pie de cada grupo. |

Primera columna sticky en scroll horizontal si la tabla lo necesita: columna "Animal".

#### Microcopy nuevo (claves i18n)

| Clave i18n | Texto ES de referencia |
|---|---|
| `stats.combat.panel_title` | "Planificador de combate por oasis" |
| `stats.combat.interval_label` | "Intervalo de envío:" |
| `stats.combat.col_animal` | "Animal" |
| `stats.combat.col_typical` | "Típica (avg · máx)" |
| `stats.combat.col_worst` | "Peor combo" |
| `stats.combat.col_def_inf` | "Def. inf." |
| `stats.combat.col_def_cav` | "Def. cav." |
| `stats.combat.def_total_label` | "Def. total:" |
| `stats.combat.def_inf_abbr` | "inf" |
| `stats.combat.def_cav_abbr` | "cav" |
| `stats.combat.no_type_note` | "Sin tipo inferido — añade más reportes para ver el peor caso" |
| `stats.combat.anomaly_note` | "Los animales anómalos no se incluyen en el peor caso." |
| `stats.combat.empty_title` | "Sin oasis con reportes" |
| `stats.combat.empty_body` | "Ingresa reportes de ataques para ver la composición y la peor combinación." |
| `stats.combat.empty_cta` | "Ir a Ingresar →" |
| `stats.combat.error` | "Error al cargar los datos de combate." |
| `stats.combat.retry` | "Reintentar" |

### v2.1.3 — Componentes: fusión y eliminación

**OasisCompositionPanel** y **WorstCasePlannerPanel** se fusionan en **OasisCombatPlannerPanel**.
Los dos componentes anteriores quedan **eliminados** del árbol de producción.

| Componente | Acción | Detalle |
|---|---|---|
| `OasisCompositionPanel` | ELIMINAR | Sustituido por `OasisCombatPlannerPanel` |
| `WorstCasePlannerPanel` | ELIMINAR | Sustituido por `OasisCombatPlannerPanel` |
| `OasisCombatPlannerPanel` | CREAR | Panel fusionado — ver §v2.1.2 |
| `SpawnMechanicsPanel` | SIN CAMBIO | Se mantiene igual |
| `TimerSelector` | REUTILIZAR | Existente, props idénticas |
| `SpawnStatusDot` | REUTILIZAR | Existente, sin cambio |
| `OasisTypeBadge` | REUTILIZAR | Existente, sin cambio |
| `AnimalCompositionChip` | ELIMINAR | Ahora es una fila de tabla, no un chip inline |
| `WorstCaseChip` | ELIMINAR | Ahora es la columna "Peor combo" de la misma fila |
| `NatureIcon` | REUTILIZAR | En la columna Animal de cada fila |

**Motivo de eliminar `AnimalCompositionChip` y `WorstCaseChip`:** al fusionar en tabla,
los chips por animal se convierten en filas. Los mismos datos (avg/max, worst_count) ahora
van en columnas de la fila, no en chips independientes. Mantener los chips introduciría
redundancia visual y haría la tabla inconsistente.

**`StatsTab.jsx`** se actualiza para el nuevo orden:
1. `SpawnMechanicsPanel`
2. `BalanceSection`
3. `OasisCombatPlannerPanel` (único fetch a EP-SPAWN con `?timer_min=N`)
4. `GlobalOasisStatsPanel`
5. `OasisList`

El estado `timerMin` (y el fetch de EP-SPAWN) que antes se compartía entre
`OasisCompositionPanel` y `WorstCasePlannerPanel` ahora reside solo en
`OasisCombatPlannerPanel` (se gestiona internamente).

### v2.1.4 — Criterios de aceptación de diseño (delta v2.1)

- [ ] El orden de paneles en StatsTab es: SpawnMechanicsPanel → BalanceSection → OasisCombatPlannerPanel → GlobalOasisStatsPanel → OasisList.
- [ ] `OasisCombatPlannerPanel` tiene un único `TimerSelector` en la cabecera (no uno por panel).
- [ ] La tabla tiene una fila por animal dentro de cada grupo de oasis.
- [ ] La cabecera de grupo muestra coordenadas + tipo inferido/badge + confianza + SpawnStatusDot (todo en una línea).
- [ ] La fila de totales de def. inf/cav aparece como pie de cada grupo, con fondo `--surface-2`.
- [ ] Los animales con `is_anomaly=true` muestran "—" en columnas Peor combo y Def., con badge "anom." visible.
- [ ] Los totales de grupo no suman filas anómalas.
- [ ] Los oasis con `inferred_type=null` muestran la nota inline en lugar de la tabla de animales.
- [ ] Si el oasis tiene `species[]` con `avg/max` pero `worst_case_count=null`, las columnas Típica se rellenan y las de peor combo/def. muestran "—".
- [ ] En `<md`: las columnas Def. inf. y Def. cav. se ocultan; la fila de totales se contrae a una línea.
- [ ] El selector de intervalo permanece habilitado durante la carga (el usuario puede cambiar mientras llega la respuesta).
- [ ] La carga del panel es independiente de `BalanceSection`, `GlobalOasisStatsPanel` y `OasisList` (fallo aislado).
- [ ] Cero texto hardcodeado: todas las nuevas claves `stats.combat.*` en los 25 catálogos.
- [ ] Propiedades CSS lógicas en toda la tabla fusionada (RTL-safe).

### v2.1.5 — Trazabilidad (delta v2.1)

| Decisión de diseño | Origen |
|---|---|
| Fusionar OasisCompositionPanel + WorstCasePlannerPanel en un panel | Cambio 1 explícito del usuario — misma fuente de datos, flujo de lectura más natural (una fila = un animal con todos sus datos) |
| Nombre "OasisCombatPlannerPanel" | Captura la intención táctica del panel fusionado; "Combat Planner" comunica que es para planificar el ataque |
| Totales como fila de pie de grupo (no columna separada) | Evita añadir una columna extra para un único valor; el pie de grupo es el patrón natural de tablas de resumen (tabla densa DESIGN.md §12) |
| Anomalías: "—" en Peor combo y Def., badge visible, no suman en totales | RN-WORST-05 (anomalías excluidas del peor caso); visualmente la anomalía sigue siendo visible sin contaminar la cifra táctica |
| Oasis tipo desconocido: nota inline, sin tabla | Si no hay tipo no hay peor combo; mostrar una tabla vacía confunde más que una nota corta |
| Oasis con species pero sin worst_case: cols Típica rellenas, cols Peor/Def con "—" | Los datos parciales son mejores que ocultarlos; el usuario ve que sí tiene historial aunque el planeador no esté disponible |
| Orden: BalanceSection en posición 2 | Cambio 2 explícito del usuario — quiere ver pérdidas/ganancias antes de la tabla de combate |
| GlobalOasisStatsPanel y OasisList se mantienen al final como arrastrables | El usuario no los mencionó explícitamente → se conservan pero se dejan arrastrables para que decida |
| TimerSelector único (no uno por panel) | Al fusionar los dos paneles el selector que controlaba WorstCase ahora controla el panel completo; mantener uno reduce la carga cognitiva |

---

## v2.2 — Panel de combinaciones simplificado (iteración sobre v2.1)

> **Fecha:** 2026-06-02. **Autor:** desarrollador-ux-ui (iteración pedida por el usuario
> tras prueba visual de la v2.1 implementada).

### Cambios respecto a v2.1

#### v2.2.1 — Nuevo orden de StatsTab (cambio 1)

Orden implementado (definitivo):

```
1. SpawnMechanicsPanel      ← leyenda / educativo / colapsable
2. BalanceSection           ← pérdidas/ganancias del mundo
3. OasisCombatPlannerPanel  ← planificador (dos filas compactas: Media/Peor)
4. GlobalOasisStatsPanel    ← apariciones globales
5. OasisList                ← lista navegable
```

#### v2.2.2 — OasisCombatPlannerPanel simplificado (cambio 2)

Reemplaza tanto `OasisCompositionPanel` como `WorstCasePlannerPanel` (y el diseño en
tabla por animal del spec v2.1). La estructura **no es una tabla de 5 columnas** sino
dos filas de chips compactos por oasis:

**Cabecera de cada oasis:**
```
(coord_x|coord_y)  [TipoBadge · confianza]  ● Estado (texto siempre)
```

**Selector de intervalo único** (6 / 7 / 10 / 15 min) arriba del panel, controla la
fila "Peor" de TODOS los oasis. Pill activo en acento oro.

**Dos filas de chips por oasis** (nada de tabla ancha):
- Fila **"Media"** (etiqueta `stats.planner.row_media`): por cada animal con
  `avg_present_per_burst != null` o `max_present_per_burst != null`, un chip
  `NatureIcon + max_present_per_burst`. Las anomalías aparecen aquí con badge "anom."
  en acento oro.
- Fila **"Peor"** (etiqueta `stats.planner.row_worst`): por cada animal NO anómalo con
  `worst_case_count != null`, un chip `NatureIcon + worst_case_count` como **número
  plano sin "×"**. Las anomalías no aparecen en esta fila.

**Eliminado por completo:** columnas/resumen de fuerza defensiva
(`def_infantry_contribution`, `def_cavalry_contribution`, totales de grupo).
El backend sigue enviando estos campos; simplemente no se pintan.

**Por qué el "×N" generaba confusión:** el usuario interpretó "×5" como un
multiplicador (12 ratas × 5 = 60). En realidad `worst_case_count` es un conteo
absoluto (animales en el peor caso para ese intervalo). Se muestra como número plano
para eliminar la ambigüedad.

#### v2.2.3 — Componentes

| Componente | Acción | Fichero |
|---|---|---|
| `OasisCombatPlannerPanel` | CREADO | `frontend/src/components/attack-reports/OasisCombatPlannerPanel.jsx` |
| `OasisCompositionPanel` | ELIMINADO | — |
| `WorstCasePlannerPanel` | ELIMINADO | — |
| `StatsTab` | MODIFICADO | nuevo orden + usa `OasisCombatPlannerPanel` |

#### v2.2.4 — Claves i18n nuevas (`stats.planner.*`)

| Clave | ES | EN |
|---|---|---|
| `stats.planner.panel_title` | "Planificador de combate por oasis" | "Combat planner per oasis" |
| `stats.planner.interval_label` | "Intervalo de envío:" | "Send interval:" |
| `stats.planner.row_media` | "Media" | "Avg" |
| `stats.planner.row_worst` | "Peor" | "Worst" |
| `stats.planner.no_type_note` | "Sin tipo inferido — añade más reportes para ver el peor caso" | "No type inferred…" |
| `stats.planner.anomaly_note` | "Los animales anómalos no se incluyen en la fila Peor." | "Anomalous animals…" |
| `stats.planner.empty_title` | "Sin oasis con reportes" | "No oasis with reports" |
| `stats.planner.empty_body` | "Ingresa reportes de ataques…" | "Enter attack reports…" |
| `stats.planner.empty_cta` | "Ir a Ingresar →" | "Go to Enter →" |
| `stats.planner.error` | "Error al cargar los datos de combate." | "Error loading combat data." |
| `stats.planner.retry` | "Reintentar" | "Retry" |

Presentes en los 25 catálogos. ES/EN con calidad; resto con texto inglés como fallback.

#### v2.2.5 — Estados del panel (igual que v2.1, sin cambio de lógica)

| Estado | Trigger |
|---|---|
| Loading | Carga inicial o cambio de intervalo |
| Error + Reintentar | Error HTTP |
| Vacío + CTA | `oasis: []` |
| Normal | `oasis.length > 0` |
| Oasis sin tipo (`inferred_type=null`) | Nota inline, sin fila Peor |
| Animal nunca visto | Ausente (no 0) |

---

## 1. Visión de la experiencia y principios de diseño

### Problema

La métrica actual `avg_regen_per_hour` mezcla conceptos incompatibles (ráfaga de spawn
+ cooldown) y produce un número que no sirve para tomar decisiones tácticas. El usuario
no sabe qué animales esperarle al próximo ataque, cuántos hay que matar, ni si el oasis
está en cooldown o generando activamente.

### Visión

Tres paneles que se complementan sin solaparse:

1. **SpawnMechanicsPanel** — panel educativo/estático que explica la mecánica del juego
   una vez y se puede plegar. Es consulta, no monitorización.
2. **OasisCompositionPanel** — para cada oasis, qué animales salen (avg/max), qué tipo
   de oasis se infiere, y si está en cooldown o repoblando.
3. **WorstCasePlannerPanel** — dado un intervalo de envío (6/7/10/15 min), qué peor
   combinación puede salirle al usuario y cuánta defensa debe superar.

### Principios aplicados (de `frontend/DESIGN.md`)

- **Divulgación progresiva**: SpawnMechanicsPanel empieza colapsado (el usuario ya sabe
  la mecánica tras la primera visita). OasisCompositionPanel y WorstCasePlannerPanel son
  operativos y siempre visibles.
- **Contenido primero**: el tipo inferido y el estado cooldown/respawn son la primera
  información visible por oasis, no el último dato en una tabla.
- **Datos, no formulario**: WorstCasePlannerPanel tiene un único selector prominente
  (el intervalo) como única acción del usuario; todo lo demás son datos.
- **Tabla densa**: herramienta interna — densidad máxima sobre decoración.
- **Una acción principal por sección**: en WorstCasePlannerPanel la acción es elegir el
  intervalo. En SpawnMechanicsPanel la acción es plegar/desplegar. En
  OasisCompositionPanel no hay acciones (es solo lectura).

---

## 2. Personas y objetivos (jobs-to-be-done)

Persona única: operador del bot. Sin cambios respecto al spec padre.

| Job | Frecuencia | Necesidad de diseño |
|---|---|---|
| Saber si el oasis está generando o en cooldown antes de atacar | Alta | Badge spawn_status prominente en OasisCompositionPanel |
| Conocer la composición típica de un oasis (qué animales salen y cuántos) | Alta | Tabla avg/max por animal en OasisCompositionPanel |
| Dimensionar el equipo de ataque para el peor caso en un intervalo dado | Media | WorstCasePlannerPanel con selector de intervalo + resumen def. inf/cav |
| Entender la mecánica de spawn (timers fijos, sets, anomalías) | Baja / primera vez | SpawnMechanicsPanel colapsable (no ocupa espacio al usuario experimentado) |
| Identificar animales fuera del set normal (anomalías) | Esporádico | Badge "anomalía" en la tabla de composición |

---

## 3. Inventario de pantallas / vistas

La feature sigue viviendo en `AttackReportsPage` → pestaña "Estadísticas" (`StatsTab`).
Solo añade tres paneles al contenido del tab:

| Vista | Componente nuevo | Descripción |
|---|---|---|
| SpawnMechanicsPanel — normal | `SpawnMechanicsPanel` | Tabla de 10 animales con timer, sets por tipo, definición de anomalía |
| SpawnMechanicsPanel — colapsado | `SpawnMechanicsPanel` | Solo header visible (chevron para desplegar) |
| OasisCompositionPanel — loading | `OasisCompositionPanel` | Skeleton de filas |
| OasisCompositionPanel — error | `OasisCompositionPanel` | Banner rojo + Reintentar |
| OasisCompositionPanel — vacío | `OasisCompositionPanel` | CTA "Ingresar reportes" |
| OasisCompositionPanel — normal | `OasisCompositionPanel` | Tabla de oasis con tipo, estado, composición |
| OasisCompositionPanel — oasis tipo desconocido | `OasisCompositionPanel` | Fila con tipo "—" y estado "desconocido" |
| OasisCompositionPanel — animal anomalía | `OasisCompositionPanel` | Badge "anomalía" en celda de animal |
| WorstCasePlannerPanel — loading | `WorstCasePlannerPanel` | Skeleton |
| WorstCasePlannerPanel — error | `WorstCasePlannerPanel` | Banner rojo + Reintentar |
| WorstCasePlannerPanel — vacío | `WorstCasePlannerPanel` | Sin datos — sin selector activo |
| WorstCasePlannerPanel — normal | `WorstCasePlannerPanel` | Selector activo + tabla peor combinación + resumen def. |
| WorstCasePlannerPanel — tipo no inferible | `WorstCasePlannerPanel` | Fila con "—" y mensaje "añade más reportes" |

---

## 4. Mapa de navegación

```mermaid
flowchart TD
    TAB3[Tab: Estadísticas] --> SPAWN_STATIC[SpawnMechanicsPanel — estático]
    TAB3 --> COMP_LOAD[GET /attack-reports/stats/oasis/spawn-composition?timer_min=N]
    TAB3 --> WORST_LOAD[mismo endpoint con ?timer_min=N elegido]

    SPAWN_STATIC -->|toggle cabecera| SPAWN_COLLAPSED[SpawnMechanicsPanel colapsado]
    SPAWN_COLLAPSED -->|toggle cabecera| SPAWN_STATIC

    COMP_LOAD -->|200 oasis>0| COMP_NORMAL[OasisCompositionPanel — tabla de oasis]
    COMP_LOAD -->|200 oasis=0| COMP_EMPTY[Estado vacío — CTA ingresar reportes]
    COMP_LOAD -->|error| COMP_ERR[Banner error + Reintentar]

    COMP_NORMAL -->|oasis.inferred_type=null| COMP_UNKNOWN[Fila tipo desconocido]
    COMP_NORMAL -->|species[i].is_anomaly=true| COMP_ANOMALY[Badge anomalía en celda]

    WORST_LOAD -->|200 oasis>0| WORST_NORMAL[WorstCasePlannerPanel — tabla peor caso]
    WORST_LOAD -->|200 oasis=0| WORST_EMPTY[Estado vacío]
    WORST_LOAD -->|error| WORST_ERR[Banner error + Reintentar]

    WORST_NORMAL -->|usuario cambia intervalo| WORST_LOAD
    WORST_NORMAL -->|oasis.worst_case_summary=null| WORST_NULL[Fila — añade más reportes]

    subgraph Paneles existentes sin cambio
        BAL[BalanceSection]
        GLOB[GlobalOasisStatsPanel]
        OLIST[OasisList]
    end

    TAB3 --> BAL
    TAB3 --> GLOB
    TAB3 --> OLIST
```

---

## 5. Flujos de usuario clave

### 5.1 Happy path — usuario abre la pestaña Estadísticas

1. `StatsTab` monta. Todos los paneles cargan en paralelo de forma independiente.
2. `SpawnMechanicsPanel` renderiza inmediatamente (datos estáticos del catálogo importado).
   Empieza colapsado en la segunda visita (persiste en localStorage la preferencia).
3. `OasisCompositionPanel` y `WorstCasePlannerPanel` muestran skeleton mientras llega la API.
   El selector de intervalo empieza en 10 min (valor por defecto razonable).
4. Cuando llega la respuesta, ambos paneles se renderizan con los datos.
5. Usuario ve por cada oasis: tipo inferido (badge con confianza), estado
   (punto verde/rojo/gris + texto), y columnas avg/max por animal.

### 5.2 Usuario cambia el intervalo de timer

1. Usuario hace clic en uno de los 4 botones de intervalo (6 / 7 / 10 / 15 min).
2. `WorstCasePlannerPanel` entra en estado loading (skeleton).
3. Se llama al endpoint con el nuevo `?timer_min=N`.
4. La tabla se actualiza con el nuevo peor caso.
5. El resumen defensivo (inf/cav total) se actualiza acorde.

### 5.3 Alternativo — BD vacía

1. Endpoint devuelve `oasis: []`.
2. `OasisCompositionPanel` muestra estado vacío: icono + texto "Sin oasis con reportes"
   + botón "Ir a Ingresar".
3. `WorstCasePlannerPanel` muestra estado vacío: el selector está deshabilitado.
4. `SpawnMechanicsPanel` se despliega automáticamente (es educativo y el usuario no tiene
   datos aún — tiene sentido leerlo).

### 5.4 Alternativo — oasis sin tipo inferido

1. La fila del oasis en `OasisCompositionPanel` muestra tipo "—" sin badge de confianza.
2. Estado: gris con texto "Desconocido".
3. En `WorstCasePlannerPanel`, la fila del mismo oasis muestra "—" en worst_case_count y
   una nota inline "Añade más reportes para inferir el tipo".

### 5.5 Alternativo — error de carga

1. Uno de los dos paneles (Composition o WorstCase) falla.
2. El panel afectado muestra banner de error + Reintentar.
3. El otro panel sigue funcionando (carga independiente).
4. `SpawnMechanicsPanel` siempre se muestra (es estático).

---

## 6. Wireframes de baja fidelidad por pantalla

### 6.1 Orden de paneles en StatsTab (de arriba a abajo)

```
┌────────────────────────────────────────────────────────────────────┐
│  H2: Estadísticas de oasis                                         │
│                                                                    │
│  [SpawnMechanicsPanel — colapsable]                  ← educativo   │
│                                                                    │
│  [OasisCompositionPanel]                             ← operativo   │
│                                                                    │
│  [WorstCasePlannerPanel]                             ← operativo   │
│                                                                    │
│  ── separador ──────────────────────────────────────               │
│                                                                    │
│  [BalanceSection]                        ← paneles existentes      │
│  [GlobalOasisStatsPanel]                                           │
│  [OasisList]                                                       │
└────────────────────────────────────────────────────────────────────┘
```

Decisión de orden: los dos paneles operativos (Composition + WorstCase) van delante de
los paneles existentes porque son la nueva funcionalidad principal. SpawnMechanicsPanel
va primero porque da el contexto conceptual que hace los otros dos comprensibles.

### 6.2 SpawnMechanicsPanel — colapsado (estado habitual)

```
┌─────────────────────────────────────────────────────────────────────┐
│  ▶  Mecánica de spawn de oasis  ·  [caption: "Cómo funciona..."]   │
└─────────────────────────────────────────────────────────────────────┘
```

- El header es clickable (rol button con aria-expanded).
- Chevron rota 90° al desplegar (transición `--dur-base`).
- Texto caption en `--text-tertiary` / 12px.

### 6.3 SpawnMechanicsPanel — desplegado

```
┌─────────────────────────────────────────────────────────────────────┐
│  ▼  Mecánica de spawn de oasis                                      │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                     │
│  Timers de aparición (servidor x1)                                  │
│  ┌──────────┬───────────────┬──────────────┐                       │
│  │  Animal  │  Orden spawn  │  Timer (min)  │                       │
│  ├──────────┼───────────────┼──────────────┤                       │
│  │ 🐀 Rata  │      1        │     5:00      │                       │
│  │ 🕷 Araña │      2        │     6:00      │                       │
│  │ 🐍 Serp. │      3        │     7:00      │                       │
│  │ 🦇 Murc. │      4        │     8:00      │                       │
│  │ 🐗 Jabal.│      5        │     9:00      │                       │
│  │ 🐺 Lobo  │      6        │    10:00      │                       │
│  │ 🐻 Oso   │      7        │    11:00      │                       │
│  │ 🐊 Croc. │      8        │    12:00      │                       │
│  │ 🐯 Tigre │      9        │    13:00      │                       │
│  │ 🐘 Elef. │     10        │    14:00      │                       │
│  └──────────┴───────────────┴──────────────┘                       │
│                                                                     │
│  Sets normales por tipo de oasis                                    │
│  ┌──────────────┬────────────────────────────────────────┐         │
│  │  Hierro      │  Rata · Araña · Murciélago              │         │
│  │  Arcilla     │  Rata · Araña · Jabalí                  │         │
│  │  Madera      │  Jabalí · Lobo · Oso                    │         │
│  │  Cereal      │  Todos (rata → elefante)                │         │
│  └──────────────┴────────────────────────────────────────┘         │
│                                                                     │
│  [ⓘ] Anomalía: animal observado fuera del set del tipo inferido.   │
│       Puede aparecer esporádicamente. No se incluye en el peor      │
│       caso ya que distorsionaría el umbral defensivo.               │
└─────────────────────────────────────────────────────────────────────┘
```

- Icono de animal: `NatureIcon` (ya existe) con `size=16`.
- Timer en `--font-mono` + `tabular-nums`.
- Sets de oasis: chips de iconos `NatureIcon` + nombre localizado.
- Nota de anomalía: icono info (`--info`) + texto en `--text-secondary` / 12px.

### 6.4 OasisCompositionPanel — normal (con datos)

```
┌─────────────────────────────────────────────────────────────────────┐
│  Composición típica por oasis                                        │
│  ─────────────────────────────────────────────────────────────────  │
│  ┌──────────┬────────────────┬────────┬──────────────────────────┐  │
│  │  Oasis   │  Tipo / Conf.  │ Estado │  Composición (avg · máx)  │  │
│  ├──────────┼────────────────┼────────┼──────────────────────────┤  │
│  │(−70|73)  │ [Cereal] ●med  │ 🟢Rep. │ 🐯 4.5·7  🐘 2.0·3       │  │
│  │          │                │        │ (12 ataques · hace 12h)   │  │
│  ├──────────┼────────────────┼────────┼──────────────────────────┤  │
│  │( 12|−45) │  [—]           │ ⬤Desc. │  Sin datos suficientes    │  │
│  │          │                │        │ (1 ataque)                │  │
│  └──────────┴────────────────┴────────┴──────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

Columnas:
- **Oasis**: coordenadas en `--font-mono`, formato `(X|Y)` con guión largo.
- **Tipo / Conf.**: badge de tipo (`[Cereal]`) + indicador de confianza (·low / ·med).
  Cuando tipo = null: "—".
- **Estado**: punto de color + texto. Verde = respawnando, Rojo = cooldown, Gris = desconocido.
- **Composición**: chips compactos `NatureIcon + avg · max` para cada animal observado.
  Los animales con `is_anomaly=true` llevan badge "A" (anomalía). Texto secundario:
  `N ataques · hace Xh Xm`.

En móvil: las columnas colapsan. Fila de coords+estado visible siempre (P1). Tipo y
composición detrás de un "expandir" (P2).

### 6.5 OasisCompositionPanel — vacío

```
┌─────────────────────────────────────────────────────────────────────┐
│  Composición típica por oasis                                        │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                     │
│       📋  Sin oasis con reportes                                    │
│           Ingresa reportes de ataques para ver la composición        │
│           típica de tus oasis.                                      │
│                                                                     │
│           [Ir a Ingresar →]                                         │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

- Icono `--text-tertiary`, texto `--text-secondary`.
- CTA: botón primario (monocromo).

### 6.6 WorstCasePlannerPanel — normal

```
┌─────────────────────────────────────────────────────────────────────┐
│  Peor combinación a batir                                            │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                     │
│  Intervalo de envío:  [ 6 min ]  [ 7 min ]  [●10 min]  [ 15 min ]  │
│                                              (activo=oro)           │
│                                                                     │
│  ┌──────────┬────────────┬───────────────────────────┬───────────┐  │
│  │  Oasis   │  Tipo      │  Peor combo (animal · N)  │ Def total  │  │
│  ├──────────┼────────────┼───────────────────────────┼───────────┤  │
│  │(−70|73)  │ [Cereal]   │ 🐯×5  🐘×3               │ inf: 2020  │  │
│  │          │            │                            │ cav: 2560  │  │
│  ├──────────┼────────────┼───────────────────────────┼───────────┤  │
│  │( 12|−45) │  [—]       │  Añade más reportes        │    —       │  │
│  └──────────┴────────────┴───────────────────────────┴───────────┘  │
│                                                                     │
│  [ⓘ] Los animales anómalos no se incluyen en el peor caso.         │
└─────────────────────────────────────────────────────────────────────┘
```

- Selector de intervalo: 4 botones pill (no dropdown). El activo en `--accent-subtle`
  con borde `--accent` y texto `--accent-text`. Los inactivos en `--surface-2`.
- Peor combo: chips `NatureIcon + ×N` separados por espacio.
- Def. infantería/caballería: `--font-mono` + `tabular-nums`.
- Oasis con `worst_case_summary=null`: "Añade más reportes" en `--text-secondary`.

### 6.7 WorstCasePlannerPanel — vacío

```
┌─────────────────────────────────────────────────────────────────────┐
│  Peor combinación a batir                                            │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                     │
│  Intervalo de envío:  [ 6 ]  [ 7 ]  [ 10 ]  [ 15 ]  (deshabilitado)│
│                                                                     │
│       Sin datos para calcular el peor caso.                         │
│       Ingresa reportes de ataques para ver la peor combinación.     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

- Los botones de intervalo aparecen pero deshabilitados (opacity 0.4, cursor not-allowed).
- Mismo CTA que OasisCompositionPanel vacío si el usuario no tiene reportes en absoluto.

---

## 6b. Mockup editable y layout aprobado

**Ruta:** `frontend/mockups/oasis-spawn-mechanics.playground.html`

**Estado v2 (implementada):** aprobado.

**Estado v2.1 (iteración):** pendiente de aprobación del usuario (gate humano).

### Vistas del mockup v2.1 (actualizado)

El mockup incluye las vistas originales (v1–v10) más las nuevas vistas de la iteración:

- v12: OasisCombatPlannerPanel — loading (skeleton bajo selector)
- v13: OasisCombatPlannerPanel — error (banner bajo selector)
- v14: OasisCombatPlannerPanel — vacío (selector deshabilitado + empty state)
- v15: OasisCombatPlannerPanel — normal (3 grupos: cereal con anomalía, arcilla, tipo desconocido)
- v16: Vista completa StatsTab v2.1 (nuevo orden: Leyenda → Balance → CombatPlanner → Globales → Lista)

La vista completa (v16) tiene bloques arrastrables para que el usuario reordene y
apruebe la composición. El usuario exporta el layout aprobado como JSON.

### Layout propuesto en v16

```
blk-spawn     → SpawnMechanicsPanel (colapsado)
blk-balance   → BalanceSection (marcador dashed, existente)
blk-combat    → OasisCombatPlannerPanel (panel nuevo fusionado)
-- separador --
blk-global    → GlobalOasisStatsPanel (marcador dashed, arrastrable)
blk-list      → OasisList (marcador dashed, arrastrable)
```

---

## 7. Estados de cada pantalla

### SpawnMechanicsPanel

| Estado | Descripción | Trigger |
|---|---|---|
| Normal (desplegado) | Tabla de 10 animales + tabla de sets + nota anomalía | Primera visita o usuario despliega manualmente |
| Colapsado | Solo header con chevron | Usuario colapsa / segunda visita (localStorage) |

### OasisCompositionPanel

| Estado | Descripción | Trigger |
|---|---|---|
| Loading | Skeleton de 3 filas animadas con pulse | Mientras el endpoint no responde |
| Error | Banner rojo + mensaje + botón "Reintentar" | Error HTTP del endpoint |
| Vacío | Icono + texto + CTA "Ir a Ingresar" | `oasis: []` en la respuesta |
| Normal | Tabla de oasis con tipo, estado, composición | `oasis.length > 0` |
| Oasis tipo desconocido | Fila con tipo "—", estado gris, composición vacía | `inferred_type: null` |
| Animal con anomalía | Chip del animal con badge "A" en naranja/acento | `species[i].is_anomaly = true` |

#### Detalle del badge de anomalía

El color del badge anomalía: como no hay "warning naranja" (prohibido por DESIGN.md §14
— choca con el oro), se usa el propio **acento oro** + texto "anom." en 10px/500.
Así la anomalía destaca sin introducir un tercer color. El badge lleva `title=` con
explicación para accesibilidad.

### WorstCasePlannerPanel

| Estado | Descripción | Trigger |
|---|---|---|
| Loading | Skeleton de 3 filas animadas | Mientras endpoint responde (cambio de intervalo o carga inicial) |
| Error | Banner rojo + mensaje + botón "Reintentar" | Error HTTP |
| Vacío | Selector de intervalo deshabilitado + texto vacío | `oasis: []` |
| Normal | Selector activo + tabla con peor combo + resumen def. | `oasis.length > 0` |
| Tipo no inferible | Fila del oasis con "—" + nota inline | `worst_case_summary: null` |

---

## 8. Inventario de componentes UI reutilizables

### Componentes REUTILIZAR (ya existen, no rediseñar)

| Componente | Ubicación | Uso en este diseño |
|---|---|---|
| `NatureIcon` | `frontend/src/components/attack-reports/NatureIcon.jsx` | Iconos de animales en las tres tablas |
| Skeleton (barras pulse) | Patrón de `GlobalOasisStatsPanel.jsx` (`GlobalStatsSkeleton`) | Loading de Composition y WorstCase |
| Error banner | Patrón de `GlobalOasisStatsPanel.jsx` (`ErrorBanner`) | Error de ambos paneles |
| Estado vacío | Patrón de `GlobalOasisStatsPanel.jsx` | Vacío de ambos paneles |
| Badge / chip de estado (§19.10 DESIGN.md) | Patrón existente | Badge de tipo de oasis, badge de confianza, badge de anomalía |

### Componentes CREAR (nuevos)

| Componente | Descripción | Props clave |
|---|---|---|
| `SpawnMechanicsPanel` | Panel educativo colapsable, datos estáticos del catálogo | `lang`, `t` |
| `OasisCompositionPanel` | Tabla de oasis con tipo, estado, composición típica | `data`, `loading`, `error`, `onRetry`, `onGoToIngest`, `lang`, `t` |
| `WorstCasePlannerPanel` | Selector de intervalo + tabla de peor combo + resumen def. | `data`, `loading`, `error`, `onRetry`, `onTimerChange`, `timerMin`, `lang`, `t` |
| `SpawnStatusDot` | Punto de color + texto para respawning/cooldown/unknown | `status` (`"respawning"/"cooldown"/"unknown"`) |
| `OasisTypeBadge` | Badge de tipo inferido + indicador de confianza | `type` (string o null), `confidence` (string o null) |
| `AnimalCompositionChip` | Chip compacto: NatureIcon + avg · max + badge anomalía si aplica | `ordinal`, `avg`, `max`, `isAnomaly`, `lang` |
| `WorstCaseChip` | Chip: NatureIcon + ×N | `ordinal`, `count` |
| `TimerSelector` | 4 botones pill: 6/7/10/15 min | `value`, `onChange`, `disabled` |

### Componentes MODIFICAR (cambio mínimo)

| Componente | Cambio | Impacto |
|---|---|---|
| `RegenRatesSection` | Retirar `avg_regen_per_hour` — adaptarse al nuevo campo o retirar si la nueva UI lo sustituye completamente | Solo afecta a `OasisStatsPanel` que lo monta |
| `GlobalOasisStatsPanel` | Retirar acceso a `r.avg_regen_per_hour` (línea 352) | Retrocompatible si se elimina el campo de la respuesta |

---

## 9. Contenido y microcopy

> Todo string va via i18n. Los códigos clave se listan a continuación (en español
> como referencia — los 25 idiomas se añaden en el paso de implementación).

### SpawnMechanicsPanel

| Clave i18n | Texto ES de referencia |
|---|---|
| `stats.spawn.panel_title` | "Mecánica de spawn de oasis" |
| `stats.spawn.panel_caption` | "Cómo funcionan los timers y los sets de animales" |
| `stats.spawn.timers_title` | "Timers de aparición (servidor x1)" |
| `stats.spawn.col_animal` | "Animal" |
| `stats.spawn.col_order` | "Orden" |
| `stats.spawn.col_timer` | "Timer (min)" |
| `stats.spawn.sets_title` | "Sets normales por tipo de oasis" |
| `stats.spawn.anomaly_note` | "Anomalía: animal observado fuera del set del tipo inferido. Puede aparecer esporádicamente. No se incluye en el peor caso." |
| `stats.spawn.oasis_type.hierro` | "Hierro" |
| `stats.spawn.oasis_type.arcilla` | "Arcilla" |
| `stats.spawn.oasis_type.madera` | "Madera" |
| `stats.spawn.oasis_type.cereal` | "Cereal" |

### OasisCompositionPanel

| Clave i18n | Texto ES de referencia |
|---|---|
| `stats.composition.panel_title` | "Composición típica por oasis" |
| `stats.composition.col_oasis` | "Oasis" |
| `stats.composition.col_type` | "Tipo" |
| `stats.composition.col_status` | "Estado" |
| `stats.composition.col_composition` | "Composición (avg · máx)" |
| `stats.composition.status.respawning` | "Repoblando" |
| `stats.composition.status.cooldown` | "Cooldown" |
| `stats.composition.status.unknown` | "Desconocido" |
| `stats.composition.confidence.low` | "baja confianza" |
| `stats.composition.confidence.medium` | "media confianza" |
| `stats.composition.anomaly_badge` | "anom." |
| `stats.composition.anomaly_tooltip` | "Animal fuera del set normal del tipo inferido" |
| `stats.composition.type_unknown` | "Tipo no inferido" |
| `stats.composition.no_data` | "Sin datos suficientes" |
| `stats.composition.attacks_suffix` | "ataques" |
| `stats.composition.ago_hours` | "hace {n}h {m}m" |
| `stats.composition.empty_title` | "Sin oasis con reportes" |
| `stats.composition.empty_body` | "Ingresa reportes de ataques para ver la composición típica de tus oasis." |
| `stats.composition.empty_cta` | "Ir a Ingresar →" |
| `stats.composition.error` | "Error al cargar la composición de oasis." |
| `stats.composition.retry` | "Reintentar" |

### WorstCasePlannerPanel

| Clave i18n | Texto ES de referencia |
|---|---|
| `stats.worst.panel_title` | "Peor combinación a batir" |
| `stats.worst.interval_label` | "Intervalo de envío:" |
| `stats.worst.col_oasis` | "Oasis" |
| `stats.worst.col_type` | "Tipo" |
| `stats.worst.col_combo` | "Peor combo" |
| `stats.worst.col_def_inf` | "Def. inf." |
| `stats.worst.col_def_cav` | "Def. cav." |
| `stats.worst.no_type` | "Añade más reportes para inferir el tipo" |
| `stats.worst.anomaly_note` | "Los animales anómalos no se incluyen en el peor caso." |
| `stats.worst.empty_title` | "Sin datos para el peor caso" |
| `stats.worst.empty_body` | "Ingresa reportes de ataques para calcular la peor combinación." |
| `stats.worst.error` | "Error al calcular el peor caso." |
| `stats.worst.retry` | "Reintentar" |
| `stats.worst.def_label` | "Defensa total" |

---

## 10. Accesibilidad

- **SpawnMechanicsPanel**: el header de collapse es `<button>` con `aria-expanded` +
  `aria-controls`. El panel colapsado tiene `hidden` o `aria-hidden` según el estado.
- **OasisCompositionPanel**: tabla con `role="table"`, `scope="col"` en cabeceras.
  Skeleton con `role="status" aria-label="Cargando..."`. Error con `role="alert"`.
- **WorstCasePlannerPanel**: botones de intervalo con `aria-pressed` para indicar el
  activo. `aria-disabled` cuando el selector está deshabilitado (BD vacía).
  Tabla con los mismos patrones que OasisCompositionPanel.
- **SpawnStatusDot**: el color nunca es la única señal — siempre va acompañado de texto.
- **OasisTypeBadge**: `title` con el texto completo del tipo y confianza para lectores
  de pantalla.
- **Badge anomalía**: `title="Animal fuera del set normal del tipo inferido"`.
- **Foco**: todos los controles interactivos tienen anillo de foco visible (`outline: 2px
  solid var(--accent); outline-offset: 2px`). Nunca `outline: none` sin reemplazo.
- **Contraste**: los tokens de DESIGN.md §4 están verificados WCAG AA.

---

## 11. Responsive / adaptación a dispositivos

### SpawnMechanicsPanel

| Breakpoint | Comportamiento |
|---|---|
| `< md` | Tabla de timers: col "Orden" oculta (P3). Col "Timer" y "Animal" (P1). Sets por tipo: chips de NatureIcon apilados en 2 columnas. |
| `≥ md` | Tabla completa. Sets horizontales. |

### OasisCompositionPanel

| Breakpoint | Comportamiento |
|---|---|
| `< md` | Tabla → tarjetas apiladas. Cada tarjeta muestra: coords (P1) + estado (P1) + tipo (P2). Composición (P2) detrás de "expandir". |
| `md` | Tabla con 3 cols: oasis, estado, tipo. Composición truncada a 2-3 chips. |
| `≥ lg` | Tabla completa. Composición con todos los chips visibles. |

### WorstCasePlannerPanel

| Breakpoint | Comportamiento |
|---|---|
| `< md` | Tabla → tarjetas. Cada tarjeta: coords (P1) + tipo (P1) + peor combo top 3 (P1) + def. inf/cav (P2). TimerSelector en fila horizontal siempre visible. |
| `≥ md` | Tabla completa. Def. separada en dos sub-columnas. |

### Regla RTL (ar/he/fa)

- Todas las props de espaciado usan propiedades lógicas CSS (`margin-inline-start`,
  `padding-inline`, `inset-inline-*`).
- El TimerSelector usa `flex-direction: row` — no cambia en RTL (los números son
  universales).
- Los chevrons del panel colapsable son `transform: scaleX(-1)` en RTL.

---

## 12. Interacciones y feedback

### SpawnMechanicsPanel — collapse/expand

- Click en header → toggle de `isOpen` en estado local (o localStorage).
- Chevron rota `0deg` (colapsado) → `90deg` (desplegado) con `transition: transform var(--dur-base)`.
- El contenido tiene `overflow: hidden` con transición de altura (o `grid-template-rows: 0fr → 1fr`).

### WorstCasePlannerPanel — cambio de intervalo

- Click en botón de intervalo → actualiza `timerMin` en estado padre.
- El panel entra en loading inmediatamente (skeleton se muestra, botones permanecen
  habilitados para cambiar de nuevo durante la carga).
- Cuando llega la respuesta: transición suave de datos (fade-in con `--dur-base`).

### Estados loading

- Skeleton: barras `background: var(--border)` con animación `pulse` (keyframe
  `opacity 0.6 → 1 → 0.6` en `1.5s ease-in-out infinite`).
- El skeleton respeta `prefers-reduced-motion: reduce` (detiene la animación).

### Estados error

- Banner rojo: `background: rgba(var(--danger-rgb), 0.08)`, `border: 1px solid rgba(var(--danger-rgb), 0.30)`.
- Botón "Reintentar": terciario/ghost (texto en `--accent-text`, sin fondo).

---

## 13. Criterios de aceptación de diseño

- [ ] SpawnMechanicsPanel empieza colapsado en la segunda visita (localStorage).
- [ ] El collapse/expand tiene transición de altura + rotación del chevron.
- [ ] La tabla de timers usa `--font-mono` + `tabular-nums` para los timers.
- [ ] El animal se muestra con `NatureIcon` (ordinal) + nombre localizado via `NATURE_{ordinal}` e i18n.
- [ ] OasisCompositionPanel muestra skeleton durante la carga y error con Reintentar.
- [ ] Estado vacío de OasisCompositionPanel tiene CTA funcional que cambia al tab Ingresar.
- [ ] El badge de tipo de oasis muestra la confianza (low/medium) como texto secundario.
- [ ] SpawnStatusDot usa verde/rojo/gris como señal visual + texto siempre (nunca solo color).
- [ ] Badge anomalía usa el acento oro (no naranja prohibido) + tooltip accesible.
- [ ] WorstCasePlannerPanel tiene el TimerSelector siempre visible (P1).
- [ ] El botón activo del TimerSelector usa `--accent-subtle` + borde `--accent`.
- [ ] Cambiar el intervalo entra en loading inmediato (no espera click en botón extra).
- [ ] Los valores def. inf. y cav. usan `--font-mono` + `tabular-nums`.
- [ ] Filas con `worst_case_summary=null` muestran "Añade más reportes" (no celda vacía sin contexto).
- [ ] En `< md`: tablas → tarjetas con jerarquía P1/P2/P3 correcta.
- [ ] Todos los controles tienen foco visible (`outline: 2px solid var(--accent)`).
- [ ] Los paneles cargan de forma independiente (fallo de uno no bloquea los demás).
- [ ] Cero texto hardcodeado: todo via claves i18n de los 25 catálogos.
- [ ] Propiedades CSS lógicas para RTL en todos los componentes nuevos.
- [ ] SpawnMechanicsPanel NO hace ninguna llamada a la API (datos del catálogo importados directamente en el componente).

---

## 14. Trazabilidad

| Decisión de diseño | Origen |
|---|---|
| SpawnMechanicsPanel colapsable (empieza colapsado en 2ª visita) | Principio "divulgación progresiva" (DESIGN.md §1) + usuario experimentado no necesita leer el educativo cada vez |
| SpawnMechanicsPanel primero en el orden | Contexto conceptual antes de datos operativos; el panel educativo da el "por qué" de los otros dos |
| OasisCompositionPanel y WorstCasePlannerPanel separados (no unidos) | Son usos distintos: uno es "qué ha salido históricamente", el otro es "qué puede salirme en mi próximo envío" |
| TimerSelector = 4 botones pill (no dropdown) | La decisión es frecuente + solo 4 opciones = pill grouping más rápido que abrir un dropdown (Principio "menos es más") |
| Intervalo por defecto = 10 min | Valor medio razonable; el usuario puede cambiarlo inmediatamente |
| Badge anomalía en acento oro (no naranja) | DESIGN.md §14 prohíbe naranja (choca con el oro); el acento es la señal de "atención" del sistema |
| SpawnStatusDot: texto siempre + color | DESIGN.md §13 y §5: el color nunca es la única señal |
| Confianza (low/medium) en texto secundario del badge, no en color | Usar un segundo color para confianza introduciría dos acentos compitiendo (prohibido §14) |
| Carga independiente de Composition y WorstCase | spec §5 flujo 1 + DESIGN.md §12 ("Cada panel de la nueva UI falla de forma aislada") |
| Paneles nuevos van ANTES de los existentes en el tab | Los nuevos paneles son la funcionalidad principal de esta feature; BalanceSection y OasisList son contexto secundario |
| Tabla densa sin zebra striping | DESIGN.md §12 "Tablas" (las tablas Apple son limpias) |
| NatureIcon reutilizado sin modificar | Palantir: componente existente que encaja exactamente; UI: reutiliza `NatureIcon` — decidido por análisis propio |
| Skeleton patrón de GlobalOasisStatsPanel | Consistencia visual con patrones existentes; palantir: mismo patrón identificado en `GlobalStatsSkeleton` |
| Error banner patrón de GlobalOasisStatsPanel | Ídem — `ErrorBanner` existente cubre el caso exacto |

---

## Registro de implementación v2.1 (iteración — pendiente)

**Fecha spec:** 2026-06-02
**Estado:** ready-for-impl (mockup pendiente de aprobación del usuario)

### Componentes a CREAR en v2.1

| Componente | Descripción |
|---|---|
| `OasisCombatPlannerPanel` | Panel fusionado: TimerSelector + tabla por animal por oasis + totales de grupo |

### Componentes a ELIMINAR en v2.1

| Componente | Motivo |
|---|---|
| `OasisCompositionPanel` | Reemplazado por `OasisCombatPlannerPanel` |
| `WorstCasePlannerPanel` | Reemplazado por `OasisCombatPlannerPanel` |
| `AnimalCompositionChip` | Los chips son ahora filas de tabla |
| `WorstCaseChip` | Los chips son ahora celdas de la columna "Peor combo" |

### Ficheros a modificar en v2.1

| Fichero | Cambio |
|---|---|
| `frontend/src/components/attack-reports/StatsTab.jsx` | Nuevo orden de paneles: SpawnMechanics → Balance → OasisCombatPlanner → Global → OasisList; gestión de timerMin delegada al nuevo panel |
| `frontend/src/i18n/catalog/*.js` | Nuevas claves `stats.combat.*` en los 25 catálogos |

---

## Registro de implementación v2 (implementada 2026-06-02)

**Implementado por:** desarrollador-ux-ui

### Ficheros creados

| Fichero | Descripción |
|---|---|
| `frontend/src/utils/oasisSpawnCatalog.js` | Catálogo JS (espejo del Python): SPAWN_TIMER_S, OASIS_TYPE_SETS, NATURE_ORDINALS, formatTimerMmSs |
| `frontend/src/components/attack-reports/SpawnMechanicsPanel.jsx` | Panel educativo colapsable (Pieza 1) |
| `frontend/src/components/attack-reports/OasisCompositionPanel.jsx` | Composición típica por oasis (Pieza 2+4) |
| `frontend/src/components/attack-reports/WorstCasePlannerPanel.jsx` | Peor combinación a batir (Pieza 3) |

### Ficheros modificados

| Fichero | Cambio |
|---|---|
| `frontend/src/components/attack-reports/StatsTab.jsx` | Reescrito para montar los 3 paneles nuevos + gestión de estado EP-SPAWN compartido |
| `frontend/src/api/client.js` | Añadido `getOasisSpawnComposition(timerMin)` |
| `frontend/src/components/attack-reports/GlobalOasisStatsPanel.jsx` | Retirado acceso a `avg_regen_per_hour` del resumen del acordeón (Pieza 5) |
| `frontend/src/components/attack-reports/RegenRatesSection.jsx` | Campo `avg_regen_per_hour` reemplazado por `—` en la columna de ratio (Pieza 5) |
| `frontend/src/i18n/catalog/*.js` | 57 claves nuevas en los 25 catálogos (NATURE_1..10 + stats.spawn.* + stats.composition.* + stats.worst.*) |

### Verificación headless

- Modo claro: paneles renderizados correctamente, SpawnMechanicsPanel colapsado con caption, selector "10 min" activo en acento oro, paneles existentes (Balance) sin regresar
- Modo oscuro: tokens duales correctos, misma estructura
- SpawnMechanicsPanel desplegado: tabla de 10 animales con iconos reales de Travian, nombres localizados en ES, timers en MM:SS font-mono, tabla de sets con chips
- Build de producción: `npm run build` sin errores (1669 módulos)

### Desviaciones respecto al diseño

1. **`mockup_aprobado_por_usuario: no → sí`**: El usuario declaró explícitamente que el mockup fue aprobado y el gate humano superado — se respeta ese estado.
2. **`RegenRatesSection` no eliminada**: El spec §8 indica que puede "eliminarse si la nueva UI la sustituye por completo". Se opta por mantenerla (mostrando `—`) hasta que el backend retire `avg_regen_per_hour` de EP-06. La eliminación completa es deuda técnica para después de RN-RET-03/04.
3. **Error state muestra "Not Found"**: Sin backend corriendo, EP-SPAWN devuelve 404; el banner de error cubre este estado correctamente con botón Reintentar.

### Qué queda pendiente (NO es responsabilidad de este agente)

- **Retirada de `avg_regen_per_hour` en el backend** (EP-06, EP-10): lo hace el usuario/desarrollador-apis por separado (RN-RET-01 fase 2-3 del spec funcional §4.6).
- **Prueba manual con backend real corriendo**: verificar estados con datos reales (oasis con tipo inferido, animales con anomalía, worst_case_summary poblado).

---

## Registro de implementación v2.2 (iteración simplificada — 2026-06-02)

**Implementado por:** desarrollador-ux-ui

### Ficheros creados

| Fichero | Descripción |
|---|---|
| `frontend/src/components/attack-reports/OasisCombatPlannerPanel.jsx` | Panel fusionado con dos filas compactas Media/Peor (chips), sin fuerza defensiva, sin "×" |

### Ficheros eliminados

| Fichero | Motivo |
|---|---|
| `frontend/src/components/attack-reports/OasisCompositionPanel.jsx` | Reemplazado por OasisCombatPlannerPanel |
| `frontend/src/components/attack-reports/WorstCasePlannerPanel.jsx` | Reemplazado por OasisCombatPlannerPanel |

### Ficheros modificados

| Fichero | Cambio |
|---|---|
| `frontend/src/components/attack-reports/StatsTab.jsx` | Nuevo orden v2.2: SpawnMechanics → Balance → OasisCombatPlanner → Global → OasisList; state timerMin movido al StatsTab (prop a OasisCombatPlannerPanel) |
| `frontend/src/i18n/catalog/es.js` | 11 claves nuevas `stats.planner.*` |
| `frontend/src/i18n/catalog/en.js` | 11 claves nuevas `stats.planner.*` (EN) |
| `frontend/src/i18n/catalog/{ar,bg,cs,da,de,el,fa,fr,he,hu,it,ja,lt,lv,nl,pl,pt,rs,ru,sl,sv,tr,uk}.js` | 11 claves nuevas `stats.planner.*` (fallback EN) |

### Verificación headless (2026-06-02)

- Modo claro: orden correcto (SpawnMechanics → Balance → Planificador → ...), selector "10 min" en acento oro, filas MEDIA/PEOR con chips compactos, sin "×" ni columnas de defensa
- Modo oscuro: tokens duales correctos, misma estructura y jerarquía
- DOM verificado: sin "×", sin "Def.", etiquetas MEDIA/PEOR presentes, selector de intervalo y título del planificador visibles, BalanceSection sin regresión
- Build producción: `npm run build` → 1668 módulos, sin errores (warning chunk size preexistente)

### Desviaciones respecto al spec v2.1

1. **Sin tabla por animal**: el spec v2.1 describía una tabla de 5 columnas (Animal, Típica, Peor combo, Def.inf, Def.cav). La v2.2 reemplaza esa tabla por dos filas de chips compactos. Motivo: cambio explícito del usuario tras prueba visual.
2. **Sin fuerza defensiva**: `def_infantry_contribution` y `def_cavalry_contribution` devueltos por el backend no se pintan. Motivo: decisión explícita del usuario ("el usuario los quitó de la vista").
3. **worst_case_count sin "×"**: se muestra como número plano (ej. "13") en lugar de "×13". Motivo: el "×N" confundía al usuario interpretándolo como multiplicador cuando es un conteo absoluto.
4. **Claves i18n**: se usa el namespace `stats.planner.*` (nuevo) en lugar del `stats.combat.*` previsto en v2.1, para reflejar el rediseño sin contaminar las claves de v2.1 que quedaron sin usar. Las claves `stats.composition.*` y `stats.worst.*` se mantienen en los catálogos (no se eliminan) para no romper posibles referencias futuras.

---

## v2.3 — Agrupación por ciudad atacante

### Decisión de producto

Cada oasis del endpoint EP-SPAWN incluye ahora `origin_villages: string[]` (RN-GROUP-01 del spec funcional). Un oasis atacado desde varias ciudades aparece bajo **cada una** de ellas con los mismos datos.

### Diseño

- Se construye un mapa `{ ciudad → [oasis...] }` con `reduce` en el componente (frontend puro, sin cambio de backend).
- Una **sección colapsable por ciudad** (`CityOasisSection`), expandidas por defecto.
  - Cabecera: chevron + nombre de ciudad + contador discreto (`"Aldea Norte · 5 oasis"`).
  - El chevron rota −90° cuando está cerrada (transición CSS `var(--dur-fast)`).
  - Accesibilidad: `<section aria-labelledby>` + botón con `aria-expanded`.
- **Orden**: alfabético (`localeCompare`), "Desconocido" (raw del backend) siempre al final.
- **"Desconocido"**: si `origin_village === "Desconocido"` se mapea a clave i18n `stats.planner.city_unknown` (ES: "Desconocido", EN: "Unknown", resto: fallback EN).
- **Selector de intervalo (6/7/10/15)**: único, arriba del panel, controla la fila Peor de todos los oasis de todas las ciudades. Sin cambio respecto a v2.2.
- **Ciudad única**: se muestra igual (una sección con cabecera). Coherencia garantizada.
- Si `origin_villages` está ausente o vacío, el oasis cae bajo "Desconocido".

### Jerarquía visual (DESIGN.md)

- Cabecera de ciudad: peso 600, `13px`, `var(--text)`. Hairline 1px `var(--border)` como divisor inferior. Sin color de fondo, sin caja coloreada.
- Chevron: `var(--text-tertiary)`, 14×14px SVG inline.
- Contador: `11px`, `var(--text-tertiary)`, `tabular-nums`.
- Los bloques de oasis dentro de la sección no cambian respecto a v2.2.

### Claves i18n nuevas (3)

| Clave | ES | EN |
|---|---|---|
| `stats.planner.city_unknown` | Desconocido | Unknown |
| `stats.planner.city_oasis_count_one` | 1 oasis | 1 oasis |
| `stats.planner.city_oasis_count_pl` | {n} oasis | {n} oasis |

Añadidas en los 25 catálogos. ES y EN con calidad; resto fallback EN.

### Ficheros creados / modificados (v2.3)

| Fichero | Cambio |
|---|---|
| `frontend/src/components/attack-reports/CityOasisSection.jsx` | Nuevo: sección colapsable por ciudad |
| `frontend/src/components/attack-reports/OasisCombatPlannerPanel.jsx` | `buildCityMap()` + render por ciudad + import CityOasisSection |
| `frontend/src/i18n/catalog/es.js` | 3 claves nuevas `stats.planner.city_*` |
| `frontend/src/i18n/catalog/en.js` | 3 claves nuevas `stats.planner.city_*` (EN) |

---

## v2.6 — Anidado Jugador → Aldea → Oasis (2026-06-02)

### Decisión de producto

El campo `origin_villages: string[]` de v2.3 se sustituye por `attackers: [{player, village}]`
(spec funcional v2.6, RN-GROUP-01). Esto permite agrupar en DOS niveles en el frontend:
**Jugador → Aldea → Oasis**.

### Diseño

El frontend construye un mapa anidado `player → (village → [oasis])` desde `attackers`.
Un oasis con N pares `(player, village)` aparece bajo CADA uno con los mismos datos.

#### Nivel 1 — Jugador (`PlayerOasisSection`)

- Nueva sección colapsable por jugador, expandida por defecto.
- Cabecera: fondo `var(--surface-2)` con borde `1px solid var(--border)` y `border-radius`,
  chevron 15px, nombre del jugador **14px / fontWeight 700**, contador de aldeas discreto
  (`11px`, `var(--text-tertiary)`, `tabular-nums`).
- Al colapsar, el chevron rota −90° (transición `var(--dur-fast)`).
- Accesibilidad: `<section aria-labelledby>` + botón con `aria-expanded`.
- Contenido expandido con `paddingInlineStart: 12px` para crear sangría visual que señale
  la jerarquía Jugador → Aldea sin usar color como única señal.
- Margen inferior: 24px entre jugadores.

#### Nivel 2 — Aldea (`CityOasisSection`, reutilizado sin cambios)

- Mismo componente de v2.3, sin modificación.
- Su cabecera es `13px / fontWeight 600` sobre fondo transparente con hairline — menor
  peso visual que el nivel jugador: la jerarquía se comunica mediante tamaño de tipo,
  peso tipográfico y sangría.

#### Nivel 3 — Oasis (`OasisBlock`, sin cambios)

- Bloques de oasis idénticos a v2.2 / v2.3.

### Orden

- Jugadores: A-Z (`localeCompare`), "Desconocido" siempre al final.
- Aldeas dentro de cada jugador: A-Z, "Desconocido" siempre al final.
- Si `attackers` está ausente o vacío → fallback a `(player="Desconocido", village="Desconocido")`.

### "Desconocido" — localización

- `player === "Desconocido"` (raw) → `t('stats.planner.player_unknown')`.
- `village === "Desconocido"` (raw) → `t('stats.planner.city_unknown')` (ya existía).

### Jerarquía visual (DESIGN.md)

| Nivel | Elemento | Estilo |
|---|---|---|
| Jugador | Fondo cabecera | `var(--surface-2)` + `border 1px var(--border)` + `border-radius` |
| Jugador | Texto nombre | `14px`, `fontWeight 700`, `var(--text)` |
| Jugador | Contador aldeas | `11px`, `var(--text-tertiary)`, `tabular-nums` |
| Jugador | Chevron | `15px`, `var(--text-secondary)` |
| Aldea | Fondo cabecera | Transparente, hairline `border-bottom 1px var(--border)` |
| Aldea | Texto nombre | `13px`, `fontWeight 600`, `var(--text)` |
| Aldea | Contador oasis | `11px`, `var(--text-tertiary)`, `tabular-nums` |
| Aldea | Chevron | `14px`, `var(--text-tertiary)` |

Sin colores de fondo coloreados. Sin acentos dorados en cabeceras. Color nunca es la única señal.
Props CSS lógicas para RTL (`paddingInlineStart`). Tokens duales claro+oscuro aplicados via CSS vars.

### Claves i18n nuevas (3)

| Clave | ES | EN | Resto |
|---|---|---|---|
| `stats.planner.player_unknown` | Desconocido | Unknown | fallback EN |
| `stats.planner.player_village_count_one` | 1 aldea | 1 village | fallback EN |
| `stats.planner.player_village_count_pl` | {n} aldeas | {n} villages | fallback EN |

### Ficheros creados / modificados (v2.6)

| Fichero | Cambio |
|---|---|
| `frontend/src/components/attack-reports/PlayerOasisSection.jsx` | Nuevo: sección colapsable nivel jugador |
| `frontend/src/components/attack-reports/OasisCombatPlannerPanel.jsx` | `buildPlayerMap()` sustituye a `buildCityMap()`; render 2 niveles (PlayerOasisSection → CityOasisSection → OasisBlock); import PlayerOasisSection |
| `frontend/src/i18n/catalog/es.js` | 3 claves nuevas `stats.planner.player_*` (ES) |
| `frontend/src/i18n/catalog/en.js` | 3 claves nuevas `stats.planner.player_*` (EN) |
| `frontend/src/i18n/catalog/{otros 23}.js` | 3 claves nuevas `stats.planner.player_*` (fallback EN) |
| `frontend/src/i18n/catalog/{ar,bg,...}.js` (23 restantes) | 3 claves nuevas `stats.planner.city_*` (fallback EN) |
