---
name: parsing-utils-bidi
description: parse_int/parse_int_or_none/parse_time están en core/utils/parsing.py; eliminan caracteres bidi U+202D/U+202C de Travian
metadata:
  type: project
---

Las funciones de parseo compartidas viven en `core/utils/parsing.py`:
- `parse_int(text)` — elimina bidi U+202D (‭) y U+202C (‬) antes de quitar separadores de miles (. o ,).
- `parse_int_or_none(text)` — igual pero devuelve None para "—", "" o "-".
- `parse_time(text)` — H:MM:SS → segundos; acepta entero pelado "0"/"5".

Estas funciones son importadas también en `adapters/scraper/kirilloid_scraper.py` (refactorizadas desde funciones privadas _parse_int, etc.).

**Why:** Travian envuelve números en páginas de statistics con bidi U+202D/U+202C; sin limpiarlos int() lanza ValueError.

**How to apply:** cualquier parser de overview debe usar estas funciones para convertir números del HTML de Travian. No redefinirlas en los adaptadores.
