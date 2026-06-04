/**
 * Toggle — Interruptor ON/OFF estilo macOS.
 *
 * Props:
 *  - checked    {boolean}   — estado actual
 *  - onChange   {Function}  — fn(newValue)
 *  - disabled   {boolean}   — deshabilitar
 *  - loading    {boolean}   — mostrar spinner pequeño en el thumb
 *  - label      {string}    — aria-label descriptivo (obligatorio)
 *  - id         {string}    — id opcional para asociar <label>
 *
 * Tokens usados:
 *  - ON:  --success (track)
 *  - OFF: --border-strong (track)
 *  - Thumb: --surface
 *
 * Tamaño: 36×20px track. Target táctil: 44px con padding compensatorio.
 * Rol: switch + aria-checked.
 *
 * Spec: docs/design/noise-catalog-ui.md §8
 */
import { useId } from 'react'
import { BadgeSpinner } from './uiUtils.jsx'

export function Toggle({ checked, onChange, disabled = false, loading = false, label, id }) {
  const autoId = useId()
  const controlId = id ?? autoId

  function handleClick() {
    if (!disabled && !loading) onChange(!checked)
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      handleClick()
    }
  }

  const trackColor = checked ? 'var(--success)' : 'var(--border-strong)'
  const thumbPos   = checked ? '18px' : '2px'

  return (
    // Padding compensatorio para target táctil ≥ 44px
    <button
      id={controlId}
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled || loading}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      style={{
        appearance: 'none',
        border: 'none',
        background: 'transparent',
        padding: '12px 4px',
        cursor: (disabled || loading) ? 'not-allowed' : 'pointer',
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        opacity: disabled ? 0.5 : 1,
        WebkitTapHighlightColor: 'transparent',
        outline: 'none',
      }}
    >
      {/* Track */}
      <span
        aria-hidden="true"
        style={{
          position: 'relative',
          display: 'block',
          width: '36px',
          height: '20px',
          borderRadius: '10px',
          background: trackColor,
          transition: 'background 150ms ease',
          flexShrink: 0,
        }}
      >
        {/* Thumb */}
        <span
          style={{
            position: 'absolute',
            top: '2px',
            insetInlineStart: thumbPos,
            width: '16px',
            height: '16px',
            borderRadius: '50%',
            background: 'var(--surface)',
            boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
            transition: 'inset-inline-start 150ms ease',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '8px',
            color: 'var(--text-secondary)',
          }}
        >
          {loading && <BadgeSpinner />}
        </span>
      </span>
    </button>
  )
}
