/**
 * NoiseConfigPanel — Panel colapsable de configuración global de ruido.
 *
 * Props:
 *  - config    {object|null}  — datos de EP-N01 ({noise_enabled, hardcore_interval_*_seconds,
 *                               passive_interval_*_seconds, dwell_*})
 *  - loading   {boolean}
 *  - onSaved   {Function}     — fn(newConfig) — callback tras guardar con éxito
 *  - worldId   {number}
 *
 * Comportamiento:
 *  - Toggle noise_enabled → PUT EP-N02 inmediato, sin "Guardar"
 *  - "Guardar config" → PUT EP-N02 con los nuevos campos de intervalo en segundos
 *  - El toggle siempre visible aunque el panel esté colapsado
 *  - Panel colapsable con transición max-height
 *  - Respeta prefers-reduced-motion
 *  - MM:SS: la UI muestra/edita en formato MM:SS; envía/recibe SEGUNDOS (int) (RN-FW01)
 *  - Mínimo 00:30 (30 s) — blindado en backend y validado en cliente (RN-FW02, CA-FW16)
 *
 * Spec: docs/specs/noise-frequency-and-destination-weight.md §8.1, §8.2, CA-FW16/17
 */
import { useState, useId, memo } from 'react'
import { useI18n } from '../../../i18n/index.jsx'
import { api, ApiError } from '../../../api/client.js'
import { Spinner, showToast } from '../../ui/uiUtils.jsx'
import { Toggle } from '../../ui/Toggle.jsx'
import { mmssToSeconds, secondsToMmss, validateMmss } from '../../../utils/time.js'

const PANEL_ANIM = `
  @keyframes noise-config-expand {
    from { opacity: 0; transform: translateY(-4px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  @media (prefers-reduced-motion: reduce) {
    .noise-config-body { animation: none !important; transition: none !important; }
  }
`

// Mínimo absoluto en segundos (RN-FW02, guardian): 30 s
const MIN_INTERVAL_SECONDS = 30

/**
 * MmssMinMaxInput — Par de inputs MM:SS (mín – máx) para un modo.
 *
 * Props:
 *  - minVal   {string}   — valor del mínimo en MM:SS
 *  - maxVal   {string}   — valor del máximo en MM:SS
 *  - onMinChange {fn}    — fn(newMmss)
 *  - onMaxChange {fn}    — fn(newMmss)
 *  - disabled  {boolean}
 *  - labelMin  {string}  — aria-label del input mínimo
 *  - labelMax  {string}  — aria-label del input máximo
 *  - errorId   {string}  — id del span de error
 */
function MmssMinMaxInput({ minVal, maxVal, onMinChange, onMaxChange, disabled, labelMin, labelMax, errorId }) {
  // Validación: formato MM:SS + mínimo 30 s + mín <= máx
  const minErr = validateMmss(minVal, MIN_INTERVAL_SECONDS)
  const maxErr = validateMmss(maxVal, MIN_INTERVAL_SECONDS)

  // Validación cruzada mín <= máx (solo si ambos formatos son válidos)
  let crossErr = null
  if (!minErr && !maxErr) {
    try {
      const minS = mmssToSeconds(minVal)
      const maxS = mmssToSeconds(maxVal)
      if (minS > maxS) {
        crossErr = 'El mínimo debe ser ≤ al máximo'
      }
    } catch (_) { /* ya manejado por minErr/maxErr */ }
  }

  const errMsg = minErr || maxErr || crossErr
  const hasError = errMsg !== null

  const inputBase = {
    width: '72px',
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
    boxSizing: 'border-box',
  }

  return (
    <span style={{ display: 'inline-flex', flexDirection: 'column', gap: '4px' }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
        <input
          type="text"
          inputMode="numeric"
          value={minVal}
          placeholder="mm:ss"
          disabled={disabled}
          aria-label={labelMin}
          aria-describedby={hasError ? errorId : undefined}
          onChange={e => onMinChange(e.target.value)}
          style={{
            ...inputBase,
            border: `1px solid ${minErr || crossErr ? 'var(--danger)' : 'var(--border-strong)'}`,
          }}
        />
        <span style={{ color: 'var(--text-secondary)', fontSize: '13px', userSelect: 'none' }}>—</span>
        <input
          type="text"
          inputMode="numeric"
          value={maxVal}
          placeholder="mm:ss"
          disabled={disabled}
          aria-label={labelMax}
          aria-describedby={hasError ? errorId : undefined}
          onChange={e => onMaxChange(e.target.value)}
          style={{
            ...inputBase,
            border: `1px solid ${maxErr || crossErr ? 'var(--danger)' : 'var(--border-strong)'}`,
          }}
        />
      </span>
      {hasError && (
        <span
          id={errorId}
          role="alert"
          style={{ fontSize: '11px', color: 'var(--danger)', marginTop: '2px' }}
        >
          {errMsg}
        </span>
      )}
    </span>
  )
}

// React.memo: evita re-render cuando NoiseTab re-renderiza por cambio de estado del drawer.
// config, loading, onSaved y worldId no cambian al abrir/cambiar de destino.
export const NoiseConfigPanel = memo(function NoiseConfigPanel({ config, loading, onSaved, worldId }) {
  const { t } = useI18n()
  const [expanded, setExpanded] = useState(false)
  const panelId = useId()

  // Estado local en MM:SS (los inputs trabajan con strings)
  // null = usa config como fuente de verdad
  const [localMmss, setLocalMmss] = useState(null)
  const [saving, setSaving] = useState(false)
  const [toggleLoading, setToggleLoading] = useState(false)
  const [apiError, setApiError] = useState(null)

  // Datos efectivos en segundos (config es la fuente canónica en segundos)
  const effCfg = config ?? {}
  const noiseEnabled = effCfg.noise_enabled ?? false

  // Convertir config (segundos) a MM:SS para mostrar, si no hay edición local
  const hcMinDefault  = secondsToMmss(effCfg.hardcore_interval_min_seconds ?? 30)
  const hcMaxDefault  = secondsToMmss(effCfg.hardcore_interval_max_seconds ?? 90)
  const paMinDefault  = secondsToMmss(effCfg.passive_interval_min_seconds  ?? 180)
  const paMaxDefault  = secondsToMmss(effCfg.passive_interval_max_seconds  ?? 1200)
  const dwellMin      = effCfg.dwell_min_seconds ?? 2.0
  const dwellMax      = effCfg.dwell_max_seconds ?? 30.0

  // Los strings editables (local tiene precedencia)
  const hcMin = localMmss?.hcMin ?? hcMinDefault
  const hcMax = localMmss?.hcMax ?? hcMaxDefault
  const paMin = localMmss?.paMin ?? paMinDefault
  const paMax = localMmss?.paMax ?? paMaxDefault

  const isDirty = localMmss !== null

  // Validaciones globales: si algún campo tiene error, no se puede guardar
  function fieldError(mmssStr) {
    return validateMmss(mmssStr, MIN_INTERVAL_SECONDS)
  }
  function crossError(minStr, maxStr) {
    if (fieldError(minStr) || fieldError(maxStr)) return true
    try {
      return mmssToSeconds(minStr) > mmssToSeconds(maxStr)
    } catch (_) { return true }
  }

  const hasError = (
    fieldError(hcMin) !== null ||
    fieldError(hcMax) !== null ||
    crossError(hcMin, hcMax) ||
    fieldError(paMin) !== null ||
    fieldError(paMax) !== null ||
    crossError(paMin, paMax)
  )

  function patch(field, value) {
    setLocalMmss(prev => ({
      hcMin:  prev?.hcMin  ?? hcMinDefault,
      hcMax:  prev?.hcMax  ?? hcMaxDefault,
      paMin:  prev?.paMin  ?? paMinDefault,
      paMax:  prev?.paMax  ?? paMaxDefault,
      [field]: value,
    }))
  }

  async function handleToggle(newVal) {
    setToggleLoading(true)
    try {
      const updated = await api.putNoiseConfig(worldId, {
        noise_enabled: newVal,
      })
      setLocalMmss(null)
      onSaved(updated)
      showToast(newVal ? t('noise.config.enabled') + ' ✓' : t('noise.config.disabled') + ' ✓')
    } catch (e) {
      showToast(e instanceof ApiError ? e.detail : t('noise.config.saveError'))
    } finally {
      setToggleLoading(false)
    }
  }

  async function handleSave() {
    if (hasError || !isDirty || saving) return
    setSaving(true)
    setApiError(null)
    try {
      // Convertir MM:SS → segundos antes de enviar (RN-FW01)
      const body = {
        hardcore_interval_min_seconds: mmssToSeconds(hcMin),
        hardcore_interval_max_seconds: mmssToSeconds(hcMax),
        passive_interval_min_seconds:  mmssToSeconds(paMin),
        passive_interval_max_seconds:  mmssToSeconds(paMax),
        dwell_min_seconds: dwellMin,
        dwell_max_seconds: dwellMax,
      }
      const updated = await api.putNoiseConfig(worldId, body)
      setLocalMmss(null)
      onSaved(updated)
      showToast(t('noise.config.saved'))
    } catch (e) {
      setApiError(e instanceof ApiError ? e.detail : t('noise.config.saveError'))
    } finally {
      setSaving(false)
    }
  }

  function handleCancel() {
    setLocalMmss(null)
    setApiError(null)
  }

  return (
    <div style={{
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-md)',
      marginBottom: '16px',
    }}>
      <style>{PANEL_ANIM}</style>

      {/* Cabecera siempre visible */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '10px',
        padding: '10px 14px',
        cursor: 'pointer',
        userSelect: 'none',
      }}>
        {/* Botón colapsable */}
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={panelId}
          onClick={() => setExpanded(v => !v)}
          style={{
            appearance: 'none', border: 'none', background: 'transparent',
            cursor: 'pointer', padding: 0,
            display: 'flex', alignItems: 'center', gap: '8px',
            fontFamily: 'inherit', fontSize: '14px', fontWeight: 500,
            color: 'var(--text)',
            flex: 1,
          }}
        >
          <span aria-hidden="true" style={{
            fontSize: '10px', color: 'var(--text-tertiary)',
            transition: 'transform 220ms ease',
            transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)',
            display: 'inline-block', width: '14px', textAlign: 'center',
          }}>
            ▶
          </span>
          {t('noise.config.title')}
        </button>

        {/* Badge estado — siempre visible */}
        {loading ? (
          <span style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>…</span>
        ) : (
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: '4px',
            fontSize: '12px', fontWeight: 500,
            color: noiseEnabled ? 'var(--success)' : 'var(--text-tertiary)',
            background: noiseEnabled ? 'rgba(36,138,61,.10)' : 'var(--surface-2)',
            borderRadius: 'var(--radius-full)',
            padding: '2px 8px',
          }}>
            {noiseEnabled ? t('noise.config.enabled') : t('noise.config.disabled')}
          </span>
        )}

        {/* Toggle — siempre visible */}
        <Toggle
          checked={noiseEnabled}
          onChange={handleToggle}
          disabled={loading || saving}
          loading={toggleLoading}
          label={noiseEnabled ? t('noise.config.enabled') : t('noise.config.disabled')}
        />
      </div>

      {/* Cuerpo colapsable */}
      {expanded && (
        <div
          id={panelId}
          className="noise-config-body"
          style={{
            borderTop: '1px solid var(--border)',
            padding: '16px 14px',
            animation: 'noise-config-expand 220ms ease',
          }}
        >
          {loading ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-tertiary)', fontSize: '13px' }}>
              <Spinner size={13} /> {t('noise.config.loading')}
            </div>
          ) : (
            <>
              {/* HARDCORE — intervalo MM:SS mín – máx */}
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '8px' }}>
                  {t('noise.config.hardcoreLabel')}
                  <span style={{ fontWeight: 400, color: 'var(--text-tertiary)', marginInlineStart: '6px' }}>
                    (MM:SS)
                  </span>
                </label>
                <MmssMinMaxInput
                  minVal={hcMin}
                  maxVal={hcMax}
                  onMinChange={v => patch('hcMin', v)}
                  onMaxChange={v => patch('hcMax', v)}
                  disabled={saving}
                  labelMin={t('noise.config.hardcoreLabel') + ' — mínimo (mm:ss)'}
                  labelMax={t('noise.config.hardcoreLabel') + ' — máximo (mm:ss)'}
                  errorId="err-hardcore"
                />
              </div>

              {/* PASIVO — intervalo MM:SS mín – máx */}
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '8px' }}>
                  {t('noise.config.passiveLabel')}
                  <span style={{ fontWeight: 400, color: 'var(--text-tertiary)', marginInlineStart: '6px' }}>
                    (MM:SS)
                  </span>
                </label>
                <MmssMinMaxInput
                  minVal={paMin}
                  maxVal={paMax}
                  onMinChange={v => patch('paMin', v)}
                  onMaxChange={v => patch('paMax', v)}
                  disabled={saving}
                  labelMin={t('noise.config.passiveLabel') + ' — mínimo (mm:ss)'}
                  labelMax={t('noise.config.passiveLabel') + ' — máximo (mm:ss)'}
                  errorId="err-passive"
                />
              </div>

              {/* DWELL — en segundos (sin cambio) */}
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '8px' }}>
                  {t('noise.config.dwellLabel')} ({t('noise.config.dwellUnit')})
                </label>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                  <input
                    type="number"
                    min="0.5"
                    step="0.5"
                    value={dwellMin}
                    disabled
                    aria-label={t('noise.config.dwellLabel') + ' mín'}
                    style={{
                      width: '72px', padding: '4px 6px',
                      border: '1px solid var(--border-strong)',
                      borderRadius: 'var(--radius-sm)',
                      background: 'var(--surface)', color: 'var(--text)',
                      fontFamily: 'var(--font-mono)', fontSize: '13px',
                      fontVariantNumeric: 'tabular-nums',
                      minHeight: '32px', textAlign: 'center',
                      opacity: 0.6,
                    }}
                  />
                  <span style={{ color: 'var(--text-secondary)', fontSize: '13px', userSelect: 'none' }}>—</span>
                  <input
                    type="number"
                    min="0.5"
                    step="0.5"
                    value={dwellMax}
                    disabled
                    aria-label={t('noise.config.dwellLabel') + ' máx'}
                    style={{
                      width: '72px', padding: '4px 6px',
                      border: '1px solid var(--border-strong)',
                      borderRadius: 'var(--radius-sm)',
                      background: 'var(--surface)', color: 'var(--text)',
                      fontFamily: 'var(--font-mono)', fontSize: '13px',
                      fontVariantNumeric: 'tabular-nums',
                      minHeight: '32px', textAlign: 'center',
                      opacity: 0.6,
                    }}
                  />
                </span>
                <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', display: 'block', marginTop: '4px' }}>
                  {t('noise.config.dwellReadOnly')}
                </span>
              </div>

              {/* Hint anti-detección (P3 — oculto en móvil) */}
              <p className="noise-antid-hint" style={{
                fontSize: '11px', color: 'var(--text-tertiary)',
                fontStyle: 'italic', marginBottom: '12px',
              }}>
                {t('noise.config.antiDetectionHint')}
              </p>

              {/* Error de API (incl. 422) */}
              {apiError && (
                <p role="alert" style={{ fontSize: '12px', color: 'var(--danger)', marginBottom: '10px' }}>
                  {apiError}
                </p>
              )}

              {/* Footer */}
              <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                {isDirty && (
                  <button
                    type="button"
                    onClick={handleCancel}
                    disabled={saving}
                    style={{
                      height: '32px', padding: '0 14px',
                      border: '1px solid var(--border-strong)',
                      background: 'var(--surface)', color: 'var(--text-secondary)',
                      borderRadius: 'var(--radius-sm)',
                      fontFamily: 'inherit', fontSize: '13px',
                      cursor: 'pointer',
                    }}
                  >
                    {t('noise.config.cancel')}
                  </button>
                )}
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={!isDirty || hasError || saving}
                  style={{
                    height: '32px', padding: '0 14px',
                    border: 'none',
                    background: (!isDirty || hasError || saving) ? 'var(--surface-2)' : 'var(--btn-primary-bg)',
                    color: (!isDirty || hasError || saving) ? 'var(--text-disabled)' : 'var(--btn-primary-text)',
                    borderRadius: 'var(--radius-sm)',
                    fontFamily: 'inherit', fontSize: '13px', fontWeight: 500,
                    cursor: (!isDirty || hasError || saving) ? 'not-allowed' : 'pointer',
                    display: 'flex', alignItems: 'center', gap: '6px',
                    transition: 'background var(--dur-fast)',
                  }}
                >
                  {saving && <Spinner size={12} />}
                  {saving ? t('noise.config.saving') : t('noise.config.save')}
                </button>
              </div>
            </>
          )}
        </div>
      )}

      <style>{`
        @media (max-width: 767px) { .noise-antid-hint { display: none; } }
      `}</style>
    </div>
  )
})
