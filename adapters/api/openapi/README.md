# OpenAPI / Swagger

Lugar recomendado para almacenar snapshots de OpenAPI/Swagger auto-generados.

Patrón sugerido:
- Durante desarrollo: exponer `/openapi.json` desde FastAPI.
- Para auditoría/versionado: guardar snapshots en `documentacion/openapi/`.
