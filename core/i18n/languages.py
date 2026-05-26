"""
Idiomas soportados por el backend de TravianBot.
Fuente de verdad única: tanto la capa API (get_language) como
el adaptador de traducciones importan desde aquí.

Los 25 códigos corresponden exactamente a las claves de idioma que existen en
core/i18n/catalog/base/troops.json (generado por el scraper de kirilloid).
Son códigos de kirilloid, NO estrictamente BCP-47: por ejemplo 'rs' identifica
el serbio (Serbia) donde BCP-47 usaría 'sr'. Se mantienen tal cual para que
cualquier código soportado resuelva directamente a datos en el catálogo sin
transformación. Ver docs/api/API.md para la tabla de correspondencias.
"""

SUPPORTED_LANGUAGES: frozenset[str] = frozenset({
    "ar", "bg", "cs", "da", "de", "el", "en", "es", "fa",
    "fr", "he", "hu", "it", "ja", "lt", "lv", "nl", "pl",
    "pt", "rs", "ru", "sl", "sv", "tr", "uk",
})
DEFAULT_LANGUAGE: str = "es"
