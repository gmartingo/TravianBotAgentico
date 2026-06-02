# Documentación técnica — TravianBot

Índice maestro de toda la documentación del proyecto. Empieza aquí.

---

## Organización de carpetas

| Carpeta | Contenido |
|---|---|
| `arquitectura/` | Arquitectura hexagonal, patrones de diseño, decisiones técnicas |
| `backend/` | Módulos de `core/` y `adapters/` — documentación funcional de código |
| `backend/referencia-funciones/` | Referencia rápida de funciones y métodos por módulo |
| `api/` | Referencia centralizada de endpoints REST |
| `funcionalidades/` | Documentación de negocio por feature (para stakeholders y PO) |
| `procesos/` | Guías de proceso y operativa del equipo |

---

## Documentación de código (backend)

| Documento | Módulo/Feature |
|---|---|
| [`backend/i18n.md`](backend/i18n.md) | Internacionalización: `core/i18n/`, `core/ports/translation_port.py`, `adapters/translations/`, `adapters/api/main.py` (exception handler, lifespan, middlewares) |
| [`backend/sesion.md`](backend/sesion.md) | Sesión del bot: `SessionRegistry`, `LoginUseCase`, `LogoutUseCase`, endpoints de sesión, cableado en `lifespan`, seguridad de credenciales |
| [`backend/farm-lists.md`](backend/farm-lists.md) | Farm Lists y Farm Stats: entidades (`FarmSlot`, `FarmList`, `FarmScheduler`, `SlotEvent`, `SlotBountyRecord`), puerto `FarmListDbPort`, adaptador SQLite (esquema, migraciones, lógica de sync por coordenadas), 10 casos de uso (ciclo automático, envío manual, sondas, stats), router `/farm` (21 endpoints) |

### Referencia de funciones

| Documento | Contenido |
|---|---|
| [`backend/referencia-funciones/translation-port.md`](backend/referencia-funciones/translation-port.md) | Métodos del puerto `TranslationPort` y su implementación `JsonTranslationAdapter` |
| [`backend/referencia-funciones/api-i18n-helpers.md`](backend/referencia-funciones/api-i18n-helpers.md) | Helpers del exception handler y dependencias de la API (`_mask_frame_locals`, `_build_trace`, `_extract_lang`, `get_language`, `get_translation_port`) |
| [`backend/referencia-funciones/sesion.md`](backend/referencia-funciones/sesion.md) | Referencia rápida de `SessionRegistry`, `LoginUseCase`, `LogoutUseCase`, `get_account_password_cipher`, `get_world_runtime_port` y `LoginFailedError` |
| [`backend/referencia-funciones/attack-report-temporal-distribution.md`](backend/referencia-funciones/attack-report-temporal-distribution.md) | `get_animal_temporal_distribution` — port, adapter (LAG+bucketizado+moda), endpoint EP-TD, cliente JS |
| [`backend/referencia-funciones/oasis-spawn-composition.md`](backend/referencia-funciones/oasis-spawn-composition.md) | Feature oasis-spawn-mechanics: catálogo de spawn (`SPAWN_TIMER_S`, `OASIS_TYPE_SETS`, `COOLDOWN_THRESHOLD_S`), `get_oasis_spawn_composition`, helpers `_infer_type` (Jaccard), `_spawn_status`, `_worst_case_count`, `_extract_player_village_from_blob`, `_infer_attackers`, frontend `SpawnMechanicsPanel` y `OasisCombatPlannerPanel` |

---

## Documentación de código (frontend)

| Documento | Módulo/Feature |
|---|---|
| [`frontend/dashboard.md`](frontend/dashboard.md) | Dashboard React de gestión de cuentas/mundos: stack, rutas, i18n 25 idiomas + RTL, cliente HTTP, pantallas S2–S9, tokens de diseño, divergencias código/diseño |

---

## Manual de usuario

| Documento | Contenido |
|---|---|
| [`manual-usuario/index.html`](manual-usuario/index.html) | **Manual de usuario (HTML con capturas reales)** — landing con selector de idioma. Disponible en **español** (`manual-usuario/es/`) e **inglés** (`manual-usuario/en/`), cada uno con sus capturas en su idioma (estructura preparada para los 25 idiomas). Cubre: pantalla de Cuentas, crear cuenta (asistente), detalle y mundos, añadir mundo, arrancar sesión, editar/borrar, idioma y tema. Ábrelo en el navegador. |
| [`manual-usuario/farm-lists.html`](manual-usuario/farm-lists.html) | **Manual de listas de vacas (HTML con capturas reales)** — cubre: acceso a la sección Farm Lists desde el mundo, tabla de listas con columnas, drawer Slots (chips de estado + tabla de vacas + acordeón de historial por vaca), drawer Stats (distribución + ranking), drawer Historial (paginado), envío manual, estados de vaca y sus insignias, menú de acciones (activar/desactivar/sonda), gestión de schedulers, y sincronización desde Travian. Capturas reales del 2026-05-28. |

---

## Documentación de negocio (funcionalidades)

| Documento | Feature |
|---|---|
| [`funcionalidades/i18n-backend.md`](funcionalidades/i18n-backend.md) | Internacionalización del backend: edificios, tropas y mensajes de error |
| [`funcionalidades/cuentas-mundos.md`](funcionalidades/cuentas-mundos.md) | Registro y gestión de cuentas y mundos + sesión del bot de extremo a extremo (negocio: reglas, flujos, restricciones) |
| [`funcionalidades/sesion.md`](funcionalidades/sesion.md) | Sesión del bot: login/logout/estado, seguridad de credenciales, nota de operación sobre `TRAVIAN_BOT_SECRET_KEY` |
| [`funcionalidades/farm-lists.md`](funcionalidades/farm-lists.md) | Farm lists y farm stats: qué son las listas de vacas, problema que resuelve el bot, actores, opciones configurables (schedulers), 16 reglas de negocio (RN-01 a RN-16), seguimiento de botín, estados de vaca, límites conocidos |
| [`funcionalidades/oasis-spawn-mechanics.md`](funcionalidades/oasis-spawn-mechanics.md) | Mecánica de spawn de oasis: objetivo de negocio, mecánica real del juego (timers fijos, sets, cooldown), las 4 piezas (panel educativo, composición típica, peor combinación, estado cooldown/respawn), reglas de negocio, cómo leer el panel, deuda técnica conocida |

---

## Referencia de API

| Documento | Contenido |
|---|---|
| [`api/catalogo.md`](api/catalogo.md) | `GET /catalog/buildings`, `GET /catalog/troops/{tribe}`, exception handler global con traducciones |
| [`api/cuentas-mundos.md`](api/cuentas-mundos.md) | `POST/GET/PUT/DELETE /accounts`, `POST/GET/DELETE /accounts/{id}/worlds` — CRUD de cuentas y mundos |
| [`api/sesion.md`](api/sesion.md) | `POST`, `DELETE`, `GET /accounts/{id}/worlds/{id}/session` — login, logout y estado de sesión del bot |
| [`api/human-sessions.md`](api/human-sessions.md) | `GET/PUT /worlds/{id}/session/...` — timeline horario, override de modo y cancelación de override (Human Sessions) |
| `docs/api/openapi.yaml` + `docs/api/API.md` | Contrato completo de la API (attack-reports EP-01..EP-TD, farm, catalog, noise, etc.) — fuente de verdad de máquina |

---

## Procesos

| Documento | Contenido |
|---|---|
| [`procesos/operativa-por-fases.md`](procesos/operativa-por-fases.md) | Flujo de 5 fases para solicitudes |

---

## Convenciones

- Cada documento lleva al pie una marca de agua `🔖` con la fecha de su última revisión.
- Al crear o modificar una función: actualizar su entrada en `referencia-funciones/`.
- Al añadir módulo, feature o endpoint: enlazarlo desde este README.
- Al detectar divergencia código/spec: documentarla en el documento afectado bajo el encabezado **Divergencias código/spec**.

🔖 Última revisión: 2026-06-02 (añadido referencia-funciones/oasis-spawn-composition.md — EP-SPAWN con catálogo de spawn, inferencia Jaccard, peor combinación, cooldown/respawn, atribución player/village; añadido funcionalidades/oasis-spawn-mechanics.md — documento de negocio de la mecánica de spawn)
