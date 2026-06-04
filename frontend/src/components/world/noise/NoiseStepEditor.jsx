/**
 * NoiseStepEditor — Editor avanzado de pasos de una ruta (patrón BlockEditor).
 *
 * Columnas: #, Acción, Selector, Valor, ms min, ms max, URL esperada, borrar
 *
 * Props:
 *  - initialSteps {Array}    — pasos actuales de la ruta
 *  - saving       {boolean}
 *  - apiError     {string|null}
 *  - onSave       {Function(steps)} — dispara PUT EP-N09
 *  - onCancel     {Function}
 *
 * Spec: docs/design/noise-catalog-ui.md §6 (Editor de pasos)
 */
import { useState } from 'react'
import { useI18n } from '../../../i18n/index.jsx'
import { Spinner } from '../../ui/uiUtils.jsx'

const ACTIONS = ['CLICK', 'WAIT_FOR_SELECTOR', 'SCROLL_TO', 'HOVER']

const DEFAULT_STEP = {
  action: 'CLICK',
  selector: '',
  value: '',
  delay_min_ms: 500,
  delay_max_ms: 900,
  expected_url_after_click: '',
}

function stepErrors(step) {
  const errs = {}
  if (!step.selector.trim()) errs.selector = true
  if (step.delay_max_ms < step.delay_min_ms) errs.delay = true
  return errs
}

export function NoiseStepEditor({ initialSteps, saving, apiError, onSave, onCancel }) {
  const { t } = useI18n()
  const [steps, setSteps] = useState(
    (initialSteps ?? []).map(s => ({ ...s, expected_url_after_click: s.expected_url_after_click ?? '' }))
  )

  const allErrors = steps.map(stepErrors)
  const hasErrors = allErrors.some(e => Object.keys(e).length > 0)

  function patchStep(idx, field, value) {
    setSteps(prev => prev.map((s, i) => i === idx ? { ...s, [field]: value } : s))
  }

  function addStep() {
    setSteps(prev => [
      ...prev,
      { ...DEFAULT_STEP, step_order: prev.length },
    ])
  }

  function removeStep(idx) {
    setSteps(prev => {
      const next = prev.filter((_, i) => i !== idx)
      return next.map((s, i) => ({ ...s, step_order: i }))
    })
  }

  function handleSave() {
    if (hasErrors || saving) return
    const payload = steps.map((s, i) => ({
      step_order: i,
      action: s.action,
      selector: s.selector.trim(),
      value: s.value ?? '',
      delay_min_ms: Number(s.delay_min_ms),
      delay_max_ms: Number(s.delay_max_ms),
      expected_url_after_click: s.expected_url_after_click?.trim() || null,
    }))
    onSave(payload)
  }

  const thStyle = {
    fontSize: '10px', color: 'var(--text-tertiary)',
    textTransform: 'uppercase', letterSpacing: '.04em',
    fontWeight: 500, padding: '4px 6px',
    borderBottom: '1px solid var(--border)',
    textAlign: 'start', whiteSpace: 'nowrap',
  }

  const tdStyle = {
    padding: '6px 5px',
    borderBottom: '1px solid var(--border)',
    verticalAlign: 'middle',
  }

  const inputBase = {
    padding: '4px 6px',
    border: '1px solid var(--border-strong)',
    borderRadius: 'var(--radius-sm)',
    background: 'var(--surface)', color: 'var(--text)',
    fontFamily: 'inherit', fontSize: '12px',
    minHeight: '30px',
    opacity: saving ? 0.7 : 1,
  }

  return (
    <div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '560px' }}>
          <thead>
            <tr>
              <th scope="col" style={{ ...thStyle, width: '24px' }}>{t('noise.steps.col.order')}</th>
              <th scope="col" style={{ ...thStyle, minWidth: '110px' }}>{t('noise.steps.col.action')}</th>
              <th scope="col" style={{ ...thStyle, minWidth: '120px' }}>{t('noise.steps.col.selector')}</th>
              <th scope="col" style={{ ...thStyle, minWidth: '60px' }}>{t('noise.steps.col.value')}</th>
              <th scope="col" style={{ ...thStyle, width: '58px' }}>{t('noise.steps.col.delayMin')}</th>
              <th scope="col" style={{ ...thStyle, width: '58px' }}>{t('noise.steps.col.delayMax')}</th>
              <th scope="col" style={{ ...thStyle, minWidth: '100px' }}>{t('noise.steps.col.expectedUrl')}</th>
              <th scope="col" style={{ ...thStyle, width: '24px' }} aria-label="Borrar" />
            </tr>
          </thead>
          <tbody>
            {steps.map((step, i) => {
              const errs = allErrors[i]
              return (
                <tr key={i}>
                  {/* Orden */}
                  <td style={{ ...tdStyle, fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-tertiary)', textAlign: 'center' }}>
                    {i}
                  </td>
                  {/* Acción */}
                  <td style={tdStyle}>
                    <select
                      value={step.action}
                      disabled={saving}
                      onChange={e => patchStep(i, 'action', e.target.value)}
                      aria-label={`${t('noise.steps.col.action')} ${i}`}
                      style={{ ...inputBase, width: '100%' }}
                    >
                      {ACTIONS.map(a => (
                        <option key={a} value={a}>{t(`noise.action.${a}`) ?? a}</option>
                      ))}
                    </select>
                  </td>
                  {/* Selector */}
                  <td style={tdStyle}>
                    <input
                      type="text"
                      value={step.selector}
                      disabled={saving}
                      onChange={e => patchStep(i, 'selector', e.target.value)}
                      aria-label={`${t('noise.steps.col.selector')} ${i}`}
                      aria-describedby={errs.selector ? `sel-err-${i}` : undefined}
                      style={{
                        ...inputBase, width: '100%',
                        border: errs.selector ? '1px solid var(--danger)' : inputBase.border,
                        fontFamily: 'var(--font-mono)', fontSize: '12px',
                      }}
                    />
                    {errs.selector && (
                      <span id={`sel-err-${i}`} role="alert" style={{ fontSize: '10px', color: 'var(--danger)' }}>
                        {t('noise.steps.selectorEmpty')}
                      </span>
                    )}
                  </td>
                  {/* Valor */}
                  <td style={tdStyle}>
                    <input
                      type="text"
                      value={step.value ?? ''}
                      disabled={saving}
                      onChange={e => patchStep(i, 'value', e.target.value)}
                      aria-label={`${t('noise.steps.col.value')} ${i}`}
                      title={t('noise.steps.valueHint')}
                      style={{ ...inputBase, width: '56px', fontFamily: 'var(--font-mono)' }}
                    />
                  </td>
                  {/* delay min */}
                  <td style={tdStyle}>
                    <input
                      type="number"
                      min="0"
                      value={step.delay_min_ms}
                      disabled={saving}
                      onChange={e => patchStep(i, 'delay_min_ms', parseInt(e.target.value, 10))}
                      aria-label={`${t('noise.steps.col.delayMin')} ${i}`}
                      style={{ ...inputBase, width: '56px', fontFamily: 'var(--font-mono)', textAlign: 'end' }}
                    />
                  </td>
                  {/* delay max */}
                  <td style={tdStyle}>
                    <input
                      type="number"
                      min="0"
                      value={step.delay_max_ms}
                      disabled={saving}
                      onChange={e => patchStep(i, 'delay_max_ms', parseInt(e.target.value, 10))}
                      aria-label={`${t('noise.steps.col.delayMax')} ${i}`}
                      aria-describedby={errs.delay ? `delay-err-${i}` : undefined}
                      style={{
                        ...inputBase, width: '56px', fontFamily: 'var(--font-mono)', textAlign: 'end',
                        border: errs.delay ? '1px solid var(--danger)' : inputBase.border,
                      }}
                    />
                    {errs.delay && (
                      <span id={`delay-err-${i}`} role="alert" style={{ fontSize: '10px', color: 'var(--danger)', display: 'block' }}>
                        {t('noise.steps.delayError')}
                      </span>
                    )}
                  </td>
                  {/* URL esperada */}
                  <td style={tdStyle}>
                    <input
                      type="text"
                      value={step.expected_url_after_click ?? ''}
                      disabled={saving}
                      onChange={e => patchStep(i, 'expected_url_after_click', e.target.value)}
                      aria-label={`${t('noise.steps.col.expectedUrl')} ${i}`}
                      title={t('noise.steps.expectedUrlHint')}
                      style={{ ...inputBase, width: '100%', fontFamily: 'var(--font-mono)', fontSize: '12px' }}
                    />
                  </td>
                  {/* Borrar */}
                  <td style={{ ...tdStyle, textAlign: 'center' }}>
                    {steps.length > 1 && (
                      <button
                        type="button"
                        onClick={() => removeStep(i)}
                        disabled={saving}
                        aria-label={t('noise.steps.remove') + ' ' + i}
                        style={{
                          width: '24px', height: '24px',
                          border: 'none', background: 'transparent',
                          cursor: saving ? 'not-allowed' : 'pointer',
                          color: 'var(--text-tertiary)', fontSize: '13px',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          borderRadius: 'var(--radius-sm)',
                        }}
                      >
                        ✕
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Footer */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '8px',
        padding: '8px 0', flexWrap: 'wrap',
      }}>
        <button
          type="button"
          onClick={addStep}
          disabled={saving}
          style={{
            height: '28px', padding: '0 10px',
            border: '1px solid var(--border-strong)',
            background: 'var(--surface)', color: 'var(--text-secondary)',
            borderRadius: 'var(--radius-sm)',
            fontFamily: 'inherit', fontSize: '12px',
            cursor: saving ? 'not-allowed' : 'pointer',
          }}
        >
          + {t('noise.steps.addStep')}
        </button>

        <div style={{ flex: 1 }} />

        {apiError && (
          <span role="alert" style={{ fontSize: '12px', color: 'var(--danger)' }}>{apiError}</span>
        )}

        <button
          type="button"
          onClick={onCancel}
          disabled={saving}
          style={{
            height: '30px', padding: '0 12px',
            border: '1px solid var(--border-strong)',
            background: 'var(--surface)', color: 'var(--text-secondary)',
            borderRadius: 'var(--radius-sm)',
            fontFamily: 'inherit', fontSize: '12px',
            cursor: 'pointer',
          }}
        >
          {t('noise.steps.cancel')}
        </button>

        <button
          type="button"
          onClick={handleSave}
          disabled={hasErrors || saving}
          style={{
            height: '30px', padding: '0 12px',
            border: 'none',
            background: (hasErrors || saving) ? 'var(--surface-2)' : 'var(--btn-primary-bg)',
            color: (hasErrors || saving) ? 'var(--text-disabled)' : 'var(--btn-primary-text)',
            borderRadius: 'var(--radius-sm)',
            fontFamily: 'inherit', fontSize: '12px', fontWeight: 500,
            cursor: (hasErrors || saving) ? 'not-allowed' : 'pointer',
            display: 'flex', alignItems: 'center', gap: '5px',
          }}
        >
          {saving && <Spinner size={11} />}
          {saving ? t('noise.steps.saving') : t('noise.steps.save')}
        </button>
      </div>
    </div>
  )
}
