---
name: fastapi-conventions
description: Convenciones FastAPI del proyecto TravianBot — headers, errores, lifespan, middleware
metadata:
  type: project
---

Convenciones FastAPI de este proyecto (2026-05-24):

1. **Lifespan (NO on_event)**: usar `@asynccontextmanager async def lifespan(app)` + `FastAPI(lifespan=lifespan)`. `on_event` está deprecado en FastAPI 0.136.

2. **Header Accept-Language como opcional para dar 400 (no 422)**: declarar `accept_language: str | None = Header(default=None, alias="Accept-Language")` y lanzar HTTPException 400 manualmente si es None. FastAPI devuelve 422 para headers `...` faltantes — no coincide con el contrato de API del proyecto.

3. **TestClient debe usar context manager**: `with TestClient(app) as client:` para disparar el lifespan (startup). Sin `with`, `app.state.translation_port` no existe y los tests fallan con AttributeError.

4. **Cabeceras mínimas via middleware**: X-Request-ID (eco o UUID), X-API-Version, X-Content-Type-Options: nosniff, X-Frame-Options: DENY se añaden en middleware `@app.middleware("http")`.

5. **Cache-Control solo en 2xx de /catalog/**: middleware separado que solo añade `Cache-Control: public, max-age=3600` si `path.startswith('/catalog/')` y `status_code < 300`. NO heredar en 4xx/5xx.

6. **Exception handler**: `@app.exception_handler(TravianBotError)` — traduce via `app.state.translation_port.get_message(exc.error_code, lang, **exc.params)`.

**Why:** Estas convenciones salieron de la implementación real y los tests del spec i18n-backend.

**How to apply:** En cualquier endpoint nuevo o modificación de main.py.
