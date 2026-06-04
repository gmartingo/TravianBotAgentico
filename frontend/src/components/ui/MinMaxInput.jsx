/**
 * MinMaxInput — Par de inputs numéricos con validación "max >= min".
 *
 * Props:
 *  - minVal       {number}   — valor del mínimo
 *  - maxVal       {number}   — valor del máximo
 *  - onMinChange  {Function} — fn(newMin)
 *  - onMaxChange  {Function} — fn(newMax)
 *  - disabled     {boolean}
 *  - step         {number}   — step del input (default 1)
 *  - minLimit     {number}   — límite inferior del mínimo (default 0)
 *  - isFloat      {boolean}  — usa ancho 80px (float) vs 72px (int)
 *  - labelMin     {string}   — aria-label mínimo
 *  - labelMax     {string}   — aria-label máximo
 *  - errorMsg     {string}   — mensaje de error (si null, la validación es interna)
 *  - errorId      {string}   — id del span de error para aria-describedby
 *
 * Spec: docs/design/noise-catalog-ui.md §8 (MinMaxInput)
 */
import { useI18n } from '../../i18n/index.jsx'

export function MinMaxInput({
  minVal, maxVal,
  onMinChange, onMaxChange,
  disabled = false,
  step = 1,
  minLimit = 0,
  isFloat = false,
  labelMin,
  labelMax,
  errorMsg,
  errorId,
}) {
  const { t } = useI18n()

  const hasError = maxVal < minVal
  const width = isFloat ? '80px' : '72px'
  const errMsg = errorMsg ?? (hasError ? t('noise.config.minMaxError') : null)
  const errSpanId = errorId ?? undefined

  const inputBase = {
    width,
    padding: '4px 6px',
    border: '1px solid var(--border-strong)',
    borderRadius: 'var(--radius-sm)',
    background: 'var(--surface)',
    color: 'var(--text)',
    fontFamily: 'var(--font-mono)',
    fontSize: '13px',
    fontVariantNumeric: 'tabular-nums',
    minHeight: '32px',
    textAlign: 'center',
    opacity: disabled ? 0.6 : 1,
  }

  return (
    <span style={{ display: 'inline-flex', flexDirection: 'column', gap: '4px' }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
        <input
          type="number"
          value={minVal}
          min={minLimit}
          step={step}
          disabled={disabled}
          aria-label={labelMin}
          aria-describedby={errSpanId}
          onChange={e => onMinChange(isFloat ? parseFloat(e.target.value) : parseInt(e.target.value, 10))}
          style={inputBase}
        />
        <span style={{ color: 'var(--text-secondary)', fontSize: '13px', userSelect: 'none' }}>—</span>
        <input
          type="number"
          value={maxVal}
          min={minLimit}
          step={step}
          disabled={disabled}
          aria-label={labelMax}
          aria-describedby={errSpanId}
          onChange={e => onMaxChange(isFloat ? parseFloat(e.target.value) : parseInt(e.target.value, 10))}
          style={{
            ...inputBase,
            border: `1px solid ${hasError ? 'var(--danger)' : 'var(--border-strong)'}`,
          }}
        />
      </span>
      {errMsg && (
        <span
          id={errSpanId}
          role="alert"
          style={{ fontSize: '11px', color: 'var(--danger)', marginTop: '2px' }}
        >
          {errMsg}
        </span>
      )}
    </span>
  )
}
