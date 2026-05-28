/**
 * Countdown — ticker HH:MM:SS que descuenta en tiempo real.
 *
 * Props:
 *  - targetIso {string|null}  — ISO datetime del próximo evento. Si null → muestra dash.
 *  - dash      {string}       — texto cuando no hay countdown (default "—")
 *  - className {string}       — clases extra (tamaño, color)
 *
 * Accesibilidad:
 *  - aria-live="off" — no anunciar cada segundo (ruido de screen reader)
 *  - aria-atomic — irrelevante sin live, pero documentado por si cambia
 *  - Valor semántico: texto legible en todo momento.
 *
 * La fuente mono + tabular-nums se aplica externamente via className.
 */
import { useState, useEffect } from 'react'

function secsUntil(isoString) {
  if (!isoString) return null
  const diff = Math.floor((new Date(isoString) - Date.now()) / 1000)
  return Math.max(0, diff)
}

function formatHMS(secs) {
  if (secs === null || secs < 0) return null
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  const s = secs % 60
  return (
    String(h).padStart(2, '0') + ':' +
    String(m).padStart(2, '0') + ':' +
    String(s).padStart(2, '0')
  )
}

export function Countdown({ targetIso, dash = '—', className = '' }) {
  const [secs, setSecs] = useState(() => secsUntil(targetIso))

  useEffect(() => {
    setSecs(secsUntil(targetIso))
    if (!targetIso) return

    const id = setInterval(() => {
      setSecs(secsUntil(targetIso))
    }, 1000)
    return () => clearInterval(id)
  }, [targetIso])

  const text = secs !== null ? (formatHMS(secs) ?? dash) : dash
  const isDash = text === dash

  return (
    <span
      aria-live="off"
      className={className}
      style={{ fontVariantNumeric: 'tabular-nums' }}
    >
      {isDash
        ? <span style={{ color: 'var(--text-disabled)' }}>{dash}</span>
        : text
      }
    </span>
  )
}

/**
 * ExactTime — muestra la hora exacta (HH:MM:SS) a la que ocurre el evento.
 * Complementa al Countdown en el mockup.
 */
export function ExactTime({ targetIso, className = '' }) {
  if (!targetIso) return null
  const d = new Date(targetIso)
  const text =
    String(d.getHours()).padStart(2, '0') + ':' +
    String(d.getMinutes()).padStart(2, '0') + ':' +
    String(d.getSeconds()).padStart(2, '0')
  return (
    <span aria-hidden="true" className={className}
      style={{ fontVariantNumeric: 'tabular-nums' }}>
      {text}
    </span>
  )
}
