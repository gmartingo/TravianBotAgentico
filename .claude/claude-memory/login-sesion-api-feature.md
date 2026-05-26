---
name: login-sesion-api-feature
description: feature API de sesión (login/logout/estado) implementada y validada en Travian real
metadata: 
  node_type: memory
  type: project
  originSessionId: 3cb63abf-740c-4663-91de-fe22727bffcb
---

Feature **login-sesion-api** implementada y probada con login real contra Travian (2026-05-26). Spec en `docs/specs/login-sesion-api.md` (incluye Amendment A1).

Qué hace: expone el ciclo de vida de sesión del bot vía REST sobre el router de cuentas:
- `POST /accounts/{aid}/worlds/{wid}/session` → login síncrono (200 / 401 LoginFailedError) — abre Chrome real, re-login silencioso si ya había sesión.
- `DELETE .../session` → logout idempotente (204), solo `browser.stop()` (nunca navega a logout de Travian).
- `GET .../session` → `{active, world_id, account_id}` (200).

Piezas: `SessionRegistry` (adapters/browser/session_registry.py, implementa `WorldRuntimePort`, dict `{world_id:(Browser,World)}`, expone `get_browser`/`get_world_server` para `LiveOverviewAdapter` vía `set_callables`); `LoginUseCase` descifra la contraseña con Fernet inyectado (`get_fernet`) — ver [[fernet-key-must-be-persisted]]; nuevo `DbPort.get_account_password_cipher`. Cableado en `main.py` lifespan solo en modo OVERVIEW_SOURCE=live.

**Depende de `live_overview_adapter.py`** (de la feature [[travian-lectura-overview-endpoints]], aún sin commitear) → entrelazadas en el árbol de trabajo. Guardian aprobó (no toca login.py/driver.py). Los 2 fallos CA-20 son de lectura-overview, ajenos.
