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
    # --- Excepciones del tronco de overview ---
    # 503: la página de Travian no cargó en el timeout = servicio no disponible ahora.
    "OVERVIEW_PAGE_NOT_LOADED":   503,
    # 500: fixture no encontrado = error de configuración del entorno de test.
    "OVERVIEW_FIXTURE_NOT_FOUND": 500,
    # --- Excepciones añadidas en la feature registro-cuentas-mundos ---
    "DUPLICATE_WORLD":          409,
    "ACTIVE_SESSION_CONFLICT":  409,
    # --- Excepciones añadidas en la feature login-sesion-api ---
    "LOGIN_FAILED":             401,
    # --- Excepciones añadidas en la feature farm-lists ---
    "SCHEDULER_NOT_FOUND":      404,
    "FARM_SLOT_NOT_FOUND":      404,
    # 502: el browser (gateway hacia Travian) no pudo enviar la lista.
    "FARM_LIST_SEND_ERROR":     502,
    # 502: la página de farm lists no cargó (Gold Club no activo, sin listas, etc.).
    "FARM_LIST_PAGE_ERROR":     502,
    # 500: el DOM devolvió datos malformados (error de parsing interno).
    "FARM_LIST_RESPONSE_ERROR": 500,
}

DEFAULT_ERROR_STATUS: int = 500
