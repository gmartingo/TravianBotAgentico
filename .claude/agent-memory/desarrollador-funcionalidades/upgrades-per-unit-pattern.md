---
name: upgrades-per-unit-pattern
description: Patrón SPA kirilloid para mejoras de herrería — URL por unidad, cabecera 6 td.upg, 13 celdas por fila
metadata:
  type: project
---

Implementado en Fase 2 del scraper kirilloid (2026-05-25).

**Hecho clave:** `#upg_table` de kirilloid es POR UNIDAD, no por tribu.
La URL `troops.php#s=1.45&tribe=T&s_lvl=0&t_lvl=1&u_lvl=0&unit=N` muestra solo la unidad N.
La implementación anterior asumía grupos por tribu (detectaba ordinal via `img.unit.uN`) → 0 filas.

**Patrón SPA obligatorio:** `about:blank` → `get(url&unit=N)` para carga fresca de cada unidad.
Navegar solo el hash no fuerza re-render del SPA.

**Estructura HTML verificada:**
- Cabecera: 6 celdas `td.upg` con `<img class="stats X">` donde X ∈ {att_all, def_i, def_c, eye, def_s, point}
  - Columnas no aplicables: `style="display:none"` en la celda td.upg
- Filas de datos: 13 celdas fijas: [nivel, wood, clay, iron, crop, sum, tiempo H:MM:SS, stats[0-5]]
  - Celda de stat puede tener `style="display:none"` en la fila de datos también (doble verificación)
  - Valor de stat: texto "40.5800" donde `.text` ya concatena el contenido de `<small>`

**Mapeo correcto img.class → stat_name:**
- `att_all` → "attack", `def_i` → "def_infantry", `def_c` → "def_cavalry"
- `eye` → "scouting", `def_s` → "counter_scouting", `point` → "destructive"

**Iconos de mejora:** eye/def_s/point se capturan durante el bucle de unidades (unit_page ya tiene el upg_table correcto). Los compartidos att_all/def_i/def_c NO se duplican (ya existen como stat_attack/stat_def_infantry/stat_def_cavalry).

**Endpoint de upgrades:** `GET /catalog/troops/{tribe}/{ordinal}/upgrades`
- Accept-Language OPCIONAL (respuesta puramente numérica, sin texto localizado)
- Niveles agrupados: {level, cost_*, upgrade_time_s, stats: {stat_name: float}}
- 404 si no hay datos; 400 solo si se envía idioma no soportado

**Why:** Distinción entre "hay tabla" (unit tiene mejoras) y "tabla sin columnas visibles" (unidad sin stats de mejora aplicables). Ambos devuelven lista vacía sin error.

**How to apply:** Al parsear cualquier otra tabla kirilloid que cambie por URL hash+param, usar el patrón about:blank→get(url).
