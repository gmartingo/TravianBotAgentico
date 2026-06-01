/**
 * HistoryFilters — Inputs de filtrado del historial de reportes.
 *
 * Desktop/tablet: inline horizontal.
 * Móvil: acordeón colapsable (P2 según §11 del spec).
 *
 * DA-CL29: inputs de fecha son type="text" con placeholder YYYY-MM-DD HH:MM:SS.
 * DA-CL30: validación en vivo: borde rojo + mensaje role="alert" si formato incorrecto.
 * DA-CL31: botón Aplicar disabled si cualquier input de fecha tiene error.
 * DA-CL14: al aplicar, los valores de fecha se convierten a ISO 8601 (espacio → T).
 *
 * Props:
 *   filters    — { x, y, from_date, to_date }
 *   onChange   — (filters) => void
 *   onApply    — (normalizedFilters) => void — recibe fechas como YYYY-MM-DDTHH:MM:SS
 *   onClear    — () => void
 *   isFiltered — boolean (hay algún filtro activo)
 */
import { useState } from 'react'
import { useI18n } from '../../i18n/index.jsx'

// Regex exacta según spec: YYYY-MM-DD HH:MM:SS
const DATE_REGEX = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/

/** Valida el valor de un campo de fecha. Vacío = válido (sin filtro). */
function validateDate(val) {
  if (!val || val.trim() === '') return true
  return DATE_REGEX.test(val.trim())
}

/** Normaliza YYYY-MM-DD HH:MM:SS → YYYY-MM-DDTHH:MM:SS para el backend. */
function toISO(val) {
  if (!val || val.trim() === '') return ''
  return val.trim().replace(' ', 'T')
}

// ── Input de texto genérico (coordenadas) ────────────────────────────────────
function FilterInput({ id, label, value, onChange, placeholder = '' }) {
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
        type="text"
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
          fontFamily: 'var(--font-mono)',
          width: '72px',
          boxSizing: 'border-box',
          outline: 'none',
        }}
        onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--accent)' }}
        onBlur={(e) => { e.currentTarget.style.borderColor = 'var(--border-strong)' }}
      />
    </div>
  )
}

// ── Input de fecha con validación en vivo ────────────────────────────────────
function DateFilterInput({ id, label, value, onChange, t }) {
  const valid = validateDate(value)
  const errorId = `${id}-error`
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
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={t('ar.history.filter.date.placeholder')}
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
          {t('ar.history.filter.date.invalid')}
        </span>
      )}
    </div>
  )
}

export function HistoryFilters({ filters, onChange, onApply, onClear, isFiltered }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)  // acordeón en móvil

  function set(key, val) {
    onChange({ ...filters, [key]: val })
  }

  // Hay error si algún campo de fecha tiene valor y no cumple la regex
  const fromInvalid = !validateDate(filters.from_date ?? '')
  const toInvalid   = !validateDate(filters.to_date ?? '')
  const hasDateError = fromInvalid || toInvalid

  function handleApply() {
    if (hasDateError) return
    // DA-CL14: normalizar fechas (espacio → T) antes de enviar al backend
    const normalized = {
      ...filters,
      from_date: toISO(filters.from_date ?? ''),
      to_date:   toISO(filters.to_date ?? ''),
    }
    onApply(normalized)
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

      {/* Grupo fechas — DA-CL29: type="text" + validación en vivo */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
        <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
          {t('ar.history.filter.dates')}
        </span>
        <div style={{ display: 'flex', gap: '6px', alignItems: 'flex-start' }}>
          <DateFilterInput
            id="filter-from"
            label={t('ar.history.filter.from')}
            value={filters.from_date ?? ''}
            onChange={(v) => set('from_date', v)}
            t={t}
          />
          <DateFilterInput
            id="filter-to"
            label={t('ar.history.filter.to')}
            value={filters.to_date ?? ''}
            onChange={(v) => set('to_date', v)}
            t={t}
          />
        </div>
      </div>

      {/* Botones — DA-CL31: Aplicar disabled si hay error de formato */}
      <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-end', paddingBottom: '0' }}>
        <button
          type="button"
          onClick={handleApply}
          disabled={hasDateError}
          aria-disabled={hasDateError}
          style={{
            height: '32px',
            padding: '0 14px',
            background: hasDateError ? 'var(--text-disabled)' : 'var(--btn-primary-bg)',
            color: 'var(--btn-primary-text)',
            border: 'none',
            borderRadius: 'var(--radius-sm)',
            fontSize: '13px',
            fontWeight: 500,
            fontFamily: 'inherit',
            cursor: hasDateError ? 'not-allowed' : 'pointer',
            opacity: hasDateError ? 0.5 : 1,
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
            {hasDateError && (
              <span style={{ marginLeft: '6px', color: 'var(--danger)', fontSize: '11px' }}>
                ⚠
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
