/**
 * NoiseWizardStepForm — Formulario de un paso del wizard.
 *
 * Campos:
 *  - URL actual (contexto, no se guarda)
 *  - Descripción del botón/enlace
 *  - outerHTML del elemento (textarea)
 *  - URL esperada tras el click (colapsable, opcional)
 *
 * Props:
 *  - worldId       {number}
 *  - stepIndex     {number}        — número del paso (para el título)
 *  - onDerived     {Function(result, outerHtml, expectedUrl)} — cuando EP-N11 devuelve OK
 *  - disabled      {boolean}
 *
 * Spec: docs/design/noise-catalog-ui.md §6 (Wizard — Formulario "Añadir paso")
 */
import { useState } from 'react'
import { useI18n } from '../../../i18n/index.jsx'
import { api, ApiError } from '../../../api/client.js'
import { Spinner } from '../../ui/uiUtils.jsx'
import { NoiseDerivedSelectorFeedback } from './NoiseDerivedSelectorFeedback.jsx'

export function NoiseWizardStepForm({ worldId, stepIndex, onDerived, disabled }) {
  const { t } = useI18n()
  const [urlCtx, setUrlCtx] = useState('')
  const [stepLabel, setStepLabel] = useState('')
  const [outerHtml, setOuterHtml] = useState('')
  const [expectedUrl, setExpectedUrl] = useState('')
  const [showExpectedUrl, setShowExpectedUrl] = useState(false)
  const [deriving, setDeriving] = useState(false)
  const [deriveResult, setDeriveResult] = useState(null)
  const [deriveError, setDeriveError] = useState(null)

  const canDerive = outerHtml.trim().length > 0 && !deriving

  async function handleDerive() {
    if (!canDerive) return
    setDeriving(true)
    setDeriveResult(null)
    setDeriveError(null)
    try {
      const result = await api.deriveNoiseSelector(worldId, outerHtml.trim())
      setDeriveResult(result)
    } catch (e) {
      if (e instanceof ApiError) {
        setDeriveError(e.detail ?? t('noise.wizard.derive.serverError'))
      } else {
        setDeriveError(t('noise.wizard.derive.serverError'))
      }
    } finally {
      setDeriving(false)
    }
  }

  function handleConfirm(selector) {
    onDerived({
      selector,
      deriveResult,
      stepLabel: stepLabel.trim(),
      expectedUrl: expectedUrl.trim() || null,
    })
    // Reset form
    setUrlCtx('')
    setStepLabel('')
    setOuterHtml('')
    setExpectedUrl('')
    setShowExpectedUrl(false)
    setDeriveResult(null)
    setDeriveError(null)
  }

  function handleRetry() {
    setDeriveResult(null)
    setDeriveError(null)
  }

  const labelStyle = {
    display: 'block',
    fontSize: '12px', fontWeight: 500,
    color: 'var(--text-secondary)',
    marginBottom: '4px',
  }

  const inputStyle = {
    width: '100%',
    padding: '6px 8px',
    border: '1px solid var(--border-strong)',
    borderRadius: 'var(--radius-sm)',
    background: 'var(--surface)', color: 'var(--text)',
    fontFamily: 'inherit', fontSize: '13px',
    boxSizing: 'border-box',
    opacity: disabled ? 0.7 : 1,
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      <p style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)', margin: 0 }}>
        {t('noise.steps.col.order')} {stepIndex + 1} — Click
      </p>

      {/* URL actual (contexto) */}
      <div>
        <label style={labelStyle}>{t('noise.wizard.step.urlCtx')}</label>
        <input
          type="text"
          value={urlCtx}
          onChange={e => setUrlCtx(e.target.value)}
          disabled={disabled}
          placeholder="/statistics"
          style={inputStyle}
        />
      </div>

      {/* Descripción del botón */}
      <div>
        <label style={labelStyle}>{t('noise.wizard.step.labelField')}</label>
        <input
          type="text"
          value={stepLabel}
          onChange={e => setStepLabel(e.target.value)}
          disabled={disabled}
          placeholder="enlace 'Estadísticas' en el menú lateral"
          style={inputStyle}
        />
      </div>

      {/* outerHTML */}
      <div>
        <label style={labelStyle}>{t('noise.wizard.step.outerHtml')}</label>
        <textarea
          value={outerHtml}
          onChange={e => { setOuterHtml(e.target.value); setDeriveResult(null); setDeriveError(null) }}
          disabled={disabled || deriving}
          rows={4}
          placeholder={t('noise.wizard.step.outerHtmlPlaceholder')}
          style={{
            ...inputStyle,
            fontFamily: 'var(--font-mono)',
            fontSize: '12px',
            resize: 'vertical',
            lineHeight: '1.5',
          }}
        />
      </div>

      {/* URL esperada (colapsable) */}
      <div>
        <button
          type="button"
          onClick={() => setShowExpectedUrl(v => !v)}
          style={{
            appearance: 'none', border: 'none', background: 'transparent',
            cursor: 'pointer', padding: 0,
            fontSize: '12px', color: 'var(--text-secondary)',
            display: 'flex', alignItems: 'center', gap: '5px',
            fontFamily: 'inherit',
          }}
          aria-expanded={showExpectedUrl}
        >
          <span>{showExpectedUrl ? '▼' : '▶'}</span>
          {t('noise.wizard.step.expectedUrl')}
        </button>
        {showExpectedUrl && (
          <div style={{ marginTop: '6px' }}>
            <input
              type="text"
              value={expectedUrl}
              onChange={e => setExpectedUrl(e.target.value)}
              disabled={disabled}
              placeholder="/village/statistics"
              style={inputStyle}
            />
          </div>
        )}
      </div>

      {/* Botón derivar */}
      {!deriveResult && !deriveError && (
        <button
          type="button"
          onClick={handleDerive}
          disabled={!canDerive || disabled}
          style={{
            height: '34px', padding: '0 16px',
            border: 'none',
            background: (!canDerive || disabled) ? 'var(--surface-2)' : 'var(--btn-primary-bg)',
            color: (!canDerive || disabled) ? 'var(--text-disabled)' : 'var(--btn-primary-text)',
            borderRadius: 'var(--radius-sm)',
            fontFamily: 'inherit', fontSize: '13px', fontWeight: 500,
            cursor: (!canDerive || disabled) ? 'not-allowed' : 'pointer',
            display: 'flex', alignItems: 'center', gap: '6px',
            alignSelf: 'flex-start',
          }}
        >
          {deriving && <Spinner size={12} />}
          {deriving ? t('noise.wizard.step.deriving') : t('noise.wizard.step.deriveBtn')}
        </button>
      )}

      {/* Feedback de derivación */}
      {(deriveResult || deriveError) && (
        <NoiseDerivedSelectorFeedback
          result={deriveResult}
          deriveError={deriveError}
          onConfirm={handleConfirm}
          onRetry={handleRetry}
        />
      )}
    </div>
  )
}
