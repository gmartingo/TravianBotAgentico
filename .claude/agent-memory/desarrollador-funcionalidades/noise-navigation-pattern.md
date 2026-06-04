---
name: noise-navigation-pattern
description: Patrón de implementación del subsistema de Ruido Humano de Navegación (human-sessions v2.2)
metadata:
  type: project
---

El subsistema de ruido se implementó como una capa opcional del WorldAgent inyectada via `noise_db: NoiseDbPort | None`. Las 4 tablas SQLite viven en `adapters/db/noise_sqlite_adapter.py`. Los 10 endpoints en `adapters/api/routes/noise.py` (sin Accept-Language, sin prefijo /api).

**Stub de ejecución**: `_execute_noise_action` es un stub funcional — hace el dwell pero no conecta con zendriver porque FarmListBrowserPort no expone navegación libre. El TODO(v2.2.1) marca dónde conectar. La estructura de scheduling (encolar/reencolar NOISE_NAVIGATION) funciona completa.

**Distribución bursty RN-HS24bis**: máquina de estados `_noise_in_burst` / `_noise_burst_remaining` en el WorldAgent. Burst: uniform(0.5,4.0)s; Silence: expovariate capado [20,600]s. Fano factor > 1 verificado estadísticamente.

**Validación URL RN-HS23**: en `noise_sqlite_adapter._validate_url_pattern()` — sin javascript:/data:/file:, sin protocol-relative, relativas deben empezar con '/', dominio externo al world_server → ValueError→422.

**Warmup post-relogin RN-HS24quater**: al completar `_relogin_with_backoff()`, se llama `_enqueue_noise_warmup(n=randint(1,3))` que encola n NOISE con priority=1 (antes de productivas). El `NoiseSQLiteAdapter` se registra en `app.state.noise_db_port` en el lifespan; para que el WorldAgent lo use, el endpoint de arranque del agente debe pasarlo como `noise_db=app.state.noise_db_port`.

**Por qué**: spec human-sessions.md sección v2.2 (entregada como briefing en el prompt del orquestador, no escrita en el fichero del spec — desviación documentada en §17 Registro).
