---
name: attack-reports-pattern
description: Patrón BD de ataques a oasis: parser de texto crudo → SQLite con 3 tablas + 6 endpoints; índice invertido NATURE; aislamiento de tests con tmp_path+monkeypatch
metadata:
  type: project
---

## Feature: bd-ataques-oasis (2026-05-30)

### Clave arquitectónica
- Parser síncrono en `core/use_cases/attack_report_parser.py`; verificación de unicidad async en el handler (no en el parser). La firma `db_port=None` en `parse_attack_report()` es de compatibilidad, no se usa en producción.
- Excepciones propias: `MultipleReportsError`, `NotNatureOasisError`, `UnrecognizedAnimalError(names)`, `ReportFormatError`. Se mapean a 422 en el router.
- `DuplicateReportError(existing_id)` en `core/ports/attack_report_port.py`; se mapea a 409 en el router.

### Índice invertido NATURE
- `build_nature_inverted_index()` — singleton lazy desde `troops.json` (NATURE_1..10); 215 entradas, 0 colisiones cross-language. Se llama con `_get_nature_index()` en el parser.

### BD SQLite — 3 tablas
- `attack_reports` (cabecera) + `attack_report_attacker_troops` + `attack_report_animals`
- 4 índices: coords_time, attacked_at, attacker_troops(report_id), animals(ordinal+report_id)
- Clave única: `(coord_x_dest, coord_y_dest, attacked_at, origin_village_name)`
- `hero_inventory_json` = JSON TEXT opaco (null si sin inventario del héroe)
- `survived` calculado al insertar (present/sent - killed/lost), no recomputado en SELECT

### Routing crítico (C6)
- EP-06 (`/attack-reports/stats/oasis`) debe declararse ANTES de EP-04 (`/attack-reports/{id}`)
- `{id}` tipado `int = Path(..., ge=1)` para que "stats" devuelva 422 y no colisione

### Tests: aislamiento de BD
- Usar `monkeypatch.setattr("adapters.db.database.DB_PATH", str(tmp_path/"test.db"))` + function-scope (igual que test_accounts_api.py). NO usar module-scope con la BD real compartida.

### Constante HTTP 422
- En FastAPI 0.136: usar `status.HTTP_422_UNPROCESSABLE_CONTENT` (no `HTTP_422_UNPROCESSABLE_ENTITY`, deprecado).

**Why:** El patrón tmp_path+monkeypatch es el único que garantiza BD limpia por test cuando los tests escriben datos. Module-scope con BD compartida falla en la segunda ejecución.
**How to apply:** Siempre que una feature de API escriba datos en BD, usar function-scope con monkeypatch de DB_PATH.

Relacionado: [[game-data-port-pattern]], [[session-registry-pattern]]

---

## Update 2026-05-31 — specs fix-hora-balance + stats-oasis-nav

### `main.py` faltaba registrar el módulo (bug descubierto al implementar)
El router y el adaptador NO estaban en `main.py`. Añadir siempre para nuevos módulos:
- `from adapters.api.routes.attack_reports import router as attack_reports_router`
- `from adapters.db.attack_report_sqlite_adapter import AttackReportSQLiteAdapter`
- En lifespan: `attack_report_adapter = AttackReportSQLiteAdapter(conn); await attack_report_adapter.ensure_tables(); application.state.attack_report_port = attack_report_adapter`
- `app.include_router(attack_reports_router)`

### Orden de routers ACTUALIZADO (3 rutas literales antes de `/{id}`)
1. EP-08 `GET /attack-reports/oasis` (literal)
2. EP-07 `GET /attack-reports/stats/bounty` (literal)
3. EP-06 `GET /attack-reports/stats/oasis` (literal)
4. EP-04 `GET /attack-reports/{id}` (dinámico)

### `attacked_at` = verbatim naive (RN-08-bis)
Campo TEXT naive ISO-8601 "YYYY-MM-DDTHH:MM:SS" — NO UTC con offset. Ver también
migración ejecutada en 2026-05-31 sobre los 5 reportes del oasis (-70,73).
`_parse_offset` eliminada del parser (ya no se necesita). `_normalize_offset` se conserva
para serializar `utc_offset` como metadato.

### `_calc_regen_rates` = función de módulo en `attack_report_sqlite_adapter.py`
Importable en tests: `from adapters.db.attack_report_sqlite_adapter import _calc_regen_rates`
Recibe `repopulation_gaps` (lista de dicts ya en memoria). Excluye gap_seconds<=0 y
regenerated<0. Incluye regenerated=0. Animales sin intervalos válidos NO aparecen.

### Datos de referencia oasis (-70,73) — 5 reportes reales
- Rata: appearances=4, avg_present=9.25, max=14, min=7
- Rata regen: avg_regen_per_hour=2.29, valid_intervals=4
- last_attack: "2026-05-31T13:39:30" (verbatim)

---

## Update 2026-06-01 — spec bd-ataques-oasis-global-pct-aparicion (EP-09 eligible_reports)

### Patrón `eligible_reports` en `get_global_oasis_stats()`
Campo aditivo (no rompe clientes existentes). La query del denominador (Paso 1b del spec)
se ejecuta justo después del Paso 1a (apariciones). Usa subconsulta DISTINCT para
"ever_present" (oasis donde el animal apareció alguna vez con present>0), luego JOIN
con attack_reports por coordenadas para contar TODOS los reportes de esos oasis.
`eligible_by_ordinal: dict[int, int]` construido en memoria para O(1) lookup al ensamblar
la respuesta.

### Invariante demostrada (no solo afirmada)
appearances <= eligible_reports: los reportes de appearances son subset de eligible_reports
por construcción de la subquery. Test T-P03 lo verifica para todos los items.

### Ejemplo numérico de referencia (T-P06)
A(10 rep, 6 rata) + B(5 rep, 2 rata) + C(20 rep, sin rata) → appearances=8, eligible=15 (NO 35).
Si se usa present=0 para "Rata ausente" en el reporte, el parser parsea la fila correctamente
(present=0 en attack_report_animals). El WHERE present > 0 en la subquery ever_present
excluye esas filas del denominador de C, pero C tampoco entra porque nunca tuvo rata con present>0.

### Documentacion/
El módulo attack_reports no tiene entrada en documentacion/ (ni backend/ ni referencia-funciones/).
Si se crea documentación de este módulo en el futuro, añadir entrada en documentacion/README.md.
