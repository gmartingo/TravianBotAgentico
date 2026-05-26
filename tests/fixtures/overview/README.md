# Fixtures — páginas de estadísticas/overview de Travian

HTML real capturado manualmente por el usuario desde su servidor
`https://ts20.x2.america.travian.com/` (T4.x, tribu **Galos** → `tribe3`).

Son las páginas **agregadas** (`/village/statistics`): cada pestaña muestra TODAS las
aldeas a la vez (una fila por aldea + fila `tr.sum` de totales). NO son páginas por aldea.

## Mapa de pestañas → URL → fixture

| Bloque | Pestaña | URL (relativa al server) | Fixture | Estado |
|---|---|---|---|---|
| overview | Overview | `/village/statistics/overview` | `overview.html` | ✅ |
| resources | Resources | `/village/statistics/resources` | `resources.html` | ✅ |
| resources | Production | `/village/statistics/resources/production` | `resources_production.html` | ✅ |
| resources | Capacity | `/village/statistics/resources/capacity` | `resources_capacity.html` | ✅ |
| culture-points | Culture points | `/village/statistics/culturepoints` | `culturepoints.html` | ✅ |
| troops | Own troops | `/village/statistics/troops/own` (= `/troops`) | `troops_own.html` | ✅ |
| troops | Troops in villages | `/village/statistics/troops/support` | `troops_support.html` | ✅ |
| troops | Smithy | `/village/statistics/troops/smithy` | `troops_smithy.html` | ✅ |
| troops | Hospital | `/village/statistics/troops/hospital` | `troops_hospital.html` | ✅ |
| troops | Training | `/village/statistics/troops/training` | `troops_training.html` | ✅ |

Los 10 fixtures están completos.

## Navegación de pestañas (para el LiveOverviewAdapter)

Tabs superiores en `.contentNavi.subNavi a.tabItem[href]`; sub-tabs (resources/troops)
en `.contentNavi.tabNavi a.tabItem[href]`. La pestaña activa lleva la clase `active`.
Cada `href` es una URL real navegable (no requiere disparar el evento JS `tabClicked`).

## Mapa de `gid` (building id) observado

| gid | Edificio | Aparece en |
|---|---|---|
| 13 | Herrería (Smithy) | smithy |
| 17 | Mercado (mercaderes) | overview, resources |
| 19 | Cuartel (Barracks) | overview, troops, training |
| 20 | Establo (Stable) | overview, troops, training |
| 21 | Taller (Workshop) | training |
| 24 | Ayuntamiento (celebraciones/CP) | culturepoints |
| 46 | Hospital | hospital, training |

Tribu vía `i.tribeN_medium` (hospital) y `i.building_small.tribeN.typeNN` (training). `tribe3` = Galos.

## Selectores clave (estructurales, idioma-independientes)

- **Aldea**: `td.vil.fc > a[href*="newdid=N"]` → `newdid` = `game_id`; texto = nombre. En tablas de tropas: `td.villageName a` o `thead th a[href*="newdid=N"]`.
- **Tipo de tropa**: SIEMPRE por la clase `img.unit.uNN` (u21-u30 propias galos, u31-u40 naturaleza, `uhero`). NUNCA por el `alt`.
- **overview** `#overview`: `td.att img.def1` (refuerzos) / `img.att2` (ataques propios), nº en prefijo del `alt` ("618x…"); `td.bui img.bau` (edificios en obra); `td.tro img.unit.uNN`; `td.tra` (mercaderes "libres/totales").
- **resources** `#ressources`: `td.lum/clay/iron/crop` (almacenado); `td.tra a` (mercaderes); `tr.sum`.
- **production** `#production`: `td.lum/clay/iron/crop` (producción/h bruta); `tr.sum td.vil span.total` (suma global).
- **capacity** `#capacity`: `td.max123` (almacén) / `td.max4` (granero).
- **culturepoints** `#culture_points`: `td.cps` (CP/día); `td.cel a span.timer[data-value]` (segundos restantes de fiesta); `td.slo` (slots "usados/total").
- **troops/own** `#troops`: cabecera define columnas por `img.unit.uNN`; celdas = cantidad (clase `none` = 0); `tr.sum` totales.
- **troops/support** `.troops_wrapper > table.vil_troops`: `tbody.troops` (tropas presentes, naturaleza+propias+hero); `tbody.upkeep` → `.consumption span` (cereal/h) + `.strengthWrapper` (off / def inf / def cav).
- **troops/smithy** `table.under_progress`: col `th.inProgress` → `img.unit.uNN` = tropa investigándose, `span.dot` = nada; resto columnas = nivel de mejora por tipo (`.none` con `0` o `-` = no investigable).
- **troops/hospital** `table.under_progress`: `th.villageName i.tribeN_medium` = icono de tribu; `td.inProgress` `span.dot`=curando / `span.none`=sin hospital; resto = heridos por tipo (u21-u26).
- **troops/training** `table.under_progress`: columnas = edificios (`i.building_small.tribeN.typeNN`: type19 cuartel, type20 establo, type21 taller, type46 hospital); por celda `a[gid=N] span.duration` (tiempo restante H:MM:SS) / `span.dot` (edificio sin cola) / `span.none` `-` (sin edificio).

## ⚠️ Gotcha de parseo — caracteres bidi invisibles

Los números vienen envueltos en caracteres de control Unicode **U+202D** y **U+202C**, más
separadores de miles (`.` o `,`). Ej: `‭8,786‬`, `‭‭14‬/‭14‬‬`.
La utilidad `parse_int` debe **eliminar estos caracteres de control** antes de convertir.
Los tiempos (`span.duration`, `span.timer`) usan `H:MM:SS`; las fiestas además exponen
`data-value` con los **segundos restantes** ya calculados (preferible al texto).
