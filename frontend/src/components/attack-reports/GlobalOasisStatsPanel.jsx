/**
 * GlobalOasisStatsPanel — Panel de estadísticas globales de todos los oasis.
 *
 * Siempre visible encima de OasisList en la pestaña Estadísticas.
 * Carga independiente: un error aquí no afecta a OasisList.
 *
 * Secciones:
 *   1. Ritmo de regeneración global (RegenRatesSection reutilizada)
 *   2. Apariciones globales de animales (tabla: animal, apariciones, prom, máx, mín)
 *
 * Estados: loading (skeleton) / error (banner rojo + reintentar) /
 *          vacío (estado descriptivo con CTA) / con-datos (dos secciones).
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
import { RegenRatesSection } from './RegenRatesSection.jsx'

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
                {/* appearances (total global, sin denominador) */}
                <td
                  style={{
                    padding: '7px 10px',
                    textAlign: 'end',
                    fontFamily: 'var(--font-mono)',
                    fontVariantNumeric: 'tabular-nums',
                    color: 'var(--text-secondary)',
                  }}
                >
                  {new Intl.NumberFormat(lang).format(row.appearances)}
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

// ── Panel principal ──────────────────────────────────────────────────────────
export function GlobalOasisStatsPanel({ data, loading, error, onRetry, onGoToIngest, lang, t }) {
  // Estado loading: skeleton
  if (loading) return <GlobalStatsSkeleton />

  // Estado error: banner rojo + botón reintentar
  if (error) {
    return (
      <ErrorBanner
        message={error}
        onRetry={onRetry}
        t={t}
      />
    )
  }

  // Estado vacío: arrays vacíos (o sin data)
  if (
    !data ||
    (data.animal_appearances.length === 0 && data.animal_regen_rates.length === 0)
  ) {
    return <GlobalStatsEmpty onGoToIngest={onGoToIngest} t={t} />
  }

  return (
    <section
      aria-labelledby="global-stats-title"
      role="region"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '0',
        padding: '0 0 4px 0',
        borderBottom: '1px solid var(--border)',
        marginBottom: '24px',
      }}
    >
      <h2
        id="global-stats-title"
        style={{
          margin: '0 0 16px 0',
          fontSize: '14px',
          fontWeight: 600,
          color: 'var(--text)',
        }}
      >
        {t('ar.stats.global.title')}
      </h2>

      {/* Sección 1: Ritmo de regeneración global (RegenRatesSection reutilizada) */}
      <RegenRatesSection
        rates={data.animal_regen_rates}
        totalAttacks={null}
        lang={lang}
        t={t}
      />

      {/* Sección 2: Apariciones globales de animales */}
      <GlobalAppearancesTable
        appearances={data.animal_appearances}
        lang={lang}
        t={t}
      />
    </section>
  )
}
