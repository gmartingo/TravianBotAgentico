---
name: oasis-origin-village-fix
description: Arquitectura para corrección del agrupamiento por ciudad atacante en EP-SPAWN — estrategia híbrida coords→farm_slots / nombre→villages / Desconocido
metadata:
  type: project
---

## Decisión arquitectónica: inferencia de ciudad atacante (RN-GROUP-01 corregido)

**Por qué falló el diseño original:** `attack_reports.origin_village_name` guardaba la línea entera del atacante cuando no había coords en el reporte (parser:588-592). Agrupar por ese campo era basura.

**Estrategia híbrida decidida:**
1. PRIMARIO: cruzar `coord_x_dest/coord_y_dest` con `farm_slots.x/y` → JOIN directo en la misma BD
2. FALLBACK: cruzar tokens del texto atacante con `villages.name` (misma BD)
3. ÚLTIMO RECURSO: "Desconocido"

**Why:** El cruce por coords es language-independent y exacto. El cruce por nombre de village es el mismo fallback que tiene el parser hoy pero más limpio (solo el último token, no la línea entera).

**How to apply:** El JOIN puede ir dentro de `get_oasis_spawn_composition` sin inyectar ningún port adicional — todos los adapters comparten `self._conn` (misma BD: `travian_bot.db`). El campo de salida sigue siendo `origin_villages: string[]` — el frontend ya lo consume correctamente.

## Hallazgos clave verificados (2026-06-02)

- **misma BD**: `database.py:6` define un único `DB_PATH = "travian_bot.db"`. El lifespan de `main.py:152` abre UNA conexión (`get_connection()`) y la pasa a todos los adapters (`FarmListSQLiteAdapter(conn)`, `AttackReportSQLiteAdapter(conn)`, `AccountSQLiteAdapter(conn)`). JOIN entre tablas de distintos adapters = válido.
- `attack_reports.world_id` es INTEGER pero **siempre NULL en MVP** (`attack_report_sqlite_adapter.py:384`). No se puede usar para filtrar por world todavía.
- El `villages` DDL está en `account_sqlite_adapter.py:73-81` pero es una tabla compartida: `farm_list_sqlite_adapter.py:639` ya hace JOIN con ella.
- `_extract_origin_village` (parser:546-606): cuando no hay coords en la línea del atacante, devuelve `first_nonempty` = toda la línea `[Tag] Player from village Aldea`. No hay catálogo i18n del literal "from village" — no existe en `core/i18n/`.

**Pista language-independent para el fallback:** el nombre de aldea suele ser el ÚLTIMO token antes del fin de línea (o el texto completo si no hay más estructura). Cruzar cualquier token de esa línea con `villages.name` (tabla de la BD) es más robusto que depender del literal multiidioma.
