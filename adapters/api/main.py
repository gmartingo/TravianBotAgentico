"""
Punto de entrada de la API FastAPI.

Registra routers, configura el exception handler global con traducciones,
inicializa el adaptador de traducciones como singleton en app.state, y
añade las cabeceras mínimas de seguridad a todas las respuestas.
"""
from __future__ import annotations

import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from adapters.api.error_codes import DEFAULT_ERROR_STATUS, ERROR_HTTP_MAP
from adapters.api.routes.catalog import router as catalog_router
from adapters.api.routes.game_data import router as game_data_router
from adapters.db.database import get_connection
from adapters.db.game_data_sqlite_adapter import GameDataSQLiteAdapter
from adapters.translations.json_translation_adapter import JsonTranslationAdapter
from core.exceptions import TravianBotError
from core.i18n.languages import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES

# ---------------------------------------------------------------------------
# Patrones para el enmascarado de datos sensibles en modo verbose
# ---------------------------------------------------------------------------

# Campos sensibles en los vars de frame (nombre de variable contiene alguna de estas palabras)
_SENSITIVE_FIELD_PATTERNS = re.compile(
    r"(password|token|api_key|authorization)",
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

    # GameDataSQLiteAdapter — conexión aiosqlite, crea tablas si no existen
    conn = await get_connection()
    game_data_adapter = GameDataSQLiteAdapter(conn)
    await game_data_adapter.ensure_tables()
    application.state.game_data_port = game_data_adapter
    application.state._db_conn = conn  # guardar para cerrar en shutdown

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

app.include_router(catalog_router)
app.include_router(game_data_router)


@app.get("/health")
def health_check() -> dict:
    """Endpoint de salud — no requiere Accept-Language."""
    return {"status": "ok"}
