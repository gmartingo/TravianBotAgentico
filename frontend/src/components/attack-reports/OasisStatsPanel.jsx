/**
 * OasisStatsPanel — Muestra las estadísticas de un oasis:
 *   0. Animales observados (apariciones, prom, máx, mín)
 *   1. Balance agregado del oasis (bajas vs ganancias + neto)
 *   2. Repoblación y regeneración (intervalo, animales regenerados)
 *
 * Las columnas de animales regenerados en la tabla de repoblación son dinámicas:
 * solo se muestran los animales que alguna vez aparecieron en ese oasis.
 *
 * Regenerados positivos: --success, null: "—", negativos: --danger.
 *
 * Props:
 *   data — respuesta de GET /attack-reports/stats/oasis
 *   lang — string
 */
import { useI18n } from '../../i18n/index.jsx'
import { formatDateVerbatim } from '../../utils/formatDateVerbatim.js'
import { BalanceGrid } from './BalanceSection.jsx'

// ── Helpers ─────────────────────────────────────────────────────────────────

// attacked_at se muestra verbatim (hora del servidor de Travian, sin conversión de zona)
function formatDate(isoStr) {
  return formatDateVerbatim(isoStr)
}

/**
 * Formatea segundos a "6 h 14 min", "2 d 3 h", "45 min", etc.
 */
function formatGap(seconds) {
  if (seconds == null) return null
  const s = Math.round(seconds)
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60)

  if (d >= 1) {
    const hPart = h > 0 ? ` ${h} h` : ''
    return `${d} d${hPart}`
  }
  if (h >= 1) {
    const mPart = m > 0 ? ` ${m} min` : ''
    return `${h} h${mPart}`
  }
  return `${m} min`
}

function fmt(n, lang) {
  if (n == null || isNaN(n)) return '—'
  return new Intl.NumberFormat(lang, { maximumFractionDigits: 1 }).format(n)
}

// ── Componente de celda de regeneración ─────────────────────────────────────
function RegenCell({ value }) {
  if (value == null) {
    return <span style={{ color: 'var(--text-tertiary)' }}>—</span>
  }
  if (value > 0) {
    return <span style={{ color: 'var(--success, #16a34a)', fontWeight: 600 }}>+{value}</span>
  }
  if (value < 0) {
    return <span style={{ color: 'var(--danger)' }}>{value}</span>
  }
  return <span style={{ color: 'var(--text-tertiary)' }}>0</span>
}

// ── Tabla de animales ────────────────────────────────────────────────────────
function AnimalsTable({ appearances, total, lang, t }) {
  if (!appearances || appearances.length === 0) return null

  return (
    <section aria-labelledby="stats-animals-title" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      <h3 id="stats-animals-title" style={{ margin: 0, fontSize: '13px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
        {t('ar.stats.animals.title')}
      </h3>
      <div style={{ overflowX: 'auto' }}>
        <table role="table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              {[
                { label: t('ar.stats.animals.col.animal'),      align: 'start' },
                { label: t('ar.stats.animals.col.appearances'), align: 'end' },
                { label: t('ar.stats.animals.col.avg'),         align: 'end' },
                { label: t('ar.stats.animals.col.max'),         align: 'end' },
                { label: t('ar.stats.animals.col.min'),         align: 'end' },
              ].map(({ label, align }) => (
                <th key={label} scope="col" style={{ padding: '6px 10px', textAlign: align, fontSize: '11px', color: 'var(--text-tertiary)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {appearances.map((row) => (
              <tr key={row.animal_name} role="row" style={{ borderBottom: '1px solid var(--border)' }}>
                <td style={{ padding: '7px 10px', color: 'var(--text)' }}>{row.animal_name}</td>
                <td style={{ padding: '7px 10px', textAlign: 'end', fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', color: 'var(--text-secondary)' }}>
                  {row.appearances}/{total}
                </td>
                <td style={{ padding: '7px 10px', textAlign: 'end', fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums' }}>
                  {fmt(row.avg_present, lang)}
                </td>
                <td style={{ padding: '7px 10px', textAlign: 'end', fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums' }}>
                  {row.max_present ?? '—'}
                </td>
                <td style={{ padding: '7px 10px', textAlign: 'end', fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums' }}>
                  {row.min_present ?? '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

// ── Tabla de repoblación/regeneración ───────────────────────────────────────
function RepopTable({ gaps, appearances, lang, t }) {
  if (!gaps || gaps.length === 0) return null

  // Extraer animales únicos de las apariciones (para las columnas dinámicas)
  const animalNames = (appearances ?? []).map((a) => a.animal_name)

  return (
    <section aria-labelledby="stats-repop-title" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      <h3 id="stats-repop-title" style={{ margin: 0, fontSize: '13px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
        {t('ar.stats.repop.title')}
      </h3>
      <div style={{ overflowX: 'auto' }}>
        <table role="table" style={{ borderCollapse: 'collapse', fontSize: '13px', minWidth: '100%' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              <th scope="col" style={{ padding: '6px 10px', textAlign: 'start', fontSize: '11px', color: 'var(--text-tertiary)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', whiteSpace: 'nowrap' }}>
                {t('ar.stats.repop.col.attack')}
              </th>
              <th scope="col" style={{ padding: '6px 10px', textAlign: 'end', fontSize: '11px', color: 'var(--text-tertiary)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', whiteSpace: 'nowrap' }}>
                {t('ar.stats.repop.col.interval')}
              </th>
              {animalNames.map((name) => (
                <th key={name} scope="col" style={{ padding: '6px 10px', textAlign: 'end', fontSize: '11px', color: 'var(--text-tertiary)', fontWeight: 600, letterSpacing: '0.04em', whiteSpace: 'nowrap' }}>
                  {name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {gaps.map((row, idx) => {
              // Transformar regenerated_animals (lista) → dict por nombre para acceso O(1)
              // { "Rata": 9, "Araña": 0, ... }
              const regenByName = Object.fromEntries(
                (row.regenerated_animals ?? []).map((a) => [a.animal_name, a.regenerated])
              )
              return (
                <tr key={idx} role="row" style={{ borderBottom: '1px solid var(--border)' }}>
                  <td style={{ padding: '7px 10px', color: 'var(--text)', whiteSpace: 'nowrap', fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums' }}>
                    {formatDate(row.attacked_at)}
                  </td>
                  <td style={{ padding: '7px 10px', textAlign: 'end', color: 'var(--text-secondary)', whiteSpace: 'nowrap', fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums' }}>
                    {row.gap_seconds != null
                      ? formatGap(row.gap_seconds)
                      : <span style={{ color: 'var(--text-tertiary)', fontStyle: 'italic' }}>{t('ar.stats.repop.first')}</span>}
                  </td>
                  {animalNames.map((name) => {
                    const regen = regenByName[name] ?? null
                    return (
                      <td key={name} style={{ padding: '7px 10px', textAlign: 'end', fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums' }}>
                        <RegenCell value={regen} />
                      </td>
                    )
                  })}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

// ── Panel principal ──────────────────────────────────────────────────────────
export function OasisStatsPanel({ data, lang }) {
  const { t } = useI18n()

  if (!data) return null

  const {
    total_attacks,
    animal_appearances,
    repopulation_gaps,
    balance,
  } = data

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0' }}>
      {/* Balance agregado de este oasis (bajas vs ganancias + neto) —
          reutiliza BalanceGrid del balance global. Solo si el endpoint lo trae. */}
      {balance && balance.total_reports > 0 && (
        <section
          aria-labelledby="oasis-balance-title"
          style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '20px' }}
        >
          <h3
            id="oasis-balance-title"
            style={{ margin: 0, fontSize: '13px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}
          >
            {t('ar.balance.title')}
          </h3>
          <BalanceGrid data={balance} lang={lang} t={t} />
        </section>
      )}

      {/* 1. Animales observados */}
      <div style={{ marginTop: '20px' }}>
        <AnimalsTable
          appearances={animal_appearances}
          total={total_attacks}
          lang={lang}
          t={t}
        />
      </div>

      {/* 2. Repoblación y regeneración (solo con 2+ ataques) */}
      {total_attacks >= 2 && (
        <div style={{ marginTop: '20px' }}>
          <RepopTable
            gaps={repopulation_gaps}
            appearances={animal_appearances}
            lang={lang}
            t={t}
          />
        </div>
      )}
    </div>
  )
}
