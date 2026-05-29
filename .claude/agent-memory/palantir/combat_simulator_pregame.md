---
name: combat-simulator-pregame
description: Hallazgos del gate de entrada para la feature simulador de combate / oasis — qué existe reutilizable y qué hay que crear. Verificado 2026-05-28.
metadata:
  type: project
---

## Hallazgos del gate de entrada — Simulador de combate (2026-05-28)

### Infraestructura reutilizable (ya existe, NO recrear)

**GameDataPort + GameDataSQLiteAdapter** (`core/ports/game_data_port.py`, `adapters/db/game_data_sqlite_adapter.py`)
- `get_troop_stats(tribe, ordinal)` → devuelve dict con `attack`, `def_infantry`, `def_cavalry`, `speed`, `carry`, `upkeep`, `cost_*`
- `get_all_troop_stats(tribe)` → todos los stats de una tribu
- Ya tienen datos de TODAS las tribus incluyendo NATURE (animales de oasis)

**Seed de troop_stats** (`seeds/game_data/troop_stats.json`)
- 90 tropas de 9 tribus (romans, teutons, gauls, egyptians, huns, spartans, vikings, nature, natars)
- NATURE (animales de oasis) ya tienen stats completos: ordinal 1-10 = rat, spider, snake, bat, boar, wolf, bear, croc, tiger, elephant
- Valores verificados: e.g. rat (ord1) attack=10 def_inf=25 def_cav=20; elephant (ord10) attack=600 def_inf=440 def_cav=520

**Catálogo de nombres** (`core/i18n/catalog/base/troops.json`)
- 91 entradas (ROMANS_1..10, TEUTONS_1..10, GAULS_1..10, NATURE_1..10, etc.) con nombres en 25 idiomas
- Acceso vía `TranslationPort.get_troop_name(tribe, ordinal, lang)`

**unit_class_to_tribe_ordinal()** (`core/utils/units.py`)
- Convierte "u31"-"u40" → (Tribe.NATURE, 1-10)
- Sin esto habría que reimplementarlo

**Tribe enum** (`core/entities/tribe.py`)
- `Tribe.NATURE`, `Tribe.NATARS` ya existen como tribus NPC

**troop_upgrades seed** (`seeds/game_data/troop_upgrades.json`)
- Tabla de mejoras de herrería por nivel (stat_name, stat_value) → necesaria para calcular ataque/defensa con bonus de herrería

### Infraestructura relevante pero solo de lectura/display (no de cálculo)

**VillageSupportTroopsDTO** (`core/dtos/troops_dto.py`)
- Tiene `offence`, `def_infantry`, `def_cavalry` ya como sumatorios del HTML de Travian
- Sirve para conocer la fuerza defensiva de aldeas propias (no de oasis)

**TroopsUseCase** (`core/use_cases/troops_use_case.py`) — solo enriquece DTOs con nombres/iconos, no calcula combate

### Lo que NO existe (delta a crear)

1. **Fórmula de combate de Travian**: ningún fichero implementa A vs D → supervivientes. Travian usa proporciones de Lanchester modificadas. A crear en `core/use_cases/combat_simulator.py` (o similar).
2. **Lógica de composición de oasis**: qué animales pueden estar en un oasis según su tipo y timer (lógica del Excel de oasis). NO existe en el código.
3. **Optimizador de tropas atacantes**: búsqueda de mínimas tropas para ganar sin pérdidas. NO existe.
4. **Entidad/DTO de resultado de combate**: CombatResult (supervivientes, bajas, botín). NO existe.
5. **Endpoint API de combate**: ningún router de `/adapters/api/routes/` tiene nada de combat/simulate.

### Riesgo de modificación

- `get_troop_stats` y `get_all_troop_stats` son la fuente de datos; se usan en `troop_display.py` y `troops_use_case.py`. Si el simulador solo los LEE (sin modificar), riesgo = cero.
- `unit_class_to_tribe_ordinal` se usa en `troop_display.py` → REUTILIZAR sin tocar.
- El seed `troop_stats.json` ya tiene datos de NATURE → el simulador puede usarlos directamente sin scraper adicional.

### Nota sobre el Excel de oasis

El usuario tiene `docs/Copia de Copy of Oasis farming from a nerd.xlsx` — guía detallada de timer raiding. Contiene tablas de composición de animales por tipo de oasis, timers de respawn (rat=5min, spider=6min, snake=7min, bat=8min, boar=9min, wolf=10min, bear=11min, croc=12min, tiger=13min, elephant=14min) y comparativas de tropas por tribu. Esta es documentación de negocio que el analista debe usar.

**Why:** El simulador necesita saber estos datos de dominio que están en el Excel pero no en el código.
**How to apply:** Al diseñar el spec, el analista puede convertir estas reglas de negocio del Excel en lógica de dominio en `core/`.
