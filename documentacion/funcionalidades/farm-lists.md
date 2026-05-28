# Farm Lists — Documentación de negocio

Audiencia: responsables de producto, propietario del proyecto, cualquier persona que quiera
entender qué hace el bot con las farm lists sin leer código.

---

## Qué es una farm list en Travian

En Travian, una **farm list** (o "lista de vacas") es un grupo de aldeas enemigas con poca
o ninguna defensa que el jugador ataca repetidamente para robar sus recursos. El jugador crea
estas listas manualmente en Travian y las organiza por nombre.

El término "vaca" es jerga habitual entre jugadores: aldeas que dan recursos regularmente y
sin apenas resistencia.

---

## Qué problema resuelve el bot

Enviar listas de vacas manualmente requiere abrir Travian varias veces al día, recordar cuándo
enviar, y estar pendiente de si alguna vaca ha empezado a defender. Esto es:
- Tedioso y repetitivo.
- Arriesgado: si el jugador olvida enviar, pierde recursos que debería haber cosechado.
- Peligroso: si una vaca empieza a defender y el jugador no lo nota, pierde tropas.

El bot automatiza el envío periódico, gestiona las vacas que han causado pérdidas, y avisa
en el historial qué ha pasado. El jugador solo necesita revisar el dashboard de vez en cuando.

---

## Cómo funciona a alto nivel

### El ciclo automático (enviado por el scheduler)

El bot repite este ciclo de forma periódica para cada farm list que el usuario ha configurado:

1. **Lee el estado actual desde Travian.** Abre la plaza de reuniones y lee todas las listas,
   incluyendo el resultado del último raid de cada vaca.

2. **Evalúa cada vaca individualmente:**
   - Si una vaca activa tuvo pérdidas → la desactiva y la pone en cuarentena durante 1 hora.
   - Si una vaca en cuarentena recibió un raid limpio (sin pérdidas) → la reactiva.
   - Si una vaca en cuarentena lleva 1 hora sin que haya llegado ningún informe → envía una
     "sonda" (un raid de prueba) para ver si sigue siendo segura.
   - Si la sonda también trae pérdidas → la cuarentena se extiende al doble (2 horas, luego 4,
     hasta un máximo de 24 horas).

3. **Envía la lista** con las vacas que están activas en ese momento.

4. **Registra todo en el historial** para que el jugador pueda revisar qué pasó.

### El envío manual

El usuario puede enviar cualquier lista en cualquier momento desde el dashboard pulsando
"Enviar ahora". Esta acción no activa la lógica de pérdidas/sondas: es un disparo puntual
que registra el evento como "manual" en el historial.

---

## Actores del sistema

| Actor | Rol |
|---|---|
| **Jugador (usuario del bot)** | Configura las listas en Travian, define los schedulers, revisa el historial y puede activar/desactivar vacas manualmente |
| **Bot (WorldAgent + scheduler)** | Ejecuta el ciclo automático de envío según la configuración del jugador |
| **Travian** | Fuente de verdad del estado real de las listas y los resultados de los raids |

---

## Qué puede configurar el usuario

### Schedulers

Un **scheduler** es el temporizador que dispara el envío periódico. El usuario puede crear
tantos schedulers como quiera y asignar farm lists distintas a cada uno.

Configuración de cada scheduler:

| Parámetro | Descripción | Restricciones |
|---|---|---|
| Nombre | Etiqueta descriptiva | 1–100 caracteres |
| Intervalo mínimo | Tiempo mínimo entre disparos | Mínimo 1 minuto |
| Intervalo máximo | Tiempo máximo entre disparos | Debe ser ≥ mínimo |
| Activado/desactivado | Permite pausar el scheduler sin borrarlo | — |

El intervalo real de cada disparo se elige al azar entre el mínimo y el máximo. Esta
aleatoriedad es deliberada: un bot que envía siempre a las mismas horas en punto es más
fácil de detectar por Travian.

### Asignación de listas a schedulers

Cada farm list puede estar asignada a cero o un scheduler. Si no tiene scheduler asignado,
no se envía automáticamente (solo manual). Si el scheduler se borra, la lista queda sin
scheduler pero no se borra.

### Activar / desactivar vacas manualmente

El usuario puede activar o desactivar cualquier vaca individual desde el drawer de la farm
list. Cuando el usuario desactiva una vaca, el bot no la toca: la desactivación manual tiene
prioridad absoluta sobre la lógica automática.

---

## Reglas de negocio

| ID | Regla |
|---|---|
| RN-01 | El bot no envía manualmente, pero sí automáticamente según el scheduler configurado. |
| RN-02 | El intervalo entre disparos del scheduler es aleatorio para evitar patrones detectables. |
| RN-03 | Cuando un scheduler tiene varias listas, el bot espera entre 2 y 5 segundos al pasar de una a la siguiente (pausa anti-detección). |
| RN-04 | Una vaca desactivada manualmente (`is_active=False` por el usuario) no es tocada por el bot bajo ninguna circunstancia. |
| RN-05 | Si el último raid de una vaca activa tuvo pérdidas, el bot la desactiva y la pone en cuarentena de 1 hora. |
| RN-06 | Si llega un informe de raid limpio (sin pérdidas) para una vaca en cuarentena, el bot la reactiva. |
| RN-07 | Si llega un informe de raid con pérdidas para una vaca en cuarentena (raid en vuelo o sonda fallida), el bot actualiza el informe de referencia y mantiene la cuarentena. |
| RN-08 | Si la cuarentena expira sin que llegue ningún informe nuevo, el bot activa brevemente la vaca, envía la lista (la vaca sale en la sonda), y la vuelve a desactivar. Si la sonda también trae pérdidas, la cuarentena se duplica. |
| RN-09 | El bot no reacciona dos veces al mismo informe de pérdidas (cada informe se procesa una sola vez). |
| RN-10 | Cuando el bot reactiva una vaca que él mismo había desactivado, registra un evento REACTIVATED en el historial. |
| RN-11 | El usuario puede cancelar una sonda pendiente de dos formas: desactivando la vaca indefinidamente, o forzando que la sonda se envíe en el próximo ciclo. |
| RN-12 | Si el usuario activa manualmente en Travian una vaca que el bot había desactivado, el bot lo acepta y limpia su cuarentena. |
| RN-13 | El historial de envíos se conserva durante 7 días. Los registros más antiguos se purgan automáticamente. |
| RN-14 | Si se borra un scheduler, las farm lists que tenía asignadas quedan sin scheduler pero no se borran. |
| RN-15 | Si Travian reasigna el ID interno de una vaca (puede ocurrir al reordenar listas), el bot la reconoce por sus coordenadas y preserva su historial de botín. |
| RN-16 | El usuario puede cancelar una sonda pendiente de dos formas: desactivar la vaca indefinidamente (modo "deactivate") o forzar el envío de la sonda en el próximo ciclo (modo "send_now"). |

---

## Seguimiento de botín (farm stats)

El bot lleva un registro del botín obtenido en cada raid. Estos datos permiten evaluar qué
vacas rinden más y qué tan eficiente es cada scheduler.

### Cómo se acumula el botín

Cada vez que llega un informe de raid nuevo con botín real, se registra en el historial.
**El botín acumulado se calcula siempre sobre los últimos 7 días** (misma ventana que el
historial de envíos). No se guardan datos más antiguos.

Esta política implica que la cifra de "botín total" de una vaca o un scheduler se reinicia
implícitamente pasada una semana de inactividad. Es un trade-off aceptado: el dashboard
muestra tendencias recientes, no un contador histórico ilimitado.

### Métricas disponibles por scheduler

El dashboard puede mostrar para cada scheduler:

| Métrica | Qué significa |
|---|---|
| Tasa de éxito | Porcentaje de envíos con resultado "success" en los últimos 7 días |
| Slots activos promedio | Media de vacas que estaban activas en los últimos 7 días |
| Botín total | Suma de todo el botín de los últimos 7 días |
| Botín por hora | Botín total dividido entre las horas desde el primer envío registrado |
| Último envío | Cuándo se envió la lista por última vez |

Estas mismas métricas están disponibles desglosadas por farm list dentro del scheduler.

### Historial del scheduler en los envíos

Cada registro de envío guarda una foto del scheduler en ese momento: su nombre, sus
intervalos y cuántas veces había disparado. Esto permite revisar el historial aunque el
scheduler haya sido modificado o borrado después.

---

## Estados posibles de una vaca

| Estado visible en el dashboard | Qué significa |
|---|---|
| Activa | El bot la incluye en los envíos normalmente |
| Desactivada por el bot | El bot la detectó con pérdidas y la puso en cuarentena |
| Sonda pendiente | Cuarentena expirada; el bot va a enviarla en el próximo ciclo como prueba |
| Desactivada manualmente | El usuario la apagó; el bot no la toca |

---

## Límites conocidos

- **El historial de botín acumula solo 7 días.** Si el usuario quiere ver el total histórico
  de toda la vida de una vaca, no está disponible.
- **No hay desglose por tipo de recurso.** El bot registra el botín total (madera + barro +
  hierro + grano como un único número). El desglose detallado por recurso está reservado para
  una funcionalidad futura (Agente ROI).
- **Los datos de botín de antes de la primera instalación de esta funcionalidad se perdieron**
  durante la migración de esquema. Es una pérdida de datos única y aceptada.

---

🔖 Última revisión: 2026-05-28 (documentación inicial de la feature farm lists)
