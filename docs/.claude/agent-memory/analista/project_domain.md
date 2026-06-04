---
name: project-domain
description: Dominio del proyecto Travian Bot — actores, restricciones habituales y convenciones de specs
metadata:
  type: project
---

Bot de Travian escrito en Python 3.14 + zendriver (CDP directo, sin ChromeDriver).
Arquitectura hexagonal: `core/` (entidades, puertos, casos de uso) + `adapters/` (browser, DB SQLite, API FastAPI).
Dashboard React + Vite + Tailwind v4.

**Actor único:** el usuario del dashboard (sin auth adicional en los endpoints de stats).

**Convenciones de specs ya establecidas:**
- `Accept-Language` obligatorio (dependencia `get_language`) en endpoints que devuelven texto localizado en el backend.
- `SUPPORTED_LANGUAGES` = 25 códigos en `core/i18n/languages.py`.
- Estado vacío → siempre `200` con lista vacía, nunca `404`.
- Error semántico (valor fuera de whitelist) → `400`. Error de tipo → `422`.
- Nombres de animal localizados vía `translation_port.get_troop_names_by_tribe(Tribe.nature, lang)`.
- `icon_url = /static/icons/nature_{ordinal}.png` (patrón de EP-06).
- Moda en Python con `Counter` (SQLite no tiene `MODE()`); empates como lista ASC.
- UI bloqueada hasta spec de `disenador-producto` + mockup editable aprobado.

**Datos de animales:**
- Tablas `attack_reports` y `attack_report_animals` ya existen.
- Animales de tipo NATURE: ordinales 1-10; `Tribe.nature` en `core/entities/tribe.py`.
- `present = NULL` cuando el reporte es derrota (sin info de cuántos animales había).
- Gaps temporales calculados con `LAG()` + `PARTITION BY coord_x_dest, coord_y_dest ORDER BY attacked_at`.

**Velocidad de servidor:** no ajusta tiempos empíricos. El endpoint trabaja con tiempo real siempre.

**Cadencias de farmeo reales del juego:** {6,7,10,15,30,60,120,180,240,300} minutos.
