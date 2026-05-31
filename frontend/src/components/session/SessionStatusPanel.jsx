/**
 * SessionStatusPanel — Panel P1 con el estado actual de Human Sessions.
 *
 * Props:
 *  - status {object|null}  — respuesta de GET /worlds/:id/session
 *  - loading {boolean}
 *  - error {string|null}
 *  - onRetry {function}
 *  - onCancelOverride {function}  — dispara PUT mode con el modo del bloque activo
 *  - cancellingOverride {boolean}
 *
 * Spec §7 (estados del panel de estado), §6 (wireframe), §9 (microcopy).
 */
import { useI18n } from '../../i18n/index.jsx'
import { Spinner } from '../ui/uiUtils.jsx'
import { Countdown } from '../world/Countdown.jsx'

// ── Helpers ───────────────────────────────────────────────────────────────────

function modeKey(mode) {
  if (!mode) return 'session.status.mode.disconnected'
  const m = mode.toLowerCase()
  if (m === 'hardcore') return 'session.status.mode.hardcore'
  if (m === 'idle') return 'session.status.mode.idle'
  return 'session.status.mode.disconnected'
}

function modeCssClass(mode) {
  if (!mode) return 'disconnected'
  const m = mode.toLowerCase()
  if (m === 'hardcore') return 'hardcore'
  if (m === 'idle') return 'idle'
  return 'disconnected'
}

// ─── ModeBadge ────────────────────────────────────────────────────────────────
export function ModeBadge({ mode, size = 'md' }) {
  const { t } = useI18n()
  const cls = modeCssClass(mode)
  const label = t(modeKey(mode))
  const dotSize = size === 'sm' ? '6px' : '7px'
  const fontSize = size === 'sm' ? '11px' : '13px'
  const padding = size === 'sm' ? '2px 7px' : '4px 10px'

  return (
    <span
      aria-label={label}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '6px',
        padding,
        borderRadius: 'var(--radius-full)',
        fontSize,
        fontWeight: 600,
        background: `var(--mode-${cls}-subtle)`,
        color: `var(--mode-${cls})`,
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: dotSize, height: dotSize,
          borderRadius: '50%',
          background: 'currentColor',
          flexShrink: 0,
        }}
      />
      {label}
    </span>
  )
}

// ─── SessionStatusPanel ───────────────────────────────────────────────────────
export function SessionStatusPanel({ status, loading, error, onRetry, onCancelOverride, cancellingOverride }) {
  const { t } = useI18n()

  // Estado cargando
  if (loading && !status) {
    return (
      <div style={cardStyle}>
        <div style={cardTitleStyle}>{t('session.status.title')}</div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '32px', gap: '12px', color: 'var(--text-secondary)', fontSize: '13px' }}>
          <Spinner size={20} />
          {t('session.status.title')}…
        </div>
        {/* Skeletons */}
        <div style={{ marginTop: '8px' }}>
          <div style={skeletonStyle({ width: '40%', height: '20px', mb: '8px' })} />
          <div style={skeletonStyle({ width: '100%', height: '36px', mb: '8px' })} />
          <div style={skeletonStyle({ width: '60%', height: '16px' })} />
        </div>
      </div>
    )
  }

  // Estado error
  if (error && !status) {
    return (
      <div style={cardStyle}>
        <div style={cardTitleStyle}>{t('session.status.title')}</div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '32px', gap: '10px', textAlign: 'center' }}
          role="alert">
          <div style={{ fontSize: '24px' }}>⚠</div>
          <div style={{ fontSize: '13px', color: 'var(--text-secondary)', maxWidth: '300px' }}>
            {t('session.status.loadingError')}
          </div>
          <button
            type="button"
            onClick={onRetry}
            style={retryBtnStyle}
          >
            {t('session.status.retry')}
          </button>
        </div>
      </div>
    )
  }

  if (!status) return null

  const { mode, block, jitter_minutes, next_block_ends_at, override } = status

  // Hora aproximada con jitter
  const approxTime = next_block_ends_at
    ? (() => {
        const d = new Date(next_block_ends_at)
        return String(d.getHours()).padStart(2, '0') + ':' +
               String(d.getMinutes()).padStart(2, '0')
      })()
    : null

  return (
    <div style={cardStyle}>
      <div style={cardTitleStyle}>{t('session.status.title')}</div>

      {/* Fila modo + bloque + jitter */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap', marginBottom: '12px' }}>
        <ModeBadge mode={mode} />
        {block && (
          <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
            {t('session.status.block', { start: block.start, end: block.end })}
          </div>
        )}
        {jitter_minutes != null && (
          <div style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>
            {t('session.status.jitter', { n: jitter_minutes })}
          </div>
        )}
      </div>

      {/* KPI: countdown al próximo cambio */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '16px', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
            {t('session.status.nextChange')}
          </div>
          <Countdown
            targetIso={next_block_ends_at}
            aria-live="polite"
            className=""
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '26px',
              fontWeight: 700,
              color: 'var(--text)',
              fontVariantNumeric: 'tabular-nums',
              lineHeight: 1.2,
            }}
          />
          {approxTime && (
            <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
              {t('session.status.approxTime', { time: approxTime })}
            </div>
          )}
        </div>
      </div>

      {/* Override activo */}
      {override && (
        <OverrideRow
          override={override}
          onCancel={onCancelOverride}
          cancelling={cancellingOverride}
        />
      )}
    </div>
  )
}

// ─── OverrideRow ──────────────────────────────────────────────────────────────
function OverrideRow({ override, onCancel, cancelling }) {
  const { t } = useI18n()
  const cls = modeCssClass(override.mode)

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap',
      padding: '10px 12px',
      borderRadius: 'var(--radius-sm)',
      background: `var(--mode-${cls}-subtle)`,
      border: `1px solid var(--mode-${cls})`,
      marginTop: '10px',
    }}>
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', flexWrap: 'wrap' }}>
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ flexShrink: 0 }} aria-hidden="true">
          <path d="M8 2L1 14h14L8 2zM8 7v3M8 12h.01" />
        </svg>
        {t('session.override.active', { mode: t(modeKey(override.mode)) })}
        &nbsp;·&nbsp;
        {t('session.override.expiresIn')}
        &nbsp;
        <Countdown
          targetIso={override.expires_at}
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '13px',
            fontWeight: 600,
            fontVariantNumeric: 'tabular-nums',
            color: 'var(--text)',
          }}
        />
      </div>
      <button
        type="button"
        onClick={onCancel}
        disabled={cancelling}
        style={{
          background: 'none', border: 'none', cursor: cancelling ? 'not-allowed' : 'pointer',
          padding: '2px 8px', borderRadius: 'var(--radius-sm)',
          fontSize: '12px', color: 'var(--text-secondary)',
          fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: '4px',
        }}
      >
        {cancelling ? <Spinner size={12} /> : null}
        {t('session.override.cancel')}
      </button>
    </div>
  )
}

// ─── Estilos reutilizables ────────────────────────────────────────────────────
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

const retryBtnStyle = {
  padding: '6px 16px',
  border: '1px solid var(--border-strong)',
  borderRadius: 'var(--radius-sm)',
  background: 'var(--surface)',
  color: 'var(--text)',
  fontSize: '13px',
  cursor: 'pointer',
  fontFamily: 'inherit',
}

function skeletonStyle({ width, height, mb }) {
  return {
    background: 'var(--surface-2)',
    borderRadius: 'var(--radius-sm)',
    width, height,
    marginBottom: mb,
    animation: 'pulse 1.4s ease-in-out infinite alternate',
  }
}
