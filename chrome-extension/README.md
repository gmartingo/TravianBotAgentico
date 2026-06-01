# TravianBot — Extensión Chrome de Captura de Reportes

Extensión Chrome Manifest V3 que permite capturar reportes de ataques a oasis de Travian
con un solo clic y enviarlos directamente al backend de TravianBot.

---

## AVISO DE ANTI-DETECCION — LEER ANTES DE INSTALAR

**Esta extension es EXCLUSIVAMENTE para uso manual en el Chrome personal del usuario.**

**NUNCA instales esta extension en los perfiles del bot (carpeta `profiles/`).**

El bot de Travian usa perfiles de Chrome gestionados en `profiles/`. Instalar cualquier
extension en esos perfiles alteria su fingerprint de navegador y comprometeria la
indetectabilidad del bot ante los sistemas anti-bot de Travian. La regla es absoluta y
no negociable: el Chrome del bot debe permanecer limpio de extensiones.

---

## Como funciona

1. Navegas a la pagina de detalle de un reporte en Travian (cualquier dominio .com, .es, .de, etc.)
2. La extension detecta automaticamente que es una pagina de reporte e inyecta un boton flotante
   "Guardar reporte" en la esquina inferior derecha
3. Haces clic → la extension extrae el texto del reporte del DOM → lo envia a `POST /attack-reports`
   del backend local
4. Recibes feedback inmediato mediante un toast en la pagina y un badge en el icono de la extension

No hay paso de confirmacion ni previsualizacion. Si el texto no es un reporte valido, el backend
responde 422 y la extension muestra un mensaje de error.

---

## Instalacion (modo desarrollador — sin empaquetar)

Esta extension NO esta en la Chrome Web Store. Se instala como extension sin empaquetar:

1. Abre Chrome y navega a `chrome://extensions`
2. Activa el **Modo de desarrollador** (toggle en la esquina superior derecha)
3. Haz clic en **Cargar descomprimida** (o "Load unpacked")
4. Selecciona la carpeta `chrome-extension/` dentro del repositorio de TravianBot
5. La extension aparece en la lista y el icono aparece en la barra de herramientas de Chrome

---

## Configuracion de la URL del backend

Por defecto la extension apunta a `http://localhost:8000` (backend corriendo en la misma maquina).

Si el backend corre en la Raspberry Pi (red local), cambia la URL:

1. Haz clic derecho en el icono de la extension → **Opciones**
   (o desde `chrome://extensions` → Detalles → Opciones de extension)
2. Escribe la URL del backend, por ejemplo: `http://192.168.1.42:8000`
3. Haz clic en **Guardar**

La URL se sincroniza en todos los Chrome del usuario (via `chrome.storage.sync`).

---

## Feedback visual

| Situacion | Toast | Badge del icono |
|---|---|---|
| Reporte guardado correctamente | Verde "Reporte guardado (ID: N)" | Verde "OK" |
| Reporte ya existia en BD | Amarillo "Este reporte ya estaba guardado" | Amarillo "DUP" |
| Texto no es un reporte valido | Rojo "Texto no reconocido como reporte valido" | Rojo "ERR" |
| Backend apagado / sin red | Rojo "No se pudo contactar con el backend" | Rojo "OFF" |
| URL del backend no configurada | Rojo "URL del backend no configurada" | Rojo "CFG" |

---

## Arquitectura tecnica

La extension sigue el modelo MV3 de Chrome:

- **content-script.js**: se inyecta en cada pagina de Travian. Detecta la URL,
  inyecta el boton y el toast, extrae el texto del DOM. NO hace fetch directamente.

- **service-worker.js**: recibe el texto via `chrome.runtime.sendMessage`, hace el
  `POST /attack-reports` al backend (sin bloqueo CORS gracias a `host_permissions`),
  actualiza el badge del icono y devuelve el resultado al content script.

- **options.html / options.js**: pagina de configuracion de la URL del backend.

**Por que el fetch sale del service worker y no del content script:**
El content script corre bajo el contexto de la pagina de Travian. Si hiciera un fetch
a `localhost:8000`, Chrome aplicaria las restricciones CORS del dominio Travian.
El service worker tiene `host_permissions` globales y el navegador no aplica CORS en
ese contexto, por lo que el backend no necesita ningun cambio de configuracion.

---

## Verificacion del selector del contenedor de reportes

El spec indica que el contenedor especifico del reporte en Travian NO esta confirmado
para todos los servidores. La extension implementa la siguiente estrategia defensiva:

1. Intenta `#reportContent` (candidato documentado en el spec)
2. Intenta `#report`, `.report-body`, `.reportContainer`
3. Fallback a `document.body.innerText` si ninguno existe

Si el texto capturado no corresponde a un reporte de ataque a oasis, el backend
responde 422 y la extension lo indica con toast rojo. En ese caso, inspecciona el DOM
del reporte con DevTools para identificar el selector correcto y actualiza
`content-script.js` en la funcion `extractReportText()`.

---

## Soporte de dominios Travian

La extension funciona en todos los dominios Travian declarados en `manifest.json`:

`.com` `.es` `.de` `.fr` `.it` `.ru` `.net` `.pl` `.com.br` `.pt` `.nl`
`.tr` `.ro` `.cz` `.sk` `.hu` `.ae` `.us` `.cn`

---

## Actualizacion de la extension

Al modificar cualquier fichero de la extension, ve a `chrome://extensions` y haz clic
en el icono de recarga (circulo con flecha) de la extension para que Chrome cargue
los cambios.
