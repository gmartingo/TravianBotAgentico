/**
 * PlayerOasisSection — Sección colapsable de un jugador (nivel 1 del anidado v2.6).
 *
 * Spec: docs/design/oasis-spawn-mechanics.md §v2.6
 *
 * Muestra una cabecera de jugador (nombre + contador discreto de aldeas u oasis)
 * y debajo los CityOasisSection de sus aldeas. Expandida por defecto.
 *
 * Jerarquía visual respecto a CityOasisSection (nivel aldea):
 *   - Fondo de cabecera: var(--surface-2) con hairline border-bottom — distingue al jugador
 *     del nivel aldea (que es solo border-bottom transparente sobre fondo blanco/grafito).
 *   - Nombre: 14px, fontWeight 700 (vs 13px/600 de aldea).
 *   - Chevron: mismo SVG inline, pero tamaño 15px.
 *   - Contador: 11px, var(--text-tertiary), tabular-nums — idéntico al de aldea.
 *   - margen inferior 24px entre jugadores (vs 20px entre aldeas).
 *
 * Props:
 *   playerName  — string: nombre del jugador (ya localizado si era "Desconocido")
 *   rawName     — string: nombre raw del backend (para keys únicas)
 *   villageCount — number: cuántas aldeas tiene este jugador
 *   t           — función de traducción
 *   children    — CityOasisSection renderizados por el padre
 */
import { useState } from 'react'

function Chevron({ open }) {
  return (
    <svg
      aria-hidden="true"
      width="15"
      height="15"
      viewBox="0 0 14 14"
      fill="none"
      style={{
        flexShrink: 0,
        transform: open ? 'rotate(0deg)' : 'rotate(-90deg)',
        transition: 'transform var(--dur-fast, 120ms) ease',
        color: 'var(--text-secondary)',
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

export function PlayerOasisSection({ playerName, rawName, villageCount, t, children }) {
  const [open, setOpen] = useState(true)

  const villageLabel =
    villageCount === 1
      ? t('stats.planner.player_village_count_one')
      : t('stats.planner.player_village_count_pl', { n: villageCount })

  const headerId = `player-section-${rawName.replace(/\s+/g, '-').toLowerCase()}`

  return (
    <section
      aria-labelledby={headerId}
      style={{ marginBottom: '24px' }}
    >
      {/* Cabecera del jugador — botón colapsable */}
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
          padding: '8px 12px',
          background: 'var(--surface-2)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)',
          cursor: 'pointer',
          textAlign: 'start',
          outline: 'none',
          marginBottom: '12px',
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
        {/* Nombre del jugador */}
        <span
          style={{
            fontSize: '14px',
            fontWeight: 700,
            color: 'var(--text)',
            flex: 1,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {playerName}
        </span>
        {/* Contador discreto de aldeas */}
        <span
          aria-label={villageLabel}
          style={{
            fontSize: '11px',
            fontWeight: 500,
            color: 'var(--text-tertiary)',
            fontVariantNumeric: 'tabular-nums',
            flexShrink: 0,
          }}
        >
          {villageLabel}
        </span>
      </button>

      {/* Contenido (CityOasisSection blocks) — sangría para distinguir aldea de jugador */}
      {open && (
        <div style={{ paddingInlineStart: '12px' }}>
          {children}
        </div>
      )}
    </section>
  )
}
