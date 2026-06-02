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
import { useState, useRef } from 'react'
import { Calendar } from 'lucide-react'
import { useI18n } from '../../i18n/index.jsx'
import { RangeCalendarPopover } from '../ui/RangeCalendarPopover.jsx'

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

// ── Input de fecha con validación en vivo + calendario integrado ──────────────
// El propio campo es el disparador del popover: hacer click en él (o en el icono
// 📅 que lleva dentro) abre el calendario de rango. Teclear sigue funcionando
// (el popover no roba el foco; es un editor visual de este mismo input).
function DateFilterInput({ id, label, value, onChange, onOpen, onToggle, calOpen, inputRef, t }) {
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
      <div style={{ position: 'relative' }}>
        <input
          id={id}
          ref={inputRef}
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onClick={onOpen}
          placeholder={t('ar.history.filter.date.placeholder')}
          aria-invalid={!valid}
          aria-describedby={!valid ? errorId : undefined}
          style={{
            height: '32px',
            // espacio a la derecha para el icono 📅 (propiedad lógica para RTL)
            paddingBlock: '0',
            paddingInlineStart: '8px',
            paddingInlineEnd: '38px',
            background: 'var(--surface)',
            border: `1px solid ${!valid ? 'var(--danger)' : 'var(--border-strong)'}`,
            borderRadius: 'var(--radius-sm)',
            fontSize: '13px',
            color: 'var(--text)',
            fontFamily: 'var(--font-mono)',
            width: '170px',
            boxSizing: 'border-box',
            outline: 'none',
            cursor: 'pointer',
          }}
          onFocus={(e) => {
            if (valid) e.currentTarget.style.borderColor = 'var(--accent)'
          }}
          onBlur={(e) => {
            e.currentTarget.style.borderColor = valid ? 'var(--border-strong)' : 'var(--danger)'
          }}
        />
        <button
          type="button"
          tabIndex={-1}
          onClick={(e) => { e.stopPropagation(); onToggle() }}
          aria-haspopup="dialog"
          aria-expanded={calOpen}
          aria-label={t('ar.history.filter.cal.title')}
          title={t('ar.history.filter.cal.title')}
          style={{
            position: 'absolute',
            insetInlineEnd: '3px',
            top: '3px',
            bottom: '3px',
            width: '28px',
            display: 'grid',
            placeItems: 'center',
            background: calOpen ? 'var(--accent-subtle)' : 'var(--surface-2)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            color: valid ? (calOpen ? 'var(--accent-text)' : 'var(--text-secondary)') : 'var(--danger)',
            cursor: 'pointer',
            transition: 'background var(--dur-fast), color var(--dur-fast), border-color var(--dur-fast)',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'var(--accent-subtle)'
            e.currentTarget.style.borderColor = 'var(--accent)'
            e.currentTarget.style.color = 'var(--accent-text)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = calOpen ? 'var(--accent-subtle)' : 'var(--surface-2)'
            e.currentTarget.style.borderColor = calOpen ? 'var(--accent)' : 'var(--border)'
            e.currentTarget.style.color = valid ? (calOpen ? 'var(--accent-text)' : 'var(--text-secondary)') : 'var(--danger)'
          }}
        >
          <Calendar size={17} aria-hidden="true" />
        </button>
      </div>
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

// Valor entero ordenable de "YYYY-MM-DD HH:MM:SS" (para detectar from > to).
function ordValue(val) {
  const m = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})$/.exec((val ?? '').trim())
  if (!m) return null
  return +m[1] * 1e10 + +m[2] * 1e8 + +m[3] * 1e6 + +m[4] * 1e4 + +m[5] * 1e2 + +m[6]
}

export function HistoryFilters({ filters, onChange, onApply, onClear, isFiltered }) {
  const { t, lang } = useI18n()
  const [open, setOpen] = useState(false)  // acordeón en móvil
  const [calOpen, setCalOpen] = useState(false)  // popover del calendario
  const fieldsWrapRef = useRef(null)   // contenedor de los inputs (anclaje + click-fuera)
  const fromInputRef = useRef(null)    // input "Desde" (recupera foco al cerrar)

  const openCal = () => setCalOpen(true)
  const toggleCal = () => setCalOpen((v) => !v)

  function set(key, val) {
    onChange({ ...filters, [key]: val })
  }

  // El calendario escribe ambos extremos a la vez (editor visual de los inputs).
  function setRange(fromVal, toVal) {
    onChange({ ...filters, from_date: fromVal, to_date: toVal })
  }

  // Hay error si algún campo de fecha tiene valor y no cumple la regex
  const fromInvalid = !validateDate(filters.from_date ?? '')
  const toInvalid   = !validateDate(filters.to_date ?? '')
  // Orden inválido: ambos válidos y no vacíos pero from > to
  const fromOrd = ordValue(filters.from_date)
  const toOrd   = ordValue(filters.to_date)
  const orderError = fromOrd !== null && toOrd !== null && fromOrd > toOrd
  const hasDateError = fromInvalid || toInvalid || orderError

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
        <div
          ref={fieldsWrapRef}
          style={{ position: 'relative', display: 'flex', gap: '6px', alignItems: 'flex-start' }}
        >
          <DateFilterInput
            id="filter-from"
            label={t('ar.history.filter.from')}
            value={filters.from_date ?? ''}
            onChange={(v) => set('from_date', v)}
            onOpen={openCal}
            onToggle={toggleCal}
            calOpen={calOpen}
            inputRef={fromInputRef}
            t={t}
          />
          <DateFilterInput
            id="filter-to"
            label={t('ar.history.filter.to')}
            value={filters.to_date ?? ''}
            onChange={(v) => set('to_date', v)}
            onOpen={openCal}
            onToggle={toggleCal}
            calOpen={calOpen}
            t={t}
          />
          {/* Popover de rango — anclado al grupo de campos, no a un botón suelto */}
          {calOpen && (
            <RangeCalendarPopover
              fromText={filters.from_date ?? ''}
              toText={filters.to_date ?? ''}
              onChange={setRange}
              onApply={handleApply}
              onClose={() => setCalOpen(false)}
              t={t}
              lang={lang}
              triggerRef={fieldsWrapRef}
              focusReturnRef={fromInputRef}
            />
          )}
        </div>
        {orderError && (
          <span
            role="alert"
            style={{ fontSize: '11px', color: 'var(--danger)', marginTop: '2px' }}
          >
            {t('ar.history.filter.cal.orderError')}
          </span>
        )}
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
