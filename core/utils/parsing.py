"""
Utilidades de parseo puro compartidas entre el scraper de kirilloid y los parsers
de overview de Travian.

Todas las funciones son puras: sin IO, sin dependencias externas, testables de forma
aislada. Pertenecen al core porque son lógica de dominio (transformación de datos del
juego), no infraestructura.

Funciones exportadas:
  - parse_time(text)         — "H:MM:SS" → segundos enteros
  - parse_int(text)          — "1.200" / "‭8,786‬" → int (elimina bidi + separadores)
  - parse_int_or_none(text)  — igual pero devuelve None para "—", vacío o no numérico
"""
from __future__ import annotations

# Caracteres de control Unicode bidi que Travian inyecta alrededor de los números.
# U+202D — LEFT-TO-RIGHT OVERRIDE (‭)
# U+202C — POP DIRECTIONAL FORMATTING (‬)
_BIDI_CHARS = "‭‬"


def parse_time(text: str) -> int:
    """
    Convierte "H:MM:SS" a segundos enteros.

    El texto puede tener espacios u otras partes (p.ej. "0:30:00 / 2880 / jornada").
    Solo se usa la primera parte antes del espacio.

    Caso especial: algunas unidades NPC o instantáneas muestran el tiempo como un
    entero pelado sin ":" (p.ej. "0", "5"). Se interpreta directamente como segundos.

    Lanza ValueError si el formato no es válido.
    """
    text = text.strip().split()[0]
    # Entero pelado sin ":" → segundos directos
    if ":" not in text:
        try:
            return int(text)
        except ValueError:
            raise ValueError(f"Formato de tiempo inesperado: '{text}'")
    parts = text.split(":")
    if len(parts) != 3:
        raise ValueError(f"Formato de tiempo inesperado: '{text}'")
    try:
        h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        raise ValueError(f"Formato de tiempo inesperado: '{text}'")
    return h * 3600 + m * 60 + s


def parse_int(text: str) -> int:
    """
    Convierte un entero con separadores de miles a int.

    Acepta tanto "." como "," como separadores de miles (ej: "1.200" → 1200,
    "1,200" → 1200).

    Elimina los caracteres de control bidi U+202D (‭) y U+202C (‬) que Travian
    inyecta alrededor de los números en las páginas de statistics (ej: "‭8,786‬").

    Lanza ValueError si el texto no es convertible a int tras la limpieza.
    """
    cleaned = text.strip().translate(str.maketrans("", "", _BIDI_CHARS))
    cleaned = cleaned.replace(".", "").replace(",", "")
    return int(cleaned)


def parse_int_or_none(text: str) -> int | None:
    """
    Como parse_int pero devuelve None para "—", vacío o texto no numérico.

    También elimina los caracteres de control bidi U+202D y U+202C antes de
    intentar la conversión.

    Conforme a la regla de negocio: valores "—" → None/NULL, nunca 0.
    """
    stripped = text.strip().translate(str.maketrans("", "", _BIDI_CHARS))
    if stripped in ("—", "", "-"):
        return None
    try:
        return parse_int(stripped)
    except ValueError:
        return None
