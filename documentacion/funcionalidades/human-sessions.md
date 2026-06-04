# Human Sessions — Documento de negocio

Feature: Human Sessions v2.1 (timeline horario + tres modos de actividad)
Spec técnico: `docs/specs/human-sessions.md`
Documentación de código: `documentacion/backend/human-sessions.md`
Referencia de API: `documentacion/api/human-sessions.md`

---

## Por qué existe

El bot fue baneado por Travian en 2026-05 (primera ofensa: downgrade del 33% de edificios). La causa raíz fue que el bot operaba las 24 horas los 7 días de la semana al mismo ritmo y recorría las colecciones de tareas siempre en el mismo orden. Ningún jugador humano hace eso: los humanos duermen, comen, trabajan y tienen hábitos distintos entre semana y fin de semana.

Human Sessions resuelve ese problema introduciendo un **calendario semanal configurable**: el bot adapta su nivel de actividad a la hora del día y al día de la semana, igual que lo haría un jugador real.

---

## Los tres modos de actividad

| Modo | Qué hace el bot | Analogía humana |
|---|---|---|
| **HARDCORE** | Operación completa: envía raids, construye edificios, entrena tropas, ejecuta ruido de navegación | El jugador está activamente jugando |
| **PASIVO** | Actividad muy reducida: solo envía listas de vacas de vez en cuando (5% de probabilidad por defecto, con intervalo doblado). Chrome sigue abierto. | El jugador tiene el juego en segundo plano mientras hace otra cosa |
| **DISCONNECTED** | Parada total. Chrome se cierra. El bot no hace nada productivo. | El jugador cerró el navegador para dormir o trabajar |

**Por qué DISCONNECTED cierra Chrome:** mantener el Chrome abierto 24/7 con una sesión activa en Travian es una firma detectable (los jugadores reales no dejan el navegador abierto mientras duermen). Al cerrar Chrome, la sesión deja de emitir pings a Travian.

**Por qué PASIVO mantiene Chrome abierto:** el jugador que deja el juego "en segundo plano" no cierra el navegador. Solo cierra el navegador quien para completamente (DISCONNECTED).

---

## Cómo se configura el calendario

El usuario configura hasta 7 timelines distintos, uno por día de la semana (lunes=0 … domingo=6). Cada timeline es una lista de bloques horarios, cada uno con un modo asignado.

**Ejemplo:**
```
Lunes:
  00:00 - 08:00  DISCONNECTED   (durmiendo)
  08:00 - 13:00  HARDCORE       (mañana productiva)
  13:00 - 15:00  PASIVO         (comiendo, juego en segundo plano)
  15:00 - 23:00  HARDCORE       (tarde productiva)
  23:00 - 24:00  DISCONNECTED   (durmiendo pronto)
```

Si el usuario no configura un día, el sistema usa un calendario por defecto:
- Lun-Vie: 08:00-23:00 HARDCORE, resto DISCONNECTED
- Sáb-Dom: 09:00-24:00 HARDCORE, resto DISCONNECTED

**Huecos en el calendar:** si el usuario solo configura algunos bloques, los huecos se rellenan automáticamente con DISCONNECTED. Por ejemplo, si solo se configura `08:00-22:00 HARDCORE`, el sistema añade automáticamente `00:00-08:00 DISCONNECTED` y `22:00-24:00 DISCONNECTED`.

---

## Jitter de bordes

Los bordes de cada bloque (la hora a la que el bot cambia de modo) tienen un jitter aleatorio de ±15 minutos por defecto. Si el bloque empieza a las 08:00, el bot puede entrar en ese modo entre las 07:45 y las 08:15.

**Por qué:** un jugador humano no empieza a jugar exactamente a las 08:00:00. El jitter evita que el bot tenga un patrón de transición perfectamente regular y detectable.

---

## Override manual de modo

El usuario puede forzar un modo en cualquier momento vía la API. El override:
- Se aplica inmediatamente.
- Dura hasta que llegue el próximo borde de bloque del calendario (con jitter).
- Si el override pide el modo que ya está activo, no tiene efecto (devuelve éxito).
- Si se fuerza DISCONNECTED → Chrome se cierra en el próximo ciclo.
- Si se fuerza HARDCORE/PASIVO estando en DISCONNECTED → el bot hace relogin automático.

---

## Relogin automático

Cuando el bot sale de DISCONNECTED (por transición de calendario o por override manual), necesita volver a autenticarse en Travian porque Chrome estaba cerrado. El bot ejecuta el flujo de login automáticamente.

Si el login falla (error de red, servidor caído), reintenta con backoff exponencial: espera 10 minutos, luego 20, luego 40, hasta un máximo de 60 minutos entre intentos.

Si el fallo es porque la clave de cifrado (`TRAVIAN_BOT_SECRET_KEY`) no está disponible o las credenciales no se pueden descifrar, el bot entra en estado de error permanente y no reintenta automáticamente. El usuario debe corregir las credenciales y reiniciar.

---

## Comportamiento PASIVO para listas de vacas

Cuando el modo es PASIVO y llega el momento de enviar una lista de vacas:
1. El bot lanza un dado virtual: con probabilidad del 5% (configurable), ejecuta el envío normalmente.
2. Con probabilidad del 95%, omite el envío pero lo registra como "skipped".
3. En ambos casos, el próximo envío se programa con el doble del intervalo normal (configurable entre 1.5× y 5×).

Esto simula al jugador que "de vez en cuando echa un vistazo" al juego pero no está prestando atención activamente.

---

## Reglas de negocio

| ID | Regla |
|---|---|
| RN-HS02 | El modo activo se calcula en runtime del reloj; nunca se persiste en BD. Al reiniciar, el bot recalcula el modo correcto para la hora actual. |
| RN-HS03 | El timeline es por día de la semana (7 calendarios). Un solo calendario para todos los días sería firma: un humano no juega igual todos los días. |
| RN-HS04 | Los huecos en el calendario se rellenan con DISCONNECTED. Los solapes (dos bloques que se pisan) devuelven error. |
| RN-HS10 | Un WorldAgent por mundo. Cada mundo tiene su propio calendario y su propio Chrome. Entrar en DISCONNECTED solo cierra el Chrome de ese mundo. |
| RN-HS11 | Si no hay calendario configurado para un mundo, se usa el calendario por defecto (hardcodeado en código, no en BD). |

---

## Parámetros configurables

| Parámetro | Dónde | Descripción |
|---|---|---|
| Timeline por día | `PUT /worlds/{id}/session/timeline/{weekday}` | Bloques horarios con sus modos |
| Jitter en minutos | En el body de PUT timeline | ±N minutos en los bordes. Default: 15 |
| `passive_interval_factor` | `PUT /worlds/{id}/session/config` | Multiplicador del intervalo de farm lists en PASIVO. Default: 2.0. Rango: [1.5, 5.0] |
| `passive_send_probability` | `PUT /worlds/{id}/session/config` | Probabilidad de ejecutar una farm list en PASIVO. Default: 0.05 (5%). Rango: [0.01, 0.50] |
| Override de modo | `PUT /worlds/{id}/session/mode` | Fuerza un modo hasta el próximo borde de bloque |

---

## Cómo se ve en la app

La pestaña "Sesión" está en el sidebar de cada mundo (ruta `/mundos/:worldId`). Tres zonas principales:

1. **Estado actual** — Badge del modo activo (verde HARDCORE, azul Pasivo, gris Descanso total), bloque horario en curso (ej. "Bloque: 20:00 – 23:30"), jitter configurado (±15 min), y cuenta atrás al próximo cambio de modo. Si hay override activo, muestra también cuánto tiempo queda para que el override expire y un botón "Cancelar override".

2. **Forzar modo** — Tres botones (HARDCORE / Pasivo / Descanso total). El botón del modo activo aparece resaltado con el color del modo. Al pulsar uno, el bot cambiará de modo en el próximo ciclo (no es instantáneo — tarda como máximo el tiempo de un tick del WorldAgent).

3. **Calendario semanal** — Selector de 7 días. Al hacer clic en un día, aparece la barra de timeline de 24h (coloreada por modo) y el editor de bloques. En el editor se configuran los bloques horarios del día: hora de inicio, hora de fin y modo. Al guardar, el bot adoptará esa configuración en la próxima transición de bloque.

### Función de copia de días

El editor de bloques incluye tres presets de copia: "Toda la semana", "Entre semana" y "Fin de semana". Al aplicar uno, los bloques del día actualmente editado se copian a todos los días del grupo seleccionado de forma secuencial.

---

## Límites conocidos

- Los bloques no pueden cruzar medianoche en una sola definición. Un bloque `23:00-08:00` debe dividirse en `23:00-24:00` y `00:00-08:00` en días separados.
- El bot no recarga el calendario en caliente si el usuario lo modifica mientras está en medio de un bloque. El cambio se aplica en la próxima transición de bloque.
- El modo PASIVO para acciones distintas de farm lists (edificios, tropas, oasis) está definido como "no activo" — en el futuro se podría añadir comportamiento diferenciado (navegación suave, lectura de mensajes). Está documentado como fuera de alcance de la v2.1.
- El forzar un modo (override) no es instantáneo: el cambio se aplica en el siguiente ciclo del WorldAgent. La API confirma inmediatamente, pero el bot puede tardar varios segundos en reaccionar.

---

## Discrepancia documentada: spec de diseño desactualizado

El spec de diseño `docs/design/human-sessions-ui.md` usa el nombre `IDLE` para el segundo modo en varios lugares (tokens CSS `--mode-idle`, microcopy `session.status.mode.idle`). El spec funcional `docs/specs/human-sessions.md` v2.1 renombró definitivamente `IDLE` → `PASIVO`. El código real y la UI implementan `PASIVO`. El spec de diseño es la fuente desactualizada. Ver detalles en `documentacion/backend/human-sessions.md` §DIV-HS01.

🔖 Última revisión: 2026-06-04 (ampliado: sección "Cómo se ve en la app", función de copia de días, actualización de límites, discrepancia IDLE/PASIVO documentada)
