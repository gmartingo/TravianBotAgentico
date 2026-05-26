# Sesión del bot — login, logout y estado

Documento de negocio — para stakeholders, Product Owner y responsables de producto.

Spec técnico de referencia: [`docs/specs/login-sesion-api.md`](../../docs/specs/login-sesion-api.md) (incluye Amendment A1)
Documentación de código: [`backend/sesion.md`](../backend/sesion.md)
Referencia de API: [`api/sesion.md`](../api/sesion.md)

---

## Qué aporta esta funcionalidad

El bot de Travian necesita autenticarse en cada servidor de juego antes de poder leer recursos, edificios, tropas o cualquier otra información de las aldeas. Antes de esta funcionalidad, el sistema podía conectar con el navegador Chrome pero no había ninguna forma de iniciar o cerrar esa sesión a través del dashboard.

Con la feature de sesión, el operador puede ordenar al bot que haga login o logout en un mundo concreto desde la interfaz web, y puede consultar en cualquier momento si la sesión está activa. Una vez activa la sesión, todas las funciones de lectura de datos de Travian quedan disponibles automáticamente.

**Objetivo de negocio**: permitir al operador controlar el ciclo de vida del bot (encender/apagar su sesión de juego) sin necesidad de acceder al servidor directamente.

---

## A quién afecta

| Actor | Qué cambia |
|---|---|
| Operador humano (usa el dashboard) | Puede iniciar y cerrar sesiones del bot mediante botones en la interfaz; ve el estado actual de cada sesión |
| Bot (LiveOverviewAdapter) | A partir de que la sesión está activa, puede navegar páginas de Travian reales en vez de páginas de prueba |
| Administrador del servidor | Debe asegurarse de que `TRAVIAN_BOT_SECRET_KEY` no cambia mientras haya cuentas registradas (ver "Nota de operación" más abajo) |

---

## Cómo funciona — vista de negocio

### Abrir sesión (login)

El operador solicita abrir sesión para una cuenta concreta en un mundo concreto. El bot:

1. Busca en su base de datos las credenciales de esa cuenta (guardadas de forma cifrada desde el momento del registro).
2. Descifra la contraseña en memoria, solo durante el tiempo necesario para teclearla.
3. Abre Chrome con el perfil del usuario correspondiente a esa cuenta+mundo.
4. Navega a la página de login de Travian y teclea las credenciales como lo haría una persona: carácter a carácter, con pausas variables entre ellos (entre 80 y 220 ms por carácter).
5. Confirma que el login fue exitoso comprobando que la URL resultante contiene la pantalla del juego.
6. Mantiene el navegador abierto en memoria. Desde ese momento, todas las lecturas de datos de Travian se realizan a través de ese navegador ya autenticado.

El proceso completo tarda entre 3 y 10 segundos. Es intencional: los delays imitan el comportamiento humano y forman parte de la estrategia de anti-detección.

Si ya había una sesión activa para ese mundo, se cierra limpiamente antes de abrir la nueva. No se devuelve ningún error en ese caso.

### Cerrar sesión (logout)

El operador solicita cerrar la sesión. El bot cierra el proceso Chrome asociado a ese mundo. La operación es inmediata y segura: cerrar el proceso de Chrome localmente no genera ningún tráfico de red hacia Travian ni es detectable.

Si no había sesión activa, la operación finaliza sin error (es idempotente).

### Consultar estado

El operador puede consultar en cualquier momento si hay sesión activa para un mundo concreto. La respuesta es inmediata (no requiere que haya sesión activa).

---

## Reglas de negocio clave

| Regla | Descripción |
|-------|-------------|
| Las credenciales nunca viajan por la red | El endpoint de login no acepta ninguna contraseña en el cuerpo de la petición. Las credenciales se recuperan de la base de datos cifrada del servidor. |
| La contraseña existe en claro solo durante el login | Se descifra en memoria justo antes de teclearla, y no se guarda en ningún log ni en ninguna variable persistente. |
| Una sesión por mundo | Solo puede haber una sesión activa por mundo. Si se hace login cuando ya hay sesión, la anterior se cierra automáticamente. |
| Las sesiones son temporales | Las sesiones viven en memoria. Si el servidor del bot se reinicia, todas las sesiones desaparecen. El operador debe volver a hacer login. |
| La API no distingue tipos de fallo de login | Si el login falla (credenciales incorrectas, error de red, Travian lento), el bot devuelve el mismo código de error genérico. Esto es intencional: no dar información que permita adivinar si una cuenta existe o no. |

---

## Nota de operación — clave de cifrado estable

La contraseña de cada cuenta se guarda cifrada con una clave secreta (`TRAVIAN_BOT_SECRET_KEY`) que debe estar configurada en el servidor. Esta clave debe ser **estable**: si cambia, las contraseñas guardadas quedarán indescifrables y el login de todas las cuentas fallará con error `401` sin que Chrome se abra.

**Síntoma**: login devuelve `401` aunque las credenciales sean correctas, y en los logs del servidor aparece "InvalidToken al descifrar contraseña".

**Recuperación**: si la clave cambia accidentalmente, hay que volver a registrar o actualizar la contraseña de cada cuenta afectada a través del endpoint correspondiente (`PUT /accounts/{id}`). La nueva contraseña se guardará cifrada con la clave actual.

**Recomendación**: guardar `TRAVIAN_BOT_SECRET_KEY` en `~/.zshrc` (macOS/Linux) o como variable de entorno persistente en Windows, y no modificarla. Hacer una copia de seguridad de la clave en un lugar seguro.

---

## Lo que esta funcionalidad no hace

- No gestiona autenticación de usuarios del dashboard (cualquiera que acceda al servidor puede abrir y cerrar sesiones — es un bot de uso personal).
- No detecta automáticamente si Chrome muere durante la sesión. Si el proceso cae, `is_active` seguirá devolviendo `True` hasta que el operador haga logout + login para recuperar la sesión.
- No notifica al operador en tiempo real si la sesión cae (no hay WebSocket ni notificaciones push en esta versión).
- No persiste el estado de sesión en base de datos (no hay "sesión permanente" que sobreviva reinicios).

---

🔖 Última revisión: 2026-05-26
