"""
Drops de recursos por matar animales de naturaleza.

Cuando se matan animales NATURE en Travian, el héroe recibe recursos directamente.
Los drops están desglosados por tipo de recurso (wood, clay, iron, crop).

DECISIÓN DE IMPLEMENTACIÓN: Opción B (dict estático).
No se añaden columnas a la BD — el dict aquí es la fuente de verdad.
Motivo: los valores de drops no se scrapearon de kirilloid (campo no disponible),
y añadir columnas a troop_stats requeriría migración sin beneficio neto en este MVP.

CONFIRMACIÓN DE DATOS (validados con reportes de batalla reales, 2026-05-29):
  Ord 1-4 (Rata, Araña, Serpiente, Murciélago): 40/recurso
  Ord 5-6 (Jabalí, Lobo): 80/recurso
  Ord 7-8 (Oso, Cocodrilo): 120/recurso
  Ord 9-10 (Tigre, Elefante): pendiente confirmar

  NOTA: bat(4)=40 no 80; bear(7)=120 no 160; croc(8)=120 no 200.
  Fuentes: 12rat+6spi+3bat=840; 10boar+9wolf+2bear=1760; 1croc=120.

Ver spec §RN-08 para detalle completo.
"""

# ordinal NATURE (1..10) → drop por tipo de recurso
NATURE_DROPS: dict[int, dict[str, int]] = {
    1:  {"wood": 40,  "clay": 40,  "iron": 40,  "crop": 40},  # Rata       — OK
    2:  {"wood": 40,  "clay": 40,  "iron": 40,  "crop": 40},  # Araña      — OK
    3:  {"wood": 40,  "clay": 40,  "iron": 40,  "crop": 40},  # Serpiente  — OK
    4:  {"wood": 40,  "clay": 40,  "iron": 40,  "crop": 40},  # Murciélago — OK (era 80)
    5:  {"wood": 80,  "clay": 80,  "iron": 80,  "crop": 80},  # Jabalí     — OK
    6:  {"wood": 80,  "clay": 80,  "iron": 80,  "crop": 80},  # Lobo       — OK
    7:  {"wood": 120, "clay": 120, "iron": 120, "crop": 120}, # Oso        — OK (era 160)
    8:  {"wood": 120, "clay": 120, "iron": 120, "crop": 120}, # Cocodrilo  — OK (era 200)
    9:  {"wood": 240, "clay": 240, "iron": 240, "crop": 240}, # Tigre      — pendiente
    10: {"wood": 300, "clay": 300, "iron": 300, "crop": 300}, # Elefante   — pendiente
}


def get_nature_drop(ordinal: int, resource: str) -> int:
    """
    Devuelve el drop de un tipo de recurso para un animal de naturaleza.

    Args:
        ordinal: ordinal 1-based del animal NATURE (1=Rata, 10=Elefante).
        resource: clave de recurso — "wood", "clay", "iron" o "crop".

    Returns:
        Drop en unidades de recurso. Devuelve 0 si el ordinal o recurso no existe.
    """
    return NATURE_DROPS.get(ordinal, {}).get(resource, 0)
