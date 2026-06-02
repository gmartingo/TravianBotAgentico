/**
 * oasisSpawnCatalog.js — Espejo JS del catálogo de spawn de oasis.
 *
 * Fuente canónica Python: core/game_data/oasis_spawn_catalog.py
 * Esta copia es solo para el frontend (panel educativo estático).
 * NO consume API. Si el catálogo Python cambia, actualizar aquí también.
 *
 * RN-CAT-01: SPAWN_TIMER_S es la única fuente de verdad para timers.
 * RN-CAT-02: datos de defensa vienen de troop_stats.json (backend).
 * RN-CAT-03: nombres localizados via i18n clave NATURE_{ordinal}.
 */

/**
 * Ordinales de los 10 animales nature (orden fijo de spawn en Travian).
 * Ordinal → nombre canónico en español (solo para referencia interna).
 */
export const NATURE_ORDINALS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

/**
 * Timer de spawn en segundos (servidor x1). Ordinal → segundos.
 * Rata = 5 min, Araña = 6 min, ... Elefante = 14 min.
 */
export const SPAWN_TIMER_S = {
  1: 300,   // Rata       5:00
  2: 360,   // Araña      6:00
  3: 420,   // Serpiente  7:00
  4: 480,   // Murciélago 8:00
  5: 540,   // Jabalí     9:00
  6: 600,   // Lobo      10:00
  7: 660,   // Oso       11:00
  8: 720,   // Cocodrilo 12:00
  9: 780,   // Tigre     13:00
  10: 840,  // Elefante  14:00
}

/**
 * Sets normales de animales por tipo de oasis.
 * Clave = tipo de oasis; valor = array de ordinales del set base.
 * Un animal fuera de este set se clasifica como "anomalía".
 *
 * Keys: "hierro" | "arcilla" | "madera" | "cereal"
 * Clave i18n del tipo: stats.spawn.oasis_type.{key}
 */
export const OASIS_TYPE_SETS = {
  hierro:  [1, 2, 4],          // rata, araña, murciélago
  arcilla: [1, 2, 5],          // rata, araña, jabalí
  madera:  [5, 6, 7],          // jabalí, lobo, oso
  cereal:  [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],  // todos
}

/**
 * Convierte segundos a formato "MM:SS".
 * Ej: 300 → "5:00", 840 → "14:00"
 */
export function formatTimerMmSs(seconds) {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

/**
 * Orden canónico de los tipos de oasis para la tabla de sets.
 */
export const OASIS_TYPE_ORDER = ['hierro', 'arcilla', 'madera', 'cereal']
