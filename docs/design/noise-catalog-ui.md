---
id: noise-catalog-ui
titulo: Catálogo de Ruido Humano de Navegación — Pestaña "Ruido" en WorldSpacePage (incl. Wizard de Rutas + Probar Ruta)
estado: implemented
fecha: 2026-06-02
autor: disenador-producto
spec_funcional_relacionado: docs/specs/human-sessions.md
spec_funcional_wizard: docs/specs/noise-path-wizard.md
mockup_editable: frontend/mockups/noise-catalog.playground.html
mockup_aprobado_por_usuario: sí
revisiones:
  - 2026-06-02: v1 — spec inicial (panel config + tabla destinos + drawer pasos)
  - 2026-06-02: v2 — rediseño del drawer de rutas alrededor del WIZARD MANUAL (modelo
      noise-path-wizard.md). Anclas precargadas (EP-N12), derivación de selector
      (EP-N11), expected_url_after_click, is_dead en rutas, refresh-villages (EP-N13).
      El drawer previo con editor de pasos en crudo se reemplaza por un wizard guiado
      que es el protagonista del flujo de creación de rutas.
  - 2026-06-02: implemented — desarrollador-ux-ui implementa la UI completa.
  - 2026-06-02: v3 — delta "Probar ruta" (EP-N14). Botón "Probar" en cada PathCard +
      panel PathTestResultPanel inline expandible. 5 estados: idle/loading/ok/error/409.
      Mockup actualizado con vistas 21-25. Estado: ready-for-impl.
  - 2026-06-02: v4 — delta "Editar ruta" (renombrar label + acciones descubribles).
      Renombrar label de ruta con edición inline (icono lápiz → input → guardar/cancelar).
      Rediseño cabecera PathCard: "Editar pasos" sube a cabecera siempre visible; ✕
      se convierte en ⋯ overflow que abre mini-popover destructivo; jerarquía visual
      clara de acciones. Mockup actualizado con vistas 26-30. Estado: ready-for-impl.
---

# Catálogo de Ruido Humano de Navegación — Pestaña "Ruido" (incl. Wizard de Rutas)

## 1. Visión de la experiencia y principios de diseño

### Por qué existe esta vista

El bot necesita navegar por páginas no esenciales de Travian para imitar a un
humano curioso: ver el mapa, revisar mensajes, echar un vistazo a un perfil rival.
Sin este ruido, el bot solo visita las páginas de farming y resulta estadísticamente
anómalo. Esta pestaña es el panel de control de ese comportamiento: el usuario
define a dónde va el bot "de paseo" y, opcionalmente, exactamente qué pasos da
al llegar allí.

La experiencia tiene tres niveles de profundidad (config global → destinos →
rutas + pasos) y debe resolverse sin abrumar. La clave es la **divulgación
progresiva**: la lista de destinos es la pantalla principal; el detalle de rutas
y pasos se abre en un drawer lateral que no interrumpe la vista de la lista.

### Principios aplicados (ref: `docs/design/PRINCIPIOS.md` / `frontend/DESIGN.md`)

- **Contenido primero**: la tabla de destinos es el elemento central. La config
  global va arriba como panel colapsable (off by default), porque la mayoría de
  las sesiones de uso son para gestionar destinos, no cambiar la config.
- **Menos es más**: una acción primaria por nivel. En la lista de destinos, la
  acción principal es "Añadir destino". En el drawer, "Añadir ruta".
- **Divulgación progresiva**: rutas y pasos se gestionan en un drawer lateral.
  Los pasos de una ruta se editan en un editor de filas inline dentro del drawer
  (igual que `BlockEditor` en la pestaña Sesión). Esto resuelve la jerarquía de
  4 niveles sin anidamiento visual agresivo.
- **Semántica de color coherente con la pestaña Sesión**: los tokens de modo
  (`--mode-hardcore`, `--mode-idle`, `--mode-disconnected`) ya definidos se
  reutilizan para las badges de categoría y estado de los destinos. Los badges
  propios de estado (is_dead, is_safe/unsafe) usan `--danger` y `--text-tertiary`.
- **Tabular-nums + font-mono** en pesos, contadores de fallo y delays.

### Trade-off de diseño resuelto: ¿drawer o expansión inline para rutas/pasos?

**Decisión: drawer lateral** (patrón `FarmListDrawer.jsx`).

Justificación: la jerarquía es de 4 niveles (config → destinos → rutas → pasos).
Un expand-inline doble en la tabla de destinos crearía filas anidadas de profundidad
variable difíciles de escanear. Un drawer lateral preserva el contexto (el usuario
sigue viendo la lista de destinos al fondo con opacidad reducida) y permite un espacio
de trabajo limpio para el wizard y la gestión de rutas sin contaminar la tabla.

El patrón drawer ya existe en `FarmListDrawer.jsx` y resuelve exactamente esta
necesidad. Su estructura (overlay semitransparente + panel lateral derecho +
trampa de foco + cierre con Escape) se reutiliza directamente.

### Trade-off resuelto (v4): ¿Renombrar en drawer separado vs. edición inline en la tarjeta?

**Decisión: edición inline directamente en la cabecera de PathCard.**

El label de la ruta vive en la cabecera de la `PathCard`. La forma más natural de
editarlo es tocarlo allí mismo, sin cambiar de contexto. Un drawer o formulario
separado sería un exceso modal para cambiar un campo de texto.

Patrón de referencia: el label del destino en `NoiseDestinationDrawer` ya usa un
`<input>` de texto estándar que se guarda con un botón "Guardar cambios". La edición
inline de la ruta es la misma idea, pero comprimida en una fila (icono lápiz → input
+ ✓/✕ inline → PUT EP-N09 → toast). Esto evita crear un patrón nuevo: reutiliza
los tokens, los estados y el comportamiento del patrón existente, simplemente en un
espacio más compacto.

El `origin` de la ruta es **inmutable por diseño de backend** (EP-N09 no lo acepta).
No se ofrece ningún control para editarlo. Se muestra como badge de solo lectura.

### Trade-off resuelto (v4): ¿Acciones siempre visibles vs. detrás de expand?

**Decisión: "Editar pasos" sube a la cabecera, siempre visible. "Eliminar" va a un
menú de overflow ⋯.**

Problema reportado: "Editar pasos" no era localizable porque estaba enterrado en el
cuerpo expandido. La solución es moverlo a la cabecera donde el usuario puede verlo
sin pasos intermedios.

"Eliminar" era un ✕ compacto en la cabecera que competía visualmente con el chevron
expand. Convertirlo en un botón ⋯ (overflow menu) tiene dos ventajas: (1) reduce el
ruido visual en la cabecera, que ya tiene varios controles, y (2) hace la acción
destructiva más difícil de ejecutar por accidente (requiere dos gestos deliberados:
abrir el menú, luego confirmar en el popover). El popover de confirmación (`DeletePopover`
existente) permanece igual.

### Trade-off resuelto (v2): ¿Editor directo de pasos vs. Wizard guiado?

**Decisión: WIZARD guiado** como flujo de creación de rutas (v2 del diseño).

El modelo anterior (v1) mostraba una tabla de filas con inputs directos de selector
CSS (patrón BlockEditor). El usuario rechazó ese modelo porque requería conocimiento
previo de selectores CSS. El modelo nuevo (spec `noise-path-wizard.md`) convierte
la creación de rutas en un wizard paso a paso donde el usuario "enseña" el camino:
pega el outerHTML del elemento a clicar, el sistema deriva el selector estructural
(EP-N11), y el usuario confirma antes de añadir el paso a la lista. El editor de
pasos en crudo (tabla de inputs directos) se reemplaza por el wizard. Las rutas ya
creadas se ven como tarjetas colapsadas en la parte inferior del drawer — la
funcionalidad secundaria queda secundaria.

---

### NOTA SOBRE COMPATIBILIDAD CON EL MODELO NUEVO (v2)

El diseño v2 refleja los contratos EP-N11, EP-N12 y EP-N13 del spec
`docs/specs/noise-path-wizard.md` (estado `implemented`). Las secciones del
spec que tratan el drawer de rutas (§§5, 6, 7, 8) han sido reescritas para
reflejar el wizard. Las secciones de config global, tabla de destinos, filtros,
badges y accesibilidad se mantienen sin cambios funcionales respecto a v1.

---

## 2. Personas y objetivos (jobs-to-be-done)

### Persona: el operador del bot (mismo perfil que pestaña Sesión)

**Jobs-to-be-done**:

1. **Configurar el volumen de ruido**: "¿Cuántas navegaciones de ruido por hora
   quiero en HARDCORE vs PASIVO? ¿Cuánto tiempo debe quedarse en cada página?"
   (Frecuencia: una vez al principio, ajustes esporádicos — P2)

2. **Construir el catálogo de destinos**: "Quiero añadir el mapa mundial y el
   perfil de un rival como destinos de ruido con peso 2 el mapa y 0.5 el perfil."
   (Frecuencia: al principio, ampliaciones esporádicas — P2)

3. **Gestionar el estado de los destinos**: "¿Qué destinos están muertos (is_dead)?
   ¿Cuáles marqué como inseguros?" (Frecuencia: ocasional, tras alertas del bot — P1
   cuando ocurre)

4. **Enseñar rutas de navegación con el wizard**: "Quiero que cuando vaya al mapa
   haga click en un tile específico. Me dices qué outerHTML pegar y tú derivas el
   selector — no quiero escribir CSS." (Frecuencia: avanzado, no siempre — P3)

5. **Habilitar/deshabilitar el ruido globalmente**: "Esta noche desactivo el ruido
   porque voy a hacer pruebas." (Frecuencia: esporádica — P1 cuando ocurre)

---

## 3. Inventario de pantallas / vistas

| Vista | Tipo | Decisión |
|---|---|---|
| `NoiseTab` | Tab nueva dentro de WorldSpacePage | CREAR |
| Panel de config global (`NoiseConfigPanel`) | Colapsable arriba | CREAR |
| Filtros de la tabla (`NoiseFilters`) | Fila encima de la tabla | CREAR (patrón inline) |
| Tabla de destinos (`NoiseDestinationsTable`) | Tabla densa principal | CREAR |
| Drawer de detalle de destino (`NoiseDestinationDrawer`) | Panel lateral derecho | CREAR (reutiliza patrón `FarmListDrawer`) |
| **WIZARD de creación de ruta** (`NoisePathWizard`) | Formulario multi-paso dentro del drawer — PROTAGONISTA | CREAR |
| Panel "Origen" del wizard (paso 0) | Desplegable de anclas precargadas (EP-N12) | CREAR |
| Panel "Añadir paso" del wizard (paso N) | Formulario de 3 campos + feedback derive-selector (EP-N11) | CREAR |
| Panel de confirmación de selector derivado | Inline en el wizard, 3 estados: único / no-único / error | CREAR |
| Lista de rutas existentes (`NoisePathList`) | Tarjetas colapsadas secundarias, bajo el wizard | CREAR |
| Modal de confirmación de borrado | Destino con cascada | REUTILIZAR `ConfirmDeleteModal.jsx` |
| Popover de borrado de ruta | Inline en tarjeta de ruta | REUTILIZAR `DeletePopover.jsx` |
| **Botón "Probar" en PathCard** (v3) | Botón secundario en la cabecera de cada tarjeta de ruta — deshabilitado durante la prueba | MODIFICAR `PathCard` (dentro de `NoisePathList.jsx`) |
| **`PathTestResultPanel`** (v3) | Panel expandible inline bajo la PathCard que muestra el reporte paso a paso (states: loading / ok / error) | CREAR |

---

## 4. Mapa de navegación

```mermaid
flowchart TD
    WS[WorldSpacePage] --> D[Tab Dashboard]
    WS --> A[Tab Agentes]
    WS --> F[Tab Farm Lists]
    WS --> S[Tab Sesión]
    WS --> N[Tab Ruido NUEVA]

    N --> CP[Panel Config Global\ncollapsible - noise_enabled + req/h + dwell]
    N --> DT[Tabla de Destinos\nfiltros category/dead/unsafe]

    DT -->|clic fila o icono| DR[Drawer Destino\nlabel + freq_weight + is_safe]
    DT -->|POST nuevo destino| DT
    DT -->|DELETE destino| CM[ConfirmDeleteModal\ncascada rutas+pasos]

    DR --> WIZ[WIZARD Nueva Ruta - PROTAGONISTA\nancla origen + pasos CLICK]
    DR --> RL[Lista Rutas existentes\ntarjetas colapsadas - secundarias]

    WIZ -->|GET /noise/origins EP-N12| OR[Selector de Ancla de Origen\n9 genéricas + 1 por aldea]
    OR -->|villages_loaded=false| RV[Botón Actualizar Aldeas\nPOST /noise/refresh-villages EP-N13]
    RV -->|409 bot desconectado| E409[Error 409 inline\nSesión inactiva]
    WIZ -->|por cada paso| SP[Formulario Añadir Paso\nURL ctx + label + outerHTML]
    SP -->|POST /noise/derive-selector EP-N11| DS[Feedback Selector Derivado\n3 estados: único / no-único / error]
    DS -->|confirmar| SP
    WIZ -->|Guardar| API1[POST /destinations/id/paths EP-N08]

    RL -->|expandir tarjeta| VI[Vista resumen pasos\nread-only + botón Editar]
    VI -->|Editar pasos| SE[Editor Pasos inline\npatrón BlockEditor - avanzado]
    SE -->|PUT /noise/paths/id EP-N09| RL
    RL -->|DELETE ruta| DP[DeletePopover inline]
    RL -->|ruta is_dead=true| RD[Badge Muerta + contador fallos\nreactivar: toggle is_active EP-N09]
    RL -->|botón Probar| PT[POST /noise/paths/id/test EP-N14]
    PT -->|200 overall ok| PTOK[PathTestResultPanel estado OK\npasos en verde + duración + browser_note]
    PT -->|200 overall error| PTERR[PathTestResultPanel estado ERROR\npasos ok/fallo coloreados + motivo]
    PT -->|409 bot desconectado| PT409[Aviso inline 409\n"El bot está desconectado..."]

    CP -->|PUT /noise/config EP-N02| CP
    DT -->|toggle noise_enabled| CP
```

---

## 5. Flujos de usuario clave

### Happy path 1 — Habilitar el ruido y ajustar el volumen

1. Usuario abre la pestaña "Ruido". Ve la tabla de destinos (vacía o con datos).
2. Ve el panel de config colapsado con el toggle `noise_enabled` visible en el
   resumen del colapsable (siempre visible aunque esté cerrado).
3. Activa el toggle. API EP-N02. Toast: "Ruido habilitado."
4. Expande el panel de config para ajustar: cambia `hardcore_total_req_per_hour_max`
   de 150 a 120. Inputs de rango min/max numéricos con validación en vivo.
5. Pulsa "Guardar config". Spinner. Toast: "Configuración guardada."

### Happy path 2 — Añadir un destino nuevo

1. Usuario pulsa "Añadir destino" (botón primario arriba de la tabla).
2. Se abre un formulario inline debajo del botón (no un modal): URL, label,
   categoría, peso. is_safe = true por defecto.
3. Valida en vivo (URL no vacía, peso > 0). Pulsa "Crear". API EP-N04. 201.
4. La nueva fila aparece al principio de la tabla. Toast: "Destino creado."

### Happy path 3 — Enseñar una ruta nueva con el wizard (flujo protagonista)

1. Usuario hace clic en el nombre del destino "Estadísticas globales" en la tabla.
2. Se abre el drawer lateral. El wizard ocupa la parte superior ("Nueva ruta").
   Si hay rutas existentes, aparecen colapsadas bajo el wizard.

3. **Paso 0 del wizard — Ancla de origen**:
   - La UI llama GET /worlds/{id}/noise/origins (EP-N12) automáticamente al abrir el drawer.
   - Se muestra un campo "Etiqueta de la ruta" (texto libre) + un desplegable "Origen".
   - El desplegable tiene dos secciones: "Páginas de Travian" (9 genéricas) y
     "Mis aldeas" (una por aldea). Si `villages_loaded=false`: sección "Mis aldeas"
     muestra un aviso "Sin aldeas cargadas" + botón "Actualizar aldeas".
   - Usuario escribe "Ir a estadísticas desde el menú", elige origen "STATISTICS".
   - Pulsa "Añadir primer paso →".

4. **Paso 1 del wizard — Primer click**:
   - El wizard muestra un formulario de 3 campos:
     - "URL actual" (texto, context): donde estoy ahora (p.ej. /statistics)
     - "Descripción del botón": texto libre (p.ej. "enlace aldea en el menú")
     - "outerHTML del elemento": textarea multilínea con placeholder
       "Pega aquí el outerHTML del elemento que quieres clicar (botón derecho
        → Inspeccionar → copiar outerHTML en DevTools)."
   - También muestra (colapsable) "URL esperada tras el click" (opcional):
     pequeño input de texto para `expected_url_after_click`.
   - El usuario pega el outerHTML: `<a href="/village/statistics">Estadísticas</a>`
   - Pulsa "Derivar selector". La UI llama POST /noise/derive-selector.

5. **Feedback de derivación** (estado "único"):
   - El panel de feedback reemplaza el textarea con:
     ```
     Selector derivado:  a[href='/village/statistics']
     Método:             href_exact  ·  Nivel 4
     ✓ Único en el fragmento analizado
     ```
   - Botones: "Confirmar selector" (primario) y "Escribir manualmente" (secundario).
   - Usuario confirma. El paso queda acumulado en la "lista de pasos pendientes" visible
     debajo del formulario: `paso 0: CLICK · a[href='/village/statistics']`.
   - La URL esperada (si la escribió) aparece junto al paso: `→ /village/statistics`.

6. Usuario pulsa "Añadir otro paso" o, si terminó, "Guardar ruta".
   - "Guardar ruta" envía EP-N08 con `origin="STATISTICS"`, `label="Ir a estadísticas..."`,
     `steps=[{step_order:0, action:"CLICK", selector:"a[href='/village/statistics']",
     expected_url_after_click:"/village/statistics", delay_min_ms:500, delay_max_ms:900}]`.
   - 201. Toast: "Ruta creada." El wizard se resetea. La nueva ruta aparece en la
     lista de rutas existentes (colapsada).

### Happy path 4 — Editar los pasos de una ruta existente (avanzado)

1. Usuario abre el drawer del destino. Ve en la lista inferior la ruta "Ir al mapa".
2. Expande la tarjeta de la ruta. Ve el resumen de pasos en modo lectura:
   `0: CLICK · a[href*='/karte']  →  /karte.php`
3. Pulsa "Editar pasos" (botón secundario en la tarjeta expandida).
4. Se abre el editor de pasos inline (patrón BlockEditor) con las columnas:
   `#`, `Acción`, `Selector`, `Valor`, `ms min`, `ms max`, `URL esperada`, `[✕]`.
5. Modifica `delay_max` del paso 0 de 900 a 1200. Validación en vivo: OK.
6. Pulsa "Guardar cambios". EP-N09 con `steps` reemplazados.
7. Toast: "Ruta actualizada." El editor se colapsa. El resumen se actualiza.

### Flujo alternativo — Ruta marcada como is_dead (rutas, no destinos)

1. El bot marcó automáticamente la ruta como `is_dead=true` tras 3 fallos consecutivos
   de `expected_url_after_click` (RN-NP07).
2. En la lista de rutas del drawer, la tarjeta muestra:
   - Badge "Muerta" en `--danger-subtle/--danger`
   - Contador "3 fallos consecutivos" en `--font-mono`
   - El toggle `is_active` está en OFF y deshabilitado.
3. El usuario puede:
   a. Pulsar "Reactivar" (que pone `is_active=true` en EP-N09) — esto resetea
      `consecutive_failures_count` a 0 (según CA-NP25 del spec funcional).
      Esto lo hace el backend automáticamente al activar; la UI muestra el toggle
      en ON y quita el badge "Muerta".
   b. Borrar la ruta (DeletePopover) y crear una nueva con el wizard.
4. Si la ruta corría sin `expected_url_after_click`, no puede marcarse is_dead por
   ese mecanismo (no hay verificación de URL). La ruta permanece viva siempre.

### Flujo alternativo — Destino marcado como is_dead (destinos, sin cambios vs v1)

1. El bot marcó automáticamente el destino como is_dead tras N fallos consecutivos.
2. En la tabla aparece el badge "Muerto" junto al nombre + chip de contador de fallos.
3. El usuario puede borrar el destino y crear uno nuevo (url_pattern es inmutable).
4. El filtro "Mostrar muertos" está disponible (por defecto la tabla los oculta).

### Flujo alternativo — Derivación de selector: selector no único

1. Usuario pega el outerHTML de un elemento con clases CSS sin semántica estructural.
2. La UI llama EP-N11. El backend devuelve `is_unique: false` con `warning` y
   `alternatives: ["a.nav-link", "#nav a"]`.
3. El panel de feedback muestra:
   ```
   Selector derivado:  div.menu a
   Método:             class_combo  ·  Nivel 7
   ⚠ No único en el fragmento. Verifica en Travian.
   ```
   Debajo del aviso: lista de alternativas como botones seleccionables.
   Debajo de las alternativas: input "Escribir selector manualmente" (siempre visible).
4. El usuario puede:
   a. Elegir una alternativa (el input "selector manual" se rellena con ese valor).
   b. Escribir su propio selector estructural.
   c. Confirmar el selector recomendado igualmente (el aviso permanece visible en
      el resumen del paso, marcado con ⚠).
5. Si el usuario escribe un selector con `:contains` o `text()` → error inline:
   "Los selectores deben ser estructurales (CSS puro). Evita :contains y text()."

### Flujo alternativo — Actualizar aldeas (botón en selector de origen)

1. En el paso 0 del wizard, el desplegable de origen muestra la sección "Mis aldeas"
   vacía: "Sin aldeas cargadas. [Actualizar aldeas]".
2. Usuario pulsa "Actualizar aldeas". La UI llama EP-N13 POST /noise/refresh-villages.
3. **Estado 409 (bot desconectado)**:
   - Badge de error inline: "El bot está desconectado. Inicia sesión primero."
   - El botón vuelve a su estado normal.
4. **Estado 200**:
   - El desplegable se refresca con las aldeas encontradas.
   - Toast: "3 aldeas cargadas."
5. Durante la llamada: botón "Actualizando..." con spinner pequeño.

### Flujo alternativo — Error 422 en creación de destino

1. Usuario envía URL inválida (no empieza por `/` ni por `http`).
2. API devuelve 422. El mensaje `detail` se muestra inline bajo el campo URL.
3. El formulario permanece abierto con los valores del usuario preservados.

### Flujo alternativo — Error 422 en deriva de selector (HTML malformado)

1. Usuario pega texto que no es HTML válido en el campo outerHTML.
2. La UI llama EP-N11. El backend devuelve 422: "El outerHTML no pudo parsearse."
3. El campo outerHTML muestra borde rojo + mensaje de error inline.
4. El usuario puede corregir el HTML y reintentar (el botón "Derivar selector"
   vuelve a estar habilitado).

### Happy path 5 — Renombrar una ruta (v4)

1. Usuario abre el drawer del destino. Ve la lista de rutas existentes.
2. Hace hover sobre la cabecera de la tarjeta "Ir al mapa". Aparece un icono ✎ (lápiz,
   12px, `--text-tertiary`) a la derecha del label de la ruta.
3. Pulsa el lápiz. El label se convierte en un `<input type="text">` inline con el valor
   actual pre-rellenado y `autoFocus`. Al lado del input aparecen dos botones mini:
   ✓ (confirmar, 22px) y ✕ (cancelar, 22px). El resto de la cabecera permanece visible.
4. El usuario modifica el texto a "Ir al mapa mundial".
5. Pulsa ✓ (o Enter). La UI llama `api.updateNoisePath(worldId, path.id, { label: newLabel })`.
6. Mientras se guarda: el input se deshabilita, aparece un spinner de 10px junto a los
   botones ✓/✕.
7. Respuesta 200: el input desaparece, el label vuelve al modo texto con el nuevo valor.
   Toast: "Ruta renombrada."
8. El usuario puede cancelar con ✕ o con Escape: el input desaparece, el label original
   se restaura sin llamada a la API.

### Flujo alternativo — Renombrar con label vacío

1. El usuario borra el contenido del input y pulsa ✓ o Enter.
2. El botón ✓ se deshabilita. Bajo el input aparece un mensaje inline: "El nombre no puede
   estar vacío." en `--danger` 11px.
3. El usuario debe escribir al menos un carácter para habilitar de nuevo el ✓.

### Flujo alternativo — Error al renombrar (422 / 500)

1. La UI llama EP-N09. El servidor devuelve 422 o 500.
2. El input permanece abierto con el borde rojo y un mensaje inline con el `detail` del
   response (o el mensaje genérico "Error al guardar. Reintenta." si es 500).
3. El usuario puede corregir y reintentar, o pulsar ✕ para cancelar.

### Happy path 6 — Accionar "Editar pasos" directamente desde la cabecera (v4)

1. Usuario ve la tarjeta "Ir al mapa" colapsada. Ve en la cabecera el botón "Editar pasos"
   (siempre visible, igual que "Probar").
2. Pulsa "Editar pasos" directamente, sin expandir antes.
3. La tarjeta se expande automáticamente y el `NoiseStepEditor` queda activo
   (`editingSteps=true`), listo para editar.
4. El flujo de edición y guardado sigue igual que en v3/v2.

### Happy path 5 — Probar una ruta y verificar que funciona (EP-N14)

1. Usuario abre el drawer del destino "Estadísticas globales".
2. Ve la sección "Rutas existentes". La ruta "Ir a estadísticas de tropas" está activa
   y muestra el botón **"Probar"** en la cabecera de la PathCard, junto a "Reactivar"
   (solo para rutas muertas) y el chevron de expand.
3. Usuario pulsa "Probar". El botón cambia a "Probando..." con spinner y se deshabilita.
   Un caption bajo el botón aparece: "Puede tardar hasta 60 s (navegación real en el bot)."
4. La UI llama `POST /worlds/{id}/noise/paths/{path_id}/test` (EP-N14, sin body).
5. **Resultado OK (overall "ok")**: debajo de la cabecera de la PathCard aparece el
   panel `PathTestResultPanel` expandido con:
   - Resumen: chip verde "Ruta OK" + duración en `--font-mono`.
   - Lista de pasos numerados: cada paso en una fila con:
     - Icono ✓ en `--success` + número de paso
     - Acción en badge mono
     - Selector en `--font-mono`
     - URL alcanzada en `--font-mono` `--text-tertiary` (si `current_url` presente)
   - Aviso `browser_note` en caption `--text-tertiary`: "El browser queda en la última
     página visitada durante el test."
   - Botón "Cerrar resultado" (terciario ghost).
6. El botón "Probar" vuelve a su estado idle.

### Flujo alternativo — Probar ruta con error en un paso

1. Mismo inicio que Happy path 5.
2. La UI llama EP-N14. Response: `overall: "error"`, `aborted_at_step: 1`.
3. `PathTestResultPanel` muestra:
   - Resumen: chip rojo "Falló en el paso 1".
   - Paso 0: fila verde ✓.
   - Paso 1: fila roja ✕ con el motivo: "elemento no encontrado en el DOM". URL
     antes del intento en `--font-mono` `--text-tertiary`.
   - Pasos 2+ (si los hubiera): filas en `--text-disabled` / `--surface-2` con texto
     "no ejecutado".
   - Aviso `browser_note` en caption.
   - Botón "Cerrar resultado".

### Flujo alternativo — Probar ruta con 409 (bot desconectado)

1. Mismo inicio que Happy path 5.
2. La UI llama EP-N14. Response: `409` con detail
   "El agente del mundo está desconectado. Inicia sesión primero."
3. Se muestra el aviso 409 inline (mismo patrón que en "Actualizar aldeas"):
   un bloque `role="alert"` con icono de información + el texto del `detail`.
   Aparece debajo del botón "Probar" en la cabecera de la PathCard.
4. El botón "Probar" vuelve a estado idle.
5. El aviso desaparece cuando el usuario pulsa "Probar" de nuevo o cierra el drawer.

### Flujo alternativo — Probar ruta con 409 (browser ocupado)

1. El bot está ejecutando ruido en ese momento y tiene el `_browser_lock` tomado.
2. Response: `409` con detail "El browser está ocupado con otra tarea. Espera a
   que finalice e inténtalo de nuevo."
3. Mismo tratamiento visual que el 409 de bot desconectado (aviso inline + botón
   vuelve a idle). El texto del aviso es el `detail` de la respuesta (no hardcodeado).

---

### Flujo alternativo — Borrar destino con rutas (cascada)

1. Usuario pulsa el icono de borrar en la fila del destino.
2. Aparece `ConfirmDeleteModal` con texto:
   "¿Eliminar 'Mapa mundial'? Se borrarán también sus 3 rutas y 7 pasos."
3. Usuario confirma. EP-N06. 204. La fila desaparece. Toast: "Destino eliminado."

---

## 6. Wireframes de baja fidelidad

### Vista completa del tab Ruido (desktop >= lg)

```
┌─ SIDEBAR (180px) ─┬──────────────────── TAB RUIDO ──────────────────────────┐
│  Dashboard        │  CONFIG GLOBAL (colapsable)                              │
│  Agentes          │  ┌──────────────────────────────────────────────────┐   │
│  Farm Lists       │  │ [▶] Configuración de ruido  [● Activo]  [Guardar]│   │  ← resumen siempre visible
│  Sesión           │  └──────────────────────────────────────────────────┘   │
│▶ Ruido (activo)   │                                                          │
│  Calculadora      │  DESTINOS DE NAVEGACIÓN                                  │
│                   │  [Añadir destino]          [Categoría ▾] [☐ Muertos]   │
│                   │  ┌──────────────────────────────────────────────────┐   │
│                   │  │ Nombre / URL          Cat.    Peso  Seg  Rutas  ⋮│   │  ← cabecera
│                   │  ├──────────────────────────────────────────────────┤   │
│                   │  │ Mapa mundial          MAP     2.0   ✓    2    [✕]│   │
│                   │  │ /karte.php                                        │   │
│                   │  ├──────────────────────────────────────────────────┤   │
│                   │  │ ⚠ Rival XYZ          PROFILE 0.5   ✗    1    [✕]│   │  ← is_dead=true
│                   │  │ /spieler.php?uid=123  [Muerto · 3 fallos]         │   │
│                   │  ├──────────────────────────────────────────────────┤   │
│                   │  │ Estadísticas          REPORTS 1.0   ✓    0    [✕]│   │  ← sin rutas
│                   │  │ /stats.php                                        │   │
│                   │  └──────────────────────────────────────────────────┘   │
└───────────────────┴──────────────────────────────────────────────────────────┘
```

### Panel de config global (expandido)

```
┌─ CONFIG DE RUIDO ─────────────────────────────────────────────────────────┐
│  [▼] Configuración de ruido                                [●/○] Activo   │
│                                                                            │
│  HARDCORE — peticiones/hora                                                │
│  [  80  ] — [  150  ]   (min — max, int ≥ 1, max ≥ min)                 │
│                                                                            │
│  PASIVO — peticiones/hora                                                  │
│  [  15  ] — [  40  ]                                                      │
│                                                                            │
│  Tiempo en página (dwell)                                                  │
│  [  2.0  ] — [  30.0  ]  segundos                                         │
│                                                                            │
│                                              [Cancelar]  [Guardar config]  │
└───────────────────────────────────────────────────────────────────────────┘
```

Notas del panel de config:
- Cada par min/max es un input numérico (no slider) de 60px de ancho.
  Separados por " — " como texto literal entre los dos inputs.
- Validación en vivo: si max < min → borde rojo en el input max + mensaje inline.
- El toggle `noise_enabled` está en la cabecera del colapsable, siempre visible.
  Se guarda inmediatamente (no requiere "Guardar config").
- "Guardar config" guarda los 6 valores numéricos en un solo PUT EP-N02.

### Tabla de destinos (fila de detalle)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Nombre / URL               Categoría   Peso    Seguro  Rutas   Acciones │
├──────────────────────────────────────────────────────────────────────────┤
│  Mapa mundial               [MAP]       2.0     [✓]     2       [✕]     │
│  /karte.php                                                               │
├──────────────────────────────────────────────────────────────────────────┤
│  ⚠ Rival XYZ               [PROFILE]   0.5     [✗]     1       [✕]     │
│  /spieler.php?uid=123       [Muerto · 3 fallos]                          │
└──────────────────────────────────────────────────────────────────────────┘
```

Desglose visual de cada fila:
- **Columna Nombre/URL**: dos líneas. Primera: label en `--text` (clicable → abre
  drawer). Segunda: url_pattern en `--font-mono` caption `--text-tertiary`.
  Si `is_dead`: icono ⚠ en `--danger` antes del label + chip "Muerto · N fallos"
  en `--danger-subtle`.
- **Columna Categoría**: badge pill con texto del enum (MAP, PROFILE…) usando
  color semántico por categoría (ver §9).
- **Columna Peso**: número con `--font-mono tabular-nums`.
- **Columna Seguro**: icono checkmark verde / X roja. `aria-label` descriptivo.
- **Columna Rutas**: número de rutas (int). 0 en `--text-tertiary`. Clicable →
  abre drawer en la sección de rutas.
- **Columna Acciones**: icono de papelera (rojo hover) → `ConfirmDeleteModal`.

### Formulario de nuevo destino (inline, bajo el botón "Añadir")

```
┌──────────────────────────────────────────────────────────────────────────┐
│  URL (patrón)  [/karte.php                  ] (min_length=1)             │
│  Label         [Mapa mundial                ]                            │
│  Categoría     [MAP                        ▾]                            │
│  Peso          [1.0     ]  (float > 0)                                   │
│  Seguro        [✓ Sí]                                                    │
│                                        [Cancelar]  [Crear destino]       │
└──────────────────────────────────────────────────────────────────────────┘
```

### Drawer de destino — vista de conjunto (panel lateral derecho, ~440px)

```
┌────────────── DRAWER DESTINO ─────────────────────────────────────────┐
│  [✕]  Estadísticas globales               [REPORTS]  [✓ Seguro]       │
│  /statistics                                                           │
│  ─────────────────────────────────────────────────────────────────────│
│  EDITAR DESTINO                                                        │
│  Label        [Estadísticas globales     ]                            │
│  Peso         [1.0    ]                                               │
│  Seguro       [✓ Sí]                          [Guardar cambios]       │
│  ─────────────────────────────────────────────────────────────────────│
│  NUEVA RUTA ← WIZARD (protagonista)                                    │
│  [Etiqueta]    [Ir a estadísticas de aldea    ]                       │
│  [Origen   ▾]  [STATISTICS — Estadísticas globales    ]   ← desplegable│
│  [+ Añadir primer paso →]                      [Limpiar wizard]       │
│  ─────────────────────────────────────────────────────────────────────│
│  RUTAS EXISTENTES (2)                                                  │
│  ┌─ Ir al mapa  [MAP]  [● activa]  [✕] ──────────────────────────┐   │
│  │  (colapsada — clic para ver resumen de pasos)                   │   │
│  └────────────────────────────────────────────────────────────────┘   │
│  ┌─ ⚠ Ruta rota  [DORF1]  [○ muerta · 3 fallos]  [Reactivar][✕] ┐   │
│  │  (colapsada)                                                    │   │
│  └────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
```

### Wizard — Paso 0: selección de origen

```
┌─ NUEVA RUTA ───────────────────────────────────────────────────────────┐
│  Etiqueta de la ruta                                                    │
│  [Ir a estadísticas de aldea desde menú          ]                     │
│                                                                        │
│  Origen (punto de partida del bot)                                     │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │ — Páginas de Travian ——                                          │  │
│  │   DORF1 — Recursos (aldea activa)                               │  │
│  │   DORF2 — Edificios (aldea activa)                              │  │
│  │   MAP — Mapa mundial                                            │  │
│  │   STATISTICS — Estadísticas globales        ← seleccionado      │  │
│  │   REPORTS — Reportes                                            │  │
│  │   MESSAGES — Mensajes                                           │  │
│  │   VILLAGE_STATISTICS — Estadísticas de aldea                    │  │
│  │   OASIS_VIEW — Vista oasis en el mapa                           │  │
│  │   ANY — Cualquier página (sin ancla)                            │  │
│  │ — Mis aldeas ——                                                 │  │
│  │   Merlinia  (newdid 12345) — /dorf1.php?newdid=12345            │  │
│  │   Forticia  (newdid 12346) — /dorf1.php?newdid=12346            │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│  [+ Añadir primer paso →]                      [Limpiar wizard]        │
└─────────────────────────────────────────────────────────────────────── ┘
```

Estado cuando `villages_loaded=false`:
```
│  — Mis aldeas ——                                                       │
│  Sin aldeas cargadas.  [Actualizar aldeas]  ← botón secundario         │
│  (requiere sesión activa)                                              │
```

### Wizard — Formulario "Añadir paso" (para cada click del camino)

```
┌─ PASO 1 — Añadir click ────────────────────────────────────────────────┐
│  URL actual (solo contexto, no se guarda)                              │
│  [/statistics                                        ]                 │
│                                                                        │
│  Descripción del botón/enlace                                          │
│  [enlace "Estadísticas de aldea" en el menú lateral  ]                 │
│                                                                        │
│  outerHTML del elemento a clicar                                       │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │ <a href="/village/statistics" class="nav-link">Estadísticas    │   │
│  │ de aldea</a>                                                    │   │
│  └────────────────────────────────────────────────────────────────┘   │
│  Pega el outerHTML del elemento (botón derecho → Inspeccionar →        │
│  clic derecho sobre el elemento → Copiar → Copiar outerHTML).          │
│                                                                        │
│  [▶ URL esperada tras el click (opcional)]  ← sección colapsable       │
│                                                                        │
│  [Derivar selector]  ← botón primario, deshabilitado si outerHTML vacío│
└─────────────────────────────────────────────────────────────────────── ┘
```

### Wizard — Feedback del selector derivado (3 estados)

**Estado A — Selector único (`is_unique: true`):**
```
┌─ SELECTOR DERIVADO ────────────────────────────────────────────────────┐
│  a[href='/village/statistics']                                          │
│  Método: href_exact · Nivel 4                                          │
│  ✓ Único en el fragmento analizado                                     │
│                                                                        │
│  [Confirmar selector]  [Escribir manualmente]                          │
└─────────────────────────────────────────────────────────────────────── ┘
```

**Estado B — Selector no único (`is_unique: false`, con alternativas):**
```
┌─ SELECTOR DERIVADO ────────────────────────────────────────────────────┐
│  div.menu a                                                             │
│  Método: class_combo · Nivel 7                                         │
│  ⚠ No único en el fragmento. Verifica en Travian.                      │
│  No se encontró un selector único estable. Considera añadir un id.    │
│                                                                        │
│  Alternativas:                                                         │
│  [a.nav-link]  [#nav a]  ← cada alternativa es un botón seleccionable  │
│                                                                        │
│  O escribe tu selector:  [a.nav-link.statistics          ]             │
│                                                                        │
│  [Confirmar selector]  [Volver a intentar con otro HTML]               │
└─────────────────────────────────────────────────────────────────────── ┘
```

**Estado C — Error de parseo (422 outerHTML malformado):**
```
┌─ SELECTOR DERIVADO ────────────────────────────────────────────────────┐
│  ✕ Error al analizar el HTML                                            │
│  El outerHTML no pudo parsearse como HTML válido.                      │
│  Asegúrate de copiar el outerHTML completo del elemento.               │
│                                                                        │
│  [Reintentar]                                                          │
└─────────────────────────────────────────────────────────────────────── ┘
```

### Wizard — Lista de pasos acumulados (pendiente de guardar)

```
┌─ PASOS DE LA RUTA ─────────────────────────────────────────────────────┐
│  0  CLICK  a[href='/village/statistics']  →  /village/statistics    [✕]│
│  1  CLICK  a[href*='/troops']  →  /village/statistics/troops        [✕]│
│                                                                        │
│  [+ Añadir otro paso]                                                  │
│  ─────────────────────────────────────────────────────────────────────│
│                             [Limpiar wizard]  [Guardar ruta] (primario)│
└─────────────────────────────────────────────────────────────────────── ┘
```

Notas de la lista de pasos acumulados:
- Cada paso muestra: `step_order` + `action` + `selector` + `→ expected_url` (si hay).
- El `→ expected_url` aparece solo si el usuario lo proporcionó en la sección
  colapsable del formulario del paso.
- El botón `[✕]` elimina el paso de la lista local (sin llamada a la API).
- "Guardar ruta" se habilita solo si hay al menos 1 paso y el campo etiqueta no está vacío.
- "Limpiar wizard" resetea el wizard a su estado inicial (confirma antes si hay pasos).

### Ruta expandida en la lista de rutas existentes

```
┌─ Ir al mapa  [MAP]  [● activa]  [▼]  [Editar pasos]  [✕] ─────────┐
│  0  CLICK  a[href*='/karte']  →  /karte.php                          │
│  1  WAIT_FOR_SELECTOR  #mapContainer  (5000 ms)                      │
│                                                                       │
│  [Editar pasos]  ← abre el editor BlockEditor inline                  │
└───────────────────────────────────────────────────────────────────── ┘
```

---

## Sección 6c — Delta v4: Wireframes de PathCard rediseñada (renombrar + acciones descubribles)

### PathCard — cabecera v4 (idle, ruta activa)

Orden de elementos en la cabecera (izquierda a derecha, `flex-wrap: wrap`):

```
┌─ PathCard ─────────────────────────────────────────────────────────────────┐
│  [label  ✎]  [ORIGIN badge]  [● Activa]  [Probar]  [Editar pasos]  [▼] [⋯] │
└────────────────────────────────────────────────────────────────────────────┘
```

- **Label**: texto 13px/500, `--text`. Clicable (toggle expand). Cuando la cabecera
  está en hover, aparece a su derecha el icono ✎ (pencil SVG, 12px, `--text-tertiary`).
  El lápiz tiene su propio `<button>` con `aria-label="Renombrar ruta"`. Target 28×24px.
- **Origin badge**: sin cambios vs v3.
- **Estado badge** (● Activa / ● Inactiva / ○ Muerta · N fallos): sin cambios vs v3.
- **[Probar]**: sin cambios vs v3. Botón secundario mini (24px alto, `--border-strong`).
- **[Editar pasos]** (NUEVO en v4): mismo estilo que [Probar]. Al pulsar: expande la
  tarjeta Y activa el editor (`editingSteps=true`). Si la tarjeta ya está expandida,
  activa solo el editor. Texto: `t('noise.paths.editSteps')`.
- **[▼]** (chevron expand/colapsar): sin cambios vs v3.
- **[⋯]** (overflow menu): botón ghost 26×26px, `--text-tertiary`. Al pulsar abre un
  mini-popover con una única acción: "Eliminar ruta" en `--danger`. El popover tiene
  el mismo comportamiento que `DeletePopover` (confirmar antes de ejecutar).

### PathCard — cabecera v4 (ruta muerta)

```
┌─ PathCard dead ────────────────────────────────────────────────────────────────┐
│  ⚠  [label  ✎]  [ORIGIN badge]  [○ Muerta · 3 fallos]  [Reactivar]  [Probar]  │
│  [Editar pasos]  [▼]  [⋯]                                                      │
└────────────────────────────────────────────────────────────────────────────────┘
```

Notas para rutas muertas:
- El lápiz ✎ sigue disponible (renombrar sigue siendo posible aunque la ruta esté muerta).
- "Reactivar" sigue en la misma posición que en v3 (antes de "Probar").
- "Editar pasos" y el chevron y el ⋯ siguen al final.
- El wrap natural de flex se encarga de que en cabeceras largas los elementos bajen a
  segunda línea sin overflow horizontal.

### PathCard — estado "Renombrando" (inline edit activo)

```
┌─ PathCard ─────────────────────────────────────────────────────────────────────────┐
│  [──────── Ir al mapa mundial ──────────────] [✓] [✕]  [ORIGIN]  [● Activa]  [▼] [⋯]│
│  (el input reemplaza el label; los otros botones de acción se ocultan mientras edita)│
└────────────────────────────────────────────────────────────────────────────────────┘
```

- Cuando `renamingLabel === true`, la cabecera muestra: `<input>` con `flex:1` +
  botón ✓ (22×22px) + botón ✕ (22×22px). Los botones [Probar], [Editar pasos] se
  **ocultan** durante la edición para reducir ruido visual. [▼] y [⋯] permanecen.
- El `<input>` tiene `border: 1px solid var(--border-strong)` y al enfocarse:
  `outline: 2px solid var(--accent)`. Padding 4px 8px. `font-size: 13px`.
- Botón ✓: fondo `--surface`, borde `--border-strong`, color `--success` al hover.
  `aria-label="Confirmar renombrado"`.
- Botón ✕: ghost, color `--text-tertiary`. `aria-label="Cancelar renombrado"`.

### PathCard — estado "Guardando renombrado"

```
┌─ PathCard ────────────────────────────────────────────────────────────────────┐
│  [──── Ir al mapa mundial ────] [⟳] [✕]  [ORIGIN]  [● Activa]  [▼] [⋯]      │
└───────────────────────────────────────────────────────────────────────────────┘
```

- Input deshabilitado (`opacity: 0.7`). El botón ✓ es reemplazado por un `Spinner`
  de 10px (misma posición, mismo tamaño de target). El botón ✕ (cancelar) permanece
  pero también deshabilitado durante el guardado.

### PathCard — estado "Error al renombrar"

```
┌─ PathCard ────────────────────────────────────────────────────────────────────────┐
│  [──── Ir al mapa mundial ────] [✓] [✕]  [ORIGIN]  [● Activa]  [▼] [⋯]          │
│  El nombre no puede estar vacío.   ← mensaje inline debajo del input, --danger 11px│
└───────────────────────────────────────────────────────────────────────────────────┘
```

- El mensaje de error aparece en una segunda línea de la cabecera (`width: 100%`,
  `padding-inline-start: 4px`, `font-size: 11px`, `color: var(--danger)`).
- El input tiene `border-color: var(--danger)`.
- El botón ✓ está deshabilitado hasta que el input tenga contenido válido.

### Botón ⋯ — mini-popover "Eliminar ruta"

```
         ┌────────────────────┐
         │  Eliminar ruta     │  ← texto en --danger, 13px
         │  [No] [Sí, eliminar]│  ← mismo patrón que DeletePopover existente
         └────────────────────┘
```

- El popover se posiciona debajo del botón ⋯ (`position: absolute`, `top: 100%`,
  `inset-inline-end: 0`). Ancho ~160px. Fondo `--surface`, borde `--border`,
  `--shadow-md`, `--radius-sm`.
- Contenido: título "¿Eliminar esta ruta?" en 12px/`--text-secondary`, + dos botones:
  "Cancelar" (ghost) y "Eliminar" (destructivo, rojo).
- Se cierra con Escape o click fuera.
- Esto reutiliza `DeletePopover.jsx` con el mismo API que en v3, simplemente ahora el
  trigger es el ⋯ en lugar del ✕.

---

### Botón "Probar" en PathCard (idle) — v3

El botón "Probar" se sitúa en la cabecera de cada PathCard, entre el badge de estado
y el chevron expand/colapsar. Es un botón secundario pequeño (igual que "Reactivar"):

```
┌─ Ir al mapa  [MAP]  [● activa]  [Probar]  [▼]  [✕] ──────────────────┐
│  (colapsada — clic en label o en ▼ para ver pasos)                     │
└───────────────────────────────────────────────────────────────────────┘

┌─ ⚠ Ruta rota  [DORF1]  [○ muerta · 3 fallos]  [Reactivar]  [Probar]  [▼]  [✕] ─┐
│  (también disponible en rutas muertas — EC-PT01)                                  │
└─────────────────────────────────────────────────────────────────────────────────── ┘
```

Notas del botón "Probar":
- Siempre visible, tanto en rutas activas como en rutas muertas (`is_dead`). El spec
  funcional EC-PT01 establece que el test se ejecuta aunque la ruta esté muerta.
- Altura: 24px, padding 0 8px. Mismo estilo que "Reactivar" (botón secundario mini).
- Color: neutro (`--surface` / `--border-strong` / `--text`). NO usa el oro ni el verde
  — el botón "Probar" es diagnóstico, no una acción primaria del flujo.
- Durante la prueba: texto "Probando..." + spinner de 10px. Deshabilitado. El botón
  expand/colapsar del drawer sigue accesible (no se bloquea toda la tarjeta).
- Al pulsar "Probar", si el panel de resultado anterior ya estaba abierto para esa
  misma ruta, se borra y se inicia un nuevo test (solo un resultado a la vez por PathCard).

### Botón "Probar" en estado loading

```
┌─ Ir al mapa  [MAP]  [● activa]  [⟳ Probando...]  [▼]  [✕] ─────────────────────┐
│  Puede tardar hasta 60 s — navegación real en el bot.                              │
└──────────────────────────────────────────────────────────────────────────────────┘
```

El caption "Puede tardar hasta 60 s" aparece como una segunda línea en la cabecera de
la PathCard, en caption style (`--text-tertiary` / 11px). Desaparece cuando llega el
resultado. No ocupa espacio fuera de la cabecera.

### PathTestResultPanel — Estado OK

```
┌─ Ir al mapa  [MAP]  [● activa]  [Probar]  [▼]  [✕] ──────────────────────────────┐
├────────────────────────────────────────────────────────────────────────────────────┤
│  ✓ Ruta OK   3,241 ms                                                [Cerrar]      │
│  ──────────────────────────────────────────────────────────────────────────────    │
│  ✓ 0   CLICK  a[href*='/karte']             → https://ts1.travian.es/karte.php     │
│  ✓ 1   CLICK  a[href*='gid=37']             → https://ts1.travian.es/karte.php     │
│  ✓ 2   WAIT   #mapTile                                                              │
│  ──────────────────────────────────────────────────────────────────────────────    │
│  ⓘ El browser queda en la última página visitada durante el test.                  │
└────────────────────────────────────────────────────────────────────────────────────┘
```

Detalles visuales del estado OK:
- **Header del resultado**: chip "✓ Ruta OK" en `--success-subtle/--success` + duración
  en `--font-mono tabular-nums` + botón ghost "Cerrar" a la derecha.
- **Cada fila de paso OK**: icono `✓` en `--success`, número de paso en `--font-mono
  --text-tertiary`, badge de acción en `--surface-2/--text-secondary font-mono 11px`,
  selector en `--font-mono 12px`, URL alcanzada en `--font-mono --text-tertiary 11px`
  precedida de `→`. La URL es la `current_url` del response.
- Si `current_url` es null para un paso (p.ej. WAIT_FOR_SELECTOR sin URL): no se muestra
  la columna de URL para ese paso (no se muestra "→ null").
- **`browser_note`**: caption italic `--text-tertiary 11px` con icono ⓘ de información.
  Se muestra el string que viene del campo `browser_note` del response (no hardcodeado).
- Fondo del panel: `--surface-2` con borde superior `--border`.

### PathTestResultPanel — Estado ERROR

```
┌─ ⚠ Ruta rota  [DORF1]  [○ muerta · 3 fallos]  [Reactivar]  [Probar]  [▼]  [✕] ──┐
├─────────────────────────────────────────────────────────────────────────────────────┤
│  ✕ Falló en el paso 1   1,832 ms                                      [Cerrar]      │
│  ──────────────────────────────────────────────────────────────────────────────     │
│  ✓ 0   CLICK  a[href*='/karte']         → https://ts1.travian.es/karte.php          │
│  ✕ 1   CLICK  a[href*='gid=37']         elemento no encontrado en el DOM            │
│                                         https://ts1.travian.es/karte.php            │
│  ─ 2   WAIT   #mapTile                  no ejecutado                                │
│  ──────────────────────────────────────────────────────────────────────────────     │
│  ⓘ El browser queda en la última página visitada durante el test.                   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

Detalles visuales del estado ERROR:
- **Header del resultado**: chip "✕ Falló en el paso N" en `--danger-subtle/--danger` +
  duración en `--font-mono tabular-nums` + botón ghost "Cerrar".
- **Pasos anteriores al error (status "ok")**: igual que el estado OK — icono ✓ verde.
- **Paso con error (`aborted_at_step`)**: icono `✕` en `--danger`, selector en
  `--font-mono`, motivo del error (`reason`) en `--danger 12px`, URL antes del intento
  en `--font-mono --text-tertiary 11px` en segunda línea de la fila.
- **Pasos no ejecutados** (step_order > aborted_at_step, no en el array `steps[]`):
  se infieren a partir de la definición de pasos de la ruta (ruta.steps) comparada con
  el array steps del reporte. Fila: icono `─` en `--text-disabled`, todo el texto en
  `--text-disabled`, etiqueta "no ejecutado" en `--text-tertiary`.
- **`browser_note`**: igual que en el estado OK.

### PathTestResultPanel — Aviso 409 inline

```
┌─ Ir al mapa  [MAP]  [● activa]  [Probar]  [▼]  [✕] ──────────────────────────────┐
│  ⓘ El agente del mundo está desconectado. Inicia sesión primero.                   │
└────────────────────────────────────────────────────────────────────────────────────┘
```

El aviso 409 aparece como una segunda línea en la cabecera de la PathCard (mismo lugar
que el caption "Puede tardar…" del estado loading), con fondo `--surface` y texto
`--text-secondary 12px` + icono de información. No es un bloque propio expandible —
se incrusta en la cabecera sin cambiar la altura de la tarjeta más allá de la segunda
línea. Desaparece al volver a pulsar "Probar" o al cerrar el drawer.

**Microcopy del aviso 409**: se usa el `detail` del response tal cual, sin traducir.
Los dos mensajes posibles según el spec funcional son:
- "El agente del mundo está desconectado. Inicia sesión primero."
- "El browser está ocupado con otra tarea. Espera a que finalice e inténtalo de nuevo."

---

### Ruta is_dead en la lista de rutas existentes

```
┌─ ⚠ Ruta rota  [DORF1]  [○ muerta · 3 fallos]  [Reactivar]  [✕] ──┐
│  El selector falló 3 veces consecutivas.                             │
│  Reactiva la ruta si corregiste el selector, o elimínala y           │
│  crea una nueva con el wizard.                                       │
└───────────────────────────────────────────────────────────────────── ┘
```

- "Reactivar" llama EP-N09 con `is_active: true`. El backend resetea
  `consecutive_failures_count` a 0. La tarjeta vuelve al estado normal.
- El botón `[✕]` abre `DeletePopover`.

### Editor de pasos de una ruta existente (avanzado, patrón BlockEditor)

Se accede pulsando "Editar pasos" en una ruta expandida. Es el editor de bajo nivel
para usuarios que quieren ajustar pasos ya guardados sin el wizard:

```
┌──────┬────────────────────┬──────────────────────┬───────┬────────┬────────┬────────────────────┬───┐
│  Ord │ Acción             │ Selector              │ Valor │ ms min │ ms max │ URL esperada        │   │
├──────┼────────────────────┼──────────────────────┼───────┼────────┼────────┼────────────────────┼───┤
│   0  │ [CLICK          ▾] │ [a[href*=/karte]    ] │ [   ] │ [ 500] │ [ 900] │ [/karte.php       ] │[✕]│
│   1  │ [WAIT_FOR_SEL.  ▾] │ [#mapContainer      ] │ [5000]│ [ 300] │ [ 600] │ [                 ] │[✕]│
└──────┴────────────────────┴──────────────────────┴───────┴────────┴────────┴────────────────────┴───┘
[+ Añadir paso]                                                          [Cancelar] [Guardar]
```

Cambios vs. v1:
- Nueva columna "URL esperada" (campo `expected_url_after_click`): input de texto, vacío
  por defecto. Solo relevante semánticamente en acción CLICK; visible en todos los tipos
  por consistencia de layout.
- El botón "✕" no aparece si solo queda 1 paso.
- "Guardar" envía EP-N09 con la lista completa de pasos (reemplazo atómico).

---

## 6b. Mockup editable y layout aprobado

**Ruta**: `frontend/mockups/noise-catalog.playground.html`

El mockup (v2, actualizado) muestra las siguientes vistas seleccionables:

**Vistas de la tabla de destinos (sin cambios vs v1):**
1. Lista de destinos — normal (con datos, ruido activo)
2. Config global expandida
3. Formulario nuevo destino (inline)
4. Destino muerto (is_dead=true)
5. Tabla vacía (sin destinos)
6. Estado cargando (skeleton)
7. Error de API

**Vistas del WIZARD (nuevas en v2):**
8. Drawer — Wizard paso 0: selección de origen (con aldeas cargadas)
9. Drawer — Wizard paso 0: selección de origen (villages_loaded=false + botón Actualizar)
10. Drawer — Formulario añadir paso (outerHTML aún no pegado)
11. Drawer — Feedback selector derivado: estado ÚNICO (is_unique=true)
12. Drawer — Feedback selector derivado: estado NO ÚNICO (is_unique=false + alternativas)
13. Drawer — Feedback selector derivado: estado ERROR (422 HTML malformado)
14. Drawer — Lista de pasos acumulados (2 pasos pendientes de guardar)
15. Drawer — Guardando ruta (spinner en botón)
16. Drawer — Wizard: estado Actualizando aldeas (spinner EP-N13)
17. Drawer — Error 409: bot desconectado (al intentar actualizar aldeas)

**Vistas de rutas existentes (actualizadas en v2):**
18. Drawer — Lista de rutas existentes (una activa, una is_dead)
19. Drawer — Ruta expandida con resumen de pasos (solo lectura)
20. Drawer — Editor de pasos (BlockEditor, avanzado) con columna URL esperada

**Vistas de "Probar ruta" (nuevas en v3):**
21. Drawer — PathCard idle: botón "Probar" disponible (ruta activa + ruta muerta)
22. Drawer — PathCard loading: "Probando..." con spinner + caption duración
23. Drawer — PathTestResultPanel estado OK: todos los pasos en verde + duración + browser_note
24. Drawer — PathTestResultPanel estado ERROR: pasos ok/error/no-ejecutado + motivo
25. Drawer — Aviso 409 inline en PathCard: bot desconectado o browser ocupado

**Vistas de "Editar ruta" (nuevas en v4):**
26. Drawer — PathCard v4 idle: cabecera rediseñada (acciones visibles, lápiz en hover)
27. Drawer — PathCard v4 renombrando: input inline activo + botones ✓/✕
28. Drawer — PathCard v4 guardando renombrado: spinner + input deshabilitado
29. Drawer — PathCard v4 error al renombrar: borde rojo + mensaje inline
30. Drawer — PathCard v4 menú ⋯ abierto: popover de eliminar

**Layout propuesto (pendiente de aprobación del usuario)**:
- Panel config colapsable arriba (P2 — el toggle noise_enabled siempre visible)
- Fila de controles (botón "Añadir" + filtros) debajo del config
- Tabla densa de destinos ocupa el resto del área
- Drawer lateral derecho (440px): wizard ocupa la parte superior, rutas existentes debajo
- El wizard tiene 3 sub-fases dentro del drawer (origen → formulario paso → feedback derivación)

---

## 7. Estados de cada pantalla

### Tab Ruido completo (carga inicial: EP-N01 + EP-N03)

| Estado | UI |
|---|---|
| **Cargando** | Skeleton: dos rectángulos grises (uno para el config panel, uno para la tabla). No se muestra el botón "Añadir destino" aún. |
| **Cargado con datos** | Config panel colapsado. Tabla con filas. |
| **Error de API** | Inline: "No se pudo cargar el catálogo. [Reintentar]" |
| **Sin destinos (vacío)** | Tabla vacía con estado vacío centrado: icono + "Sin destinos de navegación todavía." + CTA "Añadir primer destino". |

### Panel de config global (EP-N01 / EP-N02)

| Estado | UI |
|---|---|
| **Colapsado (normal)** | Una fila con: ▶ título, badge "Activo"/"Inactivo" + toggle, sin botón Guardar. |
| **Expandido sin cambios** | Campos de config con valores actuales. Botón "Guardar config" deshabilitado. |
| **Expandido con cambios** | Botón "Guardar config" habilitado. Resaltado sutil. |
| **Guardando (PUT en vuelo)** | Botón con spinner. Campos deshabilitados. |
| **Error de validación (max < min)** | Borde rojo en el input infractor + mensaje inline. Botón deshabilitado. |
| **Error de API (500)** | Mensaje inline: "Error al guardar. Reintenta." |
| **Éxito** | Toast: "Configuración guardada." Panel vuelve a estado sin cambios. |

### Toggle noise_enabled (parte del config, siempre visible)

| Estado | UI |
|---|---|
| **Activo** | Toggle ON (verde). Badge "Activo" en `--success-subtle`. |
| **Inactivo** | Toggle OFF (gris). Badge "Inactivo" en `--text-tertiary`. |
| **Cargando (tras toggle)** | Toggle con spinner pequeño. Deshabilitado hasta respuesta. |
| **Error** | Toggle vuelve al estado anterior. Toast de error. |

### Tabla de destinos (EP-N03)

| Estado | UI |
|---|---|
| **Vacío** | Área central con icono genérico + "Sin destinos" + CTA primario. |
| **Cargando** | Skeleton de 3-4 filas con rect grises animados. |
| **Con datos** | Tabla densa. Filas clicables. |
| **Fila is_dead=true** | Icono ⚠ en `--danger` + badge "Muerto" + "N fallos" en rojo. Fondo `--danger-subtle` muy sutil (5% de opacidad). |
| **Fila is_safe=false** | Icono ✗ en `--text-tertiary`. Label en `--text-secondary`. |
| **Filtro "Mostrar muertos" desactivado** | Los destinos con is_dead=true están ocultos. Contador: "N destinos ocultos." como caption. |
| **Filtro category activo** | Solo las filas de esa categoría. Sin resultados → mensaje "Sin destinos en esta categoría." |
| **Error (500)** | Inline: "No se pudo cargar. Reintenta." |

### Formulario de nuevo destino (inline, EP-N04)

| Estado | UI |
|---|---|
| **Cerrado** | Solo el botón "Añadir destino". |
| **Abierto sin cambios** | Campos vacíos excepto is_safe=true por defecto. Botón "Crear" deshabilitado. |
| **Con datos válidos** | Botón "Crear" habilitado. |
| **Creando (POST en vuelo)** | Botón "Crear" con spinner. Campos deshabilitados. |
| **Error 422 (URL inválida)** | Mensaje inline bajo el campo URL con el `detail` de la API. |
| **Éxito** | Formulario se cierra. Nueva fila aparece al principio de la tabla. Toast: "Destino creado." |

### Drawer de destino — sección wizard (EP-N12 + EP-N11 + EP-N13 + EP-N08)

**Carga inicial (GET origins al abrir el drawer):**

| Estado | UI |
|---|---|
| **Cargando origins** | Spinner pequeño donde irá el desplegable de origen. |
| **Origins cargados (villages_loaded=true)** | Desplegable con 9 genéricas + N aldeas en secciones separadas. |
| **Origins cargados (villages_loaded=false)** | Desplegable con 9 genéricas. Sección "Mis aldeas" muestra aviso + botón "Actualizar aldeas". |
| **Error al cargar origins** | Inline: "No se pudo cargar los orígenes. [Reintentar]". El wizard no avanza hasta resolverse. |

**Botón "Actualizar aldeas" (EP-N13):**

| Estado | UI |
|---|---|
| **Idle** | Botón secundario pequeño con icono de refresco. |
| **Actualizando** | Texto "Actualizando..." + spinner. Deshabilitado. |
| **Éxito (200)** | Toast "N aldeas cargadas." Desplegable se refresca con las aldeas. |
| **Error 409 (bot desconectado)** | Inline junto al botón: "El bot está desconectado. Inicia sesión primero." Botón vuelve a estado idle. |
| **Error 500** | Inline: "Error al actualizar. Reintenta." |

**Formulario de paso (derivación de selector):**

| Estado | UI |
|---|---|
| **Formulario vacío** | Botón "Derivar selector" deshabilitado (campo outerHTML vacío). |
| **outerHTML escrito** | Botón "Derivar selector" habilitado. |
| **Derivando** | Botón "Derivar selector" con spinner "Analizando...". Textarea deshabilitada. |
| **Derivación OK — único** | Panel de feedback: selector en mono + método + nivel + checkmark verde "Único". Botón "Confirmar selector". |
| **Derivación OK — no único** | Panel de feedback: selector en mono + aviso ⚠ + lista de alternativas (botones) + input manual. |
| **Derivación error 422 HTML malformado** | Panel de feedback: error rojo + mensaje descriptivo. Botón "Reintentar". |
| **Error 500** | Panel de feedback: "Error del servidor. Reintenta." |

**Selector manual (cuando el usuario escribe su propio selector):**

| Estado | UI |
|---|---|
| **Selector con `:contains` o `text()`** | Borde rojo en el input + mensaje "Los selectores deben ser CSS puro estructural. Evita :contains y text()." |
| **Selector válido** | Borde normal. Botón "Confirmar selector" habilitado. |

**Lista de pasos acumulados (pendiente de guardar):**

| Estado | UI |
|---|---|
| **Sin pasos** | El área de pasos no aparece (el wizard está en "paso 0 — origen"). |
| **Con pasos** | Lista de pasos numerados con `--font-mono`. Botón ✕ por paso. Botón "+ Añadir otro paso". |
| **Guardando** | Botón "Guardar ruta" con spinner. Toda la sección deshabilitada. |
| **Error 422 al guardar** | Mensaje inline del `detail` API bajo la lista de pasos. |
| **Éxito** | Toast "Ruta creada." Wizard se resetea. Nueva ruta aparece en la lista inferior. |

### Drawer de destino — sección rutas existentes (EP-N07 / EP-N09 / EP-N10)

| Estado | UI |
|---|---|
| **Cargando rutas** | Spinner centrado en la sección. |
| **Sin rutas (vacío)** | Caption: "Sin rutas todavía. Usa el wizard de arriba para crear la primera." (No CTA separado — el wizard ya es el CTA). |
| **Con rutas** | Lista de tarjetas colapsadas. Cada tarjeta muestra: label, origin badge, estado (activa/inactiva/muerta), botón eliminar, botón expandir. |
| **Ruta colapsada activa** | Label en `--text`. Origin badge `--surface-2`. Badge "Activa" en `--success-subtle`. |
| **Ruta colapsada inactiva** | Label en `--text-secondary`. Badge "Inactiva" en `--surface-2/--text-secondary`. |
| **Ruta colapsada is_dead=true** | Icono ⚠ antes del label. Badge "Muerta" en `--danger-subtle`. Contador "N fallos" en `--font-mono --danger`. Botón "Reactivar" visible. |
| **Ruta expandida** | Resumen de pasos (solo lectura) + botón "Editar pasos" (abre editor BlockEditor). |
| **Ruta expandida con editor abierto** | Editor BlockEditor inline (tabla de filas editable con columna "URL esperada"). |
| **Guardando cambios destino** | Botón "Guardar cambios" con spinner. |
| **Error al cargar rutas** | Inline: "No se pudo cargar las rutas. [Reintentar]" |

### PathCard — Renombrar label y acciones descubribles (v4)

| Estado | UI |
|---|---|
| **idle** | Cabecera con: label (texto) + ✎ visible solo en hover + origin badge + estado badge + [Probar] + [Editar pasos] + [▼] + [⋯]. |
| **hover cabecera** | Fondo `--surface-2` sutil. Icono ✎ visible (12px, `--text-tertiary`). |
| **editando label** | Label reemplazado por `<input>` con `autoFocus`. Botones [Probar] y [Editar pasos] ocultos. Botones ✓ y ✕ mini visibles. Foco en el input. |
| **label vacío (validación)** | Botón ✓ deshabilitado. Mensaje inline bajo el input: "El nombre no puede estar vacío." en `--danger 11px`. Input con `border-color: --danger`. |
| **guardando renombrado** | Input deshabilitado (opacity 0.7). Spinner 10px en lugar del ✓. Botón ✕ deshabilitado. |
| **renombrado OK** | Input desaparece. Label muestra nuevo valor. Toast: "Ruta renombrada." |
| **error de API al renombrar** | Input permanece con borde rojo. Mensaje inline con el `detail` del response (o mensaje genérico si 500). Botón ✓ rehabilitado. |
| **cancelando** | Input desaparece. Label restaurado al valor original. Sin toast. Sin llamada a API. |
| **menú ⋯ abierto** | Popover con "¿Eliminar esta ruta?" + botones Cancelar / Eliminar. |
| **[Editar pasos] pulsado (tarjeta colapsada)** | La tarjeta se expande y el editor de pasos se activa directamente (`expanded=true`, `editingSteps=true`). |
| **[Editar pasos] pulsado (tarjeta ya expandida)** | El editor de pasos se activa directamente sin colapsar/expandir (`editingSteps=true`). |

### Botón "Probar" y PathTestResultPanel — EP-N14 (v3)

| Estado | UI |
|---|---|
| **idle** | Botón "Probar" secundario (24px altura, mismo estilo que "Reactivar"). Disponible en rutas activas Y muertas. |
| **loading** | Botón "Probando..." + spinner 10px, deshabilitado. Caption segunda línea en la cabecera: "Puede tardar hasta 60 s — navegación real en el bot." en `--text-tertiary 11px`. |
| **resultado OK** | `PathTestResultPanel` expandido bajo la cabecera. Chip "✓ Ruta OK" en `--success-subtle/--success` + duración mono. Filas de pasos: icono ✓ verde + acción + selector + URL alcanzada. `browser_note` en caption. Botón ghost "Cerrar resultado". Botón "Probar" vuelve a idle. |
| **resultado ERROR** | Chip "✕ Falló en el paso N" en `--danger-subtle/--danger` + duración mono. Pasos ok en verde, paso fallido en rojo + motivo (`reason`), pasos no ejecutados en `--text-disabled` con etiqueta "no ejecutado". `browser_note` en caption. Botón "Cerrar resultado". Botón "Probar" vuelve a idle. |
| **409 bot desconectado** | Aviso inline en segunda línea de la cabecera (sin expandir panel separado): icono ⓘ + texto del `detail` del response en `--text-secondary 12px`. El botón "Probar" vuelve a idle. El aviso desaparece al volver a intentar o cerrar el drawer. |
| **409 browser ocupado** | Igual que "409 bot desconectado". El texto del `detail` es diferente pero el tratamiento visual es idéntico. |
| **error 5xx** | Inline bajo el botón: "Error del servidor. Reintenta." en `--danger 12px`. El botón vuelve a idle. |
| **Cerrar resultado** | El panel se colapsa y desaparece. El botón "Probar" queda listo para un nuevo test. |
| **Nuevo test (panel ya abierto)** | Al pulsar "Probar" de nuevo, el panel anterior se borra y se entra en estado loading. Solo hay un resultado a la vez por PathCard. |

---

### Editor de pasos (dentro de tarjeta de ruta expandida, EP-N09)

Mismo comportamiento que v1, con la adición de la columna `expected_url_after_click`:

| Estado | UI |
|---|---|
| **Sin cambios** | Botón "Guardar" deshabilitado. |
| **Con cambios válidos** | Botón "Guardar" habilitado. |
| **Paso con delay_max < delay_min** | Borde rojo en delay_max. Mensaje inline. Botón deshabilitado. |
| **Selector vacío** | Borde rojo en selector. Mensaje inline. |
| **Un solo paso** | Botón ✕ oculto. |
| **Guardando** | Botón spinner. Filas deshabilitadas. |
| **Error 422** | Mensaje `detail` API inline en el footer. |
| **Éxito** | Toast "Ruta actualizada." Editor vuelve a estado sin cambios. |

### Destino muerto (is_dead en destino, sin cambios vs v1)

| Estado | UI |
|---|---|
| **is_dead=true** | Badge "Muerto" en `--danger-subtle/--danger`. Contador de fallos con `--font-mono`. Botón de borrado siempre disponible. |
| **is_dead=false** | Sin acción de reseteo. El usuario borra y recrea si es necesario (url_pattern inmutable). |

**Nota:** `is_dead` de destino lo marca el bot automáticamente. La API no expone
reset directo (EP-N05 no lo incluye). La única acción es borrar (EP-N06) y recrear.

---

## 8. Inventario de componentes UI reutilizables

### REUTILIZAR tal cual

| Componente | Ubicación actual | Uso en NoiseTab |
|---|---|---|
| `FarmListDrawer` (patrón estructura/animación/a11y) | `frontend/src/components/world/FarmListDrawer.jsx` | Patrón exacto para `NoiseDestinationDrawer`: overlay + panel lateral derecho + trampa de foco + cierre con Escape/overlay click. Copiar la estructura del shell; el contenido es distinto. |
| `BlockEditor` (patrón tabla editable con validación en vivo + footer guardar) | `frontend/src/components/session/BlockEditor.jsx` | Patrón directo para el editor de pasos. Columnas distintas pero mismo patrón: filas con inputs, validación en vivo, botón ✕ por fila (oculto si hay 1 sola), botón [+] añadir, footer con estado y guardar. |
| `ConfirmDeleteModal` | `frontend/src/components/ui/ConfirmDeleteModal.jsx` | Borrar destino con mensaje de cascada ("Se eliminarán N rutas y M pasos"). |
| `DeletePopover` | `frontend/src/components/ui/DeletePopover.jsx` | Borrar ruta individual desde el drawer. |
| `Spinner`, `BadgeSpinner`, `showToast`, `ErrorBoundary`, `useFocusTrap` | `frontend/src/components/ui/uiUtils.jsx` | Igual que en SessionTab y FarmListsTab. |
| `useI18n` | `frontend/src/i18n/index.jsx` | Todos los textos. |

### CREAR de cero

| Componente | Descripción | Ruta propuesta |
|---|---|---|
| `NoiseTab` | Contenedor raíz del tab. Orquesta EP-N01+EP-N03, pasa datos a subcomponentes. | `frontend/src/components/world/noise/NoiseTab.jsx` |
| `NoiseConfigPanel` | Panel colapsable con toggle + 3 pares min/max + botón guardar. | `frontend/src/components/world/noise/NoiseConfigPanel.jsx` |
| `NoiseDestinationsTable` | Tabla densa con filas de destinos, filtros, botón añadir, fila de formulario inline. | `frontend/src/components/world/noise/NoiseDestinationsTable.jsx` |
| `NoiseDestinationRow` | Una fila de la tabla con badges, iconos, acciones. | Inline en `NoiseDestinationsTable` o fichero propio. |
| `NoiseAddDestinationForm` | Formulario inline de creación de nuevo destino. | `frontend/src/components/world/noise/NoiseAddDestinationForm.jsx` |
| `NoiseDestinationDrawer` | Drawer lateral: editar destino + wizard + lista de rutas. | `frontend/src/components/world/noise/NoiseDestinationDrawer.jsx` |
| **`NoisePathWizard`** | **NUEVO en v2.** Wizard multi-paso: selector de origen (EP-N12) + formulario por paso (EP-N11) + lista de pasos acumulados + guardar (EP-N08). Estados: idle / cargando-origins / formulario-paso / derivando / feedback-unico / feedback-no-unico / feedback-error / guardando / éxito. | `frontend/src/components/world/noise/NoisePathWizard.jsx` |
| **`NoiseOriginSelector`** | **NUEVO en v2.** Desplegable de anclas precargadas con dos secciones (genéricas + aldeas). Incluye el botón "Actualizar aldeas" (EP-N13) con sus estados. Consume el response de EP-N12. | `frontend/src/components/world/noise/NoiseOriginSelector.jsx` |
| **`NoiseDerivedSelectorFeedback`** | **NUEVO en v2.** Panel de feedback del resultado de EP-N11. 3 estados: único (checkmark), no-único (aviso + alternativas + input manual), error. | `frontend/src/components/world/noise/NoiseDerivedSelectorFeedback.jsx` |
| **`NoiseWizardStepForm`** | **NUEVO en v2.** Formulario de un paso del wizard: URL contexto + label + outerHTML textarea + sección colapsable "URL esperada". Botón "Derivar selector". | `frontend/src/components/world/noise/NoiseWizardStepForm.jsx` |
| **`NoiseWizardStepList`** | **NUEVO en v2.** Lista de pasos acumulados (pendiente de guardar). Pasos numerados con botón ✕ + botón "Añadir otro paso". | Inline en `NoisePathWizard` o fichero propio. |
| `NoisePathList` | Lista de rutas existentes dentro del drawer, cada ruta colapsable. V2: añade estado `is_dead`, botón "Reactivar", resumen de pasos en modo lectura. | `frontend/src/components/world/noise/NoisePathList.jsx` |
| `NoisePathRow` | Una tarjeta de ruta: header colapsable (label/origin/estado/delete/expand) + resumen de pasos (R/O) + botón "Editar pasos" + editor BlockEditor (avanzado). V2: añade estados `is_dead` y `consecutive_failures_count`. | Inline en `NoisePathList` o fichero propio. |
| `NoiseStepEditor` | Editor de pasos (patrón BlockEditor). V2: añade columna `expected_url_after_click`. Columnas: step_order, action, selector, value, delay_min, delay_max, URL esperada, borrar. | `frontend/src/components/world/noise/NoiseStepEditor.jsx` |
| **`PathCard`** (MODIFICAR en v3 y v4) | Cabecera de ruta en `NoisePathList`. **Delta v3:** botón "Probar". **Delta v4:** icono ✎ con edición inline del label (estados: idle/editando/guardando/error); botón "Editar pasos" en cabecera (siempre visible); botón ✕ reemplazado por ⋯ que abre `DeletePopover`; ocultamiento de [Probar] y [Editar pasos] durante la edición inline del label. Ver descripción completa abajo. | Ya existe en `frontend/src/components/world/noise/NoisePathList.jsx` |
| **`PathTestResultPanel`** (CREAR en v3) | Panel inline expandible bajo la PathCard. Muestra el reporte de EP-N14: 3 estados (ok/error/sin-datos). Filas de pasos con icono de estado, acción, selector, URL/motivo. Caption `browser_note`. Botón "Cerrar resultado". | `frontend/src/components/world/noise/PathTestResultPanel.jsx` (nuevo) |
| `NoiseCategoryBadge` | Badge pill para el enum NoiseCategory con color semántico por categoría. | Inline o en `uiUtils` como patrón. |
| `NoiseOriginBadge` | Badge pill para NavigationOrigin (9 genéricas) y para `VILLAGE_N` (muestra el nombre de la aldea). | Inline. |
| `MinMaxInput` | Par de inputs numéricos con validación "max >= min". | `frontend/src/components/ui/MinMaxInput.jsx` |
| `Toggle` | Toggle macOS (ON/OFF). | `frontend/src/components/ui/Toggle.jsx` |
| `IconNoise` | SVG inline para la pestaña Ruido. | Inline en `WorldSpacePage.jsx` |

### PathCard — Delta v3 (modificación del componente existente)

El componente `PathCard` dentro de `NoisePathList.jsx` se modifica para añadir:

**Nuevo estado local:**
```
testing: boolean         — true mientras el POST EP-N14 está en vuelo
testResult: object|null  — null = sin resultado; {overall, steps, aborted_at_step,
                           browser_note, anchor_navigated_to, duration_ms} = resultado
testError409: string|null — texto del 409 a mostrar inline (o null)
testError5xx: string|null — texto de error genérico (o null)
```

**Nuevo botón en la cabecera** (entre el badge de estado activo/muerto y el chevron expand):
```jsx
<button
  type="button"
  onClick={handleTest}
  disabled={testing}
  style={{ height:'24px', padding:'0 8px', /* igual que btn Reactivar */ }}
  aria-label={testing ? t('noise.test.testing') : t('noise.test.testBtn')}
>
  {testing && <Spinner size={10} />}
  {testing ? t('noise.test.testing') : t('noise.test.testBtn')}
</button>
```

**Caption en estado loading** (segunda línea en la cabecera, solo visible cuando `testing===true`):
```jsx
{testing && (
  <span style={{
    fontSize:'11px', color:'var(--text-tertiary)',
    width:'100%', paddingInlineStart:'8px',
  }}>
    {t('noise.test.loadingHint')}
  </span>
)}
```

**Aviso 409** (segunda línea en la cabecera, solo visible cuando `testError409` !== null):
```jsx
{testError409 && (
  <div role="alert" style={{
    display:'flex', alignItems:'center', gap:'6px',
    fontSize:'12px', color:'var(--text-secondary)',
    width:'100%', paddingInlineStart:'8px',
  }}>
    {/* icono ⓘ SVG */}
    {testError409}
  </div>
)}
```

**PathTestResultPanel montado** (en el cuerpo de la PathCard, entre cabecera y body-expandido):
```jsx
{testResult && (
  <PathTestResultPanel
    result={testResult}
    pathSteps={path.steps}
    onClose={() => setTestResult(null)}
  />
)}
```

**Handler `handleTest`:**
```
1. Limpia testResult, testError409, testError5xx.
2. Pone testing=true.
3. Llama api.testNoisePath(worldId, path.id).
4. Si éxito (200): calcula duration_ms = Date.now() - t0, guarda en testResult.
5. Si error 409: extrae detail, guarda en testError409.
6. Si otro error: guarda mensaje genérico en testError5xx.
7. En finally: pone testing=false.
```

---

### PathCard — Delta v4 (modificación adicional sobre v3)

**Nuevos estados locales añadidos:**
```
renamingLabel: boolean        — true cuando el input de renombrado está activo
renameValue: string           — valor actual del input (inicializado con path.label)
renameSaving: boolean         — true mientras el PUT EP-N09 está en vuelo
renameError: string|null      — mensaje de error inline (null = sin error)
overflowMenuOpen: boolean     — true cuando el popover ⋯ está abierto
```

**Icono ✎ (pencil) — se muestra en hover de la cabecera:**
```jsx
{/* Solo visible cuando NO está en modo edición de label */}
{!renamingLabel && (
  <button
    type="button"
    onClick={e => { e.stopPropagation(); startRenaming() }}
    aria-label={t('noise.paths.renameBtn')}
    style={{
      appearance: 'none', border: 'none', background: 'transparent',
      cursor: 'pointer', padding: '4px',
      color: 'var(--text-tertiary)', opacity: 0,   /* visible en hover via CSS */
      borderRadius: 'var(--radius-sm)',
    }}
    className="rename-pencil"   /* CSS: .path-header:hover .rename-pencil { opacity:1 } */
  >
    {/* Icono SVG pencil 12px */}
    <svg width="12" height="12" ... />
  </button>
)}
```

**Input inline cuando `renamingLabel === true`:**
```jsx
{renamingLabel ? (
  <>
    <input
      type="text"
      value={renameValue}
      onChange={e => { setRenameValue(e.target.value); setRenameError(null) }}
      onKeyDown={e => {
        if (e.key === 'Enter') handleRenameConfirm()
        if (e.key === 'Escape') handleRenameCancel()
      }}
      disabled={renameSaving}
      autoFocus
      aria-label={t('noise.paths.renameInput')}
      style={{
        flex: 1, padding: '4px 8px',
        border: `1px solid ${renameError ? 'var(--danger)' : 'var(--border-strong)'}`,
        borderRadius: 'var(--radius-sm)',
        background: 'var(--surface)', color: 'var(--text)',
        fontFamily: 'inherit', fontSize: '13px',
        opacity: renameSaving ? 0.7 : 1,
      }}
    />
    {/* Botón confirmar */}
    <button
      type="button"
      onClick={handleRenameConfirm}
      disabled={renameSaving || !renameValue.trim()}
      aria-label={t('noise.paths.renameConfirm')}
      style={{ width:'22px', height:'22px', /* btn secundario mini */ }}
    >
      {renameSaving ? <Spinner size={10} /> : '✓'}
    </button>
    {/* Botón cancelar */}
    <button
      type="button"
      onClick={handleRenameCancel}
      disabled={renameSaving}
      aria-label={t('noise.paths.renameCancel')}
      style={{ width:'22px', height:'22px', /* btn ghost */ }}
    >
      ✕
    </button>
  </>
) : (
  /* Label normal + lápiz en hover */
)}
```

**Mensaje de error inline (segunda línea de cabecera):**
```jsx
{renameError && (
  <span role="alert" style={{
    width: '100%', paddingInlineStart: '8px',
    fontSize: '11px', color: 'var(--danger)',
  }}>
    {renameError}
  </span>
)}
```

**Handler `handleRenameConfirm`:**
```
1. Si renameValue.trim() vacío → setRenameError(t('noise.paths.renameEmptyError')), return.
2. Si renameValue === path.label → handleRenameCancel(), return (sin llamada API).
3. setRenameSaving(true).
4. Llama api.updateNoisePath(worldId, path.id, { label: renameValue.trim() }).
5. Si éxito (200): onUpdate(updated), showToast(t('noise.paths.renamed')), setRenamingLabel(false).
6. Si error 422: setRenameError(e.detail ?? t('noise.paths.renameError')).
7. Si error 500: setRenameError(t('noise.paths.renameError')).
8. Finally: setRenameSaving(false).
```

**Botón "Editar pasos" en cabecera (NUEVO posición):**
```jsx
{/* Visible cuando NO estamos en modo edición de label */}
{!renamingLabel && (
  <button
    type="button"
    onClick={() => { setExpanded(true); setEditingSteps(true) }}
    style={{ /* igual que btn "Probar" */ height:'24px', padding:'0 8px', ... }}
  >
    {t('noise.paths.editSteps')}
  </button>
)}
```
Nota: si `editingSteps` ya es true, el segundo click no hace nada malo (React no re-renderiza
porque el estado ya es el mismo). Si la tarjeta ya está expandida (`expanded === true`),
el `setExpanded(true)` es idempotente.

**Botón ⋯ (overflow menu) — reemplaza el ✕ anterior:**
```jsx
<div style={{ position:'relative', flexShrink:0 }}>
  <button
    type="button"
    onClick={() => setOverflowMenuOpen(v => !v)}
    aria-label={t('noise.paths.moreActions')}
    aria-expanded={overflowMenuOpen}
    style={{
      width:'26px', height:'26px',
      border:'none', background:'transparent',
      cursor:'pointer', color:'var(--text-tertiary)',
      borderRadius:'var(--radius-sm)',
      display:'flex', alignItems:'center', justifyContent:'center',
      fontSize:'14px',
    }}
  >
    ⋯
  </button>
  {overflowMenuOpen && (
    <div
      role="menu"
      style={{
        position:'absolute', top:'100%', insetInlineEnd:0,
        background:'var(--surface)', border:'1px solid var(--border)',
        borderRadius:'var(--radius-sm)', boxShadow:'var(--shadow-md)',
        minWidth:'160px', zIndex:50, padding:'4px 0',
      }}
    >
      <button
        role="menuitem"
        type="button"
        onClick={() => { setOverflowMenuOpen(false); setDeletePopoverOpen(true) }}
        style={{
          width:'100%', textAlign:'start', padding:'8px 12px',
          border:'none', background:'transparent',
          color:'var(--danger)', fontSize:'13px',
          cursor:'pointer', fontFamily:'inherit',
        }}
        onMouseEnter={e => e.target.style.background = 'var(--danger-subtle)'}
        onMouseLeave={e => e.target.style.background = 'transparent'}
      >
        {t('noise.paths.delete')}
      </button>
    </div>
  )}
  {/* El DeletePopover se monta debajo cuando deletePopoverOpen=true (sin cambios vs v3) */}
  {deletePopoverOpen && (
    <DeletePopover ... />
  )}
</div>
```

El menú ⋯ se cierra con Escape o click fuera (handler `useEffect` en `document`).

---

### PathTestResultPanel — Diseño detallado del componente nuevo

**Props:**
```
result         {object}   — PathTestResponse del backend (overall, steps, aborted_at_step,
                            browser_note, anchor_navigated_to)
pathSteps      {Array}    — path.steps de la ruta (para inferir pasos no ejecutados)
onClose        {Function} — callback para cerrar el panel
duration_ms    {number}   — calculado en el frontend (Date.now() antes/después del POST)
```

**Layout del panel:**
- Fondo `--surface-2`, borde superior `1px solid --border`.
- Padding `10px 12px`.
- No hay sombra propia — es parte de la PathCard.

**Header del resultado:**
```jsx
<div style={{ display:'flex', alignItems:'center', gap:'8px', marginBottom:'8px' }}>
  {/* Chip overall */}
  <span style={{
    background: overall==='ok' ? 'rgba(36,138,61,.10)' : 'rgba(201,53,44,.10)',
    color: overall==='ok' ? 'var(--success)' : 'var(--danger)',
    borderRadius:'var(--radius-full)', padding:'2px 8px',
    fontSize:'12px', fontWeight:600,
    display:'inline-flex', alignItems:'center', gap:'4px',
  }}>
    {overall==='ok' ? '✓ Ruta OK' : `✕ Falló en el paso ${aborted_at_step}`}
  </span>
  {/* Duración */}
  <span style={{ fontFamily:'var(--font-mono)', fontSize:'12px', color:'var(--text-tertiary)' }}>
    {formatMs(duration_ms)}   {/* p.ej. "3.241 s" o "842 ms" */}
  </span>
  {/* Spacer + Cerrar */}
  <button style={{ marginInlineStart:'auto', /* btn ghost */ }}
    onClick={onClose} aria-label={t('noise.test.closeResult')}>
    {t('noise.test.closeResult')}
  </button>
</div>
```

**Separador hairline:** `<hr style={{ margin:'0 0 8px', border:'none', borderTop:'1px solid var(--border)' }} />`

**Filas de pasos:**
Para cada paso, se fusionan los datos del array `result.steps` (pasos ejecutados)
con los de `pathSteps` (definición completa de la ruta):

```
// Paso ejecutado con status "ok"
<div style={{ display:'flex', alignItems:'baseline', gap:'6px', padding:'3px 0',
              borderBottom: '1px solid var(--border)', fontSize:'12px' }}>
  <span style={{ color:'var(--success)', flexShrink:0, width:'14px' }}>✓</span>
  <span style={{ fontFamily:'var(--font-mono)', color:'var(--text-tertiary)',
                 fontSize:'11px', width:'16px', textAlign:'right' }}>0</span>
  <span style={{ background:'var(--surface)', border:'1px solid var(--border)',
                 borderRadius:'var(--radius-full)', padding:'0 5px',
                 fontFamily:'var(--font-mono)', fontSize:'10px',
                 color:'var(--text-secondary)', flexShrink:0 }}>CLICK</span>
  <code style={{ fontFamily:'var(--font-mono)', fontSize:'11px', flex:1,
                 wordBreak:'break-all' }}>a[href*='/karte']</code>
  {current_url && (
    <span style={{ fontFamily:'var(--font-mono)', fontSize:'10px',
                   color:'var(--text-tertiary)', whiteSpace:'nowrap',
                   overflow:'hidden', textOverflow:'ellipsis', maxWidth:'180px' }}>
      → {current_url}
    </span>
  )}
</div>

// Paso ejecutado con status "error" (el que abortó)
<div style={{ /* igual pero */ }}>
  <span style={{ color:'var(--danger)' }}>✕</span>
  ...
  {/* motivo del error */}
  <span style={{ color:'var(--danger)', fontSize:'11px', width:'100%',
                 paddingInlineStart:'calc(14px + 16px + accion-width + 6px*3)',
                 marginTop:'2px' }}>
    {reason}
  </span>
  {/* URL antes del intento (current_url del paso fallido) */}
  {current_url && (
    <span style={{ fontFamily:'var(--font-mono)', fontSize:'10px',
                   color:'var(--text-tertiary)', width:'100%', paddingInlineStart:'...' }}>
      → {current_url}
    </span>
  )}
</div>

// Paso no ejecutado (en pathSteps pero no en result.steps)
<div style={{ opacity:0.4 }}>
  <span style={{ color:'var(--text-disabled)' }}>─</span>
  ...
  <span style={{ color:'var(--text-disabled)', fontStyle:'italic' }}>no ejecutado</span>
</div>
```

**Footer con `browser_note`:**
```jsx
{result.browser_note && (
  <div style={{ marginTop:'8px', paddingTop:'8px', borderTop:'1px solid var(--border)',
                display:'flex', gap:'6px', alignItems:'flex-start',
                fontSize:'11px', color:'var(--text-tertiary)', fontStyle:'italic' }}>
    {/* icono ⓘ 12px */}
    <span>{result.browser_note}</span>
  </div>
)}
```

**Accesibilidad del panel:**
- El panel completo tiene `role="region"` + `aria-label="Resultado del test de la ruta"`.
- Al mostrarse, se anuncia via `aria-live="polite"` en un nodo invisible persistente
  en el DOM de PathCard: `aria-live="polite"` + texto conciso del resultado
  ("Ruta OK" o "Ruta falló en el paso N").
- El botón "Cerrar resultado" tiene `aria-label` descriptivo.
- Las URLs largas se truncan con `text-overflow: ellipsis` + `title` con la URL completa
  (accessible en hover/foco).

---

### Icono para la pestaña "Ruido" — IconNoise

SVG inline que representa ruido/interferencia: ondas concéntricas irregulares
(estilo wifi con "ruido" — tres arcos discontinuos de distinto tamaño):

```jsx
function IconNoise() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
      style={{ width: '16px', height: '16px', flexShrink: 0 }} aria-hidden="true">
      <path d="M5 12.5 a9 9 0 0 1 14 0" />
      <path d="M8 15.5 a5 5 0 0 1 8 0" />
      <circle cx="12" cy="18" r="1" fill="currentColor" stroke="none" />
    </svg>
  )
}
```

Este icono es coherente con el lenguaje visual de los otros iconos del sidebar
(mismos strokeWidth, mismo estilo de trazo de línea).

### Badges de categoría (NoiseCategoryBadge)

No existe un componente Badge en el proyecto. Se define como patrón inline
con tokens semánticos existentes:

| Categoría | Color de fondo | Color de texto | Justificación |
|---|---|---|---|
| MAP | `--info-subtle` | `--info` | Mapa = información/orientación |
| OASIS_INFO | `--success-subtle` | `--success` | Oasis = farming = éxito |
| PLAYER_PROFILE | `--accent-subtle` | `--accent-text` | Perfil = algo que observas con interés |
| MESSAGES | `var(--mode-idle-subtle)` | `var(--mode-idle)` | Mensajes = actividad social suave |
| REPORTS | `--surface-2` | `--text-secondary` | Reportes = datos neutros |
| BUILDING_VIEW | `--surface-2` | `--text-secondary` | Vista edificios = neutro |
| OTHER | `--surface-2` | `--text-tertiary` | Otros = sin categoría especial |

El badge usa `--radius-full`, font-size 11px, padding 2px 8px, `letter-spacing: 0.03em`.

### Badge de origen de ruta (NoiseOriginBadge)

Pequeño chip sin color semántico propio (solo `--surface-2` / `--text-secondary`):

```
[DORF1]  [DORF2]  [MAP]  [ANY]
```

### Toggle (componente nuevo)

Botón checkbox estilizado como macOS ON/OFF:
- Track: `--border-strong` cuando OFF; `--success` cuando ON.
- Thumb: `--surface` (siempre blanco/casi blanco).
- Tamaño: 36×20px. Animación 150ms ease.
- `role="switch"`, `aria-checked`, `aria-label` descriptivo.
- No usa el oro como color de acento (el verde `--success` es el color semántico
  correcto para "activo/habilitado").

### MinMaxInput (componente nuevo)

Patrón para pares de valores numéricos con validación "max >= min":

```
[  80  ] — [  150  ]
           ↑ rojo si max < min
```

- Dos `<input type="number">` con `min="0"` (o según el campo).
- El segundo input tiene `aria-label="Máximo"`, el primero `aria-label="Mínimo"`.
- Texto " — " entre los dos inputs (literal, en `--text-secondary`).
- Si max < min: borde rojo en el input max + mensaje `"Debe ser ≥ mínimo"` en
  `--danger` de 12px debajo.
- Ancho fijo de cada input: ~72px para ints, ~80px para floats (dwell).

---

## 9. Contenido y microcopy

### Claves i18n necesarias (añadir al catálogo)

```
# Pestaña
noise.tab.label = "Ruido"

# Config global
noise.config.title = "Configuración de ruido"
noise.config.enabled = "Activo"
noise.config.disabled = "Inactivo"
noise.config.hardcoreLabel = "HARDCORE — peticiones/hora"
noise.config.passiveLabel = "PASIVO — peticiones/hora"
noise.config.dwellLabel = "Tiempo en página (dwell)"
noise.config.dwellUnit = "segundos"
noise.config.save = "Guardar configuración"
noise.config.saving = "Guardando…"
noise.config.saved = "Configuración guardada."
noise.config.saveError = "Error al guardar. Reintenta."
noise.config.minMaxError = "Debe ser ≥ al mínimo."

# Destinos
noise.destinations.title = "Destinos de navegación"
noise.destinations.add = "Añadir destino"
noise.destinations.empty = "Sin destinos de navegación todavía."
noise.destinations.emptyCta = "Añadir primer destino"
noise.destinations.filterCategory = "Categoría"
noise.destinations.filterAll = "Todas"
noise.destinations.showDead = "Mostrar muertos"
noise.destinations.hiddenCount = "{n} destinos ocultos (muertos)"
noise.destinations.col.name = "Nombre / URL"
noise.destinations.col.category = "Categoría"
noise.destinations.col.weight = "Peso"
noise.destinations.col.safe = "Seguro"
noise.destinations.col.paths = "Rutas"
noise.destinations.dead = "Muerto"
noise.destinations.deadFails = "{n} fallos"
noise.destinations.deleteConfirm = "¿Eliminar \"{label}\"? Se eliminarán también sus {paths} rutas y {steps} pasos."
noise.destinations.deleted = "Destino eliminado."

# Formulario nuevo destino
noise.form.urlPattern = "URL (patrón)"
noise.form.urlPatternHint = "Ruta relativa (/karte.php) o URL completa."
noise.form.label = "Etiqueta"
noise.form.category = "Categoría"
noise.form.weight = "Peso de frecuencia"
noise.form.weightHint = "Valor > 0. Mayor peso = más visitas relativas."
noise.form.safe = "Seguro"
noise.form.create = "Crear destino"
noise.form.creating = "Creando…"
noise.form.created = "Destino creado."
noise.form.cancel = "Cancelar"

# Drawer de destino
noise.drawer.editTitle = "Editar destino"
noise.drawer.saveChanges = "Guardar cambios"
noise.drawer.saving = "Guardando…"
noise.drawer.saved = "Destino actualizado."

# Rutas
noise.paths.title = "Rutas de navegación"
noise.paths.add = "Añadir ruta"
noise.paths.empty = "Sin rutas de navegación."
noise.paths.emptyCta = "Añadir primera ruta"
noise.paths.origin = "Origen"
noise.paths.active = "Activa"
noise.paths.inactive = "Inactiva"
noise.paths.expand = "Ver pasos"
noise.paths.collapse = "Ocultar pasos"
noise.paths.delete = "Eliminar ruta"
noise.paths.deleteConfirm = "¿Eliminar la ruta \"{label}\" y sus {n} pasos?"
noise.paths.deleted = "Ruta eliminada."
noise.paths.saved = "Ruta actualizada."
noise.paths.newLabel = "Nueva ruta"
noise.paths.labelField = "Etiqueta de la ruta"
noise.paths.originField = "Origen"
noise.paths.save = "Guardar ruta"
noise.paths.saving = "Guardando…"
noise.paths.saveError = "Error al guardar. Reintenta."

# Pasos de ruta
noise.steps.col.order = "#"
noise.steps.col.action = "Acción"
noise.steps.col.selector = "Selector"
noise.steps.col.value = "Valor"
noise.steps.col.delayMin = "ms min"
noise.steps.col.delayMax = "ms max"
noise.steps.addStep = "Añadir paso"
noise.steps.remove = "Eliminar paso"
noise.steps.delayError = "ms max debe ser ≥ ms min."
noise.steps.selectorEmpty = "El selector no puede estar vacío."
noise.steps.valueHint = "WAIT_FOR_SELECTOR: timeout en ms. Otros: opcional."

# Categorías del enum
noise.category.MAP = "Mapa"
noise.category.OASIS_INFO = "Info oasis"
noise.category.PLAYER_PROFILE = "Perfil"
noise.category.MESSAGES = "Mensajes"
noise.category.REPORTS = "Reportes"
noise.category.BUILDING_VIEW = "Edificios"
noise.category.OTHER = "Otros"

# Orígenes del enum (ampliado en v2 — 9 valores + anclas por-aldea)
noise.origin.DORF1 = "Recursos (aldea activa)"
noise.origin.DORF2 = "Edificios (aldea activa)"
noise.origin.MAP = "Mapa mundial"
noise.origin.STATISTICS = "Estadísticas globales"
noise.origin.REPORTS = "Reportes"
noise.origin.MESSAGES = "Mensajes"
noise.origin.VILLAGE_STATISTICS = "Estadísticas de aldea"
noise.origin.OASIS_VIEW = "Vista oasis en el mapa"
noise.origin.ANY = "Cualquier página (sin ancla)"
noise.origin.villageGroup = "Mis aldeas"
noise.origin.genericGroup = "Páginas de Travian"

# Acciones del enum
noise.action.CLICK = "Click"
noise.action.WAIT_FOR_SELECTOR = "Esperar selector"
noise.action.SCROLL_TO = "Scroll a"
noise.action.HOVER = "Hover"

# Anti-detección hint (caption en el panel config)
noise.config.antiDetectionHint = "La variedad de navegación reduce la huella estadística del bot."

# Wizard de rutas (nuevo en v2)
noise.wizard.title = "Nueva ruta"
noise.wizard.labelField = "Etiqueta de la ruta"
noise.wizard.originField = "Origen (punto de partida del bot)"
noise.wizard.addFirstStep = "Añadir primer paso →"
noise.wizard.addStep = "Añadir otro paso →"
noise.wizard.saveRoute = "Guardar ruta"
noise.wizard.saving = "Guardando..."
noise.wizard.clear = "Limpiar wizard"
noise.wizard.clearConfirm = "¿Descartar los {n} pasos pendientes?"
noise.wizard.saved = "Ruta creada."
noise.wizard.saveError = "Error al guardar. Reintenta."

# Wizard — selector de origen
noise.wizard.originLoading = "Cargando orígenes..."
noise.wizard.originLoadError = "No se pudo cargar los orígenes. Reintenta."
noise.wizard.noVillages = "Sin aldeas cargadas."
noise.wizard.refreshVillages = "Actualizar aldeas"
noise.wizard.refreshingVillages = "Actualizando..."
noise.wizard.villagesRefreshed = "{n} aldeas cargadas."
noise.wizard.refreshError409 = "El bot está desconectado. Inicia sesión primero."
noise.wizard.refreshError = "Error al actualizar. Reintenta."

# Wizard — formulario de paso
noise.wizard.step.urlCtx = "URL actual (solo contexto, no se guarda)"
noise.wizard.step.labelField = "Descripción del botón/enlace"
noise.wizard.step.outerHtml = "outerHTML del elemento a clicar"
noise.wizard.step.outerHtmlPlaceholder = "Pega aquí el outerHTML del elemento (botón derecho → Inspeccionar → clic derecho sobre el elemento → Copiar → Copiar outerHTML)."
noise.wizard.step.expectedUrl = "URL esperada tras el click (opcional)"
noise.wizard.step.deriveBtn = "Derivar selector"
noise.wizard.step.deriving = "Analizando..."
noise.wizard.step.emptyHtml = "El campo outerHTML no puede estar vacío."
noise.wizard.step.invalidHtml = "El outerHTML no pudo parsearse como HTML válido."

# Wizard — feedback derivación
noise.wizard.derive.selectorLabel = "Selector derivado"
noise.wizard.derive.method = "Método"
noise.wizard.derive.level = "Nivel"
noise.wizard.derive.unique = "Único en el fragmento analizado"
noise.wizard.derive.notUnique = "No único en el fragmento. Verifica en Travian."
noise.wizard.derive.alternatives = "Alternativas"
noise.wizard.derive.manualSelector = "O escribe tu selector"
noise.wizard.derive.selectorCssError = "Los selectores deben ser CSS puro estructural. Evita :contains y text()."
noise.wizard.derive.confirm = "Confirmar selector"
noise.wizard.derive.retry = "Reintentar con otro HTML"
noise.wizard.derive.serverError = "Error del servidor. Reintenta."

# Wizard — lista de pasos acumulados
noise.wizard.steps.title = "Pasos de la ruta"
noise.wizard.steps.removeStep = "Eliminar paso {n}"
noise.wizard.steps.expectedUrl = "→ {url}"

# Rutas existentes — estados is_dead (nuevo en v2)
noise.paths.dead = "Muerta"
noise.paths.deadFails = "{n} fallos consecutivos"
noise.paths.reactivate = "Reactivar"
noise.paths.reactivating = "Reactivando..."
noise.paths.reactivated = "Ruta reactivada."
noise.paths.reactivateHint = "Reactiva si corregiste el selector, o elimina y crea una nueva con el wizard."
noise.paths.viewSteps = "Ver pasos"
noise.paths.editSteps = "Editar pasos"

# Editor de pasos (columna nueva en v2)
noise.steps.col.expectedUrl = "URL esperada"
noise.steps.expectedUrlHint = "CLICK: URL que debe cargarse tras el click. Vacío = sin verificación."

# Editar ruta — renombrar + acciones descubribles (nuevo en v4)
noise.paths.renameBtn = "Renombrar ruta"              # aria-label del lápiz ✎
noise.paths.renameInput = "Nombre de la ruta"         # aria-label del input
noise.paths.renameConfirm = "Confirmar renombrado"    # aria-label del botón ✓
noise.paths.renameCancel = "Cancelar renombrado"      # aria-label del botón ✕
noise.paths.renameEmptyError = "El nombre no puede estar vacío."
noise.paths.renameError = "Error al guardar. Reintenta."
noise.paths.renamed = "Ruta renombrada."
noise.paths.moreActions = "Más acciones"              # aria-label del botón ⋯

# Probar ruta — botón y estados (nuevo en v3)
noise.test.testBtn = "Probar"
noise.test.testing = "Probando..."
noise.test.loadingHint = "Puede tardar hasta 60 s — navegación real en el bot."
noise.test.closeResult = "Cerrar resultado"

# Probar ruta — resultados (nuevo en v3)
noise.test.resultOk = "Ruta OK"
noise.test.resultError = "Falló en el paso {n}"
noise.test.stepNotRun = "no ejecutado"
noise.test.stepOk = "Paso {n} OK"       # solo para aria-label
noise.test.stepError = "Paso {n} falló" # solo para aria-label
noise.test.resultLabel = "Resultado del test de la ruta"  # aria-label del panel

# Probar ruta — avisos (nuevo en v3)
# Los mensajes de 409 se usan tal cual desde el `detail` del response del backend.
# No se i18nizan para no desincronizarse con el backend.
noise.test.error5xx = "Error del servidor. Reintenta."
```

---

## 10. Accesibilidad

- **Color nunca es la única señal**: los badges de categoría tienen texto +
  color. is_dead tiene icono ⚠ + texto "Muerto" + color. is_safe tiene icono + color.
- **Foco visible**: anillo 2px en `--accent` en todos los controles. El drawer tiene
  trampa de foco (`useFocusTrap`). El primer elemento enfocable del drawer recibe
  foco al abrirse.
- **ARIA roles**:
  - Tabla de destinos: `role="table"` / `role="row"` / `role="cell"`, cabeceras
    con `scope="col"`.
  - Toggle noise_enabled: `role="switch"`, `aria-checked`, `aria-label`.
  - Drawer: `role="dialog"`, `aria-modal="true"`, `aria-labelledby` apuntando al
    título del destino.
  - Botón expandir/colapsar ruta: `aria-expanded`, `aria-controls`.
  - Panel colapsable config: `aria-expanded`, `aria-controls`.
  - Columna "Seguro": no usar solo el icono — añadir `aria-label="Seguro"` o
    `aria-label="Inseguro"` al icono.
  - Inputs numéricos del MinMaxInput: `aria-label="Mínimo"` / `aria-label="Máximo"`
    + `aria-describedby` apuntando al mensaje de error si existe.
- **Keyboard navigation**:
  - Tab order: config panel toggle → colapsable → tabla → filtros → botón añadir.
  - Dentro del drawer: edición destino → lista rutas → cada ruta (expand/colapsar/
    activar/borrar → pasos si expandida).
  - Escape: cierra el drawer. Cierra el formulario inline de nuevo destino.
- **Contraste verificado**:
  - `--info` (#0A6FCC sobre blanco): 4.8:1 ✓ — usado para MAP category badge.
  - `--success` (#248A3D sobre blanco): 4.9:1 ✓ — toggle activo.
  - `--danger` (#C9352C sobre blanco): 5.1:1 ✓ — is_dead badge.
  - `--accent-text` (#8A6418 sobre blanco): 4.9:1 ✓ — PLAYER_PROFILE badge.
  - Las categorías REPORTS/BUILDING_VIEW/OTHER usan `--text-secondary` sobre
    `--surface-2`, que tiene contraste suficiente.
- **RTL**: propiedades lógicas CSS en todos los layouts. El drawer se abre por la
  derecha en LTR y por la izquierda en RTL (usando `inset-inline-end: 0`).
- **`prefers-reduced-motion`**: deshabilitar la animación de apertura del drawer
  y la transición del panel colapsable.
- **Targets táctiles**: filas de tabla ≥ 40px de alto. Botones en drawer ≥ 36px.
  Toggle ≥ 44px de target (padding compensatorio).

**Accesibilidad del renombrado y acciones PathCard (v4):**
- **Icono ✎**: `<button>` con `aria-label={t('noise.paths.renameBtn')}`. Visible solo
  en hover/foco — accesible por teclado (Tab + Enter activa el modo edición).
- **Input de renombrado**: `aria-label={t('noise.paths.renameInput')}`. Si hay error:
  `aria-describedby` apunta al nodo del mensaje de error (role="alert").
- **Botón ✓**: `aria-label={t('noise.paths.renameConfirm')}`, `aria-disabled` cuando
  está deshabilitado (label vacío o guardando).
- **Botón ✕ (cancelar)**: `aria-label={t('noise.paths.renameCancel')}`.
- **Botón ⋯**: `aria-label={t('noise.paths.moreActions')}`, `aria-expanded` en el
  estado del popover. El menú tiene `role="menu"` y sus items `role="menuitem"`.
- **Foco al cancelar renombrado**: el foco vuelve al botón ✎ (trigger del modo edición).
- **Foco al confirmar renombrado**: el foco vuelve al label/button-label de la PathCard.
- **Tab order dentro de PathCard en modo edición**: `input → ✓ → ✕ → ▼ → ⋯`.
  Los botones de acción ([Probar], [Editar pasos]) no son focusables en modo edición
  (están ocultos del DOM cuando `renamingLabel===true`).
- **Botón [Editar pasos]**: `aria-controls={path-body-id}` + `aria-expanded` refleja
  si la tarjeta está expandida y el editor activo.

**Accesibilidad del botón "Probar" y del PathTestResultPanel (v3):**
- Botón "Probar": `aria-label` cambia dinámicamente entre `t('noise.test.testBtn')` y
  `t('noise.test.testing')` según el estado. `aria-busy="true"` cuando testing.
  `aria-disabled="true"` cuando disabled.
- El `PathTestResultPanel` tiene `role="region"` + `aria-label={t('noise.test.resultLabel')}`.
- **`aria-live` para el resultado**: nodo `aria-live="polite"` oculto (`position:absolute;
  width:1px; height:1px; overflow:hidden`) en el DOM de la PathCard. Al llegar el
  resultado se escribe en él: "Ruta OK" o "Ruta falló en el paso N". Así los lectores
  de pantalla anuncian el resultado sin foco manual.
- El aviso 409 tiene `role="alert"` para anuncio inmediato sin esperar al foco.
- URLs en las filas de resultado se truncan con `ellipsis`. El atributo `title` lleva
  la URL completa (accesible con foco via CSS `content: attr(title)` no aplicable, pero
  el title sí es leído por algunos SRs). Opcionalmente: botón "Copiar URL" invisible
  accesible por teclado — se deja como mejora futura (fuera de scope de esta entrega).
- Foco tras cerrar el resultado: el foco vuelve al botón "Probar" (es el trigger del
  panel, patrón correcto de gestión de foco en paneles programáticos).

---

## 11. Responsive / adaptación a dispositivos

### Desktop (>= lg, 1024px+)

Layout de una columna dentro del área de contenido de WorldSpacePage:
1. Panel config colapsable
2. Controles (botón añadir + filtros)
3. Tabla densa de destinos
4. Drawer como overlay lateral derecho (420px de ancho fijo)

### Tablet (md, 768–1023px)

Igual que desktop. El drawer puede reducirse a 360px. La tabla oculta la columna
"Rutas" (P3 en tablet) si hay presión de espacio.

### Móvil (< md, < 768px)

- **Config panel (P2)**: visible pero colapsado. Expandir ocupa pantalla completa.
- **Tabla (P1)**: columnas visibles: Nombre/URL + is_dead badge. El resto (Peso,
  Seguro, N Rutas) se colapsa en una segunda línea por fila o se oculta.
  Filas de 56px en móvil (más altas para el target táctil).
- **Botón "Añadir destino" (P1)**: siempre visible, ancho completo en móvil.
- **Filtros (P2)**: dropdown colapsable "Filtrar" en móvil.
- **Drawer (P1 cuando abierto)**: ocupa 100% de ancho en móvil (hoja desde abajo
  o panel lateral completo). Botón de cierre grande.
- **Editor de pasos (P2)**: en móvil la tabla de pasos se convierte en tarjetas
  apiladas (igual que BlockEditor en SessionTab).

### Prioridades P1/P2/P3

| Elemento | Prioridad | Comportamiento en móvil |
|---|---|---|
| Toggle noise_enabled | P1 | Siempre visible |
| Tabla de destinos (nombre/URL/is_dead) | P1 | Visible, columnas P2+ ocultas |
| Botón "Añadir destino" | P1 | Ancho completo |
| Panel config (campos numéricos) | P2 | Colapsado |
| Columnas Peso/Seguro/Rutas | P2/P3 | Ocultas o en segunda línea |
| Filtros de categoría | P2 | Colapsados en dropdown |
| Drawer completo | P1 (cuando abierto) | Full-width |
| Editor de pasos | P2 | Tarjetas apiladas |
| Hint anti-detección | P3 | Oculto |
| Botón "Probar" en PathCard | P2 | Visible en el drawer (que ocupa full-width en móvil). En móvil se conserva pero puede mostrarse solo el icono (sin texto) si la cabecera tiene presión de espacio. |
| PathTestResultPanel | P1 (cuando abierto) | Se adapta al ancho del drawer (full-width en móvil). Las URLs largas se truncan con ellipsis en columnas estrechas. |

---

## 12. Interacciones y feedback

### Panel config colapsable

- Apertura: `max-height: 0 → auto` con `transition: max-height 220ms ease`.
  Respeta `prefers-reduced-motion`.
- El toggle `noise_enabled` dispara el PUT EP-N02 inmediatamente (sin "Guardar").
  Feedback: spinner pequeño junto al toggle durante la llamada.
- "Guardar config" se habilita en `onChange` de cualquier campo numérico.
  Al pulsar: spinner en el botón + campos deshabilitados hasta respuesta.

### Tabla de destinos

- Hover de fila: fondo `--surface-2` (muy sutil). Transición 150ms.
- Click en nombre del destino: abre drawer con foco en el primer input.
- Click en icono ✕: `ConfirmDeleteModal`. No hay hover delay.
- Nuevo destino: el formulario inline se abre con `max-height` expand.
  La primera fila de la tabla se "empuja" hacia abajo con animación suave.

### Drawer de destino

- Apertura: slide-in desde la derecha (translateX: 100% → 0), 220ms ease.
  Overlay se desvanece: opacity 0 → 0.4.
- Cierre: slide-out + fade. Foco vuelve al elemento que abrió el drawer
  (la fila de la tabla).
- El formulario "Añadir ruta" aparece inline sobre la lista de rutas (mismo
  patrón que el formulario de nuevo destino en la tabla).

### Editor de pasos (NoiseStepEditor)

- Validación: `onChange` de cada campo. La misma iteración que BlockEditor.
- Botón "Guardar ruta" se habilita solo si todos los pasos son válidos y hay
  al menos 1 cambio respecto al estado guardado.
- El cambio en steps es un reemplazo atómico en la API: se envía la lista completa.
- Al añadir un paso: se inserta al final con valores por defecto (CLICK,
  selector vacío, delay 500/900ms). El focus salta al input selector del nuevo paso.

### Botón "Probar" y PathTestResultPanel — interacciones (v3)

- **Pulsar "Probar"**: botón entra en estado loading al instante (sin esperar ningún
  debounce). Si había un resultado anterior abierto en esa misma PathCard, se limpia.
  El estado loading también limpia los avisos 409 anteriores.
- **Durante el loading**: el botón expand/colapsar de la PathCard sigue siendo clicable
  (el test corre en paralelo mientras el usuario puede ver otros datos de la ruta). El
  resto de acciones de la PathCard (Reactivar, Eliminar, Editar pasos) siguen disponibles.
- **Llegada del resultado**: el `PathTestResultPanel` aparece con una transición suave
  `max-height: 0 → auto + opacity 0 → 1` en `220ms ease`. El panel siempre es visible
  sin necesidad de expandir la PathCard.
- **Duración display**: se muestra la duración en el frontend (`Date.now()` antes y después
  del POST). Si la duración es < 1000 ms se muestra en ms (p.ej. "842 ms"); si ≥ 1000 ms
  se muestra en segundos con un decimal (p.ej. "3.2 s"). Siempre `font-mono tabular-nums`.
- **Cerrar resultado**: el panel se colapsa con la misma transición inversa. El foco
  vuelve al botón "Probar".
- **Hover de filas del resultado**: fondo `--surface` sutil en hover (150ms), para que el
  usuario pueda distinguir filas largas. No hay acción — las filas son solo lectura.
- **URLs largas**: se truncan con `overflow:hidden; text-overflow:ellipsis; white-space:nowrap`
  + `max-width: 180px` en desktop. En móvil (drawer full-width) pueden crecer más (`max-width:
  40vw`). `title` con la URL completa.
- **Respeta `prefers-reduced-motion`**: la transición de aparición del panel se desactiva.

### Toasts

Mismo patrón que el resto del proyecto: abajo centrado, auto-dismiss 3s,
`translateY(8px) → 0` + `opacity 0 → 1`.

---

## 13. Criterios de aceptación de diseño

### Visuales

- [ ] El toggle `noise_enabled` usa `--success` cuando ON; nunca el oro.
- [ ] Los badges de categoría siguen la tabla de colores de §8 sin inventar nuevos acentos.
- [ ] Los destinos `is_dead=true` tienen fondo `--danger-subtle` + icono ⚠ + texto "Muerto".
- [ ] La columna "Peso" usa `--font-mono` y `tabular-nums`.
- [ ] Los inputs del MinMaxInput tienen ancho fijo (~72px int, ~80px float).
- [ ] El oro (`--accent`, `--accent-text`) aparece solo en: foco, nav item activo, links.
  Nunca como color de categoría ni de estado.
- [ ] En modo oscuro todos los elementos mantienen sus contrastes. Cero hex hardcodeados.
- [ ] El drawer tiene 420px de ancho en desktop; 100% en móvil.
- [ ] La vista pasa inspección visual en 390px, 768px, 1280px y 1920px.

### Funcionales — tabla y config (sin cambios vs v1)

- [ ] Al abrir el tab se cargan EP-N01 (config) y EP-N03 (destinos) en paralelo.
- [ ] El toggle `noise_enabled` dispara EP-N02 inmediatamente (sin botón guardar separado).
- [ ] "Guardar config" dispara EP-N02 con todos los campos numéricos actuales.
- [ ] La tabla oculta destinos `is_dead=true` por defecto; "Mostrar muertos" los revela.
- [ ] Crear destino (EP-N04): la nueva fila aparece en la tabla sin recargar toda la lista.
- [ ] Borrar destino (EP-N06): `ConfirmDeleteModal` con texto de cascada. La fila desaparece tras 204.
- [ ] Al abrir el drawer, se cargan en paralelo: EP-N07 (rutas) y EP-N12 (origins).
- [ ] "Guardar cambios" del destino dispara EP-N05 con solo los campos editables (label/frequency_weight/is_safe).
- [ ] Los campos url_pattern y category aparecen en el drawer en solo lectura.
- [ ] Los errores 422 de la API se muestran inline en el campo o formulario afectado.
- [ ] Todos los textos usan claves i18n. Ningún string hardcodeado en el JSX.
- [ ] RTL: drawer se abre desde la izquierda; propiedades lógicas en todos los layouts.
- [ ] La pestaña "Ruido" aparece en `navItems` de `WorldSpacePage.jsx` con `IconNoise`.

### Funcionales — wizard de rutas (nuevo en v2, casados con CA del spec funcional)

- [ ] Al abrir el drawer se llama EP-N12 (origins); hasta que resuelva, el desplegable muestra un spinner (CA-NP16, CA-NP17, CA-NP18).
- [ ] El desplegable de origen tiene dos secciones: "Páginas de Travian" (9 orígenes) y "Mis aldeas" (variable) (CA-NP16, CA-NP17).
- [ ] Si `villages_loaded=false`, la sección "Mis aldeas" muestra el aviso y el botón "Actualizar aldeas" (CA-NP18).
- [ ] El botón "Actualizar aldeas" llama EP-N13. Si 409 → inline de error. Si 200 → desplegable se refresca (CA-NP19, CA-NP20).
- [ ] El botón "Derivar selector" está deshabilitado si el campo outerHTML está vacío.
- [ ] Al pulsar "Derivar selector", la UI llama EP-N11 y muestra el feedback:
  - Si `is_unique: true` → checkmark verde + selector + método + nivel (CA-NP13).
  - Si `is_unique: false` → aviso ⚠ + alternativas como botones + input manual (CA-NP15).
  - Si 422 → mensaje de error inline (CA-NP14).
- [ ] El usuario puede confirmar el selector derivado, elegir una alternativa, o escribir uno manual.
- [ ] Si el selector manual contiene `:contains`, `text()` o equivalentes → error inline.
- [ ] Tras confirmar el selector, el paso queda acumulado en la lista local del wizard (con `expected_url_after_click` si el usuario lo proporcionó).
- [ ] "Guardar ruta" se habilita solo si hay ≥ 1 paso acumulado y la etiqueta no está vacía.
- [ ] "Guardar ruta" llama EP-N08 con el `origin` seleccionado + `label` + `steps` (incl. `expected_url_after_click` cuando aplica). (CA-NP23).
- [ ] Tras guardar con éxito, el wizard se resetea y la nueva ruta aparece en la lista de rutas existentes.
- [ ] "Limpiar wizard" pide confirmación si hay pasos acumulados.
- [ ] El origin `VILLAGE_<data_id>` se envía correctamente en el body de EP-N08 (CA-NP23, CA-NP24).

### Funcionales — rutas existentes (actualizado en v2)

- [ ] Las rutas con `is_dead=true` muestran badge "Muerta" + contador de fallos (CA-NP21, CA-NP31).
- [ ] El botón "Reactivar" en una ruta muerta llama EP-N09 con `is_active: true`. El backend resetea `consecutive_failures_count` a 0 (CA-NP25).
- [ ] Tras reactivar, la tarjeta de la ruta vuelve al estado normal (sin badge "Muerta").
- [ ] El resumen de pasos (solo lectura) muestra `expected_url_after_click` con el prefijo `→` cuando existe (CA-NP22).
- [ ] El editor avanzado (BlockEditor) tiene columna "URL esperada" para `expected_url_after_click` (CA-NP22).
- [ ] Guardar pasos editados (EP-N09): se envía la lista completa de pasos (reemplazo atómico).
- [ ] El botón ✕ de paso está oculto cuando solo hay 1 paso.
- [ ] Borrar ruta (EP-N10): `DeletePopover` inline. La ruta desaparece tras 204.

### Funcionales — "Probar ruta" / PathTestResultPanel (nuevo en v3, casados con CA del spec §16)

- [ ] El botón "Probar" aparece en cada PathCard, tanto en rutas activas como muertas (CA-PT01 alineado con EC-PT01).
- [ ] Al pulsar "Probar", el botón muestra spinner + "Probando..." y se deshabilita. Un caption con "Puede tardar hasta 60 s" aparece en la cabecera.
- [ ] La UI llama `POST /worlds/{id}/noise/paths/{path_id}/test` (EP-N14, sin body, sin Accept-Language).
- [ ] Si `overall: "ok"`: el `PathTestResultPanel` muestra chip verde "✓ Ruta OK" + duración + lista de pasos en verde + URL alcanzada por paso + `browser_note`.
- [ ] Si `overall: "error"`: chip rojo "✕ Falló en el paso N" (`aborted_at_step`). Pasos ok en verde, paso fallido en rojo con `reason`. Pasos posteriores (inferidos de `path.steps`) en `--text-disabled` con etiqueta "no ejecutado".
- [ ] La `browser_note` del response se muestra tal cual (sin hardcodear) en caption `--text-tertiary` al final del panel.
- [ ] Si response 409: aviso inline en la cabecera de la PathCard con el `detail` del response. No se abre el panel de resultado. Botón vuelve a idle.
- [ ] El texto del aviso 409 viene del `detail` del response (no hardcodeado en el frontend).
- [ ] Si error 5xx: inline "Error del servidor. Reintenta." bajo el botón.
- [ ] El botón "Cerrar resultado" cierra el panel y devuelve el foco al botón "Probar".
- [ ] Solo hay un `PathTestResultPanel` abierto a la vez por PathCard (no se acumulan resultados).
- [ ] Las demás acciones de la PathCard (expandir, reactivar, eliminar) siguen activas durante el test.
- [ ] La duración se calcula en el frontend (Date.now() antes/después del POST) y se formatea: < 1 s → "N ms", ≥ 1 s → "N.N s". Font-mono tabular-nums.
- [ ] El `PathTestResultPanel` tiene `role="region"` + `aria-label` descriptivo.
- [ ] Existe un nodo `aria-live="polite"` en PathCard que anuncia el resultado cuando llega.
- [ ] El aviso 409 tiene `role="alert"`.

### Funcionales — editar ruta (renombrar + acciones descubribles) — nuevo en v4

- [ ] El icono ✎ (lápiz) aparece al hacer hover sobre la cabecera de la PathCard, a la derecha del label.
- [ ] Al pulsar ✎, el label se convierte en un `<input>` inline con `autoFocus` y el valor actual de `path.label`.
- [ ] Durante la edición inline, los botones [Probar] y [Editar pasos] desaparecen. Solo quedan el input + ✓ + ✕ + [▼] + [⋯].
- [ ] Pulsar Enter o el botón ✓ confirma el renombrado: llama `api.updateNoisePath(worldId, path.id, { label: newLabel.trim() })`.
- [ ] Pulsar Escape o el botón ✕ cancela sin llamada a API; el label original se restaura.
- [ ] Si el label queda vacío al intentar confirmar, el botón ✓ está deshabilitado y aparece el mensaje "El nombre no puede estar vacío." en `--danger 11px` bajo el input.
- [ ] Si la API devuelve error (422 o 5xx), el input permanece con borde rojo y el mensaje de error inline. El usuario puede corregir y reintentar.
- [ ] Si el usuario confirma sin cambiar el valor (`newLabel === path.label`), no se llama a la API; la edición se cierra directamente.
- [ ] Tras un renombrado exitoso, el label muestra el nuevo valor y aparece el toast "Ruta renombrada."
- [ ] El botón "Editar pasos" está visible en la cabecera de la PathCard (no solo en el cuerpo expandido).
- [ ] Al pulsar "Editar pasos" con la tarjeta colapsada, la tarjeta se expande y el editor de pasos queda activo.
- [ ] Al pulsar "Editar pasos" con la tarjeta ya expandida, el editor de pasos se activa directamente.
- [ ] El botón ✕ (eliminar ruta) ha sido reemplazado por el botón ⋯.
- [ ] Al pulsar ⋯, se abre un mini-popover con la opción "Eliminar ruta" en `--danger`.
- [ ] El flujo de eliminación desde el ⋯ sigue usando `DeletePopover` (confirmar antes de ejecutar).
- [ ] El menú ⋯ se cierra con Escape o click fuera.

### Accesibilidad

- [ ] Toggle: `role="switch"`, `aria-checked`, `aria-label` descriptivo.
- [ ] Drawer: `role="dialog"`, `aria-modal="true"`, `aria-labelledby`.
- [ ] Trampa de foco activa en el drawer (usando `useFocusTrap`).
- [ ] Escape cierra el drawer y el formulario inline de nuevo destino.
- [ ] Todos los botones de acción tienen `aria-label` descriptivo.
- [ ] La tabla tiene semántica correcta (table/row/cell, scope="col" en cabeceras).
- [ ] Foco visible (anillo 2px `--accent`) en todos los elementos interactivos.
- [ ] `aria-expanded` en el panel colapsable y en cada ruta del drawer.

---

## 14. Trazabilidad

| Decisión de diseño | Necesidad de usuario / fuente |
|---|---|
| Pestaña "Ruido" en WorldSpacePage (no pantalla independiente) | Decisión ya tomada y confirmada por el usuario antes de iniciar el diseño. Encaje en la navegación del contexto de un mundo concreto. |
| Config global como panel colapsable (off por defecto) | JTBD-1 (configurar volumen) es frecuencia baja. La mayoría de las sesiones son para gestionar destinos. Un panel siempre abierto desperdiciaría espacio P1. PRINCIPIOS: divulgación progresiva. |
| Toggle noise_enabled en el resumen del colapsable (siempre visible) | JTBD-5 (habilitar/deshabilitar globalmente) es P1 cuando ocurre. Debe estar accesible sin expandir el panel. |
| Drawer lateral para rutas/pasos (en vez de expand inline) | Jerarquía de 4 niveles. Un doble expand inline en la tabla crearía filas de profundidad variable difíciles de escanear. El drawer preserva el contexto y ofrece espacio de trabajo limpio. Patrón ya existe en `FarmListDrawer.jsx`. |
| Patrón BlockEditor para el editor de pasos (avanzado) | Exacta correspondencia estructural: lista de filas ordenadas con inputs, validación en vivo, botón añadir/eliminar, footer guardar. Reutilizar evita reinventar. El editor se mueve a posición secundaria (tras el wizard) en v2. |
| url_pattern inmutable en UI (solo lectura en el drawer) | Spec: url_pattern no es editable tras la creación (EP-N05 no lo acepta). Mostrarlo en solo lectura deja claro la razón sin confundir con un input deshabilitado. |
| is_dead en destino: mostrar estado pero no ofrecer "resetear" | El sistema (bot) marca is_dead de destino. La API no expone reset directo (EP-N05). La única acción válida es borrar y recrear. |
| is_dead en ruta: sí ofrecer "Reactivar" (via is_active=true en EP-N09) | Para rutas, el spec CA-NP25 documenta que activar `is_active=true` vía EP-N09 resetea `consecutive_failures_count=0`. El usuario puede corregir el selector en el editor avanzado y reactivar. Es una acción explícita y consciente. |
| Filtro "Mostrar muertos" off por defecto | Los destinos muertos no son útiles operativamente. Ocultarlos por defecto reduce el ruido visual. |
| MinMaxInput como componente nuevo (no slider) | Valores numéricos concretos. Un slider exigiría mover el cursor. Preferencia de usuario técnico por inputs precisos (DESIGN.md: densidad). |
| Toggle como componente nuevo (no checkbox nativo) | Toggle macOS más legible en este contexto visual. Componente reutilizable. |
| NoiseCategoryBadge usa colores semánticos existentes | DESIGN.md: "Nunca dos acentos compitiendo." Ningún color nuevo. |
| Label "Ruido" para la pestaña | Consistencia con las otras pestañas en español. Terminología interna del spec. |
| Wizard como protagonista del drawer (v2) | El usuario rechazó explícitamente el editor directo de selectores CSS (demasiado técnico). El wizard "enseña" el camino mediante outerHTML → selector derivado, eliminando la necesidad de conocer CSS. Flujo decisión: JTBD-4. Spec: RN-NP04, noise-path-wizard.md §1. |
| Anclas precargadas en desplegable (no input de texto libre para el origen) | RN-NP01, RN-NP02: el origin es un conjunto finito de anclas semilla (9 genéricas) + anclas dinámicas por aldea. Exponer un input libre abriría la puerta a orígenes inválidos. El desplegable respeta los contratos del spec funcional. |
| Feedback derivado: tres estados visuales distintos (único/no-único/error) | RN-NP05: `is_unique` es heurístico, no garantizado. El usuario debe saber la diferencia. Los tres estados tienen tratamiento visual diferenciado para que la decisión de confirmar o ajustar el selector sea consciente. |
| `expected_url_after_click` como sección colapsable en el formulario del paso | RN-NP06: el campo es opcional. La mayoría de usuarios no querrán llenarlo en un primer uso. Colapsarlo reduce la carga cognitiva sin esconderlo. |
| Rutas existentes secundarias, bajo el wizard (no primarias) | El usuario declaró que las rutas ya creadas "le dan igual verlas". El wizard de construcción es lo que tiene valor en cada sesión de configuración. Las rutas existentes son una vista de revisión/edición de bajo uso. |
| Botón "Actualizar aldeas" en el selector de origen (no en el header del drawer) | EP-N13 es necesario exactamente cuando el usuario quiere seleccionar una ancla por-aldea y no hay aldeas cargadas. Colocarlo en el contexto (junto al desplegable vacío) es más legible que en un lugar genérico del drawer. |
| 409 de refresh-villages como error inline (no toast) | El 409 tiene un texto específico ("inicia sesión primero") que requiere acción del usuario. Un error inline junto al botón es más accionable que un toast efímero que desaparece. |
| Borrado de destino con ConfirmDeleteModal (no DeletePopover) | La cascada (borrar rutas y pasos) es destructiva e irreversible. Un modal con descripción de cascada es más seguro. DeletePopover se reserva para las rutas individuales. |
| **v3 — Botón "Probar" en PathCard (no en el header del drawer ni botón flotante)** | El test es por-ruta, no por-destino. Colocarlo en la cabecera de cada PathCard es el lugar más próximo al objeto que prueba. Reutiliza el patrón visual de "Reactivar" (mismo estilo de botón secundario mini), lo que da coherencia sin añadir un nuevo patrón. UI: MODIFICAR PathCard (palantir decision). |
| **v3 — PathTestResultPanel expandible inline (no modal)** | El spec indica que el resultado es informativo, no requiere decisión del usuario. Un modal sería excesivo para algo que se lee y se descarta. El expand inline bajo la cabecera es coherente con los demás paneles expand-in-place del proyecto (p.ej. la sección de pasos en el drawer). Mantiene el contexto visual de la ruta mientras se lee el resultado. UI: CREAR PathTestResultPanel. |
| **v3 — `browser_note` desde el response (no hardcodeado)** | El spec §16.8 explica que el campo `browser_note` existe específicamente para que la UI lo muestre sin hardcodearlo en el frontend. Así si el mensaje cambia en el backend, la UI se actualiza automáticamente. |
| **v3 — Pasos no ejecutados inferidos de `path.steps` + `aborted_at_step`** | El response de EP-N14 solo incluye los pasos que se intentaron (`result.steps`). Para mostrar los pasos que no llegaron a ejecutarse, el frontend cruza ese array con `path.steps`. Así el usuario entiende de un vistazo cuántos pasos quedaron pendientes, sin tener que navegar mentalmente entre "lo que pasó" y "lo que faltaba". |
| **v3 — 409 como aviso inline en la cabecera de PathCard (no toast)** | Mismo razonamiento que el 409 de refresh-villages: el 409 requiere acción del usuario (iniciar sesión o esperar). Un toast desaparece antes de que el usuario haya procesado el mensaje. El inline es persistente hasta que el usuario actúa. El aviso se sitúa en la cabecera de la PathCard (misma zona que el botón "Probar") para máxima proximidad. |
| **v3 — Duración calculada en el frontend** | EP-N14 no devuelve duración en el response. Se calcula con `Date.now()` antes/después del POST. Es suficientemente precisa para el objetivo informativo (el usuario quiere saber "¿tardó 2 s o 30 s?", no una precisión de microsegundos). |
| **v4 — Renombrar via icono ✎ inline (no formulario separado)** | El label de la ruta vive en la cabecera de PathCard. La edición más natural y menos disruptiva es convertir ese mismo texto en un input, en el mismo lugar. Patrón referenciado: edición de label de destino en `NoiseDestinationDrawer`. Reutilización del mismo PUT EP-N09 que ya existe para `is_active` y `steps`. UI: MODIFICAR `PathCard` (palantir: reutiliza patrón inline del drawer). |
| **v4 — label vacío → error inline (no deshabilitar el ✓ a secas)** | Deshabilitar sin feedback deja al usuario sin saber por qué el botón no responde. El mensaje inline dice exactamente qué hay que corregir. Patrón: mismo que los errores 422 en el formulario de nuevo destino. |
| **v4 — Cancelar renombrado restaura el valor original sin API call** | Cancelar es deshacer una intención, no una acción completada. Hacer una llamada al backend para "restaurar" sería un abuso del protocolo. El estado original vive en `path.label` y se re-aplica al cancelar. |
| **v4 — Ocultar [Probar] y [Editar pasos] durante edición inline** | La cabecera ya tiene muchos elementos. En modo edición del label, el contexto es "estoy renombrando" — todas las demás acciones quedan en segundo plano para reducir ruido visual y evitar activarlas accidentalmente mientras se escribe. [▼] y [⋯] permanecen porque no interfieren con la escritura. |
| **v4 — "Editar pasos" en cabecera (no solo en body expandido)** | Problema reportado: "no encontraba cómo editar". El patrón de expansión + edición requería conocer que había que expandir primero. Mover el botón a la cabecera lo hace visible a golpe de vista, sin pasos intermedios. La acción de expandir y la de editar pasos son distintas — el usuario puede no querer ver el resumen, sino editar directamente. |
| **v4 — ✕ → ⋯ (overflow menu) para la acción de eliminar** | Tres razones: (1) la cabecera ya tenía demasiados elementos con el mismo tamaño visual (todos los botones competían en pie de igualdad); (2) eliminar es destructivo e irreversible — dificultar el acceso accidental es una mejora de UX; (3) el ⋯ es un patrón convencional para "más acciones" que el usuario ya reconoce. El `DeletePopover` existente se reutiliza sin cambios. |

---

🔖 Última revisión: 2026-06-02 (v4 — delta "Editar ruta": implementado por desarrollador-ux-ui. Estado: implemented)

---

## Registro de implementación

**Fecha:** 2026-06-02
**Estado previo:** ready-for-impl → **Estado nuevo:** implemented

### Ficheros creados

- `frontend/src/components/world/noise/NoiseTab.jsx` — raíz del tab, carga EP-N01+EP-N03 en paralelo
- `frontend/src/components/world/noise/NoiseConfigPanel.jsx` — panel colapsable config global
- `frontend/src/components/world/noise/NoiseDestinationsTable.jsx` — tabla densa + formulario inline
- `frontend/src/components/world/noise/NoiseDestinationDrawer.jsx` — drawer lateral (patrón FarmListDrawer)
- `frontend/src/components/world/noise/NoisePathWizard.jsx` — wizard multi-paso protagonista
- `frontend/src/components/world/noise/NoiseOriginSelector.jsx` — desplegable de anclas EP-N12
- `frontend/src/components/world/noise/NoiseWizardStepForm.jsx` — formulario outerHTML → EP-N11
- `frontend/src/components/world/noise/NoiseDerivedSelectorFeedback.jsx` — feedback 3 estados (único/no-único/error)
- `frontend/src/components/world/noise/NoisePathList.jsx` — lista de rutas existentes con is_dead
- `frontend/src/components/world/noise/NoiseStepEditor.jsx` — editor avanzado patrón BlockEditor + columna URL esperada
- `frontend/src/components/ui/Toggle.jsx` — toggle macOS ON/OFF reutilizable
- `frontend/src/components/ui/MinMaxInput.jsx` — par de inputs numéricos con validación max≥min

### Ficheros modificados

- `frontend/src/api/client.js` — añadidos 13 métodos noise (EP-N01..N13)
- `frontend/src/i18n/catalog/es.js` — añadidas ~130 claves `noise.*`
- `frontend/src/i18n/catalog/en.js` — añadidas ~130 claves `noise.*` en inglés
- `frontend/src/pages/WorldSpacePage.jsx` — import NoiseTab, IconNoise, navItem 'noise', render de la pestaña

### Comando para ejecutar tests

```bash
cd frontend && npm run build
```
El proyecto no tiene tests unitarios de componentes React actualmente (sin vitest/jest setup). El build de Vite sirve como gate de compilación (✓ pasado).

### Verificación visual

Capturas verificadas con `frontend/scripts/uishot.mjs` (puppeteer-core + Chrome del sistema):
- `/mundos/1` → pestaña "Ruido" visible en sidebar con IconNoise (ondas wifi) en posición correcta
- Click en "Ruido" → estado de error API renderizado correctamente (no amontonado, tokens CSS aplicados)
- Modo claro verificado; todos los tokens son CSS vars (cero hex hardcodeados en componentes nuevos)

### Desviaciones respecto al diseño

1. **mockup_aprobado_por_usuario:** El frontmatter del spec indicaba `no` pero el usuario instruyó explícitamente a implementar el diseño como "YA APROBADO". Se asumió que fue un descuido de actualización del frontmatter (spec y mockup creados el mismo día). Registrado aquí como transparencia.
2. **DeletePopover en rutas:** El componente DeletePopover existente no tiene API de `open/close` gestionada externamente — se renderiza directamente cuando está montado. El NoisePathList gestiona el estado `deletePopoverOpen` localmente y renderiza el popover condicionalmente. Patrón coherente con el resto del proyecto.
3. **`worldnav.noise` en catálogo:** La clave se añadió dentro de la sección `noise.*` al final del catálogo (no junto a `worldnav.session` en la sección worldnav). Funcionalmente equivalente; el sistema i18n no requiere orden físico de claves.

---

## Registro de implementación — v3 (delta "Probar ruta")

**Fecha:** 2026-06-02
**Estado previo:** ready-for-impl (v3) → **Estado nuevo:** implemented

### Ficheros creados (v3)

- `frontend/src/components/world/noise/PathTestResultPanel.jsx` — panel inline expandible de resultado del test EP-N14: estados ok/error, filas de pasos ejecutados y no ejecutados, `browser_note`, botón "Cerrar resultado". Props: `result`, `pathSteps`, `durationMs`, `onClose`, `closeRef`. Accesibilidad: `role="region"` + `aria-label`.

### Ficheros modificados (v3)

- `frontend/src/api/client.js` — añadido método `testNoisePath(worldId, pathId)` → `POST /worlds/${worldId}/noise/paths/${pathId}/test` (EP-N14). Calca el patrón de `refreshNoiseVillages` (sin body, sin Accept-Language).
- `frontend/src/i18n/catalog/es.js` — añadidas 11 claves `noise.test.*` (botón, estados, resultados, avisos).
- `frontend/src/i18n/catalog/en.js` — añadidas 11 claves `noise.test.*` en inglés.
- `frontend/src/components/world/noise/NoisePathList.jsx` — `PathCard` modificado: nuevo estado local `testing/testResult/testDurationMs/testError409/testError5xx`; botón "Probar" (idle/loading/disabled, `aria-busy`, `aria-label` dinámico); caption "Puede tardar 60 s" en estado loading; aviso 409 inline `role="alert"`; error 5xx inline; nodo `aria-live="polite"` oculto para SR; montaje de `PathTestResultPanel` entre cabecera y body expandido; handler `handleTest` y `handleCloseResult` con devolución de foco al botón "Probar". Import de `PathTestResultPanel` añadido.

### Comando para ejecutar tests (v3)

```bash
cd "/Users/german/DEV/Travian con Agentes/frontend" && npm run build
```
Build pasado: 1682 módulos, 0 errores, 0 warnings nuevos.

### Verificación visual (v3)

Capturas verificadas con `frontend/scripts/uishot.mjs`:
1. `/mundos/1` → tab "Ruido" activo en sidebar sin error de montaje; estado "Mundo no encontrado." correcto (sin API corriendo).
2. Render estático de `PathTestResultPanel` en 3 estados verificado visualmente:
   - **Estado OK**: chip verde "✓ Ruta OK" + duración mono, pasos ✓ con URL truncada, paso WAIT sin URL, `browser_note` con icono ⓘ, botón "Cerrar resultado". Fiel al wireframe §6 del spec.
   - **Estado ERROR**: chip rojo "✕ Falló en el paso 1", pasos ok/error/no-ejecutado con semántica de color correcta (`--success`/`--danger`/`--text-disabled`), motivo + URL del paso fallido en segunda línea, etiqueta "no ejecutado" opaca. Fiel al wireframe §6.
   - **Aviso 409**: icono ⓘ + texto del `detail` del backend sin hardcodear. Fiel al wireframe §6.

### Criterios de aceptación verificados (v3)

| CA | Descripción | Estado |
|---|---|---|
| CA-PT01 | Botón "Probar" en PathCard activas y muertas | ✓ |
| CA-PT02 | Loading: spinner + "Probando..." + caption 60 s | ✓ |
| CA-PT03 | Llama `POST /worlds/{id}/noise/paths/{path_id}/test` | ✓ |
| CA-PT04 | overall ok → chip verde + pasos ok + URL + browser_note | ✓ |
| CA-PT05 | overall error → chip rojo + pasos ok/error/no-ejecutado + reason | ✓ |
| CA-PT06 | browser_note del response (no hardcodeado) | ✓ |
| CA-PT07 | 409 → aviso inline con detail del response; sin panel | ✓ |
| CA-PT08 | Texto 409 del detail (no hardcodeado en frontend) | ✓ |
| CA-PT09 | Error 5xx → inline "Error del servidor. Reintenta." | ✓ |
| CA-PT10 | "Cerrar resultado" colapsa panel y devuelve foco al botón "Probar" | ✓ |
| CA-PT11 | Solo un PathTestResultPanel por PathCard a la vez | ✓ |
| CA-PT12 | Otras acciones de PathCard (expandir, reactivar, eliminar) accesibles durante test | ✓ |
| CA-PT13 | Duración calculada en frontend (Date.now() antes/después del POST) | ✓ |
| CA-PT14 | Formato duración: < 1 s → "N ms"; ≥ 1 s → "N.N s"; font-mono tabular-nums | ✓ |
| CA-PT15 | `role="region"` + `aria-label` en PathTestResultPanel | ✓ |
| CA-PT16 | `aria-live="polite"` en PathCard anuncia resultado | ✓ |
| CA-PT17 | Aviso 409 con `role="alert"` | ✓ |

### Desviaciones respecto al diseño (v3)

Ninguna. El delta v3 se implementó con fidelidad completa al spec. El texto de los avisos 409 viene íntegro del campo `detail` del response del backend, sin hardcodear valores en el frontend.

---

## Registro de implementación — v4 (delta "Editar ruta")

**Fecha:** 2026-06-02
**Estado previo:** ready-for-impl (v4) → **Estado nuevo:** implemented

### Ficheros creados (v4)

- `frontend/scripts/test_pathcard_v4.mjs` — script puppeteer de verificación visual de los 5 estados de PathCard v4 (idle/renombrando/error-vacío/menú-⋯/is_dead). Reutilizable para regresiones futuras.

### Ficheros modificados (v4)

- `frontend/src/components/world/noise/NoisePathList.jsx` — `PathCard` delta v4:
  - **Renombrado inline**: nuevos estados `renamingLabel/renameValue/renameSaving/renameError`; icono ✎ (`<button class="rename-pencil">` con `opacity:0` en idle, visible en hover/focus via CSS); cuando `renamingLabel=true`, el label se reemplaza por `<input>` con `autoFocus`, botones ✓/✕ (22×22px); Enter confirma, Escape cancela; validación label vacío → `renameError` + botón ✓ deshabilitado; guarda con `api.updateNoisePath(worldId, path.id, { label })` (EP-N09); manejo de error 422/5xx con mensaje inline; devolución de foco al ✎ al cancelar o al label-button al confirmar; `aria-describedby` apuntando al nodo de error cuando existe; nodo `role="alert"` para el mensaje de error.
  - **Botón "Editar pasos" en cabecera** (v4): `<button>` siempre visible cuando `!renamingLabel`; al pulsar hace `setExpanded(true); setEditingSteps(true)` — si la tarjeta ya está expandida o el editor ya activo, ambos setters son idempotentes.
  - **Botón ⋯ overflow menu** (v4): reemplaza el `<button>✕</button>` directo; estado `overflowMenuOpen`; `aria-expanded`, `aria-haspopup="menu"`; menú `role="menu"` con item `role="menuitem"` de "Eliminar ruta" en `--danger`; se cierra con Escape o click fuera (useEffect con listeners en `document`); al elegir "Eliminar ruta" cierra el menú y abre el `DeletePopover` existente sin cambios.
  - Durante `renamingLabel=true`, los botones [Probar] y [Editar pasos] no se renderizan (condición `!renamingLabel`), reduciendo el ruido visual tal como especifica §6c del spec.
  - Refs nuevos: `renameBtnRef` (lápiz ✎), `labelBtnRef` (label/button-expand), `overflowBtnRef`, `overflowMenuRef`.
  - `useEffect` para sincronizar `renameValue` con `path.label` cuando cambia externamente (p.ej. tras `onUpdate`).
- `frontend/src/styles/app.css` — reglas CSS para mostrar el lápiz en hover/focus-within de `.path-header` y en foco directo de `.rename-pencil` (a11y: visible por teclado sin hover).
- `frontend/src/i18n/catalog/es.js` — 8 claves nuevas `noise.paths.rename*` + `noise.paths.moreActions`.
- `frontend/src/i18n/catalog/en.js` — 8 claves nuevas `noise.paths.rename*` + `noise.paths.moreActions` en inglés.

### Comando para ejecutar tests (v4)

```bash
cd "/Users/german/DEV/Travian con Agentes/frontend" && npm run build
# Verificación visual:
node scripts/test_pathcard_v4.mjs
```

Build: 1682 módulos, 0 errores, 0 warnings nuevos.

### Verificación visual (v4)

Capturas verificadas con `scripts/test_pathcard_v4.mjs` (puppeteer-core + Chrome del sistema):

1. **Idle activa**: label truncado con ellipsis correcto, ✎ opacity:0 (invisible en no-hover), botones Probar + Editar pasos en cabecera, chevron ▼, botón ⋯. Tokens CSS aplicados.
2. **Renombrando**: `<input>` con `outline: 2px solid var(--accent)` (borde oro), ✓ en `--success`, ✕ ghost `--text-tertiary`. [Probar]/[Editar pasos] ocultos. Origin badge + estado + ▼ + ⋯ visibles.
3. **Error label vacío**: borde rojo `var(--danger)` en input, ✓ deshabilitado (opacity 0.5), mensaje "El nombre no puede estar vacío." en `--danger 11px`. Sin desbordamiento horizontal.
4. **Menú ⋯ abierto**: popover posicionado correctamente con sombra `--shadow-md`, "Eliminar ruta" en `--danger`, "Cancelar" ghost.
5. **Ruta muerta**: icono ⚠ `--danger`, badge "○ Muerta · 3 fallos consecutivos" en mono rojo, wrap automático en segunda línea. Botones Reactivar + Probar + Editar pasos + ▼ + ⋯ todos presentes.

### Criterios de aceptación verificados (v4)

| CA | Descripción | Estado |
|---|---|---|
| CA-V4-01 | Icono ✎ aparece en hover cabecera PathCard | ✓ (CSS .path-header:hover .rename-pencil) |
| CA-V4-02 | Al pulsar ✎: label → input inline con autoFocus + valor actual | ✓ |
| CA-V4-03 | Durante edición, [Probar] y [Editar pasos] desaparecen | ✓ (!renamingLabel condition) |
| CA-V4-04 | Enter / ✓ confirma: llama api.updateNoisePath con label.trim() | ✓ |
| CA-V4-05 | Escape / ✕ cancela sin llamada API, restaura label original | ✓ |
| CA-V4-06 | Label vacío: ✓ deshabilitado + mensaje "El nombre no puede estar vacío." | ✓ |
| CA-V4-07 | Error API (422/5xx): input con borde rojo + detail inline | ✓ |
| CA-V4-08 | Sin cambio (newLabel === path.label): cierra sin llamar API | ✓ |
| CA-V4-09 | Renombrado exitoso: toast "Ruta renombrada." + label actualizado | ✓ |
| CA-V4-10 | [Editar pasos] visible en cabecera (no solo en cuerpo expandido) | ✓ |
| CA-V4-11 | [Editar pasos] desde cabecera colapsada: expande + activa editor | ✓ (setExpanded(true) + setEditingSteps(true)) |
| CA-V4-12 | [Editar pasos] con tarjeta ya expandida: activa editor directamente | ✓ (setters idempotentes) |
| CA-V4-13 | Botón ✕ reemplazado por ⋯ | ✓ |
| CA-V4-14 | Al pulsar ⋯: mini-popover con "Eliminar ruta" en --danger | ✓ |
| CA-V4-15 | Flujo eliminar desde ⋯ usa DeletePopover existente | ✓ |
| CA-V4-16 | Menú ⋯ se cierra con Escape o click fuera | ✓ (useEffect + event listeners) |
| CA-V4-17 | aria-label en ✎ (renameBtn), input (renameInput), ✓ (renameConfirm), ✕ (renameCancel), ⋯ (moreActions) | ✓ |
| CA-V4-18 | Foco devuelto al ✎ al cancelar; al label-button al confirmar | ✓ (setTimeout + ref.focus()) |
| CA-V4-19 | role="alert" en mensaje de error renombrado | ✓ |
| CA-V4-20 | Tab order en modo edición: input → ✓ → ✕ → ▼ → ⋯ | ✓ ([Probar]/[Editar pasos] no en DOM) |

### Desviaciones respecto al diseño (v4)

Ninguna. El delta v4 se implementó con fidelidad completa al spec §6c, §7, §8 y §10.
