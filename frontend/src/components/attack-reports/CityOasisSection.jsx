/**
 * CityOasisSection — Sección colapsable de una ciudad atacante.
 *
 * Spec: docs/design/oasis-spawn-mechanics.md §v2.3
 *
 * Muestra una cabecera de ciudad (nombre + contador de oasis) y debajo los
 * bloques de oasis que esa ciudad ataca. Expandida por defecto.
 *
 * Props:
 *   cityName  — string: nombre de la ciudad (ya localizado si era "Desconocido")
 *   rawName   — string: nombre raw del backend (para keys únicas)
 *   oasisList — array de objetos oasis
 *   t         — función de traducción
 *   children  — renderización de OasisBlock ya hecha por el padre
 */
import { useState } from 'react'

// ── Icono chevron inline (sin dependencias externas) ─────────────────────────
function Chevron({ open }) {
  return (
    <svg
      aria-hidden="true"
      width="14"
      height="14"
      viewBox="0 0 14 14"
      fill="none"
      style={{
        flexShrink: 0,
        transform: open ? 'rotate(0deg)' : 'rotate(-90deg)',
        transition: 'transform var(--dur-fast, 120ms) ease',
        color: 'var(--text-tertiary)',
      }}
    >
      <path
        d="M3 5l4 4 4-4"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function CityOasisSection({ cityName, rawName, oasisList, t, children }) {
  const [open, setOpen] = useState(true)
  const count = oasisList.length
  const oasisLabel = count === 1
    ? t('stats.planner.city_oasis_count_one')
    : t('stats.planner.city_oasis_count_pl', { n: count })

  const headerId = `city-section-${rawName.replace(/\s+/g, '-').toLowerCase()}`

  return (
    <section
      aria-labelledby={headerId}
      style={{ marginBottom: '20px' }}
    >
      {/* Cabecera de ciudad — botón colapsable */}
      <button
        id={headerId}
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          width: '100%',
          padding: '0 0 8px 0',
          background: 'transparent',
          border: 'none',
          borderBottom: '1px solid var(--border)',
          cursor: 'pointer',
          textAlign: 'start',
          outline: 'none',
          marginBottom: '10px',
        }}
        onFocus={(e) => {
          e.currentTarget.style.outline = '2px solid var(--accent)'
          e.currentTarget.style.outlineOffset = '2px'
        }}
        onBlur={(e) => {
          e.currentTarget.style.outline = ''
          e.currentTarget.style.outlineOffset = ''
        }}
      >
        <Chevron open={open} />
        {/* Nombre de ciudad */}
        <span
          style={{
            fontSize: '13px',
            fontWeight: 600,
            color: 'var(--text)',
            flex: 1,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {cityName}
        </span>
        {/* Contador discret de oasis */}
        <span
          aria-label={oasisLabel}
          style={{
            fontSize: '11px',
            fontWeight: 500,
            color: 'var(--text-tertiary)',
            fontVariantNumeric: 'tabular-nums',
            flexShrink: 0,
          }}
        >
          {oasisLabel}
        </span>
      </button>

      {/* Contenido (oasis blocks) */}
      {open && (
        <div>
          {children}
        </div>
      )}
    </section>
  )
}
