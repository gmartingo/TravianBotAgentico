"""
Mapeo de error_code de dominio → HTTP status code.

El exception handler global usa este mapa para determinar el status
de la respuesta cuando atrapa una TravianBotError.
"""

ERROR_HTTP_MAP: dict[str, int] = {
    "ACCOUNT_NOT_FOUND":          404,
    "DUPLICATE_ACCOUNT":          409,
    "WORLD_NOT_FOUND":            404,
    # 503: sesión no activa = el servicio de Travian no está disponible ahora mismo.
    # No es 409 (conflicto de estado de recurso) sino fallo transitorio del servicio.
    "SESSION_NOT_ACTIVE":         503,
    "INVALID_CREDENTIALS":        401,
    "VILLAGE_NOT_FOUND":          404,
    "FARM_LIST_NOT_FOUND":        404,
    "TROOP_NOT_FOUND":            404,
    "BUILDING_NOT_FOUND":         404,
    "LOGIN_ERROR":                500,
    "BROWSER_ERROR":              500,
    "DATABASE_ERROR":             500,
    # --- Excepciones añadidas en la feature registro-cuentas-mundos ---
    "DUPLICATE_WORLD":          409,
    "ACTIVE_SESSION_CONFLICT":  409,
}

DEFAULT_ERROR_STATUS: int = 500
