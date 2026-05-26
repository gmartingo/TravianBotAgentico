# Referencia de funciones — Helpers de i18n en la capa API

Módulo: `adapters/api/main.py`, `adapters/api/dependencies.py`

---

## `get_language(accept_language: str | None) -> str`

**Ubicación**: `adapters/api/dependencies.py`

**Qué hace**: dependencia FastAPI que valida y normaliza el header `Accept-Language`.

**Declaración del parámetro**:
```python
accept_language: str | None = Header(default=None, alias="Accept-Language")
```

El `default=None` es intencional: hace que FastAPI no rechace la request con 422 cuando el header falta, lo que permite que sea el propio código de `get_language` quien devuelva un 400 con mensaje descriptivo (en vez del 422 genérico de FastAPI).

**Flujo**:
1. Si `accept_language is None` → `HTTP 400` con detail `"Cabecera 'Accept-Language' obligatoria. Valores válidos: [...]"`.
2. Normalizar: `.strip().lower().split("-")[0]`. Ejemplo: `"es-ES"` → `"es"`, `"EN"` → `"en"`.
3. Si el código normalizado no está en `SUPPORTED_LANGUAGES` → `HTTP 400` con detail `"Idioma 'XX' no soportado. Valores válidos: [...]"`.
4. Si es válido → devuelve el código normalizado.

**Retorna**: `str` — código BCP 47 de dos letras en minúsculas.

**Lanza**: `HTTPException(400)` en caso de header ausente o idioma inválido.

**Por qué existe**: centraliza la validación de idioma para que ningún endpoint tenga que repetir esta lógica. Todos los endpoints del proyecto usan `Depends(get_language)`.

**Impacto en negocio**: garantiza el contrato de la API (regla de negocio 1 del spec i18n) — ninguna request puede llegar a la lógica de negocio con un idioma no soportado.

---

## `get_translation_port(request: Request) -> TranslationPort`

**Ubicación**: `adapters/api/dependencies.py`

**Qué hace**: dependencia FastAPI que recupera el singleton `TranslationPort` de `app.state`.

**Retorna**: la instancia de `JsonTranslationAdapter` inicializada en el startup de la app.

**Por qué existe**: evita que los routers importen `JsonTranslationAdapter` directamente (lo que violaría la inversión de dependencias). Los routers solo conocen la interfaz `TranslationPort`.

**Por qué `app.state` y no `@lru_cache`**: el spec (trade-off T-6) eligió `app.state` como patrón más explícito en FastAPI. Con `@lru_cache`, el ciclo de vida del adaptador sería implícito; con `app.state` + `lifespan`, la inicialización y el cierre son visibles en el punto de entrada de la app.

---

## `_extract_lang(request: Request) -> str`

**Ubicación**: `adapters/api/main.py`

**Qué hace**: extrae y normaliza el idioma del header `Accept-Language` con fallback silencioso a `DEFAULT_LANGUAGE` (`"es"`).

**Diferencia con `get_language`**: `get_language` lanza `HTTPException(400)` si el header falta o el idioma es inválido. `_extract_lang` nunca lanza: en cualquier caso de error silencia y devuelve `"es"`. Se usa en el exception handler global, que no puede depender de dependencias que lancen excepciones.

**Lógica**:
```python
raw = request.headers.get("Accept-Language", DEFAULT_LANGUAGE)
code = raw.strip().lower().split("-")[0]
return code if code in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
```

**Retorna**: `str` — código de idioma válido o `"es"` como fallback.

**Por qué existe como función separada y no como parte del handler**: separa la responsabilidad de extracción/normalización de la lógica del handler. También facilita el testing unitario del handler.

---

## `_mask_frame_locals(local_vars: dict) -> dict`

**Ubicación**: `adapters/api/main.py`

**Qué hace**: recorre el dict de variables locales de un frame de traceback y reemplaza los valores sensibles por `"***REDACTED***"`.

**Tres reglas de enmascarado** (condición obligatoria del guardian-antideteccion):

| Condición | Criterio | Ejemplo variable |
|---|---|---|
| Regla 1 | Nombre de variable contiene `password`, `token`, `api_key` o `authorization` (case-insensitive) | `password`, `auth_token`, `api_key_prod` |
| Regla 2 | Nombre de variable contiene `user_data_dir` o `profile_dir` (case-insensitive) | `user_data_dir`, `chrome_profile_dir` |
| Regla 3 | Valor (convertido a `str`) contiene dominio de Travian (`travian\.(com|es|de|...)`) | Cualquier variable cuyo valor sea una URL de Travian |

Las reglas 2 y 3 son requisito explícito del `guardian-antideteccion` (sección 11 del spec i18n): un volcado de debugging nunca debe revelar la ruta del perfil de Chrome ni el servidor de Travian que opera el bot.

**Retorna**: nuevo `dict` con las mismas claves; los valores sensibles sustituidos por `"***REDACTED***"`, los demás convertidos a `str`.

**Impacto en anti-detección**: si un error en producción provoca que alguien active `X-Verbose: true`, la respuesta no filtra información que permita correlacionar el bot con una cuenta o servidor de Travian.

---

## `_build_trace(exc: BaseException) -> list[dict]`

**Ubicación**: `adapters/api/main.py`

**Qué hace**: recorre el traceback de `exc` frame a frame y construye una lista de dicts con la información de cada frame, enmascarando las variables locales.

**Estructura de cada elemento**:
```python
{
    "file": str,      # ruta del archivo fuente
    "line": int,      # número de línea
    "function": str,  # nombre de la función
    "locals": dict    # variables locales enmascaradas
}
```

**Por qué existe**: el modo verbose (`X-Verbose: true`) está pensado para debugging interno del operador del dashboard. Necesita ver qué ocurrió, pero sin exponer secretos. `_build_trace` centraliza tanto la extracción del traceback como el enmascarado obligatorio.

---

## `lifespan(application: FastAPI)` (async context manager)

**Ubicación**: `adapters/api/main.py`

**Qué hace**: inicializa el `JsonTranslationAdapter` una sola vez al arrancar la app y lo almacena en `application.state.translation_port`. El bloque `yield` marca el momento en que la app está lista para recibir requests.

**Rutas de los catálogos**: calculadas como rutas absolutas relativas al fichero `main.py`:
```python
catalog_base     = Path(__file__).parent.parent.parent / "core" / "i18n" / "catalog" / "base"
catalog_override = Path(__file__).parent.parent.parent / "core" / "i18n" / "catalog" / "override"
```

Este patrón es portable: no depende del directorio de trabajo al lanzar la app.

**Por qué `lifespan` y no `@app.on_event("startup")`**: `@app.on_event` está deprecado en FastAPI >= 0.93. `lifespan` es el patrón recomendado y permite también definir lógica de teardown (tras el `yield`), útil si en el futuro el adaptador necesita liberar recursos.

---

## `add_security_headers` (middleware)

**Ubicación**: `adapters/api/main.py`

**Qué hace**: middleware HTTP que se ejecuta en cada request. Añade cabeceras de seguridad a todas las respuestas.

**Cabeceras añadidas**:

| Cabecera | Valor | Nota |
|---|---|---|
| `X-Request-ID` | ID de la request (reutilizado) o UUID v4 generado | Se propaga de request a respuesta si ya venía |
| `X-API-Version` | `app.version` (`"0.1.0"`) | Informativa para el cliente |
| `X-Content-Type-Options` | `nosniff` | Previene MIME sniffing |
| `X-Frame-Options` | `DENY` | Previene clickjacking |
| `Content-Type` | Garantiza `;charset=utf-8` si es JSON | Solo modifica si falta el charset |

**Qué NO hace**: no añade `Cache-Control`. Eso es responsabilidad del segundo middleware solo para rutas de catálogo.

---

## `add_catalog_cache_control` (middleware)

**Ubicación**: `adapters/api/main.py`

**Qué hace**: middleware HTTP que añade `Cache-Control: public, max-age=3600` a las respuestas 2xx de rutas que empiecen por `/catalog/`.

**Condición exacta**:
```python
is_catalog = path.startswith("/catalog/")
is_success = 200 <= response.status_code < 300
if is_catalog and is_success:
    response.headers["Cache-Control"] = "public, max-age=3600"
```

**Por qué no en el middleware de seguridad**: el `Cache-Control` no es una cabecera de seguridad genérica; es específica de endpoints de catálogo (datos estáticos). Añadirlo en el middleware genérico lo heredarían respuestas de error (4xx/5xx) y endpoints que no corresponde cachear.

---

## `travian_bot_error_handler` (exception handler)

**Ubicación**: `adapters/api/main.py`

**Qué hace**: captura cualquier `TravianBotError` en toda la aplicación y devuelve una `JSONResponse` con el mensaje localizado.

**Flujo completo**:
1. `_extract_lang(request)` → idioma del cliente (con fallback silencioso).
2. `request.app.state.translation_port.get_message(exc.error_code, lang, **exc.params)` → mensaje traducido.
3. `ERROR_HTTP_MAP.get(exc.error_code, DEFAULT_ERROR_STATUS)` → HTTP status code.
4. Si `X-Verbose: true` en headers → añadir `error_details` con traza enmascarada.
5. Construir y devolver `JSONResponse`.

**Body sin verbose**:
```json
{"detail": "<mensaje localizado>"}
```

**Body con verbose** (`X-Verbose: true`):
```json
{
  "detail": "<mensaje localizado>",
  "error_details": {
    "exception": "core.exceptions.AccountNotFoundError",
    "http_code": 404,
    "timestamp": "2026-05-24T10:30:00+00:00",
    "trace": [{"file": "...", "line": 42, "function": "...", "locals": {...}}]
  }
}
```

**Nota**: las cabeceras mínimas (`X-Request-ID`, `X-API-Version`, etc.) no las pone este handler directamente; las añade el middleware `add_security_headers` sobre la respuesta generada.

---

🔖 Última revisión: 2026-05-24
