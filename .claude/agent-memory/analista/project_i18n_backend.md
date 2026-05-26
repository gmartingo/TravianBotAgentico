---
name: project-i18n-backend
description: Decisiones cerradas del diseño de i18n del backend — catálogo, puerto, excepciones, endpoints
metadata:
  type: project
---

Feature i18n-backend spec escrito en `docs/specs/i18n-backend.md`.
Estado actual: `ready-for-impl`, `apis_validadas_por_desarrollador_apis: false` (requiere
revalidación por ajuste de schema post-validación inicial).

Decisiones cerradas (no reabrir sin justificación):
- Catálogo: JSON versionado en git en `core/i18n/catalog/base/` y `override/`. Override gana entrada por entrada.
- Puerto: `TranslationPort` en `core/ports/translation_port.py`. Adaptador: `JsonTranslationAdapter` en `adapters/translations/`.
- Idiomas: `SUPPORTED_LANGUAGES` y `DEFAULT_LANGUAGE` viven en `core/i18n/languages.py`. `adapters/api/dependencies.py` importa de ahí.
- Excepciones: se añaden `error_code` (clase) y `params` (instancia) de forma aditiva sin romper `str(err)` ni los tests existentes.
- 422 para tribu inválida en path (FastAPI automático), 404 para ordinal inexistente.
- Fallback granular a 'es' por entrada (no por idioma completo). Nunca error por traducción faltante de contenido.
- La capa API traduce los errores (exception handler global en app). Los use cases del core no reciben `lang`.
- `app.state.translation_port` como singleton inicializado en startup.

Ajuste 1 (2026-05-24): schema de respuesta de catálogo actualizado. Los items llevan el
campo `language: {lang_servido: nombre}` en vez del campo plano `name`. El wrapper ya no
lleva `lang`. El `lang_servido` puede diferir del idioma pedido cuando hay fallback granular,
lo que hace visible al cliente qué items aún no tienen traducción en su idioma.
El puerto `get_all_buildings` y `get_troop_names_by_tribe` devuelven `lang_servido` por item.

Ajuste 2 (2026-05-24): capa de datos de juego (niveles, costes, tiempos, stats de tropas)
aplazada a feature futura. Fuente prevista: scraper de kirilloid.ru + import del otro bot del usuario.
Los DTOs son BaseModel abiertos (sin `extra: forbid`) para extensión futura aditiva.
El scraper de kirilloid NO debe reutilizar el perfil/sesión de Chrome del bot; gate de guardian pendiente.

**Why:** Hexagonal estricto + simplicidad operativa (sin migraciones de BD para datos estáticos).

**How to apply:** Antes de diseñar cualquier feature que añada contenido nuevo de dominio de Travian,
proponer añadirlo al catálogo JSON existente, no crear otro mecanismo de traducción.
Reutilizar `TranslationPort` y `JsonTranslationAdapter`. Al diseñar endpoints de catálogo,
el campo `language` con clave=idioma_servido es el patrón establecido para esta API.

Pendiente: el agente `desarrollador-apis` debe revalidar el contrato actualizado de
`GET /catalog/buildings` y `GET /catalog/troops/{tribe}` (sección 8 del spec) antes de
volver a `apis_validadas_por_desarrollador_apis: true`.
