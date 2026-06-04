/**
 * NoisePathWizard — Wizard de creación de rutas de ruido.
 *
 * Flujo:
 *  - Paso 0: Etiqueta de ruta + selector de origen (EP-N12)
 *  - Pasos 1..N: formulario de paso (outerHTML → EP-N11 → confirmar selector)
 *  - Lista de pasos acumulados + Guardar (EP-N08)
 *
 * Props:
 *  - worldId          {number}
 *  - destId           {number}
 *  - onCreated        {Function(path)} — callback tras crear la ruta con éxito
 *  - origins          {object|null}   — datos EP-N12 precargados (opcional).
 *                                       Si se pasan, el wizard no hace fetch propio.
 *  - loadingOrigins   {boolean}       — estado de carga del padre
 *  - originsError     {string|null}   — error del padre
 *  - onOriginsRefreshed {Function}    — callback cuando aldeas se refrescan
 *  - onRetryOrigins   {Function}      — callback para reintentar carga de orígenes
 *
 * Optimización: cuando origins/loadingOrigins/originsError vienen como props
 * (modo "controlado"), el wizard no dispara EP-N12. Esto evita el fetch
 * duplicado en cada apertura del drawer. Si no se pasan props (modo standalone),
 * el wizard hace su propio fetch como antes.
 *
 * Spec: docs/design/noise-catalog-ui.md §5 (Happy path 3), §6 (Wizard), §7
 */
import { useState, useEffect, useCallback } from 'react'
import { useI18n } from '../../../i18n/index.jsx'
import { api, ApiError } from '../../../api/client.js'
import { Spinner, showToast } from '../../ui/uiUtils.jsx'
import { NoiseOriginSelector } from './NoiseOriginSelector.jsx'
import { NoiseWizardStepForm } from './NoiseWizardStepForm.jsx'

export function NoisePathWizard({
  worldId, destId, onCreated,
  // Props controladas de orígenes (opcionales — si se pasan, no se hace fetch propio)
  origins: originsProp,
  loadingOrigins: loadingOriginsProp,
  originsError: originsErrorProp,
  onOriginsRefreshed,
  onRetryOrigins,
}) {
  const { t } = useI18n()

  // Modo "controlado": los orígenes vienen del padre (NoiseTab vía drawer)
  const controlled = originsProp !== undefined

  // Fases: 'origin' | 'addstep' | 'saving'
  const [phase, setPhase] = useState('origin')

  // Datos del wizard
  const [routeLabel, setRouteLabel] = useState('')
  const [origin, setOrigin] = useState('')
  const [originLabel, setOriginLabel] = useState('')
  const [steps, setSteps] = useState([]) // [{selector, expectedUrl, stepLabel}]

  // Origins (EP-N12) — estado local solo en modo standalone
  const [originsLocal, setOriginsLocal] = useState(null)
  const [loadingOriginsLocal, setLoadingOriginsLocal] = useState(!controlled)
  const [originsErrorLocal, setOriginsErrorLocal] = useState(null)

  // Resolver cuáles usar (controlled vs local)
  const origins = controlled ? originsProp : originsLocal
  const loadingOrigins = controlled ? (loadingOriginsProp ?? false) : loadingOriginsLocal
  const originsError = controlled ? (originsErrorProp ?? null) : originsErrorLocal

  // Guardar
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)

  const loadOriginsLocal_ = useCallback(async () => {
    setLoadingOriginsLocal(true)
    setOriginsErrorLocal(null)
    try {
      const data = await api.getNoiseOrigins(worldId)
      setOriginsLocal(data)
      // Default origin
      if (!origin && data.generic_origins?.length > 0) {
        setOrigin(data.generic_origins[0].value)
        setOriginLabel(data.generic_origins[0].label)
      }
    } catch (e) {
      setOriginsErrorLocal(e instanceof ApiError ? e.detail : t('noise.wizard.originLoadError'))
    } finally {
      setLoadingOriginsLocal(false)
    }
  }, [worldId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Solo cargar localmente en modo standalone
  useEffect(() => {
    if (!controlled) {
      loadOriginsLocal_()
    }
  }, [controlled, loadOriginsLocal_])

  // En modo controlado: cuando los orígenes llegan por primera vez,
  // establecer el origen por defecto
  useEffect(() => {
    if (controlled && origins && !origin) {
      const first = origins.generic_origins?.[0]
      if (first) {
        setOrigin(first.value)
        setOriginLabel(first.label)
      }
    }
  }, [controlled, origins, origin])

  // Callbacks para el selector de origen
  const handleRetryOrigins = controlled ? onRetryOrigins : loadOriginsLocal_
  const handleOriginsRefreshed = controlled
    ? onOriginsRefreshed
    : (newOrigins) => setOriginsLocal(newOrigins)

  function handleStepDerived({ selector, expectedUrl }) {
    const newStep = {
      step_order: steps.length,
      action: 'CLICK',
      selector,
      value: '',
      delay_min_ms: 500,
      delay_max_ms: 900,
      expected_url_after_click: expectedUrl || null,
    }
    setSteps(prev => [...prev, newStep])
    setPhase('origin') // Vuelve a mostrar el origen + lista de pasos
  }

  function handleRemoveStep(idx) {
    setSteps(prev => {
      const next = prev.filter((_, i) => i !== idx)
      // Renumerar step_order
      return next.map((s, i) => ({ ...s, step_order: i }))
    })
  }

  async function handleSave() {
    if (steps.length === 0 || !routeLabel.trim() || saving) return
    setSaving(true)
    setSaveError(null)
    try {
      const path = await api.createNoisePath(worldId, destId, {
        origin,
        label: routeLabel.trim(),
        steps,
      })
      showToast(t('noise.wizard.saved'))
      // Reset wizard
      setRouteLabel('')
      setSteps([])
      setPhase('origin')
      onCreated(path)
    } catch (e) {
      setSaveError(e instanceof ApiError ? e.detail : t('noise.wizard.saveError'))
    } finally {
      setSaving(false)
    }
  }

  function handleClear() {
    if (steps.length > 0) {
      const msg = t('noise.wizard.clearConfirm').replace('{n}', steps.length)
      if (!window.confirm(msg)) return
    }
    setRouteLabel('')
    setSteps([])
    setPhase('origin')
    setSaveError(null)
  }

  const canSave = steps.length > 0 && routeLabel.trim().length > 0

  return (
    <div>
      {/* Título de sección */}
      <p style={{
        fontSize: '11px', fontWeight: 600,
        textTransform: 'uppercase', letterSpacing: '.06em',
        color: 'var(--text-tertiary)', marginBottom: '12px',
      }}>
        {t('noise.wizard.title')}
      </p>

      {/* Etiqueta de la ruta */}
      <div style={{ marginBottom: '12px' }}>
        <label style={{ display: 'block', fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '4px' }}>
          {t('noise.wizard.labelField')}
        </label>
        <input
          type="text"
          value={routeLabel}
          onChange={e => setRouteLabel(e.target.value)}
          disabled={saving}
          placeholder="Ir a estadísticas desde el menú"
          style={{
            width: '100%', padding: '6px 8px',
            border: '1px solid var(--border-strong)',
            borderRadius: 'var(--radius-sm)',
            background: 'var(--surface)', color: 'var(--text)',
            fontFamily: 'inherit', fontSize: '13px',
            boxSizing: 'border-box',
          }}
        />
      </div>

      {/* Selector de origen */}
      <div style={{ marginBottom: '14px' }}>
        <label style={{ display: 'block', fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '4px' }}>
          {t('noise.wizard.originField')}
        </label>
        <NoiseOriginSelector
          worldId={worldId}
          origins={origins}
          loading={loadingOrigins}
          loadError={originsError}
          value={origin}
          onChange={(v, lbl) => { setOrigin(v); setOriginLabel(lbl) }}
          onRetry={handleRetryOrigins}
          onRefreshed={handleOriginsRefreshed}
          disabled={saving}
        />
      </div>

      {/* Lista de pasos acumulados */}
      {steps.length > 0 && (
        <div style={{ marginBottom: '14px' }}>
          <p style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '6px' }}>
            {t('noise.wizard.steps.title')}
          </p>
          <div style={{
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            overflow: 'hidden',
          }}>
            {steps.map((step, i) => (
              <div key={i} style={{
                display: 'flex', alignItems: 'center', gap: '8px',
                padding: '7px 10px',
                borderBottom: i < steps.length - 1 ? '1px solid var(--border)' : undefined,
                background: 'var(--surface)',
              }}>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: '11px',
                  color: 'var(--text-tertiary)', flexShrink: 0, minWidth: '16px',
                }}>
                  {i}
                </span>
                <span style={{
                  fontSize: '11px', fontWeight: 500,
                  color: 'var(--text-secondary)', flexShrink: 0,
                  background: 'var(--surface-2)',
                  borderRadius: 'var(--radius-full)',
                  padding: '1px 6px',
                }}>
                  CLICK
                </span>
                <code style={{
                  fontFamily: 'var(--font-mono)', fontSize: '12px',
                  color: 'var(--text)', flex: 1, wordBreak: 'break-all',
                }}>
                  {step.selector}
                </code>
                {step.expected_url_after_click && (
                  <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', whiteSpace: 'nowrap' }}>
                    → {step.expected_url_after_click}
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => handleRemoveStep(i)}
                  aria-label={t('noise.wizard.steps.removeStep').replace('{n}', i)}
                  style={{
                    width: '22px', height: '22px',
                    border: 'none', background: 'transparent',
                    cursor: 'pointer', flexShrink: 0,
                    color: 'var(--text-tertiary)', fontSize: '14px',
                    borderRadius: 'var(--radius-sm)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Fase addstep: formulario del paso */}
      {phase === 'addstep' && (
        <div style={{
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)',
          padding: '14px',
          marginBottom: '14px',
          background: 'var(--surface-2)',
        }}>
          <NoiseWizardStepForm
            worldId={worldId}
            stepIndex={steps.length}
            onDerived={handleStepDerived}
            disabled={saving}
          />
        </div>
      )}

      {/* Botones de acción */}
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
        {phase === 'origin' && (
          <button
            type="button"
            onClick={() => setPhase('addstep')}
            disabled={!origin || loadingOrigins || saving}
            style={{
              height: '34px', padding: '0 14px',
              border: '1px solid var(--border-strong)',
              background: 'var(--surface)',
              color: (!origin || loadingOrigins || saving) ? 'var(--text-disabled)' : 'var(--text)',
              borderRadius: 'var(--radius-sm)',
              fontFamily: 'inherit', fontSize: '13px',
              cursor: (!origin || loadingOrigins || saving) ? 'not-allowed' : 'pointer',
            }}
          >
            {steps.length === 0 ? t('noise.wizard.addFirstStep') : t('noise.wizard.addStep')}
          </button>
        )}

        {phase === 'origin' && (
          <button
            type="button"
            onClick={handleSave}
            disabled={!canSave || saving}
            title={!canSave ? t('noise.wizard.saveHint') : undefined}
            style={{
              height: '34px', padding: '0 16px',
              border: 'none',
              background: (!canSave || saving) ? 'var(--surface-2)' : 'var(--btn-primary-bg)',
              color: (!canSave || saving) ? 'var(--text-disabled)' : 'var(--btn-primary-text)',
              borderRadius: 'var(--radius-sm)',
              fontFamily: 'inherit', fontSize: '13px', fontWeight: 500,
              cursor: (!canSave || saving) ? 'not-allowed' : 'pointer',
              display: 'flex', alignItems: 'center', gap: '6px',
            }}
          >
            {saving && <Spinner size={12} />}
            {saving ? t('noise.wizard.saving') : t('noise.wizard.saveRoute')}
          </button>
        )}

        <button
          type="button"
          onClick={handleClear}
          style={{
            marginInlineStart: 'auto',
            height: '30px', padding: '0 10px',
            border: 'none', background: 'transparent',
            color: 'var(--text-tertiary)',
            fontFamily: 'inherit', fontSize: '12px',
            cursor: 'pointer',
          }}
        >
          {t('noise.wizard.clear')}
        </button>
      </div>

      {/* Pista de por qué no se puede guardar todavía */}
      {phase === 'origin' && !canSave && !saving && (
        <p style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginTop: '8px' }}>
          {t('noise.wizard.saveHint')}
        </p>
      )}

      {/* Error de guardar */}
      {saveError && (
        <p role="alert" style={{ fontSize: '12px', color: 'var(--danger)', marginTop: '8px' }}>
          {saveError}
        </p>
      )}
    </div>
  )
}
