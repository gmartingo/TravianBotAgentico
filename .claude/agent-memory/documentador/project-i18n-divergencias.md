---
name: project-i18n-divergencias
description: Divergencias código/spec conocidas de la feature i18n-backend y su estado
metadata:
  type: project
---

Divergencias detectadas y documentadas durante la documentación de i18n-backend (2026-05-24):

**IMPL-01 — lifespan vs @app.on_event**: El spec menciona `@app.on_event("startup")` como referencia. El código usa el `lifespan` context manager (correcto, `on_event` está deprecado en FastAPI >= 0.93). No es defecto; documentado para claridad.

**SPEC-01 — Catálogo de edificios completo en de/fr/ru (mejora no planificada)**: El spec declaraba que `de`, `fr`, `ru` estarían vacíos/parciales en la iteración 1 para tropas Y edificios. El código real tiene los 40 edificios con traducción completa en los 5 idiomas. Las tropas sí quedaron con solo `es`/`en` como planificado. Estado: registrado como mejora no planificada, sin acción requerida.

**SPEC-02 — Tropas solo es/en (alineado)**: Confirmado. Los 50 items de tropas tienen `"de": ""`, `"fr": ""`, `"ru": ""`. Coherente con el spec.

**IMPL-02 — Accept-Language declarado opcional para obtener 400 (no 422)**: El header se declara `Header(default=None)` en `get_language` para que FastAPI no genere 422 automático cuando falta. El código lanza 400 manualmente. Esto es exactamente lo que el spec exige. El mecanismo es contra-intuitivo pero correcto. Documentado en el código y en la referencia de API.

**IMPL-03 — 404 de tribu sin tropas usa detail en español fijo**: En `get_troops_catalog`, el 404 por tribu sin tropas se lanza con `HTTPException` directa y mensaje en español fijo, no pasa por `get_message`. El spec implica localización. Registrado como divergencia menor; candidato a corrección si el multilenguaje de este caso llega a ser relevante.

**How to apply**: al actualizar la feature i18n o al documentar nuevos endpoints del catálogo, verificar si alguna de estas divergencias fue corregida y actualizar los documentos afectados en `documentacion/backend/i18n.md` y `documentacion/api/catalogo.md`. [[project-doc-structure]]
