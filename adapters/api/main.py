"""
Punto de entrada de la API FastAPI.

Registra routers, configura el exception handler global con traducciones,
inicializa el adaptador de traducciones como singleton en app.state, y
añade las cabeceras mínimas de seguridad a todas las respuestas.
"""
from __future__ import annotations

import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from adapters.api.error_codes import DEFAULT_ERROR_STATUS, ERROR_HTTP_MAP
from adapters.api.routes.accounts import router as accounts_router
from adapters.api.routes.attack_reports import router as attack_reports_router
from adapters.api.routes.catalog import router as catalog_router
from adapters.api.routes.combat import router as combat_router
from adapters.api.routes.farm import router as farm_router
from adapters.api.routes.game_data import router as game_data_router
from adapters.api.routes.game_culture_points import router as game_culture_points_router
from adapters.api.routes.game_overview import router as game_overview_router
from adapters.api.routes.game_resources import router as game_resources_router
from adapters.api.routes.game_troops import router as game_troops_router
from adapters.api.routes.noise import router as noise_router
from adapters.api.routes.route_categories import router as route_categories_router
from adapters.api.routes.route_templates import router as route_templates_router
from adapters.api.routes.session import router as session_router
from adapters.browser.fixture_overview_adapter import FixtureOverviewAdapter
from adapters.browser.live_farm_list_adapter import LiveFarmListAdapter
from adapters.browser.live_overview_adapter import LiveOverviewAdapter
from adapters.browser.session_registry import SessionRegistry
from adapters.db.account_sqlite_adapter import AccountSQLiteAdapter
from adapters.db.attack_report_sqlite_adapter import AttackReportSQLiteAdapter
from adapters.db.database import get_connection
from adapters.db.farm_list_sqlite_adapter import FarmListSQLiteAdapter
from adapters.db.game_data_sqlite_adapter import GameDataSQLiteAdapter
from adapters.db.seed_loader import load_if_empty
from adapters.db.noise_sqlite_adapter import NoiseSQLiteAdapter
from adapters.db.route_category_sqlite_adapter import RouteCategorySQLiteAdapter
from adapters.db.route_template_sqlite_adapter import (
    RouteTemplateSQLiteAdapter,
    seed_route_templates,
)
from adapters.db.session_sqlite_adapter import SessionSQLiteAdapter
from adapters.translations.json_translation_adapter import JsonTranslationAdapter
from core.crypto import load_fernet_key
from core.exceptions import TravianBotError
from core.i18n.languages import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES
from dotenv import load_dotenv

# Carga las variables de .env (TRAVIAN_BOT_SECRET_KEY, mundo, tribu, etc.) en os.environ
# al importar la app, para que load_fernet_key() y demás config funcionen sin exportarlas
# a mano (en tests y en arranque normal). load_dotenv no pisa variables ya presentes.
load_dotenv()

# ---------------------------------------------------------------------------
# Patrones para el enmascarado de datos sensibles en modo verbose
# ---------------------------------------------------------------------------

# Campos sensibles en los vars de frame (nombre de variable contiene alguna de estas palabras)
_SENSITIVE_FIELD_PATTERNS = re.compile(
    r"(password|token|api_key|authorization|cipher|secret)",
    re.IGNORECASE,
)

# Rutas de perfil de Chrome: variables que contengan estas palabras en su nombre
_CHROME_PROFILE_PATTERNS = re.compile(
    r"(user_data_dir|profile_dir)",
    re.IGNORECASE,
)

# URLs/hostnames de Travian: variables cuyo valor contenga dominios de Travian
_TRAVIAN_URL_PATTERN = re.compile(
    r"travian\.(com|es|de|net|ru|org|[a-z]{2,})",
    re.IGNORECASE,
)


def _mask_frame_locals(local_vars: dict) -> dict:
    """
    Enmascara valores sensibles de las variables locales de un frame.

    Reglas (OBLIGATORIAS — condición guardian-antideteccion, sección 11 del spec):
    1. Nombre de variable coincide con _SENSITIVE_FIELD_PATTERNS → valor → "***REDACTED***"
    2. Nombre de variable coincide con _CHROME_PROFILE_PATTERNS  → valor → "***REDACTED***"
    3. Valor (convertido a str) contiene un dominio de Travian     → valor → "***REDACTED***"
    """
    masked: dict = {}
    for k, v in local_vars.items():
        v_str = str(v)
        if (
            _SENSITIVE_FIELD_PATTERNS.search(k)
            or _CHROME_PROFILE_PATTERNS.search(k)
            or _TRAVIAN_URL_PATTERN.search(v_str)
        ):
            masked[k] = "***REDACTED***"
        else:
            masked[k] = v_str
    return masked


def _build_trace(exc: BaseException) -> list[dict]:
    """
    Construye la traza de frames para el modo verbose.
    Los valores de variables locales se enmascaran antes de incluirse.
    """
    tb = exc.__traceback__
    frames = []
    while tb is not None:
        frame = tb.tb_frame
        frames.append({
            "file": frame.f_code.co_filename,
            "line": tb.tb_lineno,
            "function": frame.f_code.co_name,
            "locals": _mask_frame_locals(frame.f_locals),
        })
        tb = tb.tb_next
    return frames


# ---------------------------------------------------------------------------
# Lifespan — inicializar singleton de traducciones
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(application: FastAPI):
    """
    Inicializa los singletons de puertos al arrancar la aplicación:
      - translation_port (JsonTranslationAdapter) — catálogo de textos localizados
      - game_data_port   (GameDataSQLiteAdapter)  — stats de tropas e iconos

    Ambos quedan disponibles en app.state para todos los handlers y dependencias.
    """
    # --- Clave Fernet — FALLA al arrancar si TRAVIAN_BOT_SECRET_KEY no está ---
    fernet = load_fernet_key()
    application.state.fernet = fernet

    catalog_base = (
        Path(__file__).parent.parent.parent / "core" / "i18n" / "catalog" / "base"
    )
    catalog_override = (
        Path(__file__).parent.parent.parent / "core" / "i18n" / "catalog" / "override"
    )
    application.state.translation_port = JsonTranslationAdapter(
        base_dir=catalog_base,
        override_dir=catalog_override,
    )

    # Conexión SQLite compartida (WAL mode)
    conn = await get_connection()
    application.state._db_conn = conn  # guardar para cerrar en shutdown

    # GameDataSQLiteAdapter — stats de tropas e iconos
    game_data_adapter = GameDataSQLiteAdapter(conn)
    await game_data_adapter.ensure_tables()
    # Seed: poblar tablas de juego desde ficheros JSON versionados si están vacías.
    # Solo carga si troop_stats == 0 (clon fresco o BD sin scraper ejecutado).
    # En re-arranques con datos ya presentes, este call es un COUNT query y retorna en ~0ms.
    await load_if_empty(
        game_data_adapter,
        Path(__file__).parent.parent.parent / "seeds" / "game_data",
    )
    application.state.game_data_port = game_data_adapter

    # AccountSQLiteAdapter — cuentas, mundos y aldeas
    account_adapter = AccountSQLiteAdapter(conn)
    await account_adapter.ensure_tables()
    application.state.db_port = account_adapter

    # AttackReportSQLiteAdapter — reportes de ataque a oasis
    attack_report_adapter = AttackReportSQLiteAdapter(conn)
    await attack_report_adapter.ensure_tables()
    application.state.attack_report_port = attack_report_adapter

    # OverviewHtmlSourcePort — selección por variable de entorno OVERVIEW_SOURCE
    # 'fixture' (default): devuelve HTML desde tests/fixtures/overview/ (sin Chrome)
    # 'live':              navega Travian con Chrome autenticado
    _overview_source = os.environ.get("OVERVIEW_SOURCE", "fixture").lower()
    if _overview_source == "live":
        html_source_port = LiveOverviewAdapter(
            get_browser=lambda wid: None,
            get_world_server=lambda wid: "",
        )
    else:
        # "fixture" — default; usa HTML capturado manualmente en tests/fixtures/overview/
        _fixtures_dir = (
            Path(__file__).parent.parent.parent / "tests" / "fixtures" / "overview"
        )
        html_source_port = FixtureOverviewAdapter(fixtures_dir=_fixtures_dir)

    application.state.html_source_port = html_source_port

    # SessionRegistry — implementa WorldRuntimePort + callables para LiveOverviewAdapter.
    # Se instancia DESPUÉS de html_source_port porque set_live_adapter necesita la
    # referencia al adaptador ya construido (evita dependencia circular en constructores).
    session_registry = SessionRegistry()
    application.state.world_runtime_port = session_registry

    # Cablear SessionRegistry con LiveOverviewAdapter (solo en modo 'live').
    # Reemplaza las lambdas stub que devolvían None/"" por métodos reales.
    if _overview_source == "live":
        # html_source_port ya fue asignado arriba como LiveOverviewAdapter.
        # Sustituir los callables stub por los métodos reales del registry.
        html_source_port.set_callables(
            get_browser=session_registry.get_browser,
            get_world_server=session_registry.get_world_server,
        )
        # Inyectar referencia inversa para invalidación de caché en login/logout.
        session_registry.set_live_adapter(html_source_port)
    # En modo 'fixture', session_registry no necesita referencia a html_source_port
    # (FixtureOverviewAdapter no tiene caché que invalidar).

    # -----------------------------------------------------------------------
    # Attack Reports — AttackReportSQLiteAdapter (comparte la misma conexión SQLite)
    # -----------------------------------------------------------------------
    attack_report_adapter = AttackReportSQLiteAdapter(conn)
    await attack_report_adapter.ensure_tables()
    application.state.attack_report_port = attack_report_adapter

    # -----------------------------------------------------------------------
    # Farm Lists — FarmListSQLiteAdapter (comparte la misma conexión SQLite)
    # -----------------------------------------------------------------------
    farm_db_adapter = FarmListSQLiteAdapter(conn)
    await farm_db_adapter.ensure_tables()
    application.state.farm_db_port = farm_db_adapter

    # -----------------------------------------------------------------------
    # Human Sessions — SessionSQLiteAdapter (comparte la misma conexión SQLite)
    # -----------------------------------------------------------------------
    session_db_adapter = SessionSQLiteAdapter(conn)
    await session_db_adapter.ensure_tables()
    application.state.session_db_port = session_db_adapter

    # -----------------------------------------------------------------------
    # Ruido Humano de Navegación — NoiseSQLiteAdapter (comparte la misma conexión SQLite)
    # -----------------------------------------------------------------------
    noise_db_adapter = NoiseSQLiteAdapter(conn)
    await noise_db_adapter.ensure_tables()
    application.state.noise_db_port = noise_db_adapter

    # -----------------------------------------------------------------------
    # Catálogo dinámico de Categorías de Rutas — RouteCategorySQLiteAdapter
    # (comparte la misma conexión SQLite)
    # DEBE inicializarse ANTES de RouteTemplateSQLiteAdapter (M-CAT01/M-CAT02
    # crean la tabla route_categories que las migraciones M-CAT03/M-CAT04 necesitan).
    # Spec route-categories-dynamic.md §9.1, §14 Paso 5 y 6.
    # -----------------------------------------------------------------------
    route_category_adapter = RouteCategorySQLiteAdapter(conn)
    await route_category_adapter.ensure_tables()
    application.state.route_category_port = route_category_adapter

    # -----------------------------------------------------------------------
    # Catálogo maestro de Plantillas de Rutas — RouteTemplateSQLiteAdapter
    # (comparte la misma conexión SQLite)
    # Spec route-templates-developer-portal.md §14 Paso 3 y 8.
    # -----------------------------------------------------------------------
    route_template_adapter = RouteTemplateSQLiteAdapter(conn)
    await route_template_adapter.ensure_tables()
    # Seed idempotente: inserta ~20 plantillas si aún no existen (por slug).
    await seed_route_templates(route_template_adapter)
    application.state.route_template_port = route_template_adapter

    # Dict de LiveFarmListAdapter por world_id.
    # Se puebla on-demand cuando el usuario arranca el WorldAgent para un mundo
    # (endpoint POST /farm/worlds/{world_id}/agent/start).
    # Los adaptadores ya creados se pueden reutilizar si el agente se para y se
    # vuelve a arrancar — set_callables() permite recablear los callables si el
    # SessionRegistry cambia.
    application.state.farm_browser_adapters = {}

    # Dict de WorldAgent por world_id.
    # Se gestiona desde el endpoint /farm/worlds/{world_id}/agent/start|stop.
    application.state.world_agents = {}

    # Helper para crear o recuperar un LiveFarmListAdapter por world_id.
    # Se almacena en app.state para que el endpoint start pueda usarlo sin
    # necesitar importar LiveFarmListAdapter directamente.
    def _get_or_create_farm_browser(world_id: int) -> LiveFarmListAdapter:
        adapters: dict = application.state.farm_browser_adapters
        if world_id not in adapters:
            adapters[world_id] = LiveFarmListAdapter(
                world_id=world_id,
                get_browser=session_registry.get_browser,
                get_world_server=session_registry.get_world_server,
            )
        return adapters[world_id]

    application.state.get_or_create_farm_browser = _get_or_create_farm_browser

    yield

    # Cierre limpio de la conexión SQLite
    try:
        await conn.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="TravianBot API",
    description="API de control del bot de Travian. Requiere Accept-Language en cada endpoint.",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# CORS — permite peticiones de la extensión Chrome y del dashboard local
#
# Por qué allow_credentials=False:
#   La extensión Chrome no envía cookies cross-origin (usa solo JSON + Bearer
#   si aplica). El dashboard local tampoco usa cookies cross-origin. Con
#   allow_credentials=True habría que fijar allow_origins exactos (no regex),
#   lo que rompería el soporte para IDs de extensión variables en desarrollo.
#   False es la opción correcta y más segura aquí.
#
# Orígenes permitidos (allow_origin_regex, anclado con ^ y $):
#   - chrome-extension://.*          → extensión Chrome (cualquier ID de instalación)
#   - http://localhost(:\d+)?        → dashboard Vite en desarrollo (localhost)
#   - http://127\.0\.0\.1(:\d+)?    → alternativa loopback
#   - http://192\.168\.\d+\.\d+(:\d+)? → LAN privada (escenario Raspberry Pi)
#
# No se usa allow_origins=["*"] para no exponer la API a cualquier origen de internet.
# ---------------------------------------------------------------------------

_CORS_ORIGIN_REGEX = (
    r"^(chrome-extension://.*"
    r"|http://localhost(:\d+)?"
    r"|http://127\.0\.0\.1(:\d+)?"
    r"|http://192\.168\.\d+\.\d+(:\d+)?)$"
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=_CORS_ORIGIN_REGEX,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Accept-Language", "X-Request-ID", "X-Verbose", "Authorization"],
)


# ---------------------------------------------------------------------------
# Cabeceras mínimas de seguridad — middleware aplicado a TODAS las respuestas
# ---------------------------------------------------------------------------

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """
    Añade las cabeceras mínimas de seguridad a todas las respuestas.

    - X-Request-ID: reutiliza el de la request si llega; genera UUID v4 si no.
    - X-API-Version: versión de la API declarada en app.version.
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - Content-Type: la respuesta usa application/json por defecto en FastAPI;
      el charset lo añadimos explícitamente cuando aplica.

    Cache-Control lo añade cada router que lo necesite (catálogo: public, max-age=3600).
    El middleware NO lo pone por defecto para no heredarlo en respuestas de error.
    """
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-API-Version"] = app.version
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    # Garantizar charset en Content-Type para respuestas JSON
    ct = response.headers.get("content-type", "")
    if "application/json" in ct and "charset" not in ct:
        response.headers["content-type"] = "application/json; charset=utf-8"
    return response


# ---------------------------------------------------------------------------
# Middleware de Cache-Control para endpoints de catálogo
# ---------------------------------------------------------------------------

@app.middleware("http")
async def add_catalog_cache_control(request: Request, call_next):
    """
    Añade Cache-Control: public, max-age=3600 a las respuestas 2xx de los endpoints
    de catálogo. NO se hereda en respuestas de error (4xx/5xx).
    """
    response = await call_next(request)
    path = request.url.path
    is_catalog = path.startswith("/catalog/")
    is_success = 200 <= response.status_code < 300
    if is_catalog and is_success:
        response.headers["Cache-Control"] = "public, max-age=3600"
    return response


# ---------------------------------------------------------------------------
# Exception handler global — TravianBotError
# ---------------------------------------------------------------------------

def _extract_lang(request: Request) -> str:
    """
    Extrae y normaliza el idioma del header Accept-Language.
    Defaultea a 'es' sin lanzar excepción (el handler global no puede depender
    de get_language que lanza HTTPException).
    """
    raw = request.headers.get("Accept-Language", DEFAULT_LANGUAGE)
    code = raw.strip().lower().split("-")[0]
    return code if code in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


@app.exception_handler(TravianBotError)
async def travian_bot_error_handler(request: Request, exc: TravianBotError) -> JSONResponse:
    """
    Handler global para todas las TravianBotError.

    - Traduce el mensaje de error al idioma del cliente (Accept-Language).
    - Mapea error_code → HTTP status code via ERROR_HTTP_MAP.
    - Si X-Verbose: true, incluye error_details con traza enmascarada.
    - Las cabeceras mínimas las añade el middleware (X-Request-ID, X-API-Version, etc.).
    """
    lang = _extract_lang(request)
    translation = request.app.state.translation_port
    message = translation.get_message(exc.error_code, lang, **exc.params)
    status_code = ERROR_HTTP_MAP.get(exc.error_code, DEFAULT_ERROR_STATUS)

    verbose = request.headers.get("X-Verbose", "").lower() == "true"

    if verbose:
        trace = _build_trace(exc)
        error_details = {
            "exception": f"{type(exc).__module__}.{type(exc).__name__}",
            "http_code": status_code,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trace": trace,
        }
        content = {"detail": message, "error_details": error_details}
    else:
        content = {"detail": message}

    # Construir la respuesta con Content-Type explícito (el middleware lo completará,
    # pero lo ponemos aquí para ser explícitos)
    response = JSONResponse(
        status_code=status_code,
        content=content,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    return response


# ---------------------------------------------------------------------------
# StaticFiles — iconos PNG servidos directamente desde el filesystem
# NOTA: el mount debe estar ANTES de include_router para que StaticFiles
# tenga precedencia sobre rutas dinámicas en el mismo prefijo.
# El directorio se crea automáticamente si no existe (assets/icons/).
# ---------------------------------------------------------------------------

_ICONS_DIR = Path(__file__).parent.parent.parent / "assets" / "icons"
_ICONS_DIR.mkdir(parents=True, exist_ok=True)

app.mount(
    "/static/icons",
    StaticFiles(directory=str(_ICONS_DIR)),
    name="static_icons",
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(accounts_router)
app.include_router(attack_reports_router)
app.include_router(catalog_router)
app.include_router(combat_router)
app.include_router(farm_router)
app.include_router(game_data_router)
app.include_router(game_overview_router)
app.include_router(game_resources_router)
app.include_router(game_culture_points_router)
app.include_router(game_troops_router)
app.include_router(noise_router)
app.include_router(route_categories_router)
app.include_router(route_templates_router)
app.include_router(session_router)


@app.get("/health")
def health_check() -> dict:
    """Endpoint de salud — no requiere Accept-Language."""
    return {"status": "ok"}
