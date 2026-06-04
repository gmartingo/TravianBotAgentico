# Click humano indetectable — Documento de negocio

Feature: Human Click v2.3.1
Spec técnico: `docs/specs/human-click.md`
Documentación de código: `documentacion/backend/human-click.md`

---

## Qué resuelve y por qué existe

Travian detecta bots analizando los eventos del DOM que genera el browser. Un click producido por software tiene características que ningún humano reproduce:

- El cursor va directamente al píxel exacto del centro del botón, sin trayectoria previa.
- El `mousedown` y el `mouseup` ocurren con menos de 1 ms de separación.
- Entre clicks consecutivos, el cursor permanece inmóvil.
- La "velocidad" del movimiento es siempre la misma, independientemente de la distancia al objetivo.

Esta feature elimina todas esas firmas haciendo que **cada click del bot sea indistinguible de un click humano real**: el cursor sigue una trayectoria curva (Bézier), llega al objetivo en un tiempo proporcional a la distancia (ley de Fitts), hace una pequeña pausa de "decisión motora" antes de pulsar, y mantiene el botón pulsado entre 35 y 110 ms.

**Por qué surgió:** tras el baneo de 2026-06 (primera ofensa: downgrade del 33% de edificios), el análisis identificó dos firmas residuales de la versión anterior: el Bézier duraba 50-150 ms (demasiado rápido) y el cursor permanecía quieto entre clicks (imposible en un humano activo). Esta versión v2.3.1 cierra ambas.

---

## Actores

| Actor | Rol |
|---|---|
| Cualquier módulo del bot que clique algo en Travian | Caller de `human_click` o `human_click_at_rect` |
| Módulos con tiempos de espera conocidos (AJAX, dwell) | Pueden usar `human_drift_toward` para mover el cursor mientras esperan |

No hay actores externos ni usuarios finales directamente. Esta feature es infraestructura interna del bot.

---

## Qué hace el sistema

### Click humanizado

Cuando el bot necesita pulsar un botón o enlace en Travian, en lugar de hacer click directo:

1. Obtiene las dimensiones del elemento.
2. Determina un punto de aterrizaje aleatorio dentro del área del botón (nunca siempre el centro exacto).
3. Calcula cuánto tiempo debería tardar un humano en mover el cursor esa distancia (ley de Fitts: más lejos = más tiempo, entre 200 y 800 ms).
4. Genera una trayectoria curva y la recorre enviando eventos de movimiento de ratón.
5. Se detiene brevemente antes de pulsar (80-180 ms de "settle").
6. Pulsa y mantiene el botón entre 35 y 110 ms antes de soltar.

### Movimiento pre-click ("drift")

Cuando el bot sabe que va a pasar varios segundos esperando (por ejemplo, esperando que Travian procese una petición), puede aprovechar ese tiempo para mover el cursor hacia el siguiente botón que va a pulsar. Así, cuando llega el momento del click, el cursor ya está "cerca" — como haría un humano que se va acercando mientras espera.

### Cursor persistente entre clicks

El sistema recuerda dónde quedó el cursor después de cada click. El próximo click siempre parte de esa posición. Esto elimina la firma del "cursor que aparece de la nada en cada click".

---

## Reglas de negocio relevantes

| Regla | Descripción |
|---|---|
| RN-HC01 | El cursor tiene una posición persistente por pestaña del browser |
| RN-HC03 | El punto de aterrizaje es aleatorio dentro del 80% central del elemento (nunca el borde ni siempre el centro) |
| RN-HC08 | El click es: botón pulsado → pausa 35-110 ms → botón suelto. Nunca instantáneo. |
| RN-HC12 | La duración del movimiento sigue la ley de Fitts: a mayor distancia y menor tamaño del objetivo, más tiempo |
| RN-HC15 | `human_drift_toward` aprovecha tiempos de espera para mover el cursor con propósito |
| RN-HC16 | Los clicks en la misma pestaña se serializan — no puede haber dos clicks simultáneos |
| RN-HC17 | Si el click se interrumpe a mitad del trayecto, el cursor guardado refleja la última posición real enviada |
| RN-HC18 | Si el cursor estuviese fuera de los límites de la ventana, se resetea antes de comenzar el movimiento |

---

## Limitaciones conocidas

- La curvatura del movimiento usa el mismo rango de variación (`[10%, 25%]` de la longitud) independientemente de si la distancia es corta o larga. En movimientos muy largos (>500 px), la curvatura puede ser más pronunciada de lo estadísticamente normal para humanos. Está previsto corregirlo en v2.4.
- Si la página hace scroll durante un `human_drift_toward`, el punto de destino puede quedar desajustado con la nueva posición del elemento. El caller debe evitar drift sobre targets que pueden scrollear.
- Se usa `id()` de Python como clave para identificar la pestaña del browser. En teoría podría haber colisiones si se abren y cierran pestañas muy rápidamente. Pendiente para v2.4.

🔖 Última revisión: 2026-06-04 (documento creado — human-click v2.3.1)
