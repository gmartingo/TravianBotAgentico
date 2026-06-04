# Mecánica de spawn de oasis — Documento funcional y de negocio

> Audiencias: (1) stakeholders, product owner, usuario final avanzado — sección de negocio; (2) desarrolladores — ver también `documentacion/backend/referencia-funciones/oasis-spawn-composition.md`.
> Spec de referencia: `docs/specs/oasis-spawn-mechanics-stats.md` y `docs/specs/reaparicion-animales-oasis.md`.
> Feature relacionada: Reportes de ataques a oasis (`documentacion/funcionalidades/oasis-reportes-ataques.md`).

---

## Qué resuelve esta feature

El usuario lleva tiempo recopilando reportes de ataques a oasis para entender cuándo es rentable atacar y con qué equipo. El problema era que la métrica anterior (`avg_regen_per_hour`, "promedio de regeneración por hora") **mezclaba conceptos incompatibles**: la ráfaga de spawn (muchos animales de golpe) con el cooldown posterior (el oasis deja de generar durante horas). El resultado era un número que no servía para tomar ninguna decisión táctica real.

Esta feature reemplaza esa métrica por un conjunto de indicadores coherentes con la mecánica real del juego, junto con un panel educativo que explica al usuario cómo funciona el sistema de spawn.

---

## Objetivo de negocio

Permitir al usuario responder dos preguntas antes de cada ataque a un oasis:

1. **¿Está generando el oasis ahora?** (¿Vale la pena atacar?)
2. **¿Con cuántos animales me voy a encontrar en el peor caso?** (¿Qué equipo necesito?)

---

## Actores

| Actor | Rol |
|---|---|
| Usuario del bot (único) | Consulta los paneles. No hay escritura ni configuración en esta feature. |

No hay autenticación en esta sección. El acceso a los paneles es libre para quien use la aplicación.

---

## Cómo funciona la mecánica de spawn (contexto de negocio)

Para entender qué calcula el sistema, hay que entender primero cómo funciona el spawn de animales en Travian:

1. **Orden fijo:** los animales reaparecen siempre en el mismo orden: rata → araña → serpiente → murciélago → jabalí → lobo → oso → cocodrilo → tigre → elefante.

2. **Timers fijos (servidor x1):** cada especie tiene un timer fijo de spawn. La rata reaparece cada 5 minutos, la araña cada 6, ... el elefante cada 14. Estos tiempos son fijos en todos los servidores x1 de Travian.

3. **Sets de animales por tipo de oasis:** no todos los tipos de oasis generan todos los animales. Hay cuatro tipos:

   | Tipo de oasis | Animales del set normal |
   |---|---|
   | Hierro | Rata, Araña, Murciélago |
   | Arcilla | Rata, Araña, Jabalí |
   | Madera | Jabalí, Lobo, Oso |
   | Cereal | Todos (rata hasta elefante) |

4. **Ráfaga de spawn:** cuando un oasis "se dispara", genera DE GOLPE un número fijo de animales de su set y los libera a su cadencia. Luego entra en **cooldown** (probablemente horas, aunque el umbral exacto no está documentado en el juego).

5. **Anomalías:** a veces aparece un animal que no pertenece al set normal del oasis (por ejemplo, un cocodrilo en un oasis de arcilla). Esto es raro y se muestra como "anomalía" en el panel, pero no se usa para calcular el peor caso (distorsionaría el umbral defensivo).

---

## Las cuatro piezas de la feature

### Pieza 1 — Panel educativo (SpawnMechanicsPanel)

Un panel colapsable en la pestaña Estadísticas que muestra:

- La tabla de timers de spawn (los 10 animales con su orden y su timer en min:ss).
- Los sets normales de animales por tipo de oasis (tabla de 4 filas).
- Una nota explicando qué es una anomalía.

Este panel **no llama a la API**. Los datos son estáticos. Se despliega automáticamente en la primera visita o cuando la base de datos está vacía (el usuario aún no tiene reportes). En visitas posteriores, empieza colapsado para no ocupar espacio.

### Pieza 2 — Composición típica por oasis

El sistema analiza todos los reportes históricos de cada oasis y calcula, por especie de animal:

- **Media por ráfaga** (`avg_present_per_burst`): promedio de cuántos animales de esa especie han aparecido en los ataques donde estaba presente (excluye los ataques donde no había ninguno).
- **Máximo por ráfaga** (`max_present_per_burst`): el mayor número observado de esa especie en una sola ráfaga.

Solo se muestran los animales que han aparecido al menos una vez. Un animal que nunca ha aparecido en ese oasis no ocupa espacio en el panel.

### Pieza 3 — Peor combinación a batir

El usuario elige un **intervalo de envío** (6, 7, 10 o 15 minutos). El sistema calcula cuántos animales de cada especie podrían estar presentes si el intervalo entre dos ataques consecutivos fuera exactamente ese.

La fórmula es:
```
peor_caso[especie] = máximo_histórico_observado + floor(intervalo_segundos / timer_spawn_especie)
```

Ejemplo: si el máximo de tigres observado es 7 y el timer del tigre es 13 min (780 s), con un intervalo de 10 min (600 s): `floor(600/780) = 0`, así que `peor_caso[tigre] = 7 + 0 = 7`. Con un intervalo de 15 min (900 s): `floor(900/780) = 1`, así que `peor_caso[tigre] = 7 + 1 = 8`.

Las anomalías **no se incluyen** en el peor caso.

### Pieza 4 — Estado cooldown/respawn

Por cada oasis, el sistema calcula cuánto tiempo ha pasado desde el último ataque registrado y lo clasifica en uno de tres estados:

| Estado | Significado | Color |
|---|---|---|
| **Repoblando** | El oasis acaba de ser atacado recientemente — puede estar generando animales | Verde |
| **Cooldown** | Han pasado más de 4 horas desde el último ataque — probablemente no está generando | Rojo |
| **Desconocido** | Zona intermedia o tipo no inferible | Gris |

**Nota importante:** los umbrales son heurísticos. Travian no documenta públicamente cuándo exactamente un oasis entra y sale del cooldown. Los 4 horas como umbral de cooldown son una estimación conservadora basada en la experiencia, no en una certeza absoluta.

---

## Reglas de negocio

### Reglas del catálogo (fuente canónica)

**RN-CAT-01:** Los timers de spawn viven en un único fichero del backend (`core/game_data/oasis_spawn_catalog.py`). Ningún otro módulo puede hardcodear tiempos de spawn distintos. Si Travian cambia sus timers, se actualiza solo ese fichero.

**RN-CAT-02:** Los datos de fuerza defensiva de los animales se leen del fichero de datos de juego (`seeds/game_data/troop_stats.json`, filtrado por `tribe == "nature"`). No se hardcodean en el código.

### Reglas de inferencia del tipo de oasis

**RN-TYP-01:** El tipo de oasis se infiere automáticamente a partir de los animales que han aparecido con al menos 1 individuo en algún reporte. No hay forma de asignarlo manualmente ni se guarda en la base de datos.

**RN-TYP-02:** La inferencia usa similitud de Jaccard: se compara el conjunto de animales observados con el set normal de cada tipo, y se elige el tipo con mayor similitud. En caso de empate, gana el tipo con el set más pequeño (más específico).

**RN-TYP-03:** Un animal observado que no pertenece al set del tipo inferido es una "anomalía". Se muestra en el panel con etiqueta "anom." pero no contamina el cálculo del peor caso.

**RN-TYP-04/05:** Si el oasis tiene 3 o más ráfagas observadas (ataques con al menos un animal presente), la confianza es "media". Si tiene menos de 3, la confianza es "baja". Si ningún animal ha aparecido nunca, el tipo es desconocido.

### Reglas de la composición típica

**RN-COMP-01:** Solo se incluyen en el cálculo las ráfagas donde el animal estaba presente (`present > 0`). Un ataque donde no había ningún individuo de una especie no baja la media de esa especie.

**RN-COMP-02:** Un animal nunca observado no aparece como "0" en el panel — directamente no aparece.

### Reglas del peor caso

**RN-WORST-02:** La cota superior es `max_presente_histórico + spawns_posibles_en_el_intervalo`. Es una estimación pesimista, diseñada para que el usuario no subestime el número de animales.

**RN-WORST-05:** Las anomalías no se incluyen en el peor caso. Su aparición es rara y no es predecible.

**RN-WORST-06:** El intervalo de timer solo puede ser 6, 7, 10 o 15 minutos. Cualquier otro valor es rechazado.

### Reglas del estado cooldown/respawn

**RN-CD-01:** El tiempo transcurrido se calcula en el servidor usando la hora UTC, no el reloj del navegador del usuario.

**RN-CD-02/03:** El umbral de "repoblando" es el timer del animal más lento del set del oasis (si han pasado menos segundos de eso desde el último ataque, el oasis aún puede estar generando). El umbral de cooldown es 4 horas (ajustable).

**RN-CD-04:** Si el tipo del oasis es desconocido, el estado también es desconocido.

### Reglas de atribución (jugador/aldea)

**RN-ACCT-01:** El sistema no distingue si un atacante es "el usuario del bot" o un tercero. Todos los pares jugador/aldea extraídos de los reportes se tratan igual.

**RN-ACCT-05:** La lista de atacantes nunca es vacía. Si no se puede extraer ningún par, aparece como "Desconocido/Desconocido".

**RN-CITY-01:** La atribución se basa exclusivamente en los datos de los reportes. No se usa la configuración de las farm lists para inferir quién atacó qué oasis.

> **Nota sobre la decisión de no usar farm_lists:** en la versión v2.4 se usaba un JOIN con la tabla de farm lists para inferir la aldea atacante. El bug verificado era que aldea "05" era invisible porque sus oasis aparecían en las farm lists de "00"/"01"/"02"/"03" y la regla de asignación los atribuía erróneamente a esas aldeas. La corrección en v2.5 usa solo los blobs de texto de los propios reportes.

---

## Cómo leer el panel

### Jerarquía de la vista

El panel "Planificador de combate por oasis" organiza los datos en tres niveles:

```
Jugador
  └── Aldea
        └── Oasis (coords, tipo, estado)
               ├── Fila Media: ¿cuántos animales salen típicamente? (máximo observado)
               └── Fila Peor:  ¿cuántos en el peor caso para el intervalo elegido?
```

Un mismo oasis puede aparecer bajo varios jugadores y aldeas si ha sido atacado por distintas combinaciones de jugador/aldea. Sus estadísticas son las mismas en todos los casos (se calculan con todos los reportes, independientemente de quién atacó).

### Cómo interpretar la fila Media

Muestra el **máximo histórico observado** por especie, no la media matemática. El diseño eligió el máximo como valor de la fila "Media" porque es más conservador y útil tácticamente: el usuario sabe que al menos tantos animales pueden salir.

> **Divergencia respecto al nombre:** el campo en la API se llama `max_present_per_burst` y así debería llamarse en la UI. La etiqueta "Media" en la fila fue una decisión del diseño para contrastarlo con la fila "Peor", pero el número que muestra es el máximo. Esta ambigüedad está documentada para revisión futura.

### Cómo interpretar la fila Peor

Muestra cuántos animales de cada especie podría haber si se espera exactamente el intervalo elegido entre ataques. Es un número absoluto de animales, **no un multiplicador**.

### Anomalías

Las anomalías aparecen solo en la fila Media (con badge dorado "anom."). No aparecen en la fila Peor. El usuario puede ignorarlas para la planificación táctica, aunque es útil saber que ese tipo raro de animal ha aparecido en ese oasis.

### Selector de intervalo

Los 4 botones (6 / 7 / 10 / 15 min) representan el tiempo que el usuario espera entre un ataque y el siguiente. Elegir el intervalo correcto depende de la logística del usuario (cuánto tiempo tarda en preparar y enviar el siguiente ataque). El sistema no recomienda ningún intervalo automáticamente.

---

## Lo que esta feature NO hace (fuera de alcance v1)

- No soporta servidores con velocidad distinta de x1 (x2, x3, etc.). El diseño está preparado para ello pero no implementado.
- No calcula automáticamente el intervalo de timer óptimo. El usuario lo elige manualmente.
- No persiste el tipo inferido del oasis en la base de datos (se recalcula en cada llamada a la API).
- No envía alertas ni notificaciones proactivas cuando un oasis sale del cooldown.
- No tiene en cuenta el cap de población de animales del oasis en la proyección de peor caso.
- No hay actualización en tiempo real (no hay polling ni WebSocket).

---

## Deuda técnica conocida

| Referencia | Descripción |
|---|---|
| TR-01 | Soporte a velocidad de servidor != x1 (divisor de timers). Diseño preparado, no implementado. |
| TR-02 | El umbral de cooldown de 4 horas es heurístico. Si se documenta el umbral real de Travian, actualizar `COOLDOWN_THRESHOLD_S` en `core/game_data/oasis_spawn_catalog.py`. |
| TR-06 | `avg_regen_per_hour` sigue presente en EP-09 (stats globales). Pendiente de retirada cuando el frontend deje de consumirlo. |
| TR-11 | La query de villages no filtra por `world_id` porque `attack_reports.world_id` es NULL en el MVP. Pendiente cuando se añada el campo. |
| Pieza 5 | `avg_regen_per_hour` fue retirado de EP-06 y EP-10. Queda pendiente eliminarlo de EP-09. |

---

---

## Relación con otras features del tema OASIS

Esta feature es la capa de análisis táctica. Se alimenta de los datos recogidos por el módulo de **Reportes de ataques** (`documentacion/funcionalidades/oasis-reportes-ataques.md`). La automatización del farmeo es responsabilidad del módulo de **Oasis Farming** (`documentacion/funcionalidades/oasis-farming.md`).

```
Reportes de ataques  →  (datos históricos)  →  Mecánica de spawn  →  (decisión táctica)  →  Oasis Farming
```

---

## Divergencias código / spec adicionales detectadas (2026-06-04)

Ver `documentacion/backend/referencia-funciones/oasis-spawn-composition.md` para el listado completo. Las divergencias más relevantes de esta feature son:

- **Etiqueta "Media" vs dato `max_present_per_burst`:** la fila etiquetada "Media" en el planificador muestra el máximo histórico observado, no la media matemática. Ver nota en la sección "Cómo leer el panel".
- **`avg_regen_per_hour` en EP-09:** la métrica que esta feature buscaba retirar sigue presente en el endpoint de estadísticas globales. Pendiente de eliminación (TR-06).

---

🔖 Última revisión: 2026-06-04 (actualizado — añadidas referencias cruzadas a oasis-reportes-ataques y oasis-farming; divergencias adicionales documentadas)
