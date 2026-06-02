/**
 * GlobalOasisStatsPanel — Panel de estadísticas globales de todos los oasis.
 *
 * Siempre visible encima de OasisList en la pestaña Estadísticas.
 * Carga independiente: un error aquí no afecta a OasisList.
 *
 * Secciones:
 *   1. Apariciones globales de animales (tabla: animal, apariciones, prom, máx, mín)
 *
 * Estados: loading (skeleton) / error (banner rojo + reintentar) /
 *          vacío (estado descriptivo con CTA) / con-datos.
 *
 * Props:
 *   data      — respuesta de GET /attack-reports/stats/global (o null)
 *   loading   — boolean
 *   error     — string | null
 *   onRetry   — () => void
 *   onGoToIngest — () => void — CTA del estado vacío
 *   lang      — string (idioma activo)
 *   t         — función de traducción
 *
 * Ver spec docs/specs/bd-ataques-oasis-stats-global.md §9 frontend.
 * Añadido en la feature bd-ataques-oasis-stats-global (2026-05-31).
 */
import { useState } from 'react'

// ── Skeleton de carga ────────────────────────────────────────────────────────
function GlobalStatsSkeleton() {
  const bar = (w) => (
    <div
      style={{
        height: '14px',
        width: w,
        borderRadius: 'var(--radius-sm, 4px)',
        background: 'var(--border)',
        animation: 'pulse 1.5s ease-in-out infinite',
      }}
    />
  )
  return (
    <div
      role="status"
      aria-label="Cargando estadísticas globales"
      style={{ display: 'flex', flexDirection: 'column', gap: '16px', padding: '20px 0' }}
    >
      {bar('40%')}
      {bar('70%')}
      {bar('55%')}
      {bar('65%')}
    </div>
  )
}

// ── Banner de error ──────────────────────────────────────────────────────────
function ErrorBanner({ message, onRetry, t }) {
  return (
    <div
      role="alert"
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '12px',
        padding: '12px 16px',
        background: 'var(--danger-subtle, rgba(220,38,38,.08))',
        border: '1px solid var(--danger-border, rgba(220,38,38,.30))',
        borderRadius: 'var(--radius-sm)',
        fontSize: '13px',
        color: 'var(--danger, #dc2626)',
        marginBottom: '20px',
      }}
    >
      <span>{message}</span>
      <button
        type="button"
        onClick={onRetry}
        style={{
          flexShrink: 0,
          padding: '4px 12px',
          fontSize: '12px',
          fontWeight: 600,
          color: 'var(--danger, #dc2626)',
          background: 'transparent',
          border: '1px solid var(--danger-border, rgba(220,38,38,.40))',
          borderRadius: 'var(--radius-sm)',
          cursor: 'pointer',
        }}
      >
        {t('ar.stats.global.retry')}
      </button>
    </div>
  )
}

// ── Estado vacío ─────────────────────────────────────────────────────────────
function GlobalStatsEmpty({ onGoToIngest, t }) {
  return (
    <div
      style={{
        padding: '24px 16px',
        textAlign: 'center',
        color: 'var(--text-secondary)',
        marginBottom: '20px',
      }}
    >
      <p style={{ margin: '0 0 8px 0', fontWeight: 500, color: 'var(--text)', fontSize: '14px' }}>
        {t('ar.stats.global.empty.title')}
      </p>
      <p style={{ margin: '0 0 16px 0', fontSize: '13px' }}>
        {t('ar.stats.global.empty.sub')}
      </p>
      <button
        type="button"
        onClick={onGoToIngest}
        style={{
          padding: '6px 16px',
          fontSize: '13px',
          fontWeight: 600,
          color: 'var(--text)',
          background: 'transparent',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)',
          cursor: 'pointer',
        }}
      >
        {t('ar.stats.global.empty.cta')}
      </button>
    </div>
  )
}

// ── Tabla de apariciones globales ────────────────────────────────────────────
function GlobalAppearancesTable({ appearances, lang, t }) {
  if (!appearances || appearances.length === 0) return null

  function fmtNum(n, fractionDigits = 2) {
    if (n == null || isNaN(n)) return '—'
    return new Intl.NumberFormat(lang, {
      minimumFractionDigits: 0,
      maximumFractionDigits: fractionDigits,
    }).format(n)
  }

  const cols = [
    { label: t('ar.stats.animals.col.animal'),      align: 'start',  hidden: false },
    { label: t('ar.stats.global.col.appearances'),  align: 'end',    hidden: false },
    { label: t('ar.stats.animals.col.avg'),          align: 'end',    hidden: false },
    { label: t('ar.stats.animals.col.max'),          align: 'end',    hidden: false },
    { label: t('ar.stats.animals.col.min'),          align: 'end',    hidden: false },
  ]

  return (
    <section
      aria-labelledby="global-animals-title"
      style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}
    >
      <h3
        id="global-animals-title"
        style={{
          margin: 0,
          fontSize: '13px',
          fontWeight: 600,
          color: 'var(--text-secondary)',
          textTransform: 'uppercase',
          letterSpacing: '0.04em',
        }}
      >
        {t('ar.stats.global.appearances.title')}
      </h3>
      <div style={{ overflowX: 'auto' }}>
        <table
          role="table"
          style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}
        >
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              {cols.map(({ label, align, hidden }) => (
                <th
                  key={label}
                  scope="col"
                  className={hidden ? 'hidden md:table-cell' : undefined}
                  style={{
                    padding: '6px 10px',
                    textAlign: align,
                    fontSize: '11px',
                    color: 'var(--text-tertiary)',
                    fontWeight: 600,
                    textTransform: 'uppercase',
                    letterSpacing: '0.04em',
                    whiteSpace: 'nowrap',
                    fontVariantNumeric: 'tabular-nums',
                  }}
                >
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {appearances.map((row) => (
              <tr
                key={`${row.animal_ordinal}-${row.animal_name}`}
                role="row"
                style={{ borderBottom: '1px solid var(--border)' }}
              >
                <td style={{ padding: '7px 10px', color: 'var(--text)' }}>
                  {row.animal_name}
                </td>
                {/* appearances / eligible_reports (NN%) — denominador = reportes de oasis
                    donde esa especie aparece alguna vez; oasis sin esa especie no diluyen el % */}
                <td
                  style={{
                    padding: '7px 10px',
                    textAlign: 'end',
                    fontFamily: 'var(--font-mono)',
                    fontVariantNumeric: 'tabular-nums',
                    color: 'var(--text-secondary)',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {(() => {
                    const nf = new Intl.NumberFormat(lang)
                    const app = nf.format(row.appearances)
                    // Guarda defensiva: backend antiguo sin eligible_reports → solo conteo
                    if (row.eligible_reports == null || row.eligible_reports === 0) return app
                    const pct = Math.round((row.appearances / row.eligible_reports) * 100)
                    return (
                      <>
                        {app}/{nf.format(row.eligible_reports)}{' '}
                        <span style={{ color: 'var(--text-tertiary)' }}>({pct}%)</span>
                      </>
                    )
                  })()}
                </td>
                {/* avg_present */}
                <td
                  style={{
                    padding: '7px 10px',
                    textAlign: 'end',
                    fontFamily: 'var(--font-mono)',
                    fontVariantNumeric: 'tabular-nums',
                  }}
                >
                  {row.avg_present != null ? fmtNum(row.avg_present) : '—'}
                </td>
                {/* max_present */}
                <td
                  style={{
                    padding: '7px 10px',
                    textAlign: 'end',
                    fontFamily: 'var(--font-mono)',
                    fontVariantNumeric: 'tabular-nums',
                  }}
                >
                  {row.max_present ?? '—'}
                </td>
                {/* min_present (nullable → '—') */}
                <td
                  style={{
                    padding: '7px 10px',
                    textAlign: 'end',
                    fontFamily: 'var(--font-mono)',
                    fontVariantNumeric: 'tabular-nums',
                  }}
                >
                  {row.min_present != null ? row.min_present : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

// ── Acordeón colapsable ──────────────────────────────────────────────────────
// DA-CL15–21: header + resumen + chevron + aria-expanded + max-height.
// Envuelve sin modificar el componente hijo (DA-CL22).
function Accordion({ headerId, bodyId, header, summary, open, onToggle, children }) {
  return (
    <div style={{ borderBottom: '1px solid var(--border)', marginBottom: '8px' }}>
      <div
        id={headerId}
        role="button"
        tabIndex={0}
        aria-expanded={open}
        aria-controls={bodyId}
        onClick={onToggle}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onToggle() } }}
        style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', padding: '10px 0', cursor: 'pointer', userSelect: 'none' }}
      >
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px', flex: 1, minWidth: 0 }}>
          <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em', whiteSpace: 'nowrap' }}>
            {header}
          </span>
          {!open && summary && (
            <span style={{ fontSize: '12px', color: 'var(--text-tertiary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {summary}
            </span>
          )}
        </div>
        {/* Chevron rota 180° al abrir — DA-CL19 */}
        <span
          aria-hidden="true"
          style={{ fontSize: '10px', color: 'var(--text-disabled)', flexShrink: 0, display: 'inline-block', transform: open ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform var(--dur-base) var(--ease)' }}
        >
          ▾
        </span>
      </div>
      {/* Cuerpo: transición max-height — DA-CL20 */}
      <div
        id={bodyId}
        role="region"
        aria-labelledby={headerId}
        style={{ overflow: 'hidden', maxHeight: open ? '2000px' : '0', transition: 'max-height var(--dur-base) var(--ease)' }}
      >
        <div style={{ paddingBottom: '12px' }}>{children}</div>
      </div>
      <style>{`
        @media (prefers-reduced-motion: reduce) {
          #${bodyId} { transition: none !important; }
          #${headerId} span[aria-hidden] { transition: none !important; }
        }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
      `}</style>
    </div>
  )
}

// ── Panel principal ──────────────────────────────────────────────────────────
export function GlobalOasisStatsPanel({ data, loading, error, onRetry, onGoToIngest, lang, t }) {
  const [appearancesOpen, setAppearancesOpen] = useState(false)

  if (loading) return <GlobalStatsSkeleton />
  if (error)   return <ErrorBanner message={error} onRetry={onRetry} t={t} />

  if (!data || data.animal_appearances.length === 0) {
    return <GlobalStatsEmpty onGoToIngest={onGoToIngest} t={t} />
  }

  const appearances = data.animal_appearances ?? []

  // Resumen de apariciones "N animales observados · top: X, Y, Z"
  const appearancesSummary = (() => {
    if (appearances.length === 0) return ''
    const top3 = [...appearances].sort((a, b) => (b.appearances ?? 0) - (a.appearances ?? 0)).slice(0, 3).map((a) => a.animal_name).join(', ')
    return t('ar.stats.global.appearances.summary')
      .replace('{n}', appearances.length)
      .replace('{top}', top3)
  })()

  return (
    <section
      aria-labelledby="global-stats-title"
      role="region"
      style={{ padding: '0 0 4px 0', borderBottom: '1px solid var(--border)', marginBottom: '24px' }}
    >
      <h2 id="global-stats-title" style={{ margin: '0 0 8px 0', fontSize: '14px', fontWeight: 600, color: 'var(--text)' }}>
        {t('ar.stats.global.title')}
      </h2>

      {/* Acordeón: Apariciones globales */}
      <Accordion
        headerId="global-appears-hdr"
        bodyId="global-appears-body"
        header={t('ar.stats.global.appearances.header')}
        summary={appearancesSummary}
        open={appearancesOpen}
        onToggle={() => setAppearancesOpen((v) => !v)}
      >
        <GlobalAppearancesTable appearances={appearances} lang={lang} t={t} />
      </Accordion>
    </section>
  )
}
