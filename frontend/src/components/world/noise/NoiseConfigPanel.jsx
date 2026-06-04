/**
 * NoiseConfigPanel — Panel colapsable de configuración global de ruido.
 *
 * Props:
 *  - config    {object|null}  — datos de EP-N01 ({noise_enabled, hardcore_*, passive_*, dwell_*})
 *  - loading   {boolean}
 *  - onSaved   {Function}     — fn(newConfig) — callback tras guardar con éxito
 *  - worldId   {number}
 *
 * Comportamiento:
 *  - Toggle noise_enabled → PUT EP-N02 inmediato, sin "Guardar"
 *  - "Guardar config" → PUT EP-N02 con los 6 campos numéricos
 *  - El toggle siempre visible aunque el panel esté colapsado
 *  - Panel colapsable con transición max-height
 *  - Respeta prefers-reduced-motion
 *
 * Spec: docs/design/noise-catalog-ui.md §6, §7
 */
import { useState, useId, memo } from 'react'
import { useI18n } from '../../../i18n/index.jsx'
import { api, ApiError } from '../../../api/client.js'
import { Spinner, showToast } from '../../ui/uiUtils.jsx'
import { Toggle } from '../../ui/Toggle.jsx'
import { MinMaxInput } from '../../ui/MinMaxInput.jsx'

const PANEL_ANIM = `
  @keyframes noise-config-expand {
    from { opacity: 0; transform: translateY(-4px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  @media (prefers-reduced-motion: reduce) {
    .noise-config-body { animation: none !important; transition: none !important; }
  }
`

// React.memo: evita re-render cuando NoiseTab re-renderiza por cambio de estado del drawer.
// config, loading, onSaved y worldId no cambian al abrir/cambiar de destino.
export const NoiseConfigPanel = memo(function NoiseConfigPanel({ config, loading, onSaved, worldId }) {
  const { t } = useI18n()
  const [expanded, setExpanded] = useState(false)
  const panelId = useId()

  // Estado local de los 6 campos numéricos
  const [local, setLocal] = useState(null) // null = usa config como fuente
  const [saving, setSaving] = useState(false)
  const [toggleLoading, setToggleLoading] = useState(false)
  const [apiError, setApiError] = useState(null)

  // Datos efectivos (local tiene precedencia cuando existe)
  const eff = local ?? config ?? {}

  const hardcoreMin    = eff.hardcore_total_req_per_hour_min  ?? 80
  const hardcoreMax    = eff.hardcore_total_req_per_hour_max  ?? 150
  const passiveMin     = eff.passive_total_req_per_hour_min   ?? 15
  const passiveMax     = eff.passive_total_req_per_hour_max   ?? 40
  const dwellMin       = eff.dwell_min_seconds                ?? 2.0
  const dwellMax       = eff.dwell_max_seconds                ?? 30.0
  const noiseEnabled   = eff.noise_enabled                    ?? false

  const isDirty = local !== null
  const hasError = (
    hardcoreMax < hardcoreMin ||
    passiveMax  < passiveMin  ||
    dwellMax    < dwellMin
  )

  function patch(field, value) {
    setLocal(prev => ({
      ...(prev ?? config ?? {}),
      [field]: value,
    }))
  }

  async function handleToggle(newVal) {
    setToggleLoading(true)
    try {
      const updated = await api.putNoiseConfig(worldId, {
        ...(config ?? {}),
        ...(local ?? {}),
        noise_enabled: newVal,
      })
      setLocal(null)
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
      const updated = await api.putNoiseConfig(worldId, {
        ...(config ?? {}),
        noise_enabled:                       noiseEnabled,
        hardcore_total_req_per_hour_min:     hardcoreMin,
        hardcore_total_req_per_hour_max:     hardcoreMax,
        passive_total_req_per_hour_min:      passiveMin,
        passive_total_req_per_hour_max:      passiveMax,
        dwell_min_seconds:                   dwellMin,
        dwell_max_seconds:                   dwellMax,
      })
      setLocal(null)
      onSaved(updated)
      showToast(t('noise.config.saved'))
    } catch (e) {
      setApiError(e instanceof ApiError ? e.detail : t('noise.config.saveError'))
    } finally {
      setSaving(false)
    }
  }

  function handleCancel() {
    setLocal(null)
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
              {/* HARDCORE */}
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '8px' }}>
                  {t('noise.config.hardcoreLabel')}
                </label>
                <MinMaxInput
                  minVal={hardcoreMin}
                  maxVal={hardcoreMax}
                  onMinChange={v => patch('hardcore_total_req_per_hour_min', v)}
                  onMaxChange={v => patch('hardcore_total_req_per_hour_max', v)}
                  disabled={saving}
                  step={1}
                  minLimit={1}
                  labelMin={t('noise.config.hardcoreLabel') + ' mín'}
                  labelMax={t('noise.config.hardcoreLabel') + ' máx'}
                  errorId="err-hardcore"
                />
              </div>

              {/* PASIVO */}
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '8px' }}>
                  {t('noise.config.passiveLabel')}
                </label>
                <MinMaxInput
                  minVal={passiveMin}
                  maxVal={passiveMax}
                  onMinChange={v => patch('passive_total_req_per_hour_min', v)}
                  onMaxChange={v => patch('passive_total_req_per_hour_max', v)}
                  disabled={saving}
                  step={1}
                  minLimit={1}
                  labelMin={t('noise.config.passiveLabel') + ' mín'}
                  labelMax={t('noise.config.passiveLabel') + ' máx'}
                  errorId="err-passive"
                />
              </div>

              {/* DWELL */}
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '8px' }}>
                  {t('noise.config.dwellLabel')} ({t('noise.config.dwellUnit')})
                </label>
                <MinMaxInput
                  minVal={dwellMin}
                  maxVal={dwellMax}
                  onMinChange={v => patch('dwell_min_seconds', v)}
                  onMaxChange={v => patch('dwell_max_seconds', v)}
                  disabled={saving}
                  step={0.5}
                  minLimit={0.5}
                  isFloat
                  labelMin={t('noise.config.dwellLabel') + ' mín'}
                  labelMax={t('noise.config.dwellLabel') + ' máx'}
                  errorId="err-dwell"
                />
              </div>

              {/* Hint anti-detección (P3 — oculto en móvil) */}
              <p className="noise-antid-hint" style={{
                fontSize: '11px', color: 'var(--text-tertiary)',
                fontStyle: 'italic', marginBottom: '12px',
              }}>
                {t('noise.config.antiDetectionHint')}
              </p>

              {/* Error de API */}
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
