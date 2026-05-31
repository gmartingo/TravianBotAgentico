/**
 * HistoryFilters — Inputs de filtrado del historial de reportes.
 *
 * Desktop/tablet: inline horizontal.
 * Móvil: acordeón colapsable (P2 según §11 del spec).
 *
 * Props:
 *   filters    — { x, y, from_date, to_date }
 *   onChange   — (filters) => void
 *   onApply    — () => void
 *   onClear    — () => void
 *   isFiltered — boolean (hay algún filtro activo)
 */
import { useState } from 'react'
import { useI18n } from '../../i18n/index.jsx'

function FilterInput({ id, label, value, onChange, type = 'text', placeholder = '' }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <label
        htmlFor={id}
        style={{ fontSize: '11px', color: 'var(--text-tertiary)', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.04em' }}
      >
        {label}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        style={{
          height: '32px',
          padding: '0 8px',
          background: 'var(--surface)',
          border: '1px solid var(--border-strong)',
          borderRadius: 'var(--radius-sm)',
          fontSize: '13px',
          color: 'var(--text)',
          fontFamily: type === 'text' ? 'var(--font-mono)' : 'inherit',
          width: type === 'text' ? '72px' : '130px',
          boxSizing: 'border-box',
          outline: 'none',
        }}
        onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--accent)' }}
        onBlur={(e) => { e.currentTarget.style.borderColor = 'var(--border-strong)' }}
      />
    </div>
  )
}

export function HistoryFilters({ filters, onChange, onApply, onClear, isFiltered }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)  // acordeón en móvil

  function set(key, val) {
    onChange({ ...filters, [key]: val })
  }

  const filterContent = (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: '12px 16px',
        alignItems: 'flex-end',
      }}
    >
      {/* Grupo coordenadas */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
        <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
          {t('ar.history.filter.coords')}
        </span>
        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
          <FilterInput
            id="filter-x"
            label={t('ar.history.filter.x')}
            value={filters.x ?? ''}
            onChange={(v) => set('x', v)}
            placeholder="0"
          />
          <FilterInput
            id="filter-y"
            label={t('ar.history.filter.y')}
            value={filters.y ?? ''}
            onChange={(v) => set('y', v)}
            placeholder="0"
          />
        </div>
      </div>

      {/* Grupo fechas */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
        <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
          {t('ar.history.filter.dates')}
        </span>
        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
          <FilterInput
            id="filter-from"
            label={t('ar.history.filter.from')}
            value={filters.from_date ?? ''}
            onChange={(v) => set('from_date', v)}
            type="date"
          />
          <FilterInput
            id="filter-to"
            label={t('ar.history.filter.to')}
            value={filters.to_date ?? ''}
            onChange={(v) => set('to_date', v)}
            type="date"
          />
        </div>
      </div>

      {/* Botones */}
      <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-end', paddingBottom: '0' }}>
        <button
          type="button"
          onClick={onApply}
          style={{
            height: '32px',
            padding: '0 14px',
            background: 'var(--btn-primary-bg)',
            color: 'var(--btn-primary-text)',
            border: 'none',
            borderRadius: 'var(--radius-sm)',
            fontSize: '13px',
            fontWeight: 500,
            fontFamily: 'inherit',
            cursor: 'pointer',
          }}
        >
          {t('ar.history.filter.apply')}
        </button>
        {isFiltered && (
          <button
            type="button"
            onClick={onClear}
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
            {t('ar.history.filter.clear')}
          </button>
        )}
      </div>
    </div>
  )

  return (
    <div
      style={{
        background: 'var(--surface-2)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-sm)',
        padding: '10px 14px',
      }}
    >
      {/* Header acordeón (visible en móvil) */}
      <div className="block md:hidden">
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
          style={{
            background: 'none',
            border: 'none',
            padding: 0,
            width: '100%',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            cursor: 'pointer',
            fontSize: '13px',
            color: 'var(--text-secondary)',
            fontFamily: 'inherit',
          }}
        >
          <span>
            {t('ar.history.filter.coords')} / {t('ar.history.filter.dates')}
            {isFiltered && (
              <span style={{ marginLeft: '6px', color: 'var(--accent-text)', fontSize: '11px' }}>
                ●
              </span>
            )}
          </span>
          <span aria-hidden="true" style={{ fontSize: '10px' }}>{open ? '▴' : '▾'}</span>
        </button>
        {open && <div style={{ marginTop: '12px' }}>{filterContent}</div>}
      </div>

      {/* Visible en tablet/desktop (md+) */}
      <div className="hidden md:block">
        {filterContent}
      </div>
    </div>
  )
}
