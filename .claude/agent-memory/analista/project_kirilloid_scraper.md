---
name: project-kirilloid-scraper
description: Decisiones cerradas del diseño del scraper kirilloid para tropas — puertos, persistencia, iconos, API
metadata:
  type: project
---

Spec escrito en `docs/specs/kirilloid-tropas-scraper.md`.
Estado: `ready-for-impl`. APIs pendientes de validación formal por desarrollador-apis
(el subagente no estaba disponible al cerrar; el hilo principal debe pasar el contrato).

**Decisiones cerradas (no reabrir sin justificación):**

- Scraper = adaptador en `adapters/scraper/kirilloid_scraper.py`. Reutiliza `create_browser()` y
  `human_delay()` de `adapters/browser/driver.py`. Perfil propio: `profiles/scraper_kirilloid`.
- Puerto nuevo `GameDataPort` en `core/ports/game_data_port.py`. NO extender `TranslationPort`
  (TranslationPort es solo texto; SRP hexagonal).
- Persistencia híbrida: nombres → `troops.json` (merge no-destructivo solo en `base/`);
  stats numéricos + mejoras → SQLite (tablas nuevas `troop_stats`, `troop_upgrades`);
  iconos → disco `assets/icons/`, metadatos → SQLite (`icon_metadata`).
- `server_version` es dimensión en PK de troop_stats. PK = (server_version, tribe, ordinal).
- Valores "—" de kirilloid = NULL en BD, None en Python. Nunca 0.
- Iconos: screenshot DOM del elemento `img.unit.uN` + Pillow flood-fill (no rembg).
  PNG con transparencia. Fallback: screenshot de td padre si el img tiene 0x0.
- Metadatos de iconos en SQLite (queries futuras) no en manifest JSON.
- StaticFiles mount en `/static/icons/` para servir binarios (no endpoint FileResponse).
- Endpoints bajo `/catalog/` para heredar Cache-Control middleware.
- Nuevas tribus al Enum: NATURE, NATARS, SPARTANS, VIKINGS (valores minúsculas, retrocompatible).
- Script CLI `scripts/load_kirilloid.py` — un solo tiro, sin cron, sin endpoint admin.
- Fallo ruidoso: errores parciales se loguean, datos buenos se guardan, el script continúa.

**Columnas de stats mapeadas por clase CSS (STAT_COLUMN_MAP):**
off→attack, def_i→def_infantry, def_c→def_cavalry, speed→speed, cap→carry,
res1→cost_wood, res2→cost_clay, res3→cost_iron, res4→cost_crop, res_sum→cost_sum,
cu→upkeep, time→train_time_s.

**Tiempo de entrenamiento:** formato H:MM:SS → int segundos. Función _parse_time().

**Selector de idioma en kirilloid:** `#langbar img[alt='{lang_code}']` (click en bandera).
Hay ~25 idiomas disponibles. Los datos de todos se guardan en troops.json pero SUPPORTED_LANGUAGES
de la API sigue con los 5 actuales (no ampliar).

**Estructura icon_id (clave semántica):**
- Tropa: `{tribe_value}_{ordinal}` (p.ej. `romans_1`, `nature_3`)
- Stat: `stat_{nombre}` (p.ej. `stat_attack`, `stat_wood`)
- Mejora: `upgrade_{stat}` (p.ej. `upgrade_spy`, `upgrade_destructive`)

**API validada (pendiente luz verde formal):**
- `GET /catalog/troops/{tribe}/stats` — stats numéricos, CREAR (distinto de endpoint de nombres)
- `GET /catalog/icons` — metadatos de iconos, CREAR
- `/static/icons/` — StaticFiles mount, sin Accept-Language

**Why:** Conocimiento institucional para futuros specs que amplíen datos de juego o
añadan scraping desde kirilloid.

**How to apply:** Al diseñar cualquier feature de "datos de juego" (niveles, costes, stats),
reutilizar GameDataPort y los adaptadores de esta feature. Al añadir nuevos datos de kirilloid,
extender las tablas SQLite con la dimensión server_version. Los iconos del juego van siempre
a assets/icons/ con clave semántica en SQLite.

---

## Scraper de EDIFICIOS (spec kirilloid-edificios-scraper.md — 2026-05-25)

Spec escrito en `docs/specs/kirilloid-edificios-scraper.md`. Estado: `ready-for-impl`.

**Decisiones cerradas para edificios:**

- Tablas nuevas: `building_stats` (PK: server_version, gid, level) y
  `building_catalog` (PK: server_version, gid — categoría, descripción, icon_id).
  Categoría normalizada fuera de building_stats por ser propiedad del edificio, no del nivel.
- Columnas omitidas: cap almacén (g10) y cap granero (g11) — secundarias/derivadas.
- `effect_label` (nombre del efecto específico) capturado solo en idioma 'es' — trade-off coste/valor.
- Categoría por POSICIÓN de columna (col 0→resources, 1→infrastructure, 2→military),
  no por texto del <h3> (cambia con idioma). Decisión pendiente de validación del usuario.
- Política merge buildings.json: kirilloid SOBRESCRIBE (mismo patrón que tropas, RN-04).
- `icon_type = "building"` en icon_metadata — nueva categoría de icono.
- Selector de icono: `img.building.g{gid}` en página de detalle.
- `_remove_background` extraída a `adapters/scraper/utils.py` para reutilización entre scrapers.
- `GameDataPort` extendido (no puerto nuevo): mismo adaptador SQLite, misma fuente de datos.
- server_version="1.45" para coherencia con tropas (PENDIENTE validación usuario —
  el usuario mencionó URL con s=2.46).

**Patrón SPA kirilloid para build.php:**
- Índice: about:blank → get(#mb=1&s=1.45) → esperar #build_list.
- Detalle por gid: about:blank → get(#b={gid}&mb=1&s=1.45) → esperar #data.wire.
- Nombres por idioma en ÍNDICE: click bandera + asyncio.sleep(0.15) + releer items.
  (A diferencia de tropas donde el re-render funcional fue click+sleep en loop.)

**API:**
- `GET /catalog/buildings/{gid}/stats` — CREAR (análogo a /catalog/troops/{tribe}/stats).
- `GET /catalog/buildings` — MODIFICAR para añadir campos opcionales a BuildingItem.
- Gobernanza ?lang= > Accept-Language > todos (mismo patrón que tropas ya aprobado).

**Decisiones pendientes de validación del usuario (al volver):**
#1 server_version="1.45", #2 categoría por posición, #3 omitir cap almacén/granero,
#4 no invocar gate APIs, #5 política sobrescribe, #6 effect_label solo en 'es',
#7 no re-capturar iconos r1..r7.
