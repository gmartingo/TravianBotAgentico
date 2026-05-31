/**
 * RegenRatesSection — Sección "Ritmo de regeneración" (KPI principal).
 *
 * Muestra el ratio de regeneración por hora de cada animal observado en el oasis,
 * calculado por el backend a partir de los intervalos entre ataques consecutivos.
 *
 * Layout (tabla densa, 3 columnas):
 *   Col 1: NatureIcon + nombre del animal
 *   Col 2: X,XX /h (font-mono, bold, 15px — dato principal)
 *   Col 3: ≈ N intervalos (confianza estadística, verde si >= 5, terciario si < 5)
 *
 * Estado sin datos (animal_regen_rates = [] con total_attacks < 2):
 *   Banner de aviso en acento oro con icono ⚠
 *
 * Props:
 *   rates        — array de { animal_ordinal, animal_name, avg_regen_per_hour, valid_intervals }
 *   totalAttacks — number
 *   lang         — string (para Intl.NumberFormat)
 *   t            — función de traducción (pasada desde el padre)
 */
import { NatureIcon } from './NatureIcon.jsx'

export function RegenRatesSection({ rates, totalAttacks, lang, t }) {
  // Si hay menos de 2 ataques no hay intervalos → mostrar aviso
  if (!rates || rates.length === 0) {
    return (
      <section
        aria-labelledby="regen-section-title"
        style={{ marginBottom: '20px' }}
      >
        <h3
          id="regen-section-title"
          style={{
            margin: '0 0 10px 0',
            fontSize: '11px',
            fontWeight: 600,
            color: 'var(--text-tertiary)',
            textTransform: 'uppercase',
            letterSpacing: '0.04em',
          }}
        >
          {t('ar.stats.regen.title')}
        </h3>
        <div
          role="note"
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: '10px',
            padding: '12px 14px',
            background: 'var(--accent-subtle)',
            border: '1px solid var(--accent-subtle-border, rgba(138,100,24,.40))',
            borderRadius: 'var(--radius-sm)',
            fontSize: '13px',
          }}
        >
          <span
            aria-hidden="true"
            style={{ color: 'var(--accent-text)', fontSize: '15px', flexShrink: 0, marginTop: '1px' }}
          >
            ⚠
          </span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
            <span style={{ fontWeight: 500, color: 'var(--text)' }}>
              {t('ar.stats.regen.warn.title')}
            </span>
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              {t('ar.stats.regen.warn.sub')}
            </span>
          </div>
        </div>
      </section>
    )
  }

  const fmtRatio = (n) => {
    if (n == null || isNaN(n)) return '—'
    return new Intl.NumberFormat(lang, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(n)
  }

  const intervalLabel = (n) => {
    if (n === 1) return t('ar.stats.regen.interval.one').replace('{n}', n)
    return t('ar.stats.regen.interval.pl').replace('{n}', n)
  }

  return (
    <section
      aria-labelledby="regen-section-title"
      style={{ marginBottom: '20px' }}
    >
      <h3
        id="regen-section-title"
        style={{
          margin: '0 0 10px 0',
          fontSize: '11px',
          fontWeight: 600,
          color: 'var(--text-tertiary)',
          textTransform: 'uppercase',
          letterSpacing: '0.04em',
        }}
      >
        {t('ar.stats.regen.title')}
      </h3>
      <div style={{ overflowX: 'auto' }}>
        <table
          role="table"
          style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}
        >
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              <th
                scope="col"
                style={{
                  padding: '6px 10px',
                  textAlign: 'start',
                  fontSize: '11px',
                  color: 'var(--text-tertiary)',
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                  whiteSpace: 'nowrap',
                }}
              >
                {t('ar.stats.regen.col.animal')}
              </th>
              <th
                scope="col"
                style={{
                  padding: '6px 10px',
                  textAlign: 'end',
                  fontSize: '11px',
                  color: 'var(--text-tertiary)',
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                  whiteSpace: 'nowrap',
                }}
              >
                {t('ar.stats.regen.col.ratio')}
              </th>
              {/* Confianza — P2 oculto en móvil */}
              <th
                scope="col"
                className="hidden md:table-cell"
                style={{
                  padding: '6px 10px',
                  textAlign: 'end',
                  fontSize: '11px',
                  color: 'var(--text-tertiary)',
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                  whiteSpace: 'nowrap',
                }}
              >
                {t('ar.stats.regen.col.confidence')}
              </th>
            </tr>
          </thead>
          <tbody>
            {rates.map((rate) => {
              const isHighConfidence = rate.valid_intervals >= 5
              return (
                <tr key={rate.animal_ordinal ?? rate.animal_name} role="row" style={{ borderBottom: '1px solid var(--border)' }}>
                  {/* Animal */}
                  <td style={{ padding: '8px 10px', color: 'var(--text)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <NatureIcon
                        ordinal={rate.animal_ordinal}
                        name={rate.animal_name}
                        size={20}
                      />
                      <span>{rate.animal_name}</span>
                    </div>
                  </td>
                  {/* Ratio /h */}
                  <td style={{ padding: '8px 10px', textAlign: 'end' }}>
                    <span
                      style={{
                        fontSize: '15px',
                        fontWeight: 600,
                        fontFamily: 'var(--font-mono)',
                        fontVariantNumeric: 'tabular-nums',
                        color: 'var(--text)',
                      }}
                    >
                      {fmtRatio(rate.avg_regen_per_hour)} /h
                    </span>
                  </td>
                  {/* Confianza — P2 oculto en móvil */}
                  <td
                    className="hidden md:table-cell"
                    style={{ padding: '8px 10px', textAlign: 'end' }}
                  >
                    <span
                      style={{
                        fontSize: '12px',
                        color: isHighConfidence ? 'var(--success)' : 'var(--text-tertiary)',
                      }}
                    >
                      ≈ {intervalLabel(rate.valid_intervals)}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
