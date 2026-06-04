"""
Catálogo de mecánica de spawn de oasis (servidor x1).

Fuente canónica de timers y sets de animales para toda la aplicación.

RN-CAT-01: SPAWN_TIMER_S es la única fuente de verdad para los timers de spawn.
           Ningún módulo hardcodea tiempos fuera de este fichero.

RN-CAT-02: Los datos de defensa de animales (def_infantry, def_cavalry) se leen
           de seeds/game_data/troop_stats.json filtrando tribe == "nature".

RN-CAT-03: Los nombres localizados se obtienen de core/i18n/catalog/base/troops.json
           con la clave NATURE_{ordinal}. Los endpoints numéricos no incluyen nombres.

Extensibilidad (TR-01 / RN-WORST-07): para velocidad de servidor != x1, dividir
SPAWN_TIMER_S[o] por la velocidad. No implementado en v1.

Ver spec docs/specs/oasis-spawn-mechanics-stats.md §4.1.
Añadido en la feature oasis-spawn-mechanics-stats (2026-06-02).
"""

# Nombre canónico de cada animal: mapeado al ordinal usado en troop_stats.json y i18n.
# Para nombres localizados usar core/i18n/catalog/base/troops.json → NATURE_{ordinal}
NATURE_ORDINALS: dict[str, int] = {
    "rata":        1,
    "araña":       2,
    "serpiente":   3,
    "murciélago":  4,
    "jabalí":      5,
    "lobo":        6,
    "oso":         7,
    "cocodrilo":   8,
    "tigre":       9,
    "elefante":    10,
}

# Timer de spawn en segundos (servidor x1). Ordinal → segundos.
SPAWN_TIMER_S: dict[int, int] = {
    1: 300,   # rata       5:00
    2: 360,   # araña      6:00
    3: 420,   # serpiente  7:00
    4: 480,   # murciélago 8:00
    5: 540,   # jabalí     9:00
    6: 600,   # lobo      10:00
    7: 660,   # oso       11:00
    8: 720,   # cocodrilo 12:00
    9: 780,   # tigre     13:00
    10: 840,  # elefante  14:00
}

# Sets normales de animales por tipo de oasis.
# Clave = nombre del tipo (para etiquetas UI); valor = set de ordinales del set base.
# Un animal fuera de este set que aparezca en reportes se clasifica como "anomalía".
OASIS_TYPE_SETS: dict[str, set[int]] = {
    "hierro":  {1, 2, 4},          # rata, araña, murciélago
    "arcilla": {1, 2, 5},          # rata, araña, jabalí
    "madera":  {5, 6, 7},          # jabalí, lobo, oso
    "cereal":  {1, 2, 3, 4, 5, 6, 7, 8, 9, 10},  # todos + muchos tigres/elefantes
}

# Umbral de cooldown (heurístico, v1): si elapsed_s supera este valor, el oasis
# probablemente está en cooldown. 4 horas como valor conservador (TR-02).
# Ajustable aquí sin tocar el adaptador.
COOLDOWN_THRESHOLD_S: int = 4 * 3600  # 14_400 segundos
