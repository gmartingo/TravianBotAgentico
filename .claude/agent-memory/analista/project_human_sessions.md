---
name: project-human-sessions
description: Spec human-sessions v2.1 — timeline horario con 3 modos (HARDCORE/PASIVO/DISCONNECTED); PASIVO con probabilidad y multiplicador; DISCONNECTED cierra Chrome + relogin; huecos rellenados automáticamente
metadata:
  type: project
---

Spec en `docs/specs/human-sessions.md` con estado `ready-for-impl` (APIs pendientes de
revalidación por `desarrollador-apis` tras cambio de enum IDLE→PASIVO). Versión 2.1
(2026-05-31).

**Contexto:** el bot fue baneado por Travian (primera ofensa: -33% de edificios) por operar
24/7 sin descanso y con orden iterativo determinista.

**Qué hace:** El WorldAgent sigue un timeline horario configurable por día de la semana (7
calendarios independientes). El modo activo se deriva del reloj + calendario, no se persiste.

**Tres modos (v2.1):**
- `HARDCORE`: comportamiento completo (farm lists VILLAGE, oasis, edificios, tropas).
- `PASIVO`: actividad muy reducida. Farm lists VILLAGE con probabilidad `passive_send_probability`
  (default 5%) y con intervalo × `passive_interval_factor` (default 2.0). Sin oasis, edificios
  ni tropas. Chrome abierto. NO es un no-op — manda raids muy ocasionalmente.
- `DISCONNECTED`: parada total. **Chrome se cierra** al entrar. Al salir hacia HARDCORE/PASIVO:
  **relogin automático** (`_relogin_with_backoff()`) antes de retomar tareas.

**Cambios clave en v2.1 vs v2:**
1. `IDLE` renombrado a `PASIVO` en todo el spec (enum, DDL, endpoints, ejemplos, tests).
2. `PASIVO` redefinido: ya no es no-op. Tiene `passive_send_probability` (0.05) y
   `passive_interval_factor` (2.0), ambos configurables por mundo en `world_session_config`.
3. `DISCONNECTED` cierra Chrome (antes lo mantenía abierto). Al volver: relogin automático.
   Backoff exponencial 10→20→40→60 min. `FernetDecryptionError` → DISCONNECTED-error sin backoff.
4. Huecos en el timeline se rellenan automáticamente con bloques DISCONNECTED (antes era 422).
   Solapes siguen siendo 422. `blocks:[]` → 1 bloque 00:00-24:00 DISCONNECTED (válido, 200).

**Jitter:** cada borde de bloque tiene jitter ±15min (configurable). Se recalcula en cada
transición. Si jitter < now+1min, se fuerza now+1min (EC-HS03).

**Timeline por día de la semana:** humanos tienen hábitos distintos entre semana y fin de
semana. 7 calendarios independientes. Cobertura 24h garantizada por relleno automático.

**Override manual:** PUT /worlds/{id}/session/mode → dura hasta el próximo borde de bloque
(con jitter aplicado). Se persiste en BD (`world_session_override`) para sobrevivir reinicios.
Override para modo ya activo → 200 con mensaje informativo (no 409).
Override hacia DISCONNECTED → cierra Chrome. Override desde DISCONNECTED → relogin.

**Piezas nuevas que crea:**
- `core/entities/session.py` → `SessionMode` (3 valores: HARDCORE/PASIVO/DISCONNECTED),
  `SessionBlock`, `SessionTimeline`, `SessionOverride`, `SessionConfig` (nueva en v2.1);
  + helpers puros `_find_active_block()`, `_current_mode()`
- `core/ports/session_timeline_db_port.py` → `SessionTimelineDbPort` (7 métodos, 2 nuevos
  en v2.1: `get_session_config`, `upsert_session_config`)
- Tablas: `world_session_timeline` (CHECK PASIVO), `world_session_override` (CHECK PASIVO),
  `world_session_config` (nueva en v2.1: passive_interval_factor [1.5,5.0], passive_send_probability [0.01,0.50])
- `WorldAgent._active_mode`, `_jitter_fin`, `_check_mode_transition()`,
  `_relogin_with_backoff()` (nuevo en v2.1), `_handle_send_farm_list_group()` (nuevo en v2.1),
  `_reschedule_farm_pasivo()` (nuevo en v2.1)
- Endpoints: GET/PUT /worlds/{id}/session, GET/PUT /worlds/{id}/session/timeline/{weekday},
  PUT /worlds/{id}/session/mode, GET/PUT /worlds/{id}/session/config (2 nuevos en v2.1)

**Reglas clave:**
- Modo derivado del reloj SIEMPRE (no persistido excepto el override).
- Al entrar en HARDCORE desde otro modo → llama seed_oasis_groups_from_db() (EC-HS07: captura excepción).
- DISCONNECTED: cierra Chrome, no saca tareas de la cola.
- PASIVO: dado de probabilidad + multiplicador de intervalo para farm lists VILLAGE; sin OASIS.
- HARDCORE: comportamiento completo.
- Timeline por defecto hardcodeado si BD vacía (lun-vie: 08:00-23:00 HARDCORE + noche DISCONNECTED).
- Huecos → relleno automático DISCONNECTED. Solapes → 422.
- Validar solapes ANTES de rellenar (para que el error sea atribuible al input del usuario).
- Eliminado: `rest_interval_factor`, `HumanSessionState`, `_init_human_session()`, HARDCORE_SESSION,
  REST_SESSION, nombre IDLE.

**APIs pendientes de revalidación:** `apis_validadas_por_desarrollador_apis: pendiente` en el
frontmatter. El enum cambió (IDLE→PASIVO) y hay 2 endpoints nuevos (/session/config).

**Tests:** UT-HS01…UT-HS34 (34 tests unitarios), IT-HS01…IT-HS10 (10 tests integración)

**Prerrequisito de:** [[project-oasis-farming]] (que depende de _active_mode)
**Relacionado:** [[project-task-order-randomization]] (otro spec motivado por el mismo baneo)
