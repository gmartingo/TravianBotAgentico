---
name: capability-map
description: Mapa completo de capacidades del proyecto TravianBot — qué existe, dónde vive, quién lo usa
metadata:
  type: project
---

# Mapa de capacidades — TravianBot
Última recarga: 2026-05-26 (ronda 4 — añade fuente de datos de villages: upsert via ReadFarmListsUseCase como side effect de POST /farm/worlds/{wid}/farm-lists/read).
graphify 0.8.16 — grafo base de be2e449 (2668 nodos, 5752 aristas). Sección frontend añadida por lectura directa (graphify no cubre frontend/src aún).

CAMBIOS vs recarga anterior:
- NUEVO: Sección completa del frontend React (dashboard, i18n, cliente HTTP, modales, layout)
- sessionRegistry, LiveOverviewAdapter y feature sesión ya estaban documentados en be2e449

CAMBIOS PRINCIPALES vs recarga anterior:
- WorldRuntimePort YA TIENE implementación concreta: SessionRegistry (adapters/browser/session_registry.py)
- DbPort YA TIENE implementación concreta: AccountSQLiteAdapter (adapters/db/account_sqlite_adapter.py), con nuevo método get_account_password_cipher
- LiveOverviewAdapter YA está cableado con callables reales (session_registry.get_browser / get_world_server), no lambdas stub
- LoginUseCase AHORA tiene 3 campos: registry, db, fernet (Amendment A1 — descifrado en use case, no en adaptador)

---

## CAPA CORE — Entidades

| Entidad | Ruta | Campos clave | Consumidores |
|---|---|---|---|
| `Account` | `core/entities/account.py` | id, username, worlds | LoginUseCase, DbPort |
| `World` | `core/entities/world.py` | id, url, tribe | LoginUseCase |
| `Village` | `core/entities/village.py` | id, name | (futuras features) |
| `Tribe` (Enum) | `core/entities/tribe.py` | ROMANS, TEUTONS, GAULS, EGYPTIANS, HUNS | TranslationPort, JsonTranslationAdapter, catalog.py, tests |

---

## CAPA CORE — Excepciones (`core/exceptions.py`)

Todas heredan de `TravianBotError`. Cada una declara `error_code` (SCREAMING_SNAKE_CASE) y `params` (dict para interpolación i18n).

| Excepción | error_code | params | Consumidores directos |
|---|---|---|---|
| `TravianBotError` | TRAVIAN_BOT_ERROR | {} | Base de todas |
| `AccountNotFoundError` | ACCOUNT_NOT_FOUND | {account_id} | LoginUseCase, session endpoints, test_error_handler |
| `DuplicateAccountError` | DUPLICATE_ACCOUNT | {username} | AccountSQLiteAdapter |
| `WorldNotFoundError` | WORLD_NOT_FOUND | {world_id} | LoginUseCase, _verify_world_belongs_to_account |
| `SessionNotActiveError` | SESSION_NOT_ACTIVE | {} | LiveOverviewAdapter |
| `InvalidCredentialsError` | INVALID_CREDENTIALS | {username} | adapters/browser/login.py |
| `LoginFailedError` | LOGIN_FAILED | {username} | session_login handler → 401 (NUEVA: be2e449) |
| `VillageNotFoundError` | VILLAGE_NOT_FOUND | {village_id} | (futuro) |
| `FarmListNotFoundError` | FARM_LIST_NOT_FOUND | {farm_list_id} | (futuro) |
| `LoginError` | LOGIN_ERROR | {} | test_error_handler |
| `BrowserError` | BROWSER_ERROR | {} | driver.py |
| `DatabaseError` | DATABASE_ERROR | {} | (futuro) |
| `TroopNotFoundError` | TROOP_NOT_FOUND | {tribe, ordinal} | JsonTranslationAdapter, catalog.py, tests |
| `BuildingNotFoundError` | BUILDING_NOT_FOUND | {gid} | (definida, aún no usada en rutas) |

NOTA: `LoginFailedError` cubre tanto credenciales incorrectas como errores de red/timeout de zendriver. La API no distingue entre ambas (RN-13: prevenir enumeración de información). Mapea a 401.

---

## CAPA CORE — Puertos (contratos)

| Puerto | Ruta | Métodos abstractos | Implementado por |
|---|---|---|---|
| `BrowserPort` | `core/ports/browser_port.py` | start, stop, navigate, find_element, type_text, click | `ZendriverAdapter` (adapters/browser/driver.py) |
| `DbPort` | `core/ports/db_port.py` | get_account, list_accounts, save_account, delete_account, get_account_password_cipher (NUEVO be2e449), … | `AccountSQLiteAdapter` (adapters/db/account_sqlite_adapter.py) |
| `WorldRuntimePort` | `core/ports/world_runtime_port.py` | login(account,world)→bool, logout(world_id), is_active(world_id) | `SessionRegistry` (adapters/browser/session_registry.py) — NUEVO be2e449 |
| `TranslationPort` | `core/ports/translation_port.py` | get_building_name, get_all_buildings, get_troop_name, get_troop_names_by_tribe, get_message | `JsonTranslationAdapter` (adapters/translations/) |
| `GameDataPort` | `core/ports/game_data_port.py` | get_troop_stats, get_all_troop_stats, get_troop_upgrades, upsert_*, list_icons, get_icon_metadata | `GameDataSQLiteAdapter` (adapters/db/game_data_sqlite_adapter.py) |
| `OverviewHtmlSourcePort` | `core/ports/overview_html_source_port.py` | get_page_html(world_id, page), invalidate_cache(world_id) | `LiveOverviewAdapter`, `FixtureOverviewAdapter` |

### DbPort — get_account_password_cipher (NUEVO — Amendment A1)
- `get_account_password_cipher(account_id) -> bytes | None` — devuelve el BLOB Fernet cifrado de la contraseña. get_account() sigue devolviendo password="" (separación intencional).
- Implementado por: `AccountSQLiteAdapter.get_account_password_cipher` (SELECT password FROM accounts WHERE id=?)
- Único consumidor: `LoginUseCase.execute()` — nunca usar desde handlers de API.

### TranslationPort — detalle de API (clave para reutilización futura)
- `get_building_name(gid, lang) -> str` — nombre de un edificio. Fallback a 'es'.
- `get_all_buildings(lang) -> list[dict]` — todos los edificios con lang_servido.
- `get_troop_name(tribe, ordinal, lang) -> str` — nombre de tropa. Lanza TroopNotFoundError si no existe.
- `get_troop_names_by_tribe(tribe, lang) -> list[dict]` — todas las tropas de tribu con lang_servido.
- `get_message(code, lang, **params) -> str` — mensaje de error localizado. NUNCA lanza excepción.

---

## CAPA CORE — i18n

| Módulo | Ruta | Contenido | Importado por |
|---|---|---|---|
| `core/i18n/__init__.py` | `core/i18n/__init__.py` | (vacío, marca paquete) | — |
| `SUPPORTED_LANGUAGES` | `core/i18n/languages.py` | frozenset{"es","en","de","fr","ru"} | dependencies.py, main.py |
| `DEFAULT_LANGUAGE` | `core/i18n/languages.py` | "es" | dependencies.py, main.py, JsonTranslationAdapter |

### Catálogos JSON
| Catálogo | Ruta base | Ruta override | Descripción |
|---|---|---|---|
| buildings.json | `core/i18n/catalog/base/buildings.json` | `core/i18n/catalog/override/buildings.json` | Edificios con gid, alias, traducciones por idioma |
| troops.json | `core/i18n/catalog/base/troops.json` | `core/i18n/catalog/override/troops.json` | Tropas con clave TRIBE_ordinal, traducciones por idioma |
| messages.json | `core/i18n/catalog/base/messages.json` | `core/i18n/catalog/override/messages.json` | Mensajes de error por error_code y por idioma |

Override gana entry-by-entry sobre base (merge dict superficial en __init__ del adapter).

---

## CAPA CORE — Casos de uso

| Use Case | Ruta | Puertos que consume | Excepciones que lanza |
|---|---|---|---|
| `LoginUseCase` | `core/use_cases/login_use_case.py` | DbPort, WorldRuntimePort, Fernet (cryptography) | AccountNotFoundError, WorldNotFoundError, LoginFailedError (cipher=None o InvalidToken) |
| `LogoutUseCase` | `core/use_cases/login_use_case.py` | WorldRuntimePort | (ninguna propia, idempotente) |

### LoginUseCase — flujo detallado (Amendment A1)
1. `db.get_account(account_id)` → Account (password="") | None
2. `db.get_account_password_cipher(account_id)` → bytes | None
3. `decrypt_password(fernet, cipher)` → str (en memoria, ventana mínima)
4. `_find_world(account, world_id)` → World | WorldNotFoundError
5. `registry.login(account_con_password, world)` → bool
- Si cipher=None → LoginFailedError (BD corrupta, no debería ocurrir con NOT NULL)
- Si InvalidToken → LoginFailedError (SECRET_KEY cambiada desde que se guardó la contraseña)
- Si registry.login()=False → el handler lanza LoginFailedError (el use case devuelve False)
- REGLA: el descifrado ocurre en el use case, NO en el adaptador SQLite. El adaptador es opaco al contenido del BLOB.

---

## CAPA ADAPTERS — Browser

| Artefacto | Ruta | Responsabilidad | Usa |
|---|---|---|---|
| `ZendriverAdapter` | `adapters/browser/driver.py` | Implementa BrowserPort. Capas anti-detección completas. | zendriver, BrowserPort |
| `create_browser(profile_dir)` | `adapters/browser/driver.py` | Standalone: arranca Chrome con anti-detección. Usada por login.py. | zendriver, _detect_chrome_path, _get_user_agent |
| `human_delay(min_ms, max_ms)` | `adapters/browser/driver.py` | Pausa aleatoria 500-900 ms. | asyncio |
| `human_type(element, text)` | `adapters/browser/driver.py` | Escritura char-a-char 80-220 ms. | asyncio |
| `_kill_orphan_chrome(profile_dir)` | `adapters/browser/driver.py` | Mata Chrome del perfil indicado por PID (no por nombre). | subprocess |
| `_detect_chrome_path()` | `adapters/browser/driver.py` | Primera ruta válida de Chrome por OS. | os.path |
| `_detect_chrome_full_version(path)` | `adapters/browser/driver.py` | Lee versión real de Chrome (PowerShell en Win, --version en otros). | subprocess |
| `_get_user_agent()` | `adapters/browser/driver.py` | UA coherente con OS + versión Chrome real. | platform, _detect_chrome_full_version |
| `login.py` | `adapters/browser/login.py` | Flujo de login en Travian usando browser. Devuelve (bool, Browser|None). | create_browser, human_delay, human_type |
| `SessionRegistry` | `adapters/browser/session_registry.py` | NUEVO (be2e449). Implementa WorldRuntimePort. Singleton en app.state.world_runtime_port. Dict {world_id: (Browser, World)}. | login_module, WorldRuntimePort, LiveOverviewAdapter (vía set_live_adapter) |

### SessionRegistry — métodos clave
- `login(account, world) → bool` (async): cierra sesión previa si existe → llama login_module.login → almacena (browser, world) → invalida caché
- `logout(world_id) → None` (async): idempotente, solo browser.stop(). NUNCA navega URLs de Travian.
- `is_active(world_id) → bool`: O(1), sincrónico
- `get_browser(world_id) → zd.Browser | None`: callable para LiveOverviewAdapter
- `get_world_server(world_id) → str`: callable para LiveOverviewAdapter (devuelve world.server o "")
- `set_live_adapter(adapter)`: inyección post-construcción desde main.py lifespan (evita dependencia circular)
- `_invalidate_cache(world_id)`: helper interno, no-op si _live_adapter es None

### Limitaciones conocidas de SessionRegistry (documentadas, no bugs)
- EC-12: si Chrome muere tras login exitoso, is_active() devuelve True (no detecta muerte del browser)
- EC-13: sesiones in-memory, se pierden en reinicio del servidor
- EC-10: sin lock (acepta riesgo de carrera — 1 usuario, no ocurre en la práctica)

---

## CAPA ADAPTERS — Translations (NUEVA — feature i18n-backend)

| Artefacto | Ruta | Responsabilidad |
|---|---|---|
| `JsonTranslationAdapter` | `adapters/translations/json_translation_adapter.py` | Implementa TranslationPort. Carga catálogos JSON (base + override) en memoria al init. Lookups O(1). |

Consumidores de JsonTranslationAdapter:
- `adapters/api/main.py` → lifespan: instancia el adaptador y lo guarda en `app.state.translation_port`
- `adapters/api/routes/catalog.py` → a través de `get_translation_port` (inyección de dependencias FastAPI)
- `adapters/api/main.py` → exception handler: `request.app.state.translation_port.get_message()`

---

## CAPA ADAPTERS — API

| Artefacto | Ruta | Responsabilidad | Consume |
|---|---|---|---|
| `app` (FastAPI) | `adapters/api/main.py` | App principal con lifespan, middlewares y exception handler | catalog_router, accounts_router, JsonTranslationAdapter, SessionRegistry, TravianBotError, ERROR_HTTP_MAP |
| `lifespan` | `adapters/api/main.py` | Singletons: JsonTranslationAdapter (translation_port), AccountSQLiteAdapter (db_port), LiveOverviewAdapter o FixtureOverviewAdapter (html_source_port), SessionRegistry (world_runtime_port). Cableado SessionRegistry↔LiveOverviewAdapter. | todos los adaptadores |
| `add_security_headers` middleware | `adapters/api/main.py` | X-Request-ID, X-API-Version, X-Content-Type-Options, X-Frame-Options en TODAS las respuestas | — |
| `add_catalog_cache_control` middleware | `adapters/api/main.py` | Cache-Control: public, max-age=3600 en /catalog/* 2xx | — |
| `travian_bot_error_handler` | `adapters/api/main.py` | Handler global TravianBotError: traduce mensaje, mapea HTTP status, traza enmascarada si X-Verbose:true | TranslationPort.get_message, ERROR_HTTP_MAP, _mask_frame_locals |
| `_mask_frame_locals` | `adapters/api/main.py` | Enmascara passwords/tokens/cipher/secret/chrome-profile-dirs/URLs Travian en trazas verbose. Ampliado (be2e449): añade cipher, secret. | re (regex) |
| `get_language` | `adapters/api/dependencies.py` | Valida Accept-Language (400 si falta o no soportado). Fuente de verdad: SUPPORTED_LANGUAGES | SUPPORTED_LANGUAGES |
| `get_language_optional` | `adapters/api/dependencies.py` | Header opcional, None si ausente | SUPPORTED_LANGUAGES |
| `resolve_language` | `adapters/api/dependencies.py` | Override ?lang= > Accept-Language > None (todos). Usado en endpoints de catálogo. | SUPPORTED_LANGUAGES |
| `get_translation_port` | `adapters/api/dependencies.py` | Devuelve app.state.translation_port. Para inyección en handlers. | Request.app.state |
| `get_db_port` | `adapters/api/dependencies.py` | Devuelve app.state.db_port (AccountSQLiteAdapter). | Request.app.state |
| `get_world_runtime_port` | `adapters/api/dependencies.py` | NUEVO (be2e449). Devuelve app.state.world_runtime_port (SessionRegistry). Lanza 503 si no disponible. | Request.app.state |
| `get_game_data_port` | `adapters/api/dependencies.py` | Devuelve app.state.game_data_port (GameDataSQLiteAdapter). | Request.app.state |
| `get_fernet` | `adapters/api/dependencies.py` | Devuelve instancia Fernet desde TRAVIAN_BOT_SECRET_KEY. Usado por session_login. | os.environ |
| `ERROR_HTTP_MAP` | `adapters/api/error_codes.py` | Dict error_code → HTTP status. Incluye LOGIN_FAILED→401 (NUEVO be2e449). | main.py (exception handler) |
| `DEFAULT_ERROR_STATUS` | `adapters/api/error_codes.py` | 500 (fallback si error_code no está en el mapa) | main.py (exception handler) |
| `catalog_router` | `adapters/api/routes/catalog.py` | GET /catalog/buildings + GET /catalog/troops/{tribe} + GET /catalog/troops/{tribe}/stats | TranslationPort, GameDataPort, get_language, resolve_language |
| `accounts_router` | `adapters/api/routes/accounts.py` | CRUD cuentas+mundos + 3 endpoints de sesión (NUEVO be2e449). 11 endpoints totales. | DbPort, WorldRuntimePort, Fernet |
| `SessionStatusResponse` | `adapters/api/routes/accounts.py` | NUEVO (be2e449). Schema Pydantic: {active: bool, world_id: int, account_id: int}. | session_login, session_status |
| `_verify_world_belongs_to_account` | `adapters/api/routes/accounts.py` | NUEVO (be2e449). Helper async compartido por los 3 endpoints de sesión. Verifica existencia de cuenta y pertenencia de mundo. Siempre 404, nunca 403 (no revela existencia en otra cuenta). | session_login, session_logout, session_status |
| `BuildingItem`, `BuildingsCatalogResponse` | `adapters/api/routes/catalog.py` | DTOs Pydantic para /catalog/buildings. Diseñados abiertos (extensibles). | — |
| `TroopItem`, `TroopsCatalogResponse` | `adapters/api/routes/catalog.py` | DTOs Pydantic para /catalog/troops/{tribe}. Diseñados abiertos. | — |
| `GET /health` | `adapters/api/main.py` | Endpoint de salud. No requiere Accept-Language. | — |

### Endpoints de sesión (NUEVOS — be2e449)
- `POST /accounts/{account_id}/worlds/{world_id}/session` → 200 SessionStatusResponse | 401 (login fallido) | 404 (no existe/no pertenece) | 503 (registry no disponible)
- `DELETE /accounts/{account_id}/worlds/{world_id}/session` → 204 (idempotente)
- `GET /accounts/{account_id}/worlds/{world_id}/session` → 200 SessionStatusResponse

NOTA IMPORTANTE: POST es síncrono (~3-10s por delays anti-detección). El cliente debe tener timeout ≥ 30s. NO requieren Accept-Language (son operativos, no devuelven texto localizado).

---

## CAPA DB

| Artefacto | Ruta | Responsabilidad |
|---|---|---|
| `AccountSQLiteAdapter` | `adapters/db/account_sqlite_adapter.py` | Implementa DbPort. CRUD de cuentas y mundos. Cifrado Fernet para passwords. Singleton en app.state.db_port. |
| `get_account_password_cipher` | `adapters/db/account_sqlite_adapter.py` | NUEVO (be2e449 Amendment A1). SELECT password BLOB de accounts. Solo para LoginUseCase. |
| `GameDataSQLiteAdapter` | `adapters/db/game_data_sqlite_adapter.py` | Implementa GameDataPort. Tablas: troop_stats, troop_upgrades, icon_metadata. |
| `database.py` | `adapters/db/database.py` | get_connection() — helper bajo nivel (no implementa DbPort). Abre conexión aiosqlite+WAL. |

---

## TESTS

| Test | Ruta | Cubre |
|---|---|---|
| `test_catalog_buildings.py` | `tests/` | GET /catalog/buildings (idioma válido, ausente, no soportado) |
| `test_catalog_troops.py` | `tests/` | GET /catalog/troops/{tribe} (válida, tribu inválida, tribu sin tropas) |
| `test_error_handler.py` | `tests/` | Exception handler global (traducción, HTTP codes, verbose) |
| `test_health.py` | `tests/` | GET /health |
| `test_json_translation_adapter.py` | `tests/unit/` | JsonTranslationAdapter (buildings, troops, messages, fallback, override) |
| `test_exceptions.py` | `tests/unit/` | Excepciones de dominio (error_code, params) |
| `test_entities.py` | `tests/unit/` | Entidades de dominio |
| `test_login_use_case.py` | `tests/unit/` | LoginUseCase con Fernet real (15 tests: descifrado, InvalidToken, cipher nulo, account/world not found, login fallido) |
| `test_logout_use_case.py` | `tests/unit/` | LogoutUseCase |
| `test_session_registry.py` | `tests/unit/` | NUEVO (be2e449). 15 tests unitarios de SessionRegistry (login/logout, re-login, invalidación caché, is_active, get_browser, get_world_server) |
| `test_session_api.py` | `tests/unit/` | NUEVO (be2e449). 19 tests de API con TestClient (14 spec + 2 Amendment A1 + 3 helper verify). MockRegistry sin Chrome. |
| `test_account_sqlite_adapter.py` | `tests/unit/` | NUEVO parcial (be2e449). Incluye 3 tests de get_account_password_cipher. |
| `test_accounts_api.py` | `tests/` | Incluye FakeRuntimePort (MockRegistry) para aislar endpoints de sesión en tests de integración. |
| `test_config_zendriver.py` | `tests/antideteccion/` | Configuración anti-detección de zendriver |
| `test_ca20_catalogo_no_en_browser.py` | `tests/antideteccion/` | Verifica que catalog endpoints NO usan el browser |
| `test_session_antideteccion.py` | `tests/antideteccion/` | NUEVO (be2e449). Tests estáticos de anti-detección para SessionRegistry: no-sleeps, no-log-credenciales, no-navega-URLs, logout-solo-stop, isolación por world_id, no-selectores-por-texto, 401-sin-distinguir-causa. |

Suite total tras be2e449: 732 passed, 9 fallos preexistentes no relacionados con sesión.

---

## RELACIONES CLAVE — feature sesión (grafo de dependencias — be2e449)

```
POST /accounts/{id}/worlds/{id}/session (session_login handler)
  → _verify_world_belongs_to_account (db)      [→ AccountNotFoundError / WorldNotFoundError]
  → LoginUseCase(registry, db, fernet).execute()
      → db.get_account(id)                     [→ AccountNotFoundError]
      → db.get_account_password_cipher(id)     [→ LoginFailedError si None]
      → decrypt_password(fernet, cipher)       [→ LoginFailedError si InvalidToken]
      → registry.login(account_con_password, world)  [→ False si login fallido]
          → login_module.login(account, world)  [Chrome real, ~3-10s]
          → _invalidate_cache(world_id)         [LiveOverviewAdapter.invalidate_cache]
  → LoginFailedError si result=False            [→ 401]
  → SessionStatusResponse(active=True, ...)    [→ 200]

SessionRegistry (singleton en app.state.world_runtime_port)
  IMPLEMENTA: WorldRuntimePort
  DELEGA EN:  adapters/browser/login.py (login_module)
  PROVEE A:   LiveOverviewAdapter (get_browser + get_world_server callables, via set_callables)
  REFERENCIA: LiveOverviewAdapter._live_adapter (para invalidar caché en login/logout)

main.py lifespan (orden de creación obligatorio):
  1. AccountSQLiteAdapter → app.state.db_port
  2. LiveOverviewAdapter(stubs) o FixtureOverviewAdapter → app.state.html_source_port
  3. SessionRegistry → app.state.world_runtime_port
  4. (si live) html_source_port.set_callables(registry.get_browser, registry.get_world_server)
  5. (si live) registry.set_live_adapter(html_source_port)
```

## RELACIONES CLAVE — i18n-backend (grafo de dependencias)

```
core/i18n/languages.py
  SUPPORTED_LANGUAGES, DEFAULT_LANGUAGE
      ← importado por → adapters/api/dependencies.py (get_language)
      ← importado por → adapters/api/main.py (_extract_lang en exception handler)
      ← importado por → adapters/translations/json_translation_adapter.py (DEFAULT_LANGUAGE)

core/ports/translation_port.py
  TranslationPort (ABC)
      ← implementado por → adapters/translations/json_translation_adapter.py (JsonTranslationAdapter)
      ← consumido por → adapters/api/routes/catalog.py (via get_translation_port)
      ← consumido por → adapters/api/main.py (exception handler via app.state.translation_port)

adapters/api/main.py
  lifespan → instancia JsonTranslationAdapter → app.state.translation_port
  exception handler → app.state.translation_port.get_message(error_code, lang, **params)
                    → ERROR_HTTP_MAP[error_code] → HTTP status

core/exceptions.py (TravianBotError y subclases)
      → error_code string → ERROR_HTTP_MAP (adapters/api/error_codes.py) → HTTP status
      → error_code string + params → messages.json → get_message() → texto localizado

adapters/api/routes/catalog.py
      → get_language (dependencies.py) → SUPPORTED_LANGUAGES
      → get_translation_port (dependencies.py) → app.state.translation_port
      → TranslationPort.get_all_buildings / get_troop_names_by_tribe
      → TroopNotFoundError → capturada localmente → 404 HTTPException
```

---

## CAPA GAME DATA (añadida 2026-05-25)

| Artefacto | Ruta | Responsabilidad |
|---|---|---|
| `GameDataPort` | `core/ports/game_data_port.py` | Puerto ABC para stats numéricos de tropas, upgrades de herrería e iconos. Métodos: get_troop_stats, get_all_troop_stats, get_troop_upgrades, upsert_*, list_icons, get_icon_metadata. |
| `GameDataSQLiteAdapter` | `adapters/db/game_data_sqlite_adapter.py` | Implementa GameDataPort con aiosqlite. Tablas: troop_stats, troop_upgrades, icon_metadata. Recibe conn como DI. Singleton en app.state.game_data_port. |
| `get_game_data_port` | `adapters/api/dependencies.py:88` | Dependencia FastAPI para inyectar GameDataPort desde app.state. |
| `game_data_router` | `adapters/api/routes/game_data.py` | GET /catalog/troops/{tribe}/stats + GET /catalog/icons. DTOs: TroopStatsItem, TroopStatsCatalogResponse, IconItem, IconListResponse. Consume GameDataPort + TranslationPort. |
| `KirilloidScraper` | `adapters/scraper/kirilloid_scraper.py` | Scraper de kirilloid.ru. Funciones puras (sin browser, testables): _parse_time, _parse_int, _parse_int_or_none, _remove_background, _merge_troop_names. Funciones con browser: _parse_main_table, _parse_upgrade_table, _capture_troop_icon, _capture_stat_icons, _capture_upgrade_icons, _wait_for_element. Patrón: importaciones de zendriver solo en runtime (no a nivel de módulo). |
| `scripts/load_kirilloid.py` | `scripts/load_kirilloid.py` | Script CLI que orquesta el scraping completo. |

### WorldRuntimePort — IMPLEMENTADO por SessionRegistry (be2e449)
- `SessionRegistry` en `adapters/browser/session_registry.py` implementa login/logout/is_active.
- Singleton en `app.state.world_runtime_port` (instanciado en lifespan de main.py).
- Login real delega en `adapters/browser/login.py` (NO modificado por esta feature).

### DbPort — IMPLEMENTADO por AccountSQLiteAdapter
- `AccountSQLiteAdapter` en `adapters/db/account_sqlite_adapter.py` implementa todo DbPort.
- Nuevo método (Amendment A1): `get_account_password_cipher(account_id) → bytes | None`
- Tablas: accounts (id, email, username, password BLOB Fernet), worlds (id, account_id, server, tribe, url)
- `database.py` sigue siendo helper de conexión de bajo nivel, no implementa DbPort.

### Village entity — campos actuales
`core/entities/village.py`: id, world_id, data_id (Travian game id), name, x, y. Sin campos de recursos, producción ni estado dinámico.
NOTA: VillageInfo (DTO en village_map.py) tiene game_id, name, x, y — distinta a la entidad Village.

### Capa overview (feature lectura-overview-tronco-comun)
- `core/ports/overview_html_source_port.py` — OverviewHtmlSourcePort (ABC), enum OverviewPage
- `adapters/browser/fixture_overview_adapter.py` — FixtureOverviewAdapter: sirve HTML desde disco
- `adapters/browser/live_overview_adapter.py` — LiveOverviewAdapter: navega Travian con Chrome. AHORA cableado (be2e449): set_callables(registry.get_browser, registry.get_world_server) desde main.py. Ya NO usa lambdas stub. Tiene método set_callables(get_browser, get_world_server) añadido en be2e449.
- `core/use_cases/village_map.py` — VillageMapUseCase + VillageOverviewParser + VillageInfo DTO
- Nuevas excepciones: OverviewPageNotLoadedError, OverviewFixtureNotFoundError

---

---

## CAPA FRONTEND — Dashboard React (`frontend/`)

### Stack y estructura
- React + Vite + Tailwind CSS v4
- `frontend/src/styles/` — tokens de diseño (CSS custom properties: `--accent`, `--surface`, `--bg`, `--text`, `--border`, `--radius-*`, `--dur-*`, etc.)
- `frontend/src/i18n/` — sistema i18n completo (25 idiomas, 3 RTL)
- `frontend/src/api/client.js` — cliente HTTP centralizado
- `frontend/src/components/` — componentes de layout y UI
- `frontend/src/pages/` — páginas/pantallas de la SPA
- `frontend/src/hooks/` — hooks custom reutilizables
- `frontend/scripts/uishot.mjs` — herramienta de test de screenshots (puppeteer-core)

---

### i18n Frontend

| Artefacto | Ruta | Contenido | Consumidores |
|---|---|---|---|
| `I18nProvider` | `frontend/src/i18n/index.jsx` | Context Provider. Estado: lang (localStorage['lang'] o 'es'). Aplica lang+dir a `<html>`. Fallback: clave activa → 'es' → clave literal. | todos los componentes |
| `useI18n()` | `frontend/src/i18n/index.jsx` | Hook: devuelve `{ t, lang, setLang }`. t(key, vars) interpola `{variable}`. Soporte plural vía `.pl` suffix. | todos los componentes |
| `translate(catalog, lang, key, vars)` | `frontend/src/i18n/index.jsx` | Función pura exportada (sin React). Útil para utils fuera de contexto. | (disponible para tests y utils) |
| `LANGUAGES` | `frontend/src/i18n/languages.js` | Array de 25 `{ code, name, rtl }`. `name` = endónimo del idioma. | LangPicker, I18nContext |
| `isRTL(code)` | `frontend/src/i18n/languages.js` | Devuelve true para ar/he/fa. | I18nProvider |
| Catálogos por idioma | `frontend/src/i18n/catalog/<lang>.js` | 25 ficheros (es.js, en.js, de.js, …). Keys dot-notation: `'nav.accounts'`, `'wizard.title'`, `'modal.deleteAccount.body'`, etc. | CATALOG en index.js |
| `index.js` (catálogo) | `frontend/src/i18n/catalog/index.js` | Re-exporta todos los catálogos como objeto `{ es, en, de, … }`. | I18nProvider (CATALOG) |

NOTA IMPORTANTE: el i18n frontend es INDEPENDIENTE del i18n backend (core/i18n/). Los 25 idiomas son los mismos, pero el frontend tiene su propia copia de traducciones de UI. No hay endpoint de traducción para la UI; el catálogo se carga en bundle.

---

### Cliente HTTP

| Artefacto | Ruta | Contratos |
|---|---|---|
| `api` (object) | `frontend/src/api/client.js` | Métodos: `getAccounts`, `getAccount`, `createAccount`, `updateAccount`, `deleteAccount`, `getWorlds`, `createWorld`, `deleteWorld`, `getSession`, `startSession`, `stopSession` |
| `ApiError` (class) | `frontend/src/api/client.js` | Extiende `Error`. Campos: `status` (HTTP), `detail` (mensaje FastAPI). Lanzada en 4xx/5xx. |
| `buildHeaders()` | `frontend/src/api/client.js` | Añade `Content-Type: application/json` + `Accept-Language: <lang>` en CADA petición. |
| `parseResponse(res)` | `frontend/src/api/client.js` | 204 → null. 2xx → json/text. Error → extrae `{detail}` de FastAPI y lanza ApiError. |
| `request(method, path, body, extraHeaders)` | `frontend/src/api/client.js` | Función interna. Error de red → ApiError('error.network', 0, …). |

BASE URL: `/api` (proxy Vite retira `/api` → `:8000`).
REGLA: sin llamada directa a `fetch` fuera de `client.js`; todos los consumidores usan `api.*`.
Consumidores actuales: WizardModal, AccountsListPage, AccountDetailPage, EditAccountModal, AddWorldModal.

---

### Layout (shell)

| Componente | Ruta | Responsabilidad |
|---|---|---|
| `ManagementShell` | `frontend/src/components/layout/ManagementShell.jsx` | Shell del modo Gestión. Layout: Topbar (100% ancho) + `<Outlet>`. Sidebar visible en ≥768px; colapsada (iconos sólo, 48px) en 768–1023px; oculta en <768px. |
| `Topbar` | `frontend/src/components/layout/Topbar.jsx` | Barra superior. Incluye LangPicker + ThemeToggle. Presente en todas las pantallas del shell. |
| `Sidebar` | `frontend/src/components/layout/Sidebar.jsx` | Menú de navegación lateral. Props: `collapsed` (bool). Accesos: Cuentas (/cuentas), (futuras secciones). |
| `useWindowSize()` | `frontend/src/hooks/useWindowSize.js` | Hook: devuelve `{ width, height }`. Suscribe a `resize`. Usado por ManagementShell para responsive. |
| `useTheme()` | `frontend/src/hooks/useTheme.js` | Hook: `{ theme, toggleTheme }`. Persiste en localStorage. Aplica clase `dark` a `<html>`. |

Rutas React Router:
- `/cuentas` → AccountsListPage (dentro de ManagementShell)
- `/cuentas/nueva` → NewAccountPage (dentro de ManagementShell) — abre WizardModal
- `/cuentas/:id` → AccountDetailPage (dentro de ManagementShell)
- `/mundos/:worldId` → WorldSpacePage (FUERA del ManagementShell — tiene su propia Topbar mínima)

---

### Páginas

| Página | Ruta | Estados/Notas |
|---|---|---|
| `AccountsListPage` | `frontend/src/pages/AccountsListPage.jsx` | 4 estados: loading (skeleton), data (tabla ≥md / tarjetas <md), empty, error. Llama `api.getAccounts()`. Abre `EditAccountModal` (editar) y `DeleteConfirmModal` inline (borrar). |
| `NewAccountPage` | `frontend/src/pages/NewAccountPage.jsx` | Página contenedora que renderiza `WizardModal`. Navega a /cuentas al salir del wizard. |
| `AccountDetailPage` | `frontend/src/pages/AccountDetailPage.jsx` | Detalle de cuenta con lista de mundos. Máquina de estados de sesión por mundo: `idle → connecting → active → stopping → idle` (+ `error`). POST /session es síncrono (~30s). Abre `AddWorldModal`, `EditAccountModal`, `ConfirmDeleteModal`. |
| `WorldSpacePage` | `frontend/src/pages/WorldSpacePage.jsx` | Placeholder de S9 (Etapa 1). Sin sidebar. Topbar mínima con "← Mundos". Contenido real en Etapa 2. |

---

### Componentes UI

| Componente | Ruta | Patrón reutilizable |
|---|---|---|
| `WizardModal` | `frontend/src/components/ui/WizardModal.jsx` | Wizard 2 pasos (crear cuenta + añadir mundo). Focus trap, ESC, backdrop click, aria-modal. Stepper visual. Tiene COPIA INTERNA de parseServerUrl, isValidServerUrl, Spinner, useFocusTrap, FOCUSABLE (ver code-smell abajo). |
| `EditAccountModal` | `frontend/src/components/ui/EditAccountModal.jsx` | Modal edición de cuenta. Focus trap, ESC, toggle-password con "Cambiar contraseña". USA uiUtils (Spinner, useFocusTrap, showToast). |
| `AddWorldModal` | `frontend/src/components/ui/AddWorldModal.jsx` | Modal añadir mundo. Debounce de 200ms en parseServerUrl. USA uiUtils (parseServerUrl, isValidServerUrl, Spinner, useFocusTrap, showToast). |
| `ConfirmDeleteModal` | `frontend/src/components/ui/ConfirmDeleteModal.jsx` | Modal confirmación de borrado (sirve tanto para cuenta como mundo, polimórfico vía props). Estado 409 inline (error-block). USA uiUtils (Spinner, useFocusTrap, showToast). |
| `LangPicker` | `frontend/src/components/ui/LangPicker.jsx` | Selector idioma. 25 idiomas con buscador/filtro. Animación zoom. Persistencia localStorage. Lucide-react: Globe, Check. |
| `ThemeToggle` | `frontend/src/components/ui/ThemeToggle.jsx` | Botón ☀/🌙. Lucide-react: Sun, Moon. useTheme() + useI18n(). |

### uiUtils.jsx — utilidades transversales (THE shared module)

`frontend/src/components/ui/uiUtils.jsx` exporta:
- `parseServerUrl(raw)` → "ts1 · x1 · international" | null
- `isValidServerUrl(raw)` → boolean
- `Spinner({ size, className })` — SVG animado. Usa `animation: 'spin 0.6s linear infinite'`
- `BadgeSpinner()` — spinner de 11px para badges de estado de sesión
- `FOCUSABLE` — selector CSS de elementos focusables
- `useFocusTrap(ref, active)` — hook de focus trap para modales
- `showToast(msg)` — toast DOM global 3s (crea/reutiliza `#__travianbot-toast`)

Consumidores de uiUtils: EditAccountModal, AddWorldModal, ConfirmDeleteModal, AccountDetailPage.

---

### Patrones de modal (para reutilización futura)

Todos los modales del proyecto siguen este contrato:
1. `role="dialog"`, `aria-modal="true"`, `aria-labelledby="<id>-title"`
2. Focus trap vía `useFocusTrap(ref, active)` de uiUtils
3. ESC cierra (no si hay operación en curso)
4. Click en backdrop cierra (no si hay operación en curso)
5. `triggerRef?.current?.focus()` al cerrar (devuelve foco al elemento que lo abrió)
6. Backdrop: `fixed inset-0 z-[400]`; panel: `bg-[var(--surface)] rounded-[var(--radius-lg)] shadow-[var(--shadow-lg)]`
7. CERO texto hardcodeado — todo vía `t()`

Para implementar un nuevo modal: importar `useFocusTrap`, `Spinner` y `showToast` de uiUtils, no duplicarlos.

---

## 4 BLOQUES OVERVIEW — implementados (ronda 3)

Rutas activas en `adapters/api/routes/`:
- `game_overview.py` → `GET /game/overview/{world_id}` — OverviewUseCase + OverviewParser + VillageMapUseCase
- `game_resources.py` → `GET /game/resources/{world_id}` — ResourcesUseCase + ResourcesParser
- `game_culture_points.py` → `GET /game/culture-points/{world_id}` — CulturePointsUseCase + CulturePointsParser
- `game_troops.py` → `GET /game/troops/{world_id}` — TroopsUseCase + TroopsParser

DTOs en `core/dtos/`: `overview_dto.py`, `resources_dto.py`, `culture_points_dto.py`, `troops_dto.py` (todos frozen=True).
Parsers en `adapters/browser/parsers/`: `overview_parser.py`, `resources_parser.py`, `culture_points_parser.py`, `troops_parser.py`, `_common.py` (helpers compartidos).
Dependencia compartida por los 4: `get_html_source_port` en `dependencies.py` → `OverviewHtmlSourcePort`.

`core/scheduling/__init__.py` — existe y el paquete tiene contenido: `task_queue.py` (TaskQueue) y `world_agent.py` (WorldAgent farm-only). IMPLEMENTADOS en rama develop (feature farm-lists, 2026-05-26).

## CAPA FARM LISTS — implementada (rama develop, actualizado 2026-05-27)

### Cambios post-implementación (auditados 2026-05-27, SIN consulta previa a palantir)

#### Cambio 1 — Aliases en `_serialize_send_event` (farm.py líneas 204-207)
Tres campos alias añadidos al dict de retorno sin borrar originales:
- `sent_at` = alias de `timestamp`
- `slots_sent` = alias de `being_raided_current`
- `deactivated_slots` = alias de `bot_disabled_slots`

VEREDICTO palantir: lógica de presentación introducida directamente en el serializador de la capa API.
No hay patrón previo de aliases en ningún otro serializador del proyecto. El problema no es la funcionalidad
sino la técnica: los nombres canónicos del dominio (being_raided_current, bot_disabled_slots) son correctos;
los aliases son conveniencia del frontend. DEUDA: si el frontend cambia sus expectativas,
habrá que tocar la capa API — esto acopla API al vocabulario de un cliente específico.

#### Cambio 2 — Campos agregados en `_serialize_farm_list` (farm.py líneas 165-182)
`total_bounty` (suma) y `avg_bounty_per_send` (promedio de activos) calculados en el serializador.
`last_send_time` siempre `None` (placeholder explícito pendiente de implementación real).

VEREDICTO palantir: los cálculos pertenecen a la capa de presentación/aplicación, no al core.
No hay use case de agregados en core/use_cases/farm_lists.py — la lógica se ha colocado
en el serializador de la capa API, lo que es coherente con el nivel de complejidad actual.
`total_bounty` y `average_raid_bounty` YA EXISTEN en FarmSlot (entidad de dominio) como campos nativos
calculados por el adaptador de BD. Los agregados de farm list son sumas/promedios de esos campos —
cálculo trivial no merecedor de un use case propio.

#### Cambio 3 — Endpoint toggle scheduler (farm.py líneas 361-380)
`POST /farm/worlds/{world_id}/schedulers/{scheduler_id}/toggle` — nuevo endpoint.
Patrón: get → flip is_enabled → update_scheduler → serializa → 200.
No hay use case en core/ — la lógica (get + flip + save) ocurre directamente en el handler.

VEREDICTO palantir: patrón coherente con el resto del router de farm (otros endpoints simples
también operan directo sobre db sin use case). PUT /worlds/{wid}/schedulers/{sid} ya hacía
get + mutación + update_scheduler, así que el toggle es una variante simplificada del mismo patrón.

#### Cambio 4 — Filtro scheduler_id en slot-events (farm.py líneas 709-734)
Nuevo param opcional `scheduler_id` en `GET /farm/worlds/{world_id}/slot-events`.
Implementación: fetch all (page_size=100_000) + filter en Python + paginación manual.

VEREDICTO palantir: DIVERGENCIA CRÍTICA respecto al patrón ya establecido.
`get_farm_list_send_history` (adaptador de BD, línea 971-1005) ya tiene `scheduler_id`
como filtro nativo en SQL con paginación real. `get_slot_events` (línea 740-770) NO tiene
ese parámetro en el puerto ni en el adaptador — por eso el handler lo filtra en Python.
El puerto FarmListDbPort.get_slot_events tampoco tiene scheduler_id en su firma abstracta.
Esto es asimetría entre los dos endpoints de historial y rompe el patrón de la BD.
FIX RECOMENDADO: añadir `scheduler_id: int | None = None` a FarmListDbPort.get_slot_events,
implementarlo en FarmListSQLiteAdapter.get_slot_events (igual que get_farm_list_send_history),
y eliminar el fetch-all + filter en Python del handler.


### Backend implementado
- `core/entities/farm_list.py` — FarmSlot, FarmList, BotSlotStatus, SlotEvent
- `core/entities/farm_scheduler.py` — FarmScheduler (id, world_id, name, interval_min_ms, interval_max_ms, is_enabled, last_run, next_run, execution_count, farm_list_ids)
- `core/entities/farm_list_send_event.py` — FarmListSendEvent (id, farm_list_id, farm_list_name, world_id, timestamp, status, being_raided_current/total, triggered_by, scheduler_id, bot_disabled_slots, loot_*)
- `core/entities/farm_list_send_result.py` — FarmListSendResult (farm_list_id, status, being_raided_current/total)
- `core/entities/task.py` — TaskType, Task
- `core/ports/farm_list_browser_port.py` — FarmListBrowserPort (ABC)
- `core/ports/farm_list_db_port.py` — FarmListDbPort (ABC)
- `core/scheduling/task_queue.py` — TaskQueue
- `core/scheduling/world_agent.py` — WorldAgent (seed_from_schedulers, run, _execute, _reschedule_farm, run_now, request_stop, status)
- `core/use_cases/farm_lists.py` — todos los use cases: GetFarmListsUseCase, ReadFarmListsUseCase, SendFarmListUseCase, ActivateSlotInTravianUseCase, DeactivateSlotInTravianUseCase, DisableSlotByBotUseCase, EnableSlotByBotUseCase, CancelProbeUseCase, SendSchedulerGroupUseCase, ProcessFarmListUseCase
- `adapters/db/farm_list_sqlite_adapter.py` — FarmListSQLiteAdapter
- `adapters/browser/farm_lists.py` — lector DOM
- `adapters/browser/farm_list_sender.py` — envío JS
- `adapters/browser/live_farm_list_adapter.py` — LiveFarmListAdapter (mismo patrón que LiveOverviewAdapter)
- `adapters/browser/url_utils.py` — helper build_url
- `adapters/api/routes/farm.py` — router /farm (21 endpoints)
- `tests/unit/test_farm_lists.py` — 32 tests (todos pasan)

### Endpoints /farm (prefijo sin /api)
8.1 Schedulers: GET/POST /worlds/{wid}/schedulers, PUT/DELETE /worlds/{wid}/schedulers/{sid}, PUT /worlds/{wid}/schedulers/{sid}/farm-lists, **POST /worlds/{wid}/schedulers/{sid}/toggle** (NUEVO 2026-05-27)
8.2 Farm Lists: GET /worlds/{wid}/farm-lists, POST /worlds/{wid}/farm-lists/read
8.3 Slots: POST /slots/{sid}/activate|deactivate|bot-disable|bot-enable|cancel-probe
8.4 Envío: POST /farm-lists/{id}/send
8.5 Historial: GET /worlds/{wid}/history, GET /worlds/{wid}/slot-events (paginados; slot-events acepta ?scheduler_id con filtrado Python post-query — pendiente mover filtro a SQL)
8.6 Agente: POST /worlds/{wid}/agent/start|stop, GET /worlds/{wid}/agent/status, POST /worlds/{wid}/schedulers/{sid}/run-now

### Asimetría de filtros en historial (DEUDA TÉCNICA — registrada 2026-05-27)
- `get_farm_list_send_history` tiene filtro nativo SQL por `scheduler_id` (adaptador + puerto)
- `get_slot_events` NO tiene filtro por `scheduler_id` en el puerto ni en el adaptador
- El handler de slot-events lo compensa con fetch-all (page_size=100_000) + filter en Python
- FIX PENDIENTE: añadir `scheduler_id` a FarmListDbPort.get_slot_events y FarmListSQLiteAdapter.get_slot_events

### Sin Accept-Language: datos de juego, no catálogo i18n

### Fuente de datos de villages — upsert como side effect de ReadFarmLists

La tabla `villages` (campos: id, world_id, data_id, name, x=0, y=0) recibe su primera carga desde la página de farm lists (`/build.php?gid=16&tt=99`). El flujo es:

1. `adapters/browser/farm_lists.py` — `_JS_GET_FARM_LIST_ENTRIES` (línea 143) lee `span.name[data-did]` del nav sidebar del DOM de Travian y extrae `{villageName, villageDid}` por cada lista. `villageDid` = `data_id` de la aldea en la BD.
2. `core/use_cases/farm_lists.py` — `ReadFarmListsUseCase.execute()` (línea 124): para cada FarmList cuya aldea no esté ya en BD y tenga `village_data_id > 0`, llama `db.upsert_village(world_id, fl.village_data_id, fl.village_name)`. Si `village_data_id == 0` (el nav no expuso el did), la lista se omite con warning.
3. `core/ports/farm_list_db_port.py` — `FarmListDbPort.upsert_village` (línea 70) — contrato ABC.
4. `adapters/db/farm_list_sqlite_adapter.py` — `FarmListSQLiteAdapter.upsert_village` (línea 588): `INSERT INTO villages (world_id, data_id, name, x, y) VALUES (?, ?, ?, 0, 0) ON CONFLICT(world_id, data_id) DO UPDATE SET name = excluded.name`.

**Implicaciones para features futuras:**
- `x=0, y=0` son placeholders intencionales. La plaza de reuniones no expone coordenadas. La feature VillageMap (lectura de overview) es la prevista para actualizarlos.
- Cualquier feature que necesite `villages` populada puede disparar `POST /farm/worlds/{world_id}/farm-lists/read` como paso previo — esto hace el upsert automáticamente.
- NO duplicar la lógica de upsert de aldeas. El punto de entrada único es `FarmListDbPort.upsert_village` vía `ReadFarmListsUseCase`.
- `get_villages_by_world(world_id)` (en FarmListDbPort/FarmListSQLiteAdapter) es la consulta de lectura correspondiente.

### Frontend: PARCIALMENTE IMPLEMENTADO (actualizado 2026-05-27)

Los siguientes componentes de farm lists YA EXISTEN en `frontend/src/`:

| Componente | Ruta | Contenido |
|---|---|---|
| `FarmListsTab` | `frontend/src/components/world/FarmListsTab.jsx` | Tabla principal de farm lists agrupadas por aldea. Columnas: nombre, slots (activo/total), scheduler, último envío, rec/env. |
| `FarmListDrawer` | `frontend/src/components/world/FarmListDrawer.jsx` | Drawer lateral 480px con 3 pestañas: Slots, Stats, Historial. Por slot: nombre, distancia, botín último raid, estado (badge). SlotDetail expandible con avg_bounty, total_bounty, acciones activate/deactivate/cancel-probe. |
| `SchedulerDashboard` | `frontend/src/components/world/SchedulerDashboard.jsx` | Panel de schedulers |
| `SchedulerSubPanel` | `frontend/src/components/world/SchedulerSubPanel.jsx` | Sub-panel de scheduler |
| `AgentBottomBar` | `frontend/src/components/world/AgentBottomBar.jsx` | Barra inferior del agente |
| `AgentsTab` | `frontend/src/components/world/AgentsTab.jsx` | Pestaña de agentes |
| `Countdown` | `frontend/src/components/world/Countdown.jsx` | Countdown para cooldown de sondas |
| `WorldSpacePage` | `frontend/src/pages/WorldSpacePage.jsx` | Página del mundo con 4 pestañas (sidebar): overview, agentes, farm lists, calculadora |

`WorldSpacePage` ya tiene las 4 pestañas sidebar implementadas con iconos SVG.
`api` client ya tiene todos los métodos farm (getFarmLists, readFarmLists, activateSlot, deactivateSlot, cancelProbe, sendFarmList, getFarmListHistory, getAgentStatus, etc.).

#### Lo que NO existe en el frontend para las 5 capacidades pedidas:

1. **Ordenación por columna**: NO. La tabla en FarmListsTab no tiene ningún mecanismo de sort. Las columnas son cabeceras `<th>` estáticas sin onClick.

2. **Botín acumulado por slot en la tabla principal**: PARCIAL. `total_bounty` ya existe en `FarmSlot` (entidad + BD + API). En FarmListsTab se muestra `avg_bounty_per_send` a nivel de farm list (no por slot). En el drawer (SlotDetail) sí se muestra `total_bounty` y `average_raid_bounty` por slot. En la tabla principal de FarmListsTab NO se muestra `total_bounty` por slot (solo el promedio agregado de la lista).

3. **Iconos de tropas**: NO hay ningún componente ni helper. `troops` ya viene en el payload del slot (dict `{t1:2, t4:1, ...}`) tanto en la entidad como en la API. Pero el frontend no los renderiza en ningún sitio. Los iconos PNG de tropas en `assets/icons/` están VACÍOS (solo `.gitkeep`): el scraper de kirilloid genera `unit_*.png` pero NO se han descargado aún.

4. **Dropdown de acciones por slot en la tabla principal**: PARCIAL. Las acciones (activate, deactivate, cancel-probe) YA EXISTEN implementadas en `SlotDetail` dentro del drawer (accordion expandible por slot). NO hay dropdown de acciones en la fila de slot de la tabla principal del drawer — hay que expandir el accordion. No hay ningún menú contextual inline en la tabla de FarmListsTab (nivel de lista).

5. **Último reporte con link**: PARCIAL. `last_raid_report_id` ya llega en el payload del slot. En el SlotDetail del drawer se muestra `last_raid_state` + tiempo relativo, PERO no hay link clickable a Travian. El campo `last_raid_report_id` contiene el ID del reporte (ej: `12345/678`) que hay que transformar a `<world_url>report?id=<id_con_%7C>&s=1`. La `world_url` se puede obtener desde `World.server` (disponible en la sesión) — pero NO se pasa como prop al drawer actualmente.

## CAPACIDADES REUTILIZABLES MARCADAS

### Alta prioridad para features futuras

1. **`TranslationPort.get_message(code, lang, **params)`** — cualquier endpoint futuro que necesite devolver un error localizado puede usar este método directamente a través de `get_translation_port`. No hay que implementar nada nuevo.

2. **`get_translation_port` (dependency)** — inyectable en cualquier router FastAPI. Solo `Depends(get_translation_port)`.

3. **`get_language` (dependency)** — validación centralizada de idioma. Ya es el patrón estándar del proyecto. Todo endpoint nuevo debe usarla.

4. **Catálogos base/override** — patrón extensible. Para añadir un nuevo tipo de catálogo (p.ej. recursos, unidades de ataque) basta con crear `base/nuevo.json` + `override/nuevo.json` y añadir los métodos correspondientes en TranslationPort e implementarlos en JsonTranslationAdapter.

5. **DTOs `BuildingItem` y `TroopItem`** (catalog.py) — diseñados deliberadamente abiertos (sin `extra="forbid"`) para recibir futuros campos de datos de juego (levels, cost, attack, defense, speed, carry) sin romper el contrato.

6. **Middleware de seguridad** (`add_security_headers`) — aplica a TODAS las respuestas. No hay que añadirlo en futuros routers.

7. **Middleware de cache** (`add_catalog_cache_control`) — aplica automáticamente a cualquier ruta bajo `/catalog/`. Futuros endpoints de catálogo heredan el Cache-Control sin hacer nada.

### Deuda conocida / gaps del catálogo

- `de`, `fr`, `ru` en messages.json tienen valores vacíos (solo `es` y `en` completos). El fallback a 'es' cubre esto, pero es deuda pendiente de traducción.
- `BuildingNotFoundError` está definida pero no tiene uso activo en ninguna ruta todavía.

### Capacidades reutilizables de la feature sesión (be2e449)

8. **`_verify_world_belongs_to_account(account_id, world_id, db)`** — helper async en accounts.py. Reutilizable por cualquier futuro endpoint que necesite verificar pertenencia de mundo a cuenta. Siempre 404 (nunca 403), consistente con política de no-revelación de existencia ajena.

9. **`get_world_runtime_port` (dependency)** — inyectable en cualquier router que necesite el SessionRegistry. Lanza 503 si no disponible.

10. **`SessionRegistry.is_active(world_id)`** — consulta sincrónica O(1). Reutilizable por cualquier endpoint que necesite saber si hay sesión activa antes de operar.

11. **`SessionRegistry.get_browser(world_id)` y `get_world_server(world_id)`** — callables pensados para LiveOverviewAdapter pero inyectables en cualquier futuro adaptador que necesite acceso al browser activo.

12. **`get_fernet` (dependency)** — devuelve instancia Fernet desde env. Reutilizable para cualquier use case futuro que necesite descifrar datos de la BD.

### Capacidades reutilizables del frontend

13. **`api` object en `client.js`** — cliente HTTP centralizado. Para añadir un nuevo endpoint solo hay que agregar un método aquí; NO hacer `fetch` directamente en componentes.

14. **`ApiError`** — clase tipada para errores. Los componentes hacen `if (err instanceof ApiError && err.status === 409)` para distinguir conflictos de errores de red.

15. **`useI18n()` + `translate()`** — sistema i18n completo y funcional para 25 idiomas. Cualquier nuevo componente debe usar `useI18n()`, nunca texto hardcodeado.

16. **`useFocusTrap`, `Spinner`, `BadgeSpinner`, `showToast`, `parseServerUrl`, `FOCUSABLE`** en `uiUtils.jsx` — utilidades transversales compartidas. No duplicar; importar desde `src/components/ui/uiUtils.jsx`.

17. **Patrón de modal** (ver "Patrones de modal" arriba) — contrato de accesibilidad completo ya definido y probado en 4 modales. Cualquier modal nuevo debe seguirlo.

18. **`ManagementShell`** — shell de la app. Cualquier pantalla nueva de gestión se añade como `<Route>` dentro del Outlet del shell, sin tocar Topbar/Sidebar.

19. **`useTheme()` / `useWindowSize()`** — hooks custom ya disponibles en `frontend/src/hooks/`.

---

## CODE-SMELLS DETECTADOS (frontend)

### CS-01 — Duplicación en WizardModal (ALTA)
`WizardModal.jsx` (líneas ~82-165) tiene copias privadas de:
- `parseServerUrl` — idéntica a `uiUtils.parseServerUrl`
- `isValidServerUrl` — idéntica a `uiUtils.isValidServerUrl`
- `Spinner` — muy similar a `uiUtils.Spinner` (diferencia: keyframe nombrado `wizard-spin` vs `spin`)
- `useFocusTrap` + `FOCUSABLE` — copia exacta de uiUtils

Probablemente WizardModal se implementó antes de que uiUtils existiera, y no se actualizó.
RIESGO: si parseServerUrl o isValidServerUrl cambian en uiUtils, WizardModal queda desincronizado.
RECOMENDACIÓN: en el próximo toque a WizardModal, importar desde uiUtils y eliminar las copias locales. Hay que unificar el nombre del keyframe del spinner (usar `spin` del CSS global).

### CS-02 — DeleteConfirmModal duplicado vs inline en AccountsListPage (BAJA)
`AccountsListPage.jsx` tiene un `DeleteConfirmModal` inline (definido localmente en el mismo fichero, líneas ~481-550) para el borrado de cuentas desde la lista. Existe también `ConfirmDeleteModal` en `src/components/ui/ConfirmDeleteModal.jsx` (usado en AccountDetailPage para borrar mundo y cuenta). Son muy similares pero el de AccountsListPage no tiene el estado 409 inline.
DECISIÓN SUGERIDA: mantener separados (AccountsListPage es más simple y no necesita el estado 409 — es una lista, el borrado forzado no aplica ahí). No forzar DRY si añade complejidad innecesaria.

---

## Navegación al ancla de origen en vivo (noise-path-wizard) — pregame 2026-06-02

Necesidad: acción del wizard que, dado world_id + origin, conduce el Chrome vivo del bot a la URL del ancla (para que el usuario vea la pantalla y grabe los clicks siguientes).

REUTILIZABLE (no rediseñar):
- Lógica "origin → URL del ancla" YA existe inline en `WorldAgent.execute_path_test` (`core/scheduling/world_agent.py:1461-1496`): maneja ANY (sin nav), VILLAGE_<data_id>→`/dorf1.php?newdid=<id>`, y enum genérico vía `ORIGIN_PATHS` (`core/entities/noise.py:56-66`) + `build_url(server, relative)` (`adapters/browser/url_utils.py:6`). La navegación real es `await browser.get(anchor_url)` + `human_delay(500,900)`.
- Acceso al browser vivo: `session_registry.get_browser(world_id)` + `get_world_server(world_id)` (`adapters/browser/session_registry.py:149,158`; devuelve "" si no hay sesión → `not server` lo cubre).
- Lock de browser: `WorldAgent._browser_lock` (asyncio.Lock) serializa execute_path_test / _execute_noise_action / refresh_villages. `BrowserBusyError` (core/exceptions) → 409.
- Precondición sesión activa: `WorldAgent._session_active()` (world_agent.py:403) + estado RUNNING. Patrón de handler en EP-N14 test_path (`adapters/api/routes/noise.py:1277-1296`): RUNNING + _session_active() o 409; BrowserBusyError→409; RuntimeError→500.
- Front: EP-N12 origins ya da value/path por origin a `NoiseOriginSelector.jsx`; `NoisePathWizard.jsx` ya tiene origin+originLabel en estado. Cliente HTTP `frontend/src/api/client.js:421-477` tiene helpers EP-N01..N14 (patrón `api.refreshNoiseVillages`, `api.testNoisePath`).

AJUSTE PEQUEÑO recomendado (no rompedor): extraer la lógica "origin→relative URL" de execute_path_test (líneas 1476-1489) a un helper privado reutilizable (p.ej. `_origin_to_relative_url(origin: str) -> str`) y un método público `navigate_to_origin(origin: str)` que adquiera el lock, resuelva server, build_url, browser.get + human_delay. execute_path_test pasaría a llamar al mismo helper → cero duplicación.

NUEVO mínimo: endpoint `POST /worlds/{id}/noise/navigate-to-origin` (body con origin) calcando el handler de EP-N13/EP-N14 + helper de cliente `api.navigateNoiseToOrigin(worldId, origin)`.

RIESGO duplicación a evitar: NO reimplementar el mapeo origin→URL ni el parsing de VILLAGE_<data_id> en una nueva función; reusar el de execute_path_test. NO crear un segundo patrón de acceso a browser/lock.

Anti-detección: `browser.get(anchor_url)` directo ya es el mecanismo aceptado por el guardian para llegar al ancla (idéntico a execute_path_test, RN-PT03). No hay pieza "clic en el menú" reutilizable; el guardian debe validar el nuevo método igualmente por tocar el browser de Travian.
