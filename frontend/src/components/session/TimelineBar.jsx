/**
 * TimelineBar — Barra proporcional de 24h con segmentos coloreados por modo.
 *
 * Props:
 *  - blocks {Array}   — [{start, end, mode}]  (formato HH:MM / 24:00)
 *  - dayLabel {string} — nombre del día para aria-label
 *  - hasError {boolean} — si hay error de cobertura, muestra segmento rojo
 *  - errorRange {{from, to}} — si hasError, el rango del hueco/solape
 *
 * Spec §6 (wireframe barra 24h), §10 (aria-label), §11 (responsive 16/24px).
 *
 * TimelineCoverageIndicator también se exporta desde este fichero.
 */
import { useI18n } from '../../i18n/index.jsx'

// ── Helpers ───────────────────────────────────────────────────────────────────

function timeToMin(t) {
  if (t === '24:00') return 1440
  const [h, m] = t.split(':').map(Number)
  return h * 60 + m
}

function minToTime(m) {
  if (m >= 1440) return '24:00'
  const h = Math.floor(m / 60)
  const mm = m % 60
  return `${String(h).padStart(2, '0')}:${String(mm).padStart(2, '0')}`
}

function modeLabel(mode, t) {
  if (!mode) return ''
  const m = mode.toLowerCase()
  if (m === 'hardcore') return t('session.mode.hardcore')
  if (m === 'idle') return t('session.mode.idle')
  return t('session.mode.disconnected')
}

function modeCssClass(mode) {
  if (!mode) return 'disconnected'
  const m = mode.toLowerCase()
  if (m === 'hardcore') return 'hardcore'
  if (m === 'idle') return 'idle'
  return 'disconnected'
}

/**
 * Construye los segmentos a partir de los bloques.
 * Si hay huecos, los rellena con segmentos 'error'.
 */
function buildSegments(blocks) {
  if (!blocks || blocks.length === 0) return []

  const sorted = [...blocks]
    .map(b => ({ s: timeToMin(b.start), e: timeToMin(b.end), mode: b.mode }))
    .sort((a, b) => a.s - b.s)

  const segs = []
  let cursor = 0

  for (const { s, e, mode } of sorted) {
    if (s > cursor) {
      // Hueco → segmento de error
      segs.push({ s: cursor, e: s, mode: 'error' })
    }
    if (e > Math.max(s, cursor)) {
      segs.push({ s: Math.max(s, cursor), e, mode })
    }
    cursor = Math.max(cursor, e)
  }

  // Si no llega a 1440, añadir error al final
  if (cursor < 1440) {
    segs.push({ s: cursor, e: 1440, mode: 'error' })
  }

  return segs
}

// ── TimelineBar ───────────────────────────────────────────────────────────────

export function TimelineBar({ blocks, dayLabel }) {
  const { t } = useI18n()

  const segments = buildSegments(blocks)

  // Construir aria-label descriptivo completo
  const ariaDescription = (blocks ?? [])
    .map(b => {
      const durMins = timeToMin(b.end) - timeToMin(b.start)
      const durH = (durMins / 60).toFixed(1).replace('.0', '')
      return `${b.start}–${b.end} ${modeLabel(b.mode, t)} (${durH}h)`
    })
    .join(', ')

  const fullAriaLabel = dayLabel
    ? `${t('session.timeline.ariaLabel', { day: dayLabel })}: ${ariaDescription}`
    : ariaDescription

  // Leyenda: modos únicos
  const seenModes = new Set()
  const legendItems = (blocks ?? []).filter(b => {
    const m = b.mode?.toLowerCase()
    if (seenModes.has(m)) return false
    seenModes.add(m)
    return true
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      {/* Barra */}
      <div
        role="img"
        aria-label={fullAriaLabel}
        style={{
          display: 'flex',
          height: 'clamp(16px, 2vw, 18px)',
          borderRadius: 'var(--radius-sm)',
          overflow: 'hidden',
          border: '1px solid var(--border)',
        }}
      >
        {segments.map((seg, i) => {
          const pct = ((seg.e - seg.s) / 1440 * 100).toFixed(3)
          const cls = modeCssClass(seg.mode)
          const isError = seg.mode === 'error'

          const label = isError
            ? `Hueco: ${minToTime(seg.s)}–${minToTime(seg.e)}`
            : `${minToTime(seg.s)}–${minToTime(seg.e)} ${modeLabel(seg.mode, t)} (${((seg.e - seg.s) / 60).toFixed(1).replace('.0', '')}h)`

          return (
            <div
              key={i}
              title={label}
              aria-hidden="true"
              style={{
                width: `${pct}%`,
                height: '100%',
                flexShrink: 0,
                background: isError
                  ? 'var(--danger)'
                  : `var(--mode-${cls})`,
                opacity: isError
                  ? 0.55
                  : cls === 'disconnected'
                    ? 0.45
                    : 1,
              }}
            />
          )
        })}
      </div>

      {/* Etiquetas de horas */}
      <div style={{
        display: 'flex', justifyContent: 'space-between',
        fontSize: '10px', color: 'var(--text-tertiary)',
        fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums',
      }} aria-hidden="true">
        <span>00:00</span>
        <span>06:00</span>
        <span>12:00</span>
        <span>18:00</span>
        <span>24:00</span>
      </div>

      {/* Leyenda */}
      {legendItems.length > 0 && (
        <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginTop: '4px' }} aria-hidden="true">
          {legendItems.map(b => {
            const cls = modeCssClass(b.mode)
            return (
              <div key={b.mode} style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px', color: 'var(--text-secondary)' }}>
                <span style={{
                  width: '8px', height: '8px',
                  borderRadius: '2px',
                  background: `var(--mode-${cls})`,
                  opacity: cls === 'disconnected' ? 0.6 : 1,
                  flexShrink: 0,
                }} />
                {modeLabel(b.mode, t)}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── TimelineCoverageIndicator ─────────────────────────────────────────────────

/**
 * Indica si la cobertura de 24h es válida o hay hueco/solape.
 *
 * Props:
 *  - validation {{ok, msg}}  — resultado de validateCoverage(blocks)
 */
export function TimelineCoverageIndicator({ validation }) {
  const { t } = useI18n()

  if (!validation) return null

  if (validation.ok) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', gap: '6px',
        fontSize: '12px', color: 'var(--success)', fontWeight: 500,
        marginTop: '10px',
      }}>
        <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path d="M2 8l4 4 8-8" />
        </svg>
        {t('session.editor.coverage.ok')}
      </div>
    )
  }

  return (
    <div
      role="alert"
      style={{
        display: 'flex', alignItems: 'flex-start', gap: '6px',
        padding: '8px 10px',
        borderRadius: 'var(--radius-sm)',
        background: 'var(--danger-subtle)',
        border: '1px solid var(--danger)',
        fontSize: '12px', color: 'var(--danger)', fontWeight: 500,
        marginTop: '10px',
      }}
    >
      <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ flexShrink: 0, marginTop: '1px' }} aria-hidden="true">
        <path d="M8 2L1 14h14L8 2zM8 7v3M8 12h.01" />
      </svg>
      {validation.msg}
    </div>
  )
}

// ── validateCoverage (lógica cliente, réplica del backend) ────────────────────
// Exportada para que BlockEditor pueda usarla en onChange.

export function validateCoverage(blocks) {
  if (!blocks || blocks.length === 0) {
    return { ok: false, msg: 'El timeline debe tener al menos un bloque.' }
  }

  const sorted = [...blocks]
    .map(b => ({ s: timeToMin(b.start), e: timeToMin(b.end) }))
    .sort((a, b) => a.s - b.s)

  let cursor = 0
  for (const { s, e } of sorted) {
    if (s > cursor) {
      return { ok: false, msg: `Falta cubrir: ${minToTime(cursor)} – ${minToTime(s)}` }
    }
    if (s < cursor) {
      return { ok: false, msg: `Solape detectado en ${minToTime(s)} – ${minToTime(Math.min(cursor, e))}` }
    }
    if (e <= s) {
      return { ok: false, msg: `Bloque inválido: fin (${minToTime(e)}) ≤ inicio (${minToTime(s)})` }
    }
    cursor = e
  }

  if (cursor < 1440) {
    return { ok: false, msg: `El timeline no llega a las 24:00 (cubre hasta ${minToTime(cursor)})` }
  }

  return { ok: true, msg: '' }
}

// Exportar también los helpers por si otros módulos los necesitan
export { timeToMin, minToTime }
