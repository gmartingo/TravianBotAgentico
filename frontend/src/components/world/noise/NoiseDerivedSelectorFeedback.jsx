/**
 * NoiseDerivedSelectorFeedback — Panel de feedback del resultado de EP-N11.
 *
 * 3 estados:
 *  A: único   (is_unique=true)
 *  B: no único (is_unique=false, con alternativas y input manual)
 *  C: error (422 HTML malformado u otro error)
 *
 * Props:
 *  - result       {object|null}  — respuesta de EP-N11:
 *                   { selector, is_unique, priority_level, method, warning, alternatives }
 *  - deriveError  {string|null}  — mensaje de error si el derive falló
 *  - onConfirm    {Function(selector)} — cuando el usuario confirma un selector
 *  - onRetry      {Function}     — cuando el usuario quiere reintentar con otro HTML
 *
 * Spec: docs/design/noise-catalog-ui.md §6 (Wizard — Feedback selector derivado)
 */
import { useState } from 'react'
import { useI18n } from '../../../i18n/index.jsx'

// Regex de selectores no-CSS-estructurales (spec EC-NP14)
const INVALID_SELECTOR_REGEX = /:contains|text\(\)/i

export function NoiseDerivedSelectorFeedback({ result, deriveError, onConfirm, onRetry }) {
  const { t } = useI18n()
  const [manualSelector, setManualSelector] = useState('')
  const [manualError, setManualError] = useState(null)

  // Estado C: error
  if (deriveError) {
    return (
      <div style={{
        background: 'rgba(201,53,44,.07)',
        border: '1px solid rgba(201,53,44,.25)',
        borderRadius: 'var(--radius-md)',
        padding: '14px',
      }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', marginBottom: '8px' }}>
          <span style={{ color: 'var(--danger)', fontWeight: 700, fontSize: '14px', flexShrink: 0 }}>✕</span>
          <div>
            <p style={{ fontWeight: 600, fontSize: '13px', color: 'var(--danger)', margin: 0 }}>
              {t('noise.wizard.step.invalidHtml')}
            </p>
            <p style={{ fontSize: '12px', color: 'var(--text-secondary)', margin: '4px 0 0' }}>
              {deriveError}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={onRetry}
          style={{
            height: '30px', padding: '0 12px',
            border: '1px solid var(--border-strong)',
            background: 'var(--surface)', color: 'var(--text)',
            borderRadius: 'var(--radius-sm)',
            fontFamily: 'inherit', fontSize: '12px',
            cursor: 'pointer',
          }}
        >
          {t('noise.wizard.derive.retry')}
        </button>
      </div>
    )
  }

  if (!result) return null

  const { selector, is_unique, method, priority_level, warning, alternatives = [] } = result

  function handleAlternativeClick(alt) {
    setManualSelector(alt)
    setManualError(null)
  }

  function handleManualChange(val) {
    setManualSelector(val)
    if (INVALID_SELECTOR_REGEX.test(val)) {
      setManualError(t('noise.wizard.derive.selectorCssError'))
    } else {
      setManualError(null)
    }
  }

  function handleConfirm() {
    const sel = is_unique
      ? (manualSelector.trim() || selector)
      : (manualSelector.trim() || selector)
    if (INVALID_SELECTOR_REGEX.test(sel)) {
      setManualError(t('noise.wizard.derive.selectorCssError'))
      return
    }
    onConfirm(sel)
  }

  // Estado A: único
  if (is_unique) {
    return (
      <div style={{
        background: 'rgba(36,138,61,.07)',
        border: '1px solid rgba(36,138,61,.25)',
        borderRadius: 'var(--radius-md)',
        padding: '14px',
      }}>
        {/* Selector */}
        <div style={{ marginBottom: '8px' }}>
          <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', display: 'block', marginBottom: '3px' }}>
            {t('noise.wizard.derive.selectorLabel')}
          </span>
          <code style={{
            fontFamily: 'var(--font-mono)', fontSize: '13px',
            color: 'var(--text)', fontWeight: 600,
            wordBreak: 'break-all',
          }}>
            {selector}
          </code>
        </div>

        {/* Método y nivel */}
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
          <span>{t('noise.wizard.derive.method')}: </span>
          <code style={{ fontFamily: 'var(--font-mono)' }}>{method}</code>
          {priority_level && (
            <>
              <span> · {t('noise.wizard.derive.level')} </span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{priority_level}</span>
            </>
          )}
        </div>

        {/* Badge único */}
        <p style={{ fontSize: '12px', color: 'var(--success)', fontWeight: 500, marginBottom: '12px' }}>
          ✓ {t('noise.wizard.derive.unique')}
        </p>

        {/* Botones */}
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <button
            type="button"
            onClick={() => onConfirm(selector)}
            style={{
              height: '32px', padding: '0 14px',
              border: 'none',
              background: 'var(--btn-primary-bg)', color: 'var(--btn-primary-text)',
              borderRadius: 'var(--radius-sm)',
              fontFamily: 'inherit', fontSize: '13px', fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            {t('noise.wizard.derive.confirm')}
          </button>
          <button
            type="button"
            onClick={onRetry}
            style={{
              height: '32px', padding: '0 12px',
              border: '1px solid var(--border-strong)',
              background: 'var(--surface)', color: 'var(--text-secondary)',
              borderRadius: 'var(--radius-sm)',
              fontFamily: 'inherit', fontSize: '12px',
              cursor: 'pointer',
            }}
          >
            {t('noise.wizard.derive.manualWrite')}
          </button>
        </div>
      </div>
    )
  }

  // Estado B: no único
  return (
    <div style={{
      background: 'var(--accent-subtle)',
      border: '1px solid rgba(138,100,24,.20)',
      borderRadius: 'var(--radius-md)',
      padding: '14px',
    }}>
      {/* Selector */}
      <div style={{ marginBottom: '8px' }}>
        <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', display: 'block', marginBottom: '3px' }}>
          {t('noise.wizard.derive.selectorLabel')}
        </span>
        <code style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', color: 'var(--text)', wordBreak: 'break-all' }}>
          {selector}
        </code>
      </div>

      {/* Método */}
      <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
        <span>{t('noise.wizard.derive.method')}: </span>
        <code style={{ fontFamily: 'var(--font-mono)' }}>{method}</code>
        {priority_level && (
          <> · {t('noise.wizard.derive.level')} <code style={{ fontFamily: 'var(--font-mono)' }}>{priority_level}</code></>
        )}
      </div>

      {/* Aviso */}
      <p style={{ fontSize: '12px', color: 'var(--accent-text)', fontWeight: 500, marginBottom: '4px' }}>
        ⚠ {t('noise.wizard.derive.notUnique')}
      </p>
      {warning && (
        <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '10px' }}>{warning}</p>
      )}

      {/* Alternativas */}
      {alternatives.length > 0 && (
        <div style={{ marginBottom: '12px' }}>
          <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', display: 'block', marginBottom: '5px' }}>
            {t('noise.wizard.derive.alternatives')}:
          </span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
            {alternatives.map((alt, i) => (
              <button
                key={i}
                type="button"
                onClick={() => handleAlternativeClick(alt)}
                style={{
                  padding: '3px 10px',
                  border: `1px solid ${manualSelector === alt ? 'var(--accent)' : 'var(--border-strong)'}`,
                  borderRadius: 'var(--radius-full)',
                  background: manualSelector === alt ? 'var(--accent-subtle)' : 'var(--surface)',
                  color: 'var(--text)',
                  fontFamily: 'var(--font-mono)', fontSize: '12px',
                  cursor: 'pointer',
                }}
              >
                {alt}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input manual */}
      <div style={{ marginBottom: '12px' }}>
        <label style={{ fontSize: '12px', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>
          {t('noise.wizard.derive.manualSelector')}:
        </label>
        <input
          type="text"
          value={manualSelector}
          onChange={e => handleManualChange(e.target.value)}
          placeholder={selector}
          style={{
            width: '100%', padding: '6px 8px',
            border: `1px solid ${manualError ? 'var(--danger)' : 'var(--border-strong)'}`,
            borderRadius: 'var(--radius-sm)',
            background: 'var(--surface)', color: 'var(--text)',
            fontFamily: 'var(--font-mono)', fontSize: '13px',
            boxSizing: 'border-box',
          }}
          aria-describedby={manualError ? 'manual-sel-err' : undefined}
        />
        {manualError && (
          <span id="manual-sel-err" role="alert" style={{ fontSize: '11px', color: 'var(--danger)', display: 'block', marginTop: '3px' }}>
            {manualError}
          </span>
        )}
      </div>

      {/* Botones */}
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
        <button
          type="button"
          onClick={handleConfirm}
          disabled={!!manualError}
          style={{
            height: '32px', padding: '0 14px',
            border: 'none',
            background: manualError ? 'var(--surface-2)' : 'var(--btn-primary-bg)',
            color: manualError ? 'var(--text-disabled)' : 'var(--btn-primary-text)',
            borderRadius: 'var(--radius-sm)',
            fontFamily: 'inherit', fontSize: '13px', fontWeight: 500,
            cursor: manualError ? 'not-allowed' : 'pointer',
          }}
        >
          {t('noise.wizard.derive.confirm')}
        </button>
        <button
          type="button"
          onClick={onRetry}
          style={{
            height: '32px', padding: '0 12px',
            border: '1px solid var(--border-strong)',
            background: 'var(--surface)', color: 'var(--text-secondary)',
            borderRadius: 'var(--radius-sm)',
            fontFamily: 'inherit', fontSize: '12px',
            cursor: 'pointer',
          }}
        >
          {t('noise.wizard.derive.retry')}
        </button>
      </div>
    </div>
  )
}
