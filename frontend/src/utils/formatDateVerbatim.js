/**
 * formatDateVerbatim — Formatea un string ISO 8601 naive (sin zona horaria)
 * directamente como texto, SIN construir un objeto Date.
 *
 * Problema que resuelve: `new Date("2026-05-31T13:39:30")` interpreta el string
 * como UTC y después lo convierte a la zona local del navegador. En España (UTC+2
 * en verano), mostraría 15:39 en lugar de 13:39. La hora de Travian es verbatim
 * (hora local del servidor de juego) y debe mostrarse tal cual.
 *
 * Formato de salida: "DD/MM/YY HH:MM" → "31/05/26 13:39"
 *
 * IMPORTANTE: Solo usar para campos `attacked_at` (hora de Travian, verbatim).
 * El campo `created_at` (hora del sistema del usuario) sigue usando
 * `new Date()` + `Intl.DateTimeFormat` porque sí tiene semántica de zona horaria.
 *
 * @param {string|null} isoStr - String ISO 8601 naive: "2026-05-31T13:39:30"
 * @returns {string} Fecha formateada "DD/MM/YY HH:MM" o "—" si falsy
 */
export function formatDateVerbatim(isoStr) {
  if (!isoStr) return '—'
  // Separar fecha y hora: "2026-05-31T13:39:30" → ["2026-05-31", "13:39:30"]
  const tIdx = isoStr.indexOf('T')
  if (tIdx === -1) return isoStr
  const datePart = isoStr.slice(0, tIdx)
  const timePart = isoStr.slice(tIdx + 1)
  // Separar año, mes, día
  const parts = datePart.split('-')
  if (parts.length < 3) return isoStr
  const [y, m, d] = parts
  // Tomar solo HH:MM de la hora (sin segundos ni fracciones)
  const timeShort = timePart ? timePart.slice(0, 5) : ''
  // Formato: DD/MM/YY HH:MM
  return timeShort
    ? `${d}/${m}/${y.slice(2)} ${timeShort}`
    : `${d}/${m}/${y.slice(2)}`
}
