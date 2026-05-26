"""
Mapeado global uNN → (Tribe, ordinal) para resolución de nombres localizados.

Travian usa numeración GLOBAL de unidades en las clases CSS de imágenes:
  u1–u10   → ROMANS   (ordinal 1–10)
  u11–u20  → TEUTONS  (ordinal 1–10)
  u21–u30  → GAULS    (ordinal 1–10)
  u31–u40  → NATURE   (ordinal 1–10)  — NPC; tiene entradas completas en el catálogo
  u41–u50  → EGYPTIANS (ordinal 1–10)
  u51–u60  → HUNS     (ordinal 1–10)
  u61–u71  → NATARS   (ordinal 1–11)  — NPC; NATARS_11 tiene nombre vacío en el catálogo
  u72–u81  → SPARTANS (ordinal 1–10)  — expansión jugable
  u82–u91  → VIKINGS  (ordinal 1–10)  — expansión jugable
  uhero    → None (el héroe no tiene entrada en el catálogo)

Verificado contra core/i18n/catalog/base/troops.json y core/entities/tribe.py.
El llamador debe manejar el retorno None devolviendo un fallback razonable (p.ej. unit_class).
"""
from core.entities.tribe import Tribe

_RANGES: list[tuple[int, int, Tribe]] = [
    (1,  10, Tribe.ROMANS),
    (11, 20, Tribe.TEUTONS),
    (21, 30, Tribe.GAULS),
    (31, 40, Tribe.NATURE),
    (41, 50, Tribe.EGYPTIANS),
    (51, 60, Tribe.HUNS),
    (61, 71, Tribe.NATARS),
    (72, 81, Tribe.SPARTANS),
    (82, 91, Tribe.VIKINGS),
]


def unit_class_to_tribe_ordinal(unit_class: str) -> tuple[Tribe, int] | None:
    """
    Convierte la clase CSS global de una unidad Travian a (Tribe, ordinal 1-based).

    El ordinal es 1-based dentro de la tribu:
      "u1"   → (Tribe.ROMANS, 1)
      "u10"  → (Tribe.ROMANS, 10)
      "u11"  → (Tribe.TEUTONS, 1)
      "u22"  → (Tribe.GAULS, 2)   — u21=GAULS_1, u22=GAULS_2, ...
      "u31"  → (Tribe.NATURE, 1)
      "u41"  → (Tribe.EGYPTIANS, 1)
      "u51"  → (Tribe.HUNS, 1)
      "u61"  → (Tribe.NATARS, 1)
      "u71"  → (Tribe.NATARS, 11) — NATARS_11 existe en catálogo pero nombre vacío → fallback
      "u72"  → (Tribe.SPARTANS, 1)
      "u82"  → (Tribe.VIKINGS, 1)
      "uhero" → None
      "u99"  → None  (fuera de rango)
      "foo"  → None  (no empieza por "u")
      ""     → None
      "u"    → None  (sin sufijo numérico)

    Esta función nunca lanza; siempre devuelve (Tribe, int) o None.
    """
    if not unit_class or unit_class == "uhero" or not unit_class.startswith("u"):
        return None
    suffix = unit_class[1:]
    if not suffix.isdigit():
        return None
    n = int(suffix)
    for start, end, tribe in _RANGES:
        if start <= n <= end:
            ordinal = n - start + 1
            return tribe, ordinal
    return None
