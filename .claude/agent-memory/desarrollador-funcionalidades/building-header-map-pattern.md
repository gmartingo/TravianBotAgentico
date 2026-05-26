---
name: building-header-map-pattern
description: kirilloid build.php — cabecera <tr class="rbg"> usa <td> NO <th>; mapeo por clase CSS img; g10/g11 se omiten
metadata:
  type: project
---

**CRÍTICO**: la fila de cabecera `<thead><tr class="rbg">` de kirilloid usa celdas `<td>`, NO `<th>`.
Siempre usar `query_selector_all("td")` en el header_row, nunca `"th"`.

La tabla `#data.wire` de kirilloid/build.php mapea columnas así:
- `res r1` → cost_wood, `res r2` → cost_clay, `res r3` → cost_iron, `res r4` → cost_crop
- `res r6` → cost_sum, `res r5` → upkeep, `res r7` → build_time_s
- `building g10` → **OMITIR** (cap almacén), `building g11` → **OMITIR** (cap granero)
- Sin img, texto "PC" → culture_points
- Última columna sin img con texto → effect_label / effect_value

Kirilloid puede emitir el prefijo `icon--scalable` antes de la clase; normalizar quitándolo.

Columna 0 siempre es el nivel.

**`_make_icon_id` — firma actual**: `_make_icon_id(gid, name=None, catalog_path=None)`.
El campo `alias` del buildings.json estaba desalineado con los gids reales. Siempre pasar
`name` con el nombre inglés recién scrapeado (alineado por gid). El JSON solo se usa como fallback.

**How to apply:** BUILDING_HEADER_MAP en kirilloid_buildings_scraper.py. Al añadir columnas nuevas, actualizar el mapa allí. En los mocks de test, la cabecera debe devolver `td`, no `th`.
