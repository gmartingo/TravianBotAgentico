/**
 * coordUtils — Utilidades de formateo de coordenadas de oasis.
 *
 * Fuente única de verdad para el formato "(x|y)" con signo menos correcto.
 * Deduplicación de la función que existía en:
 *   - OasisList.jsx (formatCoord / formatCoordsDisplay)
 *   - HistoryTable.jsx (formatCoord / formatCoords)
 *   - ReportPreview.jsx (formatCoord / formatCoords)
 *   - OasisStatsPanel.jsx (formatCoord)
 *   - OasisCombatPlannerPanel.jsx (formatCoord)
 *
 * Formato de salida: "(x|y)" — con guión largo U+2212 (−) para negativos,
 * "?" si la coordenada es null/undefined.
 * Ejemplo: formatCoord(−70, 73) → "(−70|73)"
 */

/**
 * Formatea una sola coordenada numérica a string con signo menos correcto.
 * Usa U+2212 (−) para negativos en lugar del ASCII hyphen-minus (-).
 *
 * @param {number|null|undefined} n
 * @returns {string}
 */
export function formatCoordSingle(n) {
  if (n == null) return '?'
  return n < 0 ? `−${Math.abs(n)}` : `${n}`
}

/**
 * Formatea un par de coordenadas en el formato canónico "(x|y)".
 * Usa U+2212 (−) para negativos. Si alguna coordenada es null,
 * aparece "?" en esa posición.
 *
 * @param {number|null|undefined} x
 * @param {number|null|undefined} y
 * @returns {string}  ej. "(−70|73)" o "(15|−3)"
 */
export function formatCoord(x, y) {
  const cx = formatCoordSingle(x)
  const cy = formatCoordSingle(y)
  return `(${cx}|${cy})`
}
