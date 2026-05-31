---
name: attack-report-pregame
description: Gate de entrada feature "copiar-pegar reporte de ataque a oasis": qué existe y qué hay que crear. Verificado 2026-05-30.
metadata:
  type: project
---

## Contexto
Feature: interfaz para pegar texto crudo de reporte de ataque Travian → parse → BD → estadísticas de animales.

## Lo que YA existe y es reutilizable directamente

**Catálogo de animales NATURE (ordinal 1-10, 25 idiomas):**  
- `core/i18n/catalog/base/troops.json` → claves NATURE_1..NATURE_10 con los 25 idiomas.  
- `core/use_cases/nature_animal_drops.py` → NATURE_DROPS dict ordinal→{wood,clay,iron,crop}.  
- Los stats de NATURE están en BD (troop_stats seed) con sus iconos en icon_metadata.  
- El catálogo de tropas jugables (ROMANS_1..VIKINGS_10) también está en el mismo JSON.  
- `core/entities/tribe.py` → Tribe.NATURE ya existe.  

**Componente TravianReport.jsx:**  
- Renderiza informe con tabla atacante + defensor + stats (exactamente el formato del reporte Travian).  
- Props normalizadas: attackerTroops, defenderTroops, animalLoot, attackerCostLoss.  
- Ya lo usa CombatCalculator (simulador) y OptimizerResult (optimizador).  

**Infraestructura BD:**  
- `adapters/db/database.py` → get_connection(), aiosqlite WAL, patrón singleton en app.state.  
- `adapters/db/game_data_sqlite_adapter.py` → patrón DDL CREATE IF NOT EXISTS + UPSERT idempotente.  
- `adapters/db/seed_loader.py` → patrón extensible: añadir tabla nueva = añadir entrada en UPSERT_MAP.  
- Patrón Port (ABC) en `core/ports/` → se replica para el nuevo puerto de reportes.  

**GameDataPort/TranslationPort:**  
- `core/ports/game_data_port.py` → get_troop_stats(tribe, ordinal) permite resolver nombre+icono de cualquier tropa.  
- `core/ports/translation_port.py` → get_troop_names_by_tribe() para resolver nombre localizado → ordinal.  

**Entidades de combate reusables (para el modelo de datos del reporte):**  
- `core/entities/combat.py` → TroopResult (tribe, ordinal, name, icon_url, qty_initial/survived/lost),  
  AnimalResourceDrop (wood/clay/iron/crop/total), Loot, ResourceLossesBand → son los DTOs exactos que  
  necesita un reporte de ataque persistido.  

## Lo que HAY QUE CREAR (delta)

1. **Parser de texto crudo** (`core/use_cases/attack_report_parser.py` o similar):  
   - Nada existe. Los scripts en `docs/read_reports.py` y `docs/analyze_reports.py` leen un Excel  
     ya estructurado (columnas pre-llenadas), NO parsean texto crudo del clipboard.  
   - El parse implica: regex/split multilingüe, detección de tribu atacante, coordenadas,  
     fecha, tablas de tropas enviadas/perdidas, animales presentes/muertos, botín, stats.  
   - Punto de riesgo: multi-idioma (nombre de animal varía por idioma → necesita invertir  
     troops.json para mapear nombre→ordinal).  

2. **Entidad/DTO del reporte guardado** (`core/entities/attack_report.py`):  
   - Una entidad persistible (con id, timestamp, coord_origen, coord_destino, tribu atacante)  
     que agrupa las entidades de combate ya existentes: TroopResult x2 + AnimalResourceDrop x2 + Loot.  
   - NO duplicar TroopResult: usarlo como subentidad o referenciar sus campos directamente.  

3. **Puerto de persistencia de reportes** (`core/ports/attack_report_port.py`):  
   - save_report(report) + list_reports(filters) + get_stats().  

4. **Adaptador SQLite de reportes** (`adapters/db/attack_report_sqlite_adapter.py`):  
   - DDL nuevas tablas: attack_reports (cabecera) + report_troops (filas atacante) +  
     report_animals (filas defensor NATURE).  
   - UPSERT idempotente, mismo patrón que GameDataSQLiteAdapter.  

5. **Endpoint REST** (`adapters/api/routes/attack_reports.py`):  
   - POST /attack-reports/parse → recibe texto crudo, devuelve preview del parse.  
   - POST /attack-reports → guarda un reporte parseado.  
   - GET /attack-reports → lista con filtros.  
   - GET /attack-reports/stats → estadísticas de aparición de animales.  

6. **Página/vista frontend**:  
   - Textarea para pegar texto crudo.  
   - Preview usando TravianReport.jsx (REUTILIZAR — ya renderiza exactamente este formato).  
   - Listado de reportes guardados.  
   - Panel de estadísticas (histograma de animales por tipo).  
   - NO existe ninguna página de este tipo.  

## Notas de diseño

- `docs/analyze_reports.py` conoce los 10 nombres en inglés hardcodeados: usar el catálogo  
  i18n existente en lugar de hardcodear (retrocompatible, multi-idioma desde el arranque).  
- `docs/read_reports.py` y el Excel son herramientas ad-hoc de análisis (fuera del árbol de src),  
  no representan ninguna infraestructura de producción. No reutilizar directamente.  
- TravianReport.jsx está desacoplado de la fuente: acepta props normalizadas, no el shape del  
  backend de simulación. Reutilizable sin modificación si el nuevo endpoint devuelve el mismo shape.

**Why:** feature nueva que expande el módulo de combate hacia persistencia de histórico real.  
**How to apply:** el analista debe saber que el parse y la persistencia son CREAR, pero el  
display (TravianReport.jsx), el catálogo de animales y la infraestructura BD son REUTILIZAR.
