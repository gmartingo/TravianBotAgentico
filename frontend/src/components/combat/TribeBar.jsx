/**
 * TribeBar — Selector de tribu con avatares circulares.
 *
 * Props:
 *   tribes        — array de { id, label } (ordenados: nature primero si es defensor)
 *   selectedTribe — id de la tribu actualmente seleccionada
 *   onSelect      — (tribeId) => void
 *   label         — string accesible para describir el grupo (aria-label del grupo)
 *
 * Cada avatar muestra las iniciales de la tribu en mayúsculas.
 * El avatar seleccionado lleva borde en var(--accent) + anillo visible.
 * Targets mínimos 44px para táctil (DESIGN.md §17.6).
 */
import { useI18n } from '../../i18n/index.jsx'

// Paletas de color por tribu (fondo neutro escalado, nunca neón)
const TRIBE_COLORS = {
  romans:    { bg: '#E8E0F0', text: '#5B3A8A' },
  teutons:   { bg: '#E8EAD8', text: '#4A5230' },
  gauls:     { bg: '#D8EEE0', text: '#1E6040' },
  egyptians: { bg: '#F0E8D0', text: '#7A5010' },
  huns:      { bg: '#F0D8D8', text: '#7A1E1E' },
  spartans:  { bg: '#D8E4F0', text: '#1E3E7A' },
  vikings:   { bg: '#D8ECF0', text: '#1E5E6A' },
  nature:    { bg: '#E4F0D8', text: '#2E6020' },
}

function tribeInitials(tribeId) {
  if (!tribeId) return '?'
  // Primeros 2 caracteres en mayúsculas
  return tribeId.slice(0, 2).toUpperCase()
}

export function TribeBar({ tribes, selectedTribe, onSelect, label }) {
  const { t } = useI18n()

  if (!tribes || tribes.length === 0) return null

  return (
    <div
      role="radiogroup"
      aria-label={label ?? t('calc.tribe.select')}
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: '8px',
        padding: '8px 0',
      }}
    >
      {tribes.map(({ id, labelKey, labelText }) => {
        const isSelected = selectedTribe === id
        const colors = TRIBE_COLORS[id] ?? { bg: 'var(--surface-2)', text: 'var(--text-secondary)' }
        const displayLabel = labelText ?? (labelKey ? t(labelKey) : id)

        return (
          <button
            key={id}
            type="button"
            role="radio"
            aria-checked={isSelected}
            aria-label={displayLabel}
            title={displayLabel}
            onClick={() => onSelect(id)}
            style={{
              // Dimensiones mínimas 44px para táctil
              width: '44px',
              height: '44px',
              borderRadius: 'var(--radius-full)',
              border: isSelected
                ? '2px solid var(--accent)'
                : '2px solid var(--border)',
              outline: isSelected
                ? '2px solid var(--accent)'
                : 'none',
              outlineOffset: '2px',
              background: isSelected ? colors.bg : 'var(--surface-2)',
              color: isSelected ? colors.text : 'var(--text-secondary)',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 700,
              fontSize: '13px',
              fontFamily: 'inherit',
              letterSpacing: '.01em',
              transition: [
                'border-color var(--dur-fast) var(--ease)',
                'background var(--dur-fast) var(--ease)',
                'color var(--dur-fast) var(--ease)',
                'outline var(--dur-fast) var(--ease)',
              ].join(', '),
              flexShrink: 0,
              userSelect: 'none',
            }}
            // Foco visible (DESIGN.md §12 — nunca outline:none sin reemplazo)
            onFocus={e => {
              if (!isSelected) e.currentTarget.style.outline = '2px solid var(--accent)'
              e.currentTarget.style.outlineOffset = '2px'
            }}
            onBlur={e => {
              if (!isSelected) e.currentTarget.style.outline = 'none'
            }}
          >
            {tribeInitials(id)}
          </button>
        )
      })}
    </div>
  )
}
