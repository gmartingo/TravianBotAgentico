/**
 * time.js — Utilidades de conversión de tiempo para el frontend.
 *
 * Spec: docs/specs/noise-frequency-and-destination-weight.md §9.3, CA-FW17
 */

/**
 * Convierte una cadena "MM:SS" a segundos enteros.
 * Acepta tanto "7:20" como "07:20".
 *
 * @param {string} mmss — cadena en formato MM:SS
 * @returns {number} segundos enteros
 * @throws {Error} si el formato es inválido
 *
 * @example
 * mmssToSeconds("05:00")  // → 300
 * mmssToSeconds("7:20")   // → 440
 * mmssToSeconds("20:10")  // → 1210
 */
export function mmssToSeconds(mmss) {
  if (typeof mmss !== 'string') throw new Error('Se esperaba una cadena MM:SS')
  const parts = mmss.trim().split(':')
  if (parts.length !== 2) throw new Error('Formato inválido: se espera MM:SS')
  const mm = parseInt(parts[0], 10)
  const ss = parseInt(parts[1], 10)
  if (isNaN(mm) || isNaN(ss)) throw new Error('MM:SS inválido: los valores deben ser números')
  if (ss < 0 || ss > 59) throw new Error('Los segundos deben estar entre 0 y 59')
  if (mm < 0) throw new Error('Los minutos no pueden ser negativos')
  return mm * 60 + ss
}

/**
 * Convierte segundos enteros a cadena "MM:SS" con ceros a la izquierda en SS.
 *
 * @param {number} seconds — segundos enteros (>= 0)
 * @returns {string} cadena en formato "M:SS" (los minutos sin cero inicial si < 10)
 *
 * @example
 * secondsToMmss(300)  // → "5:00"
 * secondsToMmss(440)  // → "7:20"
 * secondsToMmss(30)   // → "0:30"
 * secondsToMmss(1200) // → "20:00"
 */
export function secondsToMmss(seconds) {
  const s = Math.max(0, Math.floor(seconds))
  const mm = Math.floor(s / 60)
  const ss = s % 60
  return `${mm}:${String(ss).padStart(2, '0')}`
}

/**
 * Verifica si una cadena es un formato MM:SS válido.
 * Devuelve null si es válida, o un mensaje de error si no lo es.
 *
 * @param {string} mmss
 * @param {number} [minSeconds=0] — mínimo de segundos aceptado
 * @returns {string|null} null si válido, mensaje de error si inválido
 */
export function validateMmss(mmss, minSeconds = 0) {
  try {
    const secs = mmssToSeconds(mmss)
    if (secs < minSeconds) {
      return `Mínimo ${secondsToMmss(minSeconds)} (${minSeconds} s)`
    }
    return null
  } catch (e) {
    return 'Formato inválido — usa MM:SS (p. ej. 05:00)'
  }
}
