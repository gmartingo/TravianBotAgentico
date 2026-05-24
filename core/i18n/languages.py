"""
Idiomas soportados por el backend de TravianBot.
Fuente de verdad única: tanto la capa API (get_language) como
el adaptador de traducciones importan desde aquí.
"""

SUPPORTED_LANGUAGES: frozenset[str] = frozenset({"es", "en", "de", "fr", "ru"})
DEFAULT_LANGUAGE: str = "es"
