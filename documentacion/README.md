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
| [`backend/human-click.md`](backend/human-click.md) | Click humano indetectable v2.3.1: `human_click`, `human_click_at_rect`, `human_drift_toward`, motor Bézier, timing Fitts, `_CURSOR_POS`, `_TAB_LOCKS`, `_validate_or_reset_cursor` — `adapters/browser/driver.py` |
| [`backend/human-sessions.md`](backend/human-sessions.md) | Human Sessions v2.1: entidades `SessionBlock/Timeline/Override/Config`, funciones puras de cálculo de modo (`current_mode`, `_find_active_block`), integración en `WorldAgent` (transiciones, modos HARDCORE/PASIVO/DISCONNECTED, relogin automático), tablas `world_session_*` |
| [`backend/noise.md`](backend/noise.md) | Sistema de ruido v2 + Wizard: entidades noise (`NoiseDestination`, `NavigationPath`, `NavigationStep`, `NoiseConfig`), bucle de ruido en `WorldAgent`, `NoiseSQLiteAdapter`, EP-N01..EP-N14; EP-N15 y noise-frequency **pendientes** |
| [`backend/simulador-combate.md`](backend/simulador-combate.md) | Calculadora: motor de combate (`combat_engine.py`) y optimizador de balance multiraid (`combat_optimizer.py`), drops de animales de la naturaleza (`nature_animal_drops.py`), fórmulas (moral, bonus, muralla), endpoints y componentes frontend |

### Referencia de funciones

| Documento | Contenido |
|---|---|
| [`backend/referencia-funciones/translation-port.md`](backend/referencia-funciones/translation-port.md) | Métodos del puerto `TranslationPort` y su implementación `JsonTranslationAdapter` |
| [`backend/referencia-funciones/api-i18n-helpers.md`](backend/referencia-funciones/api-i18n-helpers.md) | Helpers del exception handler y dependencias de la API (`_mask_frame_locals`, `_build_trace`, `_extract_lang`, `get_language`, `get_translation_port`) |
| [`backend/referencia-funciones/sesion.md`](backend/referencia-funciones/sesion.md) | Referencia rápida de `SessionRegistry`, `LoginUseCase`, `LogoutUseCase`, `get_account_password_cipher`, `get_world_runtime_port` y `LoginFailedError` |
| [`backend/referencia-funciones/attack-report-temporal-distribution.md`](backend/referencia-funciones/attack-report-temporal-distribution.md) | `get_animal_temporal_distribution` — port, adapter (LAG+bucketizado+moda), endpoint EP-TD, cliente JS |
| [`backend/referencia-funciones/oasis-spawn-composition.md`](backend/referencia-funciones/oasis-spawn-composition.md) | Feature oasis-spawn-mechanics: catálogo de spawn (`SPAWN_TIMER_S`, `OASIS_TYPE_SETS`, `COOLDOWN_THRESHOLD_S`), `get_oasis_spawn_composition`, helpers `_infer_type` (Jaccard), `_spawn_status`, `_worst_case_count`, `_extract_player_village_from_blob`, `_infer_attackers`, frontend `SpawnMechanicsPanel` y `OasisCombatPlannerPanel` |
| [`backend/referencia-funciones/human-click.md`](backend/referencia-funciones/human-click.md) | Referencia rápida: `human_click`, `human_click_at_rect`, `human_drift_toward`, funciones privadas clave, excepciones relacionadas |
| [`backend/referencia-funciones/attack-report-adapter.md`](backend/referencia-funciones/attack-report-adapter.md) | `AttackReportSQLiteAdapter`: funciones de módulo (`_calc_regen_rates`, `_parse_utc_offset`, `_migrate_add_attacker_tribe`) y métodos del adaptador; helpers del router (`_preview_to_dict`, `_compute_attacker_cost_loss`, `_parse_or_422`) |
| [`backend/referencia-funciones/combat-engine.md`](backend/referencia-funciones/combat-engine.md) | Motor de combate y optimizador: funciones de `core/use_cases/combat_engine.py`, `combat_optimizer.py` y `nature_animal_drops.py` |

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
| [`manual-usuario/oasis-spawn.html`](manual-usuario/oasis-spawn.html) | **Manual de estadísticas de spawn de oasis (HTML con capturas reales)** — cubre: vista general de la pestaña Estadísticas, panel Leyenda/Mecánica (timers por animal, sets por tipo de oasis), Balance de operaciones, Planificador de combate (selector de intervalo 6/7/10/15 min, jerarquía Jugador→Aldea→Oasis, filas Media y Peor, tipo inferido + confianza, estados Cooldown/Repoblando/Desconocido, anomalías), Estadísticas globales, Lista de oasis, y modo oscuro. 11 capturas reales del 2026-06-02 (138 oasis; jugadores GonnaDie, CrazyMouse, SharpHorseman). |
| [`manual-usuario/oasis-reportes.html`](manual-usuario/oasis-reportes.html) | **Manual de reportes de ataques a oasis (HTML con capturas reales)** — cubre las cuatro pestañas (Ingresar, Historial, Estadísticas, Cadencia de farmeo): cómo pegar un reporte, filtrar el historial, ver el balance de operaciones, navegar las estadísticas por oasis y usar la cadencia de farmeo. 10 capturas reales del 2026-06-04 (2124 reportes, 152 oasis). |
| [`manual-usuario/calculadora.html`](manual-usuario/calculadora.html) | **Manual de la calculadora (HTML con capturas reales)** — simulador de combate (qué tropas/defensas introducir y cómo leer el resultado y el ratio) y optimizador de balance multiraid (modos Multi-tropa, Simulador ejército y Multi-raid, lectura de combinaciones ganadoras y tabla de alternativas). 10 capturas reales del 2026-06-04. |
| [`manual-usuario/human-sessions.html`](manual-usuario/human-sessions.html) | **Manual de sesión humana (HTML con capturas reales)** — timeline horario de actividad: panel de estado, selector de días, editor de bloques (HARDCORE/PASIVO/DISCONNECTED), barra timeline, override manual y modo oscuro. 6 capturas reales del 2026-06-04. |

---

## Documentación de negocio (funcionalidades)

| Documento | Feature |
|---|---|
| [`funcionalidades/i18n-backend.md`](funcionalidades/i18n-backend.md) | Internacionalización del backend: edificios, tropas y mensajes de error |
| [`funcionalidades/cuentas-mundos.md`](funcionalidades/cuentas-mundos.md) | Registro y gestión de cuentas y mundos + sesión del bot de extremo a extremo (negocio: reglas, flujos, restricciones) |
| [`funcionalidades/sesion.md`](funcionalidades/sesion.md) | Sesión del bot: login/logout/estado, seguridad de credenciales, nota de operación sobre `TRAVIAN_BOT_SECRET_KEY` |
| [`funcionalidades/farm-lists.md`](funcionalidades/farm-lists.md) | Farm lists y farm stats: qué son las listas de vacas, problema que resuelve el bot, actores, opciones configurables (schedulers), 16 reglas de negocio (RN-01 a RN-16), seguimiento de botín, estados de vaca, límites conocidos |
| [`funcionalidades/oasis-spawn-mechanics.md`](funcionalidades/oasis-spawn-mechanics.md) | Mecánica de spawn de oasis: objetivo de negocio, mecánica real del juego (timers fijos, sets, cooldown), las 4 piezas (panel educativo, composición típica, peor combinación, estado cooldown/respawn), reglas de negocio, cómo leer el panel, deuda técnica conocida |
| [`funcionalidades/anti-deteccion-click.md`](funcionalidades/anti-deteccion-click.md) | Click humano indetectable: por qué existe, los tres modos (click, drift, cursor persistente), reglas de negocio, limitaciones conocidas |
| [`funcionalidades/human-sessions.md`](funcionalidades/human-sessions.md) | Timeline horario de actividad: tres modos (HARDCORE/PASIVO/DISCONNECTED), calendario semanal, jitter de bordes, override manual, relogin automático, parámetros configurables |
| [`funcionalidades/noise.md`](funcionalidades/noise.md) | Sistema de ruido de navegación: por qué existe, destinos y rutas, wizard de creación, ciclo de ruido, reglas de negocio, pendientes (EP-N15, frecuencia MM:SS, peso configurable) |
| [`funcionalidades/oasis-reportes-ataques.md`](funcionalidades/oasis-reportes-ataques.md) | Reportes de ataques a oasis: parser multilenguaje, 13 endpoints (EP-01..EP-TD, EP-balance), balance perdido/robado, estadísticas globales y por oasis, distribución temporal por cadencia, reglas de negocio, 4 divergencias código/spec |
| [`funcionalidades/oasis-farming.md`](funcionalidades/oasis-farming.md) | Oasis farming automatizado: grupos de oasis, máquina de estados FARMING/ALERT/PAUSED, roles HARDCORE/MAINTENANCE/CLEANUP, wake-up inteligente — **spec ready-for-impl, módulo aún no implementado** |
| [`funcionalidades/simulador-combate.md`](funcionalidades/simulador-combate.md) | Simulador de combate: qué resuelve, fórmulas de batalla (moral, bonus, muralla), drops de animales de la naturaleza, cómo se interpreta el resultado y el ratio |
| [`funcionalidades/optimizador-balance-multiraid.md`](funcionalidades/optimizador-balance-multiraid.md) | Optimizador de balance multiraid: reparto óptimo de tropas entre varios objetivos, modos de cálculo, criterio de combinación ganadora y balance neto |

---

## Referencia de API

| Documento | Contenido |
|---|---|
| [`api/catalogo.md`](api/catalogo.md) | `GET /catalog/buildings`, `GET /catalog/troops/{tribe}`, exception handler global con traducciones |
| [`api/cuentas-mundos.md`](api/cuentas-mundos.md) | `POST/GET/PUT/DELETE /accounts`, `POST/GET/DELETE /accounts/{id}/worlds` — CRUD de cuentas y mundos |
| [`api/sesion.md`](api/sesion.md) | `POST`, `DELETE`, `GET /accounts/{id}/worlds/{id}/session` — login, logout y estado de sesión del bot |
| [`api/human-sessions.md`](api/human-sessions.md) | `GET/PUT /worlds/{id}/session/...` — timeline horario, override de modo y cancelación de override (Human Sessions) |
| [`api/noise.md`](api/noise.md) | `GET/PUT/POST/DELETE /worlds/{id}/noise/...` — config de ruido, destinos, rutas y pasos (EP-N01..EP-N10) |
| `docs/api/openapi.yaml` + `docs/api/API.md` | Contrato completo de la API (attack-reports EP-01..EP-TD, farm, catalog, session, noise EP-N01..EP-N14) — fuente de verdad de máquina |

---

## Procesos

| Documento | Contenido |
|---|---|
| [`procesos/operativa-por-fases.md`](procesos/operativa-por-fases.md) | Flujo de 5 fases para solicitudes |

---

## Gaps de documentación pendientes (detectados 2026-06-04)

Los siguientes módulos están implementados pero sin documentación en `documentacion/`. Se listan aquí para que el documentador los aborde en la próxima sesión.

| Módulo / Feature | Gap | Prioridad |
|---|---|---|
| ~~**Attack Reports (BD ataques oasis)**~~ | ✅ **Cerrado (2026-06-04)**: documentado en `funcionalidades/oasis-reportes-ataques.md` (negocio + módulo), `referencia-funciones/attack-report-adapter.md` y el manual `manual-usuario/oasis-reportes.html`. Junto con `attack-report-temporal-distribution.md` y `oasis-spawn-composition.md` cubre el módulo completo. | — |
| **Extensión Chrome (captura de reportes)** | Falta `funcionalidades/extension-chrome.md` (qué hace la extensión MV3, cómo instalarla, cómo envía reportes al bot). La extensión vive en `extension/`. | Media |
| **Task Order Randomization** | Spec: `docs/specs/task-order-randomization.md`. Sin documentación en `documentacion/`. | Baja |
| **noise-navigate-to-origin (EP-N15)** | Spec completo en `docs/specs/noise-navigate-to-origin.md`; mencionado como gap en `backend/noise.md`. Pendiente de implementación primero. | Baja (bloqueada por impl) |
| **noise-frequency-and-destination-weight** | Spec en `docs/specs/noise-frequency-and-destination-weight.md`; estado `ready-for-impl`. Pendiente de gate guardian + desarrollador-apis. | Baja (bloqueada por impl) |

---

## Convenciones

- Cada documento lleva al pie una marca de agua `🔖` con la fecha de su última revisión.
- Al crear o modificar una función: actualizar su entrada en `referencia-funciones/`.
- Al añadir módulo, feature o endpoint: enlazarlo desde este README.
- Al detectar divergencia código/spec: documentarla en el documento afectado bajo el encabezado **Divergencias código/spec**.

🔖 Última revisión: 2026-06-04 (documentadas tres áreas completas — **Oasis**: funcionalidades/oasis-reportes-ataques.md, funcionalidades/oasis-farming.md, ampliada oasis-spawn-mechanics.md, referencia-funciones/attack-report-adapter.md, manual oasis-reportes.html con 10 capturas reales; **Calculadora**: backend/simulador-combate.md, funcionalidades/simulador-combate.md + optimizador-balance-multiraid.md, referencia-funciones/combat-engine.md, manual calculadora.html con 10 capturas; **Sesión humana**: ampliada funcionalidades/human-sessions.md, manual human-sessions.html con 6 capturas. Cerrado el gap de Attack Reports. — entrada previa: backend/human-click.md, human-sessions.md, noise.md y sus docs de negocio + referencia-funciones/human-click.md)
