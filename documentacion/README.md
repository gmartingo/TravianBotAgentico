# Documentación técnica — TravianBot

Índice maestro de toda la documentación del proyecto. Empieza aquí.

---

## Organización de carpetas

| Carpeta | Contenido |
|---|---|
| `arquitectura/` | Arquitectura hexagonal, patrones de diseño, decisiones técnicas |
| `backend/` | Módulos de `core/` y `adapters/` — documentación funcional de código |
| `backend/referencia-funciones/` | Referencia rápida de funciones y métodos por módulo |
| `api/` | Referencia centralizada de endpoints REST |
| `funcionalidades/` | Documentación de negocio por feature (para stakeholders y PO) |
| `procesos/` | Guías de proceso y operativa del equipo |

---

## Documentación de código (backend)

| Documento | Módulo/Feature |
|---|---|
| [`backend/i18n.md`](backend/i18n.md) | Internacionalización: `core/i18n/`, `core/ports/translation_port.py`, `adapters/translations/`, `adapters/api/main.py` (exception handler, lifespan, middlewares) |
| [`backend/sesion.md`](backend/sesion.md) | Sesión del bot: `SessionRegistry`, `LoginUseCase`, `LogoutUseCase`, endpoints de sesión, cableado en `lifespan`, seguridad de credenciales |

### Referencia de funciones

| Documento | Contenido |
|---|---|
| [`backend/referencia-funciones/translation-port.md`](backend/referencia-funciones/translation-port.md) | Métodos del puerto `TranslationPort` y su implementación `JsonTranslationAdapter` |
| [`backend/referencia-funciones/api-i18n-helpers.md`](backend/referencia-funciones/api-i18n-helpers.md) | Helpers del exception handler y dependencias de la API (`_mask_frame_locals`, `_build_trace`, `_extract_lang`, `get_language`, `get_translation_port`) |
| [`backend/referencia-funciones/sesion.md`](backend/referencia-funciones/sesion.md) | Referencia rápida de `SessionRegistry`, `LoginUseCase`, `LogoutUseCase`, `get_account_password_cipher`, `get_world_runtime_port` y `LoginFailedError` |

---

## Documentación de código (frontend)

| Documento | Módulo/Feature |
|---|---|
| [`frontend/dashboard.md`](frontend/dashboard.md) | Dashboard React de gestión de cuentas/mundos: stack, rutas, i18n 25 idiomas + RTL, cliente HTTP, pantallas S2–S9, tokens de diseño, divergencias código/diseño |

---

## Documentación de negocio (funcionalidades)

| Documento | Feature |
|---|---|
| [`funcionalidades/i18n-backend.md`](funcionalidades/i18n-backend.md) | Internacionalización del backend: edificios, tropas y mensajes de error |
| [`funcionalidades/cuentas-mundos.md`](funcionalidades/cuentas-mundos.md) | Registro y gestión de cuentas y mundos + sesión del bot de extremo a extremo (negocio: reglas, flujos, restricciones) |
| [`funcionalidades/sesion.md`](funcionalidades/sesion.md) | Sesión del bot: login/logout/estado, seguridad de credenciales, nota de operación sobre `TRAVIAN_BOT_SECRET_KEY` |

---

## Referencia de API

| Documento | Contenido |
|---|---|
| [`api/catalogo.md`](api/catalogo.md) | `GET /catalog/buildings`, `GET /catalog/troops/{tribe}`, exception handler global con traducciones |
| [`api/cuentas-mundos.md`](api/cuentas-mundos.md) | `POST/GET/PUT/DELETE /accounts`, `POST/GET/DELETE /accounts/{id}/worlds` — CRUD de cuentas y mundos |
| [`api/sesion.md`](api/sesion.md) | `POST`, `DELETE`, `GET /accounts/{id}/worlds/{id}/session` — login, logout y estado de sesión del bot |

---

## Procesos

| Documento | Contenido |
|---|---|
| [`procesos/operativa-por-fases.md`](procesos/operativa-por-fases.md) | Flujo de 5 fases para solicitudes |

---

## Convenciones

- Cada documento lleva al pie una marca de agua `🔖` con la fecha de su última revisión.
- Al crear o modificar una función: actualizar su entrada en `referencia-funciones/`.
- Al añadir módulo, feature o endpoint: enlazarlo desde este README.
- Al detectar divergencia código/spec: documentarla en el documento afectado bajo el encabezado **Divergencias código/spec**.

🔖 Última revisión: 2026-05-26 (añadidos: api/cuentas-mundos.md, funcionalidades/cuentas-mundos.md, frontend/dashboard.md)
