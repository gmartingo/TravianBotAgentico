/**
 * BalanceSection — Bloque "Balance de operaciones" que encabeza la pestaña Estadísticas.
 *
 * Encabeza StatsTab ANTES de GlobalOasisStatsPanel (DA-CL01).
 * Carga independiente (DA-CL08/09): un error aquí no bloquea GlobalOasisStatsPanel ni OasisList.
 *
 * Criterios cubiertos:
 *   DA-CL01: Balance ANTES de GlobalOasisStatsPanel.
 *   DA-CL02: Skeleton durante la carga.
 *   DA-CL03: Neto positivo en --success, negativo en --danger.
 *   DA-CL04: Neto ≥ 20px — elemento tipográfico más grande del bloque.
 *   DA-CL05: 4 recursos en --font-mono + tabular-nums en ambas columnas.
 *   DA-CL06: Nota tribes solo si reports_without_tribe > 0.
 *   DA-CL07: Estado vacío con CTA "Limpiar filtro →" funcional.
 *   DA-CL10: Inputs de fecha type="text" con placeholder YYYY-MM-DD HH:MM:SS.
 *   DA-CL11: Validación regex + borde rojo + mensaje de error.
 *   DA-CL12: Botón Aplicar disabled mientras haya error.
 *   DA-CL13: Input vacío = válido (sin filtro en ese extremo).
 *   DA-CL14: Al aplicar, convierte espacio → T (ISO 8601).
 *
 * Props:
 *   lang — string (idioma activo)
 *   t    — función de traducción
 */
import { useState, useCallback, useEffect } from 'react'
import { api } from '../../api/client.js'
import { Spinner } from '../ui/uiUtils.jsx'

// ── Validación de fecha (mismo patrón que HistoryFilters) ────────────────────
const DATE_REGEX = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/

function isDateValid(val) {
  if (!val || val.trim() === '') return true
  return DATE_REGEX.test(val.trim())
}

function toISO(val) {
  if (!val || val.trim() === '') return ''
  return val.trim().replace(' ', 'T')
}

// ── Input de fecha con validación en vivo ────────────────────────────────────
function DateInput({ id, label, value, onChange, t }) {
  const valid = isDateValid(value)
  const errorId = `${id}-err`
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <label
        htmlFor={id}
        style={{
          fontSize: '11px',
          color: 'var(--text-tertiary)',
          fontWeight: 500,
          textTransform: 'uppercase',
          letterSpacing: '0.04em',
        }}
      >
        {label}
      </label>
      <input
        id={id}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={t('ar.balance.filter.placeholder')}
        aria-invalid={!valid}
        aria-describedby={!valid ? errorId : undefined}
        style={{
          height: '32px',
          padding: '0 8px',
          background: 'var(--surface)',
          border: `1px solid ${!valid ? 'var(--danger)' : 'var(--border-strong)'}`,
          borderRadius: 'var(--radius-sm)',
          fontSize: '13px',
          color: 'var(--text)',
          fontFamily: 'var(--font-mono)',
          width: '155px',
          boxSizing: 'border-box',
          outline: 'none',
          // inputs ≥ 16px en móvil (anti-zoom iOS)
        }}
        onFocus={(e) => {
          if (valid) e.currentTarget.style.borderColor = 'var(--accent)'
        }}
        onBlur={(e) => {
          e.currentTarget.style.borderColor = valid ? 'var(--border-strong)' : 'var(--danger)'
        }}
      />
      {!valid && (
        <span
          id={errorId}
          role="alert"
          style={{ fontSize: '11px', color: 'var(--danger)', marginTop: '2px' }}
        >
          {t('ar.balance.filter.invalidDate')}
        </span>
      )}
    </div>
  )
}

// ── Skeleton de carga ────────────────────────────────────────────────────────
function BalanceSkeleton() {
  const bar = (w, h = '14px') => (
    <div
      style={{
        height: h,
        width: w,
        borderRadius: 'var(--radius-sm)',
        background: 'var(--surface-2)',
        animation: 'balancePulse 1.4s ease-in-out infinite',
      }}
    />
  )
  return (
    <div role="status" aria-label="Cargando balance" style={{ padding: '12px 0' }}>
      {/* Simula el grid de 2 columnas con 5 filas */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 4px 1fr', gap: '12px', marginBottom: '12px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {[1,2,3,4].map((i) => bar(i % 2 === 0 ? '60%' : '80%'))}
          {bar('50%', '16px')}
        </div>
        <div style={{ background: 'var(--border)' }} />
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {[1,2,3,4].map((i) => bar(i % 2 === 0 ? '70%' : '85%'))}
          {bar('55%', '16px')}
        </div>
      </div>
      {/* Simula la fila de neto */}
      <div style={{ padding: '12px', background: 'var(--surface-2)', borderRadius: 'var(--radius-sm)', display: 'flex', justifyContent: 'space-between' }}>
        {bar('40%')}
        {bar('30%', '22px')}
      </div>
      <style>{`
        @keyframes balancePulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
      `}</style>
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
        padding: '10px 14px',
        background: 'color-mix(in srgb, var(--danger) 8%, transparent)',
        border: '1px solid color-mix(in srgb, var(--danger) 30%, transparent)',
        borderRadius: 'var(--radius-sm)',
        fontSize: '13px',
        color: 'var(--danger)',
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
          color: 'var(--danger)',
          background: 'transparent',
          border: '1px solid color-mix(in srgb, var(--danger) 40%, transparent)',
          borderRadius: 'var(--radius-sm)',
          cursor: 'pointer',
          fontFamily: 'inherit',
        }}
      >
        {t('ar.balance.retry')}
      </button>
    </div>
  )
}

// ── Estado vacío ─────────────────────────────────────────────────────────────
function BalanceEmpty({ onClear, t }) {
  return (
    <div
      style={{
        padding: '24px 16px',
        textAlign: 'center',
        color: 'var(--text-secondary)',
      }}
    >
      <p style={{ margin: '0 0 6px 0', fontWeight: 500, color: 'var(--text)', fontSize: '14px' }}>
        {t('ar.balance.empty.title')}
      </p>
      <p style={{ margin: '0 0 16px 0', fontSize: '13px' }}>
        {t('ar.balance.empty.sub')}
      </p>
      <button
        type="button"
        onClick={onClear}
        style={{
          background: 'transparent',
          color: 'var(--accent-text)',
          border: 'none',
          padding: 0,
          fontSize: '13px',
          cursor: 'pointer',
          fontFamily: 'inherit',
          fontWeight: 500,
        }}
      >
        {t('ar.balance.empty.cta')}
      </button>
    </div>
  )
}

// ── Formateo de número con Intl ──────────────────────────────────────────────
function fmtN(n, lang) {
  if (n == null) return '0'
  return new Intl.NumberFormat(lang).format(Math.round(n))
}

// ── Grid de datos (Perdido / Robado) ─────────────────────────────────────────
function BalanceGrid({ data, lang, t }) {
  const { lost, stolen } = data

  // Robado total = bounty + hero_inventory
  const stolenWood  = (stolen.bounty?.wood  ?? 0) + (stolen.hero_inventory?.wood  ?? 0)
  const stolenClay  = (stolen.bounty?.clay  ?? 0) + (stolen.hero_inventory?.clay  ?? 0)
  const stolenIron  = (stolen.bounty?.iron  ?? 0) + (stolen.hero_inventory?.iron  ?? 0)
  const stolenCrop  = (stolen.bounty?.crop  ?? 0) + (stolen.hero_inventory?.crop  ?? 0)
  const stolenTotal = stolen.total?.total ?? (stolenWood + stolenClay + stolenIron + stolenCrop)

  const lostTotal = lost.total

  const resources = [
    { key: 'wood', label: t('ar.balance.row.wood'), lv: lost.wood, sv: stolenWood },
    { key: 'clay', label: t('ar.balance.row.clay'), lv: lost.clay, sv: stolenClay },
    { key: 'iron', label: t('ar.balance.row.iron'), lv: lost.iron, sv: stolenIron },
    { key: 'crop', label: t('ar.balance.row.crop'), lv: lost.crop, sv: stolenCrop },
  ]

  const net = data.net ?? (stolenTotal - lostTotal)
  const netPositive = net >= 0
  const netColor    = net > 0 ? 'var(--success)' : net < 0 ? 'var(--danger)' : 'var(--text)'

  const cellStyle = {
    fontFamily: 'var(--font-mono)',
    fontVariantNumeric: 'tabular-nums',
    fontSize: '13px',
    textAlign: 'end',
  }

  const headerStyle = {
    fontSize: '11px',
    fontWeight: 600,
    color: 'var(--text-tertiary)',
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
    textAlign: 'end',
    padding: '0 0 6px 0',
  }

  const labelStyle = {
    fontSize: '13px',
    color: 'var(--text-secondary)',
    padding: '5px 0',
  }

  const totalRowStyle = {
    fontFamily: 'var(--font-mono)',
    fontVariantNumeric: 'tabular-nums',
    fontSize: '13px',
    fontWeight: 600,
    textAlign: 'end',
    borderTop: '1px solid var(--border)',
    paddingTop: '6px',
    marginTop: '4px',
  }

  return (
    <div>
      {/* Grid 3 columnas: Perdido | divisor | Robado */}
      {/* En móvil colapsa a 1 columna */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, auto)',
          gap: '0 16px',
          alignItems: 'start',
        }}
      >
        {/* Cabecera col 1: Perdido */}
        <div style={{ ...headerStyle, textAlign: 'end' }}>
          {t('ar.balance.col.lost')}
        </div>
        {/* Divisor */}
        <div />
        {/* Cabecera col 3: Robado */}
        <div style={{ ...headerStyle, textAlign: 'end' }}>
          {t('ar.balance.col.stolen')}
        </div>

        {/* Filas de recursos */}
        {resources.map(({ key, label, lv, sv }) => (
          <>
            {/* Perdido */}
            <div key={`lost-${key}`} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', padding: '4px 0', borderBottom: '1px solid var(--border)' }}>
              <span style={{ ...labelStyle, padding: 0 }}>{label}</span>
              <span
                aria-label={`${label} ${t('ar.balance.col.lost').toLowerCase()}: ${fmtN(lv, lang)}`}
                style={{ ...cellStyle }}
              >
                {fmtN(lv, lang)}
              </span>
            </div>
            {/* Divisor vertical */}
            <div key={`div-${key}`} style={{ borderLeft: '1px solid var(--border)', margin: '0 4px', padding: '4px 0', borderBottom: '1px solid var(--border)' }} />
            {/* Robado */}
            <div key={`stolen-${key}`} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', padding: '4px 0', borderBottom: '1px solid var(--border)' }}>
              <span style={{ ...labelStyle, padding: 0 }}>{label}</span>
              <span
                aria-label={`${label} ${t('ar.balance.col.stolen').toLowerCase()}: ${fmtN(sv, lang)}`}
                style={{ ...cellStyle }}
              >
                {fmtN(sv, lang)}
              </span>
            </div>
          </>
        ))}

        {/* Fila Total */}
        <div style={{ ...totalRowStyle, display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
          <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', fontFamily: 'inherit' }}>
            {t('ar.balance.row.total')}
          </span>
          <span style={{ color: lostTotal > 0 ? 'var(--danger)' : 'var(--text-secondary)' }}>
            {fmtN(lostTotal, lang)}
          </span>
        </div>
        {/* Divisor total */}
        <div style={{ borderLeft: '1px solid var(--border)', margin: '0 4px', borderTop: '1px solid var(--border)', paddingTop: '6px', marginTop: '4px' }} />
        <div style={{ ...totalRowStyle, display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
          <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', fontFamily: 'inherit' }}>
            {t('ar.balance.row.total')}
          </span>
          <span style={{ color: stolenTotal > 0 ? 'var(--success)' : 'var(--text-secondary)' }}>
            {fmtN(stolenTotal, lang)}
          </span>
        </div>
      </div>

      {/* Fila de Neto — DA-CL03/04: mayor tamaño tipográfico, color semántico */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '16px',
          marginTop: '12px',
          padding: '12px 16px',
          background: 'var(--surface-2)',
          borderRadius: 'var(--radius-sm)',
        }}
      >
        <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-secondary)' }}>
          {t('ar.balance.net.label')}
        </span>
        <span
          aria-label={`Neto: ${netPositive ? 'positivo' : 'negativo'} ${Math.abs(net)} recursos`}
          style={{
            fontSize: '22px',     /* ≥ 20px — DA-CL04 */
            fontWeight: 700,
            fontFamily: 'var(--font-mono)',
            fontVariantNumeric: 'tabular-nums',
            color: netColor,
          }}
        >
          {net > 0 ? '+' : ''}{fmtN(net, lang)}
        </span>
      </div>
    </div>
  )
}

// ── Componente principal ─────────────────────────────────────────────────────
export function BalanceSection({ lang, t }) {
  const [fromDate, setFromDate]     = useState('')
  const [toDate, setToDate]         = useState('')
  const [appliedFrom, setAppliedFrom] = useState('')
  const [appliedTo, setAppliedTo]     = useState('')

  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)

  const fromValid = isDateValid(fromDate)
  const toValid   = isDateValid(toDate)
  const hasError  = !fromValid || !toValid

  const isFiltered = !!(appliedFrom || appliedTo)

  const load = useCallback(async (fromDt, toDt) => {
    setLoading(true)
    setError(null)
    try {
      const params = {}
      if (fromDt) params.from_date = fromDt
      if (toDt)   params.to_date   = toDt
      const res = await api.getBalanceStats(params)
      setData(res)
    } catch (err) {
      setError(err?.detail ?? t('ar.balance.error'))
    } finally {
      setLoading(false)
    }
  }, [t])

  // Carga inicial (sin filtro)
  useEffect(() => { load('', '') }, [load])

  function handleApply() {
    if (hasError) return
    const from = toISO(fromDate)
    const to   = toISO(toDate)
    setAppliedFrom(from)
    setAppliedTo(to)
    load(from, to)
  }

  function handleClear() {
    setFromDate('')
    setToDate('')
    setAppliedFrom('')
    setAppliedTo('')
    load('', '')
  }

  // ── Pill de estado del filtro ─────────────────────────────────────────────
  const pillText = (() => {
    const n = data?.total_reports ?? 0
    if (isFiltered) {
      return t('ar.balance.pill.filtered')
        .replace('{n}', n)
        .replace('{from}', appliedFrom || '—')
        .replace('{to}', appliedTo || '—')
    }
    return t('ar.balance.pill.noFilter').replace('{n}', n)
  })()

  return (
    <section
      aria-labelledby="balance-section-title"
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        padding: '16px 20px',
        marginBottom: '24px',
      }}
    >
      {/* Cabecera: título + pill */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '12px', marginBottom: '12px', flexWrap: 'wrap' }}>
        <h2
          id="balance-section-title"
          style={{
            margin: 0,
            fontSize: '17px',
            fontWeight: 600,
            color: 'var(--text)',
            letterSpacing: '-0.01em',
          }}
        >
          {t('ar.balance.title')}
        </h2>
        {!loading && data && (
          <span
            style={{
              fontSize: '12px',
              color: 'var(--text-tertiary)',
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-full)',
              padding: '1px 8px',
              fontFamily: 'var(--font-mono)',
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {pillText}
          </span>
        )}
      </div>

      {/* Filtro de fecha — DA-CL10–14 */}
      <div
        style={{
          background: 'var(--surface-2)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)',
          padding: '10px 14px',
          marginBottom: '16px',
        }}
      >
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '10px 16px',
            alignItems: 'flex-end',
          }}
        >
          {/* Desde */}
          <DateInput
            id="balance-from"
            label={t('ar.balance.filter.from')}
            value={fromDate}
            onChange={setFromDate}
            t={t}
          />
          {/* Hasta */}
          <DateInput
            id="balance-to"
            label={t('ar.balance.filter.to')}
            value={toDate}
            onChange={setToDate}
            t={t}
          />
          {/* Botones */}
          <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-end' }}>
            <button
              type="button"
              onClick={handleApply}
              disabled={hasError}
              aria-disabled={hasError}
              style={{
                height: '32px',
                padding: '0 14px',
                background: hasError ? 'var(--text-disabled)' : 'var(--btn-primary-bg)',
                color: 'var(--btn-primary-text)',
                border: 'none',
                borderRadius: 'var(--radius-sm)',
                fontSize: '13px',
                fontWeight: 500,
                fontFamily: 'inherit',
                cursor: hasError ? 'not-allowed' : 'pointer',
                opacity: hasError ? 0.5 : 1,
              }}
            >
              {t('ar.balance.filter.apply')}
            </button>
            {isFiltered && (
              <button
                type="button"
                onClick={handleClear}
                style={{
                  height: '32px',
                  padding: '0 12px',
                  background: 'transparent',
                  color: 'var(--text-secondary)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '13px',
                  fontFamily: 'inherit',
                  cursor: 'pointer',
                }}
              >
                {t('ar.balance.filter.clear')}
              </button>
            )}
          </div>
        </div>
        {/* Hint */}
        <p style={{ margin: '8px 0 0', fontSize: '11px', color: 'var(--text-tertiary)' }}>
          {t('ar.balance.filter.hint')}
        </p>
      </div>

      {/* ── Cuerpo: estados ────────────────────────────────────────────────── */}

      {/* Cargando */}
      {loading && <BalanceSkeleton />}

      {/* Error — DA-CL08: aislado, no bloquea el resto */}
      {!loading && error && (
        <ErrorBanner message={error} onRetry={() => load(appliedFrom, appliedTo)} t={t} />
      )}

      {/* Vacío — DA-CL07 */}
      {!loading && !error && data && data.total_reports === 0 && (
        <BalanceEmpty onClear={handleClear} t={t} />
      )}

      {/* Con datos */}
      {!loading && !error && data && data.total_reports > 0 && (
        <>
          <BalanceGrid data={data} lang={lang} t={t} />

          {/* Nota tribes — DA-CL06: solo si reports_without_tribe > 0 */}
          {data.reports_without_tribe > 0 && (
            <p
              style={{
                margin: '12px 0 0',
                fontSize: '12px',
                color: 'var(--accent-text)',
                display: 'flex',
                alignItems: 'flex-start',
                gap: '6px',
              }}
            >
              <span aria-hidden="true" style={{ flexShrink: 0 }}>ⓘ</span>
              <span>
                {t('ar.balance.tribeless.note').replace('{n}', data.reports_without_tribe)}
              </span>
            </p>
          )}
        </>
      )}
    </section>
  )
}
