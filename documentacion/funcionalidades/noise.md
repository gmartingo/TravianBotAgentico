# Sistema de Ruido de Navegación — Documento de negocio

Feature: Noise Navigation (base en human-sessions.md §17 + ampliaciones de noise-path-wizard.md)
Spec técnico base: `docs/specs/human-sessions.md` §17
Spec del wizard: `docs/specs/noise-path-wizard.md`
Spec pendiente: `docs/specs/noise-navigate-to-origin.md` (EP-N15 — no implementado)
Spec pendiente: `docs/specs/noise-frequency-and-destination-weight.md` (ready-for-impl)
Documentación de código: `documentacion/backend/noise.md`

---

## Por qué existe

Travian puede detectar bots que solo realizan acciones productivas (enviar raids, construir edificios, entrenar tropas) sin visitar nunca otras partes del juego. Un jugador real tiene curiosidad: mira el ranking, lee mensajes, consulta el mapa, revisa estadísticas. Ese comportamiento exploratorio es difícil de falsificar con simplicidad — pero es necesario para parecer humano.

El sistema de ruido simula ese comportamiento: el bot navega periódicamente por páginas no esenciales del juego, siguiendo rutas configuradas por el usuario. Esas rutas pueden incluir clicks encadenados, hovers, y esperas en cada paso — todo humanizado.

---

## Conceptos clave

### Destino

Un "destino" es una URL (o patrón de URL) de Travian que el bot puede visitar como ruido. Por ejemplo: el mapa del mundo, la página de estadísticas, los mensajes, el ranking de puntos.

Cada destino tiene un **peso de frecuencia** (`frequency_weight`): cuanto mayor es el peso de un destino comparado con los demás, más frecuentemente el bot lo visita. Un destino con peso 2 se visita el doble que un destino con peso 1.

### Ruta

Una "ruta" es una secuencia de pasos que llevan hasta un destino. Por ejemplo, para visitar el mapa: `click en el enlace "Mapa" del menú lateral`. Una ruta puede tener varios pasos encadenados.

Cada ruta tiene un **origen**: desde qué pantalla de Travian arranca. El bot solo ejecuta esa ruta si el Chrome está en la pantalla de origen (o si el origen es `ANY`, que significa "desde donde sea").

### Paso

Cada paso de una ruta puede ser:
- **CLICK**: hacer click en un elemento identificado por un selector CSS.
- **HOVER**: mover el cursor encima de un elemento sin clicar.
- **WAIT_FOR_SELECTOR**: esperar a que un elemento aparezca en la pantalla.

Cada paso tiene un delay mínimo y máximo (entre 500 ms y 5000 ms). El bot espera un tiempo aleatorio dentro de ese rango entre pasos. No se puede configurar un delay menor a 200 ms — el sistema lo bloquea para garantizar que el comportamiento siempre parezca humano.

---

## Cómo funciona

### Ciclo de ruido

El WorldAgent, mientras está en modo HARDCORE o PASIVO, ejecuta una acción de ruido de vez en cuando. El intervalo entre acciones es aleatorio, calculado a partir de un rango de peticiones/hora configurado:

- **HARDCORE**: 80-150 peticiones/hora por defecto.
- **PASIVO**: 15-40 peticiones/hora por defecto.

Cuando llega el momento:
1. El bot selecciona un destino al azar, con probabilidad proporcional al peso de cada destino.
2. Elige una ruta activa hacia ese destino.
3. Ejecuta la ruta paso a paso, con delays humanizados.
4. Después de llegar al destino, espera entre 2 y 30 segundos (dwell) antes de retomar las tareas productivas.
5. Programa la próxima acción de ruido con un nuevo intervalo aleatorio.

### Rutas muertas

Si una ruta falla repetidamente (el bot hace click pero no llega a la URL esperada), el sistema la marca como "muerta" y deja de usarla. Esto protege de rutas que se rompen cuando Travian cambia el layout del juego.

---

## Anclas semilla y wizard de creación

Configurar rutas de ruido requería antes saber cuáles son los selectores CSS de los elementos en Travian. El **wizard de creación** (noise-path-wizard.md) simplifica ese proceso:

1. El usuario selecciona una pantalla de partida (ancla/origen) de una lista predefinida: Recursos, Edificios, Mapa, Estadísticas, Mensajes, Reportes, etc. También puede seleccionar cualquier aldea propia como punto de partida.
2. El usuario pega el código HTML del botón o enlace que quiere clicar.
3. El sistema deriva automáticamente el selector CSS estructural más robusto para ese elemento.
4. El usuario puede probar la ruta en vivo antes de guardarla.

### Botón "Ir al inicio" — pendiente de implementación

El spec `noise-navigate-to-origin.md` describe un botón que lleva el Chrome del bot a la pantalla del ancla seleccionada, para que el usuario pueda inspeccionar los elementos y copiar su HTML desde ahí. **Este botón no está implementado todavía** (EP-N15 está en estado `ready-for-impl`).

---

## Reglas de negocio

| ID | Regla |
|---|---|
| RN-N01 | El delay entre pasos tiene un mínimo forzado de 200 ms. No configurable por debajo. |
| RN-N02 | El sistema de ruido solo está activo en modos HARDCORE y PASIVO. En DISCONNECTED no se ejecuta ninguna acción de ruido. |
| RN-N03 | Los selectores CSS deben ser estructurales (por atributo, clase, tipo de elemento). Nunca por texto visible — Travian puede estar en cualquiera de los 25 idiomas soportados. |
| RN-N04 | Un destino con `is_safe=False` no recibe tráfico de ruido aunque esté configurado. |
| RN-N05 | Los clicks de ruido pasan por `human_click_at_rect` — nunca por `element.click()` directo. |
| RN-NP07 | Una ruta con demasiados fallos consecutivos se marca como "muerta" (`is_dead=True`) y se excluye del sorteo. |

---

## Actores

| Actor | Rol |
|---|---|
| Usuario | Configura destinos, rutas y el wizard. Puede probar rutas en vivo (EP-N14). |
| WorldAgent | Ejecuta las rutas de ruido en los momentos programados |
| Frontend | Ofrece la UI del wizard y la gestión de destinos/rutas |

---

## Límites conocidos y pendientes

- **Control de frecuencia:** el usuario no puede configurar la frecuencia como "cada 5-7 minutos". Solo puede configurar peticiones/hora. El spec `noise-frequency-and-destination-weight.md` introduce esta mejora pero está pendiente de implementación (gates guardian + desarrollador-apis pendientes).
- **Peso por destino:** el campo `frequency_weight` existe en BD y funciona en el sorteo interno, pero no está expuesto en la UI para que el usuario lo configure directamente. También pendiente de la implementación del spec de frecuencia.
- **Botón "Ir al inicio":** el EP-N15 del wizard está especificado pero no implementado.
- **PASIVO y ruido:** en modo PASIVO, el ruido sí se ejecuta (a menor frecuencia según la config PASIVO). Las acciones de oasis, edificios y tropas están suspendidas, pero el ruido de navegación sigue activo — el humano que tiene el juego en segundo plano sí navega ocasionalmente.

🔖 Última revisión: 2026-06-04 (documento creado — noise base + wizard EP-N01..N14 documentados; EP-N15 y frequency-weight pendientes)
