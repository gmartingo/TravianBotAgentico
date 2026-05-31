/**
 * SessionOverridePanel — Los 3 botones de override de modo.
 *
 * Props:
 *  - currentMode {string}   — modo efectivo actualmente (del status panel)
 *  - overrideMode {string|null} — si hay override activo, su modo
 *  - loading {string|null}  — qué botón está en cargando: 'HARDCORE'|'IDLE'|'DISCONNECTED'|null
 *  - onOverride {function}  — fn(mode: string) → dispara PUT /session/mode
 *
 * Spec §7 (estados de botones de override), §9 (microcopy), §12 (interacciones).
 */
import { useI18n } from '../../i18n/index.jsx'
import { Spinner } from '../ui/uiUtils.jsx'

const MODES = [
  { value: 'HARDCORE',     cssClass: 'hardcore',     iconSymbol: '●' },
  { value: 'IDLE',         cssClass: 'idle',         iconSymbol: '~' },
  { value: 'DISCONNECTED', cssClass: 'disconnected', iconSymbol: '○' },
]

function modeLabelKey(mode) {
  if (mode === 'HARDCORE') return 'session.mode.hardcore'
  if (mode === 'IDLE') return 'session.mode.idle'
  return 'session.mode.disconnected'
}

export function SessionOverridePanel({ currentMode, overrideMode, loading, onOverride }) {
  const { t } = useI18n()

  // El modo "activo" visual es el override si existe, sino el modo del bloque
  const effectiveMode = overrideMode ?? currentMode

  const anyLoading = loading !== null

  return (
    <div style={cardStyle}>
      <div style={cardTitleStyle}>{t('session.override.title')}</div>

      <div
        role="group"
        aria-label={t('session.override.title')}
        style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}
      >
        {MODES.map(({ value, cssClass, iconSymbol }) => {
          const isEffective = effectiveMode?.toUpperCase() === value
          const isLoading = loading === value
          const disabled = anyLoading && !isLoading
          const modeLabel = t(modeLabelKey(value))

          return (
            <button
              key={value}
              type="button"
              disabled={disabled}
              aria-pressed={isEffective}
              aria-label={`${t('session.override.title')}: ${modeLabel}`}
              onClick={() => !disabled && onOverride(value)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '8px 16px',
                border: isEffective
                  ? `1px solid var(--mode-${cssClass})`
                  : '1px solid var(--border-strong)',
                borderRadius: 'var(--radius-sm)',
                background: isEffective
                  ? `var(--mode-${cssClass}-subtle)`
                  : 'var(--surface)',
                color: isEffective
                  ? `var(--mode-${cssClass})`
                  : 'var(--text)',
                fontSize: '13px',
                fontWeight: 500,
                cursor: disabled ? 'not-allowed' : 'pointer',
                opacity: disabled ? 0.5 : 1,
                fontFamily: 'inherit',
                minHeight: '36px',
                transition: 'background var(--dur-fast), border-color var(--dur-fast), color var(--dur-fast)',
              }}
            >
              {isLoading ? (
                <Spinner size={14} />
              ) : (
                <span
                  aria-hidden="true"
                  style={{
                    width: '7px', height: '7px',
                    borderRadius: '50%',
                    background: `var(--mode-${cssClass})`,
                    flexShrink: 0,
                  }}
                />
              )}
              {modeLabel}
            </button>
          )
        })}
      </div>

      <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '6px' }}>
        {t('session.override.subtitle')}
        {' · '}
        {t('session.timeline.antiDetectionHint')}
      </div>
    </div>
  )
}

const cardStyle = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-md)',
  padding: '16px 20px',
}

const cardTitleStyle = {
  fontSize: '11px', fontWeight: 600,
  letterSpacing: '.05em', textTransform: 'uppercase',
  color: 'var(--text-secondary)', marginBottom: '12px',
}
