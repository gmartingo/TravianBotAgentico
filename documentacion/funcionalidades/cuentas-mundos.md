# Gestión de cuentas y mundos — registro, sesión y dashboard

Documento de negocio — para stakeholders, Product Owner y responsables de producto.

Spec funcional de referencia: [`docs/specs/registro-cuentas-mundos.md`](../../docs/specs/registro-cuentas-mundos.md)
Spec de sesión de referencia: [`docs/specs/login-sesion-api.md`](../../docs/specs/login-sesion-api.md)
Diseño de referencia: [`docs/design/gestion-cuentas-mundos.md`](../../docs/design/gestion-cuentas-mundos.md)
Documentación técnica backend: [`../backend/sesion.md`](../backend/sesion.md)
Referencia de API: [`../api/cuentas-mundos.md`](../api/cuentas-mundos.md), [`../api/sesion.md`](../api/sesion.md)
Frontend: [`../frontend/dashboard.md`](../frontend/dashboard.md)

---

## Qué aportan estas funcionalidades

El bot de Travian necesita saber a qué cuentas debe gestionar y en qué servidores juega cada una. Sin esta información, no tiene nada que automatizar.

Esta feature cubre dos capas:

1. **Registro de cuentas y mundos**: el operador registra sus credenciales de Travian (email + contraseña del lobby) y los servidores donde juega (una cuenta puede tener varios mundos). Los datos se persisten en la base de datos local del bot.

2. **Gestión de sesión**: una vez registrada una cuenta, el operador puede ordenar al bot que haga login en un mundo concreto. Mientras la sesión está activa, todas las funciones de lectura de datos de Travian (recursos, tropas, etc.) quedan disponibles para ese mundo.

**Objetivo de negocio**: dar al operador control total sobre qué cuentas y mundos gestiona el bot, y cuándo el bot está activo en cada uno de ellos.

---

## A quién afecta

| Actor | Qué cambia |
|---|---|
| Operador (único usuario) | Puede registrar cuentas, añadir mundos, editar credenciales y arrancar/parar el bot desde el dashboard |
| Bot (`LiveOverviewAdapter` y futuros adaptadores) | Solo puede leer datos de Travian cuando hay sesión activa para el mundo correspondiente |
| Administrador del servidor (en la práctica el mismo operador) | Debe mantener la variable `TRAVIAN_BOT_SECRET_KEY` estable; si cambia, todas las contraseñas almacenadas quedan indescifrables |

---

## Cómo funciona — vista de negocio

### Registrar una cuenta

El operador proporciona el email, el nombre de usuario y la contraseña del lobby de Travian. El bot:

1. Valida que el email no esté ya registrado (no puede haber dos cuentas con el mismo email).
2. Cifra la contraseña con una clave secreta del servidor (`TRAVIAN_BOT_SECRET_KEY`) antes de guardarla. La contraseña en claro nunca se persiste ni se devuelve en ninguna respuesta de API.
3. Crea la cuenta en la base de datos.

La contraseña es **write-only**: se envía al crear o actualizar una cuenta, pero nunca se lee de vuelta.

### Añadir un mundo

Cada cuenta puede tener uno o varios mundos (servidores de juego). Para cada mundo el operador indica la URL del servidor Travian y la tribu que juega allí. El bot:

1. Valida que la URL sea válida y que no esté ya registrada en esa cuenta.
2. Guarda el mundo asociado a la cuenta.

Solo se admiten las 7 tribus jugables: Romans, Teutons, Gauls, Egyptians, Huns, Spartans, Vikings. Las tribus NPC (Nature, Natars) son rechazadas.

### Editar y borrar

El operador puede editar el email o el nombre de usuario de una cuenta en cualquier momento. La contraseña se actualiza solo cuando se facilita explícitamente; si no se incluye en la petición, el cifrado existente no cambia.

Para borrar una cuenta o un mundo, el bot exige que no haya sesión activa en ninguno de sus mundos. Si hay sesión activa, el borrado se bloquea con un error. La restricción existe porque borrar una cuenta con Chrome abierto dejaría el proceso huérfano sin que el bot sepa que debe cerrarlo.

### Arrancar y parar el bot en un mundo

Desde el dashboard, el operador puede iniciar o detener la sesión del bot en cada mundo por separado. El flujo de login está documentado en detalle en [`funcionalidades/sesion.md`](sesion.md). El resumen de negocio:

- **Arrancar**: el bot abre Chrome con el perfil de esa cuenta y navega a la pantalla de login de Travian, tecleando las credenciales como lo haría un humano. El proceso tarda entre 3 y 10 segundos. Si tiene éxito, el operador es llevado automáticamente al espacio del mundo en el dashboard.
- **Parar**: el bot cierra el proceso Chrome. Es instantáneo y no deja rastro de tráfico en Travian.
- **Entrar** (sin re-login): si el bot ya tiene sesión activa, el operador puede ir directamente al espacio del mundo sin volver a hacer login.

---

## Reglas de negocio clave

| Regla | Descripción |
|-------|-------------|
| Email único | No pueden coexistir dos cuentas con el mismo email |
| Servidor único por cuenta | Un mismo servidor Travian no puede añadirse dos veces a la misma cuenta. Sí puede estar en dos cuentas distintas |
| Contraseña write-only | Nunca se devuelve en ninguna respuesta de API. Solo se envía al crear o actualizar |
| Cifrado en reposo | La contraseña se cifra con Fernet antes de persistir. La clave (`TRAVIAN_BOT_SECRET_KEY`) debe ser estable |
| Borrado bloqueado con sesión activa | No se puede borrar una cuenta ni un mundo mientras el bot tiene una sesión activa allí. El operador debe parar el bot primero |
| Cascada en borrado | Borrar una cuenta elimina también todos sus mundos y aldeas. Borrar un mundo elimina sus aldeas. Esta es una acción irreversible |
| Solo tribus jugables | Nature y Natars son rechazadas en la capa de API |
| Sin autenticación de dashboard | Cualquiera que acceda al servidor del bot puede gestionar cuentas. La app es de uso personal |

---

## El dashboard — vista de negocio

El dashboard React que acompaña a esta feature implementa las pantallas descritas en el diseño:

| Pantalla | Propósito |
|---|---|
| Lista de cuentas (S2) | Ver todas las cuentas de un vistazo; crear cuenta nueva |
| Wizard de alta (S3) | Crear cuenta + primer mundo en 2 pasos guiados |
| Detalle de cuenta (S4) | Ver datos de una cuenta; gestionar sus mundos; arrancar/parar sesiones |
| Editar cuenta (S5) | Modificar email, username o contraseña |
| Añadir mundo (S6) | Añadir un nuevo servidor a una cuenta existente |
| Confirmar borrado cuenta (S7) | Paso de confirmación antes de una acción destructiva |
| Confirmar borrado mundo (S8) | Ídem para un mundo |
| Espacio del mundo (S9) | Pantalla completa del mundo activo; sin sidebar de gestión |

La app opera en **dos modos excluyentes**:

- **Modo Gestión** (pantallas S1–S8): el operador administra cuentas y mundos. Incluye sidebar de navegación.
- **Espacio del mundo** (pantalla S9): el operador trabaja dentro de un mundo concreto con el bot activo. Sin sidebar de gestión; más espacio para el mundo y sus secciones (futuras features).

La transición entre modos es explícita: se produce al arrancar un mundo (S4 → S9) o al parar/volver (S9 → S4).

---

## Lo que esta funcionalidad no hace

- No gestiona sesiones de usuario del dashboard (no hay login para acceder al bot; es de uso personal).
- No detecta automáticamente si Chrome muere durante la sesión (ver [`funcionalidades/sesion.md`](sesion.md) — limitaciones conocidas).
- No notifica en tiempo real al dashboard si el estado de sesión cambia inesperadamente (sin WebSocket en esta versión).
- Las secciones de juego dentro del Espacio del mundo (Recursos, Tropas, Construcción, Aldeas) son placeholders en esta versión: se habilitarán como features independientes.

---

## Divergencias código/spec

**Nota en el diseño de gestion-cuentas-mundos.md (§4b)**: el spec original indicaba que el backend de sesión "no existe aún". En la implementación real el backend de sesión fue construido completamente (ver [`funcionalidades/sesion.md`](sesion.md)). El frontend conecta contra los endpoints reales (`POST/DELETE/GET .../session`). El spec de diseño no fue actualizado para reflejar este estado.

---

🔖 Última revisión: 2026-05-26
