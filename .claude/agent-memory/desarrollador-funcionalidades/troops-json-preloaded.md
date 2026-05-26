---
name: troops-json-preloaded
description: troops.json ya fue rellenado por la prueba manual del scraper; test de fallback "de" asume campos vacíos y falla en rama develop
metadata:
  type: project
---

`core/i18n/catalog/base/troops.json` fue rellenado por el scraper en la prueba manual del usuario (todas las tropas tienen "de", "fr", "ru" etc. con nombres reales). El test `test_troops_fallback_de_idioma_servido_es` en `tests/test_catalog_troops.py` asume que los romanos NO tienen "de" para verificar el fallback a "es", pero ya están rellenos.

**Why:** El test se escribió cuando troops.json solo tenía `""` en los campos; tras ejecutar el scraper en real, el JSON quedó lleno. No es un bug de mi código: preexistía antes de cualquier cambio de bugs del scraper.

**How to apply:** Al ejecutar la suite completa siempre fallará este test en la rama develop actual. No es regresión de mis cambios — confirmado con `git stash` reversible. Avisarlo al usuario si pregunta por ese fallo específico. El fix correcto es actualizar el test para que sea agnóstico del estado de troops.json (p.ej. usando un catálogo temporal en fixture).
