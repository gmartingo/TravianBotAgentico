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

### Referencia de funciones

| Documento | Contenido |
|---|---|
| [`backend/referencia-funciones/translation-port.md`](backend/referencia-funciones/translation-port.md) | Métodos del puerto `TranslationPort` y su implementación `JsonTranslationAdapter` |
| [`backend/referencia-funciones/api-i18n-helpers.md`](backend/referencia-funciones/api-i18n-helpers.md) | Helpers del exception handler y dependencias de la API (`_mask_frame_locals`, `_build_trace`, `_extract_lang`, `get_language`, `get_translation_port`) |

---

## Documentación de negocio (funcionalidades)

| Documento | Feature |
|---|---|
| [`funcionalidades/i18n-backend.md`](funcionalidades/i18n-backend.md) | Internacionalización del backend: edificios, tropas y mensajes de error |

---

## Referencia de API

| Documento | Contenido |
|---|---|
| [`api/catalogo.md`](api/catalogo.md) | `GET /catalog/buildings`, `GET /catalog/troops/{tribe}`, exception handler global con traducciones |

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

🔖 Última revisión: 2026-05-24
