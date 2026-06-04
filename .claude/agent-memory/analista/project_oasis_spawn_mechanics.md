---
name: project-oasis-spawn-mechanics
description: Spec oasis-spawn-mechanics-stats v2.6: catálogo spawn, inferencia tipo, peor combo, cooldown, retirada avg_regen_per_hour, inferencia (player, village) atacante por blobs (marcador + canonización), agrupación frontend Jugador→Aldea→Oasis
metadata:
  type: project
---

Feature `oasis-spawn-mechanics-stats` — Spec guardado en `docs/specs/oasis-spawn-mechanics-stats.md`.

**Por qué:** `avg_regen_per_hour` mezcla ráfaga de spawn con cooldown y no sirve para decisiones tácticas reales. La mecánica real es: spawn en orden fijo con timers fijos → cooldown → re-disparo.

## Gaps verificados en el código (2026-06-02)

- `_parse_utc_offset()` ya existe en el adaptador (línea 208). El spec anterior de reaparicion-animales-oasis.md lo listaba como "a crear" — era incorrecto; no recrearlo.
- `get_all_oasis_regen_comparison()` existe en el adaptador (línea 1115) y en el router (línea 532) pero **NO está declarado en `core/ports/attack_report_port.py`** — gap TR-06 que debe regularizarse en paso 0 de cualquier implementación que toque el port.
- EP-10 está implementado y funcional; solo le falta la declaración en el port.

## Catálogo de spawn (fuente canónica)

`core/game_data/oasis_spawn_catalog.py` — **NO EXISTE**, hay que crearlo.

```
SPAWN_TIMER_S = {1: 300, 2: 360, 3: 420, 4: 480, 5: 540, 6: 600, 7: 660, 8: 720, 9: 780, 10: 840}
OASIS_TYPE_SETS = {
    "hierro":  {1, 2, 4},
    "arcilla": {1, 2, 5},
    "madera":  {5, 6, 7},
    "cereal":  {1, 2, 3, 4, 5, 6, 7, 8, 9, 10},
}
```

## Datos de defensa animal

`seeds/game_data/troop_stats.json` — ya existe; filtrar `tribe == "nature"`. Campos: `ordinal`, `def_infantry`, `def_cavalry`.

## Localizaciones

`core/i18n/catalog/base/troops.json` — estructura `{NATURE_1: {es: "Rata", en: "Rat", ...}, ...}`. Los 25 idiomas están. La API NO devuelve nombres localizados — el frontend los resuelve con `NATURE_{ordinal}`.

## Call-sites de avg_regen_per_hour a migrar

- Adapter: líneas 198, 1334, 1341
- Frontend: RegenRatesSection.jsx:16/190, GlobalOasisStatsPanel.jsx:352, OasisStatsPanel.jsx:205
- Tests: test_attack_reports_api.py:1031/1044/1047, test_global_oasis_stats_api.py:335-368, test_oasis_comparison_api.py (múltiples), unit/test_attack_report_parser.py:601-680
- EP-09 conserva avg_regen_per_hour en v1 (deuda técnica TR-03)

## Heurística de inferencia de tipo

Score = Jaccard(animales_observados, set_del_tipo) = |∩| / |∪|. Empate → menor cardinal → alfabético. Confianza: <3 bursts con present>0 = "low", >=3 = "medium".
(El solapamiento bruto fue descartado porque cereal={1..10} ganaba siempre; Jaccard penaliza el set universal.)

## Estado cooldown/respawn

- "respawning": elapsed_s <= max(SPAWN_TIMER_S para animales del set)
- "cooldown": elapsed_s > 4*3600 (4h, heurístico)
- "unknown": zona intermedia o inferred_type=null

## Endpoint nuevo

`GET /attack-reports/stats/oasis/spawn-composition?timer_min=N` (N ∈ {6,7,10,15}). Sin Accept-Language. Declarar antes de EP-04 en el router.

## Inferencia de (player, village) atacante por oasis (v2.6 — VIGENTE)

`attack_reports.origin_village_name` contiene blobs como `"[Storm] GonnaDie from village 05"`.
El campo forma parte de la clave UNIQUE: NO tocar el parser ni el campo persistido.

**Contrato EP-SPAWN v2.6**: campo `attackers: [{player, village}]` (DISTINCT, player A-Z, village A-Z).
Sustituye a `origin_villages: string[]` de v2.5. Breaking change controlado (sin consumidores externos).

**Algoritmo por blob** (`_extract_player_village_from_blob`):
1. **A. Quitar tag**: si empieza con `[...]` → resto = texto desde `]` en adelante, trim.
2. **B. Buscar marcador** en `_FROM_VILLAGE_MARKERS` (case-insensitive):
   - Encontrado → player = texto_antes_marcador.strip(), village_raw = texto_despues.strip().
   - No encontrado → player = "Desconocido", village_raw = None.
3. **C. Canonizar village**: buscar `vname in village_raw` (o en `resto` si village_raw=None).
   - Gana el más largo; empate → múltiples pares (player, vname_i).
   - Sin match → village = village_raw o "Desconocido".

Unión DISTINCT de pares de TODOS los blobs del oasis → `_infer_attackers()`.
Nunca vacío: último recurso `[{"player":"Desconocido","village":"Desconocido"}]`.

**Clave de agrupación frontend: (player, village)** — dos jugadores con village mismo nombre = secciones distintas.
Frontend: Jugador (nivel 1, colapsable, A-Z, Desconocido al final) → Aldea (nivel 2) → Oasis filas Media/Peor.

Dos queries antes del bucle (anti N+1): `SELECT name FROM villages` + blobs_sql (GROUP_CONCAT).
El JOIN farm_slots fue ELIMINADO en v2.5 y permanece eliminado en v2.6.

**Why:** farm_list responde a "configurado", no a "atacó de verdad". La dimensión jugador permite al usuario
separar visualmente sus cuentas de reportes ajenos accidentalmente importados.
**How to apply:** para cualquier agrupación futura por atacante, usar `_extract_player_village_from_blob`
+ `_infer_attackers`. No re-parsear `origin_village_name` (UNIQUE key).

Blobs reales del usuario (servidor inglés, villages={00,01,02,03}):
- `"[Storm] GonnaDie from village 05"` → (GonnaDie, "05")
- `"[Storm] GonnaDie from village 02"` → (GonnaDie, "02") — canonización C-a
- `"[Storm] CrazyMouse from village 05 Caesar On Leave"` → (CrazyMouse, "05 Caesar On Leave")
- `"[Storm] CrazyMouse from village 01 Rome But Broke"` → (CrazyMouse, "01") — canonización C-a
- `"[Storm] SharpHorseman from village SharpHorseman [00]"` → (SharpHorseman, "00") — canonización C-a

Jugadores reales en BD: GonnaDie (1193 reportes), CrazyMouse (3), SharpHorseman (1).
