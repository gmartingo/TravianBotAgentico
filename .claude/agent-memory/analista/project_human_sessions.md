---
name: project-human-sessions
description: Spec human-sessions — ciclo HARDCORE_SESSION/REST_SESSION en WorldAgent; estado en memoria, factor de intervalo REST, parada de oasis en REST
metadata:
  type: project
---

Spec en `docs/specs/human-sessions.md` con estado `ready-for-impl`.

**Qué hace:** El WorldAgent alterna entre HARDCORE_SESSION (4-6h) y REST_SESSION (30-90min) en memoria. Controla el ritmo de trabajo global del bot, no solo oasis.

**Piezas nuevas que crea:**
- `core/entities/session.py` → `SessionMode` enum (2 valores) + `HumanSessionState` dataclass
- `WorldAgent._init_human_session()` → arranque siempre en REST, warmup 20-30min
- `WorldAgent._check_and_transition_session()` → detección y transición REST↔HARDCORE; llama a `seed_oasis_groups_from_db()` en REST→HARDCORE
- `WorldAgent._next_farm_list_interval_ms()` → aplica `rest_interval_factor` (1.5×-2×) durante REST
- `WorldAgent._should_reenqueue_oasis_raid()` → False en REST, suprime reencole de SEND_OASIS_RAID

**Reglas clave:**
- Arranque: SIEMPRE REST con warmup random.uniform(20,30) min
- HARDCORE: 4-6h, oasis activo, farm lists sin multiplicar
- REST: 30-90min, oasis DETENIDO (no se encolan SEND_OASIS_RAID), farm lists con factor 1.5-2.0×
- Factor REST fijo por sesión (no por tick); se regenera al inicio de cada REST_SESSION
- Sin persistencia en BD: reiniciar = REST siempre
- Transición REST→HARDCORE llama seed_oasis_groups_from_db() (con captura de excepciones: EC-HS08)
- No hay TaskType de transición; detección por tiempo en el bucle del WorldAgent

**Prerrequisito de:** `oasis-farming.md` (que depende de que session_mode exista)

**Tests:** UT-HS01…UT-HS15, IT-HS01…IT-HS05

[[project-oasis-farming]]
