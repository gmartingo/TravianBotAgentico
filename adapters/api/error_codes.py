"""
Mapeo de error_code de dominio → HTTP status code.

El exception handler global usa este mapa para determinar el status
de la respuesta cuando atrapa una TravianBotError.
"""

ERROR_HTTP_MAP: dict[str, int] = {
    "ACCOUNT_NOT_FOUND":    404,
    "DUPLICATE_ACCOUNT":    409,
    "WORLD_NOT_FOUND":      404,
    "SESSION_NOT_ACTIVE":   409,
    "INVALID_CREDENTIALS":  401,
    "VILLAGE_NOT_FOUND":    404,
    "FARM_LIST_NOT_FOUND":  404,
    "TROOP_NOT_FOUND":      404,
    "BUILDING_NOT_FOUND":   404,
    "LOGIN_ERROR":          500,
    "BROWSER_ERROR":        500,
    "DATABASE_ERROR":       500,
}

DEFAULT_ERROR_STATUS: int = 500
